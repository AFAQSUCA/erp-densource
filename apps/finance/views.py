"""Trésorerie : journal des mouvements, soldes par compte, mouvements manuels."""

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import FormView, TemplateView

from apps.accounts.mixins import RoleRequiredMixin
from apps.billing import services as billing_services
from apps.billing.exceptions import BillingError
from apps.billing.forms import ReglementForm
from apps.billing.models import STATUTS_A_RECOUVRER, CompteTresorerie
from apps.core.formats import nombre

from . import permissions, services
from .forms import FiltreTresorerieForm, MotifForm, MouvementForm
from .models import MouvementManuel


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
