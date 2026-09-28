# Azzurro Review Insights: frontend

The operations dashboard for Booking.com guest reviews across the four Azzurro Hotels properties in Sydney. It is a static React app that reads the backend's read-only JSON API (`backend/docs/CONTRACT.md`).

Built with Vite 5, React 18 and TypeScript (strict), plus Tailwind CSS 3, TanStack Query 5, React Router 6, Recharts and lucide-react. It runs on **Node 18.12+**.

## Pages

| Page | What it answers |
|---|---|
| **Overview** (`/`) | How did guests rate us this period, compared with the period before? The page has KPI cards (guest score, reviews, % positive, % negative), a "What needs attention" panel of prioritised insights, a card per property (click one to focus on it), a weekly/monthly trend, and the top complaints and top praise. |
| **Reviews** (`/reviews`) | What exactly did guests say? A feed of reviews showing the score band, tone, liked/disliked text, topic tags and any hotel response. You can filter by tone, topic, score range and text search, and sort the feed. It uses "Load more" and has an **Export CSV** button that uses the current filters. |
| **Topics** (`/topics`) | Which operational issues keep coming up? A table of complaints and praise by topic (it shows as cards on mobile), plus a chart of selected topics over time. |
| **Data health** (`/data-health`) | Can I trust the numbers? It shows recent collection runs with their status, trigger and watermark, and explains how the data is collected. |

**Shared filters.** Property and date filters (This week, Last week, Last 7/30/90 days, Custom) are stored in the URL, so any view can be shared as a link. Filters read from the URL are validated, and invalid values are ignored. "This week" and the other presets use the backend's Sydney date (`/api/meta`), not the browser clock.

**Plain language.** The dashboard says "Guest score" (not `avg_score`) and "Complaints / Praise" (not polarity). Every metric has a "What does this mean?" popover. A **Low sample** badge appears when a number rests on fewer than 5 reviews. The sidebar shows "Data last updated …", and a warning banner appears when the last successful update is more than 36 hours old or the last run failed or was partial.

**Accessibility and responsiveness.** The layout is mobile first. The sidebar becomes a top bar with a drawer, and tables become cards. There are visible focus rings and a skip link. Every icon button has an aria-label. Up/down changes always show an arrow and words as well as colour. Each chart has a "View as table" option. Every data view has a skeleton loading state, an empty state and an error state with a retry button.

## Setup

```bash
cd frontend
npm install
cp .env.example .env.local      # optional; default API is http://localhost:8000
npm run dev                      # http://localhost:5173
```

Run the backend alongside it (see `backend/`):

```bash
cd backend
python -m uvicorn app.main:app --port 8000 --env-file .env
```

The backend's `CORS_ORIGINS` must include `http://localhost:5173`, which is its default.

| Script | Purpose |
|---|---|
| `npm run dev` | Dev server with hot reload |
| `npm run build` | CSP check, type-check and production build to `dist/` |
| `npm run preview` | Serve the production build locally |
| `npm run lint` | ESLint (zero warnings allowed) |

### Environment

| Variable | Default | Notes |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend origin, with no trailing slash. |

Anything prefixed `VITE_` is bundled into public JavaScript, so **never put secrets in it**. The frontend needs no secrets.

## Deploy to Vercel

1. Import the repository in Vercel and set **Root Directory = `frontend`**. The framework preset is Vite, and the build and output settings come from `vercel.json`.
2. Set the environment variable `VITE_API_BASE_URL` to the backend's URL, e.g. `https://azzurro-reviews-api.vercel.app`.
3. Add the frontend's URL to the backend's `CORS_ORIGINS`.
4. Deploy. `vercel.json` rewrites every path to `index.html` so client-side routes work, and it sets the security headers.

### Content Security Policy

`vercel.json` sends a strict CSP (`default-src 'self'`, with Google Fonts allowed for styles and fonts only) along with `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` and HSTS.

`vercel.json` cannot read environment variables, so **the API origin is written literally in `connect-src`**. If your backend URL is different, edit this part of the `Content-Security-Policy` value:

```
connect-src 'self' https://azzurro-reviews-api.vercel.app
```

Replace the URL with your backend's origin (scheme and host only, no path). `npm run build` runs `scripts/check-csp.mjs`, which **fails the build** when `VITE_API_BASE_URL` points to an origin that `connect-src` does not list. A mismatch therefore shows up at deploy time rather than as a blank dashboard.

## Code structure

```
src/
  api/          typed client (timeouts, typed ApiError) + types mirroring CONTRACT.md
  hooks/        react-query hooks, URL-backed global filters, debounce, dismiss
  lib/          config, date presets, formatting, labels, URL param validation
  theme/        colour tokens shared by Tailwind and the charts
  components/
    ui/         primitives: Card, Button, Badge, Popover, InfoTip, Skeleton, States, SegmentedControl
    common/     domain bits: ScoreBadge, SentimentChip, Delta, LowSampleBadge, TopicChip
    layout/     AppShell (sidebar / mobile drawer), navigation, freshness indicator, page header
    filters/    property multi-select, date range picker, filter bar
    charts/     tooltip, legend and table view shared by charts
    overview/ reviews/ topics/ health/   page-specific components
  pages/        one file per route
```

**Data fetching.** Requests time out after 15 seconds. React Query retries network, timeout and 5xx errors twice with backoff, and never retries 4xx errors. Error messages shown to staff are written in plain language.

**Security.** Review text is always rendered as plain text, never with `dangerouslySetInnerHTML`. External links use `rel="noopener noreferrer"`. All query strings are built with `URLSearchParams`.

## Assumptions and limitations

- The guest score is a **simple average of reviews posted in the period**. It differs from Booking.com's weighted headline score, which is shown separately on each property card for reference.
- "Previous period" means the same number of days directly before the selected range, as defined by the backend. Early in the week, "This week" covers only a day or two, so the Overview suggests switching to "Last week" or "Last 7 days".
- The trend charts always show at least 12 weeks (or 12 months) ending on the selected end date, so that a trend is visible even when the selected range is short.
