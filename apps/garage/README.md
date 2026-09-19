# garage

Rôle : ordres de réparation (OR) — cahier-des-charges.md:161-168. Audité (module `PARC_AUTO`).

Entité : `OrdreReparation` (numéro `OR-AAAA-XXXX` via `core.services.prochain_numero`),
4 types (Curatif, Préventif, Diagnostic, Pneumatiques), 2 lieux (garage interne,
prestataire externe), statuts Ouvert / Clôturé.

Services :
- `ouvrir_or` : crée l'OR et passe le camion « En maintenance » (même en mission :
  panne en route).
- `cloturer_or` : enregistre la main-d'œuvre puis recalcule le statut du camion
  avec `fleet.services.recalculer_statut`, en fournissant `or_ouverts` (garage) et
  `mission_active` (`missions.services.vehicule_a_mission_active`).

Dépend de `fleet` et `missions` (jamais l'inverse).

Interface (`views.py`, `templates/garage/`) : liste des OR (filtres statut, type, lieu,
texte), fiche d'un OR, ouverture (préremplie depuis la fiche d'un camion), clôture avec
saisie de la main-d'œuvre. Accès : ADMIN, DIRECTION et PARCAUTO en consultation ; ADMIN
et PARCAUTO pour ouvrir, clôturer, immobiliser (`permissions.py`, la DIRECTION est en
lecture seule sur le parc auto).

Statut des camions (services) : `immobiliser_vehicule`, `mettre_hors_service`,
`remettre_en_service` (repart de « Disponible » puis applique l'algorithme complet :
OR ouvert, mission, sinon disponible). Un camion réservé ou en route pour une mission ne
s'immobilise pas : en cas de panne, on ouvre un OR.

Blocs enregistrables (`core/sections.py`) : `garage` ajoute un bloc « Maintenance » à la
fiche d'un camion (`fleet.sections.DETAIL_VEHICULE`) et expose `sections.DETAIL_OR` où
`inventory` ajoute les pièces utilisées. Ainsi `fleet` ne connaît pas `garage`, et
`garage` ne connaît pas `inventory`.

Signalements du chauffeur (`terrain.py`, `views_terrain.py`) :
- **Check-list du véhicule** : 8 points fixes (`POINTS_CHECKLIST` : pneus, freins, feux, huile, eau,
  carrosserie, documents, extincteur et triangle), OK ou KO, un KO exige une remarque. Une seule par
  mission, avant le départ. **Non bloquante** : un KO prévient le Parc Auto sans empêcher la mission.
- **Incident** : panne, accident ou autre, avec gravité, description et lieu. Il prévient le Parc Auto
  et la Direction ; **aucune action automatique** : le Parc Auto le prend en compte, ouvre un OR s'il le
  juge utile, puis le clôt avec la suite donnée (`/garage/incidents/`, `/garage/checklists/`).
Les signaux `incident_signale` et `checklist_anomalie` sont souscrits par `notifications`.
