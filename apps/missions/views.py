"""Écrans des missions.

Les vues ne portent aucune règle métier : elles contrôlent le rôle, lisent le
formulaire et délèguent à ``services.py`` (conventions.md:19-23). Une erreur
métier (``MissionError``) devient un message affiché à l'utilisateur.
"""

import io

import qrcode
from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.accounts.mixins import RoleRequiredMixin
from apps.core.formats import nombre
from apps.core.views import ImpressionListeMixin, PaginationTolerante

from . import documents, permissions, services
from .exceptions import MissionError
from .forms import AffectationForm, CodeForm, LivraisonForm, MissionForm, ModificationForm
from .models import STATUTS_MODIFIABLES, StatutMission

ETAPES = [
    (StatutMission.BROUILLON, "Brouillon"),
    (StatutMission.PLANIFIEE, "Planifiée"),
    (StatutMission.AFFECTEE, "Affectée"),
    (StatutMission.EN_COURS_DEPART, "Départ"),
    (StatutMission.EN_COURS_COLIS_RECUPERE, "Colis récupéré"),
    (StatutMission.LIVREE, "Livrée"),
    (StatutMission.CLOTUREE, "Clôturée"),
]


def _etapes(statut: str) -> list[dict]:
    """Frise du cycle de vie : chaque étape est faite, en cours ou à venir."""
    rang_courant = [code for code, _ in ETAPES].index(statut)
    return [
        {
            "libelle": libelle,
            "etat": "faite" if rang < rang_courant else "courante" if rang == rang_courant else "a_venir",
        }
        for rang, (_, libelle) in enumerate(ETAPES)
    ]


class MissionListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "missions/mission_list.html"
    context_object_name = "missions"
    paginate_by = 20

    def get_queryset(self):
        return services.rechercher_missions(
            statut=self.request.GET.get("statut"),
            recherche=self.request.GET.get("q", ""),
        )

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            statuts=StatutMission.choices,
            statut_choisi=self.request.GET.get("statut", ""),
            recherche=self.request.GET.get("q", ""),
            peut_creer=self.request.user.role_effectif in permissions.CREATION,
        )
        return contexte


class MissionImprimerView(ImpressionListeMixin, MissionListView):
    """Rapport imprimable des missions (mêmes recherche et filtre statut que la liste)."""

    titre_impression = "Missions"
    colonnes = (
        ("N°", "numero"), ("Client", "client.raison_sociale"),
        ("Chargement", "lieu_chargement"), ("Livraison", "lieu_livraison"),
        ("Départ prévu", lambda m: m.date_depart_prevue.strftime("%d/%m/%Y") if m.date_depart_prevue else "—"),
        ("Camion", lambda m: m.vehicule.immatriculation if m.vehicule_id else "—"),
        ("Chauffeur", lambda m: f"{m.chauffeur.personnel.prenom} {m.chauffeur.personnel.nom}" if m.chauffeur_id else "—"),
        ("Statut", "get_statut_display"), ("Prix convenu", lambda m: f"{nombre(m.prix_convenu)} FCFA"),
    )

    def get_sous_titre_impression(self):
        statut = self.request.GET.get("statut", "")
        morceaux = []
        if statut in StatutMission.values:
            morceaux.append(f"statut : {StatutMission(statut).label}")
        if self.request.GET.get("q", ""):
            morceaux.append(f"recherche : « {self.request.GET['q']} »")
        return " · ".join(morceaux)


class MissionDetailView(RoleRequiredMixin, DetailView):
    roles = permissions.CONSULTATION
    template_name = "missions/mission_detail.html"
    context_object_name = "mission"

    def get_queryset(self):
        return services.missions_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        mission, utilisateur = self.object, self.request.user
        actions = permissions.actions_disponibles(utilisateur, mission)
        contexte.update(
            etapes=_etapes(mission.statut),
            actions=actions,
            codes=permissions.codes_visibles(utilisateur, mission),
            form_affectation=AffectationForm() if actions["affecter"] else None,
            form_recuperation=CodeForm() if actions["recuperation"] else None,
            form_livraison=LivraisonForm() if actions["livraison"] else None,
            peut_modifier=(
                utilisateur.role_effectif in permissions.MODIFICATION
                and mission.statut in STATUTS_MODIFIABLES
            ),
        )
        return contexte


class MissionCreateView(RoleRequiredMixin, FormView):
    roles = permissions.CREATION
    form_class = MissionForm
    template_name = "missions/mission_form.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(lieux=services.lieux_deja_utilises(), **kwargs)

    def form_valid(self, form):
        try:
            mission = services.creer_mission(**form.cleaned_data)
        except MissionError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(
            self.request,
            f"Mission {mission.numero} créée en brouillon. Le PDF des codes à transmettre à "
            "l'expéditeur et au destinataire se télécharge ci-dessous.",
        )
        return redirect("missions:detail", pk=mission.pk)


class MissionUpdateView(RoleRequiredMixin, FormView):
    """Modification d'une mission (avenant-separation-des-taches.md § R3) : DIRECTION et ADMIN
    seulement, tant que le colis n'est pas encore récupéré (``STATUTS_MODIFIABLES``)."""

    roles = permissions.MODIFICATION
    form_class = ModificationForm
    template_name = "missions/mission_modifier.html"

    def dispatch(self, request, *args, **kwargs):
        self.mission = get_object_or_404(services.missions_queryset(), pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        if self.mission.statut not in STATUTS_MODIFIABLES:
            messages.info(
                request,
                f"La mission {self.mission.numero} n'est plus modifiable "
                f"({self.mission.get_statut_display()}).",
            )
            return redirect("missions:detail", pk=self.mission.pk)
        return super().get(request, *args, **kwargs)

    @property
    def reaffectation(self) -> bool:
        return self.mission.statut == StatutMission.AFFECTEE

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["reaffectation"] = self.reaffectation
        return kwargs

    def get_initial(self):
        initial = {
            "lieu_chargement": self.mission.lieu_chargement,
            "lieu_livraison": self.mission.lieu_livraison,
            "nature_marchandise": self.mission.nature_marchandise,
            "poids_t": self.mission.poids_t,
            "prix_convenu": self.mission.prix_convenu,
            "date_depart_prevue": self.mission.date_depart_prevue,
        }
        if self.reaffectation:
            initial.update(vehicule=self.mission.vehicule_id, chauffeur=self.mission.chauffeur_id)
        return initial

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            mission=self.mission, lieux=services.lieux_deja_utilises(), **kwargs
        )

    def form_valid(self, form):
        donnees = dict(form.cleaned_data)
        if not self.reaffectation:
            donnees.pop("vehicule", None)
            donnees.pop("chauffeur", None)
        try:
            services.modifier_mission(self.mission, **donnees)
        except MissionError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, f"Mission {self.mission.numero} modifiée.")
        return redirect("missions:detail", pk=self.mission.pk)


class ActionMissionView(RoleRequiredMixin, View):
    """Base des actions du cycle de vie : POST uniquement, puis retour à la fiche."""

    http_method_names = ["post"]
    form_class = None

    def executer(self, mission, donnees):  # pragma: no cover - surchargé
        raise NotImplementedError

    def message_succes(self, mission) -> str:  # pragma: no cover - surchargé
        raise NotImplementedError

    def post(self, request, pk):
        mission = get_object_or_404(services.missions_queryset(), pk=pk)
        donnees = {}
        if self.form_class is not None:
            form = self.form_class(request.POST)
            if not form.is_valid():
                for erreurs in form.errors.values():
                    for erreur in erreurs:
                        messages.error(request, erreur)
                return redirect("missions:detail", pk=mission.pk)
            donnees = form.cleaned_data
        try:
            self.executer(mission, donnees)
        except MissionError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, self.message_succes(mission))
        return redirect("missions:detail", pk=mission.pk)


class PlanifierView(ActionMissionView):
    roles = permissions.PLANIFICATION

    def executer(self, mission, donnees):
        services.planifier_mission(mission)

    def message_succes(self, mission):
        return f"Mission {mission.numero} planifiée."


class AffecterView(ActionMissionView):
    roles = permissions.AFFECTATION
    form_class = AffectationForm

    def executer(self, mission, donnees):
        services.affecter_mission(
            mission, vehicule=donnees["vehicule"], chauffeur=donnees["chauffeur"]
        )

    def message_succes(self, mission):
        return f"Mission {mission.numero} affectée."


class DemarrerView(ActionMissionView):
    roles = permissions.SUIVI_TERRAIN

    def executer(self, mission, donnees):
        services.demarrer_mission(mission)

    def message_succes(self, mission):
        return f"Mission {mission.numero} démarrée : camion et chauffeur en mission."


class RecuperationView(ActionMissionView):
    roles = permissions.CODES_TERRAIN
    form_class = CodeForm

    def executer(self, mission, donnees):
        services.confirmer_recuperation(mission, code=donnees["code"])

    def message_succes(self, mission):
        return f"Colis récupéré pour la mission {mission.numero}."


class LivraisonView(ActionMissionView):
    roles = permissions.CODES_TERRAIN
    form_class = LivraisonForm

    def executer(self, mission, donnees):
        services.livrer_mission(
            mission, code=donnees["code"], km_arrivee=donnees["km_arrivee"]
        )

    def message_succes(self, mission):
        return f"Mission {mission.numero} livrée : camion et chauffeur de nouveau disponibles."


class CloturerView(ActionMissionView):
    roles = permissions.CLOTURE

    def executer(self, mission, donnees):
        services.cloturer_mission(mission)

    def message_succes(self, mission):
        return f"Mission {mission.numero} clôturée et validée."


class CodesPdfView(RoleRequiredMixin, View):
    """PDF des codes à transmettre (une page pour l'expéditeur, une pour le destinataire).

    Mêmes règles que l'affichage des codes : rôles qui les voient, et seulement les codes encore
    utiles (jamais après la récupération / la livraison). Produit à la demande, jamais stocké ni
    mis en cache : le code est un secret.
    """

    roles = permissions.CONSULTATION
    http_method_names = ["get"]

    def get(self, request, pk):
        mission = get_object_or_404(services.missions_queryset(), pk=pk)
        codes = permissions.codes_visibles(request.user, mission)
        if not (codes["expediteur"] or codes["destinataire"]):
            raise Http404
        reponse = HttpResponse(documents.generer_pdf_codes(mission, codes), content_type="application/pdf")
        reponse["Content-Disposition"] = f'attachment; filename="codes-{mission.numero}.pdf"'
        reponse["Cache-Control"] = "no-store, private"
        return reponse


class CodeQrView(RoleRequiredMixin, View):
    """Image PNG du code QR d'une mission (« expediteur » ou « destinataire »).

    Le QR ne contient que le code : le chauffeur le scanne (ou le saisit) pour confirmer la
    récupération ou la livraison. Réservé aux rôles qui voient déjà le code, et seulement tant
    que le code est utile ; jamais mis en cache (le code est un secret).
    """

    roles = permissions.CONSULTATION
    http_method_names = ["get"]

    def get(self, request, pk, qui):
        if qui not in ("expediteur", "destinataire"):
            raise Http404
        mission = get_object_or_404(services.missions_queryset(), pk=pk)
        code = permissions.codes_visibles(request.user, mission)[qui]
        if not code:
            raise Http404
        image = qrcode.make(code, box_size=8, border=2)
        tampon = io.BytesIO()
        image.save(tampon, format="PNG")
        reponse = HttpResponse(tampon.getvalue(), content_type="image/png")
        reponse["Cache-Control"] = "no-store, private"
        return reponse
