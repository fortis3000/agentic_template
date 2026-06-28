from unittest.mock import AsyncMock, patch

import pytest
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from src.agents.google_antigravity import AntigravityAgent, AntigravityAgentGenerator


@pytest.fixture(scope="module")
def otel_setup():
    """Sets up an in-memory span exporter for OpenTelemetry tracing tests."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    processor = SimpleSpanProcessor(exporter)
    provider.add_span_processor(processor)

    yield provider, exporter


@pytest.mark.asyncio
async def test_agent_and_tool_tracing(tmp_path, otel_setup):
    """Tests that agent calls and tool calls correctly generate OpenTelemetry spans with OpenInference attributes."""
    provider, exporter = otel_setup

    # Configure test agent config
    config_file = tmp_path / "agent_config.yaml"
    config_file.write_text(
        """
agent:
  name: "test_agent"
  model: "gemini-3.5-flash"
  system_prompt: "System instruction"
  user_prompt: "User query: {query}"
  tools:
    - "custom_tool"
""",
        encoding="utf-8",
    )

    # A custom tool to trace
    def custom_tool(x: int) -> str:
        """My test tool description."""
        return f"result-{x}"

    generator = AntigravityAgentGenerator(prompt_base_dir=tmp_path)
    agent = generator.create_agent(
        str(config_file),
        tools_registry={"custom_tool": custom_tool},
    )

    assert isinstance(agent, AntigravityAgent)

    # Let's mock the G_Agent chat response
    mock_response = AsyncMock()
    mock_response.text = AsyncMock(return_value="mocked agent response")

    with (
        patch("src.agents.google_antigravity.G_Agent") as mock_g_agent,
        patch("src.agents.google_antigravity.trace.get_tracer") as mock_get_tracer,
    ):
        # Make the agent use our test provider's tracer
        mock_get_tracer.return_value = provider.get_tracer("antigravity-agent")

        mock_instance = AsyncMock()
        mock_g_agent.return_value.__aenter__.return_value = mock_instance
        mock_instance.chat.return_value = mock_response

        # Clear exporter spans before test run
        exporter.clear()

        # 1. Run the agent call
        response_text = await agent.call(inputs={"query": "hello"})
        assert response_text == "mocked agent response"

        # Retrieve the spans
        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        agent_span = spans[0]

        # Verify Agent Span attributes
        assert agent_span.name == "gemini-3.5-flash call"
        assert (
            agent_span.attributes.get(SpanAttributes.OPENINFERENCE_SPAN_KIND)
            == OpenInferenceSpanKindValues.AGENT.value
        )
        assert agent_span.attributes.get(SpanAttributes.AGENT_NAME) == "gemini-3.5-flash"
        assert "hello" in agent_span.attributes.get(SpanAttributes.INPUT_VALUE)
        assert agent_span.attributes.get(SpanAttributes.OUTPUT_VALUE) == "mocked agent response"

        # 2. Run the tool function directly to check its tracing wrapper
        exporter.clear()
        wrapped_tool = agent.config.tools[0]
        tool_result = wrapped_tool(x=42)
        assert tool_result == "result-42"

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        tool_span = spans[0]

        # Verify Tool Span attributes
        assert tool_span.name == "custom_tool"
        assert (
            tool_span.attributes.get(SpanAttributes.OPENINFERENCE_SPAN_KIND)
            == OpenInferenceSpanKindValues.TOOL.value
        )
        assert tool_span.attributes.get(SpanAttributes.TOOL_NAME) == "custom_tool"
        assert "My test tool description" in tool_span.attributes.get(
            SpanAttributes.TOOL_DESCRIPTION
        )
        assert "42" in tool_span.attributes.get(SpanAttributes.INPUT_VALUE)
        assert tool_span.attributes.get(SpanAttributes.OUTPUT_VALUE) == "result-42"


@pytest.mark.asyncio
async def test_agent_and_tool_tracing_exceptions(tmp_path, otel_setup):
    """Tests that agent and tool calls correctly record exceptions and status on spans."""

    provider, exporter = otel_setup

    # Configure test agent config
    config_file = tmp_path / "agent_config_err.yaml"
    config_file.write_text(
        """
agent:
  name: "test_agent_err"
  model: "gemini-3.5-flash"
  system_prompt: "System instruction"
  user_prompt: "User query: {query}"
  tools:
    - "failing_tool"
""",
        encoding="utf-8",
    )

    # A custom tool to trace
    def failing_tool(x: int) -> str:
        raise ValueError("tool failure")

    generator = AntigravityAgentGenerator(prompt_base_dir=tmp_path)
    agent = generator.create_agent(
        str(config_file),
        tools_registry={"failing_tool": failing_tool},
    )

    assert isinstance(agent, AntigravityAgent)

    with (
        patch("src.agents.google_antigravity.G_Agent") as mock_g_agent,
        patch("src.agents.google_antigravity.trace.get_tracer") as mock_get_tracer,
    ):
        mock_get_tracer.return_value = provider.get_tracer("antigravity-agent")

        # 1. Test failing agent call
        mock_instance = AsyncMock()
        mock_g_agent.return_value.__aenter__.return_value = mock_instance
        mock_instance.chat.side_effect = RuntimeError("agent chat failure")

        exporter.clear()
        with pytest.raises(RuntimeError, match="agent chat failure"):
            await agent.call(inputs={"query": "hello"})

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        agent_span = spans[0]
        assert agent_span.status.status_code == StatusCode.ERROR
        assert "agent chat failure" in agent_span.status.description
        assert len(agent_span.events) == 1
        assert agent_span.events[0].name == "exception"

        # 2. Test failing tool execution
        exporter.clear()
        wrapped_tool = agent.config.tools[0]
        with pytest.raises(ValueError, match="tool failure"):
            wrapped_tool(x=42)

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        tool_span = spans[0]
        assert tool_span.status.status_code == StatusCode.ERROR
        assert "tool failure" in tool_span.status.description
        assert len(tool_span.events) == 1
        assert tool_span.events[0].name == "exception"
