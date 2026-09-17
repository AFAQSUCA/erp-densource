# Architecture Technique — ERP DEN Source Group

> Document d'architecture au format C4 (Context → Containers →
> Components → Code) + vues dynamiques, données, déploiement,
> sécurité, observabilité.

---

## 1. VUE CONTEXTE (C4 Niveau 1)

Qui utilise le système, et avec quels systèmes externes il interagit.

```mermaid
C4Context
    title Contexte — ERP DEN Source Group

    Person(admin, "Administrateur", "Configure l'ERP, gère les accès")
    Person(direction, "Direction", "Pilotage stratégique")
    Person(rh, "RH", "Gestion du personnel et des congés")
    Person(commercial, "Chargé clientèle", "Clients, devis, réclamations")
    Person(parc, "Parc Auto", "Flotte, garage, stocks")
    Person(finance, "Finances", "Facturation, trésorerie")
    Person(chauffeur, "Chauffeur", "Missions terrain (mobile)")

    System(erp, "ERP DEN Source Group", "Gestion intégrée transport & logistique")

    System_Ext(paiement, "Mobile Money", "Wave, Orange Money, MTN")
    System_Ext(sms, "Passerelle SMS/Push", "Twilio / Firebase")
    System_Ext(cloud, "Cloud / S3", "Stockage + sauvegardes")
    System_Ext(monitoring, "Sentry / Prometheus", "Monitoring")

    Rel(admin, erp, "Configure, audite")
    Rel(direction, erp, "Consulte KPIs, valide")
    Rel(rh, erp, "Gère employés, congés")
    Rel(commercial, erp, "Gère clients, missions")
    Rel(parc, erp, "Gère flotte, OR, stock")
    Rel(finance, erp, "Facture, encaisse")
    Rel(chauffeur, erp, "Saisit missions, plein, pannes (PWA)")

    Rel(erp, paiement, "Initie encaissements")
    Rel(erp, sms, "Notifie (async)")
    Rel(erp, cloud, "Stocke fichiers / backups")
    Rel(erp, monitoring, "Envoie logs / métriques")
```

---

## 2. VUE CONTENEURS (C4 Niveau 2)

Les grandes briques techniques et leurs interactions.

```mermaid
C4Container
    title Conteneurs — ERP DEN Source Group

    Person(user, "Utilisateur", "Web ou mobile")
    Person(driver, "Chauffeur", "PWA mobile")

    Container_Boundary(erp, "ERP") {
        Container(web, "Frontend Web", "Django Templates + Tailwind + Alpine.js", "UI desktop/tablette")
        Container(pwa, "PWA Chauffeur", "Service Worker + Cache API", "Mode offline + sync différée")
        Container(api, "API REST", "Django REST Framework", "Endpoints /api/v1/")
        Container(admin, "Admin Django", "Django Admin", "Back-office technique")
        Container(mobile, "Mobile API", "DRF + JWT", "Endpoints dédiés chauffeur")
        Container(services, "Couche Services", "Python (services.py)", "Logique métier")
        Container(workers, "Workers Celery", "Celery", "Tâches async, alertes, PDF")
        Container(beat, "Celery Beat", "Celery Beat", "Tâches planifiées (30j docs, KPI)")
    }

    ContainerDb(db, "PostgreSQL", "PostgreSQL 16", "Données métier + audit")
    ContainerDb(redis, "Redis", "Redis 7", "Cache + broker Celery")
    ContainerDb(storage, "Stockage objet", "S3 / MinIO", "PDF, exports, QR, photos")

    Rel(user, web, "HTTPS")
    Rel(user, admin, "HTTPS")
    Rel(driver, pwa, "HTTPS + offline")
    Rel(web, services, "Appels internes")
    Rel(pwa, mobile, "Sync différée")
    Rel(api, services, "Appels internes")
    Rel(mobile, services, "Appels internes")
    Rel(admin, services, "Appels internes")
    Rel(services, db, "ORM Django")
    Rel(services, redis, "Cache")
    Rel(services, workers, "Enqueue tâches")
    Rel(beat, workers, "Déclenche planifiées")
    Rel(workers, db, "Lecture/écriture")
    Rel(workers, storage, "Écrit PDF/QR")
    Rel(services, storage, "Lecture/écriture fichiers")
```

---

## 3. VUE COMPOSANTS (C4 Niveau 3) — par app Django

Chaque app a une responsabilité unique. Voici les dépendances autorisées.

```mermaid
graph TD
    subgraph Auth
        ACC[accounts<br/>User, Role, Permission]
    end

    subgraph Transverse
        CORE[core<br/>BaseModel, mixins, perms]
        AUDIT[audit<br/>AuditLog append-only]
        NOTIF[notifications<br/>Email/SMS/Push]
        DASH[dashboard<br/>KPIs, dashboards]
    end

    subgraph Référentiels
        HR[hr<br/>Personnel, congés]
        DRV[drivers<br/>Chauffeur]
        CUST[customers<br/>Client, interactions]
        FLEET[fleet<br/>Véhicule, documents]
    end

    subgraph Exploitation
        MISSION[missions<br/>Cycle de vie + QR]
        FUEL[fuel<br/>Plein, conso]
        GARAGE[garage<br/>OR, coûts]
        INV[inventory<br/>Articles, PUMP]
    end

    subgraph Finance
        BILL[billing<br/>Factures, TVA, règlements]
        FIN[finance<br/>Trésorerie, rapprochement]
    end

    subgraph API
        APIV1[api/v1]
        MOBAPI[mobile_api]
    end

    ACC --> CORE
    CORE --> AUDIT
    AUDIT --> NOTIF
    HR --> DRV
    DRV --> MISSION
    CUST --> MISSION
    FLEET --> MISSION
    MISSION --> FUEL
    MISSION --> BILL
    FUEL --> GARAGE
    GARAGE --> INV
    GARAGE --> FLEET
    BILL --> FIN
    FIN --> DASH
    FUEL --> DASH
    MISSION --> DASH
    FLEET --> DASH
    HR --> DASH
    CUST --> DASH
    APIV1 --> MISSION
    APIV1 --> BILL
    APIV1 --> CUST
    MOBAPI --> MISSION
    MOBAPI --> FUEL
    MOBAPI --> GARAGE
```

**Règle de dépendance** : une app ne peut dépendre que des apps situées
au-dessus d'elle dans ce graphe. Toute dépendance inverse est interdite
(évite les cycles).

---

## 4. VUE DONNÉES — Modèle conceptuel

### 4.1 Entités principales et relations

```mermaid
erDiagram
    USER ||--o{ AUDIT_LOG : "génère"
    USER }o--|| ROLE : "possède"

    PERSONNEL ||--o| CHAUFFEUR : "extension"
    CHAUFFEUR ||--o{ MISSION : "conduit"
    VEHICULE ||--o{ MISSION : "assure"
    CLIENT ||--o{ MISSION : "commande"
    MISSION ||--o| FACTURE : "facturée par"

    VEHICULE ||--o{ DOCUMENT_REGLEMENTAIRE : "possède"
    VEHICULE ||--o{ OR : "concerne"
    VEHICULE ||--o{ PLEIN : "consomme"
    CHAUFFEUR ||--o{ PLEIN : "déclare"

    OR ||--o{ MOUVEMENT_STOCK : "consomme"
    ARTICLE ||--o{ MOUVEMENT_STOCK : "concerne"

    FACTURE ||--o{ REGLEMENT : "réglée par"
    FACTURE ||--o{ LIGNE_FACTURE : "contient"
    REGLEMENT }o--|| MODE_PAIEMENT : "utilise"

    PERSONNEL ||--o{ CONGE : "demande"
    CONGE ||--o{ VALIDATION_CONGE : "validé par"

    CLIENT ||--o{ INTERACTION : "historise"
```

### 4.2 Description des entités clés

| Entité | Responsabilité | Contraintes clés |
|---|---|---|
| `Personnel` | Fiche employé (matricule unique) | Soft delete, audit |
| `Chauffeur` | Extension 1-1 de Personnel | Créé auto si poste = Chauffeur |
| `Vehicule` | Camion (VIN unique) | Statut recalculé à clôture OR |
| `DocumentReglementaire` | Carte Grise, Assurance, VT, Patente | Alerte 30j |
| `Client` | Fiche client (NCC/NIF unique) | TVA configurable 3 niveaux |
| `Mission` | N° `MIS-2026-XXXX` | Transaction atomique, QR codes |
| `Plein` | Saisie carburant | Calcul L/100 km + alertes |
| `OR` | Ordre de réparation | Bloque camion, consomme stock |
| `Article` | Pièce détachée | PUMP, seuil mini |
| `Facture` | N° `FACT-2026-XXXX` | TVA 3 niveaux, motif exonération |
| `Reglement` | Encaissement | 6 modes (Virement, Chèque, Espèces, Wave, Orange, MTN) |
| `Conge` | Workflow 3 niveaux | Statuts + blocage solde |
| `AuditLog` | Trace immuable | Append-only, JSON diff |

### 4.3 Règles de données

- **Aucune suppression physique** sur entités métier → soft delete
  (`is_deleted`, `deleted_at`, `deleted_by`).
- **Audit obligatoire** sur : Personnel, Chauffeur, Vehicule, Client,
  Mission, Facture, OR, Conge.
- **Transactions atomiques** sur : création mission, émission facture,
  clôture OR, validation congé.
- **Contraintes d'intégrité** :
  - `Mission.client_id` NOT NULL
  - `Facture.mission_id` NOT NULL (une facture = une mission)
  - `Reglement.facture_id` NOT NULL
  - `MouvementStock.or_id` NULL si Entrée, NOT NULL si Sortie

---

## 5. VUE DYNAMIQUE — Workflows critiques

### 5.1 Cycle de vie d'une mission

```mermaid
stateDiagram-v2
    [*] --> Brouillon
    Brouillon --> Planifiee : validation chargé clientèle
    Planifiee --> Affectee : camion + chauffeur assignés
    Affectee --> EnCours_Depart : chauffeur démarre
    EnCours_Depart --> EnCours_ColisRecupere : scan QR expéditeur
    EnCours_ColisRecupere --> Livree : scan QR destinataire
    Livree --> Cloturee : validation finale
    Cloturee --> [*]

    note right of EnCours_Depart
        Camion + chauffeur → En mission
    end note
    note right of Livree
        Camion + chauffeur → Disponible
        MAJ km compteur
    end note
```

### 5.2 Séquence — Démarrage d'une mission (mobile chauffeur)

```mermaid
sequenceDiagram
    autonumber
    participant C as Chauffeur (PWA)
    participant API as Mobile API
    participant S as MissionService
    participant F as FleetService
    participant D as DriverService
    participant A as AuditService
    participant N as NotificationService

    C->>API: POST /api/v1/missions/{id}/start
    API->>S: start_mission(mission_id, user)
    S->>S: Vérifie statut = Affectée
    S->>F: set_status(vehicule, "En mission")
    S->>D: set_status(chauffeur, "En mission")
    S->>S: Statut mission → En cours (départ)
    S->>A: log(action=UPDATE, entite=Mission)
    S->>N: notify("en cours de route (départ)")
    S-->>API: Mission mise à jour
    API-->>C: 200 OK + état mission
```

### 5.3 Séquence — Clôture d'un OR et recalcul statut camion

```mermaid
sequenceDiagram
    autonumber
    participant P as ParcAuto
    participant API as API REST
    participant G as GarageService
    participant F as FleetService
    participant I as InventoryService
    participant A as AuditService

    P->>API: POST /api/v1/or/{id}/close
    API->>G: close_or(or_id, costs)
    G->>G: Vérifie OR ouvert
    G->>I: Consomme pièces (sortie stock)
    I->>I: MAJ PUMP + niveau stock
    I-->>G: OK + alertes seuil bas
    G->>F: recalcul_statut(vehicule)
    Note over F: Algo CDC M2.e
    F->>F: OR ouverts ? → En maintenance
    F->>F: Mission prévue ? → En mission
    F->>F: Immobilisé/Hors service ? → conserver
    F->>F: Sinon → Disponible
    F-->>G: Nouveau statut
    G->>A: log(action=VALIDATE, entite=OR)
    G-->>API: OR clôturé
    API-->>P: 200 OK + statut camion
```

### 5.4 Séquence — Workflow congés (3 niveaux)

```mermaid
sequenceDiagram
    autonumber
    participant E as Employé
    participant N1 as Chef département
    participant RH as RH
    participant S as HRService
    participant D as DriverService
    participant N as NotificationService

    E->>S: Créer demande (dates + motif)
    S->>S: Vérifie solde congés
    alt Solde insuffisant
        S-->>E: 400 Blocage
    else Solde OK
        S->>N: Notifie N1 (délai 48h)
        alt Chauffeur avec mission sur la période
            S->>N: Alerte N1
        end
        N1->>S: Valider N1
        S->>N: Notifie RH (délai 24h)
        RH->>S: Valider N2
        S->>D: Si chauffeur → statut "En congé"
        S->>N: Notifie employé (approuvé)
    end
```

---

## 6. VUE DÉPLOIEMENT

```mermaid
graph TB
    subgraph "Internet"
        U[Utilisateurs Web]
        M[Chauffeurs Mobile]
    end

    subgraph "Edge"
        CDN[Cloudflare CDN + WAF]
    end

    subgraph "Serveur de production"
        NGINX[Nginx<br/>Reverse proxy + TLS]
        GUNI1[Gunicorn worker 1]
        GUNI2[Gunicorn worker 2]
        GUNI3[Gunicorn worker N]
        CELERY[Celery worker]
        BEAT[Celery beat]
    end

    subgraph "Services managés"
        PG[(PostgreSQL 16<br/>+ réplique lecture)]
        REDIS[(Redis 7<br/>Cache + broker)]
        S3[(S3 / MinIO<br/>Fichiers)]
    end

    subgraph "Observabilité"
        SENTRY[Sentry]
        PROM[Prometheus + Grafana]
    end

    U --> CDN
    M --> CDN
    CDN --> NGINX
    NGINX --> GUNI1
    NGINX --> GUNI2
    NGINX --> GUNI3
    GUNI1 --> PG
    GUNI2 --> PG
    GUNI3 --> PG
    GUNI1 --> REDIS
    GUNI2 --> REDIS
    GUNI3 --> REDIS
    GUNI1 --> S3
    CELERY --> PG
    CELERY --> REDIS
    CELERY --> S3
    BEAT --> REDIS
    GUNI1 --> SENTRY
    CELERY --> SENTRY
    NGINX --> PROM
```

**Environnements** :
| Env | Base | Cache | Usage |
|---|---|---|---|
| Dev | SQLite | LocMem | Poste développeur |
| Test | PostgreSQL éphémère | Redis local | CI/CD |
| Staging | PostgreSQL | Redis | Recette client |
| Prod | PostgreSQL + réplique | Redis cluster | Exploitation |

---

## 7. SÉCURITÉ EN PROFONDEUR (Défense en profondeur)

```mermaid
graph TB
    L1[1. Edge : Cloudflare WAF, rate limiting, DDoS]
    L2[2. Transport : HTTPS/TLS 1.3, HSTS]
    L3[3. Application : CSRF, XSS, CSP, CORS restreint]
    L4[4. Authentification : JWT + MFA ADMIN/DIRECTION]
    L5[5. Autorisation : RBAC + permissions objet]
    L6[6. Données : chiffrement au repos, soft delete]
    L7[7. Audit : append-only, conservation 5 ans]
    L8[8. Secrets : .env, rotation, jamais en clair]
    L9[9. Sauvegardes : chiffrées, testées, offsite]

    L1 --> L2 --> L3 --> L4 --> L5 --> L6 --> L7 --> L8 --> L9
```

**Points de contrôle par module** :

| Module | Contrôle principal |
|---|---|
| Auth | MFA + JWT + sessions 15/30 min |
| Missions | Transaction atomique + audit |
| Facturation | Rôle FINANCES + validation DIRECTION |
| RH | Rôle RH + audit sur congés |
| Audit | Append-only, consultation ADMIN |
| API mobile | JWT court + `IsChauffeur` + rate limit |

---

## 8. OBSERVABILITÉ

| Pilier | Outil | Quoi |
|---|---|---|
| **Logs** | Django logging + Sentry | Erreurs, exceptions, accès |
| **Métriques** | Prometheus + Grafana | Latence, throughput, erreurs 5xx |
| **Traces** | Sentry Performance | Requêtes lentes, N+1 |
| **Alerting** | Sentry + Grafana | Seuils (temps réponse, taux d'erreur) |
| **Audit** | Table `audit_log` | Qui a fait quoi, quand |

**SLO cibles** :
- Disponibilité : 99,5 %
- Latence p95 pages simples : < 500 ms
- Latence p95 dashboards : < 2 s
- Taux d'erreur 5xx : < 0,1 %

---

## 9. SCALABILITÉ & RÉSILIENCE

| Aspect | Stratégie |
|---|---|
| **Scalabilité horizontale** | Gunicorn multi-workers derrière Nginx |
| **Scalabilité BDD** | Index, réplique lecture, partitionnement audit_log par année |
| **Cache** | Redis pour KPI + sessions |
| **Async** | Celery pour notifications, PDF, alertes 30j |
| **Tolérance panne** | Healthchecks, redémarrage auto, retry Celery |
| **Sauvegardes** | Quotidiennes chiffrées + test restauration mensuel |
| **CDN** | Cloudflare pour réduire latence Afrique de l'Ouest |

---

## 10. DÉCISIONS D'ARCHITECTURE (ADR)

### ADR-001 — Django + DRF plutôt que FastAPI
- **Contexte** : besoin d'admin, ORM riche, auth intégrée.
- **Décision** : Django 5.2 + DRF.
- **Justification** : Admin Django accélère le back-office, ORM mature,
  écosystème Celery/PostgreSQL éprouvé.
- **Conséquence** : perf légèrement inférieure à FastAPI, compensée par
  cache Redis.

### ADR-002 — PostgreSQL plutôt que SQLite en prod
- **Contexte** : données relationnelles complexes + audit + concurrence.
- **Décision** : PostgreSQL 16.
- **Justification** : transactions, JSONB (audit), index avancés,
  réplication.
- **Conséquence** : SQLite toléré en dev uniquement.

### ADR-003 — Audit via middleware + signals plutôt que triggers SQL
- **Contexte** : traçabilité complète exigée (CDC M1).
- **Décision** : middleware applicatif + signals `post_save`.
- **Justification** : plus testable, capture aussi LOGIN/LOGOUT et
  contexte applicatif (user, IP, user-agent).
- **Conséquence** : nécessite discipline (couverture tests).

### ADR-004 — Celery + Redis pour les tâches async
- **Contexte** : alertes 30j, notifications, PDF, KPI lourds.
- **Décision** : Celery 5.4 + Redis 7.
- **Justification** : standard Django, support beat pour tâches
  planifiées.
- **Conséquence** : ajoute Redis à l'infra.

### ADR-005 — PWA chauffeur plutôt qu'app native
- **Contexte** : chauffeurs sur smartphones variés, budget maîtrisé.
- **Décision** : PWA avec Service Worker + cache offline.
- **Justification** : pas de store, une seule base de code, mode offline
  possible.
- **Conséquence** : limitations natives (pas de Bluetooth, etc.).

### ADR-006 — Soft delete généralisé
- **Contexte** : exigence CDC de ne jamais supprimer physiquement.
- **Décision** : `BaseModel` avec `is_deleted`, `deleted_at`,
  `deleted_by`.
- **Justification** : conformité, audit, restauration possible.
- **Conséquence** : tous les querysets doivent filtrer `is_deleted=False`.

### ADR-007 — API versionnée `/api/v1/`
- **Contexte** : évolution prévue (mobile, partenaires).
- **Décision** : versioning par URL.
- **Justification** : simplicité, cache, debug.
- **Conséquence** : discipline de non-régression sur v1.

---

## 11. CONTRAINTES & HYPOTHÈSES

**Contraintes** :
- Devise FCFA, langue FR.
- Connexion Internet variable (Côte d'Ivoire) → PWA offline + CDN.
- Budget 4,6 M FCFA HT, 18 semaines.
- 20 camions, ~30 employés (dimensionnement modéré).

**Hypothèses** :
- Un seul tenant (pas de multi-société).
- Un utilisateur = un rôle principal (RBAC simple).
- Chauffeurs équipés de smartphones Android récents.
- Wave/Orange/MTN exposent des API accessibles.

---

## 12. LIENS

- CDC : `docs/cahier-des-charges.md`
- Conventions : `docs/conventions.md`
- Glossaire : `docs/glossaire-metier.md`
- Checklist audit : `docs/audit-checklist.md`
- API : `docs/api.md`
- Déploiement : `docs/deployment.md`