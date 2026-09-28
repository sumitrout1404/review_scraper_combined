import { Tags } from 'lucide-react';
import { useMemo, useState } from 'react';
import type { Granularity, Polarity, ScopeParams, TopicBreakdownItem } from '../api/types';
import { FilterBar } from '../components/filters/FilterBar';
import { PageHeader } from '../components/layout/PageHeader';
import { Card, CardBody, CardHeader } from '../components/ui/Card';
import { InfoTip } from '../components/ui/InfoTip';
import { SegmentedControl } from '../components/ui/SegmentedControl';
import { Skeleton } from '../components/ui/Skeleton';
import { EmptyState, QueryView } from '../components/ui/States';
import { TopicPicker } from '../components/topics/TopicPicker';
import { TopicTable } from '../components/topics/TopicTable';
import { TopicTrendChart } from '../components/topics/TopicTrendChart';
import { useTopicBreakdown, useTopics, useTopicTrends } from '../hooks/queries';
import { useGlobalFilters, type GlobalFilters } from '../hooks/useGlobalFilters';
import { trendWindow } from '../lib/dates';
import { formatDateRange, plural } from '../lib/format';
import { categorical } from '../theme/tokens';

const DEFAULT_TOPIC_COUNT = 3;
const GRANULARITY_OPTIONS = [
  { value: 'week', label: 'Weekly' },
  { value: 'month', label: 'Monthly' },
] as const;
const POLARITY_OPTIONS = [
  { value: 'negative', label: 'Complaints' },
  { value: 'positive', label: 'Praise' },
] as const;

export function TopicsPage() {
  const filters = useGlobalFilters();
  const breakdown = useTopicBreakdown(filters.scope);

  return (
    <>
      <PageHeader
        eyebrow="Operational themes"
        title="Topics"
        description="The recurring things guests complain about or praise, such as cleanliness, noise or check-in."
      />
      <FilterBar filters={filters} showComparison={false} />

      <Card className="mb-8" labelledBy="breakdown-title">
        <CardHeader
          id="breakdown-title"
          title="Complaints and praise by topic"
          subtitle={
            breakdown.data
              ? `${plural(breakdown.data.total_reviews, 'review')}, of which ${plural(breakdown.data.negative_reviews, 'was', 'were')} negative. Click a topic to read the reviews.`
              : 'Click a topic to read the reviews.'
          }
          info={
            <InfoTip topic="Complaints and praise by topic">
              <p><strong>Complaints</strong>: mentions of the topic in the “disliked” part of reviews. <strong>Praise</strong>: mentions in the “liked” part.</p>
              <p><strong>Share of negative reviews</strong>: negative reviews that complain about this topic ÷ all negative reviews.</p>
              <p><strong>Balance</strong>: praise minus complaints. Topics are tagged automatically, so a few may be missed or mis-tagged.</p>
            </InfoTip>
          }
        />
        <CardBody>
          <QueryView
            query={breakdown}
            loadingLabel="Loading topics"
            skeleton={
              <div className="space-y-3">
                {[0, 1, 2, 3, 4, 5].map((i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            }
            isEmpty={(d) => d.total_reviews === 0 || d.items.every((i) => i.negative_mentions + i.positive_mentions === 0)}
            empty={
              breakdown.data && breakdown.data.total_reviews > 0 ? (
                <EmptyState
                  icon={<Tags className="h-5 w-5" aria-hidden="true" />}
                  title="No topics tagged yet"
                  message="These reviews haven’t been tagged with topics yet. Tagging runs after each nightly update, so check back later or widen the date range."
                />
              ) : undefined
            }
          >
            {(data) => <TopicTable items={data.items} />}
          </QueryView>
        </CardBody>
      </Card>

      <TopicTrendSection filters={filters} breakdownItems={breakdown.data?.items} />
    </>
  );
}

function defaultSlots(items: TopicBreakdownItem[] | undefined): (string | null)[] {
  const slots: (string | null)[] = Array.from({ length: categorical.length }, () => null);
  (items ?? []).slice(0, DEFAULT_TOPIC_COUNT).forEach((item, i) => (slots[i] = item.topic));
  return slots;
}

function TopicTrendSection({ filters, breakdownItems }: { filters: GlobalFilters; breakdownItems?: TopicBreakdownItem[] }) {
  const topics = useTopics();
  const [granularity, setGranularity] = useState<Granularity>('week');
  const [polarity, setPolarity] = useState<Polarity>('negative');
  // null until the user picks topics; until then default to the most-complained-about ones.
  const [userSlots, setUserSlots] = useState<(string | null)[] | null>(null);
  const slots = userSlots ?? defaultSlots(breakdownItems);

  const toggle = (topic: string) => {
    const next = [...slots];
    const at = next.indexOf(topic);
    if (at !== -1) next[at] = null;
    else {
      const free = next.indexOf(null);
      if (free === -1) return;
      next[free] = topic;
    }
    setUserSlots(next);
  };

  const trendRange = useMemo(() => (filters.range ? trendWindow(filters.range, granularity) : null), [filters.range, granularity]);
  const scope = useMemo<ScopeParams | null>(
    () => (trendRange && filters.scope ? { ...filters.scope, date_from: trendRange.from, date_to: trendRange.to } : null),
    [trendRange, filters.scope],
  );
  const trends = useTopicTrends(scope, granularity, polarity);

  const labelFor = new Map((topics.data ?? []).map((t) => [t.key, t.label]));
  const selected = slots.flatMap((topic, i) =>
    topic ? [{ topic, label: labelFor.get(topic) ?? topic, color: categorical[i] ?? categorical[0] }] : [],
  );

  return (
    <Card labelledBy="topic-trend-title">
      <CardHeader
        id="topic-trend-title"
        title="Topics over time"
        subtitle={trendRange ? `${formatDateRange(trendRange.from, trendRange.to)} · number of ${polarity === 'negative' ? 'complaints' : 'praise mentions'} per ${granularity}` : ' '}
        info={
          <InfoTip topic="Topics over time" align="right">
            <p>Shows how often each topic is mentioned over time, so you can see whether an issue is getting better or worse after a change on site.</p>
            <p>The chart covers at least 12 {granularity === 'week' ? 'weeks' : 'months'} up to your selected end date.</p>
          </InfoTip>
        }
        actions={
          <>
            <SegmentedControl label="Show" value={polarity} options={POLARITY_OPTIONS} onChange={setPolarity} />
            <SegmentedControl label="Group by" value={granularity} options={GRANULARITY_OPTIONS} onChange={setGranularity} />
          </>
        }
      />
      <CardBody>
        <div className="mb-5">
          <TopicPicker topics={topics.data ?? []} slots={slots} colors={categorical} onToggle={toggle} />
        </div>
        {selected.length === 0 ? (
          <EmptyState compact icon={<Tags className="h-5 w-5" aria-hidden="true" />} title="Pick a topic" message="Choose one or more topics above to see how they change over time." />
        ) : (
          <QueryView
            query={trends}
            loadingLabel="Loading topic trends"
            skeleton={<Skeleton className="h-72 w-full" />}
            isEmpty={(d) => d.series.every((p) => p.mentions === 0 || !slots.includes(p.topic))}
          >
            {(data) => (
              <TopicTrendChart
                data={data}
                selected={selected}
                granularity={granularity}
                unit={polarity === 'negative' ? 'complaints' : 'praise'}
              />
            )}
          </QueryView>
        )}
      </CardBody>
    </Card>
  );
}
