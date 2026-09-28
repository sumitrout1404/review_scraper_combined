import { FlaskConical } from 'lucide-react';
import { config } from '../../lib/config';
import { Badge } from '../ui/Badge';

/** Shown next to any number based on fewer than `config.lowSampleThreshold` reviews. */
export function LowSampleBadge({ count }: { count: number }) {
  if (count >= config.lowSampleThreshold || count === 0) return null;
  return (
    <Badge
      tone="warning"
      icon={<FlaskConical className="h-3 w-3" aria-hidden="true" />}
      title={`Based on only ${count} review${count === 1 ? '' : 's'}, so treat this number with caution.`}
    >
      Low sample
    </Badge>
  );
}
