import type { ScrapeRun } from '../../api/types';
import { formatDate, formatTimestamp, timeAgo } from '../../lib/format';
import { TRIGGER_LABEL } from '../../lib/labels';
import { RunStatusBadge } from './RunStatusBadge';

interface RunsListProps {
  runs: ScrapeRun[];
  propertyNames: Map<string, string>;
}

function counts(run: ScrapeRun): string {
  const parts = [`${run.reviews_new ?? 0} new`, `${run.reviews_updated ?? 0} updated`];
  if (run.reviews_rejected) parts.push(`${run.reviews_rejected} rejected`);
  return parts.join(' · ');
}

function triggerText(run: ScrapeRun): string {
  return run.trigger ? TRIGGER_LABEL[run.trigger] ?? run.trigger : '–';
}

/** Recent collection runs: a table on wide screens, cards on phones. */
export function RunsList({ runs, propertyNames }: RunsListProps) {
  const name = (id: string | null) => (id ? propertyNames.get(id) ?? id : 'All properties');

  return (
    <>
      <div className="hidden overflow-x-auto lg:block">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Recent data collection runs</caption>
          <thead className="border-b border-sand text-xs uppercase tracking-wide text-ink-muted">
            <tr>
              <th scope="col" className="py-3 pr-4 font-medium">Started</th>
              <th scope="col" className="py-3 pr-4 font-medium">Property</th>
              <th scope="col" className="py-3 pr-4 font-medium">Status</th>
              <th scope="col" className="py-3 pr-4 font-medium">Started by</th>
              <th scope="col" className="py-3 pr-4 font-medium">Reviews</th>
              <th scope="col" className="py-3 pr-4 font-medium">Pages</th>
              <th scope="col" className="py-3 font-medium">Collected back to</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={`${run.run_id}-${run.property_id ?? 'all'}`} className="border-b border-sand/50 align-top last:border-0">
                <td className="whitespace-nowrap py-3 pr-4">
                  <span className="block font-medium text-ink">{timeAgo(run.started_at)}</span>
                  <span className="block text-xs text-ink-muted">{formatTimestamp(run.started_at)}</span>
                </td>
                <td className="py-3 pr-4 text-ink">{name(run.property_id)}</td>
                <td className="py-3 pr-4">
                  <RunStatusBadge status={run.status} />
                  {run.error && <p className="mt-1 max-w-xs break-words text-xs text-negative">{run.error}</p>}
                </td>
                <td className="py-3 pr-4 text-ink-muted">
                  {triggerText(run)}
                  {run.mode && <span className="block text-xs">{run.mode === 'incremental' ? 'New reviews only' : run.mode}</span>}
                </td>
                <td className="whitespace-nowrap py-3 pr-4 text-ink tabular">{counts(run)}</td>
                <td className="py-3 pr-4 text-ink tabular">{run.pages_fetched ?? '–'}</td>
                <td className="whitespace-nowrap py-3 text-ink-muted">{run.watermark_date ? formatDate(run.watermark_date) : '–'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="space-y-3 lg:hidden">
        {runs.map((run) => (
          <li key={`${run.run_id}-${run.property_id ?? 'all'}`} className="rounded-xl border border-sand/70 p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-medium text-navy">{name(run.property_id)}</p>
                <p className="text-xs text-ink-muted">
                  {timeAgo(run.started_at)} · {triggerText(run)}
                </p>
              </div>
              <RunStatusBadge status={run.status} />
            </div>
            <p className="mt-2 text-sm text-ink">{counts(run)}</p>
            {run.watermark_date && (
              <p className="mt-1 text-xs text-ink-muted">Collected back to {formatDate(run.watermark_date)}</p>
            )}
            {run.error && <p className="mt-2 text-xs text-negative">{run.error}</p>}
          </li>
        ))}
      </ul>
    </>
  );
}
