/**
 * Build guard: the CSP in vercel.json must allow the API origin the bundle will
 * call (VITE_API_BASE_URL), otherwise the deployed dashboard silently fails.
 * Local builds against localhost only get a note; any other origin must be listed.
 */
import { readFileSync } from 'node:fs';

const raw = process.env.VITE_API_BASE_URL?.trim();
if (!raw) {
  console.log('[check-csp] VITE_API_BASE_URL not set: the build will call http://localhost:8000.');
  process.exit(0);
}

let origin;
try {
  origin = new URL(raw).origin;
} catch {
  console.error(`[check-csp] VITE_API_BASE_URL is not a valid URL: ${raw}`);
  process.exit(1);
}

if (['localhost', '127.0.0.1'].includes(new URL(origin).hostname)) process.exit(0);

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
