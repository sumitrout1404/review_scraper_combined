/**
 * Brand colour tokens (docs/CONTRACT.md "Visual theme"). Used by Tailwind and
 * by the charts, so both always agree.
 */
export const colors = {
  navy: '#0f2a4d',
  navy700: '#1a3a63',
  navy50: '#eef2f7',
  navy100: '#d9e1ec',
  ink: '#1d2a3f',
  inkMuted: '#5a6577',
  cream: '#f5efe0',
  offwhite: '#faf8f4',
  sand: '#e8dcc4',
  sandLight: '#f1e9d8',
  bronze: '#a8855e',
  bronzeDark: '#7d6243',
  coral: '#ff4d6d',
  positive: '#1f8a5b',
  positiveSoft: '#e6f3ec',
  negative: '#c8374b',
  negativeSoft: '#fbe9ec',
  neutral: '#8a8f98',
  neutralSoft: '#eef0f2',
  neutralDark: '#646a74',
  warning: '#a86a12',
  warningSoft: '#fcf1de',
} as const;

/**
 * Categorical palette for multi-series charts (topic trends). Assigned to topics
 * in a fixed order and never cycled. Validated for colour-blind separation
 * against a white surface; a legend is always shown alongside.
 */
export const categorical = ['#2b6cb0', '#d08a2e', '#2f9e8f', '#8e5aa8', '#b0473c'] as const;

export const chart = {
  grid: '#efe7d6',
  axis: colors.inkMuted,
  surface: '#ffffff',
} as const;
