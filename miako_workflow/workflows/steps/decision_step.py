import time
import asyncio
from dataclasses import dataclass
from openai import OpenAI
from miako_workflow.config_files.config import workflow_settings
from azure.ai.projects import AIProjectClient
from azure.identity import ClientSecretCredential




@dataclass(slots=False)
class StateHolder:
    conversation_id: str | None = None
    async_lock: asyncio.Lock | None = None

draft_openai_client: OpenAI | None = None
draft_main_lock = asyncio.Lock()
draft_sub_main_lock: dict[str, asyncio.Lock] = {}


class AzureChatResponseDraft:
    def __init__(self, user_id: str, input_message: str):
        self.user_id = user_id
        self.input_message = input_message
        self.main_lock = draft_main_lock
        self.sub_main_lock = draft_sub_main_lock

    def get_openai_client(self) -> OpenAI:
        try:
            _credential = self.get_azure_credential()
            _project_client = self.get_azure_ai_project_client(_credential)
            return _project_client.get_openai_client()
        except Exception as ex:
            print(f"Reconnection error: {str(ex)}")
            try:
                _new_credential = self.get_azure_credential()
                _new_project_client = self.get_azure_ai_project_client(_new_credential)
                return _new_project_client.get_openai_client()
            except Exception as rex:
                print(f"Unexpected error: {rex}")
                raise Exception("Internal Error")

    @staticmethod
    def get_azure_credential():
        return ClientSecretCredential(
            client_id=workflow_settings.AZURE_CLIENT_ID.get_secret_value(),
            tenant_id=workflow_settings.AZURE_TENANT_ID.get_secret_value(),
            client_secret=workflow_settings.AZURE_CLIENT_SECRET.get_secret_value()
        )

    @staticmethod
    def get_azure_ai_project_client(credential):
        return AIProjectClient(
            credential=credential,
            endpoint=workflow_settings.AZURE_PROJECT_ENDPOINT.get_secret_value()
        )

    async def get_user_lock(self, user_id: str):
        async with self.main_lock:
            if user_id not in self.sub_main_lock:
                self.sub_main_lock[user_id] = asyncio.Lock()
            return self.sub_main_lock[user_id]

    async def process_message_with_lock(self, user_id: str, input_message: str):
        user_lock = await self.get_user_lock(user_id=user_id)

        async with user_lock:
            conv_id = await asyncio.to_thread(self.get_conversation_id_synchronous)

    def get_conversation_id_synchronous(self):
        client = self.get_openai_client()
        conv = client.conversations.create()
        return conv.id




    # def core_response_api_synchronous(self, conversation_id: str, input_message: str):
    #
    #
