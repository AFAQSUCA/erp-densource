# Avenant — 7 règles de gestion basées sur la séparation des tâches

Complète cahier-des-charges.md : celui qui demande une dépense ou fixe un prix n'est jamais
celui qui la valide. Chaque règle (R1 à R7) est livrée par lot indépendant, testée (≥ 70 % sur
les services), documentée dans le README de son app, puis fusionnée séparément.

| Règle | Contenu | Statut |
|---|---|---|
| R1 | Validation des prix et devis | Fusionnée dans R5 (seuil DIRECTION à 500 000 FCFA TTC) |
| R2 | Dépenses du parc auto (pré-approbation + enveloppe) | À venir (lot 5) |
| R3 | Modification d'une mission | En attente de fusion (PR #12, branche `feat/reprise-manuelle-et-modification-mission`) |
| R4 | Prévision de trésorerie des missions | **Ce lot** — voir ci-dessous |
| R5 | Facture proforma (devis) | En attente de fusion (PR #14, branche `feat/proforma-devis-r5-r6`) |
| R6 | Mission créée depuis une proforma acceptée | En attente de fusion (PR #14, branche `feat/proforma-devis-r5-r6`) |
| R7 | Congés : 26 jours ouvrés + report | En attente de fusion (PR #13, branche `feat/conges-26-jours-ouvres-et-report`) |

## R4 — Prévision de trésorerie des missions

**Séparation des tâches.** Celui qui déclare ou planifie un frais n'est jamais celui qui le valide :
le **Parc Auto** planifie une avance de route ou une dépense prévue, la **Finance** seule la confirme ;
le **chauffeur** déclare un imprévu (panne, incident) depuis l'espace mobile, le **Parc Auto** le valide
en premier, la **Finance** en second (double validation, jamais en une fois ni par l'auteur).

**Modèle** `missions.FraisMission` (`BaseModel`) :
- `mission` (FK, obligatoire), `type_frais` (`AVANCE_ROUTE` / `DEPENSE_PREVUE` / `IMPREVU` /
  `ENCAISSEMENT`), `montant`, `description`, `justificatif` (`FileField`, premier champ fichier du
  projet — obligatoire pour un imprévu, stocké sur `MEDIA_ROOT`) ;
- `statut` (`PREVU` → `CONFIRME` / `REJETE`), `motif_rejet` ;
- `chauffeur` (rempli pour un imprévu déclaré depuis le mobile), `saisi_par` (le Parc Auto qui a
  planifié une avance/dépense prévue) ;
- `valide_parcauto_par`/`date_validation_parcauto`, `valide_finances_par`/`date_validation_finances`.

**État et validation** (`missions.terrain`) :
- **Avance de route** / **dépense prévue** : `planifier_frais` (Parc Auto) → `PREVU` →
  `valider_finances` (Finance seule) → `CONFIRME`.
- **Imprévu** : `declarer_imprevu` (chauffeur, preuve obligatoire) → `PREVU` → `valider_parcauto`
  (Parc Auto, première validation, reste `PREVU`) → `valider_finances` (Finance, refuse tant que le
  Parc Auto n'est pas passé) → `CONFIRME`.
- **Encaissement** : `creer_encaissement`, créé directement `CONFIRME` — jamais de validation, jamais
  saisi à la main (reflet automatique d'un règlement, voir plus bas).
- `rejeter` : le Parc Auto tant qu'un imprévu attend encore sa validation, la Finance dans tous les
  autres cas (motif obligatoire).
- Contrôle **strict** (`acteur.role`, jamais `role_effectif`) : ni l'ADMIN ni un superutilisateur ne
  valident à la place du Parc Auto ou de la Finance — même logique que la validation d'une facture.

**Seule une ligne `CONFIRME` représente un mouvement de trésorerie réel.** `missions` et `billing`
s'ignorent l'un l'autre (graphe de dépendance, architecture.md:95-163 : `missions` est au-dessus de
`billing`/`finance`, il ne doit rien en importer) — c'est `finance.receivers`, seule app en dessous des
deux, qui relie :
- `missions.signals.frais_mission_confirme` (avance/dépense prévue/imprévu confirmé, `send` non
  protégé comme `garage.or_cloture` : si la dépense ne peut pas s'écrire, la confirmation est annulée)
  → `billing.comptabiliser_depense_automatique` (nouvelle catégorie `FRAIS_MISSION`, liée à la mission) ;
- `billing.signals.reglement_enregistre` (nouveau signal, `send_robust` : un échec ici ne bloque
  jamais un règlement) → `missions.terrain.creer_encaissement` (aucune dépense ni règlement
  supplémentaire, seulement le reflet pour la vue « Frais de mission »).

**Déclencheur** : signal `mission_affectee` (nouveau, émis par `affecter_mission`) → notifie la
FINANCES (mouvement de caisse probable). Notifications supplémentaires : imprévu déclaré → Parc Auto ;
imprévu validé par le Parc Auto → Finance ; ligne rejetée → son auteur (catégorie `FRAIS_MISSION`).

**Permissions** (`missions.permissions`) : `FRAIS_CONSULTATION` (ADMIN, DIRECTION, PARCAUTO, FINANCES —
écran séparé de la fiche mission, le chargé clientèle n'y a pas accès, comme il ne voit pas le prix
convenu côté chauffeur) ; `FRAIS_SAISIE_PREVISION` (ADMIN, PARCAUTO) ; `FRAIS_VALIDATION_PARCAUTO`
(PARCAUTO seul) ; `FRAIS_VALIDATION_FINANCES` (FINANCES seule).

**Écrans** : `/missions/frais/` (lignes en attente, toutes missions), `/missions/<id>/frais/`
(planification, validation, rejet), `/missions/<id>/frais/imprimer/` (rapport de mission : lignes et
totaux). Côté mobile (`/chauffeur/imprevu/` et `POST /api/v1/mobile/imprevus/`) : formulaire tactile
avec upload de preuve, mêmes règles que le signalement d'un incident (mission du chauffeur uniquement).

**Effet de bord découvert en cours de route** : `audit.registry._snapshot` ne savait pas sérialiser un
`FileField` (`FieldFile` n'est pas JSON-sérialisable) — premier modèle du projet à en avoir un. Corrigé
une fois pour toutes (`_valeur()` normalise en son chemin, ou une chaîne vide sans fichier), avant que
`FraisMission` ne soit audité.

**Limite connue** : une mission créée par R6 (proforma acceptée) reste modifiable comme une autre une
fois des frais confirmés dessus (R3 ne verrouille pas encore son prix dans ce cas) ; à reconsidérer
quand R3 et R5/R6 seront fusionnées ensemble.
