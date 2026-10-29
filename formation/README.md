# Formation — pouvoir modifier le projet seul

Programme de **12 semaines, 3 à 4 heures par jour**, pour passer de « je comprends le projet » à « je le modifie sans
aide et sans rien casser ». Chaque étape se termine par une vraie modification, vérifiée par des tests.

| Phase | Semaines | Contenu | Vous savez faire à la fin |
|---|---|---|---|
| **1. La carte** | 1-2 | [`semaines-01-02-la-carte.md`](semaines-01-02-la-carte.md) : le guide de parcours et 12 questions | retrouver où se trouve une règle, un écran, un test |
| **2. La reconstruction** | 3-10 | le tutoriel (`tutoriel/`), un chapitre par jour, et **un exercice par semaine** | ajouter un champ, une règle, un droit, un écran, une ressource d'API |
| **3. L'autonomie** | 11-12 | [`semaines-11-12-projet-final.md`](semaines-11-12-projet-final.md) : une fonctionnalité complète, seul | livrer une évolution de bout en bout |

## Le calendrier de la phase 2

| Semaine | Chapitres du tutoriel | Exercice |
|---|---|---|
| 3 | 0 à 5 | [1 — La couleur d'un camion](exercices/01-couleur-camion/) |
| 4 | 6 à 10 | [2 — Un 5e document : la carte de transport](exercices/02-carte-de-transport/) |
| 5 | 11 à 15 | [3 — Un délai d'alerte propre aux chauffeurs](exercices/03-delai-alerte-chauffeurs/) |
| 6 | 16 à 18 | [4 — Une catégorie de dépense « Frais bancaires »](exercices/04-categorie-frais-bancaires/) |
| 7 | 19 à 23 | [5 — La Finance et la RH consultent les missions](exercices/05-missions-finance-rh/) |
| 8 | 24 à 27 | [6 — Le n° de châssis dans le rapport de la flotte](exercices/06-colonne-vin-flotte/) |
| 9 | 28 à 30 | [7 — Les missions annulées du mois au tableau de bord](exercices/07-missions-annulees-tableau-de-bord/) |
| 10 | 31 à 34 | [8 — Le stock de pièces dans l'API](exercices/08-api-articles/) |

Chaque exercice est fait **dans le projet de référence** (ce dépôt), sur une branche à vous, pas dans le projet
reconstruit par le tutoriel : c'est ce code-là que vous aurez à modifier plus tard.

## Faire un exercice

```bash
git checkout -b exercice-01                      # une branche par exercice : main reste intacte
cp formation/exercices/01-couleur-camion/test_exercice_01.py apps/fleet/tests/
python -m pytest apps/fleet/tests/test_exercice_01.py -q --no-cov    # il échoue : c'est le point de départ
```

1. Lisez le `README.md` de l'exercice : la demande, ce qui doit marcher, où regarder.
2. Modifiez le code jusqu'à ce que le test passe.
3. Lancez **toute** la suite : `python -m pytest -q --no-cov`. Si d'autres tests échouent, ne les « faites pas
   passer » à l'aveugle : comprenez ce qu'ils protégeaient (exercices 2 à 5).
4. Comparez avec `correction.md` puis `correction.diff`, **seulement à la fin**.
5. Revenez sur `main` sans garder l'exercice : `git checkout main && git branch -D exercice-01`
   (supprimez aussi la migration et le fichier de test copiés s'ils restent).

## Ce que chaque exercice vous apprend

| N° | Notion principale | Le piège qu'il fait découvrir |
|---|---|---|
| 1 | modèle → migration → service → formulaire → vue → gabarit | le service n'accepte que les arguments qu'il déclare |
| 2 | une liste de choix utilisée partout | 9 tests et le classeur d'import dépendaient du nombre « 4 » |
| 3 | un paramètre modifiable à l'écran | distinguer ce qui concerne les camions de ce qui concerne les chauffeurs |
| 4 | une dépense et son écriture comptable | `max_length` trop court, et une dépense sans compte annule toute la saisie |
| 5 | les droits par rôle | une règle de l'entreprise (RH = Finance) ; 15 tests décrivaient l'ancienne règle |
| 6 | les rapports PDF et Excel | deux déclarations de colonnes, et un test qui ne prouvait rien |
| 7 | le tableau de bord | le calcul appartient à l'app `missions`, et le nombre de requêtes est surveillé |
| 8 | l'API REST | réutiliser les règles du service, et la convention `?alerte=1` |

## Comment les corrections ont été vérifiées

Pour chaque exercice : le test de validation **échoue** sur le code actuel, il **passe** avec la correction, et la
**suite complète** du projet passe avec la correction appliquée (3 419 à 3 427 tests selon l'exercice). La
correction n'est **pas** appliquée au projet : `correction.diff` se lit, ou s'applique sur une branche d'essai
(`git apply formation/exercices/NN-…/correction.diff`).

## Suivi

| Étape | Fait le | Remarques |
|---|---|---|
| Semaines 1-2 : les 12 questions | | |
| Exercice 1 | | |
| Exercice 2 | | |
| Exercice 3 | | |
| Exercice 4 | | |
| Exercice 5 | | |
| Exercice 6 | | |
| Exercice 7 | | |
| Exercice 8 | | |
| Projet final : besoin validé | | |
| Projet final : en ligne | | |
