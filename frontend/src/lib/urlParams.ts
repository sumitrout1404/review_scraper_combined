/**
 * Filters live in the URL so views are shareable. Everything read from the URL
 * is untrusted, so each value is validated here and invalid values are ignored.
 */
import { TOPIC_KEYS, type Polarity, type ReviewSort, type Sentiment } from '../api/types';
import { isISODate, RANGE_PRESETS, type RangePreset } from './dates';

export const PROPERTY_IDS = ['olympic-paddington', 'potts-point', 'central-sydney', 'darling-harbour'] as const;

const SENTIMENTS: readonly Sentiment[] = ['positive', 'neutral', 'negative'];
const POLARITIES: readonly Polarity[] = ['positive', 'negative'];
export const REVIEW_SORTS: readonly ReviewSort[] = ['date_desc', 'date_asc', 'score_desc', 'score_asc'];
export const MAX_SEARCH_LENGTH = 100;

function oneOf<T extends string>(allowed: readonly T[], value: string | null): T | undefined {
  return value !== null && (allowed as readonly string[]).includes(value) ? (value as T) : undefined;
}

function listOf<T extends string>(allowed: readonly T[], value: string | null): T[] {
  if (!value) return [];
  const items = value.split(',').filter((v): v is T => (allowed as readonly string[]).includes(v));
  return Array.from(new Set(items));
}

function score(value: string | null): number | undefined {
  if (value === null || value === '') return undefined;
  const n = Number(value);
  return Number.isInteger(n) && n >= 1 && n <= 10 ? n : undefined;
}

export interface GlobalFilterParams {
  properties: string[];
  preset: RangePreset;
  customFrom?: string;
  customTo?: string;
}

export const DEFAULT_PRESET: RangePreset = 'this_week';

export function readGlobalFilters(params: URLSearchParams): GlobalFilterParams {
  const properties = listOf(PROPERTY_IDS, params.get('properties'));
  const from = params.get('from');
  const to = params.get('to');
  const hasCustom = isISODate(from) && isISODate(to) && from <= to;
  let preset = oneOf(RANGE_PRESETS, params.get('range')) ?? DEFAULT_PRESET;
  if (preset === 'custom' && !hasCustom) preset = DEFAULT_PRESET;
  return {
    properties,
    preset,
    customFrom: preset === 'custom' && hasCustom ? from : undefined,
    customTo: preset === 'custom' && hasCustom ? to : undefined,
  };
}

export interface ReviewFilterParams {
  sentiment: Sentiment[];
  topic?: string;
  polarity?: Polarity;
  minScore?: number;
  maxScore?: number;
  q: string;
  sort: ReviewSort;
}

export function readReviewFilters(params: URLSearchParams): ReviewFilterParams {
  let minScore = score(params.get('min_score'));
  let maxScore = score(params.get('max_score'));
  if (minScore !== undefined && maxScore !== undefined && minScore > maxScore) {
    [minScore, maxScore] = [maxScore, minScore];
  }
  const topic = oneOf(TOPIC_KEYS, params.get('topic'));
  return {
    sentiment: listOf(SENTIMENTS, params.get('sentiment')),
    topic,
    polarity: topic ? oneOf(POLARITIES, params.get('polarity')) : undefined,
    minScore,
    maxScore,
    q: (params.get('q') ?? '').slice(0, MAX_SEARCH_LENGTH),
    sort: oneOf(REVIEW_SORTS, params.get('sort')) ?? 'date_desc',
  };
}


/** Returns a copy of `params` with the given keys set (or removed when empty). */
export function withParams(
  params: URLSearchParams,
  updates: Record<string, string | number | string[] | undefined | null>,
): URLSearchParams {
  const next = new URLSearchParams(params);
  for (const [key, value] of Object.entries(updates)) {
    const text = Array.isArray(value) ? value.join(',') : value === undefined || value === null ? '' : String(value);
    if (text === '') next.delete(key);
    else next.set(key, text);
  }
  return next;
}

/** The global filter keys, used to carry the current scope across pages. */
export const GLOBAL_KEYS = ['properties', 'range', 'from', 'to'] as const;

export function pickGlobal(params: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams();
  for (const key of GLOBAL_KEYS) {
    const value = params.get(key);
    if (value) next.set(key, value);
  }
  return next;
}
