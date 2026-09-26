# Chapitre 16 — Le socle de l'interface : gabarits, styles, connexion, notifications

> 54 fichier(s) dans ce chapitre, 2421 lignes de code.

## Ce que vous allez construire

Le **socle de l'interface** : tout ce qu'il faut pour que le **premier écran s'affiche** dans un navigateur, avant
même les écrans métier.

| Élément | Rôle |
|---|---|
| **Styles et bibliothèques locaux** | Tailwind (mise en forme), Alpine.js (petites interactions), Font Awesome (icônes), **servis par l'application** : aucun service externe |
| `templates/base.html` | la **mise en page commune** : menu de gauche, en-tête avec cloche et déconnexion |
| Composants | champ de formulaire, messages, pagination : des morceaux réutilisables |
| **Connexion** | page de connexion avec anti force brute |
| **Double authentification** | pages d'activation (QR code), de vérification et de codes de secours |
| **Notifications** | la liste et la cloche de l'en-tête |
| Page d'accueil **provisoire** | le temps que le tableau de bord (chapitre 26) existe |

## Prérequis

- Chapitres 1 à 15 terminés ; `python manage.py migrate` à jour.
- **Node.js** installé (`node --version`) : on s'en sert **uniquement** pour compiler les styles.

## Notions de ce chapitre

- **Gabarit (template)** : un fichier HTML où `{{ variable }}` affiche une valeur et `{% instruction %}`
  exécute une logique (boucle, condition, inclusion). Django **échappe automatiquement** le HTML des
  variables : c'est la protection contre les attaques XSS.
- **Héritage de gabarits** : `{% extends "base.html" %}` puis des `{% block contenu %}…{% endblock %}` qui
  remplissent les trous du gabarit parent. Toute page hérite de `base.html`.
- **`{% include "components/_champ.html" %}`** : insère un morceau réutilisable.
- **Processeur de contexte** : une fonction qui ajoute des variables (`menu`, `nombre_non_lues`) à **tous**
  les gabarits, sans que chaque vue s'en occupe.
- **Vue basée sur une classe** (`ListView`, `FormView`, `LoginView`, `View`) : une classe dont les méthodes
  `get()` et `post()` répondent aux requêtes. Les **mixins** (`LoginRequiredMixin`, `RoleRequiredMixin`) ajoutent
  des comportements.
- **Espaces de noms d'URL** : `app_name = "accounts"` puis `reverse("accounts:login")` : le nom logique d'une
  page ne change pas si son adresse change.
- **Jeton CSRF** : `{% csrf_token %}` dans chaque formulaire `POST` : sans lui, un site malveillant pourrait
  déclencher une action à votre insu.
- **Fichiers statiques** : `{% static 'css/tailwind.css' %}` donne l'adresse d'un fichier du dossier `static/`.
- **Politique de sécurité du contenu (CSP)** : le navigateur refuse tout script ou style qui ne vient pas de
  notre serveur. **Conséquence** : *aucune page ne contient de JavaScript écrit en ligne* ; les
  comportements passent par `static/js/app.js`.
- **Tailwind** : des classes utilitaires (`text-sm`, `bg-marque-600`, `px-4`) plutôt que du CSS écrit à la
  main. Un compilateur lit **tous les gabarits**, retrouve les classes utilisées et fabrique un fichier CSS
  minimal. **À chaque nouvelle classe, il faut recompiler.**
- **Alpine.js** : de petits attributs (`x-data`, `x-show`, `@click`) pour les interactions (par exemple
  ouvrir le menu sur téléphone).

## Étape 1 — Les images de la marque

Le projet utilise quatre images : le **logo**, l'**icône** du navigateur et deux icônes d'application. Si vous
avez le dépôt de référence, copiez `static/img/logo-emblem.jpg`, `favicon.png`, `icon-192.png` et
`icon-512.png`. Sinon, fabriquez quatre **images de remplacement** (vous les remplacerez plus tard par le vrai
logo). Créez le fichier `faire_images.py` à la racine :

```python
"""Fabrique quatre images de remplacement (à remplacer plus tard par le vrai logo)."""
from pathlib import Path

from PIL import Image, ImageDraw

dossier = Path("static/img")
dossier.mkdir(parents=True, exist_ok=True)

BORDEAUX, ORANGE = (139, 3, 25), (242, 138, 20)


def fabriquer(nom, taille, format_image):
    image = Image.new("RGB", taille, BORDEAUX)
    dessin = ImageDraw.Draw(image)
    largeur, hauteur = taille
    marge = min(largeur, hauteur) // 5
    dessin.rectangle([marge, marge, largeur - marge, hauteur - marge], outline=ORANGE, width=max(2, marge // 4))
    dessin.text((largeur // 2 - 12, hauteur // 2 - 5), "DEN", fill=ORANGE)
    image.save(dossier / nom, format_image)


fabriquer("logo-emblem.jpg", (344, 258), "JPEG")
fabriquer("favicon.png", (128, 128), "PNG")
fabriquer("icon-192.png", (192, 192), "PNG")
fabriquer("icon-512.png", (512, 512), "PNG")
print("4 images créées dans", dossier)
```

```bash
python faire_images.py
```

**Résultat attendu :** `4 images créées dans static/img`. Vous pouvez ensuite supprimer `faire_images.py`.

## Étape 2 — La chaîne de compilation des styles

Le dossier `frontend/` décrit comment fabriquer les fichiers de l'interface. **Node n'est nécessaire que pour ça** :
les fichiers produits (`static/css/tailwind.css`, `static/vendor/…`) suffisent ensuite pour faire tourner le site.

#### `frontend/package.json`

*15 lignes*

```json
{
  "name": "erp-densource-frontend",
  "private": true,
  "description": "Compilation des styles et récupération des bibliothèques de l'interface (étape 7). Les fichiers produits sont versionnés dans static/ : Node n'est nécessaire que pour les régénérer.",
  "scripts": {
    "build": "npm run build:css && npm run vendor",
    "build:css": "tailwindcss -c tailwind.config.js -i input.css -o ../static/css/tailwind.css --minify",
    "vendor": "node vendor.js"
  },
  "devDependencies": {
    "@fortawesome/fontawesome-free": "6.5.2",
    "alpinejs": "3.14.1",
    "tailwindcss": "3.4.17"
  }
}
```

`npm run build` enchaîne deux scripts : `build:css` (Tailwind) et `vendor` (copie Alpine.js et Font Awesome).
Les versions sont **épinglées** pour un résultat reproductible.

#### `frontend/tailwind.config.js`

*26 lignes*

```javascript
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
```

Deux points importants : les **couleurs de la marque** (`marque` = bordeaux #8B0319, `accent` = orange
#F28A14) sont définies ici ; et `content` liste **où Tailwind cherche les classes** : les gabarits **et le
code Python** (des classes sont écrites dans `apps/core/templatetags/ui.py`). Ne composez donc jamais un nom de
classe par morceaux (`"bg-" + couleur`) : Tailwind ne le verrait pas.

#### `frontend/input.css`

*74 lignes*

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

/* Éléments Alpine.js masqués tant que le script n'a pas démarré (évite un flash à l'affichage). */
[x-cloak] { display: none !important; }

/* --- Graphiques du tableau de bord (apps/core/graphiques.py, templates/components/_graphique_*.html) ---
   Palette catégorielle validée avec dataviz/scripts/validate_palette.js sur fond blanc :
   bleu, orange, aqua (dans cet ordre). L'interface n'a pas de thème sombre : un seul jeu de valeurs.
   Marques fines (colonnes ≤ 24 px, bout arrondi de 4 px, socle droit), quadrillage en filet plein,
   texte toujours en encre neutre (jamais dans la couleur de la série). */
:root {
  --viz-1: #2a78d6;
  --viz-2: #eb6834;
  --viz-3: #1baf7a;
  --viz-grille: #e1e0d9;
  --viz-axe: #c3c2b7;
}
.viz-s1 { background-color: var(--viz-1); }
.viz-s2 { background-color: var(--viz-2); }
.viz-s3 { background-color: var(--viz-3); }

/* Barres horizontales : libellé | piste | valeur */
.viz-barres { display: grid; gap: 0.5rem; }
.viz-barre-ligne { display: grid; grid-template-columns: minmax(6rem, 10rem) 1fr minmax(3rem, auto); align-items: center; gap: 0.75rem; font-size: 0.875rem; }
.viz-barre-libelle { color: #334155; overflow-wrap: anywhere; }
.viz-piste { display: block; height: 1.25rem; }
.viz-barre { display: block; height: 100%; border-radius: 0 4px 4px 0; transition: opacity 0.15s; }
.viz-barre-ligne:hover .viz-barre { opacity: 0.8; }
.viz-barre-valeur { text-align: right; font-weight: 600; color: #0f172a; font-variant-numeric: tabular-nums; white-space: nowrap; }
@media (max-width: 480px) {
  .viz-barre-ligne { grid-template-columns: 1fr auto; }
  .viz-barre-ligne .viz-piste { grid-column: 1 / -1; grid-row: 2; }
}

/* Légende (≥ 2 séries) */
.viz-legende { display: flex; flex-wrap: wrap; gap: 0.25rem 1rem; margin-bottom: 0.75rem; font-size: 0.8125rem; color: #334155; }
.viz-legende li { display: flex; align-items: center; gap: 0.375rem; }
.viz-cle { display: inline-block; width: 0.75rem; height: 0.75rem; border-radius: 2px; }

/* Colonnes groupées */
.viz-colonnes { display: grid; grid-template-columns: 3rem 1fr; column-gap: 0.5rem; }
.viz-axe-y { position: relative; height: 12rem; font-size: 0.75rem; color: #475569; font-variant-numeric: tabular-nums; }
.viz-axe-y span { position: absolute; right: 0; transform: translateY(50%); line-height: 1; }
.viz-trace { position: relative; height: 12rem; border-bottom: 1px solid var(--viz-axe); }
.viz-grille { position: absolute; left: 0; right: 0; height: 0; border-top: 1px solid var(--viz-grille); }
.viz-grappes { position: absolute; inset: 0; display: flex; }
.viz-grappe { position: relative; flex: 1 1 0; height: 100%; display: flex; align-items: flex-end; justify-content: center; border-radius: 4px 4px 0 0; outline: none; }
.viz-grappe:hover, .viz-grappe:focus { background-color: rgba(15, 23, 42, 0.05); }
.viz-grappe:focus-visible { box-shadow: inset 0 0 0 2px var(--viz-1); }
.viz-colonnes-serie { display: flex; align-items: flex-end; justify-content: center; gap: 2px; width: 80%; height: 100%; }
.viz-colonne { display: block; flex: 1 1 0; min-width: 0; max-width: 24px; border-radius: 4px 4px 0 0; }
.viz-axe-x { display: flex; margin-top: 0.375rem; font-size: 0.75rem; color: #475569; }
.viz-axe-x span { flex: 1 1 0; min-width: 0; text-align: center; line-height: 1.2; white-space: nowrap; }
/* Beaucoup de mois sur un petit écran : un libellé sur deux, le dernier mois toujours visible (les valeurs restent dans l'infobulle et le tableau). */
@media (max-width: 640px) { .viz-dense .viz-axe-x span:nth-child(odd) { visibility: hidden; } }
.viz-axe-x small { display: block; font-size: 0.6875rem; color: #64748b; }

/* Infobulle : la valeur d'abord (en gras), le nom de la série ensuite ; clé = petit trait de la couleur de la série */
.viz-info { display: none; position: absolute; bottom: calc(100% + 6px); z-index: 20; min-width: 10rem; padding: 0.5rem 0.625rem; background: #fff; border: 1px solid #cbd5e1; border-radius: 0.5rem; box-shadow: 0 4px 12px rgba(15, 23, 42, 0.12); font-size: 0.8125rem; pointer-events: none; }
.viz-info-milieu { left: 50%; transform: translateX(-50%); }
.viz-info-debut { left: 0; }
.viz-info-fin { right: 0; }
.viz-grappe:hover .viz-info, .viz-grappe:focus .viz-info { display: block; }
.viz-info-titre { display: block; margin-bottom: 0.25rem; color: #475569; font-weight: 500; }
.viz-info-ligne { display: flex; align-items: center; gap: 0.5rem; white-space: nowrap; }
.viz-trait { display: inline-block; width: 0.75rem; height: 2px; border-radius: 1px; }
.viz-info-valeur { font-weight: 600; color: #0f172a; font-variant-numeric: tabular-nums; }
.viz-info-nom { color: #475569; }

/* Un tableau qui défile horizontalement contient aussi ses libellés cachés (.sr-only est en position absolue) :
   sans cela, ils sortaient du conteneur et élargissaient toute la page sur téléphone. */
.overflow-x-auto { position: relative; }
```

#### `frontend/vendor.js`

*21 lignes*

```javascript
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
```

#### `frontend/.gitignore`

*1 ligne*

```bash
node_modules/
```

#### `frontend/README.md`

*24 lignes* — frontend

````markdown
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
````

## Étape 3 — Les gabarits communs

Créez d'abord les dossiers :

```bash
mkdir -p templates/components templates/registration templates/accounts static/js
```

#### `templates/components/_assets.html`

*9 lignes*

```django
{% load static %}{# Styles (Tailwind compilé), icônes et Alpine.js : servis par l'application elle-même. Partagés par l'interface de bureau et l'espace mobile. #}
{% comment %}
  Les fichiers viennent de frontend/ (voir frontend/package.json) et sont versionnés dans static/.
  Aucun script ni style écrit dans les pages : la politique de sécurité (CSP) interdit le code en ligne.
{% endcomment %}
<link rel="stylesheet" href="{% static 'css/tailwind.css' %}">
<link rel="stylesheet" href="{% static 'vendor/fontawesome/css/all.min.css' %}">
<script defer src="{% static 'js/app.js' %}"></script>
<script defer src="{% static 'vendor/alpine/alpine.min.js' %}"></script>
```

Les trois fichiers chargés sont locaux : le CSS compilé, Font Awesome, `app.js` puis Alpine.js (attribut `defer`
: le script s'exécute après l'affichage de la page).

#### `static/js/app.js`

*23 lignes*

```javascript
// Comportements communs de l'interface. Aucun code n'est écrit dans les pages (CSP stricte) :
// les gabarits déclarent leur intention par des attributs « data-… » que ce fichier interprète.
//
//   <form data-confirm="Question ?">   demande confirmation avant l'envoi du formulaire
//   <button data-imprimer>             ouvre la fenêtre d'impression
(function () {
  "use strict";

  document.addEventListener("submit", function (evenement) {
    var formulaire = evenement.target;
    var question = formulaire && formulaire.dataset ? formulaire.dataset.confirm : "";
    if (question && !window.confirm(question)) {
      evenement.preventDefault();
    }
  });

  document.addEventListener("click", function (evenement) {
    var declencheur = evenement.target.closest ? evenement.target.closest("[data-imprimer]") : null;
    if (declencheur) {
      window.print();
    }
  });
})();
```

Il n'y a **aucun code dans les pages** : un formulaire qui demande confirmation porte simplement
`data-confirm="Question ?"` ; ce fichier s'en occupe pour toute l'application.

#### `templates/base.html`

*101 lignes*

```django
{% load static %}<!DOCTYPE html>
<html lang="fr" class="h-full bg-slate-50">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block titre %}Accueil{% endblock %} · DEN Source ERP</title>
  <link rel="icon" type="image/png" href="{% static 'img/favicon.png' %}">

  {% include "components/_assets.html" %}
</head>
<body class="h-full text-slate-900 antialiased"
      x-data="{ menuOuvert: false }" @keydown.escape.window="menuOuvert = false">
  <a href="#contenu"
     class="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-white focus:px-3 focus:py-2 focus:text-sm focus:font-semibold focus:shadow">
    Aller au contenu
  </a>

  {% block layout %}
  <div class="min-h-full lg:flex">
    <div x-show="menuOuvert" x-cloak x-transition.opacity @click="menuOuvert = false"
         class="fixed inset-0 z-30 bg-slate-900/50 lg:hidden" aria-hidden="true"></div>

    <aside id="navigation" aria-label="Navigation principale"
           class="fixed inset-y-0 left-0 z-40 w-64 shrink-0 -translate-x-full transform bg-marque-900 text-marque-100 transition-transform duration-200 lg:sticky lg:top-0 lg:bottom-auto lg:h-screen lg:translate-x-0 lg:overflow-y-auto"
           :class="menuOuvert ? '!translate-x-0' : ''">
      <a href="{% url 'home' %}" class="flex h-16 items-center gap-3 border-b border-white/10 px-4 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-400">
        <span class="flex h-11 w-14 shrink-0 items-center justify-center rounded-lg bg-white p-1">
          <img src="{% static 'img/logo-emblem.jpg' %}" alt="" class="h-full w-auto">
        </span>
        <span class="leading-tight">
          <span class="block text-lg font-extrabold tracking-wide text-white">DEN</span>
          <span class="block text-[0.65rem] font-semibold uppercase tracking-[0.2em] text-accent-300">Source Group</span>
        </span>
        <span class="sr-only">Accueil DEN Source Group</span>
      </a>
      <nav class="space-y-1 px-3 py-4">
        {% for entree in menu %}
          <a href="{{ entree.url }}"
             {% if entree.actif %}aria-current="page"{% endif %}
             class="flex items-center gap-3 rounded-lg border-l-4 px-3 py-2 text-sm font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-400
                    {% if entree.actif %}border-accent-500 bg-white/10 text-white{% else %}border-transparent text-marque-100 hover:bg-white/10 hover:text-white{% endif %}">
            <i class="fa-solid {{ entree.icone }} w-5 text-center {% if entree.actif %}text-accent-400{% endif %}" aria-hidden="true"></i>
            {{ entree.libelle }}
          </a>
        {% endfor %}
      </nav>
    </aside>

    <div class="flex min-h-full flex-1 flex-col lg:min-w-0">
      <div class="h-1 bg-gradient-to-r from-marque-700 via-marque-500 to-accent-500" aria-hidden="true"></div>
      <header class="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-slate-200 bg-white px-4 sm:px-6 lg:px-8">
        <div class="flex items-center gap-3">
          <button type="button" class="rounded-lg p-2 text-slate-600 hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 lg:hidden"
                  @click="menuOuvert = !menuOuvert" aria-controls="navigation" :aria-expanded="menuOuvert.toString()">
            <span class="sr-only">Ouvrir le menu</span>
            <i class="fa-solid fa-bars" aria-hidden="true"></i>
          </button>
          <p class="text-sm font-semibold text-slate-800">{% block entete %}{% endblock %}</p>
        </div>
        {% if user.is_authenticated %}
          <div class="flex items-center gap-4">
            <a href="{% url 'notifications:liste' %}"
               class="relative rounded-lg p-2 text-slate-600 hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
              <i class="fa-regular fa-bell" aria-hidden="true"></i>
              {% if nombre_non_lues %}
                <span class="absolute -right-0.5 -top-0.5 flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-accent-500 px-1 text-[0.65rem] font-bold text-slate-900" aria-hidden="true">{{ nombre_non_lues }}</span>
              {% endif %}
              <span class="sr-only">Notifications{% if nombre_non_lues %} : {{ nombre_non_lues }} non lue{{ nombre_non_lues|pluralize }}{% endif %}</span>
            </a>
            <div class="hidden text-right leading-tight sm:block">
              <p class="text-sm font-medium text-slate-900">{{ user.get_full_name|default:user.username }}</p>
              <p class="text-xs text-slate-600">{{ user.get_role_display|default:"Administrateur" }}</p>
            </div>
            {% if mfa_requise %}
              <a href="{% url 'accounts:mfa_codes' %}" title="Codes de secours de la double authentification"
                 class="rounded-lg p-2 text-slate-600 hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
                <i class="fa-solid fa-shield-halved" aria-hidden="true"></i>
                <span class="sr-only">Codes de secours (double authentification)</span>
              </a>
            {% endif %}
            <form method="post" action="{% url 'accounts:logout' %}">
              {% csrf_token %}
              <button type="submit"
                      class="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
                <i class="fa-solid fa-right-from-bracket" aria-hidden="true"></i>
                Déconnexion
              </button>
            </form>
          </div>
        {% endif %}
      </header>

      <main id="contenu" class="flex-1 px-4 py-6 sm:px-6 lg:px-8">
        {% include "components/_messages.html" %}
        {% block contenu %}{% endblock %}
      </main>
    </div>
  </div>
  {% endblock layout %}
</body>
</html>
```

Structure de la page : un menu latéral (`{% for entree in menu %}` : le menu produit par le registre du chapitre
3), une en-tête (cloche des notifications, nom et rôle de l'utilisateur, lien vers les codes de secours pour les
rôles soumis à la MFA, bouton de déconnexion en `POST` avec jeton CSRF) et la zone `{% block contenu %}`. Les blocs
`titre`, `entete`, `layout` et `contenu` sont les « trous » que remplissent les pages filles.

#### `templates/components/_champ.html`

*11 lignes* — Champ de formulaire accessible : {% include "components/_champ.html" with champ=form.nom %}

```django
{# Champ de formulaire accessible : {% include "components/_champ.html" with champ=form.nom %} #}
<div>
  <label for="{{ champ.id_for_label }}" class="block text-sm font-medium text-slate-800">
    {{ champ.label }}{% if champ.field.required %}<span class="text-red-700" aria-hidden="true"> *</span>{% endif %}
  </label>
  <div class="mt-1">{{ champ }}</div>
  {% if champ.help_text %}<p class="mt-1 text-xs text-slate-600">{{ champ.help_text }}</p>{% endif %}
  {% for erreur in champ.errors %}
    <p class="mt-1 text-xs font-medium text-red-700" role="alert">{{ erreur }}</p>
  {% endfor %}
</div>
```

#### `templates/components/_messages.html`

*21 lignes*

```django
{% if messages %}
  <div class="mb-5 space-y-2" aria-label="Notifications">
    {% for message in messages %}
      <div x-data="{ visible: true }" x-show="visible"
           role="{% if message.level_tag == 'error' %}alert{% else %}status{% endif %}"
           class="flex items-start justify-between gap-3 rounded-lg border px-4 py-3 text-sm
                  {% if message.level_tag == 'success' %}border-emerald-300 bg-emerald-50 text-emerald-900
                  {% elif message.level_tag == 'error' %}border-red-300 bg-red-50 text-red-900
                  {% elif message.level_tag == 'warning' %}border-amber-300 bg-amber-50 text-amber-900
                  {% else %}border-blue-300 bg-blue-50 text-blue-900{% endif %}">
        <p>
          <i class="fa-solid {% if message.level_tag == 'success' %}fa-circle-check{% elif message.level_tag == 'error' %}fa-circle-exclamation{% elif message.level_tag == 'warning' %}fa-triangle-exclamation{% else %}fa-circle-info{% endif %} mr-2" aria-hidden="true"></i>{{ message }}
        </p>
        <button type="button" @click="visible = false" class="rounded p-0.5 opacity-70 hover:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-current">
          <span class="sr-only">Fermer le message</span>
          <i class="fa-solid fa-xmark" aria-hidden="true"></i>
        </button>
      </div>
    {% endfor %}
  </div>
{% endif %}
```

#### `templates/components/_pagination.html`

*22 lignes*

```django
{% if page_obj.has_other_pages %}
  <nav class="mt-4 flex flex-wrap items-center justify-between gap-3" aria-label="Pagination">
    <p class="text-sm text-slate-700">
      Page {{ page_obj.number }} sur {{ page_obj.paginator.num_pages }}
      · {{ page_obj.paginator.count }} résultat{{ page_obj.paginator.count|pluralize }}
    </p>
    <div class="flex gap-2">
      {% if page_obj.has_previous %}
        <a href="{% querystring page=page_obj.previous_page_number %}"
           class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
          Précédent
        </a>
      {% endif %}
      {% if page_obj.has_next %}
        <a href="{% querystring page=page_obj.next_page_number %}"
           class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
          Suivant
        </a>
      {% endif %}
    </div>
  </nav>
{% endif %}
```

#### `templates/403.html`

*14 lignes*

```django
{% extends "base.html" %}
{% block titre %}Accès refusé{% endblock %}
{% block entete %}Accès refusé{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-lg rounded-xl border border-slate-200 bg-white p-8 text-center shadow-sm">
  <span class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-marque-50 text-marque-700">
    <i class="fa-solid fa-lock" aria-hidden="true"></i>
  </span>
  <h1 class="mt-4 text-xl font-bold text-slate-900">Accès refusé</h1>
  <p class="mt-2 text-sm text-slate-700">Votre rôle ne vous permet pas d'accéder à cette page.</p>
  <a href="{% url 'home' %}" class="mt-6 inline-block rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white hover:bg-marque-700">Retour à l'accueil</a>
</div>
{% endblock %}
```

#### `templates/404.html`

*14 lignes*

```django
{% extends "base.html" %}
{% block titre %}Page introuvable{% endblock %}
{% block entete %}Page introuvable{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-lg rounded-xl border border-slate-200 bg-white p-8 text-center shadow-sm">
  <span class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-700">
    <i class="fa-solid fa-magnifying-glass" aria-hidden="true"></i>
  </span>
  <h1 class="mt-4 text-xl font-bold text-slate-900">Page introuvable</h1>
  <p class="mt-2 text-sm text-slate-700">Cette page n'existe pas ou a été déplacée.</p>
  <a href="{% url 'home' %}" class="mt-6 inline-block rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white hover:bg-marque-700">Retour à l'accueil</a>
</div>
{% endblock %}
```

Django utilise automatiquement `403.html` et `404.html` pour les erreurs « accès refusé » et « page
introuvable ».

## Étape 4 — La connexion et la double authentification

#### `templates/registration/login.html`

*51 lignes*

```django
{% extends "base.html" %}
{% load static %}
{% block titre %}Connexion{% endblock %}

{% block layout %}
<div class="flex min-h-full items-center justify-center bg-gradient-to-b from-marque-50 via-white to-white px-4 py-12">
  <div class="w-full max-w-md">
    <div class="mb-8 text-center">
      <span class="mx-auto inline-block rounded-2xl bg-white p-3 shadow-md ring-1 ring-marque-100"><img src="{% static 'img/logo-emblem.jpg' %}" alt="DEN Source Group" class="h-24 w-auto"></span>
      <h1 class="mt-3 text-3xl font-extrabold tracking-wide text-marque-700">DEN</h1>
      <p class="text-xs font-semibold uppercase tracking-[0.3em] text-slate-700">Source Group</p>
      <p class="mt-4 text-sm text-slate-600">Connectez-vous pour accéder à votre espace.</p>
    </div>

    <form method="post" class="space-y-5 rounded-2xl border border-slate-200 border-t-4 border-t-accent-500 bg-white p-6 shadow-sm">
      {% csrf_token %}
      <input type="hidden" name="next" value="{{ next }}">

      {% if blocage %}
        <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900"><p>{{ blocage }}</p></div>
      {% endif %}

      {% if form.non_field_errors %}
        <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">
          {% for erreur in form.non_field_errors %}<p>{{ erreur }}</p>{% endfor %}
        </div>
      {% endif %}

      <div>
        <label for="{{ form.username.id_for_label }}" class="block text-sm font-medium text-slate-800">Identifiant</label>
        <input type="text" name="username" id="{{ form.username.id_for_label }}" required autofocus
               autocomplete="username" value="{{ form.username.value|default:'' }}"
               class="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30">
      </div>
      <div>
        <label for="{{ form.password.id_for_label }}" class="block text-sm font-medium text-slate-800">Mot de passe</label>
        <input type="password" name="password" id="{{ form.password.id_for_label }}" required
               autocomplete="current-password"
               class="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30">
      </div>
      <button type="submit"
              class="w-full rounded-lg bg-marque-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
        Se connecter
      </button>
      <p class="text-center text-sm">
        <a href="{% url 'accounts:password_reset' %}" class="font-medium text-marque-700 hover:underline">Mot de passe oublié ?</a>
      </p>
    </form>
  </div>
</div>
{% endblock %}
```

#### `apps/accounts/views.py`

*83 lignes*

```python
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.urls import reverse_lazy

from . import throttle
from .models import Role
from .signals import mot_de_passe_reinitialise


class ConnexionView(LoginView):
    """Page de connexion. Les connexions réussies ou ratées sont tracées dans
    ``audit_log`` par les signaux de l'app ``audit``.

    Anti force brute : après trop d'échecs pour un même identifiant depuis une même adresse (ou
    trop d'échecs depuis l'adresse), la connexion est refusée pour un temps, **même avec le bon mot
    de passe** : la vérification n'est même pas tentée."""

    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        restant = throttle.connexion_secondes_restantes(request, request.POST.get("username", ""))
        if restant:
            form = AuthenticationForm(request)  # non liée : aucune vérification de mot de passe
            blocage = f"Trop de tentatives échouées. Réessayez dans {throttle.phrase_attente(restant)}."
            reponse = self.render_to_response(self.get_context_data(form=form, blocage=blocage))
            reponse.status_code = 429
            return reponse
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        reponse = super().form_valid(form)
        throttle.connexion_reinitialiser(self.request, form.cleaned_data.get("username", ""))
        if self.request.user.role == Role.CHAUFFEUR:
            # Espace mobile : 15 minutes d'inactivité (cahier-des-charges.md:285), 30 pour le bureau.
            self.request.session.set_expiry(settings.SESSION_COOKIE_AGE_MOBILE)
        return reponse


class DeconnexionView(LogoutView):
    """Déconnexion (POST uniquement, protégée par CSRF)."""


# --- mot de passe oublié ---
#
# Les 4 étapes standard de Django, avec nos gabarits (français, mise en page du site) : demande de
# l'adresse -> confirmation d'envoi -> lien reçu par e-mail -> nouveau mot de passe -> terminé.
# Ne dit jamais si l'adresse correspond à un compte (mêmes pages dans les deux cas) : un tiers ne
# peut pas s'en servir pour savoir qui a un compte ici. Le mot de passe choisi passe par les mêmes
# règles qu'à l'inscription (AUTH_PASSWORD_VALIDATORS, longueur 10, Argon2).


class ReinitialiserMotDePasseView(PasswordResetView):
    template_name = "registration/password_reset_form.html"
    email_template_name = "registration/password_reset_email.txt"
    subject_template_name = "registration/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")


class ReinitialiserMotDePasseEnvoyeView(PasswordResetDoneView):
    template_name = "registration/password_reset_done.html"


class ReinitialiserMotDePasseConfirmerView(PasswordResetConfirmView):
    template_name = "registration/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")

    def form_valid(self, form):
        reponse = super().form_valid(form)
        mot_de_passe_reinitialise.send(sender=self.__class__, request=self.request, utilisateur=self.user)
        return reponse


class ReinitialiserMotDePasseTermineeView(PasswordResetCompleteView):
    template_name = "registration/password_reset_complete.html"
```

`ConnexionView` prolonge `LoginView` de Django : elle ajoute le **blocage anti force brute** (réponse 429 avant
même de vérifier le mot de passe) et la **session de 15 minutes** pour les chauffeurs.

#### `apps/accounts/forms.py`

*24 lignes*

```python
from django import forms

from apps.core.forms import StyleTailwindMixin


class CodeMFAForm(StyleTailwindMixin, forms.Form):
    """Code à 6 chiffres de l'application, ou code de secours (XXXXX-XXXXX)."""

    code = forms.CharField(
        label="Code",
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "one-time-code",
                "inputmode": "text",
                "autofocus": True,
                "placeholder": "123456",
                "spellcheck": "false",
            }
        ),
    )

    def clean_code(self):
        return self.cleaned_data["code"].strip()
```

#### `apps/accounts/views_mfa.py`

*206 lignes* — Écrans de la double authentification : activation, saisie du code, codes de secours.

```python
"""Écrans de la double authentification : activation, saisie du code, codes de secours.

Aucune règle ici : ``mfa.py`` décide, ``throttle.py`` limite les essais. Ces pages sont les seules
accessibles à un ADMIN ou une DIRECTION dont la session n'est pas encore vérifiée (voir
``middleware.py``). Elles n'ont de sens que pour les rôles soumis à la MFA : les autres reçoivent 404.
"""

from __future__ import annotations

import io

import qrcode
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import FormView

from . import mfa, throttle
from .forms import CodeMFAForm
from .signals import mfa_evenement


class _MFABase(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not mfa.mfa_requise(request.user):
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def prochaine_page(self) -> str:
        cible = self.request.GET.get("next") or self.request.POST.get("next") or ""
        if cible and url_has_allowed_host_and_scheme(
            cible, allowed_hosts={self.request.get_host()}, require_https=self.request.is_secure()
        ):
            return cible
        return reverse("home")

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["next"] = self.request.GET.get("next") or self.request.POST.get("next") or ""
        return contexte

    def _refus_si_bloque(self, form):
        """Réponse 429 si trop de codes faux récemment ; ``None`` sinon."""
        restant = throttle.mfa_secondes_restantes(self.request.user)
        if not restant:
            return None
        form.add_error(
            "code",
            f"Trop de codes incorrects. Réessayez dans {throttle.phrase_attente(restant)}.",
        )
        reponse = self.render_to_response(self.get_context_data(form=form))
        reponse.status_code = 429
        return reponse

    def _signaler(self, evenement: str, succes: bool = True):
        mfa_evenement.send(
            sender=type(self),
            request=self.request,
            utilisateur=self.request.user,
            evenement=evenement,
            succes=succes,
        )


class MFAVerifierView(_MFABase, FormView):
    """Saisie du code à chaque ouverture de session."""

    template_name = "accounts/mfa_verifier.html"
    form_class = CodeMFAForm

    def get(self, request, *args, **kwargs):
        if mfa.est_verifiee(request):
            return redirect(self.prochaine_page())
        if mfa.appareil_actif(request.user) is None:
            return redirect(reverse("accounts:mfa_activer"))
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if mfa.appareil_actif(request.user) is None:
            return redirect(reverse("accounts:mfa_activer"))
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        refus = self._refus_si_bloque(form)
        if refus is not None:
            return refus
        utilisateur = self.request.user
        if not mfa.verifier_code(utilisateur, form.cleaned_data["code"]):
            throttle.mfa_enregistrer_echec(utilisateur)
            self._signaler("code_refuse", succes=False)
            form.add_error("code", "Code incorrect ou déjà utilisé.")
            return self.form_invalid(form)
        throttle.mfa_reinitialiser(utilisateur)
        mfa.marquer_verifiee(self.request)
        self._signaler("code_accepte")
        return redirect(self.prochaine_page())


class MFAActiverView(_MFABase, FormView):
    """Première utilisation : scanner le QR code, confirmer avec un premier code, noter les codes de secours."""

    template_name = "accounts/mfa_activer.html"
    form_class = CodeMFAForm

    def get(self, request, *args, **kwargs):
        if mfa.appareil_actif(request.user) is not None:
            return redirect(self.prochaine_page() if mfa.est_verifiee(request) else reverse("accounts:mfa_verifier"))
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if mfa.appareil_actif(request.user) is not None:
            return redirect(reverse("accounts:mfa_verifier"))
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        appareil = mfa.preparer_activation(self.request.user)
        contexte["secret"] = " ".join(appareil.secret[i : i + 4] for i in range(0, len(appareil.secret), 4))
        return contexte

    def form_valid(self, form):
        refus = self._refus_si_bloque(form)
        if refus is not None:
            return refus
        utilisateur = self.request.user
        try:
            codes = mfa.confirmer_activation(utilisateur, form.cleaned_data["code"])
        except mfa.CodeInvalide as erreur:
            throttle.mfa_enregistrer_echec(utilisateur)
            self._signaler("activation_refusee", succes=False)
            form.add_error("code", str(erreur))
            return self.form_invalid(form)
        throttle.mfa_reinitialiser(utilisateur)
        mfa.marquer_verifiee(self.request)
        self._signaler("activation")
        return _page_codes(self.request, codes, apres_activation=True, suite=self.prochaine_page())


class MFAQrView(_MFABase, View):
    """Image du QR code d'activation : seulement tant que l'appareil n'est pas confirmé, jamais mise en cache."""

    def get(self, request):
        try:
            appareil = mfa.preparer_activation(request.user)
        except mfa.DejaActive as erreur:
            raise Http404 from erreur
        tampon = io.BytesIO()
        qrcode.make(mfa.uri_provisionnement(appareil), box_size=8, border=2).save(tampon, format="PNG")
        reponse = HttpResponse(tampon.getvalue(), content_type="image/png")
        reponse["Cache-Control"] = "no-store, private"
        return reponse


class MFACodesView(_MFABase, FormView):
    """Régénérer les codes de secours (avec un code de l'application, pas un code de secours)."""

    template_name = "accounts/mfa_codes.html"
    form_class = CodeMFAForm

    def dispatch(self, request, *args, **kwargs):
        # Cette page fait partie des pages libres de la porte MFA : elle vérifie elle-même que la
        # session est vérifiée, pour qu'un mot de passe volé ne permette pas de toucher aux codes.
        utilisateur = request.user
        if utilisateur.is_authenticated and mfa.mfa_requise(utilisateur) and not mfa.est_verifiee(request):
            return redirect(reverse("accounts:mfa_verifier"))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["restants"] = mfa.codes_secours_restants(self.request.user)
        return contexte

    def get(self, request, *args, **kwargs):
        if mfa.appareil_actif(request.user) is None:
            return redirect(reverse("accounts:mfa_activer"))
        return super().get(request, *args, **kwargs)

    def form_valid(self, form):
        refus = self._refus_si_bloque(form)
        if refus is not None:
            return refus
        utilisateur = self.request.user
        try:
            codes = mfa.regenerer_codes_secours(utilisateur, form.cleaned_data["code"])
        except mfa.CodeInvalide:
            throttle.mfa_enregistrer_echec(utilisateur)
            self._signaler("codes_refuses", succes=False)
            form.add_error("code", "Code incorrect ou déjà utilisé.")
            return self.form_invalid(form)
        throttle.mfa_reinitialiser(utilisateur)
        self._signaler("codes_regeneres")
        return _page_codes(self.request, codes, apres_activation=False, suite=reverse("home"))


def _page_codes(request, codes, *, apres_activation: bool, suite: str):
    """Affiche les codes de secours une seule fois (réponse directe, jamais mise en cache)."""
    reponse = render(
        request,
        "accounts/mfa_codes_affiches.html",
        {"codes": codes, "apres_activation": apres_activation, "suite": suite},
    )
    reponse["Cache-Control"] = "no-store, private"
    return reponse
```

Quatre vues : **vérifier** (saisir le code à chaque ouverture de session), **activer** (QR code + premier
code + codes de secours affichés **une seule fois**), **QR** (l'image, jamais mise en cache) et **codes**
(régénérer les codes de secours). La redirection après vérification refuse toute adresse extérieure au site.

#### `apps/accounts/urls.py`

*32 lignes*

```python
from django.urls import path

from . import views, views_mfa

app_name = "accounts"

urlpatterns = [
    path("connexion/", views.ConnexionView.as_view(), name="login"),
    path("deconnexion/", views.DeconnexionView.as_view(), name="logout"),
    # Double authentification (ADMIN et DIRECTION) : pages ouvertes avant la vérification.
    path("mfa/verifier/", views_mfa.MFAVerifierView.as_view(), name="mfa_verifier"),
    path("mfa/activer/", views_mfa.MFAActiverView.as_view(), name="mfa_activer"),
    path("mfa/qr/", views_mfa.MFAQrView.as_view(), name="mfa_qr"),
    path("mfa/codes/", views_mfa.MFACodesView.as_view(), name="mfa_codes"),
    # Mot de passe oublié : ouvert à tous, avant connexion.
    path("mot-de-passe/", views.ReinitialiserMotDePasseView.as_view(), name="password_reset"),
    path(
        "mot-de-passe/envoye/",
        views.ReinitialiserMotDePasseEnvoyeView.as_view(),
        name="password_reset_done",
    ),
    path(
        "mot-de-passe/confirmer/<uidb64>/<token>/",
        views.ReinitialiserMotDePasseConfirmerView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "mot-de-passe/termine/",
        views.ReinitialiserMotDePasseTermineeView.as_view(),
        name="password_reset_complete",
    ),
]
```

#### `apps/accounts/context_processors.py`

*13 lignes*

```python
from . import mfa
from .navigation import entrees_pour


def menu(request):
    """Ajoute ``menu`` (entrées visibles pour le rôle) au contexte des templates."""
    utilisateur = request.user
    if not utilisateur.is_authenticated:
        return {}
    return {
        "menu": entrees_pour(utilisateur.role_effectif, request.path),
        "mfa_requise": mfa.mfa_requise(utilisateur),
    }
```

#### `templates/accounts/mfa_verifier.html`

*34 lignes*

```django
{% extends "base.html" %}
{% load static %}
{% block titre %}Vérification en deux étapes{% endblock %}

{% block layout %}
<div class="flex min-h-full items-center justify-center bg-gradient-to-b from-marque-50 via-white to-white px-4 py-12">
  <div class="w-full max-w-md">
    <div class="mb-6 text-center">
      <span class="mx-auto inline-block rounded-2xl bg-white p-3 shadow-md ring-1 ring-marque-100"><img src="{% static 'img/logo-emblem.jpg' %}" alt="DEN Source Group" class="h-16 w-auto"></span>
      <h1 class="mt-3 text-xl font-bold text-slate-900">Vérification en deux étapes</h1>
      <p class="mt-2 text-sm text-slate-600">Saisissez le code à 6 chiffres affiché par votre application d'authentification.</p>
    </div>

    <form method="post" class="space-y-5 rounded-2xl border border-slate-200 border-t-4 border-t-accent-500 bg-white p-6 shadow-sm">
      {% csrf_token %}
      <input type="hidden" name="next" value="{{ next }}">
      <div>
        <label for="{{ form.code.id_for_label }}" class="block text-sm font-medium text-slate-800">Code</label>
        {{ form.code }}
        {% for erreur in form.code.errors %}<p role="alert" class="mt-1 text-sm text-red-800">{{ erreur }}</p>{% endfor %}
      </div>
      <button type="submit"
              class="w-full rounded-lg bg-marque-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
        Vérifier
      </button>
      <p class="text-xs text-slate-600">Téléphone perdu ? Saisissez à la place un de vos codes de secours (format XXXXX-XXXXX). Sans code de secours, l'Administrateur peut réinitialiser votre double authentification.</p>
    </form>
    <form method="post" action="{% url 'accounts:logout' %}" class="mt-4 text-center">
      {% csrf_token %}
      <button type="submit" class="text-sm text-slate-600 underline hover:text-slate-900">Se déconnecter</button>
    </form>
  </div>
</div>
{% endblock %}
```

#### `templates/accounts/mfa_activer.html`

*41 lignes*

```django
{% extends "base.html" %}
{% load static %}
{% block titre %}Activer la double authentification{% endblock %}

{% block layout %}
<div class="flex min-h-full items-center justify-center bg-gradient-to-b from-marque-50 via-white to-white px-4 py-12">
  <div class="w-full max-w-md">
    <div class="mb-6 text-center">
      <span class="mx-auto inline-block rounded-2xl bg-white p-3 shadow-md ring-1 ring-marque-100"><img src="{% static 'img/logo-emblem.jpg' %}" alt="DEN Source Group" class="h-16 w-auto"></span>
      <h1 class="mt-3 text-xl font-bold text-slate-900">Activez la double authentification</h1>
      <p class="mt-2 text-sm text-slate-600">Votre rôle exige une vérification en deux étapes. Cela ne prend qu'une minute.</p>
    </div>

    <form method="post" class="space-y-5 rounded-2xl border border-slate-200 border-t-4 border-t-accent-500 bg-white p-6 shadow-sm">
      {% csrf_token %}
      <input type="hidden" name="next" value="{{ next }}">
      <ol class="list-decimal space-y-3 pl-5 text-sm text-slate-800">
        <li>Installez une application d'authentification sur votre téléphone (Google Authenticator, Microsoft Authenticator, Authy…).</li>
        <li>Scannez ce code QR avec l'application.
          <div class="mt-2 flex justify-center"><img src="{% url 'accounts:mfa_qr' %}" alt="Code QR d'activation de la double authentification" width="200" height="200" class="rounded-lg border border-slate-200"></div>
          <p class="mt-2 text-xs text-slate-600">Impossible de scanner ? Saisissez cette clé dans l'application : <span class="font-mono font-semibold tracking-wider text-slate-900">{{ secret }}</span></p>
        </li>
        <li>Saisissez le code à 6 chiffres qu'elle affiche.</li>
      </ol>
      <div>
        <label for="{{ form.code.id_for_label }}" class="block text-sm font-medium text-slate-800">Code</label>
        {{ form.code }}
        {% for erreur in form.code.errors %}<p role="alert" class="mt-1 text-sm text-red-800">{{ erreur }}</p>{% endfor %}
      </div>
      <button type="submit"
              class="w-full rounded-lg bg-marque-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
        Activer
      </button>
    </form>
    <form method="post" action="{% url 'accounts:logout' %}" class="mt-4 text-center">
      {% csrf_token %}
      <button type="submit" class="text-sm text-slate-600 underline hover:text-slate-900">Se déconnecter</button>
    </form>
  </div>
</div>
{% endblock %}
```

#### `templates/accounts/mfa_codes.html`

*30 lignes*

```django
{% extends "base.html" %}
{% load static %}
{% block titre %}Codes de secours{% endblock %}

{% block layout %}
<div class="flex min-h-full items-center justify-center bg-gradient-to-b from-marque-50 via-white to-white px-4 py-12">
  <div class="w-full max-w-md">
    <div class="mb-6 text-center">
      <span class="mx-auto inline-block rounded-2xl bg-white p-3 shadow-md ring-1 ring-marque-100"><img src="{% static 'img/logo-emblem.jpg' %}" alt="DEN Source Group" class="h-16 w-auto"></span>
      <h1 class="mt-3 text-xl font-bold text-slate-900">Codes de secours</h1>
      <p class="mt-2 text-sm text-slate-600">Il vous reste <strong>{{ restants }}</strong> code{{ restants|pluralize }} de secours non utilisé{{ restants|pluralize }}.</p>
    </div>

    <form method="post" class="space-y-5 rounded-2xl border border-slate-200 border-t-4 border-t-accent-500 bg-white p-6 shadow-sm">
      {% csrf_token %}
      <p class="text-sm text-slate-800">Générer de nouveaux codes annule les anciens. Confirmez avec le code actuel de votre application.</p>
      <div>
        <label for="{{ form.code.id_for_label }}" class="block text-sm font-medium text-slate-800">Code</label>
        {{ form.code }}
        {% for erreur in form.code.errors %}<p role="alert" class="mt-1 text-sm text-red-800">{{ erreur }}</p>{% endfor %}
      </div>
      <button type="submit"
              class="w-full rounded-lg bg-marque-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
        Générer de nouveaux codes
      </button>
    </form>
    <p class="mt-4 text-center"><a href="{% url 'home' %}" class="text-sm text-slate-600 underline hover:text-slate-900">Retour à l'accueil</a></p>
  </div>
</div>
{% endblock %}
```

#### `templates/accounts/mfa_codes_affiches.html`

*25 lignes*

```django
{% extends "base.html" %}
{% load static %}
{% block titre %}Vos codes de secours{% endblock %}

{% block layout %}
<div class="flex min-h-full items-center justify-center bg-gradient-to-b from-marque-50 via-white to-white px-4 py-12">
  <div class="w-full max-w-md">
    <div class="mb-6 text-center">
      <span class="mx-auto inline-block rounded-2xl bg-white p-3 shadow-md ring-1 ring-marque-100"><img src="{% static 'img/logo-emblem.jpg' %}" alt="DEN Source Group" class="h-16 w-auto"></span>
      <h1 class="mt-3 text-xl font-bold text-slate-900">Conservez vos codes de secours</h1>
      <p class="mt-2 text-sm text-slate-600">{% if apres_activation %}La double authentification est activée. {% endif %}Chaque code ne sert <strong>qu'une seule fois</strong> si vous perdez votre téléphone. Ils ne seront plus jamais affichés : notez-les dans un endroit sûr (coffre, gestionnaire de mots de passe).</p>
    </div>

    <div class="space-y-5 rounded-2xl border border-slate-200 border-t-4 border-t-accent-500 bg-white p-6 shadow-sm">
      <ul class="grid grid-cols-2 gap-2 font-mono text-sm font-semibold tracking-wider text-slate-900">
        {% for code in codes %}<li class="rounded-lg bg-slate-100 px-3 py-2 text-center">{{ code }}</li>{% endfor %}
      </ul>
      <a href="{{ suite }}"
         class="block w-full rounded-lg bg-marque-600 px-4 py-2.5 text-center text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
        J'ai noté mes codes, continuer
      </a>
    </div>
  </div>
</div>
{% endblock %}
```

## Étape 5 — Aides d'affichage, notifications, page d'accueil provisoire

#### `apps/core/templatetags/ui.py`

*129 lignes* — Aides d'affichage : pastilles de statut colorées.

```python
"""Aides d'affichage : pastilles de statut colorées.

Le texte de la pastille porte toujours le sens ; la couleur est un renfort, pas
la seule information (accessibilité WCAG 2.1 AA, cahier-des-charges.md:304).
"""

from django import template
from django.utils.html import format_html

from apps.core.formats import pourcentage_signe as _pourcentage_signe

register = template.Library()

STYLES = {
    "gris": "bg-slate-100 text-slate-700 ring-slate-300",
    "bleu": "bg-blue-50 text-blue-800 ring-blue-300",
    "indigo": "bg-indigo-50 text-indigo-800 ring-indigo-300",
    "ambre": "bg-amber-50 text-amber-900 ring-amber-400",
    "vert": "bg-emerald-50 text-emerald-900 ring-emerald-400",
    "rouge": "bg-red-50 text-red-800 ring-red-300",
}

# Couleur par code de statut. Les codes identiques d'apps différentes
# (« DISPONIBLE », « EN_MISSION »...) partagent volontairement la même couleur.
COULEURS_STATUT = {
    "BROUILLON": "gris",
    "PLANIFIEE": "bleu",
    "AFFECTEE": "indigo",
    "EN_COURS_DEPART": "ambre",
    "EN_COURS_COLIS_RECUPERE": "ambre",
    "LIVREE": "vert",
    "CLOTUREE": "gris",
    # camions
    "DISPONIBLE": "vert",
    "EN_MISSION": "bleu",
    "EN_MAINTENANCE": "ambre",
    "IMMOBILISE": "rouge",
    "HORS_SERVICE": "gris",
    # chauffeurs
    "EN_CONGE": "indigo",
    "SUSPENDU": "rouge",
    "INACTIF": "gris",
    # documents réglementaires
    "VALIDE": "vert",
    "A_RENOUVELER": "ambre",
    "EXPIRE": "rouge",
    "MANQUANT": "gris",
    # ordres de réparation
    "OUVERT": "ambre",
    "CLOTURE": "gris",
    # stock
    "STOCK_BAS": "ambre",
    "RUPTURE": "rouge",
    "ENTREE": "vert",
    "SORTIE": "bleu",
    "AJUSTEMENT": "ambre",
    # incidents
    "SIGNALE": "rouge",
    "PRIS_EN_COMPTE": "bleu",
    "CLOS": "gris",
    "FAIBLE": "gris",
    "MOYENNE": "ambre",
    "GRAVE": "rouge",
    # facturation
    "A_VALIDER": "ambre",
    "EMISE": "bleu",
    "PARTIELLEMENT_PAYEE": "indigo",
    "PAYEE": "vert",
    "ECHUE": "rouge",
    # devis
    "SOUMISE": "ambre",
    "CONTRE_PROPOSEE": "ambre",
    "EN_ATTENTE_DIRECTION": "ambre",
    "VALIDEE": "bleu",
    "ENVOYEE_CLIENT": "indigo",
    "ACCEPTEE": "vert",
    "REFUSEE": "rouge",
    "EXPIREE": "rouge",
    "CONVERTIE": "vert",
    # notifications
    "INFO": "bleu",
    "ATTENTION": "ambre",
    "URGENT": "rouge",
    # congés
    "DEMANDE": "ambre",
    "VALIDATION_N1": "bleu",
    "APPROUVE": "vert",
    "EN_COURS": "indigo",
    "TERMINE": "gris",
    "REFUSE": "rouge",
    # clients
    "RECLAMATION": "rouge",
    # carburant
    "JAUNE": "ambre",
    "ROUGE": "rouge",
    "ANOMALIE": "rouge",
    "SAISIE_SUSPECTE": "ambre",
    # frais de mission (R4)
    "PREVU": "ambre",
    "CONFIRME": "vert",
    "REJETE": "rouge",
    # demandes de dépense et ordres de décaissement (parc auto, R2)
    "SOUMISE": "ambre",
    "VALIDEE": "vert",
    "REFUSEE": "rouge",
    "A_EXECUTER": "ambre",
    "EN_ATTENTE_REVALIDATION": "rouge",
    "EXECUTE": "vert",
}


@register.simple_tag
def badge(code: str, libelle: str):
    """Pastille de statut : ``{% badge mission.statut mission.get_statut_display %}``."""
    couleur = STYLES[COULEURS_STATUT.get(code, "gris")]
    return format_html(
        '<span class="inline-flex items-center rounded-full px-2.5 py-0.5 '
        'text-xs font-semibold ring-1 ring-inset {}">{}</span>',
        couleur,
        libelle,
    )


@register.filter
def pourcentage_signe(valeur, decimales=1):
    """``{{ ecart|pourcentage_signe }} %`` → « +23,3 % » (virgule française, signe explicite)."""
    if valeur is None:
        return ""
    return _pourcentage_signe(valeur, int(decimales))
```

Des **balises de gabarit personnalisées** : `{% badge %}` affiche une pastille colorée pour un statut (le texte
porte toujours le sens, la couleur n'est qu'un renfort : accessibilité).

#### `apps/core/views.py`

*80 lignes* — Aides communes aux vues.

```python
"""Aides communes aux vues."""

from .rapports import contexte_rapport


class PaginationTolerante:
    """Pagination qui ne renvoie pas d'erreur 404 sur un numéro de page inutilisable.

    Un lien enregistré vers la page 5, une page qui disparaît après un filtre ou un
    ``?page=abc`` amènent sur la première ou la dernière page existante au lieu d'une
    page d'erreur. ``?page=last`` reste accepté.
    """

    def paginate_queryset(self, queryset, page_size):
        paginator = self.get_paginator(
            queryset,
            page_size,
            orphans=self.get_paginate_orphans(),
            allow_empty_first_page=self.get_allow_empty(),
        )
        demande = self.request.GET.get(self.page_kwarg, "1")
        try:
            numero = paginator.num_pages if demande == "last" else int(demande)
        except ValueError:
            numero = 1
        numero = min(max(numero, 1), paginator.num_pages)
        page = paginator.page(numero)
        return paginator, page, page.object_list, page.has_other_pages()


class ImpressionListeMixin:
    """Transforme un ``ListView`` existant en rapport imprimable, sans dupliquer ses filtres.

    S'utilise en écrivant une sous-classe du ``ListView`` de la liste, mixin en premier pour que son
    ``get_context_data`` l'emporte : ``class XImprimerView(ImpressionListeMixin, XListView): ...``. Les
    droits (``roles``) et la recherche/les filtres (``get_queryset``) restent ceux de la liste ; seuls la
    pagination et le contexte d'affichage changent. Chaque sous-classe déclare ``titre_impression`` et
    ``colonnes`` : une suite de ``(libellé, clé)``, ``clé`` étant soit un chemin en pointillés résolu sur
    chaque objet (``"client.raison_sociale"``, méthodes get_FOO_display comprises), soit un callable
    ``clé(objet) -> str`` pour une valeur composée.
    """

    template_name = "rapports/liste_impression.html"
    titre_impression = ""
    colonnes: tuple = ()
    limite_impression = 500

    def get_titre_impression(self) -> str:
        return self.titre_impression

    def get_sous_titre_impression(self) -> str:
        return ""

    @staticmethod
    def _valeur(objet, cle):
        if callable(cle):
            return cle(objet)
        valeur = objet
        for morceau in cle.split("."):
            if valeur in (None, ""):
                return "—"
            valeur = getattr(valeur, morceau, "")
            if callable(valeur):
                valeur = valeur()
        return valeur if valeur not in (None, "") else "—"

    def get_context_data(self, **kwargs):
        objets = list(self.get_queryset()[: self.limite_impression + 1])
        tronque = len(objets) > self.limite_impression
        objets = objets[: self.limite_impression]
        contexte = contexte_rapport(
            self.request, titre=self.get_titre_impression(), sous_titre=self.get_sous_titre_impression()
        )
        contexte.update(
            entetes=[libelle for libelle, _ in self.colonnes],
            lignes=[[self._valeur(o, cle) for _, cle in self.colonnes] for o in objets],
            nombre=len(objets),
            tronque=tronque,
        )
        return contexte
```

`PaginationTolerante` : une page inexistante ou illisible affiche la première ou la dernière page au lieu d'une
erreur 404.

#### `apps/notifications/views.py`

*55 lignes* — Page « Notifications » : liste, lecture, tout marquer comme lu.

```python
"""Page « Notifications » : liste, lecture, tout marquer comme lu.

Chaque utilisateur ne voit et ne modifie que ses propres notifications (tous rôles).
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import ListView

from apps.core.views import PaginationTolerante

from . import services


class NotificationListView(LoginRequiredMixin, PaginationTolerante, ListView):
    template_name = "notifications/liste.html"
    context_object_name = "notifications"
    paginate_by = 20

    def get_queryset(self):
        return services.notifications_de(
            self.request.user, non_lues=self.request.GET.get("non_lues") == "1"
        )

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["non_lues_seulement"] = self.request.GET.get("non_lues") == "1"
        return contexte


class LireView(LoginRequiredMixin, View):
    """Marque une notification comme lue (POST) puis ouvre son lien."""

    http_method_names = ["post"]

    def post(self, request, pk):
        notification = services.notifications_de(request.user).filter(pk=pk).first()
        if notification is None:
            raise Http404
        services.marquer_lue(notification)
        cible = notification.url
        if cible and url_has_allowed_host_and_scheme(cible, allowed_hosts=None):
            return redirect(cible)
        return redirect("notifications:liste")


class ToutLireView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request):
        services.marquer_toutes_lues(request.user)
        return redirect("notifications:liste")
```

#### `apps/notifications/urls.py`

*11 lignes*

```python
from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.NotificationListView.as_view(), name="liste"),
    path("tout-lire/", views.ToutLireView.as_view(), name="tout_lire"),
    path("<int:pk>/lire/", views.LireView.as_view(), name="lire"),
]
```

#### `apps/notifications/context_processors.py`

*9 lignes*

```python
from . import services


def notifications(request):
    """Ajoute ``nombre_non_lues`` (cloche de l'en-tête) au contexte des templates."""
    utilisateur = request.user
    if not utilisateur.is_authenticated:
        return {}
    return {"nombre_non_lues": services.nombre_non_lues(utilisateur)}
```

#### `apps/notifications/templates/notifications/liste.html`

*70 lignes*

```django
{% extends "base.html" %}
{% load ui %}
{% block titre %}Notifications{% endblock %}
{% block entete %}Notifications{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-4xl">
  <div class="flex flex-wrap items-start justify-between gap-3">
    <div>
      <h1 class="text-2xl font-bold text-slate-900">Notifications</h1>
      <p class="mt-1 text-sm text-slate-600">
        {% if nombre_non_lues %}{{ nombre_non_lues }} non lue{{ nombre_non_lues|pluralize }}{% else %}Tout est lu{% endif %}
      </p>
    </div>
    <div class="flex flex-wrap items-center gap-3">
      <a href="{% if non_lues_seulement %}{% url 'notifications:liste' %}{% else %}?non_lues=1{% endif %}"
         class="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
        {% if non_lues_seulement %}Afficher toutes{% else %}Non lues seulement{% endif %}
      </a>
      {% if nombre_non_lues %}
        <form method="post" action="{% url 'notifications:tout_lire' %}">
          {% csrf_token %}
          <button type="submit" class="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Tout marquer comme lu</button>
        </form>
      {% endif %}
    </div>
  </div>

  {% if notifications %}
    <ul class="mt-5 divide-y divide-slate-100 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      {% for n in notifications %}
        <li class="flex flex-wrap items-start gap-x-4 gap-y-3 p-4 {% if not n.est_lue %}bg-marque-50/40{% endif %}">
          <span class="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full {% if n.est_lue %}bg-transparent{% else %}bg-marque-600{% endif %}" aria-hidden="true"></span>
          <div class="min-w-0 flex-1 basis-56">
            <p class="flex flex-wrap items-center gap-2">
              {% badge n.niveau n.get_niveau_display %}
              <span class="text-xs font-semibold uppercase tracking-wide text-slate-600">{{ n.get_categorie_display }}</span>
              <span class="text-xs text-slate-600">{{ n.created_at|date:"d/m/Y H:i" }}</span>
              {% if not n.est_lue %}<span class="sr-only">Non lue</span>{% endif %}
            </p>
            <p class="mt-1 font-semibold text-slate-900">{{ n.titre }}</p>
            {% if n.message %}<p class="mt-0.5 text-sm text-slate-700">{{ n.message }}</p>{% endif %}
          </div>
          <form method="post" action="{% url 'notifications:lire' n.pk %}" class="w-full shrink-0 pl-6 sm:w-auto sm:pl-0">
            {% csrf_token %}
            {% if n.action and n.url %}
              <button type="submit"
                      class="w-full rounded-lg bg-emerald-700 px-3 py-1.5 sm:w-auto text-sm font-semibold text-white shadow-sm hover:bg-emerald-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 focus-visible:ring-offset-2">
                {{ n.action }}
              </button>
            {% else %}
              <button type="submit"
                      class="w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 sm:w-auto text-sm font-medium text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
                {% if n.url %}Ouvrir{% elif n.est_lue %}Lue{% else %}Marquer comme lue{% endif %}
              </button>
            {% endif %}
          </form>
        </li>
      {% endfor %}
    </ul>
    {% include "components/_pagination.html" %}
  {% else %}
    <div class="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
      <span class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-600"><i class="fa-regular fa-bell" aria-hidden="true"></i></span>
      <p class="mt-3 font-semibold text-slate-900">{% if non_lues_seulement %}Aucune notification non lue{% else %}Aucune notification{% endif %}</p>
      <p class="mt-1 text-sm text-slate-600">Les alertes (congés, stock, carburant, échéances) apparaîtront ici.</p>
    </div>
  {% endif %}
</div>
{% endblock %}
```

#### `apps/audit/views.py`

*97 lignes* — Écran du journal d'audit : liste filtrable, export CSV, rapport imprimable — ADMIN et DIRECTION

```python
"""Écran du journal d'audit : liste filtrable, export CSV, rapport imprimable — ADMIN et DIRECTION
(cahier-des-charges.md:56-82). Aucune écriture ici : le journal ne se remplit que via
``services.log_action`` (signaux, ``registry.audit_model``), jamais depuis cet écran.
"""

import csv

from django.http import HttpResponse
from django.views.generic import ListView

from apps.accounts.mixins import RoleRequiredMixin
from apps.core.views import ImpressionListeMixin, PaginationTolerante

from . import permissions, services
from .forms import FiltreJournalForm


class JournalListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "audit/journal_list.html"
    context_object_name = "lignes"
    paginate_by = 30

    def get_filtre(self):
        if not hasattr(self, "_filtre"):
            self._filtre = FiltreJournalForm(self.request.GET, modules=services.modules_utilises())
        return self._filtre

    def get_queryset(self):
        return services.rechercher(**self.get_filtre().criteres())

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            filtre=self.get_filtre(),
            filtres_actifs=any(self.get_filtre().criteres().values()),
        )
        return contexte


COLONNES_EXPORT = (
    ("Date/heure", lambda e: e.date_heure.strftime("%d/%m/%Y %H:%M:%S")),
    ("Utilisateur", lambda e: e.utilisateur_nom or "—"),
    ("Rôle", lambda e: e.role or "—"),
    ("Action", "get_action_display"), ("Module", "module"), ("Entité", "entite"),
    ("ID entité", lambda e: e.entite_id if e.entite_id is not None else "—"),
    ("Statut", "get_statut_display"), ("Adresse IP", lambda e: e.adresse_ip or "—"),
)


class JournalImprimerView(ImpressionListeMixin, JournalListView):
    """Rapport imprimable du journal (mêmes filtres que la liste)."""

    titre_impression = "Journal d'audit"
    colonnes = COLONNES_EXPORT

    def get_sous_titre_impression(self):
        criteres = self.get_filtre().criteres()
        morceaux = []
        if criteres.get("module"):
            morceaux.append(f"module : {criteres['module']}")
        if criteres.get("action"):
            morceaux.append(f"action : {dict(services.ActionChoices.choices)[criteres['action']]}")
        if criteres.get("statut"):
            morceaux.append(f"statut : {dict(services.StatutChoices.choices)[criteres['statut']]}")
        if criteres.get("date_debut"):
            morceaux.append(f"du {criteres['date_debut'].strftime('%d/%m/%Y')}")
        if criteres.get("date_fin"):
            morceaux.append(f"au {criteres['date_fin'].strftime('%d/%m/%Y')}")
        if criteres.get("recherche"):
            morceaux.append(f"recherche : « {criteres['recherche']} »")
        return " · ".join(morceaux)


class JournalExporterCsvView(RoleRequiredMixin, ListView):
    """Export CSV du journal filtré (cahier-des-charges.md:82 « Export CSV/PDF pour audits externes »).

    Le PDF s'obtient par :class:`JournalImprimerView` (Ctrl+P / Enregistrer au format PDF).
    """

    roles = permissions.CONSULTATION

    def get_filtre(self):
        return FiltreJournalForm(self.request.GET, modules=services.modules_utilises())

    def get_queryset(self):
        return services.rechercher(**self.get_filtre().criteres())

    def get(self, request, *args, **kwargs):
        reponse = HttpResponse(content_type="text/csv; charset=utf-8")
        reponse["Content-Disposition"] = 'attachment; filename="journal_audit.csv"'
        reponse.write("﻿")  # BOM : Excel ouvre l'UTF-8 sans le déformer
        redacteur = csv.writer(reponse, delimiter=";")
        redacteur.writerow([libelle for libelle, _ in COLONNES_EXPORT])
        for entree in self.get_queryset():
            redacteur.writerow([ImpressionListeMixin._valeur(entree, cle) for _, cle in COLONNES_EXPORT])
        return reponse
```

(Ce fichier ne contient qu'un commentaire ; l'app `audit` n'a pas d'écran dédié.)

La **page d'accueil provisoire** : le vrai tableau de bord arrivera au chapitre 26 et renvoie vers tous les
écrans ; en attendant, une page simple permet de tester la connexion.

#### `templates/accueil_provisoire.html`

*Fichier provisoire, propre au tutoriel : il sera supprimé au chapitre « La page d'accueil : le tableau de bord ».*

```django
{% extends "base.html" %}
{% block titre %}Accueil{% endblock %}
{% block entete %}Accueil{% endblock %}

{% block contenu %}
<h1 class="text-2xl font-bold text-slate-900">Bienvenue</h1>
<p class="mt-2 text-sm text-slate-700">
  Page d'accueil provisoire : le tableau de bord la remplacera au chapitre « La page d'accueil : le tableau de bord ».
</p>
{% endblock %}
```

## Étape 6 — Les tests

#### Fichiers vides à créer

Ces fichiers n'ont aucun contenu ; ils servent à faire de leur dossier un *paquet Python* (sans eux, `import apps.xxx` échouerait). Créez d'abord les dossiers, puis les fichiers :

```bash
mkdir -p apps\core\templatetags
touch apps/core/templatetags/__init__.py
```

> Sous PowerShell, `mkdir -p` s'écrit `New-Item -ItemType Directory -Force <dossier>` et `touch fichier` s'écrit `New-Item -ItemType File -Force fichier`. Vous pouvez aussi créer ces fichiers avec votre éditeur.

#### `templates/components/_graphique_barres.html`

*17 lignes* — Barres horizontales (apps.core.graphiques.barres_horizontales). Valeur au bout de la barre : rien ne dépend de la souris.

```django
{# Barres horizontales (apps.core.graphiques.barres_horizontales). Valeur au bout de la barre : rien ne dépend de la souris. #}
{% if g.vide %}
  <p class="text-sm text-slate-600">{{ vide }}</p>
{% else %}
  <ul class="viz-barres">
    {% for l in g.lignes %}
      <li class="viz-barre-ligne">
        <span class="viz-barre-libelle">
          {% if l.url %}<a href="{{ l.url }}" class="font-medium text-marque-700 underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">{{ l.libelle }}</a>{% else %}{{ l.libelle }}{% endif %}
          {% if l.detail %}<span class="text-xs text-slate-600">· {{ l.detail }}</span>{% endif %}
        </span>
        <span class="viz-piste" aria-hidden="true"><span class="viz-barre viz-s1" style="width: {{ l.largeur }}%"></span></span>
        <span class="viz-barre-valeur">{{ l.valeur_texte }}{% if g.unite %} <span class="text-xs font-normal text-slate-600">{{ g.unite }}</span>{% endif %}</span>
      </li>
    {% endfor %}
  </ul>
{% endif %}
```

#### `templates/components/_graphique_colonnes.html`

*50 lignes*

```django
{% load l10n %}{# Colonnes groupées (apps.core.graphiques.colonnes_groupees). Infobulle au survol ET au focus clavier ; équivalent en tableau dessous. #}
{% if g.vide %}
  <p class="text-sm text-slate-600">{{ vide }}</p>
{% else %}
  <ul class="viz-legende" aria-label="Légende">
    {% for s in g.legende %}<li><span class="viz-cle viz-s{{ s.rang }}" aria-hidden="true"></span>{{ s.nom }}</li>{% endfor %}
  </ul>
  <div class="viz-colonnes{% if g.grappes|length > 6 %} viz-dense{% endif %}">
    <div class="viz-axe-y" aria-hidden="true">
      {% for t in g.graduations %}<span style="bottom: {{ t.position }}%">{{ t.etiquette }}</span>{% endfor %}
    </div>
    <div class="viz-zone">
      <div class="viz-trace">
        {% for t in g.graduations %}<span class="viz-grille" style="bottom: {{ t.position }}%" aria-hidden="true"></span>{% endfor %}
        <div class="viz-grappes">
          {% for grappe in g.grappes %}
            <div class="viz-grappe" tabindex="0" aria-label="{{ grappe.libelle }} : {% for c in grappe.colonnes %}{{ c.serie }} {{ c.valeur_texte }} {{ g.unite }}{% if not forloop.last %}, {% endif %}{% endfor %}">
              <div class="viz-colonnes-serie">
                {% for c in grappe.colonnes %}<span class="viz-colonne viz-s{{ c.rang }}" style="height: {{ c.hauteur|unlocalize }}%"></span>{% endfor %}
              </div>
              <div class="viz-info viz-info-{{ grappe.bord }}" role="tooltip">
                <strong class="viz-info-titre">{{ grappe.libelle }}</strong>
                {% for c in grappe.colonnes %}
                  <span class="viz-info-ligne"><span class="viz-trait viz-s{{ c.rang }}" aria-hidden="true"></span><span class="viz-info-valeur">{{ c.valeur_texte }}</span><span class="viz-info-nom">{{ c.serie }}</span></span>
                {% endfor %}
              </div>
            </div>
          {% endfor %}
        </div>
      </div>
      <div class="viz-axe-x" aria-hidden="true">
        {% for grappe in g.grappes %}<span>{{ grappe.libelle_court }}{% if grappe.sous_libelle %}<small>{{ grappe.sous_libelle }}</small>{% endif %}</span>{% endfor %}
      </div>
    </div>
  </div>
  <details class="mt-3 text-sm">
    <summary class="cursor-pointer text-marque-700 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">Voir en tableau</summary>
    <div class="mt-2 overflow-x-auto">
      <table class="w-full text-left text-sm" id="{{ id }}-tableau">
        <caption class="sr-only">Valeurs en {{ g.unite }}</caption>
        <thead><tr class="border-b border-slate-200 text-slate-600"><th scope="col" class="py-1 pr-3 font-medium">Mois</th>{% for e in g.tableau.entetes %}<th scope="col" class="py-1 pl-3 text-right font-medium">{{ e }}</th>{% endfor %}</tr></thead>
        <tbody>
          {% for l in g.tableau.lignes %}
            <tr class="border-b border-slate-100"><th scope="row" class="py-1 pr-3 font-medium text-slate-800">{{ l.libelle }}</th>{% for v in l.valeurs %}<td class="py-1 pl-3 text-right tabular-nums text-slate-800">{{ v }}</td>{% endfor %}</tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </details>
{% endif %}
```

#### `templates/components/_suivi_direct.html`

*19 lignes* — Voyant du suivi en direct + annonce pour lecteurs d'écran + bandeau « actualiser » (static/js/suivi-missions.js).

```django
{# Voyant du suivi en direct + annonce pour lecteurs d'écran + bandeau « actualiser » (static/js/suivi-missions.js). #}
<div class="flex flex-wrap items-center gap-3">
  <p id="suivi-voyant" class="text-xs">
    <span data-etat="connecte" class="hidden items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 font-medium text-emerald-800 ring-1 ring-emerald-200">
      <span class="h-2 w-2 rounded-full bg-emerald-600" aria-hidden="true"></span>En direct
    </span>
    <span data-etat="reconnexion" class="hidden items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-1 font-medium text-amber-900 ring-1 ring-amber-300">
      <span class="h-2 w-2 rounded-full bg-amber-500" aria-hidden="true"></span>Reconnexion…
    </span>
    <span data-etat="hors_ligne" class="hidden items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-700 ring-1 ring-slate-300">
      <span class="h-2 w-2 rounded-full bg-slate-400" aria-hidden="true"></span>Suivi en direct indisponible : actualisez la page pour voir les changements
    </span>
  </p>
  <div id="suivi-bandeau" class="hidden items-center gap-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs text-amber-900" role="status">
    Cette page vient de changer.
    <button type="button" id="suivi-actualiser" class="font-semibold underline underline-offset-2 hover:text-amber-950 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-700">Actualiser</button>
  </div>
  <div id="suivi-annonce" class="sr-only" aria-live="polite"></div>
</div>
```

#### `templates/rapports/_entete_impression.html`

*17 lignes*

```django
{% load static %}{# En-tête commune des rapports imprimables : logo, entreprise, titre, sous-titre, bouton Imprimer. #}
<div class="actions"><button type="button" data-imprimer><i class="fa-solid fa-print" aria-hidden="true"></i> Imprimer ou enregistrer en PDF</button></div>

<div class="rapport-entete">
  <div class="rapport-marque">
    <img src="{% static 'img/logo-emblem.jpg' %}" alt="" class="rapport-logo">
    <div>
      <strong class="rapport-nom">{{ entreprise.nom }}</strong><br>
      {% if entreprise.adresse %}<span class="petit">{{ entreprise.adresse|linebreaksbr }}</span><br>{% endif %}
      {% if entreprise.ncc %}<span class="petit">NCC {{ entreprise.ncc }}</span>{% endif %}
    </div>
  </div>
  <div style="text-align:right">
    <h1>{{ titre }}</h1>
    {% if sous_titre %}<div class="petit">{{ sous_titre }}</div>{% endif %}
  </div>
</div>
```

#### `templates/rapports/_pied_impression.html`

*2 lignes* — Pied commun des rapports imprimables : qui l'a généré, quand.

```django
{# Pied commun des rapports imprimables : qui l'a généré, quand. #}
<p class="rapport-pied">Généré le {{ genere_le|date:"d/m/Y à H:i" }} par {{ genere_par }} — DEN Source ERP</p>
```

#### `templates/rapports/_style_impression.html`

*28 lignes*

```django
<style>
  :root { --marque: #8b0319; --accent: #f28a14; } /* couleurs du logo DEN Source Group (frontend/tailwind.config.js) */
  body { font-family: Arial, Helvetica, sans-serif; color: #111; margin: 2rem auto; max-width: 960px; padding: 0 1rem; font-size: 13px; }
  h1 { font-size: 1.5rem; margin: 0; color: var(--marque); }
  h2 { font-size: 1.05rem; margin: 1.75rem 0 .5rem; padding-top: .75rem; border-top: 2px solid var(--accent); color: var(--marque); }
  table { width: 100%; border-collapse: collapse; margin-top: .75rem; }
  th, td { padding: .4rem .6rem; border-bottom: 1px solid #ccc; text-align: left; vertical-align: top; }
  th { background: #fdf2f3; color: var(--marque); font-size: .75rem; text-transform: uppercase; letter-spacing: .03em; }
  td.droite, th.droite { text-align: right; white-space: nowrap; }
  .rapport-entete { display: flex; justify-content: space-between; gap: 2rem; align-items: flex-start; padding-bottom: .75rem; border-bottom: 3px solid var(--accent); }
  .rapport-marque { display: flex; align-items: center; gap: .85rem; }
  .rapport-logo { height: 48px; width: 48px; object-fit: contain; flex-shrink: 0; }
  .rapport-nom { color: var(--marque); font-size: 1.15rem; }
  .petit { color: #555; font-size: .85rem; }
  .cartouche { display: flex; flex-wrap: wrap; gap: 1.5rem; margin-top: 1rem; }
  .cartouche > div { min-width: 9rem; }
  .cartouche dt { color: #555; font-size: .78rem; }
  .cartouche dd { margin: 0; font-size: 1.15rem; font-weight: bold; color: var(--marque); }
  .actions { margin-bottom: 1rem; }
  .actions button { display: inline-flex; align-items: center; gap: .5rem; border: 1px solid var(--marque); background: var(--marque); color: #fff; border-radius: .5rem; padding: .5rem 1rem; font: inherit; font-weight: 600; cursor: pointer; }
  .rapport-pied { margin-top: 2rem; padding-top: .5rem; border-top: 1px solid #ddd; color: #777; font-size: .78rem; }
  @media print {
    .actions { display: none; }
    body { margin: 0; }
    h2 { break-after: avoid; }
    tr { break-inside: avoid; }
  }
</style>
```

#### `templates/rapports/liste_impression.html`

*32 lignes*

```django
{% load static %}<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ titre }} · {{ entreprise.nom }}</title>
  {% include "rapports/_style_impression.html" %}
</head>
<body>
  {% include "rapports/_entete_impression.html" %}

  <p class="petit">
    {{ nombre }} ligne{{ nombre|pluralize }}{% if tronque %} — limité aux {{ nombre }} premières ; affinez la recherche pour voir le reste{% endif %}
  </p>

  {% if lignes %}
    <table>
      <thead><tr>{% for entete in entetes %}<th>{{ entete }}</th>{% endfor %}</tr></thead>
      <tbody>
        {% for ligne in lignes %}
          <tr>{% for valeur in ligne %}<td>{{ valeur }}</td>{% endfor %}</tr>
        {% endfor %}
      </tbody>
    </table>
  {% else %}
    <p>Aucune ligne pour ces critères.</p>
  {% endif %}

  {% include "rapports/_pied_impression.html" %}
  <script src="{% static 'js/app.js' %}" defer></script>
</body>
</html>
```

#### `templates/registration/password_reset_complete.html`

*21 lignes*

```django
{% extends "base.html" %}
{% load static %}
{% block titre %}Mot de passe changé{% endblock %}

{% block layout %}
<div class="flex min-h-full items-center justify-center bg-gradient-to-b from-marque-50 via-white to-white px-4 py-12">
  <div class="w-full max-w-md">
    <div class="mb-8 text-center">
      <span class="mx-auto inline-block rounded-2xl bg-white p-3 shadow-md ring-1 ring-marque-100"><img src="{% static 'img/logo-emblem.jpg' %}" alt="DEN Source Group" class="h-24 w-auto"></span>
    </div>
    <div class="rounded-2xl border border-slate-200 border-t-4 border-t-accent-500 bg-white p-6 text-center shadow-sm">
      <h1 class="text-xl font-bold text-slate-900">Mot de passe changé</h1>
      <p class="mt-3 text-sm text-slate-600">Vous pouvez vous connecter avec votre nouveau mot de passe.</p>
      <a href="{% url 'accounts:login' %}"
         class="mt-6 inline-block rounded-lg bg-marque-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-marque-700">
        Se connecter
      </a>
    </div>
  </div>
</div>
{% endblock %}
```

#### `templates/registration/password_reset_confirm.html`

*52 lignes*

```django
{% extends "base.html" %}
{% load static %}
{% block titre %}Nouveau mot de passe{% endblock %}

{% block layout %}
<div class="flex min-h-full items-center justify-center bg-gradient-to-b from-marque-50 via-white to-white px-4 py-12">
  <div class="w-full max-w-md">
    <div class="mb-8 text-center">
      <span class="mx-auto inline-block rounded-2xl bg-white p-3 shadow-md ring-1 ring-marque-100"><img src="{% static 'img/logo-emblem.jpg' %}" alt="DEN Source Group" class="h-24 w-auto"></span>
      <h1 class="mt-3 text-2xl font-bold text-slate-900">Nouveau mot de passe</h1>
    </div>

    {% if validlink %}
      <form method="post" class="space-y-5 rounded-2xl border border-slate-200 border-t-4 border-t-accent-500 bg-white p-6 shadow-sm">
        {% csrf_token %}
        {% if form.non_field_errors %}
          <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">
            {% for erreur in form.non_field_errors %}<p>{{ erreur }}</p>{% endfor %}
          </div>
        {% endif %}

        <div>
          <label for="{{ form.new_password1.id_for_label }}" class="block text-sm font-medium text-slate-800">Nouveau mot de passe</label>
          <input type="password" name="new_password1" id="{{ form.new_password1.id_for_label }}" required autofocus
                 autocomplete="new-password"
                 class="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30">
          <p class="mt-1 text-xs text-slate-500">Au moins 10 caractères, ni trop simple ni proche de votre identifiant.</p>
          {% for erreur in form.new_password1.errors %}<p class="mt-1 text-sm text-red-700">{{ erreur }}</p>{% endfor %}
        </div>
        <div>
          <label for="{{ form.new_password2.id_for_label }}" class="block text-sm font-medium text-slate-800">Confirmer le mot de passe</label>
          <input type="password" name="new_password2" id="{{ form.new_password2.id_for_label }}" required
                 autocomplete="new-password"
                 class="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30">
          {% for erreur in form.new_password2.errors %}<p class="mt-1 text-sm text-red-700">{{ erreur }}</p>{% endfor %}
        </div>
        <button type="submit"
                class="w-full rounded-lg bg-marque-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
          Enregistrer le nouveau mot de passe
        </button>
      </form>
    {% else %}
      <div class="rounded-2xl border border-slate-200 border-t-4 border-t-red-500 bg-white p-6 text-center shadow-sm">
        <p class="text-sm text-slate-700">
          Ce lien n'est plus valable : il a déjà servi, ou il a expiré. Demandez-en un nouveau.
        </p>
        <a href="{% url 'accounts:password_reset' %}" class="mt-6 inline-block font-medium text-marque-700 hover:underline">Redemander un lien</a>
      </div>
    {% endif %}
  </div>
</div>
{% endblock %}
```

#### `templates/registration/password_reset_done.html`

*24 lignes*

```django
{% extends "base.html" %}
{% load static %}
{% block titre %}Mot de passe oublié{% endblock %}

{% block layout %}
<div class="flex min-h-full items-center justify-center bg-gradient-to-b from-marque-50 via-white to-white px-4 py-12">
  <div class="w-full max-w-md">
    <div class="mb-8 text-center">
      <span class="mx-auto inline-block rounded-2xl bg-white p-3 shadow-md ring-1 ring-marque-100"><img src="{% static 'img/logo-emblem.jpg' %}" alt="DEN Source Group" class="h-24 w-auto"></span>
    </div>
    <div class="rounded-2xl border border-slate-200 border-t-4 border-t-accent-500 bg-white p-6 text-center shadow-sm">
      <h1 class="text-xl font-bold text-slate-900">E-mail envoyé</h1>
      <p class="mt-3 text-sm text-slate-600">
        Si cette adresse correspond à un compte, un e-mail vient d'être envoyé avec un lien pour
        choisir un nouveau mot de passe. Il reste valable quelques jours.
      </p>
      <p class="mt-3 text-sm text-slate-600">
        Rien reçu ? Vérifiez le dossier indésirable, ou réessayez avec la bonne adresse.
      </p>
      <a href="{% url 'accounts:login' %}" class="mt-6 inline-block font-medium text-marque-700 hover:underline">Retour à la connexion</a>
    </div>
  </div>
</div>
{% endblock %}
```

#### `templates/registration/password_reset_email.txt`

*12 lignes*

```text
Bonjour {{ user.get_full_name|default:user.username }},

Une demande de réinitialisation de mot de passe a été faite pour votre compte sur l'ERP DEN Source Group
({{ domain }}). Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail : votre mot de passe
ne change pas tant que vous n'ouvrez pas le lien ci-dessous.

Pour choisir un nouveau mot de passe :
{{ protocol }}://{{ domain }}{% url 'accounts:password_reset_confirm' uidb64=uid token=token %}

Ce lien n'est valable qu'une fois, pendant quelques jours.

— ERP DEN Source Group
```

#### `templates/registration/password_reset_form.html`

*42 lignes*

```django
{% extends "base.html" %}
{% load static %}
{% block titre %}Mot de passe oublié{% endblock %}

{% block layout %}
<div class="flex min-h-full items-center justify-center bg-gradient-to-b from-marque-50 via-white to-white px-4 py-12">
  <div class="w-full max-w-md">
    <div class="mb-8 text-center">
      <span class="mx-auto inline-block rounded-2xl bg-white p-3 shadow-md ring-1 ring-marque-100"><img src="{% static 'img/logo-emblem.jpg' %}" alt="DEN Source Group" class="h-24 w-auto"></span>
      <h1 class="mt-3 text-2xl font-bold text-slate-900">Mot de passe oublié</h1>
      <p class="mt-2 text-sm text-slate-600">
        Indiquez l'adresse e-mail de votre compte : si elle y est rattachée, un lien pour choisir un
        nouveau mot de passe vous sera envoyé.
      </p>
    </div>

    <form method="post" class="space-y-5 rounded-2xl border border-slate-200 border-t-4 border-t-accent-500 bg-white p-6 shadow-sm">
      {% csrf_token %}
      {% if form.non_field_errors %}
        <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">
          {% for erreur in form.non_field_errors %}<p>{{ erreur }}</p>{% endfor %}
        </div>
      {% endif %}

      <div>
        <label for="{{ form.email.id_for_label }}" class="block text-sm font-medium text-slate-800">Adresse e-mail</label>
        <input type="email" name="email" id="{{ form.email.id_for_label }}" required autofocus
               autocomplete="email" value="{{ form.email.value|default:'' }}"
               class="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30">
        {% for erreur in form.email.errors %}<p class="mt-1 text-sm text-red-700">{{ erreur }}</p>{% endfor %}
      </div>
      <button type="submit"
              class="w-full rounded-lg bg-marque-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
        Envoyer le lien
      </button>
      <p class="text-center text-sm text-slate-600">
        <a href="{% url 'accounts:login' %}" class="font-medium text-marque-700 hover:underline">Retour à la connexion</a>
      </p>
    </form>
  </div>
</div>
{% endblock %}
```

#### `templates/registration/password_reset_subject.txt`

*1 ligne*

```text
Réinitialisation de votre mot de passe — ERP DEN Source Group
```

#### `apps/audit/forms.py`

*42 lignes* — Filtres du journal d'audit.

```python
"""Filtres du journal d'audit."""

from django import forms

from apps.core.forms import StyleTailwindMixin

from .models import ActionChoices, StatutChoices


class FiltreJournalForm(StyleTailwindMixin, forms.Form):
    """Filtres de la liste ; un paramètre invalide est ignoré."""

    q = forms.CharField(label="Rechercher", required=False, help_text="Utilisateur, entité, adresse IP…")
    module = forms.ChoiceField(label="Module", choices=[("", "Tous")], required=False)
    action = forms.ChoiceField(label="Action", choices=[("", "Toutes")] + ActionChoices.choices, required=False)
    statut = forms.ChoiceField(label="Statut", choices=[("", "Tous")] + StatutChoices.choices, required=False)
    date_debut = forms.DateField(label="Du", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    date_fin = forms.DateField(label="Au", required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, modules=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["module"].choices = [("", "Tous")] + [(m, m) for m in modules]

    def clean(self):
        donnees = super().clean()
        debut, fin = donnees.get("date_debut"), donnees.get("date_fin")
        if debut and fin and debut > fin:
            self.add_error("date_fin", "La date de fin précède la date de début : période ignorée.")
            donnees.pop("date_debut", None)
        return donnees

    def criteres(self) -> dict:
        self.is_valid()
        donnees = getattr(self, "cleaned_data", {})
        return {
            "recherche": donnees.get("q") or "",
            "module": donnees.get("module") or "",
            "action": donnees.get("action") or "",
            "statut": donnees.get("statut") or "",
            "date_debut": donnees.get("date_debut"),
            "date_fin": donnees.get("date_fin"),
        }
```

#### `apps/audit/urls.py`

*11 lignes*

```python
from django.urls import path

from . import views

app_name = "audit"

urlpatterns = [
    path("", views.JournalListView.as_view(), name="journal"),
    path("imprimer/", views.JournalImprimerView.as_view(), name="imprimer"),
    path("export.csv", views.JournalExporterCsvView.as_view(), name="export_csv"),
]
```

#### `apps/core/templatetags/graphiques.py`

*17 lignes* — Balises des graphiques du tableau de bord (données préparées par ``apps.core.graphiques``).

```python
"""Balises des graphiques du tableau de bord (données préparées par ``apps.core.graphiques``)."""

from django import template

register = template.Library()


@register.inclusion_tag("components/_graphique_barres.html")
def graphique_barres(donnees, vide="Aucune donnée pour le moment."):
    """Barres horizontales : ``{% graphique_barres graphique %}``."""
    return {"g": donnees, "vide": vide}


@register.inclusion_tag("components/_graphique_colonnes.html")
def graphique_colonnes(donnees, identifiant, vide="Aucune donnée sur la période."):
    """Colonnes groupées : ``{% graphique_colonnes graphique "id-unique" %}``."""
    return {"g": donnees, "id": identifiant, "vide": vide}
```

#### `apps/audit/templates/audit/journal_list.html`

*80 lignes*

```django
{% extends "base.html" %}
{% load ui %}
{% block titre %}Journal d'audit{% endblock %}
{% block entete %}Journal d'audit{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-7xl">
  <div class="flex flex-wrap items-start justify-between gap-3">
    <div>
      <h1 class="text-2xl font-bold text-slate-900">Journal d'audit</h1>
      <p class="mt-1 text-sm text-slate-600">
        {{ paginator.count|default:0 }} entrée{{ paginator.count|pluralize }} · immuable : créations, modifications,
        suppressions, connexions/déconnexions et validations, conservées au moins 5 ans.
      </p>
    </div>
    <div class="flex flex-wrap items-center gap-2">
      <a href="{% url 'audit:export_csv' %}?{{ request.GET.urlencode }}"
         class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
        <i class="fa-solid fa-file-csv" aria-hidden="true"></i> Exporter en CSV
      </a>
      <a href="{% url 'audit:imprimer' %}?{{ request.GET.urlencode }}" target="_blank" rel="noopener"
         class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
        <i class="fa-solid fa-print" aria-hidden="true"></i> Imprimer
      </a>
    </div>
  </div>

  <form method="get" class="mt-5 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
    <div class="min-w-[14rem] flex-1">{% include "components/_champ.html" with champ=filtre.q %}</div>
    <div class="min-w-[10rem]">{% include "components/_champ.html" with champ=filtre.module %}</div>
    <div class="min-w-[10rem]">{% include "components/_champ.html" with champ=filtre.action %}</div>
    <div class="min-w-[10rem]">{% include "components/_champ.html" with champ=filtre.statut %}</div>
    {% include "components/_champ.html" with champ=filtre.date_debut %}
    {% include "components/_champ.html" with champ=filtre.date_fin %}
    <button type="submit" class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Filtrer</button>
    {% if filtres_actifs %}
      <a href="{% url 'audit:journal' %}" class="px-2 py-2 text-sm font-medium text-slate-700 underline hover:text-slate-900">Réinitialiser</a>
    {% endif %}
  </form>

  {% if lignes %}
    <div class="mt-5 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <caption class="sr-only">Journal d'audit</caption>
        <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr>
            <th scope="col" class="px-4 py-3">Date/heure</th>
            <th scope="col" class="px-4 py-3">Utilisateur</th>
            <th scope="col" class="px-4 py-3">Action</th>
            <th scope="col" class="px-4 py-3">Module</th>
            <th scope="col" class="px-4 py-3">Entité</th>
            <th scope="col" class="hidden px-4 py-3 xl:table-cell">Adresse IP</th>
            <th scope="col" class="px-4 py-3">Statut</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          {% for e in lignes %}
            <tr class="hover:bg-slate-50">
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ e.date_heure|date:"d/m/Y H:i:s" }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-900">{{ e.utilisateur_nom|default:"—" }}<span class="block text-xs text-slate-600">{{ e.role|default:"—" }}</span></td>
              <td class="whitespace-nowrap px-4 py-3">{% badge e.action e.get_action_display %}</td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ e.module }}</td>
              <td class="px-4 py-3 text-slate-700">{{ e.entite }}{% if e.entite_id %} #{{ e.entite_id }}{% endif %}</td>
              <td class="hidden whitespace-nowrap px-4 py-3 text-slate-700 xl:table-cell">{{ e.adresse_ip|default:"—" }}</td>
              <td class="whitespace-nowrap px-4 py-3">{% if e.statut == "FAILED" %}{% badge "URGENT" e.get_statut_display %}{% else %}{{ e.get_statut_display }}{% endif %}</td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% include "components/_pagination.html" %}
  {% else %}
    <div class="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
      <span class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-600"><i class="fa-solid fa-clipboard-list" aria-hidden="true"></i></span>
      <p class="mt-3 font-semibold text-slate-900">Aucune entrée</p>
      <p class="mt-1 text-sm text-slate-600">{% if filtres_actifs %}Aucun résultat pour ces critères.{% else %}Les actions du journal apparaîtront ici.{% endif %}</p>
    </div>
  {% endif %}
</div>
{% endblock %}
```

#### `apps/accounts/tests/test_password_reset.py`

*170 lignes* — Mot de passe oublié : les 4 étapes, sans jamais révéler si une adresse a un compte.

```python
"""Mot de passe oublié : les 4 étapes, sans jamais révéler si une adresse a un compte."""

import re

import pytest
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.models import Role, User
from apps.audit.models import ActionChoices, AuditLog

from .factories import UserFactory

pytestmark = pytest.mark.django_db

NOUVEAU_MOT_DE_PASSE = "Un-Nouveau-Mot-2-Passe"


def _lien_confirmation(compte):
    """Construit l'URL de confirmation directement (sans dépendre du format de l'e-mail)."""
    uid = urlsafe_base64_encode(force_bytes(compte.pk))
    token = default_token_generator.make_token(compte)
    return reverse("accounts:password_reset_confirm", kwargs={"uidb64": uid, "token": token})


def _page_confirmation(client, compte):
    """Ouvre le lien (GET) : Django range le jeton en session et redirige vers l'URL réellement
    soumise par le formulaire (le jeton n'apparaît plus dans l'adresse). Un navigateur fait la
    même chose avant de pouvoir poster le nouveau mot de passe."""
    reponse = client.get(_lien_confirmation(compte), follow=True)
    return reponse.redirect_chain[-1][0]


# --- demande ---


def test_la_page_de_demande_est_ouverte_a_tous(client):
    assert client.get(reverse("accounts:password_reset")).status_code == 200


def test_une_adresse_existante_recoit_un_e_mail(client):
    UserFactory(role=Role.RH, email="marie@densourcegroup.ci")

    reponse = client.post(
        reverse("accounts:password_reset"), {"email": "marie@densourcegroup.ci"}, follow=True
    )

    assert reponse.redirect_chain[-1][0] == reverse("accounts:password_reset_done")
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["marie@densourcegroup.ci"]
    assert "mot de passe" in mail.outbox[0].subject.lower()


def test_une_adresse_inconnue_ne_revele_rien(client):
    reponse = client.post(
        reverse("accounts:password_reset"), {"email": "personne@densourcegroup.ci"}, follow=True
    )

    assert reponse.redirect_chain[-1][0] == reverse("accounts:password_reset_done")
    assert len(mail.outbox) == 0


def test_l_e_mail_contient_un_lien_qui_fonctionne(client):
    UserFactory(role=Role.RH, email="marie@densourcegroup.ci", username="marie")

    client.post(reverse("accounts:password_reset"), {"email": "marie@densourcegroup.ci"})

    lien = re.search(r"https?://\S+/mot-de-passe/confirmer/\S+/", mail.outbox[0].body)
    assert lien is not None
    chemin = lien.group(0).split("://", 1)[1].split("/", 1)[1]
    reponse = client.get("/" + chemin, follow=True)
    assert reponse.status_code == 200
    assert reponse.context["validlink"] is True


# --- confirmation ---


def test_un_nouveau_mot_de_passe_valide_fonctionne_ensuite(client):
    compte = UserFactory(role=Role.RH)
    page = _page_confirmation(client, compte)

    reponse = client.post(
        page,
        {"new_password1": NOUVEAU_MOT_DE_PASSE, "new_password2": NOUVEAU_MOT_DE_PASSE},
        follow=True,
    )

    compte.refresh_from_db()
    assert reponse.redirect_chain[-1][0] == reverse("accounts:password_reset_complete")
    assert compte.check_password(NOUVEAU_MOT_DE_PASSE)


def test_deux_mots_de_passe_differents_sont_refuses(client):
    compte = UserFactory(role=Role.RH)
    page = _page_confirmation(client, compte)

    reponse = client.post(
        page, {"new_password1": NOUVEAU_MOT_DE_PASSE, "new_password2": "Autre-Chose-2026"}
    )

    assert reponse.status_code == 200
    compte.refresh_from_db()
    assert not compte.check_password(NOUVEAU_MOT_DE_PASSE)


def test_un_mot_de_passe_trop_court_est_refuse_comme_a_la_creation(client):
    compte = UserFactory(role=Role.RH)
    page = _page_confirmation(client, compte)

    reponse = client.post(page, {"new_password1": "court1", "new_password2": "court1"})

    assert reponse.status_code == 200
    compte.refresh_from_db()
    assert not compte.check_password("court1")


def test_un_lien_deja_utilise_est_refuse(client):
    compte = UserFactory(role=Role.RH)
    lien = _lien_confirmation(compte)
    page = _page_confirmation(client, compte)
    client.post(page, {"new_password1": NOUVEAU_MOT_DE_PASSE, "new_password2": NOUVEAU_MOT_DE_PASSE})

    reponse = client.get(lien, follow=True)

    assert reponse.context["validlink"] is False
    assert "plus valable" in reponse.content.decode()


def test_un_lien_invalide_affiche_l_erreur_sans_planter(client):
    reponse = client.get(
        reverse("accounts:password_reset_confirm", kwargs={"uidb64": "invalide", "token": "invalide"})
    )

    assert reponse.status_code == 200
    assert reponse.context["validlink"] is False


def test_la_reinitialisation_est_tracee_au_journal_d_audit(client):
    compte = UserFactory(role=Role.RH)
    page = _page_confirmation(client, compte)

    client.post(page, {"new_password1": NOUVEAU_MOT_DE_PASSE, "new_password2": NOUVEAU_MOT_DE_PASSE})

    entree = AuditLog.objects.filter(entite="User", entite_id=compte.pk, action=ActionChoices.UPDATE).first()
    assert entree is not None
    assert entree.utilisateur_id == compte.pk


def test_un_administrateur_peut_aussi_reinitialiser_son_mot_de_passe(client):
    """La MFA (ADMIN/DIRECTION) ne bloque pas ce parcours : la personne n'est pas encore connectée."""
    compte = UserFactory(role=Role.ADMIN)
    page = _page_confirmation(client, compte)

    reponse = client.post(
        page,
        {"new_password1": NOUVEAU_MOT_DE_PASSE, "new_password2": NOUVEAU_MOT_DE_PASSE},
        follow=True,
    )

    assert reponse.redirect_chain[-1][0] == reverse("accounts:password_reset_complete")


def test_le_lien_mot_de_passe_oublie_est_sur_la_page_de_connexion(client):
    reponse = client.get(reverse("accounts:login"))

    assert reverse("accounts:password_reset") in reponse.content.decode()
```

#### `apps/audit/tests/test_services.py`

*68 lignes*

```python
import pytest
from django.test import RequestFactory

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.audit import services
from apps.audit.models import ActionChoices, StatutChoices

pytestmark = pytest.mark.django_db


def test_log_action_captures_ip_and_user_agent_from_request():
    user = UserFactory(role=Role.PARCAUTO)
    request = RequestFactory().post(
        "/x", REMOTE_ADDR="10.0.0.5", HTTP_USER_AGENT="pytest-agent"
    )

    entry = services.log_action(
        action=ActionChoices.UPDATE,
        module="FLEET",
        entite="Vehicule",
        entite_id=42,
        utilisateur=user,
        request=request,
    )

    assert entry.adresse_ip == "10.0.0.5"
    assert entry.user_agent == "pytest-agent"
    assert entry.role == Role.PARCAUTO
    assert entry.utilisateur_nom == user.get_full_name()


def test_log_action_ignore_x_forwarded_for_sans_proxy_de_confiance():
    """Sans proxy déclaré, l'en-tête écrit par le client ne doit jamais servir d'adresse."""
    request = RequestFactory().get(
        "/x", REMOTE_ADDR="10.0.0.5", HTTP_X_FORWARDED_FOR="1.2.3.4"
    )

    entry = services.log_action(
        action=ActionChoices.LOGIN, module="AUTH", entite="User", request=request
    )

    assert entry.adresse_ip == "10.0.0.5"


def test_log_action_lit_l_adresse_ajoutee_par_les_proxys_de_confiance(settings):
    settings.TRUSTED_PROXY_COUNT = 2
    request = RequestFactory().get(
        "/x",
        REMOTE_ADDR="10.0.0.5",
        HTTP_X_FORWARDED_FOR="203.0.113.9, 10.0.0.1",
    )

    entry = services.log_action(
        action=ActionChoices.LOGIN, module="AUTH", entite="User", request=request
    )

    assert entry.adresse_ip == "203.0.113.9"


def test_log_login_failed_records_failed_status_and_attempted_username():
    request = RequestFactory().post("/login")

    entry = services.log_login_failed("intrus", request)

    assert entry.statut == StatutChoices.FAILED
    assert entry.nouvelle_valeur == {"username_tente": "intrus"}
    assert entry.utilisateur is None
```

#### `apps/audit/tests/test_signals.py`

*41 lignes*

```python
import pytest
from django.test import Client

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.audit.models import ActionChoices, AuditLog, StatutChoices

pytestmark = pytest.mark.django_db


def test_login_signal_creates_audit_entry():
    user = UserFactory(role=Role.FINANCES)
    client = Client()

    client.force_login(user)

    entry = AuditLog.objects.filter(action=ActionChoices.LOGIN, utilisateur=user).latest(
        "date_heure"
    )
    assert entry.role == Role.FINANCES
    assert entry.statut == StatutChoices.SUCCESS


def test_logout_signal_creates_audit_entry():
    user = UserFactory(role=Role.RH)
    client = Client()
    client.force_login(user)

    client.logout()

    assert AuditLog.objects.filter(action=ActionChoices.LOGOUT, utilisateur=user).exists()


def test_failed_login_creates_audit_entry_with_failed_status():
    client = Client()

    client.post("/connexion/", {"username": "ghost", "password": "wrong"})

    assert AuditLog.objects.filter(
        action=ActionChoices.LOGIN, statut=StatutChoices.FAILED
    ).exists()
```

#### `apps/audit/tests/test_views.py`

*152 lignes* — Écran du journal d'audit : accès, filtres, export CSV, rapport imprimable.

```python
"""Écran du journal d'audit : accès, filtres, export CSV, rapport imprimable."""

from datetime import date, datetime
from datetime import timezone as dt_timezone

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.audit import services
from apps.audit.models import ActionChoices, AuditLog, StatutChoices

pytestmark = pytest.mark.django_db


def _texte(reponse) -> str:
    return reponse.content.decode()


def _entree(**surcharges):
    donnees = dict(
        action=ActionChoices.UPDATE, module="FLEET", entite="Vehicule", entite_id=1,
        utilisateur_nom="Awa Koné", role=Role.PARCAUTO, adresse_ip="10.0.0.1",
    )
    donnees.update(surcharges)
    entree = AuditLog.objects.create(**donnees)
    if "date_heure" in surcharges:
        AuditLog.objects.filter(pk=entree.pk).update(date_heure=surcharges["date_heure"])
        entree.refresh_from_db()
    return entree


# --- accès ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION])
def test_le_journal_est_accessible_a_admin_et_direction(client, role):
    client.force_login(UserFactory(role=role))

    assert client.get(reverse("audit:journal")).status_code == 200


@pytest.mark.parametrize("role", [Role.RH, Role.FINANCES, Role.PARCAUTO, Role.CHARGE_CLIENTELE])
def test_le_journal_est_interdit_aux_autres_roles(client, role):
    client.force_login(UserFactory(role=role))

    assert client.get(reverse("audit:journal")).status_code == 403


# --- filtres ---


def test_la_recherche_porte_sur_l_utilisateur_l_entite_et_l_ip(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    _entree(utilisateur_nom="Fatou Diallo", entite="Facture", adresse_ip="41.1.1.1")
    _entree(utilisateur_nom="Ibrahim Sanogo", entite="Vehicule", adresse_ip="41.2.2.2")

    reponse = client.get(reverse("audit:journal"), {"q": "Fatou"})

    assert "Fatou Diallo" in _texte(reponse) and "Ibrahim Sanogo" not in _texte(reponse)


def test_le_filtre_module_et_action_se_combinent(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    _entree(module="RH", action=ActionChoices.CREATE)
    _entree(module="RH", action=ActionChoices.DELETE)
    _entree(module="FLEET", action=ActionChoices.CREATE)

    reponse = services.rechercher(module="RH", action=ActionChoices.CREATE)

    assert reponse.count() == 1


def test_le_filtre_de_periode_borne_la_date(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    dans_la_periode = _entree(date_heure=datetime(2026, 9, 10, tzinfo=dt_timezone.utc))
    hors_periode = _entree(date_heure=datetime(2026, 8, 1, tzinfo=dt_timezone.utc))

    resultat = services.rechercher(date_debut=date(2026, 9, 1), date_fin=date(2026, 9, 30))

    assert dans_la_periode in resultat and hors_periode not in resultat


def test_le_statut_echec_est_filtrable(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    _entree(statut=StatutChoices.FAILED, module="AUTH")
    _entree(statut=StatutChoices.SUCCESS, module="AUTH")

    assert services.rechercher(statut=StatutChoices.FAILED).count() == 1


def test_le_filtre_module_liste_les_modules_deja_presents():
    _entree(module="RH")
    _entree(module="FLEET")

    assert services.modules_utilises() == ["FLEET", "RH"]


# --- export CSV ---


def test_export_csv_reprend_les_filtres_et_contient_les_colonnes(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    _entree(utilisateur_nom="Awa Koné", module="RH", entite="Personnel", entite_id=7)
    _entree(utilisateur_nom="Fatou Diallo", module="FINANCES")

    reponse = client.get(reverse("audit:export_csv"), {"module": "RH"})

    assert reponse["Content-Type"].startswith("text/csv")
    contenu = reponse.content.decode("utf-8-sig")
    assert "Awa Koné" in contenu and "Fatou Diallo" not in contenu
    assert "Date/heure;Utilisateur;Rôle;Action;Module;Entité;ID entité;Statut;Adresse IP" in contenu


def test_export_csv_interdit_hors_role(client):
    client.force_login(UserFactory(role=Role.RH))

    assert client.get(reverse("audit:export_csv")).status_code == 403


# --- rapport imprimable ---


def test_impression_du_journal(client):
    client.force_login(UserFactory(role=Role.DIRECTION))
    _entree(utilisateur_nom="Awa Koné", module="RH", action=ActionChoices.VALIDATE)

    texte = _texte(client.get(reverse("audit:imprimer"), {"module": "RH"}))

    assert "Journal d" in texte and "audit</h1>" in texte  # apostrophe échappée en HTML (&#x27;)
    assert "Awa Koné" in texte and "module : RH" in texte


def test_le_lien_imprimer_et_l_export_sont_sur_la_liste(client):
    client.force_login(UserFactory(role=Role.ADMIN))

    page = client.get(reverse("audit:journal"), {"module": "RH"}).content.decode()

    assert reverse("audit:imprimer") in page and reverse("audit:export_csv") in page
    assert "module%3DRH" in page or "module=RH" in page


# --- menu ---


def test_le_journal_apparait_dans_le_menu_de_l_admin_et_de_la_direction():
    from apps.accounts.navigation import entrees_pour

    for role in (Role.ADMIN, Role.DIRECTION):
        assert any(e["url"] == reverse("audit:journal") for e in entrees_pour(role, "/"))
    assert not any(e["url"] == reverse("audit:journal") for e in entrees_pour(Role.RH, "/"))
```

#### `apps/core/tests/test_rapports.py`

*103 lignes* — Infrastructure commune aux rapports imprimables : en-tête et mixin de liste.

```python
"""Infrastructure commune aux rapports imprimables : en-tête et mixin de liste."""

from datetime import datetime
from datetime import timezone as dt_timezone

import pytest
from django.template import Context, Template

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.core.rapports import contexte_entreprise, contexte_rapport
from apps.core.views import ImpressionListeMixin

pytestmark = pytest.mark.django_db


class _Requete:
    def __init__(self, user):
        self.user = user


def test_contexte_entreprise_reprend_les_reglages(settings):
    settings.ENTREPRISE_NOM = "DEN Source Group"
    settings.ENTREPRISE_ADRESSE = "Abidjan"
    settings.ENTREPRISE_NCC = "CI-123"

    assert contexte_entreprise() == {"nom": "DEN Source Group", "adresse": "Abidjan", "ncc": "CI-123"}


def test_contexte_rapport_identifie_qui_l_a_genere():
    utilisateur = UserFactory(role=Role.ADMIN, first_name="Awa", last_name="Koné")

    contexte = contexte_rapport(_Requete(utilisateur), titre="Missions", sous_titre="6 lignes")

    assert contexte["titre"] == "Missions" and contexte["sous_titre"] == "6 lignes"
    assert contexte["genere_par"] == "Awa Koné"
    assert (datetime.now(dt_timezone.utc) - contexte["genere_le"]).total_seconds() < 5


def test_sans_nom_le_genere_par_retombe_sur_l_identifiant():
    utilisateur = UserFactory(role=Role.ADMIN, first_name="", last_name="", username="demo_admin")

    contexte = contexte_rapport(_Requete(utilisateur), titre="x")

    assert contexte["genere_par"] == "demo_admin"


# --- ImpressionListeMixin._valeur ---


class _Sous:
    def __init__(self, nom):
        self.nom = nom


class _Objet:
    def __init__(self, libelle, sous=None):
        self.libelle = libelle
        self.sous = sous

    def get_libelle_display(self):
        return f"« {self.libelle} »"


def test_valeur_resout_un_attribut_simple():
    assert ImpressionListeMixin._valeur(_Objet("Abidjan"), "libelle") == "Abidjan"


def test_valeur_resout_une_methode_get_display():
    assert ImpressionListeMixin._valeur(_Objet("Abidjan"), "get_libelle_display") == "« Abidjan »"


def test_valeur_resout_un_chemin_en_pointilles():
    assert ImpressionListeMixin._valeur(_Objet("x", sous=_Sous("Bolloré")), "sous.nom") == "Bolloré"


def test_valeur_vide_ou_chemin_casse_donne_un_tiret():
    assert ImpressionListeMixin._valeur(_Objet(""), "libelle") == "—"
    assert ImpressionListeMixin._valeur(_Objet("x", sous=None), "sous.nom") == "—"
    assert ImpressionListeMixin._valeur(_Objet("x"), "inconnu") == "—"


def test_valeur_accepte_un_callable_pour_une_colonne_composee():
    colonne = lambda o: f"{o.libelle}!"  # noqa: E731

    assert ImpressionListeMixin._valeur(_Objet("Abidjan"), colonne) == "Abidjan!"


def test_le_rendu_echappe_les_libelles():
    html = Template(
        '{% include "rapports/liste_impression.html" %}'
    ).render(
        Context(
            {
                "entreprise": {"nom": "DEN"}, "titre": "T", "sous_titre": "",
                "genere_par": "x", "genere_le": datetime.now(dt_timezone.utc),
                "entetes": ["Client"], "lignes": [["<script>alert(1)</script>"]],
                "nombre": 1, "tronque": False,
            }
        )
    )

    assert "<script>" not in html and "&lt;script&gt;" in html
```

## Étape 7 — Brancher tout cela dans les réglages

#### `config/settings/base.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/settings/base.py (avant)
+++ config/settings/base.py (après)
@@ -113,4 +113,6 @@
                 "django.contrib.auth.context_processors.auth",
                 "django.contrib.messages.context_processors.messages",
+                "apps.accounts.context_processors.menu",
+                "apps.notifications.context_processors.notifications",
             ],
         },
```

#### `config/urls.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/urls.py (avant)
+++ config/urls.py (après)
@@ -8,12 +8,15 @@
 from django.contrib import admin
 from django.urls import include, path
-from django.views.generic import RedirectView
+from django.views.generic import RedirectView, TemplateView
 
 
 urlpatterns = [
+    path("", TemplateView.as_view(template_name="accueil_provisoire.html"), name="home"),
     path("imprimer/", DashboardImprimerView.as_view(), name="home_imprimer"),
     # Les navigateurs (et l'administration Django) réclament /favicon.ico : on renvoie vers l'icône du site.
     path("favicon.ico", RedirectView.as_view(url=settings.STATIC_URL + "img/favicon.png", permanent=True)),
+    path("", include("apps.accounts.urls")),
     path("audit/", include("apps.audit.urls")),
+    path("notifications/", include("apps.notifications.urls")),
     path("admin/", admin.site.urls),
 ]
```

Les deux processeurs de contexte apparaissent dans `TEMPLATES`, et `config/urls.py` monte les adresses de
`accounts` (connexion, MFA), de `notifications`, et la page d'accueil provisoire.

## Étape 8 — Compiler les styles

```bash
cd frontend
npm install
npm run build
cd ..
```

**Résultat attendu :** `npm install` télécharge Tailwind, Alpine.js et Font Awesome (quelques dizaines de
secondes) ; `npm run build` affiche `Done in …ms.` puis `copié static/vendor/…` pour cinq fichiers. Vérifiez :

```bash
ls static/css static/vendor/alpine static/vendor/fontawesome
```

**Résultat attendu :** `tailwind.css` (environ 30 Ko), `alpine.min.js`, `all.min.css`, `webfonts/` et `LICENSE.txt`.

> **Si `npm install` échoue** : vérifiez `node --version` (20 ou plus) et votre connexion. **Si la page s'affiche
> sans mise en forme** : `static/css/tailwind.css` manque ; relancez `npm run build`.

## Vérifier le chapitre

```bash
python manage.py check
```

```bash
python -m pytest apps/accounts/tests/test_password_reset.py apps/audit/tests/test_services.py apps/audit/tests/test_signals.py apps/audit/tests/test_views.py apps/core/tests/test_rapports.py -q --no-cov
```

**Résultat attendu :** `7 passed` (pour les 2 fichier(s) de tests présentés dans ce chapitre).

**Maintenant, regardez le résultat dans un navigateur :**

```bash
python manage.py runserver
```

1. Ouvrez **http://localhost:8000/connexion/** : la page de connexion aux couleurs bordeaux et orange.
2. Connectez-vous avec **`demo_rh`** et le mot de passe du chapitre 6. Vous arrivez sur la page « Bienvenue ». Le
   menu de gauche ne montre pour l'instant que **Accueil** : les autres écrans n'existent pas encore, le menu les
   ignore (c'est voulu). La **cloche** affiche `1` (la notification d'essai du chapitre 15) ; cliquez pour la lire.
3. Déconnectez-vous puis connectez-vous avec **`demo_direction`** : vous êtes **renvoyé vers
   `/mfa/activer/`**. Installez une application d'authentification sur votre téléphone, scannez le QR code,
   saisissez le code à 6 chiffres, **notez les 10 codes de secours**, puis continuez.
4. Déconnectez-vous et reconnectez-vous avec `demo_direction` : cette fois on vous demande **le code** (`/mfa/verifier/`).
5. Essayez de saisir 5 mots de passe faux pour `demo_rh` : la 6e tentative affiche « Trop de tentatives
   échouées » **même avec le bon mot de passe**.

> **Téléphone perdu pendant l'essai ?** `python manage.py reinitialiser_mfa demo_direction`.

Arrêtez le serveur avec `Ctrl+C`.

## Ce qu'il faut retenir

- Une page = un gabarit qui **hérite** de `base.html` ; les **composants** évitent de répéter du HTML.
- La sécurité de l'interface est **côté serveur** : jeton CSRF, garde de rôle, blocage des essais, CSP.
- Sans JavaScript en ligne, la politique de sécurité peut être **stricte** ; les comportements sont dans
  `app.js`, déclarés par des attributs `data-…`.
- Tailwind **scanne les fichiers** : après avoir ajouté des classes, **recompilez** (`npm run build:css`).

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 16 : socle de l'interface (gabarits, styles locaux, connexion, MFA, notifications)"
```

---

[← Chapitre 15](15-notifications.md) · [Sommaire](README.md) · [Chapitre 17 →](17-ecrans-rh.md)
