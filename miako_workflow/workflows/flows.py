import asyncio
import json
import uuid
from typing import Any
from crewai.flow import Flow, start, listen
from pydantic import BaseModel, ConfigDict
from miako_workflow.memory.short_term_memory.message_cache import MessageStorageV1
from miako_workflow.prompts.prompt_library import PromptLibrary
from fastapi import status, HTTPException
from miako_workflow.workflows.steps.language_step import LanguageFlow
from miako_workflow.workflows.steps.intent_step import IntentFlow
from miako_workflow.config_files.config import workflow_settings
from openai import AsyncOpenAI


prompts = PromptLibrary()
azure_client_async: AsyncOpenAI | None = None


class EngineStates(BaseModel):
    input_message: str = ""
    language_layer_handler: dict[str, Any] = {}
    model_config = ConfigDict(arbitrary_types_allowed=True)


class _AdaptiveChatbotEngine(Flow[EngineStates]):
    def __init__(self, user_id: str | uuid.UUID | Any,  **kwargs: Any):
        super().__init__(**kwargs)
        self.user_id = user_id
        self.message_storage = MessageStorageV1(user_id=user_id)

    @property
    def azure_client(self):
        global azure_client_async
        if azure_client_async is None:
            _api_key, _openai_endpoint, _ = workflow_settings.get_azure_credentials

            azure_client_async = AsyncOpenAI(
                api_key=_api_key.get_secret_value(),
                base_url=_openai_endpoint.get_secret_value()
            )
        return azure_client_async

    async def deepseek_chat(self, instructions: str | None, input_message: str):


        deployment_name = "DeepSeek-R1-0528"
        messages = []
        if instructions and isinstance(instructions, str):
            messages.append({"role": "system", "content": instructions})

        messages.append({"role": "user", "content": input_message})

        _response = await self.azure_client.chat.completions.create(
            model=deployment_name,
            messages=messages,
        )
        return _response.choices[0].message.content


    @start()
    async def safety_content_moderator(self):
        pass #For development only, assume there is a content moderator here.


    @listen(safety_content_moderator)
    async def language_layer(self) -> dict[str, Any]:
        language_flow = LanguageFlow(
            user_id=self.user_id,
            original_message=self.state.input_message,
            message_storage=self.message_storage
        )
        response = await language_flow.run()
        self.state.language_layer_handler = response
        return response

    @listen(language_layer)
    async def intent_classifier(self, translation_response: dict[str, Any]) ->Exception | str:
        intent_flow = IntentFlow(
            user_id=self.user_id,
            input_data_obj=translation_response,
            message_storage=self.message_storage
        )
        response = await intent_flow.run()
        return response

    @listen(intent_classifier)
    async def final_answer_test(self, data: Exception | str):
        global prompts
        if isinstance(data, Exception):
            return Exception(str(data))

        _input = self.state.language_layer_handler
        user_original_input = _input.get("original_text")
        user_translated_input = _input.get("translated_text")
        language_used_input = _input.get("source_language")
        memory = await self.message_storage.get_messages(include_metadata=True)
        conversation_history = json.dumps(memory)
        user_prompt_template = prompts.user_prompt_template_v3
        user_prompt = await user_prompt_template.render_async(
            conversation_history=conversation_history,
            intent_classifier_json_output=data,
            user_original_input=user_original_input,
            user_translated_input=user_translated_input,
            source_language=language_used_input
        )

        response = await self.deepseek_chat(prompts.system_prompt_v3, user_prompt)
        print(user_prompt)
        await self.message_storage.add_ai_message(content=response)
        return response




class AdaptiveChatbot:
    def __init__(self, user_id: str | uuid.UUID | Any, input_message: str):
        self.user_id = user_id
        self._engine: Flow[BaseModel] | None = None
        self._all_input_data = {
            "input_user_id": user_id,
            "input_message": input_message,
        }


    @property
    def flow_engine(self) -> Flow[BaseModel]:
        if self._engine is None:
            self._engine = _AdaptiveChatbotEngine(user_id=self.user_id)
        return self._engine

    @property
    def _input_data(self):
        return self._all_input_data

    async def run(self) -> Any | str | None:
        try:
            response= await self.flow_engine.kickoff_async(inputs=self._input_data)
            if response is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Bad Request: {str(response)}")
            # print("SSSSSSSSSSTART", response, "EEEEEEEEEEEEEEEND")
            # await self.message_storage.add_ai_message("TESTHING IF IF WORKS")
            # await self.message_storage.add_ai_message(response)
            return response
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

# chat = AdaptiveChatbot(
#     user_id="chat_id",
#     input_message="Uy may gusto ako tanungin sayo beh, sino at ano ba si miako? like product ba sya?"
# )
# output=asyncio.run(chat.run())
# print(output)