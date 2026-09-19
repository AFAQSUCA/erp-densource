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
avec alerte à 30 jours), **chauffeurs** (fiche, permis, visite médicale, suspension), **garage** (ordres de
réparation avec pièces et coût, immobilisation et remise en service des camions),
**stock** (articles, valeur au PUMP, entrées d'achat, ajustements, alerte de seuil, journal), **carburant** (pleins, alertes de surconsommation, analyse par
camion et par chauffeur), **clients** (portefeuille, fiche, TVA, historique commercial,
missions du client), **personnel** (fiche, recrutement, hiérarchie, jours de congé
exceptionnels) et **congés** (demande, validation N1 puis N2, annulation, alerte mission).
Le menu et les actions dépendent du rôle ; chaque
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
- [x] Interface web : garage (OR, pièces utilisées, immobilisation, remise en service)
- [x] Interface web : stock (articles, entrées, ajustements, journal, alerte de seuil)
- [x] Interface web : carburant (pleins, alertes, confirmation des saisies suspectes, analyse)
- [x] Interface web : clients (portefeuille, fiche, interactions)
- [x] Interface web : personnel, recrutement et congés (workflow 3 niveaux)
- [x] Étape 4 — Finance (facturation, règlements, dépenses, trésorerie) : sans écritures comptables ni rapprochement bancaire (voir apps/billing/README.md)
- [x] Étape 5 — Pilotage (tableau de bord par rôle, notifications) : sans les indicateurs financiers (étape 4) ni Celery / SMS / push (voir apps/notifications/README.md)
- [x] Étape 6 — API (api/v1 en lecture seule, API et espace mobile du chauffeur, codes QR) : sans mode hors ligne (voir apps/mobile_api/README.md)
- [ ] Étape 7 — Tests & déploiement

## Tableau de bord et notifications

La page d'accueil est le **tableau de bord** de chaque rôle (exploitation, centre d'alertes,
RH, clientèle). La **cloche** de l'en-tête compte les notifications non lues. Pour lancer les
alertes du jour (documents et permis à 30 jours, rappels de validation, statuts des congés) :

```bash
python manage.py taches_quotidiennes   # rejouable : aucune alerte en double
```

Les e-mails de notification s'affichent dans la console en développement ; en production,
réglez `NOTIFICATIONS_EMAIL=True`, `NOTIFICATIONS_URL_BASE` et l'envoi d'e-mails de Django.
Comptes d'essai : `python manage.py creer_comptes_demo`.

## Facturation et finances

`/facturation/` (factures, dépenses) et `/finances/` (trésorerie). Une facture se prépare depuis une
mission livrée (FINANCES), se valide par la DIRECTION (numéro `FACT-AAAA-XXXX`), puis s'encaisse par
acomptes et solde. Les indicateurs du mois (CA, encaissé, charges, marge, créances, trésorerie) et les
factures échues apparaissent au tableau de bord. Mentions de l'émetteur sur la facture imprimable :
`ENTREPRISE_NOM`, `ENTREPRISE_ADRESSE`, `ENTREPRISE_NCC`.

## API et espace chauffeur

- **API** : `/api/v1/` (JWT). Connexion : `POST /api/v1/auth/token/`. Documentation interactive pour
  l'ADMIN et la DIRECTION : `/api/v1/docs/`. Variable d'environnement : `CORS_ALLOWED_ORIGINS`.
- **Espace chauffeur** : `/chauffeur/`, à ouvrir sur un téléphone puis « Ajouter à l'écran d'accueil ».
  Un compte de rôle CHAUFFEUR arrive directement dessus après sa connexion.
- **Codes QR** : sur la fiche d'une mission, l'expéditeur et le destinataire disposent de leur code et
  de son QR ; le chauffeur le scanne pour confirmer la récupération puis la livraison.
