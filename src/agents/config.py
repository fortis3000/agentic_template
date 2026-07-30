from typing import Any

from pydantic import BaseModel, Field, model_validator

from src.agents.prompt_manager import PromptManager
from src.utils.retry import RetryConfig


class ImageConstraints(BaseModel):
    acceptable_data_types: list[str] = Field(
        default_factory=lambda: ["image/png", "image/jpeg", "image/gif"]
    )
    max_image_width: int = 1024
    max_image_height: int = 1024
    min_image_width: int = 128
    min_image_height: int = 128


class FileConstraints(BaseModel):
    acceptable_file_types: list[str] = Field(
        default_factory=lambda: ["application/pdf", "text/plain", "text/markdown", "text/html"]
    )
    max_file_size_bytes: int = 20_971_520  # 20 MB
    max_files_per_message: int = 5


class McpServerConfigSchema(BaseModel):
    type: str = "stdio"  # "stdio" or "http"
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    timeout: float = 30.0
    sse_read_timeout: float = 300.0
    terminate_on_close: bool = True
    enabled_tools: list[str] | None = None
    disabled_tools: list[str] | None = None


class EmbeddingModelConfigSchema(BaseModel):
    provider: str
    model: str
    dimensions: int | None = None
    # Size of the collection's image vector. Required rather than inferred: it must match what the
    # configured model actually returns from embed_image, or every image search fails with a
    # Qdrant vector-dimension error.
    image_dimensions: int
    api_key: str | None = None
    base_url: str | None = None
    supported_data_types: list[str] = Field(default_factory=lambda: ["text"])


class VectorDBConfigSchema(BaseModel):
    type: str = "qdrant"
    host: str | None = None
    port: int | None = None
    url: str | None = None
    location: str | None = None
    api_key: str | None = None


class ToolSettingsSchema(BaseModel):
    retry: RetryConfig | None = None
    allowed_search_fields: list[str] = Field(default_factory=list)
    allowed_answer_fields: list[str] = Field(default_factory=list)


class AgentConfigSchema(BaseModel):
    name: str
    model: str | None = None
    provider: str = "google"
    api_key: str | None = None
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
    mcp_servers: dict[str, McpServerConfigSchema] = Field(default_factory=dict)
    embedding_model: EmbeddingModelConfigSchema | None = None
    tool_settings: dict[str, ToolSettingsSchema] = Field(default_factory=dict)
    retry: RetryConfig = Field(default_factory=RetryConfig)

    @model_validator(mode="before")
    @classmethod
    def normalize_mcp_servers(cls, data: Any) -> Any:
        if isinstance(data, dict):
            mcp_data = data.get("mcp_servers")
            if isinstance(mcp_data, list):
                new_mcp = {}
                for server in mcp_data:
                    name = server.get("name") or server.get("type", "stdio")
                    new_mcp[name] = server
                data["mcp_servers"] = new_mcp
        return data

    acceptable_data_types: list[str] = Field(
        default_factory=lambda: ["image/png", "image/jpeg", "image/gif"]
    )
    max_image_width: int = 1024
    max_image_height: int = 1024
    min_image_width: int = 128
    min_image_height: int = 128

    acceptable_file_types: list[str] = Field(
        default_factory=lambda: ["application/pdf", "text/plain", "text/markdown", "text/html"]
    )
    max_file_size_bytes: int = 20_971_520  # 20 MB
    max_files_per_message: int = 5

    @property
    def image_constraints(self) -> ImageConstraints:
        return ImageConstraints(
            acceptable_data_types=self.acceptable_data_types,
            max_image_width=self.max_image_width,
            max_image_height=self.max_image_height,
            min_image_width=self.min_image_width,
            min_image_height=self.min_image_height,
        )

    @property
    def file_constraints(self) -> FileConstraints:
        return FileConstraints(
            acceptable_file_types=self.acceptable_file_types,
            max_file_size_bytes=self.max_file_size_bytes,
            max_files_per_message=self.max_files_per_message,
        )

    @model_validator(mode="before")
    @classmethod
    def clean_retry(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "retry" in data and data["retry"] is None:
                data["retry"] = {}
        return data

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
