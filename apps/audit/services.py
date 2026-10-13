"""Logique métier du journal d'audit — conventions.md §2.

Point d'entrée unique pour créer une ligne ``AuditLog`` : les apps métier
(fleet, missions, hr...) appelleront :func:`log_action` depuis leurs
propres signaux ``post_save``/``post_delete`` au fur et à mesure de leur
création (cahier-des-charges.md:76 "Enregistrement auto via triggers SQL
ou middleware").
"""

from __future__ import annotations

from datetime import date
from typing import Any

from django.contrib.auth import get_user_model
from django.db.models import QuerySet

from apps.core.middleware import get_client_ip
from apps.core.search import filtrer_par_texte

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
        # Nom complet, à défaut l'identifiant de connexion ; rôle effectif (un superutilisateur agit en ADMIN) :
        # jamais une entrée sans auteur lisible (audit M1-53, M1-54).
        utilisateur_nom=getattr(utilisateur, "get_full_name", lambda: "")() or getattr(utilisateur, "username", "") or "",
        role=getattr(utilisateur, "role_effectif", None) or getattr(utilisateur, "role", "") or "",
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


def identifiant_journalise(username: str) -> str:
    """Identifiant tapé lors d'une connexion échouée, tel qu'inscrit au journal (audit AUD-17) : en entier s'il
    désigne un compte existant (on sait quel compte est visé) ; sinon masqué, car ce peut être un mot de passe tapé
    dans le champ « Identifiant »."""
    username = (username or "").strip()[:150]
    if not username or get_user_model().objects.filter(username__iexact=username).exists():
        return username
    return f"{username[:2]}… ({len(username)} caractères, compte inconnu)"


def log_login_failed(username: str, request) -> AuditLog:
    return log_action(
        action=ActionChoices.LOGIN,
        module="AUTH",
        entite="User",
        utilisateur=None,
        nouvelle_valeur={"username_tente": identifiant_journalise(username)},
        request=request,
        statut=StatutChoices.FAILED,
    )


# --- consultation (écran du journal, ADMIN et DIRECTION — cahier-des-charges.md:81) ---


def journal_queryset() -> QuerySet[AuditLog]:
    return AuditLog.objects.select_related("utilisateur")


def rechercher(
    *,
    recherche: str = "",
    module: str = "",
    action: str = "",
    statut: str = "",
    date_debut: date | None = None,
    date_fin: date | None = None,
) -> QuerySet[AuditLog]:
    """Journal filtré par texte (utilisateur, entité), module, action, statut et période.

    ``date_debut``/``date_fin`` bornent ``date_heure`` (jour local, bornes incluses).
    """
    resultat = journal_queryset()
    if module:
        resultat = resultat.filter(module=module)
    if action in ActionChoices.values:
        resultat = resultat.filter(action=action)
    if statut in StatutChoices.values:
        resultat = resultat.filter(statut=statut)
    if date_debut:
        resultat = resultat.filter(date_heure__date__gte=date_debut)
    if date_fin:
        resultat = resultat.filter(date_heure__date__lte=date_fin)
    return filtrer_par_texte(resultat, recherche, "utilisateur_nom", "entite", "adresse_ip")


def historique(entite: str, entite_id: int) -> QuerySet[AuditLog]:
    """Historique complet d'une fiche précise (section « Historique » d'un écran de détail)."""
    return journal_queryset().filter(entite=entite, entite_id=entite_id)


def modules_utilises() -> list[str]:
    """Modules déjà présents dans le journal, pour peupler le filtre (ordre alphabétique)."""
    return sorted(AuditLog.objects.values_list("module", flat=True).distinct())
