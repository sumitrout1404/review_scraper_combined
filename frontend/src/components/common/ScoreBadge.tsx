import clsx from 'clsx';
import { formatScore, scoreBand, SCORE_BAND_LABEL, type ScoreBand } from '../../lib/format';

const BAND_CLASSES: Record<ScoreBand, string> = {
  great: 'bg-positive text-white',
  good: 'bg-positive-soft text-positive',
  fair: 'bg-warning-soft text-warning',
  poor: 'bg-negative text-white',
};

/** Guest score in a square badge, coloured by band and labelled in words. */
export function ScoreBadge({ score, showLabel = true }: { score: number; showLabel?: boolean }) {
  const band = scoreBand(score);
  return (
    <div className="flex items-center gap-2">
      <span
        className={clsx(
          'inline-flex h-10 w-11 items-center justify-center rounded-lg rounded-bl-none font-display text-lg font-semibold tabular',
          BAND_CLASSES[band],
        )}
        aria-label={`Guest score ${formatScore(score)} out of 10`}
      >
        {formatScore(score)}
      </span>
      {showLabel && <span className="text-xs font-medium text-ink-muted">{SCORE_BAND_LABEL[band]}</span>}
    </div>
  );
}
