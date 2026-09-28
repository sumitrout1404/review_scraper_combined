import clsx from 'clsx';
import { AlertOctagon, AlertTriangle, ArrowRight, Lightbulb, Sparkles, type LucideIcon } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import type { Insight, Severity } from '../../api/types';
import { SEVERITY_LABEL, SEVERITY_RANK } from '../../lib/labels';
import { pickGlobal, withParams } from '../../lib/urlParams';
import { LowSampleBadge } from '../common/LowSampleBadge';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/States';

const INITIAL_VISIBLE = 4;

const STYLES: Record<Severity, { icon: LucideIcon; bar: string; iconWrap: string; label: string }> = {
  alert: { icon: AlertOctagon, bar: 'bg-negative', iconWrap: 'bg-negative-soft text-negative', label: 'text-negative' },
  warning: { icon: AlertTriangle, bar: 'bg-warning', iconWrap: 'bg-warning-soft text-warning', label: 'text-warning' },
  info: { icon: Lightbulb, bar: 'bg-navy', iconWrap: 'bg-navy-50 text-navy', label: 'text-navy' },
  positive: { icon: Sparkles, bar: 'bg-positive', iconWrap: 'bg-positive-soft text-positive', label: 'text-positive' },
};

/** Plain-English callouts from /api/insights, most urgent first. */
export function InsightsList({ insights }: { insights: Insight[] }) {
  const [expanded, setExpanded] = useState(false);
  const sorted = useMemo(
    () => [...insights].sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity]),
    [insights],
  );

  if (sorted.length === 0) {
    return (
      <EmptyState
        compact
        title="Nothing stands out"
        message="There are no notable changes or recurring issues for these dates. Try a longer date range for more insight."
      />
    );
  }

  const visible = expanded ? sorted : sorted.slice(0, INITIAL_VISIBLE);
  return (
    <div>
      <ul className="space-y-3">
        {visible.map((insight) => (
          <li key={insight.id}>
            <InsightCallout insight={insight} />
          </li>
        ))}
      </ul>
      {sorted.length > INITIAL_VISIBLE && (
        <Button variant="ghost" size="sm" className="mt-3" onClick={() => setExpanded((v) => !v)} aria-expanded={expanded}>
          {expanded ? 'Show fewer' : `Show ${sorted.length - INITIAL_VISIBLE} more`}
        </Button>
      )}
    </div>
  );
}

function InsightCallout({ insight }: { insight: Insight }) {
  const [params] = useSearchParams();
  const style = STYLES[insight.severity];
  const Icon = style.icon;

  const target = insight.topic
    ? withParams(pickGlobal(params), {
        topic: insight.topic,
        polarity: insight.severity === 'positive' ? 'positive' : 'negative',
        properties: insight.property_id ? [insight.property_id] : params.get('properties'),
      })
    : null;

  return (
    <article className="relative flex gap-3 overflow-hidden rounded-xl border border-sand/70 bg-white py-3.5 pl-5 pr-4">
      <span className={clsx('absolute inset-y-0 left-0 w-1', style.bar)} aria-hidden="true" />
      <span className={clsx('mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full', style.iconWrap)}>
        <Icon className="h-4 w-4" aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className={clsx('text-[11px] font-semibold uppercase tracking-wide', style.label)}>
            {SEVERITY_LABEL[insight.severity]}
          </span>
          <LowSampleBadge count={insight.sample_size} />
        </div>
        <h3 className="mt-0.5 font-sans text-sm font-semibold text-navy">{insight.title}</h3>
        <p className="mt-1 text-sm leading-relaxed text-ink">{insight.text}</p>
        {target && (
          <Link
            to={{ pathname: '/reviews', search: target.toString() }}
            className="focus-ring mt-2 inline-flex items-center gap-1 rounded text-xs font-medium text-navy underline-offset-2 hover:underline"
          >
            Read these reviews <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        )}
      </div>
    </article>
  );
}
