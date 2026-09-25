"""Tableau de bord : page d'accueil après connexion, adaptée au rôle."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views.generic import TemplateView

from apps.accounts.models import Role
from apps.core.rapports import contexte_rapport
from apps.drivers import services as drivers_services

from . import services


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/index.html"

    def get(self, request, *args, **kwargs):
        # Un chauffeur n'a pas de tableau de bord de bureau : son espace mobile est sa page d'accueil.
        utilisateur = request.user
        if (
            utilisateur.is_authenticated
            and utilisateur.role_effectif == Role.CHAUFFEUR
            and drivers_services.chauffeur_de(utilisateur) is not None
        ):
            return redirect("chauffeur:accueil")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        mois = services.periode_valide(self.request.GET.get("periode"))
        contexte.update(services.tableau_de_bord(self.request.user, mois=mois))
        return contexte


class DashboardImprimerView(LoginRequiredMixin, TemplateView):
    """Rapport imprimable du tableau de bord de l'utilisateur connecté (mêmes blocs, mêmes droits)."""

    template_name = "dashboard/index_print.html"

    def get_context_data(self, **kwargs):
        mois = services.periode_valide(self.request.GET.get("periode"))
        tableau = services.tableau_de_bord(self.request.user, mois=mois)
        contexte = contexte_rapport(
            self.request, titre="Tableau de bord",
            sous_titre=self.request.user.get_role_display() or "Administrateur",
        )
        contexte.update(tableau)
        return contexte
