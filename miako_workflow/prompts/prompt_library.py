import yaml
import json
from typing import Dict, Union, Any
from abc import ABC, abstractmethod
from pathlib import Path
from llama_index.core.prompts import PromptTemplate
from jinja2 import Template
try:
    from importlib import resources
except ImportError:
    import importlib_resources as resources


class LoaderABC(ABC):
    def __init__(self, file_path: Union[str, None] = None):
        self.file_path = file_path

    @abstractmethod
    def _load_resources(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_prompt(self, key_path: str) -> str:
        pass


class LibraryLoader(LoaderABC):
    def __init__(self, file_path: Union[str, None] = None):
        super().__init__(file_path)
        self.base_dir = Path(__file__).parent
        self.data = self._load_resources()

    def _load_resources(self) -> Dict[str, Any]:
        try:
            full_path = self.base_dir/self.file_path
            with open(full_path, "r", encoding="utf-8") as file:
                return yaml.safe_load(file) or {}

        except (FileNotFoundError, yaml.YAMLError):
            return {}


    def get_prompt(self, key_path: str) -> str:
        data = self.data
        try:
            for keys in key_path.split("."):
                data = data[keys]

            if isinstance(data, (dict,list)):
                return json.dumps(data, indent=2, ensure_ascii=False)

            return str(data)

        except KeyError:
            return f"Error: key {key_path} not found in library"

    def create_template(self, key_path: str, **kwargs):
        template = self.get_prompt(key_path=key_path)
        template_obj = PromptTemplate(template=template)
        final_template = template_obj.format(**kwargs)
        return final_template


class BasePrompt:
    def __init__(self, yaml_file_name: Union[str, None] = None):
        self.data_source_path = f"data_sources/{yaml_file_name}"
        self.loader = LibraryLoader(file_path=self.data_source_path)

    def get_prompt(self, key_path: str) -> str:
        return self.loader.get_prompt(key_path=key_path)

class PromptLibrary(BasePrompt):
    def __init__(self):
        super().__init__("prompts.yaml")

    @property
    def system_prompt_v2(self):
        return self.get_prompt("v2.system-prompt")

    @property
    def user_prompt_v2(self):
        return self.get_prompt("v2.user-prompt")

    @property
    def user_prompt_template(self):
        return Template(self.user_prompt_v2, enable_async=True)

    @property
    def system_prompt_v3(self):
        return self.get_prompt("v3.system-prompt")

    @property
    def user_prompt_v3(self):
        return self.get_prompt("v3.user-prompt")

    @property
    def user_prompt_template_v3(self):
        return Template(self.user_prompt_v3, enable_async=True)


class LanguageLibrary(BasePrompt):
    def __init__(self):
        super().__init__("language.yaml")

class IntentLibrary(BasePrompt):
    def __init__(self):
        super().__init__("intent.yaml")

    @property
    def documentation_context(self):
        return self.get_prompt("documentation-context")

    @property
    def data_extractor_user_prompt_v1(self):
        return self.get_prompt("v1.data-extractor.user-prompt")

    @property
    def data_extractor_system_prompt_v1(self):
        return self.get_prompt("v1.data-extractor.system-prompt")

    @property
    def facts_validator_user_prompt_v1(self):
        return self.get_prompt("v1.facts-validator.user-prompt")

    @property
    def facts_validator_system_prompt_v1(self):
        return self.get_prompt("v1.facts-validator.system-prompt")
