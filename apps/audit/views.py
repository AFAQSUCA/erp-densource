"""Écran du journal d'audit : liste filtrable, export CSV, rapport imprimable — ADMIN et DIRECTION
(cahier-des-charges.md:56-82). Aucune écriture ici : le journal ne se remplit que via
``services.log_action`` (signaux, ``registry.audit_model``), jamais depuis cet écran.
"""

import csv

from django.http import HttpResponse
from django.views.generic import ListView

from apps.accounts.mixins import RoleRequiredMixin
from apps.core.views import ImpressionListeMixin, PaginationTolerante

from . import permissions, services
from .forms import FiltreJournalForm


class JournalListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "audit/journal_list.html"
    context_object_name = "lignes"
    paginate_by = 30

    def get_filtre(self):
        if not hasattr(self, "_filtre"):
            self._filtre = FiltreJournalForm(self.request.GET, modules=services.modules_utilises())
        return self._filtre

    def get_queryset(self):
        return services.rechercher(**self.get_filtre().criteres())

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            filtre=self.get_filtre(),
            filtres_actifs=any(self.get_filtre().criteres().values()),
        )
        return contexte


COLONNES_EXPORT = (
    ("Date/heure", lambda e: e.date_heure.strftime("%d/%m/%Y %H:%M:%S")),
    ("Utilisateur", lambda e: e.utilisateur_nom or "—"),
    ("Rôle", lambda e: e.role or "—"),
    ("Action", "get_action_display"), ("Module", "module"), ("Entité", "entite"),
    ("ID entité", lambda e: e.entite_id if e.entite_id is not None else "—"),
    ("Statut", "get_statut_display"), ("Adresse IP", lambda e: e.adresse_ip or "—"),
)


class JournalImprimerView(ImpressionListeMixin, JournalListView):
    """Rapport imprimable du journal (mêmes filtres que la liste)."""

    titre_impression = "Journal d'audit"
    colonnes = COLONNES_EXPORT

    def get_sous_titre_impression(self):
        criteres = self.get_filtre().criteres()
        morceaux = []
        if criteres.get("module"):
            morceaux.append(f"module : {criteres['module']}")
        if criteres.get("action"):
            morceaux.append(f"action : {dict(services.ActionChoices.choices)[criteres['action']]}")
        if criteres.get("statut"):
            morceaux.append(f"statut : {dict(services.StatutChoices.choices)[criteres['statut']]}")
        if criteres.get("date_debut"):
            morceaux.append(f"du {criteres['date_debut'].strftime('%d/%m/%Y')}")
        if criteres.get("date_fin"):
            morceaux.append(f"au {criteres['date_fin'].strftime('%d/%m/%Y')}")
        if criteres.get("recherche"):
            morceaux.append(f"recherche : « {criteres['recherche']} »")
        return " · ".join(morceaux)


class JournalExporterCsvView(RoleRequiredMixin, ListView):
    """Export CSV du journal filtré (cahier-des-charges.md:82 « Export CSV/PDF pour audits externes »).

    Le PDF s'obtient par :class:`JournalImprimerView` (Ctrl+P / Enregistrer au format PDF).
    """

    roles = permissions.CONSULTATION

    def get_filtre(self):
        return FiltreJournalForm(self.request.GET, modules=services.modules_utilises())

    def get_queryset(self):
        return services.rechercher(**self.get_filtre().criteres())

    def get(self, request, *args, **kwargs):
        reponse = HttpResponse(content_type="text/csv; charset=utf-8")
        reponse["Content-Disposition"] = 'attachment; filename="journal_audit.csv"'
        reponse.write("﻿")  # BOM : Excel ouvre l'UTF-8 sans le déformer
        redacteur = csv.writer(reponse, delimiter=";")
        redacteur.writerow([libelle for libelle, _ in COLONNES_EXPORT])
        for entree in self.get_queryset():
            redacteur.writerow([ImpressionListeMixin._valeur(entree, cle) for _, cle in COLONNES_EXPORT])
        return reponse
