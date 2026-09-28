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

**Phase 4** : saisie manuelle — écriture générée automatiquement pour un mouvement manuel de
trésorerie (`finance.MouvementManuel`, champ `nature` pour déduire le compte de contrepartie) ;
écran de saisie manuelle d'opérations diverses (brouillon → ajout/retrait de lignes → validation
par la DIRECTION, cycle calqué sur `Facture`).

**Phase 5** : exercice comptable et clôture — un exercice (année civile) s'ouvre tout
seul à la première écriture qui le concerne ; la DIRECTION peut le clôturer (contrôle strict),
ce qui verrouille définitivement toute nouvelle écriture datée dans sa période. Refusé s'il reste
des brouillons non résolus dans la période.

**Phase 6 (ce lot, dernière de la feuille de route)** : rapports en lecture seule — grand livre
d'un compte avec solde cumulé, balance générale de tous les comptes mouvementés, bilan (cumulé
depuis l'origine) et compte de résultat (strictement borné à l'exercice choisi). Aucun nouveau
modèle ni signal : uniquement des agrégations sur les écritures déjà posées par les Phases 1-5.

Entités : `Compte` (plan comptable, table de référence), `EcritureComptable` (en-tête, numérotée
par journal via `core.services.prochain_numero` — vide tant qu'elle est en `BROUILLON`),
`LigneEcriture` (ligne débit/crédit, append-only une fois l'écriture validée, modifiable tant
qu'elle est en brouillon), `ExerciceComptable` (année, période, statut `OUVERT`/`CLOTURE`).
Une écriture validée ne se modifie ni ne se supprime : seule une contre-passation (non livrée) la
corrige. Un exercice clôturé ne se rouvre jamais.

Service central : `services.passer_ecriture(...)` — garantit lui-même l'équilibre (débit ==
crédit), l'idempotence par `(origine, origine_id)` et que l'exercice de la date n'est pas
clôturé, jamais l'appelant ; toujours `VALIDEE` directement (usage automatique). Chaque événement
automatique a sa fonction dédiée qui construit les lignes puis appelle `passer_ecriture` :
`comptabiliser_facture_validee`, `comptabiliser_un_reglement`,
`comptabiliser_une_depense_automatique` (dépenses automatiques *et* manuelles, les 8 catégories
de `billing.CategorieDepense` — `avenant-comptabilite-autonomie.md` § Lot C), `reclasser_mode_depense`
(sans `origine`/`origine_id`, voir « Limite connue » P3), `comptabiliser_un_mouvement_manuel`.

La saisie manuelle passe par un cycle brouillon/validation distinct :
`creer_ecriture_manuelle` → `ajouter_ligne_manuelle`/`supprimer_ligne_manuelle` (librement, tant
que `BROUILLON`) → `valider_ecriture_manuelle` (DIRECTION, contrôle **strict**, vérifie
l'équilibre et attribue le numéro) ou `abandonner_ecriture_manuelle` (soft delete du brouillon).

`services.exercice_pour(date)` renvoie (et crée si besoin, `OUVERT`) l'exercice d'une date —
même principe que `core.services.prochain_numero`. `services.cloturer_exercice(exercice, acteur)`
verrouille la période (DIRECTION, strict), refusé s'il reste des brouillons dans la période.

Rapports (Phase 6, lecture seule) : `services.grand_livre_avec_solde(compte, debut=, fin=)`
(lignes d'un compte + solde cumulé), `services.balance(debut=, fin=)` (tous les comptes
mouvementés, total débit/crédit et solde par compte), `services.compte_de_resultat(exercice)`
(produits/charges strictement dans l'exercice), `services.bilan(exercice)` (actif/passif cumulés
depuis l'origine jusqu'à la fin de l'exercice, résultat net ajouté au passif pour l'affichage —
**aucune écriture de clôture ne l'impute réellement au compte 120000**, voir « Limite connue »
dans `avenant-comptabilite-syscohada.md` § P6).

Déclenchement (automatique) : signaux `billing.signals.facture_a_comptabiliser`,
`reglement_a_comptabiliser`, `depense_a_comptabiliser`, `depense_mode_a_reclasser`, et
`finance.signals.mouvement_a_comptabiliser` — tous émis en `send()` **brut** (pas
`emettre()`/`send_robust`) : une écriture qui échoue à s'équilibrer (ou tombe dans un exercice
clôturé) annule l'opération d'origine plutôt que de laisser un grand livre incomplet.

Reprise de l'historique (événements déjà enregistrés avant la mise en service de chaque lot) :
`python manage.py comptabiliser_historique_factures`, `comptabiliser_historique_reglements`,
`comptabiliser_historique_depenses` (chacune avec `[--depuis AAAA-MM-JJ] [--dry-run]`).

Accès : `permissions.CONSULTATION` (ADMIN, DIRECTION, FINANCES, RH, lecture) ; `SAISIE_OD` (mêmes
rôles, opérations diverses) ; `VALIDATION_OD` (DIRECTION seule, strict) ; `CLOTURE_EXERCICE`
(DIRECTION seule, strict). Écrans : `/comptabilite/operations-diverses/` (liste, création, fiche
avec ajout/retrait de ligne, validation, abandon), `/comptabilite/exercices/` (liste, clôture),
`/comptabilite/grand-livre/` (formulaire compte + période), `/comptabilite/balance/` (formulaire
période), `/comptabilite/bilan/` et `/comptabilite/compte-de-resultat/` (sélecteur d'exercice,
le plus récent par défaut), `/comptabilite/declaration-tva/` (TVA collectée 443300 − TVA
déductible 445200 sur une période, le mois en cours par défaut —
`services.declaration_tva`, `avenant-comptabilite-autonomie.md` § Lot E) — les 5 derniers
accessibles depuis le menu « Rapports comptables », chacun avec une version imprimable
(`.../imprimer/`, même mécanisme que `finance.tresorerie` — voir
`avenant-comptabilite-autonomie.md` § Lot B).

**Plan comptable de départ** (`migrations/0002_plan_comptable_seed.py`) : liste de travail, à
valider par un expert-comptable avant mise en production — aucun plan comptable existant côté
cabinet externe n'a été fourni à ce stade.
