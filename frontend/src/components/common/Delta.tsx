import clsx from 'clsx';
import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react';

interface DeltaProps {
  value: number | null | undefined;
  /** What the change is measured against, for the accessible description. */
  comparedTo?: string;
  /** For metrics where going up is bad (e.g. % negative). */
  invert?: boolean;
  unit?: string;
  digits?: number;
  className?: string;
}

/** Change indicator that never relies on colour alone: arrow + signed number + words. */
export function Delta({ value, comparedTo = 'the previous period', invert, unit = '', digits = 1, className }: DeltaProps) {
  if (value === null || value === undefined) {
    return <span className={clsx('text-xs text-ink-muted', className)}>No earlier data to compare</span>;
  }
  const rounded = Number(value.toFixed(digits));
  const direction = rounded > 0 ? 'up' : rounded < 0 ? 'down' : 'flat';
  const good = direction === 'flat' ? null : (direction === 'up') !== Boolean(invert);
  const Icon = direction === 'up' ? ArrowUpRight : direction === 'down' ? ArrowDownRight : Minus;
  const words = direction === 'flat' ? 'No change' : direction === 'up' ? 'Up' : 'Down';

  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 text-sm font-medium',
        good === null ? 'text-neutral-dark' : good ? 'text-positive' : 'text-negative',
        className,
      )}
    >
      <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
      <span>
        {direction === 'flat' ? words : `${words} ${Math.abs(rounded).toFixed(digits)}${unit}`}
        <span className="font-normal text-ink-muted"> vs {comparedTo}</span>
      </span>
    </span>
  );
}
