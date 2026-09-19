from django.contrib import admin

from .models import Plein


@admin.register(Plein)
class PleinAdmin(admin.ModelAdmin):
    """Lecture seule : un plein se saisit par apps/fuel/services.py, qui calcule
    consommation et alertes à partir de l'historique."""

    list_display = (
        "date_plein",
        "vehicule",
        "chauffeur",
        "quantite_litres",
        "consommation",
        "niveau_alerte",
        "anomalie",
    )
    list_filter = ("niveau_alerte", "anomalie", "alerte_saisie")
    search_fields = ("vehicule__immatriculation", "numero_ticket", "station")

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in Plein._meta.fields]

    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        return Plein.objects.select_related("vehicule", "chauffeur__personnel")
