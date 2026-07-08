from typing import Any

from pydantic import BaseModel, Field

from src.agents.prompt_manager import PromptManager


class AgentConfigSchema(BaseModel):
    name: str
    model: str
    provider: str
    base_url: str | None = None
    system_prompt_path: str | None = None
    system_prompt: str | None = None
    system_prompt_format: str | None = None
    user_prompt_path: str | None = None
    user_prompt: str | None = None
    user_prompt_format: str | None = None
    app_data_dir: str | None = None
    streaming: bool | None = None
    tools: list[str] = Field(default_factory=list)
    mcp_servers: dict[str, Any] = Field(default_factory=dict)

    def get_system_prompt(
        self, prompt_manager: PromptManager, variables: dict[str, Any] | None = None
    ) -> str:
        """Resolve and format the system prompt using PromptManager."""
        source = self.system_prompt_path or self.system_prompt
        if not source:
            return ""
        fmt = self.system_prompt_format or "f-string"
        return prompt_manager.load_prompt(source, variables=variables, format_style=fmt)

    def get_user_prompt(
        self, prompt_manager: PromptManager, variables: dict[str, Any] | None = None
    ) -> str:
        """Resolve and format the user prompt using PromptManager."""
        source = self.user_prompt_path or self.user_prompt
        if not source:
            return ""
        fmt = self.user_prompt_format or "f-string"
        return prompt_manager.load_prompt(source, variables=variables, format_style=fmt)


class AgentYamlConfig(BaseModel):
    agent: AgentConfigSchema
