import functools
import inspect
from typing import Any, Callable

from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry import trace


def trace_tool(tool_func: Callable[..., Any]) -> Callable[..., Any]:
    """Wraps a tool function with OpenTelemetry tracing using OpenInference conventions."""
    tool_name = getattr(tool_func, "__name__", "unknown_tool")
    tool_doc = getattr(tool_func, "__doc__", "") or ""
    if inspect.iscoroutinefunction(tool_func):

        @functools.wraps(tool_func)
        async def async_wrapped(*args: Any, **kwargs: Any) -> Any:
            tracer = trace.get_tracer("agent-tool")
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
            tracer = trace.get_tracer("agent-tool")
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
