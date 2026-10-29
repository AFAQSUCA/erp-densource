# Exercice 7 — Les missions annulées du mois au tableau de bord

**Semaine 9** · environ 2 heures · après le chapitre 30 (tableau de bord)

## La demande

« Sur la page d'accueil, à côté des missions en cours, on veut voir combien de missions ont été **annulées ce
mois-ci**. »

## Ce qui doit marcher

- Une fonction `missions_annulees_entre(debut, fin)` dans **`apps/missions/services.py`** : le nombre de missions
  annulées entre deux dates incluses, selon leur date d'annulation.
- Le bloc Exploitation (`dashboard.services.exploitation`) donne `missions_annulees_du_mois`, du 1er du mois à
  aujourd'hui.
- La page d'accueil de la DIRECTION affiche « Annulées ce mois » ; le Parc Auto, qui ne voit pas les indicateurs
  de missions, ne l'affiche pas.

## Pourquoi le calcul n'est-il pas dans le tableau de bord ?

Relisez le début de `apps/dashboard/services.py` : le tableau de bord **assemble** des lectures fournies par les
apps, il ne calcule rien lui-même. Compter des missions est l'affaire de `missions`.

## Où regarder

- `apps/missions/services.py` : `repartition_par_statut`, `missions_par_mois` (des fonctions de lecture voisines).
- `apps/dashboard/services.py` : `exploitation()`.
- `apps/dashboard/templates/dashboard/index.html` et `apps/dashboard/views.py` (la page et son PDF).

## Étapes conseillées

1. Copiez `test_exercice_07.py` dans `apps/dashboard/tests/` et lancez-le : 3 tests échouent.
2. La fonction de lecture d'abord, puis le bloc, puis l'affichage (et le PDF du tableau de bord).
3. Lancez toute la suite : un test vérifie que la page d'un ADMIN ne dépasse pas **34 requêtes SQL**.
   Votre ajout en coûte une ; tient-il toujours ?

## Correction

`correction.md`, puis `correction.diff`.
