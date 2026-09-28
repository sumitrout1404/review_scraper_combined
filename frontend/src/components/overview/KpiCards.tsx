import clsx from 'clsx';
import type { ReactNode } from 'react';
import type { Summary } from '../../api/types';
import { formatCount, formatDateRange, formatPct, formatScore, plural } from '../../lib/format';
import { Delta } from '../common/Delta';
import { LowSampleBadge } from '../common/LowSampleBadge';
import { InfoTip } from '../ui/InfoTip';
import { Skeleton } from '../ui/Skeleton';

interface KpiCardProps {
  label: string;
  value: string;
  info: ReactNode;
  footer: ReactNode;
  badge?: ReactNode;
}

function KpiCard({ label, value, info, footer, badge }: KpiCardProps) {
  return (
    <div className="card flex flex-col p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
        <div className="flex items-center gap-1">
          <h3 className="font-sans text-sm font-medium text-ink-muted">{label}</h3>
          <InfoTip topic={label}>{info}</InfoTip>
        </div>
        {badge}
      </div>
      <p className="mt-2 font-display text-3xl font-medium text-navy tabular sm:text-4xl">{value}</p>
      <div className="mt-auto pt-3">{footer}</div>
    </div>
  );
}

/** Difference in percentage points, or null when there is nothing to compare with. */
function pointChange(current: number, previous: number, previousCount: number): number | null {
  return previousCount === 0 ? null : current - previous;
}

export function KpiCards({ summary }: { summary: Summary }) {
  const { current, previous } = summary;
  const prevLabel = 'previous period';
  const previousText = `The previous period is ${formatDateRange(previous.date_from, previous.date_to)}: the same number of days directly before your selected dates.`;

  return (
    <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
      <div className="card col-span-2 flex flex-col bg-navy p-5 text-white sm:col-span-1">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1">
            <h3 className="font-sans text-sm font-medium text-sand">Guest score</h3>
            <span className="[&_button]:text-sand [&_button:hover]:bg-white/10 [&_button:hover]:text-white">
              <InfoTip topic="Guest score">
                <p>The simple average of the review scores (out of 10) posted in the selected dates.</p>
                <p>
                  This is different from Booking.com’s headline score, which is weighted over a longer period and so
                  moves more slowly.
                </p>
                <p className="text-ink-muted">{previousText}</p>
              </InfoTip>
            </span>
          </div>
          <LowSampleBadge count={current.count} />
        </div>
        <p className="mt-2 font-display text-5xl font-medium tabular">
          {formatScore(current.avg_score)}
          <span className="ml-1 text-base font-normal text-sand/80">/ 10</span>
        </p>
        <div className="mt-auto pt-3">
          <ScoreChange delta={summary.delta_avg_score} previousScore={previous.avg_score} />
        </div>
      </div>

      <KpiCard
        label="Reviews"
        value={formatCount(current.count)}
        info={
          <>
            <p>How many reviews were posted on Booking.com in the selected dates.</p>
            <p className="text-ink-muted">{previousText}</p>
          </>
        }
        footer={
          <Delta value={previous.count === 0 && current.count === 0 ? null : summary.delta_count} digits={0} comparedTo={prevLabel} />
        }
      />
      <KpiCard
        label="Positive reviews"
        value={formatPct(current.pct_positive)}
        info={
          <>
            <p>Share of reviews whose overall tone is positive (usually a score of 8 or more with mostly good comments).</p>
            <p className="text-ink-muted">{plural(current.positive, 'positive review')} in this period.</p>
          </>
        }
        badge={<LowSampleBadge count={current.count} />}
        footer={
          <Delta
            value={pointChange(current.pct_positive, previous.pct_positive, previous.count)}
            digits={0}
            unit=" pts"
            comparedTo={prevLabel}
          />
        }
      />
      <KpiCard
        label="Negative reviews"
        value={formatPct(current.pct_negative)}
        info={
          <>
            <p>Share of reviews whose overall tone is negative (usually a score below 6 or mostly complaints).</p>
            <p>Lower is better, so a fall shows in green.</p>
            <p className="text-ink-muted">{plural(current.negative, 'negative review')} in this period.</p>
          </>
        }
        badge={<LowSampleBadge count={current.count} />}
        footer={
          <Delta
            value={pointChange(current.pct_negative, previous.pct_negative, previous.count)}
            digits={0}
            unit=" pts"
            invert
            comparedTo={prevLabel}
          />
        }
      />
    </div>
  );
}

/** On the navy card the delta needs light colours, so it gets its own styling. */
function ScoreChange({ delta, previousScore }: { delta: number | null; previousScore: number | null }) {
  if (delta === null) {
    return <p className="text-sm text-sand/80">No earlier reviews to compare with</p>;
  }
  const rounded = Number(delta.toFixed(1));
  const arrow = rounded > 0 ? '↑' : rounded < 0 ? '↓' : '→';
  const words = rounded > 0 ? 'Up' : rounded < 0 ? 'Down' : 'No change';
  return (
    <p className="text-sm">
      <span
        className={clsx(
          'mr-1.5 inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-medium',
          rounded > 0 ? 'bg-[#d5efe2] text-positive' : rounded < 0 ? 'bg-[#f9dde2] text-negative' : 'bg-white/15 text-white',
        )}
      >
        <span aria-hidden="true">{arrow}</span>
        {words}
        {rounded !== 0 && ` ${Math.abs(rounded).toFixed(1)}`}
      </span>
      <span className="text-sand/80">from {formatScore(previousScore)} in the previous period</span>
    </p>
  );
}

export function KpiCardsSkeleton() {
  return (
    <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className={i === 0 ? 'card col-span-2 p-5 sm:col-span-1' : 'card p-5'}>
          <Skeleton className="h-4 w-24" />
          <Skeleton className="mt-4 h-10 w-20" />
          <Skeleton className="mt-4 h-4 w-40" />
        </div>
      ))}
    </div>
  );
}
