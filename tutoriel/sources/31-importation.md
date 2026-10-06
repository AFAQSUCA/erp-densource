## Ce que vous allez construire

**`importation`** : charger les données **réelles** de l'entreprise (personnel, chauffeurs, copilotes, clients,
camions) depuis **un classeur Excel**, au lieu de les saisir fiche par fiche. C'est une app de *reprise de données*,
réservée à l'**administrateur**.

| Écran | Adresse | Qui |
|---|---|---|
| **Import de données** (dépôt du fichier, rapport par feuille et par ligne, case « Simulation ») | `/import/` | **ADMIN seulement** |
| **Télécharger le modèle** (classeur Excel prêt à remplir) | `/import/modele.xlsx` | ADMIN seulement |

Le classeur contient **une feuille d'instructions et cinq feuilles de données** : Personnel, Véhicules, Chauffeurs,
Copilotes, Clients. Une copie du modèle est versionnée à la racine du dépôt
(`modele-donnees-entreprise-DEN-Source.xlsx`).

## Prérequis

- Chapitres 1 à 30 terminés (l'import s'appuie sur `hr`, `drivers`, `customers` et `fleet`, et sur l'écran
  des utilisateurs du chapitre 17).

## Ce que ce chapitre apporte de nouveau

- **Une source unique pour le modèle et pour l'import** : `modele.py` décrit les colonnes **une seule fois** ; le
  modèle téléchargeable et la lecture du fichier l'utilisent tous les deux, ils ne peuvent donc pas diverger. Les
  listes déroulantes viennent des énumérations de l'application (postes, départements, statuts…).
- **« Tout ou rien » avec des points de sauvegarde** : tout l'import s'exécute dans **une transaction** ; chaque
  ligne dans un **point de sauvegarde** (`transaction.atomic()` imbriqué), pour pouvoir noter l'erreur d'une ligne
  sans interrompre la lecture des suivantes. À la fin, s'il y a la moindre erreur — ou si la case
  « Simulation » est cochée — **tout est annulé** (`transaction.set_rollback(True)`).
- **Ne rien écraser** : une personne, un client ou un camion déjà présent est laissé tel quel ; réimporter le même
  fichier ne crée donc **aucun doublon**.
- **Réutiliser les services** plutôt que d'écrire dans les tables : chaque ligne passe par `hr.recruter`,
  `customers.creer_client`, `fleet.creer_vehicule`, `drivers.modifier_chauffeur`… — mêmes contrôles, même journal
  d'audit qu'à la saisie à l'écran.
- **Fabriquer un classeur Excel avec `openpyxl`** : en-têtes, ligne d'exemple, listes déroulantes
  (`DataValidation`).

## Étape 1 — Créer l'application

```bash
mkdir -p apps/importation/management/commands apps/importation/tests templates/importation
```

{{VIDES}}

## Étape 2 — Le modèle Excel

{{FICHIER apps/importation/modele.py}}

Trois idées à retenir : `COLONNES` (l'ordre et les intitulés exacts de chaque feuille), `EXEMPLES` (la ligne jaune de
chaque feuille — l'import l'**ignore** si elle est restée telle quelle : un exemple oublié ne devient jamais une
vraie fiche) et `construire_modele()` (le classeur en mémoire).

{{FICHIER apps/importation/management/commands/generer_modele_import.py}}

Cette commande écrit le classeur sur disque ; la copie versionnée à la racine du dépôt est produite ainsi.

## Étape 3 — Les droits et l'import

{{FICHIER apps/importation/permissions.py}}

{{FICHIER apps/importation/services.py}}

Lisez `importer_classeur` de haut en bas :

1. Seul l'**ADMIN** peut importer (un superutilisateur agit en ADMIN).
2. Le fichier est ouvert ; les feuilles sont reconnues par le **début de leur nom** (« Personnel », « Personnel
   (Employés) »… sont acceptés), et leurs **en-têtes** doivent être ceux du modèle.
3. L'ordre de traitement est **personnel → chauffeurs → copilotes → clients → camions** : un chauffeur doit exister
   avant d'être le « chauffeur habituel » d'un camion.
4. Chaque ligne est lue par la fonction de sa feuille (`_personnel`, `_chauffeur`, `_client`, `_vehicule`…) qui
   renvoie `"cree"`, `"maj"` ou `"present"`, ou lève `_Ligne` avec un message **destiné à l'utilisateur** (feuille et
   numéro de ligne ajoutés par l'appelant).
5. Les statuts acceptés sont **ceux qui se posent à la main** : « En mission », « En congé » et « En maintenance »
   sont posés par les missions, les congés et le garage, jamais depuis un fichier.

## Étape 4 — L'écran

{{FICHIER apps/importation/forms.py}}

{{FICHIER apps/importation/views.py}}

{{FICHIER apps/importation/urls.py}}

{{FICHIER apps/importation/apps.py}}

`ready()` ajoute l'entrée « Import de données » au menu (ADMIN seulement) : le système de menu du chapitre 3
n'importe aucune app métier, ce sont les apps qui s'y inscrivent.

{{CONFIG}}

{{FICHIER templates/importation/importer.html}}

## Étape 5 — Tests, README et compilation des styles

{{RESTANTS}}

```bash
cd frontend
npm run build:css
cd ..
```

## Vérifier le chapitre

```bash
python manage.py check
python manage.py generer_modele_import
```

**Résultat attendu :** `Modèle écrit : …/modele-donnees-entreprise-DEN-Source.xlsx`. Ce fichier binaire n'est pas montré dans
ce tutoriel : on le **génère** (un test compare sa copie versionnée au code ; sans cette copie, il est simplement ignoré).

{{PYTEST}}

**Un import dans le navigateur** (compte `demo_admin`, qui demande sa double authentification à la première
connexion) :

1. Menu **Import de données** → **Télécharger le modèle Excel**. Ouvrez-le : les listes déroulantes proposent les
   postes, départements, statuts.
2. Dans la feuille **Clients**, supprimez la ligne jaune et ajoutez un client (NCC/NIF, contact, téléphone, adresse).
   Déposez le fichier avec **Simulation** cochée : « Simulation réussie… rien n'a été enregistré ».
3. Décochez la case et redéposez : « Import terminé : 1 fiche créée ».
4. Déposez-le **une troisième fois** : « 1 déjà présent », aucun doublon.
5. Cassez volontairement une ligne (un délai de paiement « abc ») : « Rien n'a été importé » et l'erreur est listée
   avec sa feuille et son numéro de ligne.

## Ce qu'il faut retenir

- Une reprise de données doit être **rejouable** (aucun doublon) et **réversible** avant validation (simulation,
  « tout ou rien »).
- On importe **par les services** de chaque app : les règles métier et l'audit restent appliqués, il n'y a pas de
  « chemin parallèle » vers la base.
- Le modèle téléchargeable et le lecteur partagent **la même description des colonnes**.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 31 : app importation (import Excel des données, modèle téléchargeable, simulation)"
```
