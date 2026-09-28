import { BedDouble, Globe2, MessageSquareReply, Moon, ThumbsDown, ThumbsUp, Users } from 'lucide-react';
import type { Review } from '../../api/types';
import { formatDate, formatStayMonth, plural } from '../../lib/format';
import { ScoreBadge } from '../common/ScoreBadge';
import { SentimentChip } from '../common/SentimentChip';
import { TopicChip } from '../common/TopicChip';

/** One guest review. All review text is rendered as plain text. */
export function ReviewCard({ review }: { review: Review }) {
  const complaints = review.topics.filter((t) => t.polarity === 'negative');
  const praise = review.topics.filter((t) => t.polarity === 'positive');
  const liked = review.positive_text?.trim();
  const disliked = review.negative_text?.trim();
  const meta = [
    review.room_type && { icon: BedDouble, text: review.room_type },
    review.traveller_type && { icon: Users, text: review.traveller_type },
    review.reviewer_country && { icon: Globe2, text: review.reviewer_country },
    review.nights && {
      icon: Moon,
      text: `${plural(review.nights, 'night')}${review.stay_month ? ` · stayed ${formatStayMonth(review.stay_month)}` : ''}`,
    },
  ].filter(Boolean) as { icon: typeof Moon; text: string }[];

  return (
    <article className="card p-5 sm:p-6" aria-label={`Review of ${review.property_name} on ${formatDate(review.review_date)}`}>
      <header className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-bronze">{review.property_short_name}</p>
          <p className="mt-0.5 text-xs text-ink-muted">
            <time dateTime={review.review_date}>{formatDate(review.review_date)}</time>
          </p>
          <h3 className="mt-2 font-display text-lg font-medium leading-snug text-navy">
            {review.title?.trim() ? `“${review.title.trim()}”` : <span className="text-ink-muted">No title</span>}
          </h3>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <ScoreBadge score={review.score} />
          {review.sentiment && <SentimentChip sentiment={review.sentiment} />}
        </div>
      </header>

      {review.summary && <p className="mt-3 text-sm italic text-ink-muted">{review.summary}</p>}

      {liked || disliked ? (
        <div className={`mt-4 grid gap-3 ${liked && disliked ? 'md:grid-cols-2' : ''}`}>
          {liked && <ReviewText tone="liked" text={liked} />}
          {disliked && <ReviewText tone="disliked" text={disliked} />}
        </div>
      ) : (
        <p className="mt-4 text-sm italic text-ink-muted">The guest left a score without any comments.</p>
      )}

      {(complaints.length > 0 || praise.length > 0) && (
        <div className="mt-4 flex flex-wrap gap-1.5" aria-label="Topics mentioned">
          {complaints.map((t) => (
            <TopicChip key={`${t.topic}-n`} topic={t.topic} label={t.label} polarity="negative" evidence={t.evidence} />
          ))}
          {praise.map((t) => (
            <TopicChip key={`${t.topic}-p`} topic={t.topic} label={t.label} polarity="positive" evidence={t.evidence} />
          ))}
        </div>
      )}

      {meta.length > 0 && (
        <ul className="mt-4 flex flex-wrap gap-x-4 gap-y-1.5 border-t border-sand/60 pt-3 text-xs text-ink-muted">
          {meta.map(({ icon: Icon, text }) => (
            <li key={text} className="flex items-center gap-1.5">
              <Icon className="h-3.5 w-3.5 text-bronze" aria-hidden="true" />
              {text}
            </li>
          ))}
        </ul>
      )}

      {review.hotel_response && (
        <div className="mt-4 rounded-xl bg-cream/70 p-4">
          <p className="flex items-center gap-1.5 text-xs font-medium text-navy">
            <MessageSquareReply className="h-3.5 w-3.5" aria-hidden="true" />
            Hotel response
          </p>
          <p className="mt-1.5 whitespace-pre-line text-sm text-ink">{review.hotel_response}</p>
        </div>
      )}
    </article>
  );
}

function ReviewText({ tone, text }: { tone: 'liked' | 'disliked'; text: string }) {
  const liked = tone === 'liked';
  const Icon = liked ? ThumbsUp : ThumbsDown;
  return (
    <div className={liked ? 'rounded-xl bg-positive-soft/70 p-3.5' : 'rounded-xl bg-negative-soft/70 p-3.5'}>
      <p className={`flex items-center gap-1.5 text-xs font-medium ${liked ? 'text-positive' : 'text-negative'}`}>
        <Icon className="h-3.5 w-3.5" aria-hidden="true" />
        {liked ? 'Liked' : 'Disliked'}
      </p>
      <p className="mt-1.5 whitespace-pre-line text-sm leading-relaxed text-ink">{text}</p>
    </div>
  );
}

export function ReviewCardSkeleton() {
  return (
    <div className="card p-6" aria-hidden="true">
      <div className="flex justify-between">
        <div className="space-y-2">
          <div className="h-3 w-24 animate-pulse rounded bg-sand/50" />
          <div className="h-5 w-56 animate-pulse rounded bg-sand/50" />
        </div>
        <div className="h-10 w-11 animate-pulse rounded-lg bg-sand/50" />
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <div className="h-20 animate-pulse rounded-xl bg-sand/40" />
        <div className="h-20 animate-pulse rounded-xl bg-sand/40" />
      </div>
    </div>
  );
}
