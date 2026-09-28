import type { UseQueryResult } from '@tanstack/react-query';
import clsx from 'clsx';
import { AlertTriangle, CalendarSearch, RotateCw } from 'lucide-react';
import type { ReactNode } from 'react';
import { ApiError } from '../../api/client';
import { Button } from './Button';
import { LoadingRegion } from './Skeleton';

interface EmptyStateProps {
  title?: string;
  message?: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
  compact?: boolean;
}

export function EmptyState({
  title = 'No reviews in this period',
  message = 'Try widening the date range or selecting more properties.',
  icon,
  action,
  compact,
}: EmptyStateProps) {
  return (
    <div className={clsx('flex flex-col items-center text-center', compact ? 'py-6' : 'py-10')}>
      <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-cream text-bronze">
        {icon ?? <CalendarSearch className="h-5 w-5" aria-hidden="true" />}
      </div>
      <p className="font-medium text-navy">{title}</p>
      <p className="mt-1 max-w-sm text-sm text-ink-muted">{message}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return 'Something went wrong while loading this section.';
}

export function ErrorState({ error, onRetry, compact }: { error: unknown; onRetry?: () => void; compact?: boolean }) {
  return (
    <div role="alert" className={clsx('flex flex-col items-center text-center', compact ? 'py-6' : 'py-10')}>
      <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-negative-soft text-negative">
        <AlertTriangle className="h-5 w-5" aria-hidden="true" />
      </div>
      <p className="font-medium text-navy">We couldn’t load this</p>
      <p className="mt-1 max-w-sm text-sm text-ink-muted">{errorMessage(error)}</p>
      {onRetry && (
        <Button className="mt-4" size="sm" onClick={onRetry} icon={<RotateCw className="h-3.5 w-3.5" aria-hidden="true" />}>
          Try again
        </Button>
      )}
    </div>
  );
}

interface QueryViewProps<T> {
  query: Pick<UseQueryResult<T>, 'data' | 'error' | 'isError' | 'refetch'>;
  /** Screen-reader text announced while loading. */
  loadingLabel: string;
  skeleton: ReactNode;
  isEmpty?: (data: T) => boolean;
  empty?: ReactNode;
  children: (data: T) => ReactNode;
}

/** Renders the loading / error / empty / data states for one query consistently. */
export function QueryView<T>({ query, loadingLabel, skeleton, isEmpty, empty, children }: QueryViewProps<T>) {
  if (query.isError && query.data === undefined) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  }
  if (query.data === undefined) {
    return <LoadingRegion label={loadingLabel}>{skeleton}</LoadingRegion>;
  }
  if (isEmpty?.(query.data)) return <>{empty ?? <EmptyState />}</>;
  return <>{children(query.data)}</>;
}
