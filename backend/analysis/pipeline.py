"""Orchestrates one analysis run: pick pending reviews, classify (rules / LLM), persist."""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from analysis import repository as repo
from analysis.lexicon import Lexicon
from analysis.llm_classifier import LLMClassifier, has_text
from analysis.llm_client import ChatClient, GroqClient, LLMUnavailableError
from analysis.models import AnalysisResult, ReviewInput
from analysis.rules import RulesClassifier
from analysis.settings import AnalysisSettings, load_settings
from core.circuit_breaker import CircuitOpenError
from db import ensure_indexes

logger = logging.getLogger(__name__)

Method = Literal["auto", "rules", "llm"]
METHODS: tuple[str, ...] = ("auto", "rules", "llm")
SYDNEY = ZoneInfo("Australia/Sydney")
RULES_CHUNK = 200                      # reviews per bulk_write for the (fast) rules path
DEFAULT_LLM_BATCH_ESTIMATE_S = 15.0    # assumed batch latency before the first one is measured


@dataclass
class RunStats:
    """Returned (as a dict) by ``run_analysis``."""

    method: str
    model: str | None = None
    analysed: int = 0
    skipped: int = 0
    pending: int = 0
    llm_count: int = 0
    rules_count: int = 0
    rules_fallback_count: int = 0
    upgraded: int = 0
    errors: int = 0
    topics_written: int = 0
    llm_requests: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    rejected_topics: int = 0
    stopped_early: bool = False
    llm_disabled_reason: str | None = None
    duration_s: float = 0.0
    error_messages: list[str] = field(default_factory=list)

    def error(self, message: str) -> None:
        self.errors += 1
        if len(self.error_messages) < 20:
            self.error_messages.append(message)


class _Deadline:
    def __init__(self, budget_s: float | None, clock: Callable[[], float]) -> None:
        self._clock = clock
        self.at = clock() + budget_s if budget_s is not None else None

    def remaining(self) -> float:
        return float("inf") if self.at is None else self.at - self._clock()


def sydney_today() -> date:
    return datetime.now(SYDNEY).date()


def resolve_method(method: str, settings: AnalysisSettings) -> bool:
    """True if the LLM should be used. Raises ValueError for unknown / impossible methods."""
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}; expected one of {METHODS}")
    if method == "llm" and not settings.llm_available:
        raise ValueError("method 'llm' requires GROQ_API_KEY")
    return method == "llm" or (method == "auto" and settings.llm_available)


def _method_allows_llm(method: str) -> bool:
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}; expected one of {METHODS}")
    return method != "rules"


def run_analysis(
    *,
    method: Method = "auto",
    reanalyse: bool = False,
    limit: int | None = None,
    time_budget_s: float | None = None,
    upgrade_rules: bool | None = None,
    settings: AnalysisSettings | None = None,
    chat_client: ChatClient | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Classify new/changed reviews and persist ``review_analysis`` + ``review_topics``.

    Idempotent on (review_id, content_hash): already analysed reviews are skipped unless
    ``reanalyse``. The LLM is used for reviews inside ``ANALYSIS_LLM_WINDOW_DAYS`` (newest
    first, capped per run); everything else — and any LLM failure — uses the rules method.
    ``upgrade_rules`` re-runs the LLM on in-window reviews previously analysed by rules.
    Stops cleanly when ``time_budget_s`` runs out; leftovers are counted in ``pending``.
    """
    clock = time.monotonic
    started = clock()
    deadline = _Deadline(time_budget_s, clock)
    settings = settings or load_settings()
    ensure_indexes()
    use_llm = resolve_method(method, settings) if chat_client is None else _method_allows_llm(method)
    lexicon = Lexicon.load()
    rules = RulesClassifier(lexicon)
    stats = RunStats(method="llm" if use_llm else "rules", model=settings.groq_model if use_llm else None)

    repo.upsert_topics(lexicon.topics)
    pending = repo.pending_reviews(reanalyse)
    stats.skipped = repo.count_reviews() - len(pending)
    if limit is not None:
        pending = pending[:max(0, limit)]
    window_start = ((today or sydney_today()) - timedelta(days=settings.llm_window_days)).isoformat()
    plan = _plan(pending, use_llm, window_start, settings)
    if use_llm and (settings.upgrade_rules if upgrade_rules is None else upgrade_rules):
        room = settings.llm_max_reviews_per_run - len(plan.llm)
        if limit is not None:
            room = min(room, limit - len(pending))
        candidates = [p.review for p in repo.upgradable_reviews(window_start) if has_text(p.review)]
        plan.upgrades = candidates[:max(0, room)]

    unprocessed = len(pending) - _run_rules(rules, plan.rules, lexicon, stats, deadline)
    if plan.llm or plan.upgrades:
        client = chat_client or GroqClient(settings)
        try:
            unprocessed -= _run_llm(rules, LLMClassifier(client, lexicon, settings.max_output_tokens_per_review), plan, lexicon, settings,
                                    stats, deadline, client)
        finally:
            if chat_client is None and isinstance(client, GroqClient):
                client.close()

    stats.pending = max(0, unprocessed)
    stats.duration_s = round(clock() - started, 2)
    logger.info("analysis done: %s", {k: v for k, v in asdict(stats).items() if k != "error_messages"})
    return asdict(stats)


@dataclass
class _Plan:
    rules: list[ReviewInput]            # oldest first
    llm: list[ReviewInput]              # newest first, capped
    upgrades: list[ReviewInput] = field(default_factory=list)


def _plan(pending: list[repo.PendingReview], use_llm: bool, window_start: str,
          settings: AnalysisSettings) -> _Plan:
    """LLM for recent reviews with text (newest first, capped per run); rules for the rest."""
    llm: list[ReviewInput] = []
    rules: list[ReviewInput] = []
    for item in pending:
        in_window = item.review_date >= window_start and has_text(item.review)
        (llm if use_llm and in_window else rules).append(item.review)
    llm.reverse()
    cap = settings.llm_max_reviews_per_run
    return _Plan(rules=rules + llm[cap:], llm=llm[:cap])


def _save(results: list[AnalysisResult], lexicon: Lexicon, stats: RunStats) -> bool:
    """Persist; on failure the reviews simply stay pending for the next run."""
    try:
        saved, topic_rows = repo.save_results(results, lexicon.topic_keys)
    except Exception as exc:
        logger.exception("failed to save %d analyses", len(results))
        stats.error(f"db: {type(exc).__name__}")
        return False
    if saved < len(results):
        logger.info("%d reviews changed while being analysed; left pending", len(results) - saved)
    stats.analysed += saved
    stats.topics_written += topic_rows
    return True


def _run_rules(rules: RulesClassifier, reviews: list[ReviewInput], lexicon: Lexicon,
               stats: RunStats, deadline: _Deadline, *, fallback: bool = False) -> int:
    """Rules path in chunks of RULES_CHUNK. Returns number of reviews persisted."""
    done = 0
    for start in range(0, len(reviews), RULES_CHUNK):
        if deadline.remaining() <= 0:
            stats.stopped_early = True
            break
        chunk = reviews[start:start + RULES_CHUNK]
        results = []
        for review in chunk:
            try:
                results.append(rules.classify(review))
            except Exception as exc:
                logger.exception("rules classifier failed for review %s", review.id)
                stats.error(f"rules: {type(exc).__name__}")
        if _save(results, lexicon, stats):
            done += len(results)
            if fallback:
                stats.rules_fallback_count += len(results)
            else:
                stats.rules_count += len(results)
    return done


def _run_llm(rules: RulesClassifier, llm: LLMClassifier, plan: _Plan, lexicon: Lexicon,
             settings: AnalysisSettings, stats: RunStats, deadline: _Deadline, client: ChatClient) -> int:
    """LLM path in batches; new reviews the LLM could not handle fall back to rules.

    Upgrade candidates that fail simply keep their existing rules analysis.
    Returns the number of *new/changed* reviews persisted.
    """
    upgrade_ids = {r.id for r in plan.upgrades}
    queue = plan.llm + plan.upgrades
    done_new = 0
    batch_estimate = DEFAULT_LLM_BATCH_ESTIMATE_S
    for start in range(0, len(queue), settings.batch_size):
        batch = queue[start:start + settings.batch_size]
        new_in_batch = [r for r in batch if r.id not in upgrade_ids]
        reason = _llm_stop_reason(stats, settings, deadline, batch_estimate)
        if reason is None:
            if isinstance(client, GroqClient):
                client.deadline = deadline.at
            t0 = time.monotonic()
            try:
                outcome = llm.classify_batch(batch)
            except (CircuitOpenError, LLMUnavailableError) as exc:
                logger.warning("LLM disabled for the rest of this run: %s", exc)
                stats.error(f"llm: {exc}")
                reason = str(exc)
            except Exception as exc:   # LLMError or anything unexpected -> rules for this batch only
                logger.warning("LLM batch failed (%s); using rules for %d reviews", exc, len(new_in_batch))
                stats.error(f"llm: {type(exc).__name__}: {exc}")
                stats.llm_requests += 1
                done_new += _run_rules(rules, new_in_batch, lexicon, stats, deadline, fallback=True)
                continue
        if reason is not None:
            stats.llm_disabled_reason = stats.llm_disabled_reason or reason
            leftovers = [r for r in queue[start:] if r.id not in upgrade_ids]
            return done_new + _run_rules(rules, leftovers, lexicon, stats, deadline, fallback=True)

        batch_estimate = max(1.0, time.monotonic() - t0)
        stats.llm_requests += 1
        stats.prompt_tokens += outcome.prompt_tokens
        stats.completion_tokens += outcome.completion_tokens
        stats.rejected_topics += outcome.rejected_topics
        results = list(outcome.results.values())
        if _save(results, lexicon, stats):
            stats.llm_count += len(results)
            stats.upgraded += sum(1 for r in results if r.review_id in upgrade_ids)
            done_new += sum(1 for r in results if r.review_id not in upgrade_ids)
        missing = [r for r in new_in_batch if r.id not in outcome.results]
        done_new += _run_rules(rules, missing, lexicon, stats, deadline, fallback=True)
    return done_new


def _llm_stop_reason(stats: RunStats, settings: AnalysisSettings, deadline: _Deadline,
                     batch_estimate: float) -> str | None:
    if stats.llm_disabled_reason:
        return stats.llm_disabled_reason
    if deadline.remaining() < batch_estimate:
        stats.stopped_early = True
        return "time budget exhausted"
    budget = settings.llm_max_tokens_per_run
    if budget and stats.prompt_tokens + stats.completion_tokens >= budget:
        return f"token budget of {budget} reached"
    return None
