"""Écrans de la saisie manuelle d'opérations diverses (Phase 4), de la clôture d'exercice
(Phase 5) et des rapports en lecture seule — grand livre, balance, bilan, compte de résultat
(Phase 6).

Aucune règle métier ici : les vues contrôlent le rôle, lisent le formulaire et délèguent à
``services.py`` (conventions.md:19-23).
"""

import calendar

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, FormView, ListView, TemplateView

from apps.accounts.mixins import RoleRequiredMixin
from apps.core.rapports import contexte_rapport
from apps.core.views import PaginationTolerante

from . import permissions, services
from .exceptions import AccountingError, CompteDejaExistant
from .forms import CompteForm, CompteModifierForm, EcritureManuelleForm, GrandLivreForm, LigneManuelleForm, PeriodeForm
from .models import Compte, EcritureComptable, ExerciceComptable, Journal, LigneEcriture, SensEcriture, StatutEcriture


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


class PlanComptableListView(RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "accounting/plan_comptable_list.html"
    context_object_name = "comptes"

    def get_queryset(self):
        return Compte.objects.all()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["peut_gerer"] = self.request.user.role_effectif in permissions.GESTION_PLAN_COMPTABLE
        return contexte


class CompteCreateView(RoleRequiredMixin, FormView):
    roles = permissions.GESTION_PLAN_COMPTABLE
    form_class = CompteForm
    template_name = "accounting/compte_form.html"

    def form_valid(self, form):
        try:
            services.creer_compte(self.request.user, **form.cleaned_data)
        except CompteDejaExistant as erreur:
            form.add_error("numero", str(erreur))
            return self.form_invalid(form)
        except AccountingError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, "Compte créé.")
        return redirect("accounting:plan_comptable")


class CompteModifierView(RoleRequiredMixin, FormView):
    roles = permissions.GESTION_PLAN_COMPTABLE
    form_class = CompteModifierForm
    template_name = "accounting/compte_modifier_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.compte = get_object_or_404(Compte, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        return {"libelle": self.compte.libelle, "actif": self.compte.actif}

    def get_context_data(self, **kwargs):
        return super().get_context_data(compte=self.compte, **kwargs)

    def form_valid(self, form):
        try:
            services.modifier_compte(self.compte, self.request.user, **form.cleaned_data)
        except AccountingError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, "Compte modifié.")
        return redirect("accounting:plan_comptable")


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


class GrandLivreImprimerView(RoleRequiredMixin, TemplateView):
    roles = permissions.CONSULTATION
    template_name = "accounting/grand_livre_print.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        form = GrandLivreForm(self.request.GET or None)
        compte = lignes = None
        morceaux = []
        if form.is_valid() and form.cleaned_data.get("compte"):
            compte = form.cleaned_data["compte"]
            debut, fin = form.cleaned_data.get("debut"), form.cleaned_data.get("fin")
            lignes = services.grand_livre_avec_solde(compte, debut=debut, fin=fin)
            morceaux.append(f"{compte.numero} — {compte.libelle}")
            if debut or fin:
                debut_texte = f"{debut:%d/%m/%Y}" if debut else "l'origine"
                fin_texte = f"{fin:%d/%m/%Y}" if fin else "aujourd'hui"
                morceaux.append(f"du {debut_texte} au {fin_texte}")
        rapport = contexte_rapport(self.request, titre="Grand livre", sous_titre=" · ".join(morceaux))
        contexte.update(rapport, compte=compte, lignes=lignes)
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


class BalanceImprimerView(RoleRequiredMixin, TemplateView):
    roles = permissions.CONSULTATION
    template_name = "accounting/balance_print.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        form = PeriodeForm(self.request.GET or None)
        debut = fin = None
        if form.is_valid():
            debut, fin = form.cleaned_data.get("debut"), form.cleaned_data.get("fin")
        if debut or fin:
            debut_texte = f"{debut:%d/%m/%Y}" if debut else "l'origine"
            fin_texte = f"{fin:%d/%m/%Y}" if fin else "aujourd'hui"
            sous_titre = f"du {debut_texte} au {fin_texte}"
        else:
            sous_titre = "Depuis l'origine"
        lignes = services.balance(debut=debut, fin=fin)
        totaux = {
            "debit": sum((l["total_debit"] for l in lignes), start=0),
            "credit": sum((l["total_credit"] for l in lignes), start=0),
        }
        rapport = contexte_rapport(self.request, titre="Balance générale", sous_titre=sous_titre)
        contexte.update(rapport, lignes=lignes, totaux=totaux)
        return contexte


def _periode_declaration_tva(form):
    """Période d'une déclaration TVA : toujours bornée, le mois en cours par défaut (une
    déclaration ne porte jamais sur « depuis l'origine », contrairement à la balance)."""
    debut = fin = None
    if form.is_valid():
        debut, fin = form.cleaned_data.get("debut"), form.cleaned_data.get("fin")
    if debut is None and fin is None:
        aujourd_hui = timezone.localdate()
        debut = aujourd_hui.replace(day=1)
        fin = aujourd_hui.replace(day=calendar.monthrange(aujourd_hui.year, aujourd_hui.month)[1])
    elif debut is None:
        debut = fin.replace(day=1)
    elif fin is None:
        fin = debut.replace(day=calendar.monthrange(debut.year, debut.month)[1])
    return debut, fin


class DeclarationTvaView(RoleRequiredMixin, TemplateView):
    roles = permissions.CONSULTATION
    template_name = "accounting/declaration_tva.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        form = PeriodeForm(self.request.GET or None)
        debut, fin = _periode_declaration_tva(form)
        contexte.update(form=form, rapport=services.declaration_tva(debut=debut, fin=fin))
        return contexte


class DeclarationTvaImprimerView(RoleRequiredMixin, TemplateView):
    roles = permissions.CONSULTATION
    template_name = "accounting/declaration_tva_print.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        form = PeriodeForm(self.request.GET or None)
        debut, fin = _periode_declaration_tva(form)
        sous_titre = f"du {debut:%d/%m/%Y} au {fin:%d/%m/%Y}"
        rapport = contexte_rapport(self.request, titre="Déclaration TVA", sous_titre=sous_titre)
        contexte.update(rapport, rapport_tva=services.declaration_tva(debut=debut, fin=fin))
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


class BilanImprimerView(_RapportExerciceView):
    template_name = "accounting/bilan_print.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        exercice, _ = self.get_exercice()
        sous_titre = f"Exercice {exercice.annee}, au {exercice.date_fin:%d/%m/%Y}" if exercice else ""
        rapport = contexte_rapport(self.request, titre="Bilan", sous_titre=sous_titre)
        contexte.update(
            rapport,
            exercice=exercice,
            rapport_bilan=services.bilan(exercice) if exercice else None,
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


class CompteDeResultatImprimerView(_RapportExerciceView):
    template_name = "accounting/compte_resultat_print.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        exercice, _ = self.get_exercice()
        sous_titre = (
            f"Exercice {exercice.annee}, du {exercice.date_debut:%d/%m/%Y} au {exercice.date_fin:%d/%m/%Y}"
            if exercice else ""
        )
        rapport = contexte_rapport(self.request, titre="Compte de résultat", sous_titre=sous_titre)
        contexte.update(
            rapport,
            exercice=exercice,
            rapport_resultat=services.compte_de_resultat(exercice) if exercice else None,
        )
        return contexte
