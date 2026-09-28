"""Single-run lock file so two collector/analysis runs never write the DB at once."""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

logger = logging.getLogger(__name__)


class LockHeldError(RuntimeError):
    """Another run currently holds the lock."""


@contextmanager
def run_lock(path: Path | str, stale_after_s: float = 3600) -> Iterator[None]:
    """Acquire an exclusive lock file; a lock older than ``stale_after_s`` is reclaimed."""
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    _reclaim_if_stale(lock_path, stale_after_s)
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise LockHeldError(f"another run holds {lock_path}") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"pid": os.getpid(), "acquired_at": time.time()}, fh)
        yield
    finally:
        with suppress(FileNotFoundError):
            lock_path.unlink()


def _reclaim_if_stale(lock_path: Path, stale_after_s: float) -> None:
    try:
        age = time.time() - lock_path.stat().st_mtime
    except FileNotFoundError:
        return
    if age > stale_after_s:
        logger.warning("reclaiming stale lock %s (age %.0fs)", lock_path, age)
        with suppress(FileNotFoundError):
            lock_path.unlink()
