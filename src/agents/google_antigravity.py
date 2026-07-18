import functools
import inspect
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Callable

import yaml
from google.antigravity import Agent as G_Agent
from google.antigravity import LocalAgentConfig
from google.antigravity.types import (
    Image as G_Image,
)
from google.antigravity.types import (
    McpStdioServer,
    McpStreamableHttpServer,
)
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry import trace

from src.agents.base import AgentInputPart, BaseAgent, BaseAgentGenerator, ImagePart, TextPart
from src.agents.prompt_manager import PromptManager
from src.tools.base import ToolFactory
from src.utils.logger import get_logger

logger = get_logger(__name__)


def trace_tool(tool_func: Callable[..., Any]) -> Callable[..., Any]:
    """Wraps a tool function with OpenTelemetry tracing using OpenInference conventions."""
    tool_name = getattr(tool_func, "__name__", "unknown_tool")
    tool_doc = getattr(tool_func, "__doc__", "") or ""
    if inspect.iscoroutinefunction(tool_func):

        @functools.wraps(tool_func)
        async def async_wrapped(*args: Any, **kwargs: Any) -> Any:
            tracer = trace.get_tracer("antigravity-agent")
            with tracer.start_as_current_span(
                name=tool_name,
                attributes={
                    SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.TOOL.value,
                    SpanAttributes.TOOL_NAME: tool_name,
                    SpanAttributes.TOOL_DESCRIPTION: tool_doc,
                    SpanAttributes.INPUT_VALUE: str({"args": args, "kwargs": kwargs}),
                },
            ) as span:
                try:
                    res = await tool_func(*args, **kwargs)
                    span.set_attribute(SpanAttributes.OUTPUT_VALUE, str(res))
                    return res
                except Exception as e:
                    span.set_status(trace.StatusCode.ERROR, str(e))
                    raise

        return async_wrapped
    else:

        @functools.wraps(tool_func)
        def sync_wrapped(*args: Any, **kwargs: Any) -> Any:
            tracer = trace.get_tracer("antigravity-agent")
            with tracer.start_as_current_span(
                name=tool_name,
                attributes={
                    SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.TOOL.value,
                    SpanAttributes.TOOL_NAME: tool_name,
                    SpanAttributes.TOOL_DESCRIPTION: tool_doc,
                    SpanAttributes.INPUT_VALUE: str({"args": args, "kwargs": kwargs}),
                },
            ) as span:
                try:
                    res = tool_func(*args, **kwargs)
                    span.set_attribute(SpanAttributes.OUTPUT_VALUE, str(res))
                    return res
                except Exception as e:
                    span.set_status(trace.StatusCode.ERROR, str(e))
                    raise

        return sync_wrapped


class AntigravityAgent(BaseAgent):
    """Google Antigravity SDK-based implementation of BaseAgent."""

    def __init__(
        self,
        config: LocalAgentConfig,
        prompt_manager: PromptManager,
        default_user_prompt_source: str | None = None,
        default_user_prompt_format: str = "f-string",
    ):
        """Initialize the AntigravityAgent.

        Args:
            config: The LocalAgentConfig used to instantiate the Antigravity Agent.
            prompt_manager: The PromptManager for resolving prompts.
            default_user_prompt_source: The default user prompt template source.
            default_user_prompt_format: The template format of the user prompt.
        """
        self.config = config
        self.prompt_manager = prompt_manager
        self.default_user_prompt_source = default_user_prompt_source
        self.default_user_prompt_format = default_user_prompt_format

    async def call(self, inputs: list[AgentInputPart] | str | dict[str, Any] | None = None) -> str:
        """Asynchronously call the agent.

        Args:
            inputs: Can be a list of input parts, a single prompt string, a dictionary
                    of variables to render the default user prompt template, or None.

        Returns:
            The final text response from the agent.
        """
        tracer = trace.get_tracer("antigravity-agent")
        model_name = str(self.config.model) if self.config.model else ""
        with tracer.start_as_current_span(
            name=f"{model_name or 'agent'} call",
            attributes={
                SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.AGENT.value,
                SpanAttributes.AGENT_NAME: model_name or "AntigravityAgent",
                SpanAttributes.INPUT_VALUE: str(inputs),
                SpanAttributes.LLM_MODEL_NAME: model_name,
            },
        ) as span:
            try:
                converted_inputs = self._prepare_inputs(inputs)
                async with G_Agent(config=self.config) as agent:
                    response = await agent.chat(converted_inputs)
                    res_text = await response.text()
                    span.set_attribute(SpanAttributes.OUTPUT_VALUE, res_text)
                    return res_text
            except Exception as e:
                span.set_status(trace.StatusCode.ERROR, str(e))
                raise

    async def call_stream(
        self, inputs: list[AgentInputPart] | str | dict[str, Any] | None = None
    ) -> AsyncIterator[str]:
        """Asynchronously call the agent and stream the response.

        Args:
            inputs: Can be a list of input parts, a single prompt string, a dictionary
                    of variables to render the default user prompt template, or None.

        Yields:
            Response chunks.
        """
        tracer = trace.get_tracer("antigravity-agent")
        model_name = str(self.config.model) if self.config.model else ""
        with tracer.start_as_current_span(
            name=f"{model_name or 'agent'} call_stream",
            attributes={
                SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.AGENT.value,
                SpanAttributes.AGENT_NAME: model_name or "AntigravityAgent",
                SpanAttributes.INPUT_VALUE: str(inputs),
                SpanAttributes.LLM_MODEL_NAME: model_name,
            },
        ) as span:
            try:
                converted_inputs = self._prepare_inputs(inputs)
                async with G_Agent(config=self.config) as agent:
                    response = await agent.chat(converted_inputs)
                    chunks = []
                    async for token in response:
                        chunks.append(token)
                        yield token
                    span.set_attribute(SpanAttributes.OUTPUT_VALUE, "".join(chunks))
            except Exception as e:
                span.set_status(trace.StatusCode.ERROR, str(e))
                raise

    def _prepare_inputs(
        self, inputs: list[AgentInputPart] | str | dict[str, Any] | None
    ) -> list[Any]:
        """Normalize and convert input representations to Antigravity primitives."""
        # 1. Handle None / dict variables using default template
        if inputs is None or isinstance(inputs, dict):
            if not self.default_user_prompt_source:
                raise ValueError(
                    "No inputs provided, and no default user prompt template is configured."
                )
            variables = inputs or {}
            user_prompt = self.prompt_manager.load_prompt(
                self.default_user_prompt_source,
                variables=variables,
                format_style=self.default_user_prompt_format,
            )
            return [user_prompt]

        # 2. Handle single string input
        if isinstance(inputs, str):
            return [inputs]

        # 3. Handle list of parts
        raw_parts = inputs if isinstance(inputs, list) else [inputs]
        converted = []
        for part in raw_parts:
            if isinstance(part, str):
                converted.append(part)
            elif isinstance(part, TextPart):
                converted.append(part.text)
            elif isinstance(part, ImagePart):
                if part.path:
                    # If path is relative, ensure it is fully resolved to absolute path
                    abs_path = os.path.abspath(part.path)
                    converted.append(G_Image.from_file(abs_path))
                elif part.data:
                    mime = part.mime_type or "image/png"
                    converted.append(G_Image(data=part.data, mime_type=mime))
                else:
                    raise ValueError("ImagePart must have either data or path defined.")
            else:
                raise TypeError(f"Unsupported input part type: {type(part)}")

        return converted


class AntigravityAgentGenerator(BaseAgentGenerator):
    """Google Antigravity SDK-based implementation of BaseAgentGenerator."""

    def __init__(self, prompt_base_dir: str | Path | None = None):
        """Initialize the AntigravityAgentGenerator.

        Args:
            prompt_base_dir: Optional base directory to search for prompt files.
        """
        self.prompt_base_dir = prompt_base_dir

    def create_agent(
        self,
        config_path: str,
        system_variables: dict[str, Any] | None = None,
        tools_registry: dict[str, Callable[..., Any]] | None = None,
        tools_config_path: str | None = None,
        **kwargs: Any,
    ) -> BaseAgent:
        """Create and configure an AntigravityAgent from a configuration file.

        Args:
            config_path: Path to the YAML configuration file.
            system_variables: Optional variables to format the system prompt template.
            tools_registry: Optional mapping of tool names to Python callables.
            tools_config_path: Optional path to a YAML file to load tools via ToolFactory.
            **kwargs: Extra parameters to override configuration fields dynamically.

        Returns:
            An instance of AntigravityAgent.
        """
        # Load and parse YAML config
        with open(config_path, encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        agent_data = config_data.get("agent", {})
        prompt_manager = PromptManager(base_dir=self.prompt_base_dir)

        # 1. Resolve System instructions
        system_prompt = ""
        system_prompt_source = agent_data.get("system_prompt_path") or agent_data.get(
            "system_prompt"
        )
        if system_prompt_source:
            system_prompt_format = agent_data.get("system_prompt_format", "f-string")
            system_prompt = prompt_manager.load_prompt(
                system_prompt_source,
                variables=system_variables,
                format_style=system_prompt_format,
            )

        # 2. Resolve Tools
        tools = []
        tools_registry = tools_registry or {}
        if tools_config_path:
            tools_registry.update(ToolFactory.load_from_yaml(tools_config_path))

        tool_names = agent_data.get("tools", [])
        for tool_name in tool_names:
            if tool_name in tools_registry:
                tools.append(trace_tool(tools_registry[tool_name]))
            else:
                # Log warning or add a stub / placeholder warning
                logger.warning(
                    f"Tool '{tool_name}' listed in config but not provided in tools_registry."
                )

        # 3. Resolve MCP Servers
        mcp_servers = []
        mcp_data = agent_data.get("mcp_servers", {})
        # Can be a dictionary or a list
        if isinstance(mcp_data, dict):
            for name, server_cfg in mcp_data.items():
                mcp_servers.append(self._parse_mcp_server(name, server_cfg))
        elif isinstance(mcp_data, list):
            for server_cfg in mcp_data:
                name = server_cfg.get("name")
                if not name:
                    raise ValueError("MCP server in list configuration must have a 'name' field.")
                mcp_servers.append(self._parse_mcp_server(name, server_cfg))

        # 4. Resolve app_data_dir to absolute path if specified
        app_data_dir = agent_data.get("app_data_dir")
        if app_data_dir:
            app_data_dir = os.path.abspath(app_data_dir)

        # Allow overrides from kwargs
        model = kwargs.get("model") or agent_data.get("model")
        api_key = kwargs.get("api_key") or agent_data.get("api_key")

        # Build LocalAgentConfig
        config = LocalAgentConfig(
            system_instructions=system_prompt,
            tools=tools or None,
            mcp_servers=mcp_servers or None,
            app_data_dir=app_data_dir,
            model=model,
            api_key=api_key,
        )

        default_user_prompt_source = agent_data.get("user_prompt_path") or agent_data.get(
            "user_prompt"
        )
        default_user_prompt_format = agent_data.get("user_prompt_format", "f-string")

        return AntigravityAgent(
            config=config,
            prompt_manager=prompt_manager,
            default_user_prompt_source=default_user_prompt_source,
            default_user_prompt_format=default_user_prompt_format,
        )

    def _parse_mcp_server(self, name: str, cfg: dict[str, Any]) -> Any:
        """Parse dictionary configuration into Google Antigravity MCP types."""
        conn_type = cfg.get("type", "stdio")
        if conn_type == "stdio":
            return McpStdioServer(
                name=name,
                command=cfg.get("command", ""),
                args=cfg.get("args", []),
                enabled_tools=cfg.get("enabled_tools"),
                disabled_tools=cfg.get("disabled_tools"),
            )
        elif conn_type == "http":
            return McpStreamableHttpServer(
                name=name,
                url=cfg.get("url", ""),
                headers=cfg.get("headers"),
                timeout=float(cfg.get("timeout", 30.0)),
                sse_read_timeout=float(cfg.get("sse_read_timeout", 300.0)),
                terminate_on_close=bool(cfg.get("terminate_on_close", True)),
                enabled_tools=cfg.get("enabled_tools"),
                disabled_tools=cfg.get("disabled_tools"),
            )
        else:
            raise ValueError(f"Unsupported MCP server connection type: {conn_type}")
