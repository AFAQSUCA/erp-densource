# Cahier des Charges Fonctionnel et Technique
## ERP de Gestion Intégrée Transport & Logistique — DEN Source Group

> Source de vérité du projet. Toute décision technique ou métier
> doit être justifiée par une section de ce document.

---

## 1. CONTEXTE

- **Entreprise** : DEN Source Group, transport routier de marchandises.
- **Localisation** : Abidjan, Côte d'Ivoire.
- **Flotte** : 20 camions poids lourds (Mercedes-Benz, Renault, MAN, Volvo, DAF).
- **Effectif** : ~30 employés (Direction, exploitation, chargés clientèle,
  dispatcheurs, gestionnaires flotte, mécaniciens, magasiniers, comptables,
  chauffeurs).
- **Devise** : FCFA. **Langue** : Français.
- **Objectif** : ERP Métier Web Intégré sur-mesure centralisant les flux
  physiques, administratifs, documentaires et financiers.

### Problématique
- Dispersion des informations.
- Risques de pénalités (assurances, visites techniques, patentes, permis).
- Manque de visibilité sur coûts de revient.
- Surconsommations carburant non détectées.
- Délais d'émission de factures et suivi du recouvrement complexe.

---

## 2. PÉRIMÈTRE INCLUS

Authentification / Rôles / Journal d'audit · Gestion flotte camions ·
Gestion chauffeurs · Gestion clientèle · Missions & trajets ·
Portail mobile chauffeur · Carburant & consommation · Garage & maintenance ·
Stocks & pièces · Facturation & règlements · Gestion financière · RH ·
Tableau de bord & KPIs · Tableaux de bord par utilisateur.

---

## 3. MODULES FONCTIONNELS

### Module 1 — Authentification & Sécurité

**Rôles utilisateurs :**

| Rôle | Périmètre |
|---|---|
| **ADMIN** | Accès total, config, seuils d'alerte, création/suppression utilisateurs, journal d'audit complet, sauvegardes |
| **DIRECTION** | Vue exécutive (CA, marge nette, dispo flotte, alertes), création/affectation/suivi missions, gestion flotte + chauffeurs, accès financier (lecture + validation), lecture seule sur RH/Clientèle/Parc Auto |
| **RH** | Gestion complète employés (embauche, licenciement, contrats), congés/absences, dashboard RH. Pas d'accès financier ni clients |
| **CHARGE_CLIENTELE** | Portefeuille clients, historique, devis, réclamations, notes d'échange. Pas d'accès RH ni parc auto |
| **PARCAUTO** | Gestion technique véhicules, renouvellement pièces administratives, mouvements de stock, inventaires, OR |
| **FINANCES** | Validation factures, saisie dépenses/entrées, suivi trésorerie, indicateurs. Pas d'accès RH ni parc auto (sauf lecture factures) |
| **CHAUFFEUR** | Espace mobile restreint : missions assignées, check-list véhicule, saisie km/carburant, signalement incidents |

**Table `audit_log` :**

| Champ | Type | Description |
|---|---|---|
| id | BIGINT (PK) | Identifiant unique |
| date_heure | DATETIME | Horodatage automatique |
| utilisateur_id | FK | Utilisateur ayant effectué l'action |
| utilisateur_nom | VARCHAR | Nom (dénormalisé) |
| role | VARCHAR | Rôle au moment de l'action |
| action | ENUM | CREATE / UPDATE / DELETE / LOGIN / LOGOUT / VALIDATE |
| module | VARCHAR | RH, FINANCES, CLIENTELE, PARC_AUTO, MISSION… |
| entite | VARCHAR | Table/objet concerné |
| entite_id | BIGINT | ID de l'enregistrement modifié |
| ancienne_valeur | JSON | Valeur avant modification |
| nouvelle_valeur | JSON | Valeur après modification |
| adresse_ip | VARCHAR | IP source |
| user_agent | VARCHAR | Navigateur/appareil |
| statut | ENUM | SUCCESS / FAILED |

**Règles :**
- Enregistrement auto via triggers SQL ou middleware.
- **Immuabilité append-only** : aucune modification ni suppression.
- Actions tracées : créations sensibles, modifications critiques,
  suppressions, connexions/déconnexions, validations.
- Conservation ≥ 5 ans.
- Consultation ADMIN, lecture seule DIRECTION.
- Export CSV/PDF pour audits externes.

---

### Module 2 — Flotte & Camions

- **Fiche véhicule** : immatriculation unique, marque, modèle, année,
  n° châssis VIN, kilométrage compteur, capacité de charge (t),
  réservoir (L), chauffeur habituel.
- **Statuts** : `Disponible` · `En mission` · `En maintenance` ·
  `Immobilisé` · `Hors service`.
- **Documents réglementaires** : Carte Grise, Assurance, Visite Technique,
  Patente (dates délivrance + expiration).
- **Alerte préventive** : à 30 jours de l'expiration.
- **Recalcul auto du statut à la clôture d'un OR** :
  1. Si d'autres OR ouverts → `En maintenance`
  2. Si mission planifiée/en cours → `En mission`
  3. Si marqué Immobilisé/Hors service → conserver
  4. Sinon → `Disponible`

---

### Module 3 — Chauffeurs & Personnel Navigant

- Chauffeur = employé (extension de la fiche personnel).
- Matricule unique (source de vérité : table Personnel).
- Poste "Chauffeur" → crée automatiquement une fiche chauffeur liée.
- **Fiche chauffeur** : matricule, nom, prénom, téléphone, contact d'urgence.
- **Permis** : numéro, catégories (C, E), date expiration permis,
  date expiration visite médicale.
- **Statuts** : `Disponible` · `En mission` · `En congé` · `Suspendu` ·
  `Inactif`.

---

### Module 4 — Clients & Chargés Clientèle

- **Fiche client** : raison sociale, NCC/NIF, contact principal, téléphone,
  email, adresse/siège, chargé clientèle attitré, taux TVA applicable
  (défaut 18 %, 0 % si exonéré avec motif obligatoire).
- **Interactions commerciales** : appels, mails, réunions, demandes de devis,
  réclamations.

---

### Module 5 — Missions & Trajets

- **Création mission** : n° auto `MIS-2026-XXXX`, client, camion + chauffeur
  disponibles, lieux chargement/livraison, nature marchandise, poids (t),
  prix convenu (FCFA).
- **Codes** : code secret + QR pour l'expéditeur (récupération colis) ;
  code pour le destinataire (confirmation livraison).
- **Cycle de vie** : `Brouillon` → `Planifiée` → `Affectée` →
  `En cours [Départ → Colis récupéré]` → `Livrée` → `Clôturée & Validée`.
- **Démarrage** : camion + chauffeur passent `En mission` ;
  notification "en cours de route (départ)".
- **Récupération colis** : scan QR par l'expéditeur sur téléphone du
  chauffeur → "colis récupéré".
- **Livraison** : camion + chauffeur repassent `Disponible` ; km d'arrivée
  met à jour le compteur ; scan QR destinataire.
- **Espace mobile chauffeur** : version simplifiée tactile (missions, plein,
  panne, scan QR).

---

### Module 6 — Carburant & Consommation

- **Saisie plein** : date, camion, chauffeur, station, quantité (L),
  prix unitaire (FCFA), km compteur, n° ticket/reçu.
- **Formule** : `Conso (L/100 km) = (Litres ÷ (Km actuel − Km précédent)) × 100`
- **Alertes** :
  - 🟡 Jaune si écart > +20 % vs moyenne 3 derniers pleins
  - 🔴 Rouge si écart > +40 %
  - ⚠️ Alerte saisie si écart > ±60 %
- **Analyse** : conso moyenne par camion et par chauffeur.
- **Détection anomalie** : > 45 L/100 km ou < 20 L/100 km.

---

### Module 7 — Garage & Maintenance

- **OR** : n° `OR-2026-XXXX`, véhicule, type (`Curatif`, `Préventif`,
  `Diagnostic`, `Pneumatiques`), lieu (Garage interne DEN Source /
  Prestataire externe), motif/symptômes.
- **Statut camion** : ouverture OR → `En maintenance` ; clôture →
  recalcul auto.
- **Coûts** : main-d'œuvre + coût automatique des pièces utilisées.

---

### Module 8 — Stocks & Pièces Détachées

- **Magasin** : référence, désignation, catégorie, emplacement, quantité,
  seuil minimal, PUMP.
- **Mouvements** : Entrée (achat), Sortie (liée à un OR), Ajustement.
- **MAJ temps réel** à la validation d'un mouvement.

---

### Module 9 — Facturation & Dépenses

- **Facture** : n° `FACT-2026-XXXX`, client, mission rattachée, HT,
  TVA 18 %, TTC, date d'échéance.
- **TVA configurable 3 niveaux** : système (18 %), client (0 % export/ONG/
  convention), facture.
- Si TVA 0 % → motif d'exonération obligatoire (Export, ONG, Convention,
  Autre).
- **Règlements** : acomptes + solde. Modes : Virement, Chèque, Espèces,
  Mobile Money (Wave, Orange, MTN). Calcul du reste à recouvrer.
- **Dépenses** par catégorie (Péages, Entretien, Frais admin).

---

### Module 10 — Finances

- Trésorerie : entrées et sorties.
- Suivi flux : encaissements, décaissements, solde temps réel.
- Rapprochement bancaire (mouvements bancaires + caisse).
- Indicateurs : CA, charges, marge nette, créances, trésorerie.

---

### Module 11 — Ressources Humaines

- **Fiche personnel** : matricule, nom, prénom, poste, département
  (Exploitation, Parc Auto, Comptabilité, Commercial, Direction),
  date d'embauche, salaire de base (FCFA).
- **Recrutements** : matricule, nom, prénom, poste, département, type de
  contrat, date d'embauche, salaire de base.
- **Workflow congés 3 niveaux** :
  1. Demande employé (dates + motif)
  2. Validation N1 par le supérieur hiérarchique direct de l'employé ; le directeur valide lui-même (délai 48 h)
  3. Validation N2 RH (délai 24 h)
  4. Notification automatique employé
  5. Si chauffeur → statut `En congé`
- **Statuts congé** : `DEMANDE` → `VALIDATION_N1` → `APPROUVE` →
  `EN_COURS` → `TERMINE` (ou `REFUSE`).
- **Règles** : droit annuel de 2 semaines (12 jours ouvrables), plus jours exceptionnels accordés par la RH (motif obligatoire) ;
  décompte en jours ouvrables du droit ivoirien (hors dimanches et jours fériés) ; blocage si solde insuffisant ; alerte N1 si
  chauffeur a une mission sur la période ; annulation d'un congé approuvé uniquement par RH avec notification.

---

### Module 12 — Tableau de Bord Exécutif

- **Financier** : CA facturé du mois, total encaissé, charges du mois,
  marge nette.
- **Exploitation** : camions dispo / en mission / au garage ; conso moyenne
  globale (L/100 km).
- **Centre d'alertes** : assurances/permis expirants, pièces sous seuil,
  factures impayées échues.
- **Dashboards par rôle** :
  - RH : effectif, congés/absents
  - Finances : CA, flux, créances, marge nette
  - Chargé clientèle : clients actifs, satisfaction, réclamations,
    top 3 clients, contrats à renouveler
  - Chauffeur : course du jour, km parcouru, conso, état véhicule,
    prochaine mission

---

## 4. SPÉCIFICATIONS TECHNIQUES

### Stack
- **Backend** : Python 3.14 / Django 5.2.x (MVT, ORM sécurisé)
- **Base** : PostgreSQL 16+ (SQLite toléré en dev/démo)
- **Frontend** : HTML5, Tailwind CSS, Alpine.js, FontAwesome 6.5
- **Serveur** : Gunicorn / WSGI, Nginx
- **API** : DRF 3.15+, simplejwt 5.3+, django-filter 24+, drf-spectacular 0.27+
- **Cache/Queue** : Redis 7+, Celery 5.4+
- **PDF/QR** : WeasyPrint / ReportLab, qrcode + Pillow
- **Notifications** : Celery + Twilio / Firebase
- **Stockage** : S3 / MinIO
- **Conteneurisation** : Docker + Docker Compose
- **Monitoring** : Sentry + Prometheus

### Architecture Django
- Apps : `core`, `accounts`, `audit`, `fleet`, `drivers`, `customers`,
  `missions`, `fuel`, `garage`, `inventory`, `billing`, `finance`, `hr`,
  `notifications`, `api/v1`, `mobile_api`, `dashboard`
- Séparation : `views → serializers → services → models`
- Logique métier dans `services.py` (jamais dans les vues)
- Signals avec parcimonie ; `post_save` audit sur modèles sensibles
- Transactions atomiques sur missions, factures, OR
- Permissions granulaires par rôle et par objet
- API versionnée `/api/v1/…`
- Couverture de tests ≥ 70 % sur services critiques

### Sécurité
- Protection injection SQL via ORM
- CSRF + échappement XSS
- Mots de passe PBKDF2 (Argon2 recommandé)
- HTTPS/TLS obligatoire
- JWT (expiration courte + refresh) pour API mobile
- MFA obligatoire ADMIN et DIRECTION
- Rate limiting anti force brute
- Secrets via `.env`
- RBAC granulaire (rôle + objet)
- En-têtes HTTP : HSTS, X-Frame-Options, X-Content-Type-Options, CSP
- CORS restreint aux domaines connus
- Sauvegardes chiffrées et testées
- Soft delete sur données sensibles
- Journal d'audit append-only
- Sessions : 15 min mobile / 30 min desktop

### Performance
- Réponse < 500 ms (pages simples)
- Réponse < 2 s (dashboards complexes avec cache)
- Optimisation ORM (`select_related`, `prefetch_related`, `only`, `defer`)
- Cache Redis pour KPI
- Pagination obligatoire
- Index BDD sur colonnes de recherche
- Tâches async Celery (notifications, alertes, PDF)
- CDN Cloudflare
- Compression gzip
- Monitoring Sentry

### Compatibilité
- Chrome, Edge, Safari, Firefox (2 dernières versions)
- Responsive mobile-first
- PWA espace mobile chauffeur
- Fonctionnement hors ligne pour saisies chauffeur (sync différée)
- Accessibilité WCAG 2.1 AA
- Export PDF et Excel

---

## 5. ENGAGEMENTS FINANCIERS & PLANNING

- **Développement sur-mesure** : 4 600 000 FCFA HT
- **7 phases (18 semaines)** :

| Phase | Durée | Coût indicatif |
|---|---|---|
| P1 – Fondations (auth, audit, core) | 2 sem. | 500 000 FCFA |
| P2 – Référentiels (RH, chauffeurs, clients, flotte) | 3 sem. | 800 000 FCFA |
| P3 – Exploitation (missions, carburant, garage, stocks) | 4 sem. | 1 000 000 FCFA |
| P4 – Finance (facturation, trésorerie) | 3 sem. | 800 000 FCFA |
| P5 – Pilotage (dashboards, notifications) | 2 sem. | 500 000 FCFA |
| P6 – Mobile (API chauffeur) | 2 sem. | 500 000 FCFA |
| P7 – Tests & déploiement | 2 sem. | 500 000 FCFA |
| **Total** | **18 sem.** | **4 600 000 FCFA** |

- **Maintenance & hébergement** : 200 000 FCFA HT / mois (hébergement
  cloud, sauvegardes quotidiennes, assistance, corrections).

---

## 6. CRITÈRES DE VALIDATION / RECETTE

1. Les 20 camions et chauffeurs correctement configurés.
2. Une mission peut être créée, affectée, suivie sur téléphone et clôturée
   sans erreur.
3. Un plein de carburant calcule la conso exacte et remonte une anomalie en
   cas de surconsommation.
4. Un ordre de réparation bloque puis libère le camion au garage.
5. Une sortie de pièce met à jour le stock et déclenche une alerte si seuil
   bas atteint.
6. Une facture émise génère la créance client et l'écriture comptable
   équilibrée.
7. Les alertes de documents expirants s'affichent sur le tableau de bord
   principal.

---

*Fait à Abidjan, le 12 Septembre 2026 — Pour DEN Source Group*