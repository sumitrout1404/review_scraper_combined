import { addDays, addMonths, differenceInCalendarDays, format, isValid, parse, subMonths, subWeeks } from 'date-fns';
import type { Granularity, ISODate } from '../api/types';

const ISO_FORMAT = 'yyyy-MM-dd';
const ISO_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

/** Parses a `YYYY-MM-DD` calendar date as a local date (no timezone shifting). */
export function parseISODate(value: string): Date {
  return parse(value, ISO_FORMAT, new Date(2000, 0, 1));
}

export function toISODate(date: Date): ISODate {
  return format(date, ISO_FORMAT);
}

/** True for a real calendar date in `YYYY-MM-DD` form (rejects 2026-02-31). */
export function isISODate(value: unknown): value is ISODate {
  if (typeof value !== 'string' || !ISO_PATTERN.test(value)) return false;
  const date = parseISODate(value);
  return isValid(date) && toISODate(date) === value;
}

export function shiftDays(value: ISODate, days: number): ISODate {
  return toISODate(addDays(parseISODate(value), days));
}

export function daysInclusive(from: ISODate, to: ISODate): number {
  return differenceInCalendarDays(parseISODate(to), parseISODate(from)) + 1;
}

export const RANGE_PRESETS = ['this_week', 'last_week', 'last_7', 'last_30', 'last_90', 'custom'] as const;
export type RangePreset = (typeof RANGE_PRESETS)[number];

export const PRESET_LABELS: Record<RangePreset, string> = {
  this_week: 'This week',
  last_week: 'Last week',
  last_7: 'Last 7 days',
  last_30: 'Last 30 days',
  last_90: 'Last 90 days',
  custom: 'Custom dates',
};

export interface DateRange {
  from: ISODate;
  to: ISODate;
}

/** Anchor dates supplied by the backend (Sydney time), so every user sees the same week. */
export interface DateAnchor {
  today: ISODate;
  thisWeekStart: ISODate;
}

export function presetRange(preset: Exclude<RangePreset, 'custom'>, anchor: DateAnchor): DateRange {
  const { today, thisWeekStart } = anchor;
  switch (preset) {
    case 'this_week':
      return { from: thisWeekStart, to: today };
    case 'last_week':
      return { from: shiftDays(thisWeekStart, -7), to: shiftDays(thisWeekStart, -1) };
    case 'last_7':
      return { from: shiftDays(today, -6), to: today };
    case 'last_30':
      return { from: shiftDays(today, -29), to: today };
    case 'last_90':
      return { from: shiftDays(today, -89), to: today };
  }
}

/** The window the backend compares against: same length, directly before. */
export function previousRange(range: DateRange): DateRange {
  const length = daysInclusive(range.from, range.to);
  return { from: shiftDays(range.from, -length), to: shiftDays(range.from, -1) };
}

/**
 * The trend chart needs enough history to show a trend, so it shows at least
 * 12 weeks (or 12 months) ending on the selected end date.
 */
export function trendWindow(range: DateRange, granularity: Granularity): DateRange {
  const end = parseISODate(range.to);
  const minimumStart = granularity === 'week' ? subWeeks(end, 12) : subMonths(end, 12);
  const selectedStart = parseISODate(range.from);
  const start = selectedStart < minimumStart ? selectedStart : addDays(minimumStart, 1);
  return { from: toISODate(start), to: range.to };
}


/** True when the newest period in a series ends after `today`, i.e. it is not over yet. */
export function isLastPeriodInProgress(
  series: { period_start: ISODate }[],
  granularity: Granularity,
  today: ISODate | undefined,
): boolean {
  const last = series[series.length - 1];
  if (!last || !today) return false;
  const start = parseISODate(last.period_start);
  const end = granularity === 'week' ? addDays(start, 6) : addDays(addMonths(start, 1), -1);
  return toISODate(end) > today;
}
