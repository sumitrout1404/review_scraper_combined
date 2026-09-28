import clsx from 'clsx';
import { CalendarDays, ChevronDown } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { isISODate, PRESET_LABELS, RANGE_PRESETS, type DateRange, type RangePreset } from '../../lib/dates';
import { formatDateRange } from '../../lib/format';
import { Button } from '../ui/Button';
import { Popover } from '../ui/Popover';

interface DateRangePickerProps {
  preset: RangePreset;
  range: DateRange | null;
  /** Earliest/latest dates the data covers, to bound the custom inputs. */
  minDate?: string | null;
  maxDate?: string;
  onPreset: (preset: Exclude<RangePreset, 'custom'>) => void;
  onCustom: (range: DateRange) => void;
}

const QUICK_PRESETS = RANGE_PRESETS.filter((p): p is Exclude<RangePreset, 'custom'> => p !== 'custom');

export function DateRangePicker({ preset, range, minDate, maxDate, onPreset, onCustom }: DateRangePickerProps) {
  return (
    <Popover
      label="Choose dates"
      panelClassName="w-80 max-w-[calc(100vw-2rem)]"
      trigger={(props) => (
        <button
          type="button"
          {...props}
          className="focus-ring flex h-11 w-full items-center gap-2 rounded-xl border border-sand bg-white px-3 text-left text-sm hover:border-bronze/60 sm:w-auto sm:min-w-[16rem]"
        >
          <CalendarDays className="h-4 w-4 shrink-0 text-bronze" aria-hidden="true" />
          <span className="min-w-0 flex-1">
            <span className="block text-[11px] uppercase tracking-wide text-ink-muted">{PRESET_LABELS[preset]}</span>
            <span className="block truncate font-medium text-navy">
              {range ? formatDateRange(range.from, range.to) : 'Loading dates…'}
            </span>
          </span>
          <ChevronDown className="h-4 w-4 shrink-0 text-ink-muted" aria-hidden="true" />
        </button>
      )}
    >
      {(close) => (
        <div>
          <p className="label">Quick ranges</p>
          <div className="grid grid-cols-2 gap-2">
            {QUICK_PRESETS.map((p) => (
              <button
                key={p}
                type="button"
                aria-pressed={preset === p}
                onClick={() => {
                  onPreset(p);
                  close();
                }}
                className={clsx(
                  'focus-ring h-9 rounded-xl border px-3 text-left text-sm transition-colors',
                  preset === p ? 'border-navy bg-navy text-white' : 'border-sand text-navy hover:bg-cream/60',
                )}
              >
                {PRESET_LABELS[p]}
              </button>
            ))}
          </div>
          <CustomRangeForm
            initial={range}
            minDate={minDate ?? undefined}
            maxDate={maxDate}
            onApply={(r) => {
              onCustom(r);
              close();
            }}
          />
        </div>
      )}
    </Popover>
  );
}

interface CustomRangeFormProps {
  initial: DateRange | null;
  minDate?: string;
  maxDate?: string;
  onApply: (range: DateRange) => void;
}

function CustomRangeForm({ initial, minDate, maxDate, onApply }: CustomRangeFormProps) {
  const [from, setFrom] = useState(initial?.from ?? '');
  const [to, setTo] = useState(initial?.to ?? '');
  const [error, setError] = useState<string | null>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!isISODate(from) || !isISODate(to)) return setError('Please choose both dates.');
    if (from > to) return setError('The start date must be on or before the end date.');
    setError(null);
    onApply({ from, to });
  };

  return (
    <form onSubmit={submit} className="mt-4 border-t border-sand/60 pt-4" noValidate>
      <p className="label">Custom dates</p>
      <div className="grid grid-cols-2 gap-2">
        <label className="text-xs text-ink-muted">
          From
          <input type="date" className="input mt-1" value={from} min={minDate} max={to || maxDate} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="text-xs text-ink-muted">
          To
          <input type="date" className="input mt-1" value={to} min={from || minDate} max={maxDate} onChange={(e) => setTo(e.target.value)} />
        </label>
      </div>
      {error && (
        <p role="alert" className="mt-2 text-xs text-negative">
          {error}
        </p>
      )}
      <Button type="submit" variant="primary" size="sm" className="mt-3 w-full">
        Apply dates
      </Button>
    </form>
  );
}
