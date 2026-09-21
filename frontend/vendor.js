// Copie dans static/vendor/ les fichiers des bibliothèques (Alpine.js, Font Awesome) : ils sont
// servis par l'application elle-même, sans CDN. À relancer après une mise à jour de version.
const fs = require("fs");
const path = require("path");

const racine = path.resolve(__dirname, "..", "static", "vendor");
const modules = path.resolve(__dirname, "node_modules");

function copier(source, cible) {
  fs.mkdirSync(path.dirname(cible), { recursive: true });
  fs.copyFileSync(source, cible);
  console.log("copié", path.relative(path.resolve(__dirname, ".."), cible));
}

copier(path.join(modules, "alpinejs/dist/cdn.min.js"), path.join(racine, "alpine/alpine.min.js"));
const fa = path.join(modules, "@fortawesome/fontawesome-free");
copier(path.join(fa, "css/all.min.css"), path.join(racine, "fontawesome/css/all.min.css"));
for (const police of ["fa-solid-900.woff2", "fa-regular-400.woff2"]) {
  copier(path.join(fa, "webfonts", police), path.join(racine, "fontawesome/webfonts", police));
}
copier(path.join(fa, "LICENSE.txt"), path.join(racine, "fontawesome/LICENSE.txt"));
