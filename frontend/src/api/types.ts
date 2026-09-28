/**
 * Types mirroring docs/CONTRACT.md. Keep in sync with the backend.
 * Dates are `YYYY-MM-DD` strings; timestamps are UTC ISO-8601 strings.
 */

export type ISODate = string;
export type Sentiment = 'positive' | 'neutral' | 'negative';
export type Polarity = 'positive' | 'negative';
export type Granularity = 'week' | 'month';
export type Severity = 'alert' | 'warning' | 'info' | 'positive';
export type ReviewSort = 'date_desc' | 'date_asc' | 'score_asc' | 'score_desc';

/** Fixed topic keys from the contract (labels come from /api/topics). */
export const TOPIC_KEYS = [
  'cleanliness',
  'check_in',
  'staff',
  'noise',
  'facilities',
  'location',
  'room_condition',
  'value_for_money',
  'bathroom',
  'bed_comfort',
  'wifi',
  'breakfast_food',
] as const;
export type TopicKey = (typeof TOPIC_KEYS)[number];

export interface Health {
  status: string;
  db: { reviews: number; last_scraped_at: string | null };
}

export interface Meta {
  today: ISODate;
  this_week_start: ISODate;
  min_review_date: ISODate | null;
  max_review_date: ISODate | null;
  last_scraped_at: string | null;
  last_run_status: string | null;
  total_reviews: number;
}

export interface Property {
  id: string;
  name: string;
  short_name: string;
  booking_url: string;
  booking_score: number | null;
  total_reviews: number;
  avg_score: number | null;
}

export interface Topic {
  key: string;
  label: string;
  description: string | null;
}

export interface PeriodStats {
  count: number;
  avg_score: number | null;
  positive: number;
  neutral: number;
  negative: number;
  pct_positive: number;
  pct_negative: number;
}

export interface WindowStats extends PeriodStats {
  date_from: ISODate;
  date_to: ISODate;
}

export interface TopComplaint {
  topic: string;
  label: string;
  count: number;
}

export interface PropertySummary {
  property_id: string;
  name: string;
  short_name: string;
  current: PeriodStats;
  previous: PeriodStats;
  delta_avg_score: number | null;
  top_complaint: TopComplaint | null;
}

export interface Summary {
  current: WindowStats;
  previous: WindowStats;
  delta_avg_score: number | null;
  delta_count: number;
  by_property: PropertySummary[];
}

export interface TrendPoint extends PeriodStats {
  period_start: ISODate;
}

export interface Trends {
  granularity: Granularity;
  series: TrendPoint[];
  by_property: {
    property_id: string;
    short_name: string;
    series: { period_start: ISODate; count: number; avg_score: number | null }[];
  }[];
}

export interface TopicBreakdownItem {
  topic: string;
  label: string;
  negative_mentions: number;
  positive_mentions: number;
  pct_of_negative_reviews: number;
  pct_of_reviews: number;
  net: number;
}

export interface TopicBreakdown {
  total_reviews: number;
  negative_reviews: number;
  items: TopicBreakdownItem[];
}

export interface TopicTrends {
  series: { period_start: ISODate; topic: string; mentions: number }[];
}

export interface Insight {
  id: string;
  severity: Severity;
  title: string;
  text: string;
  property_id: string | null;
  topic: string | null;
  sample_size: number;
}

export interface ReviewTopic {
  topic: string;
  label: string;
  polarity: Polarity;
  evidence: string | null;
}

export interface Review {
  id: string;
  property_id: string;
  property_name: string;
  property_short_name: string;
  score: number;
  title: string | null;
  positive_text: string | null;
  negative_text: string | null;
  language: string | null;
  review_date: ISODate;
  stay_month: string | null;
  nights: number | null;
  room_type: string | null;
  traveller_type: string | null;
  reviewer_country: string | null;
  hotel_response: string | null;
  sentiment: Sentiment | null;
  sentiment_score: number | null;
  summary: string | null;
  analysis_method: string | null;
  topics: ReviewTopic[];
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export type RunTrigger = 'cron' | 'cli' | 'manual';

export interface ScrapeRun {
  run_id: string;
  property_id: string | null;
  started_at: string;
  finished_at: string | null;
  status: string;
  method: string | null;
  mode: string | null;
  pages_fetched: number | null;
  reviews_seen: number | null;
  reviews_new: number | null;
  reviews_updated: number | null;
  reviews_rejected: number | null;
  error: string | null;
  /** Added in contract v3; optional so older backends still type-check. */
  trigger?: RunTrigger | null;
  /** Newest review date already stored when the run started (incremental collection stops there). */
  watermark_date?: ISODate | null;
}

/** Filters shared by most endpoints. */
export interface ScopeParams {
  properties?: string[];
  date_from?: ISODate;
  date_to?: ISODate;
}

export interface ReviewQuery extends ScopeParams {
  sentiment?: Sentiment[];
  topic?: string;
  polarity?: Polarity;
  min_score?: number;
  max_score?: number;
  q?: string;
  sort?: ReviewSort;
  page?: number;
  page_size?: number;
}
