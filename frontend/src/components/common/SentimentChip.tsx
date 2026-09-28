import { Frown, Meh, Smile } from 'lucide-react';
import type { Sentiment } from '../../api/types';
import { SENTIMENT_LABEL } from '../../lib/labels';
import { Badge, type BadgeTone } from '../ui/Badge';

const META: Record<Sentiment, { tone: BadgeTone; Icon: typeof Smile }> = {
  positive: { tone: 'positive', Icon: Smile },
  neutral: { tone: 'neutral', Icon: Meh },
  negative: { tone: 'negative', Icon: Frown },
};

export function SentimentChip({ sentiment }: { sentiment: Sentiment }) {
  const { tone, Icon } = META[sentiment];
  const label = SENTIMENT_LABEL[sentiment];
  return (
    <Badge tone={tone} icon={<Icon className="h-3.5 w-3.5" aria-hidden="true" />}>
      {label}
    </Badge>
  );
}
