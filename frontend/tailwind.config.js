// Couleurs du logo DEN Source Group : bordeaux (#8B0319) et orange (#F28A14).
// Reprend à l'identique la configuration qui était écrite dans templates/components/_assets.html
// (Tailwind par CDN) : l'apparence ne doit pas changer.
module.exports = {
  content: [
    "../templates/**/*.html",
    "../apps/**/templates/**/*.html",
    "../apps/**/*.py", // classes écrites dans le code (badges, formulaires...)
    "../static/js/**/*.js",
  ],
  theme: {
    extend: {
      fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"] },
      colors: {
        marque: {
          50: "#fdf2f3", 100: "#fbe5e7", 200: "#f6cdd2", 300: "#ee9fa8", 400: "#e16673",
          500: "#c93448", 600: "#a80c26", 700: "#8b0319", 800: "#6f0616", 900: "#560512", 950: "#33030a",
        },
        accent: {
          50: "#fff8ec", 100: "#ffeed0", 200: "#fdd9a0", 300: "#fbbd63", 400: "#f7a038",
          500: "#f28a14", 600: "#d97008", 700: "#b45509", 800: "#90430d", 900: "#763a0e",
        },
      },
    },
  },
};
