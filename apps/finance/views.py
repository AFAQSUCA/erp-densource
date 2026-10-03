"""Trésorerie : journal des mouvements, soldes par compte, mouvements manuels."""

from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, FormView, ListView, TemplateView

from apps.accounts.mixins import RoleRequiredMixin
from apps.billing import services as billing_services
from apps.billing.exceptions import BillingError
from apps.billing.forms import ReglementForm
from apps.billing.models import STATUTS_A_RECOUVRER, CompteTresorerie
from apps.core.formats import nombre
from apps.core.rapports import contexte_rapport
from apps.core.views import PaginationTolerante
from apps.core.xlsx import reponse_classeur

from . import demandes as demandes_services
from . import permissions, services
from .forms import (
    DecisionDemandeForm,
    DemandeDepenseForm,
    EnveloppeForm,
    ExecuterOrdreForm,
    FiltreTresorerieForm,
    LigneReleveForm,
    MotifForm,
    MouvementForm,
    PeriodeRapprochementForm,
    PointerLigneReleveForm,
    RevaliderOrdreForm,
)
from .models import (
    DemandeDepense,
    LigneReleve,
    MouvementManuel,
    OrdreDecaissement,
    SensMouvement,
    StatutDemandeDepense,
    StatutOrdreDecaissement,
)


class TresorerieView(RoleRequiredMixin, TemplateView):
    roles = permissions.CONSULTATION
    template_name = "finance/tresorerie.html"
    paginate_by = 25

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        filtre = FiltreTresorerieForm(self.request.GET)
        criteres = filtre.criteres()
        aujourd_hui = timezone.localdate()
        journal = services.mouvements(**criteres)
        paginator = Paginator(journal, self.paginate_by)
        try:
            numero = int(self.request.GET.get("page", 1))
        except ValueError:
            numero = 1
        page = paginator.page(min(max(numero, 1), paginator.num_pages))
        peut_saisir = self.request.user.role_effectif in permissions.SAISIE
        soldes = services.soldes_par_compte()
        versements = services.versements_attendus(aujourd_hui)
        contexte.update(
            filtre=filtre,
            filtres_actifs=any(criteres.values()),
            page_obj=page,
            paginator=paginator,
            mouvements=page.object_list,
            soldes=soldes,
            comptes=CompteTresorerie.choices,
            versements=versements,
            solde_previsionnel=soldes["total"] + versements["total"],
            mois=services.synthese_periode(aujourd_hui.replace(day=1), aujourd_hui),
            peut_saisir=peut_saisir,
            form_mouvement=MouvementForm(initial={"date_mouvement": aujourd_hui}) if peut_saisir else None,
            form_annulation=MotifForm(),
        )
        return contexte


class TresorerieImprimerView(RoleRequiredMixin, TemplateView):
    """Rapport imprimable de la trésorerie : mêmes filtres que le journal, sans pagination.

    Le journal peut être long (l'historique complet) : plafonné comme les autres rapports
    (:class:`apps.core.views.ImpressionListeMixin`, même limite) pour rester imprimable.
    """

    roles = permissions.CONSULTATION
    template_name = "finance/tresorerie_print.html"
    limite = 500

    def get_context_data(self, **kwargs):
        filtre = FiltreTresorerieForm(self.request.GET)
        criteres = filtre.criteres()
        aujourd_hui = timezone.localdate()
        journal = services.mouvements(**criteres)
        tronque = len(journal) > self.limite
        debut = criteres["date_debut"] or aujourd_hui.replace(day=1)
        fin = criteres["date_fin"] or aujourd_hui
        morceaux = [f"Période : du {debut:%d/%m/%Y} au {fin:%d/%m/%Y}" if (criteres["date_debut"] or criteres["date_fin"]) else "Depuis le début du mois"]
        if criteres["compte"] in CompteTresorerie.values:
            morceaux.append(f"compte : {CompteTresorerie(criteres['compte']).label}")
        if criteres["sens"]:
            morceaux.append("entrées seulement" if criteres["sens"] == "ENTREE" else "sorties seulement")
        soldes = services.soldes_par_compte()
        contexte = contexte_rapport(self.request, titre="Trésorerie", sous_titre=" · ".join(morceaux))
        contexte.update(
            solde_total=soldes["total"],
            soldes_par_compte=[{"libelle": libelle, "montant": soldes[code]} for code, libelle in CompteTresorerie.choices],
            synthese=services.synthese_periode(debut, fin),
            periode_debut=debut,
            periode_fin=fin,
            journal=journal[: self.limite],
            nombre=min(len(journal), self.limite),
            tronque=tronque,
        )
        return contexte


class TresorerieExporterXlsxView(RoleRequiredMixin, View):
    """Export Excel du journal de trésorerie (règlements reçus, dépenses payées, mouvements manuels) : mêmes
    filtres que l'écran, montants signés (entrées positives, sorties négatives) pour pouvoir les additionner."""

    roles = permissions.CONSULTATION
    limite = 10000

    def get(self, request):
        criteres = FiltreTresorerieForm(request.GET).criteres()
        journal = services.mouvements(**criteres)
        lignes = [
            [
                m["date"], m["libelle"], m["origine"].capitalize(), m["mode_libelle"], m["reference"],
                m["montant"] if m["sens"] == SensMouvement.ENTREE else -m["montant"],
            ]
            for m in journal[: self.limite]
        ]
        aujourd_hui = timezone.localdate()
        debut = criteres["date_debut"] or aujourd_hui.replace(day=1)
        fin = criteres["date_fin"] or aujourd_hui
        feuille = {
            "titre": "Trésorerie",
            "sous_titre": f"du {debut:%d/%m/%Y} au {fin:%d/%m/%Y}",
            "entetes": ["Date", "Libellé", "Origine", "Mode", "Référence", "Montant (FCFA, entrée +, sortie -)"],
            "lignes": lignes,
            "pied": ["", "", "", "", "Total", sum((l[5] for l in lignes), Decimal("0"))],
        }
        return reponse_classeur("tresorerie", [feuille])


class MouvementCreateView(RoleRequiredMixin, View):
    roles = permissions.SAISIE
    http_method_names = ["post"]

    def post(self, request):
        form = MouvementForm(request.POST)
        if not form.is_valid():
            for erreurs in form.errors.values():
                for erreur in erreurs:
                    messages.error(request, erreur)
            return redirect("finance:tresorerie")
        try:
            mouvement = services.enregistrer_mouvement(request.user, **form.cleaned_data)
        except BillingError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(
                request, f"{mouvement.get_sens_display()} de {nombre(mouvement.montant)} FCFA enregistrée."
            )
        return redirect("finance:tresorerie")


class MouvementAnnulerView(RoleRequiredMixin, View):
    roles = permissions.SAISIE
    http_method_names = ["post"]

    def post(self, request, pk):
        mouvement = get_object_or_404(MouvementManuel, pk=pk)
        form = MotifForm(request.POST)
        if not form.is_valid():
            for erreurs in form.errors.values():
                for erreur in erreurs:
                    messages.error(request, erreur)
            return redirect("finance:tresorerie")
        try:
            services.annuler_mouvement(mouvement, request.user, motif=form.cleaned_data["motif"])
        except BillingError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, "Mouvement annulé.")
        return redirect("finance:tresorerie")


class VersementConfirmerView(RoleRequiredMixin, FormView):
    """La Finance confirme qu'un versement attendu (facture émise) a bien été reçu.

    Bouton des notifications « facture validée » et « facture échue », et des lignes de « Versements à
    confirmer » de la trésorerie. Formulaire prérempli avec le reste à recouvrer ; la confirmation
    ajoute une entrée à la trésorerie (règlement de la facture, sur le compte de son mode de paiement).
    """

    roles = permissions.SAISIE
    form_class = ReglementForm
    template_name = "finance/versement_confirmer.html"

    def dispatch(self, request, *args, **kwargs):
        self.facture = get_object_or_404(billing_services.factures_queryset(), pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        if self.facture.statut not in STATUTS_A_RECOUVRER:
            messages.info(request, f"La facture {self.facture.numero} n'attend plus de versement.")
            return redirect("finance:tresorerie")
        return super().get(request, *args, **kwargs)

    def get_initial(self):
        return {"montant": self.facture.reste, "date_reglement": timezone.localdate()}

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            facture=self.facture,
            regle=self.facture.montant_ttc - self.facture.reste,
            echue=billing_services.est_echue(self.facture),
        )
        return contexte

    def form_valid(self, form):
        try:
            reglement, compte = services.confirmer_versement(self.facture, self.request.user, **form.cleaned_data)
        except BillingError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(
            self.request,
            f"Versement de {nombre(reglement.montant)} FCFA confirmé : ajouté en entrée sur le compte "
            f"{compte.label} (facture {self.facture.numero}).",
        )
        return redirect("finance:tresorerie")


# --- dépenses du parc auto pré-approuvées (R2) ---


def _erreurs_en_messages(request, form):
    for erreurs in form.errors.values():
        for erreur in erreurs:
            messages.error(request, erreur)


class DemandeListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.DEMANDE_CONSULTATION
    template_name = "finance/demande_list.html"
    context_object_name = "demandes"
    paginate_by = 20

    def get_queryset(self):
        return demandes_services.demandes_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            peut_soumettre=self.request.user.role_effectif in permissions.DEMANDE_SAISIE,
            peut_definir_enveloppe=self.request.user.role_effectif in permissions.ENVELOPPE_VALIDATION,
        )
        return contexte


class DemandeCreateView(RoleRequiredMixin, FormView):
    roles = permissions.DEMANDE_SAISIE
    form_class = DemandeDepenseForm
    template_name = "finance/demande_form.html"

    def form_valid(self, form):
        try:
            demande = demandes_services.soumettre_demande(self.request.user, **form.cleaned_data)
        except BillingError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, f"Demande {demande.numero} soumise à la direction.")
        return redirect("finance:demande", pk=demande.pk)


class DemandeDetailView(RoleRequiredMixin, DetailView):
    roles = permissions.DEMANDE_CONSULTATION
    template_name = "finance/demande_detail.html"
    context_object_name = "demande"

    def get_queryset(self):
        return demandes_services.demandes_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        demande = self.object
        role = self.request.user.role
        ordre = OrdreDecaissement.objects.filter(demande=demande).select_related("execute_par").first()
        peut_decider = role in permissions.DEMANDE_VALIDATION and demande.statut == StatutDemandeDepense.SOUMISE
        peut_executer = (
            role in permissions.ORDRE_EXECUTION
            and ordre is not None and ordre.statut == StatutOrdreDecaissement.A_EXECUTER
        )
        peut_revalider = (
            role in permissions.DEMANDE_VALIDATION
            and ordre is not None and ordre.statut == StatutOrdreDecaissement.EN_ATTENTE_REVALIDATION
        )
        contexte.update(
            ordre=ordre,
            peut_decider=peut_decider,
            peut_executer=peut_executer,
            peut_revalider=peut_revalider,
            form_decision=DecisionDemandeForm() if peut_decider else None,
            form_executer=ExecuterOrdreForm() if peut_executer else None,
            form_revalider=(
                RevaliderOrdreForm(initial={"montant_valide": ordre.montant_reel}) if peut_revalider else None
            ),
        )
        return contexte


class DemandeDeciderView(RoleRequiredMixin, View):
    roles = permissions.DEMANDE_VALIDATION
    http_method_names = ["post"]

    def post(self, request, pk):
        demande = get_object_or_404(DemandeDepense, pk=pk)
        form = DecisionDemandeForm(request.POST)
        if not form.is_valid():
            _erreurs_en_messages(request, form)
            return redirect("finance:demande", pk=demande.pk)
        donnees = form.cleaned_data
        try:
            if donnees["decision"] == "VALIDER":
                demandes_services.valider_demande(
                    demande, request.user, montant_valide=donnees.get("montant_valide")
                )
                messages.success(request, "Demande validée.")
            else:
                demandes_services.refuser_demande(demande, request.user, motif=donnees["motif_refus"])
                messages.success(request, "Demande refusée.")
        except BillingError as erreur:
            messages.error(request, str(erreur))
        return redirect("finance:demande", pk=demande.pk)


class OrdreExecuterView(RoleRequiredMixin, View):
    roles = permissions.ORDRE_EXECUTION
    http_method_names = ["post"]

    def post(self, request, pk):
        ordre = get_object_or_404(OrdreDecaissement, pk=pk)
        form = ExecuterOrdreForm(request.POST, request.FILES)
        if not form.is_valid():
            _erreurs_en_messages(request, form)
            return redirect("finance:demande", pk=ordre.demande_id)
        try:
            demandes_services.executer_ordre(ordre, request.user, **form.cleaned_data)
        except BillingError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, f"Ordre {ordre.numero} exécuté : comptabilisé en dépense.")
        return redirect("finance:demande", pk=ordre.demande_id)


class OrdreRevaliderView(RoleRequiredMixin, View):
    roles = permissions.DEMANDE_VALIDATION
    http_method_names = ["post"]

    def post(self, request, pk):
        ordre = get_object_or_404(OrdreDecaissement, pk=pk)
        form = RevaliderOrdreForm(request.POST)
        if not form.is_valid():
            _erreurs_en_messages(request, form)
            return redirect("finance:demande", pk=ordre.demande_id)
        try:
            demandes_services.revalider_ordre(ordre, request.user, **form.cleaned_data)
        except BillingError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, "Ordre revalidé : la finance peut retenter l'exécution.")
        return redirect("finance:demande", pk=ordre.demande_id)


class EnveloppeListView(RoleRequiredMixin, ListView):
    roles = permissions.ENVELOPPE_VALIDATION
    template_name = "finance/enveloppe_list.html"
    context_object_name = "enveloppes"

    def get_queryset(self):
        return demandes_services.enveloppes_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        aujourd_hui = timezone.localdate()
        contexte["form"] = EnveloppeForm(initial={"annee": aujourd_hui.year, "mois": aujourd_hui.month})
        return contexte


class EnveloppeCreateView(RoleRequiredMixin, View):
    roles = permissions.ENVELOPPE_VALIDATION
    http_method_names = ["post"]

    def post(self, request):
        form = EnveloppeForm(request.POST)
        if not form.is_valid():
            _erreurs_en_messages(request, form)
            return redirect("finance:enveloppes")
        try:
            demandes_services.definir_enveloppe(request.user, **form.cleaned_data)
        except BillingError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, "Enveloppe enregistrée.")
        return redirect("finance:enveloppes")


# --- rapprochement bancaire (Lot G) ---


class RapprochementBancaireView(RoleRequiredMixin, TemplateView):
    roles = permissions.CONSULTATION
    template_name = "finance/rapprochement.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        periode_form = PeriodeRapprochementForm(self.request.GET)
        debut, fin = periode_form.periode()
        etat = services.rapprochement_bancaire(debut=debut, fin=fin)
        peut_saisir = self.request.user.role_effectif in permissions.SAISIE
        lignes_avec_suggestions = [
            {"ligne": ligne, "suggestions": services.suggestions_pointage(ligne)}
            for ligne in etat["lignes_non_pointees"]
        ]
        contexte.update(
            periode_form=periode_form,
            debut=debut,
            fin=fin,
            etat=etat,
            lignes_avec_suggestions=lignes_avec_suggestions,
            peut_saisir=peut_saisir,
            form_ligne=LigneReleveForm(initial={"date_operation": timezone.localdate()}) if peut_saisir else None,
            form_pointer=PointerLigneReleveForm() if peut_saisir else None,
        )
        return contexte


class LigneReleveCreateView(RoleRequiredMixin, View):
    roles = permissions.SAISIE
    http_method_names = ["post"]

    def post(self, request):
        form = LigneReleveForm(request.POST)
        if not form.is_valid():
            _erreurs_en_messages(request, form)
            return redirect("finance:rapprochement")
        try:
            services.saisir_ligne_releve(request.user, **form.cleaned_data)
        except BillingError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, "Ligne de relevé ajoutée.")
        return redirect("finance:rapprochement")


class LigneRelevePointerView(RoleRequiredMixin, View):
    roles = permissions.SAISIE
    http_method_names = ["post"]

    def post(self, request, pk):
        ligne = get_object_or_404(LigneReleve, pk=pk)
        form = PointerLigneReleveForm(request.POST)
        if not form.is_valid():
            _erreurs_en_messages(request, form)
            return redirect("finance:rapprochement")
        try:
            services.pointer_ligne_releve(ligne, request.user, **form.cleaned_data)
        except BillingError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, "Ligne pointée.")
        return redirect("finance:rapprochement")


class LigneReleveDepointerView(RoleRequiredMixin, View):
    roles = permissions.SAISIE
    http_method_names = ["post"]

    def post(self, request, pk):
        ligne = get_object_or_404(LigneReleve, pk=pk)
        try:
            services.depointer_ligne_releve(ligne, request.user)
        except BillingError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, "Pointage annulé.")
        return redirect("finance:rapprochement")
