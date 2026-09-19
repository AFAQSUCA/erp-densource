"""Permissions DRF fondées sur les mêmes ensembles de rôles que les écrans web.

Chaque app définit déjà qui peut la consulter (``permissions.CONSULTATION``) : l'API réutilise
ces ensembles, pour qu'un rôle n'obtienne jamais par l'API ce que l'écran lui refuse.
"""

from rest_framework.permissions import BasePermission

from apps.accounts.models import Role


def role_requis(roles: frozenset[str]) -> type[BasePermission]:
    """Fabrique une permission qui exige un rôle parmi ``roles`` (superutilisateur = ADMIN)."""

    class RoleRequis(BasePermission):
        message = "Votre rôle n'a pas accès à cette ressource."

        def has_permission(self, request, view):
            utilisateur = request.user
            return bool(
                utilisateur and utilisateur.is_authenticated and utilisateur.role_effectif in roles
            )

    RoleRequis.__name__ = "RoleRequis"
    return RoleRequis


class EstAdminOuDirection(BasePermission):
    """Documentation de l'API : réservée à l'ADMIN et à la DIRECTION connectés."""

    def has_permission(self, request, view):
        utilisateur = request.user
        return bool(
            utilisateur
            and utilisateur.is_authenticated
            and utilisateur.role_effectif in (Role.ADMIN, Role.DIRECTION)
        )
