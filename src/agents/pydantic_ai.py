import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Callable

import yaml
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry import trace
from pydantic_ai import Agent as PA_Agent
from pydantic_ai import BinaryContent
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openai import OpenAIProvider

from src.agents.base import AgentInputPart, BaseAgent, BaseAgentGenerator, ImagePart, TextPart
from src.agents.config import AgentConfigSchema, AgentYamlConfig
from src.agents.google_antigravity import trace_tool
from src.agents.prompt_manager import PromptManager
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ModelFactory:
    """Factory to resolve Pydantic AI Model instances based on the provider."""

    @staticmethod
    def create_model(
        provider: str,
        model_name: str,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> Model[Any]:
        """Create and configure a Pydantic AI Model instance."""
        provider = provider.lower().strip()

        # Clean prefix from model name if any
        clean_model_name = model_name
        for prefix in ("google:", "gemini:", "openai:", "anthropic:", "ollama:"):
            if clean_model_name.lower().startswith(prefix):
                clean_model_name = clean_model_name[len(prefix) :]
                break

        if provider == "google":
            key = (
                api_key
                or os.getenv("GEMINI_API_KEY")
                or os.getenv("GOOGLE_API_KEY")
                or "placeholder_key"
            )
            google_provider = GoogleProvider(api_key=key)
            return GoogleModel(model_name=clean_model_name, provider=google_provider)

        elif provider == "openai":
            key = api_key or os.getenv("OPENAI_API_KEY") or "placeholder_key"
            if base_url:
                openai_provider = OpenAIProvider(api_key=key, base_url=base_url)
            else:
                openai_provider = OpenAIProvider(api_key=key)
            return OpenAIChatModel(model_name=clean_model_name, provider=openai_provider)

        elif provider == "ollama":
            url = base_url or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434/v1"
            openai_provider = OpenAIProvider(api_key=api_key or "ollama", base_url=url)
            return OpenAIChatModel(model_name=clean_model_name, provider=openai_provider)

        elif provider == "anthropic":
            key = api_key or os.getenv("ANTHROPIC_API_KEY") or "placeholder_key"
            if base_url:
                anthropic_provider = AnthropicProvider(api_key=key, base_url=base_url)
            else:
                anthropic_provider = AnthropicProvider(api_key=key)
            return AnthropicModel(model_name=clean_model_name, provider=anthropic_provider)

        else:
            raise ValueError(f"Unsupported model provider: '{provider}'")


class PydanticAIAgent(BaseAgent):
    """Pydantic AI-based implementation of BaseAgent."""

    def __init__(
        self,
        agent: PA_Agent[Any, Any],
        prompt_manager: PromptManager,
        default_user_prompt_source: str | None = None,
        default_user_prompt_format: str = "f-string",
    ):
        """Initialize the PydanticAIAgent.

        Args:
            agent: The Pydantic AI Agent instance.
            prompt_manager: The PromptManager for resolving prompts.
            default_user_prompt_source: The default user prompt template source.
            default_user_prompt_format: The template format of the user prompt.
        """
        self.agent = agent
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
        tracer = trace.get_tracer("pydantic-ai-agent")
        model_name_val = getattr(self.agent.model, "model_name", None) or str(self.agent.model)
        model_name = str(model_name_val)
        if "<" in model_name or "object at" in model_name:
            model_name = self.agent.model.__class__.__name__

        with tracer.start_as_current_span(
            name=f"{model_name or 'agent'} call",
            attributes={
                SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.AGENT.value,
                SpanAttributes.AGENT_NAME: model_name or "PydanticAIAgent",
                SpanAttributes.INPUT_VALUE: str(inputs),
                SpanAttributes.LLM_MODEL_NAME: model_name,
            },
        ) as span:
            try:
                converted_inputs = self._prepare_inputs(inputs)
                result = await self.agent.run(converted_inputs)
                res_text = str(result.output)
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
        tracer = trace.get_tracer("pydantic-ai-agent")
        model_name_val = getattr(self.agent.model, "model_name", None) or str(self.agent.model)
        model_name = str(model_name_val)
        if "<" in model_name or "object at" in model_name:
            model_name = self.agent.model.__class__.__name__

        with tracer.start_as_current_span(
            name=f"{model_name or 'agent'} call_stream",
            attributes={
                SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.AGENT.value,
                SpanAttributes.AGENT_NAME: model_name or "PydanticAIAgent",
                SpanAttributes.INPUT_VALUE: str(inputs),
                SpanAttributes.LLM_MODEL_NAME: model_name,
            },
        ) as span:
            try:
                converted_inputs = self._prepare_inputs(inputs)
                async with self.agent.run_stream(converted_inputs) as response:
                    chunks = []
                    async for token in response.stream_text():
                        chunks.append(token)
                        yield token
                    span.set_attribute(SpanAttributes.OUTPUT_VALUE, "".join(chunks))
            except Exception as e:
                span.set_status(trace.StatusCode.ERROR, str(e))
                raise

    def _prepare_inputs(self, inputs: list[AgentInputPart] | str | dict[str, Any] | None) -> Any:
        """Normalize and convert input representations to Pydantic AI primitives."""
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
                    abs_path = os.path.abspath(part.path)
                    with open(abs_path, "rb") as f:
                        data = f.read()
                    mime = part.mime_type or "image/png"
                    converted.append(BinaryContent(data=data, media_type=mime))
                elif part.data:
                    mime = part.mime_type or "image/png"
                    converted.append(BinaryContent(data=part.data, media_type=mime))
                else:
                    raise ValueError("ImagePart must have either data or path defined.")
            else:
                raise TypeError(f"Unsupported input part type: {type(part)}")

        return converted


class PydanticAIAgentGenerator(BaseAgentGenerator):
    """Pydantic AI-based implementation of BaseAgentGenerator."""

    def __init__(self, prompt_base_dir: str | Path | None = None):
        """Initialize the PydanticAIAgentGenerator.

        Args:
            prompt_base_dir: Optional base directory to search for prompt files.
        """
        self.prompt_base_dir = prompt_base_dir

    def create_agent(
        self,
        config_path: str,
        system_variables: dict[str, Any] | None = None,
        tools_registry: dict[str, Callable[..., Any]] | None = None,
        **kwargs: Any,
    ) -> BaseAgent:
        """Create and configure a PydanticAIAgent from a configuration file.

        Args:
            config_path: Path to the YAML configuration file.
            system_variables: Optional variables to format the system prompt template.
            tools_registry: Optional mapping of tool names to Python callables.
            **kwargs: Extra parameters to override configuration fields dynamically.

        Returns:
            An instance of PydanticAIAgent.
        """
        # Load and parse YAML config
        with open(config_path, encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        # 1. Parse and validate using Pydantic validator
        validated_config = AgentYamlConfig.model_validate(config_data)
        agent_data_dict = validated_config.agent.model_dump()

        # 2. Handle dynamic overrides via kwargs
        for k, v in kwargs.items():
            if v is not None:
                agent_data_dict[k] = v

        # Re-validate target config with overrides
        agent_data = AgentConfigSchema.model_validate(agent_data_dict)

        prompt_manager = PromptManager(base_dir=self.prompt_base_dir)

        # 3. Resolve System instructions using the connected config method
        system_prompt = agent_data.get_system_prompt(prompt_manager, variables=system_variables)

        # 4. Resolve Tools
        tools = []
        tools_registry = tools_registry or {}
        for tool_name in agent_data.tools:
            if tool_name in tools_registry:
                tools.append(trace_tool(tools_registry[tool_name]))
            else:
                logger.warning(
                    f"Tool '{tool_name}' listed in config but not provided in tools_registry."
                )

        # 5. Resolve Model configuration via factory
        model_instance = ModelFactory.create_model(
            provider=agent_data.provider,
            model_name=agent_data.model,
            base_url=agent_data.base_url,
            api_key=agent_data.mcp_servers.get(
                "api_key"
            ),  # fallback api_key override from kwargs handled below
        )
        if kwargs.get("api_key"):
            # Recreate model with explicit api_key override if passed in kwargs
            model_instance = ModelFactory.create_model(
                provider=agent_data.provider,
                model_name=agent_data.model,
                base_url=agent_data.base_url,
                api_key=kwargs["api_key"],
            )

        # Build Pydantic AI Agent
        pa_agent = PA_Agent(
            model=model_instance,
            system_prompt=system_prompt if system_prompt else (),
            tools=tools,
        )

        default_user_prompt_source = agent_data.user_prompt_path or agent_data.user_prompt
        default_user_prompt_format = agent_data.user_prompt_format or "f-string"

        return PydanticAIAgent(
            agent=pa_agent,
            prompt_manager=prompt_manager,
            default_user_prompt_source=default_user_prompt_source,
            default_user_prompt_format=default_user_prompt_format,
        )
