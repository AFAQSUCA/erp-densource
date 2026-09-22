## Ce que vous allez construire

L'**espace mobile du chauffeur**, sous `/chauffeur/` : des pages **tactiles** (grands boutons, peu de texte),
**installables** sur l'écran d'accueil du téléphone comme une application (PWA).

| Écran | Adresse | Ce que fait le chauffeur |
|---|---|---|
| **Accueil** | `/chauffeur/` | mission du jour, camion, kilomètres du mois, consommation |
| **Missions** | `/chauffeur/missions/` | à faire, en cours, livrées cette semaine |
| **Une mission** | `/chauffeur/missions/<id>/` | **check-list**, **démarrer**, **confirmer la récupération** puis **la livraison** (code ou **scan du QR**) |
| **Plein** | `/chauffeur/plein/` | saisir un plein (avec la confirmation d'une saisie suspecte) |
| **Panne** | `/chauffeur/incident/` | signaler un incident |
| Fichiers de l'application | `manifest.webmanifest`, `sw.js`, `hors-ligne/` | installation, page « hors connexion » |

**Règles de sécurité** propres à cet espace :

- Le chauffeur ne voit **que ses données** : la mission d'un autre chauffeur est traitée comme **inexistante**
  (erreur 404).
- Il ne voit **ni le prix ni les codes secrets**.
- Il ne saisit un plein ou un incident **que sur son propre camion**.
- Sa session dure **15 minutes** d'inactivité (30 pour le bureau).
- Le *service worker* ne met en cache **que** la page « hors connexion », jamais une page privée.

## Prérequis

- Chapitres 1 à 26 terminés.

## Notions de ce chapitre

- **Trois couches sur les mêmes règles** : `services.py` (ce qu'un chauffeur voit et fait, sur ses données
  seulement), l'**API mobile** (`views.py`, chapitre 28) et les **écrans** (`views_web.py`). Les écrans et l'API
  appellent **les mêmes services** : une règle écrite une fois, vraie partout.
- **Une couche de service qui orchestre plusieurs apps** : `mobile_api.services` appelle `missions`, `fuel` et
  `garage` en ajoutant la règle « seulement pour ce chauffeur ».
- **PWA (Progressive Web App)** : un site qu'on peut « installer ». Il faut un **manifeste** (nom, icônes,
  couleurs, page de départ) et un **service worker** (un script que le navigateur exécute en tâche de fond).
- **Servir un fichier depuis une vue** : `sw.js` et `manifest.webmanifest` sont fabriqués par des vues
  (`ServiceWorkerView`, `ManifesteView`) pour connaître le bon préfixe d'adresse et rester à jour.
- **`BarcodeDetector`** : une API du navigateur (Chrome sur Android) qui lit un code QR avec la caméra.
  `scanner.js` l'utilise ; quand elle n'existe pas, le bouton n'apparaît pas et le chauffeur **saisit le code à la
  main**.
- **Pas de JavaScript en ligne** : même le *service worker* est enregistré par `sw-register.js`, à qui la
  page transmet l'adresse par `data-sw`.
- **Alpine.js** : le composant `scannerCode` pilote l'ouverture de la caméra (`x-data="scannerCode(…)"`).

## Étape 1 — Créer l'application

```bash
mkdir -p apps/mobile_api/templates/mobile apps/mobile_api/tests
```

{{VIDES}}

## Étape 2 — La couche de service du chauffeur

{{FICHIER apps/mobile_api/exceptions.py}}

{{FICHIER apps/mobile_api/services.py}}

À lire :

1. **`missions_du_chauffeur`**, **`mission_du_chauffeur`** : ne renvoient **que** les missions du chauffeur ;
   une autre mission lève `MissionIntrouvable`.
2. **`actions_possibles`** : ce que le chauffeur peut faire selon le statut (démarrer, récupérer, livrer).
3. **`demarrer`**, **`confirmer_recuperation`**, **`livrer`** : délèguent à `missions.services` après avoir
   contrôlé que la mission est bien à lui.
4. **`vehicule_courant`**, **`_vehicules_autorises`**, **`saisir_plein`** : un plein n'est accepté que sur *son*
   camion (mission en cours ou à venir, ou camion habituel).
5. **`enregistrer_checklist`**, **`declarer_incident`** : délèguent à `garage.terrain`.
6. **`tableau`** : les chiffres de l'accueil.

{{FICHIER apps/mobile_api/permissions.py}}

{{FICHIER apps/mobile_api/serializers.py}}

`permissions.py` et `serializers.py` servent surtout à l'**API mobile** du chapitre 28 ; ils sont écrits ici parce
qu'ils appartiennent à la même couche.

{{FICHIER apps/mobile_api/apps.py}}

## Étape 3 — Formulaires, vues, adresses de l'espace mobile

{{FICHIER apps/mobile_api/forms.py}}

{{FICHIER apps/mobile_api/views_web.py}}

Repérez `ChauffeurRequisMixin` : il exige un compte **CHAUFFEUR rattaché à une fiche chauffeur** (`chauffeur_de`),
sinon 403. Toutes les vues s'appuient dessus.

{{FICHIER apps/mobile_api/urls_web.py}}

{{FICHIER apps/mobile_api/views.py}}

{{FICHIER apps/mobile_api/urls.py}}

(Les deux derniers fichiers sont l'**API mobile** ; ils seront montés au chapitre 28.)

## Étape 4 — Gabarits, JavaScript et service worker

{{FICHIER apps/mobile_api/templates/mobile/base.html}}

`base.html` de l'espace mobile : la barre de navigation du bas (Accueil, Missions, Plein, Panne), le manifeste,
le service worker (enregistré par `sw-register.js`, **sans code en ligne**).

{{FICHIER apps/mobile_api/templates/mobile/accueil.html}}

{{FICHIER apps/mobile_api/templates/mobile/missions.html}}

{{FICHIER apps/mobile_api/templates/mobile/_carte_mission.html}}

{{FICHIER apps/mobile_api/templates/mobile/mission.html}}

{{FICHIER apps/mobile_api/templates/mobile/checklist.html}}

{{FICHIER apps/mobile_api/templates/mobile/plein.html}}

{{FICHIER apps/mobile_api/templates/mobile/incident.html}}

{{FICHIER apps/mobile_api/templates/mobile/_scanner.html}}

{{FICHIER static/js/scanner.js}}

{{FICHIER static/js/sw-register.js}}

{{FICHIER apps/mobile_api/templates/mobile/sw.js}}

Le *service worker* met en cache **uniquement** la page « hors connexion » et l'icône. Pour toute navigation, il
tente le réseau et, s'il échoue, affiche la page « hors connexion ». Les pages privées ne sont **jamais**
stockées.

{{FICHIER apps/mobile_api/templates/mobile/hors_ligne.html}}

Cette page est **autonome** : aucun script, aucune ressource externe, un simple lien « Réessayer », pour qu'elle
s'affiche même sans réseau.

## Étape 5 — Tests

{{RESTANTS}}

## Étape 6 — Brancher dans les réglages et les adresses

{{CONFIG}}

```bash
cd frontend
npm run build:css
cd ..
```

## Vérifier le chapitre

```bash
python manage.py check
```

{{PYTEST}}

**Dans le navigateur.** Sur un ordinateur, ouvrez les outils de développement (`F12`) puis le **mode appareil
mobile** (icône téléphone/tablette). Lancez `python manage.py runserver`.

1. Créez une mission (`demo_charge`), planifiez-la et **affectez-la** (`demo_direction`) au chauffeur `Moussa
   Ouattara` et au camion `1234 AB 01` (chapitre 21).
2. Connectez-vous avec **`demo_chauffeur`** : vous arrivez **directement** sur `/chauffeur/`. L'accueil montre la
   mission du jour, le camion, les kilomètres et la consommation. Le **prix** et les **codes** n'apparaissent
   nulle part.
3. Ouvrez la mission : faites la **check-list** (mettez « Freins » en **KO** avec une remarque : le Parc Auto est
   prévenu, la cloche de `demo_parcauto` le montre), puis **Démarrer**.
4. **Récupération** : saisissez le code de l'expéditeur (visible sur la fiche de bureau, chapitre 21). Puis
   **Livraison** avec le code du destinataire et le kilométrage. (Sur un vrai téléphone Android avec Chrome, le
   bouton **Scanner** ouvre la caméra ; sinon on tape le code.)
5. **Plein** : saisissez un plein sur le camion de la mission. **Panne** : signalez un incident grave : la cloche
   de `demo_parcauto` et de `demo_direction` compte l'alerte.
6. Essayez `/missions/` : le chauffeur reçoit **Accès refusé**. Essayez l'adresse de la mission d'un **autre**
   chauffeur : **404**.
7. Dans les outils de développement (onglet *Application*), le **service worker** est enregistré et le
   **manifeste** est lu. Coupez le réseau (case *Offline*) et rechargez : la page « **hors connexion** » s'affiche.

## Ce qu'il faut retenir

- **Une seule couche de règles** : l'API et les écrans appellent les mêmes services, donc restent cohérents.
- Le **chauffeur** n'accède qu'à **ses** données : c'est le **service** qui le garantit, pas seulement l'affichage.
- Une **PWA** = manifeste + service worker + page hors connexion ; ici on n'y met **jamais** de page privée.
- Un secret n'est jamais envoyé à qui n'en a pas besoin : les **codes ne sont pas dans les pages du chauffeur**.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 27 : espace mobile du chauffeur (PWA, check-list, codes, plein, incident)"
```
