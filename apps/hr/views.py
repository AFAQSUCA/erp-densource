"""Écrans RH : congés (demande, validation N1/N2, annulation) et fiche du personnel.

Aucune règle métier ici : les vues contrôlent le rôle, lisent le formulaire et
délèguent à ``services.py`` (conventions.md:19-23). Le droit de valider dépend de la
hiérarchie et non du seul rôle : c'est ``services.py`` qui le tranche.
"""

import openpyxl
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.accounts.mixins import RoleRequiredMixin
from apps.core.formats import nombre
from apps.core.views import ImpressionListeMixin, PaginationTolerante

from . import documents, permissions, sections, services
from .exceptions import CongeError, ImportPersonnelError, PersonnelError
from .forms import (
    AttributionForm,
    CongeForm,
    DecisionForm,
    DecisionReportForm,
    ImportPersonnelForm,
    PersonnelForm,
    ReportForm,
)
from .models import AttributionConge, Departement, ReportConge, StatutConge

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
                {
                    "conge": c,
                    "echeance": services.echeance_en_attente(c),
                    # Équivalent à services.peut_demander_report(c, utilisateur), sans requête
                    # supplémentaire par ligne : self.fiche est déjà mise en cache pour la page.
                    "peut_reporter": c.statut == StatutConge.EN_COURS and self.fiche is not None and self.fiche.pk == c.employe_id,
                }
                for c in contexte["page_obj"]
            ],
        )
        return contexte


class CongeImprimerView(ImpressionListeMixin, CongeListView):
    """Rapport imprimable des congés (même vue — mes demandes / à valider / tous — et même statut)."""

    titre_impression = "Congés"
    colonnes = (
        ("Employé", lambda c: f"{c.employe.prenom} {c.employe.nom}"),
        ("Du", lambda c: c.date_debut.strftime("%d/%m/%Y")), ("Au", lambda c: c.date_fin.strftime("%d/%m/%Y")),
        ("Jours", "jours"), ("Motif", "motif"), ("Statut", "get_statut_display"),
    )

    LIBELLES_VUE = {VUE_MES: "mes demandes", VUE_A_VALIDER: "à valider", VUE_TOUS: "tous les congés"}

    def get_sous_titre_impression(self):
        morceaux = [self.LIBELLES_VUE.get(self.get_vue(), "")]
        if self.request.GET.get("statut", "") in StatutConge.values:
            morceaux.append(f"statut : {StatutConge(self.request.GET['statut']).label}")
        return " · ".join(m for m in morceaux if m)


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
        report = services.report_en_attente(conge)
        contexte.update(
            validations=conge.validations.select_related("validateur"),
            droits=services.droits_conges(conge.employe, conge.date_debut.year),
            echeance=services.echeance_en_attente(conge),
            actions=services.actions_disponibles(conge, utilisateur),
            en_remplacement=services.decide_en_remplacement(conge, utilisateur),
            sections=sections.DETAIL_CONGE.sections(conge, utilisateur),
            peut_voir_employe=utilisateur.role_effectif in permissions.PERSONNEL_CONSULTATION,
            peut_reporter=services.peut_demander_report(conge, utilisateur),
            report_en_attente=report,
            peut_decider_report=bool(report) and services.peut_decider_report(report, utilisateur),
            reports_decides=conge.reports.exclude(pk=getattr(report, "pk", None)).select_related("valide_par"),
            peut_telecharger_autorisation=conge.statut in services.STATUTS_DECOMPTES,
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


# --- report du solde d'un congé en cours (avenant-separation-des-taches.md § R7) ---


class ReportCreateView(RoleRequiredMixin, FormView):
    """Demande de report, par l'employé actuellement en congé (bouton sur sa ligne du tableau)."""

    roles = permissions.CONGES_ACCES
    form_class = ReportForm
    template_name = "hr/report_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.conge = get_object_or_404(services.conges_queryset(), pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        if not services.peut_demander_report(self.conge, request.user):
            messages.error(request, "Le report n'est possible que pour votre propre congé, pendant que vous y êtes.")
            return redirect("hr:conges_detail", pk=self.conge.pk)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        return super().get_context_data(conge=self.conge, **kwargs)

    def form_valid(self, form):
        try:
            services.demander_report(self.conge, self.request.user, **form.cleaned_data)
        except CongeError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(
            self.request,
            "Demande de report envoyée à la RH : sans sa validation, votre congé continue normalement.",
        )
        return redirect("hr:conges_detail", pk=self.conge.pk)


class ReportDecisionView(RoleRequiredMixin, View):
    """Valide ou refuse une demande de report (POST, RH uniquement — contrôlé par le service)."""

    roles = permissions.CONGES_ACCES
    http_method_names = ["post"]

    def post(self, request, pk):
        report = get_object_or_404(ReportConge.objects.select_related("conge"), pk=pk)
        form = DecisionReportForm(request.POST)
        if not form.is_valid():
            _erreurs_en_messages(request, form)
            return redirect("hr:conges_detail", pk=report.conge_id)
        action, commentaire = form.cleaned_data["action"], form.cleaned_data["commentaire"]
        try:
            if action == "valider":
                services.approuver_report(report, request.user, commentaire=commentaire)
                messages.success(
                    request,
                    f"Report validé : {report.jours_restants} jour(s) reversé(s) au solde de l'employé.",
                )
            else:
                services.refuser_report(report, request.user, motif=commentaire)
                messages.success(request, "Report refusé : le congé continue jusqu'à sa fin initiale.")
        except CongeError as erreur:
            messages.error(request, str(erreur))
        return redirect("hr:conges_detail", pk=report.conge_id)


class AutorisationCongePdfView(RoleRequiredMixin, View):
    """PDF de l'autorisation de congé, produit à la demande (jamais stocké)."""

    roles = permissions.CONGES_ACCES
    http_method_names = ["get"]

    def get(self, request, pk):
        conge = get_object_or_404(services.conges_queryset(), pk=pk)
        if (
            request.user.role_effectif not in permissions.CONGES_TOUS
            and not services.est_concerne_par(conge, request.user)
        ):
            raise PermissionDenied
        try:
            contenu = documents.generer_pdf_autorisation(conge)
        except ValueError:
            raise Http404
        reponse = HttpResponse(contenu, content_type="application/pdf")
        reponse["Content-Disposition"] = f'attachment; filename="autorisation-conge-{conge.pk}.pdf"'
        reponse["Cache-Control"] = "no-store, private"
        return reponse


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


class PersonnelImprimerView(ImpressionListeMixin, PersonnelListView):
    """Rapport imprimable du personnel (mêmes recherche et département que la liste ; sans le salaire,
    comme la liste elle-même)."""

    titre_impression = "Personnel"
    colonnes = (
        ("Matricule", "matricule"), ("Nom", "nom"), ("Prénom", "prenom"), ("Poste", "poste"),
        ("Département", "get_departement_display"),
        ("Date d'embauche", lambda p: p.date_embauche.strftime("%d/%m/%Y")),
        ("Supérieur", lambda p: f"{p.superieur.prenom} {p.superieur.nom}" if p.superieur_id and p.superieur_id != p.pk else "—"),
    )

    def get_sous_titre_impression(self):
        morceaux = []
        if self.request.GET.get("departement", "") in Departement.values:
            morceaux.append(f"département : {Departement(self.request.GET['departement']).label}")
        if self.request.GET.get("q", ""):
            morceaux.append(f"recherche : « {self.request.GET['q']} »")
        return " · ".join(morceaux)


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


class PersonnelImportView(RoleRequiredMixin, FormView):
    """Recrutement en masse depuis un classeur Excel — voir services.importer_personnel."""

    roles = permissions.PERSONNEL_MODIFICATION
    form_class = ImportPersonnelForm
    template_name = "hr/personnel_import.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(colonnes=services.COLONNES_IMPORT, **kwargs)

    def form_valid(self, form):
        try:
            crees = services.importer_personnel(form.cleaned_data["fichier"])
        except ImportPersonnelError as erreur:
            return self.render_to_response(self.get_context_data(form=form, erreurs=erreur.erreurs))
        messages.success(
            self.request,
            f"{len(crees)} employé(s) importé(s) : "
            + ", ".join(f"{p.prenom} {p.nom} ({p.matricule})" for p in crees) + ".",
        )
        return redirect("hr:personnel_liste")


class PersonnelModeleImportView(RoleRequiredMixin, View):
    """Modèle de fichier à télécharger avant l'import en masse (colonnes attendues, un exemple)."""

    roles = permissions.PERSONNEL_MODIFICATION

    def get(self, request):
        classeur = openpyxl.Workbook()
        feuille = classeur.active
        feuille.title = "Personnel"
        feuille.append(services.COLONNES_IMPORT)
        feuille.append(["Traoré", "Awa", "Comptable", "Comptabilité", "CDI", "01/09/2026", "250000"])
        reponse = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        reponse["Content-Disposition"] = "attachment; filename=modele-import-personnel.xlsx"
        classeur.save(reponse)
        return reponse


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
