import type { ReactNode } from 'react';

export interface TooltipRow {
  label: string;
  value: string;
  color?: string;
}

/** Card-style tooltip content for Recharts charts. Text uses ink colours; the swatch carries identity. */
export function ChartTooltipCard({ title, rows, footer }: { title: string; rows: TooltipRow[]; footer?: ReactNode }) {
  return (
    <div className="min-w-[10rem] rounded-xl border border-sand bg-white px-3 py-2.5 text-xs shadow-pop">
      <p className="mb-1.5 font-medium text-navy">{title}</p>
      <ul className="space-y-1">
        {rows.map((row) => (
          <li key={row.label} className="flex items-center justify-between gap-4">
            <span className="flex items-center gap-1.5 text-ink-muted">
              {row.color && <span className="h-2 w-2 rounded-full" style={{ backgroundColor: row.color }} aria-hidden="true" />}
              {row.label}
            </span>
            <span className="font-medium text-ink tabular">{row.value}</span>
          </li>
        ))}
      </ul>
      {footer && <div className="mt-1.5 border-t border-sand/60 pt-1.5 text-ink-muted">{footer}</div>}
    </div>
  );
}

/** Legend with swatches; identity is never colour-only because every series is named. */
export function ChartLegend({ items }: { items: { label: string; color: string; shape?: 'line' | 'square' }[] }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-muted">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className={item.shape === 'line' ? 'h-0.5 w-4 rounded-full' : 'h-2.5 w-2.5 rounded-[3px]'}
            style={{ backgroundColor: item.color }}
          />
          {item.label}
        </li>
      ))}
    </ul>
  );
}

/** Collapsible table view of a chart's data, for screen readers and exact numbers. */
export function DataTableDisclosure({ caption, children }: { caption: string; children: ReactNode }) {
  return (
    <details className="group mt-4 rounded-xl border border-sand/70 text-sm">
      <summary className="focus-ring cursor-pointer select-none rounded-xl px-3 py-2 text-xs font-medium text-navy hover:bg-cream/50">
        View as table
      </summary>
      <div className="max-h-72 overflow-auto px-3 pb-3">
        <table className="w-full text-left text-xs">
          <caption className="sr-only">{caption}</caption>
          {children}
        </table>
      </div>
    </details>
  );
}
