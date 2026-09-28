import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { ScopeParams } from '../api/types';
import { presetRange, previousRange, type DateRange, type RangePreset } from '../lib/dates';
import { readGlobalFilters, withParams } from '../lib/urlParams';
import { useMeta } from './queries';

export interface GlobalFilters {
  /** Selected property ids; empty means all properties. */
  properties: string[];
  preset: RangePreset;
  /** Resolved dates; null until /api/meta has loaded. */
  range: DateRange | null;
  previous: DateRange | null;
  /** Ready-to-use API params, or null while the range is unresolved. */
  scope: ScopeParams | null;
  setProperties: (ids: string[]) => void;
  setPreset: (preset: Exclude<RangePreset, 'custom'>) => void;
  setCustomRange: (range: DateRange) => void;
}

/** Property and date filters shared by every page, stored in the URL. */
export function useGlobalFilters(): GlobalFilters {
  const [params, setParams] = useSearchParams();
  const meta = useMeta();
  const parsed = useMemo(() => readGlobalFilters(params), [params]);

  const range = useMemo<DateRange | null>(() => {
    if (parsed.preset === 'custom' && parsed.customFrom && parsed.customTo) {
      return { from: parsed.customFrom, to: parsed.customTo };
    }
    if (!meta.data) return null;
    const preset = parsed.preset === 'custom' ? 'this_week' : parsed.preset;
    return presetRange(preset, { today: meta.data.today, thisWeekStart: meta.data.this_week_start });
  }, [parsed, meta.data]);

  const scope = useMemo<ScopeParams | null>(
    () =>
      range
        ? {
            properties: parsed.properties.length > 0 ? [...parsed.properties].sort() : undefined,
            date_from: range.from,
            date_to: range.to,
          }
        : null,
    [range, parsed.properties],
  );

  const setProperties = useCallback(
    (ids: string[]) => setParams((prev) => withParams(prev, { properties: ids }), { replace: true }),
    [setParams],
  );
  const setPreset = useCallback(
    (preset: Exclude<RangePreset, 'custom'>) =>
      setParams((prev) => withParams(prev, { range: preset, from: null, to: null }), { replace: true }),
    [setParams],
  );
  const setCustomRange = useCallback(
    (r: DateRange) => setParams((prev) => withParams(prev, { range: 'custom', from: r.from, to: r.to }), { replace: true }),
    [setParams],
  );

  return {
    properties: parsed.properties,
    preset: parsed.preset,
    range,
    previous: range ? previousRange(range) : null,
    scope,
    setProperties,
    setPreset,
    setCustomRange,
  };
}
