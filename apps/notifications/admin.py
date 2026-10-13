from django.contrib import admin

from apps.core.admin import SuppressionLogiqueAdmin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(SuppressionLogiqueAdmin):
    list_display = ("titre", "destinataire", "categorie", "niveau", "lue_le", "created_at")
    list_filter = ("categorie", "niveau")
    search_fields = ("titre", "destinataire__username")

    def get_queryset(self, request):
        return Notification.all_objects.all()
