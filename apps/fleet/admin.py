from django.contrib import admin

from apps.core.admin import SuppressionLogiqueAdmin

from .models import DocumentReglementaire, Vehicule


class DocumentInline(admin.TabularInline):
    model = DocumentReglementaire
    extra = 0

    def get_queryset(self, request):
        return DocumentReglementaire.objects.all()


@admin.register(Vehicule)
class VehiculeAdmin(SuppressionLogiqueAdmin):
    list_display = ("immatriculation", "marque", "modele", "statut", "kilometrage")
    list_filter = ("statut", "marque")
    search_fields = ("immatriculation", "vin")
    inlines = [DocumentInline]

