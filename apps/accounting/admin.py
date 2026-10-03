from django.contrib import admin

from .models import Compte, EcritureComptable, ExerciceComptable, LigneEcriture

# Le grand livre est en lecture seule dans l'admin : une écriture ne se crée, ne se valide et ne se corrige que
# par ``accounting.services`` (équilibre, numéro, rôle DIRECTION, exercice ouvert, contre-passation). Passer par
# l'admin contournerait ces contrôles (audit ACC-01 : un brouillon pouvait être validé sans équilibre, ni
# numéro, ni DIRECTION ; une ligne ajoutée à une écriture validée).


class LectureSeuleAdmin(admin.ModelAdmin):
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Compte)
class CompteAdmin(admin.ModelAdmin):
    list_display = ("numero", "libelle", "nature", "actif")
    list_filter = ("nature", "actif")
    search_fields = ("numero", "libelle")

    def get_readonly_fields(self, request, obj=None):
        # Comme ``services.modifier_compte`` : le numéro et la nature ne changent plus une fois le compte créé,
        # pour ne jamais reclasser silencieusement des écritures déjà posées.
        return ("numero", "nature") if obj is not None else ()


class LigneEcritureInline(admin.TabularInline):
    model = LigneEcriture
    extra = 0
    fields = ("compte", "sens", "montant", "libelle", "tiers_type", "tiers_id")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EcritureComptable)
class EcritureComptableAdmin(LectureSeuleAdmin):
    list_display = ("numero", "journal", "date_ecriture", "libelle", "statut", "piece_reference")
    list_filter = ("journal", "statut")
    search_fields = ("numero", "libelle", "piece_reference")
    inlines = [LigneEcritureInline]

    def get_queryset(self, request):
        return EcritureComptable.objects.select_related("cree_par", "valide_par")


@admin.register(ExerciceComptable)
class ExerciceComptableAdmin(LectureSeuleAdmin):
    # La clôture passe par ``services.cloturer_exercice`` (DIRECTION, après la fin de l'année, sans brouillon,
    # avec l'écriture de clôture) ; un exercice clôturé ne se rouvre jamais.
    list_display = ("annee", "date_debut", "date_fin", "statut", "cloture_par")
    list_filter = ("statut",)
