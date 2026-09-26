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
signaler un **incident**, déclarer un **imprévu** (panne, avec preuve — R4, prévision de trésorerie des
missions, voir `apps/missions/README.md`). L'accueil est son tableau de bord : course du jour, km du mois,
consommation, état du camion.

Points de sécurité : le chauffeur ne voit jamais les codes secrets ni le prix convenu ; il ne saisit
un plein, un incident ou un imprévu que sur son camion (mission en cours ou à venir, ou camion habituel) ;
session de 15 minutes d'inactivité (jeton d'accès de 15 minutes pour l'API) ; le service worker ne met en
cache que la page « hors connexion », jamais les pages privées.

**Preuve d'un imprévu** (`FraisMission.justificatif`) : premier champ fichier du projet, stocké sur le
disque local (`MEDIA_ROOT`/`media_data`, déjà prévu par le déploiement) — distinct de la photo d'un
incident, toujours pas gérée (S3/MinIO, étape 7, voir ci-dessous).

Lecture des QR : `static/js/scanner.js` (API `BarcodeDetector`, Chrome sur Android). Sur un navigateur
qui ne la propose pas, le bouton n'apparaît pas et le chauffeur saisit le code (8 caractères).

Pas encore fait :
- **Mode hors ligne** (file d'attente des saisies, synchronisation différée, conflits) : écarté sur
  décision de l'utilisateur pour cette étape. Sans réseau, une page « hors connexion » s'affiche.
- Photos des incidents (stockage S3 ou MinIO, étape 7) ; notifications push (Firebase).
- Avoir une position GPS ; envoi du code par SMS à l'expéditeur.
