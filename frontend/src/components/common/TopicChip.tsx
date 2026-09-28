import clsx from 'clsx';
import { ThumbsDown, ThumbsUp } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import type { Polarity } from '../../api/types';
import { pickGlobal, withParams } from '../../lib/urlParams';

interface TopicChipProps {
  topic: string;
  label: string;
  polarity: Polarity;
  /** Evidence snippet shown as a tooltip. */
  evidence?: string | null;
}

/** Topic tag that links to the review feed filtered by that topic and polarity. */
export function TopicChip({ topic, label, polarity, evidence }: TopicChipProps) {
  const [params] = useSearchParams();
  const target = withParams(pickGlobal(params), { topic, polarity });
  const complaint = polarity === 'negative';
  const Icon = complaint ? ThumbsDown : ThumbsUp;
  const kind = complaint ? 'Complaint' : 'Praise';

  return (
    <Link
      to={{ pathname: '/reviews', search: target.toString() }}
      title={evidence ? `${kind}: “${evidence}”` : `${kind} about ${label}. Show all reviews like this.`}
      aria-label={`${kind}: ${label}. Show reviews with this ${kind.toLowerCase()}.`}
      className={clsx(
        'focus-ring inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors',
        complaint
          ? 'border-negative/25 bg-negative-soft text-negative hover:border-negative/60'
          : 'border-positive/25 bg-positive-soft text-positive hover:border-positive/60',
      )}
    >
      <Icon className="h-3 w-3" aria-hidden="true" />
      {label}
    </Link>
  );
}
