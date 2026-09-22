## Ce que vous allez construire

L'**API REST**, sous `/api/v1/` : la porte d'entrée pour d'autres logiciels (une application native, un partenaire).

| Route | Rôle |
|---|---|
| `POST /api/v1/auth/token/` | identifiant + mot de passe (+ code `otp` pour ADMIN et DIRECTION) → **jeton d'accès (15 min)** et **jeton de renouvellement (7 jours)** |
| `POST /api/v1/auth/token/refresh/`, `/auth/logout/` | renouveler, se déconnecter (le jeton de renouvellement est **révoqué**) |
| `GET /api/v1/moi/` | qui suis-je ? (rôle, chauffeur) |
| `GET /api/v1/missions/`, `camions/`, `chauffeurs/`, `clients/`, `factures/` | **lecture seule**, paginée par 20, filtres, recherche |
| `/api/v1/mobile/…` | l'**API du chauffeur** (chapitre 27) : ses missions, démarrer, récupérer, livrer, plein, check-list, incident |
| `GET /api/v1/docs/`, `/schema/` | documentation interactive (Swagger) et schéma OpenAPI : **ADMIN et DIRECTION** connectés |

Garanties : un rôle **n'obtient pas par l'API ce que l'écran lui refuse** ; les **codes secrets des missions n'y
figurent jamais** ; les erreurs métier deviennent des réponses `{"code", "detail"}` (400, 403, 404, 409).

## Prérequis

- Chapitres 1 à 27 terminés.

## Notions Django REST Framework (DRF)

- **Sérialiseur** (`Serializer`) : transforme un objet en **JSON** (et inversement). On y **liste chaque champ**
  exposé : jamais `fields = "__all__"`, pour ne pas révéler une colonne ajoutée plus tard.
- **`ViewSet`** : une classe qui regroupe liste et détail d'une ressource ; `ReadOnlyModelViewSet` n'expose que la
  lecture. Un **routeur** (`SimpleRouter`) fabrique les adresses.
- **Filtres** (`django-filter`) : `FilterSet` déclare les paramètres acceptés (`?statut=LIVREE&q=ciment`).
- **Permissions DRF** : une classe qui décide si la requête passe. Ici on **réutilise** les ensembles de rôles de
  chaque app (`CONSULTATION`) : un seul endroit à changer.
- **Authentification JWT** (`simplejwt`) : après connexion, le client présente `Authorization: Bearer <jeton>`.
  Un jeton d'accès **court** (15 minutes) limite les dégâts en cas de vol.
- **Limitation de débit** (*throttling*) : `ScopedRateThrottle` avec la portée `connexion` (10 essais par minute).
- **Gestionnaire d'exceptions** : traduit nos exceptions métier (`MissionError`, `SaisieSuspecte`…) en codes
  HTTP lisibles.
- **OpenAPI / Swagger** (`drf-spectacular`) : la documentation est **générée** depuis le code.
- **CORS** : n'autoriser que des domaines connus (`CORS_ALLOWED_ORIGINS`), et seulement pour `/api/`.

## Étape 1 — Créer l'application

```bash
mkdir -p apps/api/v1 apps/api/tests
```

{{VIDES}}

## Étape 2 — Erreurs, droits, connexion

{{FICHIER apps/api/exceptions.py}}

{{FICHIER apps/api/permissions.py}}

{{FICHIER apps/api/auth.py}}

`ConnexionSerializer` ajoute au formulaire de connexion de `simplejwt` le champ `otp`. Pour un ADMIN ou une
DIRECTION : compte sans MFA activée → `401 mfa_non_activee` ; sans code → `401 mfa_requise` ; code faux → `401
mfa_invalide` (et inscription au journal d'audit) ; 5 codes faux → `429`. Le nouveau jeton est délivré **seulement**
si tout est bon. Les erreurs d'authentification sont aussi comptées par l'anti force brute du chapitre 3.

{{FICHIER apps/api/apps.py}}

## Étape 3 — Les ressources

{{FICHIER apps/api/v1/serializers.py}}

{{FICHIER apps/api/v1/filters.py}}

{{FICHIER apps/api/v1/views.py}}

Chaque `ViewSet` **réutilise le queryset du service** de l'écran correspondant (la même règle de soft delete, de
recherche) et l'ensemble de rôles `CONSULTATION` de son app.

{{FICHIER apps/api/urls.py}}

{{RESTANTS}}

Ce chapitre présente aussi plusieurs fichiers de tests qui ont besoin de l'API : les tests de la
**double authentification** et de l'**anti force brute** (`accounts/tests/test_mfa.py`,
`test_securite_connexion.py`), ceux de la **politique de sécurité du contenu** (`core/tests/test_csp.py`) et ceux de
l'**API mobile** (`mobile_api/tests/test_api.py`).

## Étape 4 — Brancher dans les réglages et les adresses

{{CONFIG}}

Les réglages `REST_FRAMEWORK`, `SIMPLE_JWT`, `SPECTACULAR_SETTINGS` et `CORS_…` étaient déjà écrits au chapitre 1 ;
il ne restait qu'à **déclarer l'app** et à **monter** les adresses.

```bash
cd frontend
npm run build:css
cd ..
```

(La compilation finale est **nécessaire** : un test du chapitre vérifie que les couleurs de la marque figurent dans
le fichier de styles.)

## Vérifier le chapitre

```bash
python manage.py check
```

{{PYTEST}}

**Essayez l'API à la main** (avec `python manage.py runserver` dans un autre terminal). Le compte `demo_chauffeur`
n'est pas soumis à la MFA :

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/token/ -H "Content-Type: application/json" -d '{"username": "demo_chauffeur", "password": "VOTRE_MOT_DE_PASSE"}'
```

**Résultat attendu :** un JSON `{"refresh": "…", "access": "…"}`. Puis (en remplaçant `<ACCES>`) :

```bash
curl -s http://localhost:8000/api/v1/moi/ -H "Authorization: Bearer <ACCES>"
curl -s http://localhost:8000/api/v1/mobile/missions/ -H "Authorization: Bearer <ACCES>"
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/missions/ -H "Authorization: Bearer <ACCES>"
```

**Résultats attendus :** le profil (`role: CHAUFFEUR`), la liste des missions du chauffeur, puis **`403`** : un chauffeur n'a
pas accès aux missions du bureau.

Avec un compte **ADMIN** ou **DIRECTION** : sans `otp`, la même requête donne `401` avec
`"code": "mfa_requise"` ; avec `"otp": "123456"` (le code de votre application) elle donne les jetons.

**La documentation :** ouvrez **http://localhost:8000/api/v1/docs/** connecté en tant que `demo_direction` (avec sa
double authentification) : l'interface Swagger liste toutes les routes, et **vous pouvez les essayer** depuis la
page.

## Ce qu'il faut retenir

- Une API **n'a pas ses propres règles** : elle expose les **services** existants avec les **mêmes rôles**.
- On **liste les champs** exposés ; on n'expose jamais un modèle entier.
- Une **authentification forte** (MFA) doit aussi protéger l'API, pas seulement les écrans.
- La documentation se **génère** : elle ne peut pas mentir sur le code.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 28 : API REST (JWT + MFA, ressources en lecture seule, documentation)"
```
