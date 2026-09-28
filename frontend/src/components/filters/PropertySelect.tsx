import clsx from 'clsx';
import { Building2, Check, ChevronDown } from 'lucide-react';
import { useProperties } from '../../hooks/queries';
import { Popover } from '../ui/Popover';

interface PropertySelectProps {
  value: string[];
  onChange: (ids: string[]) => void;
}

/** Multi-select for properties. An empty selection means "All properties". */
export function PropertySelect({ value, onChange }: PropertySelectProps) {
  const properties = useProperties();
  const list = properties.data ?? [];
  const selected = new Set(value);

  const summary =
    value.length === 0 || value.length === list.length
      ? 'All properties'
      : value.length === 1
        ? (list.find((p) => p.id === value[0])?.short_name ?? '1 property')
        : `${value.length} properties`;

  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange(next.size === list.length ? [] : Array.from(next));
  };

  return (
    <Popover
      label="Choose properties"
      panelClassName="w-72 max-w-[calc(100vw-2rem)] !p-2"
      trigger={(props) => (
        <button
          type="button"
          {...props}
          className="focus-ring flex h-11 w-full items-center gap-2 rounded-xl border border-sand bg-white px-3 text-left text-sm hover:border-bronze/60 sm:w-60"
        >
          <Building2 className="h-4 w-4 shrink-0 text-bronze" aria-hidden="true" />
          <span className="min-w-0 flex-1">
            <span className="block text-[11px] uppercase tracking-wide text-ink-muted">Properties</span>
            <span className="block truncate font-medium text-navy">{summary}</span>
          </span>
          <ChevronDown className="h-4 w-4 shrink-0 text-ink-muted" aria-hidden="true" />
        </button>
      )}
    >
      {() => (
        <fieldset>
          <legend className="sr-only">Properties to include</legend>
          <OptionRow label="All properties" checked={value.length === 0} onToggle={() => onChange([])} />
          <div className="my-1 border-t border-sand/60" />
          {properties.isError && <p className="px-3 py-2 text-sm text-negative">Couldn’t load properties.</p>}
          {list.map((p) => (
            <OptionRow
              key={p.id}
              label={p.short_name}
              hint={p.name}
              checked={value.length === 0 || selected.has(p.id)}
              onToggle={() => (value.length === 0 ? onChange([p.id]) : toggle(p.id))}
            />
          ))}
        </fieldset>
      )}
    </Popover>
  );
}

function OptionRow({ label, hint, checked, onToggle }: { label: string; hint?: string; checked: boolean; onToggle: () => void }) {
  return (
    <label className="flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2 hover:bg-cream/60">
      <input type="checkbox" className="peer sr-only" checked={checked} onChange={onToggle} />
      <span
        aria-hidden="true"
        className={clsx(
          'flex h-5 w-5 shrink-0 items-center justify-center rounded-md border peer-focus-visible:ring-2 peer-focus-visible:ring-coral',
          checked ? 'border-navy bg-navy text-white' : 'border-sand bg-white',
        )}
      >
        {checked && <Check className="h-3.5 w-3.5" />}
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-medium text-navy">{label}</span>
        {hint && <span className="block truncate text-xs text-ink-muted">{hint}</span>}
      </span>
    </label>
  );
}
