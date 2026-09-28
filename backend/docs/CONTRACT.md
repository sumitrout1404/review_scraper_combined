# Shared Build Contract

This document is the agreement between the collector, the analysis step, the backend and the frontend, so each can be built in parallel. If you need to change it, keep the change backwards compatible and note it at the bottom under "Changes".

## Repository layout (v3 – ONLY `backend/` and `frontend/` at the root)

```
/
├── backend/                        # everything Python – ONE Vercel project (root = backend)
│   ├── app/                        # OWNER backend agent – FastAPI (public read API + protected cron endpoint)
│   ├── collector/                  # OWNER collector agent – scraper package: `python -m collector ...`
│   ├── analysis/                   # OWNER analysis agent – topics.yaml, rules + Groq: `python -m analysis ...`
│   ├── core/                       # OWNER lead – dependency-free: circuit_breaker, retry, locking (file lock, local only), logging (redaction)
│   ├── db/                         # OWNER lead – MongoDB: client.py, collections.py (THE data model + indexes), locks.py (DB lease)
│   ├── docs/CONTRACT.md            # this file (lead)
│   ├── data/reviews.db             # TEMPORARY – old SQLite backfill, imported into Mongo once and then deleted
│   ├── data/samples/               # JSON/CSV exports (collector)
│   ├── tests/{api,collector,analysis,core,db}/   # each owner writes only its own subfolder
│   ├── api/index.py                # Vercel entrypoint exporting `app` (backend agent)
│   ├── vercel.json, .vercelignore  # backend agent (crons + functions config)
│   ├── pyproject.toml              # backend agent – pytest (testpaths=tests, pythonpath=.) + ruff
│   ├── requirements.txt            # EVERYTHING the deployed function needs: API + DB + HTTP collector + analysis (backend agent owns; collector/analysis agents may append pinned lines)
│   ├── requirements-collector.txt  # local-only extras: `-r requirements.txt` + playwright (collector agent)
│   ├── requirements-dev.txt        # pytest, ruff… (backend agent)
│   ├── .env / .env.example         # secrets in backend/.env (gitignored)
│   └── README.md
├── frontend/                       # OWNER frontend agent – React + Vite + TS (second Vercel project, root = frontend)
└── README.md                       # lead writes last
```
There is **no GitHub Actions workflow**. Scheduling is done with Vercel Cron.

All Python commands run with **cwd = `backend/`**: `python -m collector run`, `python -m analysis`, `uvicorn app.main:app`, `pytest`.
Imports are absolute top-level packages: `from db import collection`, `from core.circuit_breaker import CircuitBreaker`, `from analysis import run_analysis`.

## Database (v4 – MongoDB Atlas)

- **Data model:** the single source is `backend/db/collections.py`. Its docstring gives the exact document shapes; read it.
  - **Analysis and topics are embedded in each review document.** They sit under `review.analysis` (a subdocument, absent until analysed) and `review.topics` (a list, `[]` until analysed). That makes every review update one atomic single-document write, so no transactions are needed.
  - The **collections** are `properties`, `reviews`, `topics`, `scrape_runs` and `job_locks`.
- **Naming:** every collection is **prefixed `scraper_`** (e.g. `scraper_reviews`) in the database `scraper`, because the Atlas cluster is shared with another app. Always go through `db.collection("reviews")` and never hardcode names. The prefix is `MONGODB_COLLECTION_PREFIX` and the database is `MONGODB_DB`.
- **Access helpers:**
  - `db.collection(name, read_only=False)` and `db.get_database(read_only=False)` return a cached, process-wide `MongoClient`, which serverless needs.
  - `read_only=True` uses `MONGODB_URI_READONLY` when set, for least privilege. The public API **must** pass `read_only=True` and must only ever read.
- **Indexes:** `db.ensure_indexes()` is idempotent. The collector and analysis call it at the start of a run; the API never does.
- **Lease lock:** `db.db_lease(name, ttl_s)` is a cross-instance lease stored in `job_locks`, and raises `LeaseHeldError`. Note that it takes **no engine argument**.
- **Idempotent writes:**
  - Upsert reviews with `update_one({"_id": id}, {"$set": {...}, "$setOnInsert": {"first_seen_at": now}}, upsert=True)`, or `bulk_write([UpdateOne(...)])` per page.
  - Analysis writes `$set: {"analysis": {...}, "topics": [...]}` in a single update, filtered on `{"_id": id, "content_hash": <hash analysed>}` so a concurrent edit isn't overwritten.
- **Queries:**
  - Use filters and aggregation pipelines (`$match`, `$group`, `$unwind`, `$facet`). Do week/month bucketing in Python on per-day aggregates.
  - Text search is a case-insensitive `$regex` built from `re.escape(q)` (q ≤ 200 chars). **Never** pass raw user input as an operator or regex.
  - Reject any user-supplied key that starts with `$` or contains `.`.
- **Tests** use `MONGODB_URI=mongomock://localhost` (in-memory, from `requirements-dev.txt`), with `db.reset_clients()` between tests. See `tests/db/test_db_layer.py`.
- **Sample data:** `backend/data/samples/reviews.json` and `.csv` are the deliverable (the collector's `export`). `python -m collector import --from data/samples/reviews.json` seeds a fresh database idempotently. The old SQLite `data/reviews.db` holds 4,472 already-collected real reviews; the collector imports it once with `import --from data/reviews.db`, after which the file is deleted.
- **No SQL anywhere any more.** SQLAlchemy, sqlite3 and psycopg are removed from runtime code and requirements.

## Deployment & scheduling (Vercel only)

- **Backend Vercel project** (root = `backend`): a single Python function `api/index.py` serving FastAPI, with `maxDuration: 300`.
- **Vercel Cron** is set in `backend/vercel.json`: `{"crons":[{"path":"/api/cron/collect","schedule":"0 14 * * *"}]}`. That's once nightly at 00:00 Sydney (AEST), or 01:00 during AEDT, because Vercel cron runs in UTC.
- **`GET /api/cron/collect`** (backend agent writes the router; it calls the collector and analysis):
  1. **Auth.** Require `Authorization: Bearer <CRON_SECRET>`, compared in constant time. Vercel sends this header automatically when the `CRON_SECRET` env var is set. Return 401 otherwise, or 503 if `CRON_SECRET` is unset. Responses use `Cache-Control: no-store`.
  2. **Lease.** Take `db_lease("collect", ttl_s=900)`. If it's already held, return 200 with `{status:"skipped"}`.
  3. **Collect.** Call `collector.run_collection(mode="incremental", trigger="cron", time_budget_s=200)`.
  4. **Analyse.** Call `analysis.run_analysis(method="auto", time_budget_s=<remaining, ~60>)`.
  5. **Respond.** Return JSON: `{ run_id, status, properties:[{property_id,status,watermark_date,reviews_new,reviews_updated,pages_fetched}], analysis:{analysed, pending} }`.
- **Watermark-based incremental collection** (collector agent):
  - For each property, `watermark = MAX(review_date)` already stored. Fetch newest first, and stop paging once a page has a review with `review_date < watermark − 1 day`, or once a whole page is already known. Booking dates are day-granular, hence the one-day overlap; id-based upsert handles the duplicates.
  - With no watermark (an empty DB), go back up to `COLLECTOR_BACKFILL_MAX_PAGES` pages.
  - Honour the time budget. Stop cleanly between pages and mark the property `partial`; the next run resumes from the watermark.
  - Only the **HTTP strategy** runs on Vercel. Playwright is an optional local fallback, loaded only if it's installed.
- **Analysis** processes only reviews that are new or changed (by content_hash), oldest first, within the time budget. Leftovers are picked up on the next run.
- **Initial backfill / fallback.** Run `python -m collector run --full` locally; it writes to the same Atlas database, and Playwright can be used locally if Booking blocks plain HTTP. `python -m collector import --from <sqlite|json>` loads existing data with idempotent upserts.
- **Backend env vars on Vercel:** `MONGODB_URI`, `MONGODB_DB=scraper`, `MONGODB_COLLECTION_PREFIX=scraper_`, optional `MONGODB_URI_READONLY`, `CRON_SECRET`, `GROQ_API_KEY`, `GROQ_MODEL`, `CORS_ORIGINS` and `ENV=production`. Atlas Network Access must allow Vercel's egress (0.0.0.0/0, or the Vercel integration).
- **Frontend Vercel project** (root = `frontend`): a static Vite build with `VITE_API_BASE_URL` pointing at the backend.

## Engineering standards (all workstreams)

**Readability**
- Small modules with a single responsibility, type hints everywhere, docstrings on public functions, and no dead code.
- Config comes from env through one typed settings module per package. Use no magic constants inline.
- Use the `logging` module (never `print` in library code) and structured, concise messages.

**Circuit breaker** (`core/circuit_breaker.py`, shared)
- Three states: CLOSED → OPEN after N consecutive failures → HALF_OPEN after the cooldown, which allows one trial call.
- Thread-safe, with an injectable clock for tests, and it raises `CircuitOpenError`.
- Collector: one breaker per fetch strategy per host. If Booking starts blocking or challenging, stop hammering it, fall through to the next strategy, and mark the run degraded.
- Analysis: one breaker around the Groq client. When open, fall back to rules immediately.
- Retries (`core/retry.py`) use exponential backoff with jitter, honour `Retry-After`, and retry only errors that are retryable (timeouts, 429, 5xx, never 4xx validation errors).

**Idempotency**
- Collector writes are upserts keyed by review id, with `content_hash` change detection, and each property's page batch runs in a single transaction. Re-running the same scrape leaves the DB unchanged apart from `last_seen_at`.
- The DB lease (`db.db_lease`) ensures only one collection runs at a time across cron invocations and CLI runs. An expired lease is taken over automatically.
- Analysis is keyed by `(review_id, content_hash)`, so a rerun skips reviews it has already analysed. Topic rows are replaced atomically inside one transaction.
- Public API endpoints are safe, idempotent GETs using the read-only Mongo client. The cron endpoint is idempotent: it runs under the lease and uses upserts, so a double trigger is harmless.

**Security**
- No secrets in code, logs, fixtures, tests or git. The logging filter redacts anything that looks like a key or token (`gsk_…`, `Bearer …`).
- No cookies or session data are saved to disk, and raw debug captures are gitignored.
- SQL is always parameterised. `LIKE` searches escape `%`/`_`. Every input is validated (dates, enumerations, id allowlist, page size ≤ 100, and a length cap on `q`).
- API:
  - Strict CORS allowlist from env.
  - Security headers middleware: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, and a restrictive CSP. HSTS in production.
  - `GET` only (other methods → 405). `/api/cron/*` requires the bearer `CRON_SECRET`, is excluded from caching, and is the only path that writes.
  - A generic 500 handler that never leaks stack traces.
  - OpenAPI docs disabled when `ENV=production`.
  - A simple per-IP rate limit.
  - Request size limits.
- CSV export neutralises formula injection by prefixing `'` to cells that start with `= + - @ 	 
`.
- Frontend:
  - Never uses `dangerouslySetInnerHTML`, and all review text is rendered as text.
  - External links use `rel="noopener noreferrer"`.
  - `vercel.json` sets security headers and a CSP whose `connect-src` is limited to the API origin.
  - No secrets in `VITE_*` variables.
- Dependencies are pinned in the requirements files and the lockfile.
- The collector only touches public pages, has polite rate limits, uses no login, and stores no reviewer names.

## Domain conventions

- **Timezone:** `Australia/Sydney`. A "week" runs Monday–Sunday. `review_date` is a date without a time.
- **Score:** Booking's 1–10 score.
- **Sentiment:** comes from the LLM when available. The rules fallback uses the score: `>= 8` positive, `>= 6 and < 8` neutral, `< 6` negative, adjusted by the text.
- **Topic polarity:** a topic found in `negative_text` is a *complaint* (negative). One found in `positive_text` is *praise* (positive). The same review can have both for one topic.
- **Topic keys** (fixed, the frontend may rely on them):
  `cleanliness, check_in, staff, noise, facilities, location, room_condition, value_for_money, bathroom, bed_comfort, wifi, breakfast_food`.
  Labels come from the `topics` table / `GET /api/topics`.
- **Properties** (ids fixed):

| id | name | short_name | booking_pagename |
|---|---|---|---|
| `olympic-paddington` | Olympic Hotel Paddington | Paddington | `olympic-paddington` |
| `potts-point` | Azzurro Potts Point | Potts Point | `venus-potts-point-sydney` |
| `central-sydney` | Azzurro Central Sydney | Central Sydney | `venus-surry-hills` |
| `darling-harbour` | Azzurro Darling Harbour | Darling Harbour | `chateau-de-venus` |

## REST API (backend → frontend)

Base path is `/api`, and everything is JSON unless noted.

**Common query parameters** (all optional):
- `properties`: comma-separated property ids. Default is all.
- `date_from`, `date_to`: inclusive dates, `YYYY-MM-DD`.

Errors return `{ "detail": string }` with a 4xx/5xx status. Numbers are rounded to 2 decimal places. `avg_score` is `null` when count is 0.

`PeriodStats` = `{ count, avg_score, positive, neutral, negative, pct_positive, pct_negative }` (percentages are 0–100).

| Endpoint | Returns |
|---|---|
| `GET /api/health` | `{ status: "ok", db: { reviews: int, last_scraped_at: str\|null } }` |
| `GET /api/meta` | `{ today: date (Sydney), this_week_start: date, min_review_date, max_review_date, last_scraped_at, last_run_status, total_reviews }` |
| `GET /api/properties` | `[{ id, name, short_name, booking_url, booking_score, total_reviews, avg_score }]` |
| `GET /api/topics` | `[{ key, label, description }]` ordered by sort_order |
| `GET /api/summary?date_from&date_to&properties` | Current window versus the **previous window of the same length directly before it**. Returns `{ current: {date_from,date_to, ...PeriodStats}, previous: {date_from,date_to, ...PeriodStats}, delta_avg_score: number\|null, delta_count: int, by_property: [{ property_id, name, short_name, current: PeriodStats, previous: PeriodStats, delta_avg_score, top_complaint: {topic,label,count}\|null }] }`. If the dates are omitted, it defaults to the current Sydney week (Monday → today). |
| `GET /api/trends?granularity=week\|month&date_from&date_to&properties` | `{ granularity, series: [{ period_start, ...PeriodStats }], by_property: [{ property_id, short_name, series: [{period_start, count, avg_score}] }] }`. Empty periods inside the range are included with count 0. |
| `GET /api/topics/breakdown?date_from&date_to&properties` | `{ total_reviews, negative_reviews, items: [{ topic, label, negative_mentions, positive_mentions, pct_of_negative_reviews, pct_of_reviews, net: positive-negative }] }` sorted by negative_mentions descending. `pct_of_negative_reviews` = negative reviews with a complaint on this topic ÷ negative reviews. |
| `GET /api/topics/trends?granularity&date_from&date_to&properties&polarity=negative` | `{ series: [{ period_start, topic, mentions }] }` |
| `GET /api/insights?date_from&date_to&properties` | Plain-English, data-driven statements: `[{ id, severity: "alert"\|"warning"\|"info"\|"positive", title, text, property_id\|null, topic\|null, sample_size }]`. Example: *"40% of negative reviews this week mentioned cleanliness (4 of 10)."* Statements with low samples (n < 5) are softened or dropped. |
| `GET /api/reviews?...&sentiment=positive,neutral,negative&topic=cleanliness&polarity=negative&min_score&max_score&q=text&sort=date_desc\|date_asc\|score_asc\|score_desc&page=1&page_size=20` | `{ items: [Review], total, page, page_size }` |
| `GET /api/reviews/export.csv?(same filters)` | `text/csv` download |
| `GET /api/scrape-runs?limit=20` | `[{ run_id, property_id, started_at, finished_at, status, method, mode, pages_fetched, reviews_seen, reviews_new, reviews_updated, reviews_rejected, error }]` |

`Review` = `{ id, property_id, property_name, property_short_name, score, title, positive_text, negative_text, language, review_date, stay_month, nights, room_type, traveller_type, reviewer_country, hotel_response, sentiment, sentiment_score, summary, analysis_method, topics: [{ topic, label, polarity, evidence }] }`

CORS: set by env `CORS_ORIGINS` (comma-separated). The default allows `http://localhost:5173`.

## Local ports

- Backend: `uvicorn app.main:app --reload --port 8000`, run from `backend/`.
- Frontend: `npm run dev` on port 5173, with `VITE_API_BASE_URL=http://localhost:8000`.

## Visual theme (derived from azzurrohotels.com, made more businesslike)

| Token | Hex | Use |
|---|---|---|
| navy | `#0f2a4d` | primary, header/sidebar, headings |
| navy-700 | `#1a3a63` | hover |
| ink | `#1d2a3f` | body text |
| cream | `#f5efe0` | subtle panels, highlights |
| offwhite | `#faf8f4` | app background |
| sand | `#e8dcc4` | borders, dividers |
| bronze | `#a8855e` | secondary accent, small highlights |
| coral | `#ff4d6d` | brand accent – use sparingly (CTAs, focus) |
| positive | `#1f8a5b` | good / up |
| negative | `#c8374b` | bad / down |
| neutral | `#8a8f98` | neutral |

Fonts (Google Fonts): **Fraunces** for display headings and big KPI numbers; **Poppins** for UI and body text. Use generous whitespace, 12–16px radii, soft navy-tinted shadows (`rgba(15,42,77,0.08)`), and cards on the off-white background.

## Changes
- v2 (2026-09-28): repo restructured to only `backend/` + `frontend/`. collector/analysis/db/docs/data moved under `backend/`; added `core/` shared helpers; added Engineering standards (circuit breaker, idempotency, security).
- v3 (2026-09-28): scheduling moved to **Vercel Cron** → `GET /api/cron/collect` with watermark-based incremental scraping; the GitHub workflow was dropped; Postgres (Neon) in production, SQLite locally; schema moved to `db/tables.py` (SQLAlchemy Core); added the DB lease lock.
- v4 (2026-09-28): **MongoDB Atlas replaces Postgres/SQLite** (the user can't use Postgres). The shared `db/` package was rewritten on pymongo, analysis and topics are embedded in review documents, collections are prefixed `scraper_` in the database `scraper`, the cron runs at 00:00 Sydney (`0 14 * * *`), and `run_collection`/`run_analysis`/`db_lease` no longer take an engine.
