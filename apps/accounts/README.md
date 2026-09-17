# accounts

Rôle : authentification et 7 rôles utilisateurs (ADMIN, DIRECTION, RH,
CHARGE_CLIENTELE, PARCAUTO, FINANCES, CHAUFFEUR) — cahier-des-charges.md:44-55.
Dépend uniquement de `core` (architecture.md:134).

Entités principales : `User` (custom, `AUTH_USER_MODEL`), `Role` — à créer
à l'étape 1.
