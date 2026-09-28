/**
 * Runtime configuration. Only public values belong here: anything prefixed
 * VITE_ is bundled into the browser build, so never put secrets in it.
 */

const DEFAULT_API_BASE_URL = 'http://localhost:8000';

function normaliseBaseUrl(raw: string | undefined): string {
  const value = (raw ?? '').trim() || DEFAULT_API_BASE_URL;
  return value.replace(/\/+$/, '');
}

export const config = {
  apiBaseUrl: normaliseBaseUrl(import.meta.env.VITE_API_BASE_URL),
  /** Abort API requests that take longer than this. */
  requestTimeoutMs: 15_000,
  /** Data is refreshed nightly at midnight (Sydney); flag it as stale after this long without a successful run. */
  staleAfterHours: 36,
  /** Below this many reviews, numbers get a "Low sample" badge. */
  lowSampleThreshold: 5,
  reviewsPageSize: 20,
  scrapeRunsLimit: 30,
  /** Search input debounce. */
  searchDebounceMs: 350,
} as const;
