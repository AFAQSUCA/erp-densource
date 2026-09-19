from django.contrib import admin

from .models import Personnel


@admin.register(Personnel)
class PersonnelAdmin(admin.ModelAdmin):
    list_display = ("matricule", "nom", "prenom", "poste", "departement")
    list_filter = ("departement",)
    search_fields = ("matricule", "nom", "prenom")

    def get_queryset(self, request):
        return Personnel.objects.all()
