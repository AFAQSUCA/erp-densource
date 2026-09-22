# Chapitre 4 — Le journal d'audit : l'app audit

> 10 fichier(s) dans ce chapitre, 422 lignes de code.

## Ce que vous allez construire

**`audit`** : le **journal d'audit**, la mémoire inaltérable de l'ERP. Chaque connexion, chaque création,
modification, suppression ou validation y laisse une trace : **qui**, **quand**, **depuis quelle adresse**,
**quoi**, **avec quelles valeurs avant et après**.

Trois idées à retenir :

| Idée | Réalisation |
|---|---|
| **Le journal ne peut pas être modifié ni effacé** | `AuditLog.save()` refuse toute modification, `delete()` est interdit, l'administration est en lecture seule |
| **Tracer un modèle coûte une ligne** | `audit_model(MonModele, module="…")` dans l'`apps.py` de chaque app |
| **Les secrets n'y entrent jamais** | `audit_model(..., exclure=("code_expediteur",))` retire des champs du journal |

## Prérequis

- Chapitre 3 terminé, `python manage.py migrate` fait (la table `accounts_user` existe).

## Notions Django de ce chapitre

- **Signaux `pre_save` / `post_save`** : Django les émet juste avant et juste après chaque `save()` d'un
  modèle. On s'y abonne pour capturer l'état **avant** puis **après** une modification.
- **`sender=Modele`** : limite l'abonnement à un seul modèle.
- **`weak=False`** : sans cela, Django garde l'abonné par référence *faible* et une fonction définie dans
  une autre fonction peut être ramassée par le ramasse-miettes : l'abonnement disparaîtrait.
- **`dispatch_uid`** : un identifiant qui empêche d'abonner deux fois la même fonction.
- **`JSONField`** : une colonne qui stocke du JSON (les valeurs avant/après sont des dictionnaires).
- **Administration en lecture seule** : on retire les droits d'ajout, de modification et de suppression.

## Étape 1 — Créer l'application

```bash
mkdir -p apps/audit/tests
```

#### Fichiers vides à créer

Ces fichiers n'ont aucun contenu ; ils servent à faire de leur dossier un *paquet Python* (sans eux, `import apps.xxx` échouerait). Créez d'abord les dossiers, puis les fichiers :

```bash
mkdir -p apps\audit apps\audit\tests
touch apps/audit/__init__.py
touch apps/audit/tests/__init__.py
```

> Sous PowerShell, `mkdir -p` s'écrit `New-Item -ItemType Directory -Force <dossier>` et `touch fichier` s'écrit `New-Item -ItemType File -Force fichier`. Vous pouvez aussi créer ces fichiers avec votre éditeur.

## Étape 2 — Le modèle du journal

#### `apps/audit/models.py`

*75 lignes*

```python
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class ActionChoices(models.TextChoices):
    CREATE = "CREATE", _("Création")
    UPDATE = "UPDATE", _("Modification")
    DELETE = "DELETE", _("Suppression")
    LOGIN = "LOGIN", _("Connexion")
    LOGOUT = "LOGOUT", _("Déconnexion")
    VALIDATE = "VALIDATE", _("Validation")


class StatutChoices(models.TextChoices):
    SUCCESS = "SUCCESS", _("Succès")
    FAILED = "FAILED", _("Échec")


class AuditLog(models.Model):
    """Journal d'audit append-only — cahier-des-charges.md:56-82 (14 champs).

    Immuabilité stricte : ``save()`` refuse toute modification d'une ligne
    existante, ``delete()`` est désactivé. Conservation ≥ 5 ans (purge hors
    applicatif, cf. politique de rétention BDD).
    """

    date_heure = models.DateTimeField(_("date/heure"), auto_now_add=True, db_index=True)
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("utilisateur"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    utilisateur_nom = models.CharField(_("nom utilisateur"), max_length=150, blank=True)
    role = models.CharField(_("rôle"), max_length=20, blank=True)
    action = models.CharField(_("action"), max_length=10, choices=ActionChoices.choices)
    module = models.CharField(_("module"), max_length=50)
    entite = models.CharField(_("entité"), max_length=100)
    entite_id = models.BigIntegerField(_("ID entité"), null=True, blank=True)
    ancienne_valeur = models.JSONField(_("ancienne valeur"), null=True, blank=True)
    nouvelle_valeur = models.JSONField(_("nouvelle valeur"), null=True, blank=True)
    adresse_ip = models.GenericIPAddressField(_("adresse IP"), null=True, blank=True)
    user_agent = models.CharField(_("user-agent"), max_length=255, blank=True)
    statut = models.CharField(
        _("statut"),
        max_length=10,
        choices=StatutChoices.choices,
        default=StatutChoices.SUCCESS,
    )

    class Meta:
        db_table = "audit_log"
        verbose_name = _("entrée d'audit")
        verbose_name_plural = _("journal d'audit")
        ordering = ["-date_heure"]
        indexes = [
            models.Index(fields=["module", "entite", "entite_id"]),
            models.Index(fields=["utilisateur", "date_heure"]),
        ]

    def __str__(self):
        return f"{self.date_heure:%Y-%m-%d %H:%M:%S} {self.action} {self.module}.{self.entite}#{self.entite_id}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError(
                "AuditLog est append-only : modification d'une entrée existante interdite."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("AuditLog est append-only : suppression interdite.")
```

Points clés :

- **14 champs** : date, utilisateur (et son nom recopié : si le compte disparaît, la trace reste
  lisible), rôle, action, module, entité, identifiant de l'entité, valeurs avant/après, adresse IP,
  navigateur, statut (succès/échec).
- **`save()` lève une erreur** si la ligne existe déjà (`self.pk is not None`) : impossible de réécrire
  l'histoire. **`delete()`** est interdit.
- **`on_delete=SET_NULL`** sur l'utilisateur : supprimer un compte n'efface pas ses traces.
- Deux **index** accélèrent les recherches courantes (par entité, par utilisateur et date).

## Étape 3 — Le service et le branchement automatique

#### `apps/audit/services.py`

*89 lignes* — Logique métier du journal d'audit — conventions.md §2.

```python
"""Logique métier du journal d'audit — conventions.md §2.

Point d'entrée unique pour créer une ligne ``AuditLog`` : les apps métier
(fleet, missions, hr...) appelleront :func:`log_action` depuis leurs
propres signaux ``post_save``/``post_delete`` au fur et à mesure de leur
création (cahier-des-charges.md:76 "Enregistrement auto via triggers SQL
ou middleware").
"""

from __future__ import annotations

from typing import Any

from apps.core.middleware import get_client_ip

from .models import ActionChoices, AuditLog, StatutChoices


def log_action(
    *,
    action: str,
    module: str,
    entite: str,
    utilisateur=None,
    entite_id: int | None = None,
    ancienne_valeur: dict[str, Any] | None = None,
    nouvelle_valeur: dict[str, Any] | None = None,
    request=None,
    statut: str = StatutChoices.SUCCESS,
) -> AuditLog:
    """Crée une entrée d'audit immuable.

    ``request`` est optionnel (absent pour les tâches Celery) : quand
    fourni, l'IP et le user-agent sont extraits automatiquement.
    """
    adresse_ip = None
    user_agent = ""
    if request is not None:
        adresse_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")[:255]

    return AuditLog.objects.create(
        utilisateur=utilisateur,
        utilisateur_nom=getattr(utilisateur, "get_full_name", lambda: "")() or "",
        role=getattr(utilisateur, "role", ""),
        action=action,
        module=module,
        entite=entite,
        entite_id=entite_id,
        ancienne_valeur=ancienne_valeur,
        nouvelle_valeur=nouvelle_valeur,
        adresse_ip=adresse_ip,
        user_agent=user_agent,
        statut=statut,
    )


def log_login(utilisateur, request) -> AuditLog:
    return log_action(
        action=ActionChoices.LOGIN,
        module="AUTH",
        entite="User",
        entite_id=utilisateur.pk,
        utilisateur=utilisateur,
        request=request,
    )


def log_logout(utilisateur, request) -> AuditLog:
    return log_action(
        action=ActionChoices.LOGOUT,
        module="AUTH",
        entite="User",
        entite_id=utilisateur.pk if utilisateur else None,
        utilisateur=utilisateur,
        request=request,
    )


def log_login_failed(username: str, request) -> AuditLog:
    return log_action(
        action=ActionChoices.LOGIN,
        module="AUTH",
        entite="User",
        utilisateur=None,
        nouvelle_valeur={"username_tente": username},
        request=request,
        statut=StatutChoices.FAILED,
    )
```

`log_action` est **l'unique porte d'entrée** pour écrire dans le journal. Elle extrait toute seule l'adresse
IP et le navigateur de la requête courante.

#### `apps/audit/registry.py`

*104 lignes* — Branchement de l'audit automatique sur les modèles sensibles.

```python
"""Branchement de l'audit automatique sur les modèles sensibles.

ADR-003 (architecture.md:488-493) : signaux ``pre_save``/``post_save``.
Chaque app appelle ``audit_model(MonModele, module="...")`` dans son
``AppConfig.ready()`` ; toute création, modification ou suppression
logique produit alors une ligne ``audit_log`` avec les valeurs avant/après.
"""

from __future__ import annotations

import json
from decimal import Decimal

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import DecimalField, Model
from django.db.models.signals import post_save, pre_save

from apps.core.middleware import get_current_request, get_current_user

from . import services
from .models import ActionChoices

# Bruit sans valeur d'audit : les horodatages techniques changent à chaque save.
CHAMPS_IGNORES = {"created_at", "updated_at"}


def _valeur(field, valeur):
    """Normalise une décimale comme la base la relira (250000 → 250000.00).

    Sans cela, l'instance en mémoire (Decimal("250000")) et la ligne relue
    en base (Decimal("250000.00")) paraîtraient différentes à chaque save().
    """
    if isinstance(field, DecimalField) and valeur is not None:
        return Decimal(valeur).quantize(Decimal(1).scaleb(-field.decimal_places))
    return valeur


def _snapshot(instance: Model, exclure: frozenset[str] = frozenset()) -> dict:
    """Valeurs des colonnes de l'instance, sérialisables en JSON."""
    data = {
        f.attname: _valeur(f, getattr(instance, f.attname))
        for f in instance._meta.concrete_fields
        if f.attname not in CHAMPS_IGNORES and f.attname not in exclure
    }
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))


def audit_model(
    model: type[Model], module: str, exclure: tuple[str, ...] = ()
) -> None:
    """Active l'audit automatique de ``model`` sous le nom de module ``module``.

    ``exclure`` liste les champs à ne jamais écrire dans le journal (secrets :
    codes de mission, etc.). Un changement sur ces seuls champs ne produit
    aucune entrée.
    """
    label = model._meta.label
    exclus = frozenset(exclure)
    entite = model.__name__

    def capturer_avant(sender, instance, raw=False, **kwargs):
        if raw:
            return
        instance._audit_avant = None
        if instance.pk:
            ancien = sender._base_manager.filter(pk=instance.pk).first()
            if ancien is not None:
                instance._audit_avant = _snapshot(ancien, exclus)

    def journaliser(sender, instance, created, raw=False, **kwargs):
        if raw:
            return
        apres = _snapshot(instance, exclus)
        avant = getattr(instance, "_audit_avant", None)

        if created or avant is None:
            action = ActionChoices.CREATE
            ancienne, nouvelle = None, apres
        else:
            changes = [k for k in apres if avant.get(k) != apres[k]]
            if not changes:
                return
            supprime = not avant.get("is_deleted") and apres.get("is_deleted")
            action = ActionChoices.DELETE if supprime else ActionChoices.UPDATE
            ancienne = {k: avant.get(k) for k in changes}
            nouvelle = {k: apres[k] for k in changes}

        services.log_action(
            action=action,
            module=module,
            entite=entite,
            entite_id=instance.pk,
            utilisateur=get_current_user(),
            ancienne_valeur=ancienne,
            nouvelle_valeur=nouvelle,
            request=get_current_request(),
        )

    pre_save.connect(
        capturer_avant, sender=model, weak=False, dispatch_uid=f"audit-pre-{label}"
    )
    post_save.connect(
        journaliser, sender=model, weak=False, dispatch_uid=f"audit-post-{label}"
    )
```

C'est le cœur du système. `audit_model(Vehicule, module="PARC_AUTO")` branche deux fonctions sur le modèle :

1. **`capturer_avant`** (`pre_save`) : relit la ligne en base et en garde une photo (`_audit_avant`).
2. **`journaliser`** (`post_save`) : compare la photo « avant » à l'état « après ». Si rien n'a changé, elle
   n'écrit **rien**. Sinon elle écrit une ligne `CREATE`, `UPDATE` ou `DELETE` (une suppression logique
   est reconnue à `is_deleted` qui passe à vrai) avec **seulement les champs modifiés**.

`get_current_user()` et `get_current_request()` viennent du middleware du chapitre 2 : c'est ce qui permet de
savoir *qui* a modifié, même depuis un service qui ne reçoit pas la requête.

#### `apps/audit/signals.py`

*49 lignes* — Signaux LOGIN/LOGOUT/LOGIN_FAILED — cahier-des-charges.md:78-79, ADR-003.

```python
"""Signaux LOGIN/LOGOUT/LOGIN_FAILED — cahier-des-charges.md:78-79, ADR-003.

Les signaux ``post_save``/``post_delete`` des modèles métier sensibles
(Personnel, Vehicule, Mission, Facture, OR, Conge — cahier-des-charges.md:222-223)
seront ajoutés dans chaque app au fur et à mesure de leur création,
en appelant :func:`apps.audit.services.log_action`.
"""

from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver

from apps.accounts.signals import mfa_evenement

from . import services
from .models import ActionChoices, StatutChoices


@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs):
    services.log_login(user, request)


@receiver(user_logged_out)
def on_user_logged_out(sender, request, user, **kwargs):
    services.log_logout(user, request)


@receiver(user_login_failed)
def on_user_login_failed(sender, credentials, request=None, **kwargs):
    services.log_login_failed(credentials.get("username", ""), request)


@receiver(mfa_evenement)
def on_mfa_evenement(sender, request, utilisateur, evenement, succes, **kwargs):
    """Activation, code accepté ou refusé, codes régénérés : tout est tracé (rien n'expose de secret)."""
    services.log_action(
        action=ActionChoices.UPDATE,
        module="AUTH",
        entite="MFA",
        entite_id=utilisateur.pk if utilisateur else None,
        utilisateur=utilisateur,
        nouvelle_valeur={"evenement": evenement},
        request=request,
        statut=StatutChoices.SUCCESS if succes else StatutChoices.FAILED,
    )
```

L'app `audit` s'abonne ici aux événements des autres : connexion réussie, déconnexion, connexion échouée
(fournis par Django) et `mfa_evenement` (notre signal du chapitre 3). Remarquez que c'est `audit` qui importe
`accounts`, pas l'inverse : `accounts` ne sait pas que le journal existe.

## Étape 4 — Administration et démarrage

#### `apps/audit/admin.py`

*40 lignes*

```python
from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Consultation ADMIN, lecture seule DIRECTION — cahier-des-charges.md:81.

    Append-only : ajout/modification/suppression désactivés dans l'admin,
    y compris pour ADMIN (une entrée ne se crée que via
    :func:`apps.audit.services.log_action`).
    """

    list_display = (
        "date_heure",
        "utilisateur_nom",
        "role",
        "action",
        "module",
        "entite",
        "entite_id",
        "statut",
    )
    list_filter = ("action", "module", "statut", "role")
    search_fields = ("utilisateur_nom", "entite", "adresse_ip")
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        user = request.user
        return bool(user.is_superuser or getattr(user, "role", None) in ("ADMIN", "DIRECTION"))
```

Dans l'administration, le journal est en **lecture seule pour tout le monde** (même l'ADMIN). Il se lit
depuis `/admin/audit/auditlog/`. Seuls un superutilisateur, un ADMIN ou une DIRECTION peuvent le *voir* ; la
DIRECTION doit en plus avoir l'accès à l'administration (case « statut équipe » cochée sur son compte).

#### `apps/audit/apps.py`

*10 lignes*

```python
from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.audit'
    label = 'audit'

    def ready(self):
        from . import signals  # noqa: F401
```

## Étape 5 — README et test

#### `apps/audit/README.md`

*13 lignes* — audit

```markdown
# audit

Rôle : journal d'audit append-only (`audit_log`), 14 champs —
cahier-des-charges.md:56-82. Capture LOGIN/LOGOUT/CREATE/UPDATE/DELETE/
VALIDATE via middleware + signals `post_save` (ADR-003, architecture.md:488-493).
Dépend de `core` (architecture.md:135).

Entités principales : `AuditLog`. `registry.audit_model()` branche l'audit automatique (CREATE/UPDATE/DELETE avant/après) sur un modèle.

Règles :
- Immuabilité stricte : aucun `update()`/`delete()` autorisé sur ce modèle.
- Conservation ≥ 5 ans.
- Consultation : ADMIN (complet), DIRECTION (lecture seule).
```

#### `apps/audit/tests/test_models.py`

*32 lignes*

```python
import pytest

from apps.audit.models import ActionChoices, AuditLog, StatutChoices

pytestmark = pytest.mark.django_db


def test_audit_log_created_with_success_status_by_default():
    entry = AuditLog.objects.create(
        action=ActionChoices.CREATE,
        module="FLEET",
        entite="Vehicule",
        entite_id=1,
    )

    assert entry.statut == StatutChoices.SUCCESS
    assert entry.date_heure is not None


def test_audit_log_save_raises_on_update_of_existing_entry():
    entry = AuditLog.objects.create(action=ActionChoices.CREATE, module="FLEET", entite="Vehicule")
    entry.statut = StatutChoices.FAILED

    with pytest.raises(ValueError):
        entry.save()


def test_audit_log_delete_is_forbidden():
    entry = AuditLog.objects.create(action=ActionChoices.CREATE, module="FLEET", entite="Vehicule")

    with pytest.raises(ValueError):
        entry.delete()
```

## Étape 6 — Déclarer l'application et migrer

#### `config/settings/base.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/settings/base.py (avant)
+++ config/settings/base.py (après)
@@ -51,4 +51,5 @@
     "apps.core",
     "apps.accounts",
+    "apps.audit",
 ]
 
```

```bash
python manage.py makemigrations audit
python manage.py migrate
```

**Résultat attendu :** `Create model AuditLog`, puis `Applying audit.0001_initial... OK`.

## Vérifier le chapitre

```bash
python manage.py check
```

```bash
python -m pytest apps/audit/tests/test_models.py -q --no-cov
```

**Résultat attendu :** `3 passed` (pour les 1 fichier(s) de tests présentés dans ce chapitre).

**Essai réel.** Le journal se remplit tout seul dès qu'un modèle est branché. Ouvrez le shell, créez un
utilisateur et regardez si la connexion échouée est tracée :

```bash
python manage.py shell -c "from apps.audit.services import log_action; from apps.audit.models import AuditLog, ActionChoices; e = log_action(action=ActionChoices.LOGIN, module='AUTH', entite='User'); print(e.date_heure is not None, AuditLog.objects.count())"
```

**Résultat attendu :** `True 1`. Essayez ensuite `e.delete()` dans un shell interactif : l'erreur
`AuditLog est append-only : suppression interdite.` apparaît.

> **Nettoyage.** Cette ligne d'essai restera dans votre journal de développement : c'est normal, on ne peut pas
> l'effacer (c'est le but !). Si vous voulez repartir d'une base propre, supprimez `db.sqlite3` et relancez
> `python manage.py migrate`.

## Ce qu'il faut retenir

- Un journal d'audit **se protège lui-même** : il n'existe aucune fonction pour le modifier.
- Le **branchement par signaux** rend la traçabilité automatique : les développeurs des autres apps n'écrivent
  jamais dans le journal à la main.
- **Dépendances à sens unique** : `audit` connaît `accounts`, jamais l'inverse.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 4 : app audit (journal inaltérable, audit automatique des modèles)"
```

---

[← Chapitre 3](03-accounts.md) · [Sommaire](README.md) · [Chapitre 5 →](05-hr.md)
