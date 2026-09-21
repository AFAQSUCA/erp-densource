# Parcours d'apprentissage du projet : de Python à ce code, pas à pas

Ce guide est fait pour quelqu'un qui **connaît Python** (fonctions, classes, modules, exceptions,
décorateurs) mais **n'a jamais utilisé Django**. Il vous dit **dans quel ordre lire le code**, **quelles
notions apprendre juste avant d'en avoir besoin**, et **quoi faire de vos mains** pour vérifier que vous
avez compris. Tous les extraits sont réels (`fichier:ligne` ou nom de fonction pour les retrouver).

Deux autres documents complètent celui-ci :

| Document | À quoi il sert |
|---|---|
| [GUIDE-INTERFACE.md](GUIDE-INTERFACE.md) | Le trajet d'un clic : URL → vue → formulaire → service → gabarit. **À lire à l'étape 5.** |
| [glossaire-metier.md](glossaire-metier.md) | Le vocabulaire du transport (OR, PUMP, N1/N2…). À garder ouvert. |

Un rythme réaliste : **une étape par séance de 1 à 2 heures**. Ne cherchez pas à tout lire d'un coup : ce
projet fait environ 14 000 lignes de code (hors tests) et environ 1 800 tests.

---

## Sommaire

0. [Avant de commencer : la méthode](#0-avant-de-commencer--la-méthode)
1. [Faire tourner le projet](#1-faire-tourner-le-projet)
2. [Les notions Django, dans l'ordre où on en a besoin](#2-les-notions-django-dans-lordre-où-on-en-a-besoin)
3. [Les idées propres à ce projet](#3-les-idées-propres-à-ce-projet)
4. [Le parcours de lecture, étape par étape](#4-le-parcours-de-lecture-étape-par-étape)
5. [Dix exercices](#5-dix-exercices)
6. [Outils pour comprendre et déboguer](#6-outils-pour-comprendre-et-déboguer)
7. [Pièges de lecture](#7-pièges-de-lecture)
8. [Petit lexique Django](#8-petit-lexique-django)

---

## 0. Avant de commencer : la méthode

**Ne lisez jamais un fichier sans savoir ce que vous cherchez.** Pour chaque module, posez-vous ces
six questions dans cet ordre, elles suffisent à comprendre 90 % du code :

1. **Quelles données ?** → `models.py` (les tables de la base).
2. **Quelles règles ?** → `services.py` (ce qui est permis, interdit, calculé).
3. **Comment vérifie-t-on ces règles ?** → `tests/test_services.py` (les tests sont la meilleure
   documentation : ils montrent chaque règle avec un exemple).
4. **Qui a le droit ?** → `permissions.py`.
5. **Comment l'utilisateur y accède ?** → `urls.py`, `views.py`, `templates/`.
6. **Qui est prévenu, qu'est-ce qui est tracé ?** → `signals.py`, `apps.py`, `notifications/receivers.py`.

**Lisez les tests avant le code quand une fonction vous échappe.** Un test comme celui-ci se lit comme
une phrase :

```python
# apps/fleet/tests/test_services.py
def test_regle_1_or_ouvert_donne_en_maintenance():
    statut = services.calculer_statut(
        StatutVehicule.DISPONIBLE, or_ouverts=True, mission_active=False
    )

    assert statut == StatutVehicule.EN_MAINTENANCE
```

« Si un ordre de réparation est ouvert, le camion est en maintenance. » Vous venez de comprendre une règle
métier sans lire le service.

**Trois habitudes qui accélèrent tout :**

- ouvrez le projet dans **VS Code** et utilisez *Aller à la définition* (F12) et *Trouver toutes les
  références* (Maj+F12) : c'est plus rapide que de chercher à la main ;
- ayez **deux terminaux** : un pour `runserver`, un pour `pytest` et `manage.py shell` ;
- **cassez volontairement** le code (voir exercice 8) pour voir quel test échoue : c'est ainsi qu'on
  comprend à quoi sert une ligne.

---

## 1. Faire tourner le projet

Depuis le dossier du projet (Git Bash ou PowerShell) :

```bash
python -m venv .venv                       # environnement virtuel : les bibliothèques du projet, isolées
.venv/Scripts/pip install -r requirements/dev.txt      # Git Bash
# PowerShell : .\.venv\Scripts\pip install -r requirements/dev.txt
cp .env.example .env                       # réglages locaux (jamais commités)
.venv/Scripts/python manage.py migrate     # crée les tables dans db.sqlite3
.venv/Scripts/python manage.py creer_comptes_demo    # 7 comptes d'essai (un par rôle)
.venv/Scripts/python manage.py runserver   # puis http://localhost:8000
```

> `manage.py` est la « télécommande » du projet : chaque commande Django passe par lui. Il choisit les
> réglages de développement (`config/settings/dev.py`) tout seul.

Deux choses à essayer **avant de lire une seule ligne** :

1. Connectez-vous avec `demo_charge` (le mot de passe est affiché par la commande, ou dans
   `COMPTES-ESSAI.md` si vous l'avez). Créez une mission, planifiez-la.
2. Reconnectez-vous avec `demo_direction` : affectez un camion et un chauffeur, puis démarrez la mission.
   Notez ce que vous avez dû faire. **Tout le code que vous allez lire sert à faire marcher ces deux minutes.**

Les comptes ADMIN et DIRECTION demandent une double authentification à la première connexion : installez
une application d'authentification sur votre téléphone (Google Authenticator, Microsoft
Authenticator…). En cas de problème : `python manage.py reinitialiser_mfa demo_direction`.

Lancer les tests (à faire maintenant, pour voir que tout est vert) :

```bash
.venv/Scripts/python -m pytest -q              # tous les tests (~1 minute)
.venv/Scripts/python -m pytest apps/fleet -q   # seulement un module
```

---

## 2. Les notions Django, dans l'ordre où on en a besoin

Chaque notion est illustrée avec un vrai fichier du projet. Lisez la notion, puis ouvrez le fichier.

### 2.1 Projet et applications

Un **projet Django** est le tout ; il est découpé en **applications** (« apps »), chacune responsable d'un
domaine. Ici :

```
config/            ← le projet : réglages (settings/), adresses (urls.py)
apps/
    core/          ← le socle commun
    accounts/      ← utilisateurs, rôles, connexion, double authentification
    fleet/         ← les camions
    missions/      ← les missions de transport
    ...            ← 17 apps en tout, une par domaine métier
```

Une app est un dossier Python avec des fichiers aux rôles conventionnels : `models.py`, `views.py`,
`urls.py`, `admin.py`, `apps.py`, `tests/`. Pour que Django la connaisse, on la liste dans
`INSTALLED_APPS` (`config/settings/base.py`, listes `DJANGO_APPS`, `THIRD_PARTY_APPS`, `LOCAL_APPS`).

Le fichier `apps.py` de chaque app est le point d'entrée : sa méthode `ready()` s'exécute **une fois au
démarrage**. Ce projet s'en sert pour brancher l'app sur le reste (menu, audit, signaux) :

```python
# apps/fleet/apps.py
class FleetConfig(AppConfig):
    name = 'apps.fleet'
    label = 'fleet'

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.audit.registry import audit_model
        from . import permissions
        from .models import DocumentReglementaire, Vehicule

        audit_model(Vehicule, module="PARC_AUTO")          # « trace tout ce qui arrive à un Vehicule »
        enregistrer(EntreeMenu("Flotte", "fleet:liste", "fa-truck", permissions.CONSULTATION, ordre=20))
```

*Ce que vous devez retenir :* `ready()` = « au démarrage, cette app s'inscrit auprès des autres ».

### 2.2 Modèles : les tables de la base de données

Un **modèle** est une classe Python qui décrit une table. Chaque attribut de classe est une colonne.
Django écrit le SQL à votre place (l'**ORM**).

```python
# apps/fleet/models.py (extrait)
class StatutVehicule(models.TextChoices):
    DISPONIBLE = "DISPONIBLE", _("Disponible")     # valeur en base, libellé affiché
    EN_MISSION = "EN_MISSION", _("En mission")
    ...

class Vehicule(BaseModel):
    immatriculation = models.CharField(_("immatriculation"), max_length=20, unique=True)
    kilometrage = models.PositiveIntegerField(_("kilométrage compteur"), default=0)
    capacite_charge_t = models.DecimalField(_("capacité de charge (t)"), max_digits=6, decimal_places=2)
    chauffeur_habituel = models.ForeignKey(
        "drivers.Chauffeur", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="vehicules_habituels",
    )
    statut = models.CharField(max_length=15, choices=StatutVehicule.choices, default=StatutVehicule.DISPONIBLE)

    class Meta:
        ordering = ["immatriculation"]
        indexes = [models.Index(fields=["statut"])]

    def __str__(self):
        return f"{self.immatriculation} ({self.marque} {self.modele})"
```

À décoder, ligne par ligne :

| Vous voyez | Ça veut dire |
|---|---|
| `CharField(max_length=20, unique=True)` | texte de 20 caractères maximum, **deux camions ne peuvent pas avoir la même plaque** (contrainte en base) |
| `DecimalField` | nombre décimal **exact** (jamais `float` pour de l'argent ou des tonnes) |
| `ForeignKey("drivers.Chauffeur", ...)` | un camion « appartient » à un chauffeur : une colonne qui pointe vers l'autre table |
| `on_delete=SET_NULL` | si le chauffeur disparaît, la colonne est mise à vide ; `PROTECT` refuse la suppression |
| `related_name="vehicules_habituels"` | permet de faire `chauffeur.vehicules_habituels.all()` dans l'autre sens |
| `null=True, blank=True` | `null` : vide autorisé **en base** ; `blank` : vide autorisé **dans un formulaire** |
| `TextChoices` | une liste de valeurs permises (une `Enum` Django) |
| `_("…")` | marque le texte comme traduisible (le projet est en français) |
| `class Meta` | réglages du modèle : tri par défaut, index, contraintes |
| `__str__` | comment l'objet s'affiche (dans l'admin, dans `print`) |

**L'héritage `BaseModel`** (`apps/core/models.py`) est la clé de tout le projet : tous les modèles métier
en héritent et reçoivent gratuitement `created_at`, `updated_at` et la **suppression logique** (« soft
delete ») :

```python
class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)   # posé à la création
    updated_at = models.DateTimeField(auto_now=True)       # mis à jour à chaque save()
    is_deleted = models.BooleanField(default=False)
    ...
    objects = ActiveManager()          # ne renvoie QUE les enregistrements non supprimés
    all_objects = models.Manager()     # renvoie tout, supprimés compris

    class Meta:
        abstract = True                # pas de table pour BaseModel lui-même

    def delete(self, ...):             # « supprimer » = marquer is_deleted=True, jamais un vrai DELETE
        self.is_deleted = True
        ...
```

*Conséquence à garder en tête :* `Vehicule.objects.all()` **ne montre pas** les camions supprimés. C'est
voulu. Les contraintes d'unicité tiennent compte de ce drapeau (`condition=Q(is_deleted=False)`, voir
`DocumentReglementaire.Meta.constraints`).

**Exercice de lecture :** ouvrez `apps/missions/models.py`. Trouvez : (a) la liste des statuts d'une
mission, (b) la colonne qui relie une mission à son client, (c) ce qui empêche de mettre un poids négatif
(cherchez `constraints`).

### 2.3 Migrations : garder la base au même niveau que les modèles

Quand vous changez un modèle, la base ne suit pas toute seule. Deux commandes :

```bash
python manage.py makemigrations   # compare vos modèles à l'état précédent, écrit un fichier de migration
python manage.py migrate          # applique les migrations à la base
```

Les fichiers générés sont dans `apps/<app>/migrations/` (par exemple `apps/fleet/migrations/0001_initial.py`,
que vous pouvez ouvrir : c'est du Python lisible, `CreateModel(name='Vehicule', fields=[...])`).
**On ne les modifie pas à la main** et on les **commit** avec le code. `python manage.py showmigrations`
liste ce qui est appliqué ; `python manage.py sqlmigrate fleet 0001` affiche le SQL qui serait exécuté.

### 2.4 L'ORM : interroger la base en Python

C'est ce que vous ferez le plus. Ouvrez le *shell* du projet, il importe déjà les modèles :

```bash
python manage.py shell
```

```python
>>> from apps.fleet.models import Vehicule
>>> Vehicule.objects.count()                                # combien ?
>>> Vehicule.objects.filter(statut="DISPONIBLE")            # WHERE statut = 'DISPONIBLE'
>>> Vehicule.objects.filter(kilometrage__gt=100000)         # __gt : « supérieur à »
>>> camion = Vehicule.objects.get(immatriculation="1234 AB 01")   # exactement un, sinon exception
>>> camion.chauffeur_habituel                               # suit la clé étrangère
>>> str(Vehicule.objects.filter(statut="DISPONIBLE").query) # le SQL généré !
```

Notions à connaître (vous les croiserez tout le temps) :

- **QuerySet** : le résultat de `filter(...)` est *paresseux* : la requête SQL ne part qu'au moment où on
  lit les résultats (boucle `for`, `list()`, `.count()`, `.first()`).
- **`select_related("client")`** : récupère aussi le client dans la même requête (évite « N+1 requêtes »).
- **`F("champ")`** : désigne une colonne dans une comparaison (`date_expiration__gte=F("date_delivrance")`).
- **`Q(...)`** : conditions combinées avec `|` (ou) et `&` (et).
- **`aggregate` / `annotate`** : totaux et calculs (`Sum`, `Count`, `Avg`) : voir `apps/finance/services.py`.

### 2.5 L'administration Django

Django génère gratuitement une interface d'administration (`/admin/`) à partir des modèles. Il suffit de
les déclarer :

```python
# apps/fleet/admin.py
@admin.register(Vehicule)
class VehiculeAdmin(admin.ModelAdmin):
    list_display = ("immatriculation", "marque", "modele", "statut", "kilometrage")
    list_filter = ("statut", "marque")
    search_fields = ("immatriculation", "vin")
```

C'est pratique pour **regarder les données** pendant que vous apprenez. (Seul un compte ADMIN y accède ;
l'interface que les utilisateurs voient est celle de l'étape 5, écrite à la main.)

### 2.6 URLs, vues, gabarits, formulaires

Ces quatre notions ont leur propre guide : **[GUIDE-INTERFACE.md](GUIDE-INTERFACE.md)**, parties 2 à 4. En
une phrase chacune :

- **URL** (`urls.py`) : associe une adresse à une vue. `path("<int:pk>/", views.VehiculeDetailView.as_view())`
  signifie « `/flotte/12/` appelle cette vue avec `pk=12` ».
- **Vue** (`views.py`) : reçoit la requête, appelle un service, renvoie une page. Ici ce sont des **classes**
  (`ListView`, `FormView`…) plutôt que des fonctions.
- **Gabarit** (`templates/…html`) : du HTML avec `{{ variable }}` et `{% instruction %}`.
- **Formulaire** (`forms.py`) : lit et **valide** ce que l'utilisateur a saisi.

### 2.7 Les signaux : « quelque chose vient d'arriver »

Un **signal** est un mégaphone : un module *annonce* un événement, d'autres modules qui l'écoutent
réagissent, sans que l'émetteur les connaisse.

```python
# apps/missions/signals.py — l'annonce
mission_demarree = Signal()

# apps/missions/services.py, dans demarrer_mission (ligne ~300) — l'émetteur
for recepteur, resultat in mission_demarree.send_robust(sender=Mission, mission=mission):
    ...   # ne regarde que les erreurs éventuelles des auditeurs

# apps/notifications/receivers.py (ligne ~186) — l'écoute
@receiver(mission_demarree)
def prevenir_du_depart(sender, mission, **kwargs):
    client = mission.client
    ...   # crée une notification pour le chargé de clientèle
```

`@receiver(...)` est un **décorateur** : il branche la fonction sur le signal. `send_robust` garantit
qu'une erreur chez un auditeur n'empêche pas la mission de démarrer. Django a aussi ses propres signaux
(`post_save` : « un enregistrement vient d'être sauvegardé ») : `apps/audit/registry.py` s'en sert pour
tracer automatiquement les modifications.

### 2.8 Les middlewares : du code qui voit toutes les requêtes

Un **middleware** est une classe exécutée **avant et après chaque vue**, pour toute requête. La liste est
dans `MIDDLEWARE` (`config/settings/base.py`). Le projet en a quelques-uns à lui :

- `apps/core/middleware.py` : `CurrentRequestMiddleware` (mémorise la requête courante pour l'audit) et
  `SecurityHeadersMiddleware` (ajoute la politique de sécurité du contenu) ;
- `apps/accounts/middleware.py` : `MFARequiseMiddleware` (refuse tout tant que la double authentification
  n'est pas passée).

Forme type :

```python
class MonMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    def __call__(self, request):
        # ... avant la vue ...
        reponse = self.get_response(request)      # la vue s'exécute ici
        # ... après la vue ...
        return reponse
```

### 2.9 Les tests : `pytest` et les « factories »

Les tests sont dans `apps/<app>/tests/`. Le projet utilise **pytest** (plus simple que `unittest` : de
simples fonctions `test_…` et des `assert`) et **factory_boy** pour fabriquer des objets de test :

```python
# apps/fleet/tests/factories.py
class VehiculeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Vehicule
    immatriculation = factory.Sequence(lambda n: f"{1000 + n} AB 01")   # une plaque différente à chaque appel
    marque = "Mercedes-Benz"
    ...
```

```python
# un test s'écrit en trois temps : préparer, agir, vérifier
def test_nouveau_vehicule_est_disponible_par_defaut():
    assert VehiculeFactory().statut == StatutVehicule.DISPONIBLE
```

`pytestmark = pytest.mark.django_db` (en haut du fichier) autorise l'accès à la base ; chaque test
travaille dans une base vide, annulée à la fin. Pour tester une page, on utilise le fixture `client`
(un faux navigateur) : `client.force_login(user)` puis `client.get("/flotte/")`.

---

## 3. Les idées propres à ce projet

Ce sont des **choix de conception** du projet, pas du Django standard. Les comprendre vous fait gagner des
jours. Elles sont détaillées dans `conventions.md` et `architecture.md`.

### 3.1 Les règles métier vivent dans `services.py`, jamais dans les vues

La vue **orchestre**, le service **décide**. Exemple : affecter un camion à une mission.

```python
# apps/missions/services.py
@transaction.atomic
def affecter_mission(mission, *, vehicule, chauffeur):
    """Planifiée → Affectée : camion et chauffeur disponibles, non réservés,
    et capable d'emporter la charge."""
    _recharger(mission)
    _exiger_statut(mission, StatutMission.PLANIFIEE, "affecter la mission")
    ...
    if vehicule.statut != StatutVehicule.DISPONIBLE:
        raise AffectationImpossible(f"Le camion {vehicule.immatriculation} n'est pas disponible ...")
    ...
    if mission.poids_t > vehicule.capacite_charge_t:
        raise AffectationImpossible("Charge de ... supérieure à la capacité du camion ...")

    mission.vehicule = vehicule
    mission.chauffeur = chauffeur
    mission.statut = StatutMission.AFFECTEE
    mission.save(update_fields=["vehicule", "chauffeur", "statut", "updated_at"])
    return mission
```

Pourquoi c'est important : l'interface web, l'API REST et l'espace mobile appellent **la même fonction**.
Une règle écrite une fois est vraie partout.

Notations Python à connaître ici : `*` dans la signature = ce qui suit est **obligatoirement nommé**
(`affecter_mission(m, vehicule=v, chauffeur=c)`) ; `@transaction.atomic` = « tout ou rien » : si une exception
survient, **rien** n'est enregistré.

### 3.2 Les erreurs métier sont des exceptions dédiées

`apps/missions/exceptions.py` : `AffectationImpossible`, `TransitionMissionInterdite`, `CodeInvalide`… toutes
héritent de `MissionError`. Le service **lève** l'exception avec un message lisible ; la vue l'**attrape** et
l'affiche à l'utilisateur ; l'API la traduit en code HTTP (400, 403, 404, 409). Vous ne verrez presque jamais
un `ValueError` générique.

### 3.3 Les applications ne se connaissent que dans un sens

`architecture.md:99-163` dessine le graphe des dépendances : `core` ne dépend de rien ; `fleet` dépend de
`core` ; `missions` dépend de `fleet`… **jamais l'inverse**. Comment fait-on quand `fleet` a besoin d'une
information de `missions` (« ce camion a-t-il une mission active ? ») sans l'importer ? Par **inversion** :

```python
# apps/fleet/services.py — fonction PURE : elle reçoit les faits en paramètre
def calculer_statut(statut_actuel, *, or_ouverts: bool, mission_active: bool) -> str:
    if or_ouverts:
        return StatutVehicule.EN_MAINTENANCE
    if mission_active:
        return StatutVehicule.EN_MISSION
    if statut_actuel in (StatutVehicule.IMMOBILISE, StatutVehicule.HORS_SERVICE):
        return statut_actuel
    return StatutVehicule.DISPONIBLE
```

C'est l'appelant (`missions` ou `garage`) qui calcule `mission_active` et le passe. Une **fonction pure**
(mêmes entrées → même sortie, pas d'accès à la base) est facile à tester : voir les tests cités au début.

### 3.4 Les registres : s'inscrire au lieu d'être importé

Le même besoin (« afficher quelque chose sans dépendre de qui le fournit ») est résolu par des **registres** :

| Registre | Fichier | Ce que chaque app y enregistre |
|---|---|---|
| Menu | `apps/accounts/navigation.py` | ses entrées de menu (`EntreeMenu`, avec les rôles autorisés) |
| Audit | `apps/audit/registry.py` | les modèles à tracer (`audit_model(Vehicule, module="PARC_AUTO")`) |
| Sections | `apps/core/sections.py` | des blocs d'affichage à ajouter à la fiche d'un camion, d'un OR, d'un client |

`EntreeMenu` est une `dataclass(frozen=True)` : un objet simple, non modifiable, écrit en 6 lignes.

### 3.5 Verrous et transactions

Deux utilisateurs peuvent cliquer en même temps. Le projet protège les opérations sensibles :
`@transaction.atomic` et `select_for_update()` (verrouille la ligne pendant l'opération). Voir
`_recharger` dans `apps/missions/services.py` et `prochain_numero` dans `apps/core/services.py`, qui
distribue les numéros `MIS-2026-0001`, `FACT-2026-0001`… sans jamais donner deux fois le même.
*(Le verrou est réellement effectif sous PostgreSQL ; SQLite, utilisé en développement, l'ignore.)*

### 3.6 Les rôles et la garde d'accès

7 rôles (`apps/accounts/models.py`, `Role`). Chaque app définit dans `permissions.py` qui a le droit de quoi :

```python
# apps/fleet/permissions.py
CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.PARCAUTO})
MODIFICATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.PARCAUTO})
```

Et la vue applique la garde (`apps/accounts/mixins.py`) :

```python
class VehiculeListView(PaginationTolerante, RoleRequiredMixin, ListView):   # apps/fleet/views.py:21
    roles = permissions.CONSULTATION        # ← seuls ces rôles passent, sinon erreur 403
```

Masquer un bouton dans le HTML ne protège **rien** : c'est cette garde, côté serveur, qui protège.

### 3.7 Tout ce qui compte est tracé

`audit_model(...)` (dans `apps.py`) fait que chaque création, modification ou suppression d'un modèle écrit
une ligne dans `audit_log`, avec les valeurs avant et après. Ce journal ne peut ni être modifié ni effacé
(`apps/audit/models.py`). Les champs secrets (codes de mission) en sont exclus.

---

## 4. Le parcours de lecture, étape par étape

On lit dans l'ordre des dépendances : **du plus simple et plus bas vers le plus haut**. Pour chaque étape :
le temps, ce qu'il faut lire, ce qu'il faut retenir, et une vérification.

### Étape 1 — Le socle : `core` (≈ 1 h)

| Lire | Pour comprendre |
|---|---|
| `apps/core/models.py` | `BaseModel`, le soft delete, `CompteurNumero` |
| `apps/core/services.py` | `prochain_numero`, `etat_echeance` (alerte à 30 jours) |
| `apps/core/constants.py`, `apps/core/formats.py` | constantes et affichage des nombres à la française |
| `apps/core/tests/test_numerotation.py` | comment un test prouve « jamais deux fois le même numéro » |

*Vérification :* dans `manage.py shell`, appelez `prochain_numero("TEST")` trois fois et regardez les
résultats. Puis cherchez (`Ctrl+Maj+F`) tous les endroits où cette fonction est appelée.

### Étape 2 — Utilisateurs et rôles : `accounts` (≈ 1 h 30)

| Lire | Pour comprendre |
|---|---|
| `apps/accounts/models.py` | `Role`, `User` (un modèle utilisateur **personnalisé**) |
| `apps/accounts/mixins.py` | `RoleRequiredMixin` : la garde de toutes les vues |
| `apps/accounts/navigation.py` | le registre du menu |
| `apps/accounts/tests/test_web.py` | connexion, menu par rôle, accès refusé |

À retenir : `role_effectif` (un « superutilisateur » agit comme un ADMIN). La double authentification
(`mfa.py`, `middleware.py`, `throttle.py`) est plus avancée : gardez-la pour l'étape 10.

### Étape 3 — Le journal d'audit : `audit` (≈ 1 h)

Lire `apps/audit/models.py` (14 champs, immuabilité), `services.py` (`log_action`), `registry.py`
(`audit_model`), `signals.py`. C'est un bon exemple de **signaux Django** (`post_save`).

*Vérification :* modifiez le kilométrage d'un camion dans l'admin Django, puis ouvrez
`/admin/audit/auditlog/` : vous devez voir la ligne avec l'ancienne et la nouvelle valeur.

### Étape 4 — Un module complet, de A à Z : `fleet` (≈ 3 h)

**C'est l'étape la plus importante.** `fleet` (les camions) est le module « modèle » : petit, complet, et
toutes les autres apps suivent le même plan. Lisez dans cet ordre :

1. `apps/fleet/README.md` (la description du module en 20 lignes) ;
2. `models.py` : `Vehicule`, `DocumentReglementaire` (contraintes en base) ;
3. `exceptions.py` puis `services.py` : `calculer_statut`, `creer_vehicule`, `enregistrer_document`,
   `etat_documents` ;
4. `tests/test_services.py` puis `tests/test_models.py` ;
5. `permissions.py`, `apps.py`, `admin.py` ;
6. `urls.py`, `views.py`, `forms.py`, `templates/fleet/` : **ici, lisez d'abord GUIDE-INTERFACE.md**
   (le guide suit le module Carburant, très proche).

*Vérification :* sans regarder le code, expliquez à voix haute ce qui se passe quand un utilisateur clique
sur « Enregistrer » dans le formulaire de création d'un camion (vue → formulaire → service → modèle →
redirection).

### Étape 5 — Le trajet d'un clic (≈ 2 h)

Lisez **GUIDE-INTERFACE.md en entier**, en gardant `apps/fuel/` ouvert. Refaites dans le navigateur ce que
le guide décrit (liste, filtre, saisie d'un plein, avertissement de saisie suspecte).

### Étape 6 — Personnes et clients : `hr`, `drivers`, `customers` (≈ 3 h, survol)

Ne cherchez pas à tout retenir. Lisez le `README.md` de chaque app, puis seulement :

- `hr/models.py` et `hr/services.py` : le **workflow des congés** en trois niveaux (demande → N1 → N2).
  C'est le meilleur exemple de **machine à états** du projet. `architecture.md:313-342` a le schéma.
- `drivers/models.py` : `Chauffeur` prolonge `Personnel` (relation un-à-un), fiche créée automatiquement
  par un signal (`drivers/signals.py`).
- `customers/services.py` : la règle de TVA (0 % exige un motif d'exonération).

### Étape 7 — Le cœur métier : `missions` (≈ 4 h)

Le module le plus riche. Lisez :

- `models.py` : `StatutMission` (7 statuts) et `Mission` ;
- `services.py` : chaque **transition** est une fonction (`creer_mission` → `planifier_mission` →
  `affecter_mission` → `demarrer_mission` → `confirmer_recuperation` → `livrer_mission` → `cloturer_mission`).
  Notez `_exiger_statut` (une mission ne saute pas d'étape) et `_verifier_code` (comparaison en temps constant
  avec `secrets.compare_digest`, pour ne pas révéler le code par le temps de réponse) ;
- `signals.py` puis, **dans une autre app**, `notifications/receivers.py` : voyez comment l'annonce
  « mission démarrée » devient une notification ;
- `tests/test_services.py` : un test par règle.

*Vérification :* dessinez au crayon le cycle de vie d'une mission (7 cases, des flèches, et pour chaque
flèche la règle qui la conditionne). Comparez avec `architecture.md:236-256`.

### Étape 8 — Garage, stock, carburant : `garage`, `inventory`, `fuel` (≈ 4 h)

Trois modules qui appliquent ce que vous savez déjà. Points intéressants :

- `garage` : ouvrir un ordre de réparation met le camion « En maintenance » en appelant
  `fleet.services.recalculer_statut` (l'inversion vue en 3.3) ;
- `inventory` : le **PUMP** (prix unitaire moyen pondéré) recalculé à chaque entrée, et le journal
  des mouvements **immuable** ;
- `fuel` : le calcul de consommation et les seuils 20 %, 40 %, 60 % (`fuel/services.py`, docstring en tête).

### Étape 9 — Argent : `billing`, `finance` (≈ 3 h)

- `billing/services.py` : le cycle d'une facture (brouillon → à valider → émise → payée), le **numéro attribué à
  la validation**, la TVA arrondie au franc (les `Decimal`) ;
- `finance/services.py` : trésorerie et indicateurs (`Sum`, `Q`).

### Étape 10 — Ce qui relie et protège : `notifications`, `dashboard`, `api`, `mobile_api`, sécurité (≈ 4 h)

- `notifications/receivers.py` (qui est prévenu de quoi) et `taches.py` (alertes quotidiennes) ;
- `dashboard/services.py` : il **assemble** les lectures des autres apps sans rien calculer lui-même ;
- `api/` : l'API REST (Django REST Framework). `v1/serializers.py` (transformer un objet en JSON),
  `v1/views.py`, `permissions.py`, `exceptions.py` (erreurs métier → codes HTTP) ;
- `mobile_api/services.py` : ce qu'un chauffeur voit et fait, **sur ses seules données** ;
- sécurité : `accounts/mfa.py`, `accounts/middleware.py`, `accounts/throttle.py`, `core/middleware.py`.
  Lisez d'abord `apps/accounts/README.md`, il explique le pourquoi de chaque choix.

---

## 5. Dix exercices

Faites-les **sur une branche** pour pouvoir tout annuler :

```bash
git switch -c mes-exercices          # créer la branche
# ... vos essais ...
git restore .                        # annuler les modifications non commitées
git switch master                    # revenir (l'état d'origine)
```

| # | Exercice | Ce que ça vous apprend |
|---|---|---|
| 1 | Dans `manage.py shell`, listez les camions disponibles, puis les missions d'un client donné. Affichez le SQL avec `str(qs.query)`. | ORM, `filter`, clés étrangères |
| 2 | Ajoutez un champ `couleur` (texte, optionnel) à `Vehicule`. Lancez `makemigrations`, lisez le fichier créé, puis `migrate`. Affichez-le dans `list_display` de l'admin. | modèles, migrations, admin |
| 3 | Annulez l'exercice 2 proprement : `python manage.py migrate fleet 0001`, supprimez le fichier de migration et le champ. | cycle de vie d'une migration |
| 4 | Trouvez où est levée l'erreur « Charge supérieure à la capacité du camion » et **quel test la vérifie** (`Ctrl+Maj+F`, cherchez `capacité`). | relier code et tests |
| 5 | Écrivez un test dans `apps/core/tests/test_echeance.py` : un document qui expire **aujourd'hui** est `A_RENOUVELER` avec 0 jour restant. | écrire un test, `etat_echeance` |
| 6 | Dans `apps/notifications/receivers.py`, ajoutez un `print("DEMARRE", mission)` dans le récepteur de `mission_demarree`, puis démarrez une mission dans le navigateur et regardez la console du serveur. | signaux |
| 7 | Dans `apps/fleet/services.py`, ajoutez temporairement `print` dans `calculer_statut`. Lancez `pytest apps/fleet -q -s` : combien de fois est-elle appelée ? | tests, `-s` |
| 8 | **Cassez une règle** : dans `affecter_mission`, remplacez `mission.poids_t > vehicule.capacite_charge_t` par `>=`. Lancez `pytest apps/missions -q`. Quel test échoue ? Puis annulez avec `git restore`. | à quoi servent les tests |
| 9 | Donnez à `demo_finances` l'accès à la liste des camions : dans `apps/fleet/permissions.py`, ajoutez `Role.FINANCES` à `CONSULTATION`. Que voit-il dans le menu ? Qu'est-ce qui casse dans les tests ? | rôles, permissions, tests d'accès |
| 10 | Ajoutez un filtre « kilométrage minimum » à la liste des camions : un champ `km_min` dans `templates/fleet/vehicule_list.html`, sa lecture dans `VehiculeListView.get_queryset` (`request.GET`), un paramètre de `services.rechercher_vehicules`, puis son test dans `tests/test_services.py`. | le trajet complet d'un écran |

Astuce pour l'exercice 10 : le filtre `statut` existe déjà. **Imitez-le** à chaque couche (gabarit :
`<select name="statut">` ; vue : `self.request.GET.get("statut")` ; service : `if statut in StatutVehicule.values`).

---

## 6. Outils pour comprendre et déboguer

| Besoin | Commande |
|---|---|
| Essayer du code avec les vrais modèles | `python manage.py shell` |
| Lancer un seul test, s'arrêter au premier échec | `python -m pytest apps/fleet/tests/test_services.py -x -q` |
| Lancer les tests dont le nom contient un mot | `python -m pytest -k "statut" -q` |
| Voir les `print` pendant un test | `python -m pytest -s` |
| S'arrêter dans le débogueur à l'échec | `python -m pytest --pdb` (commandes : `n` suivant, `c` continuer, `p variable`, `q` quitter) |
| Voir la couverture | `python -m pytest --cov=apps/fleet --cov-report=term-missing` |
| Voir les migrations | `python manage.py showmigrations` |
| Vérifier que rien n'est oublié | `python manage.py check` et `python manage.py makemigrations --check --dry-run` |
| Regarder les données | l'admin : `http://localhost:8000/admin/` (compte ADMIN) |
| Retrouver l'adresse d'un écran | lisez `config/urls.py` (il monte chaque app), puis le `urls.py` de l'app |

**Dans VS Code**, installez l'extension *Python* et choisissez l'interpréteur `.venv` ; cliquez à gauche d'un
numéro de ligne pour poser un point d'arrêt, puis lancez pytest en mode débogage (icône « flacon » de
l'onglet Tests).

**Pour retrouver un comportement :** cherchez un **texte visible** de l'interface (par exemple
« Charge de ») avec `Ctrl+Maj+F` : vous tomberez sur le service qui l'écrit, puis sur les tests qui le
vérifient.

---

## 7. Pièges de lecture

- **`objects` cache les enregistrements supprimés** (soft delete). Pour tout voir : `all_objects`.
- **`null=True` et `blank=True` ne sont pas la même chose** (base de données / formulaire).
- **`select_for_update` ne fait rien avec SQLite** (base de développement). Les verrous sont pensés pour
  PostgreSQL (prévu en production).
- **`Decimal`, pas `float`** pour l'argent, les litres, les tonnes : `Decimal("0.1") + Decimal("0.2") == Decimal("0.3")`.
- **Fuseau horaire** : `timezone.now()` renvoie une heure **avec fuseau** ; `timezone.localdate()` la date
  locale (Abidjan). Ne mélangez pas avec `datetime.now()`.
- **Les tests dépendent de la date** : le projet garde ses dates de test dans le passé (une date future est
  refusée par la validation métier). Un test qui casse « un jour sans raison » est souvent une date en dur.
- **`gettext_lazy` (`_`)** : le texte n'est évalué qu'à l'affichage. Ne l'utilisez pas dans un `f"..."`.
- **Les migrations font partie du code** : si vous changez un modèle, `makemigrations` puis committez le
  fichier créé.
- **Un service lève, une vue attrape.** Si vous voyez `try/except MissionError` dans une vue, c'est normal :
  c'est ainsi que l'erreur devient un message affiché.
- **Un gabarit qui « ne change pas »** : le navigateur a peut-être gardé l'ancienne version (`Ctrl+F5`), ou
  vous avez ajouté une classe Tailwind sans recompiler (`frontend/README.md`).

---

## 8. Petit lexique Django

| Terme | Sens |
|---|---|
| **ORM** | traduit du Python en SQL : `Vehicule.objects.filter(...)` |
| **QuerySet** | résultat paresseux d'une requête ; on peut le refiltrer avant de le lire |
| **Manager** | l'objet `objects` : le point d'entrée des requêtes d'un modèle |
| **Migration** | fichier qui fait évoluer les tables pour suivre les modèles |
| **Vue** (view) | code qui répond à une requête HTTP |
| **CBV** | *class-based view* : vue écrite comme une classe (`ListView`, `FormView`…) |
| **Mixin** | petite classe qui ajoute un comportement (`RoleRequiredMixin` ajoute la garde d'accès) |
| **Gabarit** (template) | fichier HTML avec `{{ }}` et `{% %}` |
| **Middleware** | code qui s'exécute sur toutes les requêtes |
| **Signal** | annonce d'un événement que d'autres modules écoutent |
| **`AppConfig.ready()`** | code exécuté une fois au démarrage, propre à une app |
| **Fixture** (pytest) | ressource préparée pour un test (`client`, `django_db`…) |
| **Factory** | fabrique d'objets de test (`VehiculeFactory()`) |
| **Soft delete** | « supprimer » = marquer, sans effacer la ligne |
| **CSRF** | protection contre les formulaires envoyés à l'insu de l'utilisateur (le `{% csrf_token %}`) |
| **DRF** | Django REST Framework : la bibliothèque de l'API |
| **JWT** | jeton signé qui prouve l'identité d'un appel d'API |
| **TOTP** | code à 6 chiffres qui change toutes les 30 secondes (double authentification) |

---

### Et ensuite ?

Quand vous aurez fait les étapes 1 à 5 et quelques exercices, vous saurez **lire n'importe quel module** :
ils suivent tous le même plan. Le reste est de la répétition et du métier. Si quelque chose bloque,
notez **le fichier, la ligne et la question précise** : c'est ce qu'il faut me dire pour que je vous
l'explique pas à pas.

Documents à lire à côté, quand vous êtes à l'aise : `cahier-des-charges.md` (ce que veut le client),
`architecture.md` (pourquoi ce découpage), `conventions.md` (les règles d'écriture),
`audit-checklist.md` (ce qu'on vérifie avant la recette).
