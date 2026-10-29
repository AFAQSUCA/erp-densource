# Exercice 6 — Le n° de châssis dans le rapport de la flotte

**Semaine 8** · environ 1 heure 30 · après le chapitre 22 (écrans de la flotte)

## La demande

« L'assureur nous demande la liste de nos camions **avec le numéro de châssis (VIN)**, en PDF et en Excel. »

## Ce qui doit marcher

- Le rapport imprimable de la flotte a une colonne « N° de châssis (VIN) », juste après « Modèle ».
- Le PDF de ce rapport la contient.
- L'export Excel aussi, avec la valeur brute.

## Où regarder

- `apps/fleet/views.py` : `VehiculeImprimerView` et `VehiculeExporterXlsxView`, et leur attribut `colonnes`.
- `apps/core/views.py` (`ImpressionListeMixin`) et `apps/core/xlsx.py` (`ExportXlsxMixin`) : comment ces colonnes
  deviennent un tableau, un PDF et un classeur.

## Étapes conseillées

1. Copiez `test_exercice_06.py` dans `apps/fleet/tests/` et lancez-le : 3 tests échouent.
2. Trouvez où sont déclarées les colonnes. Combien de déclarations ? Pourquoi deux ?
3. Relancez le test, puis toute la suite.

## À lire dans le test

Le test du PDF **décompresse** le fichier avant d'y chercher le VIN : un PDF n'est pas du texte lisible. Un test
qui comparait seulement la taille du fichier passait déjà avant la correction ; il ne prouvait rien. Un bon test
échoue tant que le travail n'est pas fait.

## Correction

`correction.md`, puis `correction.diff`.
