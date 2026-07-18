import asyncio
import functools
import inspect
import logging
import time
from typing import Any, Callable

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class RetryConfig(BaseModel):
    attempts: int = 3
    delay: float = 5.0


def is_retryable_exception(exc: Exception) -> bool:
    """Check if the given exception is retryable based on HTTP/gRPC status codes or message."""
    # 1. Check for status_code attribute
    status_code = getattr(exc, "status_code", None)

    # 2. Check for code attribute (google.api_core.exceptions or other libraries)
    if status_code is None:
        status_code = getattr(exc, "code", None)

    # 3. Check for response status_code (httpx or requests)
    if status_code is None and hasattr(exc, "response"):
        response = getattr(exc, "response")
        if response and hasattr(response, "status_code"):
            status_code = getattr(response, "status_code")

    # 4. Check for HTTPError/HttpError status codes (googleapiclient.errors.HttpError)
    if status_code is None:
        resp = getattr(exc, "resp", None)
        if resp and hasattr(resp, "status"):
            status_code = getattr(resp, "status")

    # If we got a numeric status code, check if it's retryable
    if isinstance(status_code, int):
        # 503 (Service Unavailable), 429 (Too Many Requests), 502 (Bad Gateway), 504 (Gateway Timeout), 500 (Internal Server Error)
        return status_code in (503, 429, 502, 504, 500)

    # Check string representation for indications of transient/overload errors
    exc_str = str(exc).lower()

    # Guard: if it's explicitly non-retryable, return False
    if any(
        code in exc_str
        for code in (
            "403",
            "401",
            "400",
            "404",
            "unauthorized",
            "forbidden",
            "not found",
            "bad request",
        )
    ):
        return False

    # Check for retryable terms
    if any(
        term in exc_str
        for term in (
            "503",
            "429",
            "502",
            "504",
            "500",
            "service unavailable",
            "resource exhausted",
            "too many requests",
            "unavailable",
        )
    ):
        return True

    return False


def wrap_tool_with_retry(
    tool_func: Callable[..., Any], retry_config: RetryConfig
) -> Callable[..., Any]:
    """Wraps a tool callable to retry execution if it encounters retryable exceptions."""
    tool_name = getattr(tool_func, "__name__", "unknown_tool")
    attempts = retry_config.attempts
    delay = retry_config.delay

    if inspect.iscoroutinefunction(tool_func):

        @functools.wraps(tool_func)
        async def async_wrapped(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(1, attempts + 1):
                try:
                    return await tool_func(*args, **kwargs)
                except Exception as e:
                    if is_retryable_exception(e) and attempt < attempts:
                        logger.warning(
                            f"Tool '{tool_name}' failed with retryable error (attempt {attempt}/{attempts}). "
                            f"Retrying in {delay}s... Error: {e}"
                        )
                        await asyncio.sleep(delay)
                    else:
                        raise

        return async_wrapped
    else:

        @functools.wraps(tool_func)
        def sync_wrapped(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(1, attempts + 1):
                try:
                    return tool_func(*args, **kwargs)
                except Exception as e:
                    if is_retryable_exception(e) and attempt < attempts:
                        logger.warning(
                            f"Tool '{tool_name}' failed with retryable error (attempt {attempt}/{attempts}). "
                            f"Retrying in {delay}s... Error: {e}"
                        )
                        time.sleep(delay)
                    else:
                        raise

        return sync_wrapped
