import { CheckCircle2, CircleDashed, CircleSlash, Loader2, TriangleAlert, XCircle } from 'lucide-react';
import { RUN_HEALTH_LABEL, runHealth, type RunHealth } from '../../lib/labels';
import { Badge, type BadgeTone } from '../ui/Badge';

const META: Record<RunHealth, { tone: BadgeTone; Icon: typeof CheckCircle2; short: string }> = {
  ok: { tone: 'positive', Icon: CheckCircle2, short: 'Succeeded' },
  partial: { tone: 'warning', Icon: TriangleAlert, short: 'Partial' },
  failed: { tone: 'negative', Icon: XCircle, short: 'Failed' },
  running: { tone: 'cream', Icon: Loader2, short: 'Running' },
  skipped: { tone: 'neutral', Icon: CircleSlash, short: 'Skipped' },
  unknown: { tone: 'neutral', Icon: CircleDashed, short: 'Unknown' },
};

export function RunStatusBadge({ status }: { status: string }) {
  const health = runHealth(status);
  const { tone, Icon, short } = META[health];
  return (
    <Badge tone={tone} icon={<Icon className="h-3.5 w-3.5" aria-hidden="true" />} title={`${RUN_HEALTH_LABEL[health]} (${status})`}>
      {short}
    </Badge>
  );
}
