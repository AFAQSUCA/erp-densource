## Ce que vous allez construire

**`garage`** : l'entretien et les pannes des camions.

| Élément | Règle |
|---|---|
| **Ordre de réparation (OR)** | numéro `OR-<année>-0001`, type (curatif, préventif, diagnostic, pneumatiques), lieu (garage interne ou prestataire), motif ; **ouvrir un OR met le camion « En maintenance »** |
| **Clôture d'un OR** | on saisit la main-d'œuvre ; le **statut du camion est recalculé** avec l'algorithme de `fleet` |
| **Immobiliser / hors service / remettre en service** | actions manuelles du Parc Auto (refusées si le camion est réservé par une mission) |
| **Check-list du chauffeur** | 8 points fixes (pneus, freins, feux…), OK ou KO ; un **KO exige une remarque** et **prévient** le Parc Auto sans bloquer le départ |
| **Incident** | panne, accident ou autre, avec gravité ; il prévient le Parc Auto et la Direction, **sans aucune action automatique** : le Parc Auto décide |

## Prérequis

- Chapitres 1 à 9 terminés.

## Notions Django de ce chapitre

- **Inversion de dépendance, suite** : c'est ici qu'on utilise `fleet.calculer_statut`. `garage` calcule
  « y a-t-il un OR ouvert ? » et « y a-t-il une mission active ? » (en appelant `missions`), puis passe ces
  **faits en paramètres** à `fleet`.
- **Plusieurs modèles dans un module** : un OR, une check-list, un incident.
- **Signaux métier** (`incident_signale`, `checklist_anomalie`) : `notifications` les écoutera.
- **Un registre pour recevoir des blocs** (`DETAIL_OR`) : `inventory` y ajoutera les pièces utilisées.
- **Un service qui filtre par acteur** : les incidents et check-lists d'un chauffeur ne peuvent être
  déclarés que **sur son propre camion** (`ChauffeurNonAutorise`).
- **`terrain.py`** : un second module de services pour tout ce qui vient du terrain (chauffeur mobile), pour
  ne pas mélanger avec la gestion des OR.

## Étape 1 — Créer l'application

```bash
mkdir -p apps/garage/tests
```

{{VIDES}}

## Étape 2 — Modèles

{{FICHIER apps/garage/models.py}}

Trois modèles :

- **`OrdreReparation`** : le numéro, le camion (`PROTECT` : on ne supprime pas un camion qui a un
  historique), le type, le lieu, le motif, le statut (Ouvert / Clôturé) et les coûts.
- **`ChecklistVehicule`** : les résultats des 8 points (`POINTS_CHECKLIST`), rattachés à **une mission**.
- **`Incident`** : type, gravité (faible, moyenne, grave), description, lieu, statut (Signalé → Pris en
  compte → Clos).

## Étape 3 — Règles métier

{{FICHIER apps/garage/exceptions.py}}

{{FICHIER apps/garage/services.py}}

À lire :

1. **`ouvrir_or`** : crée l'OR, passe le camion « En maintenance » (`fleet.definir_statut`). Autorisé même
   pendant une mission : c'est une panne en route.
2. **`cloturer_or`** : enregistre la main-d'œuvre, puis **recalcule** le statut du camion avec
   `fleet.recalculer_statut`, en fournissant `or_ouverts` (y a-t-il d'autres OR ouverts ?) et `mission_active`
   (`missions.vehicule_a_mission_active`).
3. **`immobiliser_vehicule`**, **`mettre_hors_service`**, **`remettre_en_service`** : refusés si le camion est
   réservé (`_refuser_si_mission_active`). Un camion réservé qui tombe en panne s'**ouvre en OR**, on ne
   l'immobilise pas.

{{FICHIER apps/garage/terrain.py}}

Ce que fait le chauffeur sur le terrain :

- **`enregistrer_checklist`** : refuse les points inconnus ; **exige une remarque** pour un point KO ; une
  seule check-list par mission ; **non bloquante** (elle n'empêche pas le départ).
- **`declarer_incident`** puis **`prendre_en_compte`** / **`clore_incident`** (réservés au Parc Auto) : la
  décision (ouvrir un OR ou non) reste **humaine**.

{{FICHIER apps/garage/signals.py}}

{{FICHIER apps/garage/permissions.py}}

{{FICHIER apps/garage/sections.py}}

Deux rôles : `garage` **expose** `DETAIL_OR` (où `inventory` ajoutera ses pièces) et **fournit** le bloc
« Maintenance » à la fiche d'un camion (`fleet.sections.DETAIL_VEHICULE`).

## Étape 4 — Administration, démarrage, tests

{{FICHIER apps/garage/admin.py}}

{{FICHIER apps/garage/apps.py}}

{{FICHIER apps/garage/tests/factories.py}}

{{RESTANTS}}

`test_statut_vehicule.py` teste **l'intégration** garage ↔ fleet ↔ missions : par exemple « un OR clôturé
remet le camion en mission s'il a une mission affectée ».

## Étape 5 — Déclarer l'application et migrer

{{CONFIG}}

```bash
python manage.py makemigrations garage
python manage.py migrate
```

**Résultat attendu :** `Create model OrdreReparation`, `Create model ChecklistVehicule`,
`Create model Incident`, puis `Applying garage.0001_initial... OK`.

## Vérifier le chapitre

```bash
python manage.py check
```

{{PYTEST}}

Essai dans le shell : ouvrir un OR sur le camion du chapitre 8 et regarder son statut changer, puis le clôturer.

```bash
python manage.py shell -c "from decimal import Decimal; from apps.fleet.models import Vehicule; from apps.garage import services as g; v = Vehicule.objects.get(vin='VIN00000000000001'); o = g.ouvrir_or(v, type_or='CURATIF', lieu='INTERNE', motif='Bruit au freinage'); v.refresh_from_db(); print(o.numero.startswith('OR-'), v.statut); g.cloturer_or(o, cout_main_oeuvre=Decimal('45000')); v.refresh_from_db(); print(v.statut)"
```

**Résultat attendu :** `True EN_MAINTENANCE`, puis `DISPONIBLE`.

> Si vous obtenez `DoesNotExist` ou une erreur sur `type_or` : vérifiez le VIN (`VIN00000000000001`, en
> majuscules, créé au chapitre 8) et les valeurs `CURATIF` / `INTERNE` dans `models.py`.

## Ce qu'il faut retenir

- Le statut d'un camion dépend de **plusieurs apps** (missions, garage) sans qu'elles se connaissent : chaque
  app passe des **faits** à la fonction pure de `fleet`.
- Un incident déclenche une **alerte**, pas une **décision** : les décisions restent humaines.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 10 : app garage (ordres de réparation, check-lists, incidents)"
```
