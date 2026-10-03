# mobile_api

Rôle : espace mobile du chauffeur — cahier-des-charges.md:54, 132-143, 301-303 ; architecture.md ADR-005.
Trois couches sur les mêmes règles :

- `services.py` : ce qu'un chauffeur voit et fait, **sur ses seules données** (une mission d'un autre
  chauffeur est traitée comme inexistante : 404). Il orchestre `missions`, `fuel` et `garage`.
- `views.py` + `urls.py` : **API mobile** `/api/v1/mobile/` (JWT, permission `EstChauffeur`).
- `views_web.py` + `urls_web.py` + `templates/mobile/` : **écrans mobiles** `/chauffeur/`, tactiles,
  installables (manifeste, service worker, icônes).

Ce que fait le chauffeur : voir ses missions (à faire, en cours, livrées cette semaine), faire la
**check-list** du camion, **démarrer**, confirmer la **récupération** puis la **livraison** en scannant
ou saisissant le code (QR), saisir un **plein** (avec la confirmation d'une saisie suspecte),
signaler un **incident**, **demander un congé** (voir ci-dessous), déclarer un **imprévu** (panne, avec preuve — R4, prévision de trésorerie des
missions, voir `apps/missions/README.md`). L'accueil est son tableau de bord : course du jour, km du mois,
consommation, état du camion.

Points de sécurité : le chauffeur ne voit jamais les codes secrets ni le prix convenu ; il ne saisit
un plein, un incident ou un imprévu que sur son camion (mission en cours ou à venir, ou camion habituel) ;
session de 15 minutes d'inactivité (jeton d'accès de 15 minutes pour l'API) ; le service worker ne met en
cache que la page « hors connexion », jamais les pages privées.

**Preuve d'un imprévu** (`FraisMission.justificatif`) : premier champ fichier du projet, stocké sur le
disque local (`MEDIA_ROOT`/`media_data`, déjà prévu par le déploiement) — distinct de la photo d'un
incident, toujours pas gérée (S3/MinIO, étape 7, voir ci-dessous).

Lecture des QR : `static/js/scanner.js`. L'API `BarcodeDetector` (Chrome sur Android) quand elle existe ; sinon
(Safari sur iPhone, Firefox) l'image de la caméra est copiée dans un canvas et lue par jsQR
(`static/vendor/jsqr/`, Apache-2.0, chargé seulement à ce moment-là ; `npm run vendor` dans `frontend/`). Sans caméra
accessible, le bouton n'apparaît pas et le chauffeur saisit le code (8 caractères).

Pas encore fait :
- **Mode hors ligne** (file d'attente des saisies, synchronisation différée, conflits) : écarté sur
  décision confirmée de l'entreprise le 29/09/2026 (cahier-des-charges.md:303). Sans réseau, une
  page « hors connexion » s'affiche.
- Photos des incidents (stockage S3 ou MinIO, étape 7) ; notifications push (Firebase).
- Avoir une position GPS ; envoi du code par SMS à l'expéditeur.

**Congés** (`/chauffeur/conges/`, API `/api/v1/mobile/conges/` et `conges/solde/`) : le chauffeur demande lui-même
ses congés (il n'a pas d'écran RH) et suit leur état ; `services.demander_conge` délègue à
`hr.services.demander_conge`, donc mêmes règles que tout employé : solde suffisant, **pas de chevauchement** avec
un autre congé non refusé, supérieur hiérarchique renseigné (sinon refus avec message). Son supérieur est
prévenu et valide en N1 (48 h) sur l'écran RH, puis la RH en N2 (24 h). Le solde (`droits_conges_du_chauffeur`) et
la liste (`conges_du_chauffeur`) ne portent que sur ses propres congés. Barre de navigation à 6 onglets.
