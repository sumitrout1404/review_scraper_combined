"""run_analysis end-to-end on mongomock: idempotency, fallbacks, LLM window, budgets."""
from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from analysis import repository as repo
from analysis import run_analysis
from analysis.llm_client import LLMError, LLMUnavailableError
from analysis.models import AnalysisResult
from db import REVIEWS, TOPICS, collection
from tests.analysis.conftest import NO_KEY, WITH_KEY, FakeChat, add_review, echo_topics, review, topic_pairs

TODAY = date(2026, 9, 28)


def _seed() -> None:
    add_review("a", score=9.0, positive="Very clean and friendly staff", negative="Nothing")
    add_review("b", score=5.0, positive="Location", negative="Really noisy, thin walls. Dirty bathroom.")
    add_review("c", score=7.0, positive=None, negative="N/A")


def _rules(**kwargs) -> dict:
    return run_analysis(method="rules", settings=NO_KEY, today=TODAY, **kwargs)


def _llm(chat: FakeChat, settings=WITH_KEY, **kwargs) -> dict:
    return run_analysis(method="llm", settings=settings, chat_client=chat, today=TODAY, **kwargs)


def test_rules_run_embeds_analysis_and_topics() -> None:
    _seed()
    stats = _rules()
    assert (stats["analysed"], stats["skipped"], stats["pending"], stats["errors"]) == (3, 0, 0, 0)
    assert collection(TOPICS).count_documents({}) == 12
    assert collection(TOPICS).find_one({"_id": "cleanliness"})["label"] == "Cleanliness"
    assert {r["_id"]: (r["analysis"]["sentiment"], r["analysis"]["method"]) for r in collection(REVIEWS).find()} == {
        "a": ("positive", "rules"), "b": ("negative", "rules"), "c": ("neutral", "rules")}
    assert topic_pairs("b") == {("location", "positive"), ("noise", "negative"), ("cleanliness", "negative"),
                                ("bathroom", "negative")}
    assert review("c")["topics"] == []
    assert review("b")["analysis"]["content_hash"] == "h-b"


def test_rerun_is_a_no_op_and_changed_hash_is_reanalysed() -> None:
    _seed()
    _rules()
    before = list(collection(REVIEWS).find().sort("_id"))
    again = _rules()
    assert (again["analysed"], again["skipped"]) == (0, 3)
    assert list(collection(REVIEWS).find().sort("_id")) == before

    add_review("b", score=5.0, positive="Location", negative="The wifi was slow", content_hash="h-b-v2")
    changed = _rules()
    assert (changed["analysed"], changed["skipped"]) == (1, 2)
    assert topic_pairs("b") == {("location", "positive"), ("wifi", "negative")}     # topics replaced
    assert review("b")["analysis"]["content_hash"] == "h-b-v2"


def test_stale_write_is_not_applied() -> None:
    """If the collector changes a review mid-run, the old classification must not land on it."""
    add_review("x", negative="noisy")
    stale = AnalysisResult("x", "old-hash", "negative", -0.5, "rules")
    saved, _ = repo.save_results([stale], frozenset({"noise"}))
    assert saved == 0
    assert "analysis" not in review("x")


def test_reanalyse_and_limit() -> None:
    _seed()
    first = _rules(limit=2)
    assert (first["analysed"], first["pending"]) == (2, 0)
    assert _rules()["analysed"] == 1
    assert _rules(reanalyse=True)["analysed"] == 3


def test_auto_without_key_uses_rules_and_llm_without_key_is_an_error() -> None:
    _seed()
    assert run_analysis(method="auto", settings=NO_KEY, today=TODAY)["method"] == "rules"
    with pytest.raises(ValueError):
        run_analysis(method="llm", settings=NO_KEY)
    with pytest.raises(ValueError):
        run_analysis(method="magic", settings=NO_KEY)  # type: ignore[arg-type]


def test_llm_results_are_stored_with_model_method() -> None:
    _seed()
    chat = FakeChat(echo_topics)
    stats = _llm(chat)
    assert stats["llm_count"] == 2 and stats["rules_count"] == 1     # 'c' has no text => rules
    assert len(chat.calls) == 1 and len(chat.calls[0]) == 2          # one batched request
    assert (review("b")["analysis"]["method"], review("b")["analysis"]["summary"]) == ("llm:fake-model", "s")
    assert review("b")["topics"] == [
        {"topic": "noise", "polarity": "negative", "evidence": "Really noisy, thin walls"}]


def test_failed_batch_falls_back_to_rules() -> None:
    _seed()

    def boom(_reviews: list[dict]) -> dict:
        raise LLMError("bad output")

    stats = _llm(FakeChat(boom))
    assert (stats["analysed"], stats["llm_count"], stats["rules_fallback_count"], stats["errors"]) == (3, 0, 2, 1)
    assert {r["analysis"]["method"] for r in collection(REVIEWS).find()} == {"rules"}


def test_missing_reviews_in_response_fall_back_individually() -> None:
    _seed()
    stats = _llm(FakeChat(lambda reviews: echo_topics(reviews[:1])))
    assert (stats["llm_count"], stats["rules_fallback_count"], stats["pending"]) == (1, 1, 0)


def test_unavailable_llm_stops_calling_and_uses_rules() -> None:
    for i in range(25):
        add_review(f"r{i:02d}", score=6.0, positive="ok", negative="noisy room")

    def limited(_reviews: list[dict]) -> dict:
        raise LLMUnavailableError("rate limited for 3600s")

    chat = FakeChat(limited)
    stats = _llm(chat)
    assert len(chat.calls) == 1                                       # no hammering after the first failure
    assert (stats["analysed"], stats["rules_fallback_count"]) == (25, 25)
    assert "3600" in stats["llm_disabled_reason"]


def test_llm_window_per_run_cap_and_upgrade() -> None:
    add_review("old", positive="nice", negative="noisy", review_date="2025-01-01")
    for i in range(5):
        add_review(f"new{i}", positive="nice", negative="noisy", review_date=f"2026-09-2{i}")
    settings = replace(WITH_KEY, llm_window_days=180, llm_max_reviews_per_run=3, batch_size=10)
    chat = FakeChat(echo_topics)
    stats = _llm(chat, settings)
    assert (stats["llm_count"], stats["rules_count"]) == (3, 3)
    llm_ids = {r["_id"] for r in collection(REVIEWS).find({"analysis.method": "llm:fake-model"})}
    assert llm_ids == {"new4", "new3", "new2"}                        # newest first

    upgrade = _llm(chat, settings, upgrade_rules=True)
    assert (upgrade["analysed"], upgrade["upgraded"]) == (2, 2)       # new1, new0; 'old' is outside the window
    assert review("old")["analysis"]["method"] == "rules"
    assert _llm(chat, settings, upgrade_rules=True)["analysed"] == 0  # idempotent


def test_exhausted_time_budget_leaves_reviews_pending() -> None:
    _seed()
    stats = _rules(time_budget_s=0)
    assert (stats["analysed"], stats["pending"], stats["stopped_early"]) == (0, 3, True)
    assert _rules()["analysed"] == 3
