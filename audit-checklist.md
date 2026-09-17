# Checklist d'Audit & Recette — ERP DEN Source Group

> Utilisée par l'IA pour auditer la conformité du code au cahier des
> charges, puis pour la remédiation.

## Méthode d'audit

Pour chaque exigence, verdict :
- ✅ **Conforme** — implémenté et vérifiable
- 🟡 **Partiellement conforme** — implémenté mais incomplet
- ❌ **Non conforme** — absent
- ❓ **Non vérifiable** — preuve manquante
- ⚪ **Non applicable**

Justification obligatoire : `fichier:ligne` ou "NON TROUVÉ".

---

## M1 — Authentification & Sécurité

- [ ] 7 rôles définis (ADMIN, DIRECTION, RH, CHARGE_CLIENTELE, PARCAUTO,
      FINANCES, CHAUFFEUR)
- [ ] Permissions granulaires par rôle
- [ ] Permissions par objet
- [ ] Table `audit_log` avec les 14 champs du CDC
- [ ] Immuabilité append-only
- [ ] Traçabilité LOGIN / LOGOUT / CREATE / UPDATE / DELETE / VALIDATE
- [ ] Conservation ≥ 5 ans
- [ ] Consultation ADMIN + lecture seule DIRECTION
- [ ] Export CSV/PDF
- [ ] MFA pour ADMIN et DIRECTION

## M2 — Flotte & Camions

- [ ] Fiche véhicule complète (VIN, capacité, réservoir, chauffeur habituel)
- [ ] 5 statuts implémentés
- [ ] 4 documents réglementaires (Carte Grise, Assurance, Visite Technique,
      Patente)
- [ ] Alerte à 30 jours
- [ ] Recalcul statut à la clôture d'un OR (algorithme exact)

## M3 — Chauffeurs

- [ ] Extension de la fiche Personnel (matricule partagé)
- [ ] Création automatique si poste = Chauffeur
- [ ] Permis (n° + catégories C/E + expiration)
- [ ] Visite médicale (expiration)
- [ ] 5 statuts chauffeur
- [ ] Contact d'urgence

## M4 — Clients

- [ ] Fiche client (NCC/NIF, contact, adresse, chargé attitré)
- [ ] TVA configurable (18 % défaut, 0 % exonéré + motif)
- [ ] Interactions commerciales historisées (appels, mails, réunions,
      devis, réclamations)

## M5 — Missions

- [ ] N° auto `MIS-2026-XXXX`
- [ ] Cycle de vie complet (6 statuts)
- [ ] QR expéditeur (récupération)
- [ ] QR destinataire (livraison)
- [ ] Démarrage → camion + chauffeur `En mission`
- [ ] Livraison → retour `Disponible` + MAJ km
- [ ] Espace mobile chauffeur (missions, plein, panne, scan QR)

## M6 — Carburant

- [ ] Saisie plein (7 champs)
- [ ] Formule L/100 km exacte
- [ ] Alerte jaune > +20 %
- [ ] Alerte rouge > +40 %
- [ ] Alerte saisie > ±60 %
- [ ] Conso moyenne par camion et par chauffeur
- [ ] Détection anomalie (< 20 ou > 45 L/100 km)

## M7 — Garage

- [ ] N° auto `OR-2026-XXXX`
- [ ] 4 types (Curatif, Préventif, Diagnostic, Pneumatiques)
- [ ] Lieu (interne/externe)
- [ ] Ouverture → camion `En maintenance`
- [ ] Clôture → recalcul auto
- [ ] Coût main-d'œuvre + pièces auto

## M8 — Stocks

- [ ] Fiche article (référence, PUMP, seuil mini, emplacement)
- [ ] Mouvements Entrée / Sortie (liée OR) / Ajustement
- [ ] MAJ stock temps réel
- [ ] Alerte seuil bas

## M9 — Facturation

- [ ] N° auto `FACT-2026-XXXX`
- [ ] Rattachée à une mission
- [ ] TVA 3 niveaux
- [ ] Motif exonération obligatoire si 0 %
- [ ] Règlements : Virement, Chèque, Espèces, Wave, Orange, MTN
- [ ] Reste à recouvrer calculé
- [ ] Dépenses par catégorie

## M10 — Finances

- [ ] Trésorerie entrées/sorties
- [ ] Solde temps réel
- [ ] Rapprochement bancaire
- [ ] KPI (CA, charges, marge nette, créances, trésorerie)

## M11 — RH

- [ ] Fiche personnel complète
- [ ] Recrutement
- [ ] Workflow congés 3 niveaux (délais 48h + 24h)
- [ ] Statuts congé (5 + REFUSE)
- [ ] Blocage solde insuffisant
- [ ] Alerte N1 si mission en cours sur la période
- [ ] Annulation RH uniquement
- [ ] Si chauffeur → statut `En congé`

## M12 — Dashboards

- [ ] KPI financiers (CA mois, encaissé, charges, marge nette)
- [ ] KPI exploitation (dispo/en mission/garage, conso globale)
- [ ] Centre d'alertes (docs expirants, stock bas, factures impayées)
- [ ] Dashboard RH
- [ ] Dashboard Finances
- [ ] Dashboard Chargé clientèle (top 3, satisfaction, contrats)
- [ ] Dashboard Chauffeur

---

## Technique

### Stack
- [ ] Python 3.14 / Django 5.2.x
- [ ] PostgreSQL 16+ (SQLite dev toléré)
- [ ] DRF 3.15+ / simplejwt 5.3+
- [ ] Redis 7+ / Celery 5.4+
- [ ] Tailwind / Alpine.js / FontAwesome
- [ ] Gunicorn + Nginx
- [ ] Docker + Docker Compose

### Architecture
- [ ] 17 apps Django conformes à la structure
- [ ] `views → serializers → services → models`
- [ ] Logique métier dans `services.py`
- [ ] Transactions atomiques (missions, factures, OR)
- [ ] API versionnée `/api/v1/`
- [ ] Couverture tests ≥ 70 % sur services critiques

### Sécurité
- [ ] ORM anti-injection
- [ ] CSRF
- [ ] XSS
- [ ] Mots de passe PBKDF2/Argon2
- [ ] HTTPS/TLS
- [ ] JWT API mobile
- [ ] MFA ADMIN/DIRECTION
- [ ] Rate limiting
- [ ] Secrets `.env`
- [ ] RBAC granulaire
- [ ] HSTS, X-Frame-Options, CSP, X-Content-Type-Options
- [ ] CORS restreint
- [ ] Sauvegardes chiffrées
- [ ] Soft delete
- [ ] Audit append-only
- [ ] Sessions 15/30 min

### Performance
- [ ] < 500 ms pages simples
- [ ] < 2 s dashboards
- [ ] `select_related` / `prefetch_related`
- [ ] Cache Redis KPI
- [ ] Pagination obligatoire
- [ ] Index BDD
- [ ] Celery async
- [ ] CDN Cloudflare
- [ ] Gzip
- [ ] Sentry

### Compatibilité
- [ ] 4 navigateurs (2 dernières versions)
- [ ] Responsive mobile-first
- [ ] PWA chauffeur
- [ ] Mode offline + sync différée
- [ ] WCAG 2.1 AA
- [ ] Export PDF et Excel

---

## Recette — 7 critères du CDC §6

- [ ] 20 camions + chauffeurs configurés
- [ ] Mission créée → affectée → suivie mobile → clôturée sans erreur
- [ ] Plein calcule conso + anomalie si surconsommation
- [ ] OR bloque puis libère le camion
- [ ] Sortie pièce MAJ stock + alerte seuil bas
- [ ] Facture génère créance + écriture équilibrée
- [ ] Alertes documents expirants visibles sur dashboard principal

---

## Formule taux de conformité
Taux = (Conforme + 0,5 × Partiel) / Total évaluables × 100

## Format de sortie d'audit

| ID | Module | Exigence | Priorité | Statut | Preuve | Écart | Criticité | Action |
|---|---|---|---|---|---|---|---|---|

## Format de sortie de remédiation

| ID | Module | Écart | Criticité | Avant | Après | Fichiers | Tests |
|---|---|---|---|---|---|---|---|