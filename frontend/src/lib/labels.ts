import type { ReviewSort, RunTrigger, Sentiment, Severity } from '../api/types';

/** Plain-language names used across the UI. */
export const SENTIMENT_LABEL: Record<Sentiment, string> = {
  positive: 'Positive',
  neutral: 'Mixed',
  negative: 'Negative',
};

export const SORT_LABEL: Record<ReviewSort, string> = {
  date_desc: 'Newest first',
  date_asc: 'Oldest first',
  score_desc: 'Highest score',
  score_asc: 'Lowest score',
};

export const SEVERITY_LABEL: Record<Severity, string> = {
  alert: 'Needs attention',
  warning: 'Keep an eye on',
  info: 'Good to know',
  positive: 'Going well',
};

/** Order in which insights are shown: most urgent first. */
export const SEVERITY_RANK: Record<Severity, number> = { alert: 0, warning: 1, info: 2, positive: 3 };

export type RunHealth = 'ok' | 'partial' | 'failed' | 'running' | 'skipped' | 'unknown';

/** Maps the collector's run status to a simple health level. */
export function runHealth(status: string | null | undefined): RunHealth {
  const s = (status ?? '').toLowerCase();
  if (['success', 'succeeded', 'ok', 'completed'].includes(s)) return 'ok';
  if (['partial', 'degraded'].includes(s)) return 'partial';
  if (['failed', 'error', 'blocked'].includes(s)) return 'failed';
  if (['running', 'started', 'in_progress'].includes(s)) return 'running';
  if (s === 'skipped') return 'skipped';
  return 'unknown';
}

export const RUN_HEALTH_LABEL: Record<RunHealth, string> = {
  ok: 'Succeeded',
  partial: 'Partly succeeded',
  failed: 'Failed',
  running: 'Running',
  skipped: 'Skipped (another run was in progress)',
  unknown: 'Unknown',
};

export const TRIGGER_LABEL: Record<RunTrigger, string> = {
  cron: 'Daily schedule',
  cli: 'Command line',
  manual: 'Manual',
};
