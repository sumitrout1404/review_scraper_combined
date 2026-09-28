import clsx from 'clsx';
import { Search, SlidersHorizontal, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { Polarity, ReviewSort, Sentiment, Topic } from '../../api/types';
import { useDebouncedValue } from '../../hooks/useDebouncedValue';
import { config } from '../../lib/config';
import { SENTIMENT_LABEL, SORT_LABEL } from '../../lib/labels';
import { MAX_SEARCH_LENGTH, REVIEW_SORTS, type ReviewFilterParams } from '../../lib/urlParams';

export interface ReviewFilterChange {
  sentiment?: Sentiment[];
  topic?: string | null;
  polarity?: Polarity | null;
  min_score?: number | null;
  max_score?: number | null;
  q?: string;
  sort?: ReviewSort;
}

interface ReviewFiltersProps {
  value: ReviewFilterParams;
  topics: Topic[];
  onChange: (change: ReviewFilterChange) => void;
}

const SENTIMENTS: Sentiment[] = ['positive', 'neutral', 'negative'];
const SCORES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

export function ReviewFilters({ value, topics, onChange }: ReviewFiltersProps) {
  // On phones the filter controls are collapsed behind a toggle; always shown from `sm` up.
  const [open, setOpen] = useState(false);
  const activeCount =
    (value.sentiment.length > 0 ? 1 : 0) +
    (value.topic ? 1 : 0) +
    (value.minScore !== undefined || value.maxScore !== undefined ? 1 : 0) +
    (value.sort !== 'date_desc' ? 1 : 0);

  const toggleSentiment = (s: Sentiment) => {
    const next = value.sentiment.includes(s) ? value.sentiment.filter((x) => x !== s) : [...value.sentiment, s];
    onChange({ sentiment: next });
  };

  return (
    <div className="card mb-6 space-y-4 p-4 sm:p-5">
      <div className="flex gap-2">
        <div className="min-w-0 flex-1">
          <SearchBox value={value.q} onSearch={(q) => onChange({ q })} />
        </div>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-controls="review-filter-panel"
          className="focus-ring inline-flex h-11 shrink-0 items-center gap-1.5 rounded-xl border border-sand bg-white px-3 text-sm font-medium text-navy sm:hidden"
        >
          <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
          Filters{activeCount > 0 && ` (${activeCount})`}
        </button>
      </div>

      <div
        id="review-filter-panel"
        className={clsx('grid-cols-1 gap-4 sm:grid sm:grid-cols-2 lg:grid-cols-4', open ? 'grid' : 'hidden')}
      >
        <fieldset>
          <legend className="label">Tone</legend>
          <div className="flex flex-wrap gap-1.5">
            {SENTIMENTS.map((s) => {
              const active = value.sentiment.includes(s);
              return (
                <button
                  key={s}
                  type="button"
                  aria-pressed={active}
                  onClick={() => toggleSentiment(s)}
                  className={clsx(
                    'focus-ring h-9 rounded-full border px-3 text-xs font-medium transition-colors',
                    active ? 'border-navy bg-navy text-white' : 'border-sand bg-white text-navy hover:bg-cream/60',
                  )}
                >
                  {SENTIMENT_LABEL[s]}
                </button>
              );
            })}
          </div>
        </fieldset>

        <div>
          <label htmlFor="topic-filter" className="label">
            Topic
          </label>
          <div className="flex gap-2">
            <select
              id="topic-filter"
              className="input"
              value={value.topic ?? ''}
              onChange={(e) => onChange({ topic: e.target.value || null, polarity: e.target.value ? value.polarity ?? null : null })}
            >
              <option value="">Any topic</option>
              {topics.map((t) => (
                <option key={t.key} value={t.key}>
                  {t.label}
                </option>
              ))}
            </select>
            {value.topic && (
              <select
                aria-label="Complaint or praise"
                className="input w-32 shrink-0"
                value={value.polarity ?? ''}
                onChange={(e) => onChange({ polarity: (e.target.value || null) as Polarity | null })}
              >
                <option value="">Either</option>
                <option value="negative">Complaint</option>
                <option value="positive">Praise</option>
              </select>
            )}
          </div>
        </div>

        <fieldset>
          <legend className="label">Guest score</legend>
          <div className="flex items-center gap-2">
            <select
              aria-label="Minimum score"
              className="input"
              value={value.minScore ?? ''}
              onChange={(e) => onChange({ min_score: e.target.value ? Number(e.target.value) : null })}
            >
              <option value="">From 1</option>
              {SCORES.map((s) => (
                <option key={s} value={s} disabled={value.maxScore !== undefined && s > value.maxScore}>
                  From {s}
                </option>
              ))}
            </select>
            <select
              aria-label="Maximum score"
              className="input"
              value={value.maxScore ?? ''}
              onChange={(e) => onChange({ max_score: e.target.value ? Number(e.target.value) : null })}
            >
              <option value="">To 10</option>
              {SCORES.map((s) => (
                <option key={s} value={s} disabled={value.minScore !== undefined && s < value.minScore}>
                  To {s}
                </option>
              ))}
            </select>
          </div>
        </fieldset>

        <div>
          <label htmlFor="sort" className="label">
            Sort by
          </label>
          <select id="sort" className="input" value={value.sort} onChange={(e) => onChange({ sort: e.target.value as ReviewSort })}>
            {REVIEW_SORTS.map((s) => (
              <option key={s} value={s}>
                {SORT_LABEL[s]}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}

/** Search box with its own state; the URL is updated after typing pauses. */
function SearchBox({ value, onSearch }: { value: string; onSearch: (q: string) => void }) {
  const [text, setText] = useState(value);
  const debounced = useDebouncedValue(text, config.searchDebounceMs);

  // Follow external changes (e.g. "Clear all filters").
  useEffect(() => {
    setText(value);
  }, [value]);

  useEffect(() => {
    const trimmed = debounced.trim();
    if (trimmed !== value) onSearch(trimmed);
    // Only react to the debounced text, not to `value` catching up.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);

  return (
    <div className="relative">
      <label htmlFor="review-search" className="sr-only">
        Search review text
      </label>
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" aria-hidden="true" />
      <input
        id="review-search"
        type="search"
        className="input h-11 pl-9 pr-10"
        placeholder="Search review text…"
        value={text}
        maxLength={MAX_SEARCH_LENGTH}
        onChange={(e) => setText(e.target.value)}
      />
      {text && (
        <button
          type="button"
          onClick={() => setText('')}
          aria-label="Clear search"
          className="focus-ring absolute right-2 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full text-ink-muted hover:bg-cream hover:text-navy"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      )}
    </div>
  );
}
