# Exercice 5 — La Finance et la RH consultent les missions

**Semaine 7** · environ 3 heures · après le chapitre 23 (écrans des missions) et le chapitre 32 (API)

## La demande

« La Finance doit voir les missions pour suivre ce qui sera facturé. **Consultation seulement** : ni création, ni
codes secrets. »

## Ce qui doit marcher

- La FINANCES **et la RH** ouvrent la liste et la fiche des missions, et l'API `api/v1/missions/`.
- Ni l'une ni l'autre ne voit les codes secrets, ni ne peut créer une mission.
- Le chauffeur reste sans accès.

## Pourquoi la RH aussi ?

Relisez `avenant-separation-des-taches.md` § R8 : « la RH fait tout ce que fait la FINANCES ». Une règle de
l'entreprise vous oblige à une décision que la demande ne disait pas.

## Où regarder

- `apps/missions/permissions.py` : les ensembles de rôles. Lequel décide de la consultation ? Lequel des codes ?
- Toutes les vues, l'API et la WebSocket du suivi lisent ces ensembles : il n'y a **qu'un endroit** à changer dans le
  code.

## Étapes conseillées

1. Copiez `test_exercice_05.py` dans `apps/missions/tests/` et lancez-le : 4 tests échouent.
2. Changez le droit (une ligne), relancez : tout passe.
3. Lancez **toute la suite** : une quinzaine de tests échouent. Ils vérifiaient que la Finance et la RH **n'avaient
   pas** accès. Pour chacun, décidez : faut-il remplacer le rôle testé (par le chauffeur, qui n'a toujours pas
   accès), inverser l'attente, ou la nuancer (les codes : 404 au lieu de 403) ?

## Correction

`correction.md`, puis `correction.diff`.
