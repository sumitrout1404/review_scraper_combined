"""Logging setup with secret redaction, so keys/tokens never reach logs or CI output."""

from __future__ import annotations

import logging
import re

_SECRET_PATTERNS = [
    re.compile(r"gsk_[A-Za-z0-9]{10,}"),                       # Groq keys
    re.compile(r"sk-[A-Za-z0-9_-]{10,}"),                      # generic API keys
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"),       # Authorization headers
    re.compile(r"(?i)((?:api[_-]?key|token|secret|password|cookie)\s*[=:]\s*)[^\s,;&]+"),
]


def redact(text: str) -> str:
    """Replace anything that looks like a credential with a placeholder."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(lambda m: (m.group(1) if m.groups() else "") + "[REDACTED]", text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = None
        return True


def configure_logging(level: int | str = logging.INFO) -> None:
    """Configure root logging once, with redaction on every handler."""
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
        )
        root.addHandler(handler)
    root.setLevel(level)
    for handler in root.handlers:
        if not any(isinstance(f, RedactingFilter) for f in handler.filters):
            handler.addFilter(RedactingFilter())
