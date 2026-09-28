export function Brand({ compact }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <span
        aria-hidden="true"
        className="flex h-9 w-9 items-center justify-center rounded-xl bg-cream font-display text-lg font-semibold text-navy"
      >
        A
      </span>
      <div className="leading-tight">
        <p className="font-display text-lg font-medium tracking-wide text-white">Azzurro</p>
        {!compact && <p className="text-[11px] uppercase tracking-[0.18em] text-sand/80">Review Insights</p>}
      </div>
    </div>
  );
}
