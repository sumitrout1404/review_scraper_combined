import { Info } from 'lucide-react';
import type { ReactNode } from 'react';
import { Popover } from './Popover';

interface InfoTipProps {
  /** Short name of the thing being explained, used for the button's accessible label. */
  topic: string;
  children: ReactNode;
  align?: 'left' | 'right';
}

/** "What does this mean?" explainer for a metric. */
export function InfoTip({ topic, children, align = 'left' }: InfoTipProps) {
  return (
    <Popover
      label={`About ${topic}`}
      align={align}
      panelClassName="w-72 max-w-[calc(100vw-2rem)]"
      trigger={(props) => (
        <button
          type="button"
          {...props}
          aria-label={`What does "${topic}" mean?`}
          className="focus-ring inline-flex h-7 w-7 items-center justify-center rounded-full text-bronze hover:bg-cream hover:text-navy"
        >
          <Info className="h-4 w-4" aria-hidden="true" />
        </button>
      )}
    >
      {() => (
        <div className="space-y-2 text-sm leading-relaxed text-ink">
          <p className="font-medium text-navy">What does this mean?</p>
          {children}
        </div>
      )}
    </Popover>
  );
}
