from django.contrib import admin

from .models import AttributionConge, Conge, JourFerie, Personnel, ValidationConge


@admin.register(Personnel)
class PersonnelAdmin(admin.ModelAdmin):
    list_display = ("matricule", "nom", "prenom", "poste", "departement", "superieur")
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


@admin.register(JourFerie)
class JourFerieAdmin(admin.ModelAdmin):
    """Saisie des fêtes musulmanes fixées chaque année par décret."""

    list_display = ("date", "libelle")
    ordering = ("-date",)

    def get_queryset(self, request):
        return JourFerie.objects.all()


@admin.register(AttributionConge)
class AttributionCongeAdmin(admin.ModelAdmin):
    """Lecture seule : une attribution se crée via services.accorder_jours_exceptionnels."""

    list_display = ("employe", "annee", "jours", "motif", "accorde_par")

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in AttributionConge._meta.fields]

    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        return AttributionConge.objects.select_related("employe")
