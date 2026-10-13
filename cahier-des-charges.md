# Cahier des Charges Fonctionnel et Technique
## ERP de Gestion Intégrée Transport & Logistique — DEN Source Group

> Source de vérité du projet. Toute décision technique ou métier
> doit être justifiée par une section de ce document. **Version 2 du 13/10/2026** : intègre les avenants et décisions de l'entreprise (§ 7) ; les numéros de ligne sont inchangés.

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
| **ADMIN** | Accès total, config et paramètres modifiables à l'écran (seuils d'alerte, TVA et délai de paiement par défaut, règles des congés), création/désactivation des utilisateurs (jamais de suppression physique), journal d'audit complet, sauvegardes (écran de suivi, « Sauvegarder maintenant »). Ne remplace jamais un validateur à contrôle strict (validation des factures, avoirs, dépenses, écritures, clôture) |
| **DIRECTION** | Vue exécutive (CA, marge nette, dispo flotte, alertes) ; même largeur que l'ADMIN pour la préparation et la saisie dans toute l'application ; valide seule : factures, avoirs, dépenses du parc auto et enveloppes, devis au-delà de 500 000 FCFA TTC, écritures comptables manuelles, clôture de l'exercice ; prévenue de toute création d'un compte Direction ; modifie les paramètres |
| **RH** | Gestion complète employés (embauche, sortie : démission, licenciement, fin de contrat…, contrats), congés/absences, jours fériés, dashboard RH ; mêmes droits que la FINANCES (finances, comptabilité, frais de mission). Pas d'accès clients |
| **CHARGE_CLIENTELE** | Portefeuille clients, historique, devis (prix validé par la FINANCES, et par la DIRECTION au-delà de 500 000 FCFA TTC), création et annulation des missions (avant le départ), réclamations, notes d'échange. Pas d'accès RH ni parc auto |
| **PARCAUTO** | Gestion technique véhicules, renouvellement pièces administratives, mouvements de stock, inventaires, OR, pleins ; affectation des missions (camion, chauffeur, copilote) et transfert en route ; demandes de dépense ; planification des frais de mission et première validation des imprévus |
| **FINANCES** | Préparation des factures et des avoirs (validés par la DIRECTION), validation du prix des devis, règlements, saisie dépenses/entrées, exécution des ordres de décaissement, confirmation des frais de mission, suivi trésorerie, comptabilité, indicateurs. Pas d'accès RH ni parc auto (sauf lecture factures) |
| **CHAUFFEUR** | Espace mobile restreint : missions assignées, check-list véhicule, saisie km/carburant, signalement incidents, imprévus avec preuve, congés |

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
- Export CSV, Excel et PDF (PDF généré par le serveur) pour audits externes.

---

### Module 2 — Flotte & Camions

- **Fiche véhicule** : immatriculation unique, marque, modèle, année,
  n° châssis VIN, kilométrage compteur, capacité de charge (t),
  réservoir (L), chauffeur habituel.
- **Statuts** : `Disponible` · `En mission` · `En maintenance` ·
  `Immobilisé` · `Hors service`.
- **Documents réglementaires** : Carte Grise, Assurance, Visite Technique,
  Patente (dates délivrance + expiration).
- **Alerte préventive** : à 30 jours de l'expiration (délai modifiable à l'écran). Un document expiré ou jamais enregistré bloque l'affectation et le départ du camion ; un document manquant est signalé au centre d'alertes.
- **Recalcul auto du statut à la clôture d'un OR** :
  1. Si d'autres OR ouverts → `En maintenance`
  2. Si mission planifiée/en cours → `En mission`
  3. Si marqué Immobilisé/Hors service → conserver
  4. Sinon → `Disponible`

---

### Module 3 — Chauffeurs & Personnel Navigant

- Chauffeur = employé (extension de la fiche personnel). Même principe pour le **copilote** (poste « Copilote »), assistant facultatif du chauffeur, choisi par le Parc Auto à l'affectation.
- Matricule unique (source de vérité : table Personnel).
- Poste "Chauffeur" → crée automatiquement une fiche chauffeur liée.
- **Fiche chauffeur** : matricule, nom, prénom, téléphone, contact d'urgence.
- **Permis** : numéro, catégories (C, E), date expiration permis,
  date expiration visite médicale. Pour être affecté : n° de permis, expiration du permis et de la visite renseignées et en cours de validité, catégorie C ou E.
- **Statuts** : `Disponible` · `En mission` · `En congé` · `Suspendu` ·
  `Inactif`.

---

### Module 4 — Clients & Chargés Clientèle

- **Fiche client** : raison sociale, NCC/NIF, contact principal, téléphone,
  email, adresse/siège, chargé clientèle attitré, taux TVA applicable
  (défaut 18 %, 0 % si exonéré avec motif obligatoire ; taux et délai de paiement proposés aux nouveaux clients modifiables à l'écran).
- **Interactions commerciales** : appels, mails, réunions, demandes de devis,
  réclamations.

---

### Module 5 — Missions & Trajets

- **Création mission** (à la main ou depuis un devis accepté, 1 devis = 1 mission) : n° auto `MIS-2026-XXXX`, client, camion + chauffeur (+ copilote facultatif)
  disponibles et en règle (affectés par le Parc Auto), lieux chargement/livraison, nature marchandise, poids (t),
  prix convenu (FCFA entiers, sans centimes). Modifiable par la DIRECTION et l'ADMIN jusqu'à « Colis récupéré » (client non modifiable).
- **Codes** : code secret + QR pour l'expéditeur (récupération colis) ;
  code pour le destinataire (confirmation livraison). Changer un lieu régénère les deux codes.
- **Cycle de vie** : `Brouillon` → `Planifiée` → `Affectée` →
  `En cours [Départ → Colis récupéré]` → `Livrée` → `Clôturée & Validée`. Avant le départ : `Annulée` (motif ; camion, chauffeur et devis libérés). En route : transfert vers un autre camion ou chauffeur, la mission garde ses codes.
- **Démarrage** : camion + chauffeur passent `En mission` ;
  notification "en cours de route (départ)".
- **Récupération colis** : scan QR par l'expéditeur sur téléphone du
  chauffeur → "colis récupéré".
- **Livraison** : camion + chauffeur repassent `Disponible` ; km d'arrivée
  met à jour le compteur ; scan QR destinataire.
- **Espace mobile chauffeur** : version simplifiée tactile (missions, plein,
  panne, scan QR, imprévus avec preuve). **Frais de mission** : avance et dépenses prévues planifiées par le Parc Auto, confirmées par la Finance ; imprévu déclaré par le chauffeur, validé par le Parc Auto puis par la Finance.

---

### Module 6 — Carburant & Consommation

- **Saisie plein** : date, camion, chauffeur, station, quantité (L),
  prix unitaire (FCFA entiers), km compteur, n° ticket/reçu (unique dans toute l'entreprise).
- **Formule** : `Conso (L/100 km) = (Litres ÷ (Km actuel − Km précédent)) × 100`
- **Alertes** :
  - 🟡 Jaune si écart > +20 % vs moyenne 3 derniers pleins
  - 🔴 Rouge si écart > +40 %
  - ⚠️ Alerte saisie si écart > ±60 % (les seuils de ce module sont modifiables à l'écran)
- **Analyse** : conso moyenne par camion et par chauffeur.
- **Détection anomalie** : > 45 L/100 km ou < 20 L/100 km. Un plein erroné s'annule avec motif (le dernier plein du camion, par ceux qui saisissent) ; sa dépense et son écriture sont contre-passées.

---

### Module 7 — Garage & Maintenance

- **OR** : n° `OR-2026-XXXX`, véhicule, type (`Curatif`, `Préventif`,
  `Diagnostic`, `Pneumatiques`), lieu (Garage interne DEN Source /
  Prestataire externe), motif/symptômes.
- **Statut camion** : ouverture OR → `En maintenance` ; clôture →
  recalcul auto.
- **Coûts** : main-d'œuvre + coût automatique des pièces utilisées. Achat ou réparation externe : demande de dépense du Parc Auto, validée par la DIRECTION, payée par la Finance (ordre de décaissement) ; plafonds mensuels possibles par catégorie (enveloppes).

---

### Module 8 — Stocks & Pièces Détachées

- **Magasin** : référence, désignation, catégorie, emplacement, quantité,
  seuil minimal, PUMP.
- **Mouvements** : Entrée (achat), Sortie (liée à un OR), Ajustement.
- **MAJ temps réel** à la validation d'un mouvement.

---

### Module 9 — Facturation & Dépenses

- **Facture** : n° `FACT-2026-XXXX`, client, mission rattachée, HT,
  TVA 18 %, TTC, date d'échéance. Préparée par la Finance, **validée par la DIRECTION seule** (numéro attribué à la validation). Correction d'une facture émise : **avoir** (total ou partiel, motif), validé par la DIRECTION.
- **TVA configurable 3 niveaux** : système (18 %), client (0 % export/ONG/
  convention), facture. **Devis (proforma)** : prix fixé par le chargé clientèle, validé par la Finance, et par la DIRECTION au-delà de 500 000 FCFA TTC ; valable 30 jours.
- Si TVA 0 % → motif d'exonération obligatoire (Export, ONG, Convention,
  Autre).
- **Règlements** : acomptes + solde. Modes : Virement, Chèque, Espèces,
  Mobile Money (Wave, Orange, MTN). Calcul du reste à recouvrer (avoirs déduits). Tout montant saisi est un nombre entier de FCFA (centimes refusés).
- **Dépenses** par catégorie (Péages, Entretien, Frais admin). Une dépense saisie à la main s'annule avec motif par ceux qui la saisissent (écriture contre-passée).

---

### Module 10 — Finances

- Trésorerie : entrées et sorties (mouvements manuels ; aucune opération diverse comptable sur un compte de trésorerie).
- Suivi flux : encaissements, décaissements, solde temps réel. **Comptabilité en partie double, SYSCOHADA révisé** : plan comptable, journaux, écritures automatiques (factures, règlements, dépenses, avoirs), saisie manuelle validée par la DIRECTION, grand livre, balance, bilan, compte de résultat, déclaration de TVA, exercice et clôture.
- Rapprochement bancaire (compte Banque) : saisie manuelle du relevé, suggestion automatique de pointage, écart signalé — voir `apps/finance/README.md` et `avenant-comptabilite-autonomie.md` (Lot G).
- Indicateurs : CA, charges, marge nette, créances, trésorerie. Enveloppes de dépenses du parc auto : un dépassement validé par la DIRECTION relève le plafond du mois.

---

### Module 11 — Ressources Humaines

- **Fiche personnel** : matricule, nom, prénom, poste, département
  (Parc Auto, Ressources Humaines et Finances, Commercial, Direction),
  date d'embauche, salaire de base (FCFA).
- **Recrutements** : matricule, nom, prénom, poste, département, type de
  contrat, date d'embauche, salaire de base. **Sortie** (démission, licenciement, fin de contrat, retraite, décès, autre) : effets automatiques à la date (compte désactivé, congés à venir annulés, équipe rattachée au supérieur), annulable avec motif.
- **Workflow congés 3 niveaux** :
  1. Demande employé (dates + motif)
  2. Validation N1 par le supérieur hiérarchique direct de l'employé ; le directeur valide lui-même (délai 48 h)
  3. Validation N2 RH (délai 24 h), par un autre compte que le N1 (sinon la DIRECTION) ; délais modifiables à l'écran
  4. Notification automatique employé
  5. Si chauffeur → statut `En congé`
- **Statuts congé** : `DEMANDE` → `VALIDATION_N1` → `APPROUVE` →
  `EN_COURS` → `TERMINE` (ou `REFUSE`).
- **Règles** : droit annuel de 26 jours ouvrés (modifiable à l'écran), plus jours exceptionnels accordés par la RH (motif obligatoire) ;
  décompte en jours ouvrés (du lundi au vendredi, hors jours fériés) ; blocage si solde insuffisant ; alerte N1 si
  chauffeur a une mission sur la période ; annulation d'un congé approuvé uniquement par RH avec notification. Report d'un congé en cours : l'employé indique le jour où il reprend le travail, la RH valide, le congé s'arrête la veille et les jours non pris sont reversés. PDF « Autorisation de congé » dès l'approbation.

---

### Module 12 — Tableau de Bord Exécutif

- **Financier** : CA facturé du mois, total encaissé, charges du mois,
  marge nette.
- **Exploitation** : camions dispo / en mission / au garage ; conso moyenne
  globale (L/100 km).
- **Centre d'alertes** : assurances/permis expirants, pièces sous seuil,
  factures impayées échues, documents manquants des camions ; pour l'ADMIN, sauvegarde absente ou trop ancienne.
- **Dashboards par rôle** :
  - RH : effectif, congés/absents
  - Finances : CA, flux, créances, marge nette
  - Chargé clientèle : clients actifs, réclamations, top 3 clients (satisfaction et
    contrats à renouveler non implémentés, écartés le 29/09/2026, voir `apps/dashboard/README.md`)
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
- **PDF/QR** : ReportLab (PDF générés par le serveur), qrcode + Pillow
- **Notifications** : Celery, dans l'application et par e-mail (SMS Twilio et push Firebase écartés le 13/10/2026, à revoir si besoin)
- **Stockage** : disque du serveur, chiffré dans la sauvegarde nocturne (S3 / MinIO écarté le 13/10/2026, à ajouter si le volume grossit)
- **Conteneurisation** : Docker + Docker Compose
- **Monitoring** : Sentry (erreurs) + Prometheus (mesures publiées par l'application, alertes)

### Architecture Django
- Apps : `core`, `accounts`, `audit`, `fleet`, `drivers`, `customers`,
  `missions`, `fuel`, `garage`, `inventory`, `billing`, `finance`, `hr`,
  `notifications`, `api/v1`, `mobile_api`, `dashboard`, `accounting`, `parametres`, `sauvegardes`, `importation`
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
- Sauvegardes chiffrées et testées (base et fichiers déposés, chaque nuit et à la demande ; restauration à blanc mensuelle)
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
- Tâches async Celery (notifications, alertes, PDF ; sauf codes de mission et autorisation de congé, rendus à la demande et jamais stockés)
- CDN Cloudflare
- Compression gzip
- Monitoring Sentry

### Compatibilité
- Chrome, Edge, Safari, Firefox (2 dernières versions)
- Responsive mobile-first
- PWA espace mobile chauffeur
- Fonctionnement hors ligne pour saisies chauffeur (sync différée) — non implémenté, écarté le 29/09/2026 sur décision confirmée de l'entreprise (voir `apps/mobile_api/README.md`)
- Accessibilité WCAG 2.1 AA
- Export PDF (généré par le serveur, mêmes chiffres que l'Excel) et Excel

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

---

## 7. AVENANTS ET DÉCISIONS INTÉGRÉS

La version 2 (13/10/2026) intègre au texte ci-dessus les décisions prises par l'entreprise depuis la version du
12/09/2026. Chaque décision a été intégrée **à sa place**, sans ajouter ni retirer de ligne avant cette section : les
références `cahier-des-charges.md:NNN` du code, de `audit/MATRICE.md` et des avenants restent justes. Les avenants
restent la trace détaillée de chaque décision (règles fines, implémentation, tests).

| Date | Document | Décision | Lignes |
|---|---|---|---|
| 29/09/2026 | `apps/mobile_api/README.md`, `apps/dashboard/README.md` | Saisie hors ligne du chauffeur, satisfaction et contrats à renouveler écartés | 237, 303 |
| Lot R2 | `avenant-separation-des-taches.md` § R2 | Dépenses du parc auto : demande, validation DIRECTION, exécution Finance ; enveloppes mensuelles | 52, 53, 168, 200 |
| Lot R3 | idem § R3 | Modification d'une mission jusqu'à « Colis récupéré » (DIRECTION, ADMIN) ; codes régénérés | 131, 133 |
| Lot R4 | idem § R4 | Frais de mission : planification Parc Auto, confirmation Finance ; imprévus en double validation | 52, 143 |
| Lots R1, R5 | idem § R5 | Devis : prix du chargé clientèle, validé par la Finance, et la DIRECTION au-delà de 500 000 FCFA TTC | 51, 186 |
| Lot R6 | idem § R6 | Mission créée depuis un devis accepté (1 devis = 1 mission) | 129 |
| Lot R7 | idem § R7 | Congés : 26 jours ouvrés, report d'un congé en cours, PDF d'autorisation | 219-221 |
| Lot R8 | idem § R8 | DIRECTION : largeur de l'ADMIN pour la saisie ; RH = FINANCES ; affectation par le Parc Auto ; copilote | 49-52, 106, 129 |
| Phases P1-P6, lots A-I | `avenant-comptabilite-syscohada.md`, `avenant-comptabilite-autonomie.md` | Comptabilité en partie double SYSCOHADA révisé, rapports, TVA, rapprochement, clôture | 198 |
| 12/10/2026 | `avenant-validation-factures.md` | La DIRECTION seule valide les factures ; la Finance les prépare | 49, 53, 184 |
| 12/10/2026 | `avenant-affectation-documents.md` | Permis, visite, catégorie C/E et documents du camion exigés pour affecter et partir | 95, 111, 130 |
| 12/10/2026 | `avenant-export-pdf.md` | Vrai PDF généré par le serveur pour toutes les listes et tous les rapports | 82, 252, 305 |
| 12/10/2026 | `avenant-montants-fcfa.md` | Montants saisis en FCFA entiers ; double soumission bloquée | 131, 150, 190 |
| 12/10/2026 | `avenant-parametres.md` | Seuils, TVA, délai de paiement et règles des congés modifiables à l'écran (ADMIN, DIRECTION) | 48, 95, 121, 155, 214, 219 |
| 12/10/2026 | `avenant-sauvegardes.md` | Service de sauvegarde dédié, écran de suivi et alerte de l'ADMIN | 48, 232, 282 |
| 12/10/2026 | `avenant-sortie-personnel.md` | Sortie du personnel avec effets automatiques à la date | 50, 210 |
| 12/10/2026 | `avenant-separation-des-taches.md` § R7 (audit M11-11) | Un même compte ne valide jamais N1 et N2 | 214 |
| 13/10/2026 | `avenant-decisions-audit.md` | Annulation de mission avant le départ, transfert en route | 51, 52, 135 |
| 13/10/2026 | idem | Avoir sur facture émise, validé par la DIRECTION | 53, 184, 190 |
| 13/10/2026 | idem | Annulation d'une dépense manuelle par ceux qui la saisissent ; annulation du dernier plein d'un camion | 157, 191 |
| 13/10/2026 | idem | N° de ticket de carburant unique dans toute l'entreprise | 150 |
| 13/10/2026 | idem | Report de congé : saisie du jour de reprise | 221 |
| 13/10/2026 | idem | Dépassement d'enveloppe validé : plafond du mois relevé | 200 |
| 13/10/2026 | idem | Aucune opération diverse sur un compte de trésorerie | 197 |
| 13/10/2026 | idem | Compte Direction créé par l'ADMIN : la Direction est prévenue | 49 |
| 13/10/2026 | idem | SMS, push et S3 écartés pour l'instant ; Prometheus, PDF en tâche de fond et Cloudflare mis en place | 253-256, 294, 295 |

**Contradictions de la version 1 levées** (relevées par l'audit, `audit/MATRICE.md`) : validation des factures
(ligne 53), largeur de la DIRECTION (ligne 49), accès financier de la RH (ligne 50), droit annuel de congé
(ligne 219), « accès total » de l'ADMIN face aux validateurs stricts et « suppression » des utilisateurs (ligne 48).

*Version 2, mise à jour à Abidjan le 13 octobre 2026 — Pour DEN Source Group*
