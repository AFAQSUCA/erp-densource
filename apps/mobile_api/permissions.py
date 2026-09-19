from rest_framework.permissions import BasePermission

from apps.accounts.models import Role
from apps.drivers import services as drivers_services


class EstChauffeur(BasePermission):
    """Compte de rôle CHAUFFEUR rattaché à une fiche chauffeur (architecture.md:435)."""

    message = "Cette ressource est réservée aux chauffeurs."

    def has_permission(self, request, view):
        utilisateur = request.user
        if not (utilisateur and utilisateur.is_authenticated):
            return False
        if utilisateur.role_effectif != Role.CHAUFFEUR:
            return False
        return drivers_services.chauffeur_de(utilisateur) is not None
