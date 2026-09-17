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

from . import services


@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs):
    services.log_login(user, request)


@receiver(user_logged_out)
def on_user_logged_out(sender, request, user, **kwargs):
    services.log_logout(user, request)


@receiver(user_login_failed)
def on_user_login_failed(sender, credentials, request=None, **kwargs):
    services.log_login_failed(credentials.get("username", ""), request)
