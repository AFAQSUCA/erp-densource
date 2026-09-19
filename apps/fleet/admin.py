from django.contrib import admin

from .models import DocumentReglementaire, Vehicule


class DocumentInline(admin.TabularInline):
    model = DocumentReglementaire
    extra = 0

    def get_queryset(self, request):
        return DocumentReglementaire.objects.all()


@admin.register(Vehicule)
class VehiculeAdmin(admin.ModelAdmin):
    list_display = ("immatriculation", "marque", "modele", "statut", "kilometrage")
    list_filter = ("statut", "marque")
    search_fields = ("immatriculation", "vin")
    inlines = [DocumentInline]

    def get_queryset(self, request):
        return Vehicule.objects.all()
