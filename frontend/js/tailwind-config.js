/**
 * Shared Tailwind CDN config — "Premium Editorial Fintech" design system.
 * Included on every page right after the Tailwind CDN <script> tag.
 * Neutrals match premium_editorial_fintech/DESIGN.md exactly; only the
 * primary/accent family is swapped from the design's gold to Gaxtron web's emerald.
 */
tailwind.config = {
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Accent family — emerald (web). The Android app keeps the original gold.
        primary: '#34D399',
        'primary-container': '#0F9D68',
        'on-primary': '#06281B',
        'on-primary-container': '#E7FBF2',
        'primary-fixed': '#A7F3D0',
        'primary-fixed-dim': '#34D399',
        'on-primary-fixed': '#04231A',
        'on-primary-fixed-variant': '#0B6B49',
        'inverse-primary': '#0F9D68',
        'surface-tint': '#34D399',

        // Neutrals — unchanged from DESIGN.md
        background: '#0B0B0A',
        surface: '#131312',
        'surface-dim': '#131312',
        'surface-bright': '#3a3938',
        'surface-container-lowest': '#0e0e0d',
        'surface-container-low': '#1c1c1a',
        'surface-container': '#20201e',
        'surface-container-high': '#2a2a29',
        'surface-container-highest': '#353533',
        'surface-variant': '#353533',
        'on-surface': '#e5e2df',
        'on-surface-variant': '#d3c4b0',
        'inverse-surface': '#e5e2df',
        'inverse-on-surface': '#31302f',
        'on-background': '#e5e2df',
        outline: '#9c8f7c',
        'outline-variant': '#3A3833',

        secondary: '#c9c6c0',
        'on-secondary': '#31312c',
        'secondary-container': '#474742',
        'on-secondary-container': '#b7b5af',
        'secondary-fixed': '#e5e2db',
        'secondary-fixed-dim': '#c9c6c0',
        'on-secondary-fixed': '#1c1c18',
        'on-secondary-fixed-variant': '#474742',

        tertiary: '#a2c9ff',
        'on-tertiary': '#00315c',
        'tertiary-container': '#6ba1e5',
        'on-tertiary-container': '#003764',
        'tertiary-fixed': '#d3e4ff',
        'tertiary-fixed-dim': '#a2c9ff',
        'on-tertiary-fixed': '#001c38',
        'on-tertiary-fixed-variant': '#004882',

        error: '#ffb4ab',
        'on-error': '#690005',
        'error-container': '#93000a',
        'on-error-container': '#ffdad6',
      },
      borderRadius: {
        DEFAULT: '0px',
        lg: '0px',
        xl: '0px',
        full: '9999px',
      },
      spacing: {
        unit: '4px',
        'margin-mobile': '20px',
        'margin-desktop': '64px',
        gutter: '24px',
        'stack-sm': '8px',
        'stack-md': '16px',
        'stack-lg': '32px',
      },
      fontFamily: {
        'label-caps': ['Geist'],
        'display-lg': ['Playfair Display'],
        'headline-md': ['Playfair Display'],
        'body-lg': ['Hanken Grotesk'],
        'body-md': ['Hanken Grotesk'],
        'mono-data': ['Geist'],
      },
      fontSize: {
        'label-caps': ['12px', { lineHeight: '16px', letterSpacing: '0.08em', fontWeight: '600' }],
        'display-lg': ['48px', { lineHeight: '56px', letterSpacing: '-0.02em', fontWeight: '700' }],
        'headline-md': ['24px', { lineHeight: '32px', fontWeight: '600' }],
        'body-lg': ['18px', { lineHeight: '28px', fontWeight: '400' }],
        'body-md': ['16px', { lineHeight: '24px', fontWeight: '400' }],
        'mono-data': ['14px', { lineHeight: '20px', fontWeight: '400' }],
      },
    },
  },
};
