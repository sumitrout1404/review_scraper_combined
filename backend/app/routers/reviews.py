"""GET /api/reviews and /api/reviews/export.csv."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..deps import MAX_LIST_PARAM, Filters, common_filters, parse_csv
from ..schemas import ReviewPage
from ..services.catalog import known_topic_keys, topic_labels, topic_order
from ..services.csv_export import export_filename, prepare_csv
from ..services.review_search import ReviewFormatter, ReviewQuery, count_reviews, iter_reviews

router = APIRouter(tags=["reviews"])

SENTIMENTS = ("positive", "neutral", "negative")
SortKey = Literal["date_desc", "date_asc", "score_asc", "score_desc"]
MAX_PAGE = 100_000
MAX_PAGE_SIZE = 100
MAX_QUERY_LENGTH = 200


def review_query(
    f: Filters = Depends(common_filters),
    sentiment: str | None = Query(None, max_length=100, description="Comma-separated: positive,neutral,negative"),
    topic: str | None = Query(None, max_length=MAX_LIST_PARAM, description="Topic key (comma-separated for any-of)"),
    polarity: Literal["positive", "negative"] | None = Query(None, description="Topic polarity filter"),
    min_score: float | None = Query(None, ge=1, le=10),
    max_score: float | None = Query(None, ge=1, le=10),
    q: str | None = Query(None, max_length=MAX_QUERY_LENGTH, description="Free-text search"),
    sort: SortKey = Query("date_desc"),
) -> ReviewQuery:
    """Parse and validate the review-feed filters (shared by the feed and the CSV export)."""
    sentiments = parse_csv(sentiment, "sentiment")
    bad = [s for s in sentiments if s not in SENTIMENTS]
    if bad:
        raise HTTPException(status_code=422, detail=f"Unknown sentiment value(s): {', '.join(bad)}")
    topics = parse_csv(topic, "topic")
    if topics:
        known = known_topic_keys()
        unknown = [t for t in topics if t not in known]
        if unknown:
            raise HTTPException(status_code=422, detail=f"Unknown topic(s): {', '.join(unknown)}")
    if min_score is not None and max_score is not None and min_score > max_score:
        raise HTTPException(status_code=422, detail="min_score must be less than or equal to max_score")
    return ReviewQuery(
        properties=f.properties,
        date_from=f.date_from,
        date_to=f.date_to,
        sentiments=sentiments,
        topics=topics,
        polarity=polarity,
        min_score=min_score,
        max_score=max_score,
        q=q.strip() if q and q.strip() else None,
        sort=sort,
    )


@router.get("/reviews", response_model=ReviewPage)
def reviews(
    rq: ReviewQuery = Depends(review_query),
    page: int = Query(1, ge=1, le=MAX_PAGE),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
) -> dict[str, Any]:
    """Paginated review feed with topics attached."""
    formatter = ReviewFormatter(topic_labels(), topic_order())
    items = [formatter(doc) for doc in iter_reviews(rq, skip=(page - 1) * page_size, limit=page_size)]
    return {"items": items, "total": count_reviews(rq), "page": page, "page_size": page_size}


@router.get("/reviews/export.csv", response_class=StreamingResponse)
def export_csv(rq: ReviewQuery = Depends(review_query)) -> StreamingResponse:
    """CSV download of all reviews matching the same filters as /api/reviews (no pagination)."""
    return StreamingResponse(
        prepare_csv(rq),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{export_filename(rq)}"'},
    )
