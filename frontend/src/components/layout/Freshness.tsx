import clsx from 'clsx';
import { differenceInHours } from 'date-fns';
import { AlertTriangle, CheckCircle2, RefreshCw } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMeta } from '../../hooks/queries';
import { config } from '../../lib/config';
import { formatTimestamp, parseTimestamp, timeAgo } from '../../lib/format';
import { runHealth } from '../../lib/labels';
import { pickGlobal } from '../../lib/urlParams';

const SCHEDULE_NOTE = 'Updated nightly at midnight (Sydney)';

interface Freshness {
  tone: 'ok' | 'warning';
  headline: string;
  detail: string;
}

function assess(lastScrapedAt: string | null, lastRunStatus: string | null): Freshness {
  const last = parseTimestamp(lastScrapedAt);
  if (!last) {
    return { tone: 'warning', headline: 'No data collected yet', detail: 'Reviews have not been collected yet.' };
  }
  const stale = differenceInHours(new Date(), last) > config.staleAfterHours;
  const health = runHealth(lastRunStatus);
  const headline = `Data last updated ${timeAgo(lastScrapedAt)}`;
  if (stale) {
    return {
      tone: 'warning',
      headline,
      detail: `No successful update in over ${config.staleAfterHours} hours (updates normally run nightly at midnight, Sydney time), so recent reviews may be missing.`,
    };
  }
  if (health === 'failed' || health === 'partial') {
    return {
      tone: 'warning',
      headline,
      detail:
        health === 'failed'
          ? 'The latest collection run failed. Figures may be missing recent reviews.'
          : 'The latest collection run only partly succeeded. Some properties may be missing recent reviews.',
    };
  }
  return { tone: 'ok', headline, detail: `${SCHEDULE_NOTE} · ${formatTimestamp(lastScrapedAt)}` };
}

/** "Data last updated …" indicator with a warning when data is stale or the last run failed. */
export function FreshnessIndicator({ variant }: { variant: 'sidebar' | 'banner' }) {
  const meta = useMeta();
  const [params] = useSearchParams();

  if (!meta.data) {
    if (variant === 'banner') return null;
    return (
      <p className="flex items-center gap-2 text-xs text-sand/70">
        <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
        {meta.isError ? 'Data status unavailable' : 'Checking data status…'}
      </p>
    );
  }

  const status = assess(meta.data.last_scraped_at, meta.data.last_run_status);

  if (variant === 'sidebar') {
    const Icon = status.tone === 'ok' ? CheckCircle2 : AlertTriangle;
    return (
      <div className="text-xs">
        <p className={clsx('flex items-center gap-2 font-medium', status.tone === 'ok' ? 'text-sand' : 'text-[#ffc38a]')}>
          <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {status.headline}
        </p>
        <p className="mt-1 pl-5 text-sand/60">{status.detail}</p>
      </div>
    );
  }

  if (status.tone === 'ok') return null;
  return (
    <div role="status" className="mb-6 flex items-start gap-3 rounded-2xl border border-warning/30 bg-warning-soft px-4 py-3 text-sm">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden="true" />
      <p className="text-ink">
        <span className="font-medium">{status.headline}.</span> {status.detail}{' '}
        <Link
          to={{ pathname: '/data-health', search: pickGlobal(params).toString() }}
          className="focus-ring rounded font-medium text-navy underline underline-offset-2"
        >
          See data health
        </Link>
      </p>
    </div>
  );
}
