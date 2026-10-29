# Correction — Exercice 3

## Le paramètre

| Fichier | Changement |
|---|---|
| `apps/parametres/models.py` | champ `delai_alerte_chauffeurs_jours` (défaut 30, bornes 1-365) ; l'aide du champ des camions est précisée |
| migration `0002_delai_alerte_chauffeurs.py` | générée |
| `apps/parametres/services.py` | le champ ajouté à `CHAMPS` (sinon `modifier_parametres` le refuse comme « inconnu », et le formulaire ne l'affiche pas) ; nouvelle fonction `delai_alerte_chauffeurs` |
| `apps/parametres/views.py` | le champ dans la section « Alertes d'expiration » de l'écran |

## Les lectures côté chauffeurs (6 lignes)

`delai_alerte` devient `delai_alerte_chauffeurs` dans : `apps/drivers/services.py` (2 fois), `apps/drivers/views.py`
(2 fois), `apps/notifications/taches.py` (`alerter_echeances_chauffeurs`), `apps/dashboard/services.py`
(`_alertes_chauffeurs`). Les lectures des camions ne bougent pas.

## L'effet en cascade : 4 tests

Quatre tests réglaient `delai_alerte_jours=60` en attendant un effet sur les chauffeurs (tableau de bord,
notifications, fiche et liste des chauffeurs). La règle a changé : ils règlent maintenant
`delai_alerte_chauffeurs_jours` (et les deux délais quand ils vérifient camions et chauffeurs ensemble).

**Vérification** : les 5 tests de l'exercice passent, et la suite complète aussi (3 422 tests).
