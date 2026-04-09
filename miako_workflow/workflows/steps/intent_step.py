import uuid
from typing import Any, List
from crewai.flow.flow import Flow, start, listen, router, or_
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from miako_workflow.llm.groq_llm import GroqLLM, MODEL
from miako_workflow.prompts.prompt_library import IntentLibrary
from miako_workflow.memory.short_term_memory.message_cache import MessageStorageV1
from miako_workflow.memory.knowledge_base.knowledge import HackathonRetrievalKnowledge
from jinja2 import Template
from dataclasses import dataclass
import asyncio
import json
import re

VECTOR = HackathonRetrievalKnowledge()



class Fact(BaseModel):
    confidence: float = Field(..., ge=0.0, le=1.0)
    topic: str
    fact: str
    relevance_reason: str

class ExtractionResponse(BaseModel):
    facts: List[Fact]
    message: str | None = None







@dataclass(slots=True)
class LanguageObject:
    translated_text: str
    original_text: str
    created_at: str
    source_language: str

class PromptsV1:
    def __init__(self):
        self._doc_context = None
        self._user_data_extractor_template = None
        self._intent_library = None
        self._system_data_extractor_prompt = None
        self._user_facts_validator_template = None
        self._system_facts_validator_prompt = None

    @property
    def intent(self):
        if self._intent_library is None:
            self._intent_library = IntentLibrary()
        return self._intent_library

    @property
    def documentation_context(self):
        if self._doc_context is None:
            self._doc_context = self.intent.documentation_context
        return self._doc_context

    @property
    def _get_user_data_extractor_template(self) -> Template:
        if self._user_data_extractor_template is None:
            _prompt = self.intent.data_extractor_user_prompt_v1
            _template = Template(_prompt, enable_async=True)
            self._user_data_extractor_template = _template
        return self._user_data_extractor_template

    @property
    def _get_user_facts_validator_template(self) -> Template:
        if self._user_facts_validator_template is None:
            _prompt = self.intent.facts_validator_user_prompt_v1
            _template = Template(_prompt, enable_async=True)
            self._user_facts_validator_template = _template
        return self._user_facts_validator_template

    @property
    def system_data_extractor(self) -> str:
        if self._system_data_extractor_prompt is None:
            self._system_data_extractor_prompt = self.intent.data_extractor_system_prompt_v1
        return self._system_data_extractor_prompt

    async def user_data_extractor(self, input_obj_data: dict[str, Any], history: MessageStorageV1) -> str:
        conversation_history = await history.get_messages(include_metadata=True)
        lang_obj = LanguageObject(**input_obj_data)
        query = lang_obj.translated_text + "" + lang_obj.original_text
        documentation_context = await VECTOR.show_knowledge(query=query)
        template = self._get_user_data_extractor_template
        user_prompt = await template.render_async(
            translated_text=lang_obj.translated_text,
            original_text=lang_obj.original_text,
            created_at=lang_obj.created_at,
            source_language=lang_obj.source_language,
            documentation_context=documentation_context,
            conversation_history=conversation_history
        )
        return user_prompt

    @property
    def system_facts_validator(self):
        if self._system_facts_validator_prompt is None:
            self._system_facts_validator_prompt = self.intent.facts_validator_system_prompt_v1
        return self._system_facts_validator_prompt


    async def user_facts_validator(self, extracted_data:str, history: MessageStorageV1, input_obj_data: dict[str, Any]) -> str:
        lang_obj = LanguageObject(**input_obj_data)
        _template = self._get_user_facts_validator_template
        conversation_history = await history.get_messages(include_metadata=True)
        user_prompt = await _template.render_async(
            translated_user_input=lang_obj.translated_text,
            conversation_history=conversation_history,
            extracted_data_context=extracted_data
        )
        return user_prompt

PROMPTS = PromptsV1()



class IntentFlowStates(BaseModel):
    user_id: str | uuid.UUID | Any = ""
    data_input: dict[str, Any] = {}
    data_extraction_handler: str = ""
    error_exception: Exception | str | None = None
    facts_validation_handler: str = ""

    model_config = ConfigDict(arbitrary_types_allowed=True)



class _IntentClassifier(Flow[IntentFlowStates]):
    def __init__(self, user_id: str | uuid.UUID | Any, message_storage: MessageStorageV1, **kwargs: Any):
        super().__init__(**kwargs)
        self.user_id = user_id
        self.message_storage = message_storage


    @property
    def groq_llm(self):
        return GroqLLM()

    @start
    async def prep_prompts(self) -> tuple[str, str]:
        system_prompt = PROMPTS.system_data_extractor
        user_prompt = await PROMPTS.user_data_extractor(
            input_obj_data=self.state.data_input,
            history=self.message_storage
        )
        return system_prompt, user_prompt

    @listen(prep_prompts)
    async def start_with_data_extraction(self, data_prompts: tuple[str, str]) -> str | Exception:
        try:
            system_prompt, user_prompt = data_prompts

            data_extraction_llm = self.groq_llm
            data_extraction_llm.add_system(system_prompt)
            data_extraction_llm.add_user(user_prompt)

            return await data_extraction_llm.groq_chat(
                model=MODEL.scout, temperature=.1,
                max_completion_tokens=8000
            )

        except Exception as ex:
            return ex

    @listen(start_with_data_extraction)
    def validating_extracted_data(self, input_data: str | Exception) -> str | None:
        if isinstance(input_data, Exception):
            self.state.error_exception = input_data
            return None

        if isinstance(input_data, str):
            is_valid, parsed_data, error = self._validating_data_extraction_response(input_data)

            if is_valid:
                return json.dumps(parsed_data)

            else:
                self.state.error_exception = error
                return None

        self.state.error_exception = "Unexpected error in validation"
        return None

    @listen(validating_extracted_data)
    def updating_states(self, data: str | None):
        if data is not None:
            self.state.data_extraction_handler = data
            return True
        else:
            return False


    @router(updating_states)
    def data_extraction_router(self, data: bool):

        if data:
            return "DATA_EXTRACTION_PASSED"
        else:
            return "DATA_EXTRACTION_ERROR"

    @listen("DATA_EXTRACTION_PASSED")
    async def generating_prompts_for_validator(self):
        try:
            extracted_data = self.state.data_extraction_handler
            user_prompt = await PROMPTS.user_facts_validator(
                history=self.message_storage,
                input_obj_data=self.state.data_input,
                extracted_data=extracted_data
            )
            system_prompt = PROMPTS.system_facts_validator
            return system_prompt, user_prompt
        except Exception as ex:
            return ex

    @listen("DATA_EXTRACTION_ERROR")
    def data_extraction_failure(self):
        return False


    @listen(generating_prompts_for_validator)
    async def facts_validator(self, _prompts: tuple[str, str] | Exception):
        if isinstance(_prompts, Exception):
            self.state.error_exception = _prompts
            return False
        try:
            system_prompt, user_prompt = _prompts
            llm = self.groq_llm
            llm.add_system(system_prompt)
            llm.add_user(user_prompt)
            facts_response = await llm.groq_chat(
                model=MODEL.gpt_oss_120,
                reasoning_effort="low",
                temperature=.1,
                max_completion_tokens=20_000
            )

            self.state.facts_validation_handler = facts_response
            return True

        except Exception as ex:
            self.state.error_exception = ex
            return False

    @router(facts_validator)
    def facts_validation_router(self, data):
        if data:
            return "FACTS_VALIDATED"
        else:
            return "FACTS_VALIDATION_ERROR"

    @listen("FACTS_VALIDATED")
    def facts_validation_passed(self):
        return True

    @listen("FACTS_VALIDATION_ERROR")
    def facts_validation_failure(self):
        return False


    @listen(or_(facts_validation_passed, facts_validation_failure, data_extraction_failure))
    def finalizing_output(self, is_passed: bool) -> Exception | str:
        if is_passed:
            return self.state.facts_validation_handler
        else:
            ex = Exception(f"Flow error output: {str(self.state.error_exception)}")
            return ex



    def _validating_data_extraction_response(self, input_str: str) -> tuple[bool, dict | None, str | None]:
        if not input_str:
            return False, None, "Empty LLM Response"

        try:
            data = json.loads(input_str)

        except json.JSONDecodeError:
            extracted = self.extract_json(input_str)

            if not extracted:
                return False, None, "No Json found in response"

            try:
                data = json.loads(extracted)
            except Exception as ex:
                return False, None, f"Json decode failed after extraction: {ex}"

        except Exception as _ex:
            return False, None, f"Unexpected error: {str(_ex)}"



        if data.get("message") in ['FORMAT_ERROR', 'NO_RELEVANT_CONTEXT']:
            return True, data, None


        try:
            ExtractionResponse.model_validate(data)
            return True, data, None

        except json.JSONDecodeError as je:
            return False, None, f"Invalid JSON: {je}"

        except ValidationError as ve:
            first_error = ve.errors()[0]
            field = ".".join(str(x) for x in first_error["loc"])
            return False, None, f"{field}: {first_error["msg"]}"



    @staticmethod
    def extract_json(text: str) -> str | None:
        if not text:
            return None
        text = text.strip()

        text = re.sub(r"```json\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"```", "", text)

        stack = []
        _start = None

        for i, char in enumerate(text):
            if char == "{":
                if _start is None:
                    _start = i
                stack.append("{")

            elif char == "}":
                if stack:
                    stack.pop()
                    if not stack and _start is not None:
                        return text[_start:i + 1]

        return None

class IntentFlow:
    def __init__(
            self,
            user_id: str | uuid.UUID | Any,
            input_data_obj: dict[str, Any],
            message_storage: MessageStorageV1
    ):
        self._flow: Flow[BaseModel] | None = None
        self._input = {
            "user_id":user_id,
            "data_input":input_data_obj,
        }
        self.user_id = user_id
        self.message_storage = message_storage

    @property
    def flow(self):
        if self._flow is None:
            self._flow = _IntentClassifier(
                user_id=self.user_id,
                message_storage=self.message_storage
            )
        return self._flow

    async def run(self):
        return await self.flow.kickoff_async(inputs=self._input)

#
# _metadata = {
#     "original_text": "original text test",
#     "created_at": "created at test",
#     "source_language": "source language test",
#     "translated_text": "translation text test"
# }
# # test_func = _PROMPTS.user_data_extractor(_metadata)
# # test_user_prompt = asyncio.run(test_func)
# # print(test_user_prompt)
#
#
# async def intent_flow():
#     _inputs = {
#         "user_id": str(uuid.uuid4()),
#         "data_input": _metadata
#     }
#     _intent = _InternalIntentClassifier()
#     _intent.plot()
#     return await _intent.kickoff_async(inputs=_inputs)
#
#
# test_flow_intent = asyncio.run(intent_flow())
# print(test_flow_intent)