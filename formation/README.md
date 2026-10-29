# Formation — pouvoir modifier le projet seul

Programme de 12 semaines (en cours de rédaction) :

| Phase | Semaines | Contenu |
|---|---|---|
| 1. La carte | 1-2 | `GUIDE-PARCOURS.md`, lancer le projet et les tests |
| 2. La reconstruction | 3-10 | le tutoriel, un chapitre par jour, et un exercice de modification par semaine |
| 3. L'autonomie | 11-12 | une fonctionnalité complète, seul |

## Exercices

| N° | Exercice | État |
|---|---|---|
| 1 | Ajouter la couleur d'un camion | test de validation + correction prêts |
| 2 | Nouveau document réglementaire (carte de transport) | à rédiger |
| 3 | Nouveau paramètre : délai d'alerte des permis | à rédiger |
| 4 | Nouvelle catégorie de dépense (frais bancaires, compte 631000) | à rédiger |
| 5 | Droit de consultation des missions pour la Finance et la RH | à rédiger |
| 6 | Colonne VIN dans l'export Excel et le PDF de la flotte | à rédiger |
| 7 | Indicateur « missions annulées » au tableau de bord | à rédiger |
| 8 | Ressource « articles » en lecture seule dans l'API | à rédiger |

## Faire un exercice

1. Copier `test_exercice_NN.py` dans le dossier `tests/` de l'app indiquée, puis le lancer : il échoue.
2. Modifier le code jusqu'à ce qu'il passe, puis lancer toute la suite (`python -m pytest -q --no-cov`).
3. Comparer avec `correction.diff` seulement à la fin.
