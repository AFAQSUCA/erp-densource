# Construire l'ERP DEN Source Group de A à Z

Ce tutoriel vous fait **reconstruire, fichier par fichier, l'application complète** : un ERP de
transport et de logistique (missions, camions, chauffeurs, carburant, stock, clients, personnel, congés,
facturation, trésorerie, comptabilité, tableau de bord, espace mobile du chauffeur, API), avec sa suite de
**plus de 2 500 tests**.

Chaque chapitre vous dit **quoi faire**, **pourquoi**, **quelles commandes lancer**, **donne le code complet
à créer**, puis **comment vérifier** que tout fonctionne avant de passer au suivant.

## Ce que ce tutoriel garantit

- **Le code est exact.** Il n'est pas recopié à la main : il est extrait automatiquement du dépôt par
  `outils/generer_tutoriel.py`. Si le code change, on régénère le tutoriel.
- **Le tutoriel a été rejoué.** `outils/tester_tutoriel.py` reconstruit le projet dans un dossier vide,
  chapitre après chapitre, en exécutant les commandes demandées (`check`, `makemigrations`, `migrate`,
  `npm run build`, `pytest`). À la fin : **tous les tests passent** (voir le chapitre 31).
- **Chaque fichier suivi par git est couvert** : soit présenté ici, soit exclu pour une raison écrite
  (tableau plus bas).

## Comment lire ce tutoriel

Il suit l'ordre dans lequel on construit vraiment un projet Django de cette taille :

1. **Le cerveau d'abord** (chapitres 2 à 16) : pour chaque domaine, les *modèles* (les tables), les
   *règles métier* (`services.py`) et leurs *tests*. Rien à cliquer dans un navigateur, mais tout est
   vérifié par des tests.
2. **Puis le visage** (chapitres 17 à 30) : les gabarits HTML, les formulaires, les vues, le tableau de
   bord, l'espace mobile et l'API.
3. **Enfin la vérification d'ensemble** (chapitre 31).

Chaque application n'utilise que celles qui la précèdent : on peut donc toujours s'arrêter à la fin
d'un chapitre avec un projet qui fonctionne.

## Sommaire

| N° | Chapitre | Fichiers | Lignes de code |
|---|---|---|---|
| 0 | [Prérequis et vue d'ensemble](00-prerequis.md) | — | — |
| 1 | [Le squelette du projet](01-squelette.md) | 18 | 753 |
| 2 | [Le socle : l'app core](02-core.md) | 21 | 1093 |
| 3 | [Utilisateurs, rôles et sécurité de la connexion : l'app accounts](03-accounts.md) | 20 | 944 |
| 4 | [Le journal d'audit : l'app audit](04-audit.md) | 11 | 513 |
| 5 | [Personnel et congés : l'app hr](05-hr.md) | 21 | 2283 |
| 6 | [Les chauffeurs : l'app drivers](06-drivers.md) | 19 | 1984 |
| 7 | [Les clients : l'app customers](07-customers.md) | 11 | 402 |
| 8 | [Les camions : l'app fleet](08-fleet.md) | 14 | 1191 |
| 9 | [Les missions de transport : l'app missions](09-missions.md) | 22 | 2885 |
| 10 | [Le garage : l'app garage](10-garage.md) | 17 | 1599 |
| 11 | [Le stock de pièces : l'app inventory](11-inventory.md) | 16 | 1459 |
| 12 | [Le carburant : l'app fuel](12-fuel.md) | 14 | 1240 |
| 13 | [La facturation : l'app billing](13-billing.md) | 13 | 2783 |
| 14 | [La trésorerie : l'app finance](14-finance.md) | 16 | 2276 |
| 15 | [La comptabilité en partie double : l'app accounting](15-accounting.md) | 21 | 2610 |
| 16 | [Les notifications : l'app notifications](16-notifications.md) | 14 | 1137 |
| 17 | [Le socle de l'interface : gabarits, styles, connexion, notifications](17-interface.md) | 54 | 2421 |
| 18 | [Écrans : personnel et congés](18-ecrans-rh.md) | 14 | 2513 |
| 19 | [Écrans : chauffeurs](19-ecrans-chauffeurs.md) | 8 | 1042 |
| 20 | [Écrans : clients](20-ecrans-clients.md) | 8 | 823 |
| 21 | [Écrans : flotte](21-ecrans-flotte.md) | 8 | 1166 |
| 22 | [Écrans : missions et codes QR](22-ecrans-missions.md) | 22 | 3683 |
| 23 | [Écrans : garage, incidents et check-lists](23-ecrans-garage.md) | 14 | 1533 |
| 24 | [Écrans : stock de pièces](24-ecrans-stock.md) | 11 | 1850 |
| 25 | [Écrans : carburant](25-ecrans-carburant.md) | 9 | 1674 |
| 26 | [Écrans : facturation, dépenses et trésorerie](26-ecrans-finances.md) | 38 | 6277 |
| 27 | [Écrans : plan comptable, opérations diverses et rapports comptables](27-ecrans-comptabilite.md) | 22 | 1969 |
| 28 | [La page d'accueil : le tableau de bord](28-tableau-de-bord.md) | 13 | 2168 |
| 29 | [L'espace mobile du chauffeur](29-mobile.md) | 31 | 2523 |
| 30 | [L'API REST](30-api.md) | 20 | 2664 |
| 31 | [Finalisation, vérifications et déploiement](31-finalisation.md) | 1 | 132 |

## Ce qui n'est pas recopié dans ce tutoriel

Ces fichiers sont dans le dépôt mais **ne se recopient pas**. Le chapitre concerné dit comment les obtenir.

| Fichiers | Raison |
|---|---|
| 59 (`apps/accounting/migrations/0001_initial.py`, `apps/accounting/migrations/0003_exercicecomptable.py`, `apps/accounting/migrations/__init__.py` …) | généré par `python manage.py makemigrations` (sauf la migration de données du plan comptable, écrite à la main : voir le chapitre « La comptabilité en partie double ») |
| 11 (`GUIDE-DEPLOIEMENT.md`, `GUIDE-INTERFACE.md`, `GUIDE-PARCOURS.md` …) | documents de référence à lire (ils décrivent le besoin), pas à recopier |
| 8 (`.dockerignore`, `Dockerfile`, `docker-compose.yml` …) | mise en production (Docker, Nginx, Gunicorn) : hors périmètre de ce tutoriel de développement — voir GUIDE-DEPLOIEMENT.md |
| 5 (`static/vendor/alpine/alpine.min.js`, `static/vendor/fontawesome/LICENSE.txt`, `static/vendor/fontawesome/css/all.min.css` …) | généré par `npm run build` (bibliothèques Alpine.js et Font Awesome) |
| 4 (`static/img/favicon.png`, `static/img/icon-192.png`, `static/img/icon-512.png` …) | identité visuelle de DEN Source Group : à copier depuis le dépôt (voir le chapitre « Le socle de l'interface ») |
| 3 (`CAHIER DES CHARGES FONCTIONNEL ET TECHNIQUE.docx`, `Presentation-ERP-DEN-Source.docx`, `Presentation-ERP-DEN-Source.pptx`) | documents de présentation, sans rapport avec le fonctionnement |
| 1 (`frontend/package-lock.json`) | généré par `npm install` |
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
