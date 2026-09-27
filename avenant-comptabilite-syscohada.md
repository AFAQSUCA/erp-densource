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
| P1 | Fondations : plan comptable, moteur d'écritures, écriture de facture validée | ✅ Fusionnée |
| P2 | Encaissements (règlements clients) | ✅ Fusionnée |
| P3 | Dépenses automatiques du parc auto/missions (carburant, pièces, main-d'œuvre, frais de mission, ordre de décaissement) | ✅ Fusionnée |
| P4 | Saisie manuelle (mouvements de trésorerie, opérations diverses) — brouillon → validation DIRECTION | ✅ Fusionnée |
| P5 | Exercice comptable et clôture (DIRECTION, contrôle strict) | ✅ Fusionnée |
| P6 | Rapports : grand livre, balance, bilan, compte de résultat | **✅ Ce lot** — voir ci-dessous |

## P1 — Fondations : plan comptable, moteur d'écritures, écriture de facture

**Position dans le graphe de dépendances** (architecture.md) : nouvelle app `accounting`, dépend
de `billing` (lit `Facture`, `CompteTresorerie`) ; aucune autre app ne dépend d'`accounting` — les
rapports de la P6 restent des écrans internes à l'app, aucune intégration au `dashboard`.

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

## P2 — Encaissements (règlements clients)

**Aucun nouveau modèle** : réutilise le moteur et le plan comptable de la P1 tels quels.

**Service** (`apps/accounting/services.py::comptabiliser_un_reglement`) : débite le compte de
trésorerie déduit du mode de paiement du règlement (`billing.models.COMPTE_DU_MODE` puis
`constants.COMPTE_TRESORERIE_VERS_COMPTE` — banque 521, caisse 571, mobile money 5219), crédite
le client (411, rattaché au tiers) — solde la créance. Journal déduit du même compte de
trésorerie (`constants.COMPTE_TRESORERIE_VERS_JOURNAL`) : Banque (BQ) ou Caisse (CAI) ; le mobile
money, dématérialisé, est rattaché à la Banque faute de journal auxiliaire dédié dans les 5
journaux SYSCOHADA standards.

**Déclencheur** : `apps.billing.signals.reglement_a_comptabiliser`, ajouté à côté de
`reglement_enregistre` — même principe que `facture_a_comptabiliser` (P1) : émis en `send()`
**brut**, un échec d'équilibrage annule l'enregistrement du règlement plutôt que de laisser un
encaissement non tracé.

**Permissions, audit, écrans** : inchangés (voir P1) — aucune nouvelle app-permission, aucun
nouvel écran.

**Reprise de l'historique** : `python manage.py comptabiliser_historique_reglements [--depuis
AAAA-MM-JJ] [--dry-run]`, même gabarit que `comptabiliser_historique_factures` (P1).

**Limite connue** : l'annulation d'un règlement (`billing.services.annuler_reglement`) n'émet
aucun signal et ne génère aucune contre-passation — l'écriture d'origine reste en l'état,
orpheline de son règlement annulé. La contre-passation d'une écriture arrive avec une phase
future, une fois le mécanisme de correction (par écriture inverse plutôt que par édition) posé
pour l'ensemble du chantier plutôt que traité au cas par cas.

**Implémentation** : `apps.accounting.services.comptabiliser_un_reglement`,
`apps.accounting.receivers.comptabiliser_un_reglement_recu`, signal
`apps.billing.signals.reglement_a_comptabiliser`. Détails : `apps/accounting/README.md`.

## P3 — Dépenses automatiques du parc auto/missions + reclassement de mode

**Aucun nouveau modèle** : réutilise le moteur et le plan comptable de la P1 tels quels. Les 5
origines (`OrigineDepense` : PLEIN, ACHAT_STOCK, MAIN_OEUVRE_OR, FRAIS_MISSION,
ORDRE_DECAISSEMENT) convergent toutes vers le même point d'entrée, déjà en place :
`billing.services.comptabiliser_depense_automatique` — un seul récepteur suffit donc, pas cinq.
Seules 4 catégories sont concernées (`billing.models.CATEGORIES_AUTOMATIQUES` : CARBURANT,
PIECES, MAINTENANCE, FRAIS_MISSION — vérifié que `DemandeDepense.categorie`, pour un ordre de
décaissement manuel, est lui-même restreint à `CARBURANT`/`PIECES`/`MAINTENANCE` par
`finance.demandes._exiger_categorie_automatique`, jamais `FRAIS_ADMIN`/`PEAGES`/`ENTRETIEN`/`AUTRE`) ;
ces 4 catégories manuelles arrivent avec la P4.

**Service** (`apps/accounting/services.py::comptabiliser_une_depense_automatique`) : débite la
charge selon la catégorie (`constants.CATEGORIE_DEPENSE_VERS_COMPTE` : Carburant 6051, Pièces
6058, Main-d'œuvre 6241, Frais de mission 6281), crédite la trésorerie selon le mode de paiement
(même mapping que la P2). Pour 4 des 5 origines (tout sauf l'ordre de décaissement), le mode est
**provisoire** : `comptabiliser_depense_automatique` par défaut sur Espèces (Caisse), corrigé
ensuite par la Finance via `billing.services.changer_mode_depense`. L'ordre de décaissement, lui,
connaît son mode réel dès l'exécution (`finance.demandes.executer_ordre` le passe directement) :
pas de provisoire pour cette origine.

**Reclassement de mode** (`apps/accounting/services.py::reclasser_mode_depense`) : quand la
Finance corrige le mode d'une dépense provisoire, une écriture de reclassement (journal
Opérations diverses) débite le nouveau compte de trésorerie et crédite l'ancien — jamais d'édition
de l'écriture d'origine (append-only). Aucune écriture si l'ancien et le nouveau mode partagent le
même compte de trésorerie (ex. virement → chèque, tous deux Banque).

**Déclencheurs** :
- `apps.billing.signals.depense_a_comptabiliser`, émis dans
  `comptabiliser_depense_automatique` **uniquement à la création réelle** de la `Depense` (pas
  quand le `get_or_create` retombe sur l'existante) — évite un double signal au rejeu d'une source.
- `apps.billing.signals.depense_mode_a_reclasser`, émis par `changer_mode_depense` (désormais
  `@transaction.atomic`, ne l'était pas avant ce lot) **uniquement si le mode change vraiment**.

Les deux en `send()` **brut** : un échec d'équilibrage annule l'opération d'origine (la
comptabilisation de la dépense, ou sa correction de mode).

**Permissions, audit, écrans** : inchangés (voir P1).

**Reprise de l'historique** : `python manage.py comptabiliser_historique_depenses [--depuis
AAAA-MM-JJ] [--dry-run]`, même gabarit que les commandes des P1/P2 — ne reprend que les dépenses
automatiques (`Depense.est_automatique`), pas la saisie manuelle (P4).

**Limite connue** : le reclassement de mode n'est pas idempotent (pas d'`origine`/`origine_id` sur
son écriture) — une correction rejouée deux fois (double clic, retry réseau) créerait deux
reclassements. Accepté pour cette phase : c'est une action manuelle rare de la Finance, pas un
événement automatique rejouable par construction comme les 3 autres signaux.

**Implémentation** : `apps.accounting.services.comptabiliser_une_depense_automatique`,
`apps.accounting.services.reclasser_mode_depense`, `apps.accounting.receivers`, signaux
`apps.billing.signals.depense_a_comptabiliser` et `depense_mode_a_reclasser`. Détails :
`apps/accounting/README.md`.

## P4 — Saisie manuelle (mouvements de trésorerie, opérations diverses)

Deux volets tranchés avec l'utilisateur avant implémentation (aucune décision unilatérale sur une
règle métier ambiguë) :

**1. `finance.MouvementManuel` gagne un champ structuré.** Contrairement aux événements des P1-P3,
un mouvement manuel (solde d'ouverture, apport, retrait, frais bancaires…) n'avait qu'un libellé
libre : impossible d'en déduire automatiquement le compte de contrepartie. Nouveau champ
`nature` (`finance.models.NatureMouvement` : SOLDE_OUVERTURE, APPORT, RETRAIT, FRAIS_BANCAIRE,
AUTRE — migration `finance/migrations/0003_mouvementmanuel_nature.py`, défaut `AUTRE` pour les
lignes déjà existantes). Mapping vers le plan comptable
(`accounting.constants.NATURE_MOUVEMENT_VERS_COMPTE`) : SOLDE_OUVERTURE/APPORT → 101000 Capital,
RETRAIT → 108000 Compte de l'exploitant, FRAIS_BANCAIRE → 631000, AUTRE → 658000.

**Service** (`apps/accounting/services.py::comptabiliser_un_mouvement_manuel`) : une entrée débite
la trésorerie et crédite la contrepartie ; une sortie fait l'inverse. Déclencheur :
`apps.finance.signals.mouvement_a_comptabiliser` (nouveau, `send()` brut), émis par
`finance.services.enregistrer_mouvement`. **Ce signal vit dans `finance`, pas `billing`** :
`MouvementManuel` est un modèle `finance`, et le graphe de dépendances gagne l'arête `FIN → ACCT`
(`architecture.md`) pour que `accounting` puisse lire `finance.models.NatureMouvement`.

**Limite connue** (même principe que l'annulation d'un règlement, P2) : l'annulation d'un
mouvement (`annuler_mouvement`) n'émet aucun signal, aucune contre-passation.

**Limite de périmètre** (pas une omission) : les dépenses manuelles de `billing.Depense`
(catégories PEAGES, ENTRETIEN, FRAIS_ADMIN, AUTRE, saisies via `billing.services.enregistrer_depense`)
restent hors périmètre — l'ambiguïté sur leur compte de contrepartie (péages/entretien n'ont pas
de compte déjà seedé et vérifié) n'a pas été tranchée avec l'utilisateur pour ce lot.

**2. Écran de saisie manuelle d'opérations diverses (journal OD).** Premier écran web de l'app
`accounting` — sans lui, la saisie manuelle serait inutilisable en pratique. Cycle de vie calqué
sur celui de `Facture` : `BROUILLON` (numéro vide, lignes ajoutées/retirées librement) →
`VALIDEE` (numéro attribué, verrouillée) — jamais de brouillon abandonné qui laisse un trou de
numérotation.

**Modèles** : aucun changement de schéma dans `accounting` — seul le comportement de
`EcritureComptable.delete()` et `LigneEcriture.delete()` est assoupli (suppression permise tant
que l'écriture est encore `BROUILLON`, verrouillée dès `VALIDEE`, comme documenté en P1).

**Services** (`apps/accounting/services.py`) :
- `creer_ecriture_manuelle(acteur, *, date_ecriture, libelle)` → `BROUILLON`, journal OD, pas de
  numéro.
- `ajouter_ligne_manuelle(ecriture, acteur, *, compte, sens, montant, libelle="")` /
  `supprimer_ligne_manuelle(ligne, acteur)` — uniquement sur un brouillon.
- `abandonner_ecriture_manuelle(ecriture, acteur)` — soft delete, uniquement sur un brouillon (pas
  de contre-passation nécessaire, aucun numéro n'a encore été attribué).
- `valider_ecriture_manuelle(ecriture, acteur)` — vérifie l'équilibre (au moins 2 lignes, débit ==
  crédit, la même règle que `passer_ecriture`), attribue le numéro, verrouille. **Contrôle
  strict** (`acteur.role`, jamais `role_effectif`) : réservé à la DIRECTION, comme
  `Facture.valider` — ni l'ADMIN ni un superutilisateur ne valident à sa place.

**Permissions** (`apps/accounting/permissions.py`) : `SAISIE_OD` (ADMIN, DIRECTION, FINANCES, RH —
créer, ajouter/retirer une ligne, abandonner) ; `VALIDATION_OD` (DIRECTION seule, strict).

**Écrans** (`apps/accounting/views.py`, `urls.py`, `templates/accounting/`, montés sous
`/comptabilite/`) : liste des écritures OD, formulaire de création (date + libellé), fiche
(lignes, totaux débit/crédit, indicateur d'équilibre, formulaire d'ajout de ligne, bouton
Valider réservé à la DIRECTION sur une écriture équilibrée, bouton Abandonner). Menu :
« Opérations diverses », rôles `CONSULTATION`.

**Vérifié manuellement** (navigateur, `demo_finances`) : création d'un brouillon, ajout de deux
lignes, calcul des totaux et détection d'équilibre en direct, conformes à ce que testent les
tests automatisés.

**Implémentation** : `apps.accounting.services.creer_ecriture_manuelle` /
`ajouter_ligne_manuelle` / `supprimer_ligne_manuelle` / `valider_ecriture_manuelle` /
`abandonner_ecriture_manuelle` / `comptabiliser_un_mouvement_manuel`, `apps.accounting.views`,
`apps.accounting.permissions.SAISIE_OD` / `VALIDATION_OD`, signal
`apps.finance.signals.mouvement_a_comptabiliser`, migration
`apps/finance/migrations/0003_mouvementmanuel_nature.py`. Détails : `apps/accounting/README.md`.

## P5 — Exercice comptable et clôture

**Modèle** (`apps/accounting/models.py`) : `ExerciceComptable` (`BaseModel`) — `annee` (unique),
`date_debut`/`date_fin` (année civile par défaut : le cahier des charges ne précise pas de date de
clôture fiscale propre à l'entreprise, hypothèse à confirmer avec l'expert-comptable), `statut`
(`OUVERT`/`CLOTURE`), `cloture_par`, `date_cloture`. Auto-créé `OUVERT` au passage de la première
écriture de son année (`services.exercice_pour`, même principe que
`core.services.prochain_numero` : aucun geste explicite n'est requis pour « ouvrir » une nouvelle
année). Jamais supprimé, jamais rouvert une fois clôturé.

**Verrouillage** (`services._exiger_exercice_ouvert`) : appelé par `passer_ecriture` (écritures
automatiques), `creer_ecriture_manuelle` et `valider_ecriture_manuelle` (saisie manuelle, cette
dernière en seconde ligne de défense contre une clôture concurrente — en pratique la clôture est
déjà bloquée tant qu'un brouillon existe dans la période, voir ci-dessous). Toute date tombant
dans un exercice `CLOTURE` lève `ExerciceCloture` : l'opération d'origine est annulée, comme pour
un déséquilibre.

**Service** (`apps/accounting/services.py::cloturer_exercice`) : refusé si l'exercice est déjà
clôturé, ou s'il reste des écritures manuelles en `BROUILLON` datées dans sa période (à valider ou
abandonner d'abord — jamais clôturer une année à l'insu d'une saisie en attente). Contrôle
**strict** (`acteur.role`) : réservé à la DIRECTION, comme `Facture.valider` — jamais l'ADMIN ni
un superutilisateur à sa place.

**Permissions** (`apps/accounting/permissions.py`) : `CLOTURE_EXERCICE` (DIRECTION seule, strict).
Consultation de la liste : `CONSULTATION` (inchangé).

**Écran** (`/comptabilite/exercices/`) : liste des exercices (année, période, statut, clôturé par
qui et quand), bouton « Clôturer » visible seulement à la DIRECTION sur un exercice `OUVERT`.
Vérifié manuellement dans le navigateur (`demo_finances` : la liste s'affiche, le bouton
« Clôturer » n'apparaît pas pour ce rôle — conforme à ce que testent les tests automatisés).

**Limite connue** : une fois clôturé, un exercice ne se rouvre jamais — une correction après
clôture attendra la phase de contre-passation générale (déjà signalée comme limite connue depuis
la P1), pas un mécanisme de réouverture dédié.

**Implémentation** : `apps.accounting.models.ExerciceComptable`,
`apps.accounting.services.exercice_pour` / `cloturer_exercice`,
`apps.accounting.permissions.CLOTURE_EXERCICE`, `apps.accounting.views.ExerciceListView` /
`ExerciceCloturerView`. Détails : `apps/accounting/README.md`.

## P6 — Rapports : grand livre, balance, bilan, compte de résultat

Dernier lot de la feuille de route : aucun nouveau modèle, aucun nouveau signal — uniquement de la
lecture sur les écritures déjà comptabilisées par les P1-P5.

**Services** (`apps/accounting/services.py`) :
- `grand_livre_avec_solde(compte, *, debut=None, fin=None)` : lignes du compte triées par date,
  chacune enrichie d'un solde cumulé (débit − crédit, cumulé ligne après ligne dans l'ordre
  chronologique) — la lecture brute non enrichie (`grand_livre`, P1) reste disponible pour les
  usages internes/tests qui n'ont pas besoin du solde.
- `balance(*, debut=None, fin=None)` : agrège tous les comptes mouvementés sur la période (total
  débit, total crédit, solde débiteur ou créditeur selon lequel des deux totaux l'emporte), via
  `_agreger_par_compte`.
- `compte_de_resultat(exercice)` : produits et charges **strictement dans `[date_debut, date_fin]`
  de l'exercice** — les comptes de charge/produit sont par nature des compteurs de période, remis
  à zéro à chaque exercice.
- `bilan(exercice)` : actif et passif **cumulés depuis l'origine jusqu'à `date_fin`**, sans borne de
  date basse — contrairement au compte de résultat, les comptes de bilan (trésorerie, créances,
  capital…) portent un solde qui survit d'un exercice à l'autre.

**Limite connue (documentée dans l'écran du bilan lui-même)** : le résultat net de l'exercice est
**calculé à la volée** par `compte_de_resultat` et simplement ajouté au passif du bilan
(`total_passif_avec_resultat`) pour l'équilibrer à l'affichage — il n'existe **aucune écriture de
clôture** qui transfère réellement ce résultat dans le compte 120000 "Résultat de l'exercice" au
moment de `cloturer_exercice` (P5). Une clôture comptable complète (contre-passation des comptes de
classe 6/7 vers le 120000) est un chantier à part, non demandé pour ce lot — le bilan reste donc une
photo cohérente mais pas une écriture posée dans le grand livre.

**Permissions** : inchangées, `CONSULTATION` (voir P1) — ces 4 écrans sont uniquement de la
lecture, aucune saisie.

**Écrans** (`apps/accounting/views.py`, `forms.py`, `templates/accounting/`, montés sous
`/comptabilite/`) :
- `/comptabilite/grand-livre/` : formulaire compte (obligatoire) + période (facultative) ;
  n'affiche de tableau qu'une fois un compte choisi.
- `/comptabilite/balance/` : formulaire période (facultative) ; tableau de tous les comptes
  mouvementés avec leurs totaux et soldes, plus une ligne de total général.
- `/comptabilite/bilan/` et `/comptabilite/compte-de-resultat/` : sélecteur d'exercice (le plus
  récent par défaut, `?exercice=AAAA` pour changer), partagé par les deux écrans via
  `_RapportExerciceView`.
- Menu : « Rapports comptables » pointe vers la balance ; les 3 autres rapports se rejoignent
  depuis le même sous-menu (`_nav_rapports.html`).

**Vérifié manuellement** (navigateur, `demo_finances`) : les 4 écrans affichent des montants
cohérents entre eux sur les mêmes données (le résultat net du compte de résultat correspond
exactement à celui ajouté au passif du bilan), le filtre par compte du grand livre calcule le bon
solde cumulé, la balance totalise correctement débit/crédit.

**Implémentation** : `apps.accounting.services.grand_livre_avec_solde` / `balance` /
`compte_de_resultat` / `bilan`, `apps.accounting.forms.PeriodeForm` / `GrandLivreForm`,
`apps.accounting.views.GrandLivreView` / `BalanceView` / `BilanView` / `CompteDeResultatView`.
Détails : `apps/accounting/README.md`.

**Ceci clôt la feuille de route des 6 phases.** Les limites connues documentées phase par phase
restent ouvertes (contre-passation générale, TVA déductible réelle, dépenses manuelles hors
périmètre, clôture comptable posée dans le grand livre) : à traiter dans un futur avenant si
l'entreprise en confirme le besoin une fois la comptabilité internalisée.
