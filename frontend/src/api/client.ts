import { config } from '../lib/config';
import type {
  Granularity,
  Health,
  Insight,
  Meta,
  Paginated,
  Polarity,
  Property,
  Review,
  ReviewQuery,
  ScopeParams,
  ScrapeRun,
  Summary,
  Topic,
  TopicBreakdown,
  TopicTrends,
  Trends,
} from './types';

export type ApiErrorKind = 'network' | 'timeout' | 'http';

/** Error thrown by every API call. `message` is safe to show to staff. */
export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;

  constructor(kind: ApiErrorKind, message: string, status: number | null = null) {
    super(message);
    this.name = 'ApiError';
    this.kind = kind;
    this.status = status;
  }

  /** Client errors (4xx) will not succeed on retry. */
  get isClientError(): boolean {
    return this.status !== null && this.status >= 400 && this.status < 500;
  }
}

type QueryValue = string | number | string[] | undefined;
type QueryParams = Record<string, QueryValue>;

/** Builds an absolute API URL. All values go through URLSearchParams (never concatenated). */
export function apiUrl(path: string, params: QueryParams = {}): string {
  const url = new URL(path, `${config.apiBaseUrl}/`);
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === '') continue;
    if (Array.isArray(value)) {
      if (value.length > 0) url.searchParams.set(key, value.join(','));
    } else {
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

async function request<T>(path: string, params: QueryParams, signal?: AbortSignal): Promise<T> {
  const controller = new AbortController();
  let timedOut = false;
  const timer = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, config.requestTimeoutMs);
  const onOuterAbort = () => controller.abort();
  signal?.addEventListener('abort', onOuterAbort, { once: true });

  try {
    let res: Response;
    try {
      res = await fetch(apiUrl(path, params), {
        signal: controller.signal,
        headers: { Accept: 'application/json' },
      });
    } catch (err) {
      if (timedOut) throw new ApiError('timeout', 'The data service took too long to respond. Please try again.');
      if (signal?.aborted) throw err; // cancelled by react-query, not a user-facing error
      throw new ApiError('network', 'We could not reach the data service. Check your connection and try again.');
    }

    if (!res.ok) {
      let detail = `The data service returned an error (${res.status}).`;
      try {
        const body: unknown = await res.json();
        if (body && typeof body === 'object' && typeof (body as { detail?: unknown }).detail === 'string') {
          detail = (body as { detail: string }).detail;
        }
      } catch {
        // Non-JSON error body: keep the generic message.
      }
      throw new ApiError('http', detail, res.status);
    }
    return (await res.json()) as T;
  } finally {
    window.clearTimeout(timer);
    signal?.removeEventListener('abort', onOuterAbort);
  }
}

function scope(p: ScopeParams): QueryParams {
  return { properties: p.properties, date_from: p.date_from, date_to: p.date_to };
}

function reviewParams(q: ReviewQuery): QueryParams {
  return {
    ...scope(q),
    sentiment: q.sentiment,
    topic: q.topic,
    polarity: q.polarity,
    min_score: q.min_score,
    max_score: q.max_score,
    q: q.q,
    sort: q.sort,
    page: q.page,
    page_size: q.page_size,
  };
}

type TrendParams = ScopeParams & { granularity: Granularity };
type TopicTrendParams = TrendParams & { polarity: Polarity };

export const api = {
  health: (signal?: AbortSignal) => request<Health>('api/health', {}, signal),
  meta: (signal?: AbortSignal) => request<Meta>('api/meta', {}, signal),
  properties: (signal?: AbortSignal) => request<Property[]>('api/properties', {}, signal),
  topics: (signal?: AbortSignal) => request<Topic[]>('api/topics', {}, signal),
  summary: (p: ScopeParams, signal?: AbortSignal) => request<Summary>('api/summary', scope(p), signal),
  trends: (p: TrendParams, signal?: AbortSignal) =>
    request<Trends>('api/trends', { ...scope(p), granularity: p.granularity }, signal),
  topicBreakdown: (p: ScopeParams, signal?: AbortSignal) =>
    request<TopicBreakdown>('api/topics/breakdown', scope(p), signal),
  topicTrends: (p: TopicTrendParams, signal?: AbortSignal) =>
    request<TopicTrends>(
      'api/topics/trends',
      { ...scope(p), granularity: p.granularity, polarity: p.polarity },
      signal,
    ),
  insights: (p: ScopeParams, signal?: AbortSignal) => request<Insight[]>('api/insights', scope(p), signal),
  reviews: (q: ReviewQuery, signal?: AbortSignal) =>
    request<Paginated<Review>>('api/reviews', reviewParams(q), signal),
  scrapeRuns: (limit: number, signal?: AbortSignal) =>
    request<ScrapeRun[]>('api/scrape-runs', { limit }, signal),
  /** CSV download URL with the same filters as the feed (pagination dropped). */
  exportCsvUrl: (q: ReviewQuery) =>
    apiUrl('api/reviews/export.csv', reviewParams({ ...q, page: undefined, page_size: undefined })),
};
