import clsx from 'clsx';
import type { ReactNode } from 'react';

interface CardProps {
  children: ReactNode;
  className?: string;
  as?: 'section' | 'div' | 'article';
  labelledBy?: string;
}

export function Card({ children, className, as: Tag = 'section', labelledBy }: CardProps) {
  return (
    <Tag className={clsx('card', className)} aria-labelledby={labelledBy}>
      {children}
    </Tag>
  );
}

interface CardHeaderProps {
  id?: string;
  title: ReactNode;
  subtitle?: ReactNode;
  /** Usually an <InfoTip/> explaining the metric. */
  info?: ReactNode;
  actions?: ReactNode;
}

export function CardHeader({ id, title, subtitle, info, actions }: CardHeaderProps) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 px-5 pt-5 sm:px-6 sm:pt-6">
      <div className="min-w-0">
        <div className="flex items-center gap-1.5">
          <h2 id={id} className="text-lg font-medium leading-tight sm:text-xl">
            {title}
          </h2>
          {info}
        </div>
        {subtitle && <p className="mt-1 text-sm text-ink-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function CardBody({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={clsx('px-5 pb-5 pt-4 sm:px-6 sm:pb-6', className)}>{children}</div>;
}
