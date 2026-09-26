# accounting

Rôle : comptabilité en partie double (SYSCOHADA révisé) — cahier-des-charges.md:340. Dépend de
`billing` (architecture.md). Nouveau chantier (avenant-comptabilite-syscohada.md), livré par lot
indépendant comme R1-R8 (`avenant-separation-des-taches.md`).

**Phase 1 (ce lot)** : fondations — plan comptable, moteur d'écritures toujours équilibrées,
écriture générée automatiquement à la validation d'une facture (« une facture émise génère la
créance client et l'écriture comptable équilibrée », cahier-des-charges.md:340). Les phases
suivantes (encaissements, dépenses automatiques du parc auto/missions, saisie manuelle, exercice
comptable et clôture, grand livre/balance/bilan/compte de résultat) ne sont pas encore livrées —
voir `avenant-comptabilite-syscohada.md`.

Entités : `Compte` (plan comptable, table de référence), `EcritureComptable` (en-tête, numérotée
par journal via `core.services.prochain_numero`), `LigneEcriture` (ligne débit/crédit,
append-only). Une écriture validée ne se modifie ni ne se supprime : seule une contre-passation
(non livrée) la corrige.

Service central : `services.passer_ecriture(...)` — garantit lui-même l'équilibre (débit ==
crédit) et l'idempotence par `(origine, origine_id)`, jamais l'appelant. `services.comptabiliser_facture_validee(facture)`
construit les lignes d'une facture (débit Clients TTC, crédit Ventes HT + TVA collectée si
taux > 0) et appelle `passer_ecriture`.

Déclenchement : signal `billing.signals.facture_a_comptabiliser`, émis en `send()` **brut** (pas
`emettre()`/`send_robust`) par `billing.services.valider()` — une écriture qui échoue à
s'équilibrer annule la validation de la facture plutôt que de laisser un grand livre incomplet.

Reprise de l'historique (factures déjà validées avant la mise en service de ce lot) :
`python manage.py comptabiliser_historique_factures [--depuis AAAA-MM-JJ] [--dry-run]`.

Accès : `permissions.CONSULTATION` (ADMIN, DIRECTION, FINANCES, RH) — lecture seule en Phase 1,
pas encore d'écran dédié (inspection via l'admin Django ; les écrans de grand livre/balance
viennent avec la Phase 6 du chantier).

**Plan comptable de départ** (`migrations/0002_plan_comptable_seed.py`) : liste de travail, à
valider par un expert-comptable avant mise en production — aucun plan comptable existant côté
cabinet externe n'a été fourni à ce stade.
