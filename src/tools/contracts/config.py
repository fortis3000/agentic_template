"""Configuration protocols for tools and tool managers."""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ToolSettingsProtocol(Protocol):
    """Protocol for per-tool settings (e.g. retry configuration)."""

    @property
    def retry(self) -> Any | None: ...


@runtime_checkable
class AgentToolConfigProtocol(Protocol):
    """Protocol for agent configuration objects containing tool references."""

    @property
    def tools(self) -> list[str] | None: ...

    @property
    def mcp_servers(self) -> dict[str, Any] | None: ...

    @property
    def tool_settings(self) -> dict[str, Any] | None: ...

    @property
    def retry(self) -> Any | None: ...
