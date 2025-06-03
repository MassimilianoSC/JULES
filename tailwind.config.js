/** @type {import('tailwindcss').Config} */
module.exports = {
  /* File che Tailwind deve analizzare per “purgare” le classi inutilizzate */
  content: [
    './templates/**/*.html',   // i tuoi template (Jinja, Django, ecc.)
    './static/**/*.js',        // eventuale JS vanilla o React/Vue compilato qui
    './main.py',               // se hai classi in stringhe Python
    './src/styles/**/*.css',   // 👈 la cartella dove metterai hqe.css
  ],

  /* Se hai classi generate dinamicamente (es. da un CMS) puoi metterle in safelist */
  safelist: [{ pattern: /.*/ }],

  theme: {
    extend: {
      /* 🎨 Palette HQE */
      colors: {
        hq: {
          purple:   '#5B3A9B', // <-- nuovo colore corporate viola
          blue:     '#003B71',
          blueLight:'#33689C',
          gray:     '#4B5563',
          white:    '#FFFFFF',
        },
      },

      /* 🔤 Tipografia corporate */
      fontFamily: {
        heading: ['Montserrat', 'ui-sans-serif', 'system-ui'],
        sans:    ['Inter', 'Open Sans',  'ui-sans-serif', 'system-ui'],
      },

      /* 🟦 Raggi e ombre “morbidi” */
      borderRadius: {
        lg: '0.75rem',  // 12 px  (card, bottoni)
        xl: '1rem',     // 16 px  (modali)
      },
      boxShadow: {
        header: '0 1px 3px 0 rgb(0 0 0 / 0.05)',
        card:   '0 2px 8px 0 rgb(0 0 0 / 0.07)',
      },
    },
  },

  plugins: [
    require('@tailwindcss/forms'), // form-control belli e coerenti
  ],
};
