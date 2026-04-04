import asyncio
from posthog.ai.openai import OpenAI
from miako_workflow.config_files.config import workflow_settings
from azure.ai.projects import AIProjectClient
from azure.identity import ClientSecretCredential
from starlette.concurrency import run_in_threadpool
from dataclasses import dataclass
from functools import lru_cache


_azure_project_client: AIProjectClient | None = None
_azure_credential: ClientSecretCredential | None = None


def load_azure_ai_project():
    global _azure_project_client, _azure_credential
    try:
        if _azure_credential is None:
            _azure_credential = ClientSecretCredential(
                client_id=workflow_settings.AZURE_CLIENT_ID.get_secret_value(),
                tenant_id=workflow_settings.AZURE_TENANT_ID.get_secret_value(),
                client_secret=workflow_settings.AZURE_CLIENT_SECRET.get_secret_value()
            )

        if _azure_project_client is None:
            _azure_project_client = AIProjectClient(
                credential=_azure_credential,
                endpoint=workflow_settings.AZURE_PROJECT_ENDPOINT.get_secret_value()
            )
        return _azure_project_client.get_openai_client()
    except Exception:
        _azure_credential = None
        _azure_project_client = None

        try:
            _azure_credential = ClientSecretCredential(
                client_id=workflow_settings.AZURE_CLIENT_ID.get_secret_value(),
                tenant_id=workflow_settings.AZURE_TENANT_ID.get_secret_value(),
                client_secret=workflow_settings.AZURE_CLIENT_SECRET.get_secret_value()
            )
            _azure_project_client = AIProjectClient(
                credential=_azure_credential,
                endpoint=workflow_settings.AZURE_PROJECT_ENDPOINT.get_secret_value()
            )
            return _azure_project_client.get_openai_client()
        except Exception as ex:
            raise ex


_global_client: OpenAI = load_azure_ai_project()


def _getting_conversation_id():
    __conversation = _global_client.conversations.create()
    return __conversation.id

async def getting_conversation_id():
    return await run_in_threadpool(_getting_conversation_id)

def _getting_response(session_id: str, input_message: str):
    __response = _global_client.responses.create(
        conversation=session_id,
        input=input_message,
        extra_body=workflow_settings.KOKOMI_AGENT
    )
    return __response.output_text

async def getting_response(session_id: str, input_message: str):
    return await run_in_threadpool(func=_getting_response, session_id=session_id, input_message=input_message)



@dataclass(slots=False)
class UserAzureInfo:
    user_id: str | None = None
    conversation_id: str | None = None
    user_lock: asyncio.Lock = asyncio.Lock()


@lru_cache(maxsize=100)
def get_azure_user_info(user_id: str):
    return UserAzureInfo(user_id=user_id)



class DecisionStepAzure:
    def __init__(self, user_id: str, input_message: str):
        self.state = get_azure_user_info(user_id=user_id)
        self._input_message = input_message

    @property
    def message(self):
        return self._input_message


    async def conversation_session_id(self):
        if self.state.conversation_id is None:
            _id = await getting_conversation_id()
            self.state.conversation_id = _id
        return self.state.conversation_id

    async def execute_agent(self):
        session_id = await self.conversation_session_id()
        lock = self.state.user_lock
        async with lock:
            response = await getting_response(
                input_message=self.message,
                session_id=session_id
            )
            return response


from abc import ABC, abstractmethod
from cachetools import LRUCache
import threading

CACHE_CLIENT = LRUCache(maxsize=1)
CACHE_LOCK = threading.Lock()




class AzureAgentBase(ABC):

    cache_client = LRUCache(maxsize=1)
    cache_lock = threading.Lock()

    def __init__(self):
        self._azure_credential = None

    @property
    def azure_ai_project(self):
        return AIProjectClient(
            credential=self.azure_credential,
            endpoint=workflow_settings.AZURE_PROJECT_ENDPOINT.get_secret_value()
        )

    @property
    def azure_credential(self):
        if self._azure_credential is None:
            self._azure_credential = ClientSecretCredential(
                client_id=workflow_settings.AZURE_CLIENT_ID.get_secret_value(),
                tenant_id=workflow_settings.AZURE_TENANT_ID.get_secret_value(),
                client_secret=workflow_settings.AZURE_CLIENT_SECRET.get_secret_value()
            )
        return self._azure_credential


    def azure_client(self, is_resetting: bool = False) -> OpenAI:

        with self.cache_lock:
            if is_resetting:
                self.cache_client.clear()

            if "default" not in self.cache_client:
                _client = self.azure_ai_project.get_openai_client()
                self.cache_client["default"] = _client

            return self.cache_client["default"]

    async def conversation_id(self):
        _azure_client = self.azure_client()
        _conv = await asyncio.to_thread(_azure_client.conversations.create)
        return _conv.id
