# Chapitre 16 — Le socle de l'interface : gabarits, styles, connexion, notifications

> 34 fichier(s) dans ce chapitre, 1202 lignes de code.

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

*6 lignes*

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

/* Éléments Alpine.js masqués tant que le script n'a pas démarré (évite un flash à l'affichage). */
[x-cloak] { display: none !important; }
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

*48 lignes*

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
    </form>
  </div>
</div>
{% endblock %}
```

#### `apps/accounts/views.py`

*40 lignes*

```python
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView, LogoutView

from . import throttle
from .models import Role


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

*15 lignes*

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

*108 lignes* — Aides d'affichage : pastilles de statut colorées.

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

*26 lignes* — Aides communes aux vues.

```python
"""Aides communes aux vues."""


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

*63 lignes*

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
        <li class="flex items-start gap-4 p-4 {% if not n.est_lue %}bg-marque-50/40{% endif %}">
          <span class="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full {% if n.est_lue %}bg-transparent{% else %}bg-marque-600{% endif %}" aria-hidden="true"></span>
          <div class="min-w-0 flex-1">
            <p class="flex flex-wrap items-center gap-2">
              {% badge n.niveau n.get_niveau_display %}
              <span class="text-xs font-semibold uppercase tracking-wide text-slate-600">{{ n.get_categorie_display }}</span>
              <span class="text-xs text-slate-600">{{ n.created_at|date:"d/m/Y H:i" }}</span>
              {% if not n.est_lue %}<span class="sr-only">Non lue</span>{% endif %}
            </p>
            <p class="mt-1 font-semibold text-slate-900">{{ n.titre }}</p>
            {% if n.message %}<p class="mt-0.5 text-sm text-slate-700">{{ n.message }}</p>{% endif %}
          </div>
          <form method="post" action="{% url 'notifications:lire' n.pk %}" class="shrink-0">
            {% csrf_token %}
            <button type="submit"
                    class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
              {% if n.url %}Ouvrir{% elif n.est_lue %}Lue{% else %}Marquer comme lue{% endif %}
            </button>
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

*3 lignes*

```python
from django.shortcuts import render

# Create your views here.
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

## Étape 7 — Brancher tout cela dans les réglages

#### `config/settings/base.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/settings/base.py (avant)
+++ config/settings/base.py (après)
@@ -105,4 +105,6 @@
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
@@ -8,10 +8,13 @@
 from django.contrib import admin
 from django.urls import include, path
-from django.views.generic import RedirectView
+from django.views.generic import RedirectView, TemplateView
 
 
 urlpatterns = [
+    path("", TemplateView.as_view(template_name="accueil_provisoire.html"), name="home"),
     # Les navigateurs (et l'administration Django) réclament /favicon.ico : on renvoie vers l'icône du site.
     path("favicon.ico", RedirectView.as_view(url=settings.STATIC_URL + "img/favicon.png", permanent=True)),
+    path("", include("apps.accounts.urls")),
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
python -m pytest apps/audit/tests/test_services.py apps/audit/tests/test_signals.py -q --no-cov
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
