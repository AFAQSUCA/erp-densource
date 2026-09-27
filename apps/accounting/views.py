"""Écrans de la saisie manuelle d'opérations diverses (Phase 4), de la clôture d'exercice
(Phase 5) et des rapports en lecture seule — grand livre, balance, bilan, compte de résultat
(Phase 6).

Aucune règle métier ici : les vues contrôlent le rôle, lisent le formulaire et délèguent à
``services.py`` (conventions.md:19-23).
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, FormView, ListView, TemplateView

from apps.accounts.mixins import RoleRequiredMixin
from apps.core.views import PaginationTolerante

from . import permissions, services
from .exceptions import AccountingError
from .forms import EcritureManuelleForm, GrandLivreForm, LigneManuelleForm, PeriodeForm
from .models import EcritureComptable, ExerciceComptable, Journal, LigneEcriture, SensEcriture, StatutEcriture


def _erreurs_en_messages(request, form):
    for erreurs in form.errors.values():
        for erreur in erreurs:
            messages.error(request, erreur)


def _ecritures_manuelles_queryset():
    return EcritureComptable.objects.filter(journal=Journal.OPERATIONS_DIVERSES)


class EcritureManuelleListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "accounting/ecriture_manuelle_list.html"
    context_object_name = "ecritures"
    paginate_by = 20

    def get_queryset(self):
        return _ecritures_manuelles_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["peut_saisir"] = self.request.user.role_effectif in permissions.SAISIE_OD
        return contexte


class EcritureManuelleCreateView(RoleRequiredMixin, FormView):
    roles = permissions.SAISIE_OD
    form_class = EcritureManuelleForm
    template_name = "accounting/ecriture_manuelle_form.html"

    def form_valid(self, form):
        ecriture = services.creer_ecriture_manuelle(self.request.user, **form.cleaned_data)
        messages.success(self.request, "Brouillon créé : ajoutez au moins deux lignes équilibrées.")
        return redirect("accounting:ecriture_manuelle", pk=ecriture.pk)


class EcritureManuelleDetailView(RoleRequiredMixin, DetailView):
    roles = permissions.CONSULTATION
    template_name = "accounting/ecriture_manuelle_detail.html"
    context_object_name = "ecriture"

    def get_queryset(self):
        return _ecritures_manuelles_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        ecriture = self.object
        role = self.request.user.role_effectif
        est_brouillon = ecriture.statut == StatutEcriture.BROUILLON
        peut_saisir = role in permissions.SAISIE_OD and est_brouillon
        lignes = list(ecriture.lignes.select_related("compte"))
        total_debit = sum((l.montant for l in lignes if l.sens == SensEcriture.DEBIT), start=0)
        total_credit = sum((l.montant for l in lignes if l.sens == SensEcriture.CREDIT), start=0)
        contexte.update(
            lignes=lignes,
            total_debit=total_debit,
            total_credit=total_credit,
            equilibree=len(lignes) >= 2 and total_debit == total_credit,
            peut_saisir=peut_saisir,
            peut_valider=(
                self.request.user.role in permissions.VALIDATION_OD
                and est_brouillon
                and len(lignes) >= 2
                and total_debit == total_credit
            ),
            form_ligne=LigneManuelleForm() if peut_saisir else None,
        )
        return contexte


class LigneAjouterView(RoleRequiredMixin, View):
    roles = permissions.SAISIE_OD
    http_method_names = ["post"]

    def post(self, request, pk):
        ecriture = get_object_or_404(_ecritures_manuelles_queryset(), pk=pk)
        form = LigneManuelleForm(request.POST)
        if not form.is_valid():
            _erreurs_en_messages(request, form)
            return redirect("accounting:ecriture_manuelle", pk=pk)
        donnees = form.cleaned_data
        try:
            services.ajouter_ligne_manuelle(
                ecriture, request.user, compte=donnees["compte"].numero, sens=donnees["sens"],
                montant=donnees["montant"], libelle=donnees["libelle"],
            )
        except AccountingError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, "Ligne ajoutée.")
        return redirect("accounting:ecriture_manuelle", pk=pk)


class LigneSupprimerView(RoleRequiredMixin, View):
    roles = permissions.SAISIE_OD
    http_method_names = ["post"]

    def post(self, request, pk, ligne_pk):
        ecriture = get_object_or_404(_ecritures_manuelles_queryset(), pk=pk)
        ligne = get_object_or_404(LigneEcriture, pk=ligne_pk, ecriture=ecriture)
        try:
            services.supprimer_ligne_manuelle(ligne, request.user)
        except AccountingError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, "Ligne supprimée.")
        return redirect("accounting:ecriture_manuelle", pk=pk)


class EcritureManuelleValiderView(RoleRequiredMixin, View):
    roles = permissions.VALIDATION_OD
    http_method_names = ["post"]

    def post(self, request, pk):
        ecriture = get_object_or_404(_ecritures_manuelles_queryset(), pk=pk)
        try:
            services.valider_ecriture_manuelle(ecriture, request.user)
        except AccountingError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, f"Écriture {ecriture.numero} validée.")
        return redirect("accounting:ecriture_manuelle", pk=pk)


class EcritureManuelleAbandonnerView(RoleRequiredMixin, View):
    roles = permissions.SAISIE_OD
    http_method_names = ["post"]

    def post(self, request, pk):
        ecriture = get_object_or_404(_ecritures_manuelles_queryset(), pk=pk)
        try:
            services.abandonner_ecriture_manuelle(ecriture, request.user)
        except AccountingError as erreur:
            messages.error(request, str(erreur))
            return redirect("accounting:ecriture_manuelle", pk=pk)
        messages.success(request, "Brouillon abandonné.")
        return redirect("accounting:ecritures_manuelles")


class ExerciceListView(RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "accounting/exercice_list.html"
    context_object_name = "exercices"

    def get_queryset(self):
        return ExerciceComptable.objects.all()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["peut_cloturer"] = self.request.user.role in permissions.CLOTURE_EXERCICE
        return contexte


class ExerciceCloturerView(RoleRequiredMixin, View):
    roles = permissions.CLOTURE_EXERCICE
    http_method_names = ["post"]

    def post(self, request, pk):
        exercice = get_object_or_404(ExerciceComptable, pk=pk)
        try:
            services.cloturer_exercice(exercice, request.user)
        except AccountingError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, f"Exercice {exercice.annee} clôturé.")
        return redirect("accounting:exercices")


class GrandLivreView(RoleRequiredMixin, TemplateView):
    roles = permissions.CONSULTATION
    template_name = "accounting/grand_livre.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        form = GrandLivreForm(self.request.GET or None)
        lignes = None
        if form.is_valid() and form.cleaned_data.get("compte"):
            lignes = services.grand_livre_avec_solde(
                form.cleaned_data["compte"],
                debut=form.cleaned_data.get("debut"),
                fin=form.cleaned_data.get("fin"),
            )
        contexte.update(form=form, lignes=lignes)
        return contexte


class BalanceView(RoleRequiredMixin, TemplateView):
    roles = permissions.CONSULTATION
    template_name = "accounting/balance.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        form = PeriodeForm(self.request.GET or None)
        debut = fin = None
        if form.is_valid():
            debut, fin = form.cleaned_data.get("debut"), form.cleaned_data.get("fin")
        lignes = services.balance(debut=debut, fin=fin)
        totaux = {
            "debit": sum((l["total_debit"] for l in lignes), start=0),
            "credit": sum((l["total_credit"] for l in lignes), start=0),
        }
        contexte.update(form=form, lignes=lignes, totaux=totaux)
        return contexte


class _RapportExerciceView(RoleRequiredMixin, TemplateView):
    """Un rapport (bilan, compte de résultat) porte toujours sur un exercice choisi dans la
    liste existante — le plus récent par défaut."""

    roles = permissions.CONSULTATION

    def get_exercice(self):
        exercices = ExerciceComptable.objects.order_by("-annee")
        annee = self.request.GET.get("exercice")
        if annee:
            exercice = exercices.filter(annee=annee).first()
            if exercice is not None:
                return exercice, exercices
        return exercices.first(), exercices


class BilanView(_RapportExerciceView):
    template_name = "accounting/bilan.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        exercice, exercices = self.get_exercice()
        contexte.update(
            exercices=exercices,
            exercice=exercice,
            rapport=services.bilan(exercice) if exercice else None,
        )
        return contexte


class CompteDeResultatView(_RapportExerciceView):
    template_name = "accounting/compte_resultat.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        exercice, exercices = self.get_exercice()
        contexte.update(
            exercices=exercices,
            exercice=exercice,
            rapport=services.compte_de_resultat(exercice) if exercice else None,
        )
        return contexte
