from django.contrib import admin

from .models import OrdreReparation


@admin.register(OrdreReparation)
class OrdreReparationAdmin(admin.ModelAdmin):
    """Lecture seule : ouverture et clôture passent par apps/garage/services.py,
    seul moyen de garder le statut du camion cohérent."""

    list_display = ("numero", "vehicule", "type_or", "lieu", "statut", "date_ouverture")
    list_filter = ("statut", "type_or", "lieu")
    search_fields = ("numero", "vehicule__immatriculation")

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in OrdreReparation._meta.fields]

    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        return OrdreReparation.objects.select_related("vehicule")
