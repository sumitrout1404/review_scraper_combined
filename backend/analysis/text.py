"""Text utilities for the rules classifier: normalisation, placeholders, clauses, negation.

Everything here is pure (no I/O) and deterministic so it can be unit-tested in isolation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_CHAR_MAP = str.maketrans({
    "\u2019": "'", "\u2018": "'", "\u02bc": "'", "`": "'",
    "\u201c": '"', "\u201d": '"',
    "\u2010": "-", "\u2011": "-", "\u2013": "-", "\u2014": "-", "\u2212": "-",
    "\u00a0": " ",
})

# Whole-field "nothing to report" answers Booking guests type into the liked/disliked boxes.
_PLACEHOLDER_RE = re.compile(
    r"""^(?:
        nothing|none|nil|nada|zilch|na|n/?a|no|nope|nah|not\s+applicable|-+|\.+|x|
        no\s+comments?|no\s+complaints?(?:\s+at\s+all)?|zero\s+complaints|
        nothing\s+(?:at\s+all|really|much|in\s+particular|specific|special|else|bad|negative|
                   to\s+(?:complain|dislike|report|say|mention|add|note|fault|criticise|criticize)(?:\s+about)?|
                   comes\s+to\s+mind|i\s+can\s+think\s+of|that\s+i\s+can\s+think\s+of|
                   (?:that\s+)?i\s+(?:didn'?t|did\s+not)\s+like)|
        (?:i\s+)?(?:can'?t|cannot|could\s+not|couldn'?t)\s+think\s+of\s+anything|
        all\s+(?:good|fine|great|ok|okay)|
        everything(?:\s+was)?\s+(?:good|great|fine|perfect|ok|okay|excellent|amazing)|
        there\s+are\s+no\s+comments\s+available\s+for\s+this\s+review|
        no\s+negatives?|nothing\s+negative\s+to\s+say
    )$""",
    re.VERBOSE,
)

# "Nothing, ..." / "No complaints. ..." at the start of a longer answer: strip the prefix only.
# A punctuation separator is required so "Nothing worked" is NOT stripped.
_PLACEHOLDER_PREFIX_RE = re.compile(
    r"^(?:nothing(?:\s+(?:really|at\s+all|much|major|serious))?|none|n/a|no\s+complaints?(?:\s+at\s+all)?|"
    r"not\s+much|all\s+good)\s*[,.!;:\-]+\s*",
)

_SENTENCE_BREAK_RE = re.compile(r"[.!?;\n\r]+(?!\d)|\s-+\s")
_COMMA_RE = re.compile(r",")

# Connectors that start a new clause. Exception markers flip the default polarity of
# aspect-only mentions in the *liked* box ("Great stay apart from the noise").
_EXCEPTION_MARKERS = (
    r"but|however|except(?:\s+for)?|apart\s+from|other\s+than|besides|although|though|even\s+though|"
    r"unfortunately|sadly|only\s+(?:thing|downside|down\s+side|issue|problem|complaint|negative|con|drawback|gripe)"
)
_CONNECTOR_RE = re.compile(rf"\b(?=(?:{_EXCEPTION_MARKERS}|whereas|while)\b)")
_EXCEPTION_START_RE = re.compile(rf"^\W*(?:the\s+)?(?:{_EXCEPTION_MARKERS})\b")

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")

NEGATORS = frozenset({
    "not", "no", "never", "without", "hardly", "barely", "nothing", "none", "nor", "neither",
    "zero", "lack", "lacked", "lacking", "cannot", "cant", "wasnt", "werent", "isnt", "arent",
    "didnt", "doesnt", "dont", "couldnt", "wouldnt", "wont", "hasnt", "havent", "hadnt",
    "shouldnt", "mustnt", "aint",
})
NEGATION_WINDOW = 3
SCOPE_BREAKERS = frozenset({"and", "or", "but", "so", "then", "plus", "also"})

# "noise was not an issue", "snoring didn't bother us", "wifi was fine"
_NEUTRALISER_RE = re.compile(
    r"^\W*(?:\w+\W+){0,3}?(?:"
    r"(?:was|were|is|are|wasn't|weren't|isn't|aren't)?\s*(?:not|n't|never)\s+"
    r"(?:an?\s+|really\s+|too\s+|that\s+|very\s+|much\s+of\s+an?\s+|a\s+big\s+)?"
    r"(?:issue|problem|bother|concern|big\s+deal|bad|noticeable|an\s+issue|a\s+problem|deal)"
    r"|(?:didn't|did\s+not|doesn't|does\s+not|won't)\s+(?:bother|affect|disturb|matter)"
    r"|(?:was|were|is|are)\s+(?:fine|ok|okay|minimal|manageable|bearable|acceptable|tolerable|expected)"
    r")\b"
)

# "nothing wrong with the staff", "no complaints about the location", "can't fault the cleanliness"
_COMPLAINT_NEGATOR_RE = re.compile(
    r"\b(?:(?:nothing|no|zero|not\s+any)\s+(?:bad|wrong|negative|to\s+complain|to\s+fault|to\s+dislike|"
    r"complaints?|issues?|problems?)|(?:can't|cannot|couldn't|could\s+not)\s+fault)\b"
)

# Wishes / counterfactuals turn praise words into complaints ("staff could be more helpful").
_COUNTERFACTUAL_RE = re.compile(
    r"\b(?:(?:could|should|would|might)(?:\s+(?:have|'ve))?\s+(?:be|been)\s+(?:a\s+(?:bit|little|lot)\s+)?(?:more|better|nicer|cleaner|quieter|bigger|friendlier)"
    r"|(?:could|should)\s+(?:improve|use)|wish|needs?\s+(?:to|more|some|a\s+bit)|need\s+more|"
    r"would\s+(?:be\s+)?(?:have\s+been\s+)?nice\s+(?:if|to)|more\s+\w+\s+would|if\s+only|expected\s+(?:more|better))\b"
)

# Single-word praise in the *disliked* box only counts in an assertive frame
# ("the room was clean"), not as an imperative/noun modifier ("clean more often", "cheap pillows").
ASSERTIVE_PRECEDERS = frozenset({
    "was", "were", "is", "are", "very", "really", "so", "super", "quite", "pretty", "always",
    "reasonably", "fairly", "generally", "overall", "extremely", "incredibly", "also", "and",
    "nice", "lovely", "all", "been", "be", "felt", "seemed", "looked", "too", "though",
})


@dataclass(frozen=True)
class Clause:
    """A clause of a review field.

    ``lower`` has exactly the same length as ``text``. ``sentence`` is the enclosing
    sentence (used for evidence snippets) and ``offset`` is where ``text`` starts in it.
    """

    text: str
    lower: str
    exception: bool
    sentence: str
    offset: int


def normalise(text: str | None) -> str:
    """Unify quotes/dashes/whitespace while keeping the text readable."""
    if not text:
        return ""
    cleaned = text.translate(_CHAR_MAP)
    return re.sub(r"[ \t]+", " ", cleaned).strip()


def lower_same_length(text: str) -> str:
    """Lower-case without changing string length (so offsets map back to the original)."""
    return "".join(ch.lower() if len(ch.lower()) == 1 else ch for ch in text)


def _placeholder_key(text: str) -> str:
    key = lower_same_length(normalise(text))
    key = re.sub(r"[^\w/\-.' ]+", " ", key)   # drop emoji / stray symbols
    key = re.sub(r"\s+", " ", key).strip(" .!,'")
    return key


def is_placeholder(text: str | None) -> bool:
    """True for empty or 'Nothing' / 'N/A' / '-' style answers that carry no topic."""
    if not text or not text.strip():
        return True
    key = _placeholder_key(text)
    if not key:
        return True
    return bool(_PLACEHOLDER_RE.match(key))


def strip_placeholder_prefix(text: str) -> str:
    """Remove a leading 'Nothing, ...' so the remainder can still be classified."""
    lowered = lower_same_length(text)
    match = _PLACEHOLDER_PREFIX_RE.match(lowered)
    return text[match.end():] if match else text


def meaningful_text(text: str | None) -> str:
    """Normalised field text with placeholders removed ('' when nothing is left)."""
    cleaned = normalise(text)
    if is_placeholder(cleaned):
        return ""
    cleaned = strip_placeholder_prefix(cleaned)
    return "" if is_placeholder(cleaned) else cleaned


def _pieces(text: str, cut_points: list[int]) -> list[tuple[int, str]]:
    """Cut ``text`` at the given points; return (offset, stripped piece) pairs."""
    bounds = [0] + sorted(p for p in cut_points if 0 < p < len(text)) + [len(text)]
    out: list[tuple[int, str]] = []
    for start, end in zip(bounds, bounds[1:], strict=False):
        piece = text[start:end]
        stripped = piece.strip(" ,")
        if stripped:
            out.append((start + piece.index(stripped), stripped))
    return out


def split_clauses(text: str) -> list[Clause]:
    """Split into sentences, then clauses on commas and contrast connectors ('but', 'apart from' ...)."""
    clauses: list[Clause] = []
    sentence_cuts = [p for m in _SENTENCE_BREAK_RE.finditer(text) for p in (m.start(), m.end())]
    for _, sentence in _pieces(text, sentence_cuts):
        if not re.search(r"\w", sentence):
            continue
        low_sentence = lower_same_length(sentence)
        cuts = [m.start() for m in _COMMA_RE.finditer(sentence)]
        cuts += [m.start() for m in _CONNECTOR_RE.finditer(low_sentence)]
        for offset, piece in _pieces(sentence, cuts):
            low = low_sentence[offset:offset + len(piece)]
            clauses.append(Clause(piece, low, bool(_EXCEPTION_START_RE.match(low)), sentence, offset))
    return clauses


def tokens_before(lower: str, pos: int, n: int) -> list[str]:
    """The last ``n`` tokens ending before ``pos`` (apostrophes removed: wasn't -> wasnt)."""
    toks = [m.group(0).replace("'", "") for m in _TOKEN_RE.finditer(lower[:pos])]
    return toks[-n:]


def is_negated(lower: str, start: int) -> bool:
    """A negator within the NEGATION_WINDOW tokens before ``start``.

    Scope stops at a conjunction ("no lift and dirty rooms": 'dirty' is not negated), and a
    term that itself starts with a negator ("no hot water", "not bad") is never flipped again.
    """
    own = _TOKEN_RE.match(lower, start)
    if own and own.group(0).replace("'", "") in NEGATORS:
        return False
    for tok in reversed(tokens_before(lower, start, NEGATION_WINDOW)):
        if tok in SCOPE_BREAKERS:
            return False
        if tok in NEGATORS:
            return True
    return False


def is_neutralised_after(lower: str, end: int) -> bool:
    """'<term> was not an issue' / '<term> didn't bother us' / '<term> was fine'."""
    return bool(_NEUTRALISER_RE.match(lower[end:end + 60]))


def has_complaint_negator_before(lower: str, start: int) -> bool:
    """'nothing wrong with <term>' / 'no complaints about <term>'."""
    return bool(_COMPLAINT_NEGATOR_RE.search(lower[:start]))


def is_counterfactual(lower: str) -> bool:
    """'could be cleaner', 'wish the staff were friendlier', 'needs more ...'."""
    return bool(_COUNTERFACTUAL_RE.search(lower))


def is_assertive(lower: str, start: int) -> bool:
    """A copula / intensifier right before a single praise word."""
    return any(tok in ASSERTIVE_PRECEDERS for tok in tokens_before(lower, start, 2))


def token_index_at(lower: str, pos: int) -> int:
    """Number of tokens that start before ``pos`` (used for anchor distances)."""
    return sum(1 for m in _TOKEN_RE.finditer(lower) if m.start() < pos)


def word_count(text: str) -> int:
    return len(_TOKEN_RE.findall(lower_same_length(text)))


def snippet(text: str, start: int, end: int, limit: int = 160) -> str:
    """A substring of ``text`` of at most ``limit`` chars around [start, end)."""
    if len(text) <= limit:
        return text.strip()
    left = max(0, start - (limit - (end - start)) // 2)
    right = min(len(text), left + limit)
    left = max(0, right - limit)
    piece = text[left:right]
    if left > 0 and " " in piece:
        piece = piece[piece.index(" ") + 1:]
    if right < len(text) and " " in piece:
        piece = piece[:piece.rindex(" ")]
    return piece.strip()[:limit]
