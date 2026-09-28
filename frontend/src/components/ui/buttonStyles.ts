import clsx from 'clsx';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost';
export type ButtonSize = 'sm' | 'md';

const BASE =
  'focus-ring inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded-xl font-medium transition-colors disabled:cursor-not-allowed';

const VARIANTS: Record<ButtonVariant, string> = {
  primary: 'bg-navy text-white hover:bg-navy-700 disabled:bg-navy/50',
  secondary: 'border border-sand bg-white text-navy hover:border-bronze/60 hover:bg-cream/60 disabled:opacity-60',
  ghost: 'text-navy hover:bg-cream/70 disabled:opacity-60',
};

const SIZES: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-xs gap-1.5',
  md: 'h-10 px-4 text-sm gap-2',
};

/** Button classes, shared so links can look like buttons. */
export function buttonClasses(variant: ButtonVariant = 'secondary', size: ButtonSize = 'md', className?: string): string {
  return clsx(BASE, VARIANTS[variant], SIZES[size], className);
}
