/**
 * Build guard, run before `vite build`.
 *
 * Two ways a deployed dashboard silently fails to reach its API, both caught here:
 *   1. the bundle is built pointing at localhost (VITE_API_BASE_URL never set), so
 *      every request from the deployed site goes nowhere;
 *   2. the API origin is not listed in connect-src in vercel.json, so the browser's
 *      Content Security Policy blocks the requests.
 *
 * The value is resolved exactly as Vite resolves it (process.env, then .env.production,
 * then .env), so this check sees what the bundle will actually contain.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { loadEnv } from 'vite';

const root = fileURLToPath(new URL('..', import.meta.url));
const mode = process.env.NODE_ENV === 'development' ? 'development' : 'production';
const raw = loadEnv(mode, root, 'VITE_').VITE_API_BASE_URL?.trim();

// Deploying (Vercel, or any CI) without a real API origin is always a mistake.
const isDeploy = Boolean(process.env.VERCEL || process.env.CI);

if (!raw) {
  if (isDeploy) {
    console.error(
      '[check-csp] VITE_API_BASE_URL is not set, so this build would call http://localhost:8000\n' +
        '            and fail for every visitor. Set it in the Vercel project (Settings ->\n' +
        '            Environment Variables) or in frontend/.env.production, then redeploy.',
    );
    process.exit(1);
  }
  console.log('[check-csp] VITE_API_BASE_URL not set: this build will call http://localhost:8000.');
  process.exit(0);
}

let origin;
try {
  origin = new URL(raw).origin;
} catch {
  console.error(`[check-csp] VITE_API_BASE_URL is not a valid URL: ${raw}`);
  process.exit(1);
}

if (['localhost', '127.0.0.1'].includes(new URL(origin).hostname)) {
  if (isDeploy) {
    console.error(
      `[check-csp] This build points at ${origin}, which does not exist for visitors of a\n` +
        '            deployed site. Set VITE_API_BASE_URL to the public API URL and redeploy.',
    );
    process.exit(1);
  }
  process.exit(0);
}

const config = JSON.parse(readFileSync(new URL('../vercel.json', import.meta.url), 'utf8'));
const csp = config.headers
  .flatMap((rule) => rule.headers)
  .find((h) => h.key === 'Content-Security-Policy')?.value;
const connectSrc = csp?.split(';').map((d) => d.trim()).find((d) => d.startsWith('connect-src')) ?? '';

if (!connectSrc.split(/\s+/).includes(origin)) {
  console.error(
    `[check-csp] ${origin} is missing from connect-src in frontend/vercel.json.\n` +
      `            Add it there (see README "Content Security Policy") or the browser will block API calls.`,
  );
  process.exit(1);
}
console.log(`[check-csp] OK: ${origin} is allowed by connect-src.`);
