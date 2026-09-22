## Ce que vous allez construire

**`fleet`** : les **camions** et leurs **documents réglementaires**. Le point le plus intéressant : le
**statut d'un camion n'est jamais saisi à la main**, il est **calculé** par un algorithme.

| Statut | Quand |
|---|---|
| **En maintenance** | au moins un ordre de réparation est ouvert (règle n° 1, la plus forte) |
| **En mission** | une mission est affectée ou en cours |
| **Immobilisé** / **Hors service** | marqué à la main, et conservé tant qu'aucune règle plus forte ne s'applique |
| **Disponible** | sinon |

Et quatre **documents** par camion (carte grise, assurance, visite technique, patente), avec une **alerte 30
jours avant** l'expiration.

## Prérequis

- Chapitres 1 à 7 terminés.

## Notions Django de ce chapitre

- **Fonction pure** : une fonction dont le résultat ne dépend que de ses arguments et qui ne touche pas à la
  base : `calculer_statut(statut_actuel, or_ouverts=..., mission_active=...)`. Elle est très simple à tester.
- **Inversion de dépendance par paramètres** : `fleet` ne peut pas savoir s'il existe une mission active
  (`missions` vient après). Alors **c'est l'appelant** (missions, garage) qui calcule les faits et les
  *passe en paramètre*. `fleet` reste indépendant.
- **`UniqueConstraint(condition=Q(is_deleted=False))`** : l'unicité d'un document par type et par camion,
  **hors lignes supprimées**.
- **`select_related`** : charger le camion en même temps que ses documents (une seule requête SQL).
- **Normalisation des saisies** : « ab 123 » et « AB 123 » doivent être le même camion.
- **`update_fields`** dans `save()` : n'écrire que les colonnes modifiées.

## Étape 1 — Créer l'application

```bash
mkdir -p apps/fleet/tests
```

{{VIDES}}

## Étape 2 — Modèles

{{FICHIER apps/fleet/models.py}}

- **`Vehicule`** garde la plaque et le n° de châssis (VIN) uniques, le kilométrage, la capacité de charge
  (tonnes) et la taille du réservoir.
- **`DocumentReglementaire`** porte deux contraintes en base : un seul document actif par type et par camion,
  et une date d'expiration jamais antérieure à la délivrance. `jours_restants()` donne le nombre de jours
  avant l'échéance (négatif si expiré).

## Étape 3 — Règles métier

{{FICHIER apps/fleet/exceptions.py}}

{{FICHIER apps/fleet/services.py}}

Lisez dans cet ordre :

1. **`calculer_statut`** : l'algorithme du cahier des charges en 4 lignes, dans l'ordre strict des règles.
2. **`recalculer_statut`** : applique l'algorithme et enregistre.
3. **`creer_vehicule` / `modifier_vehicule`** : normalisent plaque et VIN, refusent les doublons
   (`DoublonVehicule`) et un compteur qui reculerait (`KilometrageInvalide`).
4. **`enregistrer_document` / `etat_documents`** : renouvellement d'un document et état des quatre documents
   (valide, à renouveler, expiré, manquant).
5. **`documents_a_renouveler`**, **`vehicules_avec_documents_a_renouveler`**, **`repartition_statuts`** :
   des *lectures* qui alimenteront les alertes et le tableau de bord.

{{FICHIER apps/fleet/permissions.py}}

{{FICHIER apps/fleet/sections.py}}

`DETAIL_VEHICULE` : le registre où `garage` ajoutera son bloc « Maintenance » (chapitre 10).

## Étape 4 — Administration, démarrage, tests

{{FICHIER apps/fleet/admin.py}}

{{FICHIER apps/fleet/apps.py}}

{{FICHIER apps/fleet/tests/factories.py}}

{{RESTANTS}}

`test_services.py` commence par les quatre cas de l'algorithme ; vous les lirez comme une spécification.

## Étape 5 — Déclarer l'application et migrer

{{CONFIG}}

```bash
python manage.py makemigrations fleet
python manage.py migrate
```

**Résultat attendu :** `Create model Vehicule`, `Create model DocumentReglementaire`, les contraintes, puis
`Applying fleet.0001_initial... OK`.

## Vérifier le chapitre

```bash
python manage.py check
```

{{PYTEST}}

Essai dans le shell : créer un camion, lui donner un ordre de réparation ouvert (simulé par le paramètre) et
voir son statut changer :

```bash
python manage.py shell -c "from decimal import Decimal; from apps.fleet import services as s; v = s.creer_vehicule(immatriculation='1234 ab 01', marque='Mercedes-Benz', modele='Actros', annee=2020, vin='vin00000000000001', kilometrage=120000, capacite_charge_t=Decimal('25'), reservoir_l=600); print(v.immatriculation, v.statut); print(s.calculer_statut(v.statut, or_ouverts=True, mission_active=True))"
```

**Résultat attendu :** `1234 AB 01 DISPONIBLE` (la plaque est **normalisée en majuscules**), puis
`EN_MAINTENANCE` (la maintenance l'emporte sur la mission).

## Ce qu'il faut retenir

- Une donnée **dérivée** (le statut) se **calcule**, elle ne se saisit pas : elle ne peut pas être fausse.
- Pour rester indépendant d'une app « du dessous », on lui fait passer les **faits en paramètres**.
- **Normaliser** à l'entrée évite les doublons invisibles.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 8 : app fleet (camions, documents réglementaires, statut calculé)"
```
