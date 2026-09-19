# api

Rôle : API REST versionnée `/api/v1/` — cahier-des-charges.md:250, 267, 275 ; architecture.md, ADR-007.
Couche haute : elle lit les mêmes services et applique les mêmes rôles que les écrans.

**Authentification** (`auth.py`, JWT via simplejwt) :
- `POST /api/v1/auth/token/` : identifiant + mot de passe → jeton d'accès (15 min) et de renouvellement (7 jours) ;
- `POST /api/v1/auth/token/refresh/` : nouveau couple ; l'ancien renouvellement est révoqué ;
- `POST /api/v1/auth/logout/` : révoque le renouvellement ; `GET /api/v1/moi/` : profil et rôle.
La connexion est limitée à 10 essais par minute et par adresse (anti force brute). Connexions et
déconnexions sont inscrites au journal d'audit comme celles du site.

**Ressources en lecture seule** (`v1/`) : `missions`, `camions`, `chauffeurs`, `clients`, `factures`
(liste paginée par 20, détail, filtres). Chaque ressource réutilise le queryset du service de l'écran
correspondant et son ensemble `permissions.CONSULTATION` : un rôle n'obtient pas par l'API ce que
l'écran lui refuse. Les champs sont listés un à un (jamais `__all__`) ; **les codes secrets des
missions n'apparaissent jamais**. La recherche `q` ignore accents et casse, comme à l'écran.
Les écritures restent sur les écrans web.

**Erreurs** (`exceptions.py`) : les exceptions métier des services deviennent `{"code", "detail"}` :
400 règle refusée, 403 droit insuffisant, 404 mission introuvable, 409 saisie de plein suspecte.

**Documentation** : `/api/v1/docs/` (Swagger) et `/api/v1/schema/` (OpenAPI), réservées à l'ADMIN
et à la DIRECTION connectés. CORS limité à `/api/` et aux domaines de `CORS_ALLOWED_ORIGINS`.

Pas encore fait : écriture depuis l'API bureau, MFA à la connexion (étape 7), limitation de débit au
niveau du serveur web (étape 7), pagination par curseur.
