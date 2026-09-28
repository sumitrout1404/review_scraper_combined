# Review insights (`backend/analysis`)

Turns each Booking.com review into:

- **overall sentiment**: `positive | neutral | negative`, plus a score from -1 to 1 and, for the LLM method, a one-line summary;
- **topic mentions**: zero or more of the 12 fixed operational topics, each with a **polarity** (praise or complaint) and an **evidence** snippet quoted from the review.

The results are embedded in each MongoDB review document, as `review.analysis` and `review.topics`, in one atomic update filtered on the analysed `content_hash`. The API aggregates them into statements such as *"40% of negative reviews this week mentioned cleanliness (4 of 10)"*.

```bash
cd backend
python -m analysis                          # auto: LLM if GROQ_API_KEY is set, else rules
python -m analysis --method rules           # offline, deterministic
python -m analysis --reanalyse              # ignore the cache (e.g. after a lexicon change)
python -m analysis --upgrade-rules          # re-run the LLM on recent reviews that were analysed by rules
python -m analysis --limit 50 --time-budget 60   # uses MONGODB_URI from backend/.env
python -m analysis.eval.evaluate --models openai/gpt-oss-120b openai/gpt-oss-20b [--lang en|other] [--errors]
pytest tests/analysis
```

```python
from analysis import run_analysis
stats = run_analysis(method="auto", time_budget_s=60)
# {'analysed', 'skipped', 'pending', 'llm_count', 'rules_count', 'rules_fallback_count', 'upgraded',
#  'errors', 'prompt_tokens', 'completion_tokens', 'llm_disabled_reason', 'stopped_early', ...}
```

## Methodology: hybrid rules + LLM

### Why the liked/disliked split drives polarity
Booking asks every guest two separate questions: *what did you like?* and *what didn't you like?*. The guest has already done the hardest part of sentiment analysis, which is deciding whether something is praise or a complaint. So each box is classified **separately**. A topic found in the disliked box is a complaint by default, and one found in the liked box is praise by default. This is much more reliable than scoring free text, and it lets one review both praise and criticise the same topic ("rooms clean" / "bathroom dirty").

The default is overridden only when the clause itself says otherwise:

| Pattern | Example | Result |
|---|---|---|
| negation (3-token scope, stops at *and/or/but*) | disliked: "room **wasn't** clean" | cleanliness complaint |
| negated complaint word | liked: "**wasn't** noisy", "**no** noise" | noise praise |
| neutraliser after the term | "noise **was not an issue**", "snoring **didn't bother** us" | praise |
| "no complaints about X" | disliked: "**nothing to complain about** the staff" | staff praise |
| opinion words next to an aspect | disliked: "the staff were **lovely** though" | staff praise |
| exception markers in the liked box | liked: "great stay **apart from** the noise" | noise complaint |
| wishes / imperatives | "**could be** cleaner", "staff **could be more** helpful" | complaint |
| "didn't like X" | "**didn't like** the location" | complaint |

Booking's placeholder answers (`Nothing`, `N/A`, `-`, `nothing at all`, `no complaints`, `all good`, "There are no comments available…") produce no topics. A leading "Nothing, …" is stripped, but the rest of the answer is still classified ("Nothing really, maybe the wifi was slow" is a wifi complaint).

### Rules method (`rules.py`, `topics.yaml`), always available
- `topics.yaml` holds the 12 topics (label, description, sort order, which are synced into the `topics` table) and a curated lexicon of about 900 terms in three classes:
  - **aspect** words that name a topic ("staff", "shower");
  - **positive** words ("spotless", "quiet");
  - **negative** words ("filthy", "snoring", "thin walls").
- The lexicon includes multi-word phrases, inflections and pod-hotel vocabulary: pod, capsule, curtain, privacy, lockers, bunk/top bunk, snoring, rustling plastic bags, shared bathroom, luggage storage.
- **Leftmost-longest matching.** "common area" (facilities) beats "area" (location), "hair dryer" (bathroom) beats "hair" (cleanliness), and "bed bugs" (cleanliness) beats "bed" (bed comfort).
- **Anchored descriptors** handle words that are too generic on their own ("small", "old", "nice"). They count only within 4 tokens of an anchor noun, and are assigned to the nearest one: "pod was tiny" is room_condition, "pillow was flat" is bed_comfort. This is how the **"room" vs "room condition"** overlap is controlled: the bare word "room" never creates a tag.
- A single praise word in the *disliked* box counts only in an assertive frame ("the room **was clean**"). This keeps "clean more often" or "cheap pillows" from becoming praise.
- **Sentiment** follows the contract's score buckets (≥ 8 positive, ≥ 6 neutral, < 6 negative), adjusted by a text signal. The signal weighs words liked vs disliked, praised vs criticised topics, and strong phrases ("never again", "bed bugs", "highly recommend"). Examples: a 7.0 with a long, strongly negative disliked box becomes negative, and a 7.5 with only praise becomes positive. `sentiment_score` is 70% score and 30% text, clamped into the label's band.
- It is deterministic, has no network access, and processes about 2,500 reviews per second, so a full re-analysis of the whole database takes seconds.

### LLM method (`llm_client.py`, `llm_classifier.py`, `llm_schema.py`)
- Groq's OpenAI-compatible chat-completions API, called with plain `httpx` (no SDK). Settings: `temperature 0`, `response_format: json_object`, and `reasoning_effort: low` for the gpt-oss models.
- **10 reviews per request.** The system prompt is compact and lists the 12 allowed keys with definitions, polarity rules and disambiguation rules. The prompt sends placeholder-free text, truncated to 700 characters per field, under short local ids (`r1..r10`) that are mapped back afterwards.
- Output is **untrusted and validated with pydantic**:
  - Unknown topics are dropped, polarity synonyms are normalised ("complaint" becomes "negative") and scores are clamped.
  - **Evidence must be grounded.** It has to be an exact quote (ignoring case and punctuation) or a close fuzzy match (≥ 0.75) to a clause of the review, otherwise the topic is dropped. The stored evidence is always the review's own text, widened to its sentence and capped at 160 characters.
- Non-English reviews: the LLM classifies them and quotes evidence in the original language. The rules method is English-only.
- **Resilience:**
  - Retries timeouts, 429 and 5xx with exponential backoff (`core.retry`), honouring `Retry-After`. It also paces itself from Groq's `x-ratelimit-remaining-tokens` and `x-ratelimit-reset-tokens` headers, so it waits for the token window to refill instead of collecting 429s.
  - A `CircuitBreaker` (`core.circuit_breaker`) wraps the client. Other conditions end LLM use for the rest of the run: a `Retry-After` longer than 60 s (daily quota), 401/403, 404 (model not available), or an exhausted time budget. Remaining reviews then go straight to rules.
  - A reply that is not valid JSON (usually truncated output) is retried once as two half-batches. A batch that still fails, or individual reviews missing from a valid response, **fall back to rules** for just those reviews. `method` records `llm:<model>` or `rules`.

### Which reviews go where (`pipeline.py`)
- **Idempotent on `(review_id, content_hash)`.** Only reviews without an analysis, or whose content hash changed, are processed, so reruns cost nothing. `--reanalyse` forces everything. Each review's `analysis` and `topics` are replaced together in **one atomic single-document update**. The update is filtered on the `content_hash` that was analysed, so a review the collector edits mid-run is left pending rather than overwritten with a stale result.
- The **LLM window** is `ANALYSIS_LLM_WINDOW_DAYS` (default 180). Only recent reviews that contain text go to the LLM, newest first, capped at `ANALYSIS_LLM_MAX_REVIEWS_PER_RUN` (default 400) and optionally `ANALYSIS_LLM_MAX_TOKENS_PER_RUN`. Older or over-cap reviews use rules immediately, so the dashboard always has full history.
- `--upgrade-rules` (`upgrade_rules=True`) later re-runs the LLM on unchanged in-window reviews stored as `rules`, for example after a rate-limited backfill. If an upgrade attempt fails, the existing rules row is kept.
- `time_budget_s` (used by the Vercel cron) makes the run stop cleanly between batches. Anything left over is reported as `pending` and picked up by the next run.

### How the insight percentages are defined
All percentages count **reviews, not mentions**. A review that complains twice about noise counts once.
- `pct_of_negative_reviews(topic)` = negative-sentiment reviews with a **complaint** on the topic ÷ negative-sentiment reviews in the window.
- `pct_of_reviews(topic)` = reviews mentioning the topic with either polarity ÷ all reviews.
- Complaints are counted from the disliked box *and* from complaints written in the liked box. Praise is counted the same way, the other way round.
- The API softens or drops statements with n < 5 (see CONTRACT.md).

## Evaluation (`eval/`)

`eval/gold.jsonl` is the hand-labelled gold set: 114 real reviews (see the results below). Labels are the (topic, polarity) pairs a careful human would tag, plus overall sentiment. They were written **without looking at classifier output**. `eval/sample_gold.py` draws the stratified sample from the DB (by property × score band, only reviews with text). `eval/evaluate.py` reports:
- per-topic precision, recall and F1 on (topic, polarity) pairs, plus micro and macro F1;
- topic-only F1, ignoring polarity;
- sentiment accuracy;
- **insight error**: the mean absolute difference, in percentage points, between the predicted and gold share of negative reviews complaining about each topic. This is exactly the number the dashboard shows.

LLM predictions are cached in `eval/predictions/`, so the numbers are reproducible without spending tokens.

### Results (gold set: 114 real reviews, hand-labelled, 2026-09-28)

The gold set holds **real reviews only** (no synthetic data), stratified by property × score band × language. It covers Paddington (40), Potts Point (50) and Central Sydney (24); Darling Harbour had not been collected yet when the set was built. Of the 114 reviews, 74 are English or unlabelled-language and 40 are non-English (fr, es, de, it, pt, zh, ja, ru, sv). There are 480 gold (topic, polarity) mentions.

| method | micro P | micro R | **micro F1** | macro F1 | topic-only F1 | sentiment acc | insight err (pp) |
|---|---|---|---|---|---|---|---|
| rules | 0.85 | 0.56 | 0.67 | 0.65 | 0.69 | 0.95 | 12.4 |
| **llm: openai/gpt-oss-120b** | **0.93** | **0.75** | **0.83** | **0.83** | **0.85** | **0.96** | **5.6** |
| llm: openai/gpt-oss-20b | 0.88 | 0.64 | 0.74 | 0.74 | 0.77 | 0.89 | 6.4 |
| llm: qwen/qwen3.8-27b | 0.86 | 0.61 | 0.71* | 0.68 | 0.73 | 0.95 | 9.6 |

\* qwen was throttled with 429s: only 30 of the 114 reviews got LLM output and the rest fell back to rules, so its number is not comparable. `llama-3.3-70b-versatile` and `llama-3.1-8b-instant` return **404 (not available) on this Groq account**, so they could not be measured.

By language (micro F1):

| subset | rules | gpt-oss-120b | gpt-oss-20b |
|---|---|---|---|
| English (n = 74) | 0.85† | 0.81 | 0.74 |
| non-English (n = 40) | 0.10 | **0.86** | 0.75 |

† **Optimistic.** The lexicon was tuned against the English half of the first 90 gold reviews, which lifted micro F1 from 0.84 to 0.85. The honest reading is that rules are roughly on par with the LLM on English text, at zero cost, but useless on the ~35% of reviews that are not in English.

Per-topic F1 (rules → gpt-oss-120b): cleanliness 0.73 → 0.90, check_in 0.69 → 0.83, staff 0.64 → 0.87, noise 0.65 → 0.80, facilities 0.68 → 0.73, location 0.77 → 0.92, room_condition 0.55 → 0.68, value_for_money 0.56 → 0.67, bathroom 0.78 → 0.93, bed_comfort 0.64 → 0.88, breakfast_food 0.56 → 0.73. wifi has only 1 gold mention and is too rare to measure.

**Recommendation: `GROQ_MODEL=openai/gpt-oss-120b`** (the default). It has the best F1 overall and per topic, the best sentiment accuracy and the lowest insight error. It takes ~350 tokens per review and ~27 s per 10-review batch when throttled by the free tier's 8K TPM.

Reading the numbers:
- Precision is high for every method (0.85–0.93). When a topic is tagged, it is almost always right, which is what the "x% of negative reviews mention y" statements need.
- Recall is the weak side. Long reviews mention many topics and the classifiers tag only the main ones.
- room_condition and value_for_money are the hardest topics, because they overlap with facilities and cleanliness and are often implicit ("not as in the pictures", "you get what you pay for").
- The gold labels are one annotator's judgement, with no inter-annotator agreement measured. Borderline calls (for example "the room itself looked clean" also counting as room_condition) move the numbers by a few points.

## Cost and rate limits (Groq free tier)

Measured on the gold set with gpt-oss-120b: **~350 tokens per review** (about 1.3K prompt + 2.1K completion per 10-review request, including low-effort reasoning).

On this account the Groq free tier gives each of these models **8,000 tokens/minute and 1,000 requests/day**. The per-minute limit appears to be shared across models: running models back to back produced 429s. The client paces itself from the `x-ratelimit-*` headers.

| scenario | reviews to the LLM | tokens | time at 8K TPM | fits free tier? |
|---|---|---|---|---|
| everything (≈ 9,300 reviews) | ~4,500 with text | ~1.6M | ~3.3 h, ~450 requests | too slow/heavy for one run; hence the window |
| **initial backfill, 180-day window** (default) | ~200–400 with text | 70–140K | 10–20 min | yes (capped at 400/run) |
| **daily cron** (00:00 Sydney) | ~5–20 new | 2–7K | < 1 min, 1–2 requests | yes, essentially free |
| gold-set eval, per model | 114 | ~40K | ~5.5 min | yes (cached afterwards) |

Older reviews use rules (0 tokens). `--upgrade-rules` can move more of them to the LLM later, within `ANALYSIS_LLM_MAX_REVIEWS_PER_RUN`. A paid Groq tier, or running the upgrade over several days, would allow LLM coverage of the full history. At Groq's list price for gpt-oss-120b (roughly $0.15 per 1M input tokens and $0.60 per 1M output tokens), a full re-analysis of all 9,300 reviews would cost about $1.

## Limitations
- **Sarcasm and irony** ("great, another night of snoring") fool the rules method, which reads "great" as praise. The LLM usually gets it right.
- **Mixed reviews.** Overall sentiment is one label per review. A 7.5 with praise and complaints is "neutral", even when one complaint was serious.
- **Short texts** ("Location", "Price") are tagged with the field's polarity but carry little information. Many Booking reviews have no text at all: those get sentiment from the score and no topics.
- **Keyword overlap.** "room" vs room_condition, "bed" vs bed_comfort, cleanliness *of* the bathroom (tagged as both, on purpose), and "couldn't sleep" (noise? bed?). The rules prefer precision: generic words need an anchor, and ambiguous phrases were removed. Some recall is lost as a result.
- **Lexicon coverage.** The rules only know the words in `topics.yaml`. New slang or unusual phrasing is missed, and non-English reviews get no topics from rules.
- **LLM non-determinism.** Even at temperature 0, outputs can vary slightly between runs and model versions. The cache (`content_hash`) freezes each review's analysis, so the dashboard doesn't flicker. `method` records which model produced each row.
- **Small weekly samples.** One property often gets only a handful of reviews a week. "50% of negative reviews mention noise" might mean 1 of 2. The API reports `sample_size` and softens statements with n < 5. Compare weeks with caution, and prefer 4-week or monthly views for trends.
- **Rating ≠ text.** Booking's score often disagrees with the text, for example 9/10 with a long complaint. Sentiment follows the score unless the text is clearly stronger.
