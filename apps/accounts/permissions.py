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
