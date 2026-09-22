## Ce que vous allez construire

Les **écrans de la flotte**, accessibles à l'ADMIN, à la DIRECTION et au PARCAUTO.

| Écran | Adresse | Ce qu'on y fait |
|---|---|---|
| Liste des camions | `/flotte/` | filtrer par statut, texte, « documents à renouveler » |
| Fiche d'un camion | `/flotte/<id>/` | caractéristiques, **état des 4 documents**, statut, blocs fournis par d'autres apps |
| Créer / modifier | `/flotte/nouveau/`, `/flotte/<id>/modifier/` | fiche du camion |
| Enregistrer / renouveler un document | `/flotte/<id>/document/` (POST) | carte grise, assurance, visite technique, patente |

Le **statut** est affiché mais **jamais modifiable** dans un formulaire : il se calcule (chapitre 8).

## Prérequis

- Chapitres 1 à 19 terminés.

## Ce que ce chapitre apporte de nouveau

- **Une fiche qui héberge des blocs** : `sections=sections.DETAIL_VEHICULE.sections(self.object, self.request.user)`
  dans la vue, `{% for section in sections %}{% include section.template %}{% endfor %}` dans le gabarit. Le bloc
  « Maintenance » de `garage` s'y affichera dès le chapitre 22, **sans qu'une ligne de `fleet` ne change**.
- **Un formulaire à deux visages** : `VehiculeForm` sert à la création et à la modification ; le service refuse un
  compteur qui reculerait.
- **Un formulaire secondaire sur une fiche** (`DocumentForm`) qui poste vers une vue dédiée.

## Étape 1 — Formulaires, vues, adresses

{{FICHIER apps/fleet/forms.py}}

{{FICHIER apps/fleet/views.py}}

{{FICHIER apps/fleet/urls.py}}

{{CONFIG}}

## Étape 2 — Gabarits

```bash
mkdir -p apps/fleet/templates/fleet
```

{{FICHIER apps/fleet/templates/fleet/vehicule_list.html}}

{{FICHIER apps/fleet/templates/fleet/vehicule_detail.html}}

{{FICHIER apps/fleet/templates/fleet/vehicule_form.html}}

## Étape 3 — Tests et compilation des styles

{{RESTANTS}}

Le fichier `apps/notifications/tests/test_taches.py` teste les alertes du jour (documents à 30 jours…) : il a
besoin de la fiche d'un camion avec ses documents, donc de ces écrans.

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

1. Connectez-vous avec **`demo_parcauto`** : le menu affiche **Flotte**. Le camion `1234 AB 01` (créé par
   l'essai du chapitre 8) apparaît. Si vous n'en avez pas, créez-en un : « Nouveau camion ».
2. Ouvrez sa fiche : les quatre documents sont **Manquants**. Enregistrez une **assurance expirant dans 15 jours**
   : elle passe à **À renouveler**, et la case « documents à renouveler » de la liste retrouve le camion.
3. Renouvelez-la avec une date lointaine : elle redevient **Valide**.
4. Remettez l'assurance à 15 jours, puis lancez `python manage.py taches_quotidiennes` : la ligne
   `documents vehicules` vaut `1` (une alerte est créée pour le Parc Auto). Relancez la commande : elle vaut `0`
   (**aucune alerte en double**). La cloche de `demo_parcauto` affiche l'alerte.

## Ce qu'il faut retenir

- Un registre permet à une fiche d'afficher des blocs d'un module **qu'elle ne connaît pas**.
- Une donnée **calculée** (le statut) s'affiche mais ne se saisit pas.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 20 : écrans de la flotte (camions et documents réglementaires)"
```
