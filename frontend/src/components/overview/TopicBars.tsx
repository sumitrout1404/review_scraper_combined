import clsx from 'clsx';
import { Link, useSearchParams } from 'react-router-dom';
import type { Polarity, TopicBreakdownItem } from '../../api/types';
import { formatPct, plural } from '../../lib/format';
import { pickGlobal, withParams } from '../../lib/urlParams';

interface TopicBarsProps {
  items: TopicBreakdownItem[];
  polarity: Polarity;
  limit?: number;
}

interface Row {
  topic: string;
  label: string;
  /** 0–100, drives the bar length. */
  share: number;
  valueText: string;
  detail: string;
}

function toRows(items: TopicBreakdownItem[], polarity: Polarity): Row[] {
  if (polarity === 'negative') {
    return items
      .filter((i) => i.negative_mentions > 0)
      .sort((a, b) => b.pct_of_negative_reviews - a.pct_of_negative_reviews || b.negative_mentions - a.negative_mentions)
      .map((i) => ({
        topic: i.topic,
        label: i.label,
        share: i.pct_of_negative_reviews,
        valueText: formatPct(i.pct_of_negative_reviews),
        detail: `${plural(i.negative_mentions, 'complaint')} in total`,
      }));
  }
  const max = Math.max(1, ...items.map((i) => i.positive_mentions));
  return items
    .filter((i) => i.positive_mentions > 0)
    .sort((a, b) => b.positive_mentions - a.positive_mentions)
    .map((i) => ({
      topic: i.topic,
      label: i.label,
      share: (i.positive_mentions / max) * 100,
      valueText: String(i.positive_mentions),
      detail: plural(i.positive_mentions, 'mention'),
    }));
}

/** Horizontal bar list; each row links to the matching reviews. */
export function TopicBars({ items, polarity, limit = 6 }: TopicBarsProps) {
  const [params] = useSearchParams();
  const rows = toRows(items, polarity).slice(0, limit);
  const complaint = polarity === 'negative';

  if (rows.length === 0) {
    return (
      <div className="py-6 text-center text-sm">
        <p className="font-medium text-navy">{complaint ? 'No complaint topics found' : 'No praise topics found'}</p>
        <p className="mx-auto mt-1 max-w-xs text-ink-muted">
          Either none were mentioned in this period, or topic tagging for newly collected reviews hasn’t finished yet.
        </p>
      </div>
    );
  }

  return (
    <ul className="space-y-1">
      {rows.map((row) => (
        <li key={row.topic}>
          <Link
            to={{ pathname: '/reviews', search: withParams(pickGlobal(params), { topic: row.topic, polarity }).toString() }}
            className="focus-ring group block rounded-xl px-2 py-2 hover:bg-cream/50"
            aria-label={`${row.label}: ${row.valueText}${complaint ? ' of negative reviews' : ' praise mentions'}. Read these reviews.`}
          >
            <span className="flex items-baseline justify-between gap-3 text-sm">
              <span className="font-medium text-navy group-hover:underline">{row.label}</span>
              <span className="shrink-0 text-xs text-ink-muted">
                <span className="mr-1.5 text-sm font-semibold text-ink tabular">{row.valueText}</span>
                {row.detail}
              </span>
            </span>
            <span className="mt-1.5 block h-2 overflow-hidden rounded-full bg-offwhite" aria-hidden="true">
              <span
                className={clsx('block h-full rounded-full', complaint ? 'bg-negative' : 'bg-positive')}
                style={{ width: `${Math.max(2, Math.min(100, row.share))}%` }}
              />
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
