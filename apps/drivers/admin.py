from django.contrib import admin

from .models import Chauffeur, Copilote


@admin.register(Chauffeur)
class ChauffeurAdmin(admin.ModelAdmin):
    list_display = ("personnel", "statut", "date_expiration_permis")
    list_filter = ("statut",)
    search_fields = ("personnel__matricule", "personnel__nom", "numero_permis")

    def get_queryset(self, request):
        return Chauffeur.objects.select_related("personnel")


@admin.register(Copilote)
class CopiloteAdmin(admin.ModelAdmin):
    list_display = ("personnel", "statut")
    list_filter = ("statut",)
    search_fields = ("personnel__matricule", "personnel__nom")

    def get_queryset(self, request):
        return Copilote.objects.select_related("personnel")
