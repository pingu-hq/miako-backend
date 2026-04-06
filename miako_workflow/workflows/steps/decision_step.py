import time
import asyncio
from dataclasses import dataclass, field
from threading import Lock
from openai import OpenAI
from miako_workflow.config_files.config import workflow_settings
from azure.ai.projects import AIProjectClient
from azure.identity import ClientSecretCredential
from cachetools import TTLCache, LRUCache



AZURE_USER_TTL_CACHE = TTLCache(maxsize=100, ttl=3600)
_AZURE_OPENAI_CLIENT = LRUCache(maxsize=1)
CLIENT_LOCK = Lock()



@dataclass(slots=False)
class UserState:
    conversation_id: str | None = None
    last_reset_time: float = field(default=0)
    _async_lock: asyncio.Lock | None = None

    @property
    def async_lock(self):
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        return self._async_lock

class AzureChatResponse:
    def __init__(self,user_id: str, input_message: str):
        self.user_id = user_id
        self.input_message = input_message
        self.openai_client = self.testing_reconnection_and_stateful_client()
        self.ttl_cache = AZURE_USER_TTL_CACHE

    async def getting_response(self):
        conv_id = await self.get_conversation_id()
        return await asyncio.to_thread(self._getting_response, conv_id)

    def _getting_response(self, session_id: str):
        __response = self.openai_client.responses.create(
            conversation=session_id,
            input=self.input_message,
            extra_body=workflow_settings.KOKOMI_AGENT
        )
        return __response.output_text

    def _getting_conversation_id(self):
        conv = self.openai_client.conversations.create()
        return conv.id

    async def get_conversation_id(self):
        return await asyncio.to_thread(self._getting_conversation_id)

    async def get_user_state(self):
        time_to_reset = 1800
        user: UserState = self.ttl_cache.get(self.user_id, None)
        time_now = time.monotonic()
        if user:
            user_last_reset_time = user.last_reset_time
            if time_now - user_last_reset_time > time_to_reset:
                user.last_reset_time = time_now
                self.ttl_cache[self.user_id] = user

            return self.ttl_cache[self.user_id]

        new_user = UserState()
        async with new_user.async_lock:
            conversation_id = await self.get_conversation_id()
            new_user.conversation_id = conversation_id
            new_user.last_reset_time = time_now
            self.ttl_cache[self.user_id] = new_user
            return new_user


    @staticmethod
    def _get_credential():
        return ClientSecretCredential(
            client_id=workflow_settings.AZURE_CLIENT_ID.get_secret_value(),
            tenant_id=workflow_settings.AZURE_TENANT_ID.get_secret_value(),
            client_secret=workflow_settings.AZURE_CLIENT_SECRET.get_secret_value()
        )

    @staticmethod
    def _get_project_client(credential):
        return AIProjectClient(
            credential=credential,
            endpoint=workflow_settings.AZURE_PROJECT_ENDPOINT.get_secret_value()
        )

    def get_client_for_openai_with_retry(self) -> OpenAI:
        try:
            _credential = self._get_credential()
            _project_client = self._get_project_client(_credential)
            return _project_client.get_openai_client()
        except Exception as ex:
            print(f"Reconnection -> Error: {ex}")

            try:
                _new_credential = self._get_credential()
                _new_project_client = self._get_project_client(_new_credential)
                return _new_project_client.get_openai_client()
            except Exception as ex:
                print(f"Unexpected error: {ex}")
                raise Exception("Internal Error")

    def testing_reconnection_and_stateful_client(self):
        try:
            _old_client: OpenAI = _AZURE_OPENAI_CLIENT.get(True, None)
            if isinstance(_old_client, OpenAI):
                return _old_client

            with CLIENT_LOCK:
                _AZURE_OPENAI_CLIENT[False] = "hello world"
                _client = self.get_client_for_openai_with_retry()
                _AZURE_OPENAI_CLIENT[True] = _client
                return _client

        except Exception as ex:
            raise ex
