import asyncio
import functools
import inspect
import re
import time
from typing import Any, Callable

from pydantic import BaseModel, Field

from src.utils.logger import get_logger

logger = get_logger(__name__)


class RetryConfig(BaseModel):
    attempts: int = Field(default=3, ge=1)
    delay: float = Field(default=5.0, ge=0.0)


def is_retryable_exception(exc: Exception) -> bool:
    """Check if the given exception is retryable based on HTTP/gRPC status codes, connection errors, or messages."""
    # 1. Check for standard connection and timeout exceptions
    if isinstance(exc, (TimeoutError, ConnectionError, asyncio.TimeoutError)):
        return True

    # 2. Check class name for common connection/timeout exception naming patterns
    cls_name = exc.__class__.__name__
    if any(
        term in cls_name
        for term in (
            "Timeout",
            "ConnectError",
            "ConnectTimeout",
            "ReadTimeout",
            "WriteTimeout",
            "PoolTimeout",
            "NetworkError",
            "APIConnectionError",
            "APIConnection",
        )
    ):
        return True

    # 3. Check for status_code attribute
    status_code = getattr(exc, "status_code", None)

    # 4. Check for code attribute (google.api_core.exceptions or other libraries)
    if status_code is None:
        status_code = getattr(exc, "code", None)

    # 5. Check for response status_code (httpx or requests)
    if status_code is None and hasattr(exc, "response"):
        response = getattr(exc, "response")
        if response is not None and hasattr(response, "status_code"):
            status_code = getattr(response, "status_code")

    # 6. Check for HTTPError/HttpError status codes (googleapiclient.errors.HttpError)
    if status_code is None:
        resp = getattr(exc, "resp", None)
        if resp and hasattr(resp, "status"):
            status_code = getattr(resp, "status")

    # If we got a numeric status code, check if it's retryable
    if isinstance(status_code, int):
        # 503 (Service Unavailable), 429 (Too Many Requests), 502 (Bad Gateway),
        # 504 (Gateway Timeout), 500 (Internal Server Error), 408 (Request Timeout)
        return status_code in (503, 429, 502, 504, 500, 408)

    # Check string representation for indications of transient/overload errors
    exc_str = str(exc).lower()

    # Guard: if it's explicitly a permanent error code on word boundaries or a non-retryable message, return False
    if any(
        term in exc_str
        for term in (
            "unauthorized",
            "forbidden",
            "not found",
            "bad request",
            "invalid argument",
            "permission denied",
            "validation error",
        )
    ) or any(re.search(r"\b" + code + r"\b", exc_str) for code in ("400", "401", "403", "404")):
        return False

    # Check for retryable terms or status codes on word boundaries
    if any(
        term in exc_str
        for term in (
            "service unavailable",
            "resource exhausted",
            "too many requests",
            "rate limit",
            "quota",
            "unavailable",
            "temporary",
            "transient",
            "overloaded",
            "deadline exceeded",
            "timeout",
            "timed out",
        )
    ) or any(
        re.search(r"\b" + code + r"\b", exc_str)
        for code in ("500", "502", "503", "504", "429", "408")
    ):
        return True

    return False


async def retry_async(
    func: Callable[..., Any],
    retry_config: RetryConfig,
    on_retry: Callable[[Exception, int, int], None] | None = None,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Executes an async callable inside a retry loop for transient errors."""
    attempts = retry_config.attempts
    delay = retry_config.delay
    for attempt in range(1, attempts + 1):
        try:
            res = func(*args, **kwargs)
            if inspect.isawaitable(res):
                return await res
            return res
        except Exception as e:
            if is_retryable_exception(e) and attempt < attempts:
                if on_retry:
                    on_retry(e, attempt, attempts)
                await asyncio.sleep(delay)
            else:
                raise


def retry_sync(
    func: Callable[..., Any],
    retry_config: RetryConfig,
    on_retry: Callable[[Exception, int, int], None] | None = None,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Executes a sync callable inside a retry loop for transient errors."""
    attempts = retry_config.attempts
    delay = retry_config.delay
    for attempt in range(1, attempts + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if is_retryable_exception(e) and attempt < attempts:
                if on_retry:
                    on_retry(e, attempt, attempts)
                time.sleep(delay)
            else:
                raise


def wrap_tool_with_retry(
    tool_func: Callable[..., Any], retry_config: RetryConfig
) -> Callable[..., Any]:
    """Wraps a tool callable to retry execution if it encounters retryable exceptions."""
    tool_name = getattr(tool_func, "__name__", "unknown_tool")

    if inspect.iscoroutinefunction(tool_func):

        @functools.wraps(tool_func)
        async def async_wrapped(*args: Any, **kwargs: Any) -> Any:
            def log_retry(e: Exception, attempt: int, attempts: int):
                logger.warning(
                    f"Tool '{tool_name}' failed with retryable error (attempt {attempt}/{attempts}). "
                    f"Retrying in {retry_config.delay}s... Error: {e}"
                )

            return await retry_async(tool_func, retry_config, log_retry, *args, **kwargs)

        return async_wrapped
    else:

        @functools.wraps(tool_func)
        def sync_wrapped(*args: Any, **kwargs: Any) -> Any:
            def log_retry(e: Exception, attempt: int, attempts: int):
                logger.warning(
                    f"Tool '{tool_name}' failed with retryable error (attempt {attempt}/{attempts}). "
                    f"Retrying in {retry_config.delay}s... Error: {e}"
                )

            return retry_sync(tool_func, retry_config, log_retry, *args, **kwargs)

        return sync_wrapped
