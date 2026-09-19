"""Écrans des chauffeurs : liste, fiche, modification, changement de statut.

Aucune règle métier ici : les vues contrôlent le rôle, lisent le formulaire et
délèguent à ``services.py`` (conventions.md:19-23).
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.accounts.mixins import RoleRequiredMixin

from . import permissions, services
from .exceptions import ChauffeurError
from .forms import ChauffeurForm, StatutForm
from .models import StatutChauffeur


class ChauffeurListView(RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "drivers/chauffeur_list.html"
    context_object_name = "chauffeurs"
    paginate_by = 20

    def get_queryset(self):
        return services.rechercher_chauffeurs(
            statut=self.request.GET.get("statut"),
            recherche=self.request.GET.get("q", ""),
            a_renouveler=self.request.GET.get("alerte") == "1",
        )

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            statuts=StatutChauffeur.choices,
            statut_choisi=self.request.GET.get("statut", ""),
            recherche=self.request.GET.get("q", ""),
            alerte=self.request.GET.get("alerte") == "1",
            lignes=[
                {"chauffeur": c, "echeances": services.etat_echeances(c)}
                for c in contexte["page_obj"]
            ],
        )
        return contexte


class ChauffeurDetailView(RoleRequiredMixin, DetailView):
    roles = permissions.CONSULTATION
    template_name = "drivers/chauffeur_detail.html"
    context_object_name = "chauffeur"

    def get_queryset(self):
        return services.chauffeurs_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        chauffeur = self.object
        peut_modifier = self.request.user.role_effectif in permissions.MODIFICATION
        contexte.update(
            echeances=services.etat_echeances(chauffeur),
            peut_modifier=peut_modifier,
            statut_verrouille=chauffeur.statut in services.STATUTS_VERROUILLES,
            form_statut=StatutForm(initial={"statut": chauffeur.statut})
            if peut_modifier
            else None,
        )
        return contexte


class ChauffeurUpdateView(RoleRequiredMixin, FormView):
    roles = permissions.MODIFICATION
    form_class = ChauffeurForm
    template_name = "drivers/chauffeur_form.html"

    @property
    def chauffeur(self):
        if not hasattr(self, "_chauffeur"):
            self._chauffeur = get_object_or_404(
                services.chauffeurs_queryset(), pk=self.kwargs["pk"]
            )
        return self._chauffeur

    def get_initial(self):
        c = self.chauffeur
        return {
            "telephone": c.telephone,
            "contact_urgence": c.contact_urgence,
            "numero_permis": c.numero_permis,
            "categories_permis": c.categories_permis,
            "date_expiration_permis": c.date_expiration_permis,
            "date_expiration_visite_medicale": c.date_expiration_visite_medicale,
        }

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["chauffeur"] = self.chauffeur
        return contexte

    def form_valid(self, form):
        try:
            services.modifier_chauffeur(self.chauffeur, **form.cleaned_data)
        except ChauffeurError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, f"Fiche de {self.chauffeur} mise à jour.")
        return redirect("drivers:detail", pk=self.chauffeur.pk)


class StatutView(RoleRequiredMixin, View):
    """Suspend, désactive ou réactive un chauffeur (POST)."""

    roles = permissions.MODIFICATION
    http_method_names = ["post"]

    def post(self, request, pk):
        chauffeur = get_object_or_404(services.chauffeurs_queryset(), pk=pk)
        form = StatutForm(request.POST)
        if not form.is_valid():
            for erreurs in form.errors.values():
                for erreur in erreurs:
                    messages.error(request, erreur)
            return redirect("drivers:detail", pk=chauffeur.pk)
        try:
            services.changer_statut_manuel(chauffeur, form.cleaned_data["statut"])
        except ChauffeurError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(
                request, f"{chauffeur} est maintenant « {chauffeur.get_statut_display()} »."
            )
        return redirect("drivers:detail", pk=chauffeur.pk)
