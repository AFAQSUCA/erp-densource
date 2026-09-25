"""Écrans du Parc Auto pour les signalements du chauffeur : incidents et check-lists.

Aucune règle métier ici : les vues contrôlent le rôle, lisent le formulaire et délèguent à
``terrain.py`` (conventions.md:19-23). Ils sont alimentés par l'espace mobile du chauffeur.
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, ListView

from apps.accounts.mixins import RoleRequiredMixin
from apps.core.views import ImpressionListeMixin, PaginationTolerante

from . import permissions, terrain
from .exceptions import GarageError
from .forms_terrain import (
    ACTION_PRENDRE,
    FiltreChecklistsForm,
    FiltreIncidentsForm,
    TraitementIncidentForm,
)
from .models import GraviteIncident, Incident, StatutIncident


class IncidentListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "garage/incident_list.html"
    context_object_name = "incidents"
    paginate_by = 20

    def get_filtre(self):
        if not hasattr(self, "_filtre"):
            self._filtre = FiltreIncidentsForm(self.request.GET)
        return self._filtre

    def get_queryset(self):
        return terrain.rechercher_incidents(**self.get_filtre().criteres())

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            filtre=self.get_filtre(),
            filtres_actifs=any(self.get_filtre().criteres().values()),
            a_traiter=terrain.incidents_a_traiter().count(),
        )
        return contexte


class IncidentImprimerView(ImpressionListeMixin, IncidentListView):
    """Rapport imprimable des incidents signalés (mêmes filtres que la liste)."""

    titre_impression = "Incidents signalés par les chauffeurs"
    colonnes = (
        ("Camion", "vehicule.immatriculation"),
        ("Chauffeur", lambda i: f"{i.chauffeur.personnel.prenom} {i.chauffeur.personnel.nom}" if i.chauffeur_id else "—"),
        ("Type", "get_type_incident_display"), ("Gravité", "get_gravite_display"), ("Lieu", "lieu"),
        ("Description", "description"),
        ("Signalé le", lambda i: i.created_at.strftime("%d/%m/%Y %H:%M")),
        ("Statut", "get_statut_display"),
    )

    def get_sous_titre_impression(self):
        criteres = self.get_filtre().criteres()
        morceaux = []
        if criteres.get("statut") in StatutIncident.values:
            morceaux.append(f"statut : {StatutIncident(criteres['statut']).label}")
        if criteres.get("gravite") in GraviteIncident.values:
            morceaux.append(f"gravité : {GraviteIncident(criteres['gravite']).label}")
        if criteres.get("recherche"):
            morceaux.append(f"recherche : « {criteres['recherche']} »")
        return " · ".join(morceaux)


class IncidentDetailView(RoleRequiredMixin, DetailView):
    roles = permissions.CONSULTATION
    template_name = "garage/incident_detail.html"
    context_object_name = "incident"

    def get_queryset(self):
        return terrain.incidents_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        incident = self.object
        peut_traiter = (
            self.request.user.role_effectif in permissions.MODIFICATION
            and incident.statut != StatutIncident.CLOS
        )
        contexte.update(
            peut_traiter=peut_traiter,
            peut_prendre_en_compte=peut_traiter and incident.statut == StatutIncident.SIGNALE,
            form_traitement=TraitementIncidentForm() if peut_traiter else None,
        )
        return contexte


class IncidentTraiterView(RoleRequiredMixin, View):
    """Prend un incident en compte ou le clôt (POST)."""

    roles = permissions.MODIFICATION
    http_method_names = ["post"]

    def post(self, request, pk):
        incident = get_object_or_404(Incident, pk=pk)
        form = TraitementIncidentForm(request.POST)
        if not form.is_valid():
            for erreurs in form.errors.values():
                for erreur in erreurs:
                    messages.error(request, erreur)
            return redirect("garage:incident", pk=incident.pk)
        note = form.cleaned_data["note"]
        try:
            if form.cleaned_data["action"] == ACTION_PRENDRE:
                terrain.prendre_en_compte(incident, request.user, note=note)
                messages.success(request, "Incident pris en compte.")
            else:
                terrain.clore_incident(incident, request.user, note=note)
                messages.success(request, "Incident clos.")
        except GarageError as erreur:
            messages.error(request, str(erreur))
        return redirect("garage:incident", pk=incident.pk)


class ChecklistListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "garage/checklist_list.html"
    context_object_name = "checklists"
    paginate_by = 20

    def get_filtre(self):
        if not hasattr(self, "_filtre"):
            self._filtre = FiltreChecklistsForm(self.request.GET)
        return self._filtre

    def get_queryset(self):
        return terrain.rechercher_checklists(**self.get_filtre().criteres())

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            filtre=self.get_filtre(),
            filtres_actifs=any(self.get_filtre().criteres().values()),
        )
        return contexte
