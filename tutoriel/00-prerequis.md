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
| **Node.js** | 20 ou plus (testé avec 24) | compile les styles de l'interface (chapitre 18) | `node --version` |
| **Git** | récent | historique, un commit par chapitre | `git --version` |
| **Un éditeur** | VS Code recommandé | créer les fichiers ; l'extension *Python* aide | — |
| **Un navigateur** | Chrome, Edge ou Firefox | voir l'application | — |
| **Un téléphone** | Android ou iPhone | la double authentification (application d'authentification) | — |

Vous n'avez **pas besoin** de PostgreSQL, Redis ni Docker pour ce tutoriel : en développement, la base est
un simple fichier SQLite. (La mise en production avec PostgreSQL, Redis et Docker est le sujet du chapitre 34
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
│   │   │   │   ├── __init__.py  ← ch. 16
│   │   │   │   ├── comptabiliser_historique_depenses.py  ← ch. 16
│   │   │   │   ├── comptabiliser_historique_factures.py  ← ch. 16
│   │   │   │   ├── comptabiliser_historique_reglements.py  ← ch. 16
│   │   │   │   ├── contre_passer_historique_annulations.py  ← ch. 16
│   │   │   │   ├── corriger_reclassements_inverses.py  ← ch. 16
│   │   │   │   └── ecrire_clotures_historiques.py  ← ch. 16
│   │   │   └── __init__.py  ← ch. 16
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0002_plan_comptable_seed.py  ← ch. 16
│   │   │   ├── 0003_exercicecomptable.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0004_piece_reference_100.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0005_verrou_ecritures_validees.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templates/
│   │   │   └── accounting/
│   │   │       ├── _nav_rapports.html  ← ch. 28
│   │   │       ├── balance.html  ← ch. 28
│   │   │       ├── balance_print.html  ← ch. 28
│   │   │       ├── bilan.html  ← ch. 28
│   │   │       ├── bilan_print.html  ← ch. 28
│   │   │       ├── compte_form.html  ← ch. 28
│   │   │       ├── compte_modifier_form.html  ← ch. 28
│   │   │       ├── compte_resultat.html  ← ch. 28
│   │   │       ├── compte_resultat_print.html  ← ch. 28
│   │   │       ├── declaration_tva.html  ← ch. 28
│   │   │       ├── declaration_tva_print.html  ← ch. 28
│   │   │       ├── ecriture_manuelle_detail.html  ← ch. 28
│   │   │       ├── ecriture_manuelle_form.html  ← ch. 28
│   │   │       ├── ecriture_manuelle_list.html  ← ch. 28
│   │   │       ├── exercice_list.html  ← ch. 28
│   │   │       ├── grand_livre.html  ← ch. 28
│   │   │       ├── grand_livre_print.html  ← ch. 28
│   │   │       └── plan_comptable_list.html  ← ch. 28
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 16
│   │   │   ├── factories.py  ← ch. 16
│   │   │   ├── test_admin_lecture_seule.py  ← ch. 28
│   │   │   ├── test_cloture_resultat.py  ← ch. 16
│   │   │   ├── test_comptes_proteges.py  ← ch. 28
│   │   │   ├── test_contre_passation.py  ← ch. 16
│   │   │   ├── test_contre_passation_manuelle.py  ← ch. 28
│   │   │   ├── test_exercice_cloture_erreurs.py  ← ch. 32
│   │   │   ├── test_longueur_piece.py  ← ch. 16
│   │   │   ├── test_models.py  ← ch. 16
│   │   │   ├── test_plan_comptable_coherence.py  ← ch. 28
│   │   │   ├── test_receivers.py  ← ch. 16
│   │   │   ├── test_reprise_reclassements.py  ← ch. 16
│   │   │   ├── test_saisie_manuelle_controles.py  ← ch. 16
│   │   │   ├── test_services.py  ← ch. 16
│   │   │   ├── test_soldes_ouverture.py  ← ch. 28
│   │   │   ├── test_verrou_ecritures.py  ← ch. 16
│   │   │   └── test_views.py  ← ch. 28
│   │   ├── README.md  ← ch. 16
│   │   ├── __init__.py  ← ch. 16
│   │   ├── admin.py  ← ch. 16
│   │   ├── apps.py  ← ch. 16
│   │   ├── constants.py  ← ch. 16
│   │   ├── exceptions.py  ← ch. 16
│   │   ├── forms.py  ← ch. 28
│   │   ├── models.py  ← ch. 16
│   │   ├── permissions.py  ← ch. 16
│   │   ├── receivers.py  ← ch. 16
│   │   ├── services.py  ← ch. 16
│   │   ├── urls.py  ← ch. 28
│   │   └── views.py  ← ch. 28
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
│   │   │   ├── test_changer_mot_de_passe.py  ← ch. 18
│   │   │   ├── test_force_brute_api_reinitialisation.py  ← ch. 32
│   │   │   ├── test_mfa.py  ← ch. 32
│   │   │   ├── test_models.py  ← ch. 3
│   │   │   ├── test_password_reset.py  ← ch. 18
│   │   │   ├── test_permissions.py  ← ch. 3
│   │   │   ├── test_purge.py  ← ch. 17
│   │   │   ├── test_role_avant_objet.py  ← ch. 18
│   │   │   ├── test_securite_connexion.py  ← ch. 32
│   │   │   ├── test_utilisateurs_ecran.py  ← ch. 18
│   │   │   └── test_web.py  ← ch. 27
│   │   ├── README.md  ← ch. 3
│   │   ├── __init__.py  ← ch. 3
│   │   ├── admin.py  ← ch. 3
│   │   ├── apps.py  ← ch. 3
│   │   ├── context_processors.py  ← ch. 18
│   │   ├── forms.py  ← ch. 18
│   │   ├── mfa.py  ← ch. 3
│   │   ├── middleware.py  ← ch. 3
│   │   ├── mixins.py  ← ch. 3
│   │   ├── models.py  ← ch. 3
│   │   ├── navigation.py  ← ch. 3
│   │   ├── permissions.py  ← ch. 3
│   │   ├── services.py  ← ch. 3
│   │   ├── signals.py  ← ch. 3
│   │   ├── throttle.py  ← ch. 3
│   │   ├── urls.py  ← ch. 18
│   │   ├── views.py  ← ch. 18
│   │   ├── views_mfa.py  ← ch. 18
│   │   └── views_utilisateurs.py  ← ch. 18
│   ├── api/
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 32
│   │   │   ├── test_auth.py  ← ch. 32
│   │   │   ├── test_auth_mfa.py  ← ch. 32
│   │   │   ├── test_revocation_jetons.py  ← ch. 32
│   │   │   └── test_v1.py  ← ch. 32
│   │   ├── v1/
│   │   │   ├── __init__.py  ← ch. 32
│   │   │   ├── filters.py  ← ch. 32
│   │   │   ├── serializers.py  ← ch. 32
│   │   │   └── views.py  ← ch. 32
│   │   ├── README.md  ← ch. 32
│   │   ├── __init__.py  ← ch. 32
│   │   ├── apps.py  ← ch. 32
│   │   ├── auth.py  ← ch. 32
│   │   ├── exceptions.py  ← ch. 32
│   │   ├── permissions.py  ← ch. 32
│   │   └── urls.py  ← ch. 32
│   ├── audit/
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0002_trigger_append_only.py  ← ch. 4
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templates/
│   │   │   └── audit/
│   │   │       └── journal_list.html  ← ch. 18
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 4
│   │   │   ├── test_couverture.py  ← ch. 13
│   │   │   ├── test_immuable.py  ← ch. 12
│   │   │   ├── test_models.py  ← ch. 4
│   │   │   ├── test_services.py  ← ch. 18
│   │   │   ├── test_signals.py  ← ch. 18
│   │   │   ├── test_utilisateurs.py  ← ch. 18
│   │   │   ├── test_validation_suppression.py  ← ch. 28
│   │   │   └── test_views.py  ← ch. 18
│   │   ├── README.md  ← ch. 4
│   │   ├── __init__.py  ← ch. 4
│   │   ├── admin.py  ← ch. 4
│   │   ├── apps.py  ← ch. 4
│   │   ├── forms.py  ← ch. 18
│   │   ├── models.py  ← ch. 4
│   │   ├── permissions.py  ← ch. 4
│   │   ├── registry.py  ← ch. 4
│   │   ├── services.py  ← ch. 4
│   │   ├── signals.py  ← ch. 4
│   │   ├── urls.py  ← ch. 18
│   │   └── views.py  ← ch. 18
│   ├── billing/
│   │   ├── management/
│   │   │   ├── commands/
│   │   │   │   ├── __init__.py  ← ch. 14
│   │   │   │   └── rattacher_encaissements_missions.py  ← ch. 14
│   │   │   └── __init__.py  ← ch. 14
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0002_depenses_automatiques_parc_auto.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0003_depense_vehicule_alter_depense_categorie_and_more.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0004_proforma.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0005_depense_montant_tva_alter_depense_montant_and_more.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0006_motif_annulation.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0007_index_dates.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0008_avoir.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0009_annulation_transfert.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templates/
│   │   │   └── billing/
│   │   │       ├── avoir_print.html  ← ch. 27
│   │   │       ├── depense_form.html  ← ch. 27
│   │   │       ├── depense_list.html  ← ch. 27
│   │   │       ├── facture_detail.html  ← ch. 27
│   │   │       ├── facture_form.html  ← ch. 27
│   │   │       ├── facture_list.html  ← ch. 27
│   │   │       ├── facture_print.html  ← ch. 27
│   │   │       ├── proforma_detail.html  ← ch. 27
│   │   │       ├── proforma_form.html  ← ch. 27
│   │   │       ├── proforma_list.html  ← ch. 27
│   │   │       ├── proforma_modifier.html  ← ch. 27
│   │   │       └── proforma_print.html  ← ch. 27
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 14
│   │   │   ├── helpers.py  ← ch. 14
│   │   │   ├── test_annulation_depense.py  ← ch. 28
│   │   │   ├── test_avoirs.py  ← ch. 28
│   │   │   ├── test_proforma.py  ← ch. 14
│   │   │   ├── test_proforma_views.py  ← ch. 27
│   │   │   ├── test_r6_creer_mission.py  ← ch. 14
│   │   │   ├── test_services.py  ← ch. 14
│   │   │   └── test_views.py  ← ch. 27
│   │   ├── README.md  ← ch. 14
│   │   ├── __init__.py  ← ch. 14
│   │   ├── apps.py  ← ch. 14
│   │   ├── exceptions.py  ← ch. 14
│   │   ├── forms.py  ← ch. 27
│   │   ├── models.py  ← ch. 14
│   │   ├── permissions.py  ← ch. 14
│   │   ├── receivers.py  ← ch. 14
│   │   ├── services.py  ← ch. 14
│   │   ├── signals.py  ← ch. 14
│   │   ├── urls.py  ← ch. 27
│   │   └── views.py  ← ch. 27
│   ├── core/
│   │   ├── migrations/
│   │   │   ├── 0001_compteur_numero.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0002_document_pdf.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templatetags/
│   │   │   ├── __init__.py  ← ch. 18
│   │   │   ├── graphiques.py  ← ch. 18
│   │   │   └── ui.py  ← ch. 18
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 2
│   │   │   ├── test_admin_suppression.py  ← ch. 26
│   │   │   ├── test_architecture.py  ← ch. 34
│   │   │   ├── test_classeurs.py  ← ch. 33
│   │   │   ├── test_cloudflare.py  ← ch. 34
│   │   │   ├── test_compatibilite_postgresql.py  ← ch. 2
│   │   │   ├── test_csp.py  ← ch. 32
│   │   │   ├── test_deploiement.py  ← ch. 34
│   │   │   ├── test_doublons.py  ← ch. 15
│   │   │   ├── test_echeance.py  ← ch. 2
│   │   │   ├── test_exports_excel.py  ← ch. 26
│   │   │   ├── test_formats.py  ← ch. 2
│   │   │   ├── test_forms_date.py  ← ch. 31
│   │   │   ├── test_graphiques.py  ← ch. 2
│   │   │   ├── test_impression_listes.py  ← ch. 27
│   │   │   ├── test_medias.py  ← ch. 27
│   │   │   ├── test_mesures.py  ← ch. 34
│   │   │   ├── test_models.py  ← ch. 2
│   │   │   ├── test_montants.py  ← ch. 15
│   │   │   ├── test_numerotation.py  ← ch. 2
│   │   │   ├── test_pdf.py  ← ch. 28
│   │   │   ├── test_pdf_tache_de_fond.py  ← ch. 34
│   │   │   ├── test_rapports.py  ← ch. 18
│   │   │   ├── test_search.py  ← ch. 26
│   │   │   ├── test_secret_key_prod.py  ← ch. 2
│   │   │   ├── test_sections.py  ← ch. 2
│   │   │   ├── test_statiques.py  ← ch. 2
│   │   │   └── test_xlsx.py  ← ch. 28
│   │   ├── README.md  ← ch. 2
│   │   ├── __init__.py  ← ch. 2
│   │   ├── admin.py  ← ch. 2
│   │   ├── apps.py  ← ch. 2
│   │   ├── classeurs.py  ← ch. 2
│   │   ├── constants.py  ← ch. 2
│   │   ├── documents_pdf.py  ← ch. 2
│   │   ├── doublons.py  ← ch. 2
│   │   ├── exceptions.py  ← ch. 2
│   │   ├── formats.py  ← ch. 2
│   │   ├── forms.py  ← ch. 2
│   │   ├── graphiques.py  ← ch. 2
│   │   ├── immuable.py  ← ch. 2
│   │   ├── medias.py  ← ch. 2
│   │   ├── mesures.py  ← ch. 2
│   │   ├── middleware.py  ← ch. 2
│   │   ├── models.py  ← ch. 2
│   │   ├── montants.py  ← ch. 2
│   │   ├── pdf.py  ← ch. 2
│   │   ├── rapports.py  ← ch. 2
│   │   ├── search.py  ← ch. 2
│   │   ├── sections.py  ← ch. 2
│   │   ├── services.py  ← ch. 2
│   │   ├── statiques.py  ← ch. 2
│   │   ├── tasks.py  ← ch. 2
│   │   ├── views.py  ← ch. 18
│   │   └── xlsx.py  ← ch. 2
│   ├── customers/
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0002_delai_paiement.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templates/
│   │   │   └── customers/
│   │   │       ├── client_detail.html  ← ch. 21
│   │   │       ├── client_form.html  ← ch. 21
│   │   │       └── client_list.html  ← ch. 21
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 8
│   │   │   ├── factories.py  ← ch. 8
│   │   │   ├── test_models.py  ← ch. 21
│   │   │   ├── test_services.py  ← ch. 21
│   │   │   └── test_views.py  ← ch. 23
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
│   ├── dashboard/
│   │   ├── templates/
│   │   │   └── dashboard/
│   │   │       ├── index.html  ← ch. 30
│   │   │       └── index_print.html  ← ch. 30
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 30
│   │   │   ├── test_cache_en_panne.py  ← ch. 30
│   │   │   ├── test_dashboard.py  ← ch. 30
│   │   │   ├── test_impression.py  ← ch. 30
│   │   │   ├── test_lectures_metier.py  ← ch. 30
│   │   │   └── test_series_mensuelles.py  ← ch. 30
│   │   ├── README.md  ← ch. 30
│   │   ├── __init__.py  ← ch. 30
│   │   ├── apps.py  ← ch. 30
│   │   ├── services.py  ← ch. 30
│   │   └── views.py  ← ch. 30
│   ├── drivers/
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0002_copilote.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0003_index_dates.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templates/
│   │   │   └── drivers/
│   │   │       ├── chauffeur_detail.html  ← ch. 20
│   │   │       ├── chauffeur_form.html  ← ch. 20
│   │   │       └── chauffeur_list.html  ← ch. 20
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 7
│   │   │   ├── factories.py  ← ch. 7
│   │   │   ├── test_copilote.py  ← ch. 7
│   │   │   ├── test_fiche.py  ← ch. 7
│   │   │   ├── test_models.py  ← ch. 7
│   │   │   ├── test_services.py  ← ch. 7
│   │   │   ├── test_suivi_personnel.py  ← ch. 7
│   │   │   └── test_views.py  ← ch. 23
│   │   ├── README.md  ← ch. 7
│   │   ├── __init__.py  ← ch. 7
│   │   ├── admin.py  ← ch. 7
│   │   ├── apps.py  ← ch. 7
│   │   ├── exceptions.py  ← ch. 7
│   │   ├── forms.py  ← ch. 20
│   │   ├── models.py  ← ch. 7
│   │   ├── permissions.py  ← ch. 7
│   │   ├── services.py  ← ch. 7
│   │   ├── signals.py  ← ch. 7
│   │   ├── urls.py  ← ch. 20
│   │   └── views.py  ← ch. 20
│   ├── finance/
│   │   ├── management/
│   │   │   ├── commands/
│   │   │   │   ├── __init__.py  ← ch. 15
│   │   │   │   └── comptabiliser_historique_parc_auto.py  ← ch. 15
│   │   │   └── __init__.py  ← ch. 15
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0002_demandedepense_enveloppedepense_ordredecaissement_and_more.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0003_mouvementmanuel_nature.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0004_lignereleve.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0005_index_dates.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0006_enveloppe_globale_unique.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0007_demande_enveloppe.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templates/
│   │   │   └── finance/
│   │   │       ├── demande_detail.html  ← ch. 27
│   │   │       ├── demande_form.html  ← ch. 27
│   │   │       ├── demande_list.html  ← ch. 27
│   │   │       ├── enveloppe_list.html  ← ch. 27
│   │   │       ├── rapprochement.html  ← ch. 27
│   │   │       ├── tresorerie.html  ← ch. 27
│   │   │       ├── tresorerie_print.html  ← ch. 27
│   │   │       └── versement_confirmer.html  ← ch. 27
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 15
│   │   │   ├── test_demandes.py  ← ch. 15
│   │   │   ├── test_demandes_views.py  ← ch. 27
│   │   │   ├── test_depenses_parc_auto.py  ← ch. 27
│   │   │   ├── test_erreurs_depense_automatique.py  ← ch. 32
│   │   │   ├── test_frais_mission_receivers.py  ← ch. 15
│   │   │   ├── test_impression.py  ← ch. 27
│   │   │   ├── test_rapprochement_views.py  ← ch. 27
│   │   │   ├── test_services.py  ← ch. 16
│   │   │   ├── test_versements.py  ← ch. 27
│   │   │   └── test_views.py  ← ch. 27
│   │   ├── README.md  ← ch. 15
│   │   ├── __init__.py  ← ch. 15
│   │   ├── apps.py  ← ch. 15
│   │   ├── demandes.py  ← ch. 15
│   │   ├── forms.py  ← ch. 27
│   │   ├── models.py  ← ch. 15
│   │   ├── permissions.py  ← ch. 15
│   │   ├── receivers.py  ← ch. 15
│   │   ├── services.py  ← ch. 15
│   │   ├── signals.py  ← ch. 15
│   │   ├── urls.py  ← ch. 27
│   │   └── views.py  ← ch. 27
│   ├── fleet/
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0002_marquage_vehicule.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0003_index_dates.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templates/
│   │   │   └── fleet/
│   │   │       ├── vehicule_detail.html  ← ch. 22
│   │   │       ├── vehicule_form.html  ← ch. 22
│   │   │       └── vehicule_list.html  ← ch. 22
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 9
│   │   │   ├── factories.py  ← ch. 9
│   │   │   ├── test_correction_compteur.py  ← ch. 22
│   │   │   ├── test_fiche.py  ← ch. 9
│   │   │   ├── test_models.py  ← ch. 9
│   │   │   ├── test_services.py  ← ch. 9
│   │   │   └── test_views.py  ← ch. 22
│   │   ├── README.md  ← ch. 9
│   │   ├── __init__.py  ← ch. 9
│   │   ├── admin.py  ← ch. 9
│   │   ├── apps.py  ← ch. 9
│   │   ├── exceptions.py  ← ch. 9
│   │   ├── forms.py  ← ch. 22
│   │   ├── models.py  ← ch. 9
│   │   ├── permissions.py  ← ch. 9
│   │   ├── sections.py  ← ch. 9
│   │   ├── services.py  ← ch. 9
│   │   ├── urls.py  ← ch. 22
│   │   └── views.py  ← ch. 22
│   ├── fuel/
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0002_libelles_alertes_parametrables.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0003_motif_annulation.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0004_index_dates.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templates/
│   │   │   └── fuel/
│   │   │       ├── analyse.html  ← ch. 26
│   │   │       ├── plein_annuler.html  ← ch. 26
│   │   │       ├── plein_form.html  ← ch. 26
│   │   │       └── plein_list.html  ← ch. 26
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 13
│   │   │   ├── factories.py  ← ch. 13
│   │   │   ├── test_annulation_plein.py  ← ch. 28
│   │   │   ├── test_coherence_saisie.py  ← ch. 13
│   │   │   ├── test_lecture.py  ← ch. 13
│   │   │   ├── test_models.py  ← ch. 13
│   │   │   ├── test_services.py  ← ch. 13
│   │   │   └── test_views.py  ← ch. 26
│   │   ├── README.md  ← ch. 13
│   │   ├── __init__.py  ← ch. 13
│   │   ├── admin.py  ← ch. 13
│   │   ├── apps.py  ← ch. 13
│   │   ├── exceptions.py  ← ch. 13
│   │   ├── forms.py  ← ch. 26
│   │   ├── models.py  ← ch. 13
│   │   ├── permissions.py  ← ch. 13
│   │   ├── services.py  ← ch. 13
│   │   ├── signals.py  ← ch. 13
│   │   ├── urls.py  ← ch. 26
│   │   └── views.py  ← ch. 26
│   ├── garage/
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0002_incidents_checklists.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templates/
│   │   │   └── garage/
│   │   │       ├── _maintenance_vehicule.html  ← ch. 24
│   │   │       ├── checklist_list.html  ← ch. 24
│   │   │       ├── incident_detail.html  ← ch. 24
│   │   │       ├── incident_list.html  ← ch. 24
│   │   │       ├── or_detail.html  ← ch. 24
│   │   │       ├── or_form.html  ← ch. 24
│   │   │       └── or_list.html  ← ch. 24
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 11
│   │   │   ├── factories.py  ← ch. 11
│   │   │   ├── test_models.py  ← ch. 11
│   │   │   ├── test_services.py  ← ch. 11
│   │   │   ├── test_statut_vehicule.py  ← ch. 11
│   │   │   ├── test_terrain.py  ← ch. 11
│   │   │   ├── test_views.py  ← ch. 24
│   │   │   └── test_views_terrain.py  ← ch. 24
│   │   ├── README.md  ← ch. 11
│   │   ├── __init__.py  ← ch. 11
│   │   ├── admin.py  ← ch. 11
│   │   ├── apps.py  ← ch. 11
│   │   ├── exceptions.py  ← ch. 11
│   │   ├── forms.py  ← ch. 24
│   │   ├── forms_terrain.py  ← ch. 24
│   │   ├── models.py  ← ch. 11
│   │   ├── permissions.py  ← ch. 11
│   │   ├── sections.py  ← ch. 11
│   │   ├── services.py  ← ch. 11
│   │   ├── signals.py  ← ch. 11
│   │   ├── terrain.py  ← ch. 11
│   │   ├── urls.py  ← ch. 24
│   │   ├── views.py  ← ch. 24
│   │   └── views_terrain.py  ← ch. 24
│   ├── hr/
│   │   ├── management/
│   │   │   ├── commands/
│   │   │   │   ├── __init__.py  ← ch. 6
│   │   │   │   ├── creer_comptes_demo.py  ← ch. 6
│   │   │   │   └── initialiser_jours_feries.py  ← ch. 6
│   │   │   └── __init__.py  ← ch. 6
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
│   │   │   ├── 0011_sortie_personnel.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0012_validation_conge_auto.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0013_date_reprise.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templates/
│   │   │   └── hr/
│   │   │       ├── conge_detail.html  ← ch. 19
│   │   │       ├── conge_form.html  ← ch. 19
│   │   │       ├── conge_list.html  ← ch. 19
│   │   │       ├── jours_feries.html  ← ch. 19
│   │   │       ├── personnel_detail.html  ← ch. 19
│   │   │       ├── personnel_form.html  ← ch. 19
│   │   │       ├── personnel_import.html  ← ch. 19
│   │   │       ├── personnel_list.html  ← ch. 19
│   │   │       └── report_form.html  ← ch. 19
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 6
│   │   │   ├── factories.py  ← ch. 6
│   │   │   ├── test_audit.py  ← ch. 6
│   │   │   ├── test_comptes_demo.py  ← ch. 7
│   │   │   ├── test_conge_statut_chauffeur.py  ← ch. 7
│   │   │   ├── test_conges.py  ← ch. 7
│   │   │   ├── test_direction_remplace.py  ← ch. 19
│   │   │   ├── test_droits_conges.py  ← ch. 7
│   │   │   ├── test_import_personnel.py  ← ch. 20
│   │   │   ├── test_jours_feries.py  ← ch. 6
│   │   │   ├── test_jours_feries_ecran.py  ← ch. 19
│   │   │   ├── test_models.py  ← ch. 6
│   │   │   ├── test_recrutement.py  ← ch. 7
│   │   │   ├── test_report_conge.py  ← ch. 19
│   │   │   ├── test_separation_n1_n2.py  ← ch. 19
│   │   │   ├── test_services_ecrans.py  ← ch. 6
│   │   │   ├── test_sorties.py  ← ch. 6
│   │   │   ├── test_sorties_ecrans.py  ← ch. 19
│   │   │   ├── test_views_conges.py  ← ch. 19
│   │   │   └── test_views_personnel.py  ← ch. 20
│   │   ├── README.md  ← ch. 6
│   │   ├── __init__.py  ← ch. 6
│   │   ├── admin.py  ← ch. 6
│   │   ├── apps.py  ← ch. 6
│   │   ├── documents.py  ← ch. 6
│   │   ├── exceptions.py  ← ch. 6
│   │   ├── forms.py  ← ch. 19
│   │   ├── models.py  ← ch. 6
│   │   ├── permissions.py  ← ch. 6
│   │   ├── sections.py  ← ch. 6
│   │   ├── services.py  ← ch. 6
│   │   ├── signals.py  ← ch. 6
│   │   ├── sorties.py  ← ch. 6
│   │   ├── urls.py  ← ch. 19
│   │   └── views.py  ← ch. 19
│   ├── importation/
│   │   ├── management/
│   │   │   ├── commands/
│   │   │   │   ├── __init__.py  ← ch. 33
│   │   │   │   └── generer_modele_import.py  ← ch. 33
│   │   │   └── __init__.py  ← ch. 33
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 33
│   │   │   ├── helpers.py  ← ch. 33
│   │   │   ├── test_fichiers_pieges.py  ← ch. 33
│   │   │   └── test_import.py  ← ch. 33
│   │   ├── README.md  ← ch. 33
│   │   ├── __init__.py  ← ch. 33
│   │   ├── apps.py  ← ch. 33
│   │   ├── forms.py  ← ch. 33
│   │   ├── modele.py  ← ch. 33
│   │   ├── permissions.py  ← ch. 33
│   │   ├── services.py  ← ch. 33
│   │   ├── urls.py  ← ch. 33
│   │   └── views.py  ← ch. 33
│   ├── inventory/
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0002_trigger_append_only.py  ← ch. 12
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templates/
│   │   │   └── inventory/
│   │   │       ├── _pieces_or.html  ← ch. 25
│   │   │       ├── article_detail.html  ← ch. 25
│   │   │       ├── article_form.html  ← ch. 25
│   │   │       ├── article_list.html  ← ch. 25
│   │   │       └── mouvement_list.html  ← ch. 25
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 12
│   │   │   ├── factories.py  ← ch. 12
│   │   │   ├── test_fiche.py  ← ch. 12
│   │   │   ├── test_models.py  ← ch. 12
│   │   │   ├── test_services.py  ← ch. 12
│   │   │   ├── test_stock_views.py  ← ch. 25
│   │   │   └── test_views.py  ← ch. 27
│   │   ├── README.md  ← ch. 12
│   │   ├── __init__.py  ← ch. 12
│   │   ├── admin.py  ← ch. 12
│   │   ├── apps.py  ← ch. 12
│   │   ├── exceptions.py  ← ch. 12
│   │   ├── forms.py  ← ch. 12
│   │   ├── models.py  ← ch. 12
│   │   ├── permissions.py  ← ch. 12
│   │   ├── sections.py  ← ch. 12
│   │   ├── services.py  ← ch. 12
│   │   ├── signals.py  ← ch. 12
│   │   ├── urls.py  ← ch. 25
│   │   └── views.py  ← ch. 25
│   ├── missions/
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0002_fraismission.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0002_mission_proforma.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0003_merge_0002_fraismission_0002_mission_proforma.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0004_mission_copilote.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0005_frais_mission_reglement.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0006_annulation_transfert.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templates/
│   │   │   └── missions/
│   │   │       ├── _alerte_conge.html  ← ch. 23
│   │   │       ├── _missions_client.html  ← ch. 23
│   │   │       ├── frais_detail.html  ← ch. 23
│   │   │       ├── frais_liste.html  ← ch. 23
│   │   │       ├── frais_print.html  ← ch. 23
│   │   │       ├── mission_detail.html  ← ch. 23
│   │   │       ├── mission_form.html  ← ch. 23
│   │   │       ├── mission_list.html  ← ch. 23
│   │   │       ├── mission_modifier.html  ← ch. 23
│   │   │       └── mission_transfert.html  ← ch. 23
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 10
│   │   │   ├── factories.py  ← ch. 10
│   │   │   ├── test_alerte_conge.py  ← ch. 23
│   │   │   ├── test_annulation_transfert.py  ← ch. 27
│   │   │   ├── test_documents.py  ← ch. 23
│   │   │   ├── test_documents_et_reaffectation.py  ← ch. 23
│   │   │   ├── test_encaissement_annule.py  ← ch. 14
│   │   │   ├── test_frais_mission.py  ← ch. 10
│   │   │   ├── test_frais_mission_views.py  ← ch. 23
│   │   │   ├── test_models.py  ← ch. 10
│   │   │   ├── test_modification.py  ← ch. 23
│   │   │   ├── test_permissions.py  ← ch. 10
│   │   │   ├── test_plausibilite_km.py  ← ch. 10
│   │   │   ├── test_qr.py  ← ch. 23
│   │   │   ├── test_services.py  ← ch. 10
│   │   │   ├── test_sortie_personnel.py  ← ch. 23
│   │   │   ├── test_temps_reel.py  ← ch. 10
│   │   │   └── test_views.py  ← ch. 23
│   │   ├── README.md  ← ch. 10
│   │   ├── __init__.py  ← ch. 10
│   │   ├── admin.py  ← ch. 10
│   │   ├── apps.py  ← ch. 10
│   │   ├── consumers.py  ← ch. 10
│   │   ├── documents.py  ← ch. 10
│   │   ├── exceptions.py  ← ch. 10
│   │   ├── forms.py  ← ch. 23
│   │   ├── models.py  ← ch. 10
│   │   ├── permissions.py  ← ch. 10
│   │   ├── receivers.py  ← ch. 10
│   │   ├── routing.py  ← ch. 10
│   │   ├── sections.py  ← ch. 10
│   │   ├── services.py  ← ch. 10
│   │   ├── signals.py  ← ch. 10
│   │   ├── temps_reel.py  ← ch. 10
│   │   ├── terrain.py  ← ch. 10
│   │   ├── urls.py  ← ch. 23
│   │   └── views.py  ← ch. 23
│   ├── mobile_api/
│   │   ├── templates/
│   │   │   └── mobile/
│   │   │       ├── _carte_mission.html  ← ch. 31
│   │   │       ├── _scanner.html  ← ch. 31
│   │   │       ├── accueil.html  ← ch. 31
│   │   │       ├── base.html  ← ch. 31
│   │   │       ├── checklist.html  ← ch. 31
│   │   │       ├── conges.html  ← ch. 31
│   │   │       ├── hors_ligne.html  ← ch. 31
│   │   │       ├── imprevu.html  ← ch. 31
│   │   │       ├── incident.html  ← ch. 31
│   │   │       ├── mission.html  ← ch. 31
│   │   │       ├── missions.html  ← ch. 31
│   │   │       ├── plein.html  ← ch. 31
│   │   │       └── sw.js  ← ch. 31
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 31
│   │   │   ├── helpers.py  ← ch. 31
│   │   │   ├── test_api.py  ← ch. 32
│   │   │   ├── test_conges.py  ← ch. 32
│   │   │   ├── test_frais_mission.py  ← ch. 32
│   │   │   ├── test_services.py  ← ch. 31
│   │   │   └── test_web.py  ← ch. 31
│   │   ├── README.md  ← ch. 31
│   │   ├── __init__.py  ← ch. 31
│   │   ├── apps.py  ← ch. 31
│   │   ├── exceptions.py  ← ch. 31
│   │   ├── forms.py  ← ch. 31
│   │   ├── permissions.py  ← ch. 31
│   │   ├── serializers.py  ← ch. 31
│   │   ├── services.py  ← ch. 31
│   │   ├── urls.py  ← ch. 31
│   │   ├── urls_web.py  ← ch. 31
│   │   ├── views.py  ← ch. 31
│   │   └── views_web.py  ← ch. 31
│   ├── notifications/
│   │   ├── management/
│   │   │   ├── commands/
│   │   │   │   ├── __init__.py  ← ch. 17
│   │   │   │   └── taches_quotidiennes.py  ← ch. 17
│   │   │   └── __init__.py  ← ch. 17
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0002_categorie_facture.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0003_categorie_incident.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0004_action_du_bouton.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0005_alter_notification_categorie.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0006_categorie_personnel.py  ← (généré par `python manage.py makemigrations`)
│   │   │   ├── 0007_categorie_compte.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── templates/
│   │   │   └── notifications/
│   │   │       └── liste.html  ← ch. 18
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 17
│   │   │   ├── test_compte_direction.py  ← ch. 17
│   │   │   ├── test_facturation.py  ← ch. 27
│   │   │   ├── test_receivers.py  ← ch. 26
│   │   │   ├── test_receivers_demandes.py  ← ch. 27
│   │   │   ├── test_receivers_frais_mission.py  ← ch. 23
│   │   │   ├── test_receivers_proforma.py  ← ch. 27
│   │   │   ├── test_services.py  ← ch. 25
│   │   │   ├── test_taches.py  ← ch. 22
│   │   │   ├── test_tasks.py  ← ch. 17
│   │   │   ├── test_terrain.py  ← ch. 30
│   │   │   └── test_views.py  ← ch. 25
│   │   ├── README.md  ← ch. 17
│   │   ├── __init__.py  ← ch. 17
│   │   ├── admin.py  ← ch. 17
│   │   ├── apps.py  ← ch. 17
│   │   ├── context_processors.py  ← ch. 18
│   │   ├── models.py  ← ch. 17
│   │   ├── receivers.py  ← ch. 17
│   │   ├── services.py  ← ch. 17
│   │   ├── taches.py  ← ch. 17
│   │   ├── tasks.py  ← ch. 17
│   │   ├── urls.py  ← ch. 18
│   │   └── views.py  ← ch. 18
│   ├── parametres/
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py  ← (généré par `python manage.py makemigrations`)
│   │   │   └── __init__.py  ← (généré par `python manage.py makemigrations`)
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 5
│   │   │   └── test_parametres.py  ← ch. 18
│   │   ├── README.md  ← ch. 5
│   │   ├── __init__.py  ← ch. 5
│   │   ├── apps.py  ← ch. 5
│   │   ├── context_processors.py  ← ch. 18
│   │   ├── forms.py  ← ch. 18
│   │   ├── models.py  ← ch. 5
│   │   ├── permissions.py  ← ch. 5
│   │   ├── services.py  ← ch. 5
│   │   ├── urls.py  ← ch. 18
│   │   └── views.py  ← ch. 18
│   ├── sauvegardes/
│   │   ├── tests/
│   │   │   ├── __init__.py  ← ch. 29
│   │   │   ├── test_sauvegardes.py  ← ch. 30
│   │   │   └── test_scripts.py  ← ch. 34
│   │   ├── README.md  ← ch. 29
│   │   ├── __init__.py  ← ch. 29
│   │   ├── apps.py  ← ch. 29
│   │   ├── permissions.py  ← ch. 29
│   │   ├── services.py  ← ch. 29
│   │   ├── urls.py  ← ch. 29
│   │   └── views.py  ← ch. 29
│   └── __init__.py  ← ch. 1
├── audit/
│   └── MATRICE.md  ← (documents de référence à lire)
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
├── formation/
│   ├── exercices/
│   │   ├── 01-couleur-camion/
│   │   │   ├── README.md  ← (programme de formation)
│   │   │   ├── correction.diff  ← (programme de formation)
│   │   │   ├── correction.md  ← (programme de formation)
│   │   │   └── test_exercice_01.py  ← (programme de formation)
│   │   ├── 02-carte-de-transport/
│   │   │   ├── README.md  ← (programme de formation)
│   │   │   ├── correction.diff  ← (programme de formation)
│   │   │   ├── correction.md  ← (programme de formation)
│   │   │   └── test_exercice_02.py  ← (programme de formation)
│   │   ├── 03-delai-alerte-chauffeurs/
│   │   │   ├── README.md  ← (programme de formation)
│   │   │   ├── correction.diff  ← (programme de formation)
│   │   │   ├── correction.md  ← (programme de formation)
│   │   │   └── test_exercice_03.py  ← (programme de formation)
│   │   ├── 04-categorie-frais-bancaires/
│   │   │   ├── README.md  ← (programme de formation)
│   │   │   ├── correction.diff  ← (programme de formation)
│   │   │   ├── correction.md  ← (programme de formation)
│   │   │   └── test_exercice_04.py  ← (programme de formation)
│   │   ├── 05-missions-finance-rh/
│   │   │   ├── README.md  ← (programme de formation)
│   │   │   ├── correction.diff  ← (programme de formation)
│   │   │   ├── correction.md  ← (programme de formation)
│   │   │   └── test_exercice_05.py  ← (programme de formation)
│   │   ├── 06-colonne-vin-flotte/
│   │   │   ├── README.md  ← (programme de formation)
│   │   │   ├── correction.diff  ← (programme de formation)
│   │   │   ├── correction.md  ← (programme de formation)
│   │   │   └── test_exercice_06.py  ← (programme de formation)
│   │   ├── 07-missions-annulees-tableau-de-bord/
│   │   │   ├── README.md  ← (programme de formation)
│   │   │   ├── correction.diff  ← (programme de formation)
│   │   │   ├── correction.md  ← (programme de formation)
│   │   │   └── test_exercice_07.py  ← (programme de formation)
│   │   └── 08-api-articles/
│   │       ├── README.md  ← (programme de formation)
│   │       ├── correction.diff  ← (programme de formation)
│   │       ├── correction.md  ← (programme de formation)
│   │       └── test_exercice_08.py  ← (programme de formation)
│   ├── README.md  ← (programme de formation)
│   ├── semaines-01-02-la-carte.md  ← (programme de formation)
│   └── semaines-11-12-projet-final.md  ← (programme de formation)
├── frontend/
│   ├── .gitignore  ← ch. 18
│   ├── README.md  ← ch. 18
│   ├── input.css  ← ch. 18
│   ├── package-lock.json  ← (généré par `npm install`)
│   ├── package.json  ← ch. 18
│   ├── tailwind.config.js  ← ch. 18
│   └── vendor.js  ← ch. 18
├── nginx/
│   ├── Dockerfile  ← (mise en production)
│   ├── cloudflare-ips.conf  ← (mise en production)
│   ├── maj-ips-cloudflare.sh  ← (mise en production)
│   ├── nginx.conf  ← (mise en production)
│   └── preparer-https.sh  ← (mise en production)
├── ops/
│   ├── Dockerfile.sauvegarde  ← (mise en production)
│   ├── entrypoint.sh  ← (mise en production)
│   ├── fonctions-sauvegarde.sh  ← (mise en production)
│   ├── gunicorn.conf.py  ← (mise en production)
│   ├── planificateur-sauvegarde.sh  ← (mise en production)
│   ├── prometheus-alertes.yml  ← (mise en production)
│   ├── prometheus.yml  ← (mise en production)
│   ├── restauration.sh  ← (mise en production)
│   └── sauvegarde.sh  ← (mise en production)
├── recette_navigateurs/
│   ├── RESULTATS.md  ← (généré par la recette navigateurs)
│   ├── __init__.py  ← ch. 34
│   ├── conftest.py  ← ch. 34
│   ├── reglages_asgi.py  ← ch. 34
│   ├── test_recette.py  ← ch. 34
│   └── test_temps_reel.py  ← ch. 34
├── requirements/
│   ├── base.txt  ← ch. 1
│   ├── dev.txt  ← ch. 1
│   ├── prod.lock  ← (généré par `python outils/verrouiller_dependances.py`)
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
│   │   ├── app.js  ← ch. 18
│   │   ├── scanner.js  ← ch. 31
│   │   ├── suivi-missions.js  ← ch. 23
│   │   └── sw-register.js  ← ch. 31
│   └── vendor/
│       ├── alpine/
│       │   └── alpine.min.js  ← (généré par `npm run build`)
│       ├── fontawesome/
│       │   ├── css/
│       │   │   └── all.min.css  ← (généré par `npm run build`)
│       │   ├── webfonts/
│       │   │   ├── fa-regular-400.woff2  ← (généré par `npm run build`)
│       │   │   └── fa-solid-900.woff2  ← (généré par `npm run build`)
│       │   └── LICENSE.txt  ← (généré par `npm run build`)
│       └── jsqr/
│           ├── LICENSE  ← (généré par `npm run build`)
│           └── jsQR.js  ← (généré par `npm run build`)
├── templates/
│   ├── accounts/
│   │   ├── mfa_activer.html  ← ch. 18
│   │   ├── mfa_codes.html  ← ch. 18
│   │   ├── mfa_codes_affiches.html  ← ch. 18
│   │   ├── mfa_verifier.html  ← ch. 18
│   │   ├── utilisateur_form.html  ← ch. 18
│   │   └── utilisateur_list.html  ← ch. 18
│   ├── components/
│   │   ├── _assets.html  ← ch. 18
│   │   ├── _bouton_xlsx.html  ← ch. 18
│   │   ├── _champ.html  ← ch. 18
│   │   ├── _graphique_barres.html  ← ch. 18
│   │   ├── _graphique_colonnes.html  ← ch. 18
│   │   ├── _messages.html  ← ch. 18
│   │   ├── _pagination.html  ← ch. 18
│   │   └── _suivi_direct.html  ← ch. 18
│   ├── core/
│   │   └── document_pdf.html  ← ch. 18
│   ├── importation/
│   │   └── importer.html  ← ch. 33
│   ├── parametres/
│   │   └── parametres.html  ← ch. 18
│   ├── rapports/
│   │   ├── _entete_impression.html  ← ch. 18
│   │   ├── _pied_impression.html  ← ch. 18
│   │   ├── _style_impression.html  ← ch. 18
│   │   └── liste_impression.html  ← ch. 18
│   ├── registration/
│   │   ├── login.html  ← ch. 18
│   │   ├── password_change_form.html  ← ch. 18
│   │   ├── password_reset_complete.html  ← ch. 18
│   │   ├── password_reset_confirm.html  ← ch. 18
│   │   ├── password_reset_done.html  ← ch. 18
│   │   ├── password_reset_email.txt  ← ch. 18
│   │   ├── password_reset_form.html  ← ch. 18
│   │   └── password_reset_subject.txt  ← ch. 18
│   ├── sauvegardes/
│   │   ├── _fichier.html  ← ch. 29
│   │   └── sauvegardes.html  ← ch. 29
│   ├── 403.html  ← ch. 18
│   ├── 404.html  ← ch. 18
│   └── base.html  ← ch. 18
├── .dockerignore  ← (mise en production)
├── .env.example  ← ch. 1
├── .gitattributes  ← ch. 1
├── .gitignore  ← ch. 1
├── CAHIER DES CHARGES FONCTIONNEL ET TECHNIQUE.docx  ← (documents de présentation, sans rapport avec le fonctionnement)
├── Dockerfile  ← (mise en production)
├── GUIDE-DEPLOIEMENT.md  ← (documents de référence à lire)
├── GUIDE-INTERFACE.md  ← (documents de référence à lire)
├── GUIDE-PARCOURS.md  ← (documents de référence à lire)
├── Presentation-ERP-DEN-Source.docx  ← (documents de présentation, sans rapport avec le fonctionnement)
├── Presentation-ERP-DEN-Source.pptx  ← (documents de présentation, sans rapport avec le fonctionnement)
├── README.md  ← ch. 34
├── RECETTE-NAVIGATEURS.md  ← (documents de référence à lire)
├── architecture.md  ← (documents de référence à lire)
├── audit-checklist.md  ← (documents de référence à lire)
├── avenant-affectation-documents.md  ← (documents de référence à lire)
├── avenant-comptabilite-autonomie.md  ← (documents de référence à lire)
├── avenant-comptabilite-syscohada.md  ← (documents de référence à lire)
├── avenant-decisions-audit.md  ← (documents de référence à lire)
├── avenant-export-pdf.md  ← (documents de référence à lire)
├── avenant-montants-fcfa.md  ← (documents de référence à lire)
├── avenant-parametres.md  ← (documents de référence à lire)
├── avenant-sauvegardes.md  ← (documents de référence à lire)
├── avenant-separation-des-taches.md  ← (documents de référence à lire)
├── avenant-sortie-personnel.md  ← (documents de référence à lire)
├── avenant-validation-factures.md  ← (documents de référence à lire)
├── cahier-des-charges.md  ← (documents de référence à lire)
├── conventions.md  ← (documents de référence à lire)
├── docker-compose.yml  ← (mise en production)
├── glossaire-metier.md  ← (documents de référence à lire)
├── manage.py  ← ch. 1
├── modele-donnees-entreprise-DEN-Source.xlsx  ← (classeur Excel modèle, généré par `python manage.py generer_modele_import`)
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
