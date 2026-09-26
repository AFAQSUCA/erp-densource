# Chapitre 6 — Les chauffeurs : l'app drivers

> 19 fichier(s) dans ce chapitre, 1984 lignes de code.

## Ce que vous allez construire

**`drivers`** : les **chauffeurs**. Un chauffeur est d'abord un employé (une fiche `Personnel` de `hr`) auquel
on ajoute ce qui est propre au métier : le **permis**, la **visite médicale** et un **statut de disponibilité**
(Disponible, En mission, En congé, Suspendu, Inactif).

Trois comportements automatiques à repérer :

| Comportement | Où |
|---|---|
| Recruter quelqu'un au poste « Chauffeur » **crée sa fiche chauffeur** tout seul | `signals.py` |
| Un congé qui **commence** met le chauffeur « En congé » ; à la fin, il redevient disponible | `signals.py` |
| **Alerte 30 jours avant** l'expiration du permis ou de la visite médicale | `services.py` (`chauffeurs_a_renouveler`) |

## Prérequis

- Chapitres 1 à 5 terminés.

## Notions Django de ce chapitre

- **`OneToOneField`** : une relation « un pour un » : une fiche chauffeur ↔ une fiche personnel. C'est le
  moyen Django de « prolonger » une table sans la modifier.
- **Signal `post_save` sur le modèle d'une autre app** : `drivers` écoute `hr`. Le sens des dépendances est
  respecté : `hr` ne sait rien de `drivers`.
- **`@receiver(post_save, sender=Personnel)`** : la fonction est appelée après chaque enregistrement d'un
  `Personnel`. Le paramètre `raw` est vrai lors du chargement de données brutes (à ignorer).
- **Propriétés** (`@property`) : `chauffeur.nom` lit le nom depuis la fiche personnel, sans le dupliquer.
- **`get_or_create`** : « récupère ou crée » : rend l'opération rejouable sans doublon.

## Étape 1 — Créer l'application

```bash
mkdir -p apps/drivers/tests
```

#### Fichiers vides à créer

Ces fichiers n'ont aucun contenu ; ils servent à faire de leur dossier un *paquet Python* (sans eux, `import apps.xxx` échouerait). Créez d'abord les dossiers, puis les fichiers :

```bash
mkdir -p apps\drivers apps\drivers\tests
touch apps/drivers/__init__.py
touch apps/drivers/tests/__init__.py
```

> Sous PowerShell, `mkdir -p` s'écrit `New-Item -ItemType Directory -Force <dossier>` et `touch fichier` s'écrit `New-Item -ItemType File -Force fichier`. Vous pouvez aussi créer ces fichiers avec votre éditeur.

## Étape 2 — Modèle, exceptions et services

#### `apps/drivers/models.py`

*128 lignes*

```python
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class StatutChauffeur(models.TextChoices):
    """5 statuts — cahier-des-charges.md:112-113."""

    DISPONIBLE = "DISPONIBLE", _("Disponible")
    EN_MISSION = "EN_MISSION", _("En mission")
    EN_CONGE = "EN_CONGE", _("En congé")
    SUSPENDU = "SUSPENDU", _("Suspendu")
    INACTIF = "INACTIF", _("Inactif")


class CategoriePermis(models.TextChoices):
    """Catégories de permis poids lourd — cahier-des-charges.md:110."""

    C = "C", "C"
    E = "E", "E"


class Chauffeur(BaseModel):
    """Extension 1-1 d'une fiche Personnel — cahier-des-charges.md:105-113.

    Matricule, nom et prénom viennent de ``Personnel`` (source de vérité,
    cahier-des-charges.md:107) et ne sont jamais dupliqués ici.
    """

    personnel = models.OneToOneField(
        "hr.Personnel",
        verbose_name=_("personnel"),
        on_delete=models.PROTECT,
        related_name="chauffeur",
    )
    telephone = models.CharField(_("téléphone"), max_length=20, blank=True)
    contact_urgence = models.CharField(_("contact d'urgence"), max_length=150, blank=True)
    numero_permis = models.CharField(_("n° de permis"), max_length=50, blank=True)
    categories_permis = models.JSONField(
        _("catégories de permis"), default=list, blank=True
    )
    date_expiration_permis = models.DateField(
        _("expiration du permis"), null=True, blank=True
    )
    date_expiration_visite_medicale = models.DateField(
        _("expiration de la visite médicale"), null=True, blank=True
    )
    statut = models.CharField(
        _("statut"),
        max_length=12,
        choices=StatutChauffeur.choices,
        default=StatutChauffeur.DISPONIBLE,
    )

    class Meta:
        verbose_name = _("chauffeur")
        verbose_name_plural = _("chauffeurs")
        ordering = ["personnel__matricule"]

    def __str__(self):
        return str(self.personnel)

    @property
    def matricule(self) -> str:
        return self.personnel.matricule

    @property
    def nom(self) -> str:
        return self.personnel.nom

    @property
    def prenom(self) -> str:
        return self.personnel.prenom

    def clean(self):
        valides = set(CategoriePermis.values)
        if not isinstance(self.categories_permis, list) or not set(
            self.categories_permis
        ) <= valides:
            raise ValidationError(
                {"categories_permis": _("Catégories autorisées : C, E.")}
            )


class Copilote(BaseModel):
    """Assistant du chauffeur pendant le trajet, pour les missions qui l'exigent.

    Fonction distincte du chauffeur (jamais chauffeur principal), extension 1-1 d'une fiche
    Personnel comme ``Chauffeur`` — retour de réunion entreprise. Pas de permis à suivre (il ne
    conduit pas) ; mêmes statuts que le chauffeur pour la disponibilité (affectation, congé).
    """

    personnel = models.OneToOneField(
        "hr.Personnel",
        verbose_name=_("personnel"),
        on_delete=models.PROTECT,
        related_name="copilote",
    )
    telephone = models.CharField(_("téléphone"), max_length=20, blank=True)
    contact_urgence = models.CharField(_("contact d'urgence"), max_length=150, blank=True)
    statut = models.CharField(
        _("statut"),
        max_length=12,
        choices=StatutChauffeur.choices,
        default=StatutChauffeur.DISPONIBLE,
    )

    class Meta:
        verbose_name = _("copilote")
        verbose_name_plural = _("copilotes")
        ordering = ["personnel__matricule"]

    def __str__(self):
        return str(self.personnel)

    @property
    def matricule(self) -> str:
        return self.personnel.matricule

    @property
    def nom(self) -> str:
        return self.personnel.nom

    @property
    def prenom(self) -> str:
        return self.personnel.prenom
```

- **Pas de doublon d'identité.** Le matricule, le nom et le prénom ne sont *pas* recopiés : ce sont des
  propriétés qui lisent la fiche `Personnel`. Une seule source de vérité.
- **`CategoriePermis`** : C ou E (poids lourds). `categories_permis` est une liste stockée en JSON ;
  le `clean()` du modèle refuse toute catégorie autre que C ou E.
- **Dates d'expiration** du permis et de la visite médicale : facultatives (`null=True`), car on peut
  recruter un chauffeur avant d'avoir ses papiers ; l'alerte à 30 jours ne concerne que les dates renseignées.

#### `apps/drivers/exceptions.py`

*10 lignes*

```python
class ChauffeurError(Exception):
    """Erreur métier sur un chauffeur (traduite en message par les écrans / l'API)."""


class CategorieInvalide(ChauffeurError):
    """Catégorie de permis hors C et E."""


class StatutNonModifiable(ChauffeurError):
    """Statut interdit à la main, ou chauffeur en mission ou en congé."""
```

#### `apps/drivers/services.py`

*293 lignes* — Logique métier des chauffeurs — conventions.md §2.

```python
"""Logique métier des chauffeurs — conventions.md §2."""

from __future__ import annotations

from datetime import date, timedelta

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.core.constants import DELAI_ALERTE_JOURS
from apps.core.search import filtrer_par_texte
from apps.core.services import etat_echeance
from apps.hr.models import Personnel

from .exceptions import CategorieInvalide, StatutNonModifiable
from .models import CategoriePermis, Chauffeur, Copilote, StatutChauffeur


@transaction.atomic
def assurer_fiche_chauffeur(personnel: Personnel) -> tuple[Chauffeur, bool]:
    """Garantit qu'un employé « Chauffeur » a une fiche chauffeur liée.

    cahier-des-charges.md:108 : poste « Chauffeur » → fiche créée
    automatiquement. Idempotent : ``all_objects`` évite de violer l'unicité
    du lien 1-1 si une fiche existe déjà, y compris supprimée logiquement
    (dans ce cas elle est restaurée plutôt que dupliquée).

    Retourne ``(fiche, creee)``.
    """
    fiche, creee = Chauffeur.all_objects.get_or_create(personnel=personnel)
    if fiche.is_deleted:
        fiche.restore()
    return fiche, creee


def changer_statut(chauffeur: Chauffeur, statut: str) -> Chauffeur:
    """Change le statut (Disponible, En mission, En congé, Suspendu, Inactif)."""
    if statut not in StatutChauffeur.values:
        raise ValueError(f"Statut chauffeur inconnu : {statut!r}")
    chauffeur.statut = statut
    chauffeur.save(update_fields=["statut", "updated_at"])
    return chauffeur


def chauffeurs_actifs() -> QuerySet[Chauffeur]:
    """Chauffeurs non inactifs, pour les listes de choix (ex. chauffeur habituel)."""
    return (
        Chauffeur.objects.select_related("personnel")
        .exclude(statut=StatutChauffeur.INACTIF)
        .order_by("personnel__nom", "personnel__prenom")
    )


def chauffeurs_disponibles() -> QuerySet[Chauffeur]:
    """Chauffeurs au statut « Disponible », pour l'affectation d'une mission."""
    return Chauffeur.objects.select_related("personnel").filter(
        statut=StatutChauffeur.DISPONIBLE
    )


def mettre_en_mission(chauffeur: Chauffeur) -> Chauffeur:
    """Départ d'une mission : statut « En mission » (cahier-des-charges.md:135)."""
    return changer_statut(chauffeur, StatutChauffeur.EN_MISSION)


def rappeler_de_mission(chauffeur: Chauffeur) -> Chauffeur:
    """Fin de mission : « Disponible », sauf statut changé entre-temps
    (En congé, Suspendu, Inactif), qui reste alors conservé."""
    if chauffeur.statut == StatutChauffeur.EN_MISSION:
        return changer_statut(chauffeur, StatutChauffeur.DISPONIBLE)
    return chauffeur


def mettre_en_conge(chauffeur: Chauffeur) -> Chauffeur:
    """Début d'un congé : statut « En congé »."""
    return changer_statut(chauffeur, StatutChauffeur.EN_CONGE)


def rappeler_de_conge(chauffeur: Chauffeur) -> Chauffeur:
    """Fin d'un congé : « Disponible », sauf si le statut a changé entre-temps
    (ex. Suspendu ou Inactif), qui reste alors conservé."""
    if chauffeur.statut == StatutChauffeur.EN_CONGE:
        return changer_statut(chauffeur, StatutChauffeur.DISPONIBLE)
    return chauffeur


# --- copilotes (assistants du chauffeur, missions qui l'exigent) ---


@transaction.atomic
def assurer_fiche_copilote(personnel: Personnel) -> tuple[Copilote, bool]:
    """Garantit qu'un employé « Copilote » a une fiche liée (même principe que le chauffeur)."""
    fiche, creee = Copilote.all_objects.get_or_create(personnel=personnel)
    if fiche.is_deleted:
        fiche.restore()
    return fiche, creee


def changer_statut_copilote(copilote: Copilote, statut: str) -> Copilote:
    if statut not in StatutChauffeur.values:
        raise ValueError(f"Statut copilote inconnu : {statut!r}")
    copilote.statut = statut
    copilote.save(update_fields=["statut", "updated_at"])
    return copilote


def copilotes_actifs() -> QuerySet[Copilote]:
    return (
        Copilote.objects.select_related("personnel")
        .exclude(statut=StatutChauffeur.INACTIF)
        .order_by("personnel__nom", "personnel__prenom")
    )


def copilotes_disponibles() -> QuerySet[Copilote]:
    """Copilotes au statut « Disponible », pour l'affectation d'une mission."""
    return Copilote.objects.select_related("personnel").filter(statut=StatutChauffeur.DISPONIBLE)


def mettre_en_mission_copilote(copilote: Copilote) -> Copilote:
    return changer_statut_copilote(copilote, StatutChauffeur.EN_MISSION)


def rappeler_copilote_de_mission(copilote: Copilote) -> Copilote:
    if copilote.statut == StatutChauffeur.EN_MISSION:
        return changer_statut_copilote(copilote, StatutChauffeur.DISPONIBLE)
    return copilote


def mettre_copilote_en_conge(copilote: Copilote) -> Copilote:
    return changer_statut_copilote(copilote, StatutChauffeur.EN_CONGE)


def rappeler_copilote_de_conge(copilote: Copilote) -> Copilote:
    if copilote.statut == StatutChauffeur.EN_CONGE:
        return changer_statut_copilote(copilote, StatutChauffeur.DISPONIBLE)
    return copilote


def chauffeurs_a_renouveler(
    *, aujourd_hui: date | None = None, jours: int = DELAI_ALERTE_JOURS
) -> QuerySet[Chauffeur]:
    """Chauffeurs dont permis OU visite médicale expire d'ici ``jours`` jours.

    Inclut les documents déjà expirés (alerte préventive à 30 jours,
    cahier-des-charges.md:95 et glossaire-metier.md:10-11).
    """
    limite = (aujourd_hui or timezone.localdate()) + timedelta(days=jours)
    return Chauffeur.objects.select_related("personnel").filter(
        Q(date_expiration_permis__lte=limite)
        | Q(date_expiration_visite_medicale__lte=limite)
    )


# --- fiche chauffeur (cahier-des-charges.md:105-113) ---

# Statuts posés à la main. « En mission » et « En congé » sont posés par les
# missions et les congés : les modifier à la main casserait ces workflows.
STATUTS_MANUELS = (
    StatutChauffeur.DISPONIBLE,
    StatutChauffeur.SUSPENDU,
    StatutChauffeur.INACTIF,
)
STATUTS_VERROUILLES = (StatutChauffeur.EN_MISSION, StatutChauffeur.EN_CONGE)


def chauffeurs_queryset() -> QuerySet[Chauffeur]:
    """Chauffeurs avec leur fiche personnel chargée."""
    return Chauffeur.objects.select_related("personnel")


def rechercher_chauffeurs(
    *,
    statut: str | None = None,
    recherche: str = "",
    a_renouveler: bool = False,
) -> QuerySet[Chauffeur]:
    """Chauffeurs filtrés par statut, texte (matricule, nom, prénom, n° de permis)
    et/ou permis ou visite médicale à renouveler."""
    chauffeurs = chauffeurs_queryset()
    if statut in StatutChauffeur.values:
        chauffeurs = chauffeurs.filter(statut=statut)
    chauffeurs = filtrer_par_texte(
        chauffeurs,
        recherche,
        "personnel__matricule",
        "personnel__nom",
        "personnel__prenom",
        "numero_permis",
    )
    if a_renouveler:
        chauffeurs = chauffeurs.filter(pk__in=chauffeurs_avec_echeance_proche())
    return chauffeurs.order_by("personnel__nom", "personnel__prenom")


def chauffeurs_avec_echeance_proche(
    *, aujourd_hui: date | None = None, jours: int = DELAI_ALERTE_JOURS
) -> set[int]:
    """Identifiants des chauffeurs dont le permis ou la visite médicale expire."""
    return set(
        chauffeurs_a_renouveler(aujourd_hui=aujourd_hui, jours=jours).values_list(
            "pk", flat=True
        )
    )


def etat_echeances(
    chauffeur: Chauffeur, *, aujourd_hui: date | None = None, jours: int = DELAI_ALERTE_JOURS
) -> list[dict]:
    """Situation du permis et de la visite médicale (cahier-des-charges.md:110-111)."""
    lignes = []
    for libelle, expiration in (
        ("Permis de conduire", chauffeur.date_expiration_permis),
        ("Visite médicale", chauffeur.date_expiration_visite_medicale),
    ):
        etat, restants = etat_echeance(expiration, aujourd_hui=aujourd_hui, jours=jours)
        lignes.append(
            {
                "libelle": libelle,
                "date_expiration": expiration,
                "etat": etat,
                "jours_restants": restants,
            }
        )
    return lignes


@transaction.atomic
def modifier_chauffeur(
    chauffeur: Chauffeur,
    *,
    telephone: str = "",
    contact_urgence: str = "",
    numero_permis: str = "",
    categories_permis: list[str] | None = None,
    date_expiration_permis: date | None = None,
    date_expiration_visite_medicale: date | None = None,
) -> Chauffeur:
    """Met à jour les informations propres au chauffeur.

    Matricule, nom et prénom viennent de la fiche du personnel (source de vérité,
    cahier-des-charges.md:107) : ils ne se modifient pas ici. Les catégories de
    permis (C, E) sont validées, sans doublon, triées.
    """
    categories = sorted(set(categories_permis or []))
    inconnues = [c for c in categories if c not in CategoriePermis.values]
    if inconnues:
        raise CategorieInvalide(
            f"Catégorie(s) de permis inconnue(s) : {', '.join(inconnues)} (autorisées : C, E)."
        )
    type(chauffeur)._base_manager.select_for_update().filter(pk=chauffeur.pk).first()
    chauffeur.refresh_from_db()
    chauffeur.telephone = telephone.strip()
    chauffeur.contact_urgence = contact_urgence.strip()
    chauffeur.numero_permis = numero_permis.strip()
    chauffeur.categories_permis = categories
    chauffeur.date_expiration_permis = date_expiration_permis
    chauffeur.date_expiration_visite_medicale = date_expiration_visite_medicale
    chauffeur.save()
    return chauffeur


@transaction.atomic
def changer_statut_manuel(chauffeur: Chauffeur, statut: str) -> Chauffeur:
    """Suspend, désactive ou remet un chauffeur « Disponible » à la main.

    Refusé si le chauffeur est en mission ou en congé (statuts posés par les
    missions et les congés), ou si ``statut`` n'est pas un statut manuel.
    """
    if statut not in STATUTS_MANUELS:
        raise StatutNonModifiable(
            "Seuls les statuts Disponible, Suspendu et Inactif se posent à la main."
        )
    type(chauffeur)._base_manager.select_for_update().filter(pk=chauffeur.pk).first()
    chauffeur.refresh_from_db()
    if chauffeur.statut in STATUTS_VERROUILLES:
        raise StatutNonModifiable(
            f"Le chauffeur est « {chauffeur.get_statut_display()} » : ce statut est géré "
            "par les missions et les congés."
        )
    return changer_statut(chauffeur, statut)


def chauffeur_de(utilisateur) -> Chauffeur | None:
    """Fiche chauffeur du compte (via sa fiche du personnel), ou ``None``.

    Sert à l'espace mobile : un chauffeur n'agit que sur ses propres missions.
    """
    fiche = getattr(utilisateur, "personnel", None)
    if fiche is None:
        return None
    return getattr(fiche, "chauffeur", None)
```

Lisez en particulier :

- **`assurer_fiche_chauffeur`** : crée la fiche si elle manque (utilisée par le signal ; rejouable).
- **`mettre_en_mission` / `rappeler_de_mission`**, **`mettre_en_conge` / `rappeler_de_conge`** : les
  changements d'état automatiques. `missions` et `hr` s'en serviront.
- **`changer_statut_manuel`** : on ne peut suspendre, désactiver ou réactiver qu'à la main ; « En mission » et
  « En congé » sont **posés par le système** et refusés ici (`StatutNonModifiable`).
- **`chauffeur_de(utilisateur)`** : retrouve la fiche chauffeur d'un compte : c'est ce qui permet à l'espace
  mobile de n'afficher que *ses* missions (chapitre 27).
- **`etat_echeances`** utilise `etat_echeance` du chapitre 2 pour dire « valide / à renouveler / expiré ».

#### `apps/drivers/signals.py`

*52 lignes*

```python
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.hr.models import Conge, Personnel, StatutConge

from . import services
from .models import Chauffeur, Copilote


@receiver(post_save, sender=Personnel)
def creer_fiche_chauffeur(sender, instance, raw=False, **kwargs):
    """Poste « Chauffeur » → fiche chauffeur créée (cahier-des-charges.md:108).

    C'est ``drivers`` qui écoute ``hr`` (et non l'inverse) pour respecter le
    sens des dépendances de architecture.md:161-163.
    """
    if raw or instance.is_deleted:
        return
    if instance.est_chauffeur:
        services.assurer_fiche_chauffeur(instance)


@receiver(post_save, sender=Personnel)
def creer_fiche_copilote(sender, instance, raw=False, **kwargs):
    """Poste « Copilote » → fiche copilote créée, même principe que le chauffeur."""
    if raw or instance.is_deleted:
        return
    if instance.est_copilote:
        services.assurer_fiche_copilote(instance)


@receiver(post_save, sender=Conge)
def aligner_statut_chauffeur_sur_conge(sender, instance, raw=False, **kwargs):
    """Congé d'un chauffeur en cours → « En congé » (cahier-des-charges.md:216).

    Appliqué au démarrage effectif du congé (EN_COURS) et non à l'approbation,
    pour ne pas immobiliser le chauffeur des semaines avant son départ.
    """
    if raw or instance.statut not in (StatutConge.EN_COURS, StatutConge.TERMINE):
        return
    fiche = Chauffeur.objects.filter(personnel_id=instance.employe_id).first()
    if fiche is not None:
        if instance.statut == StatutConge.EN_COURS:
            services.mettre_en_conge(fiche)
        else:
            services.rappeler_de_conge(fiche)
    copilote = Copilote.objects.filter(personnel_id=instance.employe_id).first()
    if copilote is not None:
        if instance.statut == StatutConge.EN_COURS:
            services.mettre_copilote_en_conge(copilote)
        else:
            services.rappeler_copilote_de_conge(copilote)
```

Les deux abonnements sont la raison d'être de ce fichier. Notez le commentaire : c'est **`drivers` qui écoute
`hr`**, pas l'inverse.

#### `apps/drivers/permissions.py`

*14 lignes* — Qui peut consulter et gérer les chauffeurs.

```python
"""Qui peut consulter et gérer les chauffeurs.

Cahier-des-charges.md:44-55 : la DIRECTION assure la « gestion flotte + chauffeurs » ;
la RH a la « gestion complète des employés » (embauche, licenciement), dont les
chauffeurs, qui sont des employés (cahier-des-charges.md:105-108). L'ADMIN a tous les
droits. Le PARCAUTO, les FINANCES et la CHARGE_CLIENTELE n'ont pas accès.

Suspendre ou désactiver un chauffeur relève des mêmes rôles que la gestion de la fiche.
"""

from apps.accounts.models import Role

CONSULTATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.RH})
MODIFICATION = frozenset({Role.ADMIN, Role.DIRECTION, Role.RH})
```

## Étape 3 — Administration, démarrage et tests

#### `apps/drivers/admin.py`

*23 lignes*

```python
from django.contrib import admin

from .models import Chauffeur, Copilote


@admin.register(Chauffeur)
class ChauffeurAdmin(admin.ModelAdmin):
    list_display = ("personnel", "statut", "date_expiration_permis")
    list_filter = ("statut",)
    search_fields = ("personnel__matricule", "personnel__nom", "numero_permis")

    def get_queryset(self, request):
        return Chauffeur.objects.select_related("personnel")


@admin.register(Copilote)
class CopiloteAdmin(admin.ModelAdmin):
    list_display = ("personnel", "statut")
    list_filter = ("statut",)
    search_fields = ("personnel__matricule", "personnel__nom")

    def get_queryset(self, request):
        return Copilote.objects.select_related("personnel")
```

#### `apps/drivers/apps.py`

*21 lignes*

```python
from django.apps import AppConfig


class DriversConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.drivers'
    label = 'drivers'

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.audit.registry import audit_model

        from . import permissions, signals  # noqa: F401
        from .models import Chauffeur

        audit_model(Chauffeur, module="CHAUFFEUR")
        enregistrer(
            EntreeMenu(
                "Chauffeurs", "drivers:liste", "fa-id-card", permissions.CONSULTATION, ordre=30
            )
        )
```

Important : `ready()` doit **importer `signals`** pour que les abonnements existent. C'est l'usage standard
de Django.

#### `apps/drivers/tests/factories.py`

*44 lignes*

```python
import factory

from apps.drivers.models import Chauffeur, Copilote
from apps.hr.tests.factories import PersonnelFactory


class ChauffeurFactory(factory.django.DjangoModelFactory):
    """Crée un Personnel « Chauffeur » puis récupère la fiche.

    Le signal de ``drivers`` crée déjà la fiche à la création du Personnel ;
    la factory la récupère et lui applique les attributs demandés.
    """

    class Meta:
        model = Chauffeur

    personnel = factory.SubFactory(PersonnelFactory, poste="Chauffeur")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        personnel = kwargs.pop("personnel")
        fiche, _ = model_class.all_objects.get_or_create(personnel=personnel)
        for champ, valeur in kwargs.items():
            setattr(fiche, champ, valeur)
        fiche.save()
        return fiche


class CopiloteFactory(factory.django.DjangoModelFactory):
    """Crée un Personnel « Copilote » puis récupère la fiche (même principe que ChauffeurFactory)."""

    class Meta:
        model = Copilote

    personnel = factory.SubFactory(PersonnelFactory, poste="Copilote")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        personnel = kwargs.pop("personnel")
        fiche, _ = model_class.all_objects.get_or_create(personnel=personnel)
        for champ, valeur in kwargs.items():
            setattr(fiche, champ, valeur)
        fiche.save()
        return fiche
```

#### `apps/drivers/README.md`

*30 lignes* — drivers

```markdown
# drivers

Rôle : extension 1-1 de `Personnel` pour les chauffeurs — cahier-des-charges.md:105-113.
La fiche est créée automatiquement (signal) quand le poste est « Chauffeur ».
Dépend de `hr` (jamais l'inverse).

Entités : `Chauffeur`. Services : `assurer_fiche_chauffeur`, `changer_statut`,
`chauffeurs_a_renouveler` (alerte 30 jours permis / visite médicale).

Entité `Copilote` (retour d'une réunion entreprise) : assistant du chauffeur pendant le
trajet, exigé sur certains voyages — fonction/fiche distincte du chauffeur (jamais chauffeur
principal), même mécanisme d'auto-création (poste « Copilote » sur `Personnel`) et mêmes
statuts de disponibilité (`StatutChauffeur`, y compris la synchronisation avec les congés).
Aucune règle automatique ne décide qu'une mission exige un copilote : c'est une décision
humaine du Parc Auto au moment de l'affectation (`missions.forms.AffectationForm`).
Services : `assurer_fiche_copilote`, `changer_statut_copilote`, `copilotes_disponibles`,
`copilotes_actifs`, `mettre_en_mission_copilote` / `rappeler_copilote_de_mission`,
`mettre_copilote_en_conge` / `rappeler_copilote_de_conge`. Géré pour l'instant via l'admin
Django (`CopiloteAdmin`) — pas d'écran dédié, contrairement au chauffeur.

Interface (`views.py`, `templates/drivers/`) : liste filtrée (statut, texte, permis ou
visite à renouveler), fiche avec l'état du permis et de la visite médicale (alerte à
30 jours), modification des informations propres au chauffeur, suspension / désactivation
/ réactivation. Accès : ADMIN, DIRECTION, RH (`permissions.py`). Matricule, nom et
prénom viennent de la fiche du personnel et ne se modifient pas ici ; « En mission » et
« En congé » sont posés par les missions et les congés et ne se changent pas à la main.
Services ajoutés : `rechercher_chauffeurs`, `etat_echeances`, `modifier_chauffeur`,
`changer_statut_manuel`, `chauffeurs_avec_echeance_proche`.

Rapport imprimable des chauffeurs (bouton « Imprimer » sur la liste, mêmes filtres) : voir `apps/core/README.md` (`ImpressionListeMixin`).
```

#### `apps/drivers/tests/test_copilote.py`

*81 lignes* — Fiche copilote : création automatique, statuts (retour réunion — avenant § R... copilotes).

```python
"""Fiche copilote : création automatique, statuts (retour réunion — avenant § R... copilotes)."""

import pytest

from apps.drivers import services
from apps.drivers.models import Copilote, StatutChauffeur
from apps.hr.tests.factories import PersonnelFactory

from .factories import CopiloteFactory

pytestmark = pytest.mark.django_db


def test_un_employe_copilote_recoit_automatiquement_une_fiche():
    personnel = PersonnelFactory(poste="Copilote")

    fiche = Copilote.objects.get(personnel=personnel)
    assert fiche.statut == StatutChauffeur.DISPONIBLE


def test_un_employe_non_copilote_ne_recoit_pas_de_fiche():
    PersonnelFactory(poste="Comptable")

    assert not Copilote.objects.exists()


def test_assurer_fiche_copilote_est_idempotent():
    personnel = PersonnelFactory(poste="Copilote")

    fiche, creee = services.assurer_fiche_copilote(personnel)

    assert creee is False
    assert Copilote.objects.filter(personnel=personnel).count() == 1


def test_copilotes_disponibles_ne_retourne_que_les_disponibles():
    libre = CopiloteFactory()
    CopiloteFactory(statut=StatutChauffeur.SUSPENDU)
    CopiloteFactory(statut=StatutChauffeur.EN_MISSION)

    assert list(services.copilotes_disponibles()) == [libre]


def test_copilotes_actifs_exclut_les_inactifs():
    actif = CopiloteFactory()
    CopiloteFactory(statut=StatutChauffeur.INACTIF)

    assert list(services.copilotes_actifs()) == [actif]


def test_mettre_en_mission_puis_rappeler_de_mission():
    fiche = CopiloteFactory()

    services.mettre_en_mission_copilote(fiche)
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.EN_MISSION

    services.rappeler_copilote_de_mission(fiche)
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE


def test_rappeler_de_mission_conserve_un_statut_change_entre_temps():
    fiche = CopiloteFactory(statut=StatutChauffeur.SUSPENDU)

    services.rappeler_copilote_de_mission(fiche)

    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.SUSPENDU


def test_mettre_en_conge_puis_rappeler_de_conge():
    fiche = CopiloteFactory()

    services.mettre_copilote_en_conge(fiche)
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.EN_CONGE

    services.rappeler_copilote_de_conge(fiche)
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE
```

#### `apps/drivers/tests/test_fiche.py`

*232 lignes* — Fiche chauffeur : recherche, échéances, modification, statut manuel.

```python
"""Fiche chauffeur : recherche, échéances, modification, statut manuel."""

from datetime import date

import pytest

from apps.audit.models import AuditLog
from apps.drivers import services
from apps.drivers.exceptions import CategorieInvalide, StatutNonModifiable
from apps.drivers.models import StatutChauffeur

from .factories import ChauffeurFactory

pytestmark = pytest.mark.django_db

AUJOURDHUI = date(2026, 9, 20)


# --- recherche ---


def test_rechercher_par_statut():
    libre = ChauffeurFactory()
    ChauffeurFactory(statut=StatutChauffeur.SUSPENDU)

    assert list(services.rechercher_chauffeurs(statut=StatutChauffeur.DISPONIBLE)) == [libre]


def test_rechercher_par_nom_prenom_matricule_ou_permis():
    cible = ChauffeurFactory(
        personnel__nom="Diomandé",
        personnel__prenom="Seydou",
        personnel__matricule="CH-042",
        numero_permis="PC-998877",
    )
    ChauffeurFactory()

    for terme in ("diomand", "seydou", "ch-042", "998877"):
        assert list(services.rechercher_chauffeurs(recherche=terme)) == [cible], terme


def test_rechercher_ignore_un_statut_inconnu_et_les_espaces():
    ChauffeurFactory()

    assert services.rechercher_chauffeurs(statut="???", recherche="   ").count() == 1


def test_rechercher_trie_par_nom_puis_prenom():
    b = ChauffeurFactory(personnel__nom="Bamba", personnel__prenom="Issa")
    a2 = ChauffeurFactory(personnel__nom="Adou", personnel__prenom="Zoé")
    a1 = ChauffeurFactory(personnel__nom="Adou", personnel__prenom="Awa")

    assert list(services.rechercher_chauffeurs()) == [a1, a2, b]


def test_rechercher_les_chauffeurs_a_renouveler():
    from datetime import timedelta

    from django.utils import timezone

    aujourdhui = timezone.localdate()
    lointain = aujourdhui + timedelta(days=1800)
    proche = ChauffeurFactory(
        date_expiration_permis=lointain, date_expiration_visite_medicale=aujourdhui
    )
    ChauffeurFactory(date_expiration_permis=lointain)

    resultat = services.rechercher_chauffeurs(a_renouveler=True)

    assert list(resultat) == [proche]


def test_chauffeurs_avec_echeance_proche_retourne_les_identifiants():
    proche = ChauffeurFactory(date_expiration_permis=date(2026, 10, 10))
    ChauffeurFactory(date_expiration_permis=date(2027, 6, 1))

    assert services.chauffeurs_avec_echeance_proche(aujourd_hui=AUJOURDHUI) == {proche.pk}


# --- échéances ---


def test_etat_echeances_couvre_permis_et_visite_medicale():
    fiche = ChauffeurFactory(
        date_expiration_permis=date(2026, 9, 1),
        date_expiration_visite_medicale=date(2026, 10, 1),
    )

    permis, visite = services.etat_echeances(fiche, aujourd_hui=AUJOURDHUI)

    assert (permis["libelle"], permis["etat"], permis["jours_restants"]) == (
        "Permis de conduire",
        "EXPIRE",
        -19,
    )
    assert (visite["libelle"], visite["etat"], visite["jours_restants"]) == (
        "Visite médicale",
        "A_RENOUVELER",
        11,
    )


def test_etat_echeances_signale_les_dates_non_renseignees():
    fiche = ChauffeurFactory()

    assert [e["etat"] for e in services.etat_echeances(fiche, aujourd_hui=AUJOURDHUI)] == [
        "MANQUANT",
        "MANQUANT",
    ]


# --- modification de la fiche ---


def test_modifier_chauffeur_enregistre_les_informations():
    fiche = ChauffeurFactory()

    services.modifier_chauffeur(
        fiche,
        telephone=" +2250700112233 ",
        contact_urgence="Awa Traoré - 0701020304",
        numero_permis="PC-123456",
        categories_permis=["E", "C"],
        date_expiration_permis=date(2029, 3, 1),
        date_expiration_visite_medicale=date(2027, 3, 1),
    )

    fiche.refresh_from_db()
    assert fiche.telephone == "+2250700112233"
    assert fiche.contact_urgence == "Awa Traoré - 0701020304"
    assert fiche.numero_permis == "PC-123456"
    assert fiche.categories_permis == ["C", "E"]  # triées
    assert fiche.date_expiration_permis == date(2029, 3, 1)


def test_modifier_chauffeur_retire_les_doublons_de_categories():
    fiche = ChauffeurFactory()

    services.modifier_chauffeur(fiche, categories_permis=["C", "C", "E"])

    fiche.refresh_from_db()
    assert fiche.categories_permis == ["C", "E"]


def test_modifier_chauffeur_refuse_une_categorie_inconnue_et_ne_change_rien():
    fiche = ChauffeurFactory(telephone="0700000000")

    with pytest.raises(CategorieInvalide, match="Z"):
        services.modifier_chauffeur(fiche, telephone="0799999999", categories_permis=["C", "Z"])

    fiche.refresh_from_db()
    assert fiche.telephone == "0700000000"


def test_modifier_chauffeur_peut_vider_les_champs_facultatifs():
    fiche = ChauffeurFactory(
        telephone="0700000000",
        numero_permis="X",
        categories_permis=["C"],
        date_expiration_permis=date(2029, 1, 1),
    )

    services.modifier_chauffeur(fiche)

    fiche.refresh_from_db()
    assert (fiche.telephone, fiche.numero_permis, fiche.categories_permis) == ("", "", [])
    assert fiche.date_expiration_permis is None


def test_modifier_chauffeur_ne_touche_ni_au_statut_ni_a_l_identite():
    fiche = ChauffeurFactory(statut=StatutChauffeur.SUSPENDU, personnel__nom="Kouyaté")

    services.modifier_chauffeur(fiche, telephone="0700000000")

    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.SUSPENDU
    assert fiche.personnel.nom == "Kouyaté"


def test_la_modification_de_la_fiche_est_auditee():
    fiche = ChauffeurFactory()

    services.modifier_chauffeur(fiche, numero_permis="PC-1")

    entree = AuditLog.objects.filter(
        entite="Chauffeur", entite_id=fiche.pk, action="UPDATE"
    ).latest("date_heure")
    assert entree.nouvelle_valeur["numero_permis"] == "PC-1"


# --- statut manuel ---


@pytest.mark.parametrize(
    ("depart", "arrivee"),
    [
        (StatutChauffeur.DISPONIBLE, StatutChauffeur.SUSPENDU),
        (StatutChauffeur.DISPONIBLE, StatutChauffeur.INACTIF),
        (StatutChauffeur.SUSPENDU, StatutChauffeur.DISPONIBLE),
        (StatutChauffeur.INACTIF, StatutChauffeur.DISPONIBLE),
        (StatutChauffeur.SUSPENDU, StatutChauffeur.INACTIF),
    ],
)
def test_changer_statut_manuel_entre_statuts_manuels(depart, arrivee):
    fiche = ChauffeurFactory(statut=depart)

    services.changer_statut_manuel(fiche, arrivee)

    fiche.refresh_from_db()
    assert fiche.statut == arrivee


@pytest.mark.parametrize("verrouille", [StatutChauffeur.EN_MISSION, StatutChauffeur.EN_CONGE])
def test_un_chauffeur_en_mission_ou_en_conge_ne_se_modifie_pas_a_la_main(verrouille):
    fiche = ChauffeurFactory(statut=verrouille)

    with pytest.raises(StatutNonModifiable, match="missions et les congés"):
        services.changer_statut_manuel(fiche, StatutChauffeur.SUSPENDU)

    fiche.refresh_from_db()
    assert fiche.statut == verrouille


@pytest.mark.parametrize("cible", [StatutChauffeur.EN_MISSION, StatutChauffeur.EN_CONGE, "VOLANT"])
def test_on_ne_pose_pas_a_la_main_les_statuts_geres_par_les_workflows(cible):
    fiche = ChauffeurFactory()

    with pytest.raises(StatutNonModifiable, match="Disponible, Suspendu et Inactif"):
        services.changer_statut_manuel(fiche, cible)

    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE
```

#### `apps/drivers/tests/test_models.py`

*34 lignes*

```python
import pytest
from django.core.exceptions import ValidationError

from .factories import ChauffeurFactory

pytestmark = pytest.mark.django_db


def test_matricule_nom_prenom_viennent_de_personnel():
    fiche = ChauffeurFactory(personnel__matricule="MAT-77", personnel__nom="Diallo")

    assert fiche.matricule == "MAT-77"
    assert fiche.nom == "Diallo"
    assert fiche.prenom == "Jean"


def test_categories_permis_c_et_e_acceptees():
    fiche = ChauffeurFactory(categories_permis=["C", "E"])

    fiche.clean()


def test_categorie_permis_inconnue_refusee():
    fiche = ChauffeurFactory(categories_permis=["C", "Z"])

    with pytest.raises(ValidationError):
        fiche.clean()


def test_categories_permis_doit_etre_une_liste():
    fiche = ChauffeurFactory(categories_permis="C")

    with pytest.raises(ValidationError):
        fiche.clean()
```

#### `apps/drivers/tests/test_services.py`

*150 lignes*

```python
from datetime import date

import pytest

from apps.drivers import services
from apps.drivers.models import Chauffeur, StatutChauffeur
from apps.hr.tests.factories import PersonnelFactory

from .factories import ChauffeurFactory

pytestmark = pytest.mark.django_db


# --- création automatique de la fiche (cahier-des-charges.md:108) ---


def test_poste_chauffeur_cree_automatiquement_la_fiche():
    personnel = PersonnelFactory(poste="Chauffeur")

    assert Chauffeur.objects.filter(personnel=personnel).exists()


def test_autre_poste_ne_cree_pas_de_fiche_chauffeur():
    personnel = PersonnelFactory(poste="Comptable")

    assert not Chauffeur.objects.filter(personnel=personnel).exists()


def test_passage_au_poste_chauffeur_cree_la_fiche_plus_tard():
    personnel = PersonnelFactory(poste="Magasinier")

    personnel.poste = "Chauffeur"
    personnel.save()

    assert Chauffeur.objects.filter(personnel=personnel).exists()


def test_assurer_fiche_chauffeur_est_idempotent():
    personnel = PersonnelFactory(poste="Chauffeur")

    fiche, creee = services.assurer_fiche_chauffeur(personnel)

    assert creee is False
    assert Chauffeur.all_objects.filter(personnel=personnel).count() == 1
    assert fiche.personnel == personnel


def test_assurer_fiche_chauffeur_restaure_une_fiche_supprimee_logiquement():
    fiche = ChauffeurFactory()
    fiche.delete()

    restauree, creee = services.assurer_fiche_chauffeur(fiche.personnel)

    assert creee is False
    assert restauree.is_deleted is False
    assert Chauffeur.objects.filter(pk=fiche.pk).exists()


def test_personnel_supprime_ne_cree_pas_de_fiche():
    personnel = PersonnelFactory(poste="Chauffeur")
    Chauffeur.all_objects.filter(personnel=personnel).delete()
    personnel.delete()

    assert not Chauffeur.all_objects.filter(personnel=personnel).exists()


# --- statuts ---


def test_changer_statut_enregistre_le_nouveau_statut():
    fiche = ChauffeurFactory()

    services.changer_statut(fiche, StatutChauffeur.EN_CONGE)

    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.EN_CONGE


def test_changer_statut_refuse_un_statut_inconnu():
    fiche = ChauffeurFactory()

    with pytest.raises(ValueError):
        services.changer_statut(fiche, "VOLANT")


# --- alertes 30 jours ---


def test_chauffeurs_a_renouveler_inclut_permis_qui_expire_dans_30_jours():
    proche = ChauffeurFactory(date_expiration_permis=date(2026, 10, 10))
    lointain = ChauffeurFactory(date_expiration_permis=date(2027, 6, 1))

    resultat = services.chauffeurs_a_renouveler(aujourd_hui=date(2026, 9, 20))

    assert proche in resultat
    assert lointain not in resultat


def test_chauffeurs_a_renouveler_inclut_visite_medicale_et_documents_expires():
    visite = ChauffeurFactory(date_expiration_visite_medicale=date(2026, 9, 25))
    expire = ChauffeurFactory(date_expiration_permis=date(2026, 1, 1))

    resultat = services.chauffeurs_a_renouveler(aujourd_hui=date(2026, 9, 20))

    assert visite in resultat
    assert expire in resultat


def test_chauffeurs_a_renouveler_ignore_les_dates_non_renseignees():
    sans_dates = ChauffeurFactory()

    resultat = services.chauffeurs_a_renouveler(aujourd_hui=date(2026, 9, 20))

    assert sans_dates not in resultat


# --- missions ---


def test_mettre_en_mission_puis_rappeler_remet_disponible():
    fiche = ChauffeurFactory()

    services.mettre_en_mission(fiche)
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.EN_MISSION

    services.rappeler_de_mission(fiche)
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE


@pytest.mark.parametrize(
    "statut",
    [StatutChauffeur.EN_CONGE, StatutChauffeur.SUSPENDU, StatutChauffeur.INACTIF],
)
def test_rappeler_de_mission_conserve_un_autre_statut(statut):
    fiche = ChauffeurFactory(statut=statut)

    services.rappeler_de_mission(fiche)

    fiche.refresh_from_db()
    assert fiche.statut == statut


def test_chauffeurs_disponibles_exclut_les_autres_statuts():
    libre = ChauffeurFactory()
    ChauffeurFactory(statut=StatutChauffeur.EN_CONGE)
    ChauffeurFactory(statut=StatutChauffeur.EN_MISSION)

    assert list(services.chauffeurs_disponibles()) == [libre]
```

#### `apps/hr/tests/test_comptes_demo.py`

*85 lignes* — Commande ``creer_comptes_demo`` : un compte par rôle, hiérarchie utilisable pour les congés.

```python
"""Commande ``creer_comptes_demo`` : un compte par rôle, hiérarchie utilisable pour les congés."""

from datetime import date, datetime
from datetime import timezone as dt_timezone
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import Role, User
from apps.drivers.models import Chauffeur
from apps.hr import services
from apps.hr.models import Personnel, StatutConge

pytestmark = pytest.mark.django_db

MAINTENANT = datetime(2026, 9, 1, 8, 0, tzinfo=dt_timezone.utc)


def _lancer(settings, *args):
    settings.DEBUG = True
    sortie = StringIO()
    call_command("creer_comptes_demo", *args, stdout=sortie)
    return sortie.getvalue()


def test_la_commande_est_refusee_hors_developpement(settings):
    settings.DEBUG = False

    with pytest.raises(CommandError, match="développement"):
        call_command("creer_comptes_demo", stdout=StringIO())
    assert not User.objects.exists()


def test_un_compte_par_role_avec_le_mot_de_passe_donne(settings):
    sortie = _lancer(settings, "--mot-de-passe", "Essai-2026!")

    assert {u.role for u in User.objects.all()} == set(Role.values)
    assert User.objects.count() == 7
    assert all(u.check_password("Essai-2026!") for u in User.objects.all())
    assert "Essai-2026!" in sortie
    assert User.objects.get(username="demo_admin").is_staff
    assert not User.objects.get(username="demo_rh").is_staff


def test_un_mot_de_passe_est_genere_quand_il_n_est_pas_donne(settings):
    sortie = _lancer(settings)

    mot_de_passe = sortie.rsplit(":", 1)[1].strip()
    assert len(mot_de_passe) >= 12
    assert User.objects.get(username="demo_rh").check_password(mot_de_passe)


def test_la_commande_est_rejouable_sans_doublon(settings):
    _lancer(settings, "--mot-de-passe", "Premier-1")
    _lancer(settings, "--mot-de-passe", "Second-2")

    assert User.objects.count() == 7 and Personnel.objects.count() == 7
    assert User.objects.get(username="demo_rh").check_password("Second-2")


def test_les_fiches_suivent_la_hierarchie_et_le_chauffeur_a_sa_fiche(settings):
    _lancer(settings)

    direction = Personnel.objects.get(utilisateur__username="demo_direction")
    assert direction.superieur is None
    assert Personnel.objects.get(utilisateur__username="demo_rh").superieur == direction
    parc = Personnel.objects.get(utilisateur__username="demo_parcauto")
    assert Personnel.objects.get(utilisateur__username="demo_chauffeur").superieur == parc
    assert Chauffeur.objects.filter(personnel__utilisateur__username="demo_chauffeur").exists()


def test_le_workflow_de_conges_fonctionne_avec_ces_comptes(settings):
    _lancer(settings)
    employe = Personnel.objects.get(utilisateur__username="demo_charge")
    conge = services.demander_conge(
        employe, date_debut=date(2026, 10, 5), date_fin=date(2026, 10, 9), motif="Essai",
        maintenant=MAINTENANT,
    )

    services.valider_n1(conge, User.objects.get(username="demo_direction"), maintenant=MAINTENANT)
    services.valider_n2(conge, User.objects.get(username="demo_rh"))

    assert conge.statut == StatutConge.APPROUVE
```

#### `apps/hr/tests/test_conges.py`

*496 lignes* — Workflow de congés en 3 niveaux — cahier-des-charges.md:211-221.

```python
"""Workflow de congés en 3 niveaux — cahier-des-charges.md:211-221.

N1 = supérieur hiérarchique direct de l'employé ; N2 = RH ; décompte en jours
ouvrés (lundi-vendredi, hors jours fériés) sur un droit annuel de 26 jours
(avenant-separation-des-taches.md § R7).
"""

from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.audit.models import ActionChoices, AuditLog
from apps.drivers import services as drivers_services
from apps.drivers.models import Chauffeur, Copilote, StatutChauffeur
from apps.hr import services
from apps.hr.exceptions import (
    ActionNonAutorisee,
    CongeError,
    SoldeInsuffisant,
    TransitionInterdite,
)
from apps.hr.models import Conge, Departement, StatutConge

from .factories import PersonnelFactory

pytestmark = pytest.mark.django_db

MAINTENANT = datetime(2026, 9, 1, 8, 0, tzinfo=dt_timezone.utc)
DEBUT, FIN = date(2026, 10, 5), date(2026, 10, 9)  # lundi-vendredi = 5 jours ouvrés


def _hierarchie(poste="Dispatcheur"):
    """Un employé et le compte utilisateur de son supérieur direct.

    Le supérieur est volontairement dans un autre département : la validation
    N1 suit la hiérarchie, pas le département.
    """
    user = UserFactory(role=Role.PARCAUTO)
    chef = PersonnelFactory(
        poste="Chef", departement=Departement.DIRECTION, utilisateur=user
    )
    employe = PersonnelFactory(
        poste=poste, departement=Departement.EXPLOITATION, superieur=chef
    )
    return employe, user


def _rh():
    return UserFactory(role=Role.RH)


def _demande(hierarchie=None, debut=DEBUT, fin=FIN):
    employe, superieur = hierarchie or _hierarchie()
    conge = services.demander_conge(
        employe, date_debut=debut, date_fin=fin, motif="Repos", maintenant=MAINTENANT
    )
    return conge, superieur


def _delai_en_cours(conge):
    """Le délai de décision n'est pas dépassé (la Direction ne peut donc pas se substituer au validateur)."""
    Conge.objects.filter(pk=conge.pk).update(date_limite_n1=timezone.now() + timedelta(hours=24))
    conge.refresh_from_db()


def _approuve(hierarchie=None, debut=DEBUT, fin=FIN):
    conge, superieur = _demande(hierarchie, debut, fin)
    services.valider_n1(conge, superieur)
    services.valider_n2(conge, _rh())
    return conge


def _disponible(employe, annee=2026):
    return services.droits_conges(employe, annee)["disponible"]


# --- étape 1 : demande ---


def test_demande_cree_un_conge_au_statut_demande_en_jours_ouvres():
    conge, _ = _demande()

    assert conge.statut == StatutConge.DEMANDE
    assert conge.jours == 5


def test_demande_fixe_l_echeance_n1_a_48_heures():
    conge, _ = _demande()

    assert conge.date_limite_n1 == MAINTENANT + timedelta(hours=48)
    assert conge.date_limite_n2 is None


def test_demande_bloquee_au_dela_de_26_jours_ouvres_par_an():
    hierarchie = _hierarchie()

    with pytest.raises(SoldeInsuffisant):
        _demande(hierarchie, date(2026, 10, 5), date(2026, 11, 10))  # 27 jours ouvrés

    assert not Conge.objects.exists()


def test_demande_acceptee_sur_deux_semaines_calendaires():
    conge, _ = _demande(debut=date(2026, 10, 5), fin=date(2026, 10, 17))

    assert conge.jours == 10  # 2 x 5 jours ouvrés (les samedis 10 et 17, le dimanche 11, ne comptent pas)


def test_demande_refusee_si_fin_avant_debut():
    with pytest.raises(CongeError):
        _demande(debut=FIN, fin=DEBUT)


def test_demande_refusee_sans_superieur_hierarchique():
    employe = PersonnelFactory(superieur=None)

    with pytest.raises(CongeError, match="supérieur"):
        services.demander_conge(employe, date_debut=DEBUT, date_fin=FIN, motif="x")


def test_demande_refusee_si_la_periode_ne_contient_aucun_jour_ouvre():
    with pytest.raises(CongeError, match="jour ouvré"):
        _demande(debut=date(2026, 10, 11), fin=date(2026, 10, 11))  # un dimanche


# --- étape 2 : validation N1 par le supérieur hiérarchique ---


def test_valider_n1_par_le_superieur_direct_meme_dans_un_autre_departement():
    conge, superieur = _demande()

    services.valider_n1(conge, superieur, commentaire="OK", maintenant=MAINTENANT)

    conge.refresh_from_db()
    assert conge.statut == StatutConge.VALIDATION_N1
    assert conge.date_limite_n2 == MAINTENANT + timedelta(hours=24)
    decision = conge.validations.get()
    assert (decision.niveau, decision.decision) == (1, "APPROUVE")
    assert decision.commentaire == "OK"


def test_valider_n1_refuse_pour_un_utilisateur_qui_n_est_pas_le_superieur():
    conge, _ = _demande()
    autre = UserFactory(role=Role.PARCAUTO)
    PersonnelFactory(departement=Departement.EXPLOITATION, utilisateur=autre)

    with pytest.raises(ActionNonAutorisee):
        services.valider_n1(conge, autre)
    with pytest.raises(ActionNonAutorisee):
        services.valider_n1(conge, UserFactory(role=Role.PARCAUTO))  # sans fiche


def test_valider_n1_refuse_pour_le_superieur_du_superieur():
    employe, superieur = _hierarchie()
    directeur = UserFactory(role=Role.DIRECTION)
    chef = employe.superieur
    chef.superieur = PersonnelFactory(utilisateur=directeur)
    chef.save()
    conge, _ = _demande((employe, superieur))
    _delai_en_cours(conge)

    with pytest.raises(ActionNonAutorisee):
        services.valider_n1(conge, directeur)


def test_l_employe_ne_peut_pas_valider_sa_propre_demande():
    hierarchie = _hierarchie()
    compte = UserFactory(role=Role.PARCAUTO)
    hierarchie[0].utilisateur = compte
    hierarchie[0].save()
    conge, _ = _demande(hierarchie)

    with pytest.raises(ActionNonAutorisee):
        services.valider_n1(conge, compte)


def test_la_demande_d_un_chef_est_validee_par_son_propre_superieur():
    _, chef_user = _hierarchie()  # chef_user est le compte du « chef »
    chef_fiche = chef_user.personnel
    directeur = UserFactory(role=Role.DIRECTION)
    chef_fiche.superieur = PersonnelFactory(utilisateur=directeur)
    chef_fiche.save()
    conge, _ = _demande((chef_fiche, chef_user))

    with pytest.raises(ActionNonAutorisee):
        services.valider_n1(conge, chef_user)
    services.valider_n1(conge, directeur)

    conge.refresh_from_db()
    assert conge.statut == StatutConge.VALIDATION_N1


def test_valider_n1_impossible_hors_statut_demande():
    conge, superieur = _demande()
    services.valider_n1(conge, superieur)

    with pytest.raises(TransitionInterdite):
        services.valider_n1(conge, superieur)


# --- étape 3 : validation N2 par la RH ---


def test_valider_n2_par_la_rh_approuve_et_decompte_le_droit_annuel():
    conge, superieur = _demande()
    services.valider_n1(conge, superieur)

    services.valider_n2(conge, _rh(), commentaire="Validé")

    conge.refresh_from_db()
    assert conge.statut == StatutConge.APPROUVE
    assert _disponible(conge.employe) == 21
    assert conge.validations.filter(niveau=2, decision="APPROUVE").exists()


def test_valider_n2_refuse_hors_rh():
    conge, superieur = _demande()
    services.valider_n1(conge, superieur)

    with pytest.raises(ActionNonAutorisee):
        services.valider_n2(conge, UserFactory(role=Role.DIRECTION))


def test_valider_n2_impossible_sans_validation_n1():
    conge, _ = _demande()

    with pytest.raises(TransitionInterdite):
        services.valider_n2(conge, _rh())


def test_valider_n2_recontrole_le_droit_quand_deux_demandes_etaient_en_attente():
    hierarchie = _hierarchie()
    premiere, superieur = _demande(hierarchie, date(2026, 10, 5), date(2026, 10, 26))  # 16 j
    seconde, _ = _demande(hierarchie, date(2026, 11, 2), date(2026, 11, 23))  # 16 j : 32 > 26 ensemble
    services.valider_n1(premiere, superieur)
    services.valider_n1(seconde, superieur)
    rh = _rh()
    services.valider_n2(premiere, rh)

    with pytest.raises(SoldeInsuffisant):
        services.valider_n2(seconde, rh)

    seconde.refresh_from_db()
    assert seconde.statut == StatutConge.VALIDATION_N1


def test_un_rh_ne_peut_pas_valider_sa_propre_demande():
    employe, superieur = _hierarchie()
    compte_rh = _rh()
    employe.utilisateur = compte_rh
    employe.save()
    conge, _ = _demande((employe, superieur))
    services.valider_n1(conge, superieur)

    with pytest.raises(ActionNonAutorisee):
        services.valider_n2(conge, compte_rh)


# --- refus ---


def test_refus_n1_par_le_superieur_passe_le_conge_a_refuse():
    conge, superieur = _demande()

    services.refuser(conge, superieur, commentaire="Période chargée")

    conge.refresh_from_db()
    assert conge.statut == StatutConge.REFUSE
    assert conge.motif_decision == "Période chargée"
    assert conge.validations.get().decision == "REFUSE"


def test_refus_n2_par_la_rh_ne_decompte_rien():
    conge, superieur = _demande()
    services.valider_n1(conge, superieur)

    services.refuser(conge, _rh())

    assert _disponible(conge.employe) == 26
    assert Conge.objects.get().statut == StatutConge.REFUSE


def test_refus_a_l_etape_n1_refuse_pour_la_rh():
    conge, _ = _demande()

    with pytest.raises(ActionNonAutorisee):
        services.refuser(conge, _rh())


def test_refus_impossible_sur_un_conge_deja_approuve():
    with pytest.raises(TransitionInterdite):
        services.refuser(_approuve(), _rh())


# --- annulation (RH uniquement, cahier-des-charges.md:220-221) ---


def test_annulation_par_la_rh_restitue_les_jours():
    conge = _approuve()
    assert _disponible(conge.employe) == 21

    services.annuler_conge_approuve(conge, _rh(), motif="Urgence client")

    conge.refresh_from_db()
    assert _disponible(conge.employe) == 26
    assert conge.statut == StatutConge.REFUSE
    assert conge.motif_decision == "Urgence client"


def test_annulation_refusee_hors_rh():
    conge = _approuve()

    with pytest.raises(ActionNonAutorisee):
        services.annuler_conge_approuve(conge, conge.employe.superieur.utilisateur)


def test_annulation_impossible_si_le_conge_n_est_pas_approuve():
    conge, _ = _demande()

    with pytest.raises(TransitionInterdite):
        services.annuler_conge_approuve(conge, _rh())


# --- passage automatique EN_COURS / TERMINE et effet sur le chauffeur ---


def test_synchronisation_demarre_puis_termine_le_conge():
    conge = _approuve()

    avant = services.synchroniser_statuts_conges(aujourd_hui=DEBUT - timedelta(days=1))
    pendant = services.synchroniser_statuts_conges(aujourd_hui=DEBUT)
    apres = services.synchroniser_statuts_conges(aujourd_hui=FIN + timedelta(days=1))

    assert avant == {"demarres": 0, "termines": 0}
    assert pendant == {"demarres": 1, "termines": 0}
    assert apres == {"demarres": 0, "termines": 1}
    conge.refresh_from_db()
    assert conge.statut == StatutConge.TERMINE


def test_conge_rattrape_directement_en_termine_si_la_synchro_a_ete_manquee():
    conge = _approuve()

    resultat = services.synchroniser_statuts_conges(aujourd_hui=FIN + timedelta(days=3))

    assert resultat == {"demarres": 0, "termines": 1}
    conge.refresh_from_db()
    assert conge.statut == StatutConge.TERMINE


def test_chauffeur_passe_en_conge_au_demarrage_puis_redevient_disponible():
    hierarchie = _hierarchie(poste="Chauffeur")
    fiche = Chauffeur.objects.get(personnel=hierarchie[0])
    _approuve(hierarchie)

    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE  # pas avant le départ effectif

    services.synchroniser_statuts_conges(aujourd_hui=DEBUT)
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.EN_CONGE

    services.synchroniser_statuts_conges(aujourd_hui=FIN + timedelta(days=1))
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE


def test_fin_de_conge_conserve_un_statut_suspendu():
    hierarchie = _hierarchie(poste="Chauffeur")
    fiche = Chauffeur.objects.get(personnel=hierarchie[0])
    _approuve(hierarchie)
    services.synchroniser_statuts_conges(aujourd_hui=DEBUT)
    drivers_services.changer_statut(fiche, StatutChauffeur.SUSPENDU)

    services.synchroniser_statuts_conges(aujourd_hui=FIN + timedelta(days=1))

    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.SUSPENDU


def test_conge_d_un_non_chauffeur_ne_touche_aucune_fiche_chauffeur():
    _approuve(_hierarchie(poste="Comptable"))

    services.synchroniser_statuts_conges(aujourd_hui=DEBUT)

    assert not Chauffeur.objects.exists()


def test_copilote_passe_en_conge_au_demarrage_puis_redevient_disponible():
    """Retour réunion : le copilote suit le même cycle de statut que le chauffeur."""
    hierarchie = _hierarchie(poste="Copilote")
    fiche = Copilote.objects.get(personnel=hierarchie[0])
    _approuve(hierarchie)

    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE  # pas avant le départ effectif

    services.synchroniser_statuts_conges(aujourd_hui=DEBUT)
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.EN_CONGE

    services.synchroniser_statuts_conges(aujourd_hui=FIN + timedelta(days=1))
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE


# --- audit ---


def test_les_transitions_de_statut_sont_auditees():
    conge, superieur = _demande()
    services.valider_n1(conge, superieur)

    entrees = AuditLog.objects.filter(entite="Conge", entite_id=conge.pk)
    assert entrees.get(action=ActionChoices.CREATE).module == "RH"
    modif = entrees.filter(action=ActionChoices.UPDATE).latest("date_heure")
    assert modif.ancienne_valeur["statut"] == "DEMANDE"
    assert modif.nouvelle_valeur["statut"] == "VALIDATION_N1"


# --- le directeur (sans supérieur) valide lui-même son N1 ---


def _directeur():
    compte = UserFactory(role=Role.DIRECTION)
    fiche = PersonnelFactory(
        poste="Directeur", departement=Departement.DIRECTION, utilisateur=compte
    )
    return fiche, compte


def test_le_directeur_valide_lui_meme_son_n1_puis_la_rh_valide_en_n2():
    fiche, compte = _directeur()
    conge, _ = _demande((fiche, compte))

    services.valider_n1(conge, compte)
    services.valider_n2(conge, _rh())

    conge.refresh_from_db()
    assert conge.statut == StatutConge.APPROUVE
    assert conge.validations.get(niveau=1).validateur == compte


def test_le_directeur_ne_peut_pas_sauter_la_validation_n2_de_la_rh():
    fiche, compte = _directeur()
    conge, _ = _demande((fiche, compte))
    services.valider_n1(conge, compte)

    with pytest.raises(ActionNonAutorisee):
        services.valider_n2(conge, compte)


def test_un_employe_sans_superieur_et_sans_compte_direction_ne_peut_pas_demander():
    compte = UserFactory(role=Role.PARCAUTO)
    fiche = PersonnelFactory(superieur=None, utilisateur=compte)

    with pytest.raises(CongeError, match="supérieur"):
        services.demander_conge(fiche, date_debut=DEBUT, date_fin=FIN, motif="x")


def test_un_directeur_sans_compte_utilisateur_ne_peut_pas_demander():
    fiche = PersonnelFactory(poste="Directeur", superieur=None, utilisateur=None)

    with pytest.raises(CongeError, match="supérieur"):
        services.demander_conge(fiche, date_debut=DEBUT, date_fin=FIN, motif="x")


def test_un_autre_utilisateur_direction_ne_valide_pas_le_n1_du_directeur():
    fiche, compte = _directeur()
    conge, _ = _demande((fiche, compte))
    _delai_en_cours(conge)

    with pytest.raises(ActionNonAutorisee):
        services.valider_n1(conge, UserFactory(role=Role.DIRECTION))


def test_le_directeur_valide_le_n1_d_un_subordonne_seulement_s_il_est_son_superieur():
    fiche, compte = _directeur()
    employe = PersonnelFactory(superieur=fiche, poste="Comptable")
    conge, _ = _demande((employe, compte))

    services.valider_n1(conge, compte)

    conge.refresh_from_db()
    assert conge.statut == StatutConge.VALIDATION_N1


def test_valider_n1_sans_acteur_est_refuse():
    conge, _ = _demande()

    with pytest.raises(ActionNonAutorisee):
        services.valider_n1(conge, None)
```

#### `apps/hr/tests/test_droits_conges.py`

*197 lignes* — Droit annuel (26 jours ouvrés) et exceptions accordées par la RH.

```python
"""Droit annuel (26 jours ouvrés) et exceptions accordées par la RH."""

from datetime import date

import pytest

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditLog
from apps.hr import services
from apps.hr.exceptions import ActionNonAutorisee, CongeError, SoldeInsuffisant
from apps.hr.models import JourFerie, StatutConge

from .factories import PersonnelFactory
from .test_conges import _approuve, _demande, _hierarchie, _rh

pytestmark = pytest.mark.django_db


def _droits(employe, annee=2026):
    return services.droits_conges(employe, annee)


# --- droit de base ---


def test_droit_de_base_26_jours_ouvres_sans_exception_ni_conge():
    employe = PersonnelFactory()

    assert _droits(employe) == {
        "droit_annuel": 26,
        "exceptionnels": 0,
        "consommes": 0,
        "disponible": 26,
    }


def test_une_demande_en_attente_n_est_pas_decomptee():
    conge, _ = _demande()

    assert _droits(conge.employe)["consommes"] == 0


def test_un_conge_approuve_est_decompte():
    conge = _approuve()

    assert _droits(conge.employe) == {
        "droit_annuel": 26,
        "exceptionnels": 0,
        "consommes": 5,
        "disponible": 21,
    }


def test_un_conge_termine_reste_decompte():
    conge = _approuve()
    services.synchroniser_statuts_conges(aujourd_hui=date(2026, 12, 1))

    conge.refresh_from_db()
    assert conge.statut == StatutConge.TERMINE
    assert _droits(conge.employe)["consommes"] == 5


def test_le_droit_est_calcule_par_annee_de_debut_du_conge():
    hierarchie = _hierarchie()
    _approuve(hierarchie, date(2026, 12, 7), date(2026, 12, 12))  # lun-sam : 5 jours ouvrés (pas le samedi)
    employe = hierarchie[0]

    assert _droits(employe, 2026)["disponible"] == 21
    assert _droits(employe, 2027)["disponible"] == 26


def test_apres_avoir_pris_5_jours_une_demande_de_22_jours_est_refusee_mais_21_passe():
    hierarchie = _hierarchie()
    _approuve(hierarchie)  # 5 jours, solde restant 21

    with pytest.raises(SoldeInsuffisant):
        _demande(hierarchie, date(2026, 11, 2), date(2026, 12, 1))  # 22 jours ouvrés
    conge, _ = _demande(hierarchie, date(2026, 11, 2), date(2026, 11, 30))  # 21 jours ouvrés

    assert conge.jours == 21


# --- exceptions accordées par la RH ---


def test_la_rh_peut_accorder_des_jours_exceptionnels():
    employe = PersonnelFactory()

    attribution = services.accorder_jours_exceptionnels(
        employe, _rh(), annee=2026, jours=5, motif="Mariage"
    )

    assert attribution.motif == "Mariage"
    assert _droits(employe) == {
        "droit_annuel": 26,
        "exceptionnels": 5,
        "consommes": 0,
        "disponible": 31,
    }


def test_les_jours_exceptionnels_permettent_de_depasser_le_droit_de_base():
    hierarchie = _hierarchie()
    employe = hierarchie[0]
    services.accorder_jours_exceptionnels(
        employe, _rh(), annee=2026, jours=3, motif="Décès d'un proche"
    )

    conge, _ = _demande(hierarchie, date(2026, 11, 2), date(2026, 12, 4))  # 25 jours ouvrés (26 + 3 - 4 de marge)

    assert conge.jours == 25


def test_les_jours_exceptionnels_d_une_autre_annee_ne_comptent_pas():
    employe = PersonnelFactory()
    services.accorder_jours_exceptionnels(
        employe, _rh(), annee=2025, jours=5, motif="Mariage"
    )

    assert _droits(employe, 2026)["disponible"] == 26


def test_attribution_refusee_hors_rh():
    with pytest.raises(ActionNonAutorisee):
        services.accorder_jours_exceptionnels(
            PersonnelFactory(),
            UserFactory(role=Role.DIRECTION),
            annee=2026,
            jours=3,
            motif="x",
        )


def test_la_rh_ne_peut_pas_s_accorder_des_jours_a_elle_meme():
    compte_rh = _rh()
    fiche = PersonnelFactory(utilisateur=compte_rh)

    with pytest.raises(ActionNonAutorisee):
        services.accorder_jours_exceptionnels(
            fiche, compte_rh, annee=2026, jours=3, motif="x"
        )


@pytest.mark.parametrize("motif", ["", "   "])
def test_attribution_refusee_sans_motif(motif):
    with pytest.raises(CongeError, match="motif"):
        services.accorder_jours_exceptionnels(
            PersonnelFactory(), _rh(), annee=2026, jours=3, motif=motif
        )


def test_attribution_refusee_avec_zero_jour():
    with pytest.raises(CongeError):
        services.accorder_jours_exceptionnels(
            PersonnelFactory(), _rh(), annee=2026, jours=0, motif="x"
        )


def test_attribution_exceptionnelle_est_auditee():
    attribution = services.accorder_jours_exceptionnels(
        PersonnelFactory(), _rh(), annee=2026, jours=2, motif="Mariage"
    )

    entree = AuditLog.objects.get(entite="AttributionConge", entite_id=attribution.pk)
    assert entree.module == "RH"
    assert entree.nouvelle_valeur["jours"] == 2


# --- jours ouvrés (avenant-separation-des-taches.md § R7 : lundi-vendredi, hors jours fériés) ---


@pytest.mark.parametrize(
    ("debut", "fin", "attendu"),
    [
        (date(2026, 10, 5), date(2026, 10, 9), 5),  # lundi-vendredi
        (date(2026, 10, 5), date(2026, 10, 10), 5),  # le samedi ne compte pas
        (date(2026, 10, 5), date(2026, 10, 11), 5),  # ni le dimanche
        (date(2026, 10, 10), date(2026, 10, 11), 0),  # un week-end complet
        (date(2026, 10, 5), date(2026, 10, 5), 1),  # un seul jour
    ],
)
def test_calculer_jours_exclut_le_samedi_et_le_dimanche(debut, fin, attendu):
    assert services.calculer_jours(debut, fin) == attendu


def test_calculer_jours_exclut_les_jours_feries_enregistres():
    JourFerie.objects.create(date=date(2026, 8, 7), libelle="Fête de l'Indépendance")  # un vendredi

    assert services.calculer_jours(date(2026, 8, 3), date(2026, 8, 8)) == 4  # lun-jeu (ven férié, sam exclu)


def test_un_jour_ferie_supprime_logiquement_redevient_ouvre():
    ferie = JourFerie.objects.create(date=date(2026, 8, 7), libelle="Indépendance")
    ferie.delete()

    assert services.calculer_jours(date(2026, 8, 3), date(2026, 8, 8)) == 5  # lun-ven (sam toujours exclu)
```

#### `apps/hr/tests/test_recrutement.py`

*75 lignes*

```python
from datetime import date
from decimal import Decimal

import pytest

from apps.drivers.models import Chauffeur
from apps.hr import services
from apps.hr.models import Departement, Personnel

pytestmark = pytest.mark.django_db


def _donnees(**surcharges):
    donnees = dict(
        matricule="MAT-9001",
        nom="Bamba",
        prenom="Issa",
        poste="Mécanicien",
        departement=Departement.PARC_AUTO,
        type_contrat="CDI",
        date_embauche=date(2026, 9, 1),
        salaire_base=Decimal("300000"),
    )
    donnees.update(surcharges)
    return donnees


def test_recruter_cree_la_fiche_personnel_avec_le_contrat():
    personnel = services.recruter(**_donnees())

    assert Personnel.objects.get(matricule="MAT-9001") == personnel
    assert personnel.type_contrat == "CDI"
    assert personnel.superieur is None


def test_recruter_rattache_l_employe_a_son_superieur_hierarchique():
    chef = services.recruter(**_donnees(matricule="MAT-9000", poste="Chef d'atelier"))

    employe = services.recruter(**_donnees(matricule="MAT-9003", superieur=chef))

    assert employe.superieur == chef
    assert list(chef.subordonnes.all()) == [employe]


def test_recruter_un_chauffeur_cree_automatiquement_sa_fiche_chauffeur():
    personnel = services.recruter(**_donnees(matricule="MAT-9002", poste="Chauffeur"))

    assert Chauffeur.objects.filter(personnel=personnel).exists()


def test_recruter_un_autre_poste_ne_cree_pas_de_fiche_chauffeur():
    personnel = services.recruter(**_donnees())

    assert not Chauffeur.objects.filter(personnel=personnel).exists()


def test_recruter_sans_matricule_en_genere_un_automatiquement():
    donnees = _donnees()
    del donnees["matricule"]

    personnel = services.recruter(**donnees)

    annee = date.today().year
    assert personnel.matricule == f"PERS-{annee}-0001"


def test_recruter_sans_matricule_incremente_a_chaque_recrutement():
    donnees = _donnees()
    del donnees["matricule"]

    premier = services.recruter(**donnees)
    second = services.recruter(**{**donnees, "nom": "Koné"})

    annee = date.today().year
    assert (premier.matricule, second.matricule) == (f"PERS-{annee}-0001", f"PERS-{annee}-0002")
```

Ce chapitre présente aussi quatre fichiers de tests de `hr` (`test_conges.py`, `test_droits_conges.py`,
`test_recrutement.py`, `test_comptes_demo.py`) : ils ont besoin des chauffeurs pour s'exécuter (par exemple
« un chauffeur en congé passe au statut En congé »).

## Étape 4 — Déclarer l'application et migrer

#### `config/settings/base.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/settings/base.py (avant)
+++ config/settings/base.py (après)
@@ -56,4 +56,5 @@
     "apps.audit",
     "apps.hr",
+    "apps.drivers",
 ]
 
```

```bash
python manage.py makemigrations drivers
python manage.py migrate
```

**Résultat attendu :** `Create model Chauffeur`, puis `Applying drivers.0001_initial... OK`.

## Vérifier le chapitre

```bash
python manage.py check
```

```bash
python -m pytest apps/drivers/tests/test_copilote.py apps/drivers/tests/test_fiche.py apps/drivers/tests/test_models.py apps/drivers/tests/test_services.py apps/hr/tests/test_comptes_demo.py apps/hr/tests/test_conges.py apps/hr/tests/test_droits_conges.py apps/hr/tests/test_recrutement.py -q --no-cov
```

**Résultat attendu :** `114 passed` (pour les 7 fichier(s) de tests présentés dans ce chapitre).

**Créez maintenant vos comptes d'essai** (un par rôle) et vérifiez que la fiche chauffeur s'est créée
toute seule :

```bash
python manage.py creer_comptes_demo
python manage.py shell -c "from apps.drivers.models import Chauffeur; print(list(Chauffeur.objects.values_list('personnel__matricule', 'statut')))"
```

**Résultat attendu :** la première commande affiche un **mot de passe généré** et la liste des 7 comptes
(`demo_direction`, `demo_admin`, `demo_rh`, `demo_charge`, `demo_parcauto`, `demo_finances`,
`demo_chauffeur`). **Notez ce mot de passe** : vous en aurez besoin pour vous connecter. La seconde
affiche **une** fiche chauffeur au statut `DISPONIBLE` (celle de `demo_chauffeur`), créée par le signal.

## Ce qu'il faut retenir

- **Prolonger** une table plutôt que la dupliquer : `OneToOneField` + propriétés.
- Un **signal** permet à une app « du dessous » de réagir à une app « du dessus » sans la modifier.
- Certains états sont **posés par le système** et interdits à la saisie manuelle.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 6 : app drivers (fiche chauffeur, permis, visite médicale, statuts, alertes 30 jours)"
```

---

[← Chapitre 5](05-hr.md) · [Sommaire](README.md) · [Chapitre 7 →](07-customers.md)
