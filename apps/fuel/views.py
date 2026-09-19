"""Écrans du carburant : liste des pleins, saisie, analyse.

Aucune règle métier ici : les vues contrôlent le rôle, lisent le formulaire et
délèguent à ``services.py`` (conventions.md:19-23).
"""

from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone
from django.views.generic import FormView, ListView, TemplateView

from apps.accounts.mixins import RoleRequiredMixin
from apps.core.formats import nombre, pourcentage_signe
from apps.core.views import PaginationTolerante

from . import permissions, services
from .exceptions import CarburantError, SaisieSuspecte
from .forms import FiltrePleinsForm, PleinForm
from .models import NiveauAlerte


class PleinListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "fuel/plein_list.html"
    context_object_name = "pleins"
    paginate_by = 20

    def get_filtre(self):
        if not hasattr(self, "_filtre"):
            self._filtre = FiltrePleinsForm(self.request.GET)
        return self._filtre

    def get_queryset(self):
        return services.rechercher_pleins(**self.get_filtre().criteres())

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        criteres = self.get_filtre().criteres()
        contexte.update(
            filtre=self.get_filtre(),
            filtres_actifs=any(criteres.values()),
            consommation_moyenne=services.consommation_moyenne(
                vehicule=criteres["vehicule"], chauffeur=criteres["chauffeur"]
            ),
            nombre_a_surveiller=services.pleins_a_surveiller().count(),
            peut_modifier=self.request.user.role_effectif in permissions.MODIFICATION,
        )
        return contexte


class PleinCreateView(RoleRequiredMixin, FormView):
    """Saisie d'un plein.

    Si l'écart dépasse ±60 %, rien n'est enregistré : la page se réaffiche avec
    l'avertissement et un bouton « Confirmer » qui renvoie les mêmes valeurs
    (cahier-des-charges.md:155).
    """

    roles = permissions.MODIFICATION
    form_class = PleinForm
    template_name = "fuel/plein_form.html"

    def get_initial(self):
        return {"date_plein": timezone.localdate()}

    def form_valid(self, form):
        confirmer = self.request.POST.get("confirmer") == "1"
        try:
            plein = services.enregistrer_plein(
                **form.cleaned_data, confirmer_alerte_saisie=confirmer
            )
        except SaisieSuspecte as avertissement:
            return self.render_to_response(
                self.get_context_data(form=form, saisie_suspecte=avertissement)
            )
        except CarburantError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)

        if plein.consommation is None:
            messages.success(
                self.request,
                "Premier plein de ce camion enregistré : la consommation sera calculée dès le suivant.",
            )
        else:
            messages.success(
                self.request,
                f"Plein enregistré : {nombre(plein.consommation, 1)} L/100 km.",
            )
        self._signaler_les_alertes(plein)
        return redirect("fuel:liste")

    def _signaler_les_alertes(self, plein) -> None:
        if plein.niveau_alerte != NiveauAlerte.AUCUNE:
            messages.warning(
                self.request,
                f"Surconsommation {plein.get_niveau_alerte_display()} : "
                f"{pourcentage_signe(plein.ecart_pct)} % par rapport à la moyenne des derniers "
                f"pleins ({nombre(plein.moyenne_reference, 1)} L/100 km).",
            )
        if plein.anomalie:
            messages.warning(
                self.request,
                f"Anomalie : {nombre(plein.consommation, 1)} L/100 km est hors de la plage 20-45.",
            )


class AnalyseView(RoleRequiredMixin, TemplateView):
    roles = permissions.CONSULTATION
    template_name = "fuel/analyse.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            consommation_flotte=services.consommation_moyenne(),
            par_vehicule=services.consommation_par_vehicule(),
            par_chauffeur=services.consommation_par_chauffeur(),
        )
        return contexte
