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

from apps.accounts.signals import mfa_evenement, mot_de_passe_reinitialise

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


@receiver(mot_de_passe_reinitialise)
def on_mot_de_passe_reinitialise(sender, request, utilisateur, **kwargs):
    """« Mot de passe oublié » mené à son terme : tracé, sans jamais inscrire le mot de passe."""
    services.log_action(
        action=ActionChoices.UPDATE,
        module="AUTH",
        entite="User",
        entite_id=utilisateur.pk,
        utilisateur=utilisateur,
        nouvelle_valeur={"evenement": "mot_de_passe_reinitialise"},
        request=request,
    )
