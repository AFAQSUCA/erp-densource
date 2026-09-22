## Ce que vous allez construire

**`inventory`** : le **magasin de pièces détachées**, avec sa valeur.

| Élément | Règle |
|---|---|
| `Article` | référence unique, désignation, catégorie, emplacement, **quantité**, **seuil minimal** (0 = non surveillé), **PUMP** |
| **PUMP** | *prix unitaire moyen pondéré* : recalculé à chaque **entrée d'achat** ; chaque sortie est valorisée à ce prix |
| `MouvementStock` | le **journal des mouvements** : entrées (achat), sorties (liées à un **OR ouvert**), ajustements (**motif obligatoire**) |
| Alerte de seuil | quand un mouvement fait passer un article **au seuil ou en dessous**, un signal `seuil_bas_atteint` est émis |
| Coût d'un OR | main-d'œuvre + pièces sorties, calculé automatiquement |

Deux règles fortes : la **quantité** et le **PUMP** d'un article **ne changent que par un mouvement** (jamais à
la main), et le journal des mouvements est **immuable** : une erreur se corrige par un ajustement motivé.

## Prérequis

- Chapitres 1 à 10 terminés.

## Notions Django de ce chapitre

- **Le PUMP** : `(stock × PUMP actuel + quantité entrée × prix d'achat) / nouveau stock`. Exemple : 10
  pièces à 1 000 puis 10 pièces à 2 000 donnent un PUMP de 1 500.
- **Journal « append-only »** : `MouvementStock` n'est pas un `BaseModel` (pas de suppression logique) : on
  n'efface ni ne modifie jamais un mouvement.
- **Verrou sur l'article** pendant un mouvement : deux sorties simultanées ne peuvent pas rendre le stock
  négatif.
- **`ROUND_HALF_UP`** : l'arrondi « commercial » (0,5 arrondit vers le haut), au centime.
- **Un formulaire déjà présent dans la couche métier** : `forms.py` est ici présenté avec `inventory` (et non
  avec les écrans) parce que `sections.py` en a besoin **au démarrage** ; il ne dépend que de `core.forms`.
- **Sections** : `inventory` ajoute le bloc « Pièces utilisées » à la fiche d'un OR de `garage`.

## Étape 1 — Créer l'application

```bash
mkdir -p apps/inventory/tests
```

{{VIDES}}

## Étape 2 — Modèles

{{FICHIER apps/inventory/models.py}}

`Article` déclare `quantite` et `pump` **sans les rendre modifiables à la main** dans l'interface : seuls les
services les changent. `MouvementStock` garde, pour chaque mouvement, la variation (positive ou négative), le prix, le **stock après**
(pour retracer l'historique), l'auteur et, pour un ajustement, le **motif**.

## Étape 3 — Règles métier

{{FICHIER apps/inventory/exceptions.py}}

{{FICHIER apps/inventory/services.py}}

À lire :

1. **`creer_article`** : référence normalisée (majuscules), unique **même parmi les articles supprimés**. Un
   article naît à **stock nul** : le stock initial arrive par une entrée.
2. **`enregistrer_entree`** : recalcule le PUMP (formule ci-dessus, arrondie au centime).
3. **`sortir_pour_or`** : refuse un OR clôturé (`OrCloture`) et un stock insuffisant (`StockInsuffisant`) ;
   valorise la sortie au PUMP **du moment**.
4. **`ajuster_stock`** : corrige l'inventaire ; **le motif est obligatoire** (`MotifRequis`).
5. **`articles_sous_seuil`**, **`valeur_totale_stock`**, **`cout_pieces`**, **`cout_total`** : des lectures
   pour les écrans et le tableau de bord.

{{FICHIER apps/inventory/signals.py}}

{{FICHIER apps/inventory/permissions.py}}

{{FICHIER apps/inventory/forms.py}}

{{FICHIER apps/inventory/sections.py}}

Le bloc « Pièces utilisées » d'un OR, avec son formulaire de sortie. Il n'est visible que si le rôle a le droit
de consulter le stock.

## Étape 4 — Administration, démarrage, tests

{{FICHIER apps/inventory/admin.py}}

{{FICHIER apps/inventory/apps.py}}

{{FICHIER apps/inventory/tests/factories.py}}

{{RESTANTS}}

## Étape 5 — Déclarer l'application et migrer

{{CONFIG}}

```bash
python manage.py makemigrations inventory
python manage.py migrate
```

**Résultat attendu :** `Create model Article`, `Create model MouvementStock`, puis
`Applying inventory.0001_initial... OK`.

## Vérifier le chapitre

```bash
python manage.py check
```

{{PYTEST}}

Essai dans le shell : vérifier le calcul du PUMP.

```bash
python manage.py shell -c "from decimal import Decimal; from apps.inventory import services as s; a = s.creer_article(reference='pn-0455', designation='Pneu 315/80 R22.5', seuil_minimal=4); s.enregistrer_entree(a, quantite=10, prix_unitaire=Decimal('1000')); s.enregistrer_entree(a, quantite=10, prix_unitaire=Decimal('2000')); a.refresh_from_db(); print(a.reference, a.quantite, a.pump)"
```

**Résultat attendu :** `PN-0455 20 1500.00`.

## Ce qu'il faut retenir

- Une valeur **dérivée d'un historique** (quantité, PUMP) ne se modifie que **par un mouvement** ; l'historique
  est immuable, on corrige par un nouveau mouvement.
- Ce qu'on arrondit (l'argent) s'arrondit **une seule fois, au bon endroit**, avec la règle prévue.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 11 : app inventory (stock de pièces, PUMP, mouvements, seuils)"
```
