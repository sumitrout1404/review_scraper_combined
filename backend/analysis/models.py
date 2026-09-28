"""Plain data types shared by the rules classifier, the LLM classifier and the repository."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Sentiment = Literal["positive", "neutral", "negative"]
Polarity = Literal["positive", "negative"]

EVIDENCE_MAX_CHARS = 160
RULES_METHOD = "rules"


@dataclass(frozen=True)
class ReviewInput:
    """The review fields the classifiers look at (one row of ``reviews``)."""

    id: str
    score: float
    content_hash: str
    title: str | None = None
    positive_text: str | None = None
    negative_text: str | None = None
    language: str | None = None


@dataclass(frozen=True)
class TopicMention:
    """One topic tag with polarity and a short supporting snippet from the review."""

    topic: str
    polarity: Polarity
    evidence: str | None = None


@dataclass
class AnalysisResult:
    """Everything written to ``review_analysis`` + ``review_topics`` for one review."""

    review_id: str
    content_hash: str
    sentiment: Sentiment
    sentiment_score: float
    method: str
    summary: str | None = None
    topics: list[TopicMention] = field(default_factory=list)

    def dedupe_topics(self) -> None:
        """Keep the first mention per (topic, polarity) — the table's primary key."""
        seen: set[tuple[str, str]] = set()
        unique: list[TopicMention] = []
        for mention in self.topics:
            key = (mention.topic, mention.polarity)
            if key not in seen:
                seen.add(key)
                unique.append(mention)
        self.topics = unique
