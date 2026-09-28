import { keepPreviousData, useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import type { Granularity, Polarity, ReviewQuery, ScopeParams } from '../api/types';
import { config } from '../lib/config';

/** Reference data changes only when the collector runs, so cache it for a while. */
const REFERENCE_STALE_MS = 10 * 60_000;

export function useMeta() {
  return useQuery({ queryKey: ['meta'], queryFn: ({ signal }) => api.meta(signal), staleTime: 5 * 60_000 });
}

export function useProperties() {
  return useQuery({
    queryKey: ['properties'],
    queryFn: ({ signal }) => api.properties(signal),
    staleTime: REFERENCE_STALE_MS,
  });
}

export function useTopics() {
  return useQuery({ queryKey: ['topics'], queryFn: ({ signal }) => api.topics(signal), staleTime: REFERENCE_STALE_MS });
}

/** `scope` is null until the date range can be resolved (it needs /api/meta). */
export function useSummary(scope: ScopeParams | null) {
  return useQuery({
    queryKey: ['summary', scope],
    queryFn: ({ signal }) => api.summary(scope as ScopeParams, signal),
    enabled: scope !== null,
    placeholderData: keepPreviousData,
  });
}

export function useInsights(scope: ScopeParams | null) {
  return useQuery({
    queryKey: ['insights', scope],
    queryFn: ({ signal }) => api.insights(scope as ScopeParams, signal),
    enabled: scope !== null,
  });
}

export function useTrends(scope: ScopeParams | null, granularity: Granularity) {
  return useQuery({
    queryKey: ['trends', scope, granularity],
    queryFn: ({ signal }) => api.trends({ ...(scope as ScopeParams), granularity }, signal),
    enabled: scope !== null,
    placeholderData: keepPreviousData,
  });
}

export function useTopicBreakdown(scope: ScopeParams | null) {
  return useQuery({
    queryKey: ['topic-breakdown', scope],
    queryFn: ({ signal }) => api.topicBreakdown(scope as ScopeParams, signal),
    enabled: scope !== null,
    placeholderData: keepPreviousData,
  });
}

export function useTopicTrends(scope: ScopeParams | null, granularity: Granularity, polarity: Polarity) {
  return useQuery({
    queryKey: ['topic-trends', scope, granularity, polarity],
    queryFn: ({ signal }) => api.topicTrends({ ...(scope as ScopeParams), granularity, polarity }, signal),
    enabled: scope !== null,
    placeholderData: keepPreviousData,
  });
}

export function useReviewFeed(query: ReviewQuery | null) {
  return useInfiniteQuery({
    queryKey: ['reviews', query],
    queryFn: ({ pageParam, signal }) =>
      api.reviews({ ...(query as ReviewQuery), page: pageParam, page_size: config.reviewsPageSize }, signal),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.page * last.page_size < last.total ? last.page + 1 : undefined),
    enabled: query !== null,
  });
}

export function useScrapeRuns() {
  return useQuery({
    queryKey: ['scrape-runs'],
    queryFn: ({ signal }) => api.scrapeRuns(config.scrapeRunsLimit, signal),
  });
}
