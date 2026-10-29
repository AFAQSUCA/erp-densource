# Correction — Exercice 6

Une ligne, **deux fois**, dans `apps/fleet/views.py` : `("N° de châssis (VIN)", "vin")` après `("Modèle", "modele")`.

- `VehiculeImprimerView.colonnes` sert la page imprimable **et** son PDF (`?format=pdf`) : le PDF est construit
  depuis les mêmes colonnes, une seule déclaration suffit pour les deux.
- `VehiculeExporterXlsxView.colonnes` est déclarée à part, parce que l'Excel veut des **valeurs brutes** (un
  kilométrage en nombre, pas « 185 000 km »). Le VIN est un texte : la même clé `"vin"` convient aux deux.

Aucun test existant ne casse : ils ne figeaient pas la liste exacte des colonnes de la flotte.

**Vérification** : les 3 tests de l'exercice passent, et la suite complète aussi (3 420 tests).
