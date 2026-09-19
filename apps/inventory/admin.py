from django.contrib import admin

from .models import Article, MouvementStock


class MouvementLectureSeule(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    """Fiche modifiable, sauf quantité et PUMP : ils ne bougent que par les
    mouvements de apps/inventory/services.py."""

    list_display = ("reference", "designation", "categorie", "quantite", "seuil_minimal", "pump")
    list_filter = ("categorie",)
    search_fields = ("reference", "designation")
    readonly_fields = ("quantite", "pump")

    def get_queryset(self, request):
        return Article.objects.all()


@admin.register(MouvementStock)
class MouvementStockAdmin(MouvementLectureSeule):
    list_display = (
        "date_mouvement",
        "article",
        "type_mouvement",
        "variation",
        "quantite_apres",
        "ordre_reparation",
    )
    list_filter = ("type_mouvement",)
    search_fields = ("article__reference", "ordre_reparation__numero")

    def get_queryset(self, request):
        return MouvementStock.objects.select_related("article", "ordre_reparation")
