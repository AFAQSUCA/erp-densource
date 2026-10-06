# Chapitre 27 — Écrans : plan comptable, opérations diverses et rapports comptables

> 26 fichier(s) dans ce chapitre, 2700 lignes de code.

## Ce que vous allez construire

Les **écrans de la comptabilité** : le plan comptable, la saisie manuelle d'opérations diverses (avec son
cycle brouillon → validation par la DIRECTION), la clôture d'un exercice, et cinq rapports en lecture
seule.

| Écran | Adresse | Qui |
|---|---|---|
| **Plan comptable** (liste, création, modification) | `/comptabilite/plan-comptable/` | consultation : ADMIN, DIRECTION, FINANCES, RH ; gestion : mêmes rôles |
| **Opérations diverses** (liste, **brouillon**, ajout/retrait de ligne, validation, abandon) | `/comptabilite/operations-diverses/` | saisie : mêmes rôles ; validation : **DIRECTION seule** |
| **Exercices comptables** (liste, clôture) | `/comptabilite/exercices/` | consultation : mêmes rôles ; clôture : **DIRECTION seule** |
| **Grand livre** d'un compte | `/comptabilite/grand-livre/` | consultation |
| **Balance** générale | `/comptabilite/balance/` | consultation |
| **Bilan** et **compte de résultat** (par exercice) | `/comptabilite/bilan/`, `/comptabilite/compte-de-resultat/` | consultation |
| **Déclaration TVA** (par période, le mois en cours par défaut) | `/comptabilite/declaration-tva/` | consultation |

Chacun des 5 rapports a sa **version imprimable** (`.../imprimer/`), accessible depuis le menu « Rapports
comptables ».

Chaque rapport (grand livre, balance, bilan, compte de résultat, déclaration TVA) a aussi un bouton **Excel**. Sur une opération
diverse **validée**, la **DIRECTION** voit un bloc « Corriger cette écriture » : la contre-passation pose l'écriture inverse
(motif obligatoire, une seule fois) ; une écriture automatique (facture, règlement…) se corrige, elle, à la source.

## Prérequis

- Chapitres 1 à 26 terminés.

## Ce que ce chapitre apporte de nouveau

- **Un formulaire qui gagne son propre queryset dans `__init__`** : `GrandLivreForm.compte` et
  `LigneManuelleForm.compte` fixent `self.fields["compte"].queryset` après coup, pour ne lister que les
  comptes **actifs** — impossible à exprimer comme attribut de classe (le queryset serait figé au
  chargement du module, avant toute migration).
- **Une fiche à deux formulaires imbriqués** : `EcritureManuelleDetailView` affiche l'écriture **et**,
  si l'utilisateur peut encore saisir, un formulaire d'ajout de ligne (`LigneAjouterView`, une vue à part,
  en POST). `peut_saisir`, `peut_valider` et `equilibree` sont calculés **une fois**, dans
  `get_context_data`, jamais recalculés dans le gabarit.
- **Un rapport toujours borné à un exercice existant** : `_RapportExerciceView.get_exercice` choisit
  l'exercice demandé en paramètre `?exercice=`, ou **le plus récent** à défaut — jamais « aucun exercice »
  tant qu'au moins un existe.
- **Cinq rapports, un seul gabarit de navigation** (`_nav_rapports.html`, inclus par chacun) : l'onglet
  actif se déduit de `request.resolver_match.url_name`, sans variable de contexte dédiée.
- **La version imprimable réutilise le même service** que l'écran, avec `core.rapports.contexte_rapport`
  pour l'en-tête (entreprise, titre, généré le/par) — même mécanisme que `billing`/`finance` au
  chapitre 26.

## Étape 1 — Formulaires

#### `apps/accounting/forms.py`

*71 lignes*

```python
from django import forms
from django.utils import timezone

from apps.core.forms import StyleTailwindMixin

from .models import Compte, NatureCompte, SensEcriture


class PeriodeForm(StyleTailwindMixin, forms.Form):
    """Filtre de période, facultatif : la balance ou le grand livre portent sur toutes les dates
    connues si les deux champs sont vides."""

    debut = forms.DateField(label="Du", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    fin = forms.DateField(label="Au", required=False, widget=forms.DateInput(attrs={"type": "date"}))


class GrandLivreForm(PeriodeForm):
    """Choix du compte à consulter, plus la période facultative de ``PeriodeForm``."""

    compte = forms.ModelChoiceField(queryset=None, label="Compte", to_field_name="numero")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["compte"].queryset = Compte.objects.order_by("numero")
        self.fields["compte"].label_from_instance = lambda c: f"{c.numero} — {c.libelle}"


class CompteForm(StyleTailwindMixin, forms.Form):
    """Ajout d'un compte au plan comptable : numéro et nature ne se saisissent qu'ici, ils ne se
    modifient plus ensuite (voir ``services.modifier_compte``)."""

    numero = forms.CharField(label="Numéro", max_length=10)
    libelle = forms.CharField(label="Libellé", max_length=150)
    nature = forms.ChoiceField(label="Nature", choices=NatureCompte.choices)


class CompteModifierForm(StyleTailwindMixin, forms.Form):
    """Correction du libellé et activation/désactivation d'un compte existant."""

    libelle = forms.CharField(label="Libellé", max_length=150)
    actif = forms.BooleanField(label="Actif (utilisable dans une nouvelle écriture)", required=False)


class EcritureManuelleForm(StyleTailwindMixin, forms.Form):
    """Ouverture d'un brouillon d'opération diverse : date et libellé seulement, les lignes
    s'ajoutent ensuite une par une sur la fiche."""

    date_ecriture = forms.DateField(label="Date", widget=forms.DateInput(attrs={"type": "date"}))
    libelle = forms.CharField(label="Libellé", max_length=255)

    def clean_date_ecriture(self):
        jour = self.cleaned_data["date_ecriture"]
        if jour > timezone.localdate():
            raise forms.ValidationError("La date ne peut pas être dans le futur.")
        return jour


class LigneManuelleForm(StyleTailwindMixin, forms.Form):
    """Une ligne débit ou crédit ajoutée à un brouillon d'opération diverse."""

    compte = forms.ModelChoiceField(
        queryset=None, label="Compte", to_field_name="numero", empty_label=None
    )
    sens = forms.ChoiceField(label="Sens", choices=SensEcriture.choices)
    montant = forms.DecimalField(label="Montant (FCFA)", min_value=0.01, decimal_places=2, max_digits=14)
    libelle = forms.CharField(label="Libellé", max_length=255, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["compte"].queryset = Compte.objects.filter(actif=True)
        self.fields["compte"].label_from_instance = lambda c: f"{c.numero} — {c.libelle}"
```

`PeriodeForm` (début/fin facultatifs) est la base de `GrandLivreForm` (qui y ajoute le compte) et sert
telle quelle à la balance et à la déclaration TVA. `EcritureManuelleForm` et `LigneManuelleForm`
couvrent la saisie manuelle ; `CompteForm` et `CompteModifierForm`, le plan comptable.

## Étape 2 — Vues et adresses

#### `apps/accounting/views.py`

*617 lignes* — Écrans de la saisie manuelle d'opérations diverses (Phase 4), de la clôture d'exercice

```python
"""Écrans de la saisie manuelle d'opérations diverses (Phase 4), de la clôture d'exercice
(Phase 5) et des rapports en lecture seule — grand livre, balance, bilan, compte de résultat
(Phase 6).

Aucune règle métier ici : les vues contrôlent le rôle, lisent le formulaire et délèguent à
``services.py`` (conventions.md:19-23).
"""

import calendar

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, FormView, ListView, TemplateView

from apps.accounts.mixins import RoleRequiredMixin
from apps.core.rapports import contexte_rapport
from apps.core.views import PaginationTolerante
from apps.core.xlsx import reponse_classeur

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
            contre_passation=services.contre_passation_de(ecriture) if ecriture.statut == StatutEcriture.VALIDEE else None,
            peut_contre_passer=(
                self.request.user.role in permissions.VALIDATION_OD
                and ecriture.statut == StatutEcriture.VALIDEE
                and not ecriture.origine
                and services.contre_passation_de(ecriture) is None
            ),
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


class EcritureManuelleContrePasserView(RoleRequiredMixin, View):
    roles = permissions.VALIDATION_OD
    http_method_names = ["post"]

    def post(self, request, pk):
        ecriture = get_object_or_404(_ecritures_manuelles_queryset(), pk=pk)
        try:
            inverse = services.contre_passer_ecriture_manuelle(
                ecriture, request.user, motif=request.POST.get("motif", "")
            )
        except AccountingError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, f"Écriture {ecriture.numero} contre-passée par {inverse.numero}.")
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


class GrandLivreXlsxView(RoleRequiredMixin, View):
    roles = permissions.CONSULTATION

    def get(self, request):
        form = GrandLivreForm(request.GET or None)
        if not (form.is_valid() and form.cleaned_data.get("compte")):
            raise Http404("Choisissez un compte.")
        compte = form.cleaned_data["compte"]
        lignes = services.grand_livre_avec_solde(
            compte, debut=form.cleaned_data.get("debut"), fin=form.cleaned_data.get("fin")
        )
        feuille = {
            "titre": f"Grand livre {compte.numero}",
            "sous_titre": f"{compte.numero} — {compte.libelle}",
            "entetes": ["Date", "Écriture", "Pièce", "Libellé", "Débit", "Crédit", "Solde cumulé (débit +, crédit -)"],
            "lignes": [
                [
                    l["ligne"].ecriture.date_ecriture, l["ligne"].ecriture.numero, l["ligne"].ecriture.piece_reference,
                    l["ligne"].libelle or l["ligne"].ecriture.libelle,
                    l["ligne"].montant if l["ligne"].sens == SensEcriture.DEBIT else None,
                    l["ligne"].montant if l["ligne"].sens == SensEcriture.CREDIT else None,
                    l["solde_cumule"],
                ]
                for l in lignes
            ],
        }
        return reponse_classeur(f"grand_livre_{compte.numero}", [feuille])


class BalanceXlsxView(RoleRequiredMixin, View):
    roles = permissions.CONSULTATION

    def get(self, request):
        form = PeriodeForm(request.GET or None)
        debut = fin = None
        if form.is_valid():
            debut, fin = form.cleaned_data.get("debut"), form.cleaned_data.get("fin")
        lignes = services.balance(debut=debut, fin=fin)
        periode = (
            f"du {debut:%d/%m/%Y}" if debut else "depuis l'origine"
        ) + (f" au {fin:%d/%m/%Y}" if fin else "")
        feuille = {
            "titre": "Balance générale",
            "sous_titre": periode,
            "entetes": ["Compte", "Libellé", "Total débit", "Total crédit", "Solde débiteur", "Solde créditeur"],
            "lignes": [
                [
                    l["compte__numero"], l["compte__libelle"], l["total_debit"], l["total_credit"],
                    l["solde_debiteur"], l["solde_crediteur"],
                ]
                for l in lignes
            ],
            "pied": [
                "", "Total",
                sum((l["total_debit"] for l in lignes), 0), sum((l["total_credit"] for l in lignes), 0),
                sum((l["solde_debiteur"] for l in lignes), 0), sum((l["solde_crediteur"] for l in lignes), 0),
            ],
        }
        return reponse_classeur("balance", [feuille])


class _RapportExerciceXlsxView(RoleRequiredMixin, View):
    roles = permissions.CONSULTATION

    def exercice(self, request):
        exercices = ExerciceComptable.objects.order_by("-annee")
        annee = request.GET.get("exercice")
        exercice = (exercices.filter(annee=annee).first() if annee else None) or exercices.first()
        if exercice is None:
            raise Http404("Aucun exercice.")
        return exercice


class BilanXlsxView(_RapportExerciceXlsxView):
    def get(self, request):
        exercice = self.exercice(request)
        rapport = services.bilan(exercice)
        passif = [[l["compte__numero"], l["compte__libelle"], l["montant"]] for l in rapport["passif"]]
        if rapport["resultat_net"]:
            passif.append(["", "Résultat en cours, pas encore viré au 120000 (calculé)", rapport["resultat_net"]])
        actif = [[l["compte__numero"], l["compte__libelle"], l["montant"]] for l in rapport["actif"]]
        sous_titre = f"Exercice {exercice.annee}, au {exercice.date_fin:%d/%m/%Y}"
        entetes = ["Compte", "Libellé", "Montant"]
        return reponse_classeur(
            f"bilan_{exercice.annee}",
            [
                {"titre": "Actif", "sous_titre": sous_titre, "entetes": entetes, "lignes": actif,
                 "pied": ["", "Total actif", rapport["total_actif"]]},
                {"titre": "Passif", "sous_titre": sous_titre, "entetes": entetes, "lignes": passif,
                 "pied": ["", "Total passif", rapport["total_passif_avec_resultat"]]},
            ],
        )


class CompteDeResultatXlsxView(_RapportExerciceXlsxView):
    def get(self, request):
        exercice = self.exercice(request)
        rapport = services.compte_de_resultat(exercice)
        sous_titre = f"Exercice {exercice.annee}"
        entetes = ["Compte", "Libellé", "Montant"]
        return reponse_classeur(
            f"compte_de_resultat_{exercice.annee}",
            [
                {"titre": "Produits", "sous_titre": sous_titre, "entetes": entetes,
                 "lignes": [[l["compte__numero"], l["compte__libelle"], l["montant"]] for l in rapport["produits"]],
                 "pied": ["", "Total produits", rapport["total_produits"]]},
                {"titre": "Charges", "sous_titre": sous_titre, "entetes": entetes,
                 "lignes": [[l["compte__numero"], l["compte__libelle"], l["montant"]] for l in rapport["charges"]],
                 "pied": ["", "Total charges", rapport["total_charges"]]},
                {"titre": "Résultat", "sous_titre": sous_titre, "entetes": ["Libellé", "Montant"],
                 "lignes": [["Résultat net (bénéfice si positif)", rapport["resultat_net"]]]},
            ],
        )


class DeclarationTvaXlsxView(RoleRequiredMixin, View):
    roles = permissions.CONSULTATION

    def get(self, request):
        debut, fin = _periode_declaration_tva(PeriodeForm(request.GET or None))
        rapport = services.declaration_tva(debut=debut, fin=fin)
        feuille = {
            "titre": "Déclaration TVA",
            "sous_titre": f"du {debut:%d/%m/%Y} au {fin:%d/%m/%Y}",
            "entetes": ["Libellé", "Montant (FCFA)"],
            "lignes": [
                ["TVA collectée (443300)", rapport["tva_collectee"]],
                ["TVA déductible (445200)", rapport["tva_deductible"]],
                ["TVA nette à payer (négatif : crédit de TVA)", rapport["tva_nette"]],
            ],
        }
        return reponse_classeur("declaration_tva", [feuille])


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
```

Repérez `EcritureManuelleDetailView.get_context_data` : c'est elle qui décide, pour le gabarit, **ce que
la personne peut faire** (`peut_saisir`, `peut_valider`) à partir du statut de l'écriture et du rôle
effectif — jamais le gabarit. `_RapportExerciceView` factorise le choix de l'exercice pour `BilanView`,
`BilanImprimerView`, `CompteDeResultatView` et `CompteDeResultatImprimerView`.

#### `apps/accounting/urls.py`

*36 lignes*

```python
from django.urls import path

from . import views

app_name = "accounting"

urlpatterns = [
    path("operations-diverses/", views.EcritureManuelleListView.as_view(), name="ecritures_manuelles"),
    path("operations-diverses/nouvelle/", views.EcritureManuelleCreateView.as_view(), name="ecriture_manuelle_nouvelle"),
    path("operations-diverses/<int:pk>/", views.EcritureManuelleDetailView.as_view(), name="ecriture_manuelle"),
    path("operations-diverses/<int:pk>/valider/", views.EcritureManuelleValiderView.as_view(), name="ecriture_manuelle_valider"),
    path("operations-diverses/<int:pk>/contre-passer/", views.EcritureManuelleContrePasserView.as_view(), name="ecriture_manuelle_contre_passer"),
    path("operations-diverses/<int:pk>/abandonner/", views.EcritureManuelleAbandonnerView.as_view(), name="ecriture_manuelle_abandonner"),
    path("operations-diverses/<int:pk>/lignes/", views.LigneAjouterView.as_view(), name="ligne_ajouter"),
    path("operations-diverses/<int:pk>/lignes/<int:ligne_pk>/supprimer/", views.LigneSupprimerView.as_view(), name="ligne_supprimer"),
    path("exercices/", views.ExerciceListView.as_view(), name="exercices"),
    path("exercices/<int:pk>/cloturer/", views.ExerciceCloturerView.as_view(), name="exercice_cloturer"),
    path("plan-comptable/", views.PlanComptableListView.as_view(), name="plan_comptable"),
    path("plan-comptable/nouveau/", views.CompteCreateView.as_view(), name="compte_nouveau"),
    path("plan-comptable/<int:pk>/modifier/", views.CompteModifierView.as_view(), name="compte_modifier"),
    path("grand-livre/", views.GrandLivreView.as_view(), name="grand_livre"),
    path("grand-livre/imprimer/", views.GrandLivreImprimerView.as_view(), name="grand_livre_imprimer"),
    path("grand-livre/excel/", views.GrandLivreXlsxView.as_view(), name="grand_livre_xlsx"),
    path("balance/", views.BalanceView.as_view(), name="balance"),
    path("balance/imprimer/", views.BalanceImprimerView.as_view(), name="balance_imprimer"),
    path("balance/excel/", views.BalanceXlsxView.as_view(), name="balance_xlsx"),
    path("bilan/", views.BilanView.as_view(), name="bilan"),
    path("bilan/imprimer/", views.BilanImprimerView.as_view(), name="bilan_imprimer"),
    path("bilan/excel/", views.BilanXlsxView.as_view(), name="bilan_xlsx"),
    path("compte-de-resultat/", views.CompteDeResultatView.as_view(), name="compte_resultat"),
    path("compte-de-resultat/imprimer/", views.CompteDeResultatImprimerView.as_view(), name="compte_resultat_imprimer"),
    path("compte-de-resultat/excel/", views.CompteDeResultatXlsxView.as_view(), name="compte_resultat_xlsx"),
    path("declaration-tva/", views.DeclarationTvaView.as_view(), name="declaration_tva"),
    path("declaration-tva/imprimer/", views.DeclarationTvaImprimerView.as_view(), name="declaration_tva_imprimer"),
    path("declaration-tva/excel/", views.DeclarationTvaXlsxView.as_view(), name="declaration_tva_xlsx"),
]
```

#### `config/urls.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/urls.py (avant)
+++ config/urls.py (après)
@@ -28,4 +28,5 @@
     path("facturation/", include("apps.billing.urls")),
     path("finances/", include("apps.finance.urls")),
+    path("comptabilite/", include("apps.accounting.urls")),
     path("audit/", include("apps.audit.urls")),
     path("notifications/", include("apps.notifications.urls")),
```

## Étape 3 — Gabarits

```bash
mkdir -p apps/accounting/templates/accounting
```

#### `apps/accounting/templates/accounting/plan_comptable_list.html`

*56 lignes*

```django
{% extends "base.html" %}
{% load ui %}
{% block titre %}Plan comptable{% endblock %}
{% block entete %}Comptabilité{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-4xl">
  <div class="flex flex-wrap items-start justify-between gap-3">
    <div>
      <h1 class="text-2xl font-bold text-slate-900">Plan comptable</h1>
      <p class="mt-1 text-sm text-slate-600">
        Liste de départ à valider par un expert-comptable avant mise en production. Un compte ne
        se supprime jamais, il se désactive seulement (son historique reste lisible dans le grand
        livre).
      </p>
    </div>
    {% if peut_gerer %}
      <a href="{% url 'accounting:compte_nouveau' %}" class="inline-flex items-center gap-2 rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
        <i class="fa-solid fa-plus" aria-hidden="true"></i> Nouveau compte
      </a>
    {% endif %}
  </div>

  <div class="mt-5 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
    <table class="min-w-full divide-y divide-slate-200 text-sm">
      <caption class="sr-only">Plan comptable</caption>
      <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
        <tr>
          <th scope="col" class="px-4 py-3">Numéro</th>
          <th scope="col" class="px-4 py-3">Libellé</th>
          <th scope="col" class="px-4 py-3">Nature</th>
          <th scope="col" class="px-4 py-3">Statut</th>
          {% if peut_gerer %}<th scope="col" class="px-4 py-3"><span class="sr-only">Actions</span></th>{% endif %}
        </tr>
      </thead>
      <tbody class="divide-y divide-slate-100">
        {% for c in comptes %}
          <tr class="hover:bg-slate-50">
            <td class="whitespace-nowrap px-4 py-3 font-semibold text-slate-900">{{ c.numero }}</td>
            <td class="px-4 py-3 text-slate-700">{{ c.libelle }}</td>
            <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ c.get_nature_display }}</td>
            <td class="whitespace-nowrap px-4 py-3">
              {% if c.actif %}{% badge "DISPONIBLE" "Actif" %}{% else %}{% badge "INACTIF" "Désactivé" %}{% endif %}
            </td>
            {% if peut_gerer %}
              <td class="whitespace-nowrap px-4 py-3 text-right">
                <a href="{% url 'accounting:compte_modifier' c.pk %}" class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">Modifier</a>
              </td>
            {% endif %}
          </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endblock %}
```

#### `apps/accounting/templates/accounting/compte_form.html`

*31 lignes*

```django
{% extends "base.html" %}
{% block titre %}Nouveau compte{% endblock %}
{% block entete %}Comptabilité{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-2xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'accounting:plan_comptable' %}" class="underline-offset-2 hover:underline">Plan comptable</a>
    <span aria-hidden="true">/</span> Nouveau compte
  </nav>
  <h1 class="mt-2 text-2xl font-bold text-slate-900">Nouveau compte</h1>
  <p class="mt-1 text-sm text-slate-600">
    Le numéro et la nature ne se modifient plus une fois le compte créé — seuls le libellé et
    l'activation le pourront ensuite.
  </p>

  <form method="post" novalidate class="mt-6 space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
    {% csrf_token %}
    {% if form.non_field_errors %}
      <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">{% for erreur in form.non_field_errors %}<p>{{ erreur }}</p>{% endfor %}</div>
    {% endif %}
    {% include "components/_champ.html" with champ=form.numero %}
    {% include "components/_champ.html" with champ=form.libelle %}
    {% include "components/_champ.html" with champ=form.nature %}
    <div class="flex items-center justify-end gap-3 border-t border-slate-100 pt-5">
      <a href="{% url 'accounting:plan_comptable' %}" class="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">Annuler</a>
      <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Créer le compte</button>
    </div>
  </form>
</div>
{% endblock %}
```

#### `apps/accounting/templates/accounting/compte_modifier_form.html`

*31 lignes*

```django
{% extends "base.html" %}
{% block titre %}Modifier {{ compte.numero }}{% endblock %}
{% block entete %}Comptabilité{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-2xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'accounting:plan_comptable' %}" class="underline-offset-2 hover:underline">Plan comptable</a>
    <span aria-hidden="true">/</span> {{ compte.numero }}
  </nav>
  <h1 class="mt-2 text-2xl font-bold text-slate-900">{{ compte.numero }} — {{ compte.libelle }}</h1>
  <p class="mt-1 text-sm text-slate-600">
    Nature : {{ compte.get_nature_display }} (fixée à la création, ne se modifie plus). Désactiver
    un compte l'empêche d'être utilisé dans une nouvelle écriture ; son historique reste visible
    dans le grand livre.
  </p>

  <form method="post" novalidate class="mt-6 space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
    {% csrf_token %}
    {% if form.non_field_errors %}
      <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">{% for erreur in form.non_field_errors %}<p>{{ erreur }}</p>{% endfor %}</div>
    {% endif %}
    {% include "components/_champ.html" with champ=form.libelle %}
    {% include "components/_champ.html" with champ=form.actif %}
    <div class="flex items-center justify-end gap-3 border-t border-slate-100 pt-5">
      <a href="{% url 'accounting:plan_comptable' %}" class="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">Annuler</a>
      <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Enregistrer</button>
    </div>
  </form>
</div>
{% endblock %}
```

#### `apps/accounting/templates/accounting/ecriture_manuelle_list.html`

*54 lignes*

```django
{% extends "base.html" %}
{% load ui humanize %}
{% block titre %}Opérations diverses{% endblock %}
{% block entete %}Comptabilité{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-6xl">
  <div class="flex flex-wrap items-start justify-between gap-3">
    <div>
      <h1 class="text-2xl font-bold text-slate-900">Opérations diverses</h1>
      <p class="mt-1 text-sm text-slate-600">{{ paginator.count|default:0 }} écriture{{ paginator.count|pluralize }} — saisie manuelle, journal OD.</p>
    </div>
    {% if peut_saisir %}
      <a href="{% url 'accounting:ecriture_manuelle_nouvelle' %}" class="inline-flex items-center gap-2 rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700">
        <i class="fa-solid fa-plus" aria-hidden="true"></i> Nouvelle écriture
      </a>
    {% endif %}
  </div>

  {% if ecritures %}
    <div class="mt-5 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <caption class="sr-only">Liste des écritures d'opérations diverses</caption>
        <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr>
            <th scope="col" class="px-4 py-3">Écriture</th>
            <th scope="col" class="px-4 py-3">Date</th>
            <th scope="col" class="px-4 py-3">Libellé</th>
            <th scope="col" class="px-4 py-3">Statut</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          {% for e in ecritures %}
            <tr class="hover:bg-slate-50">
              <td class="whitespace-nowrap px-4 py-3 font-semibold">
                <a href="{% url 'accounting:ecriture_manuelle' e.pk %}" class="text-marque-700 underline-offset-2 hover:underline">{{ e.numero|default:"Brouillon" }}</a>
              </td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ e.date_ecriture|date:"d/m/Y" }}</td>
              <td class="px-4 py-3 text-slate-700">{{ e.libelle }}</td>
              <td class="whitespace-nowrap px-4 py-3">{% badge e.statut e.get_statut_display %}</td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% include "components/_pagination.html" %}
  {% else %}
    <div class="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
      <span class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-600"><i class="fa-solid fa-scale-balanced" aria-hidden="true"></i></span>
      <p class="mt-3 font-semibold text-slate-900">Aucune écriture</p>
    </div>
  {% endif %}
</div>
{% endblock %}
```

#### `apps/accounting/templates/accounting/ecriture_manuelle_form.html`

*30 lignes*

```django
{% extends "base.html" %}
{% block titre %}Nouvelle écriture{% endblock %}
{% block entete %}Comptabilité{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-2xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'accounting:ecritures_manuelles' %}" class="underline-offset-2 hover:underline">Opérations diverses</a>
    <span aria-hidden="true">/</span> Nouvelle écriture
  </nav>
  <h1 class="mt-2 text-2xl font-bold text-slate-900">Nouvelle écriture</h1>
  <p class="mt-1 text-sm text-slate-600">
    Ouvre un brouillon (journal Opérations diverses) : les lignes débit/crédit s'ajoutent ensuite
    sur la fiche, puis la direction valide une fois l'écriture équilibrée.
  </p>

  <form method="post" novalidate class="mt-6 space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
    {% csrf_token %}
    {% if form.non_field_errors %}
      <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">{% for erreur in form.non_field_errors %}<p>{{ erreur }}</p>{% endfor %}</div>
    {% endif %}
    {% include "components/_champ.html" with champ=form.date_ecriture %}
    {% include "components/_champ.html" with champ=form.libelle %}
    <div class="flex items-center justify-end gap-3 border-t border-slate-100 pt-5">
      <a href="{% url 'accounting:ecritures_manuelles' %}" class="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">Annuler</a>
      <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Créer le brouillon</button>
    </div>
  </form>
</div>
{% endblock %}
```

#### `apps/accounting/templates/accounting/ecriture_manuelle_detail.html`

*120 lignes*

```django
{% extends "base.html" %}
{% load ui humanize %}
{% block titre %}{{ ecriture.numero|default:"Brouillon" }}{% endblock %}
{% block entete %}Comptabilité{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-4xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'accounting:ecritures_manuelles' %}" class="underline-offset-2 hover:underline">Opérations diverses</a>
    <span aria-hidden="true">/</span> {{ ecriture.numero|default:"Brouillon" }}
  </nav>

  <div class="mt-2 flex flex-wrap items-center gap-3">
    <h1 class="text-2xl font-bold text-slate-900">{{ ecriture.numero|default:"Brouillon" }}</h1>
    {% badge ecriture.statut ecriture.get_statut_display %}
  </div>
  <p class="mt-1 text-sm text-slate-600">{{ ecriture.date_ecriture|date:"d/m/Y" }} · {{ ecriture.libelle }}</p>

  <section class="mt-5 rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-lignes">
    <h2 id="titre-lignes" class="text-base font-semibold text-slate-900">Lignes</h2>

    {% if lignes %}
      <div class="mt-3 overflow-x-auto">
        <table class="min-w-full divide-y divide-slate-200 text-sm">
          <caption class="sr-only">Lignes débit/crédit de l'écriture</caption>
          <thead class="text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
            <tr>
              <th scope="col" class="py-2 pr-4">Compte</th>
              <th scope="col" class="py-2 pr-4">Libellé</th>
              <th scope="col" class="py-2 pr-4 text-right">Débit</th>
              <th scope="col" class="py-2 pr-4 text-right">Crédit</th>
              {% if peut_saisir %}<th scope="col" class="py-2 pr-4"><span class="sr-only">Actions</span></th>{% endif %}
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            {% for l in lignes %}
              <tr>
                <td class="whitespace-nowrap py-2 pr-4 text-slate-900">{{ l.compte.numero }} — {{ l.compte.libelle }}</td>
                <td class="py-2 pr-4 text-slate-700">{{ l.libelle|default:"—" }}</td>
                <td class="whitespace-nowrap py-2 pr-4 text-right text-slate-900">{% if l.sens == "DEBIT" %}{{ l.montant|floatformat:0|intcomma }}{% endif %}</td>
                <td class="whitespace-nowrap py-2 pr-4 text-right text-slate-900">{% if l.sens == "CREDIT" %}{{ l.montant|floatformat:0|intcomma }}{% endif %}</td>
                {% if peut_saisir %}
                  <td class="whitespace-nowrap py-2 pr-4 text-right">
                    <form method="post" action="{% url 'accounting:ligne_supprimer' ecriture.pk l.pk %}" data-confirm="Supprimer cette ligne ?">{% csrf_token %}
                      <button type="submit" class="text-sm font-medium text-red-800 underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-red-700"><i class="fa-solid fa-trash-can" aria-hidden="true"></i><span class="sr-only">Supprimer la ligne</span></button>
                    </form>
                  </td>
                {% endif %}
              </tr>
            {% endfor %}
          </tbody>
          <tfoot class="border-t border-slate-200 font-semibold text-slate-900">
            <tr>
              <td class="py-2 pr-4" colspan="2">Total</td>
              <td class="whitespace-nowrap py-2 pr-4 text-right">{{ total_debit|floatformat:0|intcomma }}</td>
              <td class="whitespace-nowrap py-2 pr-4 text-right">{{ total_credit|floatformat:0|intcomma }}</td>
              {% if peut_saisir %}<td></td>{% endif %}
            </tr>
          </tfoot>
        </table>
      </div>
      <p class="mt-3 text-sm {% if equilibree %}text-green-800{% else %}text-amber-800{% endif %}">
        {% if equilibree %}<i class="fa-solid fa-check" aria-hidden="true"></i> Écriture équilibrée, prête à valider.
        {% else %}<i class="fa-solid fa-triangle-exclamation" aria-hidden="true"></i> Écriture déséquilibrée ou incomplète (2 lignes minimum, débit = crédit).{% endif %}
      </p>
    {% else %}
      <p class="mt-3 text-sm text-slate-700">Aucune ligne pour l'instant.</p>
    {% endif %}

    {% if form_ligne %}
      <form method="post" action="{% url 'accounting:ligne_ajouter' ecriture.pk %}" class="mt-5 space-y-3 rounded-lg bg-slate-50 p-4">{% csrf_token %}
        <h3 class="text-sm font-semibold text-slate-900">Ajouter une ligne</h3>
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-4">
          <div class="sm:col-span-2">{% include "components/_champ.html" with champ=form_ligne.compte %}</div>
          {% include "components/_champ.html" with champ=form_ligne.sens %}
          {% include "components/_champ.html" with champ=form_ligne.montant %}
        </div>
        {% include "components/_champ.html" with champ=form_ligne.libelle %}
        <button type="submit" class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Ajouter</button>
      </form>
    {% endif %}
  </section>

  {% if contre_passation %}
    <p class="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700"><i class="fa-solid fa-rotate-left" aria-hidden="true"></i> Cette écriture a été contre-passée par l'écriture <strong>{{ contre_passation.numero }}</strong> du {{ contre_passation.date_ecriture|date:"d/m/Y" }} ({{ contre_passation.libelle }}).</p>
  {% endif %}

  {% if peut_contre_passer %}
    <section class="mt-5 rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-contre-passation">
      <h2 id="titre-contre-passation" class="text-base font-semibold text-slate-900">Corriger cette écriture</h2>
      <p class="mt-1 text-sm text-slate-600">Une écriture validée ne se modifie pas : la contre-passation pose l'écriture inverse, datée d'aujourd'hui. Les deux restent au grand livre.</p>
      <form method="post" action="{% url 'accounting:ecriture_manuelle_contre_passer' ecriture.pk %}" data-confirm="Contre-passer cette écriture ? L'écriture inverse sera validée immédiatement." class="mt-3 flex flex-wrap items-end gap-3">{% csrf_token %}
        <div class="grow">
          <label for="motif-contre-passation" class="block text-sm font-medium text-slate-700">Motif (obligatoire)</label>
          <input id="motif-contre-passation" name="motif" type="text" required maxlength="200" class="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600">
        </div>
        <button type="submit" class="rounded-lg border border-red-300 bg-white px-4 py-2 text-sm font-semibold text-red-800 hover:bg-red-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-700">Contre-passer</button>
      </form>
    </section>
  {% endif %}

  {% if peut_valider or peut_saisir %}
    <section class="mt-5 rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-actions">
      <h2 id="titre-actions" class="text-base font-semibold text-slate-900">Actions</h2>
      <div class="mt-3 flex flex-wrap gap-3">
        {% if peut_valider %}
          <form method="post" action="{% url 'accounting:ecriture_manuelle_valider' ecriture.pk %}" data-confirm="Valider cette écriture ? Elle ne pourra plus être modifiée ensuite.">{% csrf_token %}
            <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Valider</button>
          </form>
        {% endif %}
        {% if peut_saisir %}
          <form method="post" action="{% url 'accounting:ecriture_manuelle_abandonner' ecriture.pk %}" data-confirm="Abandonner ce brouillon ? Cette action est irréversible.">{% csrf_token %}
            <button type="submit" class="rounded-lg border border-red-300 bg-white px-4 py-2 text-sm font-semibold text-red-800 hover:bg-red-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-700">Abandonner le brouillon</button>
          </form>
        {% endif %}
      </div>
    </section>
  {% endif %}
</div>
{% endblock %}
```

#### `apps/accounting/templates/accounting/exercice_list.html`

*58 lignes*

```django
{% extends "base.html" %}
{% load ui %}
{% block titre %}Exercices comptables{% endblock %}
{% block entete %}Comptabilité{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-4xl">
  <h1 class="text-2xl font-bold text-slate-900">Exercices comptables</h1>
  <p class="mt-1 text-sm text-slate-600">
    Un exercice s'ouvre tout seul à la première écriture de son année. Une fois clôturé, aucune
    écriture ne peut plus y être datée — la clôture est définitive.
  </p>

  {% if exercices %}
    <div class="mt-5 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <caption class="sr-only">Liste des exercices comptables</caption>
        <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr>
            <th scope="col" class="px-4 py-3">Année</th>
            <th scope="col" class="px-4 py-3">Période</th>
            <th scope="col" class="px-4 py-3">Statut</th>
            <th scope="col" class="px-4 py-3">Clôturé par</th>
            {% if peut_cloturer %}<th scope="col" class="px-4 py-3"><span class="sr-only">Actions</span></th>{% endif %}
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          {% for e in exercices %}
            <tr class="hover:bg-slate-50">
              <td class="whitespace-nowrap px-4 py-3 font-semibold text-slate-900">{{ e.annee }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ e.date_debut|date:"d/m/Y" }} – {{ e.date_fin|date:"d/m/Y" }}</td>
              <td class="whitespace-nowrap px-4 py-3">{% badge e.statut e.get_statut_display %}</td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">
                {% if e.cloture_par %}{{ e.cloture_par }} · {{ e.date_cloture|date:"d/m/Y" }}{% else %}—{% endif %}
              </td>
              {% if peut_cloturer %}
                <td class="whitespace-nowrap px-4 py-3 text-right">
                  {% if e.statut == "OUVERT" %}
                    <form method="post" action="{% url 'accounting:exercice_cloturer' e.pk %}" data-confirm="Clôturer l'exercice {{ e.annee }} ? Aucune écriture ne pourra plus y être datée, et cette action est définitive.">{% csrf_token %}
                      <button type="submit" class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">Clôturer</button>
                    </form>
                  {% endif %}
                </td>
              {% endif %}
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  {% else %}
    <div class="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
      <span class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-600"><i class="fa-solid fa-calendar-days" aria-hidden="true"></i></span>
      <p class="mt-3 font-semibold text-slate-900">Aucun exercice pour l'instant</p>
      <p class="mt-1 text-sm text-slate-600">Un exercice apparaît dès la première écriture comptable de son année.</p>
    </div>
  {% endif %}
</div>
{% endblock %}
```

#### `apps/accounting/templates/accounting/_nav_rapports.html`

*7 lignes*

```django
<nav aria-label="Rapports comptables" class="mt-4 flex flex-wrap gap-2 text-sm">
  <a href="{% url 'accounting:grand_livre' %}" class="rounded-lg px-3 py-1.5 font-medium {% if request.resolver_match.url_name == 'grand_livre' %}bg-slate-900 text-white{% else %}border border-slate-300 bg-white text-slate-800 hover:bg-slate-50{% endif %}">Grand livre</a>
  <a href="{% url 'accounting:balance' %}" class="rounded-lg px-3 py-1.5 font-medium {% if request.resolver_match.url_name == 'balance' %}bg-slate-900 text-white{% else %}border border-slate-300 bg-white text-slate-800 hover:bg-slate-50{% endif %}">Balance</a>
  <a href="{% url 'accounting:bilan' %}" class="rounded-lg px-3 py-1.5 font-medium {% if request.resolver_match.url_name == 'bilan' %}bg-slate-900 text-white{% else %}border border-slate-300 bg-white text-slate-800 hover:bg-slate-50{% endif %}">Bilan</a>
  <a href="{% url 'accounting:compte_resultat' %}" class="rounded-lg px-3 py-1.5 font-medium {% if request.resolver_match.url_name == 'compte_resultat' %}bg-slate-900 text-white{% else %}border border-slate-300 bg-white text-slate-800 hover:bg-slate-50{% endif %}">Compte de résultat</a>
  <a href="{% url 'accounting:declaration_tva' %}" class="rounded-lg px-3 py-1.5 font-medium {% if request.resolver_match.url_name == 'declaration_tva' %}bg-slate-900 text-white{% else %}border border-slate-300 bg-white text-slate-800 hover:bg-slate-50{% endif %}">Déclaration TVA</a>
</nav>
```

Incluse par les cinq gabarits de rapport suivants (`{% include %}`), pour l'onglet de navigation commun.

#### `apps/accounting/templates/accounting/grand_livre.html`

*59 lignes*

```django
{% extends "base.html" %}
{% load ui humanize %}
{% block titre %}Grand livre{% endblock %}
{% block entete %}Comptabilité{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-4xl">
  <div class="flex flex-wrap items-start justify-between gap-3">
    <h1 class="text-2xl font-bold text-slate-900">Rapports comptables</h1>
    <div class="flex flex-wrap items-center gap-2">
    <a href="{% url 'accounting:grand_livre_imprimer' %}?{{ request.GET.urlencode }}" target="_blank" rel="noopener"
       class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
      <i class="fa-solid fa-print" aria-hidden="true"></i> Imprimer
    </a>
    {% url 'accounting:grand_livre_xlsx' as url_xlsx %}{% include "components/_bouton_xlsx.html" with url=url_xlsx %}
    </div>
  </div>
  {% include "accounting/_nav_rapports.html" %}

  <form method="get" class="mt-5 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
    {% include "components/_champ.html" with champ=form.compte %}
    {% include "components/_champ.html" with champ=form.debut %}
    {% include "components/_champ.html" with champ=form.fin %}
    <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Afficher</button>
  </form>

  {% if lignes is not None %}
    <div class="mt-5 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <caption class="sr-only">Grand livre du compte sélectionné</caption>
        <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr>
            <th scope="col" class="px-4 py-3">Date</th>
            <th scope="col" class="px-4 py-3">Écriture</th>
            <th scope="col" class="px-4 py-3">Libellé</th>
            <th scope="col" class="px-4 py-3 text-right">Débit</th>
            <th scope="col" class="px-4 py-3 text-right">Crédit</th>
            <th scope="col" class="px-4 py-3 text-right">Solde cumulé</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          {% for entree in lignes %}
            <tr class="hover:bg-slate-50">
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ entree.ligne.ecriture.date_ecriture|date:"d/m/Y" }}</td>
              <td class="whitespace-nowrap px-4 py-3 font-semibold text-slate-900">{{ entree.ligne.ecriture.numero|default:"Brouillon" }}</td>
              <td class="px-4 py-3 text-slate-700">{{ entree.ligne.libelle|default:entree.ligne.ecriture.libelle }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right text-slate-900">{% if entree.ligne.sens == "DEBIT" %}{{ entree.ligne.montant|floatformat:0|intcomma }}{% endif %}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right text-slate-900">{% if entree.ligne.sens == "CREDIT" %}{{ entree.ligne.montant|floatformat:0|intcomma }}{% endif %}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right font-semibold text-slate-900">{{ entree.solde_cumule|floatformat:0|intcomma }}</td>
            </tr>
          {% empty %}
            <tr><td colspan="6" class="px-4 py-6 text-center text-slate-600">Aucun mouvement pour ce compte sur cette période.</td></tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  {% endif %}
</div>
{% endblock %}
```

#### `apps/accounting/templates/accounting/grand_livre_print.html`

*46 lignes*

```django
{% load static humanize %}<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Grand livre · {{ entreprise.nom }}</title>
  {% include "rapports/_style_impression.html" %}
</head>
<body>
  {% include "rapports/_entete_impression.html" %}

  {% if lignes is not None %}
    <table>
      <thead>
        <tr>
          <th>Date</th>
          <th>Écriture</th>
          <th>Libellé</th>
          <th class="droite">Débit</th>
          <th class="droite">Crédit</th>
          <th class="droite">Solde cumulé</th>
        </tr>
      </thead>
      <tbody>
        {% for entree in lignes %}
          <tr>
            <td>{{ entree.ligne.ecriture.date_ecriture|date:"d/m/Y" }}</td>
            <td>{{ entree.ligne.ecriture.numero|default:"Brouillon" }}</td>
            <td>{{ entree.ligne.libelle|default:entree.ligne.ecriture.libelle }}</td>
            <td class="droite">{% if entree.ligne.sens == "DEBIT" %}{{ entree.ligne.montant|floatformat:0|intcomma }}{% endif %}</td>
            <td class="droite">{% if entree.ligne.sens == "CREDIT" %}{{ entree.ligne.montant|floatformat:0|intcomma }}{% endif %}</td>
            <td class="droite">{{ entree.solde_cumule|floatformat:0|intcomma }}</td>
          </tr>
        {% empty %}
          <tr><td colspan="6">Aucun mouvement pour ce compte sur cette période.</td></tr>
        {% endfor %}
      </tbody>
    </table>
  {% else %}
    <p class="petit">Aucun compte sélectionné.</p>
  {% endif %}

  {% include "rapports/_pied_impression.html" %}
  <script src="{% static 'js/app.js' %}" defer></script>
</body>
</html>
```

#### `apps/accounting/templates/accounting/balance.html`

*65 lignes*

```django
{% extends "base.html" %}
{% load ui humanize %}
{% block titre %}Balance{% endblock %}
{% block entete %}Comptabilité{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-4xl">
  <div class="flex flex-wrap items-start justify-between gap-3">
    <h1 class="text-2xl font-bold text-slate-900">Rapports comptables</h1>
    <div class="flex flex-wrap items-center gap-2">
    <a href="{% url 'accounting:balance_imprimer' %}?{{ request.GET.urlencode }}" target="_blank" rel="noopener"
       class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
      <i class="fa-solid fa-print" aria-hidden="true"></i> Imprimer
    </a>
    {% url 'accounting:balance_xlsx' as url_xlsx %}{% include "components/_bouton_xlsx.html" with url=url_xlsx %}
    </div>
  </div>
  {% include "accounting/_nav_rapports.html" %}

  <form method="get" class="mt-5 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
    {% include "components/_champ.html" with champ=form.debut %}
    {% include "components/_champ.html" with champ=form.fin %}
    <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Afficher</button>
  </form>

  <div class="mt-5 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
    <table class="min-w-full divide-y divide-slate-200 text-sm">
      <caption class="sr-only">Balance générale des comptes</caption>
      <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
        <tr>
          <th scope="col" class="px-4 py-3">Compte</th>
          <th scope="col" class="px-4 py-3 text-right">Total débit</th>
          <th scope="col" class="px-4 py-3 text-right">Total crédit</th>
          <th scope="col" class="px-4 py-3 text-right">Solde débiteur</th>
          <th scope="col" class="px-4 py-3 text-right">Solde créditeur</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-slate-100">
        {% for l in lignes %}
          <tr class="hover:bg-slate-50">
            <td class="whitespace-nowrap px-4 py-3 text-slate-900">{{ l.compte__numero }} — {{ l.compte__libelle }}</td>
            <td class="whitespace-nowrap px-4 py-3 text-right text-slate-700">{{ l.total_debit|floatformat:0|intcomma }}</td>
            <td class="whitespace-nowrap px-4 py-3 text-right text-slate-700">{{ l.total_credit|floatformat:0|intcomma }}</td>
            <td class="whitespace-nowrap px-4 py-3 text-right font-semibold text-slate-900">{% if l.solde_debiteur %}{{ l.solde_debiteur|floatformat:0|intcomma }}{% endif %}</td>
            <td class="whitespace-nowrap px-4 py-3 text-right font-semibold text-slate-900">{% if l.solde_crediteur %}{{ l.solde_crediteur|floatformat:0|intcomma }}{% endif %}</td>
          </tr>
        {% empty %}
          <tr><td colspan="5" class="px-4 py-6 text-center text-slate-600">Aucun compte mouvementé sur cette période.</td></tr>
        {% endfor %}
      </tbody>
      {% if lignes %}
        <tfoot class="border-t border-slate-200 font-semibold text-slate-900">
          <tr>
            <td class="px-4 py-3">Total</td>
            <td class="whitespace-nowrap px-4 py-3 text-right">{{ totaux.debit|floatformat:0|intcomma }}</td>
            <td class="whitespace-nowrap px-4 py-3 text-right">{{ totaux.credit|floatformat:0|intcomma }}</td>
            <td></td>
            <td></td>
          </tr>
        </tfoot>
      {% endif %}
    </table>
  </div>
</div>
{% endblock %}
```

#### `apps/accounting/templates/accounting/balance_print.html`

*51 lignes*

```django
{% load static humanize %}<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Balance générale · {{ entreprise.nom }}</title>
  {% include "rapports/_style_impression.html" %}
</head>
<body>
  {% include "rapports/_entete_impression.html" %}

  <table>
    <thead>
      <tr>
        <th>Compte</th>
        <th class="droite">Total débit</th>
        <th class="droite">Total crédit</th>
        <th class="droite">Solde débiteur</th>
        <th class="droite">Solde créditeur</th>
      </tr>
    </thead>
    <tbody>
      {% for l in lignes %}
        <tr>
          <td>{{ l.compte__numero }} — {{ l.compte__libelle }}</td>
          <td class="droite">{{ l.total_debit|floatformat:0|intcomma }}</td>
          <td class="droite">{{ l.total_credit|floatformat:0|intcomma }}</td>
          <td class="droite">{% if l.solde_debiteur %}{{ l.solde_debiteur|floatformat:0|intcomma }}{% endif %}</td>
          <td class="droite">{% if l.solde_crediteur %}{{ l.solde_crediteur|floatformat:0|intcomma }}{% endif %}</td>
        </tr>
      {% empty %}
        <tr><td colspan="5">Aucun compte mouvementé sur cette période.</td></tr>
      {% endfor %}
    </tbody>
    {% if lignes %}
      <tfoot>
        <tr>
          <td><strong>Total</strong></td>
          <td class="droite"><strong>{{ totaux.debit|floatformat:0|intcomma }}</strong></td>
          <td class="droite"><strong>{{ totaux.credit|floatformat:0|intcomma }}</strong></td>
          <td></td>
          <td></td>
        </tr>
      </tfoot>
    {% endif %}
  </table>

  {% include "rapports/_pied_impression.html" %}
  <script src="{% static 'js/app.js' %}" defer></script>
</body>
</html>
```

#### `apps/accounting/templates/accounting/bilan.html`

*69 lignes*

```django
{% extends "base.html" %}
{% load ui humanize %}
{% block titre %}Bilan{% endblock %}
{% block entete %}Comptabilité{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-4xl">
  <div class="flex flex-wrap items-start justify-between gap-3">
    <h1 class="text-2xl font-bold text-slate-900">Rapports comptables</h1>
    <div class="flex flex-wrap items-center gap-2">
    <a href="{% url 'accounting:bilan_imprimer' %}?{{ request.GET.urlencode }}" target="_blank" rel="noopener"
       class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
      <i class="fa-solid fa-print" aria-hidden="true"></i> Imprimer
    </a>
    {% url 'accounting:bilan_xlsx' as url_xlsx %}{% include "components/_bouton_xlsx.html" with url=url_xlsx %}
    </div>
  </div>
  {% include "accounting/_nav_rapports.html" %}

  {% if exercices %}
    <nav class="mt-4 flex flex-wrap items-center gap-2 text-sm" aria-label="Exercice">
      <span class="text-slate-600">Exercice :</span>
      {% for e in exercices %}
        <a href="?exercice={{ e.annee }}"
           class="rounded-lg border px-3 py-1.5 font-medium {% if e.annee == exercice.annee %}border-slate-900 bg-slate-900 text-white{% else %}border-slate-300 bg-white text-slate-800 hover:bg-slate-50{% endif %}">{{ e.annee }}</a>
      {% endfor %}
    </nav>
  {% endif %}

  {% if rapport %}
    <p class="mt-3 text-sm text-slate-600">
      Photo cumulée depuis l'origine jusqu'au {{ exercice.date_fin|date:"d/m/Y" }}. Le résultat des exercices
      clôturés figure déjà au compte 120000 (écriture de clôture) ; le résultat qui n'a pas encore été viré
      (exercice en cours) est ajouté au passif.
    </p>
    <div class="mt-4 grid grid-cols-1 gap-5 sm:grid-cols-2">
      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-actif">
        <h2 id="titre-actif" class="text-base font-semibold text-slate-900">Actif</h2>
        <dl class="mt-3 space-y-2 text-sm">
          {% for l in rapport.actif %}
            <div class="flex justify-between gap-3"><dt class="text-slate-600">{{ l.compte__numero }} — {{ l.compte__libelle }}</dt><dd class="font-medium text-slate-900">{{ l.montant|floatformat:0|intcomma }}</dd></div>
          {% empty %}
            <p class="text-slate-600">Aucun compte d'actif mouvementé.</p>
          {% endfor %}
        </dl>
        <p class="mt-3 flex justify-between border-t border-slate-200 pt-3 font-semibold text-slate-900"><span>Total actif</span><span>{{ rapport.total_actif|floatformat:0|intcomma }}</span></p>
      </section>

      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-passif">
        <h2 id="titre-passif" class="text-base font-semibold text-slate-900">Passif</h2>
        <dl class="mt-3 space-y-2 text-sm">
          {% for l in rapport.passif %}
            <div class="flex justify-between gap-3"><dt class="text-slate-600">{{ l.compte__numero }} — {{ l.compte__libelle }}</dt><dd class="font-medium text-slate-900">{{ l.montant|floatformat:0|intcomma }}</dd></div>
          {% empty %}
            <p class="text-slate-600">Aucun compte de passif mouvementé.</p>
          {% endfor %}
          {% if rapport.resultat_net %}<div class="flex justify-between gap-3"><dt class="text-slate-600">Résultat en cours, pas encore viré au 120000 (calculé)</dt><dd class="font-medium text-slate-900">{{ rapport.resultat_net|floatformat:0|intcomma }}</dd></div>{% endif %}
        </dl>
        <p class="mt-3 flex justify-between border-t border-slate-200 pt-3 font-semibold text-slate-900"><span>Total passif</span><span>{{ rapport.total_passif_avec_resultat|floatformat:0|intcomma }}</span></p>
      </section>
    </div>
  {% else %}
    <div class="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
      <p class="font-semibold text-slate-900">Aucun exercice pour l'instant</p>
      <p class="mt-1 text-sm text-slate-600">Un exercice apparaît dès la première écriture comptable de son année.</p>
    </div>
  {% endif %}
</div>
{% endblock %}
```

#### `apps/accounting/templates/accounting/bilan_print.html`

*52 lignes*

```django
{% load static humanize %}<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Bilan · {{ entreprise.nom }}</title>
  {% include "rapports/_style_impression.html" %}
</head>
<body>
  {% include "rapports/_entete_impression.html" %}

  {% if rapport_bilan %}
    <p class="petit">
      Photo cumulée depuis l'origine jusqu'au {{ exercice.date_fin|date:"d/m/Y" }} — le résultat de
      l'exercice {{ exercice.annee }} est ajouté au passif pour équilibrer le bilan (aucune écriture
      de clôture ne l'a encore imputé au compte 120000).
    </p>

    <h2>Actif</h2>
    <table>
      <thead><tr><th>Compte</th><th class="droite">Montant</th></tr></thead>
      <tbody>
        {% for l in rapport_bilan.actif %}
          <tr><td>{{ l.compte__numero }} — {{ l.compte__libelle }}</td><td class="droite">{{ l.montant|floatformat:0|intcomma }}</td></tr>
        {% empty %}
          <tr><td colspan="2">Aucun compte d'actif mouvementé.</td></tr>
        {% endfor %}
      </tbody>
      <tfoot><tr><td><strong>Total actif</strong></td><td class="droite"><strong>{{ rapport_bilan.total_actif|floatformat:0|intcomma }}</strong></td></tr></tfoot>
    </table>

    <h2>Passif</h2>
    <table>
      <thead><tr><th>Compte</th><th class="droite">Montant</th></tr></thead>
      <tbody>
        {% for l in rapport_bilan.passif %}
          <tr><td>{{ l.compte__numero }} — {{ l.compte__libelle }}</td><td class="droite">{{ l.montant|floatformat:0|intcomma }}</td></tr>
        {% empty %}
          <tr><td colspan="2">Aucun compte de passif mouvementé.</td></tr>
        {% endfor %}
        {% if rapport_bilan.resultat_net %}<tr><td>Résultat en cours, pas encore viré au 120000 (calculé)</td><td class="droite">{{ rapport_bilan.resultat_net|floatformat:0|intcomma }}</td></tr>{% endif %}
      </tbody>
      <tfoot><tr><td><strong>Total passif</strong></td><td class="droite"><strong>{{ rapport_bilan.total_passif_avec_resultat|floatformat:0|intcomma }}</strong></td></tr></tfoot>
    </table>
  {% else %}
    <p class="petit">Aucun exercice pour l'instant.</p>
  {% endif %}

  {% include "rapports/_pied_impression.html" %}
  <script src="{% static 'js/app.js' %}" defer></script>
</body>
</html>
```

#### `apps/accounting/templates/accounting/compte_resultat.html`

*74 lignes*

```django
{% extends "base.html" %}
{% load ui humanize %}
{% block titre %}Compte de résultat{% endblock %}
{% block entete %}Comptabilité{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-4xl">
  <div class="flex flex-wrap items-start justify-between gap-3">
    <h1 class="text-2xl font-bold text-slate-900">Rapports comptables</h1>
    <div class="flex flex-wrap items-center gap-2">
    <a href="{% url 'accounting:compte_resultat_imprimer' %}?{{ request.GET.urlencode }}" target="_blank" rel="noopener"
       class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
      <i class="fa-solid fa-print" aria-hidden="true"></i> Imprimer
    </a>
    {% url 'accounting:compte_resultat_xlsx' as url_xlsx %}{% include "components/_bouton_xlsx.html" with url=url_xlsx %}
    </div>
  </div>
  {% include "accounting/_nav_rapports.html" %}

  {% if exercices %}
    <nav class="mt-4 flex flex-wrap items-center gap-2 text-sm" aria-label="Exercice">
      <span class="text-slate-600">Exercice :</span>
      {% for e in exercices %}
        <a href="?exercice={{ e.annee }}"
           class="rounded-lg border px-3 py-1.5 font-medium {% if e.annee == exercice.annee %}border-slate-900 bg-slate-900 text-white{% else %}border-slate-300 bg-white text-slate-800 hover:bg-slate-50{% endif %}">{{ e.annee }}</a>
      {% endfor %}
    </nav>
  {% endif %}

  {% if rapport %}
    <p class="mt-3 text-sm text-slate-600">
      Produits et charges du {{ exercice.date_debut|date:"d/m/Y" }} au {{ exercice.date_fin|date:"d/m/Y" }} seulement
      (contrairement au bilan, qui est cumulé depuis l'origine).
    </p>
    <div class="mt-4 grid grid-cols-1 gap-5 sm:grid-cols-2">
      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-produits">
        <h2 id="titre-produits" class="text-base font-semibold text-slate-900">Produits</h2>
        <dl class="mt-3 space-y-2 text-sm">
          {% for l in rapport.produits %}
            <div class="flex justify-between gap-3"><dt class="text-slate-600">{{ l.compte__numero }} — {{ l.compte__libelle }}</dt><dd class="font-medium text-slate-900">{{ l.montant|floatformat:0|intcomma }}</dd></div>
          {% empty %}
            <p class="text-slate-600">Aucun produit sur la période.</p>
          {% endfor %}
        </dl>
        <p class="mt-3 flex justify-between border-t border-slate-200 pt-3 font-semibold text-slate-900"><span>Total produits</span><span>{{ rapport.total_produits|floatformat:0|intcomma }}</span></p>
      </section>

      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-charges">
        <h2 id="titre-charges" class="text-base font-semibold text-slate-900">Charges</h2>
        <dl class="mt-3 space-y-2 text-sm">
          {% for l in rapport.charges %}
            <div class="flex justify-between gap-3"><dt class="text-slate-600">{{ l.compte__numero }} — {{ l.compte__libelle }}</dt><dd class="font-medium text-slate-900">{{ l.montant|floatformat:0|intcomma }}</dd></div>
          {% empty %}
            <p class="text-slate-600">Aucune charge sur la période.</p>
          {% endfor %}
        </dl>
        <p class="mt-3 flex justify-between border-t border-slate-200 pt-3 font-semibold text-slate-900"><span>Total charges</span><span>{{ rapport.total_charges|floatformat:0|intcomma }}</span></p>
      </section>
    </div>

    <section class="mt-5 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <p class="flex justify-between text-base font-semibold {% if rapport.resultat_net >= 0 %}text-green-800{% else %}text-red-800{% endif %}">
        <span>Résultat net {% if rapport.resultat_net >= 0 %}(bénéfice){% else %}(perte){% endif %}</span>
        <span>{{ rapport.resultat_net|floatformat:0|intcomma }} FCFA</span>
      </p>
    </section>
  {% else %}
    <div class="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
      <p class="font-semibold text-slate-900">Aucun exercice pour l'instant</p>
      <p class="mt-1 text-sm text-slate-600">Un exercice apparaît dès la première écriture comptable de son année.</p>
    </div>
  {% endif %}
</div>
{% endblock %}
```

#### `apps/accounting/templates/accounting/compte_resultat_print.html`

*54 lignes*

```django
{% load static humanize %}<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Compte de résultat · {{ entreprise.nom }}</title>
  {% include "rapports/_style_impression.html" %}
</head>
<body>
  {% include "rapports/_entete_impression.html" %}

  {% if rapport_resultat %}
    <p class="petit">
      Produits et charges de l'exercice seulement (contrairement au bilan, qui est cumulé
      depuis l'origine).
    </p>

    <h2>Produits</h2>
    <table>
      <thead><tr><th>Compte</th><th class="droite">Montant</th></tr></thead>
      <tbody>
        {% for l in rapport_resultat.produits %}
          <tr><td>{{ l.compte__numero }} — {{ l.compte__libelle }}</td><td class="droite">{{ l.montant|floatformat:0|intcomma }}</td></tr>
        {% empty %}
          <tr><td colspan="2">Aucun produit sur la période.</td></tr>
        {% endfor %}
      </tbody>
      <tfoot><tr><td><strong>Total produits</strong></td><td class="droite"><strong>{{ rapport_resultat.total_produits|floatformat:0|intcomma }}</strong></td></tr></tfoot>
    </table>

    <h2>Charges</h2>
    <table>
      <thead><tr><th>Compte</th><th class="droite">Montant</th></tr></thead>
      <tbody>
        {% for l in rapport_resultat.charges %}
          <tr><td>{{ l.compte__numero }} — {{ l.compte__libelle }}</td><td class="droite">{{ l.montant|floatformat:0|intcomma }}</td></tr>
        {% empty %}
          <tr><td colspan="2">Aucune charge sur la période.</td></tr>
        {% endfor %}
      </tbody>
      <tfoot><tr><td><strong>Total charges</strong></td><td class="droite"><strong>{{ rapport_resultat.total_charges|floatformat:0|intcomma }}</strong></td></tr></tfoot>
    </table>

    <div class="cartouche">
      <div><dt>Résultat net {% if rapport_resultat.resultat_net >= 0 %}(bénéfice){% else %}(perte){% endif %}</dt><dd>{{ rapport_resultat.resultat_net|floatformat:0|intcomma }} FCFA</dd></div>
    </div>
  {% else %}
    <p class="petit">Aucun exercice pour l'instant.</p>
  {% endif %}

  {% include "rapports/_pied_impression.html" %}
  <script src="{% static 'js/app.js' %}" defer></script>
</body>
</html>
```

#### `apps/accounting/templates/accounting/declaration_tva.html`

*53 lignes*

```django
{% extends "base.html" %}
{% load ui humanize %}
{% block titre %}Déclaration TVA{% endblock %}
{% block entete %}Comptabilité{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-4xl">
  <div class="flex flex-wrap items-start justify-between gap-3">
    <h1 class="text-2xl font-bold text-slate-900">Rapports comptables</h1>
    <div class="flex flex-wrap items-center gap-2">
    <a href="{% url 'accounting:declaration_tva_imprimer' %}?{{ request.GET.urlencode }}" target="_blank" rel="noopener"
       class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
      <i class="fa-solid fa-print" aria-hidden="true"></i> Imprimer
    </a>
    {% url 'accounting:declaration_tva_xlsx' as url_xlsx %}{% include "components/_bouton_xlsx.html" with url=url_xlsx %}
    </div>
  </div>
  {% include "accounting/_nav_rapports.html" %}

  <form method="get" class="mt-5 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
    {% include "components/_champ.html" with champ=form.debut %}
    {% include "components/_champ.html" with champ=form.fin %}
    <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Afficher</button>
  </form>

  <p class="mt-3 text-sm text-slate-600">
    Période du {{ rapport.debut|date:"d/m/Y" }} au {{ rapport.fin|date:"d/m/Y" }} — le mois en cours par
    défaut si aucune date n'est choisie. Comptes 443300 (TVA facturée sur ventes) et 445200 (TVA
    déductible sur achats/dépenses).
  </p>

  <div class="mt-4 grid grid-cols-1 gap-5 sm:grid-cols-2">
    <div class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <dt class="text-sm text-slate-600">TVA collectée (ventes)</dt>
      <dd class="mt-1 text-2xl font-bold text-slate-900">{{ rapport.tva_collectee|floatformat:0|intcomma }} FCFA</dd>
    </div>
    <div class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <dt class="text-sm text-slate-600">TVA déductible (dépenses)</dt>
      <dd class="mt-1 text-2xl font-bold text-slate-900">{{ rapport.tva_deductible|floatformat:0|intcomma }} FCFA</dd>
    </div>
  </div>

  <section class="mt-5 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
    <p class="flex justify-between text-base font-semibold {% if rapport.tva_nette >= 0 %}text-red-800{% else %}text-green-800{% endif %}">
      <span>{% if rapport.tva_nette >= 0 %}TVA nette à payer{% else %}Crédit de TVA reportable{% endif %}</span>
      <span>{{ rapport.tva_nette|floatformat:0|intcomma }} FCFA</span>
    </p>
    <p class="mt-2 text-xs text-slate-500">
      TVA collectée − TVA déductible. {% if rapport.tva_nette >= 0 %}Montant à reverser au Trésor Public.{% else %}Négative : crédit de TVA à reporter sur la période suivante.{% endif %}
    </p>
  </section>
</div>
{% endblock %}
```

#### `apps/accounting/templates/accounting/declaration_tva_print.html`

*31 lignes*

```django
{% load static humanize %}<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Déclaration TVA · {{ entreprise.nom }}</title>
  {% include "rapports/_style_impression.html" %}
</head>
<body>
  {% include "rapports/_entete_impression.html" %}

  <p class="petit">Comptes 443300 (TVA facturée sur ventes) et 445200 (TVA déductible sur achats/dépenses).</p>

  <table>
    <thead><tr><th>Ligne</th><th class="droite">Montant</th></tr></thead>
    <tbody>
      <tr><td>TVA collectée (ventes)</td><td class="droite">{{ rapport_tva.tva_collectee|floatformat:0|intcomma }}</td></tr>
      <tr><td>TVA déductible (dépenses)</td><td class="droite">{{ rapport_tva.tva_deductible|floatformat:0|intcomma }}</td></tr>
    </tbody>
    <tfoot>
      <tr>
        <td><strong>{% if rapport_tva.tva_nette >= 0 %}TVA nette à payer{% else %}Crédit de TVA reportable{% endif %}</strong></td>
        <td class="droite"><strong>{{ rapport_tva.tva_nette|floatformat:0|intcomma }}</strong></td>
      </tr>
    </tfoot>
  </table>

  {% include "rapports/_pied_impression.html" %}
  <script src="{% static 'js/app.js' %}" defer></script>
</body>
</html>
```

## Étape 4 — Tests et compilation des styles

#### `apps/accounting/tests/test_admin_lecture_seule.py`

*94 lignes* — Audit ACC-01 : le grand livre est en lecture seule dans l'admin, et un sens inconnu est refusé.

```python
"""Audit ACC-01 : le grand livre est en lecture seule dans l'admin, et un sens inconnu est refusé."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounting import services
from apps.accounting.exceptions import EcritureNonEquilibree
from apps.accounting.models import Compte, EcritureComptable, Journal, SensEcriture, StatutEcriture
from apps.accounting.services import LigneSaisie
from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _ecriture():
    return services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2026, 3, 1), libelle="Apport",
        lignes=[
            LigneSaisie(compte="571000", sens=SensEcriture.DEBIT, montant=Decimal("500")),
            LigneSaisie(compte="101000", sens=SensEcriture.CREDIT, montant=Decimal("500")),
        ],
    )


@pytest.fixture
def admin_client(client):
    client.force_login(UserFactory(role=Role.ADMIN, is_staff=True, is_superuser=True))
    return client


def test_un_sens_inconnu_est_refuse_au_lieu_d_etre_stocke_hors_des_totaux():
    with pytest.raises(EcritureNonEquilibree, match="Sens inconnu"):
        services.passer_ecriture(
            journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date(2026, 3, 1), libelle="Piège",
            lignes=[
                LigneSaisie(compte="571000", sens=SensEcriture.DEBIT, montant=Decimal("500")),
                LigneSaisie(compte="101000", sens=SensEcriture.CREDIT, montant=Decimal("500")),
                LigneSaisie(compte="108000", sens="X", montant=Decimal("999")),
            ],
        )

    assert not EcritureComptable.objects.exists()


def test_l_admin_ne_permet_pas_de_creer_ni_de_modifier_une_ecriture(admin_client):
    ecriture = _ecriture()

    ajout = admin_client.get(reverse("admin:accounting_ecriturecomptable_add"))
    modification = admin_client.post(
        reverse("admin:accounting_ecriturecomptable_change", args=[ecriture.pk]), {"statut": StatutEcriture.BROUILLON}
    )

    assert ajout.status_code == 403
    ecriture.refresh_from_db()
    assert ecriture.statut == StatutEcriture.VALIDEE
    assert modification.status_code in (200, 302, 403)  # jamais une modification appliquée


def test_l_admin_affiche_une_ecriture_en_lecture_seule(admin_client):
    ecriture = _ecriture()

    reponse = admin_client.get(reverse("admin:accounting_ecriturecomptable_change", args=[ecriture.pk]))

    assert reponse.status_code == 200
    assert b'name="_save"' not in reponse.content  # pas de bouton « Enregistrer »


def test_l_admin_ne_peut_pas_rouvrir_un_exercice(admin_client):
    exercice = services.exercice_pour(date(2025, 6, 1))
    exercice.statut = "CLOTURE"
    exercice.save(update_fields=["statut", "updated_at"])

    admin_client.post(
        reverse("admin:accounting_exercicecomptable_change", args=[exercice.pk]), {"statut": "OUVERT"}
    )

    exercice.refresh_from_db()
    assert exercice.statut == "CLOTURE"


def test_le_numero_et_la_nature_d_un_compte_ne_se_modifient_plus_dans_l_admin(admin_client):
    compte = Compte.objects.get(numero="571000")

    admin_client.post(
        reverse("admin:accounting_compte_change", args=[compte.pk]),
        {"numero": "999999", "libelle": "Caisse", "nature": "CHARGE", "actif": "on"},
    )

    compte.refresh_from_db()
    assert (compte.numero, compte.nature) == ("571000", "ACTIF")
```

#### `apps/accounting/tests/test_contre_passation_manuelle.py`

*106 lignes* — Corriger une opération diverse validée : contre-passation depuis l'écran, DIRECTION seulement, motif obligatoire.

```python
"""Corriger une opération diverse validée : contre-passation depuis l'écran, DIRECTION seulement, motif obligatoire."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounting import services
from apps.accounting.exceptions import ActionComptableNonAutorisee, ContrePassationImpossible
from apps.accounting.models import EcritureComptable, SensEcriture, StatutEcriture
from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing.tests.helpers import direction, finances

pytestmark = pytest.mark.django_db


def _od_validee():
    ecriture = services.creer_ecriture_manuelle(finances(), date_ecriture=date(2026, 3, 1), libelle="Apport")
    services.ajouter_ligne_manuelle(ecriture, finances(), compte="571000", sens=SensEcriture.DEBIT, montant=Decimal("500"))
    services.ajouter_ligne_manuelle(ecriture, finances(), compte="101000", sens=SensEcriture.CREDIT, montant=Decimal("500"))
    return services.valider_ecriture_manuelle(ecriture, direction())


def test_la_direction_contre_passe_une_operation_diverse_validee():
    ecriture = _od_validee()

    inverse = services.contre_passer_ecriture_manuelle(ecriture, direction(), motif="Montant erroné")

    assert inverse.statut == StatutEcriture.VALIDEE
    assert services.contre_passation_de(ecriture) == inverse
    sens = {(l.compte.numero, l.sens) for l in inverse.lignes.select_related("compte")}
    assert sens == {("571000", SensEcriture.CREDIT), ("101000", SensEcriture.DEBIT)}
    assert "Montant erroné" in inverse.libelle


def test_la_contre_passation_est_reservee_a_la_direction_en_controle_strict():
    ecriture = _od_validee()

    for acteur in (finances(), UserFactory(role=Role.ADMIN, is_superuser=True)):
        with pytest.raises(ActionComptableNonAutorisee):
            services.contre_passer_ecriture_manuelle(ecriture, acteur, motif="Test")


def test_le_motif_est_obligatoire():
    with pytest.raises(ContrePassationImpossible, match="motif"):
        services.contre_passer_ecriture_manuelle(_od_validee(), direction(), motif="   ")


def test_une_ecriture_deja_contre_passee_ne_l_est_pas_deux_fois():
    ecriture = _od_validee()
    services.contre_passer_ecriture_manuelle(ecriture, direction(), motif="Erreur")

    with pytest.raises(ContrePassationImpossible, match="déjà contre-passée"):
        services.contre_passer_ecriture_manuelle(ecriture, direction(), motif="Encore")

    assert EcritureComptable.objects.filter(origine=services.ORIGINE_CONTRE_PASSATION).count() == 1


def test_une_ecriture_automatique_ne_se_contre_passe_pas_par_cette_voie():
    automatique = services.passer_ecriture(
        journal="OD", date_ecriture=date(2026, 3, 1), libelle="Auto", origine="MOUVEMENT", origine_id=1,
        lignes=[
            services.LigneSaisie(compte="571000", sens=SensEcriture.DEBIT, montant=Decimal("10")),
            services.LigneSaisie(compte="101000", sens=SensEcriture.CREDIT, montant=Decimal("10")),
        ],
    )

    with pytest.raises(ContrePassationImpossible, match="à la source"):
        services.contre_passer_ecriture_manuelle(automatique, direction(), motif="Test")


def test_un_brouillon_ne_se_contre_passe_pas():
    brouillon = services.creer_ecriture_manuelle(finances(), date_ecriture=date(2026, 3, 1), libelle="B")

    with pytest.raises(ContrePassationImpossible):
        services.contre_passer_ecriture_manuelle(brouillon, direction(), motif="Test")


def test_l_ecran_propose_la_contre_passation_a_la_direction_seulement(client):
    ecriture = _od_validee()
    url_detail = reverse("accounting:ecriture_manuelle", args=[ecriture.pk])
    url_action = reverse("accounting:ecriture_manuelle_contre_passer", args=[ecriture.pk])

    client.force_login(UserFactory(role=Role.DIRECTION))
    assert url_action in client.get(url_detail).content.decode()
    client.force_login(UserFactory(role=Role.FINANCES))
    assert url_action not in client.get(url_detail).content.decode()
    assert client.post(url_action, {"motif": "x"}).status_code == 403


def test_contre_passer_via_l_ecran_affiche_le_resultat_puis_masque_le_bouton(client):
    ecriture = _od_validee()
    client.force_login(UserFactory(role=Role.DIRECTION))
    url_detail = reverse("accounting:ecriture_manuelle", args=[ecriture.pk])
    url_action = reverse("accounting:ecriture_manuelle_contre_passer", args=[ecriture.pk])

    sans_motif = client.post(url_action, {"motif": ""}, follow=True)
    assert "motif" in sans_motif.content.decode().lower()
    assert not EcritureComptable.objects.filter(origine=services.ORIGINE_CONTRE_PASSATION).exists()

    reponse = client.post(url_action, {"motif": "Montant erroné"}, follow=True)
    page = reponse.content.decode()
    assert "contre-passée par" in page
    assert url_action not in client.get(url_detail).content.decode()
```

#### `apps/accounting/tests/test_views.py`

*481 lignes* — Écrans de la saisie manuelle d'opérations diverses (Phase 4) et des exercices comptables

```python
"""Écrans de la saisie manuelle d'opérations diverses (Phase 4) et des exercices comptables
(Phase 5)."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounting import services
from apps.accounting.models import (
    Compte,
    EcritureComptable,
    Journal,
    SensEcriture,
    StatutEcriture,
    StatutExercice,
)

from .factories import CompteFactory

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    compte = UserFactory(role=role)
    client.force_login(compte)
    return compte


def _brouillon(**kwargs):
    return services.creer_ecriture_manuelle(
        UserFactory(role=Role.FINANCES), date_ecriture=date(2026, 9, 5), libelle="Test OD", **kwargs
    )


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.FINANCES, Role.RH])
def test_la_liste_est_accessible_aux_roles_de_consultation(client, role):
    _connecte(client, role)

    assert client.get(reverse("accounting:ecritures_manuelles")).status_code == 200


@pytest.mark.parametrize("role", [Role.PARCAUTO, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_la_liste_est_interdite_aux_autres_roles(client, role):
    _connecte(client, role)

    assert client.get(reverse("accounting:ecritures_manuelles")).status_code == 403


@pytest.mark.parametrize("role", [Role.PARCAUTO, Role.CHAUFFEUR])
def test_seuls_les_roles_de_saisie_creent_une_ecriture(client, role):
    _connecte(client, role)

    assert client.get(reverse("accounting:ecriture_manuelle_nouvelle")).status_code == 403


def test_creer_une_ecriture_manuelle_via_l_ecran(client):
    _connecte(client, Role.FINANCES)

    reponse = client.post(
        reverse("accounting:ecriture_manuelle_nouvelle"),
        {"date_ecriture": "2026-09-05", "libelle": "Régularisation caisse"},
    )

    ecriture = EcritureComptable.objects.get()
    assert reponse.status_code == 302
    assert ecriture.statut == StatutEcriture.BROUILLON
    assert ecriture.libelle == "Régularisation caisse"


def test_ajouter_puis_supprimer_une_ligne_via_l_ecran(client):
    _connecte(client, Role.FINANCES)
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = _brouillon()

    client.post(
        reverse("accounting:ligne_ajouter", args=[ecriture.pk]),
        {"compte": charge.numero, "sens": SensEcriture.DEBIT, "montant": "5000", "libelle": ""},
    )
    assert ecriture.lignes.count() == 1
    ligne = ecriture.lignes.first()

    reponse = client.post(reverse("accounting:ligne_supprimer", args=[ecriture.pk, ligne.pk]))

    assert reponse.status_code == 302
    assert ecriture.lignes.count() == 0


def test_la_fiche_propose_la_validation_a_la_direction_une_fois_equilibree(client):
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = _brouillon()
    services.ajouter_ligne_manuelle(
        ecriture, UserFactory(role=Role.FINANCES), compte=charge.numero, sens=SensEcriture.DEBIT,
        montant=Decimal("5000"),
    )
    services.ajouter_ligne_manuelle(
        ecriture, UserFactory(role=Role.FINANCES), compte=tresorerie.numero, sens=SensEcriture.CREDIT,
        montant=Decimal("5000"),
    )

    _connecte(client, Role.DIRECTION)
    page = client.get(reverse("accounting:ecriture_manuelle", args=[ecriture.pk])).content.decode()
    assert reverse("accounting:ecriture_manuelle_valider", args=[ecriture.pk]) in page

    _connecte(client, Role.FINANCES)
    page = client.get(reverse("accounting:ecriture_manuelle", args=[ecriture.pk])).content.decode()
    assert reverse("accounting:ecriture_manuelle_valider", args=[ecriture.pk]) not in page


def test_valider_via_l_ecran_est_reserve_a_la_direction(client):
    charge, tresorerie = CompteFactory(), CompteFactory()
    ecriture = _brouillon()
    services.ajouter_ligne_manuelle(
        ecriture, UserFactory(role=Role.FINANCES), compte=charge.numero, sens=SensEcriture.DEBIT,
        montant=Decimal("5000"),
    )
    services.ajouter_ligne_manuelle(
        ecriture, UserFactory(role=Role.FINANCES), compte=tresorerie.numero, sens=SensEcriture.CREDIT,
        montant=Decimal("5000"),
    )

    _connecte(client, Role.FINANCES)
    assert client.post(reverse("accounting:ecriture_manuelle_valider", args=[ecriture.pk])).status_code == 403

    _connecte(client, Role.DIRECTION)
    reponse = client.post(reverse("accounting:ecriture_manuelle_valider", args=[ecriture.pk]))
    assert reponse.status_code == 302
    ecriture.refresh_from_db()
    assert ecriture.statut == StatutEcriture.VALIDEE


def test_abandonner_via_l_ecran(client):
    _connecte(client, Role.FINANCES)
    ecriture = _brouillon()

    reponse = client.post(reverse("accounting:ecriture_manuelle_abandonner", args=[ecriture.pk]))

    assert reponse.status_code == 302
    assert not EcritureComptable.objects.filter(pk=ecriture.pk).exists()


# --- exercices comptables (Phase 5) ---


def test_la_liste_des_exercices_est_accessible_en_consultation(client):
    services.exercice_pour(date(2026, 9, 5))
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:exercices"))

    assert reponse.status_code == 200
    assert "2026" in reponse.content.decode()


def test_seule_la_direction_voit_le_bouton_cloturer(client):
    exercice = services.exercice_pour(date(2026, 9, 5))
    url_cloturer = reverse("accounting:exercice_cloturer", args=[exercice.pk])

    _connecte(client, Role.DIRECTION)
    page = client.get(reverse("accounting:exercices")).content.decode()
    assert url_cloturer in page

    _connecte(client, Role.FINANCES)
    page = client.get(reverse("accounting:exercices")).content.decode()
    assert url_cloturer not in page


def test_cloturer_via_l_ecran_est_reserve_a_la_direction(client):
    exercice = services.exercice_pour(date(2024, 6, 5))

    _connecte(client, Role.FINANCES)
    assert client.post(reverse("accounting:exercice_cloturer", args=[exercice.pk])).status_code == 403

    _connecte(client, Role.DIRECTION)
    reponse = client.post(reverse("accounting:exercice_cloturer", args=[exercice.pk]))
    assert reponse.status_code == 302
    exercice.refresh_from_db()
    assert exercice.statut == StatutExercice.CLOTURE


# --- plan comptable (Lot F, autonomie comptable) ---


def test_le_plan_comptable_est_accessible_en_consultation(client):
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:plan_comptable"))

    assert reponse.status_code == 200
    assert reponse.context["peut_gerer"] is True


def test_le_bouton_nouveau_compte_apparait_pour_un_role_autorise(client):
    _connecte(client, Role.RH)  # RH a la même largeur que Finances (CONSULTATION et GESTION)
    page = client.get(reverse("accounting:plan_comptable")).content.decode()
    assert reverse("accounting:compte_nouveau") in page


def test_creer_un_compte_via_l_ecran(client):
    _connecte(client, Role.FINANCES)

    reponse = client.post(
        reverse("accounting:compte_nouveau"),
        {"numero": "999999", "libelle": "Compte de test", "nature": "CHARGE"},
    )

    assert reponse.status_code == 302
    assert Compte.objects.filter(numero="999999", libelle="Compte de test").exists()


def test_creer_un_compte_avec_un_numero_deja_pris_affiche_une_erreur(client):
    CompteFactory(numero="999999")
    _connecte(client, Role.FINANCES)

    reponse = client.post(
        reverse("accounting:compte_nouveau"),
        {"numero": "999999", "libelle": "Doublon", "nature": "CHARGE"},
    )

    assert reponse.status_code == 200
    assert "existe déjà" in reponse.content.decode()


def test_modifier_un_compte_via_l_ecran(client):
    compte = CompteFactory(libelle="Ancien", actif=True)
    _connecte(client, Role.FINANCES)

    reponse = client.post(
        reverse("accounting:compte_modifier", args=[compte.pk]), {"libelle": "Nouveau"}
    )

    assert reponse.status_code == 302
    compte.refresh_from_db()
    assert compte.libelle == "Nouveau"
    assert compte.actif is False  # case à cocher absente du POST = décochée


def test_gestion_du_plan_comptable_est_interdite_aux_autres_roles(client):
    compte = CompteFactory()
    _connecte(client, Role.CHAUFFEUR)

    assert client.get(reverse("accounting:plan_comptable")).status_code == 403
    assert client.get(reverse("accounting:compte_nouveau")).status_code == 403
    assert client.get(reverse("accounting:compte_modifier", args=[compte.pk])).status_code == 403


# --- rapports comptables (Phase 6) ---


def _passer_ecriture_od(charge, tresorerie, *, date_ecriture, montant="5000"):
    return services.passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES, date_ecriture=date_ecriture, libelle="Test",
        lignes=[
            services.LigneSaisie(compte=charge.numero, sens=SensEcriture.DEBIT, montant=Decimal(montant)),
            services.LigneSaisie(compte=tresorerie.numero, sens=SensEcriture.CREDIT, montant=Decimal(montant)),
        ],
    )


@pytest.mark.parametrize(
    "nom_url",
    ["accounting:grand_livre", "accounting:balance", "accounting:bilan", "accounting:compte_resultat"],
)
@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.FINANCES, Role.RH])
def test_les_rapports_sont_accessibles_aux_roles_de_consultation(client, role, nom_url):
    _connecte(client, role)

    assert client.get(reverse(nom_url)).status_code == 200


@pytest.mark.parametrize(
    "nom_url",
    ["accounting:grand_livre", "accounting:balance", "accounting:bilan", "accounting:compte_resultat"],
)
@pytest.mark.parametrize("role", [Role.PARCAUTO, Role.CHAUFFEUR])
def test_les_rapports_sont_interdits_aux_autres_roles(client, role, nom_url):
    _connecte(client, role)

    assert client.get(reverse(nom_url)).status_code == 403


def test_grand_livre_sans_compte_selectionne_n_affiche_aucune_ligne(client):
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:grand_livre"))

    assert reponse.context["lignes"] is None


def test_grand_livre_avec_compte_selectionne_affiche_les_lignes(client):
    charge, tresorerie = CompteFactory(), CompteFactory()
    _passer_ecriture_od(charge, tresorerie, date_ecriture=date(2026, 9, 5))
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:grand_livre"), {"compte": charge.numero})

    lignes = reponse.context["lignes"]
    assert len(lignes) == 1
    assert lignes[0]["solde_cumule"] == Decimal("5000")


def test_balance_totalise_debit_et_credit(client):
    charge, tresorerie = CompteFactory(), CompteFactory()
    _passer_ecriture_od(charge, tresorerie, date_ecriture=date(2026, 9, 5), montant="7000")
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:balance"))

    assert reponse.context["totaux"] == {"debit": Decimal("7000"), "credit": Decimal("7000")}


def test_bilan_sans_aucun_exercice_n_affiche_pas_de_rapport(client):
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:bilan"))

    assert reponse.context["exercice"] is None
    assert reponse.context["rapport"] is None


def test_bilan_choisit_l_exercice_le_plus_recent_par_defaut(client):
    services.exercice_pour(date(2025, 6, 1))
    exercice_2026 = services.exercice_pour(date(2026, 9, 5))
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:bilan"))

    assert reponse.context["exercice"] == exercice_2026
    assert reponse.context["rapport"] is not None


def test_bilan_change_d_exercice_via_le_parametre(client):
    exercice_2025 = services.exercice_pour(date(2025, 6, 1))
    services.exercice_pour(date(2026, 9, 5))
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:bilan"), {"exercice": 2025})

    assert reponse.context["exercice"] == exercice_2025


def test_compte_de_resultat_choisit_l_exercice_le_plus_recent_par_defaut(client):
    services.exercice_pour(date(2025, 6, 1))
    exercice_2026 = services.exercice_pour(date(2026, 9, 5))
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:compte_resultat"))

    assert reponse.context["exercice"] == exercice_2026
    assert reponse.context["rapport"] is not None


def test_compte_de_resultat_sans_aucun_exercice_n_affiche_pas_de_rapport(client):
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:compte_resultat"))

    assert reponse.context["exercice"] is None
    assert reponse.context["rapport"] is None


# --- versions imprimables des rapports (Phase 6 bis) ---


@pytest.mark.parametrize(
    "nom_url",
    [
        "accounting:grand_livre_imprimer",
        "accounting:balance_imprimer",
        "accounting:bilan_imprimer",
        "accounting:compte_resultat_imprimer",
        "accounting:declaration_tva_imprimer",
    ],
)
@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.FINANCES, Role.RH])
def test_les_versions_imprimables_sont_accessibles_aux_roles_de_consultation(client, role, nom_url):
    _connecte(client, role)

    assert client.get(reverse(nom_url)).status_code == 200


@pytest.mark.parametrize(
    "nom_url",
    [
        "accounting:grand_livre_imprimer",
        "accounting:balance_imprimer",
        "accounting:bilan_imprimer",
        "accounting:compte_resultat_imprimer",
        "accounting:declaration_tva_imprimer",
    ],
)
def test_les_versions_imprimables_sont_interdites_aux_autres_roles(client, nom_url):
    _connecte(client, Role.CHAUFFEUR)

    assert client.get(reverse(nom_url)).status_code == 403


def test_grand_livre_imprimer_affiche_les_lignes_du_compte(client):
    charge, tresorerie = CompteFactory(), CompteFactory()
    _passer_ecriture_od(charge, tresorerie, date_ecriture=date(2026, 9, 5))
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:grand_livre_imprimer"), {"compte": charge.numero})

    assert reponse.status_code == 200
    assert reponse.context["lignes"] is not None
    assert len(reponse.context["lignes"]) == 1
    contenu = reponse.content.decode()
    assert "Généré le" in contenu  # pied de rapport commun (apps/core/rapports.py)


def test_balance_imprimer_affiche_les_totaux(client):
    charge, tresorerie = CompteFactory(), CompteFactory()
    _passer_ecriture_od(charge, tresorerie, date_ecriture=date(2026, 9, 5), montant="7000")
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:balance_imprimer"))

    assert reponse.context["totaux"] == {"debit": Decimal("7000"), "credit": Decimal("7000")}


def test_bilan_imprimer_reprend_l_exercice_le_plus_recent(client):
    exercice = services.exercice_pour(date(2026, 9, 5))
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:bilan_imprimer"))

    assert reponse.context["exercice"] == exercice
    assert reponse.context["rapport_bilan"] is not None


def test_compte_resultat_imprimer_reprend_l_exercice_le_plus_recent(client):
    exercice = services.exercice_pour(date(2026, 9, 5))
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:compte_resultat_imprimer"))

    assert reponse.context["exercice"] == exercice
    assert reponse.context["rapport_resultat"] is not None


# --- déclaration TVA (Phase 6 ter) ---


def test_declaration_tva_par_defaut_porte_sur_le_mois_en_cours(client):
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("accounting:declaration_tva"))

    assert reponse.status_code == 200
    rapport = reponse.context["rapport"]
    assert rapport["debut"].day == 1
    assert rapport["fin"].month == rapport["debut"].month


def test_declaration_tva_accepte_une_periode_choisie(client):
    _connecte(client, Role.FINANCES)

    reponse = client.get(
        reverse("accounting:declaration_tva"), {"debut": "2026-01-01", "fin": "2026-03-31"}
    )

    rapport = reponse.context["rapport"]
    assert (rapport["debut"], rapport["fin"]) == (date(2026, 1, 1), date(2026, 3, 31))


def test_declaration_tva_imprimer_affiche_les_totaux(client):
    _connecte(client, Role.FINANCES)

    reponse = client.get(
        reverse("accounting:declaration_tva_imprimer"), {"debut": "2026-01-01", "fin": "2026-03-31"}
    )

    assert reponse.status_code == 200
    rapport = reponse.context["rapport_tva"]
    assert (rapport["debut"], rapport["fin"]) == (date(2026, 1, 1), date(2026, 3, 31))
    contenu = reponse.content.decode()
    assert "Généré le" in contenu
```

#### `apps/audit/tests/test_validation_suppression.py`

*123 lignes* — Audit M1-06 : les validations sortent en VALIDATE, une suppression physique est journalisée, le copilote est

```python
"""Audit M1-06 : les validations sortent en VALIDATE, une suppression physique est journalisée, le copilote est
audité ; M1-09 : le CSV contient aussi les anciennes/nouvelles valeurs et le user-agent."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounting import services as compta
from apps.accounting.models import Journal, LigneEcriture, SensEcriture
from apps.accounting.services import LigneSaisie
from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.audit.models import ActionChoices, AuditLog
from apps.billing.tests.helpers import direction, emise

pytestmark = pytest.mark.django_db


def test_la_validation_d_une_facture_est_journalisee_en_validate():
    facture = emise(prix="1000000")  # brouillon -> émise par la DIRECTION

    validations = AuditLog.objects.filter(action=ActionChoices.VALIDATE, entite="Facture", entite_id=facture.pk)

    assert validations.count() == 1
    assert validations.get().nouvelle_valeur["statut"] == "EMISE"
    # et non plus une simple « modification » du statut
    assert not AuditLog.objects.filter(
        action=ActionChoices.UPDATE, entite="Facture", entite_id=facture.pk, nouvelle_valeur__statut="EMISE"
    ).exists()


def test_la_validation_d_une_ecriture_manuelle_est_journalisee_en_validate():
    from apps.billing.tests.helpers import finances

    ecriture = compta.creer_ecriture_manuelle(finances(), date_ecriture=date(2026, 3, 1), libelle="Apport")
    compta.ajouter_ligne_manuelle(ecriture, finances(), compte="571000", sens=SensEcriture.DEBIT, montant=Decimal("500"))
    compta.ajouter_ligne_manuelle(ecriture, finances(), compte="101000", sens=SensEcriture.CREDIT, montant=Decimal("500"))

    compta.valider_ecriture_manuelle(ecriture, direction())

    assert AuditLog.objects.filter(action=ActionChoices.VALIDATE, entite="EcritureComptable", entite_id=ecriture.pk).count() == 1


def test_une_modification_ordinaire_reste_une_modification():
    from apps.billing.models import Facture

    facture = emise(prix="1000000")
    Facture.objects.filter(pk=facture.pk)  # lisible
    facture.refresh_from_db()
    facture.date_echeance = date(2027, 1, 31)
    facture.save()

    assert AuditLog.objects.filter(action=ActionChoices.UPDATE, entite="Facture", entite_id=facture.pk).exists()
    assert AuditLog.objects.filter(action=ActionChoices.VALIDATE, entite="Facture", entite_id=facture.pk).count() == 1


def test_une_suppression_physique_est_journalisee():
    ecriture = compta.creer_ecriture_manuelle(
        direction(), date_ecriture=date(2026, 3, 1), libelle="Brouillon à corriger"
    )
    ligne = compta.ajouter_ligne_manuelle(
        ecriture, direction(), compte="571000", sens=SensEcriture.DEBIT, montant=Decimal("500")
    )

    identifiant = ligne.pk  # Django remet le pk à None sur l'instance supprimée
    compta.supprimer_ligne_manuelle(ligne, direction())

    suppression = AuditLog.objects.get(action=ActionChoices.DELETE, entite="LigneEcriture", entite_id=identifiant)
    assert suppression.ancienne_valeur["montant"] == "500.00"
    assert suppression.nouvelle_valeur is None
    assert not LigneEcriture.objects.filter(pk=identifiant).exists()


def test_le_copilote_est_audite():
    from apps.drivers.models import Copilote
    from apps.hr.tests.factories import PersonnelFactory

    personnel = PersonnelFactory(poste="Copilote")
    copilote = Copilote.objects.get(personnel=personnel)
    copilote.statut = "SUSPENDU"
    copilote.save()

    assert AuditLog.objects.filter(entite="Copilote", entite_id=copilote.pk, action=ActionChoices.UPDATE).exists()


def test_le_csv_contient_les_valeurs_modifiees_et_le_user_agent(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    AuditLog.objects.create(
        action=ActionChoices.UPDATE, module="RH", entite="Personnel", entite_id=3,
        ancienne_valeur={"salaire": "100"}, nouvelle_valeur={"salaire": "200"}, user_agent="=cmd|' /C calc'!A0",
    )

    contenu = client.get(reverse("audit:export_csv"), {"module": "RH"}).content.decode("utf-8-sig")

    assert "Ancienne valeur;Nouvelle valeur;User-agent" in contenu
    assert '{""salaire"": ""100""}' in contenu and '{""salaire"": ""200""}' in contenu
    assert "'=cmd" in contenu  # le user-agent ne s'exécute pas comme une formule dans Excel


def _od_validee_par(auteur, validateur):
    ecriture = compta.creer_ecriture_manuelle(auteur, date_ecriture=date(2026, 3, 1), libelle="Apport")
    compta.ajouter_ligne_manuelle(ecriture, auteur, compte="571000", sens=SensEcriture.DEBIT, montant=Decimal("500"))
    compta.ajouter_ligne_manuelle(ecriture, auteur, compte="101000", sens=SensEcriture.CREDIT, montant=Decimal("500"))
    compta.valider_ecriture_manuelle(ecriture, validateur)
    return AuditLog.objects.get(action=ActionChoices.VALIDATE, entite="EcritureComptable", entite_id=ecriture.pk)


def test_une_validation_par_l_auteur_lui_meme_est_signalee_dans_le_journal():
    patron = direction()

    validation = _od_validee_par(patron, patron)

    assert validation.nouvelle_valeur["auto_validation"] is True


def test_une_validation_par_une_autre_personne_n_est_pas_signalee():
    from apps.billing.tests.helpers import finances

    validation = _od_validee_par(finances(), direction())

    assert "auto_validation" not in validation.nouvelle_valeur
```

#### `apps/core/tests/test_xlsx.py`

*205 lignes* — Export Excel : valeurs brutes (nombres, dates), pas de formule injectée, droits de la liste respectés.

```python
"""Export Excel : valeurs brutes (nombres, dates), pas de formule injectée, droits de la liste respectés."""

from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO

import pytest
from django.urls import reverse
from openpyxl import load_workbook

from apps.accounting import services as compta
from apps.accounting.models import Journal, SensEcriture
from apps.accounting.services import LigneSaisie
from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing.tests.helpers import JOUR, direction, emise, finances
from apps.core.xlsx import TYPE_XLSX, classeur

pytestmark = pytest.mark.django_db


def _ouvrir(reponse):
    assert reponse.status_code == 200
    assert reponse["Content-Type"] == TYPE_XLSX
    assert reponse["Content-Disposition"].startswith('attachment; filename="')
    return load_workbook(BytesIO(reponse.content))


def _lignes(feuille):
    return [[c.value for c in ligne] for ligne in feuille.iter_rows()]


# --- le classeur ---


def test_les_montants_sont_des_nombres_les_dates_des_dates_et_les_formules_du_texte():
    octets = classeur([{
        "titre": "Essai", "sous_titre": "Période", "entetes": ["A", "B", "C", "D"],
        "lignes": [[Decimal("1234.50"), date(2026, 3, 1), datetime(2026, 3, 1, 8, 30, tzinfo=timezone.utc), "=1+1"]],
        "pied": ["", "", "Total", Decimal("1234.50")],
    }])

    feuille = load_workbook(BytesIO(octets))["Essai"]

    assert feuille["A5"].value == 1234.5 and feuille["A5"].number_format == "#,##0.00"
    assert feuille["B5"].value.date() == date(2026, 3, 1)
    assert feuille["D5"].value == "=1+1" and feuille["D5"].data_type == "s"  # du texte, jamais une formule
    assert feuille["D6"].value == 1234.5 and feuille["D6"].font.bold


def test_les_titres_de_feuille_sont_rendus_valides_et_uniques():
    octets = classeur([
        {"titre": "Bilan: actif/passif [2026]", "entetes": ["X"], "lignes": []},
        {"titre": "Bilan: actif/passif [2026]", "entetes": ["X"], "lignes": []},
    ])

    noms = load_workbook(BytesIO(octets)).sheetnames

    assert len(noms) == 2 and len(set(n.lower() for n in noms)) == 2
    assert all(len(n) <= 31 and not set("[]:*?/\\") & set(n) for n in noms)


# --- listes ---


def test_export_des_factures_avec_montants_numeriques(client):
    emise(prix="1000000")
    client.force_login(finances())

    feuille = _ouvrir(client.get(reverse("billing:factures_xlsx"))).active

    lignes = _lignes(feuille)
    entetes = next(l for l in lignes if l[0] == "N°")
    donnees = lignes[lignes.index(entetes) + 1]
    assert entetes[-4:] == ["HT (FCFA)", "TVA (FCFA)", "TTC (FCFA)", "Reste à recouvrer (FCFA)"]
    assert donnees[-4] == 1000000 and isinstance(donnees[-2], (int, float))


def test_export_des_depenses_et_droits(client):
    from apps.billing import services as billing
    from apps.billing.models import ModePaiement

    billing.enregistrer_depense(
        finances(), categorie="PEAGES", date_depense=JOUR, libelle="=SOMME(A1)", montant=Decimal("11800"),
        mode=ModePaiement.ESPECES, montant_tva=Decimal("1800"),
    )
    client.force_login(finances())

    feuille = _ouvrir(client.get(reverse("billing:depenses_xlsx"))).active
    lignes = _lignes(feuille)

    ligne = next(l for l in lignes if l and l[1] == "=SOMME(A1)")
    assert ligne[4] == 11800 and ligne[5] == 1800
    client.force_login(UserFactory(role=Role.CHAUFFEUR))
    assert client.get(reverse("billing:depenses_xlsx")).status_code == 403


def test_export_de_la_tresorerie_signe_les_sorties(client):
    from apps.billing import services as billing
    from apps.billing.models import ModePaiement

    billing.enregistrer_reglement(
        emise(prix="1000000"), finances(), montant=Decimal("500000"), mode=ModePaiement.VIREMENT, date_reglement=JOUR
    )
    billing.enregistrer_depense(
        finances(), categorie="PEAGES", date_depense=JOUR, libelle="Péage", montant=Decimal("100000"),
        mode=ModePaiement.ESPECES,
    )
    client.force_login(finances())

    feuille = _ouvrir(client.get(reverse("finance:xlsx"), {"date_debut": "2020-01-01", "date_fin": "2099-12-31"})).active
    lignes = [l for l in _lignes(feuille) if l and isinstance(l[0], (datetime, date))]

    montants = sorted(l[5] for l in lignes)
    assert montants == [-100000, 500000]
    assert _lignes(feuille)[-1][-1] == 400000  # total


# --- rapports comptables ---


def _ecritures():
    compta.passer_ecriture(
        journal=Journal.VENTES, date_ecriture=date(2026, 3, 1), libelle="Vente",
        lignes=[
            LigneSaisie(compte="411000", sens=SensEcriture.DEBIT, montant=Decimal("1000")),
            LigneSaisie(compte="706100", sens=SensEcriture.CREDIT, montant=Decimal("1000")),
        ],
    )


def test_balance_en_excel_avec_totaux(client):
    _ecritures()
    client.force_login(finances())

    feuille = _ouvrir(client.get(reverse("accounting:balance_xlsx"))).active
    lignes = _lignes(feuille)

    pied = lignes[-1]
    assert pied[1] == "Total" and pied[2] == 1000 and pied[3] == 1000
    assert any(l[0] == "411000" and l[2] == 1000 for l in lignes)


def test_grand_livre_en_excel_exige_un_compte(client):
    _ecritures()
    client.force_login(finances())
    from apps.accounting.models import Compte

    assert client.get(reverse("accounting:grand_livre_xlsx")).status_code == 404
    compte = Compte.objects.get(numero="411000")

    feuille = _ouvrir(client.get(reverse("accounting:grand_livre_xlsx"), {"compte": compte.numero})).active
    lignes = _lignes(feuille)

    assert any(l[0] is not None and l[4] == 1000 and l[6] == 1000 for l in lignes[4:])


def test_bilan_et_compte_de_resultat_en_excel(client):
    _ecritures()
    client.force_login(direction())

    bilan = _ouvrir(client.get(reverse("accounting:bilan_xlsx")))
    resultat = _ouvrir(client.get(reverse("accounting:compte_resultat_xlsx")))

    assert bilan.sheetnames == ["Actif", "Passif"]
    assert _lignes(bilan["Actif"])[-1] == [None, "Total actif", 1000]
    assert _lignes(bilan["Passif"])[-1] == [None, "Total passif", 1000]  # résultat en cours compris
    assert resultat.sheetnames == ["Produits", "Charges", "Résultat"]
    assert _lignes(resultat["Résultat"])[-1][1] == 1000


def test_declaration_tva_en_excel(client):
    client.force_login(finances())

    feuille = _ouvrir(client.get(reverse("accounting:declaration_tva_xlsx"))).active

    assert [l[0] for l in _lignes(feuille)[-3:]][0].startswith("TVA collectée")


@pytest.mark.parametrize("nom", ["balance_xlsx", "bilan_xlsx", "compte_resultat_xlsx", "declaration_tva_xlsx"])
def test_les_exports_comptables_sont_reserves_aux_roles_de_consultation(client, nom):
    client.force_login(UserFactory(role=Role.PARCAUTO))

    assert client.get(reverse(f"accounting:{nom}")).status_code == 403


@pytest.mark.parametrize(
    "ecran, export, role",
    [
        ("billing:factures", "billing:factures_xlsx", Role.FINANCES),
        ("billing:depenses", "billing:depenses_xlsx", Role.FINANCES),
        ("finance:tresorerie", "finance:xlsx", Role.FINANCES),
        ("accounting:balance", "accounting:balance_xlsx", Role.FINANCES),
        ("accounting:bilan", "accounting:bilan_xlsx", Role.FINANCES),
        ("accounting:compte_resultat", "accounting:compte_resultat_xlsx", Role.FINANCES),
        ("accounting:declaration_tva", "accounting:declaration_tva_xlsx", Role.FINANCES),
        ("accounting:grand_livre", "accounting:grand_livre_xlsx", Role.FINANCES),
    ],
)
def test_chaque_ecran_propose_le_bouton_excel(client, ecran, export, role):
    client.force_login(UserFactory(role=role))

    page = client.get(reverse(ecran)).content.decode()

    assert reverse(export) in page and "fa-file-excel" in page
```

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
python -m pytest apps/accounting/tests/test_admin_lecture_seule.py apps/accounting/tests/test_contre_passation_manuelle.py apps/accounting/tests/test_views.py apps/audit/tests/test_validation_suppression.py apps/core/tests/test_xlsx.py -q --no-cov
```

**Résultat attendu :** `129 passed` (pour les 5 fichier(s) de tests présentés dans ce chapitre).

**Le cycle d'une opération diverse, dans le navigateur** (le plan comptable est déjà seedé depuis le
chapitre 15 : `571000` Caisse, `101000` Capital social… y figurent déjà) :

1. **`demo_finances`** : **Plan comptable** : le plan de départ y est. **Nouveau compte** : ajoutez
   `612000` « Locations » (Charge) pour voir l'écran de création — numéro et nature ne se modifient
   plus ensuite.
2. **`demo_finances`** : **Opérations diverses → Nouvelle opération**, date du jour, libellé « Apport en
   caisse ». Le brouillon se crée **sans numéro**. Ajoutez deux lignes : `571000` au débit, `101000` au
   crédit, même montant. Le bandeau passe à **équilibrée**.
3. Essayez de valider avec `demo_finances` : le bouton n'existe pas (rôle **strict**, DIRECTION seule).
4. **`demo_direction`** : ouvrez l'écriture, **Valider**. Le numéro `OD-<année>-0001` est attribué à cet
   instant ; les lignes ne se modifient plus.
5. **Grand livre** sur le compte `571000` : la ligne apparaît, avec son solde cumulé. **Balance** : le
   compte y figure avec son solde. **Bilan** : l'exercice en cours (auto-créé à la première écriture)
   propose le compte en actif.
6. Cliquez la **version imprimable** d'un rapport, puis « Imprimer ou enregistrer en PDF ».

## Ce qu'il faut retenir

- Un rapport comptable est une **agrégation à la demande**, pas un état stocké : il reste vrai même si de
  nouvelles écritures arrivent entre deux consultations.
- La **saisie** et la **validation** d'une même écriture peuvent être deux personnes différentes — le
  contrôle de rôle vit dans le service, la vue ne fait qu'afficher ce qui est possible.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 27 : écrans de la comptabilité (plan comptable, opérations diverses, rapports)"
```

---

[← Chapitre 26](26-ecrans-finances.md) · [Sommaire](README.md) · [Chapitre 28 →](28-tableau-de-bord.md)
