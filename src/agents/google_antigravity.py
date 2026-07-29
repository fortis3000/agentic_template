import asyncio
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
from src.agents.config import AgentConfigSchema, AgentYamlConfig, McpServerConfigSchema
from src.agents.prompt_manager import PromptManager
from src.tools.base import ToolFactory
from src.utils.logger import get_logger
from src.utils.retry import RetryConfig, is_retryable_exception, retry_async, wrap_tool_with_retry

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
        retry_config: RetryConfig | None = None,
    ):
        """Initialize the AntigravityAgent.

        Args:
            config: The LocalAgentConfig instance.
            prompt_manager: The PromptManager for resolving prompts.
            default_user_prompt_source: The default user prompt template source.
            default_user_prompt_format: The template format of the user prompt.
            retry_config: Configuration for retries.
        """
        self.config = config
        self.prompt_manager = prompt_manager
        self.default_user_prompt_source = default_user_prompt_source
        self.default_user_prompt_format = default_user_prompt_format
        self.retry_config = retry_config or RetryConfig()

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

            async def _run():
                converted_inputs = self._prepare_inputs(inputs)
                async with G_Agent(config=self.config) as agent:
                    response = await agent.chat(converted_inputs)
                    return await response.text()

            def log_retry(e: Exception, attempt: int, total_attempts: int):
                span.record_exception(e)
                logger.warning(
                    f"LLM call failed with retryable error (attempt {attempt}/{total_attempts}). "
                    f"Retrying in {self.retry_config.delay}s... Error: {e}"
                )

            res_text = await retry_async(_run, self.retry_config, log_retry)
            span.set_attribute(SpanAttributes.OUTPUT_VALUE, res_text)
            return res_text

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
        attempts = self.retry_config.attempts
        delay = self.retry_config.delay

        with tracer.start_as_current_span(
            name=f"{model_name or 'agent'} call_stream",
            attributes={
                SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.AGENT.value,
                SpanAttributes.AGENT_NAME: model_name or "AntigravityAgent",
                SpanAttributes.INPUT_VALUE: str(inputs),
                SpanAttributes.LLM_MODEL_NAME: model_name,
            },
        ) as span:
            for attempt in range(1, attempts + 1):
                has_yielded = False
                try:
                    converted_inputs = self._prepare_inputs(inputs)
                    async with G_Agent(config=self.config) as agent:
                        response = await agent.chat(converted_inputs)
                        chunks = []
                        async for token in response:
                            has_yielded = True
                            chunks.append(token)
                            yield token
                        span.set_attribute(SpanAttributes.OUTPUT_VALUE, "".join(chunks))
                    break
                except Exception as e:
                    if is_retryable_exception(e) and not has_yielded and attempt < attempts:
                        span.record_exception(e)
                        logger.warning(
                            f"LLM call_stream failed with retryable error (attempt {attempt}/{attempts}). "
                            f"Retrying in {delay}s... Error: {e}"
                        )
                        await asyncio.sleep(delay)
                    else:
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

    def create_agent(  # noqa: PLR0912
        self,
        config: str | AgentYamlConfig,
        system_variables: dict[str, Any] | None = None,
        tools_registry: dict[str, Callable[..., Any]] | None = None,
        tools_config_path: str | None = None,
        **kwargs: Any,
    ) -> BaseAgent:
        """Create and configure an AntigravityAgent from a configuration file or pre-loaded config.

        Args:
            config: Path to the YAML configuration file or pre-loaded AgentYamlConfig.
            system_variables: Optional variables to format the system prompt template.
            tools_registry: Optional mapping of tool names to Python callables.
            tools_config_path: Optional path to a YAML file to load tools via ToolFactory.
            **kwargs: Extra parameters to override configuration fields dynamically.

        Returns:
            An instance of AntigravityAgent.
        """
        if isinstance(config, str):
            # Load and parse YAML config
            with open(config, encoding="utf-8") as f:
                config_data = yaml.safe_load(f)
            validated_config = AgentYamlConfig.model_validate(config_data)
        else:
            validated_config = config

        agent_data_dict = validated_config.agent.model_dump()

        # Allow overrides from kwargs
        for k, v in kwargs.items():
            if v is not None:
                agent_data_dict[k] = v

        agent_data = AgentConfigSchema.model_validate(agent_data_dict)
        prompt_manager = PromptManager(base_dir=self.prompt_base_dir)

        # 1. Resolve System instructions
        system_prompt = ""
        system_prompt_source = agent_data.system_prompt_path or agent_data.system_prompt
        if system_prompt_source:
            system_prompt_format = agent_data.system_prompt_format or "f-string"
            system_prompt = prompt_manager.load_prompt(
                system_prompt_source,
                variables=system_variables,
                format_style=system_prompt_format,
            )

        # 2. Resolve Tools
        tools = []
        tools_registry = {**(tools_registry or {})}
        if tools_config_path:
            tools_registry.update(ToolFactory.load_from_yaml(tools_config_path))

        for tool_name in agent_data.tools:
            if tool_name in tools_registry:
                tool_retry = None
                if tool_name in agent_data.tool_settings:
                    tool_retry = agent_data.tool_settings[tool_name].retry

                wrapped_tool = wrap_tool_with_retry(
                    tools_registry[tool_name], agent_data.retry, tool_retry
                )
                tools.append(trace_tool(wrapped_tool))
            else:
                raise ValueError(
                    f"Tool '{tool_name}' listed in config but not provided in tools_registry."
                )

        # 3. Resolve MCP Servers to standard wrapped tools
        from src.mcp_integration.client import (  # noqa: PLC0415
            McpServerFactory,
            make_mcp_tool_callable,
        )

        for mcp_name, mcp_cfg in agent_data.mcp_servers.items():
            # Synchronously fetch tools
            mcp_tools = McpServerFactory.fetch_tools_sync(mcp_cfg)
            for tool_info in mcp_tools:
                tool_name = tool_info["name"]

                # Check for tool retry override
                tool_retry = None
                if tool_name in agent_data.tool_settings:
                    tool_retry = agent_data.tool_settings[tool_name].retry

                # Create wrapper callable and wrap it with retry
                mcp_callable = make_mcp_tool_callable(mcp_cfg, tool_name)
                wrapped_mcp_callable = wrap_tool_with_retry(
                    mcp_callable, agent_data.retry, tool_retry
                )

                # Trace tool and append to tools
                traced_mcp_callable = trace_tool(wrapped_mcp_callable)
                tools.append(traced_mcp_callable)

        # 4. Resolve app_data_dir to absolute path if specified
        app_data_dir = agent_data.app_data_dir
        if app_data_dir:
            app_data_dir = os.path.abspath(app_data_dir)

        # Build LocalAgentConfig
        local_config = LocalAgentConfig(
            system_instructions=system_prompt,
            tools=tools or None,
            mcp_servers=None,
            app_data_dir=app_data_dir,
            model=agent_data.model,
            api_key=agent_data.api_key or kwargs.get("api_key"),
        )

        default_user_prompt_source = agent_data.user_prompt_path or agent_data.user_prompt
        default_user_prompt_format = agent_data.user_prompt_format or "f-string"

        return AntigravityAgent(
            config=local_config,
            prompt_manager=prompt_manager,
            default_user_prompt_source=default_user_prompt_source,
            default_user_prompt_format=default_user_prompt_format,
            retry_config=agent_data.retry,
        )

    def _parse_mcp_server(self, name: str, cfg: McpServerConfigSchema) -> Any:
        """Parse configuration schema into Google Antigravity MCP types."""
        if cfg.type == "stdio":
            return McpStdioServer(
                name=name,
                command=cfg.command or "",
                args=cfg.args or [],
                enabled_tools=cfg.enabled_tools,
                disabled_tools=cfg.disabled_tools,
            )
        elif cfg.type == "http":
            return McpStreamableHttpServer(
                name=name,
                url=cfg.url or "",
                headers=cfg.headers,
                timeout=float(cfg.timeout),
                sse_read_timeout=float(cfg.sse_read_timeout),
                terminate_on_close=bool(cfg.terminate_on_close),
                enabled_tools=cfg.enabled_tools,
                disabled_tools=cfg.disabled_tools,
            )
        else:
            raise ValueError(f"Unsupported MCP server connection type: {cfg.type}")
