import type { Config } from 'tailwindcss';
import { colors as c } from './src/theme/tokens';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        navy: { DEFAULT: c.navy, 700: c.navy700, 50: c.navy50, 100: c.navy100 },
        ink: { DEFAULT: c.ink, muted: c.inkMuted },
        cream: c.cream,
        offwhite: c.offwhite,
        sand: { DEFAULT: c.sand, light: c.sandLight },
        bronze: { DEFAULT: c.bronze, dark: c.bronzeDark },
        coral: c.coral,
        positive: { DEFAULT: c.positive, soft: c.positiveSoft },
        negative: { DEFAULT: c.negative, soft: c.negativeSoft },
        neutral: { DEFAULT: c.neutral, soft: c.neutralSoft, dark: c.neutralDark },
        warning: { DEFAULT: c.warning, soft: c.warningSoft },
      },
      fontFamily: {
        display: ['Fraunces', 'Georgia', 'serif'],
        sans: ['Poppins', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(15,42,77,0.04), 0 4px 16px rgba(15,42,77,0.08)',
        pop: '0 8px 32px rgba(15,42,77,0.16)',
      },
      borderRadius: { xl: '12px', '2xl': '16px' },
    },
  },
  plugins: [],
} satisfies Config;
