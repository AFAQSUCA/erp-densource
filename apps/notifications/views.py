"""Page « Notifications » : liste, lecture, tout marquer comme lu.

Chaque utilisateur ne voit et ne modifie que ses propres notifications (tous rôles).
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import ListView

from apps.core.views import PaginationTolerante

from . import services


class NotificationListView(LoginRequiredMixin, PaginationTolerante, ListView):
    template_name = "notifications/liste.html"
    context_object_name = "notifications"
    paginate_by = 20

    def get_queryset(self):
        return services.notifications_de(
            self.request.user, non_lues=self.request.GET.get("non_lues") == "1"
        )

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["non_lues_seulement"] = self.request.GET.get("non_lues") == "1"
        return contexte


class LireView(LoginRequiredMixin, View):
    """Marque une notification comme lue (POST) puis ouvre son lien."""

    http_method_names = ["post"]

    def post(self, request, pk):
        notification = services.notifications_de(request.user).filter(pk=pk).first()
        if notification is None:
            raise Http404
        services.marquer_lue(notification)
        cible = notification.url
        if cible and url_has_allowed_host_and_scheme(cible, allowed_hosts=None):
            return redirect(cible)
        return redirect("notifications:liste")


class ToutLireView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request):
        services.marquer_toutes_lues(request.user)
        return redirect("notifications:liste")
