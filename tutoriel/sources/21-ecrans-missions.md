## Ce que vous allez construire

Les **écrans des missions** : le cycle de vie du chapitre 9, cliquable.

| Écran | Adresse | Qui |
|---|---|---|
| Liste (statut, recherche) | `/missions/` | ADMIN, DIRECTION, CHARGE_CLIENTELE |
| **Créer** une mission | `/missions/nouvelle/` | idem |
| **Fiche** avec la **frise du cycle de vie**, les actions possibles, les **codes et leurs QR** | `/missions/<id>/` | idem |
| Actions en POST : **planifier**, **affecter**, **démarrer**, **récupération**, **livraison**, **clôturer** | `/missions/<id>/planifier/`… | selon le rôle et le statut |
| Image QR d'un code | `/missions/<id>/qr/expediteur.png` (ou `destinataire`) | ADMIN, DIRECTION, CHARGE_CLIENTELE |

Deux blocs sont aussi **fournis à d'autres pages** par `missions` : l'alerte « ce chauffeur a une mission prévue
sur la période » (fiche d'un congé, chapitre 17) et la **liste des missions d'un client** (fiche client,
chapitre 19).

## Prérequis

- Chapitres 1 à 20 terminés.

## Ce que ce chapitre apporte de nouveau

- **Des actions dont la disponibilité dépend du rôle *et* du statut** : `permissions.actions_disponibles(utilisateur,
  mission)` (chapitre 9) renvoie un dictionnaire ; le gabarit n'affiche que les boutons dont la valeur est vraie.
  **Mais la vue re-vérifie** : masquer un bouton ne protège rien.
- **Une classe mère d'actions** (`ActionMissionView`) : chaque action (`planifier`, `démarrer`…) hérite d'un
  comportement commun (contrôle du droit, appel du service, message, redirection) et ne définit que ce qui change.
- **Un contenu qui n'est pas une page** : `CodeQrView` renvoie une **image PNG** fabriquée à la volée avec la
  bibliothèque `qrcode`. Elle est réservée aux rôles qui voient les codes, **jamais mise en cache**
  (`Cache-Control: no-store, private`), et l'image ne contient **que le code**.
- **Des codes montrés seulement tant qu'ils servent** : `permissions.codes_visibles`.
- **Des gabarits qui s'incluent dans d'autres apps** : `_alerte_conge.html` et `_missions_client.html` sont des
  *fragments* (leur nom commence par `_`) chargés par les registres de sections.

## Étape 1 — Formulaires, vues, adresses

{{FICHIER apps/missions/forms.py}}

{{FICHIER apps/missions/views.py}}

Repérez :

- **`MissionListView`** : filtre par statut et texte via `services.rechercher_missions`.
- **`MissionDetailView`** : calcule `actions`, `codes` (montrés selon le rôle et le statut), la frise, et les
  formulaires (affectation, code, livraison) à afficher.
- **`ActionMissionView`** et ses filles : une transition = une classe de quelques lignes.
- **`CodeQrView`** : l'image du code, avec les en-têtes de non-mise en cache.

{{FICHIER apps/missions/urls.py}}

{{CONFIG}}

## Étape 2 — Gabarits

```bash
mkdir -p apps/missions/templates/missions
```

{{FICHIER apps/missions/templates/missions/mission_list.html}}

{{FICHIER apps/missions/templates/missions/mission_form.html}}

{{FICHIER apps/missions/templates/missions/mission_detail.html}}

C'est le gabarit le plus riche du projet : la **frise** (`{% for … %}` sur les statuts), la colonne des
**actions**, et le cadre des **codes à communiquer** avec leur QR. Les formulaires d'action portent
`data-confirm` pour demander confirmation avant de démarrer ou clôturer.

{{FICHIER apps/missions/templates/missions/_alerte_conge.html}}

{{FICHIER apps/missions/templates/missions/_missions_client.html}}

## Étape 3 — Tests

{{RESTANTS}}

Ce chapitre présente de nombreux tests laissés plus tôt car ils ouvrent des pages qui dépendent des missions :
les tests de connexion et de menu par rôle (`accounts/test_web.py`), des fiches des clients et des chauffeurs
(qui affichent des missions), l'alerte de congé et les codes QR.

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

Les cinq tests de `accounts/test_web.py` qui dépendent du **tableau de bord** échouent encore : ils passeront au
chapitre 26 (c'est attendu).

**Un parcours complet dans le navigateur** (`python manage.py runserver`) :

1. **`demo_charge`** : « Nouvelle mission » (client `Cimaf CI`, Abidjan → Bouaké, ciment, 22 tonnes, 780 000).
   Sur la fiche (statut **Brouillon**), cliquez **Planifier**.
2. **`demo_direction`** : ouvrez la mission, **Affecter** : choisissez le camion `1234 AB 01` et le chauffeur
   `Moussa Ouattara`. Essayez d'affecter une mission de **30 tonnes** : le service refuse (capacité 25 t).
3. **Démarrer** la mission : le camion et le chauffeur passent « En mission » (vérifiez dans Flotte et Chauffeurs).
   La fiche affiche **deux codes de 8 caractères et leurs QR**.
4. **Récupération** : saisissez le **code de l'expéditeur** (un mauvais code est refusé). Puis **Livraison** avec le
   **code du destinataire** et un kilométrage d'arrivée : la mission passe **Livrée**, le camion redevient
   Disponible et son compteur est à jour.
5. **Clôturer** la mission (Direction).
6. Avec **`demo_parcauto`**, ouvrez `/missions/` : **Accès refusé**. Avec **`demo_charge`**, la mission n'affiche
   plus le bouton « Affecter » (réservé à la Direction).
7. Le journal d'audit (`/admin/audit/auditlog/`, en tant qu'**administrateur** avec la MFA) montre chaque
   transition, **sans** aucun code secret.

## Ce qu'il faut retenir

- **Le service décide, la vue re-vérifie, le gabarit affiche** : trois couches, une seule règle.
- Une **image** peut être servie par une vue ordinaire ; on lui applique les mêmes gardes que pour une page.
- Un secret montré à l'écran ne doit **jamais être mis en cache**.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 21 : écrans des missions (cycle de vie, actions, codes QR)"
```
