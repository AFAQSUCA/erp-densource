# Chapitre 25 — Écrans : facturation, dépenses et trésorerie

> 16 fichier(s) dans ce chapitre, 2211 lignes de code.

## Ce que vous allez construire

Les **écrans de la facturation, des dépenses et de la trésorerie** : le circuit complet **FINANCES prépare, la
DIRECTION valide**.

| Écran | Adresse | Qui |
|---|---|---|
| Liste des factures (créances, échues, filtres) | `/facturation/` | ADMIN, DIRECTION, FINANCES |
| **Préparer** une facture depuis une mission livrée | `/facturation/nouvelle/` | ADMIN, FINANCES |
| **Fiche** d'une facture : lignes, conditions, **Soumettre**, **Valider et émettre** / **Renvoyer en brouillon**, règlements | `/facturation/<id>/` | selon le statut et le rôle |
| **Version imprimable** (à enregistrer en PDF) | `/facturation/<id>/imprimer/` | ADMIN, DIRECTION, FINANCES |
| Dépenses (liste, saisie) | `/facturation/depenses/` | consultation : ADMIN, DIRECTION, FINANCES ; saisie : ADMIN, FINANCES |
| **Trésorerie** : soldes par compte, journal, mouvements manuels | `/finances/` | idem |

## Prérequis

- Chapitres 1 à 24 terminés.

## Ce que ce chapitre apporte de nouveau

- **Une page à états multiples** : la fiche d'une facture n'affiche pas les mêmes boutons en brouillon, à
  valider, émise ou payée. La vue calcule `saisie`, `validation` et ce qui est possible ; **le service** contrôle
  en plus le rôle **strict** (un ADMIN ne peut pas valider).
- **Beaucoup d'actions en POST** (`_ActionFacture` puis `_Saisie`) : ajouter/supprimer une ligne, modifier les
  conditions, soumettre, abandonner, valider, refuser, ajouter/annuler un règlement.
- **Une page imprimable** : `facture_print.html` est une **page autonome** (elle n'hérite pas de `base.html`), avec sa
  feuille de style d'impression et un bouton `data-imprimer` (traité par `app.js`, sans code en ligne). Les
  mentions de l'émetteur viennent des réglages `ENTREPRISE_NOM`, `ENTREPRISE_ADRESSE`, `ENTREPRISE_NCC`.
- **Deux apps dans un chapitre** : `billing` et `finance` ont chacune leurs formulaires, vues et adresses ; les
  adresses sont montées séparément (`/facturation/` et `/finances/`).
- **Un motif** (`MotifForm`) : un refus, une annulation, un abandon exigent un **motif** saisi.

## Étape 1 — Formulaires

#### `apps/billing/forms.py`

*155 lignes*

```python
from django import forms
from django.utils import timezone

from apps.core.forms import StyleTailwindMixin
from apps.customers import services as customers_services
from apps.customers.models import MotifExoneration
from apps.missions.models import Mission

from . import services
from .models import CategorieDepense, ModePaiement, StatutFacture


def _libelle_mission(m: Mission) -> str:
    return (
        f"{m.numero} · {m.client.raison_sociale} · {m.lieu_chargement} → {m.lieu_livraison}"
        f" · {m.prix_convenu:,.0f} FCFA".replace(",", " ")
    )


class FactureNouvelleForm(StyleTailwindMixin, forms.Form):
    """Choix de la mission livrée à facturer."""

    mission = forms.ModelChoiceField(label="Mission livrée", queryset=None)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["mission"].queryset = services.missions_facturables()
        self.fields["mission"].label_from_instance = _libelle_mission


class LigneForm(StyleTailwindMixin, forms.Form):
    designation = forms.CharField(label="Désignation", max_length=255)
    quantite = forms.DecimalField(label="Quantité", min_value=0, decimal_places=2, max_digits=10, initial=1)
    prix_unitaire_ht = forms.DecimalField(
        label="Prix unitaire HT (FCFA)", min_value=0, decimal_places=2, max_digits=12
    )


class ConditionsForm(StyleTailwindMixin, forms.Form):
    """TVA (3e niveau : la facture) et délai de paiement d'un brouillon."""

    taux_tva = forms.DecimalField(
        label="Taux de TVA (%)", min_value=0, max_value=100, decimal_places=2, max_digits=5
    )
    motif_exoneration = forms.ChoiceField(
        label="Motif d'exonération",
        choices=[("", "—")] + MotifExoneration.choices,
        required=False,
    )
    delai_paiement_jours = forms.IntegerField(label="Délai de paiement (jours)", min_value=1, max_value=365)

    def clean(self):
        donnees = super().clean()
        taux = donnees.get("taux_tva")
        if taux is not None and taux == 0 and not donnees.get("motif_exoneration"):
            self.add_error("motif_exoneration", "Motif obligatoire quand la TVA est à 0 %.")
        return donnees


class MotifForm(StyleTailwindMixin, forms.Form):
    """Motif d'un refus ou d'une annulation."""

    motif = forms.CharField(label="Motif", widget=forms.Textarea(attrs={"rows": 2}))


class ReglementForm(StyleTailwindMixin, forms.Form):
    date_reglement = forms.DateField(
        label="Date du règlement", widget=forms.DateInput(attrs={"type": "date"})
    )
    montant = forms.DecimalField(label="Montant (FCFA)", min_value=0, decimal_places=2, max_digits=14)
    mode = forms.ChoiceField(label="Mode de paiement", choices=ModePaiement.choices)
    reference = forms.CharField(label="Référence", max_length=100, required=False)

    def clean_date_reglement(self):
        jour = self.cleaned_data["date_reglement"]
        if jour > timezone.localdate():
            raise forms.ValidationError("La date du règlement ne peut pas être dans le futur.")
        return jour


class DepenseForm(StyleTailwindMixin, forms.Form):
    categorie = forms.ChoiceField(label="Catégorie", choices=CategorieDepense.choices)
    date_depense = forms.DateField(label="Date", widget=forms.DateInput(attrs={"type": "date"}))
    libelle = forms.CharField(label="Libellé", max_length=200)
    montant = forms.DecimalField(label="Montant (FCFA)", min_value=0, decimal_places=2, max_digits=14)
    mode = forms.ChoiceField(label="Mode de paiement", choices=ModePaiement.choices)
    reference = forms.CharField(label="N° de pièce", max_length=100, required=False)
    mission = forms.ModelChoiceField(
        label="Mission concernée", queryset=None, required=False, empty_label="Aucune",
        help_text="Facultatif : péages et frais propres à une mission.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["mission"].queryset = Mission.objects.order_by("-created_at", "-pk")
        self.fields["mission"].label_from_instance = lambda m: f"{m.numero} · {m.client.raison_sociale}"
        self.fields["mission"].queryset = self.fields["mission"].queryset.select_related("client")

    def clean_date_depense(self):
        jour = self.cleaned_data["date_depense"]
        if jour > timezone.localdate():
            raise forms.ValidationError("La date de la dépense ne peut pas être dans le futur.")
        return jour


class FiltreFacturesForm(StyleTailwindMixin, forms.Form):
    """Filtres de la liste ; un paramètre invalide est ignoré."""

    q = forms.CharField(label="Rechercher", required=False)
    statut = forms.ChoiceField(
        label="Statut", choices=[("", "Tous les statuts")] + StatutFacture.choices, required=False
    )
    client = forms.ModelChoiceField(label="Client", queryset=None, required=False, empty_label="Tous")
    echues = forms.BooleanField(label="Échues seulement", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = customers_services.clients_pour_selection()

    def criteres(self) -> dict:
        self.is_valid()
        donnees = getattr(self, "cleaned_data", {})
        return {
            "recherche": donnees.get("q") or "",
            "statut": donnees.get("statut") or "",
            "client": donnees.get("client"),
            "echues": bool(donnees.get("echues")),
        }


class FiltreDepensesForm(StyleTailwindMixin, forms.Form):
    q = forms.CharField(label="Rechercher", required=False)
    categorie = forms.ChoiceField(
        label="Catégorie", choices=[("", "Toutes")] + CategorieDepense.choices, required=False
    )
    date_debut = forms.DateField(label="Du", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    date_fin = forms.DateField(label="Au", required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def clean(self):
        donnees = super().clean()
        debut, fin = donnees.get("date_debut"), donnees.get("date_fin")
        if debut and fin and debut > fin:
            self.add_error("date_fin", "La date de fin précède la date de début : période ignorée.")
            donnees.pop("date_debut", None)
        return donnees

    def criteres(self) -> dict:
        self.is_valid()
        donnees = getattr(self, "cleaned_data", {})
        return {
            "recherche": donnees.get("q") or "",
            "categorie": donnees.get("categorie") or "",
            "date_debut": donnees.get("date_debut"),
            "date_fin": donnees.get("date_fin"),
        }
```

#### `apps/finance/forms.py`

*57 lignes*

```python
from django import forms
from django.utils import timezone

from apps.billing.models import CompteTresorerie, ModePaiement
from apps.core.forms import StyleTailwindMixin

from .models import SensMouvement


class MouvementForm(StyleTailwindMixin, forms.Form):
    sens = forms.ChoiceField(label="Sens", choices=SensMouvement.choices)
    date_mouvement = forms.DateField(label="Date", widget=forms.DateInput(attrs={"type": "date"}))
    libelle = forms.CharField(label="Libellé", max_length=200)
    montant = forms.DecimalField(label="Montant (FCFA)", min_value=0, decimal_places=2, max_digits=14)
    mode = forms.ChoiceField(label="Mode / compte", choices=ModePaiement.choices)
    reference = forms.CharField(label="Référence", max_length=100, required=False)

    def clean_date_mouvement(self):
        jour = self.cleaned_data["date_mouvement"]
        if jour > timezone.localdate():
            raise forms.ValidationError("La date du mouvement ne peut pas être dans le futur.")
        return jour


class MotifForm(StyleTailwindMixin, forms.Form):
    motif = forms.CharField(label="Motif", widget=forms.Textarea(attrs={"rows": 2}))


class FiltreTresorerieForm(StyleTailwindMixin, forms.Form):
    """Filtres du journal ; un paramètre invalide est ignoré."""

    date_debut = forms.DateField(label="Du", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    date_fin = forms.DateField(label="Au", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    sens = forms.ChoiceField(
        label="Sens", choices=[("", "Entrées et sorties")] + SensMouvement.choices, required=False
    )
    compte = forms.ChoiceField(
        label="Compte", choices=[("", "Tous les comptes")] + CompteTresorerie.choices, required=False
    )

    def clean(self):
        donnees = super().clean()
        debut, fin = donnees.get("date_debut"), donnees.get("date_fin")
        if debut and fin and debut > fin:
            self.add_error("date_fin", "La date de fin précède la date de début : période ignorée.")
            donnees.pop("date_debut", None)
        return donnees

    def criteres(self) -> dict:
        self.is_valid()
        donnees = getattr(self, "cleaned_data", {})
        return {
            "date_debut": donnees.get("date_debut"),
            "date_fin": donnees.get("date_fin"),
            "sens": donnees.get("sens") or "",
            "compte": donnees.get("compte") or "",
        }
```

## Étape 2 — Vues et adresses

#### `apps/billing/views.py`

*341 lignes* — Écrans de facturation : factures, règlements, dépenses.

```python
"""Écrans de facturation : factures, règlements, dépenses.

Aucune règle métier ici : les vues contrôlent le rôle, lisent le formulaire et délèguent à
``services.py`` (conventions.md:19-23).
"""

from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.accounts.mixins import RoleRequiredMixin
from apps.core.formats import nombre
from apps.core.views import PaginationTolerante

from . import permissions, services
from .exceptions import BillingError
from .forms import (
    ConditionsForm,
    DepenseForm,
    FactureNouvelleForm,
    FiltreDepensesForm,
    FiltreFacturesForm,
    LigneForm,
    MotifForm,
    ReglementForm,
)
from .models import Facture, LigneFacture, Reglement, StatutFacture, STATUTS_A_RECOUVRER


def _fcfa(montant) -> str:
    return f"{nombre(montant)} FCFA"


def _erreurs_en_messages(request, form):
    for erreurs in form.errors.values():
        for erreur in erreurs:
            messages.error(request, erreur)


# --- factures ---


class FactureListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "billing/facture_list.html"
    context_object_name = "factures"
    paginate_by = 20

    def get_filtre(self):
        if not hasattr(self, "_filtre"):
            self._filtre = FiltreFacturesForm(self.request.GET)
        return self._filtre

    def get_queryset(self):
        return services.rechercher_factures(**self.get_filtre().criteres())

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        aujourd_hui = timezone.localdate()
        contexte.update(
            filtre=self.get_filtre(),
            filtres_actifs=any(self.get_filtre().criteres().values()),
            creances=services.creances(aujourd_hui),
            aujourd_hui=aujourd_hui,
            peut_saisir=self.request.user.role_effectif in permissions.SAISIE,
            missions_a_facturer=services.missions_facturables().count(),
            lignes=[
                {"facture": f, "echue": services.est_echue(f, aujourd_hui)}
                for f in contexte["page_obj"]
            ],
        )
        return contexte


class FactureCreateView(RoleRequiredMixin, FormView):
    roles = permissions.SAISIE
    form_class = FactureNouvelleForm
    template_name = "billing/facture_form.html"

    def get_initial(self):
        mission = self.request.GET.get("mission", "")
        return {"mission": mission} if mission.isdigit() else {}

    def form_valid(self, form):
        try:
            facture = services.creer_facture(form.cleaned_data["mission"], self.request.user)
        except BillingError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(
            self.request,
            "Brouillon créé. Vérifiez les lignes et la TVA, puis soumettez-le à la direction.",
        )
        return redirect("billing:facture", pk=facture.pk)


class FactureDetailView(RoleRequiredMixin, DetailView):
    roles = permissions.CONSULTATION
    template_name = "billing/facture_detail.html"
    context_object_name = "facture"

    def get_queryset(self):
        return services.factures_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        facture, role = self.object, self.request.user.role_effectif
        saisie = role in permissions.SAISIE
        brouillon = facture.statut == StatutFacture.BROUILLON
        a_valider = facture.statut == StatutFacture.A_VALIDER
        # La validation est réservée au rôle DIRECTION lui-même (un superutilisateur n'y est pas admis).
        validation = self.request.user.role in permissions.VALIDATION
        contexte.update(
            lignes=facture.lignes.all(),
            reglements=facture.reglements.select_related("saisi_par"),
            echue=services.est_echue(facture),
            peut_modifier=saisie and brouillon,
            peut_soumettre=saisie and brouillon,
            peut_valider=validation and a_valider,
            peut_regler=saisie and facture.statut in STATUTS_A_RECOUVRER,
            peut_annuler_reglement=saisie and facture.est_emise,
            form_ligne=LigneForm() if saisie and brouillon else None,
            form_conditions=ConditionsForm(
                initial={
                    "taux_tva": facture.taux_tva,
                    "motif_exoneration": facture.motif_exoneration,
                    "delai_paiement_jours": facture.delai_paiement_jours,
                }
            )
            if saisie and brouillon
            else None,
            form_refus=MotifForm() if validation and a_valider else None,
            form_reglement=ReglementForm(
                initial={"date_reglement": timezone.localdate(), "montant": facture.reste}
            )
            if saisie and facture.statut in STATUTS_A_RECOUVRER
            else None,
            form_annulation=MotifForm(),
        )
        return contexte


class FacturePrintView(RoleRequiredMixin, DetailView):
    """Version imprimable (Ctrl+P → « Enregistrer au format PDF »)."""

    roles = permissions.CONSULTATION
    template_name = "billing/facture_print.html"
    context_object_name = "facture"

    def get_queryset(self):
        return services.factures_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            lignes=self.object.lignes.all(),
            reglements=self.object.reglements.all(),
            entreprise={
                "nom": settings.ENTREPRISE_NOM,
                "adresse": settings.ENTREPRISE_ADRESSE,
                "ncc": settings.ENTREPRISE_NCC,
            },
        )
        return contexte


class _ActionFacture(RoleRequiredMixin, View):
    """Action en POST sur une facture : formulaire → service → message → retour à la fiche."""

    http_method_names = ["post"]
    form_class = None

    def get_facture(self, pk):
        return get_object_or_404(Facture, pk=pk)

    def executer(self, request, facture, donnees):  # pragma: no cover - surchargé
        raise NotImplementedError

    def post(self, request, pk, **kwargs):
        facture = self.get_facture(pk)
        donnees = {}
        if self.form_class is not None:
            form = self.form_class(request.POST)
            if not form.is_valid():
                _erreurs_en_messages(request, form)
                return redirect("billing:facture", pk=facture.pk)
            donnees = form.cleaned_data
        try:
            message = self.executer(request, facture, donnees, **kwargs)
        except BillingError as erreur:
            messages.error(request, str(erreur))
        else:
            if message:
                messages.success(request, message)
        cible, arguments = self.redirection(facture)
        return redirect(cible, **arguments)

    def redirection(self, facture):
        return "billing:facture", {"pk": facture.pk}


class _Saisie(_ActionFacture):
    roles = permissions.SAISIE


class LigneAjouterView(_Saisie):
    form_class = LigneForm

    def executer(self, request, facture, donnees):
        services.ajouter_ligne(
            facture, request.user, designation=donnees["designation"],
            quantite=donnees["quantite"], prix_unitaire_ht=donnees["prix_unitaire_ht"],
        )
        return "Ligne ajoutée."


class LigneSupprimerView(_Saisie):
    def executer(self, request, facture, donnees, ligne_pk):
        ligne = get_object_or_404(LigneFacture, pk=ligne_pk, facture=facture)
        services.supprimer_ligne(ligne, request.user)
        return "Ligne supprimée."

    def post(self, request, pk, ligne_pk):
        return super().post(request, pk, ligne_pk=ligne_pk)


class ConditionsView(_Saisie):
    form_class = ConditionsForm

    def executer(self, request, facture, donnees):
        services.modifier_conditions(facture, request.user, **donnees)
        return "Conditions mises à jour."


class SoumettreView(_Saisie):
    def executer(self, request, facture, donnees):
        services.soumettre(facture, request.user)
        return "Facture envoyée à la direction pour validation."


class AbandonnerView(_Saisie):
    def executer(self, request, facture, donnees):
        services.abandonner_brouillon(facture, request.user)
        messages.success(request, "Brouillon abandonné : la mission peut être facturée à nouveau.")
        return None

    def redirection(self, facture):
        return "billing:factures", {}


class ValiderView(_ActionFacture):
    roles = permissions.VALIDATION

    def executer(self, request, facture, donnees):
        services.valider(facture, request.user)
        facture.refresh_from_db()
        return f"Facture {facture.numero} validée et émise : échéance le {facture.date_echeance:%d/%m/%Y}."


class RefuserView(_ActionFacture):
    roles = permissions.VALIDATION
    form_class = MotifForm

    def executer(self, request, facture, donnees):
        services.refuser(facture, request.user, motif=donnees["motif"])
        return "Facture renvoyée en brouillon avec votre motif."


class ReglementAjouterView(_Saisie):
    form_class = ReglementForm

    def executer(self, request, facture, donnees):
        reglement = services.enregistrer_reglement(facture, request.user, **donnees)
        facture.refresh_from_db()
        reste = services.reste_a_recouvrer(facture)
        suite = "Facture soldée." if reste <= 0 else f"Reste à recouvrer : {_fcfa(reste)}."
        return f"Règlement de {_fcfa(reglement.montant)} enregistré. {suite}"


class ReglementAnnulerView(_Saisie):
    form_class = MotifForm

    def executer(self, request, facture, donnees, reglement_pk):
        reglement = get_object_or_404(Reglement, pk=reglement_pk, facture=facture)
        services.annuler_reglement(reglement, request.user, motif=donnees["motif"])
        return "Règlement annulé : le reste à recouvrer est recalculé."

    def post(self, request, pk, reglement_pk):
        return super().post(request, pk, reglement_pk=reglement_pk)


# --- dépenses ---


class DepenseListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.CONSULTATION
    template_name = "billing/depense_list.html"
    context_object_name = "depenses"
    paginate_by = 20

    def get_filtre(self):
        if not hasattr(self, "_filtre"):
            self._filtre = FiltreDepensesForm(self.request.GET)
        return self._filtre

    def get_queryset(self):
        return services.rechercher_depenses(**self.get_filtre().criteres())

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        aujourd_hui = timezone.localdate()
        debut = aujourd_hui.replace(day=1)
        contexte.update(
            filtre=self.get_filtre(),
            filtres_actifs=any(self.get_filtre().criteres().values()),
            par_categorie=services.depenses_par_categorie(debut, aujourd_hui),
            total_mois=services.total_depenses(debut, aujourd_hui),
            peut_saisir=self.request.user.role_effectif in permissions.SAISIE,
        )
        return contexte


class DepenseCreateView(RoleRequiredMixin, FormView):
    roles = permissions.SAISIE
    form_class = DepenseForm
    template_name = "billing/depense_form.html"

    def get_initial(self):
        return {"date_depense": timezone.localdate()}

    def form_valid(self, form):
        try:
            depense = services.enregistrer_depense(self.request.user, **form.cleaned_data)
        except BillingError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, f"Dépense de {_fcfa(depense.montant)} enregistrée.")
        return redirect("billing:depenses")
```

Lisez `FactureDetailView.get_context_data` : c'est lui qui prépare, pour le gabarit, **ce que la personne a le droit
de faire** (`saisie`, `validation`) — jamais le gabarit.

#### `apps/finance/views.py`

*94 lignes* — Trésorerie : journal des mouvements, soldes par compte, mouvements manuels.

```python
"""Trésorerie : journal des mouvements, soldes par compte, mouvements manuels."""

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.mixins import RoleRequiredMixin
from apps.billing.exceptions import BillingError
from apps.billing.models import CompteTresorerie
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
        contexte.update(
            filtre=filtre,
            filtres_actifs=any(criteres.values()),
            page_obj=page,
            paginator=paginator,
            mouvements=page.object_list,
            soldes=services.soldes_par_compte(),
            comptes=CompteTresorerie.choices,
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
```

#### `apps/billing/urls.py`

*27 lignes*

```python
from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path("", views.FactureListView.as_view(), name="factures"),
    path("nouvelle/", views.FactureCreateView.as_view(), name="nouvelle"),
    path("<int:pk>/", views.FactureDetailView.as_view(), name="facture"),
    path("<int:pk>/imprimer/", views.FacturePrintView.as_view(), name="imprimer"),
    path("<int:pk>/lignes/", views.LigneAjouterView.as_view(), name="ligne_ajouter"),
    path("<int:pk>/lignes/<int:ligne_pk>/supprimer/", views.LigneSupprimerView.as_view(), name="ligne_supprimer"),
    path("<int:pk>/conditions/", views.ConditionsView.as_view(), name="conditions"),
    path("<int:pk>/soumettre/", views.SoumettreView.as_view(), name="soumettre"),
    path("<int:pk>/abandonner/", views.AbandonnerView.as_view(), name="abandonner"),
    path("<int:pk>/valider/", views.ValiderView.as_view(), name="valider"),
    path("<int:pk>/refuser/", views.RefuserView.as_view(), name="refuser"),
    path("<int:pk>/reglements/", views.ReglementAjouterView.as_view(), name="reglement_ajouter"),
    path(
        "<int:pk>/reglements/<int:reglement_pk>/annuler/",
        views.ReglementAnnulerView.as_view(),
        name="reglement_annuler",
    ),
    path("depenses/", views.DepenseListView.as_view(), name="depenses"),
    path("depenses/nouvelle/", views.DepenseCreateView.as_view(), name="depense_nouvelle"),
]
```

#### `apps/finance/urls.py`

*11 lignes*

```python
from django.urls import path

from . import views

app_name = "finance"

urlpatterns = [
    path("", views.TresorerieView.as_view(), name="tresorerie"),
    path("mouvements/", views.MouvementCreateView.as_view(), name="mouvement_creer"),
    path("mouvements/<int:pk>/annuler/", views.MouvementAnnulerView.as_view(), name="mouvement_annuler"),
]
```

#### `config/urls.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/urls.py (avant)
+++ config/urls.py (après)
@@ -24,4 +24,6 @@
     path("carburant/", include("apps.fuel.urls")),
     path("stock/", include("apps.inventory.urls")),
+    path("facturation/", include("apps.billing.urls")),
+    path("finances/", include("apps.finance.urls")),
     path("notifications/", include("apps.notifications.urls")),
     path("admin/", admin.site.urls),
```

## Étape 3 — Gabarits

```bash
mkdir -p apps/billing/templates/billing apps/finance/templates/finance
```

#### `apps/billing/templates/billing/facture_list.html`

*79 lignes*

```django
{% extends "base.html" %}
{% load ui humanize %}
{% block titre %}Facturation{% endblock %}
{% block entete %}Facturation{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-7xl">
  <div class="flex flex-wrap items-start justify-between gap-3">
    <div>
      <h1 class="text-2xl font-bold text-slate-900">Factures</h1>
      <p class="mt-1 text-sm text-slate-600">{{ paginator.count|default:0 }} facture{{ paginator.count|pluralize }}</p>
    </div>
    {% if peut_saisir %}
      <a href="{% url 'billing:nouvelle' %}"
         class="inline-flex items-center gap-2 rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
        <i class="fa-solid fa-plus" aria-hidden="true"></i> Nouvelle facture
        {% if missions_a_facturer %}<span class="rounded-full bg-accent-500 px-2 py-0.5 text-xs text-slate-900">{{ missions_a_facturer }} mission{{ missions_a_facturer|pluralize }} à facturer</span>{% endif %}
      </a>
    {% endif %}
  </div>

  <dl class="mt-5 grid gap-4 sm:grid-cols-3">
    <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Créances à recouvrer</dt><dd class="mt-1 text-2xl font-bold text-slate-900">{{ creances.total|floatformat:0|intcomma }} <span class="text-sm font-medium text-slate-600">FCFA</span></dd><dd class="mt-1 text-xs text-slate-600">{{ creances.nombre }} facture{{ creances.nombre|pluralize }} en attente de paiement</dd></div>
    <div class="rounded-xl border {% if creances.nombre_echues %}border-red-300{% else %}border-slate-200{% endif %} bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Dont échues</dt><dd class="mt-1 text-2xl font-bold {% if creances.nombre_echues %}text-red-800{% else %}text-slate-900{% endif %}">{{ creances.echu|floatformat:0|intcomma }} <span class="text-sm font-medium text-slate-600">FCFA</span></dd><dd class="mt-1 text-xs text-slate-600">{{ creances.nombre_echues }} facture{{ creances.nombre_echues|pluralize }}</dd></div>
    <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Dépenses</dt><dd class="mt-1"><a href="{% url 'billing:depenses' %}" class="text-sm font-medium text-marque-700 underline-offset-2 hover:underline">Voir les dépenses par catégorie</a></dd></div>
  </dl>

  <form method="get" class="mt-5 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
    <div class="min-w-[14rem] flex-1">{% include "components/_champ.html" with champ=filtre.q %}</div>
    <div class="min-w-[10rem]">{% include "components/_champ.html" with champ=filtre.statut %}</div>
    <div class="min-w-[12rem]">{% include "components/_champ.html" with champ=filtre.client %}</div>
    <label class="flex items-center gap-2 pb-2 text-sm font-medium text-slate-800">
      <input type="checkbox" name="echues" value="on" {% if filtre.echues.value %}checked{% endif %} class="h-4 w-4 rounded border-slate-400 text-marque-700 focus:ring-marque-600">
      Échues seulement
    </label>
    <button type="submit" class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Filtrer</button>
    {% if filtres_actifs %}<a href="{% url 'billing:factures' %}" class="px-2 py-2 text-sm font-medium text-slate-700 underline hover:text-slate-900">Réinitialiser</a>{% endif %}
  </form>

  {% if factures %}
    <div class="mt-5 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <caption class="sr-only">Liste des factures</caption>
        <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr>
            <th scope="col" class="px-4 py-3">Facture</th>
            <th scope="col" class="px-4 py-3">Client</th>
            <th scope="col" class="px-4 py-3 text-right">TTC</th>
            <th scope="col" class="px-4 py-3 text-right">Reste</th>
            <th scope="col" class="px-4 py-3">Statut</th>
            <th scope="col" class="hidden px-4 py-3 xl:table-cell">Échéance</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          {% for ligne in lignes %}{% with f=ligne.facture %}
            <tr class="hover:bg-slate-50">
              <td class="whitespace-nowrap px-4 py-3 font-semibold"><a href="{% url 'billing:facture' f.pk %}" class="text-marque-700 underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">{% if f.numero %}{{ f.numero }}{% elif f.statut == "A_VALIDER" %}Sans numéro{% else %}Brouillon{% endif %}</a><span class="block text-xs font-normal text-slate-600">{{ f.mission.numero }}</span></td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ f.client.raison_sociale }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right text-slate-900">{{ f.montant_ttc|floatformat:0|intcomma }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right {% if f.statut == 'EMISE' or f.statut == 'PARTIELLEMENT_PAYEE' %}font-semibold text-slate-900{% else %}text-slate-500{% endif %}">{% if f.est_emise %}{{ f.reste|floatformat:0|intcomma }}{% else %}—{% endif %}</td>
              <td class="whitespace-nowrap px-4 py-3">
                {% if ligne.echue %}{% badge "ECHUE" "Échue" %}{% else %}{% badge f.statut f.get_statut_display %}{% endif %}
              </td>
              <td class="hidden whitespace-nowrap px-4 py-3 text-slate-700 xl:table-cell">{{ f.date_echeance|date:"d/m/Y"|default:"—" }}</td>
            </tr>
          {% endwith %}{% endfor %}
        </tbody>
      </table>
    </div>
    {% include "components/_pagination.html" %}
  {% else %}
    <div class="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
      <span class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-600"><i class="fa-solid fa-file-invoice-dollar" aria-hidden="true"></i></span>
      <p class="mt-3 font-semibold text-slate-900">Aucune facture</p>
      <p class="mt-1 text-sm text-slate-600">{% if filtres_actifs %}Aucun résultat pour ces critères.{% else %}Une facture se prépare depuis une mission livrée.{% endif %}</p>
    </div>
  {% endif %}
</div>
{% endblock %}
```

#### `apps/billing/templates/billing/facture_form.html`

*33 lignes*

```django
{% extends "base.html" %}
{% block titre %}Nouvelle facture{% endblock %}
{% block entete %}Facturation{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-3xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'billing:factures' %}" class="underline-offset-2 hover:underline">Facturation</a>
    <span aria-hidden="true">/</span> Nouvelle facture
  </nav>
  <h1 class="mt-2 text-2xl font-bold text-slate-900">Nouvelle facture</h1>
  <p class="mt-1 text-sm text-slate-600">
    Une facture correspond à une mission livrée. Le brouillon reprend le prix convenu, la TVA et le délai de paiement du client ;
    vous pourrez les ajuster avant de le soumettre à la direction.
  </p>

  <form method="post" novalidate class="mt-6 space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
    {% csrf_token %}
    {% if form.non_field_errors %}
      <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">{% for erreur in form.non_field_errors %}<p>{{ erreur }}</p>{% endfor %}</div>
    {% endif %}
    {% if form.mission.field.queryset %}
      {% include "components/_champ.html" with champ=form.mission %}
    {% else %}
      <p class="rounded-lg border border-dashed border-slate-300 p-4 text-sm text-slate-700">Aucune mission livrée n'attend de facture.</p>
    {% endif %}
    <div class="flex items-center justify-end gap-3 border-t border-slate-100 pt-5">
      <a href="{% url 'billing:factures' %}" class="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">Annuler</a>
      {% if form.mission.field.queryset %}<button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Créer le brouillon</button>{% endif %}
    </div>
  </form>
</div>
{% endblock %}
```

#### `apps/billing/templates/billing/facture_detail.html`

*208 lignes*

```django
{% extends "base.html" %}
{% load ui humanize %}
{% block titre %}{% if facture.numero %}{{ facture.numero }}{% elif facture.statut == "A_VALIDER" %}Facture à valider{% else %}Brouillon de facture{% endif %}{% endblock %}
{% block entete %}Facturation{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-6xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'billing:factures' %}" class="underline-offset-2 hover:underline">Facturation</a>
    <span aria-hidden="true">/</span> {% if facture.numero %}{{ facture.numero }}{% elif facture.statut == "A_VALIDER" %}À valider{% else %}Brouillon{% endif %}
  </nav>

  <div class="mt-2 flex flex-wrap items-center justify-between gap-3">
    <div class="flex flex-wrap items-center gap-3">
      <h1 class="text-2xl font-bold text-slate-900">{% if facture.numero %}Facture {{ facture.numero }}{% elif facture.statut == "A_VALIDER" %}Facture à valider{% else %}Brouillon de facture{% endif %}</h1>
      {% if echue %}{% badge "ECHUE" "Échue" %}{% else %}{% badge facture.statut facture.get_statut_display %}{% endif %}
    </div>
    <a href="{% url 'billing:imprimer' facture.pk %}" target="_blank" rel="noopener"
       class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
      <i class="fa-solid fa-print" aria-hidden="true"></i> Version imprimable
    </a>
  </div>
  <p class="mt-1 text-sm text-slate-600">
    {{ facture.client.raison_sociale }} · mission {{ facture.mission.numero }}
    {% if facture.date_emission %}· émise le {{ facture.date_emission|date:"d/m/Y" }}, échéance le {{ facture.date_echeance|date:"d/m/Y" }}{% endif %}
  </p>

  {% if facture.statut == "BROUILLON" and facture.motif_refus %}
    <div role="alert" class="mt-4 rounded-lg border border-amber-400 bg-amber-50 px-4 py-3 text-sm text-amber-950">
      <p class="font-semibold">Renvoyée par la direction</p>
      <p class="mt-1 whitespace-pre-line">{{ facture.motif_refus }}</p>
    </div>
  {% endif %}
  {% if facture.statut == "A_VALIDER" %}
    <p class="mt-4 rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800">En attente de validation par la direction. La facture n'est plus modifiable.</p>
  {% endif %}

  {% if peut_valider %}
    <section class="mt-4 rounded-xl border border-marque-300 bg-marque-50/40 p-5" aria-labelledby="titre-validation">
      <h2 id="titre-validation" class="text-base font-semibold text-slate-900">Votre validation</h2>
      <p class="mt-1 text-sm text-slate-700">La validation attribue le numéro, fixe la date d'émission et crée la créance. Les montants ne pourront plus être modifiés.</p>
      <div class="mt-4 flex flex-wrap items-start gap-4">
        <form method="post" action="{% url 'billing:valider' facture.pk %}">{% csrf_token %}
          <button type="submit" class="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 focus-visible:ring-offset-2"><i class="fa-solid fa-check mr-1" aria-hidden="true"></i> Valider et émettre</button>
        </form>
        <form method="post" action="{% url 'billing:refuser' facture.pk %}" class="flex-1 min-w-[16rem]">{% csrf_token %}
          <label for="motif-refus" class="block text-sm font-medium text-slate-800">Motif du refus <span class="text-red-700" aria-hidden="true">*</span></label>
          <textarea id="motif-refus" name="motif" rows="2" required class="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30"></textarea>
          <button type="submit" class="mt-2 rounded-lg border border-red-300 bg-white px-4 py-2 text-sm font-semibold text-red-800 hover:bg-red-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-700 focus-visible:ring-offset-2">Renvoyer en brouillon</button>
        </form>
      </div>
    </section>
  {% endif %}

  <div class="mt-6 grid gap-6 xl:grid-cols-3">
    <div class="space-y-6 xl:col-span-2">
      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-lignes">
        <h2 id="titre-lignes" class="text-base font-semibold text-slate-900">Lignes</h2>
        <div class="mt-3 overflow-x-auto">
          <table class="min-w-full divide-y divide-slate-200 text-sm">
            <caption class="sr-only">Lignes de la facture</caption>
            <thead class="text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
              <tr><th scope="col" class="py-2 pr-4">Désignation</th><th scope="col" class="px-4 py-2 text-right">Qté</th><th scope="col" class="px-4 py-2 text-right">Prix unit. HT</th><th scope="col" class="px-4 py-2 text-right">Montant HT</th>{% if peut_modifier %}<th scope="col" class="py-2 pl-4"><span class="sr-only">Actions</span></th>{% endif %}</tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              {% for l in lignes %}
                <tr>
                  <td class="py-3 pr-4 text-slate-900">{{ l.designation }}</td>
                  <td class="whitespace-nowrap px-4 py-3 text-right text-slate-700">{{ l.quantite|floatformat:"-2" }}</td>
                  <td class="whitespace-nowrap px-4 py-3 text-right text-slate-700">{{ l.prix_unitaire_ht|floatformat:0|intcomma }}</td>
                  <td class="whitespace-nowrap px-4 py-3 text-right font-medium text-slate-900">{{ l.montant_ht|floatformat:0|intcomma }}</td>
                  {% if peut_modifier %}
                    <td class="py-3 pl-4 text-right">
                      <form method="post" action="{% url 'billing:ligne_supprimer' facture.pk l.pk %}" data-confirm="Supprimer cette ligne ?">{% csrf_token %}
                        <button type="submit" class="text-sm font-medium text-red-800 underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-red-700"><i class="fa-solid fa-trash-can" aria-hidden="true"></i><span class="sr-only">Supprimer la ligne</span></button>
                      </form>
                    </td>
                  {% endif %}
                </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
        <dl class="mt-4 space-y-1 border-t border-slate-100 pt-3 text-sm sm:ml-auto sm:max-w-xs">
          <div class="flex justify-between"><dt class="text-slate-600">Total HT</dt><dd class="font-medium text-slate-900">{{ facture.montant_ht|floatformat:0|intcomma }} FCFA</dd></div>
          <div class="flex justify-between"><dt class="text-slate-600">TVA {% if facture.taux_tva == 0 %}(exonéré : {{ facture.get_motif_exoneration_display }}){% else %}({{ facture.taux_tva|floatformat:"-2" }} %){% endif %}</dt><dd class="font-medium text-slate-900">{{ facture.montant_tva|floatformat:0|intcomma }} FCFA</dd></div>
          <div class="flex justify-between border-t border-slate-100 pt-1"><dt class="font-semibold text-slate-900">Total TTC</dt><dd class="text-lg font-bold text-slate-900">{{ facture.montant_ttc|floatformat:0|intcomma }} FCFA</dd></div>
        </dl>

        {% if form_ligne %}
          <form method="post" action="{% url 'billing:ligne_ajouter' facture.pk %}" class="mt-5 space-y-3 rounded-lg bg-slate-50 p-4">{% csrf_token %}
            <h3 class="text-sm font-semibold text-slate-900">Ajouter une ligne</h3>
            <div class="grid gap-3 sm:grid-cols-3">
              <div class="sm:col-span-3">{% include "components/_champ.html" with champ=form_ligne.designation %}</div>
              {% include "components/_champ.html" with champ=form_ligne.quantite %}
              {% include "components/_champ.html" with champ=form_ligne.prix_unitaire_ht %}
              <div class="flex items-end"><button type="submit" class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Ajouter</button></div>
            </div>
          </form>
        {% endif %}
      </section>

      {% if facture.est_emise %}
        <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-reglements">
          <h2 id="titre-reglements" class="text-base font-semibold text-slate-900">Règlements</h2>
          {% if reglements %}
            <div class="mt-3 overflow-x-auto">
              <table class="min-w-full divide-y divide-slate-200 text-sm">
                <caption class="sr-only">Règlements reçus</caption>
                <thead class="text-left text-xs font-semibold uppercase tracking-wide text-slate-600"><tr><th scope="col" class="py-2 pr-4">Date</th><th scope="col" class="px-4 py-2">Mode</th><th scope="col" class="px-4 py-2">Référence</th><th scope="col" class="px-4 py-2 text-right">Montant</th>{% if peut_annuler_reglement %}<th scope="col" class="py-2 pl-4"><span class="sr-only">Actions</span></th>{% endif %}</tr></thead>
                <tbody class="divide-y divide-slate-100">
                  {% for r in reglements %}
                    <tr>
                      <td class="whitespace-nowrap py-3 pr-4 text-slate-900">{{ r.date_reglement|date:"d/m/Y" }}</td>
                      <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ r.get_mode_display }}</td>
                      <td class="px-4 py-3 text-slate-700">{{ r.reference|default:"—" }}</td>
                      <td class="whitespace-nowrap px-4 py-3 text-right font-medium text-slate-900">{{ r.montant|floatformat:0|intcomma }}</td>
                      {% if peut_annuler_reglement %}
                        <td class="py-3 pl-4 text-right" x-data="{ ouvert: false }">
                          <button type="button" @click="ouvert = !ouvert" :aria-expanded="ouvert.toString()" class="text-sm font-medium text-red-800 underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-red-700">Annuler</button>
                          <form method="post" action="{% url 'billing:reglement_annuler' facture.pk r.pk %}" x-show="ouvert" x-cloak class="mt-2 space-y-2 text-left">{% csrf_token %}
                            <label for="motif-reglement-{{ r.pk }}" class="block text-xs font-medium text-slate-800">Motif <span class="text-red-700" aria-hidden="true">*</span></label>
                            <input id="motif-reglement-{{ r.pk }}" name="motif" required class="block w-full rounded-lg border border-slate-300 px-2 py-1 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30">
                            <button type="submit" class="rounded-lg border border-red-300 bg-white px-3 py-1 text-xs font-semibold text-red-800 hover:bg-red-50">Confirmer l'annulation</button>
                          </form>
                        </td>
                      {% endif %}
                    </tr>
                  {% endfor %}
                </tbody>
              </table>
            </div>
          {% else %}<p class="mt-3 text-sm text-slate-600">Aucun règlement enregistré.</p>{% endif %}

          {% if form_reglement %}
            <form method="post" action="{% url 'billing:reglement_ajouter' facture.pk %}" class="mt-5 space-y-3 rounded-lg bg-slate-50 p-4">{% csrf_token %}
              <h3 class="text-sm font-semibold text-slate-900">Enregistrer un règlement (acompte ou solde)</h3>
              <div class="grid gap-3 sm:grid-cols-2">
                {% include "components/_champ.html" with champ=form_reglement.date_reglement %}
                {% include "components/_champ.html" with champ=form_reglement.montant %}
                {% include "components/_champ.html" with champ=form_reglement.mode %}
                {% include "components/_champ.html" with champ=form_reglement.reference %}
              </div>
              <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Enregistrer le règlement</button>
            </form>
          {% endif %}
        </section>
      {% endif %}
    </div>

    <div class="space-y-6 xl:col-span-1">
      {% if facture.est_emise %}
        <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-recouvrement">
          <h2 id="titre-recouvrement" class="text-base font-semibold text-slate-900">Recouvrement</h2>
          <dl class="mt-3 space-y-2 text-sm">
            <div class="flex justify-between"><dt class="text-slate-600">Total TTC</dt><dd class="font-medium text-slate-900">{{ facture.montant_ttc|floatformat:0|intcomma }}</dd></div>
            <div class="flex justify-between"><dt class="text-slate-600">Déjà réglé</dt><dd class="font-medium text-slate-900">{{ facture.montant_regle|floatformat:0|intcomma }}</dd></div>
            <div class="flex justify-between border-t border-slate-100 pt-2"><dt class="font-semibold text-slate-900">Reste à recouvrer</dt><dd class="text-lg font-bold {% if echue %}text-red-800{% elif facture.reste == 0 %}text-emerald-800{% else %}text-slate-900{% endif %}">{{ facture.reste|floatformat:0|intcomma }} FCFA</dd></div>
          </dl>
          {% if echue %}<p class="mt-3 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-900">Échéance dépassée depuis le {{ facture.date_echeance|date:"d/m/Y" }}.</p>{% endif %}
        </section>
      {% endif %}

      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-conditions">
        <h2 id="titre-conditions" class="text-base font-semibold text-slate-900">Conditions</h2>
        {% if form_conditions %}
          <form method="post" action="{% url 'billing:conditions' facture.pk %}" class="mt-3 space-y-3" x-data="{ tva: '' }" x-init="tva = $refs.taux.value">{% csrf_token %}
            <div>
              <label for="{{ form_conditions.taux_tva.id_for_label }}" class="block text-sm font-medium text-slate-800">{{ form_conditions.taux_tva.label }}</label>
              <input type="number" name="taux_tva" id="{{ form_conditions.taux_tva.id_for_label }}" step="0.01" min="0" max="100" required x-ref="taux" @input="tva = $event.target.value" value="{{ facture.taux_tva|stringformat:'s' }}"
                     class="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30">
              <p class="mt-1 text-xs text-slate-600">Reprise du client ; modifiable pour cette facture.</p>
            </div>
            <div x-show="parseFloat(tva) === 0" x-cloak>{% include "components/_champ.html" with champ=form_conditions.motif_exoneration %}</div>
            {% include "components/_champ.html" with champ=form_conditions.delai_paiement_jours %}
            <button type="submit" class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Mettre à jour</button>
          </form>
        {% else %}
          <dl class="mt-3 space-y-2 text-sm">
            <div><dt class="text-slate-600">TVA</dt><dd class="font-medium text-slate-900">{% if facture.taux_tva == 0 %}Exonérée : {{ facture.get_motif_exoneration_display }}{% else %}{{ facture.taux_tva|floatformat:"-2" }} %{% endif %}</dd></div>
            <div><dt class="text-slate-600">Délai de paiement</dt><dd class="font-medium text-slate-900">{{ facture.delai_paiement_jours }} jours</dd></div>
          </dl>
        {% endif %}
      </section>

      {% if peut_soumettre %}
        <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-envoi">
          <h2 id="titre-envoi" class="text-base font-semibold text-slate-900">Envoi</h2>
          <p class="mt-1 text-sm text-slate-700">Une fois soumise, la facture ne se modifie plus : la direction la valide ou la renvoie.</p>
          <form method="post" action="{% url 'billing:soumettre' facture.pk %}" class="mt-3">{% csrf_token %}
            <button type="submit" class="w-full rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Soumettre à la direction</button>
          </form>
          <form method="post" action="{% url 'billing:abandonner' facture.pk %}" class="mt-3" data-confirm="Abandonner ce brouillon ? La mission pourra être facturée à nouveau.">{% csrf_token %}
            <button type="submit" class="w-full rounded-lg border border-red-300 bg-white px-4 py-2 text-sm font-semibold text-red-800 hover:bg-red-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-700 focus-visible:ring-offset-2">Abandonner le brouillon</button>
          </form>
        </section>
      {% endif %}

      {% if facture.validee_par %}
        <section class="rounded-xl border border-slate-200 bg-white p-5 text-sm shadow-sm">
          <h2 class="text-base font-semibold text-slate-900">Suivi</h2>
          <p class="mt-2 text-slate-700">Préparée par {{ facture.cree_par|default:"—" }}.<br>Validée par {{ facture.validee_par }} le {{ facture.date_validation|date:"d/m/Y à H:i" }}.</p>
        </section>
      {% endif %}
    </div>
  </div>
</div>
{% endblock %}
```

#### `apps/billing/templates/billing/facture_print.html`

*72 lignes*

```django
{% load humanize static %}<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ facture.numero|default:"Brouillon" }} · {{ facture.client.raison_sociale }}</title>
  <style>
    body { font-family: Arial, Helvetica, sans-serif; color: #111; margin: 2rem auto; max-width: 780px; padding: 0 1rem; font-size: 14px; }
    h1 { font-size: 1.6rem; margin: 0; }
    table { width: 100%; border-collapse: collapse; margin-top: 1.5rem; }
    th, td { padding: .5rem .6rem; border-bottom: 1px solid #ccc; text-align: left; vertical-align: top; }
    th { background: #f3f3f3; font-size: .8rem; text-transform: uppercase; letter-spacing: .03em; }
    .droite { text-align: right; white-space: nowrap; }
    .entete { display: flex; justify-content: space-between; gap: 2rem; }
    .totaux { margin-left: auto; width: 320px; margin-top: 1rem; }
    .totaux div { display: flex; justify-content: space-between; padding: .25rem 0; }
    .total { border-top: 2px solid #111; font-weight: bold; font-size: 1.1rem; }
    .filigrane { color: #b91c1c; border: 2px solid #b91c1c; display: inline-block; padding: .2rem .8rem; font-weight: bold; margin-top: .5rem; }
    .petit { color: #555; font-size: .85rem; }
    .actions { margin-bottom: 1rem; }
    @media print { .actions { display: none; } body { margin: 0; } }
  </style>
</head>
<body>
  <div class="actions"><button type="button" data-imprimer>Imprimer ou enregistrer en PDF</button></div>

  <div class="entete">
    <div>
      <strong>{{ entreprise.nom }}</strong><br>
      {% if entreprise.adresse %}<span class="petit">{{ entreprise.adresse|linebreaksbr }}</span><br>{% endif %}
      {% if entreprise.ncc %}<span class="petit">NCC {{ entreprise.ncc }}</span>{% endif %}
    </div>
    <div style="text-align:right">
      <h1>{% if facture.est_emise %}FACTURE {{ facture.numero }}{% else %}PROJET DE FACTURE{% endif %}</h1>
      {% if facture.date_emission %}<div>Émise le {{ facture.date_emission|date:"d/m/Y" }}</div><div>Échéance : {{ facture.date_echeance|date:"d/m/Y" }}</div>{% endif %}
      {% if not facture.est_emise %}<div class="filigrane">NON VALIDÉE</div>{% endif %}
    </div>
  </div>

  <p style="margin-top:1.5rem">
    <strong>{{ facture.client.raison_sociale }}</strong><br>
    <span class="petit">{{ facture.client.adresse|linebreaksbr }}<br>NCC / NIF {{ facture.client.ncc_nif }}</span>
  </p>
  <p class="petit">Mission {{ facture.mission.numero }}</p>

  <table>
    <thead><tr><th>Désignation</th><th class="droite">Qté</th><th class="droite">Prix unit. HT</th><th class="droite">Montant HT</th></tr></thead>
    <tbody>
      {% for l in lignes %}
        <tr><td>{{ l.designation }}</td><td class="droite">{{ l.quantite|floatformat:"-2" }}</td><td class="droite">{{ l.prix_unitaire_ht|floatformat:0|intcomma }}</td><td class="droite">{{ l.montant_ht|floatformat:0|intcomma }}</td></tr>
      {% endfor %}
    </tbody>
  </table>

  <div class="totaux">
    <div><span>Total HT</span><span>{{ facture.montant_ht|floatformat:0|intcomma }} FCFA</span></div>
    <div><span>TVA {% if facture.taux_tva == 0 %}(exonérée : {{ facture.get_motif_exoneration_display }}){% else %}({{ facture.taux_tva|floatformat:"-2" }} %){% endif %}</span><span>{{ facture.montant_tva|floatformat:0|intcomma }} FCFA</span></div>
    <div class="total"><span>Total TTC</span><span>{{ facture.montant_ttc|floatformat:0|intcomma }} FCFA</span></div>
    {% if facture.est_emise %}
      <div><span>Déjà réglé</span><span>{{ facture.montant_regle|floatformat:0|intcomma }} FCFA</span></div>
      <div><strong>Reste à payer</strong><strong>{{ facture.reste|floatformat:0|intcomma }} FCFA</strong></div>
    {% endif %}
  </div>

  {% if reglements %}
    <p class="petit" style="margin-top:1.5rem">Règlements reçus :
      {% for r in reglements %}{{ r.date_reglement|date:"d/m/Y" }} — {{ r.montant|floatformat:0|intcomma }} FCFA ({{ r.get_mode_display }}){% if not forloop.last %} ; {% endif %}{% endfor %}
    </p>
  {% endif %}
  <script src="{% static 'js/app.js' %}" defer></script>
</body>
</html>
```

#### `apps/billing/templates/billing/depense_list.html`

*67 lignes*

```django
{% extends "base.html" %}
{% load ui humanize %}
{% block titre %}Dépenses{% endblock %}
{% block entete %}Dépenses{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-7xl">
  <div class="flex flex-wrap items-start justify-between gap-3">
    <div>
      <h1 class="text-2xl font-bold text-slate-900">Dépenses</h1>
      <p class="mt-1 text-sm text-slate-600">{{ paginator.count|default:0 }} dépense{{ paginator.count|pluralize }}</p>
    </div>
    {% if peut_saisir %}
      <a href="{% url 'billing:depense_nouvelle' %}" class="inline-flex items-center gap-2 rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2"><i class="fa-solid fa-plus" aria-hidden="true"></i> Nouvelle dépense</a>
    {% endif %}
  </div>

  <section class="mt-5" aria-labelledby="titre-mois">
    <h2 id="titre-mois" class="text-sm font-semibold text-slate-900">Ce mois-ci : {{ total_mois|floatformat:0|intcomma }} FCFA</h2>
    <dl class="mt-2 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {% for c in par_categorie %}
        <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">{{ c.libelle }}</dt><dd class="mt-1 text-xl font-bold text-slate-900">{{ c.total|floatformat:0|intcomma }} <span class="text-sm font-medium text-slate-600">FCFA</span></dd></div>
      {% endfor %}
    </dl>
    <p class="mt-2 text-xs text-slate-600">Le carburant et les ordres de réparation clôturés sont comptés à part dans les charges du mois : ne les saisissez pas ici pour éviter un double compte.</p>
  </section>

  <form method="get" class="mt-5 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
    <div class="min-w-[14rem] flex-1">{% include "components/_champ.html" with champ=filtre.q %}</div>
    <div class="min-w-[10rem]">{% include "components/_champ.html" with champ=filtre.categorie %}</div>
    {% include "components/_champ.html" with champ=filtre.date_debut %}
    {% include "components/_champ.html" with champ=filtre.date_fin %}
    <button type="submit" class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Filtrer</button>
    {% if filtres_actifs %}<a href="{% url 'billing:depenses' %}" class="px-2 py-2 text-sm font-medium text-slate-700 underline hover:text-slate-900">Réinitialiser</a>{% endif %}
  </form>

  {% if depenses %}
    <div class="mt-5 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <caption class="sr-only">Liste des dépenses</caption>
        <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr><th scope="col" class="px-4 py-3">Date</th><th scope="col" class="px-4 py-3">Libellé</th><th scope="col" class="px-4 py-3">Catégorie</th><th scope="col" class="hidden px-4 py-3 xl:table-cell">Mission</th><th scope="col" class="hidden px-4 py-3 xl:table-cell">Mode</th><th scope="col" class="px-4 py-3 text-right">Montant</th></tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          {% for d in depenses %}
            <tr class="hover:bg-slate-50">
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ d.date_depense|date:"d/m/Y" }}</td>
              <td class="px-4 py-3 text-slate-900">{{ d.libelle }}{% if d.reference %}<span class="block text-xs text-slate-600">Pièce {{ d.reference }}</span>{% endif %}</td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ d.get_categorie_display }}</td>
              <td class="hidden whitespace-nowrap px-4 py-3 text-slate-700 xl:table-cell">{{ d.mission.numero|default:"—" }}</td>
              <td class="hidden whitespace-nowrap px-4 py-3 text-slate-700 xl:table-cell">{{ d.get_mode_display }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right font-medium text-slate-900">{{ d.montant|floatformat:0|intcomma }}</td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% include "components/_pagination.html" %}
  {% else %}
    <div class="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
      <span class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-600"><i class="fa-solid fa-receipt" aria-hidden="true"></i></span>
      <p class="mt-3 font-semibold text-slate-900">Aucune dépense</p>
      <p class="mt-1 text-sm text-slate-600">{% if filtres_actifs %}Aucun résultat pour ces critères.{% else %}Péages, entretien, frais administratifs : les dépenses saisies apparaîtront ici.{% endif %}</p>
    </div>
  {% endif %}
</div>
{% endblock %}
```

#### `apps/billing/templates/billing/depense_form.html`

*34 lignes*

```django
{% extends "base.html" %}
{% block titre %}Nouvelle dépense{% endblock %}
{% block entete %}Dépenses{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-3xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'billing:depenses' %}" class="underline-offset-2 hover:underline">Dépenses</a>
    <span aria-hidden="true">/</span> Nouvelle dépense
  </nav>
  <h1 class="mt-2 text-2xl font-bold text-slate-900">Nouvelle dépense</h1>
  <p class="mt-1 text-sm text-slate-600">La dépense alimente la trésorerie (sortie) et les charges du mois. Le carburant et les réparations sont déjà comptés à partir des pleins et des OR.</p>

  <form method="post" novalidate class="mt-6 space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
    {% csrf_token %}
    {% if form.non_field_errors %}
      <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">{% for erreur in form.non_field_errors %}<p>{{ erreur }}</p>{% endfor %}</div>
    {% endif %}
    <div class="grid gap-5 sm:grid-cols-2">
      {% include "components/_champ.html" with champ=form.categorie %}
      {% include "components/_champ.html" with champ=form.date_depense %}
      <div class="sm:col-span-2">{% include "components/_champ.html" with champ=form.libelle %}</div>
      {% include "components/_champ.html" with champ=form.montant %}
      {% include "components/_champ.html" with champ=form.mode %}
      {% include "components/_champ.html" with champ=form.reference %}
      {% include "components/_champ.html" with champ=form.mission %}
    </div>
    <div class="flex items-center justify-end gap-3 border-t border-slate-100 pt-5">
      <a href="{% url 'billing:depenses' %}" class="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">Annuler</a>
      <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Enregistrer la dépense</button>
    </div>
  </form>
</div>
{% endblock %}
```

#### `apps/finance/templates/finance/tresorerie.html`

*102 lignes*

```django
{% extends "base.html" %}
{% load ui humanize %}
{% block titre %}Trésorerie{% endblock %}
{% block entete %}Trésorerie{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-7xl" x-data="{ saisie: false }">
  <div class="flex flex-wrap items-start justify-between gap-3">
    <div>
      <h1 class="text-2xl font-bold text-slate-900">Trésorerie</h1>
      <p class="mt-1 text-sm text-slate-600">Règlements reçus, dépenses payées et autres mouvements. Solde en temps réel.</p>
    </div>
    {% if peut_saisir %}
      <button type="button" @click="saisie = !saisie" :aria-expanded="saisie.toString()"
              class="inline-flex items-center gap-2 rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
        <i class="fa-solid fa-plus" aria-hidden="true"></i> Autre mouvement
      </button>
    {% endif %}
  </div>

  <dl class="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
    <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Solde total</dt><dd class="mt-1 text-2xl font-bold {% if soldes.total < 0 %}text-red-800{% else %}text-slate-900{% endif %}">{{ soldes.total|floatformat:0|intcomma }} <span class="text-sm font-medium text-slate-600">FCFA</span></dd></div>
    {% for code, libelle in comptes %}
      <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <dt class="text-sm text-slate-600">{{ libelle }}</dt>
        {% for c, s in soldes.items %}{% if c == code %}<dd class="mt-1 text-xl font-bold {% if s < 0 %}text-red-800{% else %}text-slate-900{% endif %}">{{ s|floatformat:0|intcomma }} <span class="text-sm font-medium text-slate-600">FCFA</span></dd>{% endif %}{% endfor %}
      </div>
    {% endfor %}
  </dl>
  <p class="mt-3 text-sm text-slate-700">Ce mois-ci : <strong class="text-emerald-800">+{{ mois.entrees|floatformat:0|intcomma }}</strong> d'entrées, <strong class="text-red-800">−{{ mois.sorties|floatformat:0|intcomma }}</strong> de sorties, variation <strong>{{ mois.variation|floatformat:0|intcomma }} FCFA</strong>.</p>

  {% if peut_saisir %}
    <form method="post" action="{% url 'finance:mouvement_creer' %}" x-show="saisie" x-cloak class="mt-5 space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      {% csrf_token %}
      <h2 class="text-base font-semibold text-slate-900">Autre entrée ou sortie</h2>
      <p class="text-xs text-slate-600">Solde d'ouverture, apport, frais bancaires, retrait… Les règlements et les dépenses se saisissent depuis la facturation.</p>
      <div class="grid gap-4 sm:grid-cols-3">
        {% include "components/_champ.html" with champ=form_mouvement.sens %}
        {% include "components/_champ.html" with champ=form_mouvement.date_mouvement %}
        {% include "components/_champ.html" with champ=form_mouvement.montant %}
        <div class="sm:col-span-3">{% include "components/_champ.html" with champ=form_mouvement.libelle %}</div>
        {% include "components/_champ.html" with champ=form_mouvement.mode %}
        {% include "components/_champ.html" with champ=form_mouvement.reference %}
      </div>
      <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Enregistrer</button>
    </form>
  {% endif %}

  <form method="get" class="mt-5 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
    {% include "components/_champ.html" with champ=filtre.date_debut %}
    {% include "components/_champ.html" with champ=filtre.date_fin %}
    <div class="min-w-[10rem]">{% include "components/_champ.html" with champ=filtre.sens %}</div>
    <div class="min-w-[10rem]">{% include "components/_champ.html" with champ=filtre.compte %}</div>
    <button type="submit" class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Filtrer</button>
    {% if filtres_actifs %}<a href="{% url 'finance:tresorerie' %}" class="px-2 py-2 text-sm font-medium text-slate-700 underline hover:text-slate-900">Réinitialiser</a>{% endif %}
  </form>

  {% if mouvements %}
    <div class="mt-5 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <caption class="sr-only">Journal de trésorerie</caption>
        <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr><th scope="col" class="px-4 py-3">Date</th><th scope="col" class="px-4 py-3">Libellé</th><th scope="col" class="px-4 py-3">Compte</th><th scope="col" class="px-4 py-3 text-right">Entrée</th><th scope="col" class="px-4 py-3 text-right">Sortie</th>{% if peut_saisir %}<th scope="col" class="px-4 py-3"><span class="sr-only">Actions</span></th>{% endif %}</tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          {% for m in mouvements %}
            <tr>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ m.date|date:"d/m/Y" }}</td>
              <td class="px-4 py-3 text-slate-900">
                {% if m.origine == "REGLEMENT" %}<a href="{% url 'billing:facture' m.objet.facture_id %}" class="text-marque-700 underline-offset-2 hover:underline">{{ m.libelle }}</a>{% else %}{{ m.libelle }}{% endif %}
                <span class="block text-xs text-slate-600">{{ m.mode_libelle }}{% if m.reference %} · {{ m.reference }}{% endif %}</span>
              </td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ m.compte_libelle }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right font-medium text-emerald-800">{% if m.sens == "ENTREE" %}{{ m.montant|floatformat:0|intcomma }}{% endif %}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right font-medium text-red-800">{% if m.sens == "SORTIE" %}{{ m.montant|floatformat:0|intcomma }}{% endif %}</td>
              {% if peut_saisir %}
                <td class="px-4 py-3 text-right" x-data="{ ouvert: false }">
                  {% if m.origine == "MANUEL" %}
                    <button type="button" @click="ouvert = !ouvert" :aria-expanded="ouvert.toString()" class="text-sm font-medium text-red-800 underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-red-700">Annuler</button>
                    <form method="post" action="{% url 'finance:mouvement_annuler' m.pk %}" x-show="ouvert" x-cloak class="mt-2 space-y-2 text-left">{% csrf_token %}
                      <label for="motif-mvt-{{ m.pk }}" class="block text-xs font-medium text-slate-800">Motif <span class="text-red-700" aria-hidden="true">*</span></label>
                      <input id="motif-mvt-{{ m.pk }}" name="motif" required class="block w-full rounded-lg border border-slate-300 px-2 py-1 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30">
                      <button type="submit" class="rounded-lg border border-red-300 bg-white px-3 py-1 text-xs font-semibold text-red-800 hover:bg-red-50">Confirmer l'annulation</button>
                    </form>
                  {% endif %}
                </td>
              {% endif %}
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% include "components/_pagination.html" %}
  {% else %}
    <div class="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
      <span class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-600"><i class="fa-solid fa-wallet" aria-hidden="true"></i></span>
      <p class="mt-3 font-semibold text-slate-900">Aucun mouvement</p>
      <p class="mt-1 text-sm text-slate-600">{% if filtres_actifs %}Aucun résultat pour ces critères.{% else %}Les règlements reçus et les dépenses payées apparaîtront ici.{% endif %}</p>
    </div>
  {% endif %}
</div>
{% endblock %}
```

## Étape 4 — Tests et compilation des styles

#### `apps/billing/tests/test_views.py`

*567 lignes* — Écrans de facturation : accès, cycle de vie, règlements, dépenses, version imprimable.

```python
"""Écrans de facturation : accès, cycle de vie, règlements, dépenses, version imprimable."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services
from apps.billing.models import Depense, Facture, ModePaiement, Reglement, StatutFacture
from apps.customers.tests.factories import ClientFactory
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory

from .helpers import JOUR, a_valider, brouillon, direction, emise, finances, mission_livree

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    compte = UserFactory(role=role)
    client.force_login(compte)
    return compte


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _texte(reponse):
    return reponse.content.decode().replace("\xa0", " ").replace(" ", " ")


# --- accès ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.FINANCES])
def test_la_facturation_est_accessible_a_admin_direction_et_finances(client, role):
    _connecte(client, role)
    facture = brouillon()

    for url in (
        reverse("billing:factures"),
        reverse("billing:facture", args=[facture.pk]),
        reverse("billing:imprimer", args=[facture.pk]),
        reverse("billing:depenses"),
    ):
        assert client.get(url).status_code == 200, url


@pytest.mark.parametrize(
    "role", [Role.RH, Role.PARCAUTO, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR]
)
def test_la_facturation_est_interdite_aux_autres_roles(client, role):
    _connecte(client, role)
    facture = brouillon()

    for url in (
        reverse("billing:factures"),
        reverse("billing:facture", args=[facture.pk]),
        reverse("billing:imprimer", args=[facture.pk]),
        reverse("billing:nouvelle"),
        reverse("billing:depenses"),
        reverse("billing:depense_nouvelle"),
    ):
        assert client.get(url).status_code == 403, url


def test_la_direction_lit_sans_pouvoir_preparer(client):
    _connecte(client, Role.DIRECTION)

    assert client.get(reverse("billing:nouvelle")).status_code == 403
    assert client.get(reverse("billing:depense_nouvelle")).status_code == 403
    texte = client.get(reverse("billing:factures")).content.decode()
    assert "Nouvelle facture" not in texte


def test_la_facturation_exige_la_connexion(client):
    assert client.get(reverse("billing:factures")).status_code == 302


# --- liste ---


def test_la_liste_affiche_factures_creances_et_echeances(client):
    _connecte(client, Role.FINANCES)
    echue = emise(aujourd_hui=date(2026, 7, 1))  # échéance 31/07 : échue
    en_cours = emise(aujourd_hui=timezone.localdate())
    brouillon()

    reponse = client.get(reverse("billing:factures"))
    texte = _texte(reponse)

    assert len(reponse.context["factures"]) == 3
    assert reponse.context["creances"]["nombre"] == 2 and reponse.context["creances"]["nombre_echues"] == 1
    assert echue.numero in texte and en_cours.numero in texte and "Brouillon" in texte
    assert "Échue" in texte
    assert "2 360 000" in texte  # 2 x 1 180 000 de créances


def test_la_liste_se_filtre_par_texte_statut_client_et_echeance(client):
    _connecte(client, Role.FINANCES)
    cimaf = ClientFactory(raison_sociale="Cimaf Côte d'Ivoire")
    facture_cimaf = emise(client=cimaf, aujourd_hui=date(2026, 7, 1))
    emise(aujourd_hui=timezone.localdate())
    url = reverse("billing:factures")

    def numeros(**params):
        return [f.pk for f in client.get(url, params).context["factures"]]

    assert numeros(q="CIMAF") == [facture_cimaf.pk]
    assert numeros(client=cimaf.pk) == [facture_cimaf.pk]
    assert numeros(echues="on") == [facture_cimaf.pk]
    assert len(numeros(statut="EMISE")) == 2
    assert len(numeros(statut="PAYEE")) == 0
    assert len(numeros(statut="N_IMPORTE_QUOI", client="abc")) == 2  # invalides ignorés


def test_le_bouton_nouvelle_facture_indique_les_missions_a_facturer(client):
    _connecte(client, Role.FINANCES)
    mission_livree()
    mission_livree()

    assert "2 missions à facturer" in client.get(reverse("billing:factures")).content.decode()


def test_la_liste_est_paginee_tolerante_et_a_requetes_constantes(client, django_assert_max_num_queries):
    _connecte(client, Role.FINANCES)
    for _ in range(22):
        brouillon()

    with django_assert_max_num_queries(12):
        premiere = client.get(reverse("billing:factures"))
    inconnue = client.get(reverse("billing:factures"), {"page": 99})

    assert len(premiere.context["factures"]) == 20
    assert inconnue.status_code == 200 and inconnue.context["page_obj"].number == 2


def test_liste_vide(client):
    _connecte(client, Role.FINANCES)

    assert "Une facture se prépare depuis une mission livrée" in client.get(reverse("billing:factures")).content.decode()


# --- création ---


def test_finances_cree_un_brouillon_depuis_une_mission_livree(client):
    _connecte(client, Role.FINANCES)
    mission = mission_livree(prix="800000")

    reponse = client.post(reverse("billing:nouvelle"), {"mission": mission.pk}, follow=True)

    facture = Facture.objects.get(mission=mission)
    assert facture.statut == StatutFacture.BROUILLON and facture.montant_ttc == Decimal("944000")
    assert reponse.redirect_chain[-1][0] == reverse("billing:facture", args=[facture.pk])
    assert any("Brouillon créé" in m for m in _messages(reponse))


def test_le_formulaire_ne_propose_que_les_missions_facturables(client):
    _connecte(client, Role.FINANCES)
    livree = mission_livree()
    planifiee = MissionFactory(statut=StatutMission.PLANIFIEE)

    propositions = set(client.get(reverse("billing:nouvelle")).context["form"].fields["mission"].queryset)

    assert livree in propositions and planifiee not in propositions


def test_une_mission_non_facturable_postee_a_la_main_est_refusee(client):
    _connecte(client, Role.FINANCES)
    planifiee = MissionFactory(statut=StatutMission.PLANIFIEE)

    reponse = client.post(reverse("billing:nouvelle"), {"mission": planifiee.pk})

    assert reponse.status_code == 200 and not Facture.objects.exists()


def test_la_mission_est_preselectionnee_depuis_l_adresse(client):
    _connecte(client, Role.FINANCES)
    mission = mission_livree()

    reponse = client.get(reverse("billing:nouvelle"), {"mission": mission.pk})

    assert reponse.context["form"].initial["mission"] == str(mission.pk)


def test_le_formulaire_de_creation_exige_le_csrf():
    http = Client(enforce_csrf_checks=True)
    http.force_login(UserFactory(role=Role.FINANCES))

    assert http.post(reverse("billing:nouvelle"), {"mission": mission_livree().pk}).status_code == 403


# --- fiche et actions ---


def test_la_fiche_d_un_brouillon_propose_les_actions_de_finances(client):
    _connecte(client, Role.FINANCES)
    facture = brouillon()

    texte = client.get(reverse("billing:facture", args=[facture.pk])).content.decode()

    for libelle in ("Ajouter une ligne", "Mettre à jour", "Soumettre à la direction", "Abandonner le brouillon"):
        assert libelle in texte
    assert "Valider et émettre" not in texte


def test_la_direction_valide_ce_qui_est_a_valider_et_pas_finances_ni_admin(client):
    facture = a_valider()
    url = reverse("billing:facture", args=[facture.pk])

    _connecte(client, Role.DIRECTION)
    assert "Valider et émettre" in client.get(url).content.decode()
    for role in (Role.FINANCES, Role.ADMIN):
        _connecte(client, role)
        assert "Valider et émettre" not in client.get(url).content.decode()
    client.force_login(UserFactory(role="", is_superuser=True, is_staff=True))
    assert "Valider et émettre" not in client.get(url).content.decode()


def test_cycle_complet_soumettre_valider_regler(client):
    finance, chef = UserFactory(role=Role.FINANCES), UserFactory(role=Role.DIRECTION)
    facture = brouillon(prix="1000000")

    client.force_login(finance)
    reponse = client.post(reverse("billing:soumettre", args=[facture.pk]), follow=True)
    assert any("envoyée à la direction" in m for m in _messages(reponse))

    client.force_login(chef)
    reponse = client.post(reverse("billing:valider", args=[facture.pk]), follow=True)
    facture.refresh_from_db()
    assert facture.statut == StatutFacture.EMISE and facture.numero.startswith("FACT-")
    assert any(f"Facture {facture.numero} validée" in m for m in _messages(reponse))

    client.force_login(finance)
    reponse = client.post(
        reverse("billing:reglement_ajouter", args=[facture.pk]),
        {"date_reglement": timezone.localdate().isoformat(), "montant": "500000", "mode": "WAVE", "reference": "TX-1"},
        follow=True,
    )
    assert any("Reste à recouvrer : 680 000 FCFA" in m.replace("\xa0", " ").replace(" ", " ") for m in _messages(reponse))
    reponse = client.post(
        reverse("billing:reglement_ajouter", args=[facture.pk]),
        {"date_reglement": timezone.localdate().isoformat(), "montant": "680000", "mode": "VIREMENT"},
        follow=True,
    )
    facture.refresh_from_db()
    assert facture.statut == StatutFacture.PAYEE
    assert any("Facture soldée" in m for m in _messages(reponse))


def test_finances_ne_peut_pas_valider_meme_en_postant_directement(client):
    facture = a_valider()
    _connecte(client, Role.FINANCES)

    assert client.post(reverse("billing:valider", args=[facture.pk])).status_code == 403
    assert client.post(reverse("billing:refuser", args=[facture.pk]), {"motif": "x"}).status_code == 403
    facture.refresh_from_db()
    assert facture.statut == StatutFacture.A_VALIDER


def test_la_direction_ne_peut_pas_soumettre_ni_regler(client):
    facture = emise()
    _connecte(client, Role.DIRECTION)

    assert client.post(reverse("billing:soumettre", args=[facture.pk])).status_code == 403
    assert client.post(reverse("billing:reglement_ajouter", args=[facture.pk]), {}).status_code == 403


def test_le_refus_exige_un_motif_puis_renvoie_en_brouillon(client):
    facture = a_valider()
    _connecte(client, Role.DIRECTION)
    url = reverse("billing:refuser", args=[facture.pk])

    reponse = client.post(url, {"motif": " "}, follow=True)
    facture.refresh_from_db()
    assert facture.statut == StatutFacture.A_VALIDER and _messages(reponse)

    reponse = client.post(url, {"motif": "Prix à revoir"}, follow=True)
    facture.refresh_from_db()
    assert facture.statut == StatutFacture.BROUILLON
    _connecte(client, Role.FINANCES)
    assert "Prix à revoir" in client.get(reverse("billing:facture", args=[facture.pk])).content.decode()


def test_abandonner_un_brouillon_retourne_a_la_liste_et_libere_la_mission(client):
    _connecte(client, Role.FINANCES)
    facture = brouillon()

    reponse = client.post(reverse("billing:abandonner", args=[facture.pk]), follow=True)

    assert reponse.redirect_chain[-1][0] == reverse("billing:factures")
    assert not Facture.objects.filter(pk=facture.pk).exists()
    assert any("Brouillon abandonné" in m for m in _messages(reponse))


def test_ajouter_puis_supprimer_une_ligne(client):
    _connecte(client, Role.FINANCES)
    facture = brouillon(prix="1000000")

    client.post(
        reverse("billing:ligne_ajouter", args=[facture.pk]),
        {"designation": "Péages refacturés", "quantite": "1", "prix_unitaire_ht": "25000"},
    )
    facture.refresh_from_db()
    assert facture.montant_ht == Decimal("1025000")
    ligne = facture.lignes.get(designation="Péages refacturés")

    reponse = client.post(
        reverse("billing:ligne_supprimer", args=[facture.pk, ligne.pk]), follow=True
    )

    facture.refresh_from_db()
    assert facture.montant_ht == Decimal("1000000")
    assert any("Ligne supprimée" in m for m in _messages(reponse))


def test_une_ligne_invalide_donne_un_message_sans_rien_ajouter(client):
    _connecte(client, Role.FINANCES)
    facture = brouillon()

    reponse = client.post(
        reverse("billing:ligne_ajouter", args=[facture.pk]),
        {"designation": "", "quantite": "0", "prix_unitaire_ht": "-1"}, follow=True,
    )

    assert facture.lignes.count() == 1 and _messages(reponse)


def test_supprimer_la_ligne_d_une_autre_facture_est_refuse(client):
    _connecte(client, Role.FINANCES)
    facture, autre = brouillon(), brouillon()

    reponse = client.post(
        reverse("billing:ligne_supprimer", args=[facture.pk, autre.lignes.first().pk])
    )

    assert reponse.status_code == 404


def test_modifier_les_conditions_de_tva_et_de_delai(client):
    _connecte(client, Role.FINANCES)
    facture = brouillon(prix="1000000")
    url = reverse("billing:conditions", args=[facture.pk])

    client.post(url, {"taux_tva": "0", "motif_exoneration": "", "delai_paiement_jours": "30"}, follow=True)
    facture.refresh_from_db()
    assert facture.taux_tva == Decimal("18")  # refusé : motif obligatoire

    client.post(url, {"taux_tva": "0", "motif_exoneration": "ONG", "delai_paiement_jours": "60"})
    facture.refresh_from_db()
    assert (facture.taux_tva, facture.motif_exoneration, facture.delai_paiement_jours) == (0, "ONG", 60)
    assert facture.montant_ttc == facture.montant_ht


def test_les_reglements_incoherents_donnent_un_message_d_erreur(client):
    _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000")
    url = reverse("billing:reglement_ajouter", args=[facture.pk])
    aujourd_hui = timezone.localdate().isoformat()

    trop = client.post(url, {"date_reglement": aujourd_hui, "montant": "9999999", "mode": "VIREMENT"}, follow=True)
    futur = client.post(url, {"date_reglement": "2999-01-01", "montant": "1000", "mode": "VIREMENT"}, follow=True)
    mode = client.post(url, {"date_reglement": aujourd_hui, "montant": "1000", "mode": "TROC"}, follow=True)

    assert any("dépasse le reste à recouvrer" in m for m in _messages(trop))
    assert any("futur" in m for m in _messages(futur))
    assert _messages(mode)
    assert Reglement.objects.count() == 0


def test_annuler_un_reglement_avec_motif(client):
    _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000")
    reglement = services.enregistrer_reglement(
        facture, finances(), montant=Decimal("1180000"), mode=ModePaiement.CHEQUE, date_reglement=JOUR
    )
    url = reverse("billing:reglement_annuler", args=[facture.pk, reglement.pk])

    client.post(url, {"motif": " "}, follow=True)
    facture.refresh_from_db()
    assert facture.statut == StatutFacture.PAYEE  # motif vide : rien ne change

    reponse = client.post(url, {"motif": "Chèque impayé"}, follow=True)
    facture.refresh_from_db()
    assert facture.statut == StatutFacture.EMISE
    assert any("Règlement annulé" in m for m in _messages(reponse))


def test_les_actions_n_acceptent_que_post_et_exigent_le_csrf():
    facture = a_valider()
    http = Client(enforce_csrf_checks=True)
    for nom, role in (
        ("valider", Role.DIRECTION), ("refuser", Role.DIRECTION),
        ("soumettre", Role.FINANCES), ("abandonner", Role.FINANCES),
    ):
        http.force_login(UserFactory(role=role))
        url = reverse(f"billing:{nom}", args=[facture.pk])
        assert http.get(url).status_code == 405, nom
        assert http.post(url, {"motif": "x"}).status_code == 403, nom
    facture.refresh_from_db()
    assert facture.statut == StatutFacture.A_VALIDER


def test_une_facture_inexistante_donne_404(client):
    _connecte(client, Role.FINANCES)

    assert client.get(reverse("billing:facture", args=[999])).status_code == 404
    assert client.post(reverse("billing:soumettre", args=[999])).status_code == 404


def test_la_fiche_affiche_le_recouvrement_et_l_alerte_d_echeance(client):
    _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000", aujourd_hui=date(2026, 7, 1))
    services.enregistrer_reglement(
        facture, finances(), montant=Decimal("180000"), mode=ModePaiement.ESPECES, date_reglement=date(2026, 7, 5)
    )

    reponse = client.get(reverse("billing:facture", args=[facture.pk]))
    texte = _texte(reponse)

    assert reponse.context["echue"] is True
    assert "Reste à recouvrer" in texte and "1 000 000 FCFA" in texte
    assert "Échéance dépassée depuis le 31/07/2026" in texte
    assert "Espèces" in texte


def test_les_textes_saisis_sont_echappes_dans_les_pages_de_facturation(client):
    _connecte(client, Role.FINANCES)
    mission = mission_livree(client=ClientFactory(raison_sociale="<script>alert(1)</script>"))
    facture = services.creer_facture(mission, finances())
    services.ajouter_ligne(
        facture, finances(), designation="<img src=x onerror=alert(2)>", quantite=Decimal(1), prix_unitaire_ht=Decimal(10)
    )

    for url in (reverse("billing:facture", args=[facture.pk]), reverse("billing:factures"),
                reverse("billing:imprimer", args=[facture.pk])):
        texte = client.get(url).content.decode()
        assert "<script>alert(1)</script>" not in texte and "<img src=x" not in texte, url


# --- version imprimable ---


def test_l_impression_d_un_brouillon_est_marquee_non_validee(client):
    _connecte(client, Role.FINANCES)
    facture = brouillon()

    texte = client.get(reverse("billing:imprimer", args=[facture.pk])).content.decode()

    assert "PROJET DE FACTURE" in texte and "NON VALIDÉE" in texte


def test_l_impression_d_une_facture_emise_montre_numero_totaux_et_emetteur(client, settings):
    settings.ENTREPRISE_NOM = "DEN Source Group"
    settings.ENTREPRISE_ADRESSE = "Abidjan, Zone 4"
    settings.ENTREPRISE_NCC = "1234567 A"
    _connecte(client, Role.DIRECTION)
    facture = emise(prix="1000000")
    services.enregistrer_reglement(
        facture, finances(), montant=Decimal("500000"), mode=ModePaiement.VIREMENT, date_reglement=JOUR
    )

    texte = _texte(client.get(reverse("billing:imprimer", args=[facture.pk])))

    assert f"FACTURE {facture.numero}" in texte and "NON VALIDÉE" not in texte
    assert "Total HT" in texte and "1 000 000 FCFA" in texte and "1 180 000 FCFA" in texte
    assert "Reste à payer" in texte and "680 000 FCFA" in texte
    assert "DEN Source Group" in texte and "Abidjan, Zone 4" in texte and "NCC 1234567 A" in texte


# --- dépenses ---


def _donnees_depense(**surcharges):
    donnees = {
        "categorie": "PEAGES", "date_depense": timezone.localdate().isoformat(),
        "libelle": "Péage Yamoussoukro", "montant": "5000", "mode": "ESPECES",
        "reference": "TK-12", "mission": "",
    }
    donnees.update(surcharges)
    return donnees


def test_finances_enregistre_une_depense(client):
    _connecte(client, Role.FINANCES)
    mission = mission_livree()

    reponse = client.post(
        reverse("billing:depense_nouvelle"), _donnees_depense(mission=mission.pk), follow=True
    )

    depense = Depense.objects.get()
    assert depense.mission == mission and depense.montant == Decimal("5000")
    assert reponse.redirect_chain[-1][0] == reverse("billing:depenses")
    assert any("5 000 FCFA" in m.replace("\xa0", " ").replace(" ", " ") for m in _messages(reponse))


@pytest.mark.parametrize(
    "surcharges",
    [{"montant": "0"}, {"libelle": ""}, {"date_depense": "2999-01-01"}, {"categorie": "CASINO"}, {"mode": "TROC"}],
)
def test_depense_invalide_reste_sur_le_formulaire(client, surcharges):
    _connecte(client, Role.FINANCES)

    reponse = client.post(reverse("billing:depense_nouvelle"), _donnees_depense(**surcharges))

    assert reponse.status_code == 200 and not Depense.objects.exists()


def test_la_liste_des_depenses_totalise_le_mois_par_categorie_et_filtre(client):
    compte = _connecte(client, Role.FINANCES)
    aujourd_hui = timezone.localdate()
    services.enregistrer_depense(
        compte, categorie="PEAGES", date_depense=aujourd_hui, libelle="Péage Bouaké",
        montant=Decimal("5000"), mode=ModePaiement.ESPECES,
    )
    services.enregistrer_depense(
        compte, categorie="ENTRETIEN", date_depense=aujourd_hui, libelle="Graissage",
        montant=Decimal("20000"), mode=ModePaiement.ESPECES,
    )

    reponse = client.get(reverse("billing:depenses"))
    par_categorie = {c["code"]: c["total"] for c in reponse.context["par_categorie"]}

    assert par_categorie["PEAGES"] == 5000 and par_categorie["ENTRETIEN"] == 20000
    assert reponse.context["total_mois"] == Decimal("25000")
    assert [d.libelle for d in client.get(reverse("billing:depenses"), {"categorie": "PEAGES"}).context["depenses"]] == ["Péage Bouaké"]
    assert len(client.get(reverse("billing:depenses"), {"q": "GRAISSAGE"}).context["depenses"]) == 1


def test_une_periode_de_depenses_a_l_envers_est_signalee_et_ignoree(client):
    compte = _connecte(client, Role.FINANCES)
    services.enregistrer_depense(
        compte, categorie="PEAGES", date_depense=timezone.localdate(), libelle="Péage",
        montant=Decimal("5000"), mode=ModePaiement.ESPECES,
    )

    reponse = client.get(reverse("billing:depenses"), {"date_debut": "2026-12-31", "date_fin": "2026-01-01"})

    assert "période ignorée" in reponse.content.decode()
    assert len(reponse.context["depenses"]) == 1


def test_la_creation_de_depense_exige_le_csrf():
    http = Client(enforce_csrf_checks=True)
    http.force_login(UserFactory(role=Role.FINANCES))

    assert http.post(reverse("billing:depense_nouvelle"), _donnees_depense()).status_code == 403
    assert not Depense.objects.exists()


def test_une_facture_a_valider_n_est_pas_presentee_comme_un_brouillon(client):
    _connecte(client, Role.DIRECTION)
    facture = a_valider()

    liste = client.get(reverse("billing:factures")).content.decode()
    fiche = client.get(reverse("billing:facture", args=[facture.pk])).content.decode()

    assert "Sans numéro" in liste
    assert "Facture à valider" in fiche and "Brouillon de facture" not in fiche
```

#### `apps/finance/tests/test_views.py`

*230 lignes* — Écran de trésorerie : accès, journal, soldes, mouvements manuels.

```python
"""Écran de trésorerie : accès, journal, soldes, mouvements manuels."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services as billing
from apps.billing.models import ModePaiement
from apps.billing.tests.helpers import emise, finances
from apps.finance import services
from apps.finance.models import MouvementManuel, SensMouvement

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    compte = UserFactory(role=role)
    client.force_login(compte)
    return compte


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _donnees(**surcharges):
    donnees = {
        "sens": "ENTREE", "date_mouvement": timezone.localdate().isoformat(),
        "libelle": "Solde d'ouverture", "montant": "250000", "mode": "VIREMENT", "reference": "",
    }
    donnees.update(surcharges)
    return donnees


def _texte(reponse):
    return reponse.content.decode().replace("\xa0", " ").replace(" ", " ")


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.FINANCES])
def test_la_tresorerie_est_accessible_a_admin_direction_et_finances(client, role):
    _connecte(client, role)

    assert client.get(reverse("finance:tresorerie")).status_code == 200


@pytest.mark.parametrize("role", [Role.RH, Role.PARCAUTO, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_la_tresorerie_est_interdite_aux_autres_roles(client, role):
    _connecte(client, role)

    assert client.get(reverse("finance:tresorerie")).status_code == 403


def test_la_tresorerie_exige_la_connexion(client):
    assert client.get(reverse("finance:tresorerie")).status_code == 302


def test_la_direction_consulte_sans_saisir(client):
    _connecte(client, Role.DIRECTION)

    texte = client.get(reverse("finance:tresorerie")).content.decode()

    assert "Autre mouvement" not in texte
    assert client.post(reverse("finance:mouvement_creer"), _donnees()).status_code == 403


def test_soldes_et_journal_s_affichent(client):
    _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000")
    billing.enregistrer_reglement(
        facture, finances(), montant=Decimal("600000"), mode=ModePaiement.WAVE,
        date_reglement=timezone.localdate(),
    )
    billing.enregistrer_depense(
        finances(), categorie="PEAGES", date_depense=timezone.localdate(), libelle="Péage Bouaké",
        montant=Decimal("25000"), mode=ModePaiement.ESPECES,
    )

    reponse = client.get(reverse("finance:tresorerie"))
    texte = _texte(reponse)

    assert reponse.context["soldes"]["total"] == Decimal("575000")
    assert "575 000" in texte and "Mobile Money" in texte
    assert f"Règlement {facture.numero}" in texte and "Dépense : Péage Bouaké" in texte
    assert reverse("billing:facture", args=[facture.pk]) in texte  # lien du règlement vers sa facture
    assert reponse.context["mois"]["variation"] == Decimal("575000")


def test_le_journal_se_filtre(client):
    _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000")
    aujourd_hui = timezone.localdate()
    billing.enregistrer_reglement(
        facture, finances(), montant=Decimal("100000"), mode=ModePaiement.WAVE, date_reglement=aujourd_hui
    )
    billing.enregistrer_depense(
        finances(), categorie="PEAGES", date_depense=aujourd_hui, libelle="Péage",
        montant=Decimal("5000"), mode=ModePaiement.ESPECES,
    )
    url = reverse("finance:tresorerie")

    assert [m["origine"] for m in client.get(url, {"sens": "ENTREE"}).context["mouvements"]] == ["REGLEMENT"]
    assert [m["origine"] for m in client.get(url, {"compte": "CAISSE"}).context["mouvements"]] == ["DEPENSE"]
    assert len(client.get(url, {"date_debut": aujourd_hui.isoformat()}).context["mouvements"]) == 2
    assert len(client.get(url, {"sens": "N_IMPORTE_QUOI", "compte": "???", "date_debut": "abc"}).context["mouvements"]) == 2


def test_une_periode_a_l_envers_est_signalee_et_ignoree(client):
    _connecte(client, Role.FINANCES)
    services.enregistrer_mouvement(
        finances(), sens="ENTREE", date_mouvement=timezone.localdate(), libelle="Apport",
        montant=Decimal("1000"), mode=ModePaiement.VIREMENT,
    )

    reponse = client.get(reverse("finance:tresorerie"), {"date_debut": "2026-12-31", "date_fin": "2026-01-01"})

    assert "période ignorée" in reponse.content.decode()
    assert len(reponse.context["mouvements"]) == 1


def test_le_journal_est_pagine_et_tolerant(client):
    compte = _connecte(client, Role.FINANCES)
    for i in range(30):
        services.enregistrer_mouvement(
            compte, sens="ENTREE", date_mouvement=timezone.localdate() - timedelta(days=i % 5),
            libelle=f"Apport {i}", montant=Decimal("1000"), mode=ModePaiement.VIREMENT,
        )

    premiere = client.get(reverse("finance:tresorerie"))
    trop_loin = client.get(reverse("finance:tresorerie"), {"page": 99})
    illisible = client.get(reverse("finance:tresorerie"), {"page": "abc"})

    assert len(premiere.context["mouvements"]) == 25
    assert trop_loin.context["page_obj"].number == 2 and illisible.context["page_obj"].number == 1


def test_journal_vide(client):
    _connecte(client, Role.FINANCES)

    assert "Aucun mouvement" in client.get(reverse("finance:tresorerie")).content.decode()


def test_finances_enregistre_un_mouvement_manuel(client):
    _connecte(client, Role.FINANCES)

    reponse = client.post(reverse("finance:mouvement_creer"), _donnees(), follow=True)

    mouvement = MouvementManuel.objects.get()
    assert (mouvement.sens, mouvement.montant) == (SensMouvement.ENTREE, Decimal("250000"))
    assert any("250 000 FCFA" in m.replace("\xa0", " ").replace(" ", " ") for m in _messages(reponse))
    assert services.soldes_par_compte()["BANQUE"] == Decimal("250000")


@pytest.mark.parametrize(
    "surcharges",
    [{"montant": "0"}, {"libelle": ""}, {"date_mouvement": "2999-01-01"}, {"sens": "AUTRE"}, {"mode": "TROC"}],
)
def test_mouvement_invalide_donne_un_message_sans_rien_enregistrer(client, surcharges):
    _connecte(client, Role.FINANCES)

    reponse = client.post(reverse("finance:mouvement_creer"), _donnees(**surcharges), follow=True)

    assert not MouvementManuel.objects.exists() and _messages(reponse)


def test_annuler_un_mouvement_exige_un_motif(client):
    compte = _connecte(client, Role.FINANCES)
    mouvement = services.enregistrer_mouvement(
        compte, sens="SORTIE", date_mouvement=timezone.localdate(), libelle="Retrait",
        montant=Decimal("10000"), mode=ModePaiement.ESPECES,
    )
    url = reverse("finance:mouvement_annuler", args=[mouvement.pk])

    client.post(url, {"motif": " "}, follow=True)
    assert MouvementManuel.objects.filter(pk=mouvement.pk).exists()

    reponse = client.post(url, {"motif": "Erreur de saisie"}, follow=True)
    assert not MouvementManuel.objects.filter(pk=mouvement.pk).exists()
    assert any("Mouvement annulé" in m for m in _messages(reponse))
    assert services.soldes_par_compte()["total"] == 0


def test_annuler_un_mouvement_inexistant_donne_404(client):
    _connecte(client, Role.FINANCES)

    assert client.post(reverse("finance:mouvement_annuler", args=[999]), {"motif": "x"}).status_code == 404


def test_les_actions_de_tresorerie_exigent_post_et_csrf():
    http = Client(enforce_csrf_checks=True)
    http.force_login(UserFactory(role=Role.FINANCES))
    mouvement = services.enregistrer_mouvement(
        UserFactory(role=Role.FINANCES), sens="ENTREE", date_mouvement=timezone.localdate(),
        libelle="Apport", montant=Decimal("1000"), mode=ModePaiement.VIREMENT,
    )

    assert http.get(reverse("finance:mouvement_creer")).status_code == 405
    assert http.post(reverse("finance:mouvement_creer"), _donnees()).status_code == 403
    assert http.get(reverse("finance:mouvement_annuler", args=[mouvement.pk])).status_code == 405
    assert http.post(reverse("finance:mouvement_annuler", args=[mouvement.pk]), {"motif": "x"}).status_code == 403
    assert MouvementManuel.objects.count() == 1


def test_les_libelles_sont_echappes(client):
    compte = _connecte(client, Role.FINANCES)
    services.enregistrer_mouvement(
        compte, sens="ENTREE", date_mouvement=timezone.localdate(), libelle="<script>alert(1)</script>",
        montant=Decimal("1000"), mode=ModePaiement.VIREMENT,
    )

    texte = client.get(reverse("finance:tresorerie")).content.decode()

    assert "<script>alert(1)</script>" not in texte and "&lt;script&gt;" in texte


def test_le_compte_mobile_money_s_affiche_avec_son_vrai_nom(client):
    compte = _connecte(client, Role.FINANCES)
    services.enregistrer_mouvement(
        compte, sens="ENTREE", date_mouvement=timezone.localdate(), libelle="Dépôt Wave",
        montant=Decimal("1000"), mode=ModePaiement.WAVE,
    )

    texte = client.get(reverse("finance:tresorerie")).content.decode()

    assert "Mobilemoney" not in texte and "Mobile Money" in texte
```

#### `apps/notifications/tests/test_facturation.py`

*118 lignes* — Notifications de facturation : soumission, validation, refus, factures échues.

```python
"""Notifications de facturation : soumission, validation, refus, factures échues."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.accounts.tests.factories import UserFactory
from apps.billing import services
from apps.billing.models import ModePaiement
from apps.billing.tests.helpers import brouillon, emise
from apps.notifications import taches
from apps.notifications.models import CategorieNotification, NiveauNotification, Notification

pytestmark = pytest.mark.django_db


def _de(utilisateur):
    return list(Notification.objects.filter(destinataire=utilisateur).order_by("pk"))


def test_la_direction_est_prevenue_d_une_facture_a_valider():
    chef, autre_direction, finance = (UserFactory(role=r) for r in (Role.DIRECTION, Role.DIRECTION, Role.FINANCES))
    preparateur = UserFactory(role=Role.FINANCES)
    facture = brouillon(prix="1000000", acteur=preparateur)

    services.soumettre(facture, preparateur)

    for compte in (chef, autre_direction):
        (notification,) = _de(compte)
        assert notification.categorie == CategorieNotification.FACTURE
        assert notification.niveau == NiveauNotification.ATTENTION
        assert facture.client.raison_sociale in notification.titre
        assert "1 180 000 FCFA TTC" in notification.message.replace("\xa0", " ").replace(" ", " ")
        assert facture.mission.numero in notification.message
        assert notification.url == reverse("billing:facture", args=[facture.pk])
    assert _de(finance) == []


def test_finances_et_l_auteur_sont_prevenus_de_la_validation():
    chef = UserFactory(role=Role.DIRECTION)
    preparateur = UserFactory(role=Role.ADMIN)  # un ADMIN peut aussi préparer
    autre_finances = UserFactory(role=Role.FINANCES)
    facture = brouillon(acteur=preparateur)
    services.soumettre(facture, preparateur)

    services.valider(facture, chef, aujourd_hui=date(2026, 9, 1))

    for compte in (preparateur, autre_finances):
        notification = _de(compte)[-1]
        assert notification.titre == f"Facture {facture.numero} validée"
        assert notification.niveau == NiveauNotification.INFO
        assert "échéance le 01/10/2026" in notification.message
    assert all("validée" not in n.titre for n in _de(chef))


def test_l_auteur_est_prevenu_du_refus_avec_le_motif():
    chef = UserFactory(role=Role.DIRECTION)
    preparateur = UserFactory(role=Role.FINANCES)
    autre_finances = UserFactory(role=Role.FINANCES)
    facture = brouillon(acteur=preparateur)
    services.soumettre(facture, preparateur)

    services.refuser(facture, chef, motif="Prix à revoir")

    notification = _de(preparateur)[-1]
    assert notification.titre.startswith("Facture renvoyée par la direction")
    assert "Prix à revoir" in notification.message
    assert notification.niveau == NiveauNotification.ATTENTION
    assert _de(autre_finances) == []


# --- factures échues ---


def test_les_factures_echues_previennent_finances_et_direction_une_seule_fois():
    finance, chef, rh = UserFactory(role=Role.FINANCES), UserFactory(role=Role.DIRECTION), UserFactory(role=Role.RH)
    facture = emise(prix="1000000", aujourd_hui=date(2026, 7, 1))  # échéance 31/07/2026
    services.enregistrer_reglement(
        facture, finance, montant=Decimal("180000"), mode=ModePaiement.VIREMENT, date_reglement=date(2026, 7, 5)
    )
    aujourd_hui = date(2026, 8, 10)

    premiere = taches.alerter_factures_echues(aujourd_hui=aujourd_hui)
    seconde = taches.alerter_factures_echues(aujourd_hui=aujourd_hui + timedelta(days=1))

    destinataires = User.objects.filter(role__in=[Role.FINANCES, Role.DIRECTION]).count()
    assert premiere == destinataires >= 2 and seconde == 0  # un message par compte, jamais renvoyé
    for compte in (finance, chef):
        alerte = [n for n in _de(compte) if "échue" in n.titre][0]
        assert alerte.niveau == NiveauNotification.URGENT
        assert alerte.titre == f"Facture {facture.numero} échue : {facture.client.raison_sociale}"
        assert "1 000 000 FCFA" in alerte.message.replace("\xa0", " ").replace(" ", " ")
        assert "échue depuis 10 jours" in alerte.message
        assert alerte.url == reverse("billing:facture", args=[facture.pk])
    assert _de(rh) == []


def test_pas_d_alerte_pour_une_facture_non_echue_ou_soldee():
    finance = UserFactory(role=Role.FINANCES)
    emise(aujourd_hui=date(2026, 8, 25))  # échéance 24/09
    soldee = emise(prix="1000", aujourd_hui=date(2026, 7, 1))
    services.enregistrer_reglement(
        soldee, finance, montant=Decimal("1180"), mode=ModePaiement.ESPECES, date_reglement=date(2026, 7, 2)
    )

    assert taches.alerter_factures_echues(aujourd_hui=date(2026, 9, 1)) == 0


def test_les_taches_quotidiennes_incluent_les_factures_echues():
    UserFactory(role=Role.FINANCES)
    emise(aujourd_hui=date(2026, 7, 1))

    resultat = taches.executer_taches_quotidiennes(aujourd_hui=date(2026, 9, 1))

    assert resultat["factures_echues"] == User.objects.filter(role__in=[Role.FINANCES, Role.DIRECTION]).count()
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
python -m pytest apps/billing/tests/test_views.py apps/finance/tests/test_views.py apps/notifications/tests/test_facturation.py -q --no-cov
```

**Résultat attendu :** `79 passed` (pour les 3 fichier(s) de tests présentés dans ce chapitre).

**Le circuit d'une facture, dans le navigateur :**

1. **`demo_finances`** : **Facturation → Nouvelle facture**, choisissez la mission **livrée** du chapitre 21.
   Un **brouillon** est créé (prix, TVA 18 %, délai du client). Ajoutez une ligne « Péages refacturés » 18 500.
   Cliquez **Soumettre à la Direction**.
2. **`demo_direction`** : ouvrez la facture (statut **À valider**) : **Valider et émettre**. Le **numéro
   `FACT-<année>-0001`** est attribué **à cet instant**, l'échéance est fixée (émission + 30 jours). Essayez
   avec `demo_admin` : le bouton n'existe pas, et un appel direct est refusé par le service.
3. **`demo_finances`** : **Enregistrer un règlement** (acompte, Wave), puis le solde (virement). Un montant
   **supérieur au reste à recouvrer** est refusé. La facture passe **Partiellement payée** puis **Payée**.
4. **Trésorerie** : les règlements apparaissent en entrées, sur les comptes Mobile Money et Banque.
   Saisissez un **mouvement manuel** (solde d'ouverture) et une **dépense** (péage) : les soldes se mettent à jour.
5. Cliquez **Version imprimable** puis « Imprimer ou enregistrer en PDF ».

## Ce qu'il faut retenir

- Ce que la personne peut faire dépend du **statut de l'objet** *et* de son **rôle** ; les deux sont calculés côté
  serveur.
- Une **page imprimable** est une page autonome, sans menu, avec ses propres règles d'impression.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 25 : écrans de la facturation, des dépenses et de la trésorerie"
```

---

[← Chapitre 24](24-ecrans-carburant.md) · [Sommaire](README.md) · [Chapitre 26 →](26-tableau-de-bord.md)
