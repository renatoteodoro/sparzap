// Config do Tailwind (Play CDN em dev) apontando para os tokens de
// static/css/tokens.css — ver PRD.md secao 9.6.
tailwind.config = {
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        forest: 'var(--forest)',
        green: 'var(--green)',
        'dark-green': 'var(--dark-green)',
        blue: 'var(--blue)',
        'hover-blue': 'var(--hover-blue)',
        teal: 'var(--teal)',
        'teal-gray': 'var(--teal-gray)',
        'cool-gray': 'var(--cool-gray)',
        silver: 'var(--silver)',
        surface: 'var(--white)',
        ink: 'var(--black)',
        warning: 'var(--warning)',
        danger: 'var(--danger)',
      },
      fontFamily: {
        serif: ['DM Serif Display', 'Georgia', 'serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['Source Code Pro', 'ui-monospace', 'monospace'],
      },
      borderRadius: {
        input: '4px',
        link: '8px',
        card: '16px',
        panel: '24px',
        hero: '48px',
      },
      boxShadow: {
        forest: 'var(--shadow-forest)',
        subtle: 'var(--shadow-subtle)',
        standard: 'var(--shadow-standard)',
      },
    },
  },
};
