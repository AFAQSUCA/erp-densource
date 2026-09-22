## Ce que vous allez construire

Les **écrans du garage** (Parc Auto : gestion ; Direction : lecture seule).

| Écran | Adresse | Ce qu'on y fait |
|---|---|---|
| **Ordres de réparation** (liste, fiche, ouverture, clôture) | `/garage/`, `/garage/<id>/`, `/garage/nouveau/`, `/garage/<id>/cloturer/` | ouvrir un OR depuis la fiche d'un camion, clôturer en saisissant la main-d'œuvre |
| **Incidents** signalés par les chauffeurs | `/garage/incidents/`, `/garage/incidents/<id>/` | prendre en compte, clore avec la suite donnée |
| **Check-lists** des chauffeurs | `/garage/checklists/` | consulter les points KO |
| Actions sur un camion | `/garage/camions/<id>/immobiliser/`… | immobiliser, mettre hors service, remettre en service |
| **Bloc « Maintenance »** | dans la fiche d'un camion (`/flotte/<id>/`) | historique des OR, boutons d'action |

## Prérequis

- Chapitres 1 à 21 terminés.

## Ce que ce chapitre apporte de nouveau

- **Le bloc qu'on attendait** : c'est ici que `_maintenance_vehicule.html` existe enfin. Dès que ce fichier est
  créé, la fiche d'un camion (chapitre 20) affiche **automatiquement** le bloc « Maintenance » : `fleet` n'a pas
  changé d'une ligne. C'est la force des registres.
- **Deux fichiers de vues** : `views.py` (gestion des OR et du statut des camions) et `views_terrain.py` (ce qui
  vient du terrain : incidents et check-lists). Même chose pour les formulaires : `forms.py` et
  `forms_terrain.py`.
- **Des actions manuelles gardées** : immobiliser, mettre hors service, remettre en service passent par une classe
  mère (`StatutVehiculeView`) qui appelle le service correspondant.

## Étape 1 — Formulaires

{{FICHIER apps/garage/forms.py}}

{{FICHIER apps/garage/forms_terrain.py}}

## Étape 2 — Vues et adresses

{{FICHIER apps/garage/views.py}}

{{FICHIER apps/garage/views_terrain.py}}

{{FICHIER apps/garage/urls.py}}

{{CONFIG}}

## Étape 3 — Gabarits

```bash
mkdir -p apps/garage/templates/garage
```

{{FICHIER apps/garage/templates/garage/or_list.html}}

{{FICHIER apps/garage/templates/garage/or_form.html}}

{{FICHIER apps/garage/templates/garage/or_detail.html}}

{{FICHIER apps/garage/templates/garage/_maintenance_vehicule.html}}

{{FICHIER apps/garage/templates/garage/incident_list.html}}

{{FICHIER apps/garage/templates/garage/incident_detail.html}}

{{FICHIER apps/garage/templates/garage/checklist_list.html}}

## Étape 4 — Tests et compilation des styles

{{RESTANTS}}

```bash
cd frontend
npm run build:css
cd ..
```

## Vérifier le chapitre

```bash
python manage.py check
```

{{PYTEST}}

**Dans le navigateur :**

1. **`demo_parcauto`** : ouvrez la fiche du camion `1234 AB 01` : un bloc **Maintenance** est apparu (grâce au
   registre). Cliquez **Ouvrir un OR** : type Curatif, lieu interne, motif « Bruit au freinage ». Le camion passe
   **En maintenance**.
2. Ouvrez l'OR : le bloc « Pièces utilisées » **n'existe pas encore** (il viendra avec le stock, chapitre 23).
   **Clôturez** l'OR avec 45 000 de main-d'œuvre : le camion redevient **Disponible**.
3. **Immobilisez** le camion (confirmation) : statut **Immobilisé** ; « Remettre en service » le repasse Disponible.
4. **`demo_direction`** : le bloc Maintenance est visible mais **sans boutons** (lecture seule).

## Ce qu'il faut retenir

- Un fichier de gabarit **suffit** à activer un bloc pour une autre app : le couplage est dans les registres,
  pas dans les imports.
- On peut **scinder** vues et formulaires en plusieurs fichiers quand un module a deux visages (gestion / terrain).

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 22 : écrans du garage (OR, incidents, check-lists, bloc maintenance)"
```
