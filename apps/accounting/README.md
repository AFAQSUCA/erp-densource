# accounting

Rôle : comptabilité en partie double (SYSCOHADA révisé) — cahier-des-charges.md:340. Dépend de
`billing` et `finance` (architecture.md). Nouveau chantier (avenant-comptabilite-syscohada.md),
livré par lot indépendant comme R1-R8 (`avenant-separation-des-taches.md`).

**Phase 1** : fondations — plan comptable, moteur d'écritures toujours équilibrées, écriture
générée automatiquement à la validation d'une facture (« une facture émise génère la créance
client et l'écriture comptable équilibrée », cahier-des-charges.md:340).

**Phase 2** : encaissements — écriture générée automatiquement à l'enregistrement d'un règlement
(débit trésorerie selon le mode de paiement, crédit client).

**Phase 3** : dépenses automatiques du parc auto/missions — écriture générée automatiquement pour
un plein, un achat de pièces, une main-d'œuvre d'OR, un frais de mission confirmé ou un ordre de
décaissement exécuté ; reclassement de trésorerie quand la Finance corrige après coup le mode
d'une dépense provisoire.

**Phase 4 (ce lot)** : saisie manuelle — écriture générée automatiquement pour un mouvement
manuel de trésorerie (`finance.MouvementManuel`, nouveau champ `nature` pour déduire le compte de
contrepartie) ; premier écran web de l'app, pour saisir à la main une écriture d'opérations
diverses (brouillon → ajout/retrait de lignes → validation par la DIRECTION, cycle calqué sur
`Facture`). Les phases suivantes (exercice comptable et clôture, grand livre/balance/bilan/compte
de résultat) ne sont pas encore livrées — voir `avenant-comptabilite-syscohada.md`.

Entités : `Compte` (plan comptable, table de référence), `EcritureComptable` (en-tête, numérotée
par journal via `core.services.prochain_numero` — vide tant qu'elle est en `BROUILLON`),
`LigneEcriture` (ligne débit/crédit, append-only une fois l'écriture validée, modifiable tant
qu'elle est en brouillon). Une écriture validée ne se modifie ni ne se supprime : seule une
contre-passation (non livrée) la corrige.

Service central : `services.passer_ecriture(...)` — garantit lui-même l'équilibre (débit ==
crédit) et l'idempotence par `(origine, origine_id)`, jamais l'appelant ; toujours `VALIDEE`
directement (usage automatique). Chaque événement automatique a sa fonction dédiée qui construit
les lignes puis appelle `passer_ecriture` : `comptabiliser_facture_validee`,
`comptabiliser_un_reglement`, `comptabiliser_une_depense_automatique`, `reclasser_mode_depense`
(sans `origine`/`origine_id`, voir « Limite connue » P3), `comptabiliser_un_mouvement_manuel`.

La saisie manuelle passe par un cycle brouillon/validation distinct :
`creer_ecriture_manuelle` → `ajouter_ligne_manuelle`/`supprimer_ligne_manuelle` (librement, tant
que `BROUILLON`) → `valider_ecriture_manuelle` (DIRECTION, contrôle **strict**, vérifie
l'équilibre et attribue le numéro) ou `abandonner_ecriture_manuelle` (soft delete du brouillon).

Déclenchement (automatique) : signaux `billing.signals.facture_a_comptabiliser`,
`reglement_a_comptabiliser`, `depense_a_comptabiliser`, `depense_mode_a_reclasser`, et
`finance.signals.mouvement_a_comptabiliser` — tous émis en `send()` **brut** (pas
`emettre()`/`send_robust`) : une écriture qui échoue à s'équilibrer annule l'opération d'origine
plutôt que de laisser un grand livre incomplet.

Reprise de l'historique (événements déjà enregistrés avant la mise en service de chaque lot) :
`python manage.py comptabiliser_historique_factures`, `comptabiliser_historique_reglements`,
`comptabiliser_historique_depenses` (chacune avec `[--depuis AAAA-MM-JJ] [--dry-run]`).

Accès : `permissions.CONSULTATION` (ADMIN, DIRECTION, FINANCES, RH, lecture) ; `SAISIE_OD` (mêmes
rôles, opérations diverses) ; `VALIDATION_OD` (DIRECTION seule, strict). Écran :
`/comptabilite/operations-diverses/` (liste, création, fiche avec ajout/retrait de ligne,
validation, abandon) — le seul écran du chantier pour l'instant ; les écrans de grand
livre/balance/bilan viennent avec la Phase 6.

**Plan comptable de départ** (`migrations/0002_plan_comptable_seed.py`) : liste de travail, à
valider par un expert-comptable avant mise en production — aucun plan comptable existant côté
cabinet externe n'a été fourni à ce stade.
