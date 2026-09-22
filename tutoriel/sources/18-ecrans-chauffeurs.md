## Ce que vous allez construire

Les **écrans des chauffeurs**, réservés à l'ADMIN, à la DIRECTION et à la RH.

| Écran | Adresse | Ce qu'on y fait |
|---|---|---|
| Liste | `/chauffeurs/` | filtrer par statut, par texte, ou par « permis / visite à renouveler » |
| Fiche | `/chauffeurs/<id>/` | voir l'état du **permis** et de la **visite médicale** (alerte à 30 jours), le statut, les congés |
| Modifier | `/chauffeurs/<id>/modifier/` | téléphone, contact d'urgence, permis, catégories, dates d'expiration |
| Changer le statut | `/chauffeurs/<id>/statut/` (POST) | **suspendre**, **désactiver** ou **réactiver** |

Deux règles à retrouver dans l'interface : « En mission » et « En congé » **ne se choisissent pas à la main**
(le système les pose), et le matricule, le nom et le prénom **ne se modifient pas ici** (ils viennent de la
fiche du personnel).

## Prérequis

- Chapitres 1 à 17 terminés.

## Ce que ce chapitre réutilise

Rien de nouveau côté technique : les **quatre motifs** du chapitre 17 (liste, fiche, formulaire, action POST).
Regardez comment ils s'appliquent ici :

- `ChauffeurListView` : liste filtrée, en appelant `services.rechercher_chauffeurs`.
- `ChauffeurDetailView` : `services.etat_echeances` calcule l'état du permis et de la visite.
- `ChauffeurUpdateView` : formulaire qui appelle `services.modifier_chauffeur`.
- `StatutView` : **action POST** qui appelle `services.changer_statut_manuel` ; son formulaire de confirmation
  porte `data-confirm`.

## Étape 1 — Formulaires, vues, adresses

{{FICHIER apps/drivers/forms.py}}

{{FICHIER apps/drivers/views.py}}

{{FICHIER apps/drivers/urls.py}}

Montez les adresses :

{{CONFIG}}

## Étape 2 — Gabarits

```bash
mkdir -p apps/drivers/templates/drivers
```

{{FICHIER apps/drivers/templates/drivers/chauffeur_list.html}}

{{FICHIER apps/drivers/templates/drivers/chauffeur_detail.html}}

{{FICHIER apps/drivers/templates/drivers/chauffeur_form.html}}

## Étape 3 — Tests et compilation des styles

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

Ce fichier de tests appartient à `hr` mais il ouvre aussi les pages des chauffeurs (la fiche d'un employé
chauffeur renvoie vers sa fiche chauffeur) : c'est pourquoi il n'apparaît qu'ici.

**Dans le navigateur** (`python manage.py runserver`) :

1. Connectez-vous avec **`demo_rh`** : le menu affiche **Personnel**, **Congés** et **Chauffeurs**.
2. Ouvrez **Chauffeurs**, cliquez sur `Moussa Ouattara`. Cliquez **Modifier** et saisissez une **date
   d'expiration du permis dans 10 jours** : la fiche affiche « À renouveler » en orange ; la case « permis ou
   visite à renouveler » de la liste retrouve le chauffeur.
3. Cliquez **Suspendre** : une confirmation s'affiche (`data-confirm`), puis le statut passe à **Suspendu**.
   « Réactiver » le remet **Disponible**.
4. Connectez-vous avec `demo_charge` et essayez `/chauffeurs/` : **Accès refusé**.

## Ce qu'il faut retenir

- Ce qu'on **ne doit pas pouvoir faire** (poser « En mission » à la main) se traduit par un formulaire qui
  **ne propose pas** ces choix *et* par un service qui les **refuse** : la vue n'est jamais la seule défense.
- Les mêmes quatre motifs suffisent : un nouvel écran est surtout une question d'assemblage.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 18 : écrans des chauffeurs"
```
