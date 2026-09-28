"""Review insights: topic + sentiment classification of Booking.com reviews.

Hybrid approach: a deterministic lexicon classifier (``rules``) that is always available,
and a Groq-hosted LLM (``llm:<model>``) for recent reviews when ``GROQ_API_KEY`` is set.

    from analysis import run_analysis
    stats = run_analysis(method="auto", time_budget_s=60)
"""
from analysis.pipeline import run_analysis

__all__ = ["run_analysis"]
