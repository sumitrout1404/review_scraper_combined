"""Evaluate classifiers against the hand-labelled gold set.

    python -m analysis.eval.evaluate                       # rules only (offline)
    python -m analysis.eval.evaluate --models openai/gpt-oss-120b openai/gpt-oss-20b

Reports, per method:
  * per-topic precision / recall / F1 on (topic, polarity) pairs, plus micro and macro F1
  * topic detection F1 ignoring polarity
  * sentiment accuracy
  * insight error: for each topic, |predicted - gold| share of negative reviews complaining
    about it (the number the dashboard shows), averaged over topics, in percentage points
LLM predictions are cached in ``eval/predictions/`` so re-running costs no tokens
(``--refresh`` to call the API again).
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path

from analysis.lexicon import Lexicon
from analysis.models import ReviewInput
from analysis.rules import RulesClassifier

EVAL_DIR = Path(__file__).resolve().parent
GOLD_PATH = EVAL_DIR / "gold.jsonl"
PREDICTIONS_DIR = EVAL_DIR / "predictions"

Pair = tuple[str, str]


@dataclass
class Prediction:
    topics: set[Pair]
    sentiment: str


@dataclass
class Report:
    name: str
    per_topic: dict[str, tuple[float, float, float, int]] = field(default_factory=dict)
    micro: tuple[float, float, float] = (0.0, 0.0, 0.0)
    macro_f1: float = 0.0
    detection_f1: float = 0.0
    sentiment_accuracy: float = 0.0
    insight_error_pp: float = 0.0
    n: int = 0
    notes: str = ""


def load_gold(path: Path = GOLD_PATH) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def to_input(item: dict) -> ReviewInput:
    return ReviewInput(id=str(item["id"]), score=float(item["score"]), content_hash="eval",
                       title=item.get("title"), positive_text=item.get("positive_text"),
                       negative_text=item.get("negative_text"), language=item.get("language"))


def gold_pairs(item: dict) -> set[Pair]:
    return {(t, p) for t, p in item["topics"]}


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def score(name: str, gold: list[dict], preds: dict[str, Prediction], topics: list[str]) -> Report:
    report = Report(name=name, n=len(gold))
    tp, fp, fn = Counter(), Counter(), Counter()
    det = Counter()
    sentiment_hits = 0
    gold_neg_share, pred_neg_share = Counter(), Counter()
    negatives = [g for g in gold if g["sentiment"] == "negative"]
    for item in gold:
        truth, pred = gold_pairs(item), preds[str(item["id"])]
        for topic, _ in truth & pred.topics:
            tp[topic] += 1
        for topic, _ in pred.topics - truth:
            fp[topic] += 1
        for topic, _ in truth - pred.topics:
            fn[topic] += 1
        truth_topics, pred_topics = {t for t, _ in truth}, {t for t, _ in pred.topics}
        det["tp"] += len(truth_topics & pred_topics)
        det["fp"] += len(pred_topics - truth_topics)
        det["fn"] += len(truth_topics - pred_topics)
        sentiment_hits += pred.sentiment == item["sentiment"]
        if item["sentiment"] == "negative":
            gold_neg_share.update({t for t, p in truth if p == "negative"})
            pred_neg_share.update({t for t, p in pred.topics if p == "negative"})
    f1s = []
    for topic in topics:
        p, r, f1 = _prf(tp[topic], fp[topic], fn[topic])
        support = tp[topic] + fn[topic]
        report.per_topic[topic] = (p, r, f1, support)
        if support:
            f1s.append(f1)
    report.micro = _prf(sum(tp.values()), sum(fp.values()), sum(fn.values()))
    report.macro_f1 = sum(f1s) / len(f1s) if f1s else 0.0
    report.detection_f1 = _prf(det["tp"], det["fp"], det["fn"])[2]
    report.sentiment_accuracy = sentiment_hits / len(gold) if gold else 0.0
    if negatives:
        errors = [abs(pred_neg_share[t] - gold_neg_share[t]) / len(negatives) * 100 for t in topics]
        report.insight_error_pp = sum(errors) / len(errors)
    return report


def predict_rules(gold: list[dict], lexicon: Lexicon) -> dict[str, Prediction]:
    clf = RulesClassifier(lexicon)
    out = {}
    for item in gold:
        result = clf.classify(to_input(item))
        out[str(item["id"])] = Prediction({(m.topic, m.polarity) for m in result.topics}, result.sentiment)
    return out


def predict_llm(gold: list[dict], lexicon: Lexicon, model: str, refresh: bool) -> tuple[dict[str, Prediction], str]:
    """LLM predictions, cached per model and extended incrementally (only uncached reviews are sent).

    Reviews the LLM fails on fall back to rules, exactly as in production.
    """
    cache = PREDICTIONS_DIR / f"{model.replace('/', '__')}.json"
    data: dict = {"model": model, "meta": {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0,
                                           "seconds": 0.0, "errors": []}, "results": {}}
    if cache.is_file() and not refresh:
        data = json.loads(cache.read_text(encoding="utf-8"))
    todo = [g for g in gold if str(g["id"]) not in data["results"]]
    if todo:
        _call_llm(todo, lexicon, model, data, cache)
    rules = predict_rules(gold, lexicon)
    preds = {rid: Prediction({tuple(p) for p in v["topics"]}, v["sentiment"])
             for rid, v in data["results"].items() if rid in rules}
    fallback = [rid for rid in rules if rid not in preds]
    preds.update({rid: rules[rid] for rid in fallback})
    meta = data["meta"]
    tokens = meta["prompt_tokens"] + meta["completion_tokens"]
    per_review = tokens / max(1, len(data["results"]))
    notes = (f"{meta['requests']} requests, {tokens} tokens ({per_review:.0f}/review), "
             f"{meta['seconds']:.0f}s wall, {len(fallback)} fell back to rules"
             + (f"; errors: {sorted(set(meta['errors']))[:3]}" if meta["errors"] else ""))
    return preds, notes


def _call_llm(gold: list[dict], lexicon: Lexicon, model: str, data: dict, cache: Path) -> None:
    from analysis.llm_classifier import LLMClassifier
    from analysis.llm_client import GroqClient, LLMUnavailableError
    from analysis.settings import _default_reasoning_effort, load_settings

    settings = replace(load_settings(), groq_model=model, reasoning_effort=_default_reasoning_effort(model))
    client = GroqClient(settings)
    llm = LLMClassifier(client, lexicon)
    inputs = [to_input(g) for g in gold]
    meta = data["meta"]
    PREDICTIONS_DIR.mkdir(exist_ok=True)
    try:
        for start in range(0, len(inputs), settings.batch_size):
            batch = inputs[start:start + settings.batch_size]
            t0 = time.monotonic()
            try:
                outcome = llm.classify_batch(batch)
            except LLMUnavailableError as exc:
                meta["errors"].append(f"{type(exc).__name__}: {exc}")
                break
            except Exception as exc:   # record and continue; missing reviews fall back to rules
                meta["errors"].append(f"{type(exc).__name__}: {exc}")
                continue
            finally:
                meta["seconds"] = round(meta["seconds"] + time.monotonic() - t0, 1)
            meta["requests"] += 1
            meta["prompt_tokens"] += outcome.prompt_tokens
            meta["completion_tokens"] += outcome.completion_tokens
            for rid, res in outcome.results.items():
                data["results"][rid] = {"sentiment": res.sentiment, "summary": res.summary,
                                        "topics": sorted([m.topic, m.polarity] for m in res.topics),
                                        "evidence": {f"{m.topic}:{m.polarity}": m.evidence for m in res.topics}}
            cache.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
            logging.getLogger("analysis.eval").warning("%s: %d/%d reviews cached", model, len(data["results"]),
                                                       len(data["results"]) + len(inputs) - start - len(batch))
    finally:
        client.close()
        cache.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


def render(reports: list[Report], topics: list[str]) -> str:
    lines = ["| method | n | micro P | micro R | micro F1 | macro F1 | topic-only F1 | sentiment acc | "
             "insight err (pp) |", "|---|---|---|---|---|---|---|---|---|"]
    for r in reports:
        p, rc, f1 = r.micro
        lines.append(f"| {r.name} | {r.n} | {p:.2f} | {rc:.2f} | {f1:.2f} | {r.macro_f1:.2f} | "
                     f"{r.detection_f1:.2f} | {r.sentiment_accuracy:.2f} | {r.insight_error_pp:.1f} |")
    lines += ["", "Per-topic F1 on (topic, polarity) pairs (support = gold mentions):", "",
              "| topic | support | " + " | ".join(r.name for r in reports) + " |",
              "|---|---|" + "---|" * len(reports)]
    for topic in topics:
        support = reports[0].per_topic[topic][3]
        cells = " | ".join(f"{r.per_topic[topic][0]:.2f}/{r.per_topic[topic][1]:.2f}/{r.per_topic[topic][2]:.2f}"
                           for r in reports)
        lines.append(f"| {topic} | {support} | {cells} |")
    lines.append("")
    lines.append("(cells: precision/recall/F1)")
    notes = [f"- {r.name}: {r.notes}" for r in reports if r.notes]
    return "\n".join(lines + ([""] + notes if notes else []))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gold", type=Path, default=GOLD_PATH)
    parser.add_argument("--models", nargs="*", default=[], help="Groq models to evaluate (needs GROQ_API_KEY)")
    parser.add_argument("--refresh", action="store_true", help="ignore cached LLM predictions")
    parser.add_argument("--source", choices=["all", "real", "synthetic"], default="all")
    parser.add_argument("--lang", choices=["all", "en", "other"], default="all",
                        help="en = English (or unknown) reviews only; other = non-English only")
    parser.add_argument("--errors", action="store_true", help="print rules false positives/negatives")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)

    gold = [g for g in load_gold(args.gold) if args.source == "all" or g.get("source") == args.source]
    if args.lang != "all":
        gold = [g for g in gold if ((g.get("language") or "en") == "en") == (args.lang == "en")]
    lexicon = Lexicon.load()
    topics = [t.key for t in lexicon.topics]
    rules_preds = predict_rules(gold, lexicon)
    reports = [score("rules", gold, rules_preds, topics)]
    for model in args.models:
        preds, notes = predict_llm(gold, lexicon, model, args.refresh)
        report = score(f"llm:{model}", gold, preds, topics)
        report.notes = notes
        reports.append(report)
    print(render(reports, topics))  # noqa: T201 - CLI output
    if args.errors:
        for item in gold:
            truth, pred = gold_pairs(item), rules_preds[str(item["id"])]
            if truth != pred.topics or pred.sentiment != item["sentiment"]:
                print(f"\n[{item['id']}] score={item['score']} liked={item.get('positive_text')!r} "  # noqa: T201
                      f"disliked={item.get('negative_text')!r}\n  FP={sorted(pred.topics - truth)} "
                      f"FN={sorted(truth - pred.topics)} sentiment gold={item['sentiment']} pred={pred.sentiment}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
