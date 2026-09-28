"""Typed configuration for the analysis package, read once from the environment.

``backend/.env`` is loaded when python-dotenv is installed (local runs); on Vercel the
variables come from the platform and python-dotenv is not required.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_DIR / ".env"
DEFAULT_MODEL = "openai/gpt-oss-120b"
DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:          # optional dependency (not installed on Vercel)
        return
    if ENV_FILE.is_file():
        load_dotenv(ENV_FILE, override=False)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw not in (None, "") else default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw in (None, "") else raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AnalysisSettings:
    """All tunables. ``groq_api_key`` is excluded from repr so it can never be logged by accident."""

    groq_api_key: str | None = field(default=None, repr=False)
    groq_model: str = DEFAULT_MODEL
    groq_base_url: str = DEFAULT_BASE_URL
    batch_size: int = 10                    # reviews per LLM request
    request_timeout_s: float = 60.0
    max_output_tokens_per_review: int = 450
    reasoning_effort: str | None = None     # gpt-oss / qwen "reasoning_effort"; None = model default
    retry_attempts: int = 4
    retry_base_delay_s: float = 2.0
    retry_max_delay_s: float = 60.0         # longer Retry-After => give up on the LLM for this run
    min_request_interval_s: float = 1.0     # gentle pacing for free-tier RPM limits
    breaker_failure_threshold: int = 3
    breaker_recovery_s: float = 120.0
    upgrade_rules: bool = False             # re-run the LLM on in-window reviews analysed by rules earlier
    llm_window_days: int = 180              # only reviews this recent go to the LLM (older -> rules)
    llm_max_reviews_per_run: int = 400      # cap LLM work per run (free-tier daily token limits)
    llm_max_tokens_per_run: int = 0         # 0 = no token cap (prompt + completion)

    @property
    def llm_available(self) -> bool:
        return bool(self.groq_api_key)

    @property
    def llm_method(self) -> str:
        return f"llm:{self.groq_model}"


def load_settings() -> AnalysisSettings:
    """Read settings from the environment (after loading ``backend/.env`` if possible)."""
    _load_dotenv()
    model = os.getenv("GROQ_MODEL") or DEFAULT_MODEL
    return AnalysisSettings(
        groq_api_key=os.getenv("GROQ_API_KEY") or None,
        groq_model=model,
        groq_base_url=(os.getenv("GROQ_BASE_URL") or DEFAULT_BASE_URL).rstrip("/"),
        batch_size=max(1, _env_int("ANALYSIS_BATCH_SIZE", 10)),
        request_timeout_s=_env_float("ANALYSIS_REQUEST_TIMEOUT_S", 60.0),
        reasoning_effort=os.getenv("GROQ_REASONING_EFFORT") or _default_reasoning_effort(model),
        retry_attempts=max(1, _env_int("ANALYSIS_RETRY_ATTEMPTS", 4)),
        retry_max_delay_s=_env_float("ANALYSIS_RETRY_MAX_DELAY_S", 60.0),
        min_request_interval_s=_env_float("ANALYSIS_MIN_REQUEST_INTERVAL_S", 1.0),
        upgrade_rules=_env_bool("ANALYSIS_UPGRADE_RULES", False),
        llm_window_days=max(0, _env_int("ANALYSIS_LLM_WINDOW_DAYS", 180)),
        llm_max_reviews_per_run=max(0, _env_int("ANALYSIS_LLM_MAX_REVIEWS_PER_RUN", 400)),
        llm_max_tokens_per_run=max(0, _env_int("ANALYSIS_LLM_MAX_TOKENS_PER_RUN", 0)),
    )


def _default_reasoning_effort(model: str) -> str | None:
    """Reasoning models spend output tokens on thinking; keep it minimal for classification."""
    if model.startswith("openai/gpt-oss"):
        return "low"
    if model.startswith("qwen/"):
        return "none"
    return None
