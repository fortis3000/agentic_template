# ruff: noqa: PLR2004, PLC0415, N818
import asyncio
import os
from typing import cast
from unittest.mock import MagicMock, Mock

import pytest

from src.agents.pydantic_ai import PydanticAIAgent, PydanticAIAgentGenerator
from utils.retry import (
    RetryConfig,
    is_retryable_exception,
    retry_async,
    retry_sync,
    wrap_tool_with_retry,
)


# Mock exception classes for testing
class MockAPIError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


class MockGoogleError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


class APIConnectionError(Exception):
    pass


class APITimeoutError(Exception):
    pass


class ConnectError(Exception):
    pass


class ReadTimeout(Exception):
    pass


def test_is_retryable_exception():
    # Retryable numeric errors (503, 429, 502, 504, 500, 408)
    assert is_retryable_exception(MockAPIError(503, "Unavailable")) is True
    assert is_retryable_exception(MockAPIError(429, "Too Many Requests")) is True
    assert is_retryable_exception(MockAPIError(408, "Request Timeout")) is True
    assert is_retryable_exception(MockGoogleError(503, "Unavailable")) is True

    # Non-retryable numeric errors (403, 401, 400, 404)
    assert is_retryable_exception(MockAPIError(403, "Forbidden")) is False
    assert is_retryable_exception(MockAPIError(400, "Bad Request")) is False

    # Connection and timeout errors (built-ins and library class names)
    assert is_retryable_exception(TimeoutError("Standard timeout")) is True
    assert is_retryable_exception(ConnectionResetError("Reset")) is True
    assert is_retryable_exception(APIConnectionError("OpenAI connection error")) is True
    assert is_retryable_exception(APITimeoutError("OpenAI timeout")) is True
    assert is_retryable_exception(ConnectError("HTTPX connect error")) is True
    assert is_retryable_exception(ReadTimeout("HTTPX read timeout")) is True

    # String representation checks
    assert is_retryable_exception(Exception("Model is experiencing high demand (503)")) is True
    assert is_retryable_exception(Exception("Resource Exhausted (429)")) is True
    assert is_retryable_exception(Exception("Permission Denied (403)")) is False
    assert is_retryable_exception(Exception("quota limit exceeded")) is True

    # Word boundaries check (ValueError 500x2)
    assert is_retryable_exception(ValueError("Expected 500x2, got 4x2")) is False


def test_retry_sync_success():
    call_count = 0

    def mock_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise MockAPIError(503, "Unavailable")
        return "success"

    result = retry_sync(mock_func, RetryConfig(attempts=3, delay=0.01))
    assert result == "success"
    assert call_count == 3


def test_retry_sync_fail_immediately_on_non_retryable():
    call_count = 0

    def mock_func():
        nonlocal call_count
        call_count += 1
        raise MockAPIError(403, "Forbidden")

    with pytest.raises(MockAPIError):
        retry_sync(mock_func, RetryConfig(attempts=3, delay=0.01))
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_async_success():
    call_count = 0

    async def mock_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise MockAPIError(503, "Unavailable")
        return "success"

    result = await retry_async(mock_func, RetryConfig(attempts=3, delay=0.01))
    assert result == "success"
    assert call_count == 3


def test_wrap_sync_tool_retry():
    call_count = 0

    def mock_sync_tool():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise MockAPIError(503, "Unavailable")
        return "success"

    wrapped = wrap_tool_with_retry(mock_sync_tool, RetryConfig(attempts=3, delay=0.01))
    result = wrapped()
    assert result == "success"
    assert call_count == 3


@pytest.mark.asyncio
async def test_wrap_async_tool_retry():
    call_count = 0

    async def mock_async_tool():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise MockAPIError(503, "Unavailable")
        return "success"

    wrapped = wrap_tool_with_retry(mock_async_tool, RetryConfig(attempts=3, delay=0.01))
    result = await wrapped()
    assert result == "success"
    assert call_count == 3


@pytest.mark.asyncio
async def test_agent_call_retry(tmp_path, monkeypatch):
    config_file = tmp_path / "agent_config.yaml"
    config_file.write_text(
        """
agent:
  name: "test_agent"
  model: "gemini-2.0-flash"
  provider: "google"
  retry:
    attempts: 3
    delay: 0.01
""",
        encoding="utf-8",
    )

    # Mock Otel tracer
    mock_span = MagicMock()
    mock_tracer = MagicMock()
    mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
    monkeypatch.setattr("opentelemetry.trace.get_tracer", lambda name: mock_tracer)

    generator = PydanticAIAgentGenerator(prompt_base_dir=tmp_path)
    agent = cast(PydanticAIAgent, generator.create_agent(str(config_file)))

    call_count = 0

    async def mock_run(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise MockAPIError(503, "Unavailable")
        mock_result = Mock()
        mock_result.output = "mock success"
        return mock_result

    agent.agent.run = mock_run  # type: ignore
    res = await agent.call("test query")
    assert res == "mock success"
    assert call_count == 3

    # Check that record_exception was called for the 2 failed attempts
    assert mock_span.record_exception.call_count == 2


@pytest.mark.asyncio
async def test_agent_call_stream_retry(tmp_path, monkeypatch):
    config_file = tmp_path / "agent_config.yaml"
    config_file.write_text(
        """
agent:
  name: "test_agent"
  model: "gemini-2.0-flash"
  provider: "google"
  retry:
    attempts: 3
    delay: 0.01
""",
        encoding="utf-8",
    )

    mock_span = MagicMock()
    mock_tracer = MagicMock()
    mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
    monkeypatch.setattr("opentelemetry.trace.get_tracer", lambda name: mock_tracer)

    generator = PydanticAIAgentGenerator(prompt_base_dir=tmp_path)
    agent = cast(PydanticAIAgent, generator.create_agent(str(config_file)))

    call_count = 0

    class MockStreamResponse:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def stream_text(self, **kwargs):
            yield "streamed text"

    def mock_run_stream(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise MockAPIError(503, "Unavailable")
        return MockStreamResponse()

    agent.agent.run_stream = mock_run_stream
    chunks = []
    async for chunk in agent.call_stream("test query"):
        chunks.append(chunk)
    assert "".join(chunks) == "streamed text"
    assert call_count == 3
    assert mock_span.record_exception.call_count == 2


def test_empty_retry_yaml_parsing(tmp_path):
    config_file = tmp_path / "agent_config.yaml"
    config_file.write_text(
        """
agent:
  name: "test_agent"
  model: "gemini-2.0-flash"
  provider: "google"
  retry:
""",
        encoding="utf-8",
    )
    generator = PydanticAIAgentGenerator(prompt_base_dir=tmp_path)
    agent = cast(PydanticAIAgent, generator.create_agent(str(config_file)))
    assert agent.retry_config.attempts == 3
    assert agent.retry_config.delay == 5.0


@pytest.mark.asyncio
async def test_api_run_agent_in_background_retry(tmp_path, monkeypatch):
    from src.api.main import active_streams, active_tasks, run_agent_in_background

    # We patch PydanticAIAgent.call_stream to yield the token immediately
    async def mock_call_stream(self, inputs=None):
        yield "response text"

    from src.agents.pydantic_ai import PydanticAIAgent

    monkeypatch.setattr(PydanticAIAgent, "call_stream", mock_call_stream)

    config_file = tmp_path / "agent_config.yaml"
    config_file.write_text(
        """
agent:
  name: "test_agent"
  model: "gemini-2.0-flash"
  provider: "google"
  retry:
    attempts: 2
    delay: 0.01
""",
        encoding="utf-8",
    )

    session_id = "test_session_id"
    queue = asyncio.Queue()
    active_streams[session_id] = queue
    active_tasks[session_id] = asyncio.create_task(asyncio.sleep(0.1))

    try:
        await run_agent_in_background(
            session_id=session_id,
            config_path=str(config_file),
            query="test",
            system_variables={},
        )

        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

        assert len(events) >= 2

        token_msg = events[0]
        assert token_msg["event"] == "token"
        assert token_msg["text"] == "response text"

        done_msg = events[-1]
        assert done_msg["event"] == "done"
        assert done_msg["text"] == "response text"

    finally:
        active_streams.pop(session_id, None)
        active_tasks.pop(session_id, None)
        # Explicit clean up of mock session file from data/sessions/ directory
        from src.api.main import SESSIONS_DIR

        session_file = os.path.join(SESSIONS_DIR, f"{session_id}.json")
        if os.path.exists(session_file):
            try:
                os.unlink(session_file)
            except Exception:
                pass
