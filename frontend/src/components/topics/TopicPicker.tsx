import clsx from 'clsx';
import type { Topic } from '../../api/types';

interface TopicPickerProps {
  topics: Topic[];
  /** Fixed colour slots; a topic keeps its colour while selected. */
  slots: (string | null)[];
  colors: readonly string[];
  onToggle: (topic: string) => void;
}

export function TopicPicker({ topics, slots, colors, onToggle }: TopicPickerProps) {
  const full = slots.every((s) => s !== null);
  return (
    <fieldset>
      <legend className="label">
        Topics to compare <span className="normal-case tracking-normal">(up to {slots.length})</span>
      </legend>
      <div className="flex flex-wrap gap-1.5">
        {topics.map((t) => {
          const slot = slots.indexOf(t.key);
          const active = slot !== -1;
          return (
            <button
              key={t.key}
              type="button"
              aria-pressed={active}
              disabled={!active && full}
              onClick={() => onToggle(t.key)}
              title={!active && full ? `Remove a topic first (maximum ${slots.length})` : undefined}
              className={clsx(
                'focus-ring inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50',
                active ? 'border-navy bg-white text-navy shadow-card' : 'border-sand bg-offwhite text-ink-muted hover:text-navy',
              )}
            >
              <span
                aria-hidden="true"
                className="h-2.5 w-2.5 rounded-full border"
                style={active ? { backgroundColor: colors[slot], borderColor: colors[slot] } : { borderColor: '#c9bda3' }}
              />
              {t.label}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
