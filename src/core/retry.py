"""
Error handling and retry logic for Trace.

P9-04: Error handling & retry logic
Provides exponential backoff retry for LLM failures and transient errors.
"""

import dataclasses
import functools
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ParamSpec, TypeVar

logger = logging.getLogger(__name__)

# Type variables for generic retry decorator
P = ParamSpec("P")
T = TypeVar("T")


# Default retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0
DEFAULT_MAX_DELAY = 60.0
DEFAULT_EXPONENTIAL_BASE = 2.0
DEFAULT_JITTER_FACTOR = 0.1


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = DEFAULT_MAX_RETRIES
    base_delay: float = DEFAULT_BASE_DELAY
    max_delay: float = DEFAULT_MAX_DELAY
    exponential_base: float = DEFAULT_EXPONENTIAL_BASE
    jitter_factor: float = DEFAULT_JITTER_FACTOR
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,)

    def calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay for a given attempt number using exponential backoff.

        Args:
            attempt: The current attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        # Calculate exponential delay
        delay = self.base_delay * (self.exponential_base**attempt)

        # Apply jitter
        jitter = delay * self.jitter_factor * (2 * random.random() - 1)
        delay += jitter

        # Cap at max delay
        return min(delay, self.max_delay)


@dataclass
class RetryResult:
    """Result of a retry operation."""

    success: bool
    result: Any | None
    attempts: int
    total_time: float
    last_error: Exception | None = None

    @property
    def failed(self) -> bool:
        """Check if the operation failed."""
        return not self.success


class RetryError(Exception):
    """Exception raised when all retries are exhausted."""

    def __init__(
        self,
        message: str,
        attempts: int,
        last_error: Exception | None = None,
    ):
        super().__init__(message)
        self.attempts = attempts
        self.last_error = last_error


# Pre-configured retry configs for common use cases
LLM_RETRY_CONFIG = RetryConfig(
    max_retries=3,
    base_delay=1.0,
    max_delay=30.0,
    exponential_base=2.0,
    jitter_factor=0.1,
    retryable_exceptions=(
        ConnectionError,
        TimeoutError,
        OSError,
    ),
)

API_RETRY_CONFIG = RetryConfig(
    max_retries=5,
    base_delay=0.5,
    max_delay=30.0,
    exponential_base=2.0,
    jitter_factor=0.2,
    retryable_exceptions=(
        ConnectionError,
        TimeoutError,
        OSError,
    ),
)

DATABASE_RETRY_CONFIG = RetryConfig(
    max_retries=3,
    base_delay=0.1,
    max_delay=5.0,
    exponential_base=2.0,
    jitter_factor=0.1,
)


def retry_with_backoff(
    config: RetryConfig | None = None,
    max_retries: int | None = None,
    base_delay: float | None = None,
    max_delay: float | None = None,
    retryable_exceptions: tuple[type[Exception], ...] | None = None,
    on_retry: Callable[[int, Exception], None] | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator for retrying functions with exponential backoff.

    Args:
        config: RetryConfig object (overrides individual parameters)
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries
        max_delay: Maximum delay between retries
        retryable_exceptions: Exceptions that should trigger a retry
        on_retry: Callback function called on each retry

    Returns:
        Decorated function that retries on failure

    Usage:
        @retry_with_backoff(max_retries=3)
        def call_api():
            ...

        @retry_with_backoff(config=LLM_RETRY_CONFIG)
        def call_llm():
            ...
    """
    # Build config from parameters
    if config is None:
        config = RetryConfig()
    else:
        # Create a copy to avoid mutating shared configs
        config = dataclasses.replace(config)

    if max_retries is not None:
        config.max_retries = max_retries
    if base_delay is not None:
        config.base_delay = base_delay
    if max_delay is not None:
        config.max_delay = max_delay
    if retryable_exceptions is not None:
        config.retryable_exceptions = retryable_exceptions

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_error: Exception | None = None
            attempts = 0

            while attempts <= config.max_retries:
                try:
                    return func(*args, **kwargs)
                except config.retryable_exceptions as e:
                    last_error = e
                    attempts += 1

                    if attempts > config.max_retries:
                        logger.error(
                            f"All {config.max_retries} retries exhausted for {func.__name__}: {e}"
                        )
                        raise RetryError(
                            f"Failed after {attempts} attempts: {e}",
                            attempts=attempts,
                            last_error=e,
                        ) from e

                    delay = config.calculate_delay(attempts - 1)
                    logger.warning(
                        f"Retry {attempts}/{config.max_retries} for {func.__name__} "
                        f"after {delay:.2f}s: {e}"
                    )

                    if on_retry:
                        on_retry(attempts, e)

                    time.sleep(delay)

            # This should never be reached, but just in case
            raise RetryError(
                f"Unexpected retry loop exit after {attempts} attempts",
                attempts=attempts,
                last_error=last_error,
            )

        return wrapper

    return decorator


def execute_with_retry(
    func: Callable[[], T],
    config: RetryConfig | None = None,
    on_retry: Callable[[int, Exception], None] | None = None,
) -> RetryResult:
    """
    Execute a function with retry logic, returning detailed result.

    This is a non-decorator version that returns RetryResult for more
    detailed error information.

    Args:
        func: Function to execute
        config: Retry configuration
        on_retry: Callback on each retry

    Returns:
        RetryResult with success status and details
    """
    if config is None:
        config = RetryConfig()

    start_time = time.time()
    last_error: Exception | None = None
    attempts = 0

    while attempts <= config.max_retries:
        try:
            result = func()
            return RetryResult(
                success=True,
                result=result,
                attempts=attempts + 1,
                total_time=time.time() - start_time,
            )
        except config.retryable_exceptions as e:
            last_error = e
            attempts += 1

            if attempts > config.max_retries:
                break

            delay = config.calculate_delay(attempts - 1)
            logger.warning(f"Retry {attempts}/{config.max_retries} after {delay:.2f}s: {e}")

            if on_retry:
                on_retry(attempts, e)

            time.sleep(delay)

    return RetryResult(
        success=False,
        result=None,
        attempts=attempts,
        total_time=time.time() - start_time,
        last_error=last_error,
    )


async def execute_with_retry_async(
    func: Callable[[], Any],
    config: RetryConfig | None = None,
    on_retry: Callable[[int, Exception], None] | None = None,
) -> RetryResult:
    """
    Async version of execute_with_retry.

    Args:
        func: Async function to execute
        config: Retry configuration
        on_retry: Callback on each retry

    Returns:
        RetryResult with success status and details
    """
    import asyncio

    if config is None:
        config = RetryConfig()

    start_time = time.time()
    last_error: Exception | None = None
    attempts = 0

    while attempts <= config.max_retries:
        try:
            result = await func()
            return RetryResult(
                success=True,
                result=result,
                attempts=attempts + 1,
                total_time=time.time() - start_time,
            )
        except config.retryable_exceptions as e:
            last_error = e
            attempts += 1

            if attempts > config.max_retries:
                break

            delay = config.calculate_delay(attempts - 1)
            logger.warning(f"Async retry {attempts}/{config.max_retries} after {delay:.2f}s: {e}")

            if on_retry:
                on_retry(attempts, e)

            await asyncio.sleep(delay)

    return RetryResult(
        success=False,
        result=None,
        attempts=attempts,
        total_time=time.time() - start_time,
        last_error=last_error,
    )


def is_retryable_openai_error(e: Exception) -> bool:
    """
    Check if an OpenAI API error is retryable.

    Args:
        e: The exception to check

    Returns:
        True if the error is retryable
    """
    # Import openai types if available
    try:
        from openai import APIConnectionError, APITimeoutError, RateLimitError
    except ImportError:
        return False

    # Rate limit errors are retryable
    if isinstance(e, RateLimitError):
        return True

    # Connection errors are retryable
    if isinstance(e, APIConnectionError | APITimeoutError):
        return True

    # Check for transient HTTP errors
    if hasattr(e, "status_code"):
        status_code = getattr(e, "status_code", None)
        if status_code in (429, 500, 502, 503, 504):
            return True

    return False


def get_openai_retry_config() -> RetryConfig:
    """
    Get a retry config optimized for OpenAI API calls.

    Returns:
        RetryConfig for OpenAI API
    """
    try:
        from openai import APIConnectionError, APITimeoutError, RateLimitError

        return RetryConfig(
            max_retries=3,
            base_delay=1.0,
            max_delay=60.0,
            exponential_base=2.0,
            jitter_factor=0.1,
            retryable_exceptions=(
                APIConnectionError,
                APITimeoutError,
                RateLimitError,
                ConnectionError,
                TimeoutError,
            ),
        )
    except ImportError:
        return LLM_RETRY_CONFIG


# Convenience functions for common retry patterns
def retry_llm_call(func: Callable[P, T]) -> Callable[P, T]:
    """Decorator for retrying LLM API calls."""
    return retry_with_backoff(config=get_openai_retry_config())(func)


def retry_api_call(func: Callable[P, T]) -> Callable[P, T]:
    """Decorator for retrying general API calls."""
    return retry_with_backoff(config=API_RETRY_CONFIG)(func)


def retry_database_operation(func: Callable[P, T]) -> Callable[P, T]:
    """Decorator for retrying database operations."""
    import sqlite3

    config = RetryConfig(
        max_retries=3,
        base_delay=0.1,
        max_delay=5.0,
        retryable_exceptions=(
            sqlite3.OperationalError,
            sqlite3.DatabaseError,
        ),
    )
    return retry_with_backoff(config=config)(func)


if __name__ == "__main__":
    import fire

    def test_retry(
        attempts: int = 5,
        success_on: int = 3,
        delay: float = 0.5,
    ):
        """Test the retry mechanism."""
        call_count = 0

        @retry_with_backoff(max_retries=attempts, base_delay=delay)
        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < success_on:
                raise ConnectionError(f"Simulated failure {call_count}")
            return f"Success on attempt {call_count}"

        try:
            result = flaky_function()
            return {
                "success": True,
                "result": result,
                "total_calls": call_count,
            }
        except RetryError as e:
            return {
                "success": False,
                "error": str(e),
                "total_calls": call_count,
            }

    def test_result(attempts: int = 5, success_on: int = 3):
        """Test execute_with_retry."""
        call_count = 0

        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < success_on:
                raise ConnectionError(f"Simulated failure {call_count}")
            return f"Success on attempt {call_count}"

        config = RetryConfig(max_retries=attempts, base_delay=0.1)
        result = execute_with_retry(flaky_function, config)

        return {
            "success": result.success,
            "attempts": result.attempts,
            "total_time": f"{result.total_time:.2f}s",
            "result": result.result,
            "error": str(result.last_error) if result.last_error else None,
        }

    fire.Fire(
        {
            "test": test_retry,
            "test_result": test_result,
        }
    )
