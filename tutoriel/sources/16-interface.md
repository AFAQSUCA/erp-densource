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

{{FICHIER frontend/package.json}}

`npm run build` enchaîne deux scripts : `build:css` (Tailwind) et `vendor` (copie Alpine.js et Font Awesome).
Les versions sont **épinglées** pour un résultat reproductible.

{{FICHIER frontend/tailwind.config.js}}

Deux points importants : les **couleurs de la marque** (`marque` = bordeaux #8B0319, `accent` = orange
#F28A14) sont définies ici ; et `content` liste **où Tailwind cherche les classes** : les gabarits **et le
code Python** (des classes sont écrites dans `apps/core/templatetags/ui.py`). Ne composez donc jamais un nom de
classe par morceaux (`"bg-" + couleur`) : Tailwind ne le verrait pas.

{{FICHIER frontend/input.css}}

{{FICHIER frontend/vendor.js}}

{{FICHIER frontend/.gitignore}}

{{FICHIER frontend/README.md}}

## Étape 3 — Les gabarits communs

Créez d'abord les dossiers :

```bash
mkdir -p templates/components templates/registration templates/accounts static/js
```

{{FICHIER templates/components/_assets.html}}

Les trois fichiers chargés sont locaux : le CSS compilé, Font Awesome, `app.js` puis Alpine.js (attribut `defer`
: le script s'exécute après l'affichage de la page).

{{FICHIER static/js/app.js}}

Il n'y a **aucun code dans les pages** : un formulaire qui demande confirmation porte simplement
`data-confirm="Question ?"` ; ce fichier s'en occupe pour toute l'application.

{{FICHIER templates/base.html}}

Structure de la page : un menu latéral (`{% for entree in menu %}` : le menu produit par le registre du chapitre
3), une en-tête (cloche des notifications, nom et rôle de l'utilisateur, lien vers les codes de secours pour les
rôles soumis à la MFA, bouton de déconnexion en `POST` avec jeton CSRF) et la zone `{% block contenu %}`. Les blocs
`titre`, `entete`, `layout` et `contenu` sont les « trous » que remplissent les pages filles.

{{FICHIER templates/components/_champ.html}}

{{FICHIER templates/components/_messages.html}}

{{FICHIER templates/components/_pagination.html}}

{{FICHIER templates/403.html}}

{{FICHIER templates/404.html}}

Django utilise automatiquement `403.html` et `404.html` pour les erreurs « accès refusé » et « page
introuvable ».

## Étape 4 — La connexion et la double authentification

{{FICHIER templates/registration/login.html}}

{{FICHIER apps/accounts/views.py}}

`ConnexionView` prolonge `LoginView` de Django : elle ajoute le **blocage anti force brute** (réponse 429 avant
même de vérifier le mot de passe) et la **session de 15 minutes** pour les chauffeurs.

{{FICHIER apps/accounts/forms.py}}

{{FICHIER apps/accounts/views_mfa.py}}

Quatre vues : **vérifier** (saisir le code à chaque ouverture de session), **activer** (QR code + premier
code + codes de secours affichés **une seule fois**), **QR** (l'image, jamais mise en cache) et **codes**
(régénérer les codes de secours). La redirection après vérification refuse toute adresse extérieure au site.

{{FICHIER apps/accounts/urls.py}}

{{FICHIER apps/accounts/context_processors.py}}

{{FICHIER templates/accounts/mfa_verifier.html}}

{{FICHIER templates/accounts/mfa_activer.html}}

{{FICHIER templates/accounts/mfa_codes.html}}

{{FICHIER templates/accounts/mfa_codes_affiches.html}}

## Étape 5 — Aides d'affichage, notifications, page d'accueil provisoire

{{FICHIER apps/core/templatetags/ui.py}}

Des **balises de gabarit personnalisées** : `{% badge %}` affiche une pastille colorée pour un statut (le texte
porte toujours le sens, la couleur n'est qu'un renfort : accessibilité).

{{FICHIER apps/core/views.py}}

`PaginationTolerante` : une page inexistante ou illisible affiche la première ou la dernière page au lieu d'une
erreur 404.

{{FICHIER apps/notifications/views.py}}

{{FICHIER apps/notifications/urls.py}}

{{FICHIER apps/notifications/context_processors.py}}

{{FICHIER apps/notifications/templates/notifications/liste.html}}

{{FICHIER apps/audit/views.py}}

(Ce fichier ne contient qu'un commentaire ; l'app `audit` n'a pas d'écran dédié.)

La **page d'accueil provisoire** : le vrai tableau de bord arrivera au chapitre 26 et renvoie vers tous les
écrans ; en attendant, une page simple permet de tester la connexion.

{{ACCUEIL_PROVISOIRE}}

## Étape 6 — Les tests

{{RESTANTS}}

## Étape 7 — Brancher tout cela dans les réglages

{{CONFIG}}

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

{{PYTEST}}

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
