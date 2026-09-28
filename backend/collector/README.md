# Review collector

Collects public Booking.com guest reviews for the four Azzurro properties into MongoDB
(`scraper_*` collections, see `db/collections.py`). All commands run with **cwd = `backend/`**.

```bash
pip install -r requirements.txt            # enough for the HTTP strategy (what the Vercel cron runs)
pip install -r requirements-collector.txt  # optional: Playwright browser fallbacks + headline-score probe
python -m playwright install chromium      # only if you installed the line above

python -m collector run                    # incremental (default), then analysis
python -m collector run --full --no-analyse
python -m collector run --property potts-point --max-pages 2 --http-only --time-budget 120
python -m collector status                 # counts, date ranges, Booking score, recent runs
python -m collector export                 # data/samples/reviews.json + reviews.csv
python -m collector import --from data/samples/reviews.json   # seed an empty DB (idempotent)
pytest tests/collector                     # uses mongomock, so no network or DB needed
```

`MONGODB_URI` (and optionally `MONGODB_DB` / `MONGODB_COLLECTION_PREFIX`) come from `backend/.env`.
Programmatic entrypoint (used by `GET /api/cron/collect`, which wraps it in `db_lease("collect")`):

```python
from collector import run_collection
report = run_collection(mode="incremental", trigger="cron", time_budget_s=200)
report.to_dict()
```

## How it gets the data (and why)

I spiked the options on 2026-09-28, cheapest first:

| Approach | Result |
|---|---|
| `reviewlist.html?pagename=…` via httpx | **404.** The legacy review-list endpoint has been retired. |
| Hotel page via httpx / curl_cffi (Chrome TLS impersonation) | **HTTP 202 AWS WAF JS challenge** (`challenge.js`, `awsWafCookieDomainList`). |
| Hotel page in headless Chromium (Playwright) | The challenge resolves in about 3–8 s. The reviews panel then loads data from `POST /dml/graphql`, operation **`ReviewList`**. |
| That `ReviewList` GraphQL query via **plain httpx, with no cookies or session** | **Works.** It returns JSON with a stable review id, epoch date, score, texts, language, stay details and hotel reply. |

So there's a three-step **strategy chain**, tried in order for every page:

1. **`http_graphql`** (primary; also the only one on Vercel). A plain HTTPS POST of the `ReviewList`
   query, 25 reviews per page (Booking caps `limit` at 25), sorted `NEWEST_FIRST`.
   - It needs Booking's numeric `hotelId` and the Sydney `ufi` (-1603135). These live in
     `collector/properties.py`, and I verified them against `b_hotel_id` on each hotel page.
   - No cookies, CSRF or session tokens are sent or needed. The only headers are a normal browser
     User-Agent, `origin`, `referer`, and the static client-name headers the site's own JS sends
     (`apollographql-client-name`, `x-booking-topic`, …). None of them are session-derived.
2. **`browser_graphql`**. Playwright loads the hotel page, lets the WAF challenge resolve, re-discovers
   `hotelId`/`ufi` from the page, and runs the same query with `fetch()` *inside* the page, so the
   request carries the browser's WAF token and TLS fingerprint.
3. **`browser_dom`** (last resort). It opens the reviews panel, selects "Newest first", clicks
   through pages, and parses the review cards by their `data-testid` attributes.
   - It's lower fidelity: no Booking id (ids fall back to `h_<sha1>`), no language, and truncated
     hotel replies.
   - The DOM shows a score word ("Good") as the heading when a guest left no title, so those are nulled.

When the browser is available, it also captures **Booking's headline score**, which only exists on
the WAF-protected HTML page. The total review count comes from GraphQL's `reviewsCount`.

The GraphQL document lives in **one module**, `collector/booking/queries.py`. It is
*data-minimised*: reviewer names, avatars and photos are never requested or stored.

## Fields and normalisation

| Field | Source / rule |
|---|---|
| `_id`, `source_review_id` | Booking's review token (`reviewUrl`, e.g. `035ee4ae91790134`). Fallback id `h_` + sha1 of the content. |
| `review_date` | `reviewedDate` is a **UTC epoch**, converted to the **Australia/Sydney calendar date** (this matches "Reviewed: 24 September 2026" on the site). DOM text dates are parsed in many formats (`12 September 2026`, `Sept 3, 2026`, `1st March 2025`, ISO). |
| `score` | float, 1–10 |
| `title`, `positive_text`, `negative_text`, `hotel_response` | NFC, trimmed, whitespace collapsed, blank → null. Booking placeholders ("There are no comments available for this review") → null. |
| `language` | ISO 639-1. Booking's pseudo codes are mapped (`xt` → `zh`, `xu` → null). |
| `stay_month`, `nights`, `room_type`, `traveller_type`, `reviewer_country`, `helpful_votes` | from `bookingDetails` / `guestDetails` |
| `content_hash` | sha1 of (property, date, score, title, liked, disliked), whitespace-normalised |

Every record passes a strict pydantic model (`collector/models.py`). It checks ranges, the id
pattern, the date isn't in the future or before 2005, and the stay isn't after the review. Rejected
records are counted.

## Dedup, upserts and incremental logic

- **Upserts.** Each page is one `bulk_write` of `UpdateOne(..., upsert=True)`, with `$set` for the
  content and `$setOnInsert` for `first_seen_at`/`topics`. The embedded `analysis`/`topics` are never
  touched, and the analysis step re-analyses when `content_hash` changes.
- **new / updated / unchanged.** The store compares the stored fields with the new ones.
  - An unchanged review only gets its `last_seen_at` bumped, so re-running a scrape is idempotent.
  - A hash-only (DOM) copy of a review already held with its Booking id is never duplicated or allowed
    to overwrite richer data.
  - A hash-keyed review is re-keyed once its Booking id becomes known.
- **Incremental (default), by watermark.** The watermark is the newest stored `review_date` per property.
  - Pages are fetched newest first. Paging stops at the first page that is **fully known**, or at the
    first page containing a review **older than watermark − 1 day** (Booking dates are
    day-granular, hence the overlap).
  - With no watermark it backfills up to `COLLECTOR_BACKFILL_MAX_PAGES` (default 200).
- **Backfill resume.** If a backfill was cut short (time budget, crash), the stored count stays below
  Booking's `reviewsCount`. The next incremental run then jumps to `offset ≈ stored − 25` and continues
  from there. This is how Central Sydney's interrupted backfill completed (1950 → 2492).
- **Full mode** (`--full`) pages through everything, up to 1000 pages. `--max-pages` caps any mode.
- **Time budget** (`time_budget_s`, `--time-budget`). The budget is checked between pages, with one
  average page duration of headroom. When it runs out, the run stops cleanly and the property is
  marked `partial`.

## Reliability measures

- **Politeness.** One shared throttle across all strategies: sequential requests with 1.5–3.0 s
  jittered gaps.
- **Retries** (`core.retry`). Exponential backoff with jitter, honouring `Retry-After`, only for
  timeouts, connection errors, 429 and 5xx. Never retried on 4xx or on challenges.
- **Explicit challenge/block detection.** HTTP 202/405 with AWS WAF markers, 403, or small block pages
  raise `BlockedError`.
- **Circuit breaker per strategy** (`core.circuit_breaker`, 3 consecutive failures, 5 min cooldown).
  When one strategy is blocked the chain stops hammering it and falls through to the next.
- **Page-change detection.**
  - GraphQL is strongly typed: renamed or removed fields come back as explicit GraphQL errors, and
    `unwrap_review_list` raises `ResponseShapeError`.
  - A first page that parses to 0 reviews is treated as a page change.
  - A page with more than 20 % rejects is not written (`PageQualityError`).
  - Each of these falls through to the next strategy. If all strategies fail that way, or every
    breaker is open, the property is marked **`degraded`** and nothing is written, so good data is
    never overwritten with junk.
- **Per-property isolation.** An exception in one property is recorded, and the others still run.
- **Audit trail.** Each property of each run is one `scrape_runs` document with a shared `run_id`,
  recording status (`success|partial|degraded|failed`), `method`, `mode`, `trigger`,
  `watermark_date`, counts and errors. Stale `running` documents from a crashed run are marked
  `failed` at the next start.
- **Concurrency.** The CLI and the cron both run under the `db_lease("collect")` lease.
- **Debugging.** `COLLECTOR_SAVE_RAW=1` saves raw response bodies (never headers or cookies) to the
  gitignored `backend/.cache/collector/`.

Tunables (env): `COLLECTOR_REQUEST_DELAY_S`, `COLLECTOR_REQUEST_JITTER_S`, `COLLECTOR_RETRY_ATTEMPTS`,
`COLLECTOR_BREAKER_THRESHOLD`, `COLLECTOR_BACKFILL_MAX_PAGES`, `COLLECTOR_MAX_REJECT_RATIO`,
`COLLECTOR_STRATEGIES` (e.g. `http_graphql`), `COLLECTOR_HEADLESS`, `COLLECTOR_PROBE_HEADLINE_SCORE`,
`COLLECTOR_SAVE_RAW`. See `collector/settings.py`.

## Limitations

- **Terms of service.** Booking.com's terms restrict automated access. This collector reads only
  public, logged-out review data at a low request rate, stores no reviewer names, and is meant as an
  internal operations aid. For production use, the proper channel is the property's own data via the
  Booking.com Extranet / Connectivity APIs.
- **Unofficial API.** The `ReviewList` operation and its input shape can change without notice.
  Detection is explicit (above), and fixing it is a single edit in `booking/queries.py`. The DOM
  fallback depends on `data-testid` attributes, which are more stable than CSS classes but can still drift.
- **Bot protection.** Plain HTTP works today. If Booking puts the GraphQL endpoint behind the WAF
  challenge, only the browser strategies work, and those can't run on Vercel. In that case run the
  collector locally or on a machine with Playwright.
- **Coverage.** Booking only exposes reviews from roughly the last 36 months, and only those it
  publishes. The collected counts equal Booking's `reviewsCount` for all four properties, but
  Booking's headline score is its own weighted and recency-adjusted figure, so it won't match a
  simple average of the reviews.
- **Ordering quirks.** Paging is offset-based. A review published mid-run shifts later pages by one,
  but the id-based upsert and the page overlaps absorb that.
- **Language.** Texts are stored in the guest's original language, and the `language` field records it
  (about 20 % aren't English). No translation is done. Some Booking codes are unknown and stored as null.
- **Date granularity.** Booking shows day-level dates. `review_date` is the Sydney-local day of the
  epoch timestamp, and `stay_month` is the check-in month.
- **Edits and deletions.** Edits to recent reviews are caught by incremental runs; edits to old
  reviews only by a periodic `--full` run. Reviews Booking removes stay in the DB, and `last_seen_at`
  shows when each was last observed.
