from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Consultation ADMIN, lecture seule DIRECTION — cahier-des-charges.md:81.

    Append-only : ajout/modification/suppression désactivés dans l'admin,
    y compris pour ADMIN (une entrée ne se crée que via
    :func:`apps.audit.services.log_action`).
    """

    list_display = (
        "date_heure",
        "utilisateur_nom",
        "role",
        "action",
        "module",
        "entite",
        "entite_id",
        "statut",
    )
    list_filter = ("action", "module", "statut", "role")
    search_fields = ("utilisateur_nom", "entite", "adresse_ip")
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        user = request.user
        return bool(user.is_superuser or getattr(user, "role", None) in ("ADMIN", "DIRECTION"))
