"""Load ``topics.yaml`` and compile it into fast regular expressions.

A single alternation per term family is compiled with the longest terms first, so the
leftmost-longest phrase wins ("common area" beats "area", "hair dryer" beats "hair").
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

TermClass = Literal["aspect", "positive", "negative"]
TERM_CLASSES: tuple[TermClass, ...] = ("aspect", "positive", "negative")
_VALENCE: dict[str, int] = {"positive": 1, "negative": -1}

DEFAULT_TOPICS_PATH = Path(__file__).with_name("topics.yaml")


@dataclass(frozen=True)
class TopicDef:
    key: str
    label: str
    description: str
    sort_order: int


@dataclass(frozen=True)
class TermHit:
    """A lexicon match inside a clause (offsets are clause-relative)."""

    topic: str
    term_class: TermClass
    start: int
    end: int


@dataclass(frozen=True)
class OpinionHit:
    valence: int
    start: int
    end: int


def term_pattern(term: str) -> str:
    """Translate the YAML term syntax into a regex (see the header of topics.yaml)."""
    term = term.strip().lower()
    if term.startswith("re:"):
        return term[3:]
    words = term.split()
    parts: list[str] = []
    for index, word in enumerate(words):
        wildcard = word.endswith("*")
        word = word.rstrip("*")
        piece = re.escape(word)
        if wildcard:
            piece += r"\w*"
        elif index == len(words) - 1 and word[-1:].isalpha():
            piece += r"(?:s|es)?"
        parts.append(piece)
    return r"(?<!\w)" + r"[\s\-]*".join(parts) + r"(?!\w)"


_TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
_PREFIX_LEN = 3


@dataclass(frozen=True)
class _Term:
    regex: re.Pattern[str]
    payloads: list[Any]


class _Alternation:
    """Leftmost-longest matching of many terms, indexed by their first token.

    At each token start only the handful of terms that can begin with that token are
    tried, which is ~50x faster than one giant regex alternation.
    """

    def __init__(self, entries: list[tuple[str, Any]]) -> None:
        by_pattern: dict[str, list[Any]] = {}
        keys_of: dict[str, set[tuple[str, str]]] = {}
        for term, payload in entries:
            pattern = term_pattern(term)
            payloads = by_pattern.setdefault(pattern, [])
            if payload not in payloads:
                payloads.append(payload)
            keys_of.setdefault(pattern, set()).update(_index_keys(term))
        self._exact: dict[str, list[_Term]] = {}
        self._prefix: dict[str, list[_Term]] = {}
        self._anywhere: list[_Term] = []
        for pattern, payloads in by_pattern.items():
            entry = _Term(re.compile(pattern), payloads)
            for kind, key in keys_of[pattern]:
                {"exact": self._exact, "prefix": self._prefix}.get(kind, {}).setdefault(key, []).append(entry)
                if kind == "anywhere":
                    self._anywhere.append(entry)

    def _candidates(self, token: str) -> list[_Term]:
        found: list[_Term] = list(self._anywhere)
        forms = [token]                       # ordered => deterministic tie-breaking
        if token.endswith("s"):
            forms.append(token[:-1])
        if token.endswith("es"):
            forms.append(token[:-2])
        for form in forms:
            found += self._exact.get(form, [])
        found += self._prefix.get(token[:_PREFIX_LEN], [])
        return found

    def finditer(self, text: str) -> Iterator[tuple[int, int, list[Any]]]:
        """Yield (start, end, payloads), non-overlapping, longest match at each position."""
        consumed = 0
        for token in _TOKEN_RE.finditer(text):
            if token.start() < consumed:
                continue
            best: tuple[int, _Term] | None = None
            for term in self._candidates(token.group(0)):
                match = term.regex.match(text, token.start())
                if match and (best is None or match.end() > best[0]):
                    best = (match.end(), term)
            if best is not None:
                consumed = best[0]
                yield token.start(), best[0], best[1].payloads


def _index_keys(term: str) -> set[tuple[str, str]]:
    """Index keys for a YAML term: its first token (or prefix for wildcards) and joined forms."""
    term = term.strip().lower()
    if term.startswith("re:"):
        return {("anywhere", "")}
    words = term.split()
    first = words[0]
    keys: set[tuple[str, str]] = set()
    if first.endswith("*"):
        keys.add(("prefix", first.rstrip("*")[:_PREFIX_LEN]))
    else:
        first_token = _TOKEN_RE.match(first)
        keys.add(("exact", first_token.group(0) if first_token else first))
    if len(words) > 1:   # "check in" also matches "checkin", "wi fi" matches "wifi"
        joined = "".join(w.rstrip("*") for w in words)
        keys.add(("prefix", joined[:_PREFIX_LEN]) if "*" in term else ("exact", joined))
        keys.add(("exact", words[0] + words[1].rstrip("*")))
    return keys


@dataclass(frozen=True)
class AnchoredRule:
    """Generic descriptors ('small', 'old') that only count next to an anchor noun ('room', 'pod')."""

    topic: str
    anchors: _Alternation
    descriptors: _Alternation
    window: int


class Lexicon:
    """Compiled topic lexicon + generic opinion words."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.topics: list[TopicDef] = []
        term_entries: list[tuple[str, tuple[str, TermClass]]] = []
        self.anchored: list[AnchoredRule] = []
        for raw in data["topics"]:
            key = raw["key"]
            self.topics.append(TopicDef(key, raw["label"], raw.get("description", ""), int(raw["sort_order"])))
            for term_class in TERM_CLASSES:
                term_entries += [(str(t), (key, term_class)) for t in raw.get(term_class) or []]
            for rule in raw.get("anchored") or []:
                descriptors = [(str(t), _VALENCE[v]) for v in ("positive", "negative") for t in rule.get(v) or []]
                self.anchored.append(AnchoredRule(
                    topic=key,
                    anchors=_Alternation([(str(a), key) for a in rule["anchors"]]),
                    descriptors=_Alternation(descriptors),
                    window=int(rule.get("window", 4)),
                ))
        self.topic_keys: frozenset[str] = frozenset(t.key for t in self.topics)
        self._terms = _Alternation(term_entries)
        sentiment = data.get("sentiment") or {}
        self._opinions = _Alternation(
            [(str(t), 1) for t in sentiment.get("positive") or []]
            + [(str(t), -1) for t in sentiment.get("negative") or []]
        )
        self._strong_positive = _Alternation([(str(t), 1) for t in sentiment.get("strong_positive") or []])
        self._strong_negative = _Alternation([(str(t), -1) for t in sentiment.get("strong_negative") or []])

    @classmethod
    def load(cls, path: Path = DEFAULT_TOPICS_PATH) -> Lexicon:
        with path.open(encoding="utf-8") as handle:
            return cls(yaml.safe_load(handle))

    def term_hits(self, lower: str) -> list[TermHit]:
        """All topic-term matches; a valenced class beats 'aspect' for the same term and topic."""
        hits: list[TermHit] = []
        for start, end, payloads in self._terms.finditer(lower):
            best: dict[str, TermClass] = {}
            for topic, term_class in payloads:
                if topic not in best or best[topic] == "aspect":
                    best[topic] = term_class
            hits += [TermHit(topic, term_class, start, end) for topic, term_class in best.items()]
        return hits

    def opinion_hits(self, lower: str) -> list[OpinionHit]:
        return [OpinionHit(payloads[0], s, e) for s, e, payloads in self._opinions.finditer(lower)]

    def strong_counts(self, lower: str) -> tuple[int, int]:
        """(# strong praise phrases, # strong complaint phrases)."""
        return (sum(1 for _ in self._strong_positive.finditer(lower)),
                sum(1 for _ in self._strong_negative.finditer(lower)))
