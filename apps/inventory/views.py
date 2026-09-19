"""Écrans du stock. Pour l'instant : la sortie de pièces depuis la fiche d'un OR.

Les écrans de gestion du stock (articles, entrées, ajustements) viendront ensuite.
Aucune règle métier ici : les vues contrôlent le rôle, lisent le formulaire et
délèguent à ``services.py`` (conventions.md:19-23).
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View

from apps.accounts.mixins import RoleRequiredMixin
from apps.garage import services as garage_services

from . import permissions, services
from .exceptions import StockError
from .forms import SortieForm


class SortieOrView(RoleRequiredMixin, View):
    """Sort des pièces du stock pour un OR ouvert (POST)."""

    roles = permissions.MODIFICATION
    http_method_names = ["post"]

    def post(self, request, pk):
        ordre = get_object_or_404(garage_services.ordres_queryset(), pk=pk)
        form = SortieForm(request.POST)
        if not form.is_valid():
            for erreurs in form.errors.values():
                for erreur in erreurs:
                    messages.error(request, erreur)
            return redirect("garage:detail", pk=ordre.pk)
        article, quantite = form.cleaned_data["article"], form.cleaned_data["quantite"]
        try:
            services.sortir_pour_or(article, quantite=quantite, ordre=ordre, acteur=request.user)
        except StockError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(
                request, f"{quantite} x {article.reference} sortie(s) pour l'OR {ordre.numero}."
            )
        return redirect("garage:detail", pk=ordre.pk)
