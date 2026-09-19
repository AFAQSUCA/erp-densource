from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied


class RoleRequiredMixin(LoginRequiredMixin):
    """Vue réservée aux utilisateurs connectés dont le rôle est dans ``roles``.

    Non connecté → redirection vers la connexion ; connecté mais rôle non
    autorisé → 403. Contrôle côté serveur : masquer un bouton dans le template
    ne protège rien, c'est cette garde qui protège.
    """

    roles: frozenset[str] = frozenset()

    def dispatch(self, request, *args, **kwargs):
        utilisateur = request.user
        if utilisateur.is_authenticated and utilisateur.role_effectif not in self.roles:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
