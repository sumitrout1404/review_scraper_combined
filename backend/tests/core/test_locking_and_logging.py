import logging
import os
import time
from pathlib import Path

import pytest

from core.locking import LockHeldError, run_lock
from core.logging import RedactingFilter, redact


def test_lock_is_exclusive_and_released(tmp_path: Path) -> None:
    lock = tmp_path / "run.lock"
    with run_lock(lock), pytest.raises(LockHeldError), run_lock(lock):
        pass
    assert not lock.exists()


def test_stale_lock_is_reclaimed(tmp_path: Path) -> None:
    lock = tmp_path / "run.lock"
    lock.write_text("{}")
    old = time.time() - 7200
    os.utime(lock, (old, old))
    with run_lock(lock, stale_after_s=3600):
        pass


def test_redact_masks_credentials() -> None:
    text = "key gsk_abcdefghijklmnop1234 auth Bearer abc.def.ghi123 api_key=secret123"
    out = redact(text)
    assert "gsk_" not in out and "abc.def" not in out and "secret123" not in out
    assert out.count("[REDACTED]") == 3


def test_filter_redacts_formatted_args() -> None:
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "token %s", ("gsk_abcdefghijklmnop",), None)
    RedactingFilter().filter(record)
    assert "gsk_" not in record.getMessage()
