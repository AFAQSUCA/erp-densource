# Avenant — 7 règles de gestion basées sur la séparation des tâches

Complète cahier-des-charges.md : celui qui demande une dépense ou fixe un prix n'est jamais
celui qui la valide. Chaque règle (R1 à R7) est livrée par lot indépendant, testée (≥ 70 % sur
les services), documentée dans le README de son app, puis fusionnée séparément.

| Règle | Contenu | Statut |
|---|---|---|
| R1 | Validation des prix et devis | **Fusionnée dans R5** (seuil DIRECTION à 500 000 FCFA TTC) |
| R2 | Dépenses du parc auto (pré-approbation + enveloppe) | À venir (lot 5) |
| R3 | Modification d'une mission | En attente de fusion (PR #12, branche `feat/reprise-manuelle-et-modification-mission`) |
| R4 | Prévision de trésorerie des missions | À venir (lot 4) |
| R5 | Facture proforma (devis) | **Ce lot** — voir ci-dessous |
| R6 | Mission créée depuis une proforma acceptée | **Ce lot** — voir ci-dessous |
| R7 | Congés : 26 jours ouvrés + report | En attente de fusion (PR #13, branche `feat/conges-26-jours-ouvres-et-report`) |

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
plutôt que l'inverse. (Écart corrigé après une première version qui faisait dépendre `missions` de
`billing` ; repéré en relisant le graphe pendant le lot R4.)

**Limite connue** : une mission créée ainsi reste modifiable comme n'importe quelle autre
(R3, une fois fusionnée) — rien n'empêche aujourd'hui de changer son prix après coup, alors que
le client a accepté un montant précis sur le devis. À reconsidérer à la fusion de R3.
