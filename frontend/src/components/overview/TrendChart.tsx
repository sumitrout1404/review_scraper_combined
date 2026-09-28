import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, type TooltipProps } from 'recharts';
import type { Granularity, TrendPoint } from '../../api/types';
import { formatDate, formatMonth, formatScore, formatShortDate } from '../../lib/format';
import { chart, colors } from '../../theme/tokens';
import { ChartLegend, ChartTooltipCard, DataTableDisclosure } from '../charts/ChartTooltip';

interface TrendChartProps {
  series: TrendPoint[];
  granularity: Granularity;
  /** True when the last period has not finished yet (so it has fewer reviews). */
  lastPeriodInProgress: boolean;
}

const SYNC_ID = 'overview-trend';
const AXIS_TICK = { fill: chart.axis, fontSize: 11 };

function periodLabel(periodStart: string, granularity: Granularity, long = false): string {
  if (granularity === 'month') return formatMonth(periodStart);
  return long ? `Week of ${formatDate(periodStart)}` : formatShortDate(periodStart);
}

/** Y axis from an even number just below the lowest score up to 10, ticked every 2 points. */
function scoreTicks(series: TrendPoint[]): number[] {
  const scores = series.map((p) => p.avg_score).filter((s): s is number => s !== null);
  const low = scores.length === 0 ? 0 : Math.max(0, Math.floor((Math.min(...scores) - 0.5) / 2) * 2);
  const ticks: number[] = [];
  for (let t = low; t <= 10; t += 2) ticks.push(t);
  return ticks;
}

/**
 * Two aligned charts sharing one time axis: guest score on top, review volume
 * by sentiment below. Kept separate (not a dual-axis chart) so neither scale
 * distorts the other.
 */
export function TrendChart({ series, granularity, lastPeriodInProgress }: TrendChartProps) {
  const data = series.map((p) => ({ ...p, label: periodLabel(p.period_start, granularity) }));
  const ticks = scoreTicks(series);

  const renderTooltip = ({ active, payload }: TooltipProps<number, string>) => {
    const point = payload?.[0]?.payload as (TrendPoint & { label: string }) | undefined;
    if (!active || !point) return null;
    return (
      <ChartTooltipCard
        title={periodLabel(point.period_start, granularity, true)}
        rows={[
          { label: 'Guest score', value: formatScore(point.avg_score), color: colors.navy },
          { label: 'Positive', value: String(point.positive), color: colors.positive },
          { label: 'Mixed', value: String(point.neutral), color: colors.neutral },
          { label: 'Negative', value: String(point.negative), color: colors.negative },
        ]}
        footer={`${point.count} review${point.count === 1 ? '' : 's'} in total`}
      />
    );
  };

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <p className="text-xs font-medium text-ink">Guest score (out of 10)</p>
      </div>
      <div className="h-44 sm:h-52">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} syncId={SYNC_ID} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
            <CartesianGrid vertical={false} stroke={chart.grid} />
            <XAxis dataKey="label" tick={false} axisLine={{ stroke: chart.grid }} tickLine={false} height={4} />
            <YAxis domain={[ticks[0] ?? 0, 10]} ticks={ticks} tick={AXIS_TICK} axisLine={false} tickLine={false} allowDecimals={false} width={44} />
            <Tooltip content={renderTooltip} cursor={{ stroke: colors.bronze, strokeWidth: 1 }} />
            <Line
              type="monotone"
              dataKey="avg_score"
              name="Guest score"
              stroke={colors.navy}
              strokeWidth={2}
              dot={{ r: 3.5, fill: colors.navy, stroke: chart.surface, strokeWidth: 2 }}
              activeDot={{ r: 5, fill: colors.navy, stroke: chart.surface, strokeWidth: 2 }}
              connectNulls={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="mb-2 mt-5 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-medium text-ink">Number of reviews by tone</p>
        <ChartLegend
          items={[
            { label: 'Positive', color: colors.positive },
            { label: 'Mixed', color: colors.neutral },
            { label: 'Negative', color: colors.negative },
          ]}
        />
      </div>
      <div className="h-40 sm:h-44">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} syncId={SYNC_ID} margin={{ top: 4, right: 12, bottom: 0, left: -18 }}>
            <CartesianGrid vertical={false} stroke={chart.grid} />
            <XAxis dataKey="label" tick={AXIS_TICK} axisLine={{ stroke: chart.grid }} tickLine={false} interval="preserveStartEnd" minTickGap={16} />
            <YAxis tick={AXIS_TICK} axisLine={false} tickLine={false} allowDecimals={false} width={44} />
            <Tooltip content={renderTooltip} cursor={{ fill: colors.cream, opacity: 0.6 }} />
            <Bar dataKey="positive" stackId="tone" fill={colors.positive} maxBarSize={24} stroke={chart.surface} strokeWidth={1} isAnimationActive={false} />
            <Bar dataKey="neutral" stackId="tone" fill={colors.neutral} maxBarSize={24} stroke={chart.surface} strokeWidth={1} isAnimationActive={false} />
            <Bar dataKey="negative" stackId="tone" fill={colors.negative} maxBarSize={24} radius={[4, 4, 0, 0]} stroke={chart.surface} strokeWidth={1} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {lastPeriodInProgress && (
        <p className="mt-3 text-xs text-ink-muted">
          The latest {granularity} is still in progress, so its numbers are based on fewer reviews and may change.
        </p>
      )}

      <DataTableDisclosure caption="Guest score and review counts by period">
        <thead className="text-ink-muted">
          <tr>
            <th className="py-1.5 pr-3 font-medium">{granularity === 'week' ? 'Week starting' : 'Month'}</th>
            <th className="py-1.5 pr-3 text-right font-medium">Guest score</th>
            <th className="py-1.5 pr-3 text-right font-medium">Reviews</th>
            <th className="py-1.5 pr-3 text-right font-medium">Positive</th>
            <th className="py-1.5 pr-3 text-right font-medium">Mixed</th>
            <th className="py-1.5 text-right font-medium">Negative</th>
          </tr>
        </thead>
        <tbody className="tabular">
          {series.map((p) => (
            <tr key={p.period_start} className="border-t border-sand/50">
              <td className="py-1.5 pr-3">{periodLabel(p.period_start, granularity, false)}</td>
              <td className="py-1.5 pr-3 text-right">{formatScore(p.avg_score)}</td>
              <td className="py-1.5 pr-3 text-right">{p.count}</td>
              <td className="py-1.5 pr-3 text-right">{p.positive}</td>
              <td className="py-1.5 pr-3 text-right">{p.neutral}</td>
              <td className="py-1.5 text-right">{p.negative}</td>
            </tr>
          ))}
        </tbody>
      </DataTableDisclosure>
    </div>
  );
}
