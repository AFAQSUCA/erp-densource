# Construire l'ERP DEN Source Group de A à Z

Ce tutoriel vous fait **reconstruire, fichier par fichier, l'application complète** : un ERP de
transport et de logistique (missions, camions, chauffeurs, carburant, stock, clients, personnel, congés,
facturation, trésorerie, tableau de bord, espace mobile du chauffeur, API), avec sa suite de **près de 1 800 tests**.

Chaque chapitre vous dit **quoi faire**, **pourquoi**, **quelles commandes lancer**, **donne le code complet
à créer**, puis **comment vérifier** que tout fonctionne avant de passer au suivant.

## Ce que ce tutoriel garantit

- **Le code est exact.** Il n'est pas recopié à la main : il est extrait automatiquement du dépôt par
  `outils/generer_tutoriel.py`. Si le code change, on régénère le tutoriel.
- **Le tutoriel a été rejoué.** `outils/tester_tutoriel.py` reconstruit le projet dans un dossier vide,
  chapitre après chapitre, en exécutant les commandes demandées (`check`, `makemigrations`, `migrate`,
  `npm run build`, `pytest`). À la fin : **tous les tests passent** (voir le chapitre 29).
- **Chaque fichier suivi par git est couvert** : soit présenté ici, soit exclu pour une raison écrite
  (tableau plus bas).

## Comment lire ce tutoriel

Il suit l'ordre dans lequel on construit vraiment un projet Django de cette taille :

1. **Le cerveau d'abord** (chapitres 2 à 15) : pour chaque domaine, les *modèles* (les tables), les
   *règles métier* (`services.py`) et leurs *tests*. Rien à cliquer dans un navigateur, mais tout est
   vérifié par des tests.
2. **Puis le visage** (chapitres 16 à 28) : les gabarits HTML, les formulaires, les vues, le tableau de
   bord, l'espace mobile et l'API.
3. **Enfin la vérification d'ensemble** (chapitre 29).

Chaque application n'utilise que celles qui la précèdent : on peut donc toujours s'arrêter à la fin
d'un chapitre avec un projet qui fonctionne.

## Sommaire

| N° | Chapitre | Fichiers | Lignes de code |
|---|---|---|---|
| 0 | [Prérequis et vue d'ensemble](00-prerequis.md) | — | — |
| 1 | [Le squelette du projet](01-squelette.md) | 17 | 562 |
| 2 | [Le socle : l'app core](02-core.md) | 18 | 699 |
| 3 | [Utilisateurs, rôles et sécurité de la connexion : l'app accounts](03-accounts.md) | 20 | 925 |
| 4 | [Le journal d'audit : l'app audit](04-audit.md) | 10 | 422 |
| 5 | [Personnel et congés : l'app hr](05-hr.md) | 20 | 1700 |
| 6 | [Les chauffeurs : l'app drivers](06-drivers.md) | 18 | 1701 |
| 7 | [Les clients : l'app customers](07-customers.md) | 11 | 397 |
| 8 | [Les camions : l'app fleet](08-fleet.md) | 14 | 1189 |
| 9 | [Les missions de transport : l'app missions](09-missions.md) | 15 | 1325 |
| 10 | [Le garage : l'app garage](10-garage.md) | 17 | 1568 |
| 11 | [Le stock de pièces : l'app inventory](11-inventory.md) | 16 | 1449 |
| 12 | [Le carburant : l'app fuel](12-fuel.md) | 14 | 1229 |
| 13 | [La facturation : l'app billing](13-billing.md) | 11 | 1535 |
| 14 | [La trésorerie : l'app finance](14-finance.md) | 8 | 566 |
| 15 | [Les notifications : l'app notifications](15-notifications.md) | 12 | 741 |
| 16 | [Le socle de l'interface : gabarits, styles, connexion, notifications](16-interface.md) | 34 | 1202 |
| 17 | [Écrans : personnel et congés](17-ecrans-rh.md) | 10 | 1482 |
| 18 | [Écrans : chauffeurs](18-ecrans-chauffeurs.md) | 7 | 785 |
| 19 | [Écrans : clients](19-ecrans-clients.md) | 8 | 793 |
| 20 | [Écrans : flotte](20-ecrans-flotte.md) | 8 | 1127 |
| 21 | [Écrans : missions et codes QR](21-ecrans-missions.md) | 14 | 2393 |
| 22 | [Écrans : garage, incidents et check-lists](22-ecrans-garage.md) | 14 | 1463 |
| 23 | [Écrans : stock de pièces](23-ecrans-stock.md) | 11 | 1821 |
| 24 | [Écrans : carburant](24-ecrans-carburant.md) | 9 | 1593 |
| 25 | [Écrans : facturation, dépenses et trésorerie](25-ecrans-finances.md) | 16 | 2211 |
| 26 | [La page d'accueil : le tableau de bord](26-tableau-de-bord.md) | 10 | 1455 |
| 27 | [L'espace mobile du chauffeur](27-mobile.md) | 29 | 2291 |
| 28 | [L'API REST](28-api.md) | 19 | 2548 |
| 29 | [Finalisation, vérifications et déploiement](29-finalisation.md) | 1 | 112 |

## Ce qui n'est pas recopié dans ce tutoriel

Ces fichiers sont dans le dépôt mais **ne se recopient pas**. Le chapitre concerné dit comment les obtenir.

| Fichiers | Raison |
|---|---|
| 39 (`apps/accounts/migrations/0001_initial.py`, `apps/accounts/migrations/0002_mfa.py`, `apps/accounts/migrations/__init__.py` …) | généré par `python manage.py makemigrations` |
| 7 (`GUIDE-INTERFACE.md`, `GUIDE-PARCOURS.md`, `architecture.md` …) | documents de référence à lire (ils décrivent le besoin), pas à recopier |
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
