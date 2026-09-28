"""LLM output validation and the Groq client (mocked HTTP; no network, no real key)."""
from __future__ import annotations

import json
import logging
from dataclasses import replace

import httpx
import pytest

from analysis.lexicon import Lexicon
from analysis.llm_classifier import LLMClassifier
from analysis.llm_client import GroqClient, LLMError, LLMUnavailableError
from analysis.llm_schema import ground_evidence, parse_batch
from analysis.models import ReviewInput
from core.circuit_breaker import CircuitBreaker, CircuitOpenError
from tests.analysis.conftest import WITH_KEY, FakeChat

REVIEW = ReviewInput("rev-1", 4.0, "h", title="Disappointing",
                     positive_text="Great location near the station.",
                     negative_text="The bathroom was filthy and the guy in the next pod snored all night.")


def _classify(response: dict) -> dict:
    llm = LLMClassifier(FakeChat(lambda _: response), Lexicon.load())
    return llm.classify_batch([REVIEW]).results


def test_valid_output_is_mapped_back_to_review_ids() -> None:
    results = _classify({"reviews": [{
        "id": "r1", "sentiment": "Negative", "sentiment_score": -3, "summary": "Dirty bathroom, snoring.",
        "topics": [
            {"topic": "cleanliness", "polarity": "negative", "evidence": "bathroom was filthy"},
            {"topic": "Noise", "polarity": "complaint", "evidence": "snored all night"},
            {"topic": "location", "polarity": "praise", "evidence": "Great location"},
        ]}]})
    result = results["rev-1"]
    assert result.sentiment == "negative"
    assert result.sentiment_score == -1.0                    # clamped
    assert result.method == "llm:fake-model"
    assert {(m.topic, m.polarity) for m in result.topics} == {
        ("cleanliness", "negative"), ("noise", "negative"), ("location", "positive")}
    assert all(m.evidence and len(m.evidence) <= 160 for m in result.topics)


def test_unknown_topics_and_hallucinated_evidence_are_dropped() -> None:
    results = _classify({"reviews": [{
        "id": "r1", "sentiment": "negative", "sentiment_score": -0.8, "topics": [
            {"topic": "parking", "polarity": "negative", "evidence": "bathroom was filthy"},
            {"topic": "staff", "polarity": "negative", "evidence": "the receptionist was rude to us"},
            {"topic": "wifi", "polarity": "sideways", "evidence": "Great location"},
            {"topic": "bathroom", "polarity": "negative", "evidence": "The bathroom was filthy"},
        ]}]})
    assert [(m.topic, m.polarity) for m in results["rev-1"].topics] == [("bathroom", "negative")]


def test_unknown_ids_and_invalid_reviews_are_skipped() -> None:
    results = _classify({"reviews": [{"id": "r99", "sentiment": "positive"},
                                     {"id": "r1", "sentiment": "ecstatic"}]})
    assert results == {}


def test_invalid_json_raises_llm_error() -> None:
    llm = LLMClassifier(FakeChat(lambda _: "not json {"), Lexicon.load())
    with pytest.raises(LLMError):
        llm.classify_batch([REVIEW])


def test_prompt_sends_placeholder_free_truncated_text() -> None:
    chat = FakeChat(lambda reviews: {"reviews": []})
    long_review = ReviewInput("x", 7.0, "h", positive_text="word " * 400, negative_text="Nothing")
    LLMClassifier(chat, Lexicon.load()).classify_batch([long_review])
    sent = chat.calls[0][0]
    assert sent["disliked"] == ""
    assert len(sent["liked"]) <= 710


def test_ground_evidence_accepts_near_matches_only() -> None:
    source = "Staff were lovely.\nThe shower drain was blocked every morning."
    assert ground_evidence("shower drain was blocked", source) == "The shower drain was blocked every morning"
    assert ground_evidence("The shower drain were blocked every morning", source) is not None   # small typo
    assert ground_evidence("breakfast was cold", source) is None


def test_parse_batch_tolerates_extra_fields() -> None:
    parsed = parse_batch(json.dumps({"reviews": [{"id": "r1", "sentiment": "neutral", "extra": 1}], "note": "x"}))
    assert parsed[0].id == "r1" and parsed[0].topics == []


# -- GroqClient -------------------------------------------------------------------------------

def _client(handler, *, breaker: CircuitBreaker | None = None, sleeps: list[float] | None = None) -> GroqClient:
    settings = replace(WITH_KEY, retry_attempts=3, retry_max_delay_s=30)
    return GroqClient(settings, http_client=httpx.Client(transport=httpx.MockTransport(handler)),
                      breaker=breaker, sleep=(sleeps.append if sleeps is not None else lambda _s: None))


def _ok(content: str = '{"reviews": []}') -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}],
                                     "usage": {"prompt_tokens": 11, "completion_tokens": 7}})


def test_client_retries_429_honouring_retry_after() -> None:
    responses = iter([httpx.Response(429, headers={"retry-after": "7"}), httpx.Response(503), _ok()])
    sleeps: list[float] = []
    result = _client(lambda request: next(responses), sleeps=sleeps).complete_json("s", "u", 100)
    assert result.prompt_tokens == 11
    assert sleeps[0] == 7.0


def test_client_sends_json_mode_and_auth_header() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return _ok()

    _client(handler).complete_json("sys", "user", 123)
    assert seen["auth"] == "Bearer test-key-not-real"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["body"]["temperature"] == 0 and seen["body"]["max_tokens"] == 123


def test_long_retry_after_disables_llm_instead_of_waiting() -> None:
    with pytest.raises(LLMUnavailableError):
        _client(lambda r: httpx.Response(429, headers={"retry-after": "3600"})).complete_json("s", "u", 1)


@pytest.mark.parametrize("status", [401, 404])
def test_auth_and_missing_model_disable_llm(status: int) -> None:
    with pytest.raises(LLMUnavailableError):
        _client(lambda r: httpx.Response(status, json={"error": {"code": "x"}})).complete_json("s", "u", 1)


def test_other_4xx_is_not_retried() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, json={"error": {"code": "invalid_request"}})

    with pytest.raises(LLMError):
        _client(handler).complete_json("s", "u", 1)
    assert len(calls) == 1


def test_breaker_opens_after_repeated_failures() -> None:
    breaker = CircuitBreaker("groq-test", failure_threshold=2, recovery_timeout=60)
    client = _client(lambda r: httpx.Response(500), breaker=breaker)
    for _ in range(2):
        with pytest.raises(Exception):  # noqa: B017 - retries exhausted
            client.complete_json("s", "u", 1)
    with pytest.raises(CircuitOpenError):
        client.complete_json("s", "u", 1)


def test_api_key_never_appears_in_logs(caplog: pytest.LogCaptureFixture) -> None:
    responses = iter([httpx.Response(429, headers={"retry-after": "1"}), _ok()])
    with caplog.at_level(logging.DEBUG):
        _client(lambda r: next(responses)).complete_json("s", "u", 1)
    assert "test-key-not-real" not in caplog.text
    assert "test-key-not-real" not in repr(WITH_KEY)


def test_client_waits_for_token_window_instead_of_hitting_429() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        response = _ok()
        response.headers["x-ratelimit-remaining-tokens"] = "50"
        response.headers["x-ratelimit-reset-tokens"] = "12.5s"
        return response

    sleeps: list[float] = []
    client = _client(handler, sleeps=sleeps)
    client.complete_json("s", "u", 1000)
    client.complete_json("s", "u", 1000)          # needs ~500 tokens > 50 remaining
    assert sleeps and 11 < sleeps[-1] <= 12.5


def test_invalid_json_batch_is_retried_as_two_halves() -> None:
    replies = iter(['{"reviews": [truncated', {"reviews": [{"id": "r1", "sentiment": "neutral"}]},
                    {"reviews": [{"id": "r1", "sentiment": "negative"}]}])
    chat = FakeChat(lambda _reviews: next(replies))
    other = ReviewInput("rev-2", 6.0, "h", negative_text="Noisy")
    results = LLMClassifier(chat, Lexicon.load()).classify_batch([REVIEW, other]).results
    assert [len(call) for call in chat.calls] == [2, 1, 1]
    assert (results["rev-1"].sentiment, results["rev-2"].sentiment) == ("neutral", "negative")
