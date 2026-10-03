# Chapitre 0 — Prérequis et vue d'ensemble

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
| **Node.js** | 20 ou plus (testé avec 24) | compile les styles de l'interface (chapitre 17) | `node --version` |
| **Git** | récent | historique, un commit par chapitre | `git --version` |
| **Un éditeur** | VS Code recommandé | créer les fichiers ; l'extension *Python* aide | — |
| **Un navigateur** | Chrome, Edge ou Firefox | voir l'application | — |
| **Un téléphone** | Android ou iPhone | la double authentification (application d'authentification) | — |

Vous n'avez **pas besoin** de PostgreSQL, Redis ni Docker pour ce tutoriel : en développement, la base est
un simple fichier SQLite. (La mise en production avec PostgreSQL, Redis et Docker est le sujet du chapitre 31
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

```text
erp-densource/
├── apps/
│   ├── accounting/
│   │   ├── management/
│   │   │   ├── commands/
│   │   │   │   ├── __init__.py  ← ch. 15
│   │   │   │   ├── comptabiliser_historique_depenses.py  ← ch. 15
│   │   │   │   ├── comptabiliser_historique_factures.py  ← ch. 15
│   │   │   │   └── comptabiliser_historique_reglements.py  ← ch. 15
│   │   │   └── __init__.py  ← ch. 15
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0002_plan_comptable_seed.py  ← ch. 15
│   │   │   ├── 0003_exercicecomptable.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templates/
│   │   │   └── accounting/
│   │   │       ├── _nav_rapports.html  ← ch. 27
│   │   │       ├── balance.html  ← ch. 27
│   │   │       ├── balance_print.html  ← ch. 27
│   │   │       ├── bilan.html  ← ch. 27
│   │   │       ├── bilan_print.html  ← ch. 27
│   │   │       ├── compte_form.html  ← ch. 27
│   │   │       ├── compte_modifier_form.html  ← ch. 27
│   │   │       ├── compte_resultat.html  ← ch. 27
│   │   │       ├── compte_resultat_print.html  ← ch. 27
│   │   │       ├── declaration_tva.html  ← ch. 27
│   │   │       ├── declaration_tva_print.html  ← ch. 27
│   │   │       ├── ecriture_manuelle_detail.html  ← ch. 27
│   │   │       ├── ecriture_manuelle_form.html  ← ch. 27
│   │   │       ├── ecriture_manuelle_list.html  ← ch. 27
│   │   │       ├── exercice_list.html  ← ch. 27
│   │   │       ├── grand_livre.html  ← ch. 27
│   │   │       ├── grand_livre_print.html  ← ch. 27
│   │   │       └── plan_comptable_list.html  ← ch. 27
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 15
│   │   │   ├── factories.py  ← ch. 15
│   │   │   ├── test_models.py  ← ch. 15
│   │   │   ├── test_receivers.py  ← ch. 15
│   │   │   ├── test_services.py  ← ch. 15
│   │   │   └── test_views.py  ← ch. 27
│   │   ├── README.md  ← ch. 15
│   │   ├── __init__.py  ← ch. 15
│   │   ├── admin.py  ← ch. 15
│   │   ├── apps.py  ← ch. 15
│   │   ├── constants.py  ← ch. 15
│   │   ├── exceptions.py  ← ch. 15
│   │   ├── forms.py  ← ch. 27
│   │   ├── models.py  ← ch. 15
│   │   ├── permissions.py  ← ch. 15
│   │   ├── receivers.py  ← ch. 15
│   │   ├── services.py  ← ch. 15
│   │   ├── urls.py  ← ch. 27
│   │   └── views.py  ← ch. 27
│   ├── accounts/
│   │   ├── management/
│   │   │   ├── commands/
│   │   │   │   ├── __init__.py  ← ch. 3
│   │   │   │   └── reinitialiser_mfa.py  ← ch. 3
│   │   │   └── __init__.py  ← ch. 3
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0002_mfa.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 3
│   │   │   ├── factories.py  ← ch. 3
│   │   │   ├── helpers_mfa.py  ← ch. 3
│   │   │   ├── test_mfa.py  ← ch. 30
│   │   │   ├── test_models.py  ← ch. 3
│   │   │   ├── test_password_reset.py  ← ch. 17
│   │   │   ├── test_permissions.py  ← ch. 3
│   │   │   ├── test_securite_connexion.py  ← ch. 30
│   │   │   └── test_web.py  ← ch. 26
│   │   ├── README.md  ← ch. 3
│   │   ├── __init__.py  ← ch. 3
│   │   ├── admin.py  ← ch. 3
│   │   ├── apps.py  ← ch. 3
│   │   ├── context_processors.py  ← ch. 17
│   │   ├── forms.py  ← ch. 17
│   │   ├── mfa.py  ← ch. 3
│   │   ├── middleware.py  ← ch. 3
│   │   ├── mixins.py  ← ch. 3
│   │   ├── models.py  ← ch. 3
│   │   ├── navigation.py  ← ch. 3
│   │   ├── permissions.py  ← ch. 3
│   │   ├── signals.py  ← ch. 3
│   │   ├── throttle.py  ← ch. 3
│   │   ├── urls.py  ← ch. 17
│   │   ├── views.py  ← ch. 17
│   │   └── views_mfa.py  ← ch. 17
│   ├── api/
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 30
│   │   │   ├── test_auth.py  ← ch. 30
│   │   │   ├── test_auth_mfa.py  ← ch. 30
│   │   │   └── test_v1.py  ← ch. 30
│   │   ├── v1/
│   │   │   ├── __init__.py  ← ch. 30
│   │   │   ├── filters.py  ← ch. 30
│   │   │   ├── serializers.py  ← ch. 30
│   │   │   └── views.py  ← ch. 30
│   │   ├── README.md  ← ch. 30
│   │   ├── __init__.py  ← ch. 30
│   │   ├── apps.py  ← ch. 30
│   │   ├── auth.py  ← ch. 30
│   │   ├── exceptions.py  ← ch. 30
│   │   ├── permissions.py  ← ch. 30
│   │   └── urls.py  ← ch. 30
│   ├── audit/
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templates/
│   │   │   └── audit/
│   │   │       └── journal_list.html  ← ch. 17
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 4
│   │   │   ├── test_models.py  ← ch. 4
│   │   │   ├── test_services.py  ← ch. 17
│   │   │   ├── test_signals.py  ← ch. 17
│   │   │   └── test_views.py  ← ch. 17
│   │   ├── README.md  ← ch. 4
│   │   ├── __init__.py  ← ch. 4
│   │   ├── admin.py  ← ch. 4
│   │   ├── apps.py  ← ch. 4
│   │   ├── forms.py  ← ch. 17
│   │   ├── models.py  ← ch. 4
│   │   ├── permissions.py  ← ch. 4
│   │   ├── registry.py  ← ch. 4
│   │   ├── services.py  ← ch. 4
│   │   ├── signals.py  ← ch. 4
│   │   ├── urls.py  ← ch. 17
│   │   └── views.py  ← ch. 17
│   ├── billing/
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0002_depenses_automatiques_parc_auto.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0003_depense_vehicule_alter_depense_categorie_and_more.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0004_proforma.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0005_depense_montant_tva_alter_depense_montant_and_more.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templates/
│   │   │   └── billing/
│   │   │       ├── depense_form.html  ← ch. 26
│   │   │       ├── depense_list.html  ← ch. 26
│   │   │       ├── facture_detail.html  ← ch. 26
│   │   │       ├── facture_form.html  ← ch. 26
│   │   │       ├── facture_list.html  ← ch. 26
│   │   │       ├── facture_print.html  ← ch. 26
│   │   │       ├── proforma_detail.html  ← ch. 26
│   │   │       ├── proforma_form.html  ← ch. 26
│   │   │       ├── proforma_list.html  ← ch. 26
│   │   │       ├── proforma_modifier.html  ← ch. 26
│   │   │       └── proforma_print.html  ← ch. 26
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 13
│   │   │   ├── helpers.py  ← ch. 13
│   │   │   ├── test_proforma.py  ← ch. 13
│   │   │   ├── test_proforma_views.py  ← ch. 26
│   │   │   ├── test_r6_creer_mission.py  ← ch. 13
│   │   │   ├── test_services.py  ← ch. 13
│   │   │   └── test_views.py  ← ch. 26
│   │   ├── README.md  ← ch. 13
│   │   ├── __init__.py  ← ch. 13
│   │   ├── apps.py  ← ch. 13
│   │   ├── exceptions.py  ← ch. 13
│   │   ├── forms.py  ← ch. 26
│   │   ├── models.py  ← ch. 13
│   │   ├── permissions.py  ← ch. 13
│   │   ├── services.py  ← ch. 13
│   │   ├── signals.py  ← ch. 13
│   │   ├── urls.py  ← ch. 26
│   │   └── views.py  ← ch. 26
│   ├── core/
│   │   ├── migrations/
│   │   │   ├── 0001_compteur_numero.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templatetags/
│   │   │   ├── __init__.py  ← ch. 17
│   │   │   ├── graphiques.py  ← ch. 17
│   │   │   └── ui.py  ← ch. 17
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 2
│   │   │   ├── test_csp.py  ← ch. 30
│   │   │   ├── test_echeance.py  ← ch. 2
│   │   │   ├── test_formats.py  ← ch. 2
│   │   │   ├── test_forms_date.py  ← ch. 29
│   │   │   ├── test_graphiques.py  ← ch. 2
│   │   │   ├── test_impression_listes.py  ← ch. 26
│   │   │   ├── test_models.py  ← ch. 2
│   │   │   ├── test_numerotation.py  ← ch. 2
│   │   │   ├── test_rapports.py  ← ch. 17
│   │   │   ├── test_search.py  ← ch. 25
│   │   │   └── test_sections.py  ← ch. 2
│   │   ├── README.md  ← ch. 2
│   │   ├── __init__.py  ← ch. 2
│   │   ├── admin.py  ← ch. 2
│   │   ├── apps.py  ← ch. 2
│   │   ├── constants.py  ← ch. 2
│   │   ├── formats.py  ← ch. 2
│   │   ├── forms.py  ← ch. 2
│   │   ├── graphiques.py  ← ch. 2
│   │   ├── middleware.py  ← ch. 2
│   │   ├── models.py  ← ch. 2
│   │   ├── rapports.py  ← ch. 2
│   │   ├── search.py  ← ch. 2
│   │   ├── sections.py  ← ch. 2
│   │   ├── services.py  ← ch. 2
│   │   └── views.py  ← ch. 17
│   ├── customers/
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0002_delai_paiement.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templates/
│   │   │   └── customers/
│   │   │       ├── client_detail.html  ← ch. 20
│   │   │       ├── client_form.html  ← ch. 20
│   │   │       └── client_list.html  ← ch. 20
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 7
│   │   │   ├── factories.py  ← ch. 7
│   │   │   ├── test_models.py  ← ch. 20
│   │   │   ├── test_services.py  ← ch. 20
│   │   │   └── test_views.py  ← ch. 22
│   │   ├── README.md  ← ch. 7
│   │   ├── __init__.py  ← ch. 7
│   │   ├── admin.py  ← ch. 7
│   │   ├── apps.py  ← ch. 7
│   │   ├── exceptions.py  ← ch. 7
│   │   ├── forms.py  ← ch. 20
│   │   ├── models.py  ← ch. 7
│   │   ├── permissions.py  ← ch. 7
│   │   ├── sections.py  ← ch. 7
│   │   ├── services.py  ← ch. 7
│   │   ├── urls.py  ← ch. 20
│   │   └── views.py  ← ch. 20
│   ├── dashboard/
│   │   ├── templates/
│   │   │   └── dashboard/
│   │   │       ├── index.html  ← ch. 28
│   │   │       └── index_print.html  ← ch. 28
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 28
│   │   │   ├── test_dashboard.py  ← ch. 28
│   │   │   ├── test_impression.py  ← ch. 28
│   │   │   ├── test_lectures_metier.py  ← ch. 28
│   │   │   └── test_series_mensuelles.py  ← ch. 28
│   │   ├── README.md  ← ch. 28
│   │   ├── __init__.py  ← ch. 28
│   │   ├── apps.py  ← ch. 28
│   │   ├── services.py  ← ch. 28
│   │   └── views.py  ← ch. 28
│   ├── drivers/
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0002_copilote.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templates/
│   │   │   └── drivers/
│   │   │       ├── chauffeur_detail.html  ← ch. 19
│   │   │       ├── chauffeur_form.html  ← ch. 19
│   │   │       └── chauffeur_list.html  ← ch. 19
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 6
│   │   │   ├── factories.py  ← ch. 6
│   │   │   ├── test_copilote.py  ← ch. 6
│   │   │   ├── test_fiche.py  ← ch. 6
│   │   │   ├── test_models.py  ← ch. 6
│   │   │   ├── test_services.py  ← ch. 6
│   │   │   └── test_views.py  ← ch. 22
│   │   ├── README.md  ← ch. 6
│   │   ├── __init__.py  ← ch. 6
│   │   ├── admin.py  ← ch. 6
│   │   ├── apps.py  ← ch. 6
│   │   ├── exceptions.py  ← ch. 6
│   │   ├── forms.py  ← ch. 19
│   │   ├── models.py  ← ch. 6
│   │   ├── permissions.py  ← ch. 6
│   │   ├── services.py  ← ch. 6
│   │   ├── signals.py  ← ch. 6
│   │   ├── urls.py  ← ch. 19
│   │   └── views.py  ← ch. 19
│   ├── finance/
│   │   ├── management/
│   │   │   ├── commands/
│   │   │   │   ├── __init__.py  ← ch. 14
│   │   │   │   └── comptabiliser_historique_parc_auto.py  ← ch. 14
│   │   │   └── __init__.py  ← ch. 14
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0002_demandedepense_enveloppedepense_ordredecaissement_and_more.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0003_mouvementmanuel_nature.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templates/
│   │   │   └── finance/
│   │   │       ├── demande_detail.html  ← ch. 26
│   │   │       ├── demande_form.html  ← ch. 26
│   │   │       ├── demande_list.html  ← ch. 26
│   │   │       ├── enveloppe_list.html  ← ch. 26
│   │   │       ├── tresorerie.html  ← ch. 26
│   │   │       ├── tresorerie_print.html  ← ch. 26
│   │   │       └── versement_confirmer.html  ← ch. 26
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 14
│   │   │   ├── test_demandes.py  ← ch. 14
│   │   │   ├── test_demandes_views.py  ← ch. 26
│   │   │   ├── test_depenses_parc_auto.py  ← ch. 26
│   │   │   ├── test_frais_mission_receivers.py  ← ch. 14
│   │   │   ├── test_impression.py  ← ch. 26
│   │   │   ├── test_services.py  ← ch. 14
│   │   │   ├── test_versements.py  ← ch. 26
│   │   │   └── test_views.py  ← ch. 26
│   │   ├── README.md  ← ch. 14
│   │   ├── __init__.py  ← ch. 14
│   │   ├── apps.py  ← ch. 14
│   │   ├── demandes.py  ← ch. 14
│   │   ├── forms.py  ← ch. 26
│   │   ├── models.py  ← ch. 14
│   │   ├── permissions.py  ← ch. 14
│   │   ├── receivers.py  ← ch. 14
│   │   ├── services.py  ← ch. 14
│   │   ├── signals.py  ← ch. 14
│   │   ├── urls.py  ← ch. 26
│   │   └── views.py  ← ch. 26
│   ├── fleet/
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templates/
│   │   │   └── fleet/
│   │   │       ├── vehicule_detail.html  ← ch. 21
│   │   │       ├── vehicule_form.html  ← ch. 21
│   │   │       └── vehicule_list.html  ← ch. 21
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 8
│   │   │   ├── factories.py  ← ch. 8
│   │   │   ├── test_fiche.py  ← ch. 8
│   │   │   ├── test_models.py  ← ch. 8
│   │   │   ├── test_services.py  ← ch. 8
│   │   │   └── test_views.py  ← ch. 21
│   │   ├── README.md  ← ch. 8
│   │   ├── __init__.py  ← ch. 8
│   │   ├── admin.py  ← ch. 8
│   │   ├── apps.py  ← ch. 8
│   │   ├── exceptions.py  ← ch. 8
│   │   ├── forms.py  ← ch. 21
│   │   ├── models.py  ← ch. 8
│   │   ├── permissions.py  ← ch. 8
│   │   ├── sections.py  ← ch. 8
│   │   ├── services.py  ← ch. 8
│   │   ├── urls.py  ← ch. 21
│   │   └── views.py  ← ch. 21
│   ├── fuel/
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templates/
│   │   │   └── fuel/
│   │   │       ├── analyse.html  ← ch. 25
│   │   │       ├── plein_form.html  ← ch. 25
│   │   │       └── plein_list.html  ← ch. 25
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 12
│   │   │   ├── factories.py  ← ch. 12
│   │   │   ├── test_lecture.py  ← ch. 12
│   │   │   ├── test_models.py  ← ch. 12
│   │   │   ├── test_services.py  ← ch. 12
│   │   │   └── test_views.py  ← ch. 25
│   │   ├── README.md  ← ch. 12
│   │   ├── __init__.py  ← ch. 12
│   │   ├── admin.py  ← ch. 12
│   │   ├── apps.py  ← ch. 12
│   │   ├── exceptions.py  ← ch. 12
│   │   ├── forms.py  ← ch. 25
│   │   ├── models.py  ← ch. 12
│   │   ├── permissions.py  ← ch. 12
│   │   ├── services.py  ← ch. 12
│   │   ├── signals.py  ← ch. 12
│   │   ├── urls.py  ← ch. 25
│   │   └── views.py  ← ch. 25
│   ├── garage/
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0002_incidents_checklists.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templates/
│   │   │   └── garage/
│   │   │       ├── _maintenance_vehicule.html  ← ch. 23
│   │   │       ├── checklist_list.html  ← ch. 23
│   │   │       ├── incident_detail.html  ← ch. 23
│   │   │       ├── incident_list.html  ← ch. 23
│   │   │       ├── or_detail.html  ← ch. 23
│   │   │       ├── or_form.html  ← ch. 23
│   │   │       └── or_list.html  ← ch. 23
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 10
│   │   │   ├── factories.py  ← ch. 10
│   │   │   ├── test_models.py  ← ch. 10
│   │   │   ├── test_services.py  ← ch. 10
│   │   │   ├── test_statut_vehicule.py  ← ch. 10
│   │   │   ├── test_terrain.py  ← ch. 10
│   │   │   ├── test_views.py  ← ch. 23
│   │   │   └── test_views_terrain.py  ← ch. 23
│   │   ├── README.md  ← ch. 10
│   │   ├── __init__.py  ← ch. 10
│   │   ├── admin.py  ← ch. 10
│   │   ├── apps.py  ← ch. 10
│   │   ├── exceptions.py  ← ch. 10
│   │   ├── forms.py  ← ch. 23
│   │   ├── forms_terrain.py  ← ch. 23
│   │   ├── models.py  ← ch. 10
│   │   ├── permissions.py  ← ch. 10
│   │   ├── sections.py  ← ch. 10
│   │   ├── services.py  ← ch. 10
│   │   ├── signals.py  ← ch. 10
│   │   ├── terrain.py  ← ch. 10
│   │   ├── urls.py  ← ch. 23
│   │   ├── views.py  ← ch. 23
│   │   └── views_terrain.py  ← ch. 23
│   ├── hr/
│   │   ├── management/
│   │   │   ├── commands/
│   │   │   │   ├── __init__.py  ← ch. 5
│   │   │   │   ├── creer_comptes_demo.py  ← ch. 5
│   │   │   │   └── initialiser_jours_feries.py  ← ch. 5
│   │   │   └── __init__.py  ← ch. 5
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0002_personnel_contrat_solde_chef_utilisateur.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0003_conges.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0004_hierarchie_superieur.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0005_jours_feries.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0006_droits_conges_annuels.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0007_libelle_niveau_superieur.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0008_report_conge.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0009_alter_personnel_departement.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0010_alter_personnel_departement.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templates/
│   │   │   └── hr/
│   │   │       ├── conge_detail.html  ← ch. 18
│   │   │       ├── conge_form.html  ← ch. 18
│   │   │       ├── conge_list.html  ← ch. 18
│   │   │       ├── personnel_detail.html  ← ch. 18
│   │   │       ├── personnel_form.html  ← ch. 18
│   │   │       ├── personnel_import.html  ← ch. 18
│   │   │       ├── personnel_list.html  ← ch. 18
│   │   │       └── report_form.html  ← ch. 18
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 5
│   │   │   ├── factories.py  ← ch. 5
│   │   │   ├── test_audit.py  ← ch. 5
│   │   │   ├── test_comptes_demo.py  ← ch. 6
│   │   │   ├── test_conges.py  ← ch. 6
│   │   │   ├── test_direction_remplace.py  ← ch. 18
│   │   │   ├── test_droits_conges.py  ← ch. 6
│   │   │   ├── test_import_personnel.py  ← ch. 19
│   │   │   ├── test_jours_feries.py  ← ch. 5
│   │   │   ├── test_models.py  ← ch. 5
│   │   │   ├── test_recrutement.py  ← ch. 6
│   │   │   ├── test_report_conge.py  ← ch. 18
│   │   │   ├── test_services_ecrans.py  ← ch. 5
│   │   │   ├── test_views_conges.py  ← ch. 18
│   │   │   └── test_views_personnel.py  ← ch. 19
│   │   ├── README.md  ← ch. 5
│   │   ├── __init__.py  ← ch. 5
│   │   ├── admin.py  ← ch. 5
│   │   ├── apps.py  ← ch. 5
│   │   ├── documents.py  ← ch. 5
│   │   ├── exceptions.py  ← ch. 5
│   │   ├── forms.py  ← ch. 18
│   │   ├── models.py  ← ch. 5
│   │   ├── permissions.py  ← ch. 5
│   │   ├── sections.py  ← ch. 5
│   │   ├── services.py  ← ch. 5
│   │   ├── signals.py  ← ch. 5
│   │   ├── urls.py  ← ch. 18
│   │   └── views.py  ← ch. 18
│   ├── inventory/
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templates/
│   │   │   └── inventory/
│   │   │       ├── _pieces_or.html  ← ch. 24
│   │   │       ├── article_detail.html  ← ch. 24
│   │   │       ├── article_form.html  ← ch. 24
│   │   │       ├── article_list.html  ← ch. 24
│   │   │       └── mouvement_list.html  ← ch. 24
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 11
│   │   │   ├── factories.py  ← ch. 11
│   │   │   ├── test_fiche.py  ← ch. 11
│   │   │   ├── test_models.py  ← ch. 11
│   │   │   ├── test_services.py  ← ch. 11
│   │   │   ├── test_stock_views.py  ← ch. 24
│   │   │   └── test_views.py  ← ch. 24
│   │   ├── README.md  ← ch. 11
│   │   ├── __init__.py  ← ch. 11
│   │   ├── admin.py  ← ch. 11
│   │   ├── apps.py  ← ch. 11
│   │   ├── exceptions.py  ← ch. 11
│   │   ├── forms.py  ← ch. 11
│   │   ├── models.py  ← ch. 11
│   │   ├── permissions.py  ← ch. 11
│   │   ├── sections.py  ← ch. 11
│   │   ├── services.py  ← ch. 11
│   │   ├── signals.py  ← ch. 11
│   │   ├── urls.py  ← ch. 24
│   │   └── views.py  ← ch. 24
│   ├── missions/
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0002_fraismission.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0002_mission_proforma.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0003_merge_0002_fraismission_0002_mission_proforma.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0004_mission_copilote.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templates/
│   │   │   └── missions/
│   │   │       ├── _alerte_conge.html  ← ch. 22
│   │   │       ├── _missions_client.html  ← ch. 22
│   │   │       ├── frais_detail.html  ← ch. 22
│   │   │       ├── frais_liste.html  ← ch. 22
│   │   │       ├── frais_print.html  ← ch. 22
│   │   │       ├── mission_detail.html  ← ch. 22
│   │   │       ├── mission_form.html  ← ch. 22
│   │   │       ├── mission_list.html  ← ch. 22
│   │   │       └── mission_modifier.html  ← ch. 22
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 9
│   │   │   ├── factories.py  ← ch. 9
│   │   │   ├── test_alerte_conge.py  ← ch. 22
│   │   │   ├── test_documents.py  ← ch. 22
│   │   │   ├── test_frais_mission.py  ← ch. 9
│   │   │   ├── test_frais_mission_views.py  ← ch. 22
│   │   │   ├── test_models.py  ← ch. 9
│   │   │   ├── test_modification.py  ← ch. 22
│   │   │   ├── test_permissions.py  ← ch. 9
│   │   │   ├── test_qr.py  ← ch. 22
│   │   │   ├── test_services.py  ← ch. 9
│   │   │   ├── test_temps_reel.py  ← ch. 9
│   │   │   └── test_views.py  ← ch. 22
│   │   ├── README.md  ← ch. 9
│   │   ├── __init__.py  ← ch. 9
│   │   ├── admin.py  ← ch. 9
│   │   ├── apps.py  ← ch. 9
│   │   ├── consumers.py  ← ch. 9
│   │   ├── documents.py  ← ch. 9
│   │   ├── exceptions.py  ← ch. 9
│   │   ├── forms.py  ← ch. 22
│   │   ├── models.py  ← ch. 9
│   │   ├── permissions.py  ← ch. 9
│   │   ├── routing.py  ← ch. 9
│   │   ├── sections.py  ← ch. 9
│   │   ├── services.py  ← ch. 9
│   │   ├── signals.py  ← ch. 9
│   │   ├── temps_reel.py  ← ch. 9
│   │   ├── terrain.py  ← ch. 9
│   │   ├── urls.py  ← ch. 22
│   │   └── views.py  ← ch. 22
│   ├── mobile_api/
│   │   ├── templates/
│   │   │   └── mobile/
│   │   │       ├── _carte_mission.html  ← ch. 29
│   │   │       ├── _scanner.html  ← ch. 29
│   │   │       ├── accueil.html  ← ch. 29
│   │   │       ├── base.html  ← ch. 29
│   │   │       ├── checklist.html  ← ch. 29
│   │   │       ├── hors_ligne.html  ← ch. 29
│   │   │       ├── imprevu.html  ← ch. 29
│   │   │       ├── incident.html  ← ch. 29
│   │   │       ├── mission.html  ← ch. 29
│   │   │       ├── missions.html  ← ch. 29
│   │   │       ├── plein.html  ← ch. 29
│   │   │       └── sw.js  ← ch. 29
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 29
│   │   │   ├── helpers.py  ← ch. 29
│   │   │   ├── test_api.py  ← ch. 30
│   │   │   ├── test_frais_mission.py  ← ch. 30
│   │   │   ├── test_services.py  ← ch. 29
│   │   │   └── test_web.py  ← ch. 29
│   │   ├── README.md  ← ch. 29
│   │   ├── __init__.py  ← ch. 29
│   │   ├── apps.py  ← ch. 29
│   │   ├── exceptions.py  ← ch. 29
│   │   ├── forms.py  ← ch. 29
│   │   ├── permissions.py  ← ch. 29
│   │   ├── serializers.py  ← ch. 29
│   │   ├── services.py  ← ch. 29
│   │   ├── urls.py  ← ch. 29
│   │   ├── urls_web.py  ← ch. 29
│   │   ├── views.py  ← ch. 29
│   │   └── views_web.py  ← ch. 29
│   ├── notifications/
│   │   ├── management/
│   │   │   ├── commands/
│   │   │   │   ├── __init__.py  ← ch. 16
│   │   │   │   └── taches_quotidiennes.py  ← ch. 16
│   │   │   └── __init__.py  ← ch. 16
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0002_categorie_facture.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0003_categorie_incident.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0004_action_du_bouton.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0005_alter_notification_categorie.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templates/
│   │   │   └── notifications/
│   │   │       └── liste.html  ← ch. 17
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 16
│   │   │   ├── test_facturation.py  ← ch. 26
│   │   │   ├── test_receivers.py  ← ch. 25
│   │   │   ├── test_receivers_demandes.py  ← ch. 26
│   │   │   ├── test_receivers_frais_mission.py  ← ch. 22
│   │   │   ├── test_receivers_proforma.py  ← ch. 26
│   │   │   ├── test_services.py  ← ch. 24
│   │   │   ├── test_taches.py  ← ch. 21
│   │   │   ├── test_tasks.py  ← ch. 16
│   │   │   ├── test_terrain.py  ← ch. 28
│   │   │   └── test_views.py  ← ch. 24
│   │   ├── README.md  ← ch. 16
│   │   ├── __init__.py  ← ch. 16
│   │   ├── admin.py  ← ch. 16
│   │   ├── apps.py  ← ch. 16
│   │   ├── context_processors.py  ← ch. 17
│   │   ├── models.py  ← ch. 16
│   │   ├── receivers.py  ← ch. 16
│   │   ├── services.py  ← ch. 16
│   │   ├── taches.py  ← ch. 16
│   │   ├── tasks.py  ← ch. 16
│   │   ├── urls.py  ← ch. 17
│   │   └── views.py  ← ch. 17
│   └── __init__.py  ← ch. 1
├── config/
│   ├── settings/
│   │   ├── __init__.py  ← ch. 1
│   │   ├── base.py  ← ch. 1
│   │   ├── dev.py  ← ch. 1
│   │   ├── prod.py  ← ch. 1
│   │   └── test.py  ← ch. 1
│   ├── __init__.py  ← ch. 1
│   ├── asgi.py  ← ch. 1
│   ├── celery.py  ← ch. 1
│   ├── urls.py  ← ch. 1
│   └── wsgi.py  ← ch. 1
├── frontend/
│   ├── .gitignore  ← ch. 17
│   ├── README.md  ← ch. 17
│   ├── input.css  ← ch. 17
│   ├── package-lock.json  ← (généré par `npm install`)
│   ├── package.json  ← ch. 17
│   ├── tailwind.config.js  ← ch. 17
│   └── vendor.js  ← ch. 17
├── nginx/
│   └── nginx.conf  ← (mise en production)
├── ops/
│   ├── entrypoint.sh  ← (mise en production)
│   ├── gunicorn.conf.py  ← (mise en production)
│   ├── restauration.sh  ← (mise en production)
│   └── sauvegarde.sh  ← (mise en production)
├── requirements/
│   ├── base.txt  ← ch. 1
│   ├── dev.txt  ← ch. 1
│   └── prod.txt  ← ch. 1
├── static/
│   ├── css/
│   │   └── tailwind.css  ← (généré par `npm run build`)
│   ├── img/
│   │   ├── favicon.png  ← (identité visuelle de DEN Source Group : à copier depuis le dépôt)
│   │   ├── icon-192.png  ← (identité visuelle de DEN Source Group : à copier depuis le dépôt)
│   │   ├── icon-512.png  ← (identité visuelle de DEN Source Group : à copier depuis le dépôt)
│   │   └── logo-emblem.jpg  ← (identité visuelle de DEN Source Group : à copier depuis le dépôt)
│   ├── js/
│   │   ├── app.js  ← ch. 17
│   │   ├── scanner.js  ← ch. 29
│   │   ├── suivi-missions.js  ← ch. 22
│   │   └── sw-register.js  ← ch. 29
│   └── vendor/
│       ├── alpine/
│       │   └── alpine.min.js  ← (généré par `npm run build`)
│       └── fontawesome/
│           ├── css/
│           │   └── all.min.css  ← (généré par `npm run build`)
│           ├── webfonts/
│           │   ├── fa-regular-400.woff2  ← (généré par `npm run build`)
│           │   └── fa-solid-900.woff2  ← (généré par `npm run build`)
│           └── LICENSE.txt  ← (généré par `npm run build`)
├── templates/
│   ├── accounts/
│   │   ├── mfa_activer.html  ← ch. 17
│   │   ├── mfa_codes.html  ← ch. 17
│   │   ├── mfa_codes_affiches.html  ← ch. 17
│   │   └── mfa_verifier.html  ← ch. 17
│   ├── components/
│   │   ├── _assets.html  ← ch. 17
│   │   ├── _champ.html  ← ch. 17
│   │   ├── _graphique_barres.html  ← ch. 17
│   │   ├── _graphique_colonnes.html  ← ch. 17
│   │   ├── _messages.html  ← ch. 17
│   │   ├── _pagination.html  ← ch. 17
│   │   └── _suivi_direct.html  ← ch. 17
│   ├── rapports/
│   │   ├── _entete_impression.html  ← ch. 17
│   │   ├── _pied_impression.html  ← ch. 17
│   │   ├── _style_impression.html  ← ch. 17
│   │   └── liste_impression.html  ← ch. 17
│   ├── registration/
│   │   ├── login.html  ← ch. 17
│   │   ├── password_reset_complete.html  ← ch. 17
│   │   ├── password_reset_confirm.html  ← ch. 17
│   │   ├── password_reset_done.html  ← ch. 17
│   │   ├── password_reset_email.txt  ← ch. 17
│   │   ├── password_reset_form.html  ← ch. 17
│   │   └── password_reset_subject.txt  ← ch. 17
│   ├── 403.html  ← ch. 17
│   ├── 404.html  ← ch. 17
│   └── base.html  ← ch. 17
├── .dockerignore  ← (mise en production)
├── .env.example  ← ch. 1
├── .gitignore  ← ch. 1
├── CAHIER DES CHARGES FONCTIONNEL ET TECHNIQUE.docx  ← (documents de présentation, sans rapport avec le fonctionnement)
├── Dockerfile  ← (mise en production)
├── GUIDE-DEPLOIEMENT.md  ← (documents de référence à lire)
├── GUIDE-INTERFACE.md  ← (documents de référence à lire)
├── GUIDE-PARCOURS.md  ← (documents de référence à lire)
├── Presentation-ERP-DEN-Source.docx  ← (documents de présentation, sans rapport avec le fonctionnement)
├── Presentation-ERP-DEN-Source.pptx  ← (documents de présentation, sans rapport avec le fonctionnement)
├── README.md  ← ch. 31
├── architecture.md  ← (documents de référence à lire)
├── audit-checklist.md  ← (documents de référence à lire)
├── avenant-comptabilite-autonomie.md  ← (documents de référence à lire)
├── avenant-comptabilite-syscohada.md  ← (documents de référence à lire)
├── avenant-separation-des-taches.md  ← (documents de référence à lire)
├── cahier-des-charges.md  ← (documents de référence à lire)
├── conventions.md  ← (documents de référence à lire)
├── docker-compose.yml  ← (mise en production)
├── glossaire-metier.md  ← (documents de référence à lire)
├── manage.py  ← ch. 1
└── pytest.ini  ← ch. 1
```

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

---

[Sommaire](README.md) · [Chapitre 1 →](01-squelette.md)
