## Ce que vous allez construire

La **vraie page d'accueil** : le **tableau de bord**, différent pour chaque rôle. Il **remplace** la page provisoire
du chapitre 16.

| Bloc | Qui le voit | Contenu |
|---|---|---|
| **Centre d'alertes** | selon les droits de chacun | documents des camions à 30 jours ou expirés, permis et visites des chauffeurs, pièces sous le seuil, surconsommation des 30 derniers jours, validations de congés en retard, **incidents à traiter**, **factures échues** |
| **Exploitation** | ADMIN, DIRECTION, PARCAUTO | camions disponibles / en mission / au garage, consommation moyenne, missions en cours, à affecter, à clôturer |
| **Ressources humaines** | ADMIN, DIRECTION, RH | effectif par département, absents du jour, prochains départs en congé, demandes à valider |
| **Finances du mois** | ADMIN, DIRECTION, FINANCES | CA HT, encaissé, charges, marge nette, créances (dont échues), trésorerie |
| **Clientèle** | ADMIN, DIRECTION, CHARGE_CLIENTELE | clients actifs, réclamations, top 3 des clients |
| **Accès rapides** | tous | raccourcis vers les écrans du menu |

## Prérequis

- Chapitres 1 à 25 terminés. C'est **pour cela** que le tableau de bord arrive maintenant : il renvoie vers tous les
  écrans (`reverse('inventory:articles')`…), qui doivent tous exister.

## Ce que ce chapitre apporte de nouveau

- **Une app qui n'a presque pas de règles** : `dashboard/services.py` **assemble** des lectures que les autres
  apps fournissent (`fleet.repartition_statuts`, `fuel.consommation_moyenne`, `hr.absents_du_jour`,
  `finance.indicateurs`…). Il **ne calcule rien lui-même** : aucune règle n'est dupliquée.
- **Qui voit quoi, sans le réécrire** : les ensembles de rôles sont **importés** des `permissions` de chaque app
  (`fleet_permissions.CONSULTATION`…). Si un droit change dans une app, le tableau de bord suit.
- **Le cache** : les blocs *exploitation* et *clientèle* sont mis en cache `DASHBOARD_CACHE_SECONDS` (60 s par
  défaut). Le centre d'alertes, lui, est **toujours recalculé**. En production avec Redis, le cache est partagé
  entre les processus.
- **Performance** : le tableau de bord d'un ADMIN fait **au plus 34 requêtes SQL** quel que soit le volume de
  données ; un test le vérifie (`django_assert_max_num_queries`).
- **Remplacer une page provisoire** : on supprime le fichier provisoire et la ligne d'adresse qui l'utilisait.

## Étape 1 — Créer l'application

```bash
mkdir -p apps/dashboard/templates/dashboard apps/dashboard/tests
```

{{VIDES}}

## Étape 2 — Services, vue, gabarit

{{FICHIER apps/dashboard/services.py}}

Lisez-le de bas en haut :

1. **`tableau_de_bord(utilisateur)`** : l'orchestre ; décide quels blocs assembler d'après le rôle.
2. **`centre_alertes(role)`** : construit la liste des groupes d'alertes (`_alertes_documents`,
   `_alertes_chauffeurs`, `_alertes_stock`, `_alertes_carburant`, `_alertes_factures`, `_alertes_incidents`,
   `_alertes_conges`) et n'en garde que les non vides.
3. **`exploitation`**, **`ressources_humaines`**, **`clientele`**, **`finances`** : un bloc chacun, qui appelle des
   services des autres apps.

{{FICHIER apps/dashboard/views.py}}

`DashboardView` est **la page d'accueil** (`name="home"`). Le chauffeur, lui, est **redirigé vers son espace
mobile** (chapitre 27).

{{FICHIER apps/dashboard/templates/dashboard/index.html}}

{{FICHIER apps/dashboard/apps.py}}

{{RESTANTS}}

## Étape 3 — Retirer la page provisoire

Supprimez le fichier provisoire du chapitre 16 (il n'a plus d'utilité) :

```bash
rm templates/accueil_provisoire.html
```

> Sous PowerShell : `Remove-Item templates/accueil_provisoire.html`.

Et remplacez, dans `config/urls.py`, la page provisoire par le vrai tableau de bord (la variante « avant » utilise
`TemplateView`, la variante « après » importe `DashboardView`). Déclarez aussi l'application dans les réglages :

{{CONFIG}}

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

Les cinq tests qui échouaient au chapitre 21 (`test_web.py` : accueil, menu par rôle, déconnexion, chauffeur
renvoyé vers son espace) **passent enfin**.

**Dans le navigateur** : reconnectez-vous avec chacun des sept comptes (la MFA pour ADMIN et DIRECTION) et
comparez les tableaux de bord :

1. **`demo_direction`** : tous les blocs ; le **centre d'alertes** affiche par exemple le document d'un camion à
   renouveler, l'alerte de surconsommation du chapitre 24, l'incident éventuel.
2. **`demo_rh`** : effectif, absents du jour, demandes à valider.
3. **`demo_charge`** : clients actifs, réclamations, top 3.
4. **`demo_parcauto`** : exploitation, alertes de documents, de stock, de carburant.
5. **`demo_finances`** : finances du mois, factures échues.
6. Le **menu** de chacun ne contient que ses écrans, et **tous existent maintenant**.

## Ce qu'il faut retenir

- Une page de synthèse **n'invente aucune règle** : elle appelle celles des autres apps.
- Les **droits** se réutilisent par **import** plutôt que de se recopier.
- Un **cache court** sur les blocs coûteux, **aucun cache** sur ce qui est urgent.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 26 : tableau de bord par rôle (centre d'alertes, indicateurs)"
```
