## Ce que vous allez construire

**`fuel`** : les **pleins de carburant** et la **consommation**. Chaque plein est enregistré et sa
consommation est calculée, pour repérer très vite les anomalies : fuite, vol, erreur de saisie, conduite à revoir.

**La formule :** `Consommation (L/100 km) = Litres ÷ (Km actuel − Km du plein précédent) × 100`.

**Les seuils** (l'écart est mesuré par rapport à la moyenne des **3 derniers pleins du camion**) :

| Écart | Réaction |
|---|---|
| supérieur à **+20 %** | alerte **jaune** |
| supérieur à **+40 %** | alerte **rouge** |
| supérieur à **±60 %** | **saisie suspecte** : rien n'est enregistré tant que la personne n'a pas corrigé ou **confirmé** |
| consommation **> 45** ou **< 20** L/100 km | **anomalie** |

Tous les seuils sont **stricts** (« supérieur à », pas « supérieur ou égal »). Les alertes jaune/rouge et la
saisie suspecte sont indépendantes : +65 % est *à la fois* rouge et suspect.

## Prérequis

- Chapitres 1 à 11 terminés.

## Notions Django de ce chapitre

- **Champs calculés figés à la saisie** : la distance, la consommation, la moyenne de référence, l'écart et
  les alertes sont **calculés une fois** par le service et **enregistrés** avec le plein : un plein ancien
  garde l'alerte qu'il avait *à l'époque*, même si la moyenne évolue ensuite.
- **Exception « à confirmer »** : `SaisieSuspecte` est levée **sans rien enregistrer** ; l'appelant renvoie le
  même plein avec `confirmer_alerte_saisie=True`. C'est un moyen propre de demander une confirmation depuis un
  service.
- **Cohérence chronologique** : les pleins d'un camion se saisissent **dans l'ordre** (date non antérieure, km
  strictement croissant).
- **Numéro de ticket unique** : un ticket ne peut pas être saisi deux fois.
- **`Decimal.quantize`** avec `ROUND_HALF_UP` pour arrondir au centième.
- **Relever le compteur du camion** : `fuel` appelle `fleet.enregistrer_kilometrage`.
- **Signal `alerte_consommation`** : émis quand il y a quelque chose à signaler (`notifications` prévient
  le Parc Auto et la Direction).

## Étape 1 — Créer l'application

```bash
mkdir -p apps/fuel/tests
```

{{VIDES}}

## Étape 2 — Modèle et règles

{{FICHIER apps/fuel/models.py}}

{{FICHIER apps/fuel/exceptions.py}}

{{FICHIER apps/fuel/services.py}}

Lisez les fonctions dans cet ordre, elles se lisent comme la spécification :

1. **`calculer_consommation`** : la formule, arrondie au centième.
2. **`moyenne_reference`** : moyenne des consommations des 3 derniers pleins (moins s'il y en a moins ;
   `None` s'il n'y en a aucun).
3. **`evaluer_ecart`** : renvoie `(écart en %, niveau d'alerte, saisie suspecte ?)`.
4. **`est_anomalie`** : consommation hors de la plage plausible 20-45.
5. **`enregistrer_plein`** : orchestre tout : contrôles de saisie, chronologie, calculs, saisie suspecte,
   enregistrement, relevé du compteur, signal.
6. **Lectures** : `consommation_moyenne` (globale, par camion, par chauffeur, pondérée par la distance),
   `pleins_a_surveiller`, `cout_carburant` (pour les indicateurs financiers).

{{FICHIER apps/fuel/signals.py}}

{{FICHIER apps/fuel/permissions.py}}

Le CDC réserve la saisie au **chauffeur** (depuis son téléphone, chapitre 27). Côté bureau, le **Parc Auto** et
l'**ADMIN** saisissent à partir des tickets ; la **DIRECTION** consulte.

## Étape 3 — Administration, démarrage, tests

{{FICHIER apps/fuel/admin.py}}

{{FICHIER apps/fuel/apps.py}}

{{FICHIER apps/fuel/tests/factories.py}}

{{RESTANTS}}

## Étape 4 — Déclarer l'application et migrer

{{CONFIG}}

```bash
python manage.py makemigrations fuel
python manage.py migrate
```

**Résultat attendu :** `Create model Plein`, puis `Applying fuel.0001_initial... OK`.

## Vérifier le chapitre

```bash
python manage.py check
```

{{PYTEST}}

Essais dans le shell : les seuils.

```bash
python manage.py shell -c "from decimal import Decimal; from apps.fuel import services as s; c = s.calculer_consommation(Decimal('180'), 600); print(c); print(s.evaluer_ecart(Decimal('42'), Decimal('30'))); print(s.est_anomalie(Decimal('46')), s.est_anomalie(Decimal('45')))"
```

**Résultat attendu :** `30.00`, puis `(Decimal('40.00'), NiveauAlerte.JAUNE, False)` (l'écart est exactement +40 % : le seuil
rouge est **strict**, donc jaune seulement), puis `True False` (45 n'est **pas** une anomalie).

## Ce qu'il faut retenir

- Quand une règle demande une **confirmation**, une **exception qui n'enregistre rien** est plus sûre qu'un
  booléen oublié.
- **Figer** un résultat calculé au moment où il a un sens évite de le voir changer rétroactivement.
- Les seuils sont des **constantes nommées** en tête du module (`SEUIL_JAUNE`…) : faciles à lire et à ajuster.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 12 : app fuel (pleins, consommation, alertes de surconsommation)"
```
