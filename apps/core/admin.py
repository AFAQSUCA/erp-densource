"""Règles communes à l'admin Django pour les modèles à suppression logique (``BaseModel``) — audit AUD-04, TECH-57.

L'action « Supprimer la sélection » de l'admin appelle ``QuerySet.delete()`` : un ``DELETE`` physique, qui
contourne la suppression logique de ``BaseModel`` (et, pour les données d'exploitation, les règles métier des
services : contre-passation d'une dépense, statut d'une mission...). Deux comportements, au choix de chaque admin :

- :class:`SansSuppressionAdmin` : données d'exploitation (plein, mission, OR, article, congé) ; rien ne se supprime
  depuis l'admin, une correction passe par l'application.
- :class:`SuppressionLogiqueAdmin` : fiches de référence (client, camion, employé...) ; la suppression marque la
  fiche « supprimée » (réversible), l'admin montre aussi les fiches supprimées et permet de les restaurer — c'est la
  « restauration (administration) » demandée par l'import quand une ligne correspond à une fiche supprimée
  (audit AV-15).
"""

from django.contrib import admin, messages
from django.db import IntegrityError, transaction


class SansSuppressionAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None):
        return False


class SuppressionLogiqueAdmin(admin.ModelAdmin):
    actions = ["restaurer"]

    def get_queryset(self, request):
        """Fiches supprimées comprises (filtre « supprimé ») : sans cela, aucune ne pouvait être restaurée."""
        return self.model.all_objects.all()

    def get_list_display(self, request):
        return (*super().get_list_display(request), "is_deleted")

    def get_list_filter(self, request):
        return (*super().get_list_filter(request), "is_deleted")

    def delete_model(self, request, obj):
        obj.delete(deleted_by=request.user)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            obj.delete(deleted_by=request.user)

    @admin.action(description="Restaurer les fiches supprimées sélectionnées")
    def restaurer(self, request, queryset):
        restaurees, refusees = 0, []
        for obj in queryset.filter(is_deleted=True):
            try:
                with transaction.atomic():
                    obj.restore()
            except IntegrityError:  # une fiche active porte déjà le même identifiant (n°, date...)
                refusees.append(str(obj))
            else:
                restaurees += 1
        self.message_user(request, f"{restaurees} fiche(s) restaurée(s).", messages.SUCCESS)
        if refusees:
            self.message_user(
                request,
                "Non restaurée(s), une fiche active porte déjà le même identifiant : " + ", ".join(refusees) + ".",
                messages.ERROR,
            )
