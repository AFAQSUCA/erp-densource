# Correction — Exercice 5

## Le code : une ligne

`apps/missions/permissions.py` : `Role.FINANCES` et `Role.RH` ajoutés à `CONSULTATION`, avec un commentaire qui
explique pourquoi. `VOIR_CODES` et `CREATION` ne bougent pas : ce sont des ensembles **indépendants**, voulus ainsi
justement pour qu'élargir la consultation n'ouvre pas les codes.

## Les tests : une quinzaine, et c'est normal

Ces tests décrivaient l'ancienne règle « la Finance et la RH n'ont pas accès aux missions ». Chacun est réécrit
selon ce qu'il protégeait vraiment :

| Ce que le test protégeait | Nouvelle version |
|---|---|
| « un rôle sans droit reçoit une page 403 » (accueil, impression, liste, menu) | il prend le **chauffeur**, qui n'a toujours pas accès, et le menu de la Finance montre désormais « Missions » |
| « seuls ceux qui consultent les missions voient le lien ou la section » (congés, fiche client) | la RH voit maintenant le lien ; le contre-exemple devient le chauffeur |
| « les autres rôles n'ont pas le PDF ni le QR des codes » | le chauffeur reçoit toujours 403 ; la Finance et la RH reçoivent **404** : elles ouvrent la mission, mais ses codes ne leur sont jamais montrés |
| « la WebSocket du suivi refuse les autres rôles » | la Finance et la RH passent dans la liste des rôles acceptés |
| les droits de chaque ressource de l'API | `mission-list` ajoute la Finance et la RH |

**À retenir** : un test qui échoue après un changement de règle n'est pas à « faire passer » n'importe comment.
Il faut comprendre ce qu'il protégeait et garder cette protection.

**Vérification** : les 7 tests de l'exercice passent, et la suite complète aussi (3 422 tests).
