## Ce que vous allez construire

Les **écrans du carburant** (Parc Auto et ADMIN : saisie ; Direction : lecture).

| Écran | Adresse | Ce qu'on y fait |
|---|---|---|
| Liste des pleins | `/carburant/` | filtres (camion, chauffeur, période, type d'alerte, texte), consommation moyenne, nombre de pleins à surveiller |
| **Saisir un plein** | `/carburant/nouveau/` | avec les alertes et la **confirmation d'une saisie suspecte** |
| **Analyse** | `/carburant/analyse/` | consommation par camion et par chauffeur |

## Prérequis

- Chapitres 1 à 23 terminés.

## Ce que ce chapitre apporte de nouveau

- **Le dialogue de confirmation d'un service** : `services.enregistrer_plein` lève `SaisieSuspecte` (chapitre 12).
  La vue l'attrape, **réaffiche le formulaire avec les valeurs saisies** et un avertissement, et propose un
  bouton **« Confirmer »** qui renvoie le même formulaire avec `confirmer_alerte_saisie=True`. Rien n'est
  enregistré tant que la personne n'a pas corrigé ou confirmé.
- **Des messages selon le résultat** : après l'enregistrement, un message *warning* signale une alerte jaune ou
  rouge, une anomalie de consommation.
- **Des nombres à la française** dans les messages : `nombre(...)` et `pourcentage_signe(...)` (chapitre 2), jamais
  un `f"{valeur}"`.
- **Un formulaire de filtre à plusieurs champs**, dont des dates : une période inversée (fin avant début) est
  signalée plutôt qu'ignorée.

## Étape 1 — Formulaires, vues, adresses

{{FICHIER apps/fuel/forms.py}}

{{FICHIER apps/fuel/views.py}}

{{FICHIER apps/fuel/urls.py}}

{{CONFIG}}

## Étape 2 — Gabarits

```bash
mkdir -p apps/fuel/templates/fuel
```

{{FICHIER apps/fuel/templates/fuel/plein_list.html}}

{{FICHIER apps/fuel/templates/fuel/plein_form.html}}

{{FICHIER apps/fuel/templates/fuel/analyse.html}}

## Étape 3 — Tests et compilation des styles

{{RESTANTS}}

`core/tests/test_search.py` vérifie qu'un numéro de page inutilisable ne donne jamais 404 sur **toutes** les
listes : il a donc besoin que les listes existent.

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

**Dans le navigateur (`demo_parcauto`) :**

1. **Carburant → Nouveau plein** : camion `1234 AB 01`, chauffeur `Moussa Ouattara`, une station, **180 litres**,
   prix 700, un compteur (par exemple le kilométrage actuel du camion + 10) et un numéro de ticket. Un premier
   plein n'a **pas de plein précédent** : pas de consommation, aucune alerte.
2. Saisissez un **deuxième plein** : compteur **+ 600 km**, **180 litres** (ticket différent) : consommation
   **30 L/100 km**, mais encore **aucune comparaison** (la moyenne de référence se calcule sur les pleins qui ont
   déjà une consommation).
3. Saisissez un **troisième plein** : compteur **+ 600 km** de plus, **300 litres** (soit 50 L/100 km contre 30) :
   l'écart est de **+66,7 %**. Le formulaire **se réaffiche avec un avertissement de saisie suspecte (au-delà de
   60 %) et un bouton Confirmer**. Rien n'est enregistré. Cliquez **Confirmer** : le plein est enregistré avec une
   **alerte rouge** et une **anomalie** (50 > 45).
4. Le **ticket déjà utilisé** est refusé. Un plein **daté avant** le dernier est refusé (chronologie).
5. Ouvrez **Analyse** : la consommation par camion et par chauffeur apparaît. La **cloche de `demo_direction`**
   compte l'alerte.

## Ce qu'il faut retenir

- Un service peut demander une **confirmation** en levant une exception *sans rien enregistrer* ; la vue
  transforme cela en dialogue.
- Les **messages** affichés à l'utilisateur formatent les nombres à la française.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 24 : écrans du carburant (pleins, confirmation des saisies suspectes, analyse)"
```
