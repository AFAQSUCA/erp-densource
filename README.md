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

## Interface web

Django Templates + Tailwind + Alpine.js + FontAwesome, chargés par CDN pour le
développement (à remplacer par un build avant la production). Les vues appellent
les `services.py` : aucune règle métier dans les vues.

```bash
python manage.py runserver   # puis http://localhost:8000
python manage.py createsuperuser   # un superutilisateur agit comme ADMIN
```

Modules disponibles : connexion / déconnexion, accueil, **missions** (liste, fiche,
création, cycle de vie complet), **flotte** (camions, fiche, documents réglementaires
avec alerte à 30 jours), **chauffeurs** (fiche, permis, visite médicale, suspension). Le menu et les actions dépendent du rôle ; chaque
app déclare ses entrées de menu dans son `AppConfig.ready()`
(`apps/accounts/navigation.py`).

Identité visuelle : couleurs du logo DEN Source Group (bordeaux `#8B0319`, orange
`#F28A14`), définies sous les noms `marque` et `accent` dans la configuration Tailwind de
`templates/base.html`. Images dans `static/img/`.

## Structure

- `config/settings/` : `base.py` / `dev.py` / `test.py` / `prod.py`
- `apps/` : une app Django par domaine métier (cahier-des-charges.md:259-261)
- `requirements/` : dépendances par environnement

## Avancement (phases CDC §5)

- [x] Étape 0 — Squelette Django (settings, apps vides core/accounts/audit)
- [x] Étape 1 — Fondations (BaseModel, User + rôles, AuditLog)
- [x] Étape 2a — Référentiels (hr, drivers, customers, fleet)
- [x] Étape 2b — Congés et recrutements (hr)
- [x] Étape 3 — Exploitation (missions, garage, inventory, fuel)
- [x] Interface web : connexion, mise en page, module missions
- [x] Interface web : flotte (camions, documents réglementaires)
- [x] Interface web : chauffeurs (fiche, permis, visite médicale, statut)
- [ ] Interface web : autres modules (carburant, garage, stock, congés, clients)
- [ ] Étape 4 — Finance (billing, finance)
- [ ] Étape 5 — Pilotage (dashboard, notifications)
- [ ] Étape 6 — API (api/v1, mobile_api)
- [ ] Étape 7 — Tests & déploiement
