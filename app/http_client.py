import logging
import time
from functools import lru_cache
from typing import Any

import httpx
import pybreaker

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_RETRIES = 3
CIRCUIT_BREAKER_FAIL_MAX = 5
CIRCUIT_BREAKER_RESET_TIMEOUT = 60


class CircuitBreakerError(Exception):
    pass


class ResilientHttpClient:
    _circuit_breakers: dict[str, pybreaker.CircuitBreaker] = {}

    def __init__(
        self,
        name: str = "default",
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        retries: int = DEFAULT_RETRIES,
    ) -> None:
        self.name = name
        self.timeout = timeout
        self.retries = retries
        self._breaker = self._get_breaker(name)

    @classmethod
    def _get_breaker(cls, name: str) -> pybreaker.CircuitBreaker:
        if name not in cls._circuit_breakers:
            cls._circuit_breakers[name] = pybreaker.CircuitBreaker(
                fail_max=CIRCUIT_BREAKER_FAIL_MAX,
                reset_timeout=CIRCUIT_BREAKER_RESET_TIMEOUT,
                exclude=[httpx.TimeoutException],
            )
        return cls._circuit_breakers[name]

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._call_with_retry("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._call_with_retry("POST", url, **kwargs)

    def _call_with_retry(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        timeout = kwargs.pop("timeout", self.timeout)
        last_exception: Exception | None = None

        for attempt in range(self.retries):
            try:
                response = self._breaker.call(self._do_request, method, url, timeout, **kwargs)
                if attempt > 0:
                    logger.info(
                        "Request succeeded after %d retries",
                        attempt,
                        extra={"url": url, "attempt": attempt},
                    )
                return response
            except pybreaker.CircuitBreakerError:
                logger.warning(
                    "Circuit breaker open for %s",
                    self.name,
                    extra={"url": url},
                )
                raise CircuitBreakerError(f"Circuit breaker open for {self.name}")
            except httpx.TimeoutException as e:
                last_exception = e
                logger.warning(
                    "Request timeout (attempt %d/%d)",
                    attempt + 1,
                    self.retries,
                    extra={"url": url, "attempt": attempt + 1},
                )
            except httpx.HTTPStatusError as e:
                last_exception = e
                if e.response.status_code < 500:
                    logger.warning(
                        "Client error %d, not retrying",
                        e.response.status_code,
                        extra={"url": url, "status": e.response.status_code},
                    )
                    raise
                logger.warning(
                    "Server error %d (attempt %d/%d)",
                    e.response.status_code,
                    attempt + 1,
                    self.retries,
                    extra={"url": url, "status": e.response.status_code},
                )
            except httpx.RequestError as e:
                last_exception = e
                logger.warning(
                    "Request error (attempt %d/%d): %s",
                    attempt + 1,
                    self.retries,
                    str(e),
                    extra={"url": url, "attempt": attempt + 1},
                )

            if attempt < self.retries - 1:
                sleep_time = (2**attempt) * 0.5
                time.sleep(sleep_time)

        logger.error(
            "All %d retries exhausted for %s",
            self.retries,
            url,
            extra={"url": url},
        )
        if last_exception:
            raise last_exception
        raise httpx.RequestError(f"All retries exhausted for {url}")

    def _do_request(
        self, method: str, url: str, timeout: float, **kwargs: Any
    ) -> httpx.Response:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            request_method = getattr(client, method.lower())
            return request_method(url, **kwargs)


@lru_cache(maxsize=128)
def get_http_client(name: str = "default") -> ResilientHttpClient:
    return ResilientHttpClient(name=name)
