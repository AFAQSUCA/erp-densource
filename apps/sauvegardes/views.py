"""Écran « Sauvegardes » (ADMIN). Les règles sont dans ``sauvegardes.services`` ; la vue n'ajoute que l'affichage."""

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.views.generic import TemplateView

from apps.accounts.mixins import RoleRequiredMixin

from . import permissions, services


class SauvegardesView(RoleRequiredMixin, TemplateView):
    roles = permissions.CONSULTATION
    template_name = "sauvegardes/sauvegardes.html"

    def get_context_data(self, **kwargs):
        en_cours, demande = services.en_cours(), services.demande_en_attente()
        return super().get_context_data(
            essais=services.journal(),
            derniere=services.derniere_reussie(),
            alerte=services.alerte(),
            en_cours=en_cours,
            demande=demande,
            rafraichir=en_cours is not None or demande is not None,
            surveillees=settings.SAUVEGARDES_SURVEILLEES,
            peut_demander=services.peut_demander(self.request.user),
            **kwargs,
        )

    def post(self, request):
        try:
            services.demander_sauvegarde(request.user, request=request)
        except services.SauvegardeError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, "Sauvegarde demandée : elle démarre dans la minute. Cette page se met à jour.")
        return redirect("sauvegardes:liste")
