# Avenant — Comptabilité en partie double (SYSCOHADA révisé)

Complète cahier-des-charges.md : la seule exigence déjà écrite sur ce sujet est « Une facture
émise génère la créance client et l'écriture comptable équilibrée » (cahier-des-charges.md:340).
Tout le reste (plan comptable, journaux, grand livre, bilan, compte de résultat, exercice
comptable et clôture) est un chantier neuf, demandé par l'entreprise : la comptabilité légale est
aujourd'hui tenue par un cabinet externe, mais l'entreprise compte l'internaliser dans quelques
mois — l'ERP doit devenir la source de vérité comptable, pas un simple export.

Référentiel retenu : **SYSCOHADA révisé, système normal** (pas le système minimal de trésorerie :
`billing.Facture` gère déjà des créances clients en droits constatés, incompatible avec l'esprit
du SMT ; un bilan et un compte de résultat au sens SYSCOHADA sont explicitement demandés).

Comme les règles R1-R8 de `avenant-separation-des-taches.md`, chaque phase est livrée par lot
indépendant, testée (≥ 70 % sur les services), documentée, fusionnée séparément.

| Phase | Contenu | Statut |
|---|---|---|
| P1 | Fondations : plan comptable, moteur d'écritures, écriture de facture validée | **✅ Ce lot** — voir ci-dessous |
| P2 | Encaissements (règlements clients) | À livrer |
| P3 | Dépenses automatiques du parc auto/missions (carburant, pièces, main-d'œuvre, frais de mission, ordre de décaissement) | À livrer |
| P4 | Saisie manuelle (mouvements de trésorerie, opérations diverses) — brouillon → validation DIRECTION | À livrer |
| P5 | Exercice comptable et clôture (DIRECTION, contrôle strict) | À livrer |
| P6 | Rapports : grand livre, balance, bilan, compte de résultat | À livrer |

## P1 — Fondations : plan comptable, moteur d'écritures, écriture de facture

**Position dans le graphe de dépendances** (architecture.md) : nouvelle app `accounting`, dépend
de `billing` (lit `Facture`, `CompteTresorerie`) ; aucune app existante ne dépend d'`accounting`
pour l'instant (la Phase 6 y ajoutera `dashboard`).

**Modèles** (`apps/accounting/models.py`) :
- `Compte` : plan comptable (numéro, libellé, nature ACTIF/PASSIF/CHARGE/PRODUIT, actif). Table de
  référence, jamais soft-supprimée (comme `core.CompteurNumero`).
- `EcritureComptable` (`BaseModel`) : en-tête (numéro `JOURNAL-AAAA-XXXX` via
  `core.services.prochain_numero`, journal, date, libellé, pièce justificative, origine générique
  `(origine, origine_id)` pour l'idempotence, statut BROUILLON/VALIDEE). Une écriture `VALIDEE` ne
  se modifie ni ne se supprime : seule une contre-passation la corrige (non livrée en P1).
- `LigneEcriture` : ligne débit ou crédit, append-only (comme `inventory.MouvementStock`), montant
  strictement positif, rattachement générique optionnel à un tiers (`tiers_type`/`tiers_id`, ex.
  un client pour le compte 411).
- 5 journaux auxiliaires SYSCOHADA (`Journal`) : Achats (ACH), Ventes (VTE), Banque (BQ), Caisse
  (CAI), Opérations diverses (OD). Seul VTE est utilisé en P1.

**Moteur** (`apps/accounting/services.py::passer_ecriture`) : garantit lui-même l'équilibre
(jamais l'appelant) — au moins 2 lignes, montants strictement positifs, comptes existants et
actifs, total débit == total crédit (sinon `EcritureNonEquilibree`). Idempotent par
`(origine, origine_id)` : rejouer le même événement source renvoie l'écriture déjà comptabilisée.
`@transaction.atomic`, `statut=VALIDEE` directement (aucune écriture automatique ne passe par un
brouillon).

**Déclencheur** : `apps.billing.signals.facture_a_comptabiliser`, ajouté à côté de
`facture_validee` — émis en `send()` **brut** (pas `emettre()`/`send_robust`, contrairement aux
signaux existants de `billing`) : une écriture qui échoue à s'équilibrer annule la validation de
la facture plutôt que d'être silencieusement absente du grand livre. Souscrit dans
`apps/accounting/receivers.py`, qui appelle `services.comptabiliser_facture_validee(facture)` :
débite le client (411, montant TTC, rattaché au tiers), crédite les ventes (706, montant HT) et la
TVA collectée (4433, si le taux n'est pas nul).

**Permissions** (`apps/accounting/permissions.py`) : `CONSULTATION` (ADMIN, DIRECTION, FINANCES,
RH) — lecture seule, aucune saisie manuelle avant la P4. Cohérent avec le reste du projet : la RH
fait tout ce que fait la FINANCES, la DIRECTION a la même largeur que l'ADMIN.

**Audit** : `Compte`, `EcritureComptable`, `LigneEcriture` journalisés (module `COMPTABILITE`).

**Écrans** : aucun écran dédié en P1 (inspection via l'admin Django) — les écrans de grand
livre/balance/bilan viennent avec la P6, quand il y aura assez de lots comptabilisés pour qu'un
écran soit utile.

**Reprise de l'historique** : `python manage.py comptabiliser_historique_factures [--depuis
AAAA-MM-JJ] [--dry-run]`, même principe que
`finance.comptabiliser_historique_parc_auto` — comptabilise les factures déjà validées avant la
mise en service de ce lot.

**Plan comptable de départ** (`migrations/0002_plan_comptable_seed.py`) : liste de travail
(Clients 411, Ventes transport 706, TVA collectée 4433, Banque/Caisse/Mobile Money 521/571/5219,
Carburant 6051, Pièces 6058, Entretien 6241, Frais de mission 6281, Frais bancaires 631, Charges
diverses 658, Capital 101, Compte de l'exploitant 108, Résultat 120, Fournisseurs 401, TVA
déductible 4452) — **à valider par un expert-comptable avant mise en production** ; aucun cabinet
externe n'a été consulté à ce stade. Seuls 411, 706, 4433 et les 3 comptes de trésorerie sont
mobilisés par le code de la P1, le reste est seedé pour éviter une migration de données fragmentée
aux phases suivantes.

**Limites connues (assumées pour ce lot)** :
- Les pièces détachées restent comptabilisées en charge à l'achat (comportement déjà en place
  côté `finance.receivers`, cf. « Les pièces sont comptées à l'achat, pas à leur sortie de stock
  ») plutôt qu'en vraie entrée de stock (classe 3) suivie d'une sortie en charge — décision
  confirmée avec l'entreprise, pas une omission.
- Aucune récupération de TVA déductible réelle : `billing.Depense` n'a pas de champ HT/TVA
  séparé, les charges seront comptabilisées TTC (le compte 4452 reste à 0 tant que ce n'est pas
  traité).
- Les comptes Mobile Money des 3 opérateurs (Wave, Orange Money, MTN) restent fusionnés en un
  seul compte 5219, comme `billing.CompteTresorerie.MOBILE_MONEY` aujourd'hui.
- Classes 2 (immobilisations, camions) et 8 (hors activités ordinaires) hors périmètre : aucun
  événement de l'ERP ne produit aujourd'hui un achat d'immobilisation ou une charge exceptionnelle.
- Pas d'exercice comptable ni de clôture en P1 (arrive en P5) : aucune écriture n'est encore
  verrouillée par période.

**Implémentation** : `apps.accounting.services.passer_ecriture`,
`apps.accounting.services.comptabiliser_facture_validee`, `apps.accounting.receivers`,
signal `apps.billing.signals.facture_a_comptabiliser`. Détails : `apps/accounting/README.md`.
