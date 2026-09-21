"""Configuration protocols for agents."""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AgentConfigProtocol(Protocol):
    """Protocol representing agent configuration metadata."""

    @property
    def name(self) -> str: ...

    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str | None: ...

    @property
    def system_prompt_path(self) -> str | None: ...

    @property
    def system_prompt(self) -> str | None: ...

    @property
    def tools(self) -> list[str] | None: ...

    @property
    def mcp_servers(self) -> dict[str, Any] | None: ...

    @property
    def tool_settings(self) -> dict[str, Any] | None: ...

    @property
    def retry(self) -> Any | None: ...
