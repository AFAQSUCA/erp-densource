# Avenant — 7 règles de gestion basées sur la séparation des tâches

Complète cahier-des-charges.md : celui qui demande une dépense ou fixe un prix n'est jamais
celui qui la valide. Chaque règle (R1 à R7) est livrée par lot indépendant, testée (≥ 70 % sur
les services), documentée dans le README de son app, puis fusionnée séparément.

| Règle | Contenu | Statut |
|---|---|---|
| R1 | Validation des prix et devis | Fusionnée dans R5 (seuil DIRECTION à 500 000 FCFA TTC) |
| R2 | Dépenses du parc auto (pré-approbation + enveloppe) | **Ce lot** — voir ci-dessous |
| R3 | Modification d'une mission | En attente de fusion (PR #12, branche `feat/reprise-manuelle-et-modification-mission`) |
| R4 | Prévision de trésorerie des missions | En attente de fusion (PR #15, branche `feat/prevision-tresorerie-missions-r4`) |
| R5 | Facture proforma (devis) | En attente de fusion (PR #14, branche `feat/proforma-devis-r5-r6`) |
| R6 | Mission créée depuis une proforma acceptée | En attente de fusion (PR #14, branche `feat/proforma-devis-r5-r6`) |
| R7 | Congés : 26 jours ouvrés + report | En attente de fusion (PR #13, branche `feat/conges-26-jours-ouvres-et-report`) |

## R2 — Dépenses du parc auto pré-approuvées

**Séparation des tâches.** Le **Parc Auto** demande, la **DIRECTION** valide (jamais l'ADMIN à sa
place — contrôle strict, comme pour la validation d'une facture), la **FINANCES** exécute le
paiement. Deux circuits distincts, réconciliés avec le mécanisme déjà livré (une session plus tôt)
qui comptabilise automatiquement un plein, un achat de pièces ou la main-d'œuvre d'un OR clôturé,
sans aucune approbation préalable :

1. **Manuelle** : pour un achat ou une réparation non routinière (pièce commandée à un fournisseur
   externe, réparation chez un prestataire externe), le Parc Auto soumet une `DemandeDepense`
   *avant* tout engagement.
2. **Dépassement d'enveloppe** : pour le flux automatique déjà en place (carburant, pièces,
   main-d'œuvre), la DIRECTION peut fixer une `EnveloppeDepense` — un plafond mensuel par
   catégorie, globalement ou par camion. Tant qu'on reste dans l'enveloppe, **rien ne change** :
   c'est aussi le comportement par défaut, sans enveloppe définie (illimité, comme avant R2). La
   dépense qui fait franchir le plafond reste comptabilisée (l'argent est déjà sorti — un plein ne
   se refuse pas après coup) mais ouvre une demande a posteriori qui bloque la dépense automatique
   *suivante* de cette catégorie tant que la DIRECTION ne l'a pas décidée.

**Modèles** (`apps/finance/models.py`, cohérent avec `MouvementManuel` déjà là et
`finance/receivers.py` qui dépend déjà de `garage`/`inventory`/`fuel` — le graphe de dépendance des
apps, architecture.md:95-163, place `finance` sous `billing`, seul endroit qui peut connaître les
deux à la fois) :
- `EnveloppeDepense` : `categorie`, `vehicule` (vide = globale, sinon prioritaire sur la globale),
  `annee`/`mois`, `montant_plafond`, `valide_par` (DIRECTION). Une seule par (catégorie, camion, mois).
- `DemandeDepense` (`DEM-AAAA-XXXX`) : `categorie`, `vehicule`, `origine` (`MANUELLE` /
  `DEPASSEMENT_ENVELOPPE`), `montant_estime`, `motif`, `fournisseur`, `piece_jointe` (`FileField`),
  `statut` (`SOUMISE` → `VALIDEE` / `REFUSEE`), `demandeur`, `valide_par`, `date_decision`,
  `motif_refus`.
- `OrdreDecaissement` (`ODC-AAAA-XXXX`, uniquement pour l'origine `MANUELLE` — un dépassement
  d'enveloppe n'en génère pas, la dépense existe déjà) : `demande` (1-1), `montant_valide`, `statut`
  (`A_EXECUTER` → `EXECUTE`, ou `EN_ATTENTE_REVALIDATION` en cas de dépassement), `mode_paiement`,
  `justificatif` (`FileField`), `montant_reel`, `execute_par`, `depense` (la `billing.Depense`
  résultante, origine `ORDRE_DECAISSEMENT`).
- `billing.Depense` gagne un champ `vehicule` (facultatif) : sert au suivi par enveloppe (un plein
  ou une main-d'œuvre d'OR est déjà lié à un camion ; un achat de pièces reste sans camion, comme
  aujourd'hui — un achat de stock n'est pas encore affecté à un véhicule précis).

**Machine à états** :
- Manuelle : `soumettre_demande` (Parc Auto) → `SOUMISE` → `valider_demande` (DIRECTION, génère
  l'`OrdreDecaissement`) ou `refuser_demande` (motif obligatoire) → `executer_ordre` (FINANCES :
  mode, montant réel, justificatif) → `EXECUTE`, dépense créée.
- Dépassement d'enveloppe : ouverte automatiquement par
  `finance.demandes.comptabiliser_avec_controle_enveloppe` (appelée par `finance.receivers` à la
  place de `billing.comptabiliser_depense_automatique`) → `SOUMISE` → `valider_demande` ou
  `refuser_demande` — les deux débloquent le mécanisme automatique (le refus n'est qu'un constat de
  désaccord, il ne fige pas la flotte) ; aucun ordre généré.
- **Dépassement de plus de 10 %** à l'exécution (manuelle) : bloqué, l'ordre passe en
  `EN_ATTENTE_REVALIDATION` — un état qui doit **survivre** à l'erreur renvoyée à l'écran
  (`executer_ordre` n'a donc pas de `@transaction.atomic` sur toute sa longueur, seulement sur le
  bloc qui écrit cet état ; sans cette précaution, l'erreur lève une exception qui annule aussi la
  mise en attente qu'on veut pourtant garder — repéré par un test qui vérifiait l'état après coup).
  La DIRECTION revalide (`revalider_ordre`, nouveau montant) avant que la Finance ne retente.

**Permissions** (`finance.permissions`) : `DEMANDE_SAISIE` (ADMIN, PARCAUTO) ; `DEMANDE_VALIDATION`
(DIRECTION seule, strict) ; `ORDRE_EXECUTION` (FINANCES seule, strict) ; `ENVELOPPE_VALIDATION`
(DIRECTION seule, strict) ; `DEMANDE_CONSULTATION` (ADMIN, DIRECTION, PARCAUTO, FINANCES).

**Notifications** (catégorie `DEMANDE_DEPENSE`) : soumission (manuelle ou dépassement) → DIRECTION ;
décision → le demandeur (ou le Parc Auto pour un dépassement, sans demandeur nommé) ; ordre à
exécuter → FINANCES ; dépassement de 10 % → DIRECTION.

**Audit** : les trois modèles sont journalisés (module `FINANCES`).

**Effet de bord découvert en cours de route (déjà rencontré sur la branche R4, corrigé
indépendamment ici)** : `audit.registry._snapshot` ne savait pas sérialiser un `FileField`
(`FieldFile` n'est pas JSON-sérialisable) — `DemandeDepense.piece_jointe` et
`OrdreDecaissement.justificatif` sont les premiers champs fichier de cette branche. Corrigé de la
même façon (`_valeur()` normalise en son chemin, ou une chaîne vide sans fichier).

**Écrans** : `/finances/demandes/` (liste + « Nouvelle demande » pour le Parc Auto), fiche par
demande (décision, exécution, revalidation selon le rôle et l'état), `/finances/enveloppes/`
(DIRECTION, liste + formulaire).
