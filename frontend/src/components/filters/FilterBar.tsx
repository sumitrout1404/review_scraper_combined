import { useMeta } from '../../hooks/queries';
import type { GlobalFilters } from '../../hooks/useGlobalFilters';
import { daysInclusive } from '../../lib/dates';
import { formatDateRange } from '../../lib/format';
import { DateRangePicker } from './DateRangePicker';
import { PropertySelect } from './PropertySelect';

/** Global property + date filters, shown at the top of every data page. */
export function FilterBar({ filters, showComparison = true }: { filters: GlobalFilters; showComparison?: boolean }) {
  const meta = useMeta();
  return (
    <div className="card mb-8 flex flex-col gap-3 p-3 sm:flex-row sm:flex-wrap sm:items-center sm:p-4">
      <PropertySelect value={filters.properties} onChange={filters.setProperties} />
      <DateRangePicker
        preset={filters.preset}
        range={filters.range}
        minDate={meta.data?.min_review_date}
        maxDate={meta.data?.today}
        onPreset={filters.setPreset}
        onCustom={filters.setCustomRange}
      />
      {showComparison && filters.previous && (
        <p className="text-xs text-ink-muted sm:ml-auto sm:max-w-xs sm:text-right">
          Compared with the {`${daysLabel(filters)} before`}:{' '}
          <span className="font-medium text-ink">{formatDateRange(filters.previous.from, filters.previous.to)}</span>
        </p>
      )}
    </div>
  );
}

function daysLabel(filters: GlobalFilters): string {
  if (!filters.previous) return 'period';
  const days = daysInclusive(filters.previous.from, filters.previous.to);
  return days === 1 ? 'day' : `${days} days`;
}
