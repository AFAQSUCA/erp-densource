## Ce que vous allez construire

**`sauvegardes`** : l'écran où l'**ADMIN suit les sauvegardes** et en demande une immédiatement
(`avenant-sauvegardes.md`). L'application ne sauvegarde rien elle-même : un **service dédié** de la mise en
production (Docker, chapitre 34) sauvegarde la base et les fichiers déposés chaque nuit, chiffrés. L'application,
elle, **lit son journal** et **dépose des demandes**.

| Élément | Règle |
|---|---|
| **Journal** | un fichier `journal.jsonl` écrit par le service : une ligne JSON par essai (début, fin, statut, taille et empreinte de chaque fichier) ; une ligne illisible est ignorée sans masquer les autres |
| **Statuts** | `OK` ; `ALERTE` (sauvegarde faite, copie hors serveur échouée) ; `ECHEC` |
| **« Sauvegarder maintenant »** | dépose un fichier de demande que le service exécute dans la minute ; refusé si une sauvegarde est déjà en cours ou demandée (double clic) |
| **Alerte** | au centre d'alertes de l'ADMIN : aucune sauvegarde réussie, ou la dernière a plus de 26 h (urgent) ; dernier essai en échec (attention) |
| **Droits** | ADMIN seulement ; chaque demande va au journal d'audit |

Pourquoi maintenant ? Le **tableau de bord** du chapitre suivant affiche cette alerte : il lit `sauvegardes`, qui doit
donc exister avant lui.

## Prérequis

- Chapitres 1 à 28 terminés (l'écran utilise le socle de l'interface du chapitre 18).

## Ce que ce chapitre apporte de nouveau

- **Une app sans modèle** : tout son état vit dans des **fichiers** partagés avec le service de sauvegarde
  (`settings.SAUVEGARDES_DIR`). Pas de migration.
- **Séparer les privilèges** : l'application n'a accès ni à Docker ni aux fichiers chiffrés. Elle se contente de
  **déposer une demande** ; seul le service, qui tourne à part, a le droit de sauvegarder.
- **Écriture atomique** : la demande est écrite dans un fichier temporaire puis **renommée** (`os.replace`) : le
  service ne lit jamais un fichier à moitié écrit.
- **Une jauge pour Prometheus** : au démarrage, `ready()` inscrit l'âge de la dernière sauvegarde réussie parmi les
  mesures du socle (`apps/core/mesures.py`, chapitre 2), sans que `core` ait à connaître `sauvegardes`.

## Étape 1 — Créer l'application

```bash
mkdir -p apps/sauvegardes/tests templates/sauvegardes
```

{{VIDES}}

## Étape 2 — Lire le journal, déposer une demande

{{FICHIER apps/sauvegardes/README.md}}

{{FICHIER apps/sauvegardes/permissions.py}}

{{FICHIER apps/sauvegardes/services.py}}

- **`journal()`** et **`derniere_reussie()`** relisent `journal.jsonl` du plus récent au plus ancien.
- **`demander_sauvegarde`** contrôle le rôle, refuse un doublon, écrit la demande de façon atomique puis la
  journalise.
- **`alerte()`** ne dit rien tant que `SAUVEGARDES_SURVEILLEES` est faux : en développement, aucun service de
  sauvegarde ne tourne, l'alerte serait permanente.

{{FICHIER apps/sauvegardes/apps.py}}

## Étape 3 — L'écran

{{RESTANTS}}

La page se **recharge seule** tant qu'une sauvegarde est demandée ou en cours (`rafraichir`), pour afficher le
résultat dès qu'il arrive.

## Étape 4 — Déclarer l'application

{{CONFIG}}

```bash
cd frontend && npm run build:css && cd ..
python manage.py check
```

**Résultat attendu :** `System check identified no issues (0 silenced).` (pas de `makemigrations` : l'app n'a pas de
modèle).

## Vérifier le chapitre

Les tests de `sauvegardes` vérifient aussi l'alerte du tableau de bord : ils sont présentés au chapitre suivant.
Vérifiez à la main, avec un compte ADMIN (`python manage.py runserver`, menu « Sauvegardes ») : la page indique
qu'aucune sauvegarde n'est encore enregistrée ; « Sauvegarder maintenant » crée un fichier dans
`sauvegardes/demandes/` et un second clic est refusé avec le message « Une sauvegarde est déjà demandée ».
Supprimez ensuite ce fichier de demande : en développement, aucun service ne viendra le traiter.

## Ce qu'il faut retenir

- Une application web n'a pas à détenir tous les droits : elle peut **demander** une action à un service qui, lui,
  a le privilège de l'exécuter.
- Écrire puis renommer un fichier rend son apparition **atomique** pour celui qui le lit.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 29 : app sauvegardes (suivi des sauvegardes, demande immédiate, alerte)"
```
