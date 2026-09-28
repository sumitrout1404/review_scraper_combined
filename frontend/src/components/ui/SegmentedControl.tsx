import clsx from 'clsx';

interface SegmentedControlProps<T extends string> {
  label: string;
  value: T;
  options: readonly { value: T; label: string }[];
  onChange: (value: T) => void;
}

/** A small radio group styled as a toggle, e.g. Weekly / Monthly. */
export function SegmentedControl<T extends string>({ label, value, options, onChange }: SegmentedControlProps<T>) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-xl border border-sand bg-offwhite p-0.5">
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(option.value)}
            className={clsx(
              'focus-ring h-8 rounded-[10px] px-3 text-xs font-medium transition-colors',
              selected ? 'bg-white text-navy shadow-card' : 'text-ink-muted hover:text-navy',
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
