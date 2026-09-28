import clsx from 'clsx';
import type { ReactNode } from 'react';

export type BadgeTone = 'positive' | 'negative' | 'neutral' | 'warning' | 'navy' | 'bronze' | 'cream';

const TONES: Record<BadgeTone, string> = {
  positive: 'bg-positive-soft text-positive',
  negative: 'bg-negative-soft text-negative',
  neutral: 'bg-neutral-soft text-neutral-dark',
  warning: 'bg-warning-soft text-warning',
  navy: 'bg-navy text-white',
  bronze: 'bg-cream text-bronze-dark',
  cream: 'bg-cream text-navy',
};

interface BadgeProps {
  tone?: BadgeTone;
  icon?: ReactNode;
  children: ReactNode;
  className?: string;
  title?: string;
}

export function Badge({ tone = 'neutral', icon, children, className, title }: BadgeProps) {
  return (
    <span
      title={title}
      className={clsx(
        'inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium',
        TONES[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}
