# Avenant — règles de gestion basées sur la séparation des tâches

Complète cahier-des-charges.md : celui qui demande une dépense ou fixe un prix n'est jamais
celui qui la valide. Chaque règle (R1 à R7) est livrée par lot indépendant, testée (≥ 70 % sur
les services), documentée dans le README de son app, puis fusionnée séparément.

| Règle | Contenu | Statut |
|---|---|---|
| R1 | Validation des prix et devis | Fusionnée dans R5 (seuil DIRECTION à 500 000 FCFA TTC) |
| R2 | Dépenses du parc auto (pré-approbation + enveloppe) | ✅ Fusionnée |
| R3 | Modification d'une mission | ✅ Fusionnée |
| R4 | Prévision de trésorerie des missions | ✅ Fusionnée |
| R5 | Facture proforma (devis) | ✅ Fusionnée |
| R6 | Mission créée depuis une proforma acceptée | ✅ Fusionnée |
| R7 | Congés : 26 jours ouvrés + report | ✅ Fusionnée |
| R8 | Retours de réunion : largeur DIRECTION, RH = FINANCES, affectation Parc Auto, copilote | **✅ Ce lot** — voir ci-dessous |

Les 7 règles historiques sont fusionnées ; R8 (retours de réunion, ci-dessous) les complète.

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
   *suivante* de cette catégorie tant que la DIRECTION ne l'a pas décidée. Volontairement plus
   restreint que `billing.CATEGORIES_AUTOMATIQUES` (qui inclut aussi `FRAIS_MISSION`, R4) : une
   constante dédiée `finance.demandes.CATEGORIES_PARC_AUTO` scope l'enveloppe aux 3 catégories
   d'origine — un frais de mission a déjà sa propre double validation, il ne passe pas en plus par
   une enveloppe.

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

**Écrans** : `/finances/demandes/` (liste + « Nouvelle demande » pour le Parc Auto), fiche par
demande (décision, exécution, revalidation selon le rôle et l'état), `/finances/enveloppes/`
(DIRECTION, liste + formulaire).

## R3 — Modification d'une mission

**Ajoute à** cahier-des-charges.md Module 5 (Missions & Trajets), après le cycle de vie
(cahier-des-charges.md:132-134).

- Une mission peut être modifiée (lieux, marchandise, poids, prix convenu, date de départ prévue)
  tant qu'elle n'a pas dépassé le statut **« Colis récupéré »**.
- Modification réservée à **DIRECTION et ADMIN** (plus restreint que la création, ouverte aussi au
  chargé clientèle).
- Changer le camion ou le chauffeur revérifie leur disponibilité (mêmes contrôles qu'à
  l'affectation initiale) — possible uniquement sur une mission déjà **Affectée**, avant le départ.
- Changer un lieu de chargement ou de livraison régénère les deux codes secrets (expéditeur,
  destinataire) : l'ancien code, et son QR, ne servent plus.
- Le client n'est pas modifiable.
- Chaque modification est tracée dans le journal d'audit (ancienne/nouvelle valeur), au même titre
  que le reste du cycle de vie de la mission.

**Implémentation** : `apps.missions.services.modifier_mission`, `permissions.MODIFICATION`,
écran `/missions/<id>/modifier/`. Détails : `apps/missions/README.md` § Modification.

**Limite connue** : une mission créée depuis un devis accepté (R6) reste modifiable comme une
autre — son prix n'est pas verrouillé du fait d'avoir été accepté par le client sur le devis.

## R4 — Prévision de trésorerie des missions

**Séparation des tâches.** Celui qui déclare ou planifie un frais n'est jamais celui qui le valide :
le **Parc Auto** planifie une avance de route ou une dépense prévue, la **Finance** seule la confirme ;
le **chauffeur** déclare un imprévu (panne, incident) depuis l'espace mobile, le **Parc Auto** le valide
en premier, la **Finance** en second (double validation, jamais en une fois ni par l'auteur).

**Modèle** `missions.FraisMission` (`BaseModel`) :
- `mission` (FK, obligatoire), `type_frais` (`AVANCE_ROUTE` / `DEPENSE_PREVUE` / `IMPREVU` /
  `ENCAISSEMENT`), `montant`, `description`, `justificatif` (`FileField` — obligatoire pour un
  imprévu, stocké sur `MEDIA_ROOT`) ;
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
  → `billing.comptabiliser_depense_automatique` (catégorie `FRAIS_MISSION`, liée à la mission) ;
- `billing.signals.reglement_enregistre` (`send_robust` : un échec ici ne bloque jamais un règlement)
  → `missions.terrain.creer_encaissement` (aucune dépense ni règlement supplémentaire, seulement le
  reflet pour la vue « Frais de mission »).

**Déclencheur** : signal `mission_affectee` (émis par `affecter_mission`) → notifie la FINANCES
(mouvement de caisse probable). Notifications supplémentaires : imprévu déclaré → Parc Auto ;
imprévu validé par le Parc Auto → Finance ; ligne rejetée → son auteur (catégorie `FRAIS_MISSION`).

**Permissions** (`missions.permissions`) : `FRAIS_CONSULTATION` (ADMIN, DIRECTION, PARCAUTO, FINANCES —
écran séparé de la fiche mission, le chargé clientèle n'y a pas accès, comme il ne voit pas le prix
convenu côté chauffeur) ; `FRAIS_SAISIE_PREVISION` (ADMIN, PARCAUTO) ; `FRAIS_VALIDATION_PARCAUTO`
(PARCAUTO seul) ; `FRAIS_VALIDATION_FINANCES` (FINANCES seule).

**Écrans** : `/missions/frais/` (lignes en attente, toutes missions), `/missions/<id>/frais/`
(planification, validation, rejet), `/missions/<id>/frais/imprimer/` (rapport de mission : lignes et
totaux). Côté mobile (`/chauffeur/imprevu/` et `POST /api/v1/mobile/imprevus/`) : formulaire tactile
avec upload de preuve, mêmes règles que le signalement d'un incident (mission du chauffeur uniquement).

## R5 — Facture proforma (et R1 fusionnée)

**Séparation des tâches.** Le **chargé clientèle** fixe le trajet et le prix d'un devis ; il
n'est jamais celui qui le valide. La **FINANCES** valide toujours le prix ; la **DIRECTION**
valide en plus quand le montant TTC dépasse `SEUIL_VALIDATION_DIRECTION` (500 000 FCFA — c'est la
fusion de R1, qui demandait exactement cette règle pour « la validation des prix et devis »).

**Modèle** `apps.billing.models.Proforma` (`BaseModel`) :
- `numero` (`PRO-AAAA-XXXX`, attribué à la validation finale seulement — comme `Facture`, pour
  qu'un devis abandonné ou contesté ne laisse aucun trou de numérotation) ;
- `client`, `lieu_chargement`, `lieu_livraison`, `nature_marchandise`, `poids_t`,
  `date_depart_souhaitee` (indicatif) : les mêmes champs qu'une `Mission`, plutôt que des lignes
  comme `Facture` — R6 les recopie tels quels dans la mission créée ;
- `prix_convenu` (HT), `taux_tva`, `motif_exoneration`, `montant_ht`/`montant_tva`/`montant_ttc`
  (mêmes 3 niveaux de TVA et même arrondi au franc qu'une facture) ;
- `motif_contre_proposition`, `motif_refus_client` ;
- `date_envoi`, `date_validite` (envoi + 30 jours) ;
- `cree_par`, `valide_par_finances`/`date_validation_finances`,
  `valide_par_direction`/`date_validation_direction`.

Pas de modèle séparé pour l'historique des versions : la section « Historique » de la fiche lit
directement `audit_log` (`apps.audit.services.historique`), qui journalise déjà chaque
modification (auteur, date, champs changés) — un modèle dédié aurait dupliqué cette information.

**État** (`StatutProforma`) :

```
BROUILLON → SOUMISE ⇄ CONTRE_PROPOSEE
              │
              ├─ (TTC ≤ seuil) FINANCES valide ──────────────► VALIDEE
              └─ (TTC > seuil) FINANCES valide → EN_ATTENTE_DIRECTION → DIRECTION valide → VALIDEE

VALIDEE → ENVOYEE_CLIENT → ACCEPTEE / REFUSEE / EXPIREE (tâche quotidienne, 30 jours sans réponse)
ACCEPTEE → CONVERTIE (R6 : la mission est créée)
```

Le devis reste modifiable (trajet, marchandise, poids, prix, TVA) tant qu'il est `BROUILLON` ou
`CONTRE_PROPOSEE`. Une contre-proposition renvoie systématiquement vers le chargé clientèle
plutôt que vers un refus définitif : il ajuste puis resoumet (comme `Facture.refuser`, mais avec
un état dédié qui distingue explicitement « à revoir » de « brouillon jamais soumis »).

**Permissions** (`PROFORMA_*` dans `apps/billing/permissions.py`) :
- `PROFORMA_CONSULTATION` : ADMIN, DIRECTION, FINANCES, CHARGE_CLIENTELE ;
- `PROFORMA_SAISIE` (créer, modifier, abandonner, soumettre, envoyer au client, décision client) :
  ADMIN, CHARGE_CLIENTELE ;
- `PROFORMA_VALIDATION_FINANCES` : FINANCES seul (contrôle **strict** : un ADMIN ou un
  superutilisateur ne valide pas, comme pour une facture) ;
- `PROFORMA_VALIDATION_DIRECTION` : DIRECTION seule, même contrôle strict.

**Notifications** (`apps.notifications.receivers`, catégorie `PROFORMA`) : devis soumis → FINANCES ;
devis en attente (seuil dépassé) → DIRECTION ; devis validé, contre-proposé ou expiré → son
auteur. Tâche quotidienne `expirer_proformas` ajoutée à
`notifications.taches.executer_taches_quotidiennes` (compteur `proformas_expirees`).

**Audit** : `Proforma` est journalisé (module `FINANCES`, comme `Facture`) — chaque création,
contre-proposition, validation et changement de statut est tracée avec l'auteur et l'horodatage.

## R6 — Mission créée depuis une proforma acceptée

Une fois le devis `ACCEPTEE`, l'acteur qui pourrait créer une mission à la main (rôle
`missions.permissions.CREATION` : ADMIN, DIRECTION, CHARGE_CLIENTELE) déclenche
« Créer la mission » depuis la fiche du devis
(`POST /facturation/devis/<id>/creer-mission/`) :

- `billing.services.convertir_en_mission(proforma)` recopie tel quel le trajet, la marchandise, le
  poids et le **prix HT** du devis dans une nouvelle `Mission` (via `missions.services.creer_mission`,
  au statut `BROUILLON`, comme une mission créée à la main) — la facture recalculera la TVA plus
  tard, avec le taux du client en vigueur ce jour-là, jamais celui figé sur le devis ;
- le devis passe à `CONVERTIE` (même fonction) ;
- **1 devis = 1 mission** est garanti au niveau base par `Mission.proforma`
  (`OneToOneField(billing.Proforma, on_delete=PROTECT)`), pas seulement par le contrôle de
  statut : deux tentatives concurrentes ne peuvent pas produire deux missions.

Refusé (`TransitionFactureInterdite`) si le devis n'est pas `ACCEPTEE` — y compris s'il l'a déjà
été converti une première fois. Orchestré côté `billing` et non `missions` : le graphe de
dépendance des apps (architecture.md:95-163) interdit à `missions` (Exploitation) de dépendre de
`billing` (Finance) — l'inverse est permis, `billing` appelle donc `missions.services.creer_mission`
plutôt que l'inverse.

**Limite connue** : une mission créée ainsi reste modifiable comme n'importe quelle autre (R3) —
rien n'empêche aujourd'hui de changer son prix après coup, alors que le client a accepté un
montant précis sur le devis.

## R7 — Congés : 26 jours ouvrés, report du solde d'un congé en cours

**Remplace, dans cahier-des-charges.md Module 11** (cahier-des-charges.md:219-221) :

- **Droit annuel : 26 jours ouvrés** (au lieu de 12 jours ouvrables) — avantage social au-delà du
  minimum légal ivoirien (2,2 jours ouvrables/mois ≈ 26,4 jours ouvrables/an). Décision confirmée
  explicitement par l'entreprise après vérification du calcul (26 jours **ouvrés**, lundi-vendredi,
  donne davantage de repos calendaire que le minimum légal en jours **ouvrables**, samedi compris).
- **Décompte en jours ouvrés** : du lundi au vendredi, hors jours fériés légaux (`JourFerie`). Le
  samedi ne compte plus (avant : « ouvrables », tous les jours sauf dimanche).
- **Annulation par la RH inchangée** : un congé approuvé annulé continue de restituer les jours à
  l'employé (règle non modifiée — l'entreprise n'a pas confirmé ce changement-là lors de la
  clarification).
- **Nouveau : report du solde d'un congé en cours.** Un bouton « Reporter » apparaît sur la ligne
  du tableau des congés de l'employé **actuellement en congé** (statut « En cours »). Il indique le
  jour où il reprend réellement le travail (avant la fin initialement prévue) et un motif. **Sans
  validation de la RH, la demande n'a aucun effet** : le congé continue normalement. La RH est
  notifiée (bouton « Confirmer le report ») ; une fois validée : le congé est raccourci à la
  nouvelle date de reprise, les jours ouvrés non pris sont reversés au solde de l'année, et le
  document d'autorisation (PDF) reflète le report (motif, date, jours reversés) — automatiquement,
  puisqu'il est régénéré à la demande à chaque téléchargement plutôt que stocké une fois pour
  toutes. Une seule demande de report à la fois par congé.
- **Nouveau : PDF « Autorisation de congé ».** Téléchargeable dès qu'un congé est approuvé (N2) :
  numéro, employé, dates, jours décomptés, validateurs N1/N2, solde restant de l'année, et la
  section report si applicable. Même en-tête (logo, couleurs de la marque) que le PDF des codes de
  mission.

**Implémentation** : `apps.hr.models.ReportConge`, `apps.hr.services.demander_report` /
`approuver_report` / `refuser_report`, écran `/rh/conges/<id>/reporter/`, PDF
`/rh/conges/<id>/autorisation.pdf` (`apps.hr.documents`). Détails : `apps/hr/README.md`.

## R8 — Retours d'une réunion entreprise (largeur DIRECTION, RH = FINANCES, affectation Parc Auto, copilote)

Quatre remarques de la direction, traitées ensemble car elles touchent toutes aux permissions par
rôle :

1. **La DIRECTION peut faire toutes les tâches** — interprété comme : la DIRECTION gagne la même
   largeur que l'ADMIN pour les actions de **préparation/saisie** dans toute l'application, mais ne
   **remplace jamais** un rôle exclusivement chargé d'une validation ou d'une exécution stricte
   (ex. la FINANCES reste seule à exécuter un ordre de décaissement, le Parc Auto seul à donner la
   première validation d'un imprévu). Concrètement, `Role.DIRECTION` a été ajouté à chaque ensemble
   de **saisie/modification** (jamais aux ensembles `*_VALIDATION`/`*_EXECUTION` à rôle unique et
   contrôle strict) : `billing.SAISIE`/`PROFORMA_SAISIE`, `finance.DEMANDE_SAISIE`,
   `customers.MODIFICATION`, `hr.PERSONNEL_MODIFICATION`, `fuel.MODIFICATION`,
   `garage.MODIFICATION`, `inventory.MODIFICATION`, `missions.FRAIS_SAISIE_PREVISION`,
   `missions.CODES_TERRAIN` (déjà présente dans `drivers.MODIFICATION`/`fleet.MODIFICATION`).
2. **La RH doit pouvoir faire tout ce que fait la FINANCES** — lu littéralement et sans réserve
   (contrairement au point 1) : `Role.RH` a été ajouté partout où `Role.FINANCES` apparaît,
   **y compris** les ensembles stricts à rôle unique (`billing.CONSULTATION`/`SAISIE`/
   `PROFORMA_CONSULTATION`/`PROFORMA_VALIDATION_FINANCES`, `finance.DEMANDE_CONSULTATION`/
   `ORDRE_EXECUTION`) et les notifications adressées à la FINANCES
   (`notifications.receivers`/`taches` : chaque `utilisateurs_du_role(Role.FINANCES)` devient
   `utilisateurs_du_role(Role.FINANCES, Role.RH)`).
3. **C'est le Parc Auto qui affecte les missions**, une fois créées par le chargé clientèle —
   `Role.PARCAUTO` ajouté à `missions.AFFECTATION` (et nécessairement à `missions.CONSULTATION`,
   pour voir les missions à affecter). Point de vigilance : `VOIR_CODES` (codes secrets
   expéditeur/destinataire) était défini comme un simple alias de `CONSULTATION`
   (`VOIR_CODES = CONSULTATION`) — laissé tel quel, le Parc Auto aurait hérité de la visibilité des
   codes, qui n'a rien à voir avec l'affectation. Corrigé en **décorrélant** `VOIR_CODES` en un
   ensemble explicite et indépendant (`{ADMIN, DIRECTION, CHARGE_CLIENTELE}`), qui ne bouge plus
   avec `CONSULTATION`.
4. **Certains voyages exigent un copilote**, assistant du chauffeur pendant le trajet — nouvelle
   entité `drivers.Copilote`, fonction/fiche **distincte** du chauffeur (jamais un chauffeur
   principal), même mécanisme que `Chauffeur` : extension 1-1 de `hr.Personnel` (poste
   « Copilote »), auto-création par signal, mêmes statuts de disponibilité (`StatutChauffeur`,
   y compris la synchronisation avec les congés). Aucune règle automatique ne décide qu'une mission
   exige un copilote : **décision humaine du Parc Auto au moment de l'affectation**, sur le même
   écran que le camion et le chauffeur (`Mission.copilote`, facultatif). `affecter_mission` vérifie
   sa disponibilité comme pour le chauffeur ; `demarrer_mission`/`livrer_mission` le mettent
   « En mission » / le libèrent en parallèle.

**Implémentation** : `apps/drivers/models.py` (`Copilote`), `apps/drivers/services.py` (section
copilotes), `apps/drivers/signals.py` (auto-création + synchronisation congés), `apps/missions/`
(`models.Mission.copilote`, `services.py` affectation/démarrage/livraison, `forms.AffectationForm`,
templates). Permissions détaillées ci-dessus, réparties dans le `permissions.py` de chaque app
concernée. Pas d'écran dédié pour gérer les fiches copilote (contrairement au chauffeur) : géré via
l'admin Django pour l'instant.

**Limite connue** : `missions.services.modifier_mission` (R3) ne permet pas encore de changer le
copilote d'une mission déjà affectée (seuls camion et chauffeur sont réaffectables) — seule
l'affectation initiale propose ce choix.
