/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: 'rgb(var(--background) / <alpha-value>)',
        foreground: 'rgb(var(--foreground) / <alpha-value>)',
        primary: {
          DEFAULT: 'rgb(var(--primary) / <alpha-value>)',
          foreground: 'rgb(var(--primary-foreground) / <alpha-value>)',
        },
        secondary: {
          DEFAULT: 'rgb(var(--secondary) / <alpha-value>)',
          foreground: 'rgb(var(--secondary-foreground) / <alpha-value>)',
        },
        destructive: {
          DEFAULT: 'rgb(var(--destructive) / <alpha-value>)',
          foreground: 'rgb(var(--error-foreground) / <alpha-value>)',
        },
        card: {
          DEFAULT: 'rgb(var(--card) / <alpha-value>)',
          foreground: 'rgb(var(--card-foreground) / <alpha-value>)',
        },
        popover: {
          DEFAULT: 'rgb(var(--popover) / <alpha-value>)',
          foreground: 'rgb(var(--popover-foreground) / <alpha-value>)',
        },
        accent: {
          DEFAULT: 'rgb(var(--accent) / <alpha-value>)',
          foreground: 'rgb(var(--accent-foreground) / <alpha-value>)',
        },
        accentPurple: {
          DEFAULT: 'rgb(var(--accent-purple) / <alpha-value>)',
          foreground: 'rgb(var(--accent-purple-foreground) / <alpha-value>)',
        },
        accentBrown: {
          DEFAULT: 'rgb(var(--accent-brown) / <alpha-value>)',
          foreground: 'rgb(var(--accent-brown-foreground) / <alpha-value>)',
        },
        brandBrown: {
          900: 'rgb(var(--brand-brown-900) / <alpha-value>)',
          700: 'rgb(var(--brand-brown-700) / <alpha-value>)',
          foreground: 'rgb(var(--brand-brown-foreground) / <alpha-value>)',
        },
        brandYellow: {
          500: 'rgb(var(--brand-yellow-500) / <alpha-value>)',
          foreground: 'rgb(var(--brand-yellow-foreground) / <alpha-value>)',
        },
        gray: {
          50: 'rgb(var(--gray-50) / <alpha-value>)',
          100: 'rgb(var(--gray-100) / <alpha-value>)',
          200: 'rgb(var(--gray-200) / <alpha-value>)',
          300: 'rgb(var(--gray-300) / <alpha-value>)',
          400: 'rgb(var(--gray-400) / <alpha-value>)',
          500: 'rgb(var(--gray-500) / <alpha-value>)',
          600: 'rgb(var(--gray-600) / <alpha-value>)',
          700: 'rgb(var(--gray-700) / <alpha-value>)',
          800: 'rgb(var(--gray-800) / <alpha-value>)',
        },
        muted: {
          DEFAULT: 'rgb(var(--muted) / <alpha-value>)',
          foreground: 'rgb(var(--muted-foreground) / <alpha-value>)',
        },
        success: {
          DEFAULT: 'rgb(var(--success) / <alpha-value>)',
          foreground: 'rgb(var(--success-foreground) / <alpha-value>)',
        },
        warning: {
          DEFAULT: 'rgb(var(--warning) / <alpha-value>)',
          foreground: 'rgb(var(--warning-foreground) / <alpha-value>)',
        },
        error: {
          DEFAULT: 'rgb(var(--error) / <alpha-value>)',
          foreground: 'rgb(var(--error-foreground) / <alpha-value>)',
        },
        info: {
          DEFAULT: 'rgb(var(--info) / <alpha-value>)',
          foreground: 'rgb(var(--info-foreground) / <alpha-value>)',
        },
        border: {
          subtle: 'rgb(var(--border-subtle) / <alpha-value>)',
          DEFAULT: 'rgb(var(--border) / <alpha-value>)',
          strong: 'rgb(var(--border-strong) / <alpha-value>)',
        },
        input: 'rgb(var(--input) / <alpha-value>)',
        ring: 'rgb(var(--ring) / <alpha-value>)',
        dns: {
          DEFAULT: 'rgb(var(--dns) / <alpha-value>)',
          foreground: 'rgb(var(--dns-foreground) / <alpha-value>)',
        },
        uptime: {
          DEFAULT: 'rgb(var(--uptime) / <alpha-value>)',
          foreground: 'rgb(var(--uptime-foreground) / <alpha-value>)',
        },
        ssl: {
          DEFAULT: 'rgb(var(--ssl) / <alpha-value>)',
          foreground: 'rgb(var(--ssl-foreground) / <alpha-value>)',
        },
        blacklist: {
          DEFAULT: 'rgb(var(--blacklist) / <alpha-value>)',
          foreground: 'rgb(var(--blacklist-foreground) / <alpha-value>)',
        },
        billing: {
          DEFAULT: 'rgb(var(--billing) / <alpha-value>)',
          foreground: 'rgb(var(--billing-foreground) / <alpha-value>)',
        },
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
};
