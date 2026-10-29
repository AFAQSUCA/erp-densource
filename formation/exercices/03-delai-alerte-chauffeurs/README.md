# Exercice 3 — Un délai d'alerte propre aux chauffeurs

**Semaine 5** · environ 3 heures · après le chapitre 5 (paramètres) et le chapitre 20 (écrans chauffeurs)

## La demande

« Renouveler un permis prend plus de temps qu'une assurance. On veut être prévenus **plus tôt pour les permis et
les visites médicales** que pour les documents des camions, et pouvoir régler ce délai à l'écran. »

## Ce qui doit marcher

- Un nouveau paramètre `delai_alerte_chauffeurs_jours` : 30 jours par défaut, entre 1 et 365, modifiable par
  l'ADMIN et la DIRECTION sur l'écran « Paramètres ».
- Une fonction `services.delai_alerte_chauffeurs(jours=None)`, sur le modèle de `delai_alerte`.
- Les permis et visites médicales suivent ce délai ; les documents des camions gardent le leur.
- La notification quotidienne et le centre d'alertes du tableau de bord aussi.

## Où regarder

- `apps/parametres/` : `models.py`, `services.py` (`CHAMPS`, `delai_alerte`), `views.py` (`SECTIONS`).
- Cherchez qui lit le délai : `grep -rn "delai_alerte" apps`. Lesquelles de ces lignes parlent des chauffeurs ?

## Étapes conseillées

1. Copiez `test_exercice_03.py` dans `apps/parametres/tests/` et lancez-le : 5 tests échouent.
2. Le paramètre (modèle, `CHAMPS`, migration), puis la fonction, puis chaque lecture côté chauffeurs.
3. Lancez toute la suite : quels tests réglaient « le » délai en s'attendant à ce qu'il vaille aussi pour les
   chauffeurs ?

## Indice

Ne changez **pas** le délai des camions : dans le test, un permis et une assurance qui expirent tous deux dans
45 jours ne doivent pas réagir pareil.

## Correction

`correction.md`, puis `correction.diff`.
