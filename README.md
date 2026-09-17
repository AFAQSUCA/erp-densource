# ERP DEN Source Group

Gestion intégrée transport & logistique — voir [cahier-des-charges.md](cahier-des-charges.md)
(source de vérité), [architecture.md](architecture.md), [conventions.md](conventions.md),
[glossaire-metier.md](glossaire-metier.md), [audit-checklist.md](audit-checklist.md).

## Démarrage (dev)

```bash
python -m venv .venv
./.venv/Scripts/pip install -r requirements/dev.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

## Structure

- `config/settings/` : `base.py` / `dev.py` / `test.py` / `prod.py`
- `apps/` : une app Django par domaine métier (cahier-des-charges.md:259-261)
- `requirements/` : dépendances par environnement

## Avancement (phases CDC §5)

- [x] Étape 0 — Squelette Django (settings, apps vides core/accounts/audit)
- [ ] Étape 1 — Fondations (BaseModel, User + rôles, AuditLog)
- [ ] Étape 2 — Référentiels (hr, drivers, customers, fleet)
- [ ] Étape 3 — Exploitation (missions, fuel, garage, inventory)
- [ ] Étape 4 — Finance (billing, finance)
- [ ] Étape 5 — Pilotage (dashboard, notifications)
- [ ] Étape 6 — API (api/v1, mobile_api)
- [ ] Étape 7 — Tests & déploiement
