import clsx from 'clsx';
import { useCallback, useId, useRef, useState, type ReactNode } from 'react';
import { useDismiss } from '../../hooks/useDismiss';

interface PopoverProps {
  /** Renders the trigger; spread `props` onto a <button>. */
  trigger: (props: {
    'aria-expanded': boolean;
    'aria-controls': string;
    onClick: () => void;
  }) => ReactNode;
  children: (close: () => void) => ReactNode;
  align?: 'left' | 'right';
  className?: string;
  panelClassName?: string;
  label: string;
}

/** Minimal accessible disclosure popover: Escape / outside click closes it and focus returns to the trigger. */
export function Popover({ trigger, children, align = 'left', className, panelClassName, label }: PopoverProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const panelId = useId();

  const close = useCallback(() => {
    setOpen(false);
    rootRef.current?.querySelector<HTMLButtonElement>('button')?.focus();
  }, []);
  const dismiss = useCallback(
    (reason: 'escape' | 'outside') => (reason === 'escape' ? close() : setOpen(false)),
    [close],
  );

  useDismiss(rootRef, open, dismiss);

  return (
    <div ref={rootRef} className={clsx('relative', className)}>
      {trigger({ 'aria-expanded': open, 'aria-controls': panelId, onClick: () => setOpen((v) => !v) })}
      {open && (
        <div
          id={panelId}
          role="dialog"
          aria-label={label}
          className={clsx(
            'absolute z-40 mt-2 rounded-2xl border border-sand bg-white p-4 shadow-pop',
            align === 'right' ? 'right-0' : 'left-0',
            panelClassName,
          )}
        >
          {children(close)}
        </div>
      )}
    </div>
  );
}
