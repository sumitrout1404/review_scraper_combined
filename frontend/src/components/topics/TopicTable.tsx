import clsx from 'clsx';
import { ArrowDownRight, ArrowUpRight, ChevronRight, Minus } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import type { Polarity, TopicBreakdownItem } from '../../api/types';
import { formatPct } from '../../lib/format';
import { pickGlobal, withParams } from '../../lib/urlParams';

function useReviewsLink() {
  const [params] = useSearchParams();
  return (topic: string, polarity?: Polarity) => ({
    pathname: '/reviews',
    search: withParams(pickGlobal(params), { topic, polarity }).toString(),
  });
}

function Net({ value }: { value: number }) {
  const Icon = value > 0 ? ArrowUpRight : value < 0 ? ArrowDownRight : Minus;
  const text = value > 0 ? `+${value} more praise` : value < 0 ? `${Math.abs(value)} more complaints` : 'Balanced';
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 text-xs font-medium',
        value > 0 ? 'text-positive' : value < 0 ? 'text-negative' : 'text-neutral-dark',
      )}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      {text}
    </span>
  );
}

/** Topic breakdown: a table on wide screens, stacked cards on phones. */
export function TopicTable({ items }: { items: TopicBreakdownItem[] }) {
  const link = useReviewsLink();

  return (
    <>
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Complaints and praise by topic</caption>
          <thead className="border-b border-sand text-xs uppercase tracking-wide text-ink-muted">
            <tr>
              <th scope="col" className="py-3 pr-4 font-medium">Topic</th>
              <th scope="col" className="py-3 pr-4 text-right font-medium">Complaints</th>
              <th scope="col" className="py-3 pr-4 text-right font-medium">Praise</th>
              <th scope="col" className="py-3 pr-4 font-medium">Share of negative reviews</th>
              <th scope="col" className="py-3 pr-4 font-medium">Balance</th>
              <th scope="col" className="py-3"><span className="sr-only">Open reviews</span></th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.topic} className="border-b border-sand/50 last:border-0 hover:bg-cream/40">
                <th scope="row" className="py-3 pr-4 font-medium text-navy">
                  <Link to={link(item.topic)} className="focus-ring rounded hover:underline">
                    {item.label}
                  </Link>
                </th>
                <td className="py-3 pr-4 text-right tabular">
                  <Link to={link(item.topic, 'negative')} className="focus-ring rounded font-medium text-negative hover:underline" aria-label={`${item.negative_mentions} complaints about ${item.label}`}>
                    {item.negative_mentions}
                  </Link>
                </td>
                <td className="py-3 pr-4 text-right tabular">
                  <Link to={link(item.topic, 'positive')} className="focus-ring rounded font-medium text-positive hover:underline" aria-label={`${item.positive_mentions} praise mentions for ${item.label}`}>
                    {item.positive_mentions}
                  </Link>
                </td>
                <td className="py-3 pr-4">
                  <ShareBar pct={item.pct_of_negative_reviews} />
                </td>
                <td className="py-3 pr-4">
                  <Net value={item.net} />
                </td>
                <td className="py-3 text-right">
                  <Link to={link(item.topic)} className="focus-ring inline-flex rounded-full p-1 text-ink-muted hover:bg-cream hover:text-navy" aria-label={`Read reviews about ${item.label}`}>
                    <ChevronRight className="h-4 w-4" aria-hidden="true" />
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="space-y-3 md:hidden">
        {items.map((item) => (
          <li key={item.topic}>
            <Link to={link(item.topic)} className="focus-ring block rounded-xl border border-sand/70 p-4 hover:bg-cream/40">
              <span className="flex items-center justify-between">
                <span className="font-medium text-navy">{item.label}</span>
                <ChevronRight className="h-4 w-4 text-ink-muted" aria-hidden="true" />
              </span>
              <span className="mt-2 flex gap-4 text-sm">
                <span className="text-negative"><span className="font-semibold">{item.negative_mentions}</span> complaints</span>
                <span className="text-positive"><span className="font-semibold">{item.positive_mentions}</span> praise</span>
              </span>
              <span className="mt-3 block">
                <span className="mb-1 block text-xs text-ink-muted">Share of negative reviews</span>
                <ShareBar pct={item.pct_of_negative_reviews} />
              </span>
              <span className="mt-2 block">
                <Net value={item.net} />
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}

function ShareBar({ pct }: { pct: number }) {
  return (
    <span className="flex items-center gap-2">
      <span className="h-2 w-full max-w-[10rem] overflow-hidden rounded-full bg-offwhite" aria-hidden="true">
        <span className="block h-full rounded-full bg-negative" style={{ width: `${Math.min(100, Math.max(pct > 0 ? 2 : 0, pct))}%` }} />
      </span>
      <span className="w-10 shrink-0 text-right text-xs font-medium tabular">{formatPct(pct)}</span>
    </span>
  );
}
