# Exercice 2 — Un 5e document : la carte de transport

**Semaine 4** · environ 3 heures · après le chapitre 23 du tutoriel (écrans des missions)

## La demande

« La **carte de transport** est obligatoire pour nos camions, comme la carte grise, l'assurance, la visite technique
et la patente. Suivez-la de la même façon : alerte avant l'expiration, et pas de mission sans elle. »

## Ce qui doit marcher

- `TypeDocument.CARTE_TRANSPORT` existe, libellé « Carte de transport ».
- Un camion qui a les 4 anciens documents mais pas la carte de transport **ne peut pas être affecté** ; le message
  dit « carte de transport non enregistrée ».
- Une carte de transport qui expire dans 10 jours apparaît dans les documents à renouveler.
- La fiche du camion la montre ; le **classeur d'import Excel** a ses deux colonnes.

## Où regarder

- `apps/fleet/models.py` : `TypeDocument`.
- Cherchez **toutes** les utilisations : `grep -rn "TypeDocument" apps`. Où la liste des documents est-elle écrite
  en dur au lieu d'être lue dans `TypeDocument` ?
- `apps/importation/modele.py` : le classeur modèle (colonnes, ligne d'exemple, largeurs).

## Étapes conseillées

1. Copiez `test_exercice_02.py` dans `apps/fleet/tests/` et lancez-le : 4 tests échouent.
2. Ajoutez le type, générez la migration, relancez.
3. **Lancez toute la suite.** Des tests d'autres fichiers vont échouer : c'est le cœur de l'exercice.
   Pour chacun, demandez-vous : *le code est-il faux, ou le test décrivait-il l'ancienne règle ?*
4. Le classeur modèle livré avec le projet se régénère : `python manage.py generer_modele_import`.

## Indice

Ajouter une valeur à une liste de choix paraît anodin. Mais tout ce qui comptait « 4 documents » (tests, ligne
d'exemple du classeur, largeurs des colonnes) doit suivre.

## Correction

`correction.md`, puis `correction.diff`.
