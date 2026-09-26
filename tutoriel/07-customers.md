# Chapitre 7 — Les clients : l'app customers

> 11 fichier(s) dans ce chapitre, 402 lignes de code.

## Ce que vous allez construire

**`customers`** : le **portefeuille clients** et leur **historique commercial**.

| Élément | Règle |
|---|---|
| `Client` | raison sociale, n° de contribuable (NCC/NIF, unique), contact, adresse, **chargé de clientèle attitré** |
| **TVA** | **18 % par défaut** ; à **0 %**, un **motif d'exonération** est obligatoire (export, ONG, convention, autre) |
| **Délai de paiement** | 30 jours par défaut, réglable de 1 à 365 jours ; il servira à calculer l'échéance des factures |
| `Interaction` | l'historique : appel, mail, réunion, demande de devis, **réclamation** |

## Prérequis

- Chapitres 1 à 6 terminés.

## Notions Django de ce chapitre

- **`CheckConstraint` avec `Q`** : une règle vérifiée par la base : « si le taux de TVA est 0, le motif
  d'exonération n'est pas vide » (`client_tva_zero_requiert_motif`). Le service la contrôle aussi, pour
  donner un message clair *avant* que la base ne refuse.
- **`DecimalField`** : pour l'argent et les taux, **jamais `float`** (les flottants s'arrondissent mal).
- **Unicité et suppression logique** : un NCC/NIF reste unique **même parmi les clients supprimés**
  (sinon on pourrait recréer un doublon d'un ancien client).
- **`**champs`** : une fonction qui accepte un nombre variable d'arguments nommés ; ici `creer_client`
  applique des valeurs par défaut avec `setdefault`.
- **Registre `sections`** : comme pour `hr`, `customers` expose un bloc que `missions` remplira (les missions
  d'un client s'affichent sur sa fiche).

## Étape 1 — Créer l'application

```bash
mkdir -p apps/customers/tests
```

#### Fichiers vides à créer

Ces fichiers n'ont aucun contenu ; ils servent à faire de leur dossier un *paquet Python* (sans eux, `import apps.xxx` échouerait). Créez d'abord les dossiers, puis les fichiers :

```bash
mkdir -p apps\customers apps\customers\tests
touch apps/customers/__init__.py
touch apps/customers/tests/__init__.py
```

> Sous PowerShell, `mkdir -p` s'écrit `New-Item -ItemType Directory -Force <dossier>` et `touch fichier` s'écrit `New-Item -ItemType File -Force fichier`. Vous pouvez aussi créer ces fichiers avec votre éditeur.

## Étape 2 — Modèles et règles

#### `apps/customers/models.py`

*128 lignes*

```python
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel

TVA_DEFAUT = Decimal("18.00")
DELAI_PAIEMENT_DEFAUT = 30  # jours ; échéance d'une facture = émission + délai du client


class MotifExoneration(models.TextChoices):
    """Motifs d'exonération de TVA — cahier-des-charges.md:187-188."""

    EXPORT = "EXPORT", _("Export")
    ONG = "ONG", _("ONG")
    CONVENTION = "CONVENTION", _("Convention")
    AUTRE = "AUTRE", _("Autre")


class Client(BaseModel):
    """Fiche client — cahier-des-charges.md:119-122."""

    raison_sociale = models.CharField(_("raison sociale"), max_length=200)
    ncc_nif = models.CharField(_("NCC / NIF"), max_length=50, unique=True)
    contact_principal = models.CharField(_("contact principal"), max_length=150)
    telephone = models.CharField(_("téléphone"), max_length=20)
    email = models.EmailField(_("email"), blank=True)
    adresse = models.TextField(_("adresse / siège"))
    charge_clientele = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("chargé clientèle attitré"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="clients",
        limit_choices_to={"role": "CHARGE_CLIENTELE"},
    )
    taux_tva = models.DecimalField(
        _("taux de TVA (%)"), max_digits=5, decimal_places=2, default=TVA_DEFAUT
    )
    motif_exoneration = models.CharField(
        _("motif d'exonération"),
        max_length=12,
        choices=MotifExoneration.choices,
        blank=True,
    )

    delai_paiement_jours = models.PositiveSmallIntegerField(
        _("délai de paiement (jours)"),
        default=DELAI_PAIEMENT_DEFAUT,
        help_text=_("Date d'échéance de ses factures = date d'émission + ce délai."),
    )

    class Meta:
        verbose_name = _("client")
        verbose_name_plural = _("clients")
        ordering = ["raison_sociale"]
        indexes = [models.Index(fields=["raison_sociale"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(taux_tva__gt=0) | ~Q(motif_exoneration=""),
                name="client_tva_zero_requiert_motif",
            ),
            models.CheckConstraint(
                condition=Q(taux_tva__gte=0) & Q(taux_tva__lte=100),
                name="client_taux_tva_entre_0_et_100",
            ),
            models.CheckConstraint(
                condition=Q(delai_paiement_jours__gte=1) & Q(delai_paiement_jours__lte=365),
                name="client_delai_paiement_entre_1_et_365",
            ),
        ]

    def __str__(self):
        return self.raison_sociale

    def clean(self):
        if self.taux_tva == 0 and not self.motif_exoneration:
            raise ValidationError(
                {"motif_exoneration": _("Motif obligatoire quand la TVA est à 0 %.")}
            )


class TypeInteraction(models.TextChoices):
    """Interactions commerciales — cahier-des-charges.md:123-124."""

    APPEL = "APPEL", _("Appel")
    MAIL = "MAIL", _("Mail")
    REUNION = "REUNION", _("Réunion")
    DEMANDE_DEVIS = "DEMANDE_DEVIS", _("Demande de devis")
    RECLAMATION = "RECLAMATION", _("Réclamation")


class Interaction(BaseModel):
    """Historique commercial d'un client."""

    client = models.ForeignKey(
        Client,
        verbose_name=_("client"),
        on_delete=models.PROTECT,
        related_name="interactions",
    )
    type_interaction = models.CharField(
        _("type"), max_length=15, choices=TypeInteraction.choices
    )
    date_interaction = models.DateTimeField(_("date"), default=timezone.now)
    resume = models.TextField(_("résumé / notes d'échange"))
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("auteur"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        verbose_name = _("interaction")
        verbose_name_plural = _("interactions")
        ordering = ["-date_interaction"]

    def __str__(self):
        return f"{self.get_type_interaction_display()} - {self.client}"
```

Repérez les trois `CheckConstraint` : la TVA à zéro exige un motif, le taux reste entre 0 et 100, le délai
de paiement entre 1 et 365 jours.

#### `apps/customers/exceptions.py`

*2 lignes*

```python
class ClientError(Exception):
    """Erreur métier sur une fiche client ou une interaction."""
```

#### `apps/customers/services.py`

*157 lignes* — Logique métier des clients : fiche, TVA, portefeuille et historique commercial.

```python
"""Logique métier des clients : fiche, TVA, portefeuille et historique commercial.

Réf. cahier-des-charges.md:119-124, 185-188.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Max, Q, QuerySet
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.core.search import filtrer_par_texte

from .exceptions import ClientError
from .models import DELAI_PAIEMENT_DEFAUT, TVA_DEFAUT, Client, Interaction, TypeInteraction

CHAMPS_MODIFIABLES = (
    "raison_sociale",
    "ncc_nif",
    "contact_principal",
    "telephone",
    "email",
    "adresse",
    "charge_clientele",
    "taux_tva",
    "motif_exoneration",
    "delai_paiement_jours",
)


def clients_pour_selection() -> QuerySet[Client]:
    """Clients triés par raison sociale, pour les listes déroulantes."""
    return Client.objects.order_by("raison_sociale")


def clients_queryset() -> QuerySet[Client]:
    """Clients avec le nombre d'interactions, de réclamations et la dernière interaction."""
    actives = Q(interactions__is_deleted=False)
    # order_by explicite : l'agrégation ignore l'ordre par défaut du modèle.
    return Client.objects.select_related("charge_clientele").order_by("raison_sociale").annotate(
        nb_interactions=Count("interactions", filter=actives, distinct=True),
        nb_reclamations=Count(
            "interactions",
            filter=actives & Q(interactions__type_interaction=TypeInteraction.RECLAMATION),
            distinct=True,
        ),
        derniere_interaction=Max("interactions__date_interaction", filter=actives),
    )


def rechercher_clients(
    *, recherche: str = "", charge_clientele: User | None = None, exonere: bool = False
) -> QuerySet[Client]:
    """Clients filtrés par texte, chargé clientèle attitré et exonération de TVA."""
    resultat = clients_queryset()
    resultat = filtrer_par_texte(
        resultat, recherche, "raison_sociale", "ncc_nif", "contact_principal", "telephone"
    )
    if charge_clientele is not None:
        resultat = resultat.filter(charge_clientele=charge_clientele)
    if exonere:
        resultat = resultat.filter(taux_tva=0)
    return resultat


def charges_clientele() -> QuerySet[User]:
    """Comptes actifs pouvant être chargé clientèle attitré."""
    return User.objects.filter(role=Role.CHARGE_CLIENTELE, is_active=True).order_by(
        "last_name", "first_name", "username"
    )


def interactions_du_client(client: Client) -> QuerySet[Interaction]:
    return client.interactions.select_related("auteur").order_by("-date_interaction", "-pk")


def _controler(champs: dict, *, client: Client | None = None) -> dict:
    """Vérifie et normalise les champs d'une fiche client."""
    taux = Decimal(champs["taux_tva"])
    if not Decimal(0) <= taux <= Decimal(100):
        raise ClientError("Le taux de TVA doit être compris entre 0 et 100 %.")
    if taux == 0 and not champs.get("motif_exoneration"):
        raise ClientError("Un motif d'exonération est obligatoire quand la TVA est à 0 %.")
    delai = champs.get("delai_paiement_jours", DELAI_PAIEMENT_DEFAUT)
    if not 1 <= delai <= 365:
        raise ClientError("Le délai de paiement doit être compris entre 1 et 365 jours.")
    resultat = dict(champs, taux_tva=taux, delai_paiement_jours=delai)
    if taux > 0:
        resultat["motif_exoneration"] = ""  # sans exonération, aucun motif n'a de sens
    charge = champs.get("charge_clientele")
    if charge is not None and (charge.role != Role.CHARGE_CLIENTELE or not charge.is_active):
        raise ClientError("Le chargé clientèle attitré doit être un compte actif de ce rôle.")
    doublon = Client.all_objects.filter(ncc_nif=champs["ncc_nif"])
    if client is not None:
        doublon = doublon.exclude(pk=client.pk)
    if doublon.exists():
        raise ClientError(f"Le NCC / NIF {champs['ncc_nif']} est déjà utilisé par un autre client.")
    return resultat


@transaction.atomic
def creer_client(**champs) -> Client:
    """Crée un client. TVA à 18 % par défaut ; à 0 %, le motif d'exonération est obligatoire."""
    champs.setdefault("taux_tva", TVA_DEFAUT)
    champs.setdefault("charge_clientele", None)
    champs.setdefault("motif_exoneration", "")
    champs.setdefault("email", "")
    return Client.objects.create(**_controler(champs))


@transaction.atomic
def modifier_client(client: Client, **champs) -> Client:
    """Met à jour la fiche d'un client (mêmes contrôles qu'à la création)."""
    for nom in CHAMPS_MODIFIABLES:
        champs.setdefault(nom, getattr(client, nom))
    for nom, valeur in _controler(champs, client=client).items():
        if nom in CHAMPS_MODIFIABLES:
            setattr(client, nom, valeur)
    client.save()
    return client


@transaction.atomic
def enregistrer_interaction(
    client: Client,
    auteur: User,
    *,
    type_interaction: str,
    resume: str,
    date_interaction: datetime | None = None,
) -> Interaction:
    """Ajoute une interaction à l'historique commercial du client (date non future)."""
    if not resume.strip():
        raise ClientError("Le résumé de l'échange est obligatoire.")
    maintenant = timezone.now()
    date_interaction = date_interaction or maintenant
    if date_interaction > maintenant:
        raise ClientError("La date d'une interaction ne peut pas être dans le futur.")
    return Interaction.objects.create(
        client=client,
        type_interaction=type_interaction,
        resume=resume,
        date_interaction=date_interaction,
        auteur=auteur,
    )


def reclamations_recentes(*, jours: int = 30, maintenant: datetime | None = None) -> int:
    """Nombre de réclamations enregistrées sur les ``jours`` derniers jours."""
    depuis = (maintenant or timezone.now()) - timedelta(days=jours)
    return Interaction.objects.filter(
        type_interaction=TypeInteraction.RECLAMATION, date_interaction__gte=depuis
    ).count()
```

- **`_controler`** rassemble tous les contrôles communs à la création et à la modification (TVA, unicité du
  NCC/NIF, chargé de clientèle valide, motif effacé si la TVA redevient positive). Il **transforme une
  violation de règle en `ClientError`** avec un message lisible.
- **`enregistrer_interaction`** refuse un résumé vide et une date **dans le futur**.
- **`rechercher_clients`** utilise `filtrer_par_texte` du chapitre 2 : « traore » trouve « Traoré ».
- **`reclamations_recentes`** alimentera le tableau de bord clientèle.

#### `apps/customers/permissions.py`

*16 lignes* — Qui peut consulter et gérer les clients.

```python
"""Qui peut consulter et gérer les clients.

Cahier-des-charges.md:44-55 : le CHARGE_CLIENTELE tient le « portefeuille clients,
historique, devis, réclamations, notes d'échange » ; l'ADMIN a tous les droits. La
DIRECTION, à l'origine en « lecture seule sur RH/Clientèle », modifie désormais aussi :
retour d'une réunion entreprise, elle a la même largeur que l'ADMIN sur la
saisie/modification. La RH n'a « pas d'accès clients » ; le PARCAUTO et le CHAUFFEUR
n'y ont pas accès non plus. L'accès des FINANCES (factures) se décidera avec la
facturation (étape 4).
"""

from apps.accounts.models import Role

CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE})
# Retour réunion : la DIRECTION a la même largeur que l'ADMIN pour la saisie/modification.
MODIFICATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE})
```

Le CDC donne la **gestion** des clients à l'ADMIN et au CHARGE_CLIENTELE, et la **lecture seule** à la
DIRECTION. La RH, le Parc Auto, les Finances et le chauffeur n'y ont pas accès.

#### `apps/customers/sections.py`

*9 lignes* — Blocs ajoutés à la fiche d'un client par des apps situées « en dessous ».

```python
"""Blocs ajoutés à la fiche d'un client par des apps situées « en dessous ».

``DETAIL_CLIENT`` : fournisseurs appelés avec ``(client, utilisateur)``. ``missions`` y
ajoute l'historique des missions du client.
"""

from apps.core.sections import RegistreSections

DETAIL_CLIENT = RegistreSections()
```

## Étape 3 — Administration, démarrage et fabrique de test

#### `apps/customers/admin.py`

*18 lignes*

```python
from django.contrib import admin

from .models import Client, Interaction


class InteractionInline(admin.TabularInline):
    model = Interaction
    extra = 0


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("raison_sociale", "ncc_nif", "contact_principal", "taux_tva")
    search_fields = ("raison_sociale", "ncc_nif")
    inlines = [InteractionInline]

    def get_queryset(self, request):
        return Client.objects.all()
```

#### `apps/customers/apps.py`

*21 lignes*

```python
from django.apps import AppConfig


class CustomersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.customers'
    label = 'customers'

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.audit.registry import audit_model

        from . import permissions
        from .models import Client

        audit_model(Client, module="CLIENTELE")
        enregistrer(
            EntreeMenu(
                "Clients", "customers:liste", "fa-handshake", permissions.CONSULTATION, ordre=15
            )
        )
```

#### `apps/customers/README.md`

*26 lignes* — customers

```markdown
# customers

Rôle : fiche client et historique commercial — cahier-des-charges.md:119-124.
TVA 18 % par défaut ; 0 % exige un motif d'exonération (contrainte en base).

Entités : `Client`, `Interaction`.

Services (`services.py`) : `creer_client`, `modifier_client` (TVA 0 % = motif obligatoire,
motif effacé si la TVA redevient positive, NCC / NIF unique même parmi les clients
supprimés, chargé clientèle = compte actif de ce rôle), `enregistrer_interaction` (résumé
obligatoire, date non future), `rechercher_clients`.

Délai de paiement : `delai_paiement_jours` (30 par défaut, entre 1 et 365), repris par ses
factures pour calculer l'échéance.

Interface (`views.py`, `templates/customers/`, montée sous `/clients/`) : portefeuille
filtrable (texte, « Mon portefeuille », exonérés de TVA) avec dernière interaction et
nombre de réclamations ; fiche avec historique commercial ; création et modification ;
ajout d'interactions. Accès : ADMIN et CHARGE_CLIENTELE gèrent, DIRECTION lit seulement.
Les missions du client s'affichent dans sa fiche via `customers.sections.DETAIL_CLIENT`
(fournisseur enregistré par `missions`).

Pas encore de gestion des devis ni des contrats à renouveler (indicateurs du tableau de
bord chargé clientèle, étape 5) ; les FINANCES ont accès à la facturation, pas à la fiche client.

Rapport imprimable des clients (bouton « Imprimer » sur la liste, mêmes filtres) : voir `apps/core/README.md` (`ImpressionListeMixin`).
```

#### `apps/customers/tests/factories.py`

*14 lignes*

```python
import factory

from apps.customers.models import Client


class ClientFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Client

    raison_sociale = factory.Sequence(lambda n: f"Société {n}")
    ncc_nif = factory.Sequence(lambda n: f"CI-{n:07d}A")
    contact_principal = "Awa Coulibaly"
    telephone = "+2250700000000"
    adresse = "Abidjan, Plateau"
```

## Étape 4 — Déclarer l'application et migrer

#### `config/settings/base.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/settings/base.py (avant)
+++ config/settings/base.py (après)
@@ -57,4 +57,5 @@
     "apps.hr",
     "apps.drivers",
+    "apps.customers",
 ]
 
```

```bash
python manage.py makemigrations customers
python manage.py migrate
```

**Résultat attendu :** `Create model Client`, `Create model Interaction`, `Add constraint …`, puis
`Applying customers.0001_initial... OK`.

## Vérifier le chapitre

Les tests de `customers` (formulaires, écrans) sont présentés avec les écrans au chapitre 19 ; pour l'instant on
vérifie à la main, dans le shell :

```bash
python manage.py check
python manage.py shell -c "from apps.customers import services as s; c = s.creer_client(raison_sociale='Cimaf CI', ncc_nif='CI-0001', contact_principal='M. Kouassi', telephone='0700000000', adresse='Abidjan'); print(c.raison_sociale, c.taux_tva, c.delai_paiement_jours)"
```

**Résultat attendu :** `Cimaf CI 18.00 30` (TVA à 18 % et délai à 30 jours **par défaut**).

Vérifiez maintenant que la base protège la règle de TVA, même si on contourne le service :

```bash
python manage.py shell -c "from apps.customers.models import Client; Client.objects.create(raison_sociale='ONG', ncc_nif='CI-0002', contact_principal='x', telephone='1', adresse='a', taux_tva=0)"
```

**Résultat attendu :** une erreur qui se termine par `CHECK constraint failed: client_tva_zero_requiert_motif`
(`IntegrityError`).

## Ce qu'il faut retenir

- Une règle importante se protège **deux fois** : dans le service (message clair) et dans la base
  (contrainte), pour qu'aucun chemin de code ne puisse la contourner.
- **Ne jamais utiliser `float`** pour de l'argent : `DecimalField` / `Decimal`.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 7 : app customers (portefeuille clients, TVA, délai de paiement, historique)"
```

---

[← Chapitre 6](06-drivers.md) · [Sommaire](README.md) · [Chapitre 8 →](08-fleet.md)
