# Chapitre 23 — Écrans : missions et codes QR

> 25 fichier(s) dans ce chapitre, 4401 lignes de code.

## Ce que vous allez construire

Les **écrans des missions** : le cycle de vie du chapitre 10, cliquable.

| Écran | Adresse | Qui |
|---|---|---|
| Liste (statut, recherche) | `/missions/` | ADMIN, DIRECTION, CHARGE_CLIENTELE |
| **Créer** une mission | `/missions/nouvelle/` | idem |
| **Fiche** avec la **frise du cycle de vie**, les actions possibles, les **codes et leurs QR** | `/missions/<id>/` | idem |
| Actions en POST : **planifier**, **affecter**, **démarrer**, **récupération**, **livraison**, **clôturer** | `/missions/<id>/planifier/`… | selon le rôle et le statut |
| Image QR d'un code | `/missions/<id>/qr/expediteur.png` (ou `destinataire`) | ADMIN, DIRECTION, CHARGE_CLIENTELE |

Deux blocs sont aussi **fournis à d'autres pages** par `missions` : l'alerte « ce chauffeur a une mission prévue
sur la période » (fiche d'un congé, chapitre 19) et la **liste des missions d'un client** (fiche client,
chapitre 21).

## Prérequis

- Chapitres 1 à 22 terminés.

## Ce que ce chapitre apporte de nouveau

- **Des actions dont la disponibilité dépend du rôle *et* du statut** : `permissions.actions_disponibles(utilisateur,
  mission)` (chapitre 10) renvoie un dictionnaire ; le gabarit n'affiche que les boutons dont la valeur est vraie.
  **Mais la vue re-vérifie** : masquer un bouton ne protège rien.
- **Une classe mère d'actions** (`ActionMissionView`) : chaque action (`planifier`, `démarrer`…) hérite d'un
  comportement commun (contrôle du droit, appel du service, message, redirection) et ne définit que ce qui change.
- **Un contenu qui n'est pas une page** : `CodeQrView` renvoie une **image PNG** fabriquée à la volée avec la
  bibliothèque `qrcode`. Elle est réservée aux rôles qui voient les codes, **jamais mise en cache**
  (`Cache-Control: no-store, private`), et l'image ne contient **que le code**.
- **Des codes montrés seulement tant qu'ils servent** : `permissions.codes_visibles`.
- **Des gabarits qui s'incluent dans d'autres apps** : `_alerte_conge.html` et `_missions_client.html` sont des
  *fragments* (leur nom commence par `_`) chargés par les registres de sections.

## Étape 1 — Formulaires, vues, adresses

#### `apps/missions/forms.py`

*183 lignes*

```python
from django import forms

from apps.core.forms import StyleTailwindMixin
from apps.customers import services as customers_services
from apps.drivers import services as drivers_services
from apps.fleet import services as fleet_services

from .models import TypeFraisMission
from .terrain import TYPES_PLANIFIABLES


class MissionForm(StyleTailwindMixin, forms.Form):
    """Création d'une mission (cahier-des-charges.md:129-131)."""

    client = forms.ModelChoiceField(queryset=None, label="Client")
    # « list » relie le champ à la liste de suggestions « lieux-missions » (mission_form.html) :
    # les lieux déjà utilisés s'affichent dès les premières lettres, la saisie libre reste possible.
    lieu_chargement = forms.CharField(
        label="Lieu de chargement",
        max_length=200,
        widget=forms.TextInput(attrs={"list": "lieux-missions", "autocomplete": "off"}),
    )
    lieu_livraison = forms.CharField(
        label="Lieu de livraison",
        max_length=200,
        widget=forms.TextInput(attrs={"list": "lieux-missions", "autocomplete": "off"}),
    )
    nature_marchandise = forms.CharField(label="Nature de la marchandise", max_length=200)
    poids_t = forms.DecimalField(
        label="Poids (tonnes)", min_value=0, decimal_places=2, max_digits=8
    )
    prix_convenu = forms.DecimalField(
        label="Prix convenu (FCFA)", min_value=0, decimal_places=2, max_digits=12
    )
    date_depart_prevue = forms.DateField(
        label="Départ prévu",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Facultatif. Sert à repérer les conflits avec les congés des chauffeurs.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = customers_services.clients_pour_selection()


class ModificationForm(StyleTailwindMixin, forms.Form):
    """Modification d'une mission déjà créée (avenant-separation-des-taches.md § R3).

    Le camion et le chauffeur ne sont proposés que si la mission est déjà affectée
    (``reaffectation=True``) : avant, il n'y en a pas encore à réaffecter.
    """

    lieu_chargement = forms.CharField(
        label="Lieu de chargement",
        max_length=200,
        widget=forms.TextInput(attrs={"list": "lieux-missions", "autocomplete": "off"}),
    )
    lieu_livraison = forms.CharField(
        label="Lieu de livraison",
        max_length=200,
        widget=forms.TextInput(attrs={"list": "lieux-missions", "autocomplete": "off"}),
    )
    nature_marchandise = forms.CharField(label="Nature de la marchandise", max_length=200)
    poids_t = forms.DecimalField(
        label="Poids (tonnes)", min_value=0, decimal_places=2, max_digits=8
    )
    prix_convenu = forms.DecimalField(
        label="Prix convenu (FCFA)", min_value=0, decimal_places=2, max_digits=12
    )
    date_depart_prevue = forms.DateField(
        label="Départ prévu", required=False, widget=forms.DateInput(attrs={"type": "date"}),
    )
    vehicule = forms.ModelChoiceField(queryset=None, label="Camion disponible", required=False)
    chauffeur = forms.ModelChoiceField(queryset=None, label="Chauffeur disponible", required=False)

    def __init__(self, *args, reaffectation=False, **kwargs):
        super().__init__(*args, **kwargs)
        if reaffectation:
            self.fields["vehicule"].queryset = fleet_services.vehicules_disponibles()
            self.fields["vehicule"].label_from_instance = lambda v: (
                f"{v.immatriculation} - {v.marque} {v.modele} ({v.capacite_charge_t} t)"
            )
            self.fields["chauffeur"].queryset = drivers_services.chauffeurs_disponibles()
        else:
            del self.fields["vehicule"]
            del self.fields["chauffeur"]


class AffectationForm(StyleTailwindMixin, forms.Form):
    """Affectation d'un camion, d'un chauffeur disponibles et, si le voyage l'exige, d'un copilote."""

    vehicule = forms.ModelChoiceField(queryset=None, label="Camion disponible")
    chauffeur = forms.ModelChoiceField(queryset=None, label="Chauffeur disponible")
    copilote = forms.ModelChoiceField(
        queryset=None, label="Copilote", required=False, empty_label="Aucun (facultatif)"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vehicule"].queryset = fleet_services.vehicules_disponibles()
        self.fields["vehicule"].label_from_instance = lambda v: (
            f"{v.immatriculation} - {v.marque} {v.modele} ({v.capacite_charge_t} t)"
        )
        self.fields["chauffeur"].queryset = drivers_services.chauffeurs_disponibles()
        self.fields["copilote"].queryset = drivers_services.copilotes_disponibles()


class CodeForm(StyleTailwindMixin, forms.Form):
    """Saisie du code remis à l'expéditeur ou au destinataire."""

    code = forms.CharField(
        label="Code", max_length=12, widget=forms.TextInput(attrs={"autocomplete": "off"})
    )


class LivraisonForm(CodeForm):
    km_arrivee = forms.IntegerField(label="Kilométrage à l'arrivée", min_value=0)


class FraisPrevisionForm(StyleTailwindMixin, forms.Form):
    """Le Parc Auto planifie une avance de route ou une dépense prévue (R4)."""

    type_frais = forms.ChoiceField(
        label="Type",
        choices=[(t, l) for t, l in TypeFraisMission.choices if t in TYPES_PLANIFIABLES],
    )
    montant = forms.DecimalField(label="Montant (FCFA)", min_value=0, decimal_places=2, max_digits=12)
    description = forms.CharField(label="Libellé", max_length=255, required=False)


class MotifRejetFraisForm(StyleTailwindMixin, forms.Form):
    """Motif du rejet d'un frais de mission."""

    motif = forms.CharField(label="Motif du rejet", widget=forms.Textarea(attrs={"rows": 2}))


class AnnulationMissionForm(StyleTailwindMixin, forms.Form):
    motif = forms.CharField(label="Motif de l'annulation", widget=forms.Textarea(attrs={"rows": 2}))


class TransfertMissionForm(StyleTailwindMixin, forms.Form):
    """Transfert en route (audit AUD-02) : les listes proposent les camions, chauffeurs et copilotes disponibles, et
    l'équipage actuel pour pouvoir le garder (ne changer que le chauffeur, par exemple)."""

    vehicule = forms.ModelChoiceField(queryset=None, label="Camion")
    chauffeur = forms.ModelChoiceField(queryset=None, label="Chauffeur")
    copilote = forms.ModelChoiceField(queryset=None, label="Copilote", required=False, empty_label="Aucun (facultatif)")
    km_ancien_vehicule = forms.IntegerField(
        label="Kilométrage de l'ancien camion au transfert", min_value=0,
        help_text="Compteur du camion laissé en route (ignoré si le camion ne change pas).",
    )
    statut_ancien_vehicule = forms.ChoiceField(label="L'ancien camion passe", choices=())
    motif = forms.CharField(label="Motif du transfert", widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, mission, **kwargs):
        from apps.drivers.models import Chauffeur, Copilote
        from apps.fleet.models import StatutVehicule, Vehicule

        from .services import STATUTS_ANCIEN_CAMION

        super().__init__(*args, **kwargs)
        self.fields["vehicule"].queryset = (
            fleet_services.vehicules_disponibles() | Vehicule.objects.filter(pk=mission.vehicule_id)
        ).distinct()
        self.fields["vehicule"].label_from_instance = lambda v: (
            f"{v.immatriculation} - {v.marque} {v.modele} ({v.capacite_charge_t} t)"
            + (" — camion actuel" if v.pk == mission.vehicule_id else "")
        )
        self.fields["chauffeur"].queryset = (
            drivers_services.chauffeurs_disponibles() | Chauffeur.objects.filter(pk=mission.chauffeur_id)
        ).distinct()
        self.fields["copilote"].queryset = (
            drivers_services.copilotes_disponibles() | Copilote.objects.filter(pk=mission.copilote_id)
        ).distinct()
        self.fields["statut_ancien_vehicule"].choices = [
            (code, StatutVehicule(code).label) for code in STATUTS_ANCIEN_CAMION
        ]
        self.initial.setdefault("vehicule", mission.vehicule_id)
        self.initial.setdefault("chauffeur", mission.chauffeur_id)
        self.initial.setdefault("copilote", mission.copilote_id)
        if mission.vehicule_id:
            self.initial.setdefault("km_ancien_vehicule", mission.vehicule.kilometrage)
```

#### `apps/missions/views.py`

*605 lignes* — Écrans des missions.

```python
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
from apps.core.rapports import contexte_rapport
from apps.core import pdf
from apps.core.views import ImpressionListeMixin, PaginationTolerante, TelechargementPdfMixin, fcfa
from apps.core.xlsx import ExportXlsxMixin

from . import documents, permissions, services
from . import terrain as frais_terrain
from .exceptions import MissionError
from .forms import (
    AffectationForm,
    AnnulationMissionForm,
    CodeForm,
    FraisPrevisionForm,
    LivraisonForm,
    MissionForm,
    ModificationForm,
    MotifRejetFraisForm,
    TransfertMissionForm,
)
from .models import STATUTS_MODIFIABLES, FraisMission, Mission, StatutMission

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
    """Frise du cycle de vie : chaque étape est faite, en cours ou à venir. Une mission annulée n'a pas de frise
    (audit AUD-02) : son motif d'annulation s'affiche à la place."""
    codes = [code for code, _ in ETAPES]
    if statut not in codes:
        return []
    rang_courant = codes.index(statut)
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

    def get(self, request, *args, **kwargs):
        reponse = super().get(request, *args, **kwargs)
        # La fiche affiche les codes de départ et de livraison : jamais gardée en cache (ordinateur partagé, bouton
        # « précédent » après déconnexion), comme le PDF et le QR des codes (audit AUD-15).
        reponse["Cache-Control"] = "no-store, private"
        return reponse

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
            peut_voir_frais=utilisateur.role_effectif in permissions.FRAIS_CONSULTATION,
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

    def charger_objet(self, request, *args, **kwargs):
        self.mission = get_object_or_404(services.missions_queryset(), pk=kwargs["pk"])

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
            mission, vehicule=donnees["vehicule"], chauffeur=donnees["chauffeur"],
            copilote=donnees.get("copilote"),
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


# --- prévision de trésorerie des missions (R4) ---


class FraisMissionListeView(PaginationTolerante, RoleRequiredMixin, ListView):
    """Lignes en attente (toutes missions), pour le Parc Auto et la Finance."""

    roles = permissions.FRAIS_CONSULTATION
    template_name = "missions/frais_liste.html"
    context_object_name = "lignes"
    paginate_by = 30

    def get_queryset(self):
        return frais_terrain.frais_a_traiter()


class FraisMissionDetailView(RoleRequiredMixin, DetailView):
    """Prévision de trésorerie d'une mission : lignes, totaux, planification et validation."""

    roles = permissions.FRAIS_CONSULTATION
    template_name = "missions/frais_detail.html"
    context_object_name = "mission"

    def get_queryset(self):
        return services.missions_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        mission = self.object
        role = self.request.user.role
        peut_planifier = self.request.user.role_effectif in permissions.FRAIS_SAISIE_PREVISION
        contexte.update(
            lignes=frais_terrain.frais_queryset(mission),
            totaux=frais_terrain.totaux(mission),
            peut_planifier=peut_planifier,
            peut_valider_parcauto=role in permissions.FRAIS_VALIDATION_PARCAUTO,
            peut_valider_finances=role in permissions.FRAIS_VALIDATION_FINANCES,
            form_planifier=FraisPrevisionForm() if peut_planifier else None,
            form_rejet=MotifRejetFraisForm(),
        )
        return contexte


class FraisMissionPrintView(TelechargementPdfMixin, RoleRequiredMixin, DetailView):
    """Rapport de mission imprimable (et en PDF, ``?format=pdf``) : toutes les lignes et leurs totaux."""

    roles = permissions.FRAIS_CONSULTATION
    template_name = "missions/frais_print.html"
    context_object_name = "mission"

    def get_queryset(self):
        return services.missions_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(contexte_rapport(self.request, titre=f"Rapport de mission {self.object.numero}"))
        contexte.update(lignes=frais_terrain.frais_queryset(self.object), totaux=frais_terrain.totaux(self.object))
        return contexte

    def blocs_pdf(self, contexte):
        mission = self.object

        def detail(frais):
            if frais.type_frais == "IMPREVU" and frais.chauffeur_id:
                auteur = f"{frais.chauffeur.personnel.prenom} {frais.chauffeur.personnel.nom}"
            else:
                auteur = str(frais.saisi_par or "—")
            return f"{auteur} · {frais.description}" if frais.description else auteur

        totaux = contexte["totaux"]
        return [
            pdf.Texte(f"{mission.client.raison_sociale}\n{mission.lieu_chargement} → {mission.lieu_livraison} "
                      f"({mission.nature_marchandise})"),
            pdf.Tableau(
                entetes=["Type", "Détail", "Statut", "Montant"],
                lignes=[
                    [f.get_type_frais_display(), detail(f), f.get_statut_display(), pdf.cellule(f.montant)]
                    for f in contexte["lignes"]
                ],
                alignes_a_droite={3}, largeurs=[2, 5, 2, 2],
            ),
            pdf.Rubriques([
                ("Sorties confirmées", fcfa(totaux["sorties"])),
                ("Encaissé confirmé", fcfa(totaux["encaisse"])),
                ("Solde", fcfa(totaux["solde"])),
            ]),
        ]


class FraisPlanifierView(RoleRequiredMixin, View):
    roles = permissions.FRAIS_SAISIE_PREVISION
    http_method_names = ["post"]

    def post(self, request, pk):
        mission = get_object_or_404(Mission, pk=pk)
        form = FraisPrevisionForm(request.POST)
        if not form.is_valid():
            for erreurs in form.errors.values():
                for erreur in erreurs:
                    messages.error(request, erreur)
            return redirect("missions:frais", pk=mission.pk)
        try:
            frais_terrain.planifier_frais(mission, request.user, **form.cleaned_data)
        except MissionError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, "Frais planifié : la finance peut le confirmer.")
        return redirect("missions:frais", pk=mission.pk)


class _ActionFrais(RoleRequiredMixin, View):
    """Action en POST sur un frais de mission : formulaire → service → message → retour à la mission."""

    http_method_names = ["post"]
    form_class = None

    def executer(self, request, frais, donnees):  # pragma: no cover - surchargé
        raise NotImplementedError

    def post(self, request, frais_pk):
        frais = get_object_or_404(FraisMission, pk=frais_pk)
        donnees = {}
        if self.form_class is not None:
            form = self.form_class(request.POST)
            if not form.is_valid():
                for erreurs in form.errors.values():
                    for erreur in erreurs:
                        messages.error(request, erreur)
                return redirect("missions:frais", pk=frais.mission_id)
            donnees = form.cleaned_data
        try:
            message = self.executer(request, frais, donnees)
        except MissionError as erreur:
            messages.error(request, str(erreur))
        else:
            if message:
                messages.success(request, message)
        return redirect("missions:frais", pk=frais.mission_id)


class FraisValiderParcautoView(_ActionFrais):
    roles = permissions.FRAIS_VALIDATION_PARCAUTO

    def executer(self, request, frais, donnees):
        frais_terrain.valider_parcauto(frais, request.user)
        return "Imprévu validé : transmis à la finance pour confirmation."


class FraisValiderFinancesView(_ActionFrais):
    roles = permissions.FRAIS_VALIDATION_FINANCES

    def executer(self, request, frais, donnees):
        frais_terrain.valider_finances(frais, request.user)
        return "Frais confirmé : comptabilisé en dépense."


class FraisRejeterView(_ActionFrais):
    roles = permissions.FRAIS_VALIDATION_PARCAUTO | permissions.FRAIS_VALIDATION_FINANCES
    form_class = MotifRejetFraisForm

    def executer(self, request, frais, donnees):
        frais_terrain.rejeter(frais, request.user, motif=donnees["motif"])
        return "Frais rejeté."


class MissionExporterXlsxView(ExportXlsxMixin, MissionImprimerView):
    """Export Excel (mêmes droits et filtres que la liste), valeurs brutes — audit TECH-83."""

    nom_fichier = "missions"
    colonnes = (
        ("N°", "numero"), ("Client", "client.raison_sociale"),
        ("Chargement", "lieu_chargement"), ("Livraison", "lieu_livraison"),
        ("Départ prévu", lambda m: m.date_depart_prevue),
        ("Camion", lambda m: m.vehicule.immatriculation if m.vehicule_id else ""),
        ("Chauffeur", lambda m: f"{m.chauffeur.personnel.prenom} {m.chauffeur.personnel.nom}" if m.chauffeur_id else ""),
        ("Statut", "get_statut_display"), ("Prix convenu (FCFA)", lambda m: m.prix_convenu),
    )


# --- annulation avant le départ et transfert en route (décision du 13/10/2026, audit AUD-02) ---


class AnnulerView(RoleRequiredMixin, View):
    roles = permissions.ANNULATION
    http_method_names = ["post"]

    def post(self, request, pk):
        mission = get_object_or_404(services.missions_queryset(), pk=pk)
        form = AnnulationMissionForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Le motif de l'annulation est obligatoire.")
            return redirect("missions:detail", pk=mission.pk)
        try:
            services.annuler_mission(mission, request.user, motif=form.cleaned_data["motif"])
        except MissionError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, f"Mission {mission.numero} annulée : le camion et le chauffeur ne sont plus réservés.")
        return redirect("missions:detail", pk=mission.pk)


class TransfererView(RoleRequiredMixin, FormView):
    roles = permissions.TRANSFERT
    template_name = "missions/mission_transfert.html"
    form_class = TransfertMissionForm

    def charger_objet(self, request, *args, **kwargs):
        self.mission = get_object_or_404(services.missions_queryset(), pk=kwargs["pk"])

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "mission": self.mission}

    def get_context_data(self, **kwargs):
        return super().get_context_data(mission=self.mission, **kwargs)

    def form_valid(self, form):
        try:
            transfert = services.transferer_mission(self.mission, self.request.user, **form.cleaned_data)
        except MissionError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(
            self.request,
            f"Mission {self.mission.numero} transférée : {transfert.nouveau_vehicule.immatriculation}, "
            f"chauffeur {transfert.nouveau_chauffeur}.",
        )
        return redirect("missions:detail", pk=self.mission.pk)
```

Repérez :

- **`MissionListView`** : filtre par statut et texte via `services.rechercher_missions`.
- **`MissionDetailView`** : calcule `actions`, `codes` (montrés selon le rôle et le statut), la frise, et les
  formulaires (affectation, code, livraison) à afficher.
- **`ActionMissionView`** et ses filles : une transition = une classe de quelques lignes.
- **`CodeQrView`** : l'image du code, avec les en-têtes de non-mise en cache.

#### `apps/missions/urls.py`

*39 lignes*

```python
from django.urls import path

from . import views

app_name = "missions"

urlpatterns = [
    path("", views.MissionListView.as_view(), name="liste"),
    path("imprimer/", views.MissionImprimerView.as_view(), name="imprimer"),
    path("excel/", views.MissionExporterXlsxView.as_view(), name="xlsx"),
    path("nouvelle/", views.MissionCreateView.as_view(), name="creer"),
    path("<int:pk>/", views.MissionDetailView.as_view(), name="detail"),
    path("<int:pk>/modifier/", views.MissionUpdateView.as_view(), name="modifier"),
    path("<int:pk>/planifier/", views.PlanifierView.as_view(), name="planifier"),
    path("<int:pk>/affecter/", views.AffecterView.as_view(), name="affecter"),
    path("<int:pk>/demarrer/", views.DemarrerView.as_view(), name="demarrer"),
    path("<int:pk>/recuperation/", views.RecuperationView.as_view(), name="recuperation"),
    path("<int:pk>/livraison/", views.LivraisonView.as_view(), name="livraison"),
    path("<int:pk>/cloturer/", views.CloturerView.as_view(), name="cloturer"),
    path("<int:pk>/annuler/", views.AnnulerView.as_view(), name="annuler"),
    path("<int:pk>/transferer/", views.TransfererView.as_view(), name="transferer"),
    path("<int:pk>/codes.pdf", views.CodesPdfView.as_view(), name="codes_pdf"),
    path("<int:pk>/qr/<str:qui>.png", views.CodeQrView.as_view(), name="qr"),
    path("frais/", views.FraisMissionListeView.as_view(), name="frais_liste"),
    path("<int:pk>/frais/", views.FraisMissionDetailView.as_view(), name="frais"),
    path("<int:pk>/frais/imprimer/", views.FraisMissionPrintView.as_view(), name="frais_imprimer"),
    path("<int:pk>/frais/planifier/", views.FraisPlanifierView.as_view(), name="frais_planifier"),
    path(
        "frais/<int:frais_pk>/valider-parcauto/",
        views.FraisValiderParcautoView.as_view(),
        name="frais_valider_parcauto",
    ),
    path(
        "frais/<int:frais_pk>/valider-finances/",
        views.FraisValiderFinancesView.as_view(),
        name="frais_valider_finances",
    ),
    path("frais/<int:frais_pk>/rejeter/", views.FraisRejeterView.as_view(), name="frais_rejeter"),
]
```

#### `config/urls.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/urls.py (avant)
+++ config/urls.py (après)
@@ -22,4 +22,5 @@
     path("documents-pdf/<uuid:cle>/telecharger/", DocumentPdfTelechargerView.as_view(), name="document_pdf_telecharger"),
     path("", include("apps.accounts.urls")),
+    path("missions/", include("apps.missions.urls")),
     path("clients/", include("apps.customers.urls")),
     path("flotte/", include("apps.fleet.urls")),
```

## Étape 2 — Gabarits

```bash
mkdir -p apps/missions/templates/missions
```

#### `apps/missions/templates/missions/mission_list.html`

*101 lignes*

```django
{% extends "base.html" %}
{% load humanize static ui %}
{% block titre %}Missions{% endblock %}
{% block entete %}Missions{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-7xl" data-suivi-missions data-ws-chemin="/ws/missions/suivi/">
  <div class="flex flex-wrap items-end justify-between gap-3">
    <div>
      <h1 class="text-2xl font-bold text-slate-900">Missions</h1>
      <p class="mt-1 text-sm text-slate-600" data-suivi-zone="compteur">{{ paginator.count|default:0 }} mission{{ paginator.count|pluralize }}</p>
      <div class="mt-2">{% include "components/_suivi_direct.html" %}</div>
    </div>
    <div class="flex flex-wrap items-center gap-2">
      <a href="{% url 'missions:imprimer' %}?{{ request.GET.urlencode }}" target="_blank" rel="noopener"
         class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
        <i class="fa-solid fa-print" aria-hidden="true"></i> Imprimer
      </a>
      {% url 'missions:xlsx' as url_xlsx %}{% include "components/_bouton_xlsx.html" with url=url_xlsx %}
      {% if peut_creer %}
        <a href="{% url 'missions:creer' %}"
           class="inline-flex items-center gap-2 rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
          <i class="fa-solid fa-plus" aria-hidden="true"></i> Nouvelle mission
        </a>
      {% endif %}
    </div>
  </div>

  <form method="get" class="mt-5 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
    <div class="min-w-[14rem] flex-1">
      <label for="q" class="block text-sm font-medium text-slate-800">Rechercher</label>
      <input type="search" id="q" name="q" value="{{ recherche }}" placeholder="N°, client, lieu…"
             class="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30">
    </div>
    <div>
      <label for="statut" class="block text-sm font-medium text-slate-800">Statut</label>
      <select id="statut" name="statut"
              class="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30">
        <option value="">Tous les statuts</option>
        {% for code, libelle in statuts %}
          <option value="{{ code }}" {% if code == statut_choisi %}selected{% endif %}>{{ libelle }}</option>
        {% endfor %}
      </select>
    </div>
    <button type="submit" class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Filtrer</button>
    {% if recherche or statut_choisi %}
      <a href="{% url 'missions:liste' %}" class="px-2 py-2 text-sm font-medium text-slate-700 underline hover:text-slate-900">Réinitialiser</a>
    {% endif %}
  </form>

  <div data-suivi-zone="liste">
  {% if missions %}
    <div class="mt-5 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <caption class="sr-only">Liste des missions</caption>
        <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr>
            <th scope="col" class="px-4 py-3">N°</th>
            <th scope="col" class="px-4 py-3">Client</th>
            <th scope="col" class="px-4 py-3">Trajet</th>
            <th scope="col" class="px-4 py-3 text-right">Poids</th>
            <th scope="col" class="px-4 py-3">Camion</th>
            <th scope="col" class="px-4 py-3">Chauffeur</th>
            <th scope="col" class="px-4 py-3 text-right">Prix</th>
            <th scope="col" class="px-4 py-3">Statut</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          {% for mission in missions %}
            <tr class="hover:bg-slate-50">
              <td class="whitespace-nowrap px-4 py-3 font-semibold">
                <a href="{% url 'missions:detail' mission.pk %}" class="text-marque-700 underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">{{ mission.numero }}</a>
              </td>
              <td class="px-4 py-3 text-slate-800">{{ mission.client }}</td>
              <td class="px-4 py-3 text-slate-700">{{ mission.lieu_chargement }} <span aria-label="vers">→</span> {{ mission.lieu_livraison }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right text-slate-700">{{ mission.poids_t|floatformat:"-2" }} t</td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ mission.vehicule.immatriculation|default:"—" }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{% if mission.chauffeur %}{{ mission.chauffeur.personnel.prenom }} {{ mission.chauffeur.personnel.nom }}{% else %}—{% endif %}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right text-slate-800">{{ mission.prix_convenu|floatformat:0|intcomma }} FCFA</td>
              <td class="whitespace-nowrap px-4 py-3">{% badge mission.statut mission.get_statut_display %}</td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% include "components/_pagination.html" %}
  {% else %}
    <div class="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
      <span class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-600">
        <i class="fa-solid fa-truck-fast" aria-hidden="true"></i>
      </span>
      <p class="mt-3 font-semibold text-slate-900">Aucune mission trouvée</p>
      <p class="mt-1 text-sm text-slate-600">
        {% if recherche or statut_choisi %}Aucun résultat pour ces critères.{% else %}Les missions créées apparaîtront ici.{% endif %}
      </p>
    </div>
  {% endif %}
  </div>{# fin de la zone rafraîchie en direct #}
</div>
<script src="{% static 'js/suivi-missions.js' %}" defer></script>
{% endblock %}
```

#### `apps/missions/templates/missions/mission_form.html`

*45 lignes*

```django
{% extends "base.html" %}
{% block titre %}Nouvelle mission{% endblock %}
{% block entete %}Missions{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-3xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'missions:liste' %}" class="underline-offset-2 hover:underline">Missions</a>
    <span aria-hidden="true">/</span> Nouvelle mission
  </nav>
  <h1 class="mt-2 text-2xl font-bold text-slate-900">Nouvelle mission</h1>
  <p class="mt-1 text-sm text-slate-600">
    La mission est créée en brouillon ; elle reçoit son numéro et ses deux codes (expéditeur, destinataire).
  </p>

  {# Lieux déjà utilisés par des missions : suggérés dès les premières lettres (champs « list ») #}
  <datalist id="lieux-missions">{% for lieu in lieux %}<option value="{{ lieu }}"></option>{% endfor %}</datalist>

  <form method="post" novalidate class="mt-6 space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
    {% csrf_token %}
    {% if form.non_field_errors %}
      <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">
        {% for erreur in form.non_field_errors %}<p>{{ erreur }}</p>{% endfor %}
      </div>
    {% endif %}

    <div class="grid grid-cols-1 gap-5 sm:grid-cols-2">
      <div class="sm:col-span-2">{% include "components/_champ.html" with champ=form.client %}</div>
      {% include "components/_champ.html" with champ=form.lieu_chargement %}
      {% include "components/_champ.html" with champ=form.lieu_livraison %}
      <div class="sm:col-span-2">{% include "components/_champ.html" with champ=form.nature_marchandise %}</div>
      {% include "components/_champ.html" with champ=form.poids_t %}
      {% include "components/_champ.html" with champ=form.prix_convenu %}
      <div class="sm:col-span-2">{% include "components/_champ.html" with champ=form.date_depart_prevue %}</div>
    </div>

    <div class="flex items-center justify-end gap-3 border-t border-slate-100 pt-5">
      <a href="{% url 'missions:liste' %}" class="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">Annuler</a>
      <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
        Créer la mission
      </button>
    </div>
  </form>
</div>
{% endblock %}
```

#### `apps/missions/templates/missions/mission_detail.html`

*232 lignes*

```django
{% extends "base.html" %}
{% load humanize static ui %}
{% block titre %}{{ mission.numero }}{% endblock %}
{% block entete %}Missions{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-5xl" data-suivi-missions data-ws-chemin="/ws/missions/suivi/" data-mission-id="{{ mission.pk }}">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'missions:liste' %}" class="underline-offset-2 hover:underline">Missions</a>
    <span aria-hidden="true">/</span> {{ mission.numero }}
  </nav>
  <div class="mt-2">{% include "components/_suivi_direct.html" %}</div>

  {% if peut_voir_frais %}
    <div class="mt-2 text-right">
      <a href="{% url 'missions:frais' mission.pk %}" class="text-sm font-medium text-marque-700 underline-offset-2 hover:underline">
        <i class="fa-solid fa-money-bill-transfer mr-1" aria-hidden="true"></i>Frais de mission
      </a>
    </div>
  {% endif %}

  {# Zone rafraîchie en direct (static/js/suivi-missions.js) : statut, frise, actions et codes #}
  <div data-suivi-zone="mission">
  <div class="mt-2 flex flex-wrap items-center justify-between gap-3">
    <div class="flex flex-wrap items-center gap-3">
      <h1 class="text-2xl font-bold text-slate-900">{{ mission.numero }}</h1>
      {% badge mission.statut mission.get_statut_display %}
    </div>
    {% if peut_modifier %}
      <a href="{% url 'missions:modifier' mission.pk %}"
         class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
        <i class="fa-solid fa-pen" aria-hidden="true"></i> Modifier
      </a>
    {% endif %}
  </div>
  <p class="mt-1 text-sm text-slate-600">{{ mission.client }}</p>

  {# Frise du cycle de vie #}
  <ol class="mt-6 flex flex-wrap gap-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm" aria-label="Avancement de la mission">
    {% for etape in etapes %}
      <li class="flex items-center" {% if etape.etat == "courante" %}aria-current="step"{% endif %}>
        <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold
              {% if etape.etat == 'faite' %}bg-emerald-700 text-white
              {% elif etape.etat == 'courante' %}bg-accent-500 text-slate-900 ring-4 ring-accent-200
              {% else %}bg-slate-200 text-slate-600{% endif %}">
          {% if etape.etat == "faite" %}<i class="fa-solid fa-check" aria-hidden="true"></i><span class="sr-only">Terminée : </span>{% else %}{{ forloop.counter }}{% endif %}
        </span>
        <span class="ml-2 text-sm {% if etape.etat == 'courante' %}font-semibold text-slate-900{% elif etape.etat == 'faite' %}text-slate-800{% else %}text-slate-600{% endif %}">{{ etape.libelle }}</span>
        {% if not forloop.last %}<span class="mx-3 hidden h-px w-6 bg-slate-300 sm:block" aria-hidden="true"></span>{% endif %}
      </li>
    {% endfor %}
  </ol>

  <div class="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
    <div class="space-y-6 lg:col-span-2">
      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-transport">
        <h2 id="titre-transport" class="text-base font-semibold text-slate-900">Transport</h2>
        <dl class="mt-4 grid grid-cols-1 gap-x-6 gap-y-4 text-sm sm:grid-cols-2">
          <div><dt class="text-slate-600">Chargement</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.lieu_chargement }}</dd></div>
          <div><dt class="text-slate-600">Livraison</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.lieu_livraison }}</dd></div>
          <div><dt class="text-slate-600">Marchandise</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.nature_marchandise }}</dd></div>
          <div><dt class="text-slate-600">Poids</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.poids_t|floatformat:"-2" }} t</dd></div>
          <div><dt class="text-slate-600">Prix convenu</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.prix_convenu|floatformat:0|intcomma }} FCFA</dd></div>
          <div><dt class="text-slate-600">Départ prévu</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.date_depart_prevue|date:"d/m/Y"|default:"Non renseigné" }}</dd></div>
        </dl>
      </section>

      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-affectation">
        <h2 id="titre-affectation" class="text-base font-semibold text-slate-900">Camion et chauffeur</h2>
        {% if mission.vehicule %}
          <dl class="mt-4 grid grid-cols-1 gap-x-6 gap-y-4 text-sm sm:grid-cols-2">
            <div><dt class="text-slate-600">Camion</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.vehicule.immatriculation }} — {{ mission.vehicule.marque }} {{ mission.vehicule.modele }}</dd></div>
            <div><dt class="text-slate-600">Chauffeur</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.chauffeur.personnel.prenom }} {{ mission.chauffeur.personnel.nom }}</dd></div>
            {% if mission.copilote %}
              <div><dt class="text-slate-600">Copilote</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.copilote.personnel.prenom }} {{ mission.copilote.personnel.nom }}</dd></div>
            {% endif %}
            <div><dt class="text-slate-600">Km au départ</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.km_depart|default_if_none:"—"|intcomma }}</dd></div>
            <div><dt class="text-slate-600">Km à l'arrivée</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.km_arrivee|default_if_none:"—"|intcomma }}</dd></div>
          </dl>
        {% else %}
          <p class="mt-3 text-sm text-slate-700">Aucun camion ni chauffeur affecté pour l'instant.</p>
        {% endif %}
      </section>

      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-dates">
        <h2 id="titre-dates" class="text-base font-semibold text-slate-900">Historique</h2>
        <dl class="mt-4 grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
          <div><dt class="text-slate-600">Créée le</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.created_at|date:"d/m/Y H:i" }}</dd></div>
          <div><dt class="text-slate-600">Départ effectif</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.date_depart|date:"d/m/Y H:i"|default:"—" }}</dd></div>
          <div><dt class="text-slate-600">Colis récupéré le</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.date_recuperation|date:"d/m/Y H:i"|default:"—" }}</dd></div>
          <div><dt class="text-slate-600">Livrée le</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.date_livraison|date:"d/m/Y H:i"|default:"—" }}</dd></div>
          <div><dt class="text-slate-600">Clôturée le</dt><dd class="mt-0.5 font-medium text-slate-900">{{ mission.date_cloture|date:"d/m/Y H:i"|default:"—" }}</dd></div>
        </dl>
      </section>
    </div>

    <div class="space-y-6">
      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-actions">
        <h2 id="titre-actions" class="text-base font-semibold text-slate-900">Actions</h2>

        {% if actions.planifier %}
          <form method="post" action="{% url 'missions:planifier' mission.pk %}" class="mt-4">
            {% csrf_token %}
            <p class="mb-2 text-sm text-slate-700">Valider la mission pour la rendre disponible à l'affectation.</p>
            <button type="submit" class="w-full rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Valider et planifier</button>
          </form>
        {% endif %}

        {% if actions.affecter %}
          <form method="post" action="{% url 'missions:affecter' mission.pk %}" class="mt-4 space-y-4">
            {% csrf_token %}
            {% include "components/_champ.html" with champ=form_affectation.vehicule %}
            {% include "components/_champ.html" with champ=form_affectation.chauffeur %}
            {% include "components/_champ.html" with champ=form_affectation.copilote %}
            <button type="submit" class="w-full rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Affecter</button>
          </form>
        {% endif %}

        {% if actions.demarrer %}
          <form method="post" action="{% url 'missions:demarrer' mission.pk %}" class="mt-4"
                data-confirm="Démarrer la mission ? Le camion et le chauffeur passeront « En mission ».">
            {% csrf_token %}
            <button type="submit" class="w-full rounded-lg bg-accent-500 px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-accent-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-600 focus-visible:ring-offset-2">Démarrer la mission</button>
          </form>
        {% endif %}

        {% if actions.recuperation %}
          <form method="post" action="{% url 'missions:recuperation' mission.pk %}" class="mt-4 space-y-4">
            {% csrf_token %}
            <p class="text-sm text-slate-700">L'expéditeur confirme la récupération du colis avec son code.</p>
            {% include "components/_champ.html" with champ=form_recuperation.code %}
            <button type="submit" class="w-full rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Confirmer la récupération</button>
          </form>
        {% endif %}

        {% if actions.livraison %}
          <form method="post" action="{% url 'missions:livraison' mission.pk %}" class="mt-4 space-y-4">
            {% csrf_token %}
            <p class="text-sm text-slate-700">Le destinataire confirme la livraison avec son code.</p>
            {% include "components/_champ.html" with champ=form_livraison.code %}
            {% include "components/_champ.html" with champ=form_livraison.km_arrivee %}
            <button type="submit" class="w-full rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 focus-visible:ring-offset-2">Confirmer la livraison</button>
          </form>
        {% endif %}

        {% if actions.cloturer %}
          <form method="post" action="{% url 'missions:cloturer' mission.pk %}" class="mt-4"
                data-confirm="Clôturer et valider définitivement cette mission ?">
            {% csrf_token %}
            <button type="submit" class="w-full rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Clôturer et valider</button>
          </form>
        {% endif %}

        {% if mission.statut == "EN_COURS_DEPART" and not actions.recuperation %}
          <p class="mt-4 text-sm text-slate-700"><i class="fa-solid fa-mobile-screen mr-1" aria-hidden="true"></i>La récupération se confirme par le code de l'expéditeur, saisi ou scanné par le chauffeur affecté depuis son téléphone. Cet écran se met à jour dès que c'est fait.</p>
        {% elif mission.statut == "EN_COURS_COLIS_RECUPERE" and not actions.livraison %}
          <p class="mt-4 text-sm text-slate-700"><i class="fa-solid fa-mobile-screen mr-1" aria-hidden="true"></i>La livraison se confirme par le code du destinataire, saisi ou scanné par le chauffeur affecté depuis son téléphone. Cet écran se met à jour dès que c'est fait.</p>
        {% endif %}

        {% if actions.transferer %}
          <a href="{% url 'missions:transferer' mission.pk %}"
             class="mt-4 flex w-full items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
            <i class="fa-solid fa-right-left" aria-hidden="true"></i> Transférer vers un autre camion ou chauffeur
          </a>
        {% endif %}

        {% if actions.annuler %}
          <div class="mt-4" x-data="{ ouvert: false }">
            <button type="button" @click="ouvert = !ouvert" :aria-expanded="ouvert.toString()" class="text-sm font-medium text-red-800 underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-red-700">Annuler la mission</button>
            <form method="post" action="{% url 'missions:annuler' mission.pk %}" x-show="ouvert" x-cloak class="mt-2 space-y-2"
                  data-confirm="Annuler définitivement cette mission ?">{% csrf_token %}
              <label for="motif-annulation" class="block text-xs font-medium text-slate-800">Motif <span class="text-red-700" aria-hidden="true">*</span></label>
              <textarea id="motif-annulation" name="motif" rows="2" required class="block w-full rounded-lg border border-slate-300 px-2 py-1 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30"></textarea>
              <button type="submit" class="rounded-lg border border-red-300 bg-white px-3 py-1 text-xs font-semibold text-red-800 hover:bg-red-50">Confirmer l'annulation</button>
            </form>
          </div>
        {% endif %}

        {% if mission.statut == "ANNULEE" %}
          <p class="mt-3 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-900">
            Annulée le {{ mission.date_annulation|date:"d/m/Y à H:i" }} : {{ mission.motif_annulation }}
          </p>
        {% endif %}

        {% if mission.transferts.all %}
          <div class="mt-4 text-sm">
            <h3 class="font-semibold text-slate-900">Transferts en route</h3>
            <ul class="mt-1 space-y-1 text-slate-700">
              {% for t in mission.transferts.all %}
                <li>{{ t.created_at|date:"d/m/Y H:i" }} : {{ t.ancien_vehicule.immatriculation }} → {{ t.nouveau_vehicule.immatriculation }}, {{ t.ancien_chauffeur }} → {{ t.nouveau_chauffeur }} ({{ t.motif }})</li>
              {% endfor %}
            </ul>
          </div>
        {% endif %}

        {% if not actions.planifier and not actions.affecter and not actions.demarrer and not actions.recuperation and not actions.livraison and not actions.cloturer and not actions.annuler and not actions.transferer %}
          <p class="mt-3 text-sm text-slate-700">Aucune action disponible pour votre rôle à cette étape.</p>
        {% endif %}
      </section>

      {% if codes.expediteur or codes.destinataire %}
        <section class="rounded-xl border border-amber-300 bg-amber-50 p-5 shadow-sm" aria-labelledby="titre-codes">
          <h2 id="titre-codes" class="text-base font-semibold text-amber-900"><i class="fa-solid fa-key mr-2" aria-hidden="true"></i>Codes à communiquer</h2>
          <p class="mt-1 text-xs text-amber-900">Confidentiels : à remettre uniquement à la personne concernée.</p>
          <a href="{% url 'missions:codes_pdf' mission.pk %}"
             class="mt-3 flex items-center justify-center gap-2 rounded-lg bg-amber-700 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-amber-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-700 focus-visible:ring-offset-2">
            <i class="fa-solid fa-file-pdf" aria-hidden="true"></i> Télécharger le PDF des codes
          </a>
          <p class="mt-1 text-center text-xs text-amber-900">Une page pour l'expéditeur, une pour le destinataire : à envoyer à chacun.</p>
          {% if codes.expediteur %}
            <div class="mt-4">
              <p class="text-sm text-amber-900">Expéditeur (récupération du colis)</p>
              <p class="mt-1 rounded-lg bg-white px-3 py-2 text-center font-mono text-xl font-bold tracking-widest text-slate-900">{{ codes.expediteur }}</p>
              <img src="{% url 'missions:qr' mission.pk 'expediteur' %}" alt="Code QR de l'expéditeur : {{ codes.expediteur }}" width="160" height="160" class="mx-auto mt-2 rounded-lg bg-white p-1">
              <p class="mt-1 text-center text-xs text-amber-900">Le chauffeur scanne ce QR avec l'espace mobile.</p>
            </div>
          {% endif %}
          {% if codes.destinataire %}
            <div class="mt-4">
              <p class="text-sm text-amber-900">Destinataire (confirmation de livraison)</p>
              <p class="mt-1 rounded-lg bg-white px-3 py-2 text-center font-mono text-xl font-bold tracking-widest text-slate-900">{{ codes.destinataire }}</p>
              <img src="{% url 'missions:qr' mission.pk 'destinataire' %}" alt="Code QR du destinataire : {{ codes.destinataire }}" width="160" height="160" class="mx-auto mt-2 rounded-lg bg-white p-1">
            </div>
          {% endif %}
        </section>
      {% endif %}
    </div>
  </div>
  </div>{# fin de la zone rafraîchie en direct #}
</div>
<script src="{% static 'js/suivi-missions.js' %}" defer></script>
{% endblock %}
```

C'est le gabarit le plus riche du projet : la **frise** (`{% for … %}` sur les statuts), la colonne des
**actions**, et le cadre des **codes à communiquer** avec leur QR. Les formulaires d'action portent
`data-confirm` pour demander confirmation avant de démarrer ou clôturer.

#### `apps/missions/templates/missions/_alerte_conge.html`

*14 lignes*

```django
{% load ui %}
<div role="alert" class="mt-4 rounded-lg border border-amber-400 bg-amber-50 p-4 text-sm text-amber-950">
  <p class="font-semibold"><i class="fa-solid fa-triangle-exclamation mr-2" aria-hidden="true"></i>Ce chauffeur a {{ section.contexte.missions|length }} mission{{ section.contexte.missions|length|pluralize }} prévue{{ section.contexte.missions|length|pluralize }} pendant cette période</p>
  <ul class="mt-2 space-y-1">
    {% for m in section.contexte.missions %}
      <li>
        {% if section.contexte.peut_ouvrir %}<a href="{% url 'missions:detail' m.pk %}" class="font-semibold underline underline-offset-2">{{ m.numero }}</a>{% else %}<strong>{{ m.numero }}</strong>{% endif %}
        · départ prévu le {{ m.date_depart_prevue|date:"d/m/Y" }} · {{ m.client }} · {{ m.lieu_chargement }} → {{ m.lieu_livraison }}
        · {% badge m.statut m.get_statut_display %}
      </li>
    {% endfor %}
  </ul>
  <p class="mt-2">Vérifiez avec l'exploitation que la mission peut être réaffectée avant de valider.</p>
</div>
```

#### `apps/missions/templates/missions/_missions_client.html`

*21 lignes*

```django
{% load ui humanize %}
<section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-missions-client">
  <div class="flex flex-wrap items-center justify-between gap-3">
    <h2 id="titre-missions-client" class="text-base font-semibold text-slate-900">Missions ({{ section.contexte.total }})</h2>
  </div>
  {% if section.contexte.missions %}
    <ul class="mt-4 divide-y divide-slate-100 text-sm">
      {% for m in section.contexte.missions %}
        <li class="flex flex-wrap items-center justify-between gap-2 py-2">
          <span>
            <a href="{% url 'missions:detail' m.pk %}" class="font-semibold text-marque-700 underline-offset-2 hover:underline">{{ m.numero }}</a>
            <span class="text-slate-700">· {{ m.lieu_chargement }} → {{ m.lieu_livraison }} · {{ m.prix_convenu|floatformat:0|intcomma }} FCFA</span>
          </span>
          {% badge m.statut m.get_statut_display %}
        </li>
      {% endfor %}
    </ul>
  {% else %}
    <p class="mt-3 text-sm text-slate-600">Aucune mission pour ce client.</p>
  {% endif %}
</section>
```

#### `static/js/suivi-missions.js`

*143 lignes*

```javascript
// Suivi des missions en direct : ouvre la WebSocket du serveur et rafraîchit l'écran dès qu'une mission
// change (par exemple quand le chauffeur saisit ou scanne un code depuis son téléphone).
//
// Aucun code n'est écrit dans les pages (CSP stricte) ; le gabarit déclare son intention :
//   <div data-suivi-missions data-ws-chemin="/ws/missions/suivi/" data-mission-id="12">
//       data-mission-id : ne réagit qu'aux changements de cette mission (fiche) ; absent : toute
//       mission (liste).
//   <div data-suivi-zone="nom">   zone remplacée par la même zone de la page rechargée
//   #suivi-voyant [data-etat=connecte|reconnexion|hors_ligne], #suivi-annonce (lecteurs d'écran),
//   #suivi-bandeau + #suivi-actualiser (changement arrivé pendant une saisie).
//
// Le message reçu ne contient que « quelle mission, quel statut » : les données, elles, sont relues par
// une requête ordinaire, avec les droits de l'utilisateur. Rien de secret ne transite par la WebSocket.
(function () {
  "use strict";

  var racine = document.querySelector("[data-suivi-missions]");
  if (!racine || !("WebSocket" in window)) {
    return;
  }

  var chemin = racine.getAttribute("data-ws-chemin");
  var missionId = racine.getAttribute("data-mission-id");
  var voyant = document.getElementById("suivi-voyant");
  var annonce = document.getElementById("suivi-annonce");
  var bandeau = document.getElementById("suivi-bandeau");
  var bouton = document.getElementById("suivi-actualiser");

  var delai = 1000;      // attente avant de se reconnecter, doublée à chaque échec (15 s au plus)
  var echecs = 0;        // échecs de connexion consécutifs avant la toute première ouverture
  var dejaOuverte = false;
  var minuterie = null;

  function montrerEtat(etat) {
    if (!voyant) {
      return;
    }
    var pastilles = voyant.querySelectorAll("[data-etat]");
    for (var i = 0; i < pastilles.length; i++) {
      pastilles[i].classList.toggle("hidden", pastilles[i].getAttribute("data-etat") !== etat);
    }
  }

  function saisieEnCours(zone) {
    var actif = document.activeElement;
    return !!actif && zone.contains(actif) && /^(INPUT|SELECT|TEXTAREA)$/.test(actif.tagName);
  }

  // Relit la page et remplace les zones ; une zone où l'on est en train de saisir est laissée telle
  // quelle (on ne perd pas une saisie) et un bandeau propose d'actualiser.
  function actualiser() {
    fetch(window.location.href, { credentials: "same-origin", headers: { "X-Requested-With": "suivi" } })
      .then(function (reponse) {
        if (!reponse.ok || reponse.redirected) {
          window.location.reload(); // session expirée, page disparue : on laisse le serveur décider
          return null;
        }
        return reponse.text();
      })
      .then(function (html) {
        if (html === null) {
          return;
        }
        var page = new DOMParser().parseFromString(html, "text/html");
        var occupee = false;
        var zones = document.querySelectorAll("[data-suivi-zone]");
        for (var i = 0; i < zones.length; i++) {
          var nouvelle = page.querySelector('[data-suivi-zone="' + zones[i].getAttribute("data-suivi-zone") + '"]');
          if (!nouvelle) {
            continue;
          }
          if (saisieEnCours(zones[i])) {
            occupee = true;
          } else {
            zones[i].replaceWith(nouvelle);
          }
        }
        if (bandeau) {
          bandeau.classList.toggle("hidden", !occupee);
        }
      })
      .catch(function () {
        /* réseau coupé : la reconnexion et l'actualisation qui suit rattraperont le retard */
      });
  }

  function planifierActualisation() {
    window.clearTimeout(minuterie);
    minuterie = window.setTimeout(actualiser, 250); // regroupe des changements rapprochés
  }

  function annoncer(mission) {
    if (annonce) {
      annonce.textContent = "Mission " + mission.numero + " : " + mission.statut_libelle + ".";
    }
  }

  function connecter() {
    var protocole = window.location.protocol === "https:" ? "wss://" : "ws://";
    var socket = new WebSocket(protocole + window.location.host + chemin);

    socket.onopen = function () {
      delai = 1000;
      echecs = 0;
      montrerEtat("connecte");
      if (dejaOuverte) {
        planifierActualisation(); // reconnecté : rattrape ce qui a changé pendant la coupure
      }
      dejaOuverte = true;
    };

    socket.onmessage = function (evenement) {
      var mission;
      try {
        mission = JSON.parse(evenement.data);
      } catch (erreur) {
        return;
      }
      if (missionId && String(mission.id) !== missionId) {
        return;
      }
      annoncer(mission);
      planifierActualisation();
    };

    socket.onclose = function () {
      if (!dejaOuverte && ++echecs >= 4) {
        montrerEtat("hors_ligne"); // refusée (droits, MFA) ou serveur sans WebSocket : inutile d'insister
        return;
      }
      montrerEtat("reconnexion");
      window.setTimeout(connecter, delai);
      delai = Math.min(delai * 2, 15000);
    };
  }

  if (bouton) {
    bouton.addEventListener("click", function () {
      window.location.reload();
    });
  }
  connecter();
})();
```

Le suivi en direct d'une mission (liste ou fiche) ouvre une **WebSocket** (`/ws/missions/suivi/`,
consommateur `apps.missions.temps_reel` du chapitre 10) : quand un chauffeur démarre, récupère ou livre
depuis son téléphone, la page se **rafraîchit toute seule**, sans rien recharger à la main. Comme pour
`app.js`, aucun code n'est écrit dans les pages (CSP stricte) : le gabarit déclare son intention avec
`data-suivi-missions`, et le message reçu ne contient que « quelle mission, quel statut » — les données
elles-mêmes sont relues par une requête ordinaire, avec les droits de l'utilisateur qui consulte la page.

## Étape 3 — Tests

#### `apps/missions/templates/missions/frais_detail.html`

*98 lignes*

```django
{% extends "base.html" %}
{% load ui humanize %}
{% block titre %}Frais de mission {{ mission.numero }}{% endblock %}
{% block entete %}Frais de mission{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-5xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'missions:frais_liste' %}" class="underline-offset-2 hover:underline">Frais de mission</a>
    <span aria-hidden="true">/</span> {{ mission.numero }}
  </nav>

  <div class="mt-2 flex flex-wrap items-center justify-between gap-3">
    <h1 class="text-2xl font-bold text-slate-900">Frais de mission {{ mission.numero }}</h1>
    <div class="flex items-center gap-2">
      <a href="{% url 'missions:detail' mission.pk %}" class="text-sm font-medium text-slate-700 underline-offset-2 hover:underline">Voir la mission</a>
      <a href="{% url 'missions:frais_imprimer' mission.pk %}" target="_blank" rel="noopener"
         class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50">
        <i class="fa-solid fa-print" aria-hidden="true"></i> Rapport de mission
      </a>
    </div>
  </div>
  <p class="mt-1 text-sm text-slate-600">{{ mission.client.raison_sociale }} · {{ mission.lieu_chargement }} → {{ mission.lieu_livraison }}</p>

  <dl class="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
    <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Sorties confirmées</dt><dd class="mt-1 text-2xl font-bold text-slate-900">{{ totaux.sorties|floatformat:0|intcomma }} <span class="text-sm font-medium text-slate-600">FCFA</span></dd></div>
    <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Encaissé</dt><dd class="mt-1 text-2xl font-bold text-slate-900">{{ totaux.encaisse|floatformat:0|intcomma }} <span class="text-sm font-medium text-slate-600">FCFA</span></dd></div>
    <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Solde</dt><dd class="mt-1 text-2xl font-bold {% if totaux.solde < 0 %}text-red-800{% else %}text-slate-900{% endif %}">{{ totaux.solde|floatformat:0|intcomma }} <span class="text-sm font-medium text-slate-600">FCFA</span></dd></div>
  </dl>

  {% if form_planifier %}
    <form method="post" action="{% url 'missions:frais_planifier' mission.pk %}" class="mt-5 space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      {% csrf_token %}
      <h2 class="text-sm font-semibold text-slate-900">Planifier une avance de route ou une dépense prévue</h2>
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {% include "components/_champ.html" with champ=form_planifier.type_frais %}
        {% include "components/_champ.html" with champ=form_planifier.montant %}
        {% include "components/_champ.html" with champ=form_planifier.description %}
      </div>
      <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700">Planifier</button>
    </form>
  {% endif %}

  {% if lignes %}
    <div class="mt-5 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <caption class="sr-only">Lignes de frais de la mission</caption>
        <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr>
            <th scope="col" class="px-4 py-3">Type</th>
            <th scope="col" class="px-4 py-3">Détail</th>
            <th scope="col" class="px-4 py-3 text-right">Montant</th>
            <th scope="col" class="px-4 py-3">Statut</th>
            <th scope="col" class="px-4 py-3"><span class="sr-only">Actions</span></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          {% for f in lignes %}
            <tr>
              <td class="whitespace-nowrap px-4 py-3 text-slate-900">{{ f.get_type_frais_display }}</td>
              <td class="px-4 py-3 text-slate-700">
                {% if f.type_frais == "IMPREVU" %}{{ f.chauffeur.personnel.prenom }} {{ f.chauffeur.personnel.nom }}{% else %}{{ f.saisi_par|default:"—" }}{% endif %}
                {% if f.description %}<span class="block text-xs text-slate-600">{{ f.description }}</span>{% endif %}
                {% if f.justificatif %}<a href="{{ f.justificatif.url }}" target="_blank" rel="noopener" class="text-xs font-medium text-marque-700 underline-offset-2 hover:underline">Voir la preuve</a>{% endif %}
                {% if f.statut == "REJETE" and f.motif_rejet %}<span class="block text-xs text-red-700">Motif : {{ f.motif_rejet }}</span>{% endif %}
              </td>
              <td class="whitespace-nowrap px-4 py-3 text-right font-medium text-slate-900">{{ f.montant|floatformat:0|intcomma }}</td>
              <td class="whitespace-nowrap px-4 py-3">{% badge f.statut f.get_statut_display %}</td>
              <td class="px-4 py-3">
                {% if f.attend_le_parc_auto and peut_valider_parcauto %}
                  <form method="post" action="{% url 'missions:frais_valider_parcauto' f.pk %}" class="inline">{% csrf_token %}<button type="submit" class="text-sm font-medium text-emerald-800 underline-offset-2 hover:underline">Valider</button></form>
                {% elif f.attend_la_finance and peut_valider_finances %}
                  <form method="post" action="{% url 'missions:frais_valider_finances' f.pk %}" class="inline">{% csrf_token %}<button type="submit" class="text-sm font-medium text-emerald-800 underline-offset-2 hover:underline">Confirmer</button></form>
                {% endif %}
                {% if f.statut == "PREVU" %}
                  {% if peut_valider_parcauto or peut_valider_finances %}
                    <span x-data="{ ouvert: false }" class="ml-2 inline">
                      <button type="button" @click="ouvert = !ouvert" class="text-sm font-medium text-red-800 underline-offset-2 hover:underline">Rejeter</button>
                      <form method="post" action="{% url 'missions:frais_rejeter' f.pk %}" x-show="ouvert" x-cloak class="mt-2 space-y-2 text-left">{% csrf_token %}
                        <textarea name="motif" rows="2" required placeholder="Motif du rejet" aria-label="Motif du rejet" class="block w-full rounded-lg border border-slate-300 px-2 py-1 text-xs"></textarea>
                        <button type="submit" class="rounded-lg border border-red-300 bg-white px-3 py-1 text-xs font-semibold text-red-800 hover:bg-red-50">Confirmer le rejet</button>
                      </form>
                    </span>
                  {% endif %}
                {% endif %}
              </td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  {% else %}
    <div class="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
      <p class="text-sm text-slate-600">Aucun frais de mission pour l'instant.</p>
    </div>
  {% endif %}
</div>
{% endblock %}
```

#### `apps/missions/templates/missions/frais_liste.html`

*54 lignes*

```django
{% extends "base.html" %}
{% load ui humanize %}
{% block titre %}Frais de mission{% endblock %}
{% block entete %}Frais de mission{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-6xl">
  <h1 class="text-2xl font-bold text-slate-900">Frais de mission</h1>
  <p class="mt-1 text-sm text-slate-600">Lignes en attente de validation, toutes missions confondues.</p>

  {% if lignes %}
    <div class="mt-5 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <caption class="sr-only">Frais de mission en attente</caption>
        <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr>
            <th scope="col" class="px-4 py-3">Mission</th>
            <th scope="col" class="px-4 py-3">Type</th>
            <th scope="col" class="px-4 py-3">Détail</th>
            <th scope="col" class="px-4 py-3 text-right">Montant</th>
            <th scope="col" class="px-4 py-3">Étape</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          {% for f in lignes %}
            <tr class="hover:bg-slate-50">
              <td class="whitespace-nowrap px-4 py-3 font-semibold"><a href="{% url 'missions:frais' f.mission_id %}" class="text-marque-700 underline-offset-2 hover:underline">{{ f.mission.numero }}</a></td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ f.get_type_frais_display }}</td>
              <td class="px-4 py-3 text-slate-700">
                {% if f.type_frais == "IMPREVU" %}{{ f.chauffeur.personnel.prenom }} {{ f.chauffeur.personnel.nom }}{% else %}{{ f.saisi_par|default:"—" }}{% endif %}
                {% if f.description %} · {{ f.description|truncatechars:60 }}{% endif %}
              </td>
              <td class="whitespace-nowrap px-4 py-3 text-right text-slate-900">{{ f.montant|floatformat:0|intcomma }}</td>
              <td class="whitespace-nowrap px-4 py-3">
                {% if f.attend_le_parc_auto %}
                  {% badge "PREVU" "Attend le Parc Auto" %}
                {% else %}
                  {% badge "PREVU" "Attend la Finance" %}
                {% endif %}
              </td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% include "components/_pagination.html" %}
  {% else %}
    <div class="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
      <span class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-600"><i class="fa-solid fa-money-bill-transfer" aria-hidden="true"></i></span>
      <p class="mt-3 font-semibold text-slate-900">Aucune ligne en attente</p>
    </div>
  {% endif %}
</div>
{% endblock %}
```

#### `apps/missions/templates/missions/frais_print.html`

*42 lignes*

```django
{% load humanize static %}<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Rapport de mission {{ mission.numero }}</title>
  {% include "rapports/_style_impression.html" %}
</head>
<body>
  {% include "rapports/_entete_impression.html" %}

  <p style="margin-top:1.5rem">
    <strong>{{ mission.client.raison_sociale }}</strong><br>
    <span class="petit">{{ mission.lieu_chargement }} → {{ mission.lieu_livraison }} ({{ mission.nature_marchandise }})</span>
  </p>

  <table>
    <thead><tr><th>Type</th><th>Détail</th><th>Statut</th><th class="droite">Montant</th></tr></thead>
    <tbody>
      {% for f in lignes %}
        <tr>
          <td>{{ f.get_type_frais_display }}</td>
          <td>{% if f.type_frais == "IMPREVU" %}{{ f.chauffeur.personnel.prenom }} {{ f.chauffeur.personnel.nom }}{% else %}{{ f.saisi_par|default:"—" }}{% endif %}{% if f.description %} · {{ f.description }}{% endif %}</td>
          <td>{{ f.get_statut_display }}</td>
          <td class="droite">{{ f.montant|floatformat:0|intcomma }}</td>
        </tr>
      {% empty %}
        <tr><td colspan="4">Aucun frais enregistré.</td></tr>
      {% endfor %}
    </tbody>
  </table>

  <div class="totaux" style="margin-left:auto;width:320px;margin-top:1rem">
    <div style="display:flex;justify-content:space-between;padding:.25rem 0"><span>Sorties confirmées</span><span>{{ totaux.sorties|floatformat:0|intcomma }} FCFA</span></div>
    <div style="display:flex;justify-content:space-between;padding:.25rem 0"><span>Encaissé confirmé</span><span>{{ totaux.encaisse|floatformat:0|intcomma }} FCFA</span></div>
    <div style="display:flex;justify-content:space-between;padding:.25rem 0;border-top:2px solid #111;font-weight:bold"><span>Solde</span><span>{{ totaux.solde|floatformat:0|intcomma }} FCFA</span></div>
  </div>

  {% include "rapports/_pied_impression.html" %}
  <script src="{% static 'js/app.js' %}" defer></script>
</body>
</html>
```

#### `apps/missions/templates/missions/mission_modifier.html`

*51 lignes*

```django
{% extends "base.html" %}
{% block titre %}Modifier {{ mission.numero }}{% endblock %}
{% block entete %}Missions{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-3xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'missions:liste' %}" class="underline-offset-2 hover:underline">Missions</a>
    <span aria-hidden="true">/</span>
    <a href="{% url 'missions:detail' mission.pk %}" class="underline-offset-2 hover:underline">{{ mission.numero }}</a>
    <span aria-hidden="true">/</span> Modifier
  </nav>
  <h1 class="mt-2 text-2xl font-bold text-slate-900">Modifier {{ mission.numero }}</h1>
  <p class="mt-1 text-sm text-slate-600">
    {{ mission.client.raison_sociale }} · possible tant que le colis n'est pas encore récupéré.
    {% if form.vehicule %}Changer le camion ou le chauffeur revérifie leur disponibilité.{% endif %}
    Changer un lieu régénère les deux codes secrets (l'ancien QR ne servira plus).
  </p>

  <datalist id="lieux-missions">{% for lieu in lieux %}<option value="{{ lieu }}"></option>{% endfor %}</datalist>

  <form method="post" novalidate class="mt-6 space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
    {% csrf_token %}
    {% if form.non_field_errors %}
      <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">
        {% for erreur in form.non_field_errors %}<p>{{ erreur }}</p>{% endfor %}
      </div>
    {% endif %}

    <div class="grid grid-cols-1 gap-5 sm:grid-cols-2">
      {% include "components/_champ.html" with champ=form.lieu_chargement %}
      {% include "components/_champ.html" with champ=form.lieu_livraison %}
      <div class="sm:col-span-2">{% include "components/_champ.html" with champ=form.nature_marchandise %}</div>
      {% include "components/_champ.html" with champ=form.poids_t %}
      {% include "components/_champ.html" with champ=form.prix_convenu %}
      <div class="sm:col-span-2">{% include "components/_champ.html" with champ=form.date_depart_prevue %}</div>
      {% if form.vehicule %}
        {% include "components/_champ.html" with champ=form.vehicule %}
        {% include "components/_champ.html" with champ=form.chauffeur %}
      {% endif %}
    </div>

    <div class="flex items-center justify-end gap-3 border-t border-slate-100 pt-5">
      <a href="{% url 'missions:detail' mission.pk %}" class="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">Annuler</a>
      <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
        Enregistrer les modifications
      </button>
    </div>
  </form>
</div>
{% endblock %}
```

#### `apps/missions/templates/missions/mission_transfert.html`

*38 lignes*

```django
{% extends "base.html" %}
{% block titre %}Transférer la mission {{ mission.numero }}{% endblock %}
{% block entete %}Missions{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-2xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'missions:liste' %}" class="underline-offset-2 hover:underline">Missions</a>
    <span aria-hidden="true">/</span>
    <a href="{% url 'missions:detail' mission.pk %}" class="underline-offset-2 hover:underline">{{ mission.numero }}</a>
    <span aria-hidden="true">/</span> Transférer
  </nav>
  <h1 class="mt-2 text-2xl font-bold text-slate-900">Transférer la mission {{ mission.numero }}</h1>
  <p class="mt-1 text-sm text-slate-600">
    En route : {{ mission.vehicule.immatriculation }}, chauffeur {{ mission.chauffeur }}. Choisissez le nouvel équipage
    (gardez le camion ou le chauffeur actuel s'il continue) ; la mission garde ses codes.
  </p>

  <form method="post" novalidate class="mt-6 space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
    {% csrf_token %}
    {% if form.non_field_errors %}
      <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">{% for erreur in form.non_field_errors %}<p>{{ erreur }}</p>{% endfor %}</div>
    {% endif %}
    {% include "components/_champ.html" with champ=form.vehicule %}
    {% include "components/_champ.html" with champ=form.chauffeur %}
    {% include "components/_champ.html" with champ=form.copilote %}
    <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {% include "components/_champ.html" with champ=form.km_ancien_vehicule %}
      {% include "components/_champ.html" with champ=form.statut_ancien_vehicule %}
    </div>
    {% include "components/_champ.html" with champ=form.motif %}
    <div class="flex items-center justify-end gap-3 border-t border-slate-100 pt-5">
      <a href="{% url 'missions:detail' mission.pk %}" class="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">Retour</a>
      <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Transférer</button>
    </div>
  </form>
</div>
{% endblock %}
```

#### `apps/customers/tests/test_views.py`

*444 lignes* — Écrans clients : accès par rôle, portefeuille, fiche, création, interactions.

```python
"""Écrans clients : accès par rôle, portefeuille, fiche, création, interactions."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client as HttpClient
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.customers import services
from apps.customers.models import Client, Interaction, TypeInteraction
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory
from apps.parametres import services as parametres_services

from .factories import ClientFactory

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    compte = UserFactory(role=role)
    client.force_login(compte)
    return compte


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _donnees(**surcharges):
    donnees = {
        "raison_sociale": "Cimaf CI",
        "ncc_nif": "CI-1234567A",
        "contact_principal": "Awa Coulibaly",
        "telephone": "+2250700000000",
        "email": "awa@cimaf.ci",
        "adresse": "Abidjan, Plateau",
        "charge_clientele": "",
        "taux_tva": "18",
        "motif_exoneration": "",
        "delai_paiement_jours": "30",
    }
    donnees.update(surcharges)
    return donnees


def _interaction(**surcharges):
    donnees = {
        "type_interaction": "APPEL",
        "date_interaction": (timezone.localtime() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
        "resume": "Point sur la livraison de mardi",
    }
    donnees.update(surcharges)
    return donnees


# --- accès ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE])
def test_les_clients_sont_accessibles_a_admin_direction_et_charge_clientele(client, role):
    _connecte(client, role)
    fiche = ClientFactory()

    assert client.get(reverse("customers:liste")).status_code == 200
    assert client.get(reverse("customers:detail", args=[fiche.pk])).status_code == 200


@pytest.mark.parametrize("role", [Role.RH, Role.PARCAUTO, Role.FINANCES, Role.CHAUFFEUR])
def test_les_clients_sont_interdits_aux_autres_roles(client, role):
    _connecte(client, role)
    fiche = ClientFactory()

    for url in (
        reverse("customers:liste"),
        reverse("customers:detail", args=[fiche.pk]),
        reverse("customers:creer"),
        reverse("customers:modifier", args=[fiche.pk]),
    ):
        assert client.get(url).status_code == 403, url


def test_la_direction_peut_desormais_modifier(client):
    """Retour réunion : la DIRECTION a la même largeur que l'ADMIN pour la saisie/modification."""
    _connecte(client, Role.DIRECTION)
    fiche = ClientFactory()

    assert client.get(reverse("customers:creer")).status_code == 200
    assert client.get(reverse("customers:modifier", args=[fiche.pk])).status_code == 200
    assert client.post(reverse("customers:interaction", args=[fiche.pk]), _interaction()).status_code != 403
    texte = client.get(reverse("customers:detail", args=[fiche.pk])).content.decode()
    assert "Modifier" in texte and "Ajouter une interaction" in texte


def test_les_clients_exigent_la_connexion(client):
    assert client.get(reverse("customers:liste")).status_code == 302


# --- liste ---


def test_la_liste_affiche_les_clients_et_filtre(client):
    charge = _connecte(client, Role.CHARGE_CLIENTELE)
    ClientFactory(raison_sociale="Cimaf", charge_clientele=charge)
    ClientFactory(raison_sociale="Solibra", taux_tva=Decimal("0"), motif_exoneration="ONG")

    tous = client.get(reverse("customers:liste"))
    recherche = client.get(reverse("customers:liste"), {"q": "soli"})
    portefeuille = client.get(reverse("customers:liste"), {"mes_clients": "on"})
    exonere = client.get(reverse("customers:liste"), {"exonere": "on"})

    assert len(tous.context["clients"]) == 2
    assert [c.raison_sociale for c in recherche.context["clients"]] == ["Solibra"]
    assert [c.raison_sociale for c in portefeuille.context["clients"]] == ["Cimaf"]
    assert [c.raison_sociale for c in exonere.context["clients"]] == ["Solibra"]
    assert "Mon portefeuille" in tous.content.decode()
    assert "Exonéré" in exonere.content.decode()


def test_le_filtre_portefeuille_n_est_propose_qu_au_charge_clientele(client):
    _connecte(client, Role.DIRECTION)

    assert "Mon portefeuille" not in client.get(reverse("customers:liste")).content.decode()


def test_la_liste_vide_invite_a_creer_un_client(client):
    _connecte(client, Role.CHARGE_CLIENTELE)

    texte = client.get(reverse("customers:liste")).content.decode()

    assert "Créez la fiche du premier client" in texte


def test_la_liste_signale_les_reclamations(client):
    auteur = _connecte(client, Role.CHARGE_CLIENTELE)
    fiche = ClientFactory()
    services.enregistrer_interaction(
        fiche, auteur, type_interaction=TypeInteraction.RECLAMATION, resume="Retard"
    )

    reponse = client.get(reverse("customers:liste"))

    assert reponse.context["clients"][0].nb_reclamations == 1


def test_la_liste_des_clients_reste_a_requetes_constantes(client, django_assert_max_num_queries):
    auteur = _connecte(client, Role.CHARGE_CLIENTELE)
    for _ in range(12):
        fiche = ClientFactory(charge_clientele=auteur)
        services.enregistrer_interaction(fiche, auteur, type_interaction=TypeInteraction.MAIL, resume="x")

    with django_assert_max_num_queries(8):
        assert client.get(reverse("customers:liste")).status_code == 200


# --- fiche ---


def test_la_fiche_affiche_les_informations_et_l_historique(client):
    auteur = _connecte(client, Role.CHARGE_CLIENTELE)
    fiche = ClientFactory(raison_sociale="Cimaf CI", taux_tva=Decimal("0"), motif_exoneration="ONG")
    services.enregistrer_interaction(
        fiche, auteur, type_interaction=TypeInteraction.REUNION, resume="Réunion de cadrage"
    )

    texte = client.get(reverse("customers:detail", args=[fiche.pk])).content.decode()

    assert "Cimaf CI" in texte and "Exonéré : ONG" in texte
    assert "Réunion de cadrage" in texte and "Historique commercial (1)" in texte


def test_la_fiche_liste_les_missions_du_client(client):
    _connecte(client, Role.DIRECTION)
    fiche = ClientFactory()
    mission = MissionFactory(client=fiche, statut=StatutMission.PLANIFIEE)
    MissionFactory(client=ClientFactory())  # mission d'un autre client

    texte = client.get(reverse("customers:detail", args=[fiche.pk])).content.decode()

    assert "Missions (1)" in texte and mission.numero in texte


def test_les_textes_saisis_sont_echappes(client):
    auteur = _connecte(client, Role.CHARGE_CLIENTELE)
    fiche = ClientFactory(raison_sociale="<script>alert(1)</script>")
    services.enregistrer_interaction(
        fiche, auteur, type_interaction=TypeInteraction.MAIL, resume="<img src=x onerror=alert(2)>"
    )

    texte = client.get(reverse("customers:detail", args=[fiche.pk])).content.decode()

    assert "<script>alert(1)</script>" not in texte
    assert "<img src=x" not in texte
    assert "&lt;img src=x onerror=alert(2)&gt;" in texte


def test_un_client_inexistant_donne_404(client):
    _connecte(client, Role.ADMIN)

    assert client.get(reverse("customers:detail", args=[999])).status_code == 404


# --- création et modification ---


def test_le_charge_clientele_cree_un_client(client):
    charge = _connecte(client, Role.CHARGE_CLIENTELE)

    reponse = client.post(
        reverse("customers:creer"), _donnees(charge_clientele=charge.pk), follow=True
    )

    fiche = Client.objects.get(ncc_nif="CI-1234567A")
    assert fiche.charge_clientele == charge and fiche.taux_tva == Decimal("18")
    assert reponse.redirect_chain[-1][0] == reverse("customers:detail", args=[fiche.pk])
    assert any("Cimaf CI" in m for m in _messages(reponse))


def test_creation_d_un_client_exonere_sans_motif_est_refusee(client):
    _connecte(client, Role.ADMIN)

    reponse = client.post(reverse("customers:creer"), _donnees(taux_tva="0"))

    assert reponse.status_code == 200
    assert "Motif obligatoire" in reponse.content.decode()
    assert not Client.objects.exists()


def test_creation_d_un_client_exonere_avec_motif(client):
    _connecte(client, Role.ADMIN)

    client.post(reverse("customers:creer"), _donnees(taux_tva="0", motif_exoneration="EXPORT"))

    assert Client.objects.get().motif_exoneration == "EXPORT"


def test_un_nif_deja_utilise_est_signale(client):
    _connecte(client, Role.ADMIN)
    ClientFactory(ncc_nif="CI-1234567A")

    reponse = client.post(reverse("customers:creer"), _donnees())

    assert "déjà utilisé" in reponse.content.decode()
    assert Client.objects.count() == 1


def test_le_formulaire_ne_propose_que_les_charges_clientele_actifs(client):
    _connecte(client, Role.ADMIN)
    bon = UserFactory(role=Role.CHARGE_CLIENTELE)
    autre = UserFactory(role=Role.FINANCES)

    propositions = set(
        client.get(reverse("customers:creer")).context["form"].fields["charge_clientele"].queryset
    )

    assert bon in propositions and autre not in propositions


def test_la_modification_met_a_jour_la_fiche(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    fiche = ClientFactory(ncc_nif="CI-0000001A")

    reponse = client.post(
        reverse("customers:modifier", args=[fiche.pk]),
        _donnees(ncc_nif="CI-0000001A", telephone="+2250101010101"),
        follow=True,
    )

    fiche.refresh_from_db()
    assert fiche.telephone == "+2250101010101" and fiche.raison_sociale == "Cimaf CI"
    assert any("mise à jour" in m for m in _messages(reponse))


def test_le_formulaire_de_modification_est_prerempli(client):
    _connecte(client, Role.ADMIN)
    fiche = ClientFactory(raison_sociale="Solibra")

    reponse = client.get(reverse("customers:modifier", args=[fiche.pk]))

    assert reponse.context["form"].initial["raison_sociale"] == "Solibra"


def test_le_formulaire_de_modification_conserve_la_tva_a_zero_d_un_client_exonere(client):
    # Audit M4-09 : ``|default:'18'`` prenait 0,00 pour une valeur vide et remettait 18 %.
    _connecte(client, Role.ADMIN)
    fiche = ClientFactory(taux_tva=Decimal("0.00"), motif_exoneration="ONG")

    page = client.get(reverse("customers:modifier", args=[fiche.pk])).content.decode()

    assert 'name="taux_tva"' in page
    assert 'value="0.00"' in page
    assert 'value="18' not in page


def test_le_formulaire_de_creation_propose_18_pourcent(client):
    _connecte(client, Role.ADMIN)

    page = client.get(reverse("customers:creer")).content.decode()

    assert 'value="18.00"' in page


def test_la_creation_exige_le_csrf():
    http = HttpClient(enforce_csrf_checks=True)
    http.force_login(UserFactory(role=Role.ADMIN))

    assert http.post(reverse("customers:creer"), _donnees()).status_code == 403


# --- interactions ---


def test_le_charge_clientele_ajoute_une_interaction(client):
    auteur = _connecte(client, Role.CHARGE_CLIENTELE)
    fiche = ClientFactory()

    reponse = client.post(reverse("customers:interaction", args=[fiche.pk]), _interaction(), follow=True)

    interaction = Interaction.objects.get()
    assert interaction.auteur == auteur and interaction.client == fiche
    assert any("ajoutée" in m for m in _messages(reponse))
    assert "Point sur la livraison de mardi" in reponse.content.decode()


def test_une_interaction_sans_resume_est_refusee(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    fiche = ClientFactory()

    reponse = client.post(
        reverse("customers:interaction", args=[fiche.pk]), _interaction(resume=""), follow=True
    )

    assert not Interaction.objects.exists()
    assert _messages(reponse)


def test_une_interaction_dans_le_futur_est_refusee(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    fiche = ClientFactory()
    demain = (timezone.localtime() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")

    reponse = client.post(
        reverse("customers:interaction", args=[fiche.pk]),
        _interaction(date_interaction=demain),
        follow=True,
    )

    assert not Interaction.objects.exists()
    assert any("futur" in m for m in _messages(reponse))


def test_l_interaction_n_accepte_que_post_et_exige_le_csrf():
    http = HttpClient(enforce_csrf_checks=True)
    http.force_login(UserFactory(role=Role.CHARGE_CLIENTELE))
    fiche = ClientFactory()
    url = reverse("customers:interaction", args=[fiche.pk])

    assert http.get(url).status_code == 405
    assert http.post(url, _interaction()).status_code == 403


def test_la_modification_refuse_le_nif_d_un_autre_client(client):
    _connecte(client, Role.ADMIN)
    ClientFactory(ncc_nif="CI-0000009A")
    fiche = ClientFactory(ncc_nif="CI-0000001A")

    reponse = client.post(
        reverse("customers:modifier", args=[fiche.pk]), _donnees(ncc_nif="CI-0000009A")
    )

    assert "déjà utilisé" in reponse.content.decode()
    fiche.refresh_from_db()
    assert fiche.ncc_nif == "CI-0000001A"


def test_le_delai_de_paiement_se_saisit_et_s_affiche(client):
    _connecte(client, Role.ADMIN)

    reponse = client.post(
        reverse("customers:creer"), _donnees(delai_paiement_jours="45"), follow=True
    )

    fiche = Client.objects.get(ncc_nif="CI-1234567A")
    assert fiche.delai_paiement_jours == 45
    assert "45 jours" in reponse.content.decode()


def test_le_delai_de_paiement_doit_etre_entre_1_et_365_jours(client):
    _connecte(client, Role.ADMIN)

    for valeur in ("0", "366", "abc"):
        reponse = client.post(reverse("customers:creer"), _donnees(delai_paiement_jours=valeur))
        assert reponse.status_code == 200, valeur
    assert not Client.objects.exists()


# --- chargé attitré désactivé (audit M4-05) ---


def test_modifier_un_client_dont_le_charge_a_ete_desactive_le_conserve(client):
    charge = UserFactory(role=Role.CHARGE_CLIENTELE)
    fiche = ClientFactory(raison_sociale="Cimaf", ncc_nif="CI-1", charge_clientele=charge)
    charge.is_active = False
    charge.save()
    _connecte(client, Role.DIRECTION)

    page = client.get(reverse("customers:modifier", args=[fiche.pk])).content.decode()
    assert f'value="{charge.pk}" selected' in page  # toujours proposé, et sélectionné

    reponse = client.post(
        reverse("customers:modifier", args=[fiche.pk]),
        _donnees(raison_sociale="Cimaf CI", ncc_nif="CI-1", charge_clientele=charge.pk),
        follow=True,
    )

    fiche.refresh_from_db()
    assert fiche.raison_sociale == "Cimaf CI" and fiche.charge_clientele_id == charge.pk  # plus remplacé par « aucun »


def test_un_nouveau_charge_desactive_reste_refuse(client):
    inactif = UserFactory(role=Role.CHARGE_CLIENTELE, is_active=False)
    fiche = ClientFactory(ncc_nif="CI-2")
    _connecte(client, Role.DIRECTION)

    client.post(reverse("customers:modifier", args=[fiche.pk]), _donnees(ncc_nif="CI-2", charge_clientele=inactif.pk))

    fiche.refresh_from_db()
    assert fiche.charge_clientele_id is None


def test_le_formulaire_de_creation_propose_la_tva_et_le_delai_des_parametres(client):
    parametres_services.modifier_parametres(
        UserFactory(role=Role.ADMIN), tva_defaut=Decimal("9.5"), delai_paiement_defaut_jours=45
    )
    _connecte(client, Role.ADMIN)

    page = client.get(reverse("customers:creer")).content.decode()

    assert 'value="9.50"' in page and "9,50 % par défaut" in page
    assert 'name="delai_paiement_jours" value="45"' in page
```

#### `apps/drivers/tests/test_views.py`

*366 lignes* — Écrans des chauffeurs : accès par rôle, liste, fiche, modification, statut.

```python
"""Écrans des chauffeurs : accès par rôle, liste, fiche, modification, statut."""

from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.models import StatutChauffeur
from apps.parametres import services as parametres_services

from .factories import ChauffeurFactory, chauffeur_sans_permis

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    utilisateur = UserFactory(role=role)
    client.force_login(utilisateur)
    return utilisateur


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _donnees(**surcharges):
    donnees = {
        "telephone": "+2250701020304",
        "contact_urgence": "Awa - 0700000000",
        "numero_permis": "PC-555",
        "categories_permis": ["C", "E"],
        "date_expiration_permis": "2029-05-01",
        "date_expiration_visite_medicale": "2027-05-01",
    }
    donnees.update(surcharges)
    return donnees


# --- accès par rôle ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.RH])
def test_les_chauffeurs_sont_accessibles_a_la_direction_a_la_rh_et_a_l_admin(client, role):
    _connecte(client, role)

    assert client.get(reverse("drivers:liste")).status_code == 200


@pytest.mark.parametrize(
    "role", [Role.PARCAUTO, Role.FINANCES, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR]
)
def test_les_chauffeurs_sont_interdits_aux_autres_roles(client, role):
    _connecte(client, role)
    fiche = ChauffeurFactory()

    assert client.get(reverse("drivers:liste")).status_code == 403
    assert client.get(reverse("drivers:detail", args=[fiche.pk])).status_code == 403
    assert client.get(reverse("drivers:modifier", args=[fiche.pk])).status_code == 403
    assert client.post(reverse("drivers:statut", args=[fiche.pk]), {"statut": "SUSPENDU"}).status_code == 403
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE


def test_un_visiteur_non_connecte_est_renvoye_vers_la_connexion(client):
    reponse = client.get(reverse("drivers:liste"))

    assert reponse.status_code == 302
    assert reponse.url.startswith(reverse("accounts:login"))


def test_le_menu_chauffeurs_est_visible_de_la_rh_mais_pas_du_parc_auto(client):
    _connecte(client, Role.RH)
    assert 'href="/chauffeurs/"' in client.get(reverse("home")).content.decode()

    autre = Client()
    _connecte(autre, Role.PARCAUTO)
    assert 'href="/chauffeurs/"' not in autre.get(reverse("home")).content.decode()


# --- liste ---


def test_la_liste_affiche_les_chauffeurs_avec_leur_statut(client):
    _connecte(client, Role.DIRECTION)
    ChauffeurFactory(personnel__nom="Traoré", personnel__prenom="Moussa", telephone="0700112233")

    contenu = client.get(reverse("drivers:liste")).content.decode()

    assert "Moussa Traoré" in contenu
    assert "0700112233" in contenu
    assert "Disponible" in contenu


def test_la_liste_vide_affiche_un_message(client):
    _connecte(client, Role.DIRECTION)

    assert "Aucun chauffeur trouvé" in client.get(reverse("drivers:liste")).content.decode()


def test_la_liste_filtre_par_statut_et_recherche(client):
    _connecte(client, Role.RH)
    libre = ChauffeurFactory(personnel__nom="Adou")
    ChauffeurFactory(personnel__nom="Bamba", statut=StatutChauffeur.SUSPENDU)

    par_statut = client.get(reverse("drivers:liste"), {"statut": "DISPONIBLE"})
    par_texte = client.get(reverse("drivers:liste"), {"q": "adou"})

    assert [l["chauffeur"] for l in par_statut.context["lignes"]] == [libre]
    assert [l["chauffeur"] for l in par_texte.context["lignes"]] == [libre]


def test_la_liste_signale_et_filtre_les_echeances_proches(client):
    _connecte(client, Role.DIRECTION)
    aujourdhui = timezone.localdate()
    alerte = ChauffeurFactory(
        personnel__nom="Alerte", date_expiration_permis=aujourdhui + timedelta(days=10)
    )
    ChauffeurFactory(
        personnel__nom="Tranquille",
        date_expiration_permis=aujourdhui + timedelta(days=900),
        date_expiration_visite_medicale=aujourdhui + timedelta(days=900),
    )

    complet = client.get(reverse("drivers:liste"))
    filtre = client.get(reverse("drivers:liste"), {"alerte": "1"})

    assert "À renouveler" in complet.content.decode()
    assert [l["chauffeur"] for l in filtre.context["lignes"]] == [alerte]


def test_la_liste_est_paginee_par_20(client):
    _connecte(client, Role.DIRECTION)
    for _ in range(21):
        ChauffeurFactory()

    page2 = client.get(reverse("drivers:liste"), {"page": 2})

    assert len(page2.context["lignes"]) == 1


def test_la_liste_n_effectue_pas_une_requete_par_chauffeur(client, django_assert_max_num_queries):
    _connecte(client, Role.DIRECTION)
    for _ in range(15):
        ChauffeurFactory()

    with django_assert_max_num_queries(10):
        client.get(reverse("drivers:liste"))


def test_les_donnees_saisies_sont_echappees_contre_le_xss(client):
    _connecte(client, Role.DIRECTION)
    # Charge utile courte : `telephone` fait max_length=20 (apps/drivers/models.py), une contrainte
    # que PostgreSQL applique réellement (SQLite l'aurait acceptée sans erreur).
    ChauffeurFactory(telephone="<script>x</script>")

    contenu = client.get(reverse("drivers:liste")).content.decode()

    assert "<script>x</script>" not in contenu
    assert "&lt;script&gt;" in contenu


# --- fiche ---


def test_la_fiche_affiche_l_identite_les_contacts_et_les_echeances(client):
    _connecte(client, Role.DIRECTION)
    aujourdhui = timezone.localdate()
    fiche = ChauffeurFactory(
        personnel__nom="Traoré",
        personnel__prenom="Moussa",
        personnel__matricule="CH-007",
        telephone="0700112233",
        contact_urgence="Fatou 0701",
        numero_permis="PC-42",
        categories_permis=["C", "E"],
        date_expiration_permis=aujourdhui - timedelta(days=5),
        date_expiration_visite_medicale=aujourdhui + timedelta(days=12),
    )

    reponse = client.get(reverse("drivers:detail", args=[fiche.pk]))
    contenu = reponse.content.decode()

    for attendu in ("Moussa Traoré", "CH-007", "0700112233", "Fatou 0701", "PC-42", "C, E"):
        assert attendu in contenu, attendu
    assert "Expiré" in contenu and "depuis 5 j" in contenu
    assert "À renouveler" in contenu and "dans 12 j" in contenu


def test_la_fiche_signale_les_informations_manquantes(client):
    _connecte(client, Role.DIRECTION)
    fiche = chauffeur_sans_permis()

    contenu = client.get(reverse("drivers:detail", args=[fiche.pk])).content.decode()

    assert "Non renseigné" in contenu and "Non renseignées" in contenu


def test_la_fiche_d_un_chauffeur_inconnu_est_introuvable(client):
    _connecte(client, Role.DIRECTION)

    assert client.get(reverse("drivers:detail", args=[999999])).status_code == 404


def test_la_fiche_propose_le_changement_de_statut_sauf_en_mission_ou_en_conge(client):
    _connecte(client, Role.DIRECTION)
    libre = ChauffeurFactory()
    en_mission = ChauffeurFactory(statut=StatutChauffeur.EN_MISSION)

    page_libre = client.get(reverse("drivers:detail", args=[libre.pk])).content.decode()
    page_mission = client.get(reverse("drivers:detail", args=[en_mission.pk])).content.decode()

    assert reverse("drivers:statut", args=[libre.pk]) in page_libre
    assert reverse("drivers:statut", args=[en_mission.pk]) not in page_mission
    assert "géré automatiquement" in page_mission


# --- modification ---


def test_le_formulaire_de_modification_est_prerempli(client):
    _connecte(client, Role.RH)
    fiche = ChauffeurFactory(telephone="0700112233", categories_permis=["C"])

    reponse = client.get(reverse("drivers:modifier", args=[fiche.pk]))

    assert reponse.context["form"].initial["telephone"] == "0700112233"
    assert reponse.context["form"].initial["categories_permis"] == ["C"]
    assert fiche.personnel.matricule in reponse.content.decode()


def test_modifier_une_fiche(client):
    _connecte(client, Role.RH)
    fiche = ChauffeurFactory()

    reponse = client.post(reverse("drivers:modifier", args=[fiche.pk]), _donnees(), follow=True)

    fiche.refresh_from_db()
    assert reponse.redirect_chain[-1][0] == reverse("drivers:detail", args=[fiche.pk])
    assert fiche.numero_permis == "PC-555"
    assert fiche.categories_permis == ["C", "E"]
    assert str(fiche.date_expiration_permis) == "2029-05-01"
    assert any("mise à jour" in m for m in _messages(reponse))


def test_modifier_avec_une_categorie_inconnue_est_refuse_par_le_formulaire(client):
    _connecte(client, Role.RH)
    fiche = chauffeur_sans_permis()

    reponse = client.post(
        reverse("drivers:modifier", args=[fiche.pk]), _donnees(categories_permis=["C", "Z"])
    )

    fiche.refresh_from_db()
    assert reponse.status_code == 200
    assert reponse.context["form"].errors
    assert fiche.categories_permis == []


def test_modifier_avec_une_date_invalide_est_refuse(client):
    _connecte(client, Role.RH)
    fiche = chauffeur_sans_permis()

    reponse = client.post(
        reverse("drivers:modifier", args=[fiche.pk]), _donnees(date_expiration_permis="31/02/2029")
    )

    assert reponse.context["form"].errors
    fiche.refresh_from_db()
    assert fiche.numero_permis == ""


def test_modifier_un_chauffeur_inconnu_est_introuvable(client):
    _connecte(client, Role.RH)

    assert client.get(reverse("drivers:modifier", args=[999999])).status_code == 404


# --- statut ---


def test_suspendre_puis_reactiver_un_chauffeur(client):
    _connecte(client, Role.DIRECTION)
    fiche = ChauffeurFactory()

    reponse = client.post(reverse("drivers:statut", args=[fiche.pk]), {"statut": "SUSPENDU"}, follow=True)
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.SUSPENDU
    assert any("Suspendu" in m for m in _messages(reponse))

    client.post(reverse("drivers:statut", args=[fiche.pk]), {"statut": "DISPONIBLE"})
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE


def test_changer_le_statut_d_un_chauffeur_en_mission_est_refuse(client):
    _connecte(client, Role.DIRECTION)
    fiche = ChauffeurFactory(statut=StatutChauffeur.EN_MISSION)

    reponse = client.post(reverse("drivers:statut", args=[fiche.pk]), {"statut": "SUSPENDU"}, follow=True)

    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.EN_MISSION
    assert any("missions et les congés" in m for m in _messages(reponse))


@pytest.mark.parametrize("cible", ["EN_MISSION", "EN_CONGE", "VOLANT", ""])
def test_un_statut_non_manuel_est_refuse_par_le_formulaire(client, cible):
    _connecte(client, Role.DIRECTION)
    fiche = ChauffeurFactory()

    client.post(reverse("drivers:statut", args=[fiche.pk]), {"statut": cible})

    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE


def test_le_changement_de_statut_refuse_le_get(client):
    _connecte(client, Role.DIRECTION)
    fiche = ChauffeurFactory()

    assert client.get(reverse("drivers:statut", args=[fiche.pk])).status_code == 405


def test_un_chauffeur_suspendu_ne_peut_plus_etre_affecte_a_une_mission():
    """Lien avec les missions : l'affectation exige un chauffeur « Disponible »."""
    from apps.fleet.tests.factories import VehiculeEnRegleFactory
    from apps.missions import services as missions_services
    from apps.missions.exceptions import AffectationImpossible
    from apps.missions.tests.test_services import _planifiee
    from apps.drivers import services

    fiche = ChauffeurFactory()
    services.changer_statut_manuel(fiche, StatutChauffeur.SUSPENDU)

    with pytest.raises(AffectationImpossible, match="chauffeur"):
        missions_services.affecter_mission(
            _planifiee(), vehicule=VehiculeEnRegleFactory(), chauffeur=fiche
        )


def test_les_formulaires_des_chauffeurs_sont_proteges_par_csrf():
    client = Client(enforce_csrf_checks=True)
    client.force_login(UserFactory(role=Role.DIRECTION))
    fiche = chauffeur_sans_permis()

    assert client.post(reverse("drivers:modifier", args=[fiche.pk]), _donnees()).status_code == 403
    assert client.post(reverse("drivers:statut", args=[fiche.pk]), {"statut": "SUSPENDU"}).status_code == 403
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE and fiche.numero_permis == ""


def test_la_fiche_et_la_liste_appliquent_le_delai_d_alerte_des_parametres(client):
    parametres_services.modifier_parametres(UserFactory(role=Role.ADMIN), delai_alerte_jours=60)
    chauffeur = ChauffeurFactory(date_expiration_permis=timezone.localdate() + timedelta(days=45))
    _connecte(client, Role.RH)

    fiche = client.get(reverse("drivers:detail", args=[chauffeur.pk]))
    liste = client.get(reverse("drivers:liste"))

    assert "Une alerte apparaît 60 jours avant l'expiration." in fiche.content.decode()
    assert fiche.context["echeances"][0]["etat"] == "A_RENOUVELER"
    assert liste.context["lignes"][0]["echeances"][0]["etat"] == "A_RENOUVELER"
```

#### `apps/missions/tests/test_alerte_conge.py`

*155 lignes* — Alerte N1 : le chauffeur qui demande un congé a une mission prévue sur la période.

```python
"""Alerte N1 : le chauffeur qui demande un congé a une mission prévue sur la période.

Cahier-des-charges.md:219-221. Bloc fourni par ``missions`` à la fiche d'un congé.
"""

from datetime import date, datetime
from datetime import timezone as dt_timezone

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.hr import services
from apps.hr.tests.factories import PersonnelFactory
from apps.missions.models import StatutMission

from .factories import MissionFactory

pytestmark = pytest.mark.django_db

MAINTENANT = datetime(2026, 9, 1, 8, 0, tzinfo=dt_timezone.utc)
DEBUT, FIN = date(2026, 10, 5), date(2026, 10, 9)


@pytest.fixture
def cas():
    compte_sup = UserFactory(role=Role.PARCAUTO)
    superieur = PersonnelFactory(utilisateur=compte_sup)
    fiche = ChauffeurFactory(personnel=PersonnelFactory(poste="Chauffeur", superieur=superieur))
    conge = services.demander_conge(
        fiche.personnel, date_debut=DEBUT, date_fin=FIN, motif="Repos", maintenant=MAINTENANT
    )
    return conge, fiche, compte_sup


def _page(client, compte, conge):
    client.force_login(compte)
    return client.get(reverse("hr:conges_detail", args=[conge.pk])).content.decode()


def test_le_validateur_est_prevenu_d_une_mission_sur_la_periode(client, cas):
    conge, fiche, compte_sup = cas
    mission = MissionFactory(
        chauffeur=fiche, statut=StatutMission.PLANIFIEE, date_depart_prevue=date(2026, 10, 7)
    )

    texte = _page(client, compte_sup, conge)

    assert "1 mission prévue pendant cette période" in texte
    assert mission.numero in texte


def test_le_lien_vers_la_mission_est_reserve_aux_roles_qui_y_ont_acces(client, cas):
    conge, fiche, compte_sup = cas
    mission = MissionFactory(
        chauffeur=fiche, statut=StatutMission.PLANIFIEE, date_depart_prevue=date(2026, 10, 7)
    )
    lien = reverse("missions:detail", args=[mission.pk])

    # Retour réunion : le Parc Auto affecte les missions, donc les consulte désormais aussi.
    assert lien in _page(client, compte_sup, conge)
    assert lien in _page(client, UserFactory(role=Role.DIRECTION), conge)
    assert lien not in _page(client, UserFactory(role=Role.RH), conge)


@pytest.mark.parametrize(
    "surcharges",
    [
        {"date_depart_prevue": date(2026, 10, 12)},  # après la période
        {"date_depart_prevue": date(2026, 10, 2)},  # avant la période
        {"date_depart_prevue": None},  # pas de date : non détectable
        {"date_depart_prevue": date(2026, 10, 7), "statut": StatutMission.CLOTUREE},
        {"date_depart_prevue": date(2026, 10, 7), "statut": StatutMission.BROUILLON},
    ],
)
def test_aucune_alerte_hors_periode_ou_hors_mission_active(client, cas, surcharges):
    conge, fiche, compte_sup = cas
    donnees = {"statut": StatutMission.PLANIFIEE, **surcharges}
    if donnees["statut"] == StatutMission.CLOTUREE:
        donnees["vehicule"] = VehiculeFactory()  # une mission clôturée a un camion
    MissionFactory(chauffeur=fiche, **donnees)

    assert "mission prévue" not in _page(client, compte_sup, conge)


def test_la_mission_d_un_autre_chauffeur_ne_declenche_pas_d_alerte(client, cas):
    conge, fiche, compte_sup = cas
    autre = ChauffeurFactory()
    MissionFactory(
        chauffeur=autre, statut=StatutMission.PLANIFIEE, date_depart_prevue=date(2026, 10, 7)
    )

    assert "mission prévue" not in _page(client, compte_sup, conge)


def test_plus_d_alerte_une_fois_le_conge_decide(client, cas):
    conge, fiche, compte_sup = cas
    MissionFactory(
        chauffeur=fiche, statut=StatutMission.PLANIFIEE, date_depart_prevue=date(2026, 10, 7)
    )
    services.refuser(conge, compte_sup, commentaire="Mission prévue")

    assert "mission prévue pendant" not in _page(client, compte_sup, conge)


def test_la_section_missions_du_client_est_reservee_aux_roles_des_missions():
    from apps.customers.tests.factories import ClientFactory
    from apps.missions import sections

    fiche = ClientFactory()

    assert sections.section_missions_client(fiche, UserFactory(role=Role.RH)) is None
    assert sections.section_missions_client(fiche, UserFactory(role=Role.DIRECTION)) is not None


# --- chevauchement et copilote (audit M11-06) ---


def test_une_mission_deja_en_cours_qui_deborde_sur_le_conge_declenche_l_alerte(client, cas):
    conge, fiche, compte_sup = cas
    MissionFactory(
        chauffeur=fiche, statut=StatutMission.EN_COURS_COLIS_RECUPERE, vehicule=VehiculeFactory(),
        date_depart_prevue=date(2026, 10, 1), date_depart=datetime(2026, 10, 1, 7, 0, tzinfo=dt_timezone.utc),
    )

    assert "1 mission prévue pendant cette période" in _page(client, compte_sup, conge)


def test_une_mission_en_cours_partie_apres_la_fin_du_conge_ne_declenche_pas_d_alerte(client, cas):
    conge, fiche, compte_sup = cas
    MissionFactory(
        chauffeur=fiche, statut=StatutMission.EN_COURS_DEPART, vehicule=VehiculeFactory(),
        date_depart_prevue=date(2026, 10, 12), date_depart=datetime(2026, 10, 12, 7, 0, tzinfo=dt_timezone.utc),
    )

    assert "mission prévue" not in _page(client, compte_sup, conge)


def test_le_copilote_en_conge_est_prevenu_comme_le_chauffeur(client):
    from apps.drivers.models import Copilote

    compte_sup = UserFactory(role=Role.PARCAUTO)
    superieur = PersonnelFactory(utilisateur=compte_sup)
    personnel = PersonnelFactory(poste="Copilote", superieur=superieur)
    copilote = Copilote.objects.get(personnel=personnel)
    conge = services.demander_conge(personnel, date_debut=DEBUT, date_fin=FIN, motif="Repos", maintenant=MAINTENANT)
    MissionFactory(
        chauffeur=ChauffeurFactory(), copilote=copilote, statut=StatutMission.PLANIFIEE,
        date_depart_prevue=date(2026, 10, 7),
    )

    assert "1 mission prévue pendant cette période" in _page(client, compte_sup, conge)
```

#### `apps/missions/tests/test_documents.py`

*127 lignes* — PDF des codes d'une mission : une page par partie, jamais un code devenu inutile.

```python
"""PDF des codes d'une mission : une page par partie, jamais un code devenu inutile."""

import re

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.missions import documents, permissions
from apps.missions.models import StatutMission

from .factories import MissionFactory

pytestmark = pytest.mark.django_db

CODES = {"expediteur": "ABCD2345", "destinataire": "WXYZ6789"}


def _pages(pdf: bytes) -> int:
    return len(re.findall(rb"/Type /Page(?![s\w])", pdf))


def test_le_pdf_a_une_page_par_partie_avec_son_code_et_son_qr():
    mission = MissionFactory(numero="MIS-2026-0042")

    pdf = documents.generer_pdf_codes(mission, CODES)

    assert pdf.startswith(b"%PDF")
    assert _pages(pdf) == 2
    assert b"MIS-2026-0042" in pdf
    # chaque code sert de contenu à son QR ; à l'écran il est écrit espacé (« A B C D … »)
    assert b"(A B C D 2 3 4 5) Tj" in pdf and b"(W X Y Z 6 7 8 9) Tj" in pdf
    assert pdf.count(b"/Subtype /Image") >= 2  # le logo et les QR


def test_un_seul_code_utile_donne_une_seule_page():
    pdf = documents.generer_pdf_codes(MissionFactory(), {"expediteur": None, "destinataire": "WXYZ6789"})

    assert _pages(pdf) == 1
    assert b"ABCD2345" not in pdf and b"A B C D 2 3 4 5" not in pdf  # le code de l'autre partie n'y est pas


def test_aucun_code_utile_est_une_erreur():
    with pytest.raises(ValueError):
        documents.generer_pdf_codes(MissionFactory(), {"expediteur": None, "destinataire": None})


def test_l_entete_porte_le_nom_de_l_entreprise(settings):
    settings.ENTREPRISE_NOM = "Transport Essai SA"
    settings.ENTREPRISE_ADRESSE = "Zone 4, Abidjan"

    pdf = documents.generer_pdf_codes(MissionFactory(), CODES)

    assert b"Transport Essai SA" in pdf and b"Zone 4, Abidjan" in pdf


# --- écran ---


@pytest.mark.parametrize("role", sorted(permissions.VOIR_CODES))
def test_les_roles_qui_voient_les_codes_telechargent_le_pdf(client, role):
    client.force_login(UserFactory(role=role))
    mission = MissionFactory()

    reponse = client.get(reverse("missions:codes_pdf", args=[mission.pk]))

    assert reponse.status_code == 200
    assert reponse["Content-Type"] == "application/pdf"
    assert reponse["Content-Disposition"] == f'attachment; filename="codes-{mission.numero}.pdf"'
    assert "no-store" in reponse["Cache-Control"]


@pytest.mark.parametrize("role", [Role.CHAUFFEUR, Role.RH, Role.FINANCES])
def test_les_autres_roles_n_ont_pas_le_pdf(client, role):
    client.force_login(UserFactory(role=role))

    assert client.get(reverse("missions:codes_pdf", args=[MissionFactory().pk])).status_code == 403


def test_le_parc_auto_consulte_la_mission_mais_pas_le_pdf_des_codes(client):
    """Retour réunion : le Parc Auto affecte les missions (CONSULTATION), mais les codes restent
    réservés à ceux qui gèrent la relation client (VOIR_CODES, décision indépendante)."""
    client.force_login(UserFactory(role=Role.PARCAUTO))

    assert client.get(reverse("missions:codes_pdf", args=[MissionFactory().pk])).status_code == 404


def test_le_pdf_ne_contient_plus_le_code_expediteur_apres_la_recuperation(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    mission = MissionFactory(
        statut=StatutMission.EN_COURS_COLIS_RECUPERE, vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory(), km_depart=1000
    )

    pdf = client.get(reverse("missions:codes_pdf", args=[mission.pk])).content

    assert _pages(pdf) == 1
    assert b"A B C D 2 3 4 5" not in pdf and b"W X Y Z 6 7 8 9" in pdf


def test_le_pdf_est_introuvable_une_fois_la_mission_livree(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    mission = MissionFactory(
        statut=StatutMission.LIVREE, vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory(), km_depart=1000, km_arrivee=1200
    )

    assert client.get(reverse("missions:codes_pdf", args=[mission.pk])).status_code == 404


def test_la_fiche_propose_le_telechargement_du_pdf(client):
    client.force_login(UserFactory(role=Role.CHARGE_CLIENTELE))
    mission = MissionFactory()

    contenu = client.get(reverse("missions:detail", args=[mission.pk])).content.decode()

    assert reverse("missions:codes_pdf", args=[mission.pk]) in contenu


def test_la_fiche_mission_qui_affiche_les_codes_n_est_jamais_gardee_en_cache(client):
    """Audit AUD-15 : comme le PDF et le QR des codes."""
    client.force_login(UserFactory(role=sorted(permissions.VOIR_CODES)[0]))

    reponse = client.get(reverse("missions:detail", args=[MissionFactory().pk]))

    assert reponse.status_code == 200 and reponse["Cache-Control"] == "no-store, private"
```

#### `apps/missions/tests/test_documents_et_reaffectation.py`

*193 lignes* — Audit M3-10 : un chauffeur au permis ou à la visite médicale expiré n'est pas affectable.

```python
"""Audit M3-10 : un chauffeur au permis ou à la visite médicale expiré n'est pas affectable.
Audit M5-09 : réaffecter seulement le camion ou seulement le chauffeur marche, et une hausse du poids est
recontrôlée contre la capacité du camion conservé."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.models import DocumentReglementaire, TypeDocument
from apps.fleet.tests.factories import VehiculeEnRegleFactory, VehiculeFactory
from apps.missions import services
from apps.missions.exceptions import AffectationImpossible, DemarrageImpossible

from .test_modification import _champs
from .test_services import _affectee, _planifiee

pytestmark = pytest.mark.django_db

HIER = timezone.localdate() - timedelta(days=1)
DEMAIN = timezone.localdate() + timedelta(days=1)


# --- documents du chauffeur ---


def test_un_permis_expire_bloque_l_affectation():
    mission = _planifiee()
    chauffeur = ChauffeurFactory(date_expiration_permis=HIER)

    with pytest.raises(AffectationImpossible, match=r"permis de conduire \(expiré le"):
        services.affecter_mission(mission, vehicule=VehiculeEnRegleFactory(), chauffeur=chauffeur)


def test_une_visite_medicale_expiree_bloque_l_affectation():
    mission = _planifiee()
    chauffeur = ChauffeurFactory(date_expiration_visite_medicale=HIER)

    with pytest.raises(AffectationImpossible, match="visite médicale"):
        services.affecter_mission(mission, vehicule=VehiculeEnRegleFactory(), chauffeur=chauffeur)


def test_les_deux_documents_expires_sont_nommes():
    mission = _planifiee()
    chauffeur = ChauffeurFactory(date_expiration_permis=HIER, date_expiration_visite_medicale=HIER)

    with pytest.raises(AffectationImpossible, match="permis de conduire.* ; visite médicale"):
        services.affecter_mission(mission, vehicule=VehiculeEnRegleFactory(), chauffeur=chauffeur)


def test_l_expiration_aujourd_hui_ne_bloque_pas_encore():
    aujourd_hui = timezone.localdate()
    chauffeur = ChauffeurFactory(date_expiration_permis=aujourd_hui, date_expiration_visite_medicale=DEMAIN)

    mission = services.affecter_mission(_planifiee(), vehicule=VehiculeEnRegleFactory(), chauffeur=chauffeur)

    assert mission.chauffeur == chauffeur


# --- fiche permis incomplète : bloquante depuis la décision du 12/10/2026 (audit M5-04) ---


@pytest.mark.parametrize(
    ("champs", "message"),
    [
        ({"numero_permis": ""}, "n° de permis non renseigné"),
        ({"categories_permis": []}, "ni catégorie C ni catégorie E"),
        ({"date_expiration_permis": None}, "date d'expiration du permis non renseignée"),
        ({"date_expiration_visite_medicale": None}, "visite médicale non renseignée"),
    ],
)
def test_une_fiche_permis_incomplete_bloque_l_affectation(champs, message):
    chauffeur = ChauffeurFactory(**champs)

    with pytest.raises(AffectationImpossible, match=message):
        services.affecter_mission(_planifiee(), vehicule=VehiculeEnRegleFactory(), chauffeur=chauffeur)


@pytest.mark.parametrize("categories", [["C"], ["E"], ["C", "E"]])
def test_la_categorie_c_ou_e_suffit(categories):
    chauffeur = ChauffeurFactory(categories_permis=categories)

    mission = services.affecter_mission(_planifiee(), vehicule=VehiculeEnRegleFactory(), chauffeur=chauffeur)

    assert mission.chauffeur == chauffeur


def test_tous_les_manques_sont_nommes_ensemble():
    chauffeur = ChauffeurFactory(numero_permis="", date_expiration_visite_medicale=None)

    with pytest.raises(AffectationImpossible, match="n° de permis non renseigné ; visite médicale non renseignée"):
        services.affecter_mission(_planifiee(), vehicule=VehiculeEnRegleFactory(), chauffeur=chauffeur)


# --- documents du camion : bloquants s'ils sont expirés ou manquants (audit AUD-12) ---


def test_un_camion_sans_assurance_n_est_pas_affectable():
    camion = VehiculeEnRegleFactory()
    DocumentReglementaire.objects.filter(vehicule=camion, type_document=TypeDocument.ASSURANCE).delete()

    with pytest.raises(AffectationImpossible, match=r"ne peut pas rouler : assurance non enregistrée"):
        services.affecter_mission(_planifiee(), vehicule=camion, chauffeur=ChauffeurFactory())


def test_un_camion_a_la_visite_technique_expiree_n_est_pas_affectable():
    camion = VehiculeEnRegleFactory()
    DocumentReglementaire.objects.filter(vehicule=camion, type_document=TypeDocument.VISITE_TECHNIQUE).update(
        date_expiration=HIER
    )

    with pytest.raises(AffectationImpossible, match="visite technique expirée le"):
        services.affecter_mission(_planifiee(), vehicule=camion, chauffeur=ChauffeurFactory())


def test_un_camion_sans_aucun_document_les_nomme_tous():
    camion = VehiculeFactory()

    with pytest.raises(AffectationImpossible) as erreur:
        services.affecter_mission(_planifiee(), vehicule=camion, chauffeur=ChauffeurFactory())

    for libelle in ("carte grise", "assurance", "visite technique", "patente"):
        assert f"{libelle} non enregistrée" in str(erreur.value)


def test_un_document_du_camion_expire_depuis_l_affectation_bloque_le_depart():
    mission = _affectee()
    DocumentReglementaire.objects.filter(vehicule=mission.vehicule, type_document=TypeDocument.ASSURANCE).update(
        date_expiration=HIER
    )

    with pytest.raises(DemarrageImpossible, match="assurance expirée le"):
        services.demarrer_mission(mission)


def test_le_depart_est_refuse_si_un_document_a_expire_depuis_l_affectation():
    chauffeur = ChauffeurFactory(date_expiration_permis=DEMAIN)
    mission = _affectee(chauffeur=chauffeur)
    type(chauffeur).objects.filter(pk=chauffeur.pk).update(date_expiration_permis=HIER)

    with pytest.raises(DemarrageImpossible, match="permis de conduire"):
        services.demarrer_mission(mission)


def test_reaffecter_vers_un_chauffeur_au_permis_expire_est_refuse():
    mission = _affectee()

    with pytest.raises(AffectationImpossible, match="permis de conduire"):
        services.modifier_mission(
            mission, **_champs(mission), vehicule=mission.vehicule,
            chauffeur=ChauffeurFactory(date_expiration_permis=HIER),
        )


# --- réaffectation partielle ---


def test_changer_seulement_le_camion_garde_le_chauffeur():
    mission = _affectee()
    chauffeur, nouveau = mission.chauffeur, VehiculeEnRegleFactory()

    modifiee = services.modifier_mission(mission, **_champs(mission), vehicule=nouveau, chauffeur=chauffeur)

    assert (modifiee.vehicule, modifiee.chauffeur) == (nouveau, chauffeur)


def test_changer_seulement_le_chauffeur_garde_le_camion():
    mission = _affectee()
    vehicule, nouveau = mission.vehicule, ChauffeurFactory()

    modifiee = services.modifier_mission(mission, **_champs(mission), vehicule=vehicule, chauffeur=nouveau)

    assert (modifiee.vehicule, modifiee.chauffeur) == (vehicule, nouveau)


def test_une_hausse_du_poids_est_recontrolee_contre_le_camion_conserve():
    mission = _affectee()
    capacite = mission.vehicule.capacite_charge_t

    with pytest.raises(AffectationImpossible, match="capacité du camion"):
        services.modifier_mission(mission, **_champs(mission, poids_t=capacite + Decimal("1")))


def test_un_poids_dans_la_capacite_reste_accepte():
    mission = _affectee()

    modifiee = services.modifier_mission(
        mission, **_champs(mission, poids_t=mission.vehicule.capacite_charge_t)
    )

    assert modifiee.poids_t == mission.vehicule.capacite_charge_t
```

#### `apps/missions/tests/test_frais_mission_views.py`

*120 lignes* — Écrans de la prévision de trésorerie des missions (R4) : accès, planification, validation.

```python
"""Écrans de la prévision de trésorerie des missions (R4) : accès, planification, validation."""

from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.missions import terrain as missions_terrain
from apps.missions.models import StatutFraisMission, TypeFraisMission

from .test_frais_mission import _chauffeur, _finances, _mission_affectee, _parcauto

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    compte = UserFactory(role=role)
    client.force_login(compte)
    return compte


# La RH fait tout ce que fait la FINANCES (avenant R8 § 2 ; audit M1-27, décision du 12/10/2026).
@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.PARCAUTO, Role.FINANCES, Role.RH])
def test_les_frais_de_mission_sont_accessibles_aux_roles_concernes(client, role):
    _connecte(client, role)
    mission = _mission_affectee()

    for url in (reverse("missions:frais_liste"), reverse("missions:frais", args=[mission.pk])):
        assert client.get(url).status_code == 200, url


@pytest.mark.parametrize("role", [Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_les_frais_de_mission_sont_interdits_aux_autres_roles(client, role):
    _connecte(client, role)
    mission = _mission_affectee()

    assert client.get(reverse("missions:frais_liste")).status_code == 403
    assert client.get(reverse("missions:frais", args=[mission.pk])).status_code == 403


def test_le_lien_frais_de_mission_n_apparait_pas_pour_le_charge_clientele(client):
    mission = _mission_affectee()
    _connecte(client, Role.DIRECTION)
    assert "Frais de mission" in client.get(reverse("missions:detail", args=[mission.pk])).content.decode()

    _connecte(client, Role.CHARGE_CLIENTELE)
    assert "Frais de mission" not in client.get(reverse("missions:detail", args=[mission.pk])).content.decode()


def test_le_parc_auto_planifie_une_avance_via_l_ecran(client):
    mission = _mission_affectee()
    _connecte(client, Role.PARCAUTO)

    reponse = client.post(
        reverse("missions:frais_planifier", args=[mission.pk]),
        {"type_frais": TypeFraisMission.AVANCE_ROUTE, "montant": "50000", "description": "Avance essence"},
    )

    assert reponse.status_code == 302
    assert mission.frais.filter(type_frais=TypeFraisMission.AVANCE_ROUTE).exists()


def test_la_finance_confirme_une_avance_via_l_ecran(client):
    mission = _mission_affectee()
    frais = missions_terrain.planifier_frais(
        mission, _parcauto(), type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000")
    )
    _connecte(client, Role.FINANCES)

    reponse = client.post(reverse("missions:frais_valider_finances", args=[frais.pk]))

    assert reponse.status_code == 302
    frais.refresh_from_db()
    assert frais.statut == StatutFraisMission.CONFIRME


def test_le_parc_auto_valide_puis_la_finance_confirme_un_imprevu_via_les_ecrans(client):
    chauffeur = _chauffeur()
    mission = _mission_affectee(chauffeur)
    preuve = SimpleUploadedFile("p.jpg", BytesIO(b"x").read(), content_type="image/jpeg")
    frais = missions_terrain.declarer_imprevu(mission, chauffeur, montant=Decimal("9000"), justificatif=preuve)

    _connecte(client, Role.PARCAUTO)
    reponse = client.post(reverse("missions:frais_valider_parcauto", args=[frais.pk]))
    assert reponse.status_code == 302
    frais.refresh_from_db()
    assert frais.statut == StatutFraisMission.PREVU and frais.valide_parcauto_par is not None

    _connecte(client, Role.FINANCES)
    reponse = client.post(reverse("missions:frais_valider_finances", args=[frais.pk]))
    assert reponse.status_code == 302
    frais.refresh_from_db()
    assert frais.statut == StatutFraisMission.CONFIRME


def test_rejeter_un_frais_via_l_ecran(client):
    mission = _mission_affectee()
    frais = missions_terrain.planifier_frais(
        mission, _parcauto(), type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000")
    )
    _connecte(client, Role.FINANCES)

    reponse = client.post(reverse("missions:frais_rejeter", args=[frais.pk]), {"motif": "Montant excessif"})

    assert reponse.status_code == 302
    frais.refresh_from_db()
    assert frais.statut == StatutFraisMission.REJETE


def test_le_rapport_de_mission_s_imprime(client):
    mission = _mission_affectee()
    _connecte(client, Role.DIRECTION)

    reponse = client.get(reverse("missions:frais_imprimer", args=[mission.pk]))

    assert reponse.status_code == 200
```

#### `apps/missions/tests/test_modification.py`

*305 lignes* — R3 — Modification d'une mission (avenant-separation-des-taches.md) : DIRECTION et ADMIN

```python
"""R3 — Modification d'une mission (avenant-separation-des-taches.md) : DIRECTION et ADMIN
seulement, tant que le colis n'est pas encore récupéré ; changer un lieu régénère les codes,
changer camion/chauffeur revérifie leur disponibilité."""

from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.models import StatutChauffeur
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.models import StatutVehicule
from apps.fleet.tests.factories import VehiculeEnRegleFactory
from apps.missions import services
from apps.missions.exceptions import AffectationImpossible, MissionError, TransitionMissionInterdite
from apps.missions.models import Mission, StatutMission

from .test_services import _affectee, _creer, _en_cours, _livree, _planifiee, _recuperee

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    utilisateur = UserFactory(role=role)
    client.force_login(utilisateur)
    return utilisateur


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _champs(mission, **surcharges):
    donnees = dict(
        lieu_chargement=mission.lieu_chargement,
        lieu_livraison=mission.lieu_livraison,
        nature_marchandise=mission.nature_marchandise,
        poids_t=mission.poids_t,
        prix_convenu=mission.prix_convenu,
        date_depart_prevue=mission.date_depart_prevue,
    )
    donnees.update(surcharges)
    return donnees


def _poste(mission, **surcharges):
    """``_champs`` prête pour un POST HTTP (le client de test n'encode pas ``None``)."""
    donnees = _champs(mission, **surcharges)
    if donnees.get("date_depart_prevue") is None:
        donnees["date_depart_prevue"] = ""
    return donnees


# --- service : statuts modifiables ---


@pytest.mark.parametrize("fabrique", [_creer, _planifiee, _affectee, _en_cours])
def test_modifiable_jusqu_a_en_cours_depart(fabrique):
    mission = fabrique()

    modifiee = services.modifier_mission(mission, **_champs(mission, nature_marchandise="Sable"))

    assert modifiee.nature_marchandise == "Sable"


@pytest.mark.parametrize("fabrique", [_recuperee, _livree])
def test_plus_modifiable_a_partir_de_colis_recupere(fabrique):
    mission = fabrique()

    with pytest.raises(TransitionMissionInterdite):
        services.modifier_mission(mission, **_champs(mission, nature_marchandise="Sable"))


# --- validations ---


def test_poids_et_prix_restent_valides():
    mission = _creer()

    with pytest.raises(MissionError, match="poids"):
        services.modifier_mission(mission, **_champs(mission, poids_t=Decimal("0")))
    with pytest.raises(MissionError, match="négatif"):
        services.modifier_mission(mission, **_champs(mission, prix_convenu=Decimal("-1")))


def test_le_prix_convenu_est_bien_modifiable():
    mission = _creer()

    modifiee = services.modifier_mission(mission, **_champs(mission, prix_convenu=Decimal("999000")))

    assert modifiee.prix_convenu == Decimal("999000")


# --- lieu → codes régénérés ---


def test_changer_un_lieu_regenere_les_deux_codes():
    mission = _creer()
    ancien_expediteur, ancien_destinataire = mission.code_expediteur, mission.code_destinataire

    modifiee = services.modifier_mission(mission, **_champs(mission, lieu_livraison="Korhogo"))

    assert modifiee.code_expediteur != ancien_expediteur
    assert modifiee.code_destinataire != ancien_destinataire
    assert modifiee.code_expediteur != modifiee.code_destinataire


def test_ne_pas_changer_le_lieu_garde_les_memes_codes():
    mission = _creer()
    code = mission.code_expediteur

    modifiee = services.modifier_mission(mission, **_champs(mission, nature_marchandise="Sable"))

    assert modifiee.code_expediteur == code


# --- camion / chauffeur ---


def test_reaffecter_camion_et_chauffeur_sur_une_mission_affectee():
    mission = _affectee()
    nouveau_vehicule, nouveau_chauffeur = VehiculeEnRegleFactory(), ChauffeurFactory()

    modifiee = services.modifier_mission(
        mission, **_champs(mission), vehicule=nouveau_vehicule, chauffeur=nouveau_chauffeur
    )

    assert (modifiee.vehicule, modifiee.chauffeur) == (nouveau_vehicule, nouveau_chauffeur)


def test_reaffecter_revalide_la_disponibilite():
    mission = _affectee()

    with pytest.raises(AffectationImpossible, match="camion"):
        services.modifier_mission(
            mission, **_champs(mission),
            vehicule=VehiculeEnRegleFactory(statut=StatutVehicule.EN_MAINTENANCE), chauffeur=ChauffeurFactory(),
        )


def test_reaffecter_refuse_un_camion_deja_reserve_par_une_autre_mission():
    vehicule = VehiculeEnRegleFactory()
    _affectee(vehicule=vehicule)
    mission = _affectee()

    with pytest.raises(AffectationImpossible, match="déjà réservé"):
        services.modifier_mission(
            mission, **_champs(mission), vehicule=vehicule, chauffeur=ChauffeurFactory()
        )


def test_ne_pas_changer_camion_ni_chauffeur_ne_revalide_rien():
    """Le camion actuel n'est pas « disponible » au sens strict une fois affecté ailleurs (une autre
    mission) : mais tant qu'on ne le change pas, aucune revérification n'a lieu."""
    mission = _affectee()
    vehicule, chauffeur = mission.vehicule, mission.chauffeur

    modifiee = services.modifier_mission(mission, **_champs(mission), vehicule=vehicule, chauffeur=chauffeur)

    assert (modifiee.vehicule, modifiee.chauffeur) == (vehicule, chauffeur)


def test_reaffecter_impossible_apres_le_depart():
    mission = _en_cours()

    with pytest.raises(TransitionMissionInterdite, match="avant le départ"):
        services.modifier_mission(
            mission, **_champs(mission), vehicule=VehiculeEnRegleFactory(), chauffeur=ChauffeurFactory()
        )


def test_reaffecter_impossible_avant_l_affectation():
    mission = _planifiee()

    with pytest.raises(TransitionMissionInterdite, match="avant le départ"):
        services.modifier_mission(
            mission, **_champs(mission), vehicule=VehiculeEnRegleFactory(), chauffeur=ChauffeurFactory()
        )


def test_camion_et_chauffeur_se_changent_ensemble():
    mission = _affectee()

    with pytest.raises(MissionError, match="ensemble"):
        services.modifier_mission(mission, **_champs(mission), vehicule=VehiculeEnRegleFactory())


# --- audit ---


def test_la_modification_est_tracee_dans_l_audit():
    from apps.audit.models import ActionChoices, AuditLog

    mission = _creer()

    services.modifier_mission(mission, **_champs(mission, nature_marchandise="Sable"))

    entree = AuditLog.objects.filter(entite="Mission", entite_id=mission.pk, action=ActionChoices.UPDATE).latest("date_heure")
    assert entree.nouvelle_valeur.get("nature_marchandise") == "Sable"
    assert "code_expediteur" not in (entree.ancienne_valeur or {})  # codes exclus de l'audit


# --- permissions ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION])
def test_admin_et_direction_modifient(client, role):
    _connecte(client, role)
    mission = _creer()

    reponse = client.post(
        reverse("missions:modifier", args=[mission.pk]),
        _poste(mission, nature_marchandise="Sable"),
        follow=True,
    )

    mission.refresh_from_db()
    assert mission.nature_marchandise == "Sable"
    assert any("modifiée" in m for m in _messages(reponse))


@pytest.mark.parametrize("role", [Role.CHARGE_CLIENTELE, Role.PARCAUTO, Role.FINANCES, Role.RH])
def test_les_autres_roles_ne_modifient_pas(client, role):
    _connecte(client, role)
    mission = _creer()

    for methode, args in ((client.get, ()), (client.post, (_poste(mission),))):
        reponse = methode(reverse("missions:modifier", args=[mission.pk]), *args)
        assert reponse.status_code == 403


def test_le_lien_modifier_n_apparait_que_pour_les_bons_roles_et_statuts(client):
    mission = _recuperee()

    _connecte(client, Role.DIRECTION)
    page = client.get(reverse("missions:detail", args=[mission.pk])).content.decode()
    assert reverse("missions:modifier", args=[mission.pk]) not in page  # plus modifiable

    autre = _creer()
    page = client.get(reverse("missions:detail", args=[autre.pk])).content.decode()
    assert reverse("missions:modifier", args=[autre.pk]) in page

    _connecte(client, Role.CHARGE_CLIENTELE)
    page = client.get(reverse("missions:detail", args=[autre.pk])).content.decode()
    assert reverse("missions:modifier", args=[autre.pk]) not in page  # pas le bon rôle


# --- écran ---


def test_le_formulaire_est_prerempli(client):
    _connecte(client, Role.DIRECTION)
    mission = _creer()

    reponse = client.get(reverse("missions:modifier", args=[mission.pk]))

    assert reponse.context["form"].initial["nature_marchandise"] == mission.nature_marchandise
    assert "vehicule" not in reponse.context["form"].fields  # pas encore affectée


def test_le_formulaire_propose_camion_et_chauffeur_une_fois_affectee(client):
    _connecte(client, Role.DIRECTION)
    mission = _affectee()

    reponse = client.get(reverse("missions:modifier", args=[mission.pk]))

    assert "vehicule" in reponse.context["form"].fields
    assert reponse.context["form"].initial["vehicule"] == mission.vehicule_id


def test_acceder_a_l_ecran_sur_une_mission_non_modifiable_renvoie_a_la_fiche(client):
    _connecte(client, Role.DIRECTION)
    mission = _livree()

    reponse = client.get(reverse("missions:modifier", args=[mission.pk]), follow=True)

    assert reponse.redirect_chain[-1][0] == reverse("missions:detail", args=[mission.pk])
    assert any("n'est plus modifiable" in m for m in _messages(reponse))


def test_une_erreur_metier_reste_sur_le_formulaire(client):
    _connecte(client, Role.DIRECTION)
    mission = _creer()

    reponse = client.post(
        reverse("missions:modifier", args=[mission.pk]), _poste(mission, poids_t="0"),
    )

    assert reponse.status_code == 200
    assert "strictement positif" in reponse.content.decode()
    mission.refresh_from_db()
    assert mission.poids_t != Decimal("0")


def test_le_client_n_est_pas_modifiable(client):
    """Aucun champ « client » sur l'écran : il n'apparaît nulle part dans le formulaire."""
    _connecte(client, Role.DIRECTION)
    mission = _creer()

    reponse = client.get(reverse("missions:modifier", args=[mission.pk]))

    assert "client" not in reponse.context["form"].fields
```

#### `apps/missions/tests/test_qr.py`

*118 lignes* — Image QR des codes d'une mission : droits, contenu, secret.

```python
"""Image QR des codes d'une mission : droits, contenu, secret."""

import io

import pytest
import qrcode
from django.test import Client
from django.urls import reverse
from PIL import Image

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.missions.models import StatutMission

from .factories import MissionFactory

pytestmark = pytest.mark.django_db


def _png(code):
    tampon = io.BytesIO()
    qrcode.make(code, box_size=8, border=2).save(tampon, format="PNG")
    return tampon.getvalue()


def _mission(statut=StatutMission.AFFECTEE):
    from apps.drivers.tests.factories import ChauffeurFactory
    from apps.fleet.tests.factories import VehiculeFactory

    return MissionFactory(
        statut=statut, vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory(),
        code_expediteur="ABCD2345", code_destinataire="WXYZ6789",
    )


def test_le_qr_est_une_image_png_qui_ne_contient_que_le_code(client):
    client.force_login(UserFactory(role=Role.DIRECTION))
    mission = _mission()

    exp = client.get(reverse("missions:qr", args=[mission.pk, "expediteur"]))
    dest = client.get(reverse("missions:qr", args=[mission.pk, "destinataire"]))

    assert exp.status_code == 200 and exp["Content-Type"] == "image/png"
    assert exp.content.startswith(b"\x89PNG") and Image.open(io.BytesIO(exp.content)).size[0] > 100
    assert exp.content == _png("ABCD2345") and dest.content == _png("WXYZ6789")  # contenu = le code seul
    assert exp.content != dest.content


def test_le_qr_n_est_jamais_mis_en_cache(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    mission = _mission()

    reponse = client.get(reverse("missions:qr", args=[mission.pk, "expediteur"]))

    assert reponse["Cache-Control"] == "no-store, private"


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE])
def test_les_roles_qui_voient_les_codes_voient_le_qr(client, role):
    client.force_login(UserFactory(role=role))
    mission = _mission()

    assert client.get(reverse("missions:qr", args=[mission.pk, "expediteur"])).status_code == 200


@pytest.mark.parametrize("role", [Role.CHAUFFEUR, Role.RH, Role.FINANCES])
def test_les_autres_roles_n_obtiennent_pas_le_qr(client, role):
    client.force_login(UserFactory(role=role))
    mission = _mission()

    assert client.get(reverse("missions:qr", args=[mission.pk, "expediteur"])).status_code == 403


def test_le_parc_auto_consulte_la_mission_mais_pas_le_qr_des_codes(client):
    """Retour réunion : le Parc Auto affecte les missions (CONSULTATION), mais les codes restent
    réservés à ceux qui gèrent la relation client (VOIR_CODES, décision indépendante)."""
    client.force_login(UserFactory(role=Role.PARCAUTO))
    mission = _mission()

    assert client.get(reverse("missions:qr", args=[mission.pk, "expediteur"])).status_code == 404


def test_le_qr_exige_la_connexion(client):
    mission = _mission()

    assert client.get(reverse("missions:qr", args=[mission.pk, "expediteur"])).status_code == 302


def test_un_qr_inutile_ou_inconnu_est_un_404(client):
    client.force_login(UserFactory(role=Role.DIRECTION))
    recuperee = _mission(StatutMission.EN_COURS_COLIS_RECUPERE)
    livree = _mission(StatutMission.LIVREE)

    assert client.get(reverse("missions:qr", args=[recuperee.pk, "expediteur"])).status_code == 404  # colis déjà récupéré
    assert client.get(reverse("missions:qr", args=[recuperee.pk, "destinataire"])).status_code == 200
    assert client.get(reverse("missions:qr", args=[livree.pk, "destinataire"])).status_code == 404
    assert client.get(reverse("missions:qr", args=[recuperee.pk, "autre"])).status_code == 404
    assert client.get(reverse("missions:qr", args=[99999, "expediteur"])).status_code == 404


def test_la_fiche_de_la_mission_affiche_les_qr_pour_le_bon_role(client):
    mission = _mission()

    client.force_login(UserFactory(role=Role.DIRECTION))
    texte = client.get(reverse("missions:detail", args=[mission.pk])).content.decode()
    assert reverse("missions:qr", args=[mission.pk, "expediteur"]) in texte
    assert reverse("missions:qr", args=[mission.pk, "destinataire"]) in texte
    assert "Code QR de l&#x27;expéditeur" in texte or "Code QR de l'expéditeur" in texte


def test_le_qr_ne_fuite_pas_dans_la_fiche_des_roles_sans_droit(client):
    mission = _mission()
    client.force_login(UserFactory(role=Role.ADMIN))
    assert "/qr/" in client.get(reverse("missions:detail", args=[mission.pk])).content.decode()

    http = Client()
    http.force_login(UserFactory(role=Role.CHAUFFEUR))
    assert http.get(reverse("missions:detail", args=[mission.pk])).status_code == 403
```

#### `apps/missions/tests/test_sortie_personnel.py`

*159 lignes* — Sortie d'un chauffeur ou d'un copilote (audit M1-22, avenant-sortie-personnel.md) : effets sur les missions,

```python
"""Sortie d'un chauffeur ou d'un copilote (audit M1-22, avenant-sortie-personnel.md) : effets sur les missions,
les fiches et les notifications."""

from datetime import date, timedelta

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers import services as drivers_services
from apps.drivers.models import Chauffeur, Copilote, StatutChauffeur
from apps.drivers.tests.factories import ChauffeurFactory, CopiloteFactory
from apps.fleet.tests.factories import VehiculeEnRegleFactory
from apps.hr import sorties
from apps.hr.exceptions import SortieImpossible
from apps.hr.models import MotifSortie, SortiePersonnel
from apps.missions.models import Mission, StatutMission
from apps.notifications import taches
from apps.notifications.models import Notification

from .factories import MissionFactory

pytestmark = pytest.mark.django_db

AUJOURD_HUI = date(2026, 10, 12)


def _sortir(personnel, *, le=AUJOURD_HUI):
    return sorties.enregistrer_sortie(
        personnel, UserFactory(role=Role.RH), date_sortie=le, motif=MotifSortie.LICENCIEMENT, aujourd_hui=AUJOURD_HUI
    )


def _mission(statut, chauffeur, copilote=None):
    return MissionFactory(statut=statut, vehicule=VehiculeEnRegleFactory(), chauffeur=chauffeur, copilote=copilote)


@pytest.mark.parametrize("statut", [StatutMission.EN_COURS_DEPART, StatutMission.EN_COURS_COLIS_RECUPERE])
def test_un_chauffeur_sur_la_route_ne_peut_pas_sortir(statut):
    chauffeur = ChauffeurFactory()
    mission = _mission(statut, chauffeur)

    with pytest.raises(SortieImpossible, match=f"sur la route \\(mission {mission.numero}\\)"):
        _sortir(chauffeur.personnel)
    assert not SortiePersonnel.objects.exists()  # rien n'est enregistré


def test_un_copilote_sur_la_route_ne_peut_pas_sortir():
    copilote = CopiloteFactory()
    _mission(StatutMission.EN_COURS_DEPART, ChauffeurFactory(), copilote)

    with pytest.raises(SortieImpossible, match="sur la route"):
        _sortir(copilote.personnel)


def test_une_sortie_a_venir_attend_la_fin_de_la_mission():
    chauffeur = ChauffeurFactory()
    mission = _mission(StatutMission.EN_COURS_DEPART, chauffeur)
    sortie, _ = _sortir(chauffeur.personnel, le=AUJOURD_HUI + timedelta(days=3))
    echeance = AUJOURD_HUI + timedelta(days=3)

    resultat = sorties.appliquer_sorties_echues(aujourd_hui=echeance)

    assert resultat["appliquees"] == 0 and resultat["reportees"][0][0] == sortie
    Mission.objects.filter(pk=mission.pk).update(statut=StatutMission.LIVREE)
    assert sorties.appliquer_sorties_echues(aujourd_hui=echeance + timedelta(days=1))["appliquees"] == 1


def test_les_fiches_chauffeur_et_copilote_du_partant_deviennent_inactives():
    chauffeur, copilote = ChauffeurFactory(), CopiloteFactory()

    _, bilan_chauffeur = _sortir(chauffeur.personnel)
    _, bilan_copilote = _sortir(copilote.personnel)

    assert Chauffeur.objects.get(pk=chauffeur.pk).statut == StatutChauffeur.INACTIF
    assert Copilote.objects.get(pk=copilote.pk).statut == StatutChauffeur.INACTIF
    assert bilan_chauffeur["fiche_chauffeur_inactive"] and bilan_copilote["fiche_copilote_inactive"]


def test_un_chauffeur_en_conge_qui_sort_devient_inactif_et_le_reste_a_la_fin_du_conge():
    chauffeur = ChauffeurFactory(statut=StatutChauffeur.EN_CONGE)

    _sortir(chauffeur.personnel)

    assert Chauffeur.objects.get(pk=chauffeur.pk).statut == StatutChauffeur.INACTIF


def test_la_mission_affectee_du_chauffeur_sortant_repasse_planifiee_et_le_parc_auto_est_prevenu():
    parc = UserFactory(role=Role.PARCAUTO)
    chauffeur = ChauffeurFactory(personnel__prenom="Issa", personnel__nom="Bamba")
    mission = _mission(StatutMission.AFFECTEE, chauffeur, CopiloteFactory())

    _, bilan = _sortir(chauffeur.personnel)

    mission.refresh_from_db()
    assert mission.statut == StatutMission.PLANIFIEE
    assert mission.vehicule is None and mission.chauffeur is None and mission.copilote is None
    assert bilan["missions_desaffectees"] == [mission.numero]
    (notification,) = Notification.objects.filter(destinataire=parc)
    assert notification.titre == f"Mission {mission.numero} à réaffecter"
    assert notification.message.startswith("Sortie de Issa Bamba le 12/10/2026")
    assert notification.url == reverse("missions:detail", args=[mission.pk])


def test_le_copilote_sortant_est_seulement_retire_de_la_mission_affectee():
    chauffeur, copilote = ChauffeurFactory(), CopiloteFactory()
    mission = _mission(StatutMission.AFFECTEE, chauffeur, copilote)

    _, bilan = _sortir(copilote.personnel)

    mission.refresh_from_db()
    assert mission.statut == StatutMission.AFFECTEE and mission.chauffeur == chauffeur and mission.copilote is None
    assert bilan["missions_sans_copilote"] == [mission.numero] and bilan["missions_desaffectees"] == []


def test_les_missions_terminees_ne_sont_pas_touchees():
    chauffeur = ChauffeurFactory()
    livree = _mission(StatutMission.LIVREE, chauffeur)
    planifiee = MissionFactory(statut=StatutMission.PLANIFIEE)

    _sortir(chauffeur.personnel)

    assert Mission.objects.get(pk=livree.pk).chauffeur == chauffeur
    assert Mission.objects.get(pk=planifiee.pk).statut == StatutMission.PLANIFIEE


def test_un_chauffeur_sorti_n_est_plus_propose():
    chauffeur = ChauffeurFactory()

    _sortir(chauffeur.personnel)

    assert chauffeur not in drivers_services.chauffeurs_actifs()
    assert chauffeur not in drivers_services.chauffeurs_disponibles()


def test_la_tache_du_jour_previent_la_rh_une_seule_fois_d_une_sortie_retenue():
    rh = UserFactory(role=Role.RH)
    chauffeur = ChauffeurFactory(personnel__prenom="Issa", personnel__nom="Bamba")
    _mission(StatutMission.EN_COURS_DEPART, chauffeur)
    _sortir(chauffeur.personnel, le=AUJOURD_HUI + timedelta(days=1))

    for jour in (1, 2):
        resultat = taches.executer_taches_quotidiennes(aujourd_hui=AUJOURD_HUI + timedelta(days=jour))

    assert resultat["sorties_appliquees"] == 0
    (notification,) = Notification.objects.filter(destinataire=rh, titre="Sortie de Issa Bamba en attente")
    assert "sur la route" in notification.message
    assert notification.url == reverse("hr:personnel_detail", args=[chauffeur.personnel_id])


def test_la_tache_du_jour_applique_une_sortie_echue():
    chauffeur = ChauffeurFactory()
    _sortir(chauffeur.personnel, le=AUJOURD_HUI + timedelta(days=1))

    resultat = taches.executer_taches_quotidiennes(aujourd_hui=AUJOURD_HUI + timedelta(days=1))

    assert resultat["sorties_appliquees"] == 1
    assert Chauffeur.objects.get(pk=chauffeur.pk).statut == StatutChauffeur.INACTIF
```

#### `apps/missions/tests/test_views.py`

*633 lignes* — Écrans des missions : accès par rôle, affichage, actions du cycle de vie.

```python
"""Écrans des missions : accès par rôle, affichage, actions du cycle de vie."""

from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.customers.tests.factories import ClientFactory
from apps.fleet.models import StatutVehicule
from apps.fleet.tests.factories import VehiculeEnRegleFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.missions import services
from apps.missions.models import Mission, StatutMission

from .factories import MissionFactory
from .test_services import (
    _affectee,
    _creer,
    _en_cours,
    _livree,
    _planifiee,
    _recuperee,
)

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    utilisateur = UserFactory(role=role)
    client.force_login(utilisateur)
    return utilisateur


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _url(nom, mission):
    return reverse(f"missions:{nom}", args=[mission.pk])


# --- accès par rôle ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE, Role.PARCAUTO])
def test_la_liste_est_accessible_aux_roles_de_gestion(client, role):
    # Retour réunion : le Parc Auto affecte les missions, donc les consulte désormais aussi.
    _connecte(client, role)

    assert client.get(reverse("missions:liste")).status_code == 200


@pytest.mark.parametrize("role", [Role.RH, Role.FINANCES, Role.CHAUFFEUR])
def test_la_liste_est_interdite_aux_autres_roles(client, role):
    _connecte(client, role)

    assert client.get(reverse("missions:liste")).status_code == 403


@pytest.mark.parametrize(
    "nom", ["liste", "creer"]
)
def test_un_visiteur_non_connecte_est_renvoye_vers_la_connexion(client, nom):
    reponse = client.get(reverse(f"missions:{nom}"))

    assert reponse.status_code == 302
    assert reponse.url.startswith(reverse("accounts:login"))


# --- liste ---


def test_la_liste_affiche_les_missions(client):
    _connecte(client, Role.DIRECTION)
    mission = _planifiee()

    contenu = client.get(reverse("missions:liste")).content.decode()

    assert mission.numero in contenu
    assert mission.client.raison_sociale in contenu
    assert "Planifiée" in contenu


def test_la_liste_vide_affiche_un_message(client):
    _connecte(client, Role.DIRECTION)

    assert "Aucune mission trouvée" in client.get(reverse("missions:liste")).content.decode()


def test_la_liste_filtre_par_statut(client):
    _connecte(client, Role.DIRECTION)
    brouillon, planifiee = _creer(), _planifiee()

    reponse = client.get(reverse("missions:liste"), {"statut": StatutMission.PLANIFIEE})

    assert list(reponse.context["missions"]) == [planifiee]
    assert brouillon.numero not in reponse.content.decode()


def test_la_liste_ignore_un_statut_inconnu(client):
    _connecte(client, Role.DIRECTION)
    _creer()

    reponse = client.get(reverse("missions:liste"), {"statut": "N_IMPORTE_QUOI"})

    assert len(reponse.context["missions"]) == 1


def test_la_liste_recherche_par_client_numero_ou_lieu(client):
    _connecte(client, Role.DIRECTION)
    cible = _creer(client=ClientFactory(raison_sociale="Cimaf Côte d'Ivoire"))
    _creer(lieu_livraison="Korhogo")

    par_client = client.get(reverse("missions:liste"), {"q": "cimaf"})
    par_numero = client.get(reverse("missions:liste"), {"q": cible.numero})
    par_lieu = client.get(reverse("missions:liste"), {"q": "korhogo"})

    assert list(par_client.context["missions"]) == [cible]
    assert list(par_numero.context["missions"]) == [cible]
    assert len(par_lieu.context["missions"]) == 1


def test_la_liste_est_paginee_par_20_et_conserve_les_filtres(client):
    _connecte(client, Role.DIRECTION)
    for _ in range(21):
        MissionFactory(statut=StatutMission.BROUILLON)

    page1 = client.get(reverse("missions:liste"), {"statut": "BROUILLON"})
    page2 = client.get(reverse("missions:liste"), {"statut": "BROUILLON", "page": 2})

    assert len(page1.context["missions"]) == 20
    assert len(page2.context["missions"]) == 1
    assert "statut=BROUILLON" in page1.content.decode()  # lien « Suivant »


def test_la_liste_n_effectue_pas_une_requete_par_mission(client, django_assert_max_num_queries):
    _connecte(client, Role.DIRECTION)
    for _ in range(15):
        MissionFactory()

    with django_assert_max_num_queries(10):
        client.get(reverse("missions:liste"))


def test_le_contenu_saisi_est_echappe_contre_le_xss(client):
    _connecte(client, Role.DIRECTION)
    _creer(lieu_chargement="<script>alert('xss')</script>")

    contenu = client.get(reverse("missions:liste")).content.decode()

    assert "<script>alert('xss')</script>" not in contenu
    assert "&lt;script&gt;" in contenu


# --- fiche ---


def test_la_fiche_affiche_le_detail(client):
    _connecte(client, Role.DIRECTION)
    mission = _affectee()

    contenu = client.get(_url("detail", mission)).content.decode()

    assert mission.numero in contenu
    assert mission.vehicule.immatriculation in contenu
    assert mission.chauffeur.personnel.nom in contenu


def test_la_fiche_d_une_mission_inconnue_est_introuvable(client):
    _connecte(client, Role.DIRECTION)

    assert client.get(reverse("missions:detail", args=[999999])).status_code == 404


def test_la_frise_marque_l_etape_courante(client):
    _connecte(client, Role.DIRECTION)
    mission = _en_cours()

    reponse = client.get(_url("detail", mission))

    etapes = reponse.context["etapes"]
    assert [e["etat"] for e in etapes] == [
        "faite", "faite", "faite", "courante", "a_venir", "a_venir", "a_venir",
    ]
    assert reponse.content.decode().count('aria-current="step"') == 1


@pytest.mark.parametrize(
    ("etape", "expediteur", "destinataire"),
    [
        (_creer, True, True),
        (_en_cours, True, True),
        (_recuperee, False, True),  # colis récupéré : le code expéditeur ne sert plus
        (_livree, False, False),  # livrée : plus aucun code utile
    ],
)
def test_les_codes_ne_s_affichent_que_tant_qu_ils_servent(client, etape, expediteur, destinataire):
    _connecte(client, Role.DIRECTION)
    mission = etape()

    contenu = client.get(_url("detail", mission)).content.decode()

    assert (mission.code_expediteur in contenu) is expediteur
    assert (mission.code_destinataire in contenu) is destinataire


# --- actions proposées selon rôle et statut ---


def test_le_charge_clientele_peut_planifier_un_brouillon_mais_pas_affecter(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    brouillon = _creer()
    planifiee = _planifiee()

    page_brouillon = client.get(_url("detail", brouillon)).content.decode()
    page_planifiee = client.get(_url("detail", planifiee)).content.decode()

    assert _url("planifier", brouillon) in page_brouillon
    assert _url("affecter", planifiee) not in page_planifiee
    assert _url("annuler", planifiee) in page_planifiee  # il peut l'annuler avant le départ (audit AUD-02)


def test_la_direction_voit_le_formulaire_d_affectation_avec_les_seuls_camions_disponibles(client):
    _connecte(client, Role.DIRECTION)
    mission = _planifiee()
    libre = VehiculeEnRegleFactory(immatriculation="1111 AA 01")
    VehiculeEnRegleFactory(immatriculation="2222 BB 01", statut=StatutVehicule.EN_MAINTENANCE)

    reponse = client.get(_url("detail", mission))
    contenu = reponse.content.decode()

    assert _url("affecter", mission) in contenu
    assert libre.immatriculation in contenu
    assert "2222 BB 01" not in contenu


@pytest.mark.parametrize(
    ("etape", "action_attendue"),
    [
        (_affectee, "demarrer"),
        (_livree, "cloturer"),
    ],
)
def test_la_direction_voit_l_action_de_l_etape(client, etape, action_attendue):
    _connecte(client, Role.DIRECTION)
    mission = etape()

    contenu = client.get(_url("detail", mission)).content.decode()

    assert _url(action_attendue, mission) in contenu


@pytest.mark.parametrize(
    ("etape", "action_attendue"), [(_en_cours, "recuperation"), (_recuperee, "livraison")]
)
def test_l_admin_voit_la_saisie_du_code_a_la_place_du_chauffeur(client, etape, action_attendue):
    _connecte(client, Role.ADMIN)
    mission = etape()

    contenu = client.get(_url("detail", mission)).content.decode()

    assert _url(action_attendue, mission) in contenu


@pytest.mark.parametrize(
    ("etape", "action"), [(_en_cours, "recuperation"), (_recuperee, "livraison")]
)
def test_seul_le_chargeur_clientele_voit_les_codes_sans_les_saisir(client, etape, action):
    """Le chargé clientèle voit les codes mais ne les saisit pas."""
    _connecte(client, Role.CHARGE_CLIENTELE)
    mission = etape()
    statut_avant = mission.statut
    code = mission.code_expediteur if action == "recuperation" else mission.code_destinataire

    contenu = client.get(_url("detail", mission)).content.decode()
    reponse = client.post(_url(action, mission), {"code": code, "km_arrivee": mission.km_depart + 10})

    assert _url(action, mission) not in contenu
    assert reponse.status_code == 403
    mission.refresh_from_db()
    assert mission.statut == statut_avant


@pytest.mark.parametrize(
    ("etape", "action_attendue"), [(_en_cours, "recuperation"), (_recuperee, "livraison")]
)
def test_la_direction_saisit_desormais_aussi_les_codes(client, etape, action_attendue):
    """Retour réunion : la DIRECTION a la même largeur que l'ADMIN (CODES_TERRAIN)."""
    _connecte(client, Role.DIRECTION)
    mission = etape()

    contenu = client.get(_url("detail", mission)).content.decode()

    assert _url(action_attendue, mission) in contenu


def test_une_mission_cloturee_n_a_plus_d_action(client):
    _connecte(client, Role.ADMIN)
    mission = services.cloturer_mission(_livree())

    contenu = client.get(_url("detail", mission)).content.decode()

    assert "Aucune action disponible" in contenu


# --- création ---


def test_le_formulaire_de_creation_s_affiche(client):
    _connecte(client, Role.CHARGE_CLIENTELE)

    reponse = client.get(reverse("missions:creer"))

    assert reponse.status_code == 200
    assert "Nouvelle mission" in reponse.content.decode()


def test_creer_une_mission_valide(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    societe = ClientFactory()

    reponse = client.post(
        reverse("missions:creer"),
        {
            "client": societe.pk,
            "lieu_chargement": "Abidjan, Port",
            "lieu_livraison": "Bouaké",
            "nature_marchandise": "Ciment",
            "poids_t": "18.50",
            "prix_convenu": "850000",
            "date_depart_prevue": "2026-10-12",
        },
        follow=True,
    )

    mission = Mission.objects.get()
    assert reponse.redirect_chain[-1][0] == _url("detail", mission)
    assert mission.statut == StatutMission.BROUILLON
    assert mission.poids_t == Decimal("18.50")
    assert str(mission.date_depart_prevue) == "2026-10-12"
    assert mission.numero in " ".join(_messages(reponse))


def test_creer_avec_un_poids_nul_affiche_l_erreur_sans_creer(client):
    _connecte(client, Role.DIRECTION)
    societe = ClientFactory()

    reponse = client.post(
        reverse("missions:creer"),
        {
            "client": societe.pk,
            "lieu_chargement": "Abidjan",
            "lieu_livraison": "Bouaké",
            "nature_marchandise": "Ciment",
            "poids_t": "0",
            "prix_convenu": "1000",
        },
    )

    assert reponse.status_code == 200
    assert reponse.context["form"].errors
    assert Mission.objects.count() == 0


def test_creer_sans_client_est_refuse(client):
    _connecte(client, Role.DIRECTION)

    reponse = client.post(reverse("missions:creer"), {"lieu_chargement": "x"})

    assert "client" in reponse.context["form"].errors
    assert Mission.objects.count() == 0


def test_la_creation_est_interdite_aux_autres_roles(client):
    _connecte(client, Role.RH)

    assert client.get(reverse("missions:creer")).status_code == 403
    assert client.post(reverse("missions:creer"), {}).status_code == 403


# --- actions du cycle de vie ---


def test_planifier(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    mission = _creer()

    reponse = client.post(_url("planifier", mission), follow=True)

    mission.refresh_from_db()
    assert mission.statut == StatutMission.PLANIFIEE
    assert reponse.redirect_chain[-1][0] == _url("detail", mission)
    assert any("planifiée" in m for m in _messages(reponse))


def test_une_action_refusee_par_le_service_affiche_l_erreur_sans_rien_changer(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    mission = _planifiee()

    reponse = client.post(_url("planifier", mission), follow=True)  # déjà planifiée

    mission.refresh_from_db()
    assert mission.statut == StatutMission.PLANIFIEE
    assert any("Impossible de planifier" in m for m in _messages(reponse))


def test_un_role_sans_droit_ne_peut_pas_agir_meme_par_post_direct(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    mission = _planifiee()
    camion, chauffeur = VehiculeEnRegleFactory(), ChauffeurFactory()

    reponse = client.post(
        _url("affecter", mission), {"vehicule": camion.pk, "chauffeur": chauffeur.pk}
    )

    mission.refresh_from_db()
    assert reponse.status_code == 403
    assert mission.statut == StatutMission.PLANIFIEE


def test_affecter(client):
    _connecte(client, Role.DIRECTION)
    mission = _planifiee()
    camion, chauffeur = VehiculeEnRegleFactory(), ChauffeurFactory()

    client.post(
        _url("affecter", mission), {"vehicule": camion.pk, "chauffeur": chauffeur.pk}
    )

    mission.refresh_from_db()
    assert mission.statut == StatutMission.AFFECTEE
    assert (mission.vehicule, mission.chauffeur) == (camion, chauffeur)


def test_affecter_un_camion_indisponible_est_refuse(client):
    _connecte(client, Role.DIRECTION)
    mission = _planifiee()
    en_panne = VehiculeEnRegleFactory(statut=StatutVehicule.EN_MAINTENANCE)

    reponse = client.post(
        _url("affecter", mission),
        {"vehicule": en_panne.pk, "chauffeur": ChauffeurFactory().pk},
        follow=True,
    )

    mission.refresh_from_db()
    assert mission.statut == StatutMission.PLANIFIEE
    assert any(m for m in _messages(reponse))  # message d'erreur du formulaire


def test_affecter_une_charge_trop_lourde_affiche_l_erreur_du_service(client):
    _connecte(client, Role.DIRECTION)
    mission = _planifiee(poids_t=Decimal("30"))
    petit = VehiculeEnRegleFactory(capacite_charge_t=Decimal("10"))

    reponse = client.post(
        _url("affecter", mission),
        {"vehicule": petit.pk, "chauffeur": ChauffeurFactory().pk},
        follow=True,
    )

    assert any("capacité" in m for m in _messages(reponse))
    mission.refresh_from_db()
    assert mission.statut == StatutMission.PLANIFIEE


def test_demarrer(client):
    _connecte(client, Role.DIRECTION)
    mission = _affectee()

    client.post(_url("demarrer", mission))

    mission.refresh_from_db()
    mission.vehicule.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_DEPART
    assert mission.vehicule.statut == StatutVehicule.EN_MISSION


def test_recuperation_avec_un_mauvais_code_est_refusee(client):
    _connecte(client, Role.ADMIN)
    mission = _en_cours()

    reponse = client.post(_url("recuperation", mission), {"code": "AAAAAAAA"}, follow=True)

    mission.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_DEPART
    assert "Code incorrect." in _messages(reponse)


def test_recuperation_avec_le_bon_code_meme_en_minuscules(client):
    _connecte(client, Role.ADMIN)
    mission = _en_cours()

    client.post(_url("recuperation", mission), {"code": mission.code_expediteur.lower()})

    mission.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_COLIS_RECUPERE


def test_livraison(client):
    _connecte(client, Role.ADMIN)
    mission = _recuperee()

    client.post(
        _url("livraison", mission),
        {"code": mission.code_destinataire, "km_arrivee": mission.km_depart + 250},
    )

    mission.refresh_from_db()
    mission.vehicule.refresh_from_db()
    assert mission.statut == StatutMission.LIVREE
    assert mission.vehicule.kilometrage == mission.km_depart + 250
    assert mission.vehicule.statut == StatutVehicule.DISPONIBLE


def test_livraison_avec_un_km_incoherent_est_refusee(client):
    _connecte(client, Role.ADMIN)
    mission = _recuperee()

    reponse = client.post(
        _url("livraison", mission),
        {"code": mission.code_destinataire, "km_arrivee": mission.km_depart - 1},
        follow=True,
    )

    mission.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_COLIS_RECUPERE
    assert any("kilométrage" in m.lower() for m in _messages(reponse))


def test_livraison_sans_km_est_refusee_par_le_formulaire(client):
    _connecte(client, Role.ADMIN)
    mission = _recuperee()

    client.post(_url("livraison", mission), {"code": mission.code_destinataire})

    mission.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_COLIS_RECUPERE


def test_cloturer(client):
    _connecte(client, Role.DIRECTION)
    mission = _livree()

    client.post(_url("cloturer", mission))

    mission.refresh_from_db()
    assert mission.statut == StatutMission.CLOTUREE


def test_les_actions_refusent_le_get(client):
    _connecte(client, Role.DIRECTION)
    mission = _creer()

    assert client.get(_url("planifier", mission)).status_code == 405


def test_une_action_sur_une_mission_inconnue_est_introuvable(client):
    _connecte(client, Role.DIRECTION)

    assert client.post(reverse("missions:planifier", args=[999999])).status_code == 404


def test_les_actions_sont_protegees_par_csrf():
    client = Client(enforce_csrf_checks=True)
    client.force_login(UserFactory(role=Role.DIRECTION))
    mission = _creer()

    reponse = client.post(_url("planifier", mission))

    mission.refresh_from_db()
    assert reponse.status_code == 403
    assert mission.statut == StatutMission.BROUILLON


def test_un_parcours_complet_par_l_interface(client):
    """Brouillon → clôturée, uniquement par les écrans, avec les bons rôles (les codes : l'ADMIN)."""
    charge = Client()
    _connecte(charge, Role.CHARGE_CLIENTELE)
    direction = Client()
    _connecte(direction, Role.DIRECTION)
    admin = Client()
    _connecte(admin, Role.ADMIN)
    societe = ClientFactory()
    camion, chauffeur = VehiculeEnRegleFactory(kilometrage=50000), ChauffeurFactory()

    charge.post(
        reverse("missions:creer"),
        {
            "client": societe.pk,
            "lieu_chargement": "Abidjan",
            "lieu_livraison": "Yamoussoukro",
            "nature_marchandise": "Riz",
            "poids_t": "12",
            "prix_convenu": "600000",
        },
    )
    mission = Mission.objects.get()
    charge.post(_url("planifier", mission))
    direction.post(
        _url("affecter", mission), {"vehicule": camion.pk, "chauffeur": chauffeur.pk}
    )
    direction.post(_url("demarrer", mission))
    mission.refresh_from_db()
    admin.post(_url("recuperation", mission), {"code": mission.code_expediteur})
    admin.post(
        _url("livraison", mission),
        {"code": mission.code_destinataire, "km_arrivee": 50240},
    )
    direction.post(_url("cloturer", mission))

    mission.refresh_from_db()
    camion.refresh_from_db()
    assert mission.statut == StatutMission.CLOTUREE
    assert camion.kilometrage == 50240 and camion.statut == StatutVehicule.DISPONIBLE


# --- suggestions de lieux ---


def test_le_formulaire_propose_les_lieux_deja_utilises(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    _creer(lieu_chargement="Abidjan", lieu_livraison="Korhogo")

    contenu = client.get(reverse("missions:creer")).content.decode()

    assert '<datalist id="lieux-missions">' in contenu
    assert '<option value="Korhogo">' in contenu
    assert '<option value="Abidjan">' in contenu
    assert contenu.count('list="lieux-missions"') == 2  # chargement et livraison
```

#### `apps/notifications/tests/test_receivers_frais_mission.py`

*90 lignes* — Qui est prévenu de quoi pour la prévision de trésorerie des missions (R4).

```python
"""Qui est prévenu de quoi pour la prévision de trésorerie des missions (R4)."""

from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.missions import services as missions_services
from apps.missions import terrain as missions_terrain
from apps.missions.models import TypeFraisMission
from apps.missions.tests.test_frais_mission import _chauffeur, _finances, _mission_affectee, _parcauto
from apps.notifications.models import CategorieNotification, Notification

pytestmark = pytest.mark.django_db


def _de(utilisateur):
    return list(Notification.objects.filter(destinataire=utilisateur).order_by("pk"))


def _preuve():
    return SimpleUploadedFile("p.jpg", BytesIO(b"x").read(), content_type="image/jpeg")


def test_la_finance_est_prevenue_d_une_affectation():
    finance = UserFactory(role=Role.FINANCES)
    from apps.drivers.tests.factories import ChauffeurFactory
    from apps.fleet.tests.factories import VehiculeEnRegleFactory
    from apps.missions.models import StatutMission
    from apps.missions.tests.factories import MissionFactory

    mission = MissionFactory(statut=StatutMission.PLANIFIEE)

    missions_services.affecter_mission(mission, vehicule=VehiculeEnRegleFactory(), chauffeur=ChauffeurFactory())

    (notification,) = _de(finance)
    assert notification.categorie == CategorieNotification.FRAIS_MISSION


def test_le_parc_auto_est_prevenu_d_un_imprevu_declare():
    parcauto = UserFactory(role=Role.PARCAUTO)
    chauffeur = _chauffeur()
    mission = _mission_affectee(chauffeur)

    missions_terrain.declarer_imprevu(mission, chauffeur, montant=Decimal("9000"), justificatif=_preuve())

    (notification,) = _de(parcauto)
    assert notification.categorie == CategorieNotification.FRAIS_MISSION
    assert mission.numero in notification.titre


def test_la_finance_est_prevenue_apres_la_validation_du_parc_auto():
    finance = UserFactory(role=Role.FINANCES)
    chauffeur = _chauffeur()
    mission = _mission_affectee(chauffeur)
    frais = missions_terrain.declarer_imprevu(mission, chauffeur, montant=Decimal("9000"), justificatif=_preuve())

    missions_terrain.valider_parcauto(frais, _parcauto())

    (notification,) = _de(finance)
    assert notification.categorie == CategorieNotification.FRAIS_MISSION
    assert "Parc Auto" in notification.message


def test_l_auteur_est_prevenu_du_rejet_d_une_avance():
    mission = _mission_affectee()
    parcauto = _parcauto()
    frais = missions_terrain.planifier_frais(
        mission, parcauto, type_frais=TypeFraisMission.AVANCE_ROUTE, montant=Decimal("50000")
    )

    missions_terrain.rejeter(frais, _finances(), motif="Montant excessif")

    (notification,) = _de(parcauto)
    assert "Montant excessif" in notification.message


def test_le_chauffeur_est_prevenu_du_rejet_de_son_imprevu():
    chauffeur = _chauffeur()
    mission = _mission_affectee(chauffeur)
    frais = missions_terrain.declarer_imprevu(mission, chauffeur, montant=Decimal("9000"), justificatif=_preuve())

    missions_terrain.rejeter(frais, _parcauto(), motif="Aucune preuve valable")

    utilisateur_chauffeur = chauffeur.personnel.utilisateur
    (notification,) = _de(utilisateur_chauffeur)
    assert "Aucune preuve valable" in notification.message
```

Ce chapitre présente de nombreux tests laissés plus tôt car ils ouvrent des pages qui dépendent des missions :
les tests de connexion et de menu par rôle (`accounts/test_web.py`), des fiches des clients et des chauffeurs
(qui affichent des missions), l'alerte de congé et les codes QR.

```bash
cd frontend
npm run build:css
cd ..
```

## Vérifier le chapitre

```bash
python manage.py check
```

```bash
python -m pytest apps/customers/tests/test_views.py apps/drivers/tests/test_views.py apps/missions/tests/test_alerte_conge.py apps/missions/tests/test_documents.py apps/missions/tests/test_documents_et_reaffectation.py apps/missions/tests/test_frais_mission_views.py apps/missions/tests/test_modification.py apps/missions/tests/test_qr.py apps/missions/tests/test_sortie_personnel.py apps/missions/tests/test_views.py apps/notifications/tests/test_receivers_frais_mission.py -q --no-cov
```

**Résultat attendu :** `254 passed` (pour les 11 fichier(s) de tests présentés dans ce chapitre).

Les cinq tests de `accounts/test_web.py` qui dépendent du **tableau de bord** échouent encore : ils passeront au
chapitre 30 (c'est attendu).

**Un parcours complet dans le navigateur** (`python manage.py runserver`) :

1. **`demo_charge`** : « Nouvelle mission » (client `Cimaf CI`, Abidjan → Bouaké, ciment, 22 tonnes, 780 000).
   Sur la fiche (statut **Brouillon**), cliquez **Planifier**.
2. **`demo_direction`** : ouvrez la mission, **Affecter** : choisissez le camion `1234 AB 01` et le chauffeur
   `Moussa Ouattara`. Essayez d'affecter une mission de **30 tonnes** : le service refuse (capacité 25 t).
3. **Démarrer** la mission : le camion et le chauffeur passent « En mission » (vérifiez dans Flotte et Chauffeurs).
   La fiche affiche **deux codes de 8 caractères et leurs QR**.
4. **Récupération** : saisissez le **code de l'expéditeur** (un mauvais code est refusé). Puis **Livraison** avec le
   **code du destinataire** et un kilométrage d'arrivée : la mission passe **Livrée**, le camion redevient
   Disponible et son compteur est à jour.
5. **Clôturer** la mission (Direction).
6. Avec **`demo_parcauto`**, ouvrez `/missions/` : **Accès refusé**. Avec **`demo_charge`**, la mission n'affiche
   plus le bouton « Affecter » (réservé à la Direction).
7. Le journal d'audit (`/admin/audit/auditlog/`, en tant qu'**administrateur** avec la MFA) montre chaque
   transition, **sans** aucun code secret.

## Ce qu'il faut retenir

- **Le service décide, la vue re-vérifie, le gabarit affiche** : trois couches, une seule règle.
- Une **image** peut être servie par une vue ordinaire ; on lui applique les mêmes gardes que pour une page.
- Un secret montré à l'écran ne doit **jamais être mis en cache**.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 23 : écrans des missions (cycle de vie, actions, codes QR)"
```

---

[← Chapitre 22](22-ecrans-flotte.md) · [Sommaire](README.md) · [Chapitre 24 →](24-ecrans-garage.md)
