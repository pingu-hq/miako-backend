from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class WorkflowSetting(BaseSettings):
    GROQ_API_KEY: SecretStr
    CLIENT_USER: SecretStr
    CLIENT_PASSWORD: SecretStr
    CLIENT_SERVER_NAME: SecretStr
    CLIENT_URI: SecretStr
    CLIENT_TOKEN: SecretStr
    COHERE_API_KEY: SecretStr
    SECRET_KEY: SecretStr
    AZURE_PROJECT_ENDPOINT: SecretStr
    AGENT_NAME_1: str
    AGENT_VERSION_1: str
    HELLO_WORLD: str

    @property
    def KOKOMI_AGENT(self) -> dict[str, dict[str, str]]:
        return self._create_agent_ref(name=self.AGENT_NAME_1, version=self.AGENT_VERSION_1)

    @staticmethod
    def _create_agent_ref(name:str, version:str):
        return {"agent_reference": {"name": name, "version": version, "type": "agent_reference"}}


    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

workflow_settings = WorkflowSetting()

