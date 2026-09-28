import clsx from 'clsx';
import type { ReactNode } from 'react';

/** Placeholder block shown while data loads. Hidden from screen readers. */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={clsx('animate-pulse rounded-lg bg-sand/50', className)} />;
}

/** Announces loading once for assistive tech, with visual skeletons as children. */
export function LoadingRegion({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      {children}
    </div>
  );
}
