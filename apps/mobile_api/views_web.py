"""Espace mobile du chauffeur (PWA) : pages tactiles servies sous ``/chauffeur/``.

Comme le reste de l'interface, aucune règle métier ici : chaque vue identifie le chauffeur du
compte connecté et délègue à ``services.py`` (les mêmes que l'API mobile). Session de 15 minutes
d'inactivité pour ce rôle (cahier-des-charges.md:285). L'application est installable
(manifeste + service worker) ; la saisie hors ligne n'est pas gérée : une page « hors connexion »
s'affiche à la place quand le réseau manque.
"""

import json

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.mixins import RoleRequiredMixin
from apps.accounts.models import Role
from apps.core.formats import nombre, pourcentage_signe
from apps.drivers import services as drivers_services
from apps.fuel.exceptions import CarburantError, SaisieSuspecte
from apps.fuel.models import NiveauAlerte
from apps.garage.exceptions import GarageError
from apps.missions.exceptions import MissionError

from . import services
from .exceptions import MissionIntrouvable, MobileError
from .forms import (
    ChecklistForm,
    CodeForm,
    FraisImprevuChauffeurForm,
    IncidentChauffeurForm,
    LivraisonForm,
    PleinChauffeurForm,
)

ERREURS = (MissionError, CarburantError, GarageError, MobileError)


class ChauffeurRequisMixin(RoleRequiredMixin):
    """Réservé aux comptes CHAUFFEUR rattachés à une fiche chauffeur."""

    roles = frozenset({Role.CHAUFFEUR})

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["navigation"] = [
            ("accueil", reverse("chauffeur:accueil"), "fa-house", "Accueil"),
            ("missions", reverse("chauffeur:missions"), "fa-truck-fast", "Missions"),
            ("plein", reverse("chauffeur:plein"), "fa-gas-pump", "Plein"),
            ("incident", reverse("chauffeur:incident"), "fa-triangle-exclamation", "Panne"),
            ("imprevu", reverse("chauffeur:imprevu"), "fa-money-bill-transfer", "Imprévu"),
        ]
        return contexte

    def dispatch(self, request, *args, **kwargs):
        utilisateur = request.user
        if utilisateur.is_authenticated and utilisateur.role_effectif in self.roles:
            self.chauffeur = drivers_services.chauffeur_de(utilisateur)
            if self.chauffeur is None:
                raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


def _mission_ou_404(chauffeur, pk):
    try:
        return services.mission_du_chauffeur(chauffeur, pk)
    except MissionIntrouvable as erreur:
        raise Http404 from erreur


class AccueilView(ChauffeurRequisMixin, TemplateView):
    template_name = "mobile/accueil.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        tableau = services.tableau(self.chauffeur)
        mission = tableau["mission_du_jour"]
        contexte.update(
            tableau,
            actions=services.actions_possibles(mission) if mission else {},
            nav="accueil",
        )
        return contexte


class MissionsView(ChauffeurRequisMixin, TemplateView):
    template_name = "mobile/missions.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(missions=services.missions_du_chauffeur(self.chauffeur), nav="missions")
        return contexte


class MissionView(ChauffeurRequisMixin, TemplateView):
    template_name = "mobile/mission.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        mission = _mission_ou_404(self.chauffeur, self.kwargs["pk"])
        actions = services.actions_possibles(mission)
        contexte.update(
            mission=mission,
            actions=actions,
            checklist_faite=services.checklist_faite(mission),
            form_recuperation=CodeForm() if actions["recuperation"] else None,
            form_livraison=LivraisonForm() if actions["livraison"] else None,
            nav="missions",
        )
        return contexte


class _ActionMission(ChauffeurRequisMixin, View):
    """Action en POST sur une mission du chauffeur, puis retour à sa fiche."""

    http_method_names = ["post"]
    form_class = None

    def executer(self, pk, donnees):
        raise NotImplementedError  # pragma: no cover

    def message(self, mission):
        raise NotImplementedError  # pragma: no cover

    def post(self, request, pk):
        donnees = {}
        if self.form_class is not None:
            form = self.form_class(request.POST)
            if not form.is_valid():
                for erreurs in form.errors.values():
                    for erreur in erreurs:
                        messages.error(request, erreur)
                return redirect("chauffeur:mission", pk=pk)
            donnees = form.cleaned_data
        try:
            mission = self.executer(pk, donnees)
        except MissionIntrouvable as erreur:
            raise Http404 from erreur
        except ERREURS as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, self.message(mission))
        return redirect("chauffeur:mission", pk=pk)


class DemarrerView(_ActionMission):
    def executer(self, pk, donnees):
        return services.demarrer(self.chauffeur, pk)

    def message(self, mission):
        return "C'est parti ! Bonne route."


class RecuperationView(_ActionMission):
    form_class = CodeForm

    def executer(self, pk, donnees):
        return services.confirmer_recuperation(self.chauffeur, pk, code=donnees["code"])

    def message(self, mission):
        return "Colis récupéré. Vous pouvez prendre la route vers la livraison."


class LivraisonView(_ActionMission):
    form_class = LivraisonForm

    def executer(self, pk, donnees):
        return services.livrer(self.chauffeur, pk, code=donnees["code"], km_arrivee=donnees["km_arrivee"])

    def message(self, mission):
        return "Livraison confirmée. Merci !"


class ChecklistView(ChauffeurRequisMixin, TemplateView):
    template_name = "mobile/checklist.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            mission=_mission_ou_404(self.chauffeur, self.kwargs["pk"]),
            form=kwargs.get("form") or ChecklistForm(),
            nav="missions",
        )
        return contexte

    def post(self, request, pk):
        form = ChecklistForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        try:
            checklist = services.enregistrer_checklist(
                self.chauffeur, pk, resultats=form.resultats(), remarque=form.cleaned_data["remarque"]
            )
        except MissionIntrouvable as erreur:
            raise Http404 from erreur
        except ERREURS as erreur:
            form.add_error(None, str(erreur))
            return self.render_to_response(self.get_context_data(form=form))
        if checklist.nb_anomalies:
            messages.warning(
                request,
                f"Check-list enregistrée : {checklist.nb_anomalies} point(s) KO. "
                "Le Parc Auto est prévenu ; vous pouvez partir.",
            )
        else:
            messages.success(request, "Check-list enregistrée : tout est OK.")
        return redirect("chauffeur:mission", pk=pk)


class PleinView(ChauffeurRequisMixin, TemplateView):
    """Saisie d'un plein ; un écart de plus de 60 % demande une confirmation explicite."""

    template_name = "mobile/plein.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            form=kwargs.get("form") or PleinChauffeurForm(initial={"date_plein": timezone.localdate()}),
            saisie_suspecte=kwargs.get("saisie_suspecte"),
            vehicule=services.vehicule_courant(self.chauffeur),
            derniers=services.pleins_du_chauffeur(self.chauffeur, limite=5),
            nav="plein",
        )
        return contexte

    def post(self, request):
        form = PleinChauffeurForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        try:
            plein = services.saisir_plein(
                self.chauffeur,
                confirmer=request.POST.get("confirmer") == "1",
                **form.cleaned_data,
            )
        except SaisieSuspecte as avertissement:
            return self.render_to_response(self.get_context_data(form=form, saisie_suspecte=avertissement))
        except ERREURS as erreur:
            form.add_error(None, str(erreur))
            return self.render_to_response(self.get_context_data(form=form))
        if plein.consommation is None:
            messages.success(request, "Premier plein enregistré : la consommation sera calculée au suivant.")
        else:
            messages.success(request, f"Plein enregistré : {nombre(plein.consommation, 1)} L/100 km.")
        if plein.niveau_alerte != NiveauAlerte.AUCUNE:
            messages.warning(
                request,
                f"Surconsommation : {pourcentage_signe(plein.ecart_pct)} % par rapport à votre moyenne récente.",
            )
        return redirect("chauffeur:accueil")


class IncidentView(ChauffeurRequisMixin, TemplateView):
    template_name = "mobile/incident.html"

    def _missions(self):
        return list(services.missions_du_chauffeur(self.chauffeur))

    def _formulaire_vide(self):
        mission = self.request.GET.get("mission", "")
        return IncidentChauffeurForm(
            missions=self._missions(), initial={"mission": mission} if mission.isdigit() else {}
        )

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            form=kwargs.get("form") or self._formulaire_vide(),
            derniers=services.incidents_du_chauffeur(self.chauffeur, limite=5),
            nav="incident",
        )
        return contexte

    def post(self, request):
        form = IncidentChauffeurForm(request.POST, missions=self._missions())
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        donnees = form.cleaned_data
        try:
            services.declarer_incident(
                self.chauffeur,
                type_incident=donnees["type_incident"],
                gravite=donnees["gravite"],
                description=donnees["description"],
                lieu=donnees["lieu"],
                mission_id=donnees["mission"],
            )
        except MissionIntrouvable as erreur:
            raise Http404 from erreur
        except ERREURS as erreur:
            form.add_error(None, str(erreur))
            return self.render_to_response(self.get_context_data(form=form))
        messages.success(request, "Incident signalé : le Parc Auto et la Direction sont prévenus.")
        return redirect("chauffeur:accueil")


class FraisImprevuView(ChauffeurRequisMixin, TemplateView):
    """Déclaration d'un imprévu (panne, incident) avec une preuve — R4."""

    template_name = "mobile/imprevu.html"

    def _missions(self):
        return list(services.missions_du_chauffeur(self.chauffeur))

    def _formulaire_vide(self):
        mission = self.request.GET.get("mission", "")
        return FraisImprevuChauffeurForm(
            missions=self._missions(), initial={"mission": mission} if mission.isdigit() else {}
        )

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            form=kwargs.get("form") or self._formulaire_vide(),
            derniers=services.frais_du_chauffeur(self.chauffeur, limite=5),
            nav="imprevu",
        )
        return contexte

    def post(self, request):
        form = FraisImprevuChauffeurForm(request.POST, request.FILES, missions=self._missions())
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        donnees = form.cleaned_data
        try:
            services.declarer_frais_imprevu(
                self.chauffeur,
                mission_id=donnees["mission"],
                montant=donnees["montant"],
                justificatif=donnees["justificatif"],
                description=donnees["description"],
            )
        except MissionIntrouvable as erreur:
            raise Http404 from erreur
        except ERREURS as erreur:
            form.add_error(None, str(erreur))
            return self.render_to_response(self.get_context_data(form=form))
        messages.success(request, "Imprévu signalé : le Parc Auto est prévenu.")
        return redirect("chauffeur:accueil")


# --- application installable (PWA) ---


class ManifesteView(View):
    """Manifeste de l'application : nom, couleurs, icônes, page de démarrage."""

    def get(self, request):
        manifeste = {
            "name": "DEN Source Group : espace chauffeur",
            "short_name": "DEN Chauffeur",
            "description": "Missions, plein de carburant, check-list et signalement d'incident.",
            "lang": "fr",
            "start_url": reverse("chauffeur:accueil"),
            "scope": reverse("chauffeur:accueil"),
            "display": "standalone",
            "orientation": "portrait",
            "background_color": "#ffffff",
            "theme_color": "#8b0319",
            "icons": [
                {"src": static("img/icon-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "any"},
                {"src": static("img/icon-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any"},
            ],
        }
        return HttpResponse(json.dumps(manifeste), content_type="application/manifest+json")


class ServiceWorkerView(View):
    """Service worker : ne met en cache que la page « hors connexion » et les icônes.

    Les pages du chauffeur (missions, codes...) ne sont jamais mises en cache : elles contiennent
    des données privées et doivent toujours être à jour.
    """

    def get(self, request):
        reponse = render(
            request, "mobile/sw.js",
            {"hors_ligne": reverse("chauffeur:hors_ligne"), "icone": static("img/icon-192.png")},
            content_type="application/javascript",
        )
        reponse["Service-Worker-Allowed"] = reverse("chauffeur:accueil")
        reponse["Cache-Control"] = "no-cache"
        return reponse


class HorsLigneView(TemplateView):
    template_name = "mobile/hors_ligne.html"
