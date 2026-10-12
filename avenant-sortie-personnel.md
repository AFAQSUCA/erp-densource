# Avenant — Sortie du personnel (licenciement, démission…)

Complète le cahier des charges, §3 Module 1, ligne 50 : « **RH** : gestion complète employés (embauche,
**licenciement**, contrats) ». L'embauche existait ; aucun départ ne pouvait être enregistré : un employé parti
gardait une fiche active, un compte qui se connectait et, s'il était chauffeur, restait affectable (audit M1-22).

## Décisions de l'entreprise (12/10/2026)

| Question | Décision |
|---|---|
| Motifs | Démission, Licenciement, Fin de contrat (CDD, stage), Départ à la retraite, Décès, Autre (commentaire obligatoire) |
| Missions, congés, équipe du partant | **Réglés automatiquement** : congés à venir annulés, équipe rattachée au supérieur du partant ; seule une mission **en cours** bloque |
| Mission « Affectée » pas encore partie | Chauffeur sortant : la mission repasse « Planifiée » (camion libéré) et le Parc Auto est prévenu pour la réaffecter. Copilote sortant : il est seulement retiré de la mission |
| Date de sortie à venir (préavis) | **Oui** : rien ne change avant ; les effets s'appliquent à la date (tâche quotidienne) |
| Annulation (erreur, réintégration) | **Oui**, avec motif tracé ; le compte et les fiches se réactivent à la main |

## Règles

- **Qui** : RH, DIRECTION, ADMIN (mêmes droits que la modification d'une fiche personnel) ; jamais pour sa propre
  fiche. Chaque sortie et chaque annulation est au journal d'audit (module RH).
- **Une seule sortie active** par employé ; la date de sortie (dernier jour) ne précède pas l'embauche.
- **À la date de sortie**, en une seule opération (tout ou rien) :
  1. refus si l'employé conduit ou accompagne une mission partie ; la tâche du jour réessaie chaque jour et la RH
     est prévenue une fois ;
  2. demandes de congé en attente refusées, congés approuvés pas encore commencés annulés (motif « Sortie du
     personnel le … ») ; un congé déjà commencé suit son cours ;
  3. équipe rattachée au supérieur du partant (sans supérieur s'il n'en avait pas) ;
  4. compte utilisateur désactivé (un compte superutilisateur est signalé, il se désactive en ligne de commande) ;
  5. fiches chauffeur et copilote « Inactif » ; missions affectées libérées comme décidé ci-dessus.
- **Annulation** : l'employé redevient « présent » ; ses accès, ses fiches chauffeur ou copilote et ses congés
  ne sont pas rétablis automatiquement (décision consciente : pas d'accès rendu sans geste humain).
- **Listes** : le personnel sorti n'apparaît plus par défaut (filtre « Présents / Sortis / Tous »), n'est plus
  compté dans l'effectif ni proposé comme supérieur.

## Implémentation

`apps/hr/sorties.py` (modèle `SortiePersonnel`), signaux `hr.signals.sortie_a_verifier` et `sortie_appliquee`,
récepteurs `apps/missions/receivers.py` et `apps/drivers/signals.py`, tâche
`notifications.taches.appliquer_sorties_du_jour`. Détails : `apps/hr/README.md`.
