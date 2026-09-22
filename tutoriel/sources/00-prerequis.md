## Ce que vous allez construire

Un **ERP** (progiciel de gestion) pour une entreprise de transport en Côte d'Ivoire : **DEN Source Group**.
Il remplace des fichiers Excel et des appels téléphoniques par une seule application où chaque métier voit
ce qui le concerne.

| Domaine | Ce que l'application sait faire |
|---|---|
| **Missions** | créer, planifier, affecter un camion et un chauffeur, suivre le colis, confirmer la livraison par code QR |
| **Flotte et garage** | état des camions calculé automatiquement, documents réglementaires, ordres de réparation, incidents |
| **Chauffeurs et personnel** | fiches, permis, visites médicales, congés validés en trois niveaux |
| **Stock et carburant** | pièces détachées valorisées, consommation aux 100 km, alertes de surconsommation |
| **Clients et finances** | portefeuille, factures (TVA, règlements), dépenses, trésorerie |
| **Pilotage** | tableau de bord par rôle, notifications |
| **Terrain** | espace mobile du chauffeur (installable sur téléphone), API REST |
| **Sécurité** | 7 rôles, double authentification, journal d'audit inaltérable |

## Ce que vous devez savoir avant

- **Python** : fonctions, classes, modules, exceptions, décorateurs, `import`. Rien de plus.
- **Django n'est pas nécessaire** : chaque notion est expliquée au moment où on en a besoin.
- Savoir **ouvrir un terminal** et **créer un fichier** avec un éditeur de texte.
- Une idée de ce qu'est une base de données et du HTML. Le SQL n'est pas nécessaire (Django l'écrit).

## Prérequis techniques

| Outil | Version | Pourquoi | Vérifier |
|---|---|---|---|
| **Python** | 3.12 ou plus (le projet a été construit avec 3.14) | le langage | `python --version` |
| **pip** | fourni avec Python | installe les bibliothèques | `pip --version` |
| **Node.js** | 20 ou plus (testé avec 24) | compile les styles de l'interface (chapitre 16) | `node --version` |
| **Git** | récent | historique, un commit par chapitre | `git --version` |
| **Un éditeur** | VS Code recommandé | créer les fichiers ; l'extension *Python* aide | — |
| **Un navigateur** | Chrome, Edge ou Firefox | voir l'application | — |
| **Un téléphone** | Android ou iPhone | la double authentification (application d'authentification) | — |

Vous n'avez **pas besoin** de PostgreSQL, Redis ni Docker pour ce tutoriel : en développement, la base est
un simple fichier SQLite. (La mise en production avec PostgreSQL, Redis et Docker est le sujet du chapitre 29
« Aller plus loin ».)

Espace disque : environ 400 Mo (dont 300 Mo pour `node_modules`). Durée : comptez **20 à 30 heures** en
recopiant tout, ou quelques heures si vous ne faites que lire et exécuter les vérifications.

> **Windows, macOS ou Linux ?** Les commandes de ce tutoriel fonctionnent partout **une fois
> l'environnement virtuel activé** (voir plus bas). Les seules différences sont signalées dans des encadrés.
> Sous Windows, utilisez **Git Bash** (fourni avec Git) ou **PowerShell**.

## La méthode de travail

Pour **chaque chapitre**, le même rythme :

1. **Lire** l'introduction (ce qu'on construit et pourquoi).
2. **Créer les fichiers** : le titre `#### chemin/du/fichier` donne l'emplacement ; copiez le contenu tel quel.
   Les dossiers manquants se créent avec `mkdir -p`.
3. **Lancer les commandes** du chapitre (migrations, tests, serveur).
4. **Comparer** avec le **résultat attendu**. S'il diffère, cherchez l'erreur *avant* de continuer :
   une faute de frappe non détectée se répercute sur tous les chapitres suivants.
5. **Valider avec Git** (`git add -A && git commit`) : si vous vous perdez plus tard, vous pouvez revenir.

> **Si un test échoue** : lisez le message, il indique le fichier et la ligne. La cause est presque toujours
> une faute de copie (une virgule, une indentation). Comparez avec le tutoriel, caractère par caractère.
> Un fichier se compare facilement avec l'outil de votre éditeur (*Comparer avec le presse-papiers*).

## L'idée directrice : des couches qui ne se mélangent pas

Toute l'application respecte le même plan, que vous verrez apparaître dans chaque chapitre :

```text
Navigateur ─► URL ─► Vue ─► Formulaire ─► Service ─► Modèle (base de données)
                      │                     │
                      └──── Gabarit HTML ◄──┘
```

| Couche | Fichier | Seule responsabilité |
|---|---|---|
| **Modèle** | `models.py` | décrire les tables et leurs contraintes |
| **Service** | `services.py` | **toutes les règles métier** (ce qui est permis, calculé, interdit) |
| **Formulaire** | `forms.py` | lire et valider ce que l'utilisateur saisit |
| **Vue** | `views.py` | vérifier le rôle, appeler un service, choisir la page |
| **Gabarit** | `templates/…html` | afficher |
| **URL** | `urls.py` | relier une adresse à une vue |

Deux règles en découlent : **jamais de règle métier dans une vue** (l'interface web, l'API et l'espace
mobile appellent les mêmes services, donc les mêmes règles), et **une application ne dépend que de celles qui
la précèdent** (d'où l'ordre des chapitres).

## Les 17 applications, dans l'ordre où on les construit

```text
core ─► accounts ─► audit ─► hr ─► drivers ─► customers ─► fleet ─► missions ─► garage
   ─► inventory ─► fuel ─► billing ─► finance ─► notifications ─► dashboard ─► mobile_api ─► api
```

Une **application Django** (« app ») est un dossier Python qui regroupe tout un domaine : ses tables, ses
règles, ses écrans, ses tests. Ici, chaque domaine du tableau du début a la sienne.

## L'arborescence finale

Voici tous les fichiers du projet terminé. Chaque fichier porte, à droite, le **numéro du chapitre** où
vous le créez. Les fichiers marqués entre parenthèses sont **générés ou copiés**, pas recopiés à la main.

{{ARBORESCENCE}}

## Étape A — Préparer le dossier du projet

Choisissez un dossier de travail (ici `erp-densource`) et initialisez Git :

```bash
mkdir erp-densource
cd erp-densource
git init
git branch -M main
```

**Résultat attendu :** `Initialized empty Git repository in …/erp-densource/.git/`.

## Étape B — Créer l'environnement virtuel

Un **environnement virtuel** est un dossier `.venv` qui contient *les bibliothèques de ce projet
seulement* : il évite de polluer votre Python global et de mélanger les versions.

```bash
python -m venv .venv
```

Puis **activez-le** (à refaire à chaque nouveau terminal) :

```bash
# Git Bash (Windows)
source .venv/Scripts/activate

# PowerShell (Windows)
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

Le début de l'invite de commande devient `(.venv)`. Vérifiez :

```bash
python --version
python -c "import sys; print(sys.prefix)"
```

**Résultat attendu :** la seconde commande affiche un chemin qui se termine par `.venv`.

> **PowerShell refuse d'exécuter le script ?** Lancez une fois
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, puis réessayez.

À partir de maintenant, **toutes les commandes `python` et `pip` du tutoriel supposent l'environnement activé**.

## Étape C — Lire les documents de référence (facultatif mais conseillé)

Le projet a été écrit à partir de cinq documents, décrits dans la colonne de droite du tableau
« Ce qui n'est pas recopié » du [sommaire](README.md). Les plus utiles :

| Document | Contenu |
|---|---|
| `cahier-des-charges.md` | le besoin du client : rôles, règles, écrans, critères de recette |
| `glossaire-metier.md` | le vocabulaire (OR, PUMP, N1/N2, …) |
| `architecture.md` | le découpage en apps, le cycle de vie d'une mission, les décisions d'architecture |
| `conventions.md` | les règles d'écriture du code |

Les commentaires du code citent ces documents (par exemple `cahier-des-charges.md:96-100`) : c'est ainsi
qu'on sait *pourquoi* une règle existe. Vous pouvez suivre le tutoriel sans eux.

## Étape D — Valider ce chapitre

Il n'y a encore aucun fichier. Passez au [chapitre 1](01-squelette.md) : on crée le squelette du projet.
