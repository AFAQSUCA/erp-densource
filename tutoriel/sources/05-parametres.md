## Ce que vous allez construire

**`parametres`** : les **réglages de l'application modifiables à l'écran**, sans toucher au code. Le cahier des charges
confie à l'ADMIN « config, seuils d'alerte » ; l'entreprise a décidé que la DIRECTION les modifie aussi
(`avenant-parametres.md`).

| Élément | Règle |
|---|---|
| `Parametres` | **une seule ligne** (`pk = 1`, garantie par une contrainte en base) de 12 valeurs |
| **Valeurs par défaut** | celles du cahier des charges : alerte à 30 jours, seuils carburant 20 / 40 / ± 60 %, plage plausible 20-45 L/100 km, TVA 18 %, délai de paiement 30 jours, congés N1 48 h / N2 24 h, droit annuel 26 jours ouvrés |
| **Lecture** | toujours `services.parametres()`, jamais une constante ; **rien n'est écrit en base** tant que personne n'a enregistré l'écran |
| **Modification** | ADMIN et DIRECTION ; bornes de chaque champ, puis cohérence (jaune < rouge < saisie suspecte, consommation minimale < maximale) ; **tout est vérifié avant d'écrire** |
| **Traçabilité** | chaque modification va au journal d'audit du chapitre 4 (ancienne et nouvelle valeur) |

Pourquoi si tôt ? Parce que presque toutes les apps suivantes **lisent** ces réglages : les congés (`hr`, chapitre 6),
les échéances des chauffeurs et des camions, les seuils du carburant, la TVA proposée aux nouveaux clients. Une app
ne peut lire que ce qui existe déjà : `parametres` passe donc avant elles. Son **écran** viendra avec le socle de
l'interface, au chapitre 18.

## Prérequis

- Chapitres 1 à 4 terminés.

## Notions Django de ce chapitre

- **Une table d'une seule ligne** (*singleton*) : `CheckConstraint(condition=Q(pk=1))` interdit toute autre ligne,
  même en contournant le code.
- **Lire sans écrire** : `Parametres.objects.filter(pk=1).first() or Parametres(pk=1)` renvoie un objet **non
  enregistré** portant les valeurs par défaut des champs. Tant que l'écran n'a jamais servi, la table reste vide.
- **Validateurs de champ** (`MinValueValidator`, `MaxValueValidator`) et **`full_clean()`** : Django vérifie les
  bornes de chaque champ avant l'enregistrement ; le service y ajoute les règles **entre** champs.
- **Une erreur qui porte plusieurs messages** : `ParametresInvalides` garde un dictionnaire « champ → messages »,
  que l'écran affichera sous chaque champ.
- **`select_for_update()`** : deux personnes qui enregistrent l'écran en même temps ne s'écrasent pas.

## Étape 1 — Créer l'application

```bash
mkdir -p apps/parametres/tests
```

{{VIDES}}

## Étape 2 — Le modèle et ses valeurs par défaut

{{FICHIER apps/parametres/README.md}}

{{FICHIER apps/parametres/models.py}}

Repérez les constantes `TVA_DEFAUT` et `DELAI_PAIEMENT_DEFAUT` : `customers` (chapitre 8) les réutilisera pour ses
propres valeurs par défaut.

## Étape 3 — Lire et modifier

{{FICHIER apps/parametres/permissions.py}}

{{FICHIER apps/parametres/services.py}}

- **`parametres()`** est la seule porte d'entrée en lecture. Dans une boucle, lisez-la **une fois** et passez la
  valeur, plutôt que de relire la base à chaque tour.
- **`delai_alerte(jours=None)`** : un test ou un appel explicite peut imposer son délai, sinon le paramètre
  s'applique.
- **`modifier_parametres`** refuse un champ inconnu, vérifie les bornes (`full_clean`) puis la cohérence ; rien
  n'est écrit si une seule règle est fausse.

## Étape 4 — Démarrage : audit et menu

{{FICHIER apps/parametres/apps.py}}

`ready()` branche le journal d'audit (chapitre 4) et inscrit l'entrée « Paramètres » dans le menu (chapitre 3) :
l'entrée n'apparaîtra qu'aux rôles de `permissions.MODIFICATION`.

{{RESTANTS}}

## Étape 5 — Déclarer l'application et migrer

{{CONFIG}}

```bash
python manage.py makemigrations parametres
python manage.py migrate
```

**Résultat attendu :** `Create model Parametres`, puis `Applying parametres.0001_initial... OK`.

## Vérifier le chapitre

Les tests de `parametres` ouvrent son écran : ils sont présentés au chapitre 18. Vérifiez à la main que les valeurs
du cahier des charges s'appliquent **sans rien écrire** :

```bash
python manage.py shell -c "from apps.parametres.models import Parametres; from apps.parametres.services import parametres; p = parametres(); print(p.delai_alerte_jours, p.droit_annuel_jours, p.tva_defaut, Parametres.objects.count())"
```

**Résultat attendu :** `30 26 18.00 0` (les valeurs par défaut, et toujours aucune ligne en base).

Puis qu'une incohérence est refusée avant toute écriture :

```bash
python manage.py shell -c "from apps.accounts.models import User; from apps.parametres import services as s; d = User.objects.create_user(username='direction-essai', password='Mot-de-passe-1', role='DIRECTION'); s.modifier_parametres(d, seuil_conso_rouge_pct=10)"
```

**Résultat attendu :** une erreur `ParametresInvalides: Le seuil de l'alerte rouge doit être supérieur à celui de
l'alerte jaune.`

## Ce qu'il faut retenir

- Un réglage qui peut changer ne s'écrit pas en constante : il se **lit** au moment où il sert.
- Les valeurs par défaut vivent dans le modèle : l'application se comporte comme le cahier des charges tant que
  personne n'a rien modifié.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 5 : app parametres (réglages modifiables, valeurs du cahier des charges par défaut)"
```
