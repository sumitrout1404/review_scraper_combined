"""Deterministic, data-driven insight statements for operations staff (GET /api/insights).

Every statement is computed from counts in the selected window and the previous
window of the same length. Each rule is a small function that returns zero or
more ``Insight`` objects; ``generate`` runs them all and ranks the result.

Guard rails
-----------
* Percentages are only quoted when the denominator is >= ``MIN_SAMPLE`` (5);
  otherwise the statement is phrased as a plain count, or dropped.
* Score comparisons need >= ``MIN_SAMPLE`` reviews in *both* windows.
* A topic needs >= ``MIN_TOPIC_MENTIONS`` mentions before it is called out.
* Ranking: alert > warning > info > positive, then by magnitude.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from db import REVIEWS

from ..db import aggregate
from ..deps import Filters
from .catalog import label_for, list_properties, topic_labels
from .dates import describe_window, previous_window, sydney_today, week_start
from .query import base_match, pct
from .stats import daily_rows, stats_for
from .topic_stats import TopicCounts, topic_counts

MIN_SAMPLE = 5
MIN_TOPIC_MENTIONS = 2
MAX_ITEMS = 12
LOW_SCORE = 6  # reviews scoring below this need a reply
SEVERITY_RANK = {"alert": 0, "warning": 1, "info": 2, "positive": 3}

# Score change thresholds (points on the 1-10 scale).
SCORE_ALERT_DROP = -1.0
SCORE_WARNING_DROP = -0.5
SCORE_NOTABLE_RISE = 0.5
OVERALL_POSITIVE_RISE = 0.3
BIGGEST_DROP_MIN = -0.3
# Complaint-share thresholds (% of negative reviews).
SHARE_ALERT_PCT = 40
SHARE_ALERT_MIN_COUNT = 4
SHARE_WARNING_PCT = 25
# A single property "owns" a complaint when it has at least this share of mentions.
PROPERTY_CONCENTRATION = 0.6
# Negative-review share rise (percentage points).
NEG_SHARE_WARNING_PTS = 10
NEG_SHARE_ALERT_PTS = 20


@dataclass
class Insight:
    """One statement; ``weight`` only orders items within a severity and is not exposed."""

    id: str
    severity: str
    title: str
    text: str
    property_id: str | None = None
    topic: str | None = None
    sample_size: int = 0
    weight: float = 0.0

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity,
            "title": self.title,
            "text": self.text,
            "property_id": self.property_id,
            "topic": self.topic,
            "sample_size": self.sample_size,
        }


@dataclass
class Context:
    """Everything the rules need, computed once per request."""

    filters: Filters
    d_from: date
    d_to: date
    when: str  # e.g. "this week"
    prev_when: str  # e.g. "last week"
    labels: dict[str, str]
    properties: dict[str, dict[str, Any]]
    cur_rows: list[dict[str, Any]]
    prev_rows: list[dict[str, Any]]
    cur: dict[str, Any]
    prev: dict[str, Any]
    topics_cur: TopicCounts
    topics_prev: TopicCounts

    @property
    def multi_property(self) -> bool:
        return len(self.properties) > 1

    def short(self, property_id: str) -> str:
        prop = self.properties.get(property_id)
        return prop["short_name"] if prop else property_id

    def label(self, topic: str) -> str:
        return label_for(self.labels, topic)


# ---------------------------------------------------------------- wording helpers
def phrase(label: str) -> str:
    """Label for use mid-sentence: 'Check-in & check-out' -> 'check-in & check-out'; keeps 'Wi-Fi…'."""
    if label.lower().startswith(("wi-fi", "wifi")) or label[:2].isupper():
        return label
    return label[0].lower() + label[1:]


def plural(n: int, word: str = "review") -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def fmt_score(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}"


def previous_phrase(p_from: date, p_to: date, today: date) -> str:
    """How to refer to the comparison window in a sentence."""
    this_monday = week_start(today)
    if (p_from, p_to) == (this_monday - timedelta(days=7), this_monday - timedelta(days=1)):
        return "last week"
    if (p_from, p_to) == (this_monday - timedelta(days=14), this_monday - timedelta(days=8)):
        return "the week before"
    days = (p_to - p_from).days + 1
    if days == 1:
        return f"the previous day ({p_from.strftime('%a')} {p_from.day} {p_from.strftime('%b')})"
    return f"the previous {days} days"


# ---------------------------------------------------------------- rules
def volume(ctx: Context) -> list[Insight]:
    """Tell the user when there is too little data for reliable statements."""
    n = ctx.cur["count"]
    if n == 0:
        text = f"No reviews were posted {ctx.when}. Widen the date range to see earlier guest feedback."
        return [Insight("volume:none", "info", "No reviews in this period", text)]
    if n < MIN_SAMPLE:
        verb = "was" if n == 1 else "were"
        text = (
            f"Only {plural(n)} {verb} posted {ctx.when}, so trends are not reliable yet. "
            "Widen the date range for a fuller picture."
        )
        return [Insight("volume:low", "info", "Not many reviews yet", text, sample_size=n)]
    return []


def overall_score(ctx: Context) -> list[Insight]:
    """Average score for the window, compared with the previous window when both are big enough."""
    n, cur_avg, prev_avg = ctx.cur["count"], ctx.cur["avg_score"], ctx.prev["avg_score"]
    if n == 0:
        return []
    if n < MIN_SAMPLE or ctx.prev["count"] < MIN_SAMPLE:
        text = (
            f"Average score {ctx.when} is {fmt_score(cur_avg)} from {plural(n)} "
            f"(too few reviews {ctx.prev_when} to compare)."
        )
        return [Insight("score:overall", "info", "Overall guest score", text, sample_size=n)]
    change = round(cur_avg - prev_avg, 2)
    if change <= SCORE_ALERT_DROP:
        severity = "alert"
    elif change <= SCORE_WARNING_DROP:
        severity = "warning"
    elif change >= OVERALL_POSITIVE_RISE:
        severity = "positive"
    else:
        severity = "info"
    if abs(change) >= 0.05:
        direction = "down" if change < 0 else "up"
        comparison = f"{direction} {abs(change):.1f} from {fmt_score(prev_avg)} {ctx.prev_when}."
    else:
        comparison = f"about the same as {ctx.prev_when} ({fmt_score(prev_avg)})."
    text = f"Average score {ctx.when} is {fmt_score(cur_avg)} from {n} reviews, {comparison}"
    return [Insight("score:overall", severity, "Overall guest score", text, sample_size=n, weight=abs(change))]


def property_scores(ctx: Context) -> list[Insight]:
    """Per-property week-over-week change; flags the property with the biggest drop."""
    changes = []
    for pid in ctx.properties:
        cur, prev = stats_for(ctx.cur_rows, pid), stats_for(ctx.prev_rows, pid)
        if cur["count"] >= MIN_SAMPLE and prev["count"] >= MIN_SAMPLE:
            changes.append((pid, round(cur["avg_score"] - prev["avg_score"], 2), cur, prev))
    if not changes:
        return []
    biggest = min(changes, key=lambda c: c[1])
    out = []
    for pid, change, cur, prev in changes:
        is_biggest = ctx.multi_property and pid == biggest[0] and change <= BIGGEST_DROP_MIN
        if abs(change) < SCORE_NOTABLE_RISE and not is_biggest:
            continue
        name = ctx.short(pid)
        direction = "down" if change < 0 else "up"
        text = (
            f"{name} averaged {fmt_score(cur['avg_score'])} {ctx.when} ({cur['count']} reviews), "
            f"{direction} {abs(change):.1f} from {fmt_score(prev['avg_score'])} {ctx.prev_when}."
        )
        if change < 0:
            severity = "alert" if change <= SCORE_ALERT_DROP else "warning" if change <= SCORE_WARNING_DROP else "info"
            title = f"Biggest score drop: {name}" if is_biggest else f"{name} score down"
        else:
            severity, title = "positive", f"{name} score up"
        weight = abs(change) + (0.5 if is_biggest else 0)
        out.append(Insight(f"score:{pid}", severity, title, text, pid, None, cur["count"], weight))
    return out


def _concentration(ctx: Context, topic: str) -> tuple[str | None, str]:
    """(property_id, sentence) when most complaints about ``topic`` come from one property."""
    split = ctx.topics_cur.negative_by_property.get(topic, {})
    total = sum(split.values())
    if not ctx.multi_property or total < 3:
        return None, ""
    pid, count = max(split.items(), key=lambda kv: (kv[1], kv[0]))
    if count / total < PROPERTY_CONCENTRATION:
        return None, ""
    return pid, f" Most of these complaints were at {ctx.short(pid)} ({count} of {total})."


def complaint_shares(ctx: Context) -> list[Insight]:
    """'40% of negative reviews this week mentioned cleanliness (4 of 10).'"""
    negatives = ctx.topics_cur.negative_reviews
    ranked = sorted(
        ((t, n) for t, n in ctx.topics_cur.neg_in_negative.items() if n >= MIN_TOPIC_MENTIONS),
        key=lambda kv: (-kv[1], kv[0]),
    )
    out = []
    for i, (topic, count) in enumerate(ranked[: 3 if negatives >= MIN_SAMPLE else 2]):
        label = ctx.label(topic)
        pid, where = _concentration(ctx, topic)
        if negatives >= MIN_SAMPLE:
            share = pct(count, negatives)
            if share >= SHARE_ALERT_PCT and count >= SHARE_ALERT_MIN_COUNT:
                severity = "alert"
            elif share >= SHARE_WARNING_PCT:
                severity = "warning"
            else:
                severity = "info"
            text = f"{share:.0f}% of negative reviews {ctx.when} mentioned {phrase(label)} ({count} of {negatives}).{where}"
            weight = share / 100
        else:
            severity = "warning" if count >= 3 else "info"
            text = f"{count} of the {negatives} negative reviews {ctx.when} mentioned {phrase(label)}.{where}"
            weight = count / 10
        title = f"Top complaint: {label}" if i == 0 else f"Recurring complaint: {label}"
        out.append(Insight(f"complaint-share:{topic}", severity, title, text, pid, topic, negatives, weight))
    return out


def complaint_changes(ctx: Context) -> list[Insight]:
    """Topics whose complaints spiked (or clearly eased) versus the previous window, adjusted for volume."""
    cur, prev = ctx.topics_cur, ctx.topics_prev
    spikes, easing = [], []
    for topic in set(cur.negative) | set(prev.negative):
        c, p = cur.negative.get(topic, 0), prev.negative.get(topic, 0)
        c_rate = c / cur.total_reviews if cur.total_reviews else 0
        p_rate = p / prev.total_reviews if prev.total_reviews else 0
        if c >= 3 and c - p >= 3 and c >= 2 * p and c_rate > 1.5 * p_rate:
            spikes.append((topic, c, p))
        elif p >= MIN_SAMPLE and c <= p / 2 and cur.total_reviews >= MIN_SAMPLE and c_rate < 0.5 * p_rate:
            easing.append((topic, c, p))
    out = []
    for topic, c, p in sorted(spikes, key=lambda x: (x[2] - x[1], x[0]))[:2]:
        label = ctx.label(topic)
        severity = "alert" if c >= 5 and c >= 3 * max(p, 1) else "warning"
        text = (
            f"Complaints about {phrase(label)} rose to {c} {ctx.when}, from {p} {ctx.prev_when} "
            f"({cur.total_reviews} vs {prev.total_reviews} reviews in total)."
        )
        out.append(
            Insight(f"complaint-spike:{topic}", severity, f"{label} complaints rising", text, None, topic,
                    cur.total_reviews, (c - p) / 5)
        )  # fmt: skip
    for topic, c, p in sorted(easing, key=lambda x: (x[1] - x[2], x[0]))[:1]:
        label = ctx.label(topic)
        text = f"Complaints about {phrase(label)} fell to {c} {ctx.when}, from {p} {ctx.prev_when}."
        out.append(
            Insight(f"complaint-drop:{topic}", "positive", f"{label} complaints easing", text, None, topic,
                    cur.total_reviews, (p - c) / 10)
        )  # fmt: skip
    return out


def negative_share(ctx: Context) -> list[Insight]:
    """Flag a clear rise in the share of negative reviews."""
    n = ctx.cur["count"]
    if n < MIN_SAMPLE or ctx.prev["count"] < MIN_SAMPLE:
        return []
    rise = ctx.cur["pct_negative"] - ctx.prev["pct_negative"]
    if rise < NEG_SHARE_WARNING_PTS:
        return []
    severity = "alert" if rise >= NEG_SHARE_ALERT_PTS else "warning"
    text = (
        f"{ctx.cur['pct_negative']:.0f}% of reviews {ctx.when} were negative ({ctx.cur['negative']} of {n}), "
        f"up from {ctx.prev['pct_negative']:.0f}% {ctx.prev_when}."
    )
    return [Insight("negative-share", severity, "More negative reviews", text, sample_size=n, weight=rise / 100)]


def top_praise(ctx: Context) -> list[Insight]:
    """The most praised topic in the window."""
    if not ctx.topics_cur.positive:
        return []
    topic, count = max(ctx.topics_cur.positive.items(), key=lambda kv: (kv[1], kv[0]))
    if count < 3:
        return []
    total = ctx.topics_cur.total_reviews
    label = ctx.label(topic)
    if total >= MIN_SAMPLE:
        text = (
            f"{label} was the most praised topic {ctx.when}: {pct(count, total):.0f}% of reviews "
            f"({count} of {total}) complimented it."
        )
    else:
        text = f"{count} reviews {ctx.when} praised {phrase(label)}, more than any other topic."
    return [
        Insight(f"praise:{topic}", "positive", f"Guests love: {label}", text, None, topic, total, count / max(total, 1))
    ]


def unanswered_low_scores(ctx: Context) -> list[Insight]:
    """Low-score reviews without a hotel response: a concrete to-do for the team."""
    match = {**base_match(ctx.filters.properties, ctx.d_from, ctx.d_to), "score": {"$lt": LOW_SCORE}}
    no_reply = {"$eq": [{"$ifNull": ["$hotel_response", ""]}, ""]}
    rows = [
        {"p": r["_id"], "n": r["n"], "unanswered": r["unanswered"]}
        for r in aggregate(
            REVIEWS,
            [
                {"$match": match},
                {
                    "$group": {
                        "_id": "$property_id",
                        "n": {"$sum": 1},
                        "unanswered": {"$sum": {"$cond": [no_reply, 1, 0]}},
                    }
                },
            ],
        )
    ]
    low_total = sum(int(r["n"]) for r in rows)
    by_property = {r["p"]: int(r["unanswered"] or 0) for r in rows if r["unanswered"]}
    unanswered = sum(by_property.values())
    if not unanswered:
        return []
    pid = next(iter(by_property)) if len(by_property) == 1 else None
    detail = ""
    if ctx.multi_property and len(by_property) > 1:
        ordered = sorted(by_property.items(), key=lambda kv: (-kv[1], kv[0]))
        detail = " (" + ", ".join(f"{ctx.short(p)} {c}" for p, c in ordered) + ")"
    elif pid and ctx.multi_property:
        detail = f" (all at {ctx.short(pid)})"
    verb = "has" if unanswered == 1 else "have"
    text = (
        f"{unanswered} of {plural(low_total)} scoring below {LOW_SCORE} {ctx.when} {verb} no hotel response yet{detail}. "
        "A public reply shows future guests the issue is being handled."
    )
    severity = "warning" if unanswered >= 3 else "info"
    return [
        Insight(
            "unanswered-low-scores",
            severity,
            "Unanswered low-score reviews",
            text,
            pid,
            None,
            low_total,
            unanswered / 10,
        )
    ]


RULES: tuple[Callable[[Context], list[Insight]], ...] = (
    volume,
    overall_score,
    property_scores,
    complaint_shares,
    complaint_changes,
    negative_share,
    top_praise,
    unanswered_low_scores,
)


def build_context(f: Filters, d_from: date, d_to: date, today: date) -> Context:
    p_from, p_to = previous_window(d_from, d_to)
    cur_rows = daily_rows(f.properties, d_from, d_to)
    prev_rows = daily_rows(f.properties, p_from, p_to)
    return Context(
        filters=f,
        d_from=d_from,
        d_to=d_to,
        when=describe_window(d_from, d_to, today),
        prev_when=previous_phrase(p_from, p_to, today),
        labels=topic_labels(),
        properties={p["id"]: p for p in list_properties(f.properties)},
        cur_rows=cur_rows,
        prev_rows=prev_rows,
        cur=stats_for(cur_rows),
        prev=stats_for(prev_rows),
        topics_cur=topic_counts(f.properties, d_from, d_to),
        topics_prev=topic_counts(f.properties, p_from, p_to),
    )


def generate(f: Filters, d_from: date, d_to: date, today: date | None = None) -> list[dict[str, Any]]:
    """Run every rule for the window and return the ranked public insight dicts."""
    ctx = build_context(f, d_from, d_to, today or sydney_today())
    items = [insight for rule in RULES for insight in rule(ctx)]
    items.sort(key=lambda i: (SEVERITY_RANK[i.severity], -i.weight, i.id))
    return [i.public() for i in items[:MAX_ITEMS]]
