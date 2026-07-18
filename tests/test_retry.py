# ruff: noqa: PLR2004, PLC0415
import asyncio
from typing import cast
from unittest.mock import Mock

import pytest

from src.agents.pydantic_ai import PydanticAIAgent, PydanticAIAgentGenerator
from src.utils.retry import RetryConfig, is_retryable_exception, wrap_tool_with_retry


# Mock exception classes for testing
class MockAPIError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


class MockGoogleError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def test_is_retryable_exception():
    # Retryable errors (503, 429, 502, 504, 500)
    assert is_retryable_exception(MockAPIError(503, "Unavailable")) is True
    assert is_retryable_exception(MockAPIError(429, "Too Many Requests")) is True
    assert is_retryable_exception(MockGoogleError(503, "Unavailable")) is True

    # Non-retryable errors (403, 401, 400, 404)
    assert is_retryable_exception(MockAPIError(403, "Forbidden")) is False
    assert is_retryable_exception(MockAPIError(400, "Bad Request")) is False

    # String representation checks
    assert is_retryable_exception(Exception("Model is experiencing high demand (503)")) is True
    assert is_retryable_exception(Exception("Resource Exhausted (429)")) is True
    assert is_retryable_exception(Exception("Permission Denied (403)")) is False


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


def test_wrap_sync_tool_no_retry_on_permanent_error():
    call_count = 0

    def mock_sync_tool():
        nonlocal call_count
        call_count += 1
        raise MockAPIError(403, "Forbidden")

    wrapped = wrap_tool_with_retry(mock_sync_tool, RetryConfig(attempts=3, delay=0.01))
    with pytest.raises(MockAPIError) as exc_info:
        wrapped()
    assert exc_info.value.status_code == 403
    assert call_count == 1


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
async def test_agent_call_retry(tmp_path):
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


@pytest.mark.asyncio
async def test_agent_call_stream_retry(tmp_path):
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

    generator = PydanticAIAgentGenerator(prompt_base_dir=tmp_path)
    agent = cast(PydanticAIAgent, generator.create_agent(str(config_file)))

    call_count = 0

    class MockStreamResponse:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def stream_text(self):
            yield "streamed text"

    def mock_run_stream(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise MockAPIError(503, "Unavailable")
        return MockStreamResponse()

    agent.agent.run_stream = mock_run_stream  # type: ignore
    chunks = []
    async for chunk in agent.call_stream("test query"):
        chunks.append(chunk)
    assert "".join(chunks) == "streamed text"
    assert call_count == 3


@pytest.mark.asyncio
async def test_api_run_agent_in_background_retry(tmp_path, monkeypatch):
    from src.api.main import active_streams, active_tasks, run_agent_in_background

    call_count = 0

    async def mock_call_stream(self, inputs=None):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise MockAPIError(503, "Unavailable")
        yield "response text"

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

        retry_msg = events[0]
        assert retry_msg["event"] == "token"
        assert "Retryable error occurred" in retry_msg["text"]

        token_msg = events[1]
        assert token_msg["event"] == "token"
        assert token_msg["text"] == "response text"

        done_msg = events[-1]
        assert done_msg["event"] == "done"
        assert done_msg["text"] == "response text"

    finally:
        active_streams.pop(session_id, None)
        active_tasks.pop(session_id, None)
