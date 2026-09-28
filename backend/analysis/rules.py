"""Deterministic, offline topic + sentiment classifier.

Booking splits every review into a *liked* box (``positive_text``) and a *disliked* box
(``negative_text``). That split is the strongest polarity signal we have, so topics are
matched separately per box: a mention defaults to praise in the liked box and to a
complaint in the disliked box. The default is then overridden by explicit evidence in
the same clause — negation ("wasn't clean"), opinion words ("staff were lovely"),
"no complaints about ...", "... was not an issue", wishes ("could be cleaner"), and
exception markers in the liked box ("great stay apart from the noise").
"""
from __future__ import annotations

import re
from collections import defaultdict

from analysis import text as tx
from analysis.lexicon import Lexicon, TermHit
from analysis.models import (
    EVIDENCE_MAX_CHARS,
    RULES_METHOD,
    AnalysisResult,
    Polarity,
    ReviewInput,
    TopicMention,
)
from analysis.sentiment import SentimentInputs, rules_sentiment

_DISLIKE_BEFORE_RE = re.compile(
    r"\b(?:didn't|did\s+not|don't|do\s+not|doesn't|does\s+not|not|wasn't|weren't)\s+(?:really\s+|too\s+|very\s+)?"
    r"(?:like|enjoy|love|appreciate|care\s+for|happy\s+with|impressed\s+(?:by|with)|a\s+fan\s+of)\b[^,]{0,40}$"
)
_POLARITY_OF_SIGN: dict[int, Polarity] = {1: "positive", -1: "negative"}


class RulesClassifier:
    """Lexicon-driven classifier. ``classify`` never raises for well-formed input."""

    method = RULES_METHOD

    def __init__(self, lexicon: Lexicon) -> None:
        self.lexicon = lexicon

    # -- public -------------------------------------------------------------------------------

    def classify(self, review: ReviewInput) -> AnalysisResult:
        """Topics per box + score-based sentiment adjusted by the text."""
        praise = self.topics_for_field(review.positive_text, "positive")
        complaints = self.topics_for_field(review.negative_text, "negative")
        mentions = praise + complaints
        sentiment, score = rules_sentiment(SentimentInputs(
            score=review.score,
            title=review.title,
            positive_text=tx.meaningful_text(review.positive_text),
            negative_text=tx.meaningful_text(review.negative_text),
            praise_count=len({m.topic for m in mentions if m.polarity == "positive"}),
            complaint_count=len({m.topic for m in mentions if m.polarity == "negative"}),
        ), self.lexicon)
        result = AnalysisResult(
            review_id=review.id,
            content_hash=review.content_hash,
            sentiment=sentiment,
            sentiment_score=score,
            method=self.method,
            summary=None,
            topics=mentions,
        )
        result.dedupe_topics()
        return result

    def topics_for_field(self, raw_text: str | None, field_polarity: Polarity) -> list[TopicMention]:
        """Topic mentions found in one Booking box (liked = 'positive', disliked = 'negative')."""
        cleaned = tx.meaningful_text(raw_text)
        if not cleaned:
            return []
        mentions: list[TopicMention] = []
        for clause in tx.split_clauses(cleaned):
            mentions += self._classify_clause(clause, field_polarity)
        return mentions

    # -- clause level -------------------------------------------------------------------------

    def _classify_clause(self, clause: tx.Clause, field_polarity: Polarity) -> list[TopicMention]:
        low = clause.lower
        in_disliked = field_polarity == "negative"
        default_sign = -1 if in_disliked or clause.exception else 1
        counterfactual = tx.is_counterfactual(low)

        hits = self.lexicon.term_hits(low)
        found: dict[str, dict[int, tuple[int, int]]] = defaultdict(dict)   # topic -> sign -> span
        valenced_signs: list[int] = []

        for hit in hits:
            if hit.term_class == "aspect":
                continue
            base = 1 if hit.term_class == "positive" else -1
            sign = self._valenced_sign(low, hit.start, hit.end, base, in_disliked, counterfactual)
            if sign is not None:
                found[hit.topic].setdefault(sign, (hit.start, hit.end))
                valenced_signs.append(sign)

        for topic, start, end, base in self._anchored_hits(low, hits):
            sign = self._valenced_sign(low, start, end, base, in_disliked, counterfactual)
            if sign is not None:
                found[topic].setdefault(sign, (start, end))
                valenced_signs.append(sign)

        opinion = sum(valenced_signs) + self._generic_opinion(low, hits, counterfactual)
        for hit in hits:
            if hit.term_class != "aspect" or hit.topic in found:
                continue
            sign = self._aspect_sign(low, hit, opinion, default_sign, counterfactual, in_disliked)
            if sign is not None:
                found[hit.topic].setdefault(sign, (hit.start, hit.end))

        return [
            TopicMention(topic, _POLARITY_OF_SIGN[sign], self._evidence(clause, span))
            for topic, by_sign in found.items()
            for sign, span in by_sign.items()
        ]

    @staticmethod
    def _valenced_sign(low: str, start: int, end: int, base: int, in_disliked: bool,
                       counterfactual: bool) -> int | None:
        """Polarity of an opinion term after negation / neutralisers; None = too ambiguous."""
        if _DISLIKE_BEFORE_RE.search(low[:start]):
            return -1
        negated = tx.is_negated(low, start)
        sign = -base if negated else base
        if base < 0 and not negated and (
            tx.is_neutralised_after(low, end) or tx.has_complaint_negator_before(low, start)
        ):
            sign = 1
        if sign > 0 and counterfactual:
            return -1
        single_word = not re.search(r"[\s\-]", low[start:end])
        if base > 0 and sign > 0 and in_disliked and single_word and not tx.is_assertive(low, start):
            return None   # "clean more often", "cheap pillows" — not praise
        return sign

    @staticmethod
    def _aspect_sign(low: str, hit: TermHit, opinion: int, default_sign: int, counterfactual: bool,
                     in_disliked: bool) -> int | None:
        """Polarity of an aspect-only mention; None = too ambiguous to tag."""
        if _DISLIKE_BEFORE_RE.search(low[:hit.start]):
            return -1                               # "didn't like the kitchen"
        if tx.is_negated(low, hit.start):
            # "no lift" in the disliked box is a complaint; "No breakfast" typed into the liked box is not
            return -1 if in_disliked or default_sign < 0 else None
        if tx.has_complaint_negator_before(low, hit.start) or tx.is_neutralised_after(low, hit.end):
            return 1                                # "no complaints about the staff", "wifi was fine"
        if counterfactual:
            return -1                               # "wish the kitchen had more pans"
        if opinion:
            return 1 if opinion > 0 else -1          # "staff were lovely" in the disliked box
        return default_sign

    def _generic_opinion(self, low: str, hits: list[TermHit], counterfactual: bool) -> int:
        """Net generic opinion ('great', 'terrible') in the clause, ignoring words already used as topic terms."""
        taken = [(h.start, h.end) for h in hits]
        total = 0
        for op in self.lexicon.opinion_hits(low):
            if any(s < op.end and op.start < e for s, e in taken):
                continue
            sign = -op.valence if tx.is_negated(low, op.start) else op.valence
            total += -1 if (sign > 0 and counterfactual) else sign
        return total

    def _anchored_hits(self, low: str, hits: list[TermHit]) -> list[tuple[str, int, int, int]]:
        """Descriptors assigned to the nearest anchor noun ('pod was tiny' -> room_condition)."""
        taken = [(h.start, h.end) for h in hits]
        best: dict[tuple[int, int], tuple[int, str, int]] = {}
        for rule in self.lexicon.anchored:
            anchors = [tx.token_index_at(low, s) for s, _, _ in rule.anchors.finditer(low)]
            if not anchors:
                continue
            for start, end, payloads in rule.descriptors.finditer(low):
                if any(s < end and start < e for s, e in taken):
                    continue
                position = tx.token_index_at(low, start)
                distance = min(abs(position - a) for a in anchors)
                if distance <= rule.window and ((start, end) not in best or distance < best[(start, end)][0]):
                    best[(start, end)] = (distance, rule.topic, payloads[0])
        return [(topic, s, e, valence) for (s, e), (_, topic, valence) in best.items()]

    @staticmethod
    def _evidence(clause: tx.Clause, span: tuple[int, int]) -> str:
        start, end = clause.offset + span[0], clause.offset + span[1]
        return tx.snippet(clause.sentence, start, end, EVIDENCE_MAX_CHARS)
