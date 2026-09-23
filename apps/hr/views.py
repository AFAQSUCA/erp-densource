"""Écrans RH : congés (demande, validation N1/N2, annulation) et fiche du personnel.

Aucune règle métier ici : les vues contrôlent le rôle, lisent le formulaire et
délèguent à ``services.py`` (conventions.md:19-23). Le droit de valider dépend de la
hiérarchie et non du seul rôle : c'est ``services.py`` qui le tranche.
"""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.accounts.mixins import RoleRequiredMixin
from apps.core.formats import nombre
from apps.core.views import PaginationTolerante

from . import permissions, sections, services
from .exceptions import CongeError, PersonnelError
from .forms import AttributionForm, CongeForm, DecisionForm, PersonnelForm
from .models import AttributionConge, Departement, StatutConge

VUE_MES, VUE_A_VALIDER, VUE_TOUS = "mes", "a_valider", "tous"


def _erreurs_en_messages(request, form):
    for erreurs in form.errors.values():
        for erreur in erreurs:
            messages.error(request, erreur)


# --- congés ---


class CongeListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.CONGES_ACCES
    template_name = "hr/conge_list.html"
    context_object_name = "conges"
    paginate_by = 20

    @property
    def fiche(self):
        if not hasattr(self, "_fiche"):
            self._fiche = services.fiche_personnel(self.request.user)
        return self._fiche

    @property
    def a_valider(self):
        if not hasattr(self, "_a_valider"):
            self._a_valider = services.conges_a_valider(self.request.user)
        return self._a_valider

    def vues_disponibles(self):
        vues = []
        if self.fiche is not None:
            vues.append(VUE_MES)
        vues.append(VUE_A_VALIDER)
        if self.request.user.role_effectif in permissions.CONGES_TOUS:
            vues.append(VUE_TOUS)
        return vues

    def get_vue(self):
        disponibles = self.vues_disponibles()
        demandee = self.request.GET.get("vue")
        if demandee in disponibles:
            return demandee
        if self.a_valider.exists():
            return VUE_A_VALIDER
        return disponibles[0]

    def get_queryset(self):
        vue = self.get_vue()
        if vue == VUE_MES:
            resultat = services.conges_de(self.fiche)
        elif vue == VUE_A_VALIDER:
            resultat = self.a_valider
        else:
            resultat = services.conges_queryset()
        statut = self.request.GET.get("statut", "")
        if statut in StatutConge.values:
            resultat = resultat.filter(statut=statut)
        return resultat.order_by("-date_debut", "-pk")

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        annee = timezone.localdate().year
        contexte.update(
            vue=self.get_vue(),
            vues=self.vues_disponibles(),
            nombre_a_valider=self.a_valider.count(),
            statuts=StatutConge.choices,
            statut_choisi=self.request.GET.get("statut", ""),
            fiche=self.fiche,
            annee=annee,
            droits=services.droits_conges(self.fiche, annee) if self.fiche else None,
            lignes=[
                {"conge": c, "echeance": services.echeance_en_attente(c)}
                for c in contexte["page_obj"]
            ],
        )
        return contexte


class CongeCreateView(RoleRequiredMixin, FormView):
    roles = permissions.CONGES_ACCES
    form_class = CongeForm
    template_name = "hr/conge_form.html"

    def dispatch(self, request, *args, **kwargs):
        utilisateur = request.user
        if (
            utilisateur.is_authenticated
            and utilisateur.role_effectif in self.roles
            and services.fiche_personnel(utilisateur) is None
        ):
            messages.error(
                request,
                "Votre compte n'est rattaché à aucune fiche du personnel : "
                "demandez à la RH de le renseigner pour pouvoir demander un congé.",
            )
            return redirect("hr:conges_liste")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        fiche = services.fiche_personnel(self.request.user)
        annee = timezone.localdate().year
        contexte.update(
            fiche=fiche,
            annee=annee,
            droits=services.droits_conges(fiche, annee),
        )
        return contexte

    def form_valid(self, form):
        fiche = services.fiche_personnel(self.request.user)
        try:
            conge = services.demander_conge(fiche, **form.cleaned_data)
        except CongeError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(
            self.request,
            f"Demande enregistrée : {conge.jours} jour{'s' if conge.jours > 1 else ''} "
            "ouvrable(s). Votre supérieur hiérarchique doit la valider sous 48 h.",
        )
        return redirect("hr:conges_detail", pk=conge.pk)


class CongeDetailView(RoleRequiredMixin, DetailView):
    roles = permissions.CONGES_ACCES
    template_name = "hr/conge_detail.html"
    context_object_name = "conge"

    def get_queryset(self):
        return services.conges_queryset()

    def get_object(self, queryset=None):
        conge = super().get_object(queryset)
        utilisateur = self.request.user
        if (
            utilisateur.role_effectif not in permissions.CONGES_TOUS
            and not services.est_concerne_par(conge, utilisateur)
        ):
            raise PermissionDenied
        return conge

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        conge, utilisateur = self.object, self.request.user
        contexte.update(
            validations=conge.validations.select_related("validateur"),
            droits=services.droits_conges(conge.employe, conge.date_debut.year),
            echeance=services.echeance_en_attente(conge),
            actions=services.actions_disponibles(conge, utilisateur),
            sections=sections.DETAIL_CONGE.sections(conge, utilisateur),
            peut_voir_employe=utilisateur.role_effectif in permissions.PERSONNEL_CONSULTATION,
        )
        return contexte


class CongeDecisionView(RoleRequiredMixin, View):
    """Valide, refuse ou annule un congé (POST) ; le service contrôle le droit de le faire."""

    roles = permissions.CONGES_ACCES
    http_method_names = ["post"]

    def post(self, request, pk):
        conge = get_object_or_404(services.conges_queryset(), pk=pk)
        if (
            request.user.role_effectif not in permissions.CONGES_TOUS
            and not services.est_concerne_par(conge, request.user)
        ):
            raise PermissionDenied
        form = DecisionForm(request.POST)
        if not form.is_valid():
            _erreurs_en_messages(request, form)
            return redirect("hr:conges_detail", pk=conge.pk)
        action, commentaire = form.cleaned_data["action"], form.cleaned_data["commentaire"]
        statut_avant = conge.statut
        try:
            if action == services.ACTION_VALIDER:
                services.valider_conge(conge, request.user, commentaire=commentaire)
            elif action == services.ACTION_REFUSER:
                services.refuser(conge, request.user, commentaire=commentaire)
            else:
                services.annuler_conge_approuve(conge, request.user, motif=commentaire)
        except CongeError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, self._message(action, statut_avant, conge))
        return redirect("hr:conges_detail", pk=conge.pk)

    @staticmethod
    def _message(action, statut_avant, conge):
        if action == services.ACTION_REFUSER:
            return "Demande refusée : votre motif est visible par l'employé sur sa demande."
        if action == services.ACTION_ANNULER:
            return "Congé annulé : les jours sont restitués à l'employé."
        if statut_avant == StatutConge.DEMANDE:
            return "Demande validée en N1. Elle attend maintenant la validation de la RH (24 h)."
        return (
            f"Congé approuvé : {conge.jours} jour{'s' if conge.jours > 1 else ''} "
            f"décompté{'s' if conge.jours > 1 else ''} du droit de {conge.date_debut.year}."
        )


# --- personnel ---


class PersonnelListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.PERSONNEL_CONSULTATION
    template_name = "hr/personnel_list.html"
    context_object_name = "personnel"
    paginate_by = 20

    def get_queryset(self):
        return services.rechercher_personnel(
            departement=self.request.GET.get("departement", ""),
            recherche=self.request.GET.get("q", ""),
        )

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            departements=Departement.choices,
            departement_choisi=self.request.GET.get("departement", ""),
            recherche=self.request.GET.get("q", ""),
            peut_modifier=self.request.user.role_effectif in permissions.PERSONNEL_MODIFICATION,
        )
        return contexte


class PersonnelDetailView(RoleRequiredMixin, DetailView):
    roles = permissions.PERSONNEL_CONSULTATION
    template_name = "hr/personnel_detail.html"
    context_object_name = "employe"

    def get_queryset(self):
        return services.personnel_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        employe, utilisateur = self.object, self.request.user
        annee = timezone.localdate().year
        peut_accorder = services.peut_accorder_jours(utilisateur, employe)
        contexte.update(
            annee=annee,
            droits=services.droits_conges(employe, annee),
            conges=services.conges_de(employe)[:10],
            attributions=AttributionConge.objects.filter(employe=employe).select_related(
                "accorde_par"
            ),
            subordonnes=employe.subordonnes.order_by("nom", "prenom"),
            peut_modifier=utilisateur.role_effectif in permissions.PERSONNEL_MODIFICATION,
            peut_accorder=peut_accorder,
            form_attribution=AttributionForm() if peut_accorder else None,
        )
        return contexte


class PersonnelCreateView(RoleRequiredMixin, FormView):
    roles = permissions.PERSONNEL_MODIFICATION
    form_class = PersonnelForm
    template_name = "hr/personnel_form.html"

    def form_valid(self, form):
        try:
            personnel = services.recruter(**form.cleaned_data)
        except PersonnelError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        suite = (
            " Sa fiche chauffeur a été créée automatiquement." if personnel.est_chauffeur else ""
        )
        messages.success(
            self.request,
            f"{personnel.prenom} {personnel.nom} est enregistré(e) sous le matricule "
            f"{personnel.matricule}.{suite}",
        )
        return redirect("hr:personnel_detail", pk=personnel.pk)


class PersonnelUpdateView(RoleRequiredMixin, FormView):
    roles = permissions.PERSONNEL_MODIFICATION
    form_class = PersonnelForm
    template_name = "hr/personnel_form.html"

    @property
    def employe(self):
        if not hasattr(self, "_employe"):
            self._employe = get_object_or_404(services.personnel_queryset(), pk=self.kwargs["pk"])
        return self._employe

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["personnel"] = self.employe
        return kwargs

    def get_initial(self):
        e = self.employe
        return {
            "nom": e.nom,
            "prenom": e.prenom,
            "poste": e.poste,
            "departement": e.departement,
            "type_contrat": e.type_contrat,
            "salaire_base": e.salaire_base,
            "superieur": e.superieur,
            "utilisateur": e.utilisateur,
        }

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["employe"] = self.employe
        return contexte

    def form_valid(self, form):
        try:
            services.modifier_personnel(self.employe, **form.cleaned_data)
        except PersonnelError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, f"Fiche de {self.employe.prenom} {self.employe.nom} mise à jour.")
        return redirect("hr:personnel_detail", pk=self.employe.pk)


class AttributionView(RoleRequiredMixin, View):
    """Jours de congé exceptionnels (POST) : réservé à la RH, contrôlé par le service."""

    roles = permissions.PERSONNEL_MODIFICATION
    http_method_names = ["post"]

    def post(self, request, pk):
        employe = get_object_or_404(services.personnel_queryset(), pk=pk)
        form = AttributionForm(request.POST)
        if not form.is_valid():
            _erreurs_en_messages(request, form)
            return redirect("hr:personnel_detail", pk=employe.pk)
        try:
            attribution = services.accorder_jours_exceptionnels(
                employe, request.user, **form.cleaned_data
            )
        except CongeError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(
                request,
                f"{nombre(attribution.jours)} jour(s) exceptionnel(s) accordé(s) "
                f"pour {attribution.annee}.",
            )
        return redirect("hr:personnel_detail", pk=employe.pk)
