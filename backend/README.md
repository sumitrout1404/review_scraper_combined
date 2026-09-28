# Backend – Review Insights API

A FastAPI service that reads Booking.com reviews for the four Azzurro Hotels properties from **MongoDB Atlas** and serves the dashboard's REST API (`/api/*`, spec in [`docs/CONTRACT.md`](docs/CONTRACT.md)). The same Vercel function also hosts the protected cron endpoint that runs the collector and the analysis step.

Data is **updated nightly at midnight (Sydney)**.

## Layout (API parts)

```
app/
  main.py        app factory: routers, error handlers, CORS
  config.py      typed settings from env (+ optional backend/.env via python-dotenv)
  security.py    security headers, request id, GET-only, size limits, per-IP rate limit, generic 500
  db.py          read-only Mongo helpers (collection(name, read_only=True)); DB errors -> 503
  deps.py        filter parsing/validation (allowlists, enums, date bounds, rejects $/. values)
  schemas.py     pydantic response models (mirror the contract)
  routers/       meta, properties, summary, trends, topics, insights, reviews, runs, cron
  services/      stats, trends, topic_stats, review_search, csv_export, freshness, catalog, insights, cron_job
api/index.py     Vercel entrypoint (exports `app`)
scripts/seed_dev.py  synthetic data for a *dev* database (refuses MONGODB_DB=scraper)
tests/api/       API tests (mongomock)
```

## Run locally

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate      # Windows (use bin/activate elsewhere)
pip install -r requirements-dev.txt
cp .env.example .env                                   # fill in MONGODB_URI etc. Never commit .env
uvicorn app.main:app --reload --port 8000 --env-file .env
```

`app/config.py` also loads `backend/.env` automatically if python-dotenv is installed. Real environment variables always take precedence. Docs are at http://localhost:8000/docs (disabled when `ENV=production`).

**Synthetic dev data.** To try things without touching the real data, seed a separate database:

```bash
MONGODB_DB=scraper_dev python scripts/seed_dev.py      # ~600 reviews, 6 months, analysis embedded
MONGODB_DB=scraper_dev uvicorn app.main:app --port 8000 --env-file .env
```

The seed script refuses to write to the production database (`scraper`).

## Tests and lint

```bash
pytest                 # whole suite; API tests use MONGODB_URI=mongomock://localhost
ruff check . && ruff format --check app api scripts tests/api
```

## How the numbers are computed

- **Sentiment** comes from `review.analysis.sentiment`. For an unanalysed review it falls back to the score: 8 or more is positive, 6 up to 8 is neutral, and below 6 is negative. This is computed inside the aggregation pipeline.
- **Summary** compares the selected window with the *previous window of the same length directly before it*. Without dates it covers this Sydney week, Monday to today.
- **Trends** are aggregated per day in Mongo and bucketed into Monday-start weeks or calendar months in Python. Empty periods are included with count 0. Without dates the range is the last 26 weeks or 12 months, trimmed to the first review.
- **Topics.** `$unwind` runs over the embedded `topics`. `pct_of_negative_reviews` is negative reviews with a complaint on the topic divided by negative reviews. `pct_of_reviews` is reviews mentioning the topic (either polarity) divided by all reviews.
- **Insights** are deterministic rules: complaint share of negative reviews, complaint spikes or easing versus the previous window (volume-adjusted), overall and per-property score change (including the biggest drop), a rising negative share, the top praise topic, and unanswered low-score reviews (score below 6 with no hotel response).
  - A percentage is quoted only when n ≥ 5. Otherwise the insight is phrased as a count or dropped.
  - Score comparisons need at least 5 reviews in both windows.
  - Insights are ranked alert, then warning, info and positive, then by magnitude.

## Security

- The public API only reads, through `collection(..., read_only=True)`, which uses `MONGODB_URI_READONLY` when it is set. A test fails if any module other than the cron job calls a write method.
- User input only ever becomes a filter *value*:
  - property ids and topics are allowlisted, and enums are checked;
  - dates are parsed and bounded, `q` is capped at 200 characters and passed through `re.escape`;
  - any value starting with `$` or containing `.` is rejected with 422.
- Responses carry `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy` and a `default-src 'none'` CSP, plus HSTS when `ENV=production`. Only GET, HEAD and OPTIONS are allowed; other methods get 405. URL and body sizes are limited.
- Every response has an `X-Request-ID`. Unhandled errors return a generic 500 and are logged with that request id.
- Database errors return a generic 503 that never includes hostnames.
- The rate limit is an in-memory token bucket per IP (`RATE_LIMIT_PER_MINUTE`, default 120), which answers 429 with `Retry-After`. On serverless it is **per instance**, so it is best effort; use Vercel's firewall for hard limits.
- CSV export neutralises formula injection: cells that start with `= + - @ TAB CR` get a leading `'`.
- CORS uses an explicit allowlist (`CORS_ORIGINS`). At startup in production, the app checks that `CRON_SECRET` is at least 32 characters and that `CORS_ORIGINS` is not `*`. `/api/health` reports the result as `config_ok` and never includes values.
- Public GETs are sent with `Cache-Control: public, max-age=300`. Health, cron and error responses use `no-store`.

## Deploy (Vercel)

1. Create a Vercel project with **Root Directory = `backend`**. Python is detected from `api/index.py` and `requirements.txt`.
2. Set these environment variables:

   | Variable | Value |
   |---|---|
   | `MONGODB_URI` | Atlas connection string |
   | `MONGODB_URI_READONLY` | Recommended; a connection string for a read-only Atlas user |
   | `MONGODB_DB` | `scraper` |
   | `CRON_SECRET` | At least 32 random characters |
   | `CORS_ORIGINS` | The frontend's URL |
   | `ENV` | `production` |
   | `GROQ_API_KEY`, `GROQ_MODEL` | For the analysis step |

   In Atlas, allow Vercel's egress (Network Access `0.0.0.0/0`, or Vercel's static IPs).
3. How `vercel.json` sets up the function:
   - It runs one function, `api/index.py`, with `maxDuration: 300`. It bundles `app/`, `collector/`, `analysis/`, `core/` and `db/`, and rewrites every path to it.
   - `.vercelignore` keeps `tests/`, `scripts/`, `docs/`, `data/`, `.env*` and dev requirements out of the bundle.
4. **Cron: updated nightly at midnight (Sydney).**
   - The schedule is `0 14 * * *` in UTC, which is 00:00 AEST. Vercel cron runs on UTC and does not follow daylight saving, so during AEDT (October to April) it runs at 01:00 Sydney time.
   - Vercel calls `GET /api/cron/collect` with `Authorization: Bearer $CRON_SECRET`.
   - The endpoint checks the token in constant time; it returns 401 if the token is wrong and 503 if `CRON_SECRET` is unset.
   - It takes the `collect` DB lease; if another run holds it, it responds `{status:"skipped"}` and logs a `skipped` run.
   - It runs `run_collection(mode="incremental", trigger="cron", time_budget_s=200)`, then `run_analysis(method="auto", time_budget_s=<remaining>)`, and returns a JSON summary.
   - You can trigger it by hand with `curl -H "Authorization: Bearer $CRON_SECRET" https://<backend>/api/cron/collect`.
