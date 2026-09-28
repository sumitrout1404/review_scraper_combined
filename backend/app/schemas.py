"""Pydantic response models mirroring docs/CONTRACT.md."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class CronRun(BaseModel):
    run_id: str
    started_at: str
    finished_at: str | None
    status: str


class HealthDB(BaseModel):
    dialect: str
    reviews: int
    last_scraped_at: str | None
    last_cron_run: CronRun | None


class Health(BaseModel):
    status: str
    config_ok: bool
    db: HealthDB | None = None
    # Set only on failure; deliberately free of any configuration values.
    db_configured: bool | None = None
    reason: str | None = None
    detail: str | None = None


class Meta(BaseModel):
    today: str
    this_week_start: str
    min_review_date: str | None
    max_review_date: str | None
    last_scraped_at: str | None
    last_run_status: str | None
    total_reviews: int


class Property(BaseModel):
    id: str
    name: str
    short_name: str
    booking_url: str | None
    booking_score: float | None
    total_reviews: int
    avg_score: float | None


class Topic(BaseModel):
    key: str
    label: str
    description: str | None


class PeriodStats(BaseModel):
    count: int
    avg_score: float | None
    positive: int
    neutral: int
    negative: int
    pct_positive: float
    pct_negative: float


class WindowStats(PeriodStats):
    date_from: str
    date_to: str


class TopComplaint(BaseModel):
    topic: str
    label: str
    count: int


class PropertySummary(BaseModel):
    property_id: str
    name: str
    short_name: str
    current: PeriodStats
    previous: PeriodStats
    delta_avg_score: float | None
    top_complaint: TopComplaint | None


class Summary(BaseModel):
    current: WindowStats
    previous: WindowStats
    delta_avg_score: float | None
    delta_count: int
    by_property: list[PropertySummary]


class TrendPoint(PeriodStats):
    period_start: str


class PropertyTrendPoint(BaseModel):
    period_start: str
    count: int
    avg_score: float | None


class PropertyTrend(BaseModel):
    property_id: str
    short_name: str
    series: list[PropertyTrendPoint]


class Trends(BaseModel):
    granularity: Literal["week", "month"]
    series: list[TrendPoint]
    by_property: list[PropertyTrend]


class TopicBreakdownItem(BaseModel):
    topic: str
    label: str
    negative_mentions: int
    positive_mentions: int
    pct_of_negative_reviews: float
    pct_of_reviews: float
    net: int


class TopicBreakdown(BaseModel):
    total_reviews: int
    negative_reviews: int
    items: list[TopicBreakdownItem]


class TopicTrendPoint(BaseModel):
    period_start: str
    topic: str
    mentions: int


class TopicTrends(BaseModel):
    series: list[TopicTrendPoint]


class Insight(BaseModel):
    id: str
    severity: Literal["alert", "warning", "info", "positive"]
    title: str
    text: str
    property_id: str | None
    topic: str | None
    sample_size: int


class ReviewTopic(BaseModel):
    topic: str
    label: str
    polarity: Literal["positive", "negative"]
    evidence: str | None


class Review(BaseModel):
    id: str
    property_id: str
    property_name: str | None
    property_short_name: str | None
    score: float
    title: str | None
    positive_text: str | None
    negative_text: str | None
    language: str | None
    review_date: str
    stay_month: str | None
    nights: int | None
    room_type: str | None
    traveller_type: str | None
    reviewer_country: str | None
    hotel_response: str | None
    sentiment: Literal["positive", "neutral", "negative"]
    sentiment_score: float | None
    summary: str | None
    analysis_method: str | None
    topics: list[ReviewTopic]


class ReviewPage(BaseModel):
    items: list[Review]
    total: int
    page: int
    page_size: int


class ScrapeRun(BaseModel):
    run_id: str
    property_id: str | None
    trigger: str | None
    started_at: str
    finished_at: str | None
    status: str
    method: str | None
    mode: str | None
    watermark_date: str | None
    pages_fetched: int | None
    reviews_seen: int | None
    reviews_new: int | None
    reviews_updated: int | None
    reviews_rejected: int | None
    error: str | None
