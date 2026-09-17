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
