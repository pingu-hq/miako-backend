import time
import asyncio
from dataclasses import dataclass
from openai import OpenAI
from miako_workflow.config_files.config import workflow_settings
from azure.ai.projects import AIProjectClient
from azure.identity import ClientSecretCredential
from azure.core.exceptions import HTTPResponseType



@dataclass(slots=False)
class StateHolder:
    conversation_id: str | None = None
    async_lock: asyncio.Lock | None = None

_openai_client: OpenAI | None = None
_main_lock = asyncio.Lock()
_data_state_holder:  dict[str, StateHolder] = {}


class AzureChatResponseBase:
    def __init__(self, user_id: str, input_message: str, extra_body: dict | None = None):
        self.user_id = user_id
        self.input_message = input_message
        self.main_lock = _main_lock
        self.state_holder = _data_state_holder
        self.extra_body = extra_body or {}

    def get_openai_client_synchronous(self) -> OpenAI | None:
        try:
            _credential = self.get_azure_credential()
            _project_client = self.get_azure_ai_project_client(_credential)
            return _project_client.get_openai_client()
        except HTTPResponseType as http_err:
            return None
        except Exception as err:
            raise err

    @property
    def azure_client(self):
        global _openai_client
        if _openai_client is None:
            _openai_client = self.get_openai_client_synchronous()

        if _openai_client is None:
            _openai_client = self.get_openai_client_synchronous()

        return _openai_client

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

    async def get_current_user_state(self, user_id: str):
        async with self.main_lock:
            if user_id not in self.state_holder:
                self.state_holder[user_id] = StateHolder(
                    conversation_id=None,
                    async_lock=asyncio.Lock(),
                )
            return self.state_holder[user_id]

    def create_conversation_in_synchronous(self):
        conv = self.azure_client.conversations.create()
        return conv.id

    async def get_conversation_id(self):
        return await asyncio.to_thread(self.create_conversation_in_synchronous)


    def create_response_in_synchronous(self, conversation_id: str, input_message: str):
        response = self.azure_client.responses.create(
            input=input_message,
            conversation=conversation_id,
            extra_body=self.extra_body
        )
        return response.output_text

    async def agent_response_async(self, conversation_id: str, input_message: str):
        return await asyncio.to_thread(
            self.create_response_in_synchronous,
            conversation_id,
            input_message
        )

    async def final_agent_response_with_safety(self, user_id: str, input_message: str):
        data_state = await self.get_current_user_state(user_id=user_id)
        async with data_state.async_lock:
            if not data_state.conversation_id:
                conv_id = await self.get_conversation_id()
                print("MAKING NEW CONVERSATION ID")
                data_state.conversation_id = conv_id
            else:
                print("REUSING CONVERSATION ID")
                conv_id = data_state.conversation_id

            response = await self.agent_response_async(conversation_id=conv_id, input_message=input_message)
            return response

    async def execute(self):
        try:
            return await self.final_agent_response_with_safety(
                user_id=self.user_id,
                input_message=self.input_message
            )
        except Exception as ex:
            raise ex


class KokomiChatResponse:
    def __init__(self, user_id: str, input_message: str):
        self.chat_object = AzureChatResponseBase(
            user_id=user_id,
            input_message=input_message,
            extra_body=workflow_settings.KOKOMI_AGENT
        )

    async def run_agent(self):
        try:
            response = await self.chat_object.execute()
            return response
        except Exception as ex:
            raise ex

# async def run_the_draft():
#     user_id = "test_user"
#     user_id_2 = "new_test_user"
#     message_1 = "Hello my name is alpapi, whats yours?"
#     message_2 = "Do you remember whats my name?"
#     time_1 = time.monotonic()
#
#     resp_obj_1 = KokomiChatResponse(user_id, message_1)
#     resp_1 = await resp_obj_1.run_agent()
#     print(message_1)
#     print(resp_1)
#
#     time_2 = time.monotonic()
#     print(f"Time taken by 1st message: {time_2 - time_1}")
#
#     resp_obj_2 = KokomiChatResponse(user_id, message_2)
#     resp_2 = await resp_obj_2.run_agent()
#     print(message_2)
#     print(resp_2)
#
#
#
#     time_3 = time.monotonic()
#     print(f"Time taken by 2nd message: {time_3 - time_2}")
#
#
#     resp_obj_3 = KokomiChatResponse(user_id=user_id_2, input_message=message_1)
#     resp_3 = await resp_obj_3.run_agent()
#     print(message_1)
#     print(resp_3)
#     time_4 = time.monotonic()
#     print(f"Time taken by 3rd message: {time_4 - time_3}")
#
#     resp_obj_4 = KokomiChatResponse(user_id_2, message_2)
#     resp_4 = await resp_obj_4.run_agent()
#     print(message_2)
#     print(resp_4)
#     time_5 = time.monotonic()
#     print(f"Time taken by 4th message: {time_5 - time_4}")
#
# asyncio.run(run_the_draft())