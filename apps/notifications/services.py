"""Envoi et lecture des notifications.

Une notification est toujours enregistrée dans l'application ; elle est aussi envoyée par
e-mail si ``NOTIFICATIONS_EMAIL`` est actif et que le destinataire a une adresse. Un e-mail
qui échoue est journalisé mais ne fait jamais échouer l'opération métier qui l'a déclenchée.
"""

from __future__ import annotations

import logging
from typing import Iterable

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.accounts.models import User

from .models import CategorieNotification, NiveauNotification, Notification

logger = logging.getLogger(__name__)


def utilisateurs_du_role(*roles: str) -> QuerySet[User]:
    """Comptes actifs ayant l'un de ces rôles."""
    return User.objects.filter(role__in=roles, is_active=True)


def envoyer_email(notification_id: int) -> None:
    notification = Notification.objects.select_related("destinataire").get(pk=notification_id)
    adresse = notification.destinataire.email
    if not adresse:
        return
    corps = notification.message
    if notification.url:
        corps += f"\n\nOuvrir : {settings.NOTIFICATIONS_URL_BASE.rstrip('/')}{notification.url}"
    try:
        send_mail(notification.titre, corps, settings.DEFAULT_FROM_EMAIL, [adresse])
    except Exception:  # noqa: BLE001 - un e-mail perdu ne doit pas bloquer le métier
        logger.exception("Envoi de la notification %s par e-mail impossible", notification_id)
        return
    Notification.objects.filter(pk=notification_id).update(email_envoye=True)


def notifier(
    destinataires: Iterable[User | None],
    *,
    categorie: str,
    titre: str,
    message: str = "",
    url: str = "",
    niveau: str = NiveauNotification.INFO,
    cle: str = "",
) -> list[Notification]:
    """Crée une notification par destinataire actif et retourne celles qui ont été créées.

    ``cle`` : si ce destinataire a déjà reçu une notification avec cette clé, rien n'est
    créé (le rappel n'est envoyé qu'une fois). Les doublons dans ``destinataires`` et les
    valeurs vides sont ignorés.
    """
    creees: list[Notification] = []
    vus: set[int] = set()
    for utilisateur in destinataires:
        if utilisateur is None or not utilisateur.is_active or utilisateur.pk in vus:
            continue
        vus.add(utilisateur.pk)
        if cle and Notification.all_objects.filter(
            destinataire=utilisateur, cle_unicite=cle
        ).exists():
            continue
        notification = Notification.objects.create(
            destinataire=utilisateur,
            categorie=categorie,
            niveau=niveau,
            titre=titre[:200],
            message=message,
            url=url,
            cle_unicite=cle,
        )
        creees.append(notification)
        if settings.NOTIFICATIONS_EMAIL and utilisateur.email:
            # Import différé : évite un cycle avec tasks.py, qui appelle `envoyer_email` ci-dessus.
            from .tasks import envoyer_email_notification

            transaction.on_commit(lambda pk=notification.pk: envoyer_email_notification.delay(pk))
    return creees


# --- lecture ---


def notifications_de(utilisateur: User, *, non_lues: bool = False) -> QuerySet[Notification]:
    resultat = Notification.objects.filter(destinataire=utilisateur)
    return resultat.filter(lue_le__isnull=True) if non_lues else resultat


def nombre_non_lues(utilisateur: User) -> int:
    return notifications_de(utilisateur, non_lues=True).count()


def marquer_lue(notification: Notification) -> Notification:
    if notification.lue_le is None:
        notification.lue_le = timezone.now()
        notification.save(update_fields=["lue_le", "updated_at"])
    return notification


def marquer_toutes_lues(utilisateur: User) -> int:
    """Marque lues toutes les notifications de l'utilisateur ; retourne leur nombre."""
    return notifications_de(utilisateur, non_lues=True).update(
        lue_le=timezone.now(), updated_at=timezone.now()
    )


__all__ = [
    "CategorieNotification",
    "NiveauNotification",
    "marquer_lue",
    "marquer_toutes_lues",
    "nombre_non_lues",
    "notifications_de",
    "notifier",
    "utilisateurs_du_role",
]
