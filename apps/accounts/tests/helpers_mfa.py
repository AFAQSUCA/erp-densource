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
