from django.contrib import admin

from .models import Compte, EcritureComptable, LigneEcriture


@admin.register(Compte)
class CompteAdmin(admin.ModelAdmin):
    list_display = ("numero", "libelle", "nature", "actif")
    list_filter = ("nature", "actif")
    search_fields = ("numero", "libelle")


class LigneEcritureInline(admin.TabularInline):
    model = LigneEcriture
    extra = 0
    fields = ("compte", "sens", "montant", "libelle", "tiers_type", "tiers_id")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EcritureComptable)
class EcritureComptableAdmin(admin.ModelAdmin):
    list_display = ("numero", "journal", "date_ecriture", "libelle", "statut", "piece_reference")
    list_filter = ("journal", "statut")
    search_fields = ("numero", "libelle", "piece_reference")
    inlines = [LigneEcritureInline]

    def get_queryset(self, request):
        return EcritureComptable.objects.select_related("cree_par", "valide_par")

    def has_delete_permission(self, request, obj=None):
        return False
