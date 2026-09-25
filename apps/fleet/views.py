"""Écrans de la flotte : liste, fiche, création, modification, documents.

Aucune règle métier ici : les vues contrôlent le rôle, lisent le formulaire et
délèguent à ``services.py`` (conventions.md:19-23).
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.accounts.mixins import RoleRequiredMixin
from apps.core.views import ImpressionListeMixin, PaginationTolerante

from . import permissions, sections, services
from .exceptions import FlotteError
from .forms import DocumentForm, VehiculeForm
from .models import StatutVehicule, TypeDocument


class VehiculeListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "fleet/vehicule_list.html"
    context_object_name = "vehicules"
    paginate_by = 20

    def get_queryset(self):
        return services.rechercher_vehicules(
            statut=self.request.GET.get("statut"),
            recherche=self.request.GET.get("q", ""),
            documents_a_renouveler=self.request.GET.get("alerte") == "1",
        )

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            statuts=StatutVehicule.choices,
            statut_choisi=self.request.GET.get("statut", ""),
            recherche=self.request.GET.get("q", ""),
            alerte=self.request.GET.get("alerte") == "1",
            vehicules_en_alerte=services.vehicules_avec_documents_a_renouveler(),
            peut_modifier=self.request.user.role_effectif in permissions.MODIFICATION,
        )
        return contexte


class VehiculeImprimerView(ImpressionListeMixin, VehiculeListView):
    """Rapport imprimable des camions (mêmes recherche, statut et alerte que la liste)."""

    titre_impression = "Flotte"
    colonnes = (
        ("Immatriculation", "immatriculation"), ("Marque", "marque"), ("Modèle", "modele"),
        ("Année", "annee"), ("Statut", "get_statut_display"), ("Kilométrage", lambda v: f"{v.kilometrage:,} km".replace(",", " ")),
        ("Chauffeur habituel", lambda v: f"{v.chauffeur_habituel.prenom} {v.chauffeur_habituel.nom}" if v.chauffeur_habituel_id else "—"),
    )

    def get_sous_titre_impression(self):
        morceaux = []
        statut = self.request.GET.get("statut", "")
        if statut in StatutVehicule.values:
            morceaux.append(f"statut : {StatutVehicule(statut).label}")
        if self.request.GET.get("alerte") == "1":
            morceaux.append("documents à renouveler")
        if self.request.GET.get("q", ""):
            morceaux.append(f"recherche : « {self.request.GET['q']} »")
        return " · ".join(morceaux)


class VehiculeDetailView(RoleRequiredMixin, DetailView):
    roles = permissions.CONSULTATION
    template_name = "fleet/vehicule_detail.html"
    context_object_name = "vehicule"

    def get_queryset(self):
        return services.vehicules_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        peut_modifier = self.request.user.role_effectif in permissions.MODIFICATION
        type_choisi = self.request.GET.get("document")
        contexte.update(
            documents=services.etat_documents(self.object),
            sections=sections.DETAIL_VEHICULE.sections(self.object, self.request.user),
            peut_modifier=peut_modifier,
            form_document=(
                DocumentForm(
                    initial={
                        "type_document": type_choisi
                        if type_choisi in TypeDocument.values
                        else None
                    }
                )
                if peut_modifier
                else None
            ),
        )
        return contexte


class VehiculeCreateView(RoleRequiredMixin, FormView):
    roles = permissions.MODIFICATION
    form_class = VehiculeForm
    template_name = "fleet/vehicule_form.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(titre="Nouveau camion", bouton="Créer le camion")
        return contexte

    def form_valid(self, form):
        try:
            vehicule = services.creer_vehicule(**form.cleaned_data)
        except FlotteError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, f"Camion {vehicule.immatriculation} créé.")
        return redirect("fleet:detail", pk=vehicule.pk)


class VehiculeUpdateView(RoleRequiredMixin, FormView):
    roles = permissions.MODIFICATION
    form_class = VehiculeForm
    template_name = "fleet/vehicule_form.html"

    @property
    def vehicule(self):
        if not hasattr(self, "_vehicule"):
            self._vehicule = get_object_or_404(
                services.vehicules_queryset(), pk=self.kwargs["pk"]
            )
        return self._vehicule

    def get_initial(self):
        v = self.vehicule
        return {
            "immatriculation": v.immatriculation,
            "marque": v.marque,
            "modele": v.modele,
            "annee": v.annee,
            "vin": v.vin,
            "kilometrage": v.kilometrage,
            "capacite_charge_t": v.capacite_charge_t,
            "reservoir_l": v.reservoir_l,
            "chauffeur_habituel": v.chauffeur_habituel,
        }

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            titre=f"Modifier {self.vehicule.immatriculation}",
            bouton="Enregistrer",
            vehicule=self.vehicule,
        )
        return contexte

    def form_valid(self, form):
        try:
            services.modifier_vehicule(self.vehicule, **form.cleaned_data)
        except FlotteError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, f"Camion {self.vehicule.immatriculation} mis à jour.")
        return redirect("fleet:detail", pk=self.vehicule.pk)


class DocumentView(RoleRequiredMixin, View):
    """Enregistre ou renouvelle un document réglementaire (POST)."""

    roles = permissions.MODIFICATION
    http_method_names = ["post"]

    def post(self, request, pk):
        vehicule = get_object_or_404(services.vehicules_queryset(), pk=pk)
        form = DocumentForm(request.POST)
        if not form.is_valid():
            for erreurs in form.errors.values():
                for erreur in erreurs:
                    messages.error(request, erreur)
            return redirect("fleet:detail", pk=vehicule.pk)
        try:
            document, cree = services.enregistrer_document(vehicule, **form.cleaned_data)
        except FlotteError as erreur:
            messages.error(request, str(erreur))
        else:
            action = "enregistré" if cree else "renouvelé"
            messages.success(
                request, f"{document.get_type_document_display()} {action}."
            )
        return redirect("fleet:detail", pk=vehicule.pk)
