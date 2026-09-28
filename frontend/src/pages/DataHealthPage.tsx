import { CalendarClock, Database, ShieldCheck, Sparkles } from 'lucide-react';
import type { ReactNode } from 'react';
import type { ScrapeRun } from '../api/types';
import { RunsList } from '../components/health/RunsList';
import { PageHeader } from '../components/layout/PageHeader';
import { Card, CardBody, CardHeader } from '../components/ui/Card';
import { Skeleton } from '../components/ui/Skeleton';
import { EmptyState, QueryView } from '../components/ui/States';
import { useMeta, useProperties, useScrapeRuns } from '../hooks/queries';
import { formatCount, formatDate, formatTimestamp, timeAgo } from '../lib/format';
import { runHealth } from '../lib/labels';

function lastSuccessful(runs: ScrapeRun[]): ScrapeRun | undefined {
  return runs
    .filter((r) => runHealth(r.status) === 'ok')
    .sort((a, b) => (b.finished_at ?? b.started_at).localeCompare(a.finished_at ?? a.started_at))[0];
}

export function DataHealthPage() {
  const meta = useMeta();
  const runs = useScrapeRuns();
  const properties = useProperties();
  const propertyNames = new Map((properties.data ?? []).map((p) => [p.id, p.short_name]));
  const success = runs.data ? lastSuccessful(runs.data) : undefined;

  return (
    <>
      <PageHeader
        eyebrow="Behind the numbers"
        title="Data health"
        description="Where the numbers come from, and whether the latest update worked."
      />

      <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Stat label="Reviews stored" value={meta.data ? formatCount(meta.data.total_reviews) : undefined}>
          {meta.data?.min_review_date && meta.data.max_review_date
            ? `${formatDate(meta.data.min_review_date)} to ${formatDate(meta.data.max_review_date)}`
            : ' '}
        </Stat>
        <Stat label="Last data update" value={meta.data ? timeAgo(meta.data.last_scraped_at) : undefined}>
          {meta.data ? formatTimestamp(meta.data.last_scraped_at) : ' '}
        </Stat>
        <Stat label="Last fully successful run" value={runs.data ? (success ? timeAgo(success.finished_at ?? success.started_at) : 'None recently') : undefined}>
          Updated nightly at midnight (Sydney).
        </Stat>
      </div>

      <div className="grid grid-cols-1 gap-6 2xl:grid-cols-12">
        <Card className="2xl:col-span-8" labelledBy="runs-title">
          <CardHeader id="runs-title" title="Recent updates" subtitle="One row per property per update run, newest first." />
          <CardBody>
            <QueryView
              query={runs}
              loadingLabel="Loading update history"
              skeleton={
                <div className="space-y-3">
                  {[0, 1, 2, 3].map((i) => (
                    <Skeleton key={i} className="h-12 w-full" />
                  ))}
                </div>
              }
              isEmpty={(d) => d.length === 0}
              empty={<EmptyState title="No updates recorded yet" message="Update runs will appear here once data collection has run." />}
            >
              {(data) => <RunsList runs={data} propertyNames={propertyNames} />}
            </QueryView>
          </CardBody>
        </Card>

        <Card className="2xl:col-span-4" labelledBy="how-title">
          <CardHeader id="how-title" title="How the data is collected" />
          <CardBody>
            <ul className="grid gap-5 text-sm leading-relaxed text-ink md:grid-cols-2 2xl:grid-cols-1">
              <Explainer icon={<CalendarClock className="h-4 w-4" aria-hidden="true" />} title="Every night">
                Every night at midnight (Sydney time), a scheduled job reads the public review pages of all four properties on
                Booking.com. It only fetches reviews newer than the ones we already have (“collected back to” in the table).
              </Explainer>
              <Explainer icon={<Database className="h-4 w-4" aria-hidden="true" />} title="No duplicates">
                Each review is stored once. If a guest edits a review, or the hotel replies, the stored copy is updated
                rather than duplicated.
              </Explainer>
              <Explainer icon={<Sparkles className="h-4 w-4" aria-hidden="true" />} title="Topics and tone">
                Each review is tagged with topics (such as cleanliness or noise) and an overall tone. Tagging is automatic,
                so the occasional review may be mis-tagged. Always read the reviews behind an important decision.
              </Explainer>
              <Explainer icon={<ShieldCheck className="h-4 w-4" aria-hidden="true" />} title="Limits">
                Booking.com has no official API for this, so if Booking changes its pages or blocks access, an update can
                fail or be partial. Failed properties are retried the next day. Reviewer names are never stored.
              </Explainer>
            </ul>
          </CardBody>
        </Card>
      </div>
    </>
  );
}

function Stat({ label, value, children }: { label: string; value: string | undefined; children: ReactNode }) {
  return (
    <div className="card p-5">
      <p className="text-sm font-medium text-ink-muted">{label}</p>
      {value === undefined ? (
        <Skeleton className="mt-2 h-8 w-28" />
      ) : (
        <p className="mt-1 font-display text-2xl font-medium text-navy">{value}</p>
      )}
      <p className="mt-2 text-xs text-ink-muted">{children}</p>
    </div>
  );
}

function Explainer({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <li className="flex gap-3">
      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-cream text-bronze">{icon}</span>
      <div>
        <p className="font-medium text-navy">{title}</p>
        <p className="mt-0.5 text-ink-muted">{children}</p>
      </div>
    </li>
  );
}
