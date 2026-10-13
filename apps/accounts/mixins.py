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
        if not utilisateur.is_authenticated:
            return self.handle_no_permission()
        if utilisateur.role_effectif not in self.roles:
            raise PermissionDenied
        self.charger_objet(request, *args, **kwargs)
        return super().dispatch(request, *args, **kwargs)

    def charger_objet(self, request, *args, **kwargs) -> None:
        """Charge l'objet de la page (``self.compte = get_object_or_404(...)``), **après** les contrôles de connexion
        et de rôle : chargé avant, un rôle non autorisé recevait 404 ou 403 selon que l'objet existe, et pouvait
        ainsi deviner les identifiants existants (audit TECH-34). Ne rien charger dans ``dispatch``."""
