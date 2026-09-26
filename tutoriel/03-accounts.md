# Chapitre 3 — Utilisateurs, rôles et sécurité de la connexion : l'app accounts

> 20 fichier(s) dans ce chapitre, 944 lignes de code.

## Ce que vous allez construire

**`accounts`** : les utilisateurs, leurs **sept rôles** et tout ce qui protège la connexion.

| Élément | À quoi il sert |
|---|---|
| `User` et `Role` | l'utilisateur de l'ERP et son rôle : ADMIN, DIRECTION, RH, CHARGE_CLIENTELE, PARCAUTO, FINANCES, CHAUFFEUR |
| `RoleRequiredMixin` | la **garde** de toutes les vues : refuse l'accès si le rôle n'est pas autorisé |
| `navigation` | le **menu** de gauche, différent selon le rôle, alimenté par un registre |
| `throttle` | **anti force brute** : après trop d'échecs, la connexion est bloquée quelques minutes |
| `mfa` | **double authentification** (application d'authentification + codes de secours), obligatoire pour l'ADMIN et la DIRECTION |
| `middleware` | la **porte** qui refuse tout tant que la double authentification n'est pas passée |

## Prérequis

- Chapitres 1 et 2 terminés (`python -m pytest apps/core -q` est vert).
- Une application d'authentification sur le téléphone n'est pas nécessaire ici ; elle servira au chapitre 16.

## Notions Django de ce chapitre

- **Modèle utilisateur personnalisé** : Django fournit un `User` par défaut. Ici on le remplace par le nôtre
  (avec un champ `role`) grâce au réglage `AUTH_USER_MODEL`. **Il faut le faire avant la première
  migration** : changer plus tard est très pénible. C'est pourquoi on n'a pas encore lancé `migrate`.
- **`AbstractUser`** : la classe de Django qu'on prolonge (elle apporte identifiant, mot de passe haché,
  nom, e-mail, `is_active`, `is_staff`…).
- **Mixin** : une petite classe qui ajoute un comportement à une vue par héritage multiple
  (`class MaVue(RoleRequiredMixin, ListView)`).
- **Décorateur `@receiver`** : abonne une fonction à un **signal** (ici, l'échec d'une connexion).
- **Signal personnalisé** : `Signal()` crée une annonce à laquelle d'autres apps s'abonneront. C'est ainsi
  que `audit` (chapitre 4) sera prévenu sans que `accounts` l'importe.
- **Commande de gestion** : un script lancé par `python manage.py <nom>` (dossier
  `management/commands/`).
- **Fabrique de test (`factory_boy`)** : une classe qui fabrique des objets de test valides en une ligne
  (`UserFactory(role="RH")`).

## Étape 1 — Créer l'application

```bash
mkdir -p apps/accounts/tests apps/accounts/management/commands
```

#### Fichiers vides à créer

Ces fichiers n'ont aucun contenu ; ils servent à faire de leur dossier un *paquet Python* (sans eux, `import apps.xxx` échouerait). Créez d'abord les dossiers, puis les fichiers :

```bash
mkdir -p apps\accounts apps\accounts\management apps\accounts\management\commands apps\accounts\tests
touch apps/accounts/__init__.py
touch apps/accounts/management/__init__.py
touch apps/accounts/management/commands/__init__.py
touch apps/accounts/tests/__init__.py
```

> Sous PowerShell, `mkdir -p` s'écrit `New-Item -ItemType Directory -Force <dossier>` et `touch fichier` s'écrit `New-Item -ItemType File -Force fichier`. Vous pouvez aussi créer ces fichiers avec votre éditeur.

## Étape 2 — Le modèle utilisateur

#### `apps/accounts/models.py`

*103 lignes*

```python
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class Role(models.TextChoices):
    """7 rôles utilisateurs — cahier-des-charges.md:44-55."""

    ADMIN = "ADMIN", _("Administrateur")
    DIRECTION = "DIRECTION", _("Direction")
    RH = "RH", _("Ressources Humaines")
    CHARGE_CLIENTELE = "CHARGE_CLIENTELE", _("Chargé clientèle")
    PARCAUTO = "PARCAUTO", _("Parc Auto")
    FINANCES = "FINANCES", _("Finances")
    CHAUFFEUR = "CHAUFFEUR", _("Chauffeur")


class User(AbstractUser):
    """Utilisateur de l'ERP.

    RBAC simple : un utilisateur = un rôle principal
    (architecture.md:534, hypothèse H2). La désactivation utilise le
    champ standard ``is_active`` de Django plutôt que le soft delete de
    ``BaseModel`` : un compte auth n'est pas un « enregistrement métier »
    et le queryset par défaut d'authentification ne doit jamais être
    filtré silencieusement.
    """

    role = models.CharField(_("rôle"), max_length=20, choices=Role.choices)
    telephone = models.CharField(_("téléphone"), max_length=20, blank=True)

    # MFA obligatoire ADMIN/DIRECTION — cahier-des-charges.md:276. Ce drapeau reflète l'état de
    # l'appareil TOTP (voir ``AppareilMFA``) : il est tenu à jour par ``accounts.mfa``, jamais à la main.
    mfa_enabled = models.BooleanField(_("MFA activé"), default=False)

    class Meta:
        db_table = "accounts_user"
        verbose_name = _("utilisateur")
        verbose_name_plural = _("utilisateurs")

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def role_effectif(self) -> str:
        """Rôle utilisé pour les droits : un superutilisateur agit en ADMIN.

        ``createsuperuser`` ne renseigne pas ``role`` ; sans cela le premier
        compte créé ne verrait aucun écran de l'interface.
        """
        return Role.ADMIN if self.is_superuser else self.role

    @property
    def is_admin(self):
        return self.role == Role.ADMIN

    @property
    def is_direction(self):
        return self.role == Role.DIRECTION


class AppareilMFA(models.Model):
    """Application d'authentification (TOTP) d'un utilisateur : un seul appareil par compte.

    Le secret sert à recalculer les codes à 6 chiffres ; tant que la personne n'a pas saisi un
    premier code valable (``confirme``), l'appareil n'est pas actif. ``dernier_pas`` mémorise le
    dernier intervalle de 30 secondes accepté : un même code ne sert qu'une fois (anti-rejeu).
    """

    utilisateur = models.OneToOneField(
        User, verbose_name=_("utilisateur"), on_delete=models.CASCADE, related_name="appareil_mfa"
    )
    secret = models.CharField(_("secret TOTP"), max_length=64)
    confirme = models.BooleanField(_("confirmé"), default=False)
    dernier_pas = models.BigIntegerField(_("dernier intervalle accepté"), default=0)
    cree_le = models.DateTimeField(_("créé le"), auto_now_add=True)
    confirme_le = models.DateTimeField(_("confirmé le"), null=True, blank=True)

    class Meta:
        db_table = "accounts_appareil_mfa"
        verbose_name = _("appareil MFA")
        verbose_name_plural = _("appareils MFA")

    def __str__(self):
        return f"MFA de {self.utilisateur}"


class CodeSecours(models.Model):
    """Code de secours à usage unique (téléphone perdu). Seule l'empreinte est conservée."""

    utilisateur = models.ForeignKey(
        User, verbose_name=_("utilisateur"), on_delete=models.CASCADE, related_name="codes_secours"
    )
    empreinte = models.CharField(_("empreinte SHA-256"), max_length=64, db_index=True)
    utilise_le = models.DateTimeField(_("utilisé le"), null=True, blank=True)

    class Meta:
        db_table = "accounts_code_secours"
        verbose_name = _("code de secours")
        verbose_name_plural = _("codes de secours")

    def __str__(self):
        return f"Code de secours de {self.utilisateur}"
```

À retenir :

- **`Role`** est une énumération (`TextChoices`) : la valeur stockée en base (`"ADMIN"`) et le libellé
  affiché (« Administrateur »).
- **`role_effectif`** : un *superutilisateur* Django (créé par `createsuperuser`, sans rôle) agit comme
  ADMIN. Sans cela, le premier compte créé ne verrait aucun écran.
- **`AppareilMFA`** : l'application d'authentification d'un utilisateur (un seul par compte). Le champ
  `dernier_pas` mémorise le dernier code accepté pour qu'**un code ne serve qu'une fois** (anti-rejeu).
- **`CodeSecours`** : on ne garde **jamais** un code de secours en clair, seulement son *empreinte*
  SHA-256. Si la base fuitait, les codes resteraient inutilisables.

## Étape 3 — Les droits et le menu

#### `apps/accounts/permissions.py`

*59 lignes* — Permissions DRF par rôle — conventions.md §3 "RBAC granulaire".

```python
"""Permissions DRF par rôle — conventions.md §3 "RBAC granulaire".

Périmètre par rôle : cahier-des-charges.md:44-55 (table des rôles).
Le contrôle au niveau objet (``DjangoObjectPermissions``, conventions.md:37)
sera ajouté app par app à partir de l'étape 2, une fois les entités
métier (Personnel, Client, Véhicule...) créées.
"""

from rest_framework.permissions import BasePermission

from .models import Role


class HasRole(BasePermission):
    """Base : autorise si ``request.user.role`` est dans ``allowed_roles``."""

    allowed_roles: tuple[str, ...] = ()

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.role in self.allowed_roles
        )


class IsAdmin(HasRole):
    allowed_roles = (Role.ADMIN,)


class IsDirection(HasRole):
    allowed_roles = (Role.DIRECTION,)


class IsRH(HasRole):
    allowed_roles = (Role.RH,)


class IsChargeClientele(HasRole):
    allowed_roles = (Role.CHARGE_CLIENTELE,)


class IsParcAuto(HasRole):
    allowed_roles = (Role.PARCAUTO,)


class IsFinances(HasRole):
    allowed_roles = (Role.FINANCES,)


class IsChauffeur(HasRole):
    allowed_roles = (Role.CHAUFFEUR,)


class IsAdminOrDirection(HasRole):
    """Lecture élargie ADMIN + DIRECTION (ex. journal d'audit, cahier-des-charges.md:81)."""

    allowed_roles = (Role.ADMIN, Role.DIRECTION)
```

Ces classes servent à l'**API** (chapitre 28) : `IsAdmin`, `IsDirection`… décident si un rôle a accès à une
route.

#### `apps/accounts/mixins.py`

*19 lignes*

```python
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied


class RoleRequiredMixin(LoginRequiredMixin):
    """Vue réservée aux utilisateurs connectés dont le rôle est dans ``roles``.

    Non connecté → redirection vers la connexion ; connecté mais rôle non
    autorisé → 403. Contrôle côté serveur : masquer un bouton dans le template
    ne protège rien, c'est cette garde qui protège.
    """

    roles: frozenset[str] = frozenset()

    def dispatch(self, request, *args, **kwargs):
        utilisateur = request.user
        if utilisateur.is_authenticated and utilisateur.role_effectif not in self.roles:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
```

C'est **le** fichier de sécurité de l'interface web : toute vue qui hérite de `RoleRequiredMixin` et déclare
`roles = ...` refuse (erreur 403) tout utilisateur d'un autre rôle. Masquer un bouton dans le HTML ne protège
rien ; c'est cette garde, **côté serveur**, qui protège.

#### `apps/accounts/navigation.py`

*64 lignes* — Menu latéral, filtré selon le rôle de l'utilisateur.

```python
"""Menu latéral, filtré selon le rôle de l'utilisateur.

Chaque app déclare ses entrées dans ``AppConfig.ready()`` avec
:func:`enregistrer` : ``accounts`` n'importe ainsi aucune app métier
(sens des dépendances, architecture.md:161-163) et une entrée n'existe que si
son écran existe.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.urls import NoReverseMatch, reverse


@dataclass(frozen=True)
class EntreeMenu:
    libelle: str
    url_name: str
    icone: str  # classe FontAwesome, ex. "fa-truck-fast"
    roles: frozenset[str] | None  # None = tous les rôles connectés
    ordre: int = 100


_ENTREES: dict[str, EntreeMenu] = {}


def enregistrer(entree: EntreeMenu) -> None:
    """Ajoute (ou remplace) une entrée : idempotent, sûr si ``ready()`` est rappelé."""
    _ENTREES[entree.url_name] = entree


def entrees_pour(role: str, chemin: str) -> list[dict]:
    """Entrées visibles pour ``role``, triées, avec l'indicateur ``actif``."""
    visibles = sorted(
        (e for e in _ENTREES.values() if e.roles is None or role in e.roles),
        key=lambda e: (e.ordre, e.libelle),
    )
    resultat = []
    for entree in visibles:
        try:
            url = reverse(entree.url_name)
        except NoReverseMatch:
            continue  # « une entrée n'existe que si son écran existe » : jamais d'erreur 500 pour un menu
        resultat.append(
            {
                "libelle": entree.libelle,
                "url": url,
                "icone": entree.icone,
                "actif": False,
            }
        )
    # Un seul onglet actif : le plus précis. Sans cela, sur /facturation/depenses/ « Facturation »
    # (préfixe /facturation/) et « Dépenses » s'allumaient ensemble, comme « Garage » et « Incidents » :
    # un clic sur un onglet semblait en activer un autre. L'accueil (« / ») ne correspond qu'à lui-même.
    correspondants = [
        e for e in resultat if (chemin == e["url"] if e["url"] == "/" else chemin.startswith(e["url"]))
    ]
    if correspondants:
        max(correspondants, key=lambda e: len(e["url"]))["actif"] = True
    return resultat


enregistrer(EntreeMenu("Accueil", "home", "fa-house", None, ordre=0))
```

Le menu est un **registre** : chaque app (au démarrage, dans son `apps.py`) déclare ses entrées avec
`enregistrer(EntreeMenu(...))`. `accounts` n'importe donc aucune app métier. Une entrée dont l'écran
n'existe pas encore est simplement ignorée : c'est ce qui permet de construire l'interface écran par écran.

## Étape 4 — Anti force brute et double authentification

#### `apps/accounts/signals.py`

*37 lignes* — Signaux de l'app ``accounts``.

```python
"""Signaux de l'app ``accounts``.

``mfa_evenement`` : émis à chaque étape de la double authentification (activation, code vérifié ou
refusé, codes régénérés, réinitialisation). ``mot_de_passe_reinitialise`` : émis quand un compte
choisit un nouveau mot de passe via « mot de passe oublié » (``views.ReinitialiserMotDePasseConfirmerView``).
L'app ``audit`` s'y abonne pour inscrire ces deux au journal : ``accounts`` n'importe pas ``audit``
(sens des dépendances, architecture.md:134).

Les récepteurs ci-dessous branchent aussi la limitation d'essais et l'oubli de la vérification MFA
sur les signaux d'authentification de Django.
"""

from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import Signal, receiver

from . import mfa, throttle

# providing_args : request, utilisateur, evenement (str), succes (bool)
mfa_evenement = Signal()

# providing_args : request, utilisateur
mot_de_passe_reinitialise = Signal()


@receiver(user_login_failed)
def compter_echec_de_connexion(sender, credentials, request=None, **kwargs):
    """Chaque échec (formulaire web, administration, API) alimente le compteur anti force brute."""
    if request is not None:
        throttle.connexion_enregistrer_echec(request, credentials.get("username", ""))


@receiver(user_logged_in)
def repartir_sans_mfa_verifiee(sender, request=None, user=None, **kwargs):
    """Une nouvelle ouverture de session doit repasser la MFA, même pour la même personne."""
    session = getattr(request, "session", None)
    if session is not None:
        mfa.oublier_verification(request)
```

Deux abonnements aux signaux de connexion de Django : chaque **échec** alimente le compteur anti force
brute ; chaque **nouvelle connexion** oublie la vérification MFA de la session précédente.

`mfa_evenement` est notre propre signal : chaque étape de la double authentification l'émet, et l'app
`audit` (chapitre suivant) l'écoutera pour tout inscrire au journal.

#### `apps/accounts/throttle.py`

*96 lignes* — Limitation des essais de connexion et de double authentification (anti force brute).

```python
"""Limitation des essais de connexion et de double authentification (anti force brute).

Cahier-des-charges.md:277 « Rate limiting anti force brute ». Les compteurs vivent dans le cache
Django (Redis en production, partagé entre les processus ; en mémoire locale en développement).
Chaque compteur porte sa propre fenêtre : dès que le plafond est atteint, l'accès reste refusé
jusqu'à la fin de la fenêtre, même avec le bon mot de passe. Cette couche complète celle du
serveur web (Nginx, étape 7 lot 3) et ne la remplace pas.
"""

from __future__ import annotations

import hashlib
import math
import time

from django.conf import settings
from django.core.cache import cache

from apps.core.middleware import get_client_ip


def _empreinte(texte: str) -> str:
    return hashlib.sha256(texte.strip().lower().encode("utf-8")).hexdigest()[:32]


def _cle_compte(request, identifiant: str) -> str:
    return f"throttle:login:{get_client_ip(request)}:{_empreinte(identifiant or '')}"


def _cle_adresse(request) -> str:
    return f"throttle:login-ip:{get_client_ip(request)}"


def _cle_mfa(utilisateur) -> str:
    return f"throttle:mfa:{utilisateur.pk}"


def _incrementer(cle: str, fenetre: int) -> None:
    maintenant = time.time()
    etat = cache.get(cle)
    if etat is None or etat[1] <= maintenant:
        etat = (0, maintenant + fenetre)
    etat = (etat[0] + 1, etat[1])
    cache.set(cle, etat, timeout=max(1, math.ceil(etat[1] - maintenant)))


def _secondes_restantes(cle: str, plafond: int) -> int:
    etat = cache.get(cle)
    if etat is None:
        return 0
    reste = etat[1] - time.time()
    if etat[0] >= plafond and reste > 0:
        return math.ceil(reste)
    return 0


# --- connexion par mot de passe ---


def connexion_secondes_restantes(request, identifiant: str) -> int:
    """Secondes avant de pouvoir réessayer ; 0 si la connexion n'est pas bloquée."""
    return max(
        _secondes_restantes(_cle_compte(request, identifiant), settings.LOGIN_MAX_ECHECS_COMPTE),
        _secondes_restantes(_cle_adresse(request), settings.LOGIN_MAX_ECHECS_ADRESSE),
    )


def connexion_enregistrer_echec(request, identifiant: str) -> None:
    _incrementer(_cle_compte(request, identifiant), settings.LOGIN_FENETRE)
    _incrementer(_cle_adresse(request), settings.LOGIN_FENETRE)


def connexion_reinitialiser(request, identifiant: str) -> None:
    """Une connexion réussie efface les échecs du couple (adresse, identifiant), pas ceux de l'adresse."""
    cache.delete(_cle_compte(request, identifiant))


# --- double authentification ---


def mfa_secondes_restantes(utilisateur) -> int:
    return _secondes_restantes(_cle_mfa(utilisateur), settings.MFA_MAX_ECHECS)


def mfa_enregistrer_echec(utilisateur) -> None:
    _incrementer(_cle_mfa(utilisateur), settings.MFA_FENETRE)


def mfa_reinitialiser(utilisateur) -> None:
    cache.delete(_cle_mfa(utilisateur))


def phrase_attente(secondes: int) -> str:
    """« 1 minute » / « 4 minutes » : arrondi vers le haut, en français."""
    minutes = max(1, math.ceil(secondes / 60))
    return f"{minutes} minute{'s' if minutes > 1 else ''}"
```

Le principe : un compteur dans le **cache** (par couple adresse + identifiant, puis par adresse seule).
Une fois le plafond atteint (5 échecs pour un compte, 20 pour une adresse, sur 15 minutes), l'accès reste
refusé **même avec le bon mot de passe** : on ne vérifie même plus. Le message ne révèle pas si le
compte existe.

#### `apps/accounts/mfa.py`

*206 lignes* — Double authentification (TOTP + codes de secours) — cahier-des-charges.md:276.

```python
"""Double authentification (TOTP + codes de secours) — cahier-des-charges.md:276.

Logique métier de la MFA, sans rien savoir des vues : activer, vérifier un code, régénérer les codes
de secours, réinitialiser. Obligatoire pour les rôles de ``settings.MFA_ROLES`` (ADMIN, DIRECTION).

Choix de conception :
- code à 6 chiffres sur 30 secondes (RFC 6238, compatible Google/Microsoft Authenticator) ;
- un code TOTP ne sert qu'une fois (``dernier_pas``) et une tolérance d'un intervalle de chaque
  côté absorbe le décalage d'horloge d'un téléphone ;
- 10 codes de secours à usage unique, jamais stockés en clair (empreinte SHA-256 : ce sont des
  secrets aléatoires de 50 bits, pas des mots de passe choisis par une personne) ;
- le secret TOTP est conservé en base tel quel : il doit pouvoir être relu pour recalculer les codes.
"""

from __future__ import annotations

import hashlib
import secrets
import time

import pyotp
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import AppareilMFA, CodeSecours, User

NOMBRE_CODES_SECOURS = 10
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sans 0/O/1/I : lisibles à la main
_INTERVALLE = 30
_TOLERANCE = 1  # intervalles acceptés de chaque côté de l'instant présent


class MFAErreur(Exception):
    """Base des erreurs de la double authentification."""


class DejaActive(MFAErreur):
    """L'appareil de cette personne est déjà activé."""


class CodeInvalide(MFAErreur):
    """Le code saisi n'est pas valable."""


def mfa_requise(utilisateur) -> bool:
    """Vrai si ce compte doit passer la double authentification (ADMIN et DIRECTION)."""
    return bool(
        settings.MFA_ENFORCED
        and utilisateur is not None
        and utilisateur.is_authenticated
        and utilisateur.role_effectif in settings.MFA_ROLES
    )


def appareil_actif(utilisateur) -> AppareilMFA | None:
    return AppareilMFA.objects.filter(utilisateur=utilisateur, confirme=True).first()


def _normaliser_code(code: str) -> str:
    return "".join((code or "").split()).replace("-", "").upper()


def _empreinte(code: str) -> str:
    return hashlib.sha256(_normaliser_code(code).encode("utf-8")).hexdigest()


def _generer_codes() -> list[str]:
    codes = []
    for _ in range(NOMBRE_CODES_SECOURS):
        brut = "".join(secrets.choice(_ALPHABET) for _ in range(10))
        codes.append(f"{brut[:5]}-{brut[5:]}")
    return codes


def _remplacer_codes_secours(utilisateur) -> list[str]:
    CodeSecours.objects.filter(utilisateur=utilisateur).delete()
    codes = _generer_codes()
    CodeSecours.objects.bulk_create(
        [CodeSecours(utilisateur=utilisateur, empreinte=_empreinte(c)) for c in codes]
    )
    return codes


# --- activation ---


def preparer_activation(utilisateur) -> AppareilMFA:
    """Appareil en attente de confirmation (créé au besoin, secret conservé si on recharge la page)."""
    if appareil_actif(utilisateur) is not None:
        raise DejaActive("La double authentification est déjà activée sur ce compte.")
    appareil, _ = AppareilMFA.objects.get_or_create(
        utilisateur=utilisateur, defaults={"secret": pyotp.random_base32()}
    )
    return appareil


def uri_provisionnement(appareil: AppareilMFA) -> str:
    """Adresse ``otpauth://`` que l'application lit dans le QR code."""
    return pyotp.TOTP(appareil.secret).provisioning_uri(
        name=appareil.utilisateur.username, issuer_name=settings.MFA_ISSUER
    )


@transaction.atomic
def confirmer_activation(utilisateur, code: str) -> list[str]:
    """Active l'appareil si le premier code est bon ; renvoie les codes de secours (à montrer une fois)."""
    appareil = preparer_activation(utilisateur)
    if not _verifier_totp(appareil, code):
        raise CodeInvalide("Ce code n'est pas valable. Vérifiez l'heure de votre téléphone et réessayez.")
    appareil.confirme = True
    appareil.confirme_le = timezone.now()
    appareil.save(update_fields=["confirme", "confirme_le", "dernier_pas"])
    User.objects.filter(pk=utilisateur.pk).update(mfa_enabled=True)
    utilisateur.mfa_enabled = True
    return _remplacer_codes_secours(utilisateur)


# --- vérification ---


def _verifier_totp(appareil: AppareilMFA, code: str) -> bool:
    """Compare en temps constant, refuse un intervalle déjà utilisé (rejeu) et mémorise le nouveau."""
    saisi = _normaliser_code(code)
    if not (saisi.isdigit() and len(saisi) == 6):
        return False
    totp = pyotp.TOTP(appareil.secret, interval=_INTERVALLE)
    courant = int(time.time() // _INTERVALLE)
    for decalage in range(-_TOLERANCE, _TOLERANCE + 1):
        pas = courant + decalage
        if pas > appareil.dernier_pas and secrets.compare_digest(totp.at(pas * _INTERVALLE), saisi):
            appareil.dernier_pas = pas
            appareil.save(update_fields=["dernier_pas"])
            return True
    return False


@transaction.atomic
def verifier_code(utilisateur, code: str) -> bool:
    """Vrai si ``code`` est un code TOTP frais ou un code de secours non encore utilisé (consommé)."""
    appareil = (
        AppareilMFA.objects.select_for_update()
        .filter(utilisateur=utilisateur, confirme=True)
        .first()
    )
    if appareil is None:
        return False
    if _verifier_totp(appareil, code):
        return True
    secours = (
        CodeSecours.objects.select_for_update()
        .filter(utilisateur=utilisateur, empreinte=_empreinte(code), utilise_le__isnull=True)
        .first()
    )
    if secours is None:
        return False
    secours.utilise_le = timezone.now()
    secours.save(update_fields=["utilise_le"])
    return True


def codes_secours_restants(utilisateur) -> int:
    return CodeSecours.objects.filter(utilisateur=utilisateur, utilise_le__isnull=True).count()


# --- gestion ---


@transaction.atomic
def regenerer_codes_secours(utilisateur, code_totp: str) -> list[str]:
    """Nouveaux codes de secours (les anciens cessent de valoir). Exige un code TOTP, pas un code de secours."""
    appareil = (
        AppareilMFA.objects.select_for_update()
        .filter(utilisateur=utilisateur, confirme=True)
        .first()
    )
    if appareil is None or not _verifier_totp(appareil, code_totp):
        raise CodeInvalide("Ce code n'est pas valable.")
    return _remplacer_codes_secours(utilisateur)


@transaction.atomic
def reinitialiser(utilisateur) -> None:
    """Supprime l'appareil et les codes : à l'ouverture de session suivante, la personne le réactive."""
    AppareilMFA.objects.filter(utilisateur=utilisateur).delete()
    CodeSecours.objects.filter(utilisateur=utilisateur).delete()
    User.objects.filter(pk=utilisateur.pk).update(mfa_enabled=False)
    utilisateur.mfa_enabled = False


# --- session ---

CLE_SESSION = "mfa_verifiee"


def marquer_verifiee(request) -> None:
    request.session[CLE_SESSION] = True
    request.session.cycle_key()  # nouvel identifiant de session : celui d'avant la MFA ne sert plus


def est_verifiee(request) -> bool:
    return bool(request.session.get(CLE_SESSION))


def oublier_verification(request) -> None:
    request.session.pop(CLE_SESSION, None)
```

La double authentification en quelques mots :

1. À l'activation, on génère un **secret** aléatoire que l'utilisateur scanne (QR code) dans son
   application (Google Authenticator, Microsoft Authenticator…).
2. L'application affiche toutes les 30 secondes un **code à 6 chiffres** calculé à partir du secret et de
   l'heure (norme TOTP). Le serveur recalcule le même code et compare, en **temps constant**
   (`secrets.compare_digest`).
3. Un code déjà utilisé est refusé (`dernier_pas`). Un décalage d'horloge d'un intervalle est toléré.
4. On donne **10 codes de secours** à usage unique, au cas où le téléphone serait perdu.

#### `apps/accounts/middleware.py`

*54 lignes* — Porte de la double authentification : refus par défaut tant que la MFA n'est pas passée.

```python
"""Porte de la double authentification : refus par défaut tant que la MFA n'est pas passée.

Un ADMIN ou une DIRECTION qui vient de saisir son mot de passe est connecté, mais sa session n'est
pas « vérifiée » : toute page, hors quelques exceptions, le renvoie vers la saisie du code (ou vers
l'activation de la MFA s'il n'a pas encore d'application). Comme la règle est un refus par défaut
appliqué à chaque requête, elle couvre aussi l'espace d'administration et la documentation de l'API,
sans que chaque vue ait à y penser.

Les requêtes de l'API authentifiées par jeton (JWT) ne passent pas ici : la MFA y est contrôlée à
l'émission du jeton (``apps.api.auth``).
"""

from __future__ import annotations

from urllib.parse import quote

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from . import mfa

# Pages accessibles avant la vérification : la MFA elle-même, la connexion et la déconnexion.
_PREFIXES_LIBRES = ("/mfa/", "/connexion/", "/deconnexion/")
# Pages de l'API ouvertes dans un navigateur (documentation) : redirigées, comme le reste du site.
_PAGES_API_NAVIGATEUR = ("/api/v1/docs/", "/api/v1/schema/")


class MFARequiseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        utilisateur = request.user
        if (
            mfa.mfa_requise(utilisateur)
            and not mfa.est_verifiee(request)
            and not self._est_libre(request.path)
        ):
            if request.path.startswith("/api/") and not request.path.startswith(_PAGES_API_NAVIGATEUR):
                return JsonResponse(
                    {"code": "mfa_requise", "detail": "Double authentification requise."}, status=403
                )
            page = "accounts:mfa_verifier" if mfa.appareil_actif(utilisateur) else "accounts:mfa_activer"
            cible = reverse(page)
            if request.method == "GET":
                cible += f"?next={quote(request.get_full_path(), safe='/')}"
            return redirect(cible)
        return self.get_response(request)

    @staticmethod
    def _est_libre(chemin: str) -> bool:
        return chemin.startswith(_PREFIXES_LIBRES) or chemin.startswith(settings.STATIC_URL)
```

La **porte** : à chaque requête, si l'utilisateur est un ADMIN ou une DIRECTION dont la session n'est pas
« vérifiée », on le renvoie vers la saisie du code. C'est un **refus par défaut** : il couvre aussi
l'administration et la documentation de l'API, sans que chaque vue y pense. Les appels d'API avec un jeton
(JWT) ne passent pas ici : la MFA y est contrôlée à l'émission du jeton (chapitre 28).

## Étape 5 — Administration, démarrage et commande de secours

#### `apps/accounts/admin.py`

*80 lignes*

```python
from urllib.parse import quote

from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.shortcuts import redirect
from django.urls import reverse

from . import mfa
from .models import Role, User
from .signals import mfa_evenement


def connexion_par_la_page_du_site(request, extra_context=None):
    """L'administration n'a pas son propre formulaire de connexion : tout passe par la page du site.

    Ainsi la limitation d'essais et la double authentification s'appliquent partout de la même façon.
    """
    suite = request.GET.get("next") or reverse("admin:index")
    return redirect(f"{reverse('accounts:login')}?next={quote(suite, safe='/')}")


admin.site.login = connexion_par_la_page_du_site


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = (
        "username",
        "get_full_name",
        "role",
        "is_active",
        "is_staff",
        "mfa_enabled",
    )
    list_filter = ("role", "is_active", "is_staff", "mfa_enabled")
    readonly_fields = DjangoUserAdmin.readonly_fields + ("mfa_enabled",)
    fieldsets = DjangoUserAdmin.fieldsets + (
        (
            "ERP",
            {"fields": ("role", "telephone", "mfa_enabled")},
        ),
    )
    actions = ["reinitialiser_mfa"]

    # Un compte de rôle ADMIN (cahier-des-charges.md:48 : gestion des utilisateurs) voit la liste des
    # utilisateurs et peut réinitialiser leur double authentification, sans autre droit de modification :
    # les permissions Django habituelles restent réservées aux superutilisateurs.
    @staticmethod
    def _est_administrateur(request) -> bool:
        return request.user.is_active and request.user.is_staff and request.user.role_effectif == Role.ADMIN

    def has_module_permission(self, request):
        return super().has_module_permission(request) or self._est_administrateur(request)

    def has_view_permission(self, request, obj=None):
        return super().has_view_permission(request, obj) or self._est_administrateur(request)

    def has_reinitialiser_mfa_permission(self, request):
        return request.user.is_superuser or self._est_administrateur(request)

    @admin.action(
        description="Réinitialiser la double authentification (téléphone perdu)",
        permissions=["reinitialiser_mfa"],
    )
    def reinitialiser_mfa(self, request, queryset):
        """La personne devra réactiver la MFA à sa prochaine connexion. Action tracée au journal d'audit."""
        for utilisateur in queryset:
            mfa.reinitialiser(utilisateur)
            mfa_evenement.send(
                sender=type(self),
                request=request,
                utilisateur=utilisateur,
                evenement=f"reinitialisation_par_{request.user.username}",
                succes=True,
            )
        self.message_user(
            request,
            f"Double authentification réinitialisée pour {queryset.count()} compte(s).",
            messages.SUCCESS,
        )
```

L'**administration Django** (`/admin/`) est une interface générée automatiquement. Ici on lui apprend à
lister les utilisateurs, à réinitialiser la MFA d'un compte (téléphone perdu), et on redirige sa page de
connexion vers celle du site, pour que l'anti force brute et la MFA s'appliquent partout.

#### `apps/accounts/apps.py`

*10 lignes*

```python
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'
    label = 'accounts'

    def ready(self):
        from . import signals  # noqa: F401  (branche les récepteurs)
```

#### `apps/accounts/management/commands/reinitialiser_mfa.py`

*29 lignes*

```python
from django.core.management.base import BaseCommand, CommandError

from apps.accounts import mfa
from apps.accounts.models import User
from apps.accounts.signals import mfa_evenement


class Command(BaseCommand):
    help = (
        "Réinitialise la double authentification d'un compte (téléphone perdu, plus de codes de "
        "secours). À utiliser quand plus aucun administrateur ne peut le faire depuis l'interface."
    )

    def add_arguments(self, parser):
        parser.add_argument("identifiant", help="Identifiant (username) du compte")

    def handle(self, *args, identifiant, **options):
        try:
            utilisateur = User.objects.get(username=identifiant)
        except User.DoesNotExist as erreur:
            raise CommandError(f"Aucun compte « {identifiant} ».") from erreur
        mfa.reinitialiser(utilisateur)
        mfa_evenement.send(
            sender=type(self), request=None, utilisateur=utilisateur,
            evenement="reinitialisation_en_ligne_de_commande", succes=True,
        )
        self.stdout.write(self.style.SUCCESS(
            f"Double authentification réinitialisée pour {identifiant} : elle sera à réactiver à sa prochaine connexion."
        ))
```

Une **commande de gestion** : `python manage.py reinitialiser_mfa <identifiant>`. Utile quand plus aucun
administrateur ne peut réinitialiser la MFA depuis l'interface.

## Étape 6 — Tests et fabriques

#### `apps/accounts/tests/factories.py`

*16 lignes*

```python
import factory

from apps.accounts.models import Role, User


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("username",)

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@densourcegroup.ci")
    first_name = "Jean"
    last_name = "Kouassi"
    role = Role.ADMIN
    password = factory.PostGenerationMethodCall("set_password", "Test-Passw0rd!")
```

`UserFactory` fabrique un utilisateur valide en une ligne : `UserFactory(role=Role.RH)`. On s'en servira
dans des centaines de tests.

#### `apps/accounts/tests/helpers_mfa.py`

*20 lignes* — Aides communes aux tests de la double authentification.

```python
"""Aides communes aux tests de la double authentification."""

import pyotp

from apps.accounts import mfa
from apps.accounts.models import AppareilMFA


def activer_mfa(utilisateur):
    """Active la MFA d'un compte ; renvoie (appareil, codes de secours)."""
    appareil = mfa.preparer_activation(utilisateur)
    codes = mfa.confirmer_activation(utilisateur, pyotp.TOTP(appareil.secret).now())
    appareil.refresh_from_db()
    return appareil, codes


def code_frais(utilisateur):
    """Code TOTP valable maintenant, même si un code vient d'être utilisé (anti-rejeu remis à zéro)."""
    AppareilMFA.objects.filter(utilisateur=utilisateur).update(dernier_pas=0)
    return pyotp.TOTP(AppareilMFA.objects.get(utilisateur=utilisateur).secret).now()
```

#### `apps/accounts/README.md`

*56 lignes* — accounts

```markdown
# accounts

Rôle : authentification, 7 rôles utilisateurs (ADMIN, DIRECTION, RH, CHARGE_CLIENTELE, PARCAUTO,
FINANCES, CHAUFFEUR) — cahier-des-charges.md:44-55 — et sécurité de la connexion (étape 7, lot 1).
Dépend uniquement de `core` (architecture.md:134) ; `audit` s'abonne à ses signaux, pas l'inverse.

Entités : `User` (`AUTH_USER_MODEL`), `Role`, `AppareilMFA` (application TOTP d'un compte),
`CodeSecours` (10 codes à usage unique, empreinte SHA-256 seulement).

## Connexion

- **Mots de passe en Argon2** (cahier-des-charges.md:273). PBKDF2 reste accepté : un ancien hachage est
  converti à la prochaine connexion. Longueur minimale : 10 caractères.
- **Anti force brute** (`throttle.py`, cache Django) : 5 échecs pour un même identifiant depuis une même
  adresse, ou 20 échecs depuis une adresse, bloquent la connexion 15 minutes, **même avec le bon mot de
  passe**. Le blocage compte aussi les échecs de l'API et de l'administration. Il ne dit pas si le
  compte existe. En production, le cache doit être partagé entre processus (Redis, lot 2).
- **Adresse du client** (`core.middleware.get_client_ip`) : `X-Forwarded-For` n'est lu que si
  `TRUSTED_PROXY_COUNT` (proxys de confiance) est renseigné, et seule l'adresse ajoutée par eux compte.
  Sinon un client pourrait forger son adresse et échapper à la limitation. Derrière Nginx : `1`.
- L'administration Django n'a plus son propre formulaire : `/admin/login/` renvoie vers `/connexion/`.
- **Mot de passe oublié** (`/mot-de-passe/`) : les 4 vues standard de Django (demande de l'adresse,
  confirmation d'envoi, lien reçu par e-mail, nouveau mot de passe), gabarits français assortis au
  reste du site. Ne révèle jamais si l'adresse correspond à un compte (même page dans les deux cas).
  Le nouveau mot de passe passe par les mêmes règles qu'à la création (Argon2, longueur 10,
  validateurs). Nécessite un serveur SMTP réel en production (`EMAIL_HOST` et consorts,
  `.env.example`) ; sans lui, sans autre canal, cette fonctionnalité ne peut pas envoyer de lien.
  Tracé au journal d'audit (module AUTH, entité User), sans jamais inscrire le mot de passe.

## Double authentification (MFA)

Obligatoire pour l'ADMIN et la DIRECTION (`settings.MFA_ROLES`, `MFA_ENFORCED`), cahier-des-charges.md:276.

- **Porte** (`middleware.py`) : refus par défaut. Un ADMIN ou une DIRECTION dont la session n'est pas
  « vérifiée » est renvoyé vers `/mfa/verifier/` (ou `/mfa/activer/` s'il n'a pas d'appareil) pour toute page,
  administration et documentation de l'API comprises. Les requêtes d'API reçoivent un 403 JSON.
  Seules `/mfa/`, `/connexion/`, `/deconnexion/` et `/static/` sont libres.
- **Activation** : à la première connexion, QR code à scanner (Google/Microsoft Authenticator…), premier
  code, puis 10 codes de secours affichés **une seule fois**.
- **Vérification** (`mfa.py`) : code à 6 chiffres sur 30 s (±1 intervalle), **un code ne sert qu'une fois**
  (anti-rejeu), 5 codes faux par 10 minutes puis blocage. Une nouvelle ouverture de session redemande la MFA.
- **API** : `POST /api/v1/auth/token/` exige le champ `otp` pour ces rôles (code ou code de secours) ; un
  compte sans MFA activée doit d'abord l'activer sur le site (`401` avec `code` = `mfa_non_activee`,
  `mfa_requise` ou `mfa_invalide`).
- **Téléphone perdu** : codes de secours, sinon un compte de rôle ADMIN réinitialise l'appareil depuis
  l'administration (action « Réinitialiser la double authentification »), ou en ligne de commande :
  `python manage.py reinitialiser_mfa <identifiant>`. Les codes se régénèrent depuis l'en-tête (`/mfa/codes/`).
  Toutes les étapes sont inscrites au journal d'audit (module AUTH, entité MFA), sans aucun secret.
- Tests : `MFA_ENFORCED = False` dans `settings/test.py` ; les tests de la MFA la réactivent.

Limites connues :
- Le secret TOTP est stocké tel quel en base (il doit pouvoir être relu pour recalculer les codes).
- L'activation se fait à la première connexion : un mot de passe volé **avant** l'activation permettrait
  d'enrôler l'appareil d'un tiers. Activer la MFA de chaque ADMIN et DIRECTION dès la création du compte.
- Un compte ADMIN (non superutilisateur) peut lister les utilisateurs et réinitialiser leur MFA dans
  l'administration, mais ne peut pas les modifier : ces droits restent réservés aux superutilisateurs.
```

#### `apps/accounts/tests/test_models.py`

*34 lignes*

```python
import pytest

from apps.accounts.models import Role

from .factories import UserFactory

pytestmark = pytest.mark.django_db


def test_user_str_returns_full_name_when_available():
    user = UserFactory(first_name="Awa", last_name="Traore")

    assert str(user) == "Awa Traore"


def test_user_str_falls_back_to_username_without_name():
    user = UserFactory(first_name="", last_name="", username="chauffeur01")

    assert str(user) == "chauffeur01"


def test_is_admin_true_only_for_admin_role():
    admin = UserFactory(role=Role.ADMIN)
    chauffeur = UserFactory(role=Role.CHAUFFEUR)

    assert admin.is_admin is True
    assert chauffeur.is_admin is False


def test_is_direction_true_only_for_direction_role():
    direction = UserFactory(role=Role.DIRECTION)

    assert direction.is_direction is True
    assert direction.is_admin is False
```

#### `apps/accounts/tests/test_permissions.py`

*41 lignes*

```python
from types import SimpleNamespace

import pytest

from apps.accounts.models import Role
from apps.accounts.permissions import IsAdmin, IsAdminOrDirection, IsChauffeur

from .factories import UserFactory

pytestmark = pytest.mark.django_db


def _request_for(user):
    return SimpleNamespace(user=user)


def test_is_admin_permission_grants_admin_denies_others():
    admin = UserFactory(role=Role.ADMIN)
    chauffeur = UserFactory(role=Role.CHAUFFEUR)
    perm = IsAdmin()

    assert perm.has_permission(_request_for(admin), None) is True
    assert perm.has_permission(_request_for(chauffeur), None) is False


def test_is_admin_or_direction_grants_both_roles_denies_rh():
    admin = UserFactory(role=Role.ADMIN)
    direction = UserFactory(role=Role.DIRECTION)
    rh = UserFactory(role=Role.RH)
    perm = IsAdminOrDirection()

    assert perm.has_permission(_request_for(admin), None) is True
    assert perm.has_permission(_request_for(direction), None) is True
    assert perm.has_permission(_request_for(rh), None) is False


def test_has_role_denies_unauthenticated_user():
    anonymous = SimpleNamespace(is_authenticated=False, role=None)
    perm = IsChauffeur()

    assert perm.has_permission(_request_for(anonymous), None) is False
```

## Étape 7 — Déclarer l'application dans les réglages

#### `config/settings/base.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/settings/base.py (avant)
+++ config/settings/base.py (après)
@@ -53,4 +53,5 @@
 LOCAL_APPS = [
     "apps.core",
+    "apps.accounts",
 ]
 
@@ -58,4 +59,5 @@
 
 # 7 rôles, RBAC simple — cahier-des-charges.md:44-55, architecture.md:534.
+AUTH_USER_MODEL = "accounts.User"
 
 LOGIN_URL = "accounts:login"
@@ -81,4 +83,5 @@
     "django.middleware.csrf.CsrfViewMiddleware",
     "django.contrib.auth.middleware.AuthenticationMiddleware",
+    "apps.accounts.middleware.MFARequiseMiddleware",
     "django.contrib.messages.middleware.MessageMiddleware",
     "django.middleware.clickjacking.XFrameOptionsMiddleware",
```

Trois modifications : `"apps.accounts"` dans `LOCAL_APPS`, **`AUTH_USER_MODEL`** (le point crucial) et la
porte MFA dans `MIDDLEWARE` (juste après `AuthenticationMiddleware`, car elle a besoin de savoir qui est
connecté).

## Étape 8 — Migrations : cette fois, on migre

```bash
python manage.py makemigrations accounts
python manage.py migrate
```

**Résultat attendu :** `makemigrations` liste `Create model User`, `Create model AppareilMFA`,
`Create model CodeSecours` ; `migrate` applique une vingtaine de migrations (`contenttypes`, `auth`,
`admin`, `sessions`, `core`, `accounts`…) et se termine par `OK`. Un fichier `db.sqlite3` apparaît à la
racine : c'est votre base de développement.

> **Si `migrate` échoue avec `InconsistentMigrationHistory`** : une migration a été lancée avec le
> `User` par défaut. Supprimez `db.sqlite3` et relancez `python manage.py migrate` (aucune donnée à perdre
> à ce stade).

## Vérifier le chapitre

```bash
python manage.py check
```

```bash
python -m pytest apps/accounts/tests/test_models.py apps/accounts/tests/test_permissions.py -q --no-cov
```

**Résultat attendu :** `7 passed` (pour les 2 fichier(s) de tests présentés dans ce chapitre).

Les tests de connexion, de MFA et de menu par rôle **ouvrent des pages** et seront présentés plus tard
(chapitres 16 et suivants), quand les écrans existeront.

Petit essai dans le shell : créer un utilisateur et lire son rôle effectif.

```bash
python manage.py shell -c "from apps.accounts.models import User; u = User.objects.create_user('essai', password='Essai-de-mot-de-passe-1', role='RH'); print(u, u.role_effectif, u.check_password('Essai-de-mot-de-passe-1')); u.delete()"
```

**Résultat attendu :** `essai RH True`.

## Ce qu'il faut retenir

- Le **rôle** est un champ de l'utilisateur ; la **garde** est un mixin de vue ; le **menu** est un registre.
- La sécurité d'une connexion se pense en couches : mot de passe (Argon2), limitation d'essais, double
  authentification, session courte.
- Deux apps peuvent collaborer par **signal** sans s'importer.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 3 : app accounts (utilisateurs, 7 rôles, garde d'accès, menu, MFA, anti force brute)"
```

---

[← Chapitre 2](02-core.md) · [Sommaire](README.md) · [Chapitre 4 →](04-audit.md)
