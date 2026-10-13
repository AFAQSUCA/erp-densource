# Matrice d'audit — ERP DEN Source Group

Inventaire de toutes les exigences, une ligne par exigence, extraites de `cahier-des-charges.md` (CDC) §3 modules 1 à
12, §4 (technique) et §6 (recette), de `audit-checklist.md`, et des avenants qui modifient le CDC
(`avenant-separation-des-taches.md`, `avenant-comptabilite-syscohada.md`, `avenant-comptabilite-autonomie.md`).

**Date de l'état initial** : 12/10/2026, sur `main` (commit `6755e65`). Verdicts issus du 3e audit global (six revues
indépendantes avec scénarios de reproduction) et relus contre le code ; preuve = `fichier:ligne`.

**Verdicts** : ✅ conforme · 🟡 partiel · ❌ absent · ❓ non vérifiable ou décision requise · ⚪ non applicable
(écarté par une décision écrite).
**Statut** : `Fait` (preuve + test) · `À faire` · `Décision` (règle métier à trancher par l'entreprise) ·
`Hors code` (vérification manuelle) · `—` (non applicable).

## Bilan

**441 exigences : 429 ✅, 0 🟡, 2 ❌, 4 ❓, 6 ⚪** — taux de conformité (✅ + ½ 🟡) / évaluables = **98,6 %**.

| Bloc | Lignes | ✅ | 🟡 | ❌ | ❓ | ⚪ |
|---|---|---|---|---|---|---|
| M1 Sécurité & audit | 77 | 77 | 0 | 0 | 0 | 0 |
| M2 Flotte | 26 | 26 | 0 | 0 | 0 | 0 |
| M3 Chauffeurs | 18 | 18 | 0 | 0 | 0 | 0 |
| M4 Clients | 15 | 15 | 0 | 0 | 0 | 0 |
| M5 Missions | 31 | 31 | 0 | 0 | 0 | 0 |
| M6 Carburant | 17 | 17 | 0 | 0 | 0 | 0 |
| M7 Garage | 13 | 13 | 0 | 0 | 0 | 0 |
| M8 Stocks | 12 | 12 | 0 | 0 | 0 | 0 |
| M9 Facturation | 27 | 27 | 0 | 0 | 0 | 0 |
| M10 Finances | 13 | 13 | 0 | 0 | 0 | 0 |
| M11 RH | 30 | 30 | 0 | 0 | 0 | 0 |
| M12 Tableaux de bord | 28 | 26 | 0 | 0 | 0 | 2 |
| Technique | 87 | 77 | 0 | 2 | 4 | 4 |
| Recette | 7 | 7 | 0 | 0 | 0 | 0 |
| Avenants | 17 | 17 | 0 | 0 | 0 | 0 |
| Écarts d'audit | 23 | 23 | 0 | 0 | 0 | 0 |

**Reprise à TECH-24** (première ligne non terminée, dans l'ordre des ID).

## Contradictions entre sources (règle 1)

| # | Sujet | CDC | Autre source | État |
|---|---|---|---|---|
| C1 | Qui valide une facture | §3 M1, ligne 53 : FINANCES « Validation factures » | Code et `architecture.md:446` : la DIRECTION valide, la FINANCES prépare (`apps/billing/permissions.py:18`) | Tranché le 12/10/2026 : DIRECTION valide (`avenant-validation-factures.md`) |
| C2 | Largeur de la DIRECTION | §3 M1, ligne 49 : « lecture seule sur RH/Clientèle/Parc Auto » | Avenant R8 §1 : la DIRECTION a la même largeur que l'ADMIN pour la saisie | Tranché par l'avenant R8 |
| C3 | Accès financier de la RH | §3 M1, ligne 50 : « Pas d'accès financier » | Avenant R8 §2 : « la RH fait tout ce que fait la FINANCES » | Tranché par l'avenant R8 |
| C4 | Droit annuel de congé | §3 M11, ligne 219 : 12 jours ouvrables | Avenant R7 : 26 jours ouvrés, hors samedi | Tranché par l'avenant R7 |
| C5 | « Accès total » de l'ADMIN | §3 M1, ligne 48 | Avenants R2/R8 : jamais l'ADMIN à la place d'un validateur strict | Tranché par les avenants |
| C6 | « Suppression » d'utilisateurs | §3 M1, ligne 48 | §4 sécurité « soft delete » : désactivation, jamais de suppression physique | Tranché par le CDC §4 |

## Module 1 — Authentification & Sécurité (CDC §3 M1, lignes 42-82)

| ID | Source | Exigence | Verdict | Preuve | Action | Statut |
|---|---|---|---|---|---|---|
| M1-01 | M1 l.48 | Rôle ADMIN | ✅ | `apps/accounts/models.py:9` | — | Fait |
| M1-02 | M1 l.49 | Rôle DIRECTION | ✅ | `apps/accounts/models.py:10` | — | Fait |
| M1-03 | M1 l.50 | Rôle RH | ✅ | `apps/accounts/models.py:11` | — | Fait |
| M1-04 | M1 l.51 | Rôle CHARGE_CLIENTELE | ✅ | `apps/accounts/models.py:12` | — | Fait |
| M1-05 | M1 l.52 | Rôle PARCAUTO | ✅ | `apps/accounts/models.py:13` | — | Fait |
| M1-06 | M1 l.53 | Rôle FINANCES | ✅ | `apps/accounts/models.py:14` | — | Fait |
| M1-07 | M1 l.54 | Rôle CHAUFFEUR | ✅ | `apps/accounts/models.py:15` | — | Fait |
| M1-08 | M1 l.48 | ADMIN : accès total (hors validations strictes, C5) | ✅ | `apps/accounts/models.py:51` (`role_effectif`), ADMIN présent dans tous les ensembles de consultation | — | Fait |
| M1-09 | M1 l.48 | ADMIN : configuration | ✅ | Écran « Paramètres » `apps/parametres/views.py:33`, modèle à ligne unique `apps/parametres/models.py:40`, service `apps/parametres/services.py:87` (ADMIN et DIRECTION, décision du 12/10/2026, `avenant-parametres.md`) ; tests `apps/parametres/tests/test_parametres.py` (36 tests, couverture 100 %) | Fait (`b7e1272` … `3d9d936`) | Fait |
| M1-10 | M1 l.48 | ADMIN : seuils d'alerte configurables | ✅ | 12 paramètres lus par `apps/parametres/services.py:55` : délai d'alerte (fleet, drivers, dashboard, notifications), seuils carburant et écart de compteur (fuel, missions), TVA et délai de paiement (customers), délais et droit de congé (hr, mobile) ; tests dans chaque app (« …des_parametres… ») ; vérifié dans le navigateur (délai N1 72 h affiché puis remis à 48 h) | Fait (`2e5623e`, `d97d7ce`, `c515dd5`, `babceb5`) | Fait |
| M1-11 | M1 l.48 | ADMIN : création d'utilisateurs | ✅ | `apps/accounts/services.py:76`, écran `apps/accounts/views_utilisateurs.py:17` | Voir AUD-09 (élévation de privilège) | Fait |
| M1-12 | M1 l.48 | ADMIN : suppression d'utilisateurs (désactivation, C6) | ✅ | `apps/accounts/services.py:125` | — | Fait |
| M1-13 | M1 l.48 | ADMIN : journal d'audit complet | ✅ | `apps/audit/permissions.py:10` | — | Fait |
| M1-14 | M1 l.48 | ADMIN : sauvegardes | ✅ | Base + fichiers déposés `ops/sauvegarde.sh`, service planifié `docker-compose.yml:145` (`ops/planificateur-sauvegarde.sh`), écran ADMIN et bouton `apps/sauvegardes/services.py:106,147`, alerte `:174` (décision du 12/10/2026, `avenant-sauvegardes.md`) ; tests `apps/sauvegardes/tests/` (43 tests, services 100 %) ; joué réellement sous Docker (demande, sauvegarde, restauration base et fichiers, échec consigné) | Fait (`b042d06` … `d8b3e58`) | Fait |
| M1-15 | M1 l.49 | DIRECTION : vue exécutive (CA, marge, dispo flotte, alertes) | ✅ | `apps/dashboard/services.py:474` | — | Fait |
| M1-16 | M1 l.49 | DIRECTION : création, affectation, suivi des missions | ✅ | `apps/missions/permissions.py:22,24,29` | — | Fait |
| M1-17 | M1 l.49 | DIRECTION : gestion flotte | ✅ | `apps/fleet/permissions.py:12` | — | Fait |
| M1-18 | M1 l.49 | DIRECTION : gestion chauffeurs | ✅ | `apps/drivers/permissions.py:14` | — | Fait |
| M1-19 | M1 l.49 | DIRECTION : accès financier (lecture + validation) | ✅ | `apps/billing/permissions.py:16,18` | — | Fait |
| M1-20 | M1 l.49 + R8 | DIRECTION : RH/Clientèle/Parc Auto (élargi par R8, C2) | ✅ | `apps/customers/permissions.py:16`, `apps/hr/permissions.py:19` | — | Fait |
| M1-21 | M1 l.50 | RH : embauche | ✅ | `apps/hr/services.py:108`, `apps/hr/permissions.py:19` | — | Fait |
| M1-22 | M1 l.50 | RH : licenciement (sortie d'un employé) | ✅ | `apps/hr/sorties.py:135,172,220,240` (enregistrement, effets à la date, tâche du jour, annulation), récepteurs `apps/drivers/signals.py:57`, `apps/missions/services.py:257` ; écrans fiche et liste (décisions du 12/10/2026, `avenant-sortie-personnel.md`) ; tests `apps/hr/tests/test_sorties.py`, `test_sorties_ecrans.py`, `apps/missions/tests/test_sortie_personnel.py` (54 tests) ; vérifié dans le navigateur (formulaire, filtre de la liste) | Fait (`9ca31be` … `59b8288`) | Fait |
| M1-23 | M1 l.50 | RH : contrats | ✅ | `apps/hr/models.py:68` | — | Fait |
| M1-24 | M1 l.50 | RH : congés et absences | ✅ | `apps/hr/permissions.py:23` | — | Fait |
| M1-25 | M1 l.50 | RH : dashboard RH | ✅ | `apps/dashboard/services.py:148` | — | Fait |
| M1-26 | M1 l.50 | RH : pas d'accès aux clients | ✅ | `apps/customers/permissions.py:14` (RH absente) | — | Fait |
| M1-27 | M1 l.50 + R8 | RH : accès financier (élargi par R8, C3) | ✅ | `apps/billing/permissions.py:16` ; frais de mission `apps/missions/permissions.py` (`FRAIS_CONSULTATION`, `FRAIS_VALIDATION_FINANCES` avec RH) ; seuls oublis trouvés, vérifié sur tous les ensembles ; tests `apps/missions/tests/test_frais_mission.py`, `test_frais_mission_views.py` | Fait (`d1456ed`) | Fait |
| M1-28 | M1 l.51 | CHARGE_CLIENTELE : portefeuille clients | ✅ | `apps/customers/permissions.py:16` | — | Fait |
| M1-29 | M1 l.51 | CHARGE_CLIENTELE : historique | ✅ | `apps/customers/models.py:89` | — | Fait |
| M1-30 | M1 l.51 | CHARGE_CLIENTELE : devis | ✅ | `apps/billing/permissions.py:25` | — | Fait |
| M1-31 | M1 l.51 | CHARGE_CLIENTELE : réclamations | ✅ | `apps/customers/models.py:89` | — | Fait |
| M1-32 | M1 l.51 | CHARGE_CLIENTELE : notes d'échange | ✅ | `apps/customers/models.py:89` | — | Fait |
| M1-33 | M1 l.51 | CHARGE_CLIENTELE : pas d'accès RH | ✅ | `apps/hr/permissions.py:17` | — | Fait |
| M1-34 | M1 l.51 | CHARGE_CLIENTELE : pas d'accès parc auto | ✅ | `apps/fleet/permissions.py:11` | — | Fait |
| M1-35 | M1 l.52 | PARCAUTO : gestion technique des véhicules | ✅ | `apps/fleet/permissions.py:12` | — | Fait |
| M1-36 | M1 l.52 | PARCAUTO : renouvellement des pièces administratives | ✅ | `apps/fleet/services.py:314` | — | Fait |
| M1-37 | M1 l.53 | FINANCES : validation des factures (modifiée : préparation, validation DIRECTION) | ✅ | Contradiction C1 tranchée le 12/10/2026 : `avenant-validation-factures.md` ; `apps/billing/permissions.py:18`, `apps/billing/services.py:380` ; test `apps/billing/tests/test_services.py:244` | Avenant écrit | Fait |
| M1-38 | M1 l.52 | PARCAUTO : mouvements de stock | ✅ | `apps/inventory/permissions.py:13` | — | Fait |
| M1-39 | M1 l.52 | PARCAUTO : inventaires | ✅ | `apps/inventory/services.py:193` | — | Fait |
| M1-40 | M1 l.52 | PARCAUTO : ordres de réparation | ✅ | `apps/garage/permissions.py:14` | — | Fait |
| M1-41 | M1 l.53 | FINANCES : saisie dépenses et entrées | ✅ | `apps/billing/permissions.py:17` | — | Fait |
| M1-42 | M1 l.53 | FINANCES : suivi trésorerie | ✅ | `apps/finance/permissions.py` (`CONSULTATION`) | — | Fait |
| M1-43 | M1 l.53 | FINANCES : indicateurs | ✅ | `apps/dashboard/services.py:203` | — | Fait |
| M1-44 | M1 l.53 | FINANCES : pas d'accès RH | ✅ | `apps/hr/permissions.py:17` | — | Fait |
| M1-45 | M1 l.53 | FINANCES : pas d'accès parc auto (sauf lecture factures) | ✅ | `apps/fleet/permissions.py:11` | — | Fait |
| M1-46 | M1 l.54 | CHAUFFEUR : missions assignées | ✅ | `apps/mobile_api/services.py:38` | — | Fait |
| M1-47 | M1 l.54 | CHAUFFEUR : check-list véhicule | ✅ | `apps/mobile_api/services.py:172` | — | Fait |
| M1-48 | M1 l.54 | CHAUFFEUR : saisie km et carburant | ✅ | `apps/mobile_api/services.py:130` | — | Fait |
| M1-49 | M1 l.54 | CHAUFFEUR : signalement d'incidents | ✅ | `apps/mobile_api/services.py:179` | — | Fait |
| M1-50 | M1 l.60 | audit_log : id BIGINT | ✅ | `config/settings/base.py:171` (`BigAutoField`) | — | Fait |
| M1-51 | M1 l.61 | audit_log : date_heure automatique | ✅ | `apps/audit/models.py:30` | — | Fait |
| M1-52 | M1 l.62 | audit_log : utilisateur_id | ✅ | `apps/audit/models.py:31` | — | Fait |
| M1-53 | M1 l.63 | audit_log : utilisateur_nom | ✅ | `apps/audit/models.py:39` ; nom complet, à défaut identifiant de connexion (`apps/audit/services.py:50`) ; tests `apps/audit/tests/test_services.py` | Fait | Fait |
| M1-54 | M1 l.64 | audit_log : rôle au moment de l'action | ✅ | `apps/audit/models.py:40` ; rôle effectif, ADMIN pour un superutilisateur (`apps/audit/services.py:51`) ; tests `apps/audit/tests/test_services.py` | Fait | Fait |
| M1-55 | M1 l.65 | audit_log : action (6 valeurs) | ✅ | `apps/audit/models.py:8` | — | Fait |
| M1-56 | M1 l.66 | audit_log : module | ✅ | `apps/audit/models.py:42` | — | Fait |
| M1-57 | M1 l.67 | audit_log : entité | ✅ | `apps/audit/models.py:43` | — | Fait |
| M1-58 | M1 l.68 | audit_log : entite_id | ✅ | `apps/audit/models.py:44` | — | Fait |
| M1-59 | M1 l.69 | audit_log : ancienne valeur | ✅ | `apps/audit/models.py:45` | — | Fait |
| M1-60 | M1 l.70 | audit_log : nouvelle valeur | ✅ | `apps/audit/models.py:46` | — | Fait |
| M1-61 | M1 l.71 | audit_log : adresse IP | ✅ | `apps/audit/models.py:47` ; `TRUSTED_PROXY_COUNT` fixé à 1 pour `web` et `realtime` dans `docker-compose.yml` (derrière Nginx) ; lecture testée `apps/audit/tests/test_services.py` (`…proxys_de_confiance`) | Fait | Fait |
| M1-62 | M1 l.72 | audit_log : user-agent | ✅ | `apps/audit/models.py:48` | — | Fait |
| M1-63 | M1 l.73 | audit_log : statut SUCCESS/FAILED | ✅ | `apps/audit/models.py:49` | — | Fait |
| M1-64 | M1 l.76 | Enregistrement automatique (signaux/middleware) | ✅ | `apps/audit/registry.py:61` | — | Fait |
| M1-65 | M1 l.77 | Append-only : aucune modification | ✅ | `apps/audit/models.py:58,73`, trigger `apps/audit/migrations/0002_trigger_append_only.py:3` | — | Fait |
| M1-66 | M1 l.77 | Append-only : aucune suppression | ✅ | `apps/core/immuable.py`, trigger (idem) | — | Fait |
| M1-67 | M1 l.78 | Tracer les créations sensibles | ✅ | `audit_model` ajouté pour `inventory.Article`, `fuel.Plein`, `billing.LigneFacture`, `hr.ReportConge`, `hr.ValidationConge`, `hr.JourFerie`, `customers.Interaction`, `garage.ChecklistVehicule` (`apps/*/apps.py`) ; test garde-fou `apps/audit/tests/test_couverture.py` (22 modèles sensibles) | Fait | Fait |
| M1-68 | M1 l.78 | Tracer les modifications critiques | ✅ | Idem M1-67 ; seuil d'un article modifié : ancienne et nouvelle valeur au journal (`apps/audit/tests/test_couverture.py`) | Fait | Fait |
| M1-69 | M1 l.79 | Tracer les suppressions | ✅ | `apps/audit/registry.py:150` (+ suppression logique) | — | Fait |
| M1-70 | M1 l.79 | Tracer les connexions | ✅ | `apps/audit/signals.py:10` | — | Fait |
| M1-71 | M1 l.79 | Tracer les déconnexions | ✅ | `apps/audit/signals.py:11` | — | Fait |
| M1-72 | M1 l.79 | Tracer les validations | ✅ | `apps/audit/registry.py:113` ; décisions de congé tracées et auto-validation marquée (`ValidationConge.auto_validation`, `apps/hr/services.py` `_decide_pour_lui_meme`), repère « auto-validation » sur la fiche ; tests `apps/hr/tests/test_conges.py` | Fait | Fait |
| M1-73 | M1 l.80 | Conservation ≥ 5 ans | ✅ | Aucune purge applicative ; suppression bloquée (`apps/core/immuable.py`) | — | Fait |
| M1-74 | M1 l.81 | Consultation par l'ADMIN | ✅ | `apps/audit/permissions.py:10` | — | Fait |
| M1-75 | M1 l.81 | Lecture seule pour la DIRECTION | ✅ | `apps/audit/views.py` (aucune écriture) | — | Fait |
| M1-76 | M1 l.82 | Export CSV | ✅ | `apps/audit/views.py` (`JournalExporterCsvView`) : toutes les cellules neutralisées contre l'injection de formule, lecture par lots (`iterator`) ; test `apps/audit/tests/test_views.py` (`…neutralise_les_formules…`) | Fait | Fait |
| M1-77 | M1 l.82 | Export PDF | ✅ | Journal d'audit en vrai PDF (`ImpressionListeMixin.get`, `apps/core/pdf.py`), bouton « Télécharger en PDF » (décision du 12/10/2026, `avenant-export-pdf.md`) ; test `apps/core/tests/test_pdf.py` | Fait | Fait |

## Module 2 — Flotte & Camions (CDC §3 M2, lignes 86-100)

| ID | Source | Exigence | Verdict | Preuve | Action | Statut |
|---|---|---|---|---|---|---|
| M2-01 | M2 l.88 | Immatriculation | ✅ | `apps/fleet/models.py:23` | — | Fait |
| M2-02 | M2 l.88 | Immatriculation unique | ✅ | Comparaison sans séparateur `apps/fleet/services.py:203,209` (saisie et import Excel) ; tests `apps/fleet/tests/test_fiche.py` (`…ecrite_autrement…`) | Fait (`dee8e4f`) | Fait |
| M2-03 | M2 l.88 | Marque | ✅ | `apps/fleet/models.py:24` | — | Fait |
| M2-04 | M2 l.88 | Modèle | ✅ | `apps/fleet/models.py:25` | — | Fait |
| M2-05 | M2 l.89 | Année | ✅ | Bornée 1950 → an prochain dans le service `apps/fleet/services.py:216` ; tests `test_fiche.py` | Fait (`dee8e4f`) | Fait |
| M2-06 | M2 l.89 | N° de châssis VIN | ✅ | 17 caractères au plus `apps/fleet/services.py:217` (plus d'erreur 500 à l'import) ; tests `test_fiche.py` | Fait (`dee8e4f`) | Fait |
| M2-07 | M2 l.89 | Kilométrage compteur | ✅ | Hausse au-delà de l'écart maximal des paramètres refusée sur la fiche `apps/fleet/services.py:325` (correction ADMIN sinon) ; tests `test_fiche.py` | Fait (`dee8e4f`) | Fait |
| M2-08 | M2 l.89 | Capacité de charge (t) | ✅ | `apps/fleet/models.py:31` | — | Fait |
| M2-09 | M2 l.90 | Réservoir (L) | ✅ | `apps/fleet/models.py:34` | — | Fait |
| M2-10 | M2 l.90 | Chauffeur habituel | ✅ | Chauffeur actuel conservé même inactif `apps/fleet/forms.py:42` ; tests `apps/fleet/tests/test_views.py` | Fait (`96b1b8d`) | Fait |
| M2-11 | M2 l.91 | Statut Disponible | ✅ | `apps/fleet/models.py:13` | — | Fait |
| M2-12 | M2 l.91 | Statut En mission | ✅ | `apps/fleet/models.py:14` | — | Fait |
| M2-13 | M2 l.91 | Statut En maintenance | ✅ | `apps/fleet/models.py:15` | — | Fait |
| M2-14 | M2 l.92 | Statut Immobilisé | ✅ | `apps/fleet/models.py:16` | — | Fait |
| M2-15 | M2 l.92 | Statut Hors service | ✅ | `apps/fleet/models.py:17` | — | Fait |
| M2-16 | M2 l.93 | Document Carte grise | ✅ | `apps/fleet/models.py:63` | — | Fait |
| M2-17 | M2 l.93 | Document Assurance | ✅ | `apps/fleet/models.py:64` | — | Fait |
| M2-18 | M2 l.93 | Document Visite technique | ✅ | `apps/fleet/models.py:65` | — | Fait |
| M2-19 | M2 l.94 | Document Patente | ✅ | `apps/fleet/models.py:66` | — | Fait |
| M2-20 | M2 l.94 | Date de délivrance | ✅ | `apps/fleet/models.py:86` | — | Fait |
| M2-21 | M2 l.94 | Date d'expiration | ✅ | `apps/fleet/models.py:87` | — | Fait |
| M2-22 | M2 l.95 | Alerte préventive à 30 jours | ✅ | Documents manquants signalés `apps/fleet/services.py:174`, camions supprimés ou hors service exclus `:169` ; centre d'alertes `apps/dashboard/services.py:301`, badge « Document manquant » de la liste ; tests `test_fiche.py`, `test_views.py`, `apps/dashboard/tests/test_dashboard.py` | Fait (`cbb3d51`) | Fait |
| M2-23 | M2 l.97 | Recalcul à la clôture : autres OR ouverts → En maintenance | ✅ | `apps/fleet/services.py:40` (règle 1, marquage conservé dans `Vehicule.marquage`) ; tests `apps/garage/tests/test_statut_vehicule.py` | Fait (`9f8b812`) | Fait |
| M2-24 | M2 l.98 | Recalcul : mission planifiée/en cours → En mission | ✅ | `apps/fleet/services.py:39` | — | Fait |
| M2-25 | M2 l.99 | Recalcul : Immobilisé/Hors service conservé | ✅ | Marquage dédié `apps/fleet/models.py:56` (repris des statuts existants par la migration `fleet.0002`), relu par la règle 3, levé seulement par « Remettre en service » (`apps/fleet/services.py:93`) ; scénario 2 OR testé `apps/garage/tests/test_statut_vehicule.py` | Fait (`9f8b812`) | Fait |
| M2-26 | M2 l.100 | Recalcul : sinon Disponible | ✅ | `apps/fleet/services.py:39` | — | Fait |

## Module 3 — Chauffeurs (CDC §3 M3, lignes 104-113)

| ID | Source | Exigence | Verdict | Preuve | Action | Statut |
|---|---|---|---|---|---|---|
| M3-01 | M3 l.106 | Chauffeur = extension de la fiche personnel | ✅ | `apps/drivers/models.py:32` | — | Fait |
| M3-02 | M3 l.107 | Matricule unique (source : Personnel) | ✅ | `apps/hr/models.py:54` | — | Fait |
| M3-03 | M3 l.108 | Poste « Chauffeur » → fiche créée automatiquement | ✅ | `apps/drivers/signals.py:11` | — | Fait |
| M3-04 | M3 l.106 | La fiche suit le personnel (poste changé, personnel supprimé) | ✅ | `apps/drivers/signals.py` (`creer_fiche_chauffeur`, `creer_fiche_copilote`) et `apps/drivers/services.py` (`desactiver_fiche_chauffeur/copilote`) : poste quitté ou fiche supprimée → « Inactif » ; changement refusé pendant une mission ; sortie du personnel (M1-22) ; tests `apps/drivers/tests/test_suivi_personnel.py` | Fait | Fait |
| M3-05 | M3 l.109 | Fiche : matricule | ✅ | `apps/drivers/models.py:66` | — | Fait |
| M3-06 | M3 l.109 | Fiche : nom | ✅ | `apps/drivers/models.py:70` | — | Fait |
| M3-07 | M3 l.109 | Fiche : prénom | ✅ | `apps/drivers/models.py:74` | — | Fait |
| M3-08 | M3 l.109 | Fiche : téléphone | ✅ | `apps/drivers/models.py:38` | — | Fait |
| M3-09 | M3 l.109 | Fiche : contact d'urgence | ✅ | `apps/drivers/models.py:39` | — | Fait |
| M3-10 | M3 l.110 | Permis : numéro | ✅ | `apps/drivers/models.py:40` | — | Fait |
| M3-11 | M3 l.110 | Permis : catégories C, E | ✅ | `apps/drivers/models.py:41` | — | Fait |
| M3-12 | M3 l.110 | Date d'expiration du permis | ✅ | `apps/drivers/models.py:44` | — | Fait |
| M3-13 | M3 l.111 | Date d'expiration de la visite médicale | ✅ | `apps/drivers/models.py:47` | — | Fait |
| M3-14 | M3 l.112 | Statut Disponible | ✅ | `apps/drivers/models.py:11` | — | Fait |
| M3-15 | M3 l.112 | Statut En mission | ✅ | `apps/drivers/models.py:12` | — | Fait |
| M3-16 | M3 l.112 | Statut En congé | ✅ | `apps/drivers/models.py:13` | — | Fait |
| M3-17 | M3 l.112 | Statut Suspendu | ✅ | `apps/drivers/models.py:14` | — | Fait |
| M3-18 | M3 l.113 | Statut Inactif | ✅ | `apps/drivers/models.py:15` | — | Fait |

## Module 4 — Clients (CDC §3 M4, lignes 117-123)

| ID | Source | Exigence | Verdict | Preuve | Action | Statut |
|---|---|---|---|---|---|---|
| M4-01 | M4 l.119 | Raison sociale | ✅ | `apps/customers/models.py:28` | — | Fait |
| M4-02 | M4 l.119 | NCC/NIF | ✅ | Comparaison sans séparateur ni casse `apps/customers/services.py` (`cle_ncc`, `client_par_ncc`), saisie et import Excel ; NCC enregistré en majuscules ; tests `apps/customers/tests/test_services.py` | Fait (`ba562d8`) | Fait |
| M4-03 | M4 l.119 | Contact principal | ✅ | `apps/customers/models.py:30` | — | Fait |
| M4-04 | M4 l.119 | Téléphone | ✅ | `apps/customers/models.py:31` | — | Fait |
| M4-05 | M4 l.120 | Email | ✅ | `apps/customers/models.py:32` | — | Fait |
| M4-06 | M4 l.120 | Adresse / siège | ✅ | `apps/customers/models.py:33` | — | Fait |
| M4-07 | M4 l.120 | Chargé clientèle attitré | ✅ | `apps/customers/models.py:34` | — | Fait |
| M4-08 | M4 l.120 | Taux de TVA par défaut 18 % | ✅ | `apps/customers/models.py:12` | — | Fait |
| M4-09 | M4 l.121 | Taux 0 % si exonéré | ✅ | `apps/customers/templates/customers/client_form.html:51` (valeur non localisée, 0,00 conservé) ; tests `apps/customers/tests/test_views.py:286,298` ; vérifié dans le navigateur | Corrigé (`e443e67`) | Fait |
| M4-10 | M4 l.121 | Motif obligatoire si 0 % | ✅ | `apps/customers/models.py:46` + contrainte, service, formulaire | — | Fait |
| M4-11 | M4 l.122 | Interactions : appels | ✅ | `apps/customers/models.py:89` | — | Fait |
| M4-12 | M4 l.122 | Interactions : mails | ✅ | `apps/customers/models.py:89` | — | Fait |
| M4-13 | M4 l.122 | Interactions : réunions | ✅ | `apps/customers/models.py:89` | — | Fait |
| M4-14 | M4 l.122 | Interactions : demandes de devis | ✅ | `apps/customers/models.py:89` | — | Fait |
| M4-15 | M4 l.123 | Interactions : réclamations | ✅ | `apps/customers/models.py:89` | — | Fait |

## Module 5 — Missions (CDC §3 M5, lignes 127-143)

| ID | Source | Exigence | Verdict | Preuve | Action | Statut |
|---|---|---|---|---|---|---|
| M5-01 | M5 l.129 | N° automatique MIS-AAAA-XXXX | ✅ | `apps/missions/services.py:266` | — | Fait |
| M5-02 | M5 l.129 | Client | ✅ | `apps/missions/models.py:46` | — | Fait |
| M5-03 | M5 l.129 | Camion disponible | ✅ | `apps/missions/services.py` (`_verifier_vehicule`) | — | Fait |
| M5-04 | M5 l.129 | Chauffeur disponible | ✅ | Disponible, non réservé, permis complet (n°, catégorie C ou E, dates) et visite médicale valides, à l'affectation, à la réaffectation et au départ : `apps/missions/services.py` (`documents_manquants_du_chauffeur`, `_exiger_documents_valides`) ; décision du 12/10/2026 (`avenant-affectation-documents.md`) ; tests `apps/missions/tests/test_documents_et_reaffectation.py` | Fait (`65c73ed`) | Fait |
| M5-05 | M5 l.130 | Lieu de chargement | ✅ | `apps/missions/models.py:86` | — | Fait |
| M5-06 | M5 l.130 | Lieu de livraison | ✅ | `apps/missions/models.py:87` | — | Fait |
| M5-07 | M5 l.130 | Nature de la marchandise | ✅ | `apps/missions/models.py:88` | — | Fait |
| M5-08 | M5 l.130 | Poids (t) | ✅ | `apps/missions/models.py:89` | — | Fait |
| M5-09 | M5 l.131 | Prix convenu (FCFA) | ✅ | `apps/missions/models.py:90` | — | Fait |
| M5-10 | M5 l.132 | Code secret expéditeur | ✅ | `apps/missions/services.py:56` | — | Fait |
| M5-11 | M5 l.132 | QR expéditeur | ✅ | `apps/missions/views.py:340` | Pages avec codes sans `no-store` (AUD-15) | Fait |
| M5-12 | M5 l.133 | Code destinataire | ✅ | `apps/missions/services.py:56` | — | Fait |
| M5-13 | M5 l.134 | Statut Brouillon | ✅ | `apps/missions/models.py:9` | — | Fait |
| M5-14 | M5 l.134 | Statut Planifiée | ✅ | `apps/missions/models.py:9` | — | Fait |
| M5-15 | M5 l.134 | Statut Affectée | ✅ | `apps/missions/models.py:9` | — | Fait |
| M5-16 | M5 l.135 | Statut En cours — Départ | ✅ | `apps/missions/models.py:9` | — | Fait |
| M5-17 | M5 l.135 | Statut En cours — Colis récupéré | ✅ | `apps/missions/models.py:9` | — | Fait |
| M5-18 | M5 l.135 | Statut Livrée | ✅ | `apps/missions/models.py:9` | — | Fait |
| M5-19 | M5 l.135 | Statut Clôturée & Validée | ✅ | `apps/missions/models.py:9` | — | Fait |
| M5-20 | M5 l.136 | Démarrage : camion En mission | ✅ | `apps/missions/services.py:481` | — | Fait |
| M5-21 | M5 l.136 | Démarrage : chauffeur En mission | ✅ | `apps/missions/services.py:481` | — | Fait |
| M5-22 | M5 l.137 | Notification « en cours de route (départ) » | ✅ | `apps/notifications/receivers.py:236` | — | Fait |
| M5-23 | M5 l.138 | Récupération : scan QR expéditeur → colis récupéré | ✅ | `apps/missions/services.py:526`, `static/js/scanner.js:5` | — | Fait |
| M5-24 | M5 l.140 | Livraison : camion Disponible | ✅ | `apps/missions/services.py:541` | — | Fait |
| M5-25 | M5 l.140 | Livraison : chauffeur Disponible | ✅ | `apps/missions/services.py:541` | — | Fait |
| M5-26 | M5 l.141 | Km d'arrivée met à jour le compteur | ✅ | `apps/missions/services.py:541` | — | Fait |
| M5-27 | M5 l.141 | Livraison : scan QR destinataire | ✅ | `apps/missions/services.py:541` | — | Fait |
| M5-28 | M5 l.142 | Espace mobile : missions | ✅ | `apps/mobile_api/urls_web.py:9` | — | Fait |
| M5-29 | M5 l.142 | Espace mobile : plein | ✅ | `apps/mobile_api/services.py:130` | — | Fait |
| M5-30 | M5 l.143 | Espace mobile : panne | ✅ | `apps/mobile_api/services.py:179` | — | Fait |
| M5-31 | M5 l.143 | Espace mobile : scan QR | ✅ | `static/js/scanner.js:5` | — | Fait |

## Module 6 — Carburant (CDC §3 M6, lignes 147-157)

| ID | Source | Exigence | Verdict | Preuve | Action | Statut |
|---|---|---|---|---|---|---|
| M6-01 | M6 l.149 | Plein : date | ✅ | `apps/fuel/models.py:24` | — | Fait |
| M6-02 | M6 l.149 | Plein : camion | ✅ | `apps/fuel/models.py:25` | — | Fait |
| M6-03 | M6 l.149 | Plein : chauffeur | ✅ | `apps/fuel/models.py:31` | — | Fait |
| M6-04 | M6 l.149 | Plein : station | ✅ | `apps/fuel/models.py:37` | — | Fait |
| M6-05 | M6 l.149 | Plein : quantité (L) | ✅ | `apps/fuel/models.py:38` | — | Fait |
| M6-06 | M6 l.150 | Plein : prix unitaire (FCFA) | ✅ | `apps/fuel/models.py:41` | — | Fait |
| M6-07 | M6 l.150 | Plein : km compteur | ✅ | Plancher du premier plein = compteur du camion `apps/fuel/services.py` (`enregistrer_plein`) ; tests `apps/fuel/tests/test_services.py` (`…premier_plein_sous_le_compteur…`) | Fait | Fait |
| M6-08 | M6 l.150 | Plein : n° ticket / reçu | ✅ | `apps/fuel/models.py:45` | — | Fait |
| M6-09 | M6 l.151 | Formule L/100 km | ✅ | `apps/fuel/services.py:46` | — | Fait |
| M6-10 | M6 l.153 | Alerte jaune si écart > +20 % | ✅ | `apps/fuel/services.py:37` | — | Fait |
| M6-11 | M6 l.153 | Moyenne des 3 derniers pleins | ✅ | `apps/fuel/services.py:53` | — | Fait |
| M6-12 | M6 l.154 | Alerte rouge si écart > +40 % | ✅ | `apps/fuel/services.py:38` | — | Fait |
| M6-13 | M6 l.155 | Alerte saisie si écart > ±60 % | ✅ | `apps/fuel/services.py:39` | — | Fait |
| M6-14 | M6 l.156 | Conso moyenne par camion | ✅ | `apps/fuel/services.py:219` | — | Fait |
| M6-15 | M6 l.156 | Conso moyenne par chauffeur | ✅ | `apps/fuel/services.py:219` | — | Fait |
| M6-16 | M6 l.157 | Anomalie > 45 L/100 km | ✅ | `apps/fuel/services.py:89` | — | Fait |
| M6-17 | M6 l.157 | Anomalie < 20 L/100 km | ✅ | `apps/fuel/services.py:89` | — | Fait |

## Module 7 — Garage (CDC §3 M7, lignes 161-168)

| ID | Source | Exigence | Verdict | Preuve | Action | Statut |
|---|---|---|---|---|---|---|
| M7-01 | M7 l.163 | N° OR-AAAA-XXXX | ✅ | `apps/garage/services.py:59` | — | Fait |
| M7-02 | M7 l.163 | Véhicule | ✅ | `apps/garage/models.py` (`vehicule`) | — | Fait |
| M7-03 | M7 l.163 | Type Curatif | ✅ | `apps/garage/models.py:9` | — | Fait |
| M7-04 | M7 l.164 | Type Préventif | ✅ | `apps/garage/models.py:9` | — | Fait |
| M7-05 | M7 l.164 | Type Diagnostic | ✅ | `apps/garage/models.py:9` | — | Fait |
| M7-06 | M7 l.164 | Type Pneumatiques | ✅ | `apps/garage/models.py:9` | — | Fait |
| M7-07 | M7 l.164 | Lieu : garage interne | ✅ | `apps/garage/models.py:18` | — | Fait |
| M7-08 | M7 l.165 | Lieu : prestataire externe | ✅ | `apps/garage/models.py:18` | — | Fait |
| M7-09 | M7 l.165 | Motif / symptômes | ✅ | `apps/garage/models.py:46` | — | Fait |
| M7-10 | M7 l.166 | Ouverture → En maintenance | ✅ | `apps/garage/services.py:44` | — | Fait |
| M7-11 | M7 l.167 | Clôture → recalcul automatique | ✅ | `apps/garage/services.py` (`cloturer_or`) ; voir M2-25 | Fait (`9f8b812`) | Fait |
| M7-12 | M7 l.168 | Coût main-d'œuvre | ✅ | `apps/garage/models.py:52` | — | Fait |
| M7-13 | M7 l.168 | Coût automatique des pièces | ✅ | `apps/inventory/services.py:227` | — | Fait |

## Module 8 — Stocks (CDC §3 M8, lignes 172-177)

| ID | Source | Exigence | Verdict | Preuve | Action | Statut |
|---|---|---|---|---|---|---|
| M8-01 | M8 l.174 | Référence | ✅ | `apps/inventory/models.py:19` | — | Fait |
| M8-02 | M8 l.174 | Désignation | ✅ | `apps/inventory/models.py:20` | — | Fait |
| M8-03 | M8 l.174 | Catégorie | ✅ | `apps/inventory/models.py:21` | — | Fait |
| M8-04 | M8 l.174 | Emplacement | ✅ | `apps/inventory/models.py:22` | — | Fait |
| M8-05 | M8 l.175 | Quantité | ✅ | `apps/inventory/models.py:23` | — | Fait |
| M8-06 | M8 l.175 | Seuil minimal | ✅ | `apps/inventory/models.py:24` | — | Fait |
| M8-07 | M8 l.175 | PUMP | ✅ | `apps/inventory/models.py:29` | — | Fait |
| M8-08 | M8 l.176 | Mouvement Entrée (achat) | ✅ | `apps/inventory/services.py:136` | — | Fait |
| M8-09 | M8 l.176 | Mouvement Sortie liée à un OR | ✅ | `apps/inventory/services.py:163` | — | Fait |
| M8-10 | M8 l.176 | Mouvement Ajustement | ✅ | `apps/inventory/services.py:193` | — | Fait |
| M8-11 | M8 l.177 | Mise à jour en temps réel | ✅ | `apps/inventory/services.py:41` | — | Fait |
| M8-12 | checklist M8 | Alerte seuil bas | ✅ | `apps/inventory/services.py:70` | — | Fait |

## Module 9 — Facturation & Dépenses (CDC §3 M9, lignes 181-191)

| ID | Source | Exigence | Verdict | Preuve | Action | Statut |
|---|---|---|---|---|---|---|
| M9-01 | M9 l.183 | N° FACT-AAAA-XXXX | ✅ | `apps/billing/services.py:384` | — | Fait |
| M9-02 | M9 l.183 | Client | ✅ | `apps/billing/models.py:69` | — | Fait |
| M9-03 | M9 l.183 | Mission rattachée | ✅ | `apps/billing/models.py:75` | — | Fait |
| M9-04 | M9 l.183 | Montant HT | ✅ | `apps/billing/models.py:94` | — | Fait |
| M9-05 | M9 l.184 | TVA (18 % par défaut) | ✅ | `apps/billing/models.py:95` | — | Fait |
| M9-06 | M9 l.184 | Montant TTC | ✅ | `apps/billing/models.py:96` | — | Fait |
| M9-07 | M9 l.184 | Date d'échéance | ✅ | `apps/billing/models.py:93` | — | Fait |
| M9-08 | M9 l.185 | TVA niveau système (18 %) | ✅ | Paramètre `tva_defaut` (`apps/parametres/models.py:40`), appliqué à la création d'un client `apps/customers/services.py:115` ; tests `apps/customers/tests/test_services.py`, `test_views.py` | Fait (`c515dd5`) | Fait |
| M9-09 | M9 l.185 | TVA niveau client | ✅ | `apps/customers/models.py:43` | — | Fait |
| M9-10 | M9 l.186 | TVA niveau facture | ✅ | `apps/billing/models.py:87` | — | Fait |
| M9-11 | M9 l.187 | Motif obligatoire si TVA 0 % | ✅ | `apps/billing/models.py:88` | — | Fait |
| M9-12 | M9 l.187 | Motif Export | ✅ | `apps/customers/models.py:19` | — | Fait |
| M9-13 | M9 l.187 | Motif ONG | ✅ | `apps/customers/models.py:20` | — | Fait |
| M9-14 | M9 l.187 | Motif Convention | ✅ | `apps/customers/models.py:21` | — | Fait |
| M9-15 | M9 l.188 | Motif Autre | ✅ | `apps/customers/models.py:22` | — | Fait |
| M9-16 | M9 l.189 | Règlements : acomptes | ✅ | `apps/billing/services.py:436` ; montant entier exigé (`apps/billing/services.py:459`) et double saisie refusée (`apps/billing/services.py:469`) ; tests `apps/core/tests/test_montants.py`, `apps/core/tests/test_doublons.py` | Fait (`d621d1e`, `762f616`) | Fait |
| M9-17 | M9 l.189 | Règlements : solde | ✅ | `apps/billing/services.py:433` | — | Fait |
| M9-18 | M9 l.189 | Mode Virement | ✅ | `apps/billing/models.py:12` | — | Fait |
| M9-19 | M9 l.189 | Mode Chèque | ✅ | `apps/billing/models.py:12` | — | Fait |
| M9-20 | M9 l.189 | Mode Espèces | ✅ | `apps/billing/models.py:12` | — | Fait |
| M9-21 | M9 l.190 | Mode Wave | ✅ | `apps/billing/models.py:12` | — | Fait |
| M9-22 | M9 l.190 | Mode Orange Money | ✅ | `apps/billing/models.py:12` | — | Fait |
| M9-23 | M9 l.190 | Mode MTN | ✅ | `apps/billing/models.py:12` | — | Fait |
| M9-24 | M9 l.190 | Reste à recouvrer | ✅ | `apps/billing/services.py:117` ; plus de reste de 0,50 FCFA : règlement entier exigé (`apps/billing/services.py:459`) ; test `apps/core/tests/test_montants.py` (`test_un_reglement_avec_des_centimes_est_refuse_et_le_reste_ne_traine_pas_a_0_50`) | Fait (`d621d1e`) | Fait |
| M9-25 | M9 l.191 | Dépense catégorie Péages | ✅ | `apps/billing/models.py:346` | — | Fait |
| M9-26 | M9 l.191 | Dépense catégorie Entretien | ✅ | `apps/billing/models.py:346` | — | Fait |
| M9-27 | M9 l.191 | Dépense catégorie Frais admin | ✅ | `apps/billing/models.py:346` | — | Fait |

## Module 10 — Finances (CDC §3 M10, lignes 195-200)

| ID | Source | Exigence | Verdict | Preuve | Action | Statut |
|---|---|---|---|---|---|---|
| M10-01 | M10 l.197 | Trésorerie : entrées | ✅ | `apps/finance/services.py:113` | — | Fait |
| M10-02 | M10 l.197 | Trésorerie : sorties | ✅ | `apps/finance/services.py:113` | — | Fait |
| M10-03 | M10 l.198 | Suivi des encaissements | ✅ | `apps/finance/services.py:113` | — | Fait |
| M10-04 | M10 l.198 | Suivi des décaissements | ✅ | `apps/finance/services.py:113` | — | Fait |
| M10-05 | M10 l.198 | Solde en temps réel | ✅ | `apps/finance/services.py:341` | — | Fait |
| M10-06 | M10 l.199 | Rapprochement : saisie manuelle du relevé | ✅ | `apps/finance/services.py:204` | — | Fait |
| M10-07 | M10 l.199 | Rapprochement : suggestion de pointage | ✅ | `apps/finance/services.py:241` ; une dépense pointée passée hors banque est dépointée (`apps/finance/receivers.py:122`), elle reste pointée si elle reste en banque ; tests `apps/finance/tests/test_depenses_parc_auto.py:221` | Fait (`1e1cf60`) | Fait |
| M10-08 | M10 l.199 | Rapprochement : écart signalé | ✅ | `apps/finance/services.py:304` | — | Fait |
| M10-09 | M10 l.200 | Indicateur CA | ✅ | `apps/finance/services.py:471` | — | Fait |
| M10-10 | M10 l.200 | Indicateur charges | ✅ | `apps/finance/services.py:471` | — | Fait |
| M10-11 | M10 l.200 | Indicateur marge nette | ✅ | `apps/finance/services.py:471` | — | Fait |
| M10-12 | M10 l.200 | Indicateur créances | ✅ | `apps/finance/services.py:471` | — | Fait |
| M10-13 | M10 l.200 | Indicateur trésorerie | ✅ | `apps/finance/services.py:471` | — | Fait |

## Module 11 — RH (CDC §3 M11, lignes 204-221, modifié par l'avenant R7)

| ID | Source | Exigence | Verdict | Preuve | Action | Statut |
|---|---|---|---|---|---|---|
| M11-01 | M11 l.206 | Fiche : matricule | ✅ | `apps/hr/models.py:54` | — | Fait |
| M11-02 | M11 l.206 | Fiche : nom | ✅ | `apps/hr/models.py:55` | — | Fait |
| M11-03 | M11 l.206 | Fiche : prénom | ✅ | `apps/hr/models.py:56` | — | Fait |
| M11-04 | M11 l.206 | Fiche : poste | ✅ | `apps/hr/models.py:57` | — | Fait |
| M11-05 | M11 l.207 | Fiche : département (4 valeurs) | ✅ | `apps/hr/models.py:35` | — | Fait |
| M11-06 | M11 l.208 | Fiche : date d'embauche | ✅ | `apps/hr/models.py:61` | — | Fait |
| M11-07 | M11 l.208 | Fiche : salaire de base (FCFA) | ✅ | `apps/hr/models.py:62` | — | Fait |
| M11-08 | M11 l.209 | Recrutement (champs de la fiche) | ✅ | `apps/hr/services.py:108` ; import Excel rejouable et robuste : `apps/hr/services.py:236` (voir AV-17) ; tests `apps/hr/tests/test_import_personnel.py` | Fait (`0b38030`) | Fait |
| M11-09 | M11 l.210 | Recrutement : type de contrat | ✅ | `apps/hr/models.py:68` | — | Fait |
| M11-10 | M11 l.212 | Congé : demande employé (dates + motif) | ✅ | `apps/hr/services.py:640` | — | Fait |
| M11-11 | M11 l.213 | Validation N1 par le supérieur direct | ✅ | Un même compte ne valide jamais N1 et N2 : `apps/hr/services.py:511,522` ; le N2 revient à un autre RH, ou à la Direction sans attendre s'il était le seul ; notification et relance (`apps/notifications/receivers.py:109`, `apps/notifications/taches.py:122`) ; décision du 12/10/2026 (`avenant-separation-des-taches.md` § R7) ; tests `apps/hr/tests/test_separation_n1_n2.py` (7 tests) | Fait (`a1a8ddf`, `ab285ae`) | Fait |
| M11-12 | M11 l.213 | Le directeur valide lui-même son N1 | ✅ | `apps/hr/services.py` (`_est_sommet_hierarchie`) | — | Fait |
| M11-13 | M11 l.213 | Délai N1 48 h | ✅ | `apps/hr/services.py:48` | DIRECTION non alertée des retards (AUD-16) | Fait |
| M11-14 | M11 l.214 | Validation N2 RH | ✅ | `apps/hr/services.py:707` | — | Fait |
| M11-15 | M11 l.214 | Délai N2 24 h | ✅ | `apps/hr/services.py:48` | — | Fait |
| M11-16 | M11 l.215 | Notification automatique de l'employé | ✅ | `apps/notifications/receivers.py:120` | — | Fait |
| M11-17 | M11 l.216 | Chauffeur → statut En congé | ✅ | `apps/drivers/signals.py:33` | — | Fait |
| M11-18 | M11 l.217 | Statut DEMANDE | ✅ | `apps/hr/models.py:114` | — | Fait |
| M11-19 | M11 l.217 | Statut VALIDATION_N1 | ✅ | `apps/hr/models.py:114` | — | Fait |
| M11-20 | M11 l.217 | Statut APPROUVE | ✅ | `apps/hr/models.py:114` | — | Fait |
| M11-21 | M11 l.218 | Statut EN_COURS | ✅ | `apps/hr/models.py:114` | — | Fait |
| M11-22 | M11 l.218 | Statut TERMINE | ✅ | `apps/hr/models.py:114` | — | Fait |
| M11-23 | M11 l.218 | Statut REFUSE | ✅ | `apps/hr/models.py:114` | — | Fait |
| M11-24 | M11 l.219 + R7 | Droit annuel (26 jours ouvrés, avenant R7) | ✅ | `apps/hr/services.py:56` | — | Fait |
| M11-25 | M11 l.219 | Jours exceptionnels accordés par la RH, motif obligatoire | ✅ | `apps/hr/services.py:419` | — | Fait |
| M11-26 | M11 l.220 + R7 | Décompte en jours ouvrés, hors jours fériés | ✅ | `apps/hr/services.py:685` ; fériés entretenus : écran `/rh/jours-feries/` (`apps/hr/views.py:649`, menu RH), saisie `apps/hr/services.py:1104`, génération quotidienne de l'année et de la suivante (`apps/notifications/taches.py:202`), un jour supprimé n'est pas recréé (`apps/hr/services.py:1071`) ; tests `apps/hr/tests/test_jours_feries_ecran.py` (9 tests) ; vérifié dans le navigateur | Fait (`23b4918`) | Fait |
| M11-27 | M11 l.220 | Blocage si solde insuffisant | ✅ | `apps/hr/services.py:409` | — | Fait |
| M11-28 | M11 l.220 | Alerte N1 si mission sur la période | ✅ | `apps/missions/services.py:136` | — | Fait |
| M11-29 | M11 l.221 | Annulation d'un congé approuvé : RH uniquement | ✅ | `apps/hr/services.py:765` | — | Fait |
| M11-30 | M11 l.221 | Annulation : avec notification | ✅ | `apps/notifications/receivers.py:120` | — | Fait |

## Module 12 — Tableau de bord (CDC §3 M12, lignes 225-239)

| ID | Source | Exigence | Verdict | Preuve | Action | Statut |
|---|---|---|---|---|---|---|
| M12-01 | M12 l.227 | CA facturé du mois | ✅ | `apps/dashboard/services.py:203` | — | Fait |
| M12-02 | M12 l.227 | Total encaissé | ✅ | `apps/dashboard/services.py:203` | — | Fait |
| M12-03 | M12 l.227 | Charges du mois | ✅ | `apps/dashboard/services.py:203` | — | Fait |
| M12-04 | M12 l.228 | Marge nette | ✅ | `apps/dashboard/services.py:203` | — | Fait |
| M12-05 | M12 l.229 | Camions disponibles | ✅ | `apps/dashboard/services.py:90` | — | Fait |
| M12-06 | M12 l.229 | Camions en mission | ✅ | `apps/dashboard/services.py:90` | — | Fait |
| M12-07 | M12 l.229 | Camions au garage | ✅ | `apps/dashboard/services.py:90` | — | Fait |
| M12-08 | M12 l.230 | Conso moyenne globale | ✅ | `apps/dashboard/services.py:90` | — | Fait |
| M12-09 | M12 l.231 | Alerte : assurances expirantes | ✅ | `apps/dashboard/services.py:284` ; documents manquants et camions réformés traités (voir M2-22) | Fait (`cbb3d51`) | Fait |
| M12-10 | M12 l.231 | Alerte : permis expirants | ✅ | `apps/dashboard/services.py:341` : en plus des dates qui expirent, fiche permis incomplète (n°, date, catégorie C/E, visite médicale) signalée « non renseigné(e) » ; règle commune `apps/drivers/services.py:242,257` (aussi pour « Voir tout ») ; tests `apps/dashboard/tests/test_dashboard.py:243`, `apps/drivers/tests/test_services.py` ; vérifié dans le navigateur | Fait (`501f90e`) | Fait |
| M12-11 | M12 l.231 | Alerte : pièces sous seuil | ✅ | `apps/dashboard/services.py:336` | — | Fait |
| M12-12 | M12 l.232 | Alerte : factures impayées échues | ✅ | `apps/dashboard/services.py:387` | — | Fait |
| M12-13 | M12 l.234 | RH : effectif | ✅ | `apps/dashboard/services.py:148`, sans le personnel sorti `apps/hr/services.py:543` (test `apps/hr/tests/test_sorties.py`) | — | Fait |
| M12-14 | M12 l.234 | RH : congés / absents | ✅ | `apps/dashboard/services.py:148` | — | Fait |
| M12-15 | M12 l.235 | Finances : CA | ✅ | `apps/dashboard/services.py:203` | — | Fait |
| M12-16 | M12 l.235 | Finances : flux | ✅ | `apps/dashboard/services.py:203` | — | Fait |
| M12-17 | M12 l.235 | Finances : créances | ✅ | `apps/dashboard/services.py:203` | — | Fait |
| M12-18 | M12 l.235 | Finances : marge nette | ✅ | `apps/dashboard/services.py:203` | — | Fait |
| M12-19 | M12 l.236 | Chargé clientèle : clients actifs | ✅ | `apps/dashboard/services.py:173` | — | Fait |
| M12-20 | M12 l.236 | Chargé clientèle : réclamations | ✅ | `apps/dashboard/services.py:173` | — | Fait |
| M12-21 | M12 l.236 | Chargé clientèle : top 3 clients | ✅ | `apps/dashboard/services.py:173` | Docstring périmé `apps/missions/services.py:195` | Fait |
| M12-22 | M12 l.236 | Chargé clientèle : satisfaction | ⚪ | Écarté le 29/09/2026 (CDC l.237) | — | — |
| M12-23 | M12 l.237 | Chargé clientèle : contrats à renouveler | ⚪ | Écarté le 29/09/2026 (CDC l.237) | — | — |
| M12-24 | M12 l.238 | Chauffeur : course du jour | ✅ | `apps/mobile_api/services.py:231` | — | Fait |
| M12-25 | M12 l.238 | Chauffeur : km parcourus | ✅ | `apps/mobile_api/services.py:231` | — | Fait |
| M12-26 | M12 l.238 | Chauffeur : consommation | ✅ | `apps/mobile_api/services.py:231` | — | Fait |
| M12-27 | M12 l.239 | Chauffeur : état du véhicule | ✅ | `apps/mobile_api/services.py:231` | — | Fait |
| M12-28 | M12 l.239 | Chauffeur : prochaine mission | ✅ | `apps/mobile_api/services.py:231` | — | Fait |

## Technique (CDC §4, lignes 243-305)

| ID | Source | Exigence | Verdict | Preuve | Action | Statut |
|---|---|---|---|---|---|---|
| TECH-01 | §4 l.246 | Python 3.14 | ✅ | `Dockerfile:6` | — | Fait |
| TECH-02 | §4 l.246 | Django 5.2.x | ✅ | `requirements/base.txt:1` | — | Fait |
| TECH-03 | §4 l.247 | PostgreSQL 16+ | ✅ | `docker-compose.yml:20` | — | Fait |
| TECH-04 | §4 l.247 | SQLite toléré en dev | ✅ | `config/settings/dev.py` | — | Fait |
| TECH-05 | §4 l.248 | Tailwind CSS | ✅ | `frontend/package.json` | — | Fait |
| TECH-06 | §4 l.248 | Alpine.js | ✅ | `frontend/package.json` | — | Fait |
| TECH-07 | §4 l.248 | FontAwesome 6.5 | ✅ | `frontend/package.json:11` | — | Fait |
| TECH-08 | §4 l.249 | Gunicorn | ✅ | `ops/gunicorn.conf.py` | — | Fait |
| TECH-09 | §4 l.249 | Nginx | ✅ | `nginx/nginx.conf` | — | Fait |
| TECH-10 | §4 l.250 | DRF 3.15+ | ✅ | `requirements/base.txt` | Dépendances non épinglées (TECH-84) | Fait |
| TECH-11 | §4 l.250 | simplejwt 5.3+ | ✅ | `requirements/base.txt` | — | Fait |
| TECH-12 | §4 l.250 | django-filter 24+ | ✅ | `requirements/base.txt:7` | — | Fait |
| TECH-13 | §4 l.250 | drf-spectacular 0.27+ | ✅ | `requirements/base.txt:8` | Vue `SoldeCongesView` sans serializer (`apps/mobile_api/views.py:204`) | Fait |
| TECH-14 | §4 l.251 | Redis 7+ | ✅ | `docker-compose.yml:37` | — | Fait |
| TECH-15 | §4 l.251 | Celery 5.4+ | ✅ | `requirements/base.txt:19` | — | Fait |
| TECH-16 | §4 l.252 | PDF (WeasyPrint / ReportLab) | ✅ | `requirements/base.txt:24` | — | Fait |
| TECH-17 | §4 l.252 | QR : qrcode + Pillow | ✅ | `requirements/base.txt:10-11` | — | Fait |
| TECH-18 | §4 l.253 | Notifications SMS (Twilio) | ⚪ | Écarté le 13/10/2026 : alertes dans l'application et par e-mail (`avenant-decisions-audit.md`) | — | — |
| TECH-19 | §4 l.253 | Notifications push (Firebase) | ⚪ | Écarté le 13/10/2026 : espace chauffeur en page web (`avenant-decisions-audit.md`) | — | — |
| TECH-20 | §4 l.254 | Stockage S3 / MinIO | ⚪ | Écarté le 13/10/2026 : disque du serveur, chiffré dans la sauvegarde nocturne (`avenant-decisions-audit.md`) | — | — |
| TECH-21 | §4 l.255 | Docker | ✅ | `Dockerfile` | `certs/` copié dans l'image (TECH-49) | Fait |
| TECH-22 | §4 l.255 | Docker Compose | ✅ | `docker-compose.yml` | — | Fait |
| TECH-23 | §4 l.256 | Sentry | ✅ | `config/settings/prod.py:125` | — | Fait |
| TECH-24 | §4 l.256 | Prometheus | ❌ | Décision du 13/10/2026 : à mettre en place (`avenant-decisions-audit.md`) | Exposer les mesures | À faire |
| TECH-25 | §4 l.259 | Les 17 apps | ✅ | `config/settings/base.py` (`INSTALLED_APPS`) | — | Fait |
| TECH-26 | §4 l.262 | views → serializers → services → models | ✅ | Les 7 lectures directes passent par des services (`accounting.services.ecritures_manuelles`, `exercices`, `plan_comptable` ; `finance.demandes.ordre_de` ; `hr.services.attributions_de`) ; restent seulement les `get_object_or_404` de l'objet de la page | Fait (`616403e`) | Fait |
| TECH-27 | §4 l.263 | Logique métier dans services.py | ✅ | Aucun calcul métier dans les vues | — | Fait |
| TECH-28 | §4 l.264 | Signaux avec parcimonie | ✅ | `apps/*/signals.py` | — | Fait |
| TECH-29 | §4 l.264 | post_save audit sur modèles sensibles | ✅ | Voir M1-67 (`apps/audit/tests/test_couverture.py`) | Fait | Fait |
| TECH-30 | §4 l.265 | Transactions atomiques : missions | ✅ | `apps/missions/services.py` (`@transaction.atomic`) | — | Fait |
| TECH-31 | §4 l.265 | Transactions atomiques : factures | ✅ | `apps/billing/services.py` | — | Fait |
| TECH-32 | §4 l.265 | Transactions atomiques : OR | ✅ | `apps/garage/services.py` | `corriger_kilometrage` et `expirer_proformas` non atomiques | Fait |
| TECH-33 | §4 l.266 | Permissions par rôle | ✅ | `apps/accounts/mixins.py`, `apps/*/permissions.py` | — | Fait |
| TECH-34 | §4 l.266 | Permissions par objet | ✅ | `apps/accounts/mixins.py` (`charger_objet` après les contrôles de connexion et de rôle) ; 7 vues converties ; test `apps/accounts/tests/test_role_avant_objet.py` (403 pour un identifiant inexistant, toutes vues retrouvées automatiquement) ; objets propres à l'utilisateur : `apps/mobile_api/services.py:54`, `apps/hr/views.py` | Fait (`113e40d`) | Fait |
| TECH-35 | §4 l.267 | API versionnée /api/v1/ | ✅ | `config/urls.py` | — | Fait |
| TECH-36 | §4 l.268 | Couverture ≥ 70 % des services critiques | ✅ | Mesurée : 95 à 100 % sur tous les `services.py` | — | Fait |
| TECH-37 | §4 l.271 | Injection SQL via ORM | ✅ | Aucun `.raw(`, `cursor()`, `.extra(` dans `apps/` | — | Fait |
| TECH-38 | §4 l.272 | CSRF | ✅ | `config/settings/base.py:78`, 104 formulaires avec `csrf_token` | — | Fait |
| TECH-39 | §4 l.272 | Échappement XSS | ✅ | Aucun `|safe`/`mark_safe` | — | Fait |
| TECH-40 | §4 l.273 | Mots de passe Argon2/PBKDF2 | ✅ | `config/settings/base.py:133` | Pas de changement de mot de passe une fois connecté (TECH-87) | Fait |
| TECH-41 | §4 l.274 | HTTPS/TLS obligatoire | ✅ | `config/settings/prod.py:81`, `nginx/nginx.conf` | — | Fait |
| TECH-42 | §4 l.275 | JWT : expiration courte | ✅ | `config/settings/base.py:194` | — | Fait |
| TECH-43 | §4 l.275 | JWT : refresh | ✅ | `config/settings/base.py` (`JWT_SESSION_MAX` = 30 jours) ; `apps/api/auth.py` (`auth_time` à la connexion, `RenouvellementSerializer`) ; révocation au changement de mot de passe, de rôle ou d'activation : `apps/accounts/signals.py`, `apps/accounts/services.py` (`revoquer_jetons_api`) ; tests `apps/api/tests/test_revocation_jetons.py` (7 tests) | Fait (`67c17df`) | Fait |
| TECH-44 | §4 l.276 | MFA obligatoire ADMIN | ✅ | `config/settings/base.py:269`, `apps/accounts/middleware.py:30` | — | Fait |
| TECH-45 | §4 l.276 | MFA obligatoire DIRECTION | ✅ | Idem, et API `apps/api/auth.py:39` | — | Fait |
| TECH-46 | §4 l.277 | Rate limiting anti force brute | ✅ | API : même verrou de compte que le site (`apps/api/auth.py`, `ConnexionView.post`) ; « mot de passe oublié » : 5 demandes/h par IP, 3 par e-mail (`apps/accounts/throttle.py`, `apps/accounts/views.py`) ; Nginx : `limit_req` sur /connexion/, /mot-de-passe/, /api/v1/auth/ (`nginx/nginx.conf`, validé par `nginx -t`) ; tests `apps/accounts/tests/test_force_brute_api_reinitialisation.py` | Fait (`91f55c2`) | Fait |
| TECH-47 | §4 l.278 | Secrets via .env | ✅ | `config/settings/prod.py` exige ses secrets ; `config/wsgi.py`, `config/asgi.py`, `config/celery.py` partent sur la production par défaut (jamais DEBUG par oubli) ; `manage.py` garde le développement ; test `apps/core/tests/test_deploiement.py` | Fait (`1995788`) | Fait |
| TECH-48 | §4 l.279 | RBAC rôle | ✅ | Voir TECH-33 | — | Fait |
| TECH-49 | §4 l.279 | RBAC objet | ✅ | Voir TECH-34 ; `.dockerignore` exclut `certs/`, `*.pem`, `*.key`, `COMPTES-ESSAI.md` ; test `apps/core/tests/test_deploiement.py` | Fait (`1995788`, `113e40d`) | Fait |
| TECH-50 | §4 l.280 | HSTS | ✅ | `config/settings/prod.py:84` | — | Fait |
| TECH-51 | §4 l.280 | X-Frame-Options | ✅ | `config/settings/prod.py:88` | — | Fait |
| TECH-52 | §4 l.280 | X-Content-Type-Options | ✅ | `config/settings/prod.py:87` | — | Fait |
| TECH-53 | §4 l.280 | CSP | ✅ | `apps/core/middleware.py` | — | Fait |
| TECH-54 | §4 l.281 | CORS restreint | ✅ | `config/settings/base.py:217` | — | Fait |
| TECH-55 | §4 l.282 | Sauvegardes chiffrées | ✅ | `ops/sauvegarde.sh` (GPG AES256) | — | Fait |
| TECH-56 | §4 l.282 | Sauvegardes testées | ✅ | Restauration base et fichiers jouée le 12/10/2026 (GUIDE-DEPLOIEMENT.md § 9 et § vérifications) ; procédure mensuelle depuis le service ; rappel sur l'écran « Sauvegardes » | Essai mensuel à faire en production | Fait |
| TECH-57 | §4 l.283 | Soft delete sur données sensibles | ✅ | `apps/core/models.py` ; admin : `apps/core/admin.py` (`SansSuppressionAdmin` pour plein, mission, OR, article, congé ; `SuppressionLogiqueAdmin` avec restauration pour les fiches de référence) ; voir AUD-04 | Fait (`1c7a72f`) | Fait |
| TECH-58 | §4 l.284 | Journal d'audit append-only | ✅ | Voir M1-65 | — | Fait |
| TECH-59 | §4 l.285 | Session 15 min mobile | ✅ | `config/settings/base.py:221` | — | Fait |
| TECH-60 | §4 l.285 | Session 30 min desktop | ✅ | `config/settings/base.py:91` | — | Fait |
| TECH-61 | §4 l.288 | < 500 ms pages simples | ✅ | Mesuré 6 à 60 ms (SQLite) | Re-mesurer sur PostgreSQL | Fait |
| TECH-62 | §4 l.289 | < 2 s dashboards | ✅ | Mesuré 117 à 200 ms | — | Fait |
| TECH-63 | §4 l.290 | select_related / prefetch_related | ✅ | Requêtes constantes sur 22 pages | — | Fait |
| TECH-64 | §4 l.290 | only / defer | ✅ | Requêtes constantes, volumes modestes | — | Fait |
| TECH-65 | §4 l.291 | Cache Redis des KPI | ✅ | `apps/dashboard/services.py` (`_en_cache` : calcul direct si Redis tombe) ; `apps/accounts/throttle.py` (compteurs tolérants à la panne, Nginx limite toujours) ; panne signalée dans les journaux ; tests `apps/dashboard/tests/test_cache_en_panne.py` | Fait (`73befb0`) | Fait |
| TECH-66 | §4 l.292 | Pagination obligatoire | ✅ | Grand livre par pages de 50 (cumul calculé sur toute la période, `apps/accounting/views.py`) ; plan comptable (50), exercices (20), enveloppes (24) paginés ; journal de trésorerie déjà paginé (25) ; test `apps/accounting/tests/test_soldes_ouverture.py` | Fait (`f07a706`) | Fait |
| TECH-67 | §4 l.293 | Index BDD sur colonnes de recherche | ✅ | Index sur `date_emission`, `date_reglement`, `date_depense` (+ catégorie), `date_mouvement`, `date_plein`, `date_expiration` (documents), dates d'expiration du permis et de la visite médicale (migrations `*_index_dates`, appliquées sur PostgreSQL 16) | Fait (`dd05e33`) | Fait |
| TECH-68 | §4 l.294 | Celery : notifications | ✅ | `apps/notifications/tasks.py` | — | Fait |
| TECH-69 | §4 l.294 | Celery : alertes | ✅ | `config/settings/base.py` (beat quotidien) | — | Fait |
| TECH-70 | §4 l.294 | Celery : PDF | ✅ | Décision du 13/10/2026 (`avenant-decisions-audit.md`) : `apps/core/documents_pdf.py:45` (`telecharger`, appelé par `apps/core/views.py` et `apps/core/xlsx.py` : rapports, listes, factures, devis, avoirs), tâche `apps/core/tasks.py` ; `DocumentPdf` (`apps/core/models.py`, réservé au demandeur, purgé après 24 h) ; page d'attente `templates/core/document_pdf.html` ; prod `config/settings/prod.py` (`PDF_EN_TACHE_DE_FOND`), volume media du worker `docker-compose.yml` ; codes de mission et autorisation de congé restent dans la requête (jamais stockés) ; tests `apps/core/tests/test_pdf_tache_de_fond.py` (14 tests) ; vérifié dans le navigateur | Fait (`89076d1`) | Fait |
| TECH-71 | §4 l.295 | CDN Cloudflare | ❌ | Décision du 13/10/2026 : derrière Cloudflare (`avenant-decisions-audit.md`) | Réglages + guide | À faire |
| TECH-72 | §4 l.296 | Compression gzip | ✅ | `nginx/nginx.conf:26` | — | Fait |
| TECH-73 | §4 l.297 | Monitoring Sentry | ✅ | `config/settings/prod.py:125` | — | Fait |
| TECH-74 | §4 l.300 | Chrome (2 dernières versions) | ❓ | Aucun test navigateur réel | Recette manuelle | Hors code |
| TECH-75 | §4 l.300 | Edge | ❓ | Idem | Recette manuelle | Hors code |
| TECH-76 | §4 l.300 | Safari | ❓ | Idem | Recette manuelle | Hors code |
| TECH-77 | §4 l.300 | Firefox | ❓ | Idem | Recette manuelle | Hors code |
| TECH-78 | §4 l.301 | Responsive mobile-first | ✅ | `templates/base.html:5`, `apps/mobile_api/templates/mobile/base.html:5` | — | Fait |
| TECH-79 | §4 l.302 | PWA espace chauffeur | ✅ | `apps/mobile_api/views_web.py:388` | — | Fait |
| TECH-80 | §4 l.303 | Hors ligne + sync différée | ⚪ | Écarté le 29/09/2026 (CDC l.303) | — | — |
| TECH-81 | §4 l.304 | Accessibilité WCAG 2.1 AA | ✅ | Bouton des codes `bg-amber-700` (5,0:1) ; textes d'exemple `slate-500` (4,8:1, `apps/core/forms.py`, `apps/mobile_api/forms.py`) ; menu mobile fermé `max-lg:invisible` (hors tabulation, `templates/base.html`) ; « Motif du rejet » avec libellé ; feuille Tailwind recompilée ; vérifié dans le navigateur (téléphone fermé/ouvert, grand écran) | Fait (`5cc6445`) | Fait |
| TECH-82 | §4 l.305 | Export PDF | ✅ | Vrai PDF serveur partout : 16 listes, 5 rapports comptables, trésorerie, facture, devis, frais de mission, tableau de bord (`apps/core/pdf.py`, `TelechargementPdfMixin`, `reponse_rapport`) ; `apps/core/tests/test_pdf.py` (43 tests) ; rendu contrôlé (personnel, bilan, facture) | Fait | Fait |
| TECH-83 | §4 l.305 | Export Excel | ✅ | Bouton « Excel » (`ExportXlsxMixin`, mêmes droits et filtres, valeurs brutes) sur missions, flotte, carburant, stock, clients, chauffeurs, congés, personnel et ordres de réparation, en plus de la finance et de la comptabilité ; tests `apps/core/tests/test_exports_excel.py` (13 tests) | Fait (`f7b49cc`) | Fait |
| TECH-84 | checklist Technique | Dépendances reproductibles | ✅ | `requirements/prod.lock` (72 paquets, versions exactes pour Linux / Python 3.14), généré par `outils/verrouiller_dependances.py` ; appliqué en contrainte par le `Dockerfile` ; test `apps/core/tests/test_deploiement.py` | Fait (`0d16e6f`) | Fait |
| TECH-85 | checklist Technique | Migrations à jour | ✅ | `manage.py makemigrations --check` : aucun changement | — | Fait |
| TECH-86 | checklist Technique | Suite de tests verte | ✅ | 3 173 tests réussis, 0 échec ; suite rejouée avec l'horloge avancée d'un et de deux ans sans autre échec (seul un artefact du décalage) ; voir AUD-01 | Fait (`1c87fbb`) | Fait |
| TECH-87 | §4 l.273 | Changement de mot de passe une fois connecté | ✅ | `apps/accounts/views.py:91` (`/mon-mot-de-passe/`, lien clé dans `templates/base.html`) : ancien mot de passe exigé, validateurs, session gardée, événement tracé (`apps/audit/signals.py`) ; tests `apps/accounts/tests/test_changer_mot_de_passe.py` (6 tests) ; vérifié dans le navigateur | Fait (`358b5c9`) | Fait |

## Recette (CDC §6, lignes 330-343)

| ID | Source | Exigence | Verdict | Preuve | Action | Statut |
|---|---|---|---|---|---|---|
| REC-01 | §6 l.332 | 20 camions et chauffeurs configurés | ✅ | Scénario d'audit : import de 20 personnes, 20 chauffeurs, 20 camions | Rejouer en fin de mission | Fait |
| REC-02 | §6 l.333 | Mission créée, affectée, suivie sur téléphone, clôturée | ✅ | Scénario d'audit (API mobile 200, clôture) | Rejouer en fin de mission | Fait |
| REC-03 | §6 l.335 | Plein : conso exacte + anomalie si surconsommation | ✅ | Scénario d'audit (30,00 puis 40,00 L/100 km, alerte jaune) | Rejouer avec un cas > 45 L/100 km | Fait |
| REC-04 | §6 l.337 | OR bloque puis libère le camion | ✅ | Scénario d'audit | Rejouer en fin de mission | Fait |
| REC-05 | §6 l.338 | Sortie de pièce : stock + alerte seuil bas | ✅ | Scénario d'audit | Rejouer avec un compte PARCAUTO | Fait |
| REC-06 | §6 l.340 | Facture : créance + écriture équilibrée | ✅ | Scénario d'audit (VTE-2026-0001, débit = crédit) | Rejouer en fin de mission | Fait |
| REC-07 | §6 l.342 | Alertes de documents expirants sur le tableau de bord | ✅ | Scénario d'audit (document à J+10 visible) | Rejouer en fin de mission | Fait |

## Avenants (exigences ajoutées ou modifiées)

| ID | Source | Exigence | Verdict | Preuve | Action | Statut |
|---|---|---|---|---|---|---|
| AV-01 | R7 | Report de congé : la date de reprise n'est pas un jour de congé | ✅ | Décision du 13/10/2026 : on saisit le jour de reprise, le congé s'arrête la veille (`apps/hr/services.py`, `demander_report` / `approuver_report`) ; champ `ReportConge.date_reprise` (migration `0013`) ; test `test_le_jour_de_reprise_n_est_pas_un_jour_de_conge` | Fait (`66cea4c`) | Fait |
| AV-02 | R8 §2 | RH = FINANCES partout (dont frais de mission) | ✅ | `apps/missions/permissions.py` (RH dans `FRAIS_CONSULTATION` et `FRAIS_VALIDATION_FINANCES`), décision du 12/10/2026, note datée dans l'avenant R8 § 2 | Fait (`d1456ed`) | Fait |
| AV-03 | R2 | Dépassement d'enveloppe validé : la dépense suivante n'est plus bloquée | ✅ | Décision du 13/10/2026 : la validation relève le plafond du montant validé (`apps/finance/demandes.py`, `_relever_le_plafond`) ; `DemandeDepense.enveloppe` (migration `0007`) ; tests `apps/finance/tests/test_demandes.py` | Fait (`061bc70`) | Fait |
| AV-04 | Compta P3 | Reclassement du mode de paiement d'une dépense : écriture correcte | ✅ | `apps/accounting/services.py:421-455` (débit de l'ancien compte, crédit du nouveau, pièce de la dépense) ; reprise `apps/accounting/services.py:461,479` + commande `corriger_reclassements_inverses` ; tests `apps/accounting/tests/test_receivers.py:224,238`, `apps/accounting/tests/test_reprise_reclassements.py` (8 tests) ; couverture 99 % ; avenant P3 corrigé | Corrigé (`595cb83`, `ed05eec`, `50497cc`) ; lancer la commande en production | Fait |
| AV-05 | Compta P1/F | Comptes utilisés par le code non désactivables | ✅ | `apps/accounting/constants.py:64` (`COMPTES_UTILISES_PAR_LE_CODE`) ; refus au service `apps/accounting/services.py:133,138`, case grisée à l'écran, lecture seule et suppression interdite dans l'admin ; tests `apps/accounting/tests/test_comptes_proteges.py` (5 tests) ; vérifié dans le navigateur | Fait (`1c53252`) | Fait |
| AV-06 | Compta P1 | Écritures validées immuables | ✅ | `apps/accounting/models.py:65,160` (`EcritureQuerySet`, `LigneQuerySet` : pas de modification ni suppression en masse) ; déclencheurs PostgreSQL (migration `0005_verrou_ecritures_validees`) ; tests `apps/accounting/tests/test_verrou_ecritures.py` (dont 2 sur PostgreSQL 16) | Fait (`a407692`) | Fait |
| AV-07 | Compta P6 | Grand livre et balance d'une période : solde d'ouverture | ✅ | `apps/accounting/services.py:777` (`solde_ouverture`, clôtures passées comprises), `apps/accounting/services.py:814` (balance : colonnes d'ouverture) ; écran, impression, Excel ; tests `apps/accounting/tests/test_soldes_ouverture.py` (6 tests) ; vérifié dans le navigateur | Fait (`f69eb5d`) | Fait |
| AV-08 | Compta F | Plan comptable : numéro et nature cohérents | ✅ | `apps/accounting/services.py:88,100` : 2 à 10 chiffres, nature permise par la classe SYSCOHADA (1 passif ; 2-3 actif ; 4-5 actif/passif ; 6 charge ; 7 produit ; 8 charge/produit ; 9 libre) ; tests `apps/accounting/tests/test_plan_comptable_coherence.py` (27 tests) | Fait (`fc3b649`) | Fait |
| AV-09 | Compta P4 | Saisie manuelle : sens contrôlé, comptes actifs revérifiés | ✅ | `apps/accounting/services.py:692` (sens débit/crédit), `apps/accounting/services.py:727` (comptes revérifiés à la validation) ; tests `apps/accounting/tests/test_saisie_manuelle_controles.py` | Fait (`83f0cb1`) | Fait |
| AV-10 | Compta P4/G | OD sur un compte de trésorerie | ✅ | Décision du 13/10/2026 : interdit à l'ajout et à la validation (`apps/accounting/services.py`, `_exiger_hors_tresorerie`) ; tests `apps/accounting/tests/test_saisie_manuelle_controles.py` | Fait (`685a3c8`) | Fait |
| AV-11 | Compta (CDC l.340) | Avoir / annulation d'une facture émise | ✅ | Décision du 13/10/2026 : modèle `Avoir` (migration `billing.0008`) ; `apps/billing/services.py` (`creer_avoir`, `valider_avoir`, `refuser_avoir` ; reste à recouvrer et CA réduits) ; écriture inverse `apps/accounting/services.py` (`comptabiliser_avoir`) ; fiche facture (section Avoirs), document et PDF de l'avoir ; notifications ; tests `apps/billing/tests/test_avoirs.py` | Fait (`eda857c`) | Fait |
| AV-12 | Compta C | Annulation / correction d'une dépense | ✅ | Décision du 13/10/2026 : `apps/billing/services.py` (`annuler_depense` : Finance, RH, Direction, admin ; motif ; dépense manuelle seulement) ; écriture contre-passée, pointage défait (`depense_annulee`) ; écran : lien « Annuler » dans la liste des dépenses ; tests `apps/billing/tests/test_annulation_depense.py` | Fait (`031ccd0`) | Fait |
| AV-13 | Import | Valeurs non finies (NaN, Infinity, nombre énorme) | ✅ | `apps/importation/services.py` (`_nombre_fini`, `_entier`, `_decimal` : nombre fini et borné à la capacité du champ en base) ; import RH : `apps/hr/services.py` (`SALAIRE_MAX`) ; tests `apps/importation/tests/test_fichiers_pieges.py` ; vérifié sur PostgreSQL 16 | Fait (`ec4190e`) | Fait |
| AV-14 | Import | Fichier à dimension fausse | ✅ | `apps/importation/services.py` (`reset_dimensions()` avant lecture) ; test `test_une_dimension_fausse_ne_fait_perdre_aucune_ligne` | Fait (`ec4190e`) | Fait |
| AV-15 | Import | Enregistrements supprimés logiquement | ✅ | Décision du 12/10/2026 : erreur de ligne « restaurez la fiche ou retirez la ligne » pour employé, client, camion et import RH (`apps/importation/services.py`, `apps/hr/services.py`) ; règle dans `apps/importation/README.md` ; tests `apps/importation/tests/test_fichiers_pieges.py` | Fait (`e75f07f`) | Fait |
| AV-16 | Import | Archives piégées (zip bomb) | ✅ | `apps/core/classeurs.py` : sommaire de l'archive lu avant ouverture, refus au-delà de 50 Mo décompressés ou 500 éléments ; import général et import RH (limite de 5 Mo ajoutée au formulaire RH) ; tests `apps/core/tests/test_classeurs.py` | Fait (`83bce63`) | Fait |
| AV-17 | Import RH | Import du personnel idempotent et robuste | ✅ | `apps/hr/services.py:236` : un employé déjà présent (même nom et prénom, sans accents ni majuscules, comme `apps/importation`) est signalé et non recréé ; fichier illisible refusé avec un message au lieu d'une 500 ; tests `apps/hr/tests/test_import_personnel.py` (6 nouveaux) | Fait (`0b38030`) | Fait |

## Écarts d'audit sans exigence écrite (qualité, sécurité, cohérence)

| ID | Rattachement | Écart | Verdict | Preuve | Action | Statut |
|---|---|---|---|---|---|---|
| AUD-01 | TECH-86 | 3 tests à dates codées en dur échouent depuis le 08/10/2026 | ✅ | `apps/notifications/tests/test_receivers.py` (jour du report fixé) ; 18 autres tests datés corrigés avant d'échouer : `apps/hr/tests/test_report_conge.py` (fixture « aujourd'hui »), `apps/finance/tests/test_demandes.py`, `apps/hr/tests/test_recrutement.py`, `apps/api/tests/test_v1.py` | Fait (`1c87fbb`) | Fait |
| AUD-02 | M5 | Mission sans issue : ni annulation ni transfert (panne définitive) | ✅ | Décision du 13/10/2026 : `apps/missions/services.py` (`annuler_mission` avant le départ, `transferer_mission` en route, historique `TransfertMission`) ; devis annulé (`apps/billing/receivers.py`) ; écrans : « Annuler la mission » sur la fiche, page de transfert ; notifications ; tests `apps/missions/tests/test_annulation_transfert.py` (12 tests) ; vérifié dans le navigateur (formulaire d'annulation) | Fait (`16be438`) | Fait |
| AUD-03 | M6-07 | Pas d'annulation ni de correction d'un plein | ✅ | Décision du 13/10/2026 : `apps/fuel/services.py` (`annuler_plein`, `peut_annuler` : Parc Auto, Direction, admin ; motif ; dernier plein du camion seulement) ; dépense annulée (`apps/billing/services.py`, `annuler_depense_automatique`), écriture contre-passée, pointage défait (signaux `plein_annule`, `depense_annulee`) ; écran `/carburant/<id>/annuler/` ; tests `apps/fuel/tests/test_annulation_plein.py` ; vérifié dans le navigateur | Fait (`a8d15ac`) | Fait |
| AUD-04 | TECH-57 | Suppression physique via l'admin Django | ✅ | `apps/core/admin.py` appliqué à `apps/fuel/admin.py`, `apps/missions/admin.py`, `apps/garage/admin.py`, `apps/inventory/admin.py`, `apps/hr/admin.py`, `apps/customers/admin.py`, `apps/fleet/admin.py`, `apps/drivers/admin.py`, `apps/notifications/admin.py` ; comptes : `apps/accounting/admin.py` (AV-05) ; test `apps/core/tests/test_admin_suppression.py` (tout admin `BaseModel` vérifié) | Fait (`1c7a72f`) | Fait |
| AUD-05 | M9-16 | Centimes acceptés (règlements, dépenses, mouvements) | ✅ | Refusés, jamais arrondis : `apps/core/montants.py` (`exiger_montant_entier`), appelé par billing, finance, missions, garage, inventory, fuel, accounting ; décision du 12/10/2026 (`avenant-montants-fcfa.md`) ; tests `apps/core/tests/test_montants.py` (13 tests) | Fait (`d621d1e`) | Fait |
| AUD-06 | M9-16 | Double soumission non protégée (règlement, dépense, mouvement, imprévu) | ✅ | Navigateur : un formulaire POST envoyé une fois (`static/js/app.js:27`) ; serveur : enregistrement identique de moins d'une minute refusé (`apps/core/doublons.py`, `apps/billing/services.py:469,661`, `apps/finance/services.py:85`, `apps/missions/terrain.py:98,128`) ; tests `apps/core/tests/test_doublons.py` (6 tests) | Fait (`762f616`) | Fait |
| AUD-07 | M11-11 | Même compte en N1 et N2 | ✅ | `apps/hr/services.py:511,522` ; voir M11-11 ; tests `apps/hr/tests/test_separation_n1_n2.py` | Fait (`a1a8ddf`, `ab285ae`) | Fait |
| AUD-08 | TECH-46 | `TRUSTED_PROXY_COUNT` absent de `docker-compose.yml` | ✅ | `docker-compose.yml` (`web`, `realtime` : `${TRUSTED_PROXY_COUNT:-1}`) ; guide § variables mis à jour | Fait | Fait |
| AUD-09 | M1-11 | L'ADMIN peut créer un compte DIRECTION et valider à sa place | ✅ | Décision du 13/10/2026 : permis, la Direction est prévenue (avis urgent, catégorie « Comptes et sécurité », auteur nommé) ; `apps/accounts/signals.py` (`compte_direction_attribue`), `apps/notifications/receivers.py` ; tests `apps/notifications/tests/test_compte_direction.py` | Fait (`dccfbfc`) | Fait |
| AUD-10 | M5-04 | Chauffeur sans permis / visite / catégorie C-E affectable | ✅ | Bloquant (décision du 12/10/2026) : voir M5-04 | Fait (`65c73ed`) | Fait |
| AUD-11 | M1-67 | Imprévu ou avance acceptés sur une mission clôturée | ✅ | `apps/missions/terrain.py:82` (`_exiger_mission_non_cloturee`, appelé par `declarer_imprevu` et `planifier_frais`) ; une mission livrée non clôturée accepte encore un imprévu (trajet retour) ; tests `apps/missions/tests/test_frais_mission.py` | Fait (`af062ba`) | Fait |
| AUD-12 | M2 | Camion aux documents expirés affectable | ✅ | Bloquant si expiré ou manquant (décision du 12/10/2026) : `apps/missions/services.py` (`documents_non_valides_du_vehicule`, `_exiger_vehicule_en_regle`), affectation et départ ; tests `test_documents_et_reaffectation.py` | Fait (`65c73ed`) | Fait |
| AUD-13 | M6-08 | N° de ticket unique globalement (pas par station) | ✅ | Décision du 13/10/2026 : règle conservée, unique dans toute l'entreprise (`avenant-decisions-audit.md`) ; `apps/fuel/models.py` (contrainte `plein_ticket_unique`) | Décidé | Fait |
| AUD-14 | AV-03 | Enveloppe globale dupliquée (NULL), aucun verrou | ✅ | Contrainte `enveloppe_globale_unique_par_mois` (`apps/finance/models.py`, migration `0006` qui supprime d'abord les doublons) ; verrou de l'enveloppe au contrôle (`apps/finance/demandes.py`) ; tests `apps/finance/tests/test_demandes.py`, verts sur PostgreSQL 16 | Fait (`9392dac`) | Fait |
| AUD-15 | M5-11 | Pages contenant les codes sans `Cache-Control: no-store` | ✅ | `apps/missions/views.py` (`MissionDetailView.get` : `no-store, private`, comme le PDF et le QR) ; test `apps/missions/tests/test_documents.py` | Fait (`18d12c2`) | Fait |
| AUD-16 | M11-13 | DIRECTION jamais prévenue des validations de congé en retard | ✅ | `apps/notifications/taches.py` (`_prevenir_la_direction` : une fois par congé et par niveau, jamais pour sa propre demande) ; tests `apps/notifications/tests/test_taches.py` | Fait (`831beaf`) | Fait |
| AUD-17 | TECH-46 | Identifiant mal saisi journalisé en clair à l'échec de connexion | ✅ | `apps/audit/services.py` (`identifiant_journalise` : compte existant en entier, identifiant inconnu masqué) ; tests `apps/audit/tests/test_services.py` | Fait (`3cbe348`) | Fait |
| AUD-18 | TECH-55 | Mot de passe de la base dans les arguments de `pg_dump` | ✅ | `ops/fonctions-sauvegarde.sh:30` (URL sans mot de passe, `.pgpass` temporaire 600) ; tests `apps/sauvegardes/tests/test_scripts.py` | Fait (`b042d06`) | Fait |
| AUD-19 | TECH-43 | Tables de sessions et de jetons jamais purgées | ✅ | `apps/accounts/services.py` (`purger_sessions_et_jetons_expires`), lancée par la tâche quotidienne (`apps/notifications/taches.py`) ; tests `apps/accounts/tests/test_purge.py` | Fait (`5d5d6ac`) | Fait |
| AUD-20 | architecture | `architecture.md` ne reflète plus les dépendances réelles | ✅ | § 3 régénéré depuis les imports réels ; 2 cycles supprimés (`accounts`↔`audit`, `missions`↔`billing`) et une dépendance remontante (`inventory`→`billing`) ; test `apps/core/tests/test_architecture.py` (aucun cycle, schéma conforme au code) | Fait (`db59ec2`) | Fait |
| AUD-21 | M9-10 | Modification d'un devis : TVA écrite « 18,00 » (format français), refusée par le champ numérique qui reste vide | ✅ | `apps/billing/templates/billing/proforma_modifier.html:22,42` (`unlocalize`) ; test `apps/billing/tests/test_proforma_views.py:257` | Fait (`7942790`) | Fait |
| AUD-22 | AV-06 | Pièce d'une écriture limitée à 30 caractères, référence d'une dépense ou d'un mouvement à 100 : erreur 500 sur PostgreSQL au-delà de 30 | ✅ | `apps/accounting/models.py:95` (100 caractères, migration `0004_piece_reference_100`) ; tests `apps/accounting/tests/test_longueur_piece.py` (alignement des longueurs) | Fait (`3e1454a`) | Fait |
| AUD-23 | M11 (sortie du personnel) + TECH-86 | Sortie du personnel : erreur 500 sur PostgreSQL (verrou sur une jointure facultative), invisible sur SQLite | ✅ | `apps/hr/sorties.py:178,248` (`select_for_update(of=("self",))`) ; garde-fou `apps/core/tests/test_compatibilite_postgresql.py` ; suite complète rejouée sur PostgreSQL 16 : 3 232 tests réussis, 0 échec | Fait (`a80ee99`) | Fait |
