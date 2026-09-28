import clsx from 'clsx';
import { ExternalLink, ThumbsDown } from 'lucide-react';
import type { Property, PropertySummary } from '../../api/types';
import { formatScore, plural } from '../../lib/format';
import { Delta } from '../common/Delta';
import { LowSampleBadge } from '../common/LowSampleBadge';

interface PropertyComparisonProps {
  rows: PropertySummary[];
  properties: Property[];
  selected: string[];
  onSelect: (id: string) => void;
}

/** One card per property; clicking a card narrows the whole dashboard to that property. */
export function PropertyComparison({ rows, properties, selected, onSelect }: PropertyComparisonProps) {
  const byId = new Map(properties.map((p) => [p.id, p]));
  const ranked = [...rows].sort((a, b) => (b.current.avg_score ?? -1) - (a.current.avg_score ?? -1));

  return (
    <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {ranked.map((row) => {
        const property = byId.get(row.property_id);
        const isSelected = selected.length === 1 && selected[0] === row.property_id;
        return (
          <li key={row.property_id} className="relative">
            <button
              type="button"
              onClick={() => onSelect(row.property_id)}
              aria-pressed={isSelected}
              aria-label={`${row.name}: ${isSelected ? 'showing only this property. Click to show all properties.' : 'show only this property'}`}
              className={clsx(
                'focus-ring card flex h-full w-full flex-col p-5 text-left transition-all hover:-translate-y-0.5 hover:shadow-pop',
                isSelected && 'ring-2 ring-navy',
              )}
            >
              <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-bronze">{row.short_name}</span>
              <span className="mt-0.5 block pr-8 text-sm text-ink-muted">{row.name}</span>

              <span className="mt-4 flex items-end gap-2">
                <span className="font-display text-4xl font-medium text-navy tabular">{formatScore(row.current.avg_score)}</span>
                <span className="mb-1.5 text-xs text-ink-muted">guest score</span>
              </span>
              <span className="mt-1 flex flex-wrap items-center gap-2">
                <Delta value={row.delta_avg_score} comparedTo="previous" className="text-xs" />
              </span>

              <span className="mt-4 flex flex-wrap items-center gap-2 text-sm text-ink">
                {plural(row.current.count, 'review')}
                <LowSampleBadge count={row.current.count} />
              </span>

              <span className="mt-3 block border-t border-sand/60 pt-3 text-xs">
                <span className="block text-ink-muted">Top complaint</span>
                {row.top_complaint ? (
                  <span className="mt-0.5 flex items-center gap-1.5 font-medium text-negative">
                    <ThumbsDown className="h-3.5 w-3.5" aria-hidden="true" />
                    {row.top_complaint.label}
                    <span className="font-normal text-ink-muted">({plural(row.top_complaint.count, 'mention')})</span>
                  </span>
                ) : (
                  <span className="mt-0.5 block font-medium text-ink">None in this period</span>
                )}
              </span>
              {property?.booking_score != null && (
                <span className="mt-2 block text-xs text-ink-muted">
                  Booking.com headline score: <span className="font-medium text-ink">{formatScore(property.booking_score)}</span>
                </span>
              )}
            </button>
            {property && (
              <a
                href={property.booking_url}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`Open ${row.name} on Booking.com (opens in a new tab)`}
                className="focus-ring absolute right-3 top-3 flex h-8 w-8 items-center justify-center rounded-full text-ink-muted hover:bg-cream hover:text-navy"
              >
                <ExternalLink className="h-4 w-4" aria-hidden="true" />
              </a>
            )}
          </li>
        );
      })}
    </ul>
  );
}
