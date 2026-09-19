"""Écrans du garage : liste et fiche des OR, ouverture, clôture, statut des camions.

Aucune règle métier ici : les vues contrôlent le rôle, lisent le formulaire et
délèguent à ``services.py`` (conventions.md:19-23).
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.accounts.mixins import RoleRequiredMixin
from apps.core.views import PaginationTolerante
from apps.fleet import services as fleet_services

from . import permissions, sections, services
from .exceptions import GarageError
from .forms import ClotureForm, OrForm
from .models import LieuReparation, StatutOr, TypeOr


class OrListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "garage/or_list.html"
    context_object_name = "ordres"
    paginate_by = 20

    def get_queryset(self):
        return services.rechercher_ordres(
            statut=self.request.GET.get("statut"),
            type_or=self.request.GET.get("type"),
            lieu=self.request.GET.get("lieu"),
            recherche=self.request.GET.get("q", ""),
        )

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            statuts=StatutOr.choices,
            types=TypeOr.choices,
            lieux=LieuReparation.choices,
            statut_choisi=self.request.GET.get("statut", ""),
            type_choisi=self.request.GET.get("type", ""),
            lieu_choisi=self.request.GET.get("lieu", ""),
            recherche=self.request.GET.get("q", ""),
            peut_modifier=self.request.user.role_effectif in permissions.MODIFICATION,
        )
        return contexte


class OrDetailView(RoleRequiredMixin, DetailView):
    roles = permissions.CONSULTATION
    template_name = "garage/or_detail.html"
    context_object_name = "ordre"

    def get_queryset(self):
        return services.ordres_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        ordre = self.object
        peut_modifier = self.request.user.role_effectif in permissions.MODIFICATION
        contexte.update(
            sections=sections.DETAIL_OR.sections(ordre, self.request.user),
            peut_cloturer=peut_modifier and ordre.statut == StatutOr.OUVERT,
            form_cloture=ClotureForm()
            if peut_modifier and ordre.statut == StatutOr.OUVERT
            else None,
        )
        return contexte


class OrCreateView(RoleRequiredMixin, FormView):
    roles = permissions.MODIFICATION
    form_class = OrForm
    template_name = "garage/or_form.html"

    def get_initial(self):
        # Prérempli depuis la fiche d'un camion : /garage/nouveau/?vehicule=<pk>
        try:
            return {"vehicule": int(self.request.GET.get("vehicule", ""))}
        except ValueError:
            return {}

    def form_valid(self, form):
        try:
            ordre = services.ouvrir_or(**form.cleaned_data)
        except GarageError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(
            self.request,
            f"OR {ordre.numero} ouvert : le camion {ordre.vehicule.immatriculation} "
            "est « En maintenance ».",
        )
        return redirect("garage:detail", pk=ordre.pk)


class OrCloturerView(RoleRequiredMixin, View):
    """Clôture un OR (POST) : main-d'œuvre saisie, statut du camion recalculé."""

    roles = permissions.MODIFICATION
    http_method_names = ["post"]

    def post(self, request, pk):
        ordre = get_object_or_404(services.ordres_queryset(), pk=pk)
        form = ClotureForm(request.POST)
        if not form.is_valid():
            for erreurs in form.errors.values():
                for erreur in erreurs:
                    messages.error(request, erreur)
            return redirect("garage:detail", pk=ordre.pk)
        try:
            services.cloturer_or(ordre, cout_main_oeuvre=form.cleaned_data["cout_main_oeuvre"])
        except GarageError as erreur:
            messages.error(request, str(erreur))
        else:
            ordre.vehicule.refresh_from_db()
            messages.success(
                request,
                f"OR {ordre.numero} clôturé : le camion {ordre.vehicule.immatriculation} "
                f"est « {ordre.vehicule.get_statut_display()} ».",
            )
        return redirect("garage:detail", pk=ordre.pk)


class StatutVehiculeView(RoleRequiredMixin, View):
    """Immobilise, met hors service ou remet en service un camion (POST)."""

    roles = permissions.MODIFICATION
    http_method_names = ["post"]
    action = None  # nom de la fonction de services.py

    def post(self, request, pk):
        vehicule = get_object_or_404(fleet_services.vehicules_queryset(), pk=pk)
        try:
            getattr(services, self.action)(vehicule)
        except GarageError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(
                request,
                f"Camion {vehicule.immatriculation} : statut « {vehicule.get_statut_display()} ».",
            )
        return redirect("fleet:detail", pk=vehicule.pk)


class ImmobiliserView(StatutVehiculeView):
    action = "immobiliser_vehicule"


class HorsServiceView(StatutVehiculeView):
    action = "mettre_hors_service"


class RemiseEnServiceView(StatutVehiculeView):
    action = "remettre_en_service"
