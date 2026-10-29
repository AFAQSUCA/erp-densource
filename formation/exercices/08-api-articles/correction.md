# Correction — Exercice 8

| Fichier | Ajout |
|---|---|
| `apps/api/v1/serializers.py` | `ArticleSerializer` : les 7 champs du modèle en lecture seule, plus `sous_seuil` (`SerializerMethodField`) avec **la même règle** que `inventory.services.articles_sous_seuil` : seuil supérieur à 0 et quantité au seuil ou en dessous |
| `apps/api/v1/filters.py` | `ArticleFilter` : `q` réutilise `rechercher_articles` (comme les autres ressources) ; `alerte` est un `CharFilter` qui ne filtre que pour la valeur `"1"`, la convention des écrans |
| `apps/api/v1/views.py` | `ArticleViewSet(ReadOnlyModelViewSet)` : `role_requis(inventory_permissions.CONSULTATION)`, queryset `rechercher_articles()`, tags de documentation « stock » |
| `apps/api/urls.py` | `routeur.register("articles", views.ArticleViewSet, basename="article")` |

**Pourquoi un `CharFilter` ?** Un `BooleanFilter` attend `true`/`false` : avec `?alerte=1`, il ne filtre rien, et le
test qui l'utilise renvoie les deux articles. Plutôt que de demander à l'API une autre convention que l'écran, le
filtre lit la même.

**`ReadOnlyModelViewSet`** ne fournit que la liste et le détail : POST, PUT et DELETE répondent 405 sans rien
écrire de plus.

Pas de changement à `architecture.md` : l'API dépendait déjà de `inventory` (le test d'architecture l'aurait
signalé sinon).

**Vérification** : les 10 tests de l'exercice passent, et la suite complète aussi (3 427 tests).
