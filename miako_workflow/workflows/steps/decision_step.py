import asyncio
import time
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
                client_id=workflow_settings.AZURE_CLIENT_ID,
                tenant_id=workflow_settings.AZURE_TENANT_ID,
                client_secret=workflow_settings.AZURE_CLIENT_SECRET
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
            client_id=workflow_settings.AZURE_CLIENT_ID,
            tenant_id=workflow_settings.AZURE_TENANT_ID,
            client_secret=workflow_settings.AZURE_CLIENT_SECRET
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


# async def main_test_run():
#     user_id = "test_user_123"
#     # decision = DecisionAzureFlow(user_id)
#     start_conv = time.perf_counter()
#     message_1 = "Hello my name is alpapi, whats your name?"
#     decision = DecisionStepAzure(user_id=user_id, input_message=message_1)
#
#     resp_1 = await decision.execute_agent()
#     mid_conv = time.perf_counter()
#     print(f"INPUT: {message_1}\nOUTPUT: {resp_1}\n\n TIME: {mid_conv - start_conv}")
#     message_2 = "Do you remember me?"
#     decision_2 = DecisionStepAzure(user_id=user_id, input_message=message_2)
#     resp_2 = await decision_2.execute_agent()
#     print(f"INPUT: {message_2}\nOUTPUT: {resp_2}\n\n TIME: {time.perf_counter() - mid_conv}")
#
#
# asyncio.run(main_test_run())
#
#
# async def main_test_run_loop():
#     user_id = "test_user_123"
#     while True:
#         _input_message = input(f"\n---\n\nUser ID: {user_id}\nInput message: ")
#
#         exiting_keywords = ["exit","quit", "done"]
#         if _input_message in exiting_keywords:
#             break
#         _start_time = time.perf_counter()
#         dec_obj = DecisionStepAzure(user_id=user_id, input_message=_input_message)
#         _resp = await dec_obj.execute_agent()
#         mid_conv = time.perf_counter()
#         print(f"Output: {_resp}\n\n TIME: {mid_conv - _start_time}")
#
#     print("Ending loop")
#
# asyncio.run(main_test_run_loop())