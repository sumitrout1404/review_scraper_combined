import { CalendarClock } from 'lucide-react';
import { useMemo, useState } from 'react';
import type { Granularity, ScopeParams } from '../api/types';
import { FilterBar } from '../components/filters/FilterBar';
import { PageHeader } from '../components/layout/PageHeader';
import { InsightsList } from '../components/overview/InsightsPanel';
import { KpiCards, KpiCardsSkeleton } from '../components/overview/KpiCards';
import { PropertyComparison } from '../components/overview/PropertyComparison';
import { TopicBars } from '../components/overview/TopicBars';
import { TrendChart } from '../components/overview/TrendChart';
import { Button } from '../components/ui/Button';
import { Card, CardBody, CardHeader } from '../components/ui/Card';
import { InfoTip } from '../components/ui/InfoTip';
import { SegmentedControl } from '../components/ui/SegmentedControl';
import { Skeleton } from '../components/ui/Skeleton';
import { QueryView } from '../components/ui/States';
import { useInsights, useMeta, useProperties, useSummary, useTopicBreakdown, useTrends } from '../hooks/queries';
import { useGlobalFilters, type GlobalFilters } from '../hooks/useGlobalFilters';
import { daysInclusive, isLastPeriodInProgress, trendWindow } from '../lib/dates';
import { formatDateRange, plural } from '../lib/format';

const GRANULARITY_OPTIONS = [
  { value: 'week', label: 'Weekly' },
  { value: 'month', label: 'Monthly' },
] as const;

export function OverviewPage() {
  const filters = useGlobalFilters();
  const { scope } = filters;

  return (
    <>
      <PageHeader
        eyebrow="Azzurro Hotels · Sydney"
        title="Overview"
        description="How guests rated their stays on Booking.com, and what needs your attention."
      />
      <FilterBar filters={filters} />
      <ShortPeriodHint filters={filters} />

      <section aria-label="Key numbers" className="mb-8">
        <SummarySection scope={scope} />
      </section>

      <div className="mb-8 grid grid-cols-1 gap-6 lg:grid-cols-12">
        <InsightsSection scope={scope} />
        <TrendSection filters={filters} />
      </div>

      <PropertiesSection filters={filters} />

      <TopicsSection scope={scope} />
    </>
  );
}

/** Early in the week "This week" covers very few days; suggest a fuller view. */
function ShortPeriodHint({ filters }: { filters: GlobalFilters }) {
  if (filters.preset !== 'this_week' || !filters.range) return null;
  const days = daysInclusive(filters.range.from, filters.range.to);
  if (days > 2) return null;
  return (
    <div className="-mt-4 mb-6 flex flex-col gap-3 rounded-2xl border border-sand bg-cream/70 px-4 py-3 text-sm sm:flex-row sm:items-center">
      <CalendarClock className="hidden h-5 w-5 shrink-0 text-bronze sm:block" aria-hidden="true" />
      <p className="flex-1 text-ink">
        The week has only just started ({plural(days, 'day')} so far), so these numbers are based on few reviews.
      </p>
      <div className="flex gap-2">
        <Button size="sm" onClick={() => filters.setPreset('last_week')}>
          See last week
        </Button>
        <Button size="sm" onClick={() => filters.setPreset('last_7')}>
          Last 7 days
        </Button>
      </div>
    </div>
  );
}

function SummarySection({ scope }: { scope: ScopeParams | null }) {
  const summary = useSummary(scope);
  return (
    <QueryView query={summary} loadingLabel="Loading key numbers" skeleton={<KpiCardsSkeleton />}>
      {(data) => <KpiCards summary={data} />}
    </QueryView>
  );
}

function InsightsSection({ scope }: { scope: ScopeParams | null }) {
  const insights = useInsights(scope);
  return (
    <Card className="lg:col-span-5" labelledBy="insights-title">
      <CardHeader
        id="insights-title"
        title="What needs attention"
        subtitle="Automatic observations for the selected dates, most urgent first."
        info={
          <InfoTip topic="What needs attention">
            <p>These notes are generated from the reviews using simple, transparent rules, e.g. a complaint topic rising compared with the previous period.</p>
            <p>Statements based on fewer than 5 reviews are marked “Low sample” or left out.</p>
          </InfoTip>
        }
      />
      <CardBody>
        <QueryView
          query={insights}
          loadingLabel="Loading insights"
          skeleton={
            <div className="space-y-3">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-24 w-full" />
              ))}
            </div>
          }
        >
          {(data) => <InsightsList insights={data} />}
        </QueryView>
      </CardBody>
    </Card>
  );
}

function TrendSection({ filters }: { filters: GlobalFilters }) {
  const [granularity, setGranularity] = useState<Granularity>('week');
  const trendRange = useMemo(() => (filters.range ? trendWindow(filters.range, granularity) : null), [filters.range, granularity]);
  const scope = useMemo<ScopeParams | null>(
    () => (trendRange && filters.scope ? { ...filters.scope, date_from: trendRange.from, date_to: trendRange.to } : null),
    [trendRange, filters.scope],
  );
  const trends = useTrends(scope, granularity);
  const meta = useMeta();

  return (
    <Card className="lg:col-span-7" labelledBy="trend-title">
      <CardHeader
        id="trend-title"
        title="Trend"
        subtitle={trendRange ? `${formatDateRange(trendRange.from, trendRange.to)} · positive and negative reviews over time` : ' '}
        info={
          <InfoTip topic="Trend" align="right">
            <p>To show a meaningful trend, this chart always covers at least the last 12 {granularity === 'week' ? 'weeks' : 'months'} up to your selected end date.</p>
            <p>Weeks run Monday to Sunday. Periods with no reviews show a gap in the score line.</p>
          </InfoTip>
        }
        actions={<SegmentedControl label="Group by" value={granularity} options={GRANULARITY_OPTIONS} onChange={setGranularity} />}
      />
      <CardBody>
        <QueryView
          query={trends}
          loadingLabel="Loading trend"
          skeleton={<Skeleton className="h-[26rem] w-full" />}
          isEmpty={(d) => d.series.every((p) => p.count === 0)}
        >
          {(data) => (
            <TrendChart
              series={data.series}
              granularity={data.granularity}
              lastPeriodInProgress={isLastPeriodInProgress(data.series, data.granularity, meta.data?.today)}
            />
          )}
        </QueryView>
      </CardBody>
    </Card>
  );
}

function PropertiesSection({ filters }: { filters: GlobalFilters }) {
  // Always compare all four properties, whatever is selected, so the cards act as a switcher.
  const scope = useMemo<ScopeParams | null>(
    () => (filters.scope ? { date_from: filters.scope.date_from, date_to: filters.scope.date_to } : null),
    [filters.scope],
  );
  const summary = useSummary(scope);
  const properties = useProperties();
  const selectOne = (id: string) =>
    filters.setProperties(filters.properties.length === 1 && filters.properties[0] === id ? [] : [id]);

  return (
    <section className="mb-8" aria-labelledby="properties-title">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
        <div>
          <div className="flex items-center gap-1.5">
            <h2 id="properties-title" className="text-xl font-medium">
              Property by property
            </h2>
            <InfoTip topic="Property by property">
              <p>Each card shows the guest score for the selected dates and the change against the previous period.</p>
              <p>Click a card to focus the whole dashboard on that property; click it again to see all properties.</p>
              <p>The Booking.com headline score is Booking’s own long-term weighted score, shown for reference.</p>
            </InfoTip>
          </div>
          <p className="mt-1 text-sm text-ink-muted">Ranked by guest score. Click a property to focus on it.</p>
        </div>
      </div>
      <QueryView
        query={summary}
        loadingLabel="Loading properties"
        skeleton={
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-60 w-full rounded-2xl" />
            ))}
          </div>
        }
      >
        {(data) => (
          <PropertyComparison
            rows={data.by_property}
            properties={properties.data ?? []}
            selected={filters.properties}
            onSelect={selectOne}
          />
        )}
      </QueryView>
    </section>
  );
}

function TopicsSection({ scope }: { scope: ScopeParams | null }) {
  const breakdown = useTopicBreakdown(scope);
  const skeleton = (
    <div className="space-y-4">
      {[0, 1, 2, 3, 4].map((i) => (
        <Skeleton key={i} className="h-8 w-full" />
      ))}
    </div>
  );

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <Card labelledBy="complaints-title">
        <CardHeader
          id="complaints-title"
          title="Top complaints"
          subtitle={
            breakdown.data
              ? `Share of the ${plural(breakdown.data.negative_reviews, 'negative review')} that mention each topic`
              : 'Share of negative reviews that mention each topic'
          }
          info={
            <InfoTip topic="Top complaints">
              <p>We read the “disliked” part of each review and tag the topics it mentions, like cleanliness or noise.</p>
              <p>
                The percentage is: negative reviews complaining about the topic ÷ all negative reviews. A review can
                mention several topics, so the numbers don’t add up to 100%.
              </p>
            </InfoTip>
          }
        />
        <CardBody>
          <QueryView
            query={breakdown}
            loadingLabel="Loading complaints"
            skeleton={skeleton}
            isEmpty={(d) => d.total_reviews === 0}
          >
            {(data) => <TopicBars items={data.items} polarity="negative" />}
          </QueryView>
        </CardBody>
      </Card>
      <Card labelledBy="praise-title">
        <CardHeader
          id="praise-title"
          title="Top praise"
          subtitle="What guests liked most, by number of mentions"
          info={
            <InfoTip topic="Top praise" align="right">
              <p>Topics mentioned in the “liked” part of reviews. Bars are relative to the most-praised topic.</p>
            </InfoTip>
          }
        />
        <CardBody>
          <QueryView
            query={breakdown}
            loadingLabel="Loading praise"
            skeleton={skeleton}
            isEmpty={(d) => d.total_reviews === 0}
          >
            {(data) => <TopicBars items={data.items} polarity="positive" />}
          </QueryView>
        </CardBody>
      </Card>
    </div>
  );
}
