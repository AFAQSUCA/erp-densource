## Ce que vous allez construire

Les **écrans du stock de pièces** (Parc Auto : gestion ; Direction : lecture seule).

| Écran | Adresse | Ce qu'on y fait |
|---|---|---|
| Liste des articles | `/stock/` | recherche, catégorie, filtre « sous le seuil », **valeur totale du stock au PUMP** |
| Fiche d'un article | `/stock/articles/<id>/` | derniers mouvements, entrée d'achat, ajustement |
| Créer / modifier | `/stock/articles/nouveau/`, `…/<id>/modifier/` | la référence ne change plus après création |
| **Entrée** (achat) | `/stock/articles/<id>/entree/` (POST) | recalcule le PUMP |
| **Ajustement** (inventaire) | `/stock/articles/<id>/ajustement/` (POST) | **motif obligatoire** |
| Journal des mouvements | `/stock/mouvements/` | filtrable |
| **Sortie pour un OR** | `/stock/or/<id>/sortie/` (POST) | depuis la fiche d'un OR |
| Bloc « **Pièces utilisées** » | dans la fiche d'un OR (`/garage/<id>/`) | pièces, coût des pièces, coût total |

## Prérequis

- Chapitres 1 à 22 terminés.

## Ce que ce chapitre apporte de nouveau

- **Le second bloc attendu** : `_pieces_or.html` est enfin créé. La fiche d'un OR (chapitre 22) affiche
  automatiquement les pièces utilisées, avec leur formulaire de sortie, sans modification de `garage`.
- **Un message d'alerte** quand une sortie ou un ajustement fait atteindre le seuil minimal : `services` renvoie
  l'information, la vue en fait un `messages.warning`.
- **Le journal comme écran de lecture** : pas de formulaire, seulement filtres et liste.
- Les formulaires (`SortieForm`, `ArticleForm`, `EntreeForm`, `AjustementForm`) existent déjà (chapitre 11) : ce
  chapitre ne présente que les **vues, adresses et gabarits**.

## Étape 1 — Vues et adresses

{{FICHIER apps/inventory/views.py}}

{{FICHIER apps/inventory/urls.py}}

{{CONFIG}}

## Étape 2 — Gabarits

```bash
mkdir -p apps/inventory/templates/inventory
```

{{FICHIER apps/inventory/templates/inventory/article_list.html}}

{{FICHIER apps/inventory/templates/inventory/article_detail.html}}

{{FICHIER apps/inventory/templates/inventory/article_form.html}}

{{FICHIER apps/inventory/templates/inventory/mouvement_list.html}}

{{FICHIER apps/inventory/templates/inventory/_pieces_or.html}}

## Étape 3 — Tests et compilation des styles

{{RESTANTS}}

Trois fichiers de `notifications` (`test_services.py`, `test_views.py`) sont aussi présentés ici : la cloche et la
page des notifications se testent sur des pages complètes, et ces pages ont besoin du stock.

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

1. **`demo_parcauto`** : le menu affiche **Stock**. « Nouvel article » : référence `PN-0455`, désignation « Pneu
   315/80 R22.5 », **seuil 4** (si vous avez fait l'essai du chapitre 11, il existe déjà).
2. Sur la fiche, **Entrée d'achat** : 10 pièces à 1 000, puis 10 à 2 000 : le **PUMP** passe à 1 500 et la valeur
   totale du stock s'affiche sur la liste.
3. Ouvrez un **OR ouvert** (chapitre 22) : le bloc **Pièces utilisées** est apparu. Faites une **sortie de 17
   pièces** : il reste 3 pièces, **sous le seuil de 4** : un message d'alerte s'affiche et la **cloche de
   `demo_parcauto`** compte une notification.
4. Faites un **ajustement** sans motif : refusé (« motif obligatoire »). Avec un motif : accepté et tracé dans le
   journal des mouvements.
5. Essayez de faire une sortie sur un OR **clôturé** : refusée.

## Ce qu'il faut retenir

- Les **blocs fournis à d'autres pages** s'activent par simple présence du gabarit.
- Un service peut **renvoyer un avertissement** à la vue sans lever d'erreur : l'action a réussi, mais l'utilisateur
  doit le savoir.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 23 : écrans du stock (articles, mouvements, pièces d'un OR)"
```
