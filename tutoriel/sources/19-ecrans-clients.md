## Ce que vous allez construire

Les **écrans du portefeuille clients**.

| Écran | Adresse | Qui |
|---|---|---|
| Portefeuille (liste) | `/clients/` | ADMIN et CHARGE_CLIENTELE gèrent ; DIRECTION lit |
| Fiche client (avec historique commercial) | `/clients/<id>/` | idem |
| Créer / modifier | `/clients/nouveau/`, `/clients/<id>/modifier/` | ADMIN, CHARGE_CLIENTELE |
| Ajouter une interaction (appel, mail, réunion, devis, réclamation) | `/clients/<id>/interactions/` (POST) | ADMIN, CHARGE_CLIENTELE |

Fonctions à retrouver : filtres **« Mon portefeuille »** (les clients dont je suis le chargé attitré) et
**« Exonérés de TVA »**, dernière interaction et nombre de **réclamations** affichés dans la liste.

## Prérequis

- Chapitres 1 à 18 terminés.

## Ce que ce chapitre apporte de nouveau

Un **formulaire de filtre** (`FiltreClientsForm`) : plutôt que de lire `request.GET` à la main, on valide les
paramètres de l'adresse avec un vrai formulaire, ce qui ignore proprement une valeur inutilisable.

Et une page qui **héberge les blocs d'une autre app** : la fiche client affiche
`{% for section in sections %}…` : les **missions du client** seront fournies par `missions` au chapitre 21 (le
registre `DETAIL_CLIENT` du chapitre 7). Tant que ce chapitre n'existe pas, la fiche s'affiche sans ce bloc.

## Étape 1 — Formulaires, vues, adresses

{{FICHIER apps/customers/forms.py}}

{{FICHIER apps/customers/views.py}}

{{FICHIER apps/customers/urls.py}}

{{CONFIG}}

## Étape 2 — Gabarits

```bash
mkdir -p apps/customers/templates/customers
```

{{FICHIER apps/customers/templates/customers/client_list.html}}

{{FICHIER apps/customers/templates/customers/client_detail.html}}

{{FICHIER apps/customers/templates/customers/client_form.html}}

## Étape 3 — Tests et compilation des styles

Ce chapitre présente les tests de `customers` laissés de côté au chapitre 7 (ils ouvrent des pages).

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

1. Connectez-vous avec **`demo_charge`** : le menu affiche **Clients**.
2. « Nouveau client » : saisissez une **TVA à 0 %** **sans motif** : le formulaire refuse (le service lève
   `ClientError`, la vue l'affiche). Saisissez le motif « Export » : le client est créé.
3. Sur la fiche, **Ajouter une interaction** de type **Réclamation** : la liste affiche maintenant « 1
   réclamation » pour ce client.
4. Connectez-vous avec `demo_direction` : la fiche s'ouvre **sans** boutons de modification (lecture seule).

## Ce qu'il faut retenir

- On peut valider les **paramètres d'une adresse** (les filtres) avec un formulaire, comme n'importe quelle saisie.
- Une fiche peut afficher des blocs de **modules qu'elle ne connaît pas** grâce aux registres.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 19 : écrans des clients"
```
