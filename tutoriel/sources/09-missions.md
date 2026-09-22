## Ce que vous allez construire

**`missions`** : le **cœur de l'ERP**. Une mission est un transport confié par un client : où charger, où
livrer, quelle marchandise, quel poids, à quel prix. Elle suit un **cycle de vie** strict :

```text
Brouillon → Planifiée → Affectée → En cours (départ → colis récupéré) → Livrée → Clôturée
```

| Étape | Ce que le système vérifie ou fait |
|---|---|
| **Créer** | numéro `MIS-<année>-0001`, **deux codes secrets** de 8 caractères (expéditeur et destinataire) |
| **Affecter** | le camion et le chauffeur sont **disponibles**, **non réservés** par une autre mission, et la **capacité** du camion suffit pour le poids |
| **Démarrer** | le camion et le chauffeur passent « En mission » ; le kilométrage de départ est relevé |
| **Confirmer la récupération** | il faut le **code de l'expéditeur** |
| **Livrer** | il faut le **code du destinataire** et le kilométrage d'arrivée (le compteur du camion est mis à jour ; camion et chauffeur sont libérés) |
| **Clôturer** | validation finale (la Direction) |

## Prérequis

- Chapitres 1 à 8 terminés.

## Notions Django de ce chapitre

- **Machine à états complète** : chaque transition est une fonction qui vérifie le statut de départ
  (`_exiger_statut`) et lève `TransitionMissionInterdite` sinon.
- **Verrou de ligne** (`select_for_update`) dans `_recharger` : deux personnes ne peuvent pas agir en même
  temps sur la même mission.
- **Le module `secrets`** (et non `random`) pour générer les codes : c'est le générateur prévu pour les
  secrets. **`secrets.compare_digest`** compare deux chaînes en **temps constant**, pour ne pas révéler par
  le temps de réponse combien de caractères sont justes.
- **Contrainte multi-condition** : une mission **Affectée** exige un camion **et** un chauffeur (contrainte
  `mission_affectee_requiert_camion_et_chauffeur`).
- **Signal émis avec `send_robust`** : `mission_demarree` prévient `notifications` sans dépendre d'elle.
- **Composition de services** : `demarrer_mission` appelle les services de `fleet` et `drivers` (dépendances
  descendantes autorisées).
- **Agrégation** (`Count`, `Sum`) pour les statistiques (meilleurs clients).

## Étape 1 — Créer l'application

```bash
mkdir -p apps/missions/tests
```

{{VIDES}}

## Étape 2 — Le modèle

{{FICHIER apps/missions/models.py}}

Points clés :

- **`StatutMission`** : les 7 statuts (« En cours » se décompose en *départ* puis *colis récupéré*).
- **`STATUTS_ACTIFS`** : les statuts pendant lesquels le camion et le chauffeur sont **réservés**.
- Le **prix convenu** est un `DecimalField` ; les **codes** sont stockés en clair *mais exclus du journal
  d'audit* (voir `apps.py`).
- Trois contraintes en base : poids positif, prix positif ou nul, camion et chauffeur obligatoires dès
  « Affectée ».

## Étape 3 — Exceptions et règles métier

{{FICHIER apps/missions/exceptions.py}}

{{FICHIER apps/missions/services.py}}

C'est le fichier à lire **le plus attentivement** de tout le projet. Une fonction par transition :

1. **`creer_mission`** : contrôle poids et prix, génère deux codes différents, attribue le numéro avec
   `prochain_numero` (chapitre 2).
2. **`planifier_mission`** : Brouillon → Planifiée.
3. **`affecter_mission`** : la fonction que vous avez peut-être déjà croisée. Elle recharge la mission, le
   camion et le chauffeur sous verrou, puis enchaîne les contrôles : statut « Disponible », non réservé,
   capacité suffisante.
4. **`demarrer_mission`** : camion et chauffeur passent « En mission » (via `fleet` et `drivers`), le
   kilométrage de départ est relevé, `mission_demarree` est émis.
5. **`confirmer_recuperation`** : compare le code saisi à celui de l'expéditeur avec `_verifier_code`.
6. **`livrer_mission`** : compare le code du destinataire, vérifie le kilométrage d'arrivée (jamais
   inférieur au départ ni au compteur), met à jour le compteur du camion, libère camion et chauffeur.
7. **`cloturer_mission`** : Livrée → Clôturée.
8. Les *lectures* : `rechercher_missions`, `missions_du_personnel_sur_periode` (pour l'alerte de congé de
   `hr`), `vehicule_a_mission_active` et `chauffeur_a_mission_active` (fournis à `fleet` et `drivers`),
   `meilleurs_clients`, `clients_actifs`.

{{FICHIER apps/missions/signals.py}}

{{FICHIER apps/missions/permissions.py}}

Remarquez `actions_disponibles(utilisateur, mission)` : elle indique à l'interface **quelles actions afficher**
selon le rôle *et* le statut. Et `codes_visibles` : un code n'est montré que tant qu'il sert (celui de
l'expéditeur jusqu'à la récupération, celui du destinataire jusqu'à la livraison), et **jamais** au
chauffeur.

{{FICHIER apps/missions/sections.py}}

Ce fichier **ajoute des blocs à d'autres apps** : l'alerte « ce chauffeur a une mission prévue » sur la fiche
d'un congé (`hr`), et la liste des missions sur la fiche d'un client (`customers`). C'est le registre du
chapitre 2 en action.

## Étape 4 — Administration, démarrage, tests

{{FICHIER apps/missions/admin.py}}

{{FICHIER apps/missions/apps.py}}

Ici `ready()` fait quatre choses : branche l'**audit** sur `Mission` en excluant les codes, enregistre les deux
sections, et déclare l'entrée de menu « Missions ».

{{FICHIER apps/missions/tests/factories.py}}

{{RESTANTS}}

## Étape 5 — Déclarer l'application et migrer

{{CONFIG}}

```bash
python manage.py makemigrations missions
python manage.py migrate
```

**Résultat attendu :** `Create model Mission`, les contraintes, puis `Applying missions.0001_initial... OK`.

## Vérifier le chapitre

```bash
python manage.py check
```

{{PYTEST}}

Essais dans le shell (avec le client `Cimaf CI` créé au chapitre 7) :

```bash
python manage.py shell -c "from apps.missions.services import generer_code; print(len(generer_code()))"
python manage.py shell -c "from decimal import Decimal; from apps.customers.models import Client; from apps.missions import services as s; m = s.creer_mission(client=Client.objects.get(ncc_nif='CI-0001'), lieu_chargement='Abidjan', lieu_livraison='Bouaké', nature_marchandise='Ciment', poids_t=Decimal('22'), prix_convenu=Decimal('780000')); print(m.numero.startswith('MIS-'), m.statut, len(m.code_expediteur), m.code_expediteur != m.code_destinataire)"
```

**Résultat attendu :** `8`, puis `True BROUILLON 8 True`.

Vérifiez enfin que **le journal d'audit n'a pas gardé les codes** :

```bash
python manage.py shell -c "from apps.audit.models import AuditLog; l = AuditLog.objects.filter(entite='Mission').first(); print(l.action, 'code_expediteur' in l.nouvelle_valeur)"
```

**Résultat attendu :** `CREATE False`.

## Ce qu'il faut retenir

- Un **workflow** se code comme une suite de fonctions, chacune gardée par une vérification de statut.
- Les **secrets** se génèrent avec `secrets` et se comparent avec `compare_digest`.
- Ce qui est **réservé** (camion, chauffeur) se **verrouille** pendant l'opération.
- On peut **exclure des champs** du journal d'audit : le journal ne doit jamais contenir de secret.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 9 : app missions (cycle de vie, codes de confirmation, affectation contrôlée)"
```
