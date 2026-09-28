import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, type TooltipProps } from 'recharts';
import type { Granularity, TopicTrends } from '../../api/types';
import { formatDate, formatMonth, formatShortDate } from '../../lib/format';
import { chart } from '../../theme/tokens';
import { ChartLegend, ChartTooltipCard, DataTableDisclosure } from '../charts/ChartTooltip';

export interface TopicSeries {
  topic: string;
  label: string;
  color: string;
}

interface TopicTrendChartProps {
  data: TopicTrends;
  selected: TopicSeries[];
  granularity: Granularity;
  unit: string;
}

type Row = { period_start: string; label: string } & Record<string, number | string>;

function periodLabel(start: string, granularity: Granularity, long = false) {
  if (granularity === 'month') return formatMonth(start);
  return long ? `Week of ${formatDate(start)}` : formatShortDate(start);
}

/** Pivot the long-format API series into one row per period. */
function pivot(data: TopicTrends, granularity: Granularity): Row[] {
  const rows = new Map<string, Row>();
  for (const point of data.series) {
    let row = rows.get(point.period_start);
    if (!row) {
      row = { period_start: point.period_start, label: periodLabel(point.period_start, granularity) };
      rows.set(point.period_start, row);
    }
    row[point.topic] = point.mentions;
  }
  return [...rows.values()].sort((a, b) => a.period_start.localeCompare(b.period_start));
}

export function TopicTrendChart({ data, selected, granularity, unit }: TopicTrendChartProps) {
  const rows = pivot(data, granularity);

  const renderTooltip = ({ active, payload }: TooltipProps<number, string>) => {
    const row = payload?.[0]?.payload as Row | undefined;
    if (!active || !row) return null;
    return (
      <ChartTooltipCard
        title={periodLabel(row.period_start, granularity, true)}
        rows={selected.map((s) => ({ label: s.label, value: `${Number(row[s.topic] ?? 0)} ${unit}`, color: s.color }))}
      />
    );
  };

  return (
    <div>
      <div className="mb-3">
        <ChartLegend items={selected.map((s) => ({ label: s.label, color: s.color, shape: 'line' as const }))} />
      </div>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
            <CartesianGrid vertical={false} stroke={chart.grid} />
            <XAxis dataKey="label" tick={{ fill: chart.axis, fontSize: 11 }} axisLine={{ stroke: chart.grid }} tickLine={false} minTickGap={16} />
            <YAxis tick={{ fill: chart.axis, fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} width={44} />
            <Tooltip content={renderTooltip} cursor={{ stroke: chart.axis, strokeWidth: 1 }} />
            {selected.map((s) => (
              <Line
                key={s.topic}
                type="monotone"
                dataKey={s.topic}
                name={s.label}
                stroke={s.color}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 5, fill: s.color, stroke: chart.surface, strokeWidth: 2 }}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <DataTableDisclosure caption={`Topic ${unit} by period`}>
        <thead className="text-ink-muted">
          <tr>
            <th className="py-1.5 pr-3 font-medium">{granularity === 'week' ? 'Week starting' : 'Month'}</th>
            {selected.map((s) => (
              <th key={s.topic} className="py-1.5 pr-3 text-right font-medium">{s.label}</th>
            ))}
          </tr>
        </thead>
        <tbody className="tabular">
          {rows.map((row) => (
            <tr key={row.period_start} className="border-t border-sand/50">
              <td className="py-1.5 pr-3">{row.label}</td>
              {selected.map((s) => (
                <td key={s.topic} className="py-1.5 pr-3 text-right">{Number(row[s.topic] ?? 0)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </DataTableDisclosure>
    </div>
  );
}
