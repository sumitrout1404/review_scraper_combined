"""Minimal Groq (OpenAI-compatible) chat-completions client over httpx.

- JSON mode (``response_format: json_object``), temperature 0.
- Retries timeouts / 429 / 5xx with backoff, honouring ``Retry-After`` (core.retry).
- Wrapped in a circuit breaker (core.circuit_breaker): after N failed batches the
  breaker opens and callers fall back to rules immediately.
- Never logs the API key or request headers.
"""
from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from analysis.settings import AnalysisSettings
from core.circuit_breaker import CircuitBreaker
from core.retry import RetryableError, retry_call

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})
CHARS_PER_TOKEN = 4
_DURATION_RE = re.compile(r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m(?!s))?(?:(\d+(?:\.\d+)?)s)?(?:(\d+(?:\.\d+)?)ms)?$")


class LLMError(Exception):
    """A non-retryable LLM failure (bad request, auth, invalid output after retries)."""


class LLMUnavailableError(LLMError):
    """The LLM should not be used for the rest of this run (auth / quota / long back-off / budget)."""


@dataclass(frozen=True)
class ChatResult:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class ChatClient(Protocol):
    """What the classifier needs from an LLM client (mocked in tests)."""

    model: str

    def complete_json(self, system: str, user: str, max_tokens: int) -> ChatResult: ...


def parse_duration(raw: str | None) -> float | None:
    """Parse Groq reset durations such as '2.047s', '1m26.4s', '450ms' into seconds."""
    if not raw:
        return None
    match = _DURATION_RE.match(raw.strip())
    if not match or not any(match.groups()):
        return None
    hours, minutes, seconds, millis = (float(g) if g else 0.0 for g in match.groups())
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    try:
        return float(raw) if raw is not None else None
    except ValueError:
        return None


def _error_code(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    error = body.get("error") if isinstance(body, dict) else None
    return str(error.get("code") or error.get("type") or "") if isinstance(error, dict) else ""


class GroqClient:
    """Groq chat client with retries + circuit breaker. One instance per analysis run."""

    def __init__(
        self,
        settings: AnalysisSettings,
        *,
        http_client: httpx.Client | None = None,
        breaker: CircuitBreaker | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not settings.groq_api_key:
            raise LLMUnavailableError("GROQ_API_KEY is not set")
        self.model = settings.groq_model
        self._settings = settings
        self._url = f"{settings.groq_base_url}/chat/completions"
        self._http = http_client or httpx.Client(timeout=settings.request_timeout_s)
        self._breaker = breaker or CircuitBreaker(
            "groq", failure_threshold=settings.breaker_failure_threshold,
            recovery_timeout=settings.breaker_recovery_s,
        )
        self._sleep = sleep
        self._clock = clock
        self._last_request_at: float | None = None
        self._tokens_remaining: int | None = None
        self._tokens_reset_at = 0.0
        self.deadline: float | None = None   # monotonic time after which no new waits are started

    @property
    def breaker(self) -> CircuitBreaker:
        return self._breaker

    def close(self) -> None:
        self._http.close()

    def complete_json(self, system: str, user: str, max_tokens: int) -> ChatResult:
        """One JSON-mode completion. Raises CircuitOpenError, LLMUnavailableError or LLMError."""
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if self._settings.reasoning_effort:
            payload["reasoning_effort"] = self._settings.reasoning_effort
        expected_tokens = (len(system) + len(user)) // CHARS_PER_TOKEN + max_tokens // 2
        return self._breaker.call(
            retry_call,
            lambda: self._post(payload, expected_tokens),
            attempts=self._settings.retry_attempts,
            base_delay=self._settings.retry_base_delay_s,
            max_delay=self._settings.retry_max_delay_s,
            is_retryable=lambda exc: isinstance(exc, RetryableError),
            sleep=self._bounded_sleep,
            on_retry=self._log_retry,
        )

    # -- internals ----------------------------------------------------------------------------

    def _post(self, payload: dict[str, Any], expected_tokens: int) -> ChatResult:
        self._pace(expected_tokens)
        headers = {"Authorization": f"Bearer {self._settings.groq_api_key}"}
        try:
            response = self._http.post(self._url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise RetryableError(f"groq timeout: {type(exc).__name__}") from None
        except httpx.TransportError as exc:
            raise RetryableError(f"groq transport error: {type(exc).__name__}") from None
        finally:
            self._last_request_at = self._clock()
        self._remember_token_budget(response)
        return self._parse(response)

    def _parse(self, response: httpx.Response) -> ChatResult:
        status = response.status_code
        if status in _RETRYABLE_STATUS:
            retry_after = _retry_after_seconds(response)
            if retry_after is not None and retry_after > self._settings.retry_max_delay_s:
                raise LLMUnavailableError(f"groq rate limited for {retry_after:.0f}s (status {status})")
            raise RetryableError(f"groq status {status}", retry_after=retry_after)
        if status in (401, 403):
            raise LLMUnavailableError(f"groq rejected credentials (status {status})")
        if status == 404:
            raise LLMUnavailableError(f"groq model '{self.model}' not available (status 404)")
        if status == 400 and _error_code(response) == "json_validate_failed":
            raise RetryableError("groq could not produce valid JSON")   # sampling issue: try again
        if status >= 400:
            raise LLMError(f"groq status {status} ({_error_code(response) or 'error'})")
        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError):
            raise LLMError("groq returned an unexpected response body") from None
        usage = body.get("usage") or {}
        return ChatResult(content, int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0))

    def _remember_token_budget(self, response: httpx.Response) -> None:
        """Track Groq's per-minute token budget from the x-ratelimit-* headers."""
        remaining = response.headers.get("x-ratelimit-remaining-tokens")
        reset = parse_duration(response.headers.get("x-ratelimit-reset-tokens"))
        if remaining is not None and remaining.isdigit() and reset is not None:
            self._tokens_remaining = int(remaining)
            self._tokens_reset_at = self._clock() + reset

    def _pace(self, expected_tokens: int) -> None:
        """Space requests (RPM) and wait for the token window to refill (TPM) instead of eating 429s."""
        now = self._clock()
        waits = [0.0]
        if self._last_request_at is not None:
            waits.append(self._settings.min_request_interval_s - (now - self._last_request_at))
        if self._tokens_remaining is not None and self._tokens_remaining < expected_tokens:
            waits.append(self._tokens_reset_at - now)
        wait = max(waits)
        if wait > 0:
            logger.debug("pacing groq requests: waiting %.1fs", wait)
            self._bounded_sleep(min(wait, self._settings.retry_max_delay_s))

    def _bounded_sleep(self, seconds: float) -> None:
        if self.deadline is not None and self._clock() + seconds > self.deadline:
            raise LLMUnavailableError("time budget exhausted while waiting for the LLM")
        self._sleep(seconds)

    @staticmethod
    def _log_retry(attempt: int, exc: BaseException, delay: float) -> None:
        logger.warning("groq attempt %d failed (%s); retrying in %.1fs", attempt, exc, delay)
