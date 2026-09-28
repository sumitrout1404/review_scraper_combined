"""Optional raw-response capture for debugging markup/API drift.

Disabled by default (``COLLECTOR_SAVE_RAW=1`` enables it). Files go to the
gitignored ``backend/.cache/collector/`` directory and contain response bodies
only – never request headers or cookies.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class RawCapture:
    """Writes response bodies to ``<root>/<strategy>/<property>_<offset>.<ext>`` when enabled."""

    def __init__(self, root: Path, enabled: bool) -> None:
        self._root = root
        self.enabled = enabled

    def save(self, strategy: str, property_id: str, offset: int, ext: str, body: str) -> None:
        if not self.enabled:
            return
        try:
            target = self._root / strategy / f"{property_id}_{offset:05d}.{ext}"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
        except OSError as exc:  # debugging aid only; never fail a run because of it
            logger.warning("raw capture failed: %s", exc)
