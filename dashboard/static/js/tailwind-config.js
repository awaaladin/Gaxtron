/**
 * Shared Tailwind CDN config — ported from the "code-companion" Lovable design's
 * Tailwind v4 @theme block (src/styles.css) into Tailwind v3 CDN syntax, since
 * cdn.tailwindcss.com only runs v3. Colors reference the CSS custom properties
 * defined in css/base.css so both files stay the single source of truth.
 */
tailwind.config = {
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: 'var(--background)',
        foreground: 'var(--foreground)',
        card: 'var(--card)',
        'card-foreground': 'var(--foreground)',
        popover: 'var(--card)',
        'popover-foreground': 'var(--foreground)',
        primary: 'var(--primary)',
        'primary-foreground': 'var(--primary-foreground)',
        'primary-deep': 'var(--primary-deep)',
        'primary-soft': 'var(--primary-soft)',
        secondary: 'var(--secondary)',
        'secondary-foreground': 'var(--secondary-foreground)',
        muted: 'var(--muted)',
        'muted-foreground': 'var(--muted-foreground)',
        accent: 'var(--accent)',
        'accent-foreground': 'var(--accent-foreground)',
        destructive: 'var(--destructive)',
        'destructive-foreground': 'var(--destructive-foreground)',
        border: 'var(--border)',
        input: 'var(--border)',
        ring: 'var(--primary)',
        outline: 'var(--outline)',
        surface: 'var(--surface)',
        'surface-low': 'var(--surface-low)',
        'surface-high': 'var(--surface-high)',
        'surface-lowest': 'var(--surface-lowest)',
      },
      fontFamily: {
        display: ['Playfair Display', 'serif'],
        body: ['Hanken Grotesk', 'sans-serif'],
        sans: ['Hanken Grotesk', 'sans-serif'],
        mono: ['Geist Mono', 'ui-monospace', 'monospace'],
      },
      spacing: {
        'margin-mobile': '20px',
        'margin-desktop': '64px',
        gutter: '24px',
        'stack-sm': '8px',
        'stack-md': '16px',
        'stack-lg': '32px',
      },
      borderRadius: {
        sm: '8px',
        md: '10px',
        lg: '14px',
        xl: '20px',
        '2xl': '28px',
      },
      keyframes: {
        'fade-up': {
          from: { opacity: 0, transform: 'translateY(18px)' },
          to: { opacity: 1, transform: 'translateY(0)' },
        },
        'fade-in': {
          from: { opacity: 0 },
          to: { opacity: 1 },
        },
        marquee: {
          from: { transform: 'translateX(0)' },
          to: { transform: 'translateX(-50%)' },
        },
        'pulse-ring': {
          '0%': { boxShadow: '0 0 0 0 color-mix(in oklab, var(--primary) 45%, transparent)' },
          '70%': { boxShadow: '0 0 0 14px transparent' },
          '100%': { boxShadow: '0 0 0 0 transparent' },
        },
      },
      animation: {
        'fade-up': 'fade-up 0.7s cubic-bezier(0.22,1,0.36,1) both',
        'fade-in': 'fade-in 0.6s ease-out both',
        marquee: 'marquee 32s linear infinite',
        'pulse-ring': 'pulse-ring 2.6s ease-out infinite',
      },
    },
  },
};
