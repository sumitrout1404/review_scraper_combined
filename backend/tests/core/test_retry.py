import pytest

from core.retry import RetryableError, backoff_delay, retry_call


def test_retries_until_success() -> None:
    calls = {"n": 0}
    sleeps: list[float] = []

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RetryableError("transient")
        return "ok"

    assert retry_call(flaky, attempts=4, sleep=sleeps.append) == "ok"
    assert calls["n"] == 3 and len(sleeps) == 2


def test_non_retryable_raises_immediately() -> None:
    calls = {"n": 0}

    def bad() -> None:
        calls["n"] += 1
        raise ValueError("permanent")

    with pytest.raises(ValueError):
        retry_call(bad, attempts=5, sleep=lambda _: None)
    assert calls["n"] == 1


def test_gives_up_after_attempts() -> None:
    with pytest.raises(RetryableError):
        retry_call(lambda: (_ for _ in ()).throw(RetryableError("x")), attempts=2, sleep=lambda _: None)


def test_retry_after_is_honoured_and_capped() -> None:
    assert backoff_delay(1, 1.0, 30.0, retry_after=7) == 7
    assert backoff_delay(1, 1.0, 30.0, retry_after=120) == 30
    assert 0 <= backoff_delay(3, 1.0, 30.0) <= 4
