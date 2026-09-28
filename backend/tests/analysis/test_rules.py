"""Rules classifier: placeholders, negation, liked/disliked polarity split, sentiment."""
from __future__ import annotations

import pytest

from analysis import text as tx
from analysis.lexicon import Lexicon
from analysis.models import ReviewInput
from analysis.rules import RulesClassifier


@pytest.fixture(scope="module")
def clf() -> RulesClassifier:
    return RulesClassifier(Lexicon.load())


def tags(clf: RulesClassifier, positive: str | None = None, negative: str | None = None,
         score: float = 7.0) -> set[tuple[str, str]]:
    result = clf.classify(ReviewInput("r1", score, "h", positive_text=positive, negative_text=negative))
    return {(m.topic, m.polarity) for m in result.topics}


@pytest.mark.parametrize("text", ["Nothing", "nothing at all!", "N/A", "n/a", "-", "...", "None", "No complaints",
                                  "Nothing to complain about", "nothing really", "All good :)", "Nope",
                                  "There are no comments available for this review", "  "])
def test_placeholder_negatives_are_ignored(clf: RulesClassifier, text: str) -> None:
    assert tx.is_placeholder(text)
    assert tags(clf, negative=text) == set()


def test_placeholder_prefix_is_stripped_but_rest_is_kept(clf: RulesClassifier) -> None:
    assert tx.meaningful_text("Nothing, the staff were lovely") == "the staff were lovely"
    assert tx.meaningful_text("Nothing worked") == "Nothing worked"   # no punctuation => not a placeholder
    assert tags(clf, negative="Nothing really, maybe the wifi was slow") == {("wifi", "negative")}


def test_polarity_follows_the_booking_box(clf: RulesClassifier) -> None:
    assert tags(clf, positive="Great location and friendly staff") == {("location", "positive"), ("staff", "positive")}
    assert tags(clf, negative="The shower and the kitchen") == {("bathroom", "negative"), ("facilities", "negative")}


def test_same_topic_can_be_praised_and_criticised(clf: RulesClassifier) -> None:
    got = tags(clf, positive="Rooms were clean", negative="The shared bathroom was dirty")
    assert {("cleanliness", "positive"), ("cleanliness", "negative"), ("bathroom", "negative")} <= got


@pytest.mark.parametrize(("negative", "expected"), [
    ("The room wasn't clean", {("cleanliness", "negative")}),
    ("Not the cleanest place", {("cleanliness", "negative")}),
    ("No lift and no hot water", {("facilities", "negative"), ("bathroom", "negative")}),
    ("Staff were not helpful", {("staff", "negative")}),
])
def test_negation_in_disliked_box(clf: RulesClassifier, negative: str, expected: set) -> None:
    assert tags(clf, negative=negative) == expected


@pytest.mark.parametrize(("positive", "expected"), [
    ("It wasn't noisy at all", {("noise", "positive")}),
    ("No noise, quiet at night", {("noise", "positive")}),
    ("Noise was not an issue", {("noise", "positive")}),
    ("Snoring didn't bother us", {("noise", "positive")}),
])
def test_negated_complaint_words_become_praise(clf: RulesClassifier, positive: str, expected: set) -> None:
    assert tags(clf, positive=positive) == expected


def test_praise_written_in_disliked_box(clf: RulesClassifier) -> None:
    assert tags(clf, negative="Nothing to complain about the staff") == {("staff", "positive")}
    assert tags(clf, negative="The only good thing was the location") == {("location", "positive")}


def test_complaint_written_in_liked_box(clf: RulesClassifier) -> None:
    assert tags(clf, positive="Great value apart from the noise") == {
        ("value_for_money", "positive"), ("noise", "negative")}
    assert tags(clf, positive="Good location but the wifi was terrible") == {
        ("location", "positive"), ("wifi", "negative")}


def test_wishes_and_imperatives_are_complaints(clf: RulesClassifier) -> None:
    assert tags(clf, negative="Could be cleaner") == {("cleanliness", "negative")}
    assert tags(clf, negative="Staff could be more helpful") == {("staff", "negative")}
    assert ("value_for_money", "positive") not in tags(clf, negative="Cheap pillows")


def test_pod_specific_terms(clf: RulesClassifier) -> None:
    got = tags(clf, negative="Guy in the next pod was snoring, curtain gives no privacy, lockers too small, "
                            "top bunk shakes")
    assert {("noise", "negative"), ("room_condition", "negative"), ("facilities", "negative"),
            ("bed_comfort", "negative")} <= got


def test_longest_phrase_wins(clf: RulesClassifier) -> None:
    assert tags(clf, negative="The common area was tiny") == {("facilities", "negative")}
    assert ("cleanliness", "negative") not in tags(clf, negative="Hair dryer was broken")
    assert tags(clf, negative="Bed bugs!") == {("cleanliness", "negative")}


def test_evidence_is_a_short_substring(clf: RulesClassifier) -> None:
    negative = "The check-in took forever. " + "Blah blah " * 40 + "and the room was filthy."
    result = clf.classify(ReviewInput("r1", 4.0, "h", negative_text=negative))
    for mention in result.topics:
        assert mention.evidence and len(mention.evidence) <= 160
        assert mention.evidence in negative


@pytest.mark.parametrize(("score", "expected"), [(9.0, "positive"), (8.0, "positive"), (7.0, "neutral"),
                                                 (6.0, "neutral"), (5.9, "negative"), (2.0, "negative")])
def test_sentiment_score_buckets(clf: RulesClassifier, score: float, expected: str) -> None:
    result = clf.classify(ReviewInput("r1", score, "h", positive_text="Location", negative_text="Nothing"))
    assert result.sentiment == expected
    assert -1.0 <= result.sentiment_score <= 1.0


def test_long_strongly_negative_text_pulls_a_seven_down(clf: RulesClassifier) -> None:
    negative = ("The room was filthy, there were cockroaches in the kitchen, the staff were rude and the noise "
                "from the bar downstairs kept us awake all night. Terrible experience, would not recommend.")
    result = clf.classify(ReviewInput("r1", 7.0, "h", positive_text="Location", negative_text=negative))
    assert result.sentiment == "negative"
    assert result.sentiment_score < 0


def test_classification_is_deterministic(clf: RulesClassifier) -> None:
    review = ReviewInput("r1", 6.5, "h", positive_text="Clean, great staff", negative_text="Noisy, small pod")
    assert clf.classify(review) == clf.classify(review)


def test_negated_aspect_in_liked_box_is_not_a_complaint(clf: RulesClassifier) -> None:
    assert tags(clf, positive="No breakfast") == set()
    assert tags(clf, negative="No breakfast") == {("breakfast_food", "negative")}
