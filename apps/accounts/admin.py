from urllib.parse import quote

from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.shortcuts import redirect
from django.urls import reverse

from . import mfa
from .models import Role, User
from .signals import mfa_evenement


def connexion_par_la_page_du_site(request, extra_context=None):
    """L'administration n'a pas son propre formulaire de connexion : tout passe par la page du site.

    Ainsi la limitation d'essais et la double authentification s'appliquent partout de la même façon.
    """
    suite = request.GET.get("next") or reverse("admin:index")
    return redirect(f"{reverse('accounts:login')}?next={quote(suite, safe='/')}")


admin.site.login = connexion_par_la_page_du_site


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = (
        "username",
        "get_full_name",
        "role",
        "is_active",
        "is_staff",
        "mfa_enabled",
    )
    list_filter = ("role", "is_active", "is_staff", "mfa_enabled")
    readonly_fields = DjangoUserAdmin.readonly_fields + ("mfa_enabled",)
    fieldsets = DjangoUserAdmin.fieldsets + (
        (
            "ERP",
            {"fields": ("role", "telephone", "mfa_enabled")},
        ),
    )
    actions = ["reinitialiser_mfa"]

    # Un compte de rôle ADMIN (cahier-des-charges.md:48 : gestion des utilisateurs) voit la liste des
    # utilisateurs et peut réinitialiser leur double authentification, sans autre droit de modification :
    # les permissions Django habituelles restent réservées aux superutilisateurs.
    @staticmethod
    def _est_administrateur(request) -> bool:
        return request.user.is_active and request.user.is_staff and request.user.role_effectif == Role.ADMIN

    def has_module_permission(self, request):
        return super().has_module_permission(request) or self._est_administrateur(request)

    def has_view_permission(self, request, obj=None):
        return super().has_view_permission(request, obj) or self._est_administrateur(request)

    def has_reinitialiser_mfa_permission(self, request):
        return request.user.is_superuser or self._est_administrateur(request)

    @admin.action(
        description="Réinitialiser la double authentification (téléphone perdu)",
        permissions=["reinitialiser_mfa"],
    )
    def reinitialiser_mfa(self, request, queryset):
        """La personne devra réactiver la MFA à sa prochaine connexion. Action tracée au journal d'audit."""
        for utilisateur in queryset:
            mfa.reinitialiser(utilisateur)
            mfa_evenement.send(
                sender=type(self),
                request=request,
                utilisateur=utilisateur,
                evenement=f"reinitialisation_par_{request.user.username}",
                succes=True,
            )
        self.message_user(
            request,
            f"Double authentification réinitialisée pour {queryset.count()} compte(s).",
            messages.SUCCESS,
        )
