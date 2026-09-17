# Conventions de Code — ERP DEN Source Group

> Ces règles s'appliquent à TOUT code produit ou modifié dans ce projet.

## 1. Style Python / Django

- **PEP 8** strict. Max 88 caractères par ligne.
- Formatage : `black`, tri imports : `isort`, lint : `ruff` ou `flake8`.
- Nommage :
  - Modules : `snake_case.py`
  - Classes : `PascalCase`
  - Fonctions / variables : `snake_case`
  - Constantes : `UPPER_SNAKE_CASE`
  - Modèles : singulier (`Vehicule`, `Mission`, `Facture`)
  - Tables BDD : `app_modele` en minuscules
- Docstrings obligatoires sur classes et fonctions publiques.
- Type hints obligatoires sur les services.

## 2. Architecture Django

- Ordre strict : `views → serializers → services → models`
- **Jamais** de logique métier dans `views.py` ou `serializers.py`.
- **Jamais** d'appel direct à un modèle depuis une vue : passer par un
  service.
- Utiliser `BaseModel` (dans `core/models.py`) pour tous les modèles
  métier (timestamps + soft delete + audit).
- Utiliser `transaction.atomic` sur toute opération multi-tables
  (missions, factures, OR).
- Migrations : une migration = un changement logique. Jamais éditer une
  migration appliquée.

## 3. Sécurité

- **Jamais** de secret dans le code → `.env` uniquement.
- **Jamais** de `DELETE` physique sur données sensibles → soft delete.
- RBAC granulaire : `permissions.py` dans chaque app.
- Contrôle au niveau objet via `DjangoObjectPermissions`.
- Validation systématique des entrées dans les serializers.
- Requêtes ORM uniquement (jamais de SQL brut non paramétré).
- MFA obligatoire pour ADMIN et DIRECTION.

## 4. Audit

- Journal `audit_log` **append-only**.
- Toute création/modification/suppression/validation sensible doit
  laisser une trace.
- Ne jamais modifier ni supprimer une ligne d'audit.
- Utiliser le signal `post_save` (via `apps/audit/signals.py`).
- Middleware pour LOGIN/LOGOUT et erreurs.

## 5. API

- Versioning obligatoire : `/api/v1/…`
- Serializers séparés : `XxxReadSerializer`, `XxxWriteSerializer`.
- Pagination obligatoire sur toutes les listes.
- Filtres via `django-filter`.
- Documentation : `drf-spectacular` (Swagger).
- Codes HTTP : 200/201/204/400/401/403/404/409/422/500.
- Réponses d'erreur normalisées (voir `core/exceptions.py`).

## 6. Modèles

- Héritent de `BaseModel` (sauf modèles techniques).
- `Meta.ordering` défini quand pertinent.
- Index sur colonnes de recherche fréquentes.
- Champs monétaires : `DecimalField`, jamais `FloatField`.
- Devise FCFA : `decimal_places=2` ou entier selon le contexte.
- Dates : `timezone.now()` (aware), jamais `datetime.now()`.

## 7. Tests

- Chaque service a ses tests unitaires.
- Chaque endpoint API a ses tests d'intégration.
- Nommage : `test_<comportement>_<condition>_<attendu>`.
- Factories : `factory_boy`.
- Couverture ≥ 70 % sur `services.py`.
- Commande : `pytest --cov=apps`.

## 8. Git / Commits

Format Conventional Commits :
feat(module): nouvelle fonctionnalité
fix(module): correction de bug
refactor(module): refonte sans changement de comportement
test(module): ajout/modification de tests
docs: documentation
chore: tâche de maintenance
Exemples :
feat(missions): ajout scan QR destinataire à la livraison
fix(fuel): corrige calcul L/100km quand km précédent = 0
test(hr): couvre workflow congés 3 niveaux

- 1 commit = 1 changement logique.
- Jamais de commit direct sur `main`.
- Branches : `feat/xxx`, `fix/xxx`, `hotfix/xxx`.

## 9. Anti-patterns à bannir

- ❌ Inventer une fonction/modèle inexistant.
- ❌ Réécrire un fichier entier sans demande explicite.
- ❌ Logique métier dans `views.py`.
- ❌ Ignorer les migrations après modif de modèle.
- ❌ Sauter les tests.
- ❌ Décider seul d'une règle métier ambiguë → demander confirmation.
- ❌ `print()` → utiliser `logging`.
- ❌ Secrets dans le code.
- ❌ `DELETE` physique sur données sensibles.
- ❌ Appel API externe sans timeout ni gestion d'erreur.

## 10. Performance

- `select_related` / `prefetch_related` obligatoires sur les listes.
- Jamais de requête dans une boucle (N+1).
- Cache Redis pour les KPI.
- Pagination obligatoire.
- Tâches lourdes en Celery (PDF, notifications, alertes).

## 11. Internationalisation

- Langue par défaut : `fr`.
- Toutes les chaînes visibles via `gettext_lazy`.
- Formats dates / devises localisés.

## 12. Documentation

- Chaque app a un `README.md` court (rôle + entités principales).
- Chaque service public a une docstring.
- Toute décision d'architecture va dans `docs/architecture.md`.
- Toute nouvelle règle métier va dans `docs/cahier-des-charges.md`
  (section concernée).