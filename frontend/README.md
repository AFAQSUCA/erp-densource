# frontend

Compilation des styles et récupération des bibliothèques de l'interface (étape 7, lot 1). **Node n'est
nécessaire que pour régénérer** les fichiers : ceux-ci sont versionnés dans `static/` et l'application
tourne sans Node.

```bash
cd frontend
npm install
npm run build        # = build:css (Tailwind) + vendor (Alpine.js, Font Awesome)
```

- `tailwind.config.js` : palette du logo (`marque` #8B0319, `accent` #F28A14), reprise à l'identique de
  l'ancienne configuration CDN. Il scanne les gabarits **et le code Python** (`apps/**/*.py`) : une classe
  Tailwind écrite dans un `templatetags/ui.py` est donc bien compilée. Ne pas composer un nom de classe
  par morceaux (`"bg-" + couleur`) : Tailwind ne le verrait pas.
- Sortie : `static/css/tailwind.css`, `static/vendor/alpine/`, `static/vendor/fontawesome/` (seules les
  polices solid et regular sont copiées).
- **À relancer** quand on ajoute une nouvelle classe Tailwind dans un gabarit ou un fichier Python.
  Un test (`apps/core/tests/test_csp.py`) signale un CSS périmé pour les couleurs de la marque.
- Politique de sécurité du contenu (CSP) : aucun script ni style écrit dans les pages ; les
  comportements passent par `static/js/app.js` (`data-confirm`, `data-imprimer`) et par les attributs
  Alpine.js. Réserves assumées : `'unsafe-eval'` (Alpine.js) et `'unsafe-inline'` pour les styles.
- Pour observer une CSP sans bloquer (mise au point) : `CSP_REPORT_ONLY=true`.
