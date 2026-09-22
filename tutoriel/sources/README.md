# Construire l'ERP DEN Source Group de A à Z

Ce tutoriel vous fait **reconstruire, fichier par fichier, l'application complète** : un ERP de
transport et de logistique (missions, camions, chauffeurs, carburant, stock, clients, personnel, congés,
facturation, trésorerie, tableau de bord, espace mobile du chauffeur, API), avec sa suite de **près de 1 800 tests**.

Chaque chapitre vous dit **quoi faire**, **pourquoi**, **quelles commandes lancer**, **donne le code complet
à créer**, puis **comment vérifier** que tout fonctionne avant de passer au suivant.

## Ce que ce tutoriel garantit

- **Le code est exact.** Il n'est pas recopié à la main : il est extrait automatiquement du dépôt par
  `outils/generer_tutoriel.py`. Si le code change, on régénère le tutoriel.
- **Le tutoriel a été rejoué.** `outils/tester_tutoriel.py` reconstruit le projet dans un dossier vide,
  chapitre après chapitre, en exécutant les commandes demandées (`check`, `makemigrations`, `migrate`,
  `npm run build`, `pytest`). À la fin : **tous les tests passent** (voir le chapitre 29).
- **Chaque fichier suivi par git est couvert** : soit présenté ici, soit exclu pour une raison écrite
  (tableau plus bas).

## Comment lire ce tutoriel

Il suit l'ordre dans lequel on construit vraiment un projet Django de cette taille :

1. **Le cerveau d'abord** (chapitres 2 à 15) : pour chaque domaine, les *modèles* (les tables), les
   *règles métier* (`services.py`) et leurs *tests*. Rien à cliquer dans un navigateur, mais tout est
   vérifié par des tests.
2. **Puis le visage** (chapitres 16 à 28) : les gabarits HTML, les formulaires, les vues, le tableau de
   bord, l'espace mobile et l'API.
3. **Enfin la vérification d'ensemble** (chapitre 29).

Chaque application n'utilise que celles qui la précèdent : on peut donc toujours s'arrêter à la fin
d'un chapitre avec un projet qui fonctionne.

## Sommaire

{{INDEX}}

## Ce qui n'est pas recopié dans ce tutoriel

Ces fichiers sont dans le dépôt mais **ne se recopient pas**. Le chapitre concerné dit comment les obtenir.

{{COUVERTURE}}

## Avant de commencer

Lisez le [chapitre 0](00-prerequis.md) : il liste les outils à installer, explique l'arborescence finale
du projet et la méthode de travail (une copie de fichier, une vérification, un commit).

## Petit lexique des symboles

| Symbole | Sens |
|---|---|
| `#### chemin/du/fichier.py` | un fichier à créer, avec son contenu complet juste en dessous |
| ` ```bash ` | une commande à taper dans le terminal, à la racine du projet |
| ` ```diff ` | une modification de fichier existant : les lignes `+` sont à ajouter |
| **Résultat attendu** | ce que vous devez voir ; si ce n'est pas le cas, ne continuez pas |
