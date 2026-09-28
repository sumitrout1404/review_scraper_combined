import { Download, FilterX, Loader2 } from 'lucide-react';
import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import type { ReviewQuery } from '../api/types';
import { FilterBar } from '../components/filters/FilterBar';
import { PageHeader } from '../components/layout/PageHeader';
import { ReviewCard, ReviewCardSkeleton } from '../components/reviews/ReviewCard';
import { ReviewFilters, type ReviewFilterChange } from '../components/reviews/ReviewFilters';
import { Button } from '../components/ui/Button';
import { buttonClasses } from '../components/ui/buttonStyles';
import { LoadingRegion } from '../components/ui/Skeleton';
import { EmptyState, ErrorState } from '../components/ui/States';
import { useReviewFeed, useTopics } from '../hooks/queries';
import { useGlobalFilters } from '../hooks/useGlobalFilters';
import { formatCount } from '../lib/format';
import { readReviewFilters, withParams } from '../lib/urlParams';

const REVIEW_FILTER_KEYS = ['sentiment', 'topic', 'polarity', 'min_score', 'max_score', 'q', 'sort'] as const;

export function ReviewsPage() {
  const filters = useGlobalFilters();
  const [params, setParams] = useSearchParams();
  const reviewFilters = useMemo(() => readReviewFilters(params), [params]);
  const topics = useTopics();

  const query = useMemo<ReviewQuery | null>(
    () =>
      filters.scope
        ? {
            ...filters.scope,
            sentiment: reviewFilters.sentiment.length > 0 ? reviewFilters.sentiment : undefined,
            topic: reviewFilters.topic,
            polarity: reviewFilters.polarity,
            min_score: reviewFilters.minScore,
            max_score: reviewFilters.maxScore,
            q: reviewFilters.q || undefined,
            sort: reviewFilters.sort,
          }
        : null,
    [filters.scope, reviewFilters],
  );
  const feed = useReviewFeed(query);

  const update = (change: ReviewFilterChange) =>
    setParams((prev) => withParams(prev, change as Record<string, string | number | string[] | null | undefined>), {
      replace: true,
    });
  const clearAll = () =>
    setParams((prev) => withParams(prev, Object.fromEntries(REVIEW_FILTER_KEYS.map((k) => [k, null]))), { replace: true });

  const hasReviewFilters = REVIEW_FILTER_KEYS.some((k) => k !== 'sort' && params.has(k));
  const items = feed.data?.pages.flatMap((p) => p.items) ?? [];
  const total = feed.data?.pages[0]?.total ?? 0;

  return (
    <>
      <PageHeader
        eyebrow="Guest voice"
        title="Reviews"
        description="Read what guests wrote. Click a topic tag to see every review that mentions it."
        actions={
          query && (
            <a
              href={api.exportCsvUrl(query)}
              className={buttonClasses('secondary', 'md')}
              download
              aria-label="Export these reviews as a CSV spreadsheet"
            >
              <Download className="h-4 w-4" aria-hidden="true" />
              Export CSV
            </a>
          )
        }
      />
      <FilterBar filters={filters} showComparison={false} />
      <ReviewFilters value={reviewFilters} topics={topics.data ?? []} onChange={update} />

      <div className="mb-4 flex min-h-[2rem] flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-ink-muted" aria-live="polite">
          {feed.data ? (
            <>
              Showing <span className="font-medium text-ink">{formatCount(items.length)}</span> of{' '}
              <span className="font-medium text-ink">{formatCount(total)}</span> reviews
            </>
          ) : (
            ' '
          )}
        </p>
        {hasReviewFilters && (
          <Button variant="ghost" size="sm" onClick={clearAll} icon={<FilterX className="h-3.5 w-3.5" aria-hidden="true" />}>
            Clear review filters
          </Button>
        )}
      </div>

      {feed.isError && !feed.data ? (
        <div className="card">
          <ErrorState error={feed.error} onRetry={() => void feed.refetch()} />
        </div>
      ) : !feed.data ? (
        <LoadingRegion label="Loading reviews">
          <div className="space-y-4">
            {[0, 1, 2].map((i) => (
              <ReviewCardSkeleton key={i} />
            ))}
          </div>
        </LoadingRegion>
      ) : items.length === 0 ? (
        <div className="card">
          <EmptyState
            title={hasReviewFilters ? 'No reviews match these filters' : 'No reviews in this period'}
            message={
              hasReviewFilters
                ? 'Try removing a filter, or widen the date range.'
                : 'Try widening the date range or selecting more properties.'
            }
            action={
              hasReviewFilters && (
                <Button size="sm" onClick={clearAll}>
                  Clear review filters
                </Button>
              )
            }
          />
        </div>
      ) : (
        <>
          <ul className="space-y-4">
            {items.map((review) => (
              <li key={review.id}>
                <ReviewCard review={review} />
              </li>
            ))}
          </ul>
          <div className="mt-6 flex flex-col items-center gap-2">
            {feed.hasNextPage ? (
              <Button
                onClick={() => void feed.fetchNextPage()}
                disabled={feed.isFetchingNextPage}
                icon={feed.isFetchingNextPage ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : undefined}
              >
                {feed.isFetchingNextPage ? 'Loading…' : 'Load more reviews'}
              </Button>
            ) : (
              <p className="text-xs text-ink-muted">You’ve reached the end of the list.</p>
            )}
            {feed.isFetchNextPageError && <p role="alert" className="text-sm text-negative">Couldn’t load more reviews. Please try again.</p>}
          </div>
        </>
      )}
    </>
  );
}
