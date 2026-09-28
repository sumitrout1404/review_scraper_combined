"""Pydantic validation of LLM output + evidence grounding.

The model's JSON is untrusted: unknown topics are dropped, scores clamped, polarity
synonyms normalised, and every topic must quote evidence that actually occurs in the
review (exact modulo case/punctuation, or a close fuzzy match to one clause). Evidence
that cannot be grounded drops the topic — no hallucinated tags reach the dashboard.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from analysis import text as tx
from analysis.models import EVIDENCE_MAX_CHARS, Polarity, Sentiment, TopicMention

FUZZY_MIN_RATIO = 0.75
SUMMARY_MAX_CHARS = 200
_POLARITY_SYNONYMS = {"praise": "positive", "complaint": "negative", "pos": "positive", "neg": "negative"}
_WORD_RE = re.compile(r"\w+", re.UNICODE)


class LLMTopic(BaseModel):
    model_config = ConfigDict(extra="ignore")

    topic: str
    polarity: Polarity
    evidence: str = ""

    @field_validator("topic", mode="before")
    @classmethod
    def _norm_topic(cls, value: Any) -> str:
        return str(value).strip().lower().replace("-", "_").replace(" ", "_")

    @field_validator("polarity", mode="before")
    @classmethod
    def _norm_polarity(cls, value: Any) -> str:
        key = str(value).strip().lower()
        return _POLARITY_SYNONYMS.get(key, key)


class LLMReview(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    sentiment: Sentiment
    sentiment_score: float = 0.0
    summary: str | None = None
    topics: list[dict[str, Any]] = Field(default_factory=list)   # validated one by one

    @field_validator("id", mode="before")
    @classmethod
    def _norm_id(cls, value: Any) -> str:
        return str(value).strip()

    @field_validator("sentiment", mode="before")
    @classmethod
    def _norm_sentiment(cls, value: Any) -> str:
        return str(value).strip().lower()

    @field_validator("sentiment_score", mode="before")
    @classmethod
    def _clamp_score(cls, value: Any) -> float:
        try:
            return max(-1.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0

    @field_validator("summary", mode="before")
    @classmethod
    def _trim_summary(cls, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(tx.normalise(str(value)).split())
        return cleaned[:SUMMARY_MAX_CHARS] or None

    @field_validator("topics", mode="before")
    @classmethod
    def _topics_list(cls, value: Any) -> list[Any]:
        return [t for t in value if isinstance(t, dict)] if isinstance(value, list) else []


class LLMBatch(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reviews: list[dict[str, Any]] = Field(default_factory=list)   # validated one by one


def parse_batch(content: str) -> list[LLMReview]:
    """Parse the model's JSON; invalid individual reviews are skipped (they fall back to rules)."""
    batch = LLMBatch.model_validate_json(content)
    parsed: list[LLMReview] = []
    for raw in batch.reviews:
        try:
            parsed.append(LLMReview.model_validate(raw))
        except ValidationError:
            continue
    return parsed


def ground_evidence(evidence: str, source: str) -> str | None:
    """Return a real substring of ``source`` supporting ``evidence``, or None if not grounded."""
    words = _WORD_RE.findall(evidence.lower())
    if not words or not source:
        return None
    pattern = r"\W+".join(re.escape(w) for w in words)
    match = re.search(pattern, source, flags=re.IGNORECASE)
    if match:
        return _sentence_around(source, match.start(), match.end())
    target = " ".join(words)
    best, best_ratio = None, 0.0
    for clause in tx.split_clauses(source):
        candidate = " ".join(_WORD_RE.findall(clause.lower))
        ratio = SequenceMatcher(None, target, candidate, autojunk=False).ratio()
        if ratio > best_ratio:
            best, best_ratio = clause.text, ratio
    if best is not None and best_ratio >= FUZZY_MIN_RATIO:
        return best[:EVIDENCE_MAX_CHARS]
    return None


def _sentence_around(source: str, start: int, end: int) -> str:
    """The sentence(s) containing [start, end), capped at EVIDENCE_MAX_CHARS (context for short quotes)."""
    left = max(source.rfind(ch, 0, start) for ch in ".!?\n") + 1
    rights = [i for i in (source.find(ch, end) for ch in ".!?\n") if i != -1]
    right = min(rights) if rights else len(source)
    return tx.snippet(source[left:right], start - left, end - left, EVIDENCE_MAX_CHARS)


def validated_mentions(review: LLMReview, allowed_topics: frozenset[str], source: str) -> tuple[
        list[TopicMention], int]:
    """(grounded topic mentions, number of topics rejected)."""
    mentions: list[TopicMention] = []
    rejected = 0
    for raw in review.topics:
        try:
            topic = LLMTopic.model_validate(raw)
        except ValidationError:
            rejected += 1
            continue
        evidence = ground_evidence(topic.evidence, source) if topic.topic in allowed_topics else None
        if evidence is None:
            rejected += 1
            continue
        mentions.append(TopicMention(topic.topic, topic.polarity, evidence))
    return mentions, rejected
