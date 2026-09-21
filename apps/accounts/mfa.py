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
