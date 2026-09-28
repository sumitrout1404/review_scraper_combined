"""A small, thread-safe circuit breaker.

States:
    CLOSED     – calls flow normally; consecutive failures are counted.
    OPEN       – calls are rejected immediately with ``CircuitOpenError`` until
                 ``recovery_timeout`` seconds have passed.
    HALF_OPEN  – a single trial call is allowed; success closes the circuit,
                 failure re-opens it.

Used to stop hammering a dependency (Booking.com, the Groq API) once it is
clearly failing, so callers can fall back quickly instead of piling up retries.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from enum import Enum
from typing import TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when a call is attempted while the circuit is open."""

    def __init__(self, name: str, retry_in_s: float) -> None:
        super().__init__(f"circuit '{name}' is open; retry in {retry_in_s:.0f}s")
        self.name = name
        self.retry_in_s = retry_in_s


class CircuitBreaker:
    """Counts consecutive failures and short-circuits calls once a threshold is hit."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be > 0")
        self.name = name
        self._threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._clock = clock
        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._trial_in_flight = False

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._current_state()

    def allow_request(self) -> bool:
        """Return True if a call may proceed now (reserves the half-open trial slot)."""
        with self._lock:
            state = self._current_state()
            if state is CircuitState.CLOSED:
                return True
            if state is CircuitState.HALF_OPEN and not self._trial_in_flight:
                self._trial_in_flight = True
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            if self._state is not CircuitState.CLOSED:
                logger.info("circuit '%s' closed after successful trial", self.name)
            self._state = CircuitState.CLOSED
            self._failures = 0
            self._trial_in_flight = False

    def record_failure(self) -> None:
        with self._lock:
            self._trial_in_flight = False
            self._failures += 1
            state = self._current_state()
            if state is CircuitState.HALF_OPEN or self._failures >= self._threshold:
                self._open()

    def call(self, fn: Callable[..., T], *args: object, **kwargs: object) -> T:
        """Invoke ``fn`` through the breaker, recording the outcome."""
        if not self.allow_request():
            raise CircuitOpenError(self.name, self._retry_in())
        try:
            result = fn(*args, **kwargs)
        except Exception:
            self.record_failure()
            raise
        self.record_success()
        return result

    # -- internals (caller must hold the lock) ---------------------------------

    def _current_state(self) -> CircuitState:
        if (
            self._state is CircuitState.OPEN
            and self._clock() - self._opened_at >= self._recovery_timeout
        ):
            self._state = CircuitState.HALF_OPEN
        return self._state

    def _open(self) -> None:
        if self._state is not CircuitState.OPEN:
            logger.warning(
                "circuit '%s' opened after %d consecutive failures", self.name, self._failures
            )
        self._state = CircuitState.OPEN
        self._opened_at = self._clock()

    def _retry_in(self) -> float:
        with self._lock:
            return max(0.0, self._recovery_timeout - (self._clock() - self._opened_at))
