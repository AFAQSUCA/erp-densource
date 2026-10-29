# Construire l'ERP DEN Source Group de A à Z

Ce tutoriel vous fait **reconstruire, fichier par fichier, l'application complète** : un ERP de
transport et de logistique (missions, camions, chauffeurs, carburant, stock, clients, personnel, congés,
facturation, trésorerie, comptabilité, tableau de bord, espace mobile du chauffeur, API), avec sa suite de
**plus de 3 400 tests**.

Chaque chapitre vous dit **quoi faire**, **pourquoi**, **quelles commandes lancer**, **donne le code complet
à créer**, puis **comment vérifier** que tout fonctionne avant de passer au suivant.

## Ce que ce tutoriel garantit

- **Le code est exact.** Il n'est pas recopié à la main : il est extrait automatiquement du dépôt par
  `outils/generer_tutoriel.py`. Si le code change, on régénère le tutoriel.
- **Le tutoriel a été rejoué.** `outils/tester_tutoriel.py` reconstruit le projet dans un dossier vide,
  chapitre après chapitre, en exécutant les commandes demandées (`check`, `makemigrations`, `migrate`,
  `npm run build`, `pytest`). À la fin : **tous les tests passent** (voir le chapitre 34).
- **Chaque fichier suivi par git est couvert** : soit présenté ici, soit exclu pour une raison écrite
  (tableau plus bas).

## Comment lire ce tutoriel

Il suit l'ordre dans lequel on construit vraiment un projet Django de cette taille :

1. **Le cerveau d'abord** (chapitres 2 à 17) : pour chaque domaine, les *modèles* (les tables), les
   *règles métier* (`services.py`) et leurs *tests*. Rien à cliquer dans un navigateur, mais tout est
   vérifié par des tests.
2. **Puis le visage** (chapitres 18 à 33) : les gabarits HTML, les formulaires, les vues, le tableau de
   bord, l'espace mobile et l'API.
3. **Enfin la vérification d'ensemble** (chapitre 34).

Chaque application n'utilise que celles qui la précèdent : on peut donc toujours s'arrêter à la fin
d'un chapitre avec un projet qui fonctionne.

## Sommaire

| N° | Chapitre | Fichiers | Lignes de code |
|---|---|---|---|
| 0 | [Prérequis et vue d'ensemble](00-prerequis.md) | — | — |
| 1 | [Le squelette du projet](01-squelette.md) | 19 | 849 |
| 2 | [Le socle : l'app core](02-core.md) | 36 | 2529 |
| 3 | [Utilisateurs, rôles et sécurité de la connexion : l'app accounts](03-accounts.md) | 21 | 1246 |
| 4 | [Le journal d'audit : l'app audit](04-audit.md) | 12 | 637 |
| 5 | [Les réglages modifiables à l'écran : l'app parametres](05-parametres.md) | 7 | 273 |
| 6 | [Personnel et congés : l'app hr](06-hr.md) | 23 | 3096 |
| 7 | [Les chauffeurs : l'app drivers](07-drivers.md) | 21 | 2427 |
| 8 | [Les clients : l'app customers](08-customers.md) | 11 | 428 |
| 9 | [Les camions : l'app fleet](09-fleet.md) | 14 | 1450 |
| 10 | [Les missions de transport : l'app missions](10-missions.md) | 24 | 3440 |
| 11 | [Le garage : l'app garage](11-garage.md) | 17 | 1658 |
| 12 | [Le stock de pièces : l'app inventory](12-inventory.md) | 18 | 1539 |
| 13 | [Le carburant : l'app fuel](13-fuel.md) | 16 | 1563 |
| 14 | [La facturation : l'app billing](14-billing.md) | 18 | 3211 |
| 15 | [La trésorerie : l'app finance](15-finance.md) | 17 | 2295 |
| 16 | [La comptabilité en partie double : l'app accounting](16-accounting.md) | 31 | 4746 |
| 17 | [Les notifications : l'app notifications](17-notifications.md) | 16 | 1409 |
| 18 | [Le socle de l'interface : gabarits, styles, connexion, notifications](18-interface.md) | 70 | 3753 |
| 19 | [Écrans : personnel et congés](19-ecrans-rh.md) | 18 | 3355 |
| 20 | [Écrans : chauffeurs](20-ecrans-chauffeurs.md) | 8 | 1117 |
| 21 | [Écrans : clients](21-ecrans-clients.md) | 8 | 905 |
| 22 | [Écrans : flotte](22-ecrans-flotte.md) | 9 | 1414 |
| 23 | [Écrans : missions et codes QR](23-ecrans-missions.md) | 25 | 4401 |
| 24 | [Écrans : garage, incidents et check-lists](24-ecrans-garage.md) | 14 | 1553 |
| 25 | [Écrans : stock de pièces](25-ecrans-stock.md) | 10 | 1615 |
| 26 | [Écrans : carburant](26-ecrans-carburant.md) | 12 | 1961 |
| 27 | [Écrans : facturation, dépenses et trésorerie](27-ecrans-finances.md) | 42 | 7289 |
| 28 | [Écrans : plan comptable, opérations diverses et rapports comptables](28-ecrans-comptabilite.md) | 33 | 3649 |
| 29 | [Le suivi des sauvegardes : l'app sauvegardes](29-sauvegardes.md) | 10 | 420 |
| 30 | [La page d'accueil : le tableau de bord](30-tableau-de-bord.md) | 15 | 2722 |
| 31 | [L'espace mobile du chauffeur](31-mobile.md) | 32 | 2794 |
| 32 | [L'API REST](32-api.md) | 25 | 3440 |
| 33 | [L'import Excel des données : l'app importation](33-importation.md) | 18 | 1482 |
| 34 | [Finalisation, vérifications et déploiement](34-finalisation.md) | 12 | 1540 |

## Ce qui n'est pas recopié dans ce tutoriel

Ces fichiers sont dans le dépôt mais **ne se recopient pas**. Le chapitre concerné dit comment les obtenir.

| Fichiers | Raison |
|---|---|
| 84 (`apps/accounting/migrations/0001_initial.py`, `apps/accounting/migrations/0003_exercicecomptable.py`, `apps/accounting/migrations/0004_piece_reference_100.py` …) | généré par `python manage.py makemigrations` (sauf les migrations écrites à la main : le plan comptable, voir le chapitre « La comptabilité en partie double », et les triggers PostgreSQL des journaux append-only, voir les chapitres « Le journal d'audit » et « Le stock de pièces ») |
| 35 (`formation/README.md`, `formation/exercices/01-couleur-camion/README.md`, `formation/exercices/01-couleur-camion/correction.diff` …) | programme de formation (exercices et corrections), à faire après le tutoriel |
| 21 (`GUIDE-DEPLOIEMENT.md`, `GUIDE-INTERFACE.md`, `GUIDE-PARCOURS.md` …) | documents de référence à lire (ils décrivent le besoin), pas à recopier |
| 17 (`.dockerignore`, `Dockerfile`, `docker-compose.yml` …) | mise en production (Docker, Nginx, Gunicorn) : hors périmètre de ce tutoriel de développement — voir GUIDE-DEPLOIEMENT.md |
| 7 (`static/vendor/alpine/alpine.min.js`, `static/vendor/fontawesome/LICENSE.txt`, `static/vendor/fontawesome/css/all.min.css` …) | généré par `npm run build` (bibliothèques Alpine.js et Font Awesome) |
| 4 (`static/img/favicon.png`, `static/img/icon-192.png`, `static/img/icon-512.png` …) | identité visuelle de DEN Source Group : à copier depuis le dépôt (voir le chapitre « Le socle de l'interface ») |
| 3 (`CAHIER DES CHARGES FONCTIONNEL ET TECHNIQUE.docx`, `Presentation-ERP-DEN-Source.docx`, `Presentation-ERP-DEN-Source.pptx`) | documents de présentation, sans rapport avec le fonctionnement |
| 1 (`frontend/package-lock.json`) | généré par `npm install` |
| 1 (`modele-donnees-entreprise-DEN-Source.xlsx`) | classeur Excel modèle, généré par `python manage.py generer_modele_import` (voir le chapitre « L'import Excel des données ») |
| 1 (`recette_navigateurs/RESULTATS.md`) | généré par la recette navigateurs (`python -m pytest recette_navigateurs`) |
| 1 (`requirements/prod.lock`) | généré par `python outils/verrouiller_dependances.py` (versions figées de la production) |
| 1 (`static/css/tailwind.css`) | généré par `npm run build` (Tailwind compilé) |

## Avant de commencer

Lisez le [chapitre 0](00-prerequis.md) : il liste les outils à installer, explique l'arborescence finale
du projet et la méthode de travail (une copie de fichier, une vérification, un commit).

## Petit lexique des symboles

| Symbole | Sens |
|---|---|
| `#### chemin/du/fichier.py` | un fichier à créer, avec son contenu complet juste en dessous |
| ` ```bash ` | une commande à taper dans le terminal, à la racine du projet |
| ` ```diff ` | une modification de fichier existant : les lignes `+` sont à ajouter |
| **Résultat attendu** | ce que vous devez voir ; si ce n'est pas le cas, ne continuez pas |
