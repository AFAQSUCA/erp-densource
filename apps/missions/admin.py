from django.contrib import admin

from .models import Mission


@admin.register(Mission)
class MissionAdmin(admin.ModelAdmin):
    """Lecture seule : le cycle de vie passe par apps/missions/services.py."""

    list_display = ("numero", "client", "vehicule", "chauffeur", "statut", "prix_convenu")
    list_filter = ("statut",)
    search_fields = ("numero", "client__raison_sociale")

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in Mission._meta.fields]

    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        return Mission.objects.select_related("client", "vehicule", "chauffeur__personnel")
