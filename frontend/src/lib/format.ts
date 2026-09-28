import { format, formatDistanceToNowStrict, isValid, parseISO } from 'date-fns';
import type { ISODate } from '../api/types';
import { parseISODate } from './dates';

/** Guest scores are shown to one decimal place, like Booking.com. */
export function formatScore(score: number | null | undefined): string {
  return score === null || score === undefined ? '–' : score.toFixed(1);
}

export function formatDelta(delta: number | null | undefined, digits = 1): string {
  if (delta === null || delta === undefined) return '–';
  const rounded = Number(delta.toFixed(digits));
  if (rounded === 0) return (0).toFixed(digits);
  return `${rounded > 0 ? '+' : '−'}${Math.abs(rounded).toFixed(digits)}`;
}

export function formatPct(value: number | null | undefined): string {
  return value === null || value === undefined ? '–' : `${Math.round(value)}%`;
}

export function formatCount(value: number): string {
  return value.toLocaleString('en-AU');
}

export function plural(count: number, singular: string, pluralForm = `${singular}s`): string {
  return `${formatCount(count)} ${count === 1 ? singular : pluralForm}`;
}

export function formatDate(value: ISODate): string {
  return format(parseISODate(value), 'd MMM yyyy');
}

export function formatShortDate(value: ISODate): string {
  return format(parseISODate(value), 'd MMM');
}

export function formatMonth(value: ISODate): string {
  return format(parseISODate(value), 'MMM yyyy');
}

export function formatDateRange(from: ISODate, to: ISODate): string {
  if (from === to) return formatDate(from);
  const a = parseISODate(from);
  const b = parseISODate(to);
  if (a.getFullYear() === b.getFullYear()) return `${format(a, 'd MMM')} – ${format(b, 'd MMM yyyy')}`;
  return `${formatDate(from)} – ${formatDate(to)}`;
}

/** "Mar 2026" from a `YYYY-MM` stay month. */
export function formatStayMonth(value: string): string {
  const date = parseISO(`${value}-01`);
  return isValid(date) ? format(date, 'MMM yyyy') : value;
}

export function parseTimestamp(value: string | null | undefined): Date | null {
  if (!value) return null;
  const date = parseISO(value);
  return isValid(date) ? date : null;
}

export function formatTimestamp(value: string | null | undefined): string {
  const date = parseTimestamp(value);
  return date ? format(date, 'd MMM yyyy, h:mm a') : '–';
}

export function timeAgo(value: string | null | undefined): string {
  const date = parseTimestamp(value);
  return date ? `${formatDistanceToNowStrict(date)} ago` : 'never';
}

export type ScoreBand = 'great' | 'good' | 'fair' | 'poor';

/** Bands used for colouring scores. Aligned with the sentiment rules (8+ positive, below 6 negative). */
export function scoreBand(score: number): ScoreBand {
  if (score >= 9) return 'great';
  if (score >= 8) return 'good';
  if (score >= 6) return 'fair';
  return 'poor';
}

export const SCORE_BAND_LABEL: Record<ScoreBand, string> = {
  great: 'Superb',
  good: 'Very good',
  fair: 'Okay',
  poor: 'Poor',
};
