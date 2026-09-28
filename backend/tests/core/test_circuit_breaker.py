import pytest

from core.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _boom() -> None:
    raise ValueError("boom")


def test_opens_after_threshold_and_rejects_calls() -> None:
    breaker = CircuitBreaker("t", failure_threshold=2, recovery_timeout=10, clock=FakeClock())
    for _ in range(2):
        with pytest.raises(ValueError):
            breaker.call(_boom)
    assert breaker.state is CircuitState.OPEN
    with pytest.raises(CircuitOpenError):
        breaker.call(lambda: "never")


def test_half_open_trial_success_closes() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker("t", failure_threshold=1, recovery_timeout=10, clock=clock)
    with pytest.raises(ValueError):
        breaker.call(_boom)
    clock.now = 11
    assert breaker.state is CircuitState.HALF_OPEN
    assert breaker.call(lambda: "ok") == "ok"
    assert breaker.state is CircuitState.CLOSED


def test_half_open_trial_failure_reopens_and_allows_single_trial() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker("t", failure_threshold=3, recovery_timeout=10, clock=clock)
    for _ in range(3):
        breaker.record_failure()
    clock.now = 10
    assert breaker.allow_request() is True
    assert breaker.allow_request() is False  # only one trial in flight
    breaker.record_failure()
    assert breaker.state is CircuitState.OPEN


def test_success_resets_failure_count() -> None:
    breaker = CircuitBreaker("t", failure_threshold=2, clock=FakeClock())
    breaker.record_failure()
    breaker.record_success()
    breaker.record_failure()
    assert breaker.state is CircuitState.CLOSED
