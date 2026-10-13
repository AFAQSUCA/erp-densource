from django.contrib import admin

from apps.core.admin import SuppressionLogiqueAdmin

from .models import Client, Interaction


class InteractionInline(admin.TabularInline):
    model = Interaction
    extra = 0


@admin.register(Client)
class ClientAdmin(SuppressionLogiqueAdmin):
    list_display = ("raison_sociale", "ncc_nif", "contact_principal", "taux_tva")
    search_fields = ("raison_sociale", "ncc_nif")
    inlines = [InteractionInline]

