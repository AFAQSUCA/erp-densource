# Exercice 8 — Le stock de pièces dans l'API

**Semaine 10** · environ 3 heures · après le chapitre 32 (API REST)

## La demande

« Notre fournisseur de pièces veut brancher son logiciel sur notre stock pour nous proposer des commandes. Ouvrez
une **lecture seule** des articles dans l'API, avec ceux qui sont sous le seuil. »

## Ce qui doit marcher

- `GET /api/v1/articles/` (nom de route `api:article-list`) et le détail `api:article-detail`.
- Mêmes droits que l'écran du stock : ADMIN, DIRECTION, PARCAUTO ; tous les autres rôles reçoivent 403.
- Champs exposés : `id`, `reference`, `designation`, `categorie`, `quantite`, `seuil_minimal`, `pump`, et
  `sous_seuil` (vrai ou faux).
- Filtres : `?q=` (recherche sans accents, comme l'écran) et `?alerte=1` (au seuil ou en dessous, comme l'écran).
- Aucune écriture : POST et DELETE répondent 405.

## Où regarder

- `apps/api/v1/` : `serializers.py`, `filters.py`, `views.py` ; `apps/api/urls.py` (le routeur).
- Prenez modèle sur `VehiculeViewSet` : il réutilise le queryset **du service** de l'app et ses
  `permissions.CONSULTATION`.
- `apps/inventory/services.py` : `rechercher_articles`, `articles_sous_seuil`. La règle « sous le seuil » existe
  déjà ; ne la réécrivez pas autrement.

## Étapes conseillées

1. Copiez `test_exercice_08.py` dans `apps/api/tests/` et lancez-le : 10 tests échouent.
2. Le serializer, la vue, la route : la liste répond. Puis le filtre.
3. Ouvrez `/api/v1/docs/` (connecté en ADMIN) : la nouvelle ressource apparaît dans la documentation.

## Indice

Les écrans écrivent `?alerte=1`. Un filtre booléen de django-filter attend `true` ou `false` : le test de
l'alerte vous le fera découvrir.

## Correction

`correction.md`, puis `correction.diff`.
