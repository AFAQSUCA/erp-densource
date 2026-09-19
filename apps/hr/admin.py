from django.contrib import admin

from .models import Conge, Personnel, ValidationConge


@admin.register(Personnel)
class PersonnelAdmin(admin.ModelAdmin):
    list_display = ("matricule", "nom", "prenom", "poste", "departement")
    list_filter = ("departement",)
    search_fields = ("matricule", "nom", "prenom")

    def get_queryset(self, request):
        return Personnel.objects.all()


class ValidationInline(admin.TabularInline):
    model = ValidationConge
    extra = 0
    readonly_fields = ("niveau", "validateur", "decision", "commentaire", "date_decision")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Conge)
class CongeAdmin(admin.ModelAdmin):
    """Lecture seule : les transitions passent par apps/hr/services.py."""

    list_display = ("employe", "date_debut", "date_fin", "jours", "statut")
    list_filter = ("statut",)
    inlines = [ValidationInline]

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in Conge._meta.fields]

    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        return Conge.objects.select_related("employe")
