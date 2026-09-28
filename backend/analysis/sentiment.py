"""Review-level sentiment for the rules method.

Base label from Booking's score (contract: >= 8 positive, >= 6 neutral, < 6 negative),
then adjusted by a text signal so e.g. a 7.0 with a long, strongly negative "disliked"
box becomes negative. ``sentiment_score`` blends score (70 %) and text (30 %) into
-1..1 and is clamped into a band consistent with the label.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from analysis import text as tx
from analysis.lexicon import Lexicon
from analysis.models import Sentiment

POSITIVE_MIN_SCORE = 8.0
NEUTRAL_MIN_SCORE = 6.0
SCORE_WEIGHT = 0.7
TEXT_WEIGHT = 0.3
_BANDS: dict[str, tuple[float, float]] = {
    "positive": (0.1, 1.0),
    "neutral": (-0.4, 0.4),
    "negative": (-1.0, -0.1),
}


@dataclass(frozen=True)
class SentimentInputs:
    score: float
    title: str | None
    positive_text: str          # placeholders already removed
    negative_text: str
    praise_count: int           # distinct topics praised
    complaint_count: int        # distinct topics complained about


def score_bucket(score: float) -> Sentiment:
    if score >= POSITIVE_MIN_SCORE:
        return "positive"
    if score >= NEUTRAL_MIN_SCORE:
        return "neutral"
    return "negative"


def text_signal(inputs: SentimentInputs, lexicon: Lexicon) -> float:
    """-1..1: how much more the guest wrote/complained than praised, plus strong phrases."""
    pos_words = tx.word_count(inputs.positive_text)
    neg_words = tx.word_count(inputs.negative_text)
    combined = tx.lower_same_length(" . ".join(filter(None, [inputs.title, inputs.positive_text, inputs.negative_text])))
    strong_pos, strong_neg = lexicon.strong_counts(combined)
    length_term = math.tanh((pos_words - neg_words) / 30)
    topic_term = math.tanh((inputs.praise_count - inputs.complaint_count) / 3)
    strong_term = math.tanh((strong_pos - 1.5 * strong_neg) / 2)
    return 0.4 * length_term + 0.35 * topic_term + 0.25 * strong_term


def rules_sentiment(inputs: SentimentInputs, lexicon: Lexicon) -> tuple[Sentiment, float]:
    """(label, score in -1..1)."""
    signal = text_signal(inputs, lexicon)
    neg_words = tx.word_count(inputs.negative_text)
    label = score_bucket(inputs.score)
    if label == "neutral":
        if signal <= -0.35 and neg_words >= 20:
            label = "negative"
        elif signal >= 0.45 and neg_words == 0 and inputs.score >= 7:
            label = "positive"
    elif label == "positive":
        if inputs.score < 9 and signal <= -0.45 and neg_words >= 30:
            label = "neutral"
    elif inputs.score >= 5 and signal >= 0.5 and neg_words == 0:
        label = "neutral"

    rating = max(-1.0, min(1.0, (inputs.score - 5.5) / 4.5))
    raw = SCORE_WEIGHT * rating + TEXT_WEIGHT * signal
    low, high = _BANDS[label]
    return label, round(max(low, min(high, raw)), 3)
