"""
Enhanced Retry Logic for OpenAI API Calls (Issue #29)

Implements smart timeout and retry logic with exponential backoff, fast failure modes,
and jitter to prevent thundering herd problems. Provides production-ready retry
patterns specifically tuned for OpenAI API characteristics.
"""

import asyncio
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from functools import wraps

logger = logging.getLogger(__name__)


class RetryStrategy(Enum):
    """Different retry strategies for different types of operations."""

    EXPONENTIAL_BACKOFF = "exponential_backoff"
    FIXED_DELAY = "fixed_delay"
    LINEAR_BACKOFF = "linear_backoff"


class ErrorType(Enum):
    """Classification of errors for retry decision making."""

    RETRYABLE = "retryable"  # Temporary errors worth retrying
    NON_RETRYABLE = "non_retryable"  # Permanent errors, fail fast
    RATE_LIMITED = "rate_limited"  # Rate limit errors, longer backoff
    TIMEOUT = "timeout"  # Timeout errors, may need different strategy


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    base_delay: float = 1.0  # Base delay in seconds
    max_delay: float = 60.0  # Maximum delay between retries
    exponential_base: float = 2.0  # Base for exponential backoff
    jitter: bool = True  # Add random jitter to prevent thundering herd
    jitter_range: float = 0.1  # Jitter as percentage of delay (0.1 = ±10%)
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF

    # Fast failure configurations
    fail_fast_on_auth: bool = True  # Don't retry authentication errors
    fail_fast_on_quota: bool = True  # Don't retry quota exceeded errors
    fail_fast_on_invalid: bool = True  # Don't retry invalid request errors

    # Rate limiting specific
    rate_limit_backoff_multiplier: float = 2.0  # Extra backoff for rate limits

    # Timeout escalation
    timeout_escalation: bool = True  # Increase timeout on subsequent attempts
    timeout_multiplier: float = 1.5  # Multiply timeout by this factor each retry


class RetryableError(Exception):
    """Exception that indicates an operation should be retried."""

    def __init__(
        self, message: str, error_type: ErrorType, original_error: Exception | None = None
    ):
        super().__init__(message)
        self.error_type = error_type
        self.original_error = original_error


class OpenAIErrorClassifier:
    """Classifies OpenAI API errors for retry decisions."""

    @staticmethod
    def classify_error(error: Exception) -> ErrorType:
        """Classify an error to determine retry strategy."""
        error_str = str(error).lower()
        error_type_name = type(error).__name__.lower()

        # Authentication errors - fail fast
        if any(
            term in error_str
            for term in ["unauthorized", "invalid api key", "authentication", "api_key"]
        ):
            return ErrorType.NON_RETRYABLE

        # Rate limiting - special handling
        if any(term in error_str for term in ["rate limit", "quota", "too many requests"]):
            return ErrorType.RATE_LIMITED

        # Invalid requests - fail fast
        if any(term in error_str for term in ["invalid request", "bad request", "validation"]):
            return ErrorType.NON_RETRYABLE

        # Timeout errors - retryable with escalation
        if (
            any(term in error_str for term in ["timeout", "timed out"])
            or "timeout" in error_type_name
        ):
            return ErrorType.TIMEOUT

        # Network/connection errors - retryable
        if any(term in error_str for term in ["connection", "network", "host", "dns", "ssl"]):
            return ErrorType.RETRYABLE

        # Server errors (5xx) - retryable
        if any(
            term in error_str
            for term in ["server error", "internal error", "5", "service unavailable"]
        ):
            return ErrorType.RETRYABLE

        # Default to retryable for unknown errors
        return ErrorType.RETRYABLE

    @staticmethod
    def should_retry(error: Exception, config: RetryConfig) -> bool:
        """Determine if an error should be retried based on configuration."""
        error_type = OpenAIErrorClassifier.classify_error(error)

        if error_type == ErrorType.NON_RETRYABLE:
            return False

        return not (error_type == ErrorType.RATE_LIMITED and config.fail_fast_on_quota)


class EnhancedRetry:
    """Enhanced retry decorator with OpenAI-specific optimizations."""

    def __init__(self, config: RetryConfig | None = None):
        self.config = config or RetryConfig()

    def __call__(self, func: Callable) -> Callable:
        """Decorator that adds enhanced retry logic to a function."""
        if asyncio.iscoroutinefunction(func):
            return self._wrap_async(func)
        return self._wrap_sync(func)

    def _wrap_async(self, func: Callable) -> Callable:
        """Wrap an async function with retry logic."""

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_error = None

            for attempt in range(1, self.config.max_attempts + 1):
                try:
                    # Apply timeout escalation if enabled
                    if self.config.timeout_escalation and "timeout" in kwargs:
                        original_timeout = kwargs["timeout"]
                        escalated_timeout = original_timeout * (
                            self.config.timeout_multiplier ** (attempt - 1)
                        )
                        kwargs["timeout"] = min(escalated_timeout, self.config.max_delay * 3)
                        logger.debug(
                            f"Attempt {attempt}: timeout escalated to {kwargs['timeout']:.1f}s"
                        )

                    result = await func(*args, **kwargs)

                    # Log successful retry
                    if attempt > 1:
                        logger.info(f"Function {func.__name__} succeeded on attempt {attempt}")

                    return result

                except Exception as error:
                    last_error = error

                    # Check if we should retry this error
                    if not OpenAIErrorClassifier.should_retry(error, self.config):
                        logger.exception(f"Non-retryable error in {func.__name__}: {error}")
                        raise error

                    # Don't retry on the last attempt
                    if attempt == self.config.max_attempts:
                        logger.exception(
                            f"Function {func.__name__} failed after {attempt} attempts: {error}"
                        )
                        raise error

                    # Calculate delay
                    delay = self._calculate_delay(attempt, error)
                    logger.warning(
                        f"Attempt {attempt}/{self.config.max_attempts} failed for {func.__name__}: {error}. Retrying in {delay:.2f}s"
                    )

                    # Wait before retrying
                    await asyncio.sleep(delay)

            # This should never be reached, but just in case
            raise last_error

        return async_wrapper

    def _wrap_sync(self, func: Callable) -> Callable:
        """Wrap a sync function with retry logic."""

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_error = None

            for attempt in range(1, self.config.max_attempts + 1):
                try:
                    result = func(*args, **kwargs)

                    # Log successful retry
                    if attempt > 1:
                        logger.info(f"Function {func.__name__} succeeded on attempt {attempt}")

                    return result

                except Exception as error:
                    last_error = error

                    # Check if we should retry this error
                    if not OpenAIErrorClassifier.should_retry(error, self.config):
                        logger.exception(f"Non-retryable error in {func.__name__}: {error}")
                        raise error

                    # Don't retry on the last attempt
                    if attempt == self.config.max_attempts:
                        logger.exception(
                            f"Function {func.__name__} failed after {attempt} attempts: {error}"
                        )
                        raise error

                    # Calculate delay
                    delay = self._calculate_delay(attempt, error)
                    logger.warning(
                        f"Attempt {attempt}/{self.config.max_attempts} failed for {func.__name__}: {error}. Retrying in {delay:.2f}s"
                    )

                    # Wait before retrying
                    time.sleep(delay)

            # This should never be reached, but just in case
            raise last_error

        return sync_wrapper

    def _calculate_delay(self, attempt: int, error: Exception) -> float:
        """Calculate delay before next retry attempt."""
        error_type = OpenAIErrorClassifier.classify_error(error)

        # Base delay calculation
        if self.config.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            delay = self.config.base_delay * (self.config.exponential_base ** (attempt - 1))
        elif self.config.strategy == RetryStrategy.LINEAR_BACKOFF:
            delay = self.config.base_delay * attempt
        else:  # FIXED_DELAY
            delay = self.config.base_delay

        # Apply special handling for rate limits
        if error_type == ErrorType.RATE_LIMITED:
            delay *= self.config.rate_limit_backoff_multiplier
            logger.info(
                f"Rate limit detected, applying {self.config.rate_limit_backoff_multiplier}x backoff multiplier"
            )

        # Cap at maximum delay
        delay = min(delay, self.config.max_delay)

        # Add jitter to prevent thundering herd
        if self.config.jitter:
            jitter_amount = delay * self.config.jitter_range
            jitter = random.uniform(-jitter_amount, jitter_amount)  # noqa: S311
            delay += jitter
            delay = max(0.1, delay)  # Ensure positive delay

        return delay


# Convenience factory functions for common retry configurations


def create_vision_retry(max_attempts: int = 3, base_timeout: float = 30.0) -> EnhancedRetry:
    """Create retry configuration optimized for OpenAI Vision API calls."""
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=2.0,  # Longer base delay for vision calls
        max_delay=120.0,  # Higher max delay for complex vision tasks
        exponential_base=2.0,
        timeout_escalation=True,
        timeout_multiplier=1.5,
        rate_limit_backoff_multiplier=3.0,  # Vision API has stricter rate limits
    )
    return EnhancedRetry(config)


def create_text_retry(max_attempts: int = 3) -> EnhancedRetry:
    """Create retry configuration optimized for OpenAI text API calls."""
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=1.0,
        max_delay=60.0,
        exponential_base=2.0,
        timeout_escalation=True,
        timeout_multiplier=1.3,
        rate_limit_backoff_multiplier=2.0,
    )
    return EnhancedRetry(config)


def create_embedding_retry(max_attempts: int = 3) -> EnhancedRetry:
    """Create retry configuration optimized for OpenAI embedding API calls."""
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=0.5,  # Faster for embedding calls
        max_delay=30.0,  # Lower max delay for embeddings
        exponential_base=1.8,  # Slightly gentler exponential backoff
        timeout_escalation=True,
        timeout_multiplier=1.2,
        rate_limit_backoff_multiplier=1.5,
    )
    return EnhancedRetry(config)


def create_batch_retry(max_attempts: int = 2) -> EnhancedRetry:
    """Create retry configuration for batch operations (fewer retries)."""
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=3.0,  # Longer delay for batch operations
        max_delay=180.0,  # Much higher max delay for large batches
        exponential_base=2.5,  # More aggressive backoff
        timeout_escalation=True,
        timeout_multiplier=2.0,  # Aggressive timeout escalation
        rate_limit_backoff_multiplier=4.0,  # Very long backoff for batch rate limits
    )
    return EnhancedRetry(config)


# Legacy compatibility wrapper
def enhanced_retry_api_call(
    max_attempts: int = 3, timeout: float | None = None, retry_type: str = "text"
) -> Callable:
    """
    Enhanced version of the original retry_api_call decorator.

    Args:
        max_attempts: Maximum number of retry attempts
        timeout: Optional timeout in seconds
        retry_type: Type of retry configuration ("vision", "text", "embedding", "batch")
    """
    if retry_type == "vision":
        retry_decorator = create_vision_retry(max_attempts)
    elif retry_type == "embedding":
        retry_decorator = create_embedding_retry(max_attempts)
    elif retry_type == "batch":
        retry_decorator = create_batch_retry(max_attempts)
    else:  # Default to text
        retry_decorator = create_text_retry(max_attempts)

    def decorator(func):
        # Apply the enhanced retry
        enhanced_func = retry_decorator(func)

        # If timeout is specified, wrap with timeout handling
        if timeout is not None:
            if asyncio.iscoroutinefunction(func):

                @wraps(enhanced_func)
                async def timeout_wrapper(*args, **kwargs):
                    return await asyncio.wait_for(enhanced_func(*args, **kwargs), timeout=timeout)

                return timeout_wrapper
            # For sync functions, timeout handling is more complex and not implemented here
            logger.warning(
                "Timeout handling for sync functions not implemented in enhanced_retry_api_call"
            )
            return enhanced_func

        return enhanced_func

    return decorator


# Circuit breaker pattern for additional resilience
class CircuitBreaker:
    """Circuit breaker pattern to prevent cascading failures."""

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: float = 60.0,
        expected_exception: type[Exception] = Exception,
    ):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    def __call__(self, func: Callable) -> Callable:
        """Decorator that applies circuit breaker pattern."""

        @wraps(func)
        async def wrapper(*args, **kwargs):
            if self.state == "OPEN":
                if time.time() - self.last_failure_time > self.timeout:
                    self.state = "HALF_OPEN"
                    logger.info(f"Circuit breaker for {func.__name__} moving to HALF_OPEN state")
                else:
                    raise Exception(f"Circuit breaker OPEN for {func.__name__}")

            try:
                result = await func(*args, **kwargs)
                if self.state == "HALF_OPEN":
                    self.state = "CLOSED"
                    self.failure_count = 0
                    logger.info(f"Circuit breaker for {func.__name__} restored to CLOSED state")
                return result
            except self.expected_exception as e:
                self.failure_count += 1
                self.last_failure_time = time.time()

                if self.failure_count >= self.failure_threshold:
                    self.state = "OPEN"
                    logger.exception(
                        f"Circuit breaker OPENED for {func.__name__} after {self.failure_count} failures"
                    )

                raise e

        return wrapper


# Export the main interfaces
__all__ = [
    "CircuitBreaker",
    "EnhancedRetry",
    "ErrorType",
    "OpenAIErrorClassifier",
    "RetryConfig",
    "RetryStrategy",
    "create_batch_retry",
    "create_embedding_retry",
    "create_text_retry",
    "create_vision_retry",
    "enhanced_retry_api_call",
]
