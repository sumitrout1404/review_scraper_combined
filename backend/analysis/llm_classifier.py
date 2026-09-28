"""Batch LLM classification via any ``ChatClient`` (Groq in production, a fake in tests)."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from pydantic import ValidationError

from analysis import text as tx
from analysis.lexicon import Lexicon
from analysis.llm_client import ChatClient, LLMError, LLMUnavailableError
from analysis.llm_schema import parse_batch, validated_mentions
from analysis.models import AnalysisResult, ReviewInput

logger = logging.getLogger(__name__)

MAX_CHARS_PER_FIELD = 700          # long reviews are truncated in the prompt (evidence still checked on full text)
REASONING_TOKEN_ALLOWANCE = 800    # reasoning models think before answering

_RULES = """Rules:
1. Tag a topic only when the text explicitly discusses it. Never infer topics from the score.
2. polarity "negative" = complaint, "positive" = praise. "disliked" text is usually a complaint and "liked" \
text usually praise, but follow the meaning: disliked "nothing, staff were great" = staff positive; \
liked "good but noisy" = noise negative. One topic may have both polarities.
3. evidence = exact quote (max 15 words) copied verbatim from the review, in its original language.
4. sentiment = overall guest experience: usually score >= 8 positive, 6-7.9 neutral, < 6 negative, \
but clearly negative or positive text overrides the score.
5. summary = one neutral English sentence, max 20 words.
6. bed_comfort = beds/pillows/bunks/sleep comfort; room_condition = room/pod size, state, privacy, A/C, \
outlets; bathroom = showers/toilets incl. shared; cleanliness = dirt/smells/pests anywhere; staff = how people \
behaved; check_in = the process, keys, codes, timing; noise includes snoring and other guests; facilities = \
shared amenities (kitchen, lockers, lounge, lift, laundry, luggage storage).
7. Ignore placeholder answers such as "Nothing" or "N/A"."""


def build_system_prompt(lexicon: Lexicon) -> str:
    """Tight instructions listing the only allowed topic keys."""
    topic_lines = "\n".join(f"- {t.key}: {t.description}" for t in lexicon.topics)
    return (
        "You label Booking.com guest reviews of budget pod/capsule hotels in Sydney for an operations dashboard.\n"
        "Input: JSON {\"reviews\":[{id, score (1-10), title, liked, disliked}]}. Text may be in any language.\n"
        "Output JSON only: {\"reviews\":[{\"id\":str,\"sentiment\":\"positive\"|\"neutral\"|\"negative\","
        "\"sentiment_score\":number -1..1,\"summary\":str,\"topics\":[{\"topic\":key,"
        "\"polarity\":\"positive\"|\"negative\",\"evidence\":str}]}]}, one entry per input review, same ids.\n"
        f"Allowed topic keys:\n{topic_lines}\n{_RULES}"
    )


def _truncate(text: str) -> str:
    return text if len(text) <= MAX_CHARS_PER_FIELD else text[:MAX_CHARS_PER_FIELD].rsplit(" ", 1)[0] + " ..."


def has_text(review: ReviewInput) -> bool:
    """False when both boxes are empty/placeholders (nothing for an LLM to add)."""
    return bool(tx.meaningful_text(review.positive_text) or tx.meaningful_text(review.negative_text))


@dataclass
class BatchOutcome:
    results: dict[str, AnalysisResult] = field(default_factory=dict)   # review id -> result
    prompt_tokens: int = 0
    completion_tokens: int = 0
    rejected_topics: int = 0


class LLMClassifier:
    """Classifies reviews in batches; reviews missing from a valid response are left to the caller."""

    def __init__(self, client: ChatClient, lexicon: Lexicon, max_output_tokens_per_review: int = 450) -> None:
        self._client = client
        self._allowed = lexicon.topic_keys
        self._system = build_system_prompt(lexicon)
        self._tokens_per_review = max_output_tokens_per_review

    @property
    def method(self) -> str:
        return f"llm:{self._client.model}"

    def classify_batch(self, reviews: list[ReviewInput]) -> BatchOutcome:
        """Classify a batch; if the reply is not valid JSON (usually truncated), retry once as two halves.

        Raises LLMError (or client errors) only if the batch could not be classified at all.
        """
        try:
            return self._classify_once(reviews)
        except LLMUnavailableError:
            raise
        except LLMError:
            if len(reviews) < 2:
                raise
            logger.warning("invalid LLM JSON for a batch of %d; retrying as two halves", len(reviews))
            middle = len(reviews) // 2
            first, second = self._classify_once(reviews[:middle]), self._classify_once(reviews[middle:])
            first.results.update(second.results)
            first.prompt_tokens += second.prompt_tokens
            first.completion_tokens += second.completion_tokens
            first.rejected_topics += second.rejected_topics
            return first

    def _classify_once(self, reviews: list[ReviewInput]) -> BatchOutcome:
        """One request for the batch."""
        local_ids = {f"r{i}": review for i, review in enumerate(reviews, start=1)}
        payload = {"reviews": [
            {
                "id": local_id,
                "score": review.score,
                "title": _truncate(tx.normalise(review.title)),
                "liked": _truncate(tx.meaningful_text(review.positive_text)),
                "disliked": _truncate(tx.meaningful_text(review.negative_text)),
            }
            for local_id, review in local_ids.items()
        ]}
        max_tokens = self._tokens_per_review * len(reviews) + REASONING_TOKEN_ALLOWANCE
        chat = self._client.complete_json(self._system, json.dumps(payload, ensure_ascii=False), max_tokens)
        try:
            parsed = parse_batch(chat.content)
        except (ValidationError, ValueError) as exc:
            raise LLMError(f"LLM returned invalid JSON: {type(exc).__name__}") from None

        outcome = BatchOutcome(prompt_tokens=chat.prompt_tokens, completion_tokens=chat.completion_tokens)
        for item in parsed:
            review = local_ids.get(item.id)
            if review is None or review.id in outcome.results:
                continue
            source = "\n".join(filter(None, (tx.normalise(review.title), tx.normalise(review.positive_text),
                                             tx.normalise(review.negative_text))))
            mentions, rejected = validated_mentions(item, self._allowed, source)
            outcome.rejected_topics += rejected
            result = AnalysisResult(
                review_id=review.id,
                content_hash=review.content_hash,
                sentiment=item.sentiment,
                sentiment_score=round(item.sentiment_score, 3),
                method=self.method,
                summary=item.summary,
                topics=mentions,
            )
            result.dedupe_topics()
            outcome.results[review.id] = result
        missing = len(reviews) - len(outcome.results)
        if missing:
            logger.warning("LLM response missing/invalid for %d of %d reviews", missing, len(reviews))
        return outcome
