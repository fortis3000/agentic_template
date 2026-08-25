from typing import Any
from unittest.mock import patch

import pytest
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from pydantic_ai.models.test import TestModel

from src.agents.pydantic_ai import PydanticAIAgent, PydanticAIAgentGenerator
from src.agents.tracing import trace_tool


@pytest.fixture(scope="module")
def otel_setup():
    """Sets up an in-memory span exporter for OpenTelemetry tracing tests."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    processor = SimpleSpanProcessor(exporter)
    provider.add_span_processor(processor)

    yield provider, exporter


@pytest.mark.asyncio
async def test_trace_tool_sync_and_async(otel_setup):
    """Tests that trace_tool decorator wraps sync and async functions correctly."""
    provider, exporter = otel_setup

    def sync_tool(a: int, b: str = "default") -> str:
        """Sync tool docs."""
        return f"{a}-{b}"

    async def async_tool(a: int) -> str:
        """Async tool docs."""
        return f"async-{a}"

    traced_sync = trace_tool(sync_tool)
    traced_async = trace_tool(async_tool)

    exporter.clear()
    with patch(
        "src.agents.tracing.trace.get_tracer", return_value=provider.get_tracer("agent-tool")
    ):
        res_sync = traced_sync(10, b="val")
        assert res_sync == "10-val"

        res_async = await traced_async(20)
        assert res_async == "async-20"

    spans = exporter.get_finished_spans()
    assert len(spans) == 2  # noqa: PLR2004

    sync_span = spans[0]
    assert sync_span.name == "sync_tool"
    assert (
        sync_span.attributes.get(SpanAttributes.OPENINFERENCE_SPAN_KIND)
        == OpenInferenceSpanKindValues.TOOL.value
    )
    assert sync_span.attributes.get(SpanAttributes.TOOL_NAME) == "sync_tool"
    assert sync_span.attributes.get(SpanAttributes.TOOL_DESCRIPTION) == "Sync tool docs."
    assert sync_span.attributes.get(SpanAttributes.OUTPUT_VALUE) == "10-val"

    async_span = spans[1]
    assert async_span.name == "async_tool"
    assert (
        async_span.attributes.get(SpanAttributes.OPENINFERENCE_SPAN_KIND)
        == OpenInferenceSpanKindValues.TOOL.value
    )
    assert async_span.attributes.get(SpanAttributes.TOOL_NAME) == "async_tool"
    assert async_span.attributes.get(SpanAttributes.TOOL_DESCRIPTION) == "Async tool docs."
    assert async_span.attributes.get(SpanAttributes.OUTPUT_VALUE) == "async-20"


@pytest.mark.asyncio
async def test_pydantic_ai_agent_and_tool_tracing(tmp_path, otel_setup):
    """Tests that PydanticAIAgent calls and tool calls correctly generate OTel spans with OpenInference attributes."""
    provider, exporter = otel_setup

    config_file = tmp_path / "pydantic_agent_config.yaml"
    config_file.write_text(
        """
agent:
  name: "test_pydantic_agent"
  model: "gemini-2.0-flash"
  provider: "google"
  system_prompt: "System instruction"
  user_prompt: "User query: {query}"
  tools:
    - "custom_tool"
""",
        encoding="utf-8",
    )

    def custom_tool(x: int) -> str:
        """My test tool description."""
        return f"result-{x}"

    generator = PydanticAIAgentGenerator(prompt_base_dir=tmp_path)
    agent = generator.create_agent(
        str(config_file),
        tools_registry={"custom_tool": custom_tool},
    )

    assert isinstance(agent, PydanticAIAgent)

    test_model = TestModel(custom_output_text="mocked agent response")

    with (
        agent.agent.override(model=test_model),
        patch("src.agents.pydantic_ai.trace.get_tracer") as mock_get_tracer,
    ):
        mock_get_tracer.return_value = provider.get_tracer("pydantic-ai-agent")

        exporter.clear()

        # 1. Run the agent call
        response_text = await agent.call(inputs={"query": "hello"})
        assert response_text == "mocked agent response"

        # Retrieve the spans
        spans = exporter.get_finished_spans()
        assert len(spans) >= 1
        agent_spans = [s for s in spans if s.name == "gemini-2.0-flash call"]
        assert len(agent_spans) == 1
        agent_span = agent_spans[0]

        # Verify Agent Span attributes
        assert agent_span.name == "gemini-2.0-flash call"
        assert (
            agent_span.attributes.get(SpanAttributes.OPENINFERENCE_SPAN_KIND)
            == OpenInferenceSpanKindValues.AGENT.value
        )
        assert agent_span.attributes.get(SpanAttributes.AGENT_NAME) == "gemini-2.0-flash"
        assert "hello" in agent_span.attributes.get(SpanAttributes.INPUT_VALUE)
        assert agent_span.attributes.get(SpanAttributes.OUTPUT_VALUE) == "mocked agent response"

        # 2. Run the tool function directly to check its tracing wrapper
        exporter.clear()
        wrapped_tool: Any = agent.agent._function_toolset.tools["custom_tool"].function
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
async def test_pydantic_ai_agent_and_tool_tracing_exceptions(tmp_path, otel_setup):
    """Tests that PydanticAIAgent and tool calls correctly record exceptions and status on spans."""
    provider, exporter = otel_setup

    config_file = tmp_path / "pydantic_agent_config_err.yaml"
    config_file.write_text(
        """
agent:
  name: "test_pydantic_agent_err"
  model: "gemini-2.0-flash"
  provider: "google"
  system_prompt: "System instruction"
  user_prompt: "User query: {query}"
  tools:
    - "failing_tool"
""",
        encoding="utf-8",
    )

    def failing_tool(x: int) -> str:
        raise ValueError("tool failure")

    generator = PydanticAIAgentGenerator(prompt_base_dir=tmp_path)
    agent = generator.create_agent(
        str(config_file),
        tools_registry={"failing_tool": failing_tool},
    )

    assert isinstance(agent, PydanticAIAgent)

    test_model = TestModel(custom_output_text="mocked agent response")

    with (
        agent.agent.override(model=test_model),
        patch("src.agents.pydantic_ai.trace.get_tracer") as mock_get_tracer,
    ):
        mock_get_tracer.return_value = provider.get_tracer("pydantic-ai-agent")

        # 1. Test failing agent call
        with patch.object(agent.agent, "run", side_effect=RuntimeError("agent run failure")):
            exporter.clear()
            with pytest.raises(RuntimeError, match="agent run failure"):
                await agent.call(inputs={"query": "hello"})

            spans = exporter.get_finished_spans()
            assert len(spans) == 1
            agent_span = spans[0]
            assert agent_span.status.status_code == StatusCode.ERROR
            assert "agent run failure" in agent_span.status.description
            assert len(agent_span.events) == 1
            assert agent_span.events[0].name == "exception"

        # 2. Test failing tool execution
        exporter.clear()
        wrapped_tool: Any = agent.agent._function_toolset.tools["failing_tool"].function
        with pytest.raises(ValueError, match="tool failure"):
            wrapped_tool(x=42)

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        tool_span = spans[0]
        assert tool_span.status.status_code == StatusCode.ERROR
        assert "tool failure" in tool_span.status.description
        assert len(tool_span.events) == 1
        assert tool_span.events[0].name == "exception"
