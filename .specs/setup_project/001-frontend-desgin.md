- preciso que o front end tenha o tailwind instalado
- preciso que o shadcn seja instalado
- preciso que o mcp do shadcn seja configurado

- Preciso que essas deginições se estilo sejam definidas para o projeto

```javascript
// tailwind.config.js
// This is a comprehensive Tailwind CSS configuration for a design system inspired by Grok's style.
// Grok's aesthetic is modern, futuristic, and minimalistic, often with dark themes reminiscent of xAI's branding.
// We've incorporated dark and light modes, with auxiliary colors in purple (for accents) and brown (to represent the owl mascot).
// The design system uses CSS variables for theming, allowing easy switching between light and dark modes.
// All necessary tokens are defined: colors, typography, spacing, borders, shadows, transitions, etc.
// This setup assumes you're using Next.js with Tailwind CSS. Add this to your tailwind.config.js file.
// Also, in your global CSS (e.g., globals.css), add the following to enable dark mode:
// @tailwind base;
// @tailwind components;
// @tailwind utilities;
//
// :root {
//   --background: #ffffff;
//   --foreground: #0f172a;
//   --primary: #3b82f6;
//   --secondary: #64748b;
//   --accent-purple: #a855f7;
//   --accent-brown: #8b4513;
//   /* ... add all variables here based on the theme */
// }
//
// @media (prefers-color-scheme: dark) {
//   :root {
//     --background: #0f172a;
//     --foreground: #f1f5f9;
//     /* ... override for dark */
//   }
// }
// body {
//   color: var(--foreground);
//   background: var(--background);
// }

import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  darkMode: 'class', // Enables dark mode via class (add 'dark' to html for dark mode)
  theme: {
    extend: {
      // Colors: Comprehensive palette with light/dark variants.
      // Inspired by Grok: Neutral tones (grays, blacks, whites) with futuristic accents.
      // Primary: Blue-ish for main actions (inspired by xAI's subtle blues).
      // Secondary: Grays for backgrounds and text.
      // Accents: Purple for highlights, Brown for mascot representation.
      // Also includes success, warning, error, info for semantic use.
      colors: {
        background: 'hsl(var(--background) / <alpha-value>)',
        foreground: 'hsl(var(--foreground) / <alpha-value>)',
        primary: {
          DEFAULT: 'hsl(var(--primary) / <alpha-value>)',
          foreground: 'hsl(var(--primary-foreground) / <alpha-value>)',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary) / <alpha-value>)',
          foreground: 'hsl(var(--secondary-foreground) / <alpha-value>)',
        },
        accentPurple: {
          DEFAULT: 'hsl(var(--accent-purple) / <alpha-value>)',
          foreground: 'hsl(var(--accent-purple-foreground) / <alpha-value>)',
        },
        accentBrown: {
          DEFAULT: 'hsl(var(--accent-brown) / <alpha-value>)',
          foreground: 'hsl(var(--accent-brown-foreground) / <alpha-value>)',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted) / <alpha-value>)',
          foreground: 'hsl(var(--muted-foreground) / <alpha-value>)',
        },
        success: {
          DEFAULT: 'hsl(var(--success) / <alpha-value>)',
          foreground: 'hsl(var(--success-foreground) / <alpha-value>)',
        },
        warning: {
          DEFAULT: 'hsl(var(--warning) / <alpha-value>)',
          foreground: 'hsl(var(--warning-foreground) / <alpha-value>)',
        },
        error: {
          DEFAULT: 'hsl(var(--error) / <alpha-value>)',
          foreground: 'hsl(var(--error-foreground) / <alpha-value>)',
        },
        info: {
          DEFAULT: 'hsl(var(--info) / <alpha-value>)',
          foreground: 'hsl(var(--info-foreground) / <alpha-value>)',
        },
        border: 'hsl(var(--border) / <alpha-value>)',
        input: 'hsl(var(--input) / <alpha-value>)',
        ring: 'hsl(var(--ring) / <alpha-value>)',
      },
      // Typography: Fonts, sizes, weights, line heights.
      // Inspired by Grok: Clean, sans-serif fonts like Inter or system defaults for modernity.
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'Noto Sans', 'sans-serif'],
        serif: ['ui-serif', 'Georgia', 'Cambria', 'Times New Roman', 'Times', 'serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'Liberation Mono', 'Courier New', 'monospace'],
        display: ['var(--font-display)', 'sans-serif'], // Custom display font if needed
        body: ['var(--font-body)', 'sans-serif'],
      },
      fontSize: {
        xs: ['0.75rem', { lineHeight: '1rem' }], // 12px
        sm: ['0.875rem', { lineHeight: '1.25rem' }], // 14px
        base: ['1rem', { lineHeight: '1.5rem' }], // 16px
        lg: ['1.125rem', { lineHeight: '1.75rem' }], // 18px
        xl: ['1.25rem', { lineHeight: '1.75rem' }], // 20px
        '2xl': ['1.5rem', { lineHeight: '2rem' }], // 24px
        '3xl': ['1.875rem', { lineHeight: '2.25rem' }], // 30px
        '4xl': ['2.25rem', { lineHeight: '2.5rem' }], // 36px
        '5xl': ['3rem', { lineHeight: '1' }], // 48px
        '6xl': ['3.75rem', { lineHeight: '1' }], // 60px
        '7xl': ['4.5rem', { lineHeight: '1' }], // 72px
        '8xl': ['6rem', { lineHeight: '1' }], // 96px
        '9xl': ['8rem', { lineHeight: '1' }], // 128px
      },
      fontWeight: {
        thin: '100',
        extralight: '200',
        light: '300',
        normal: '400',
        medium: '500',
        semibold: '600',
        bold: '700',
        extrabold: '800',
        black: '900',
      },
      lineHeight: {
        none: '1',
        tight: '1.25',
        snug: '1.375',
        normal: '1.5',
        relaxed: '1.625',
        loose: '2',
      },
      letterSpacing: {
        tighter: '-0.05em',
        tight: '-0.025em',
        normal: '0em',
        wide: '0.025em',
        wider: '0.05em',
        widest: '0.1em',
      },
      // Spacing: Extended scale for padding, margin, gap, etc.
      spacing: {
        px: '1px',
        0: '0px',
        0.5: '0.125rem', // 2px
        1: '0.25rem', // 4px
        1.5: '0.375rem', // 6px
        2: '0.5rem', // 8px
        2.5: '0.625rem', // 10px
        3: '0.75rem', // 12px
        3.5: '0.875rem', // 14px
        4: '1rem', // 16px
        5: '1.25rem', // 20px
        6: '1.5rem', // 24px
        7: '1.75rem', // 28px
        8: '2rem', // 32px
        9: '2.25rem', // 36px
        10: '2.5rem', // 40px
        11: '2.75rem', // 44px
        12: '3rem', // 48px
        14: '3.5rem', // 56px
        16: '4rem', // 64px
        20: '5rem', // 80px
        24: '6rem', // 96px
        28: '7rem', // 112px
        32: '8rem', // 128px
        36: '9rem', // 144px
        40: '10rem', // 160px
        44: '11rem', // 176px
        48: '12rem', // 192px
        52: '13rem', // 208px
        56: '14rem', // 224px
        60: '15rem', // 240px
        64: '16rem', // 256px
        72: '18rem', // 288px
        80: '20rem', // 320px
        96: '24rem', // 384px
      },
      // Borders: Radii and widths.
      borderRadius: {
        none: '0px',
        sm: '0.125rem', // 2px
        DEFAULT: '0.25rem', // 4px
        md: '0.375rem', // 6px
        lg: '0.5rem', // 8px
        xl: '0.75rem', // 12px
        '2xl': '1rem', // 16px
        '3xl': '1.5rem', // 24px
        full: '9999px',
      },
      borderWidth: {
        DEFAULT: '1px',
        0: '0px',
        2: '2px',
        4: '4px',
        8: '8px',
      },
      // Shadows: For elevation and depth, inspired by subtle Grok-like effects.
      boxShadow: {
        sm: '0 1px 2px 0 rgb(0 0 0 / 0.05)',
        DEFAULT: '0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)',
        md: '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
        lg: '0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)',
        xl: '0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1)',
        '2xl': '0 25px 50px -12px rgb(0 0 0 / 0.25)',
        inner: 'inset 0 2px 4px 0 rgb(0 0 0 / 0.05)',
        none: 'none',
      },
      // Transitions and Animations: For smooth interactions.
      transitionProperty: {
        none: 'none',
        all: 'all',
        DEFAULT: 'color, background-color, border-color, text-decoration-color, fill, stroke, opacity, box-shadow, transform, filter, backdrop-filter',
        colors: 'color, background-color, border-color, text-decoration-color, fill, stroke',
        opacity: 'opacity',
        shadow: 'box-shadow',
        transform: 'transform',
      },
      transitionDuration: {
        DEFAULT: '150ms',
        75: '75ms',
        100: '100ms',
        150: '150ms',
        200: '200ms',
        300: '300ms',
        500: '500ms',
        700: '700ms',
        1000: '1000ms',
      },
      transitionTimingFunction: {
        DEFAULT: 'cubic-bezier(0.4, 0, 0.2, 1)',
        linear: 'linear',
        in: 'cubic-bezier(0.4, 0, 1, 1)',
        out: 'cubic-bezier(0, 0, 0.2, 1)',
        'in-out': 'cubic-bezier(0.4, 0, 0.2, 1)',
      },
      transitionDelay: {
        75: '75ms',
        100: '100ms',
        150: '150ms',
        200: '200ms',
        300: '300ms',
        500: '500ms',
        700: '700ms',
        1000: '1000ms',
      },
      // Breakpoints: For responsive design.
      screens: {
        xs: '475px',
        sm: '640px',
        md: '768px',
        lg: '1024px',
        xl: '1280px',
        '2xl': '1536px',
      },
      // Z-index: Layers.
      zIndex: {
        auto: 'auto',
        0: '0',
        10: '10',
        20: '20',
        30: '30',
        40: '40',
        50: '50',
      },
      // Opacity: For overlays and fades.
      opacity: {
        0: '0',
        5: '0.05',
        10: '0.1',
        20: '0.2',
        25: '0.25',
        30: '0.3',
        40: '0.4',
        50: '0.5',
        60: '0.6',
        70: '0.7',
        75: '0.75',
        80: '0.8',
        90: '0.9',
        95: '0.95',
        100: '1',
      },
      // Additional utilities if needed (e.g., aspect ratios, containers).
      aspectRatio: {
        auto: 'auto',
        square: '1 / 1',
        video: '16 / 9',
      },
      container: {
        center: true,
        padding: '1rem',
        screens: {
          sm: '640px',
          md: '768px',
          lg: '1024px',
          xl: '1280px',
          '2xl': '1536px',
        },
      },
    },
  },
  plugins: [
    // Add any additional plugins if needed, e.g., require('@tailwindcss/forms'), require('@tailwindcss/typography')
  ],
};

export default config;
```

```css
/* globals.css or styles.css */
/* Add this to your global CSS file to define the CSS variables for light and dark modes. */
/* This enables theme switching. You can use JavaScript to toggle the 'dark' class on the html element. */

:root {
  --background: 255 255 255; /* white */
  --foreground: 15 23 42; /* slate-900 */
  --primary: 59 130 246; /* blue-500 */
  --primary-foreground: 255 255 255; /* white */
  --secondary: 100 116 139; /* slate-500 */
  --secondary-foreground: 255 255 255; /* white */
  --accent-purple: 168 85 247; /* purple-500 */
  --accent-purple-foreground: 255 255 255; /* white */
  --accent-brown: 139 69 19; /* saddlebrown */
  --accent-brown-foreground: 255 255 255; /* white */
  --muted: 226 232 240; /* slate-200 */
  --muted-foreground: 100 116 139; /* slate-500 */
  --success: 34 197 94; /* green-500 */
  --success-foreground: 255 255 255;
  --warning: 234 179 8; /* yellow-500 */
  --warning-foreground: 15 23 42;
  --error: 239 68 68; /* red-500 */
  --error-foreground: 255 255 255;
  --info: 59 130 246; /* blue-500 */
  --info-foreground: 255 255 255;
  --border: 226 232 240; /* slate-200 */
  --input: 226 232 240;
  --ring: 59 130 246; /* blue-500 */
}

.dark {
  --background: 15 23 42; /* slate-900 */
  --foreground: 241 245 249; /* slate-100 */
  --primary: 59 130 246; /* blue-500 (keep consistent or adjust if needed) */
  --primary-foreground: 255 255 255;
  --secondary: 51 65 85; /* slate-700 */
  --secondary-foreground: 241 245 249;
  --accent-purple: 168 85 247;
  --accent-purple-foreground: 255 255 255;
  --accent-brown: 139 69 19;
  --accent-brown-foreground: 255 255 255;
  --muted: 51 65 85; /* slate-700 */
  --muted-foreground: 148 163 184; /* slate-400 */
  --success: 34 197 94;
  --success-foreground: 255 255 255;
  --warning: 234 179 8;
  --warning-foreground: 15 23 42;
  --error: 239 68 68;
  --error-foreground: 255 255 255;
  --info: 59 130 246;
  --info-foreground: 255 255 255;
  --border: 51 65 85; /* slate-700 */
  --input: 51 65 85;
  --ring: 59 130 246;
}

/* Apply to body or root elements */
body {
  color: rgb(var(--foreground));
  background: rgb(var(--background));
  font-family: var(--font-sans, sans-serif);
}
```

This configuration provides a complete design system foundation. To use it in your Next.js app:

1. Install Tailwind: `npm install -D tailwindcss postcss autoprefixer`
2. Initialize: `npx tailwindcss init -p`
3. Replace tailwind.config.js with the above.
4. Add the CSS variables to your globals.css.
5. For dark mode, use a theme provider or localStorage to toggle the 'dark' class on the html element.

You can now use classes like `bg-background text-foreground hover:bg-primary` etc., and they will adapt to light/dark modes. If you need more custom tokens or adjustments, let me know!