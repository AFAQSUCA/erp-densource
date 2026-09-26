# Chapitre 25 — Écrans : facturation, dépenses et trésorerie

> 34 fichier(s) dans ce chapitre, 5569 lignes de code.

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

*253 lignes*

```python
from django import forms
from django.utils import timezone

from apps.core.forms import StyleTailwindMixin
from apps.customers import services as customers_services
from apps.customers.models import MotifExoneration
from apps.missions.models import Mission

from . import services
from .models import CATEGORIES_AUTOMATIQUES, CategorieDepense, ModePaiement, StatutFacture, StatutProforma


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
    categorie = forms.ChoiceField(
        label="Catégorie",
        choices=[c for c in CategorieDepense.choices if c[0] not in CATEGORIES_AUTOMATIQUES],
    )
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


# --- devis (R5) ---


class ProformaNouveauForm(StyleTailwindMixin, forms.Form):
    """Trajet, marchandise, poids et prix d'un nouveau devis ; la TVA reprend celle du client."""

    client = forms.ModelChoiceField(label="Client", queryset=None)
    lieu_chargement = forms.CharField(label="Lieu de chargement", max_length=200)
    lieu_livraison = forms.CharField(label="Lieu de livraison", max_length=200)
    nature_marchandise = forms.CharField(label="Nature de la marchandise", max_length=200)
    poids_t = forms.DecimalField(label="Poids (t)", min_value=0.01, decimal_places=2, max_digits=8)
    date_depart_souhaitee = forms.DateField(
        label="Départ souhaité", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    prix_convenu = forms.DecimalField(
        label="Prix convenu HT (FCFA)", min_value=0, decimal_places=2, max_digits=12
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = customers_services.clients_pour_selection()


class ProformaModifierForm(StyleTailwindMixin, forms.Form):
    """Trajet, marchandise, poids, prix et TVA d'un devis modifiable (brouillon ou contre-proposé)."""

    lieu_chargement = forms.CharField(label="Lieu de chargement", max_length=200)
    lieu_livraison = forms.CharField(label="Lieu de livraison", max_length=200)
    nature_marchandise = forms.CharField(label="Nature de la marchandise", max_length=200)
    poids_t = forms.DecimalField(label="Poids (t)", min_value=0.01, decimal_places=2, max_digits=8)
    date_depart_souhaitee = forms.DateField(
        label="Départ souhaité", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    prix_convenu = forms.DecimalField(
        label="Prix convenu HT (FCFA)", min_value=0, decimal_places=2, max_digits=12
    )
    taux_tva = forms.DecimalField(
        label="Taux de TVA (%)", min_value=0, max_value=100, decimal_places=2, max_digits=5
    )
    motif_exoneration = forms.ChoiceField(
        label="Motif d'exonération",
        choices=[("", "—")] + MotifExoneration.choices,
        required=False,
    )

    def clean(self):
        donnees = super().clean()
        taux = donnees.get("taux_tva")
        if taux is not None and taux == 0 and not donnees.get("motif_exoneration"):
            self.add_error("motif_exoneration", "Motif obligatoire quand la TVA est à 0 %.")
        return donnees


class DecisionClientProformaForm(StyleTailwindMixin, forms.Form):
    """Réponse du client à un devis envoyé, saisie par le chargé clientèle."""

    decision = forms.ChoiceField(
        label="Décision du client",
        choices=[("ACCEPTEE", "Le client accepte"), ("REFUSEE", "Le client refuse")],
        widget=forms.RadioSelect,
    )
    motif = forms.CharField(
        label="Motif du refus", widget=forms.Textarea(attrs={"rows": 2}), required=False
    )

    def clean(self):
        donnees = super().clean()
        if donnees.get("decision") == "REFUSEE" and not donnees.get("motif", "").strip():
            self.add_error("motif", "Motif obligatoire en cas de refus.")
        return donnees


class FiltreProformasForm(StyleTailwindMixin, forms.Form):
    """Filtres de la liste des devis ; un paramètre invalide est ignoré."""

    q = forms.CharField(label="Rechercher", required=False)
    statut = forms.ChoiceField(
        label="Statut", choices=[("", "Tous les statuts")] + StatutProforma.choices, required=False
    )
    client = forms.ModelChoiceField(label="Client", queryset=None, required=False, empty_label="Tous")

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
        }
```

#### `apps/finance/forms.py`

*142 lignes*

```python
from django import forms
from django.utils import timezone

from apps.billing.models import CategorieDepense, CompteTresorerie, ModePaiement
from apps.core.forms import StyleTailwindMixin
from apps.fleet import services as fleet_services

from .demandes import CATEGORIES_PARC_AUTO as CATEGORIES_PARC_AUTO_CODES
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


# --- dépenses du parc auto pré-approuvées (R2) ---


CATEGORIES_PARC_AUTO = [c for c in CategorieDepense.choices if c[0] in CATEGORIES_PARC_AUTO_CODES]


class DemandeDepenseForm(StyleTailwindMixin, forms.Form):
    """Le Parc Auto demande par avance un achat ou une réparation non routinière."""

    categorie = forms.ChoiceField(label="Catégorie", choices=CATEGORIES_PARC_AUTO)
    vehicule = forms.ModelChoiceField(
        label="Camion", queryset=None, required=False, empty_label="Aucun camion en particulier",
    )
    montant_estime = forms.DecimalField(
        label="Montant estimé (FCFA)", min_value=0, decimal_places=2, max_digits=14
    )
    fournisseur = forms.CharField(label="Fournisseur", max_length=200, required=False)
    motif = forms.CharField(label="Motif", widget=forms.Textarea(attrs={"rows": 3}))
    piece_jointe = forms.FileField(label="Devis ou pièce jointe", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vehicule"].queryset = fleet_services.vehicules_queryset()


class DecisionDemandeForm(StyleTailwindMixin, forms.Form):
    """Décision de la direction : validation (montant validé ajustable) ou refus (motif)."""

    decision = forms.ChoiceField(
        label="Décision", choices=[("VALIDER", "Valider"), ("REFUSER", "Refuser")], widget=forms.RadioSelect,
    )
    montant_valide = forms.DecimalField(
        label="Montant validé (FCFA)", min_value=0, decimal_places=2, max_digits=14, required=False,
        help_text="Laissez vide pour valider le montant estimé tel quel.",
    )
    motif_refus = forms.CharField(
        label="Motif du refus", widget=forms.Textarea(attrs={"rows": 2}), required=False
    )

    def clean(self):
        donnees = super().clean()
        if donnees.get("decision") == "REFUSER" and not donnees.get("motif_refus", "").strip():
            self.add_error("motif_refus", "Motif obligatoire en cas de refus.")
        return donnees


class ExecuterOrdreForm(StyleTailwindMixin, forms.Form):
    """La Finance exécute un ordre de décaissement validé par la direction."""

    mode_paiement = forms.ChoiceField(label="Mode de paiement", choices=ModePaiement.choices)
    montant_reel = forms.DecimalField(
        label="Montant réel (FCFA)", min_value=0, decimal_places=2, max_digits=14
    )
    reference = forms.CharField(label="Référence", max_length=100, required=False)
    justificatif = forms.FileField(label="Justificatif", required=False)


class RevaliderOrdreForm(StyleTailwindMixin, forms.Form):
    """La direction revoit un ordre bloqué par un dépassement de plus de 10 %."""

    montant_valide = forms.DecimalField(
        label="Nouveau montant validé (FCFA)", min_value=0, decimal_places=2, max_digits=14
    )


class EnveloppeForm(StyleTailwindMixin, forms.Form):
    """La direction fixe le plafond mensuel d'une catégorie, globalement ou pour un camion précis."""

    categorie = forms.ChoiceField(label="Catégorie", choices=CATEGORIES_PARC_AUTO)
    vehicule = forms.ModelChoiceField(
        label="Camion", queryset=None, required=False, empty_label="Tous les camions (enveloppe globale)",
    )
    annee = forms.IntegerField(label="Année", min_value=2020, max_value=2100)
    mois = forms.IntegerField(label="Mois", min_value=1, max_value=12)
    montant_plafond = forms.DecimalField(
        label="Plafond (FCFA)", min_value=0, decimal_places=2, max_digits=14
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vehicule"].queryset = fleet_services.vehicules_queryset()
```

## Étape 2 — Vues et adresses

#### `apps/billing/views.py`

*723 lignes* — Écrans de facturation : factures, règlements, dépenses.

```python
"""Écrans de facturation : factures, règlements, dépenses.

Aucune règle métier ici : les vues contrôlent le rôle, lisent le formulaire et délèguent à
``services.py`` (conventions.md:19-23).
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.accounts.mixins import RoleRequiredMixin
from apps.core.formats import nombre
from apps.core.rapports import contexte_rapport
from apps.core.views import ImpressionListeMixin, PaginationTolerante
from apps.missions import permissions as missions_permissions
from apps.missions.exceptions import MissionError

from . import permissions, services
from .exceptions import BillingError
from .forms import (
    ConditionsForm,
    DecisionClientProformaForm,
    DepenseForm,
    FactureNouvelleForm,
    FiltreDepensesForm,
    FiltreFacturesForm,
    FiltreProformasForm,
    LigneForm,
    MotifForm,
    ProformaModifierForm,
    ProformaNouveauForm,
    ReglementForm,
)
from .models import (
    CategorieDepense,
    Depense,
    Facture,
    LigneFacture,
    ModePaiement,
    Proforma,
    Reglement,
    StatutFacture,
    StatutProforma,
    STATUTS_A_RECOUVRER,
)


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


class FactureImprimerView(ImpressionListeMixin, FactureListView):
    """Rapport imprimable des factures (mêmes filtres que la liste)."""

    titre_impression = "Factures"
    colonnes = (
        ("N°", lambda f: f.numero or f"Sans numéro ({f.mission.numero})"), ("Client", "client.raison_sociale"),
        ("Mission", "mission.numero"), ("Statut", "get_statut_display"),
        ("Émise le", lambda f: f.date_emission.strftime("%d/%m/%Y") if f.date_emission else "—"),
        ("Échéance", lambda f: f.date_echeance.strftime("%d/%m/%Y") if f.date_echeance else "—"),
        ("TTC", lambda f: f"{nombre(f.montant_ttc)} FCFA"), ("Reste à recouvrer", lambda f: f"{nombre(f.reste)} FCFA"),
    )

    def get_sous_titre_impression(self):
        criteres = self.get_filtre().criteres()
        morceaux = []
        if criteres.get("statut") in StatutFacture.values:
            morceaux.append(f"statut : {StatutFacture(criteres['statut']).label}")
        if criteres.get("client"):
            morceaux.append(f"client : {criteres['client'].raison_sociale}")
        if criteres.get("echues"):
            morceaux.append("échues seulement")
        if criteres.get("recherche"):
            morceaux.append(f"recherche : « {criteres['recherche']} »")
        return " · ".join(morceaux)


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
        titre = f"FACTURE {self.object.numero}" if self.object.est_emise else "PROJET DE FACTURE"
        contexte.update(contexte_rapport(self.request, titre=titre))
        contexte.update(
            lignes=self.object.lignes.all(),
            reglements=self.object.reglements.all(),
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
            modes=ModePaiement.choices,
        )
        return contexte


class DepenseImprimerView(ImpressionListeMixin, DepenseListView):
    """Rapport imprimable des dépenses (mêmes filtres que la liste, y compris carburant/pièces/OR)."""

    titre_impression = "Dépenses"
    colonnes = (
        ("Date", lambda d: d.date_depense.strftime("%d/%m/%Y")), ("Libellé", "libelle"),
        ("Catégorie", "get_categorie_display"), ("Mode", "get_mode_display"),
        ("Montant", lambda d: f"{nombre(d.montant)} FCFA"),
        ("Origine", lambda d: "Automatique" if d.est_automatique else "Saisie"),
    )

    def get_sous_titre_impression(self):
        criteres = self.get_filtre().criteres()
        morceaux = []
        if criteres.get("categorie") in CategorieDepense.values:
            morceaux.append(f"catégorie : {CategorieDepense(criteres['categorie']).label}")
        if criteres.get("date_debut"):
            morceaux.append(f"du {criteres['date_debut'].strftime('%d/%m/%Y')}")
        if criteres.get("date_fin"):
            morceaux.append(f"au {criteres['date_fin'].strftime('%d/%m/%Y')}")
        if criteres.get("recherche"):
            morceaux.append(f"recherche : « {criteres['recherche']} »")
        return " · ".join(morceaux)


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


class DepenseModeView(RoleRequiredMixin, View):
    """La Finance corrige le mode de paiement d'une dépense automatique (plein, achat de pièces, OR).

    Ces dépenses sont créées en espèces par défaut ; le mode décide du compte débité en trésorerie.
    """

    roles = permissions.SAISIE
    http_method_names = ["post"]

    def post(self, request, pk):
        depense = get_object_or_404(Depense, pk=pk)
        mode = request.POST.get("mode", "")
        try:
            services.changer_mode_depense(depense, request.user, mode=mode)
        except BillingError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(
                request, f"Mode de paiement de « {depense.libelle} » : {ModePaiement(mode).label}."
            )
        return redirect("billing:depenses")


# --- devis (R5) ---


class ProformaListView(PaginationTolerante, RoleRequiredMixin, ListView):
    roles = permissions.PROFORMA_CONSULTATION
    template_name = "billing/proforma_list.html"
    context_object_name = "proformas"
    paginate_by = 20

    def get_filtre(self):
        if not hasattr(self, "_filtre"):
            self._filtre = FiltreProformasForm(self.request.GET)
        return self._filtre

    def get_queryset(self):
        return services.rechercher_proformas(**self.get_filtre().criteres())

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            filtre=self.get_filtre(),
            filtres_actifs=any(self.get_filtre().criteres().values()),
            peut_saisir=self.request.user.role_effectif in permissions.PROFORMA_SAISIE,
        )
        return contexte


class ProformaImprimerView(ImpressionListeMixin, ProformaListView):
    """Rapport imprimable des devis (mêmes filtres que la liste)."""

    titre_impression = "Devis"
    colonnes = (
        ("N°", lambda p: p.numero or "Brouillon"), ("Client", "client.raison_sociale"),
        ("Trajet", lambda p: f"{p.lieu_chargement} → {p.lieu_livraison}"),
        ("Statut", "get_statut_display"),
        ("TTC", lambda p: f"{nombre(p.montant_ttc)} FCFA"),
        ("Valable jusqu'au", lambda p: p.date_validite.strftime("%d/%m/%Y") if p.date_validite else "—"),
    )

    def get_sous_titre_impression(self):
        criteres = self.get_filtre().criteres()
        morceaux = []
        if criteres.get("statut") in StatutProforma.values:
            morceaux.append(f"statut : {StatutProforma(criteres['statut']).label}")
        if criteres.get("client"):
            morceaux.append(f"client : {criteres['client'].raison_sociale}")
        if criteres.get("recherche"):
            morceaux.append(f"recherche : « {criteres['recherche']} »")
        return " · ".join(morceaux)


class ProformaCreateView(RoleRequiredMixin, FormView):
    roles = permissions.PROFORMA_SAISIE
    form_class = ProformaNouveauForm
    template_name = "billing/proforma_form.html"

    def form_valid(self, form):
        try:
            proforma = services.creer_proforma(self.request.user, **form.cleaned_data)
        except BillingError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, "Devis créé. Vérifiez le prix, puis soumettez-le à la finance.")
        return redirect("billing:proforma", pk=proforma.pk)


class ProformaModifierView(RoleRequiredMixin, FormView):
    roles = permissions.PROFORMA_SAISIE
    form_class = ProformaModifierForm
    template_name = "billing/proforma_modifier.html"

    def dispatch(self, request, *args, **kwargs):
        self.proforma = get_object_or_404(Proforma, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        if not self.proforma.est_modifiable:
            messages.error(request, "Ce devis n'est plus modifiable dans son état actuel.")
            return redirect("billing:proforma", pk=self.proforma.pk)
        return super().get(request, *args, **kwargs)

    def get_initial(self):
        p = self.proforma
        return {
            "lieu_chargement": p.lieu_chargement,
            "lieu_livraison": p.lieu_livraison,
            "nature_marchandise": p.nature_marchandise,
            "poids_t": p.poids_t,
            "date_depart_souhaitee": p.date_depart_souhaitee,
            "prix_convenu": p.prix_convenu,
            "taux_tva": p.taux_tva,
            "motif_exoneration": p.motif_exoneration,
        }

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["proforma"] = self.proforma
        return contexte

    def form_valid(self, form):
        try:
            services.modifier_proforma(self.proforma, self.request.user, **form.cleaned_data)
        except BillingError as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, "Devis mis à jour.")
        return redirect("billing:proforma", pk=self.proforma.pk)


class ProformaDetailView(RoleRequiredMixin, DetailView):
    roles = permissions.PROFORMA_CONSULTATION
    template_name = "billing/proforma_detail.html"
    context_object_name = "proforma"

    def get_queryset(self):
        return services.proformas_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        proforma = self.object
        # La validation (finance ou direction) et la contre-proposition sont réservées au rôle
        # lui-même (un superutilisateur n'y est pas admis), comme pour la validation d'une facture.
        role_strict = self.request.user.role
        saisie = self.request.user.role_effectif in permissions.PROFORMA_SAISIE
        modifiable = proforma.est_modifiable
        peut_valider_finances = (
            role_strict in permissions.PROFORMA_VALIDATION_FINANCES
            and proforma.statut == StatutProforma.SOUMISE
        )
        peut_valider_direction = (
            role_strict in permissions.PROFORMA_VALIDATION_DIRECTION
            and proforma.statut == StatutProforma.EN_ATTENTE_DIRECTION
        )
        contexte.update(
            peut_modifier=saisie and modifiable,
            peut_abandonner=saisie and modifiable,
            peut_soumettre=saisie and modifiable,
            peut_valider_finances=peut_valider_finances,
            peut_valider_direction=peut_valider_direction,
            peut_contre_proposer=peut_valider_finances or peut_valider_direction,
            peut_envoyer_client=saisie and proforma.statut == StatutProforma.VALIDEE,
            peut_decider_client=saisie and proforma.statut == StatutProforma.ENVOYEE_CLIENT,
            peut_creer_mission=(
                proforma.statut == StatutProforma.ACCEPTEE
                and self.request.user.role_effectif in missions_permissions.CREATION
            ),
            form_contre_proposition=MotifForm() if peut_valider_finances or peut_valider_direction else None,
            form_decision_client=DecisionClientProformaForm()
            if saisie and proforma.statut == StatutProforma.ENVOYEE_CLIENT
            else None,
            historique=services.historique_proforma(proforma),
        )
        return contexte


class ProformaPrintView(RoleRequiredMixin, DetailView):
    """Version imprimable du devis à remettre au client (Ctrl+P → « Enregistrer au format PDF »)."""

    roles = permissions.PROFORMA_CONSULTATION
    template_name = "billing/proforma_print.html"
    context_object_name = "proforma"

    def get_queryset(self):
        return services.proformas_queryset()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        titre = f"DEVIS {self.object.numero}" if self.object.numero else "PROJET DE DEVIS"
        contexte.update(contexte_rapport(self.request, titre=titre))
        return contexte


class _ActionProforma(RoleRequiredMixin, View):
    """Action en POST sur un devis : formulaire → service → message → retour à la fiche."""

    http_method_names = ["post"]
    form_class = None

    def get_proforma(self, pk):
        return get_object_or_404(Proforma, pk=pk)

    def executer(self, request, proforma, donnees):  # pragma: no cover - surchargé
        raise NotImplementedError

    def post(self, request, pk, **kwargs):
        proforma = self.get_proforma(pk)
        donnees = {}
        if self.form_class is not None:
            form = self.form_class(request.POST)
            if not form.is_valid():
                _erreurs_en_messages(request, form)
                return redirect("billing:proforma", pk=proforma.pk)
            donnees = form.cleaned_data
        try:
            message = self.executer(request, proforma, donnees, **kwargs)
        except BillingError as erreur:
            messages.error(request, str(erreur))
        else:
            if message:
                messages.success(request, message)
        cible, arguments = self.redirection(proforma)
        return redirect(cible, **arguments)

    def redirection(self, proforma):
        return "billing:proforma", {"pk": proforma.pk}


class ProformaAbandonnerView(_ActionProforma):
    roles = permissions.PROFORMA_SAISIE

    def executer(self, request, proforma, donnees):
        services.abandonner_proforma(proforma, request.user)
        messages.success(request, "Devis abandonné.")
        return None

    def redirection(self, proforma):
        return "billing:proformas", {}


class ProformaSoumettreView(_ActionProforma):
    roles = permissions.PROFORMA_SAISIE

    def executer(self, request, proforma, donnees):
        services.soumettre_proforma(proforma, request.user)
        return "Devis envoyé à la finance pour validation."


class ProformaContreProposerView(_ActionProforma):
    roles = permissions.PROFORMA_VALIDATION_FINANCES | permissions.PROFORMA_VALIDATION_DIRECTION
    form_class = MotifForm

    def executer(self, request, proforma, donnees):
        services.contre_proposer_proforma(proforma, request.user, motif=donnees["motif"])
        return "Devis renvoyé au chargé clientèle avec votre motif."


class ProformaValiderFinancesView(_ActionProforma):
    roles = permissions.PROFORMA_VALIDATION_FINANCES

    def executer(self, request, proforma, donnees):
        proforma = services.valider_proforma(proforma, request.user)
        if proforma.statut == StatutProforma.EN_ATTENTE_DIRECTION:
            return "Devis validé : transmis à la direction (montant au-delà du seuil)."
        return f"Devis {proforma.numero} validé."


class ProformaValiderDirectionView(_ActionProforma):
    roles = permissions.PROFORMA_VALIDATION_DIRECTION

    def executer(self, request, proforma, donnees):
        proforma = services.valider_proforma_direction(proforma, request.user)
        return f"Devis {proforma.numero} validé."


class ProformaEnvoyerClientView(_ActionProforma):
    roles = permissions.PROFORMA_SAISIE

    def executer(self, request, proforma, donnees):
        proforma = services.envoyer_proforma_au_client(proforma, request.user)
        return f"Devis envoyé au client, valable jusqu'au {proforma.date_validite:%d/%m/%Y}."


class ProformaDecisionClientView(_ActionProforma):
    roles = permissions.PROFORMA_SAISIE
    form_class = DecisionClientProformaForm

    def executer(self, request, proforma, donnees):
        services.enregistrer_decision_client(
            proforma, request.user,
            acceptee=donnees["decision"] == "ACCEPTEE",
            motif=donnees.get("motif", ""),
        )
        return "Décision du client enregistrée."


class ProformaCreerMissionView(RoleRequiredMixin, View):
    """Devis accepté → mission (R6) : même rôle que la création manuelle d'une mission."""

    roles = missions_permissions.CREATION
    http_method_names = ["post"]

    def post(self, request, pk):
        proforma = get_object_or_404(Proforma, pk=pk)
        try:
            mission = services.convertir_en_mission(proforma)
        except (BillingError, MissionError) as erreur:
            messages.error(request, str(erreur))
            return redirect("billing:proforma", pk=proforma.pk)
        messages.success(request, f"Mission {mission.numero} créée à partir du devis {proforma.numero}.")
        return redirect("missions:detail", pk=mission.pk)

```

Lisez `FactureDetailView.get_context_data` : c'est lui qui prépare, pour le gabarit, **ce que la personne a le droit
de faire** (`saisie`, `validation`) — jamais le gabarit.

#### `apps/finance/views.py`

*373 lignes* — Trésorerie : journal des mouvements, soldes par compte, mouvements manuels.

```python
"""Trésorerie : journal des mouvements, soldes par compte, mouvements manuels."""

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

from . import demandes as demandes_services
from . import permissions, services
from .forms import (
    DecisionDemandeForm,
    DemandeDepenseForm,
    EnveloppeForm,
    ExecuterOrdreForm,
    FiltreTresorerieForm,
    MotifForm,
    MouvementForm,
    RevaliderOrdreForm,
)
from .models import DemandeDepense, MouvementManuel, OrdreDecaissement, StatutDemandeDepense, StatutOrdreDecaissement


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
```

#### `apps/billing/urls.py`

*68 lignes*

```python
from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path("", views.FactureListView.as_view(), name="factures"),
    path("imprimer/", views.FactureImprimerView.as_view(), name="factures_imprimer"),
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
    path("depenses/imprimer/", views.DepenseImprimerView.as_view(), name="depenses_imprimer"),
    path("depenses/nouvelle/", views.DepenseCreateView.as_view(), name="depense_nouvelle"),
    path("depenses/<int:pk>/mode/", views.DepenseModeView.as_view(), name="depense_mode"),
    path("devis/", views.ProformaListView.as_view(), name="proformas"),
    path("devis/imprimer/", views.ProformaImprimerView.as_view(), name="proformas_imprimer"),
    path("devis/nouveau/", views.ProformaCreateView.as_view(), name="proforma_nouveau"),
    path("devis/<int:pk>/", views.ProformaDetailView.as_view(), name="proforma"),
    path("devis/<int:pk>/imprimer/", views.ProformaPrintView.as_view(), name="proforma_imprimer"),
    path("devis/<int:pk>/modifier/", views.ProformaModifierView.as_view(), name="proforma_modifier"),
    path("devis/<int:pk>/abandonner/", views.ProformaAbandonnerView.as_view(), name="proforma_abandonner"),
    path("devis/<int:pk>/soumettre/", views.ProformaSoumettreView.as_view(), name="proforma_soumettre"),
    path(
        "devis/<int:pk>/contre-proposer/",
        views.ProformaContreProposerView.as_view(),
        name="proforma_contre_proposer",
    ),
    path(
        "devis/<int:pk>/valider-finances/",
        views.ProformaValiderFinancesView.as_view(),
        name="proforma_valider_finances",
    ),
    path(
        "devis/<int:pk>/valider-direction/",
        views.ProformaValiderDirectionView.as_view(),
        name="proforma_valider_direction",
    ),
    path(
        "devis/<int:pk>/envoyer-client/",
        views.ProformaEnvoyerClientView.as_view(),
        name="proforma_envoyer_client",
    ),
    path(
        "devis/<int:pk>/decision-client/",
        views.ProformaDecisionClientView.as_view(),
        name="proforma_decision_client",
    ),
    path(
        "devis/<int:pk>/creer-mission/",
        views.ProformaCreerMissionView.as_view(),
        name="proforma_creer_mission",
    ),
]
```

#### `apps/finance/urls.py`

*25 lignes*

```python
from django.urls import path

from . import views

app_name = "finance"

urlpatterns = [
    path("", views.TresorerieView.as_view(), name="tresorerie"),
    path("imprimer/", views.TresorerieImprimerView.as_view(), name="imprimer"),
    path(
        "versements/<int:pk>/confirmer/",
        views.VersementConfirmerView.as_view(),
        name="versement_confirmer",
    ),
    path("mouvements/", views.MouvementCreateView.as_view(), name="mouvement_creer"),
    path("mouvements/<int:pk>/annuler/", views.MouvementAnnulerView.as_view(), name="mouvement_annuler"),
    path("demandes/", views.DemandeListView.as_view(), name="demandes"),
    path("demandes/nouvelle/", views.DemandeCreateView.as_view(), name="demande_nouvelle"),
    path("demandes/<int:pk>/", views.DemandeDetailView.as_view(), name="demande"),
    path("demandes/<int:pk>/decider/", views.DemandeDeciderView.as_view(), name="demande_decider"),
    path("ordres/<int:pk>/executer/", views.OrdreExecuterView.as_view(), name="ordre_executer"),
    path("ordres/<int:pk>/revalider/", views.OrdreRevaliderView.as_view(), name="ordre_revalider"),
    path("enveloppes/", views.EnveloppeListView.as_view(), name="enveloppes"),
    path("enveloppes/nouvelle/", views.EnveloppeCreateView.as_view(), name="enveloppe_nouvelle"),
]
```

#### `config/urls.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/urls.py (avant)
+++ config/urls.py (après)
@@ -25,4 +25,6 @@
     path("carburant/", include("apps.fuel.urls")),
     path("stock/", include("apps.inventory.urls")),
+    path("facturation/", include("apps.billing.urls")),
+    path("finances/", include("apps.finance.urls")),
     path("audit/", include("apps.audit.urls")),
     path("notifications/", include("apps.notifications.urls")),
```

## Étape 3 — Gabarits

```bash
mkdir -p apps/billing/templates/billing apps/finance/templates/finance
```

#### `apps/billing/templates/billing/facture_list.html`

*85 lignes*

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
    <div class="flex flex-wrap items-center gap-2">
      <a href="{% url 'billing:factures_imprimer' %}?{{ request.GET.urlencode }}" target="_blank" rel="noopener"
         class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
        <i class="fa-solid fa-print" aria-hidden="true"></i> Imprimer
      </a>
      {% if peut_saisir %}
        <a href="{% url 'billing:nouvelle' %}"
           class="inline-flex items-center gap-2 rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
          <i class="fa-solid fa-plus" aria-hidden="true"></i> Nouvelle facture
          {% if missions_a_facturer %}<span class="rounded-full bg-accent-500 px-2 py-0.5 text-xs text-slate-900">{{ missions_a_facturer }} mission{{ missions_a_facturer|pluralize }} à facturer</span>{% endif %}
        </a>
      {% endif %}
    </div>
  </div>

  <dl class="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
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

  <div class="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
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
            <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
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
              <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
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

*55 lignes*

```django
{% load humanize static %}<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ facture.numero|default:"Brouillon" }} · {{ facture.client.raison_sociale }}</title>
  {% include "rapports/_style_impression.html" %}
  <style>
    .totaux { margin-left: auto; width: 320px; margin-top: 1rem; }
    .totaux div { display: flex; justify-content: space-between; padding: .25rem 0; }
    .total { border-top: 2px solid #111; font-weight: bold; font-size: 1.1rem; }
    .filigrane { color: #b91c1c; border: 2px solid #b91c1c; display: inline-block; padding: .2rem .8rem; font-weight: bold; margin-top: .5rem; }
  </style>
</head>
<body>
  {% include "rapports/_entete_impression.html" %}
  <div style="text-align:right">
    {% if facture.date_emission %}<div class="petit">Émise le {{ facture.date_emission|date:"d/m/Y" }} — Échéance : {{ facture.date_echeance|date:"d/m/Y" }}</div>{% endif %}
    {% if not facture.est_emise %}<div class="filigrane">NON VALIDÉE</div>{% endif %}
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
  {% include "rapports/_pied_impression.html" %}
  <script src="{% static 'js/app.js' %}" defer></script>
</body>
</html>
```

#### `apps/billing/templates/billing/depense_list.html`

*84 lignes*

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
    <div class="flex flex-wrap items-center gap-2">
      <a href="{% url 'billing:depenses_imprimer' %}?{{ request.GET.urlencode }}" target="_blank" rel="noopener"
         class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
        <i class="fa-solid fa-print" aria-hidden="true"></i> Imprimer
      </a>
      {% if peut_saisir %}
        <a href="{% url 'billing:depense_nouvelle' %}" class="inline-flex items-center gap-2 rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2"><i class="fa-solid fa-plus" aria-hidden="true"></i> Nouvelle dépense</a>
      {% endif %}
    </div>
  </div>

  <section class="mt-5" aria-labelledby="titre-mois">
    <h2 id="titre-mois" class="text-sm font-semibold text-slate-900">Ce mois-ci : {{ total_mois|floatformat:0|intcomma }} FCFA</h2>
    <dl class="mt-2 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {% for c in par_categorie %}
        <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">{{ c.libelle }}</dt><dd class="mt-1 text-xl font-bold text-slate-900">{{ c.total|floatformat:0|intcomma }} <span class="text-sm font-medium text-slate-600">FCFA</span></dd></div>
      {% endfor %}
    </dl>
    <p class="mt-2 text-xs text-slate-600">Le carburant (chaque plein), les pièces (chaque achat en stock) et la main-d'œuvre des ordres de réparation clôturés s'ajoutent ici automatiquement, en espèces par défaut : ne les saisissez pas à la main. Si le paiement s'est fait autrement, corrigez le mode sur la ligne.</p>
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
          <tr><th scope="col" class="px-4 py-3">Date</th><th scope="col" class="px-4 py-3">Libellé</th><th scope="col" class="px-4 py-3">Catégorie</th><th scope="col" class="hidden px-4 py-3 xl:table-cell">Mission</th><th scope="col" class="px-4 py-3">Mode</th><th scope="col" class="px-4 py-3 text-right">Montant</th></tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          {% for d in depenses %}
            <tr class="hover:bg-slate-50">
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ d.date_depense|date:"d/m/Y" }}</td>
              <td class="px-4 py-3 text-slate-900">{{ d.libelle }}{% if d.est_automatique %}<span class="ml-1 inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700 ring-1 ring-inset ring-slate-300">Automatique</span>{% endif %}{% if d.reference %}<span class="block text-xs text-slate-600">Pièce {{ d.reference }}</span>{% endif %}</td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ d.get_categorie_display }}</td>
              <td class="hidden whitespace-nowrap px-4 py-3 text-slate-700 xl:table-cell">{{ d.mission.numero|default:"—" }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">
                {% if peut_saisir and d.est_automatique %}
                  <form method="post" action="{% url 'billing:depense_mode' d.pk %}" class="flex items-center gap-1">
                    {% csrf_token %}
                    <label class="sr-only" for="mode-{{ d.pk }}">Mode de paiement</label>
                    <select id="mode-{{ d.pk }}" name="mode" class="rounded-lg border border-slate-300 bg-white px-2 py-1 text-xs focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30">
                      {% for code, libelle in modes %}<option value="{{ code }}"{% if code == d.mode %} selected{% endif %}>{{ libelle }}</option>{% endfor %}
                    </select>
                    <button type="submit" class="rounded-lg border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">Changer</button>
                  </form>
                {% else %}{{ d.get_mode_display }}{% endif %}
              </td>
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
    <div class="grid grid-cols-1 gap-5 sm:grid-cols-2">
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

*146 lignes*

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
    <div class="flex flex-wrap items-center gap-2">
      <a href="{% url 'finance:imprimer' %}?{{ request.GET.urlencode }}" target="_blank" rel="noopener"
         class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
        <i class="fa-solid fa-print" aria-hidden="true"></i> Imprimer
      </a>
      {% if peut_saisir %}
        <button type="button" @click="saisie = !saisie" :aria-expanded="saisie.toString()"
                class="inline-flex items-center gap-2 rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
          <i class="fa-solid fa-plus" aria-hidden="true"></i> Autre mouvement
        </button>
      {% endif %}
    </div>
  </div>

  <dl class="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
    <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><dt class="text-sm text-slate-600">Solde total</dt><dd class="mt-1 text-2xl font-bold {% if soldes.total < 0 %}text-red-800{% else %}text-slate-900{% endif %}">{{ soldes.total|floatformat:0|intcomma }} <span class="text-sm font-medium text-slate-600">FCFA</span></dd></div>
    {% for code, libelle in comptes %}
      <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <dt class="text-sm text-slate-600">{{ libelle }}</dt>
        {% for c, s in soldes.items %}{% if c == code %}<dd class="mt-1 text-xl font-bold {% if s < 0 %}text-red-800{% else %}text-slate-900{% endif %}">{{ s|floatformat:0|intcomma }} <span class="text-sm font-medium text-slate-600">FCFA</span></dd>{% endif %}{% endfor %}
      </div>
    {% endfor %}
  </dl>
  <p class="mt-3 text-sm text-slate-700">Ce mois-ci : <strong class="text-emerald-800">+{{ mois.entrees|floatformat:0|intcomma }}</strong> d'entrées, <strong class="text-red-800">−{{ mois.sorties|floatformat:0|intcomma }}</strong> de sorties, variation <strong>{{ mois.variation|floatformat:0|intcomma }} FCFA</strong>.</p>

  {# Factures émises dont le versement n'est pas encore confirmé : pas de l'argent en caisse, une attente #}
  <section class="mt-6 rounded-xl border {% if versements.echu %}border-red-300{% else %}border-amber-300{% endif %} bg-white p-5 shadow-sm" aria-labelledby="titre-versements">
    <div class="flex flex-wrap items-baseline justify-between gap-2">
      <h2 id="titre-versements" class="text-base font-semibold text-slate-900"><i class="fa-solid fa-hourglass-half mr-2 text-amber-700" aria-hidden="true"></i>Versements à confirmer</h2>
      {% if versements.nombre %}
        <p class="text-sm text-slate-700"><strong>{{ versements.total|floatformat:0|intcomma }} FCFA</strong> attendus{% if versements.echu %}, dont <strong class="text-red-800">{{ versements.echu|floatformat:0|intcomma }} échus</strong>{% endif %}</p>
      {% endif %}
    </div>
    {% if versements.nombre %}
      <p class="mt-1 text-xs text-slate-600">Factures émises, en attente de règlement. Quand l'argent est reçu, confirmez-le : il devient une entrée ci-dessous. Solde prévisionnel si tout est encaissé : <strong>{{ solde_previsionnel|floatformat:0|intcomma }} FCFA</strong>.</p>
      <div class="mt-3 overflow-x-auto">
        <table class="min-w-full divide-y divide-slate-200 text-sm">
          <caption class="sr-only">Versements attendus</caption>
          <thead class="text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
            <tr><th scope="col" class="py-2 pr-4">Facture</th><th scope="col" class="px-4 py-2">Client</th><th scope="col" class="px-4 py-2">Échéance</th><th scope="col" class="px-4 py-2 text-right">Reste à recouvrer</th>{% if peut_saisir %}<th scope="col" class="py-2 pl-4"><span class="sr-only">Action</span></th>{% endif %}</tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            {% for v in versements.lignes %}
              <tr>
                <td class="whitespace-nowrap py-2 pr-4 font-semibold"><a href="{% url 'billing:facture' v.facture.pk %}" class="text-marque-700 underline-offset-2 hover:underline">{{ v.facture.numero }}</a></td>
                <td class="px-4 py-2 text-slate-800">{{ v.facture.client.raison_sociale }}<span class="block text-xs text-slate-600">{{ v.facture.mission.numero }}</span></td>
                <td class="whitespace-nowrap px-4 py-2 {% if v.echue %}font-semibold text-red-800{% else %}text-slate-700{% endif %}">{{ v.facture.date_echeance|date:"d/m/Y"|default:"—" }}{% if v.echue %} · échue depuis {{ v.jours }} j{% elif v.jours is not None %} · dans {{ v.jours }} j{% endif %}</td>
                <td class="whitespace-nowrap px-4 py-2 text-right font-medium text-slate-900">{{ v.reste|floatformat:0|intcomma }} FCFA</td>
                {% if peut_saisir %}
                  <td class="whitespace-nowrap py-2 pl-4 text-right">
                    <a href="{% url 'finance:versement_confirmer' v.facture.pk %}" class="inline-flex items-center gap-1.5 rounded-lg bg-emerald-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 focus-visible:ring-offset-2"><i class="fa-solid fa-circle-check" aria-hidden="true"></i> Confirmer le versement</a>
                  </td>
                {% endif %}
              </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    {% else %}
      <p class="mt-2 text-sm text-slate-600">Aucun versement en attente : toutes les factures émises sont soldées.</p>
    {% endif %}
  </section>

  {% if peut_saisir %}
    <form method="post" action="{% url 'finance:mouvement_creer' %}" x-show="saisie" x-cloak class="mt-5 space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      {% csrf_token %}
      <h2 class="text-base font-semibold text-slate-900">Autre entrée ou sortie</h2>
      <p class="text-xs text-slate-600">Solde d'ouverture, apport, frais bancaires, retrait… Les règlements et les dépenses se saisissent depuis la facturation.</p>
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
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

#### `apps/billing/templates/billing/proforma_detail.html`

*175 lignes*

```django
{% extends "base.html" %}
{% load ui humanize %}
{% block titre %}{{ proforma.numero|default:"Devis" }}{% endblock %}
{% block entete %}Devis{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-6xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'billing:proformas' %}" class="underline-offset-2 hover:underline">Devis</a>
    <span aria-hidden="true">/</span> {{ proforma.numero|default:"Brouillon" }}
  </nav>

  <div class="mt-2 flex flex-wrap items-center justify-between gap-3">
    <div class="flex flex-wrap items-center gap-3">
      <h1 class="text-2xl font-bold text-slate-900">{{ proforma.numero|default:"Devis" }}</h1>
      {% badge proforma.statut proforma.get_statut_display %}
    </div>
    <a href="{% url 'billing:proforma_imprimer' proforma.pk %}" target="_blank" rel="noopener"
       class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
      <i class="fa-solid fa-print" aria-hidden="true"></i> Version imprimable
    </a>
  </div>
  <p class="mt-1 text-sm text-slate-600">
    {{ proforma.client.raison_sociale }} · {{ proforma.lieu_chargement }} → {{ proforma.lieu_livraison }}
    {% if proforma.date_envoi %}· envoyé le {{ proforma.date_envoi|date:"d/m/Y" }}, valable jusqu'au {{ proforma.date_validite|date:"d/m/Y" }}{% endif %}
  </p>

  {% if proforma.statut == "CONTRE_PROPOSEE" and proforma.motif_contre_proposition %}
    <div role="alert" class="mt-4 rounded-lg border border-amber-400 bg-amber-50 px-4 py-3 text-sm text-amber-950">
      <p class="font-semibold">Contre-proposition</p>
      <p class="mt-1 whitespace-pre-line">{{ proforma.motif_contre_proposition }}</p>
    </div>
  {% endif %}
  {% if proforma.statut == "REFUSEE" and proforma.motif_refus_client %}
    <div role="alert" class="mt-4 rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">
      <p class="font-semibold">Refusé par le client</p>
      <p class="mt-1 whitespace-pre-line">{{ proforma.motif_refus_client }}</p>
    </div>
  {% endif %}
  {% if proforma.statut == "SOUMISE" %}
    <p class="mt-4 rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800">En attente de validation par la finance. Le devis n'est plus modifiable.</p>
  {% endif %}
  {% if proforma.statut == "EN_ATTENTE_DIRECTION" %}
    <p class="mt-4 rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800">Validé par la finance ; en attente de validation par la direction (montant au-delà du seuil).</p>
  {% endif %}

  {% if peut_valider_finances or peut_valider_direction %}
    <section class="mt-4 rounded-xl border border-marque-300 bg-marque-50/40 p-5" aria-labelledby="titre-validation">
      <h2 id="titre-validation" class="text-base font-semibold text-slate-900">Votre validation</h2>
      <p class="mt-1 text-sm text-slate-700">
        {% if peut_valider_finances %}La validation attribue le numéro si le montant reste sous le seuil, sinon transmet le devis à la direction.{% else %}La validation attribue le numéro et rend le devis prêt à être envoyé au client.{% endif %}
      </p>
      <div class="mt-4 flex flex-wrap items-start gap-4">
        <form method="post" action="{% if peut_valider_finances %}{% url 'billing:proforma_valider_finances' proforma.pk %}{% else %}{% url 'billing:proforma_valider_direction' proforma.pk %}{% endif %}">{% csrf_token %}
          <button type="submit" class="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 focus-visible:ring-offset-2"><i class="fa-solid fa-check mr-1" aria-hidden="true"></i> Valider</button>
        </form>
        <form method="post" action="{% url 'billing:proforma_contre_proposer' proforma.pk %}" class="flex-1 min-w-[16rem]">{% csrf_token %}
          <label for="motif-contre-proposition" class="block text-sm font-medium text-slate-800">Motif de la contre-proposition <span class="text-red-700" aria-hidden="true">*</span></label>
          <textarea id="motif-contre-proposition" name="motif" rows="2" required class="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30"></textarea>
          <button type="submit" class="mt-2 rounded-lg border border-red-300 bg-white px-4 py-2 text-sm font-semibold text-red-800 hover:bg-red-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-700 focus-visible:ring-offset-2">Contre-proposer</button>
        </form>
      </div>
    </section>
  {% endif %}

  <div class="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
    <div class="space-y-6 xl:col-span-2">
      <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-devis">
        <div class="flex items-center justify-between">
          <h2 id="titre-devis" class="text-base font-semibold text-slate-900">Détail du devis</h2>
          {% if peut_modifier %}
            <a href="{% url 'billing:proforma_modifier' proforma.pk %}" class="text-sm font-medium text-marque-700 underline-offset-2 hover:underline">Modifier</a>
          {% endif %}
        </div>
        <dl class="mt-3 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
          <div><dt class="text-slate-600">Nature de la marchandise</dt><dd class="font-medium text-slate-900">{{ proforma.nature_marchandise }}</dd></div>
          <div><dt class="text-slate-600">Poids</dt><dd class="font-medium text-slate-900">{{ proforma.poids_t|floatformat:"-2" }} t</dd></div>
          <div><dt class="text-slate-600">Départ souhaité</dt><dd class="font-medium text-slate-900">{{ proforma.date_depart_souhaitee|date:"d/m/Y"|default:"—" }}</dd></div>
        </dl>
        <dl class="mt-4 space-y-1 border-t border-slate-100 pt-3 text-sm sm:ml-auto sm:max-w-xs">
          <div class="flex justify-between"><dt class="text-slate-600">Prix convenu HT</dt><dd class="font-medium text-slate-900">{{ proforma.montant_ht|floatformat:0|intcomma }} FCFA</dd></div>
          <div class="flex justify-between"><dt class="text-slate-600">TVA {% if proforma.taux_tva == 0 %}(exonéré : {{ proforma.get_motif_exoneration_display }}){% else %}({{ proforma.taux_tva|floatformat:"-2" }} %){% endif %}</dt><dd class="font-medium text-slate-900">{{ proforma.montant_tva|floatformat:0|intcomma }} FCFA</dd></div>
          <div class="flex justify-between border-t border-slate-100 pt-1"><dt class="font-semibold text-slate-900">Total TTC</dt><dd class="text-lg font-bold text-slate-900">{{ proforma.montant_ttc|floatformat:0|intcomma }} FCFA</dd></div>
        </dl>
      </section>

      {% if historique %}
        <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-historique">
          <h2 id="titre-historique" class="text-base font-semibold text-slate-900">Historique</h2>
          <ul class="mt-3 space-y-2 text-sm">
            {% for entree in historique %}
              <li class="flex flex-wrap items-baseline justify-between gap-2 border-b border-slate-100 pb-2">
                <span class="text-slate-800">{{ entree.get_action_display }}{% if entree.nouvelle_valeur %} — {{ entree.nouvelle_valeur|join:", " }}{% endif %}</span>
                <span class="whitespace-nowrap text-xs text-slate-500">{{ entree.utilisateur_nom|default:"—" }} · {{ entree.date_heure|date:"d/m/Y à H:i" }}</span>
              </li>
            {% endfor %}
          </ul>
        </section>
      {% endif %}
    </div>

    <div class="space-y-6 xl:col-span-1">
      {% if peut_soumettre %}
        <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-envoi">
          <h2 id="titre-envoi" class="text-base font-semibold text-slate-900">Envoi</h2>
          <p class="mt-1 text-sm text-slate-700">Une fois soumis, le devis ne se modifie plus : la finance le valide ou le conteste.</p>
          <form method="post" action="{% url 'billing:proforma_soumettre' proforma.pk %}" class="mt-3">{% csrf_token %}
            <button type="submit" class="w-full rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Soumettre à la finance</button>
          </form>
          {% if peut_abandonner %}
            <form method="post" action="{% url 'billing:proforma_abandonner' proforma.pk %}" class="mt-3" data-confirm="Abandonner ce devis ?">{% csrf_token %}
              <button type="submit" class="w-full rounded-lg border border-red-300 bg-white px-4 py-2 text-sm font-semibold text-red-800 hover:bg-red-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-700 focus-visible:ring-offset-2">Abandonner le devis</button>
            </form>
          {% endif %}
        </section>
      {% endif %}

      {% if peut_creer_mission %}
        <section class="rounded-xl border border-emerald-300 bg-emerald-50/40 p-5" aria-labelledby="titre-mission">
          <h2 id="titre-mission" class="text-base font-semibold text-slate-900">Créer la mission</h2>
          <p class="mt-1 text-sm text-slate-700">Le client a accepté : le trajet, la marchandise, le poids et le prix sont repris tels quels dans une nouvelle mission.</p>
          <form method="post" action="{% url 'billing:proforma_creer_mission' proforma.pk %}" class="mt-3">{% csrf_token %}
            <button type="submit" class="w-full rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 focus-visible:ring-offset-2">Créer la mission</button>
          </form>
        </section>
      {% endif %}
      {% if proforma.statut == "CONVERTIE" and proforma.mission_creee %}
        <section class="rounded-xl border border-slate-200 bg-white p-5 text-sm shadow-sm">
          <h2 class="text-base font-semibold text-slate-900">Mission créée</h2>
          <p class="mt-2"><a href="{% url 'missions:detail' proforma.mission_creee.pk %}" class="font-medium text-marque-700 underline-offset-2 hover:underline">{{ proforma.mission_creee.numero }}</a></p>
        </section>
      {% endif %}

      {% if peut_envoyer_client %}
        <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-client">
          <h2 id="titre-client" class="text-base font-semibold text-slate-900">Envoi au client</h2>
          <p class="mt-1 text-sm text-slate-700">Le devis est validé : la validité de 30 jours démarre à l'envoi.</p>
          <form method="post" action="{% url 'billing:proforma_envoyer_client' proforma.pk %}" class="mt-3">{% csrf_token %}
            <button type="submit" class="w-full rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Envoyer au client</button>
          </form>
        </section>
      {% endif %}

      {% if form_decision_client %}
        <section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-decision">
          <h2 id="titre-decision" class="text-base font-semibold text-slate-900">Décision du client</h2>
          <form method="post" action="{% url 'billing:proforma_decision_client' proforma.pk %}" class="mt-3 space-y-3" x-data="{ decision: '' }">{% csrf_token %}
            <div class="space-y-2">
              {% for valeur, libelle in form_decision_client.decision.field.choices %}
                <label class="flex items-center gap-2 text-sm text-slate-800">
                  <input type="radio" name="decision" value="{{ valeur }}" x-model="decision" required class="h-4 w-4 border-slate-400 text-marque-700 focus:ring-marque-600"> {{ libelle }}
                </label>
              {% endfor %}
            </div>
            <div x-show="decision === 'REFUSEE'" x-cloak>
              <label for="motif-decision" class="block text-sm font-medium text-slate-800">Motif du refus</label>
              <textarea id="motif-decision" name="motif" rows="2" class="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30"></textarea>
            </div>
            <button type="submit" class="w-full rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Enregistrer la décision</button>
          </form>
        </section>
      {% endif %}

      <section class="rounded-xl border border-slate-200 bg-white p-5 text-sm shadow-sm">
        <h2 class="text-base font-semibold text-slate-900">Suivi</h2>
        <p class="mt-2 text-slate-700">Préparé par {{ proforma.cree_par|default:"—" }}.
          {% if proforma.valide_par_finances %}<br>Validé par la finance : {{ proforma.valide_par_finances }} le {{ proforma.date_validation_finances|date:"d/m/Y à H:i" }}.{% endif %}
          {% if proforma.valide_par_direction %}<br>Validé par la direction : {{ proforma.valide_par_direction }} le {{ proforma.date_validation_direction|date:"d/m/Y à H:i" }}.{% endif %}
          {% if proforma.date_envoi %}<br>Envoyé au client le {{ proforma.date_envoi|date:"d/m/Y" }}, valable jusqu'au {{ proforma.date_validite|date:"d/m/Y" }}.{% endif %}
        </p>
      </section>
    </div>
  </div>
</div>
{% endblock %}
```

#### `apps/billing/templates/billing/proforma_form.html`

*41 lignes*

```django
{% extends "base.html" %}
{% block titre %}Nouveau devis{% endblock %}
{% block entete %}Devis{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-3xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'billing:proformas' %}" class="underline-offset-2 hover:underline">Devis</a>
    <span aria-hidden="true">/</span> Nouveau devis
  </nav>
  <h1 class="mt-2 text-2xl font-bold text-slate-900">Nouveau devis</h1>
  <p class="mt-1 text-sm text-slate-600">
    Le trajet, la marchandise et le prix seront repris tels quels dans la mission si le client accepte.
    La TVA reprend celle du client ; vous pourrez l'ajuster avant de soumettre le devis à la finance.
  </p>

  <form method="post" novalidate class="mt-6 space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
    {% csrf_token %}
    {% if form.non_field_errors %}
      <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">{% for erreur in form.non_field_errors %}<p>{{ erreur }}</p>{% endfor %}</div>
    {% endif %}
    {% include "components/_champ.html" with champ=form.client %}
    <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {% include "components/_champ.html" with champ=form.lieu_chargement %}
      {% include "components/_champ.html" with champ=form.lieu_livraison %}
    </div>
    <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {% include "components/_champ.html" with champ=form.nature_marchandise %}
      {% include "components/_champ.html" with champ=form.poids_t %}
    </div>
    <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {% include "components/_champ.html" with champ=form.date_depart_souhaitee %}
      {% include "components/_champ.html" with champ=form.prix_convenu %}
    </div>
    <div class="flex items-center justify-end gap-3 border-t border-slate-100 pt-5">
      <a href="{% url 'billing:proformas' %}" class="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">Annuler</a>
      <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Créer le devis</button>
    </div>
  </form>
</div>
{% endblock %}
```

#### `apps/billing/templates/billing/proforma_list.html`

*72 lignes*

```django
{% extends "base.html" %}
{% load ui humanize %}
{% block titre %}Devis{% endblock %}
{% block entete %}Devis{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-7xl">
  <div class="flex flex-wrap items-start justify-between gap-3">
    <div>
      <h1 class="text-2xl font-bold text-slate-900">Devis</h1>
      <p class="mt-1 text-sm text-slate-600">{{ paginator.count|default:0 }} devis</p>
    </div>
    <div class="flex flex-wrap items-center gap-2">
      <a href="{% url 'billing:proformas_imprimer' %}?{{ request.GET.urlencode }}" target="_blank" rel="noopener"
         class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
        <i class="fa-solid fa-print" aria-hidden="true"></i> Imprimer
      </a>
      {% if peut_saisir %}
        <a href="{% url 'billing:proforma_nouveau' %}"
           class="inline-flex items-center gap-2 rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">
          <i class="fa-solid fa-plus" aria-hidden="true"></i> Nouveau devis
        </a>
      {% endif %}
    </div>
  </div>

  <form method="get" class="mt-5 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
    <div class="min-w-[14rem] flex-1">{% include "components/_champ.html" with champ=filtre.q %}</div>
    <div class="min-w-[10rem]">{% include "components/_champ.html" with champ=filtre.statut %}</div>
    <div class="min-w-[12rem]">{% include "components/_champ.html" with champ=filtre.client %}</div>
    <button type="submit" class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2">Filtrer</button>
    {% if filtres_actifs %}<a href="{% url 'billing:proformas' %}" class="px-2 py-2 text-sm font-medium text-slate-700 underline hover:text-slate-900">Réinitialiser</a>{% endif %}
  </form>

  {% if proformas %}
    <div class="mt-5 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <caption class="sr-only">Liste des devis</caption>
        <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr>
            <th scope="col" class="px-4 py-3">Devis</th>
            <th scope="col" class="px-4 py-3">Client</th>
            <th scope="col" class="px-4 py-3">Trajet</th>
            <th scope="col" class="px-4 py-3 text-right">TTC</th>
            <th scope="col" class="px-4 py-3">Statut</th>
            <th scope="col" class="hidden px-4 py-3 xl:table-cell">Valable jusqu'au</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          {% for p in proformas %}
            <tr class="hover:bg-slate-50">
              <td class="whitespace-nowrap px-4 py-3 font-semibold"><a href="{% url 'billing:proforma' p.pk %}" class="text-marque-700 underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">{{ p.numero|default:"Brouillon" }}</a></td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ p.client.raison_sociale }}</td>
              <td class="px-4 py-3 text-slate-700">{{ p.lieu_chargement }} → {{ p.lieu_livraison }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right text-slate-900">{{ p.montant_ttc|floatformat:0|intcomma }}</td>
              <td class="whitespace-nowrap px-4 py-3">{% badge p.statut p.get_statut_display %}</td>
              <td class="hidden whitespace-nowrap px-4 py-3 text-slate-700 xl:table-cell">{{ p.date_validite|date:"d/m/Y"|default:"—" }}</td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% include "components/_pagination.html" %}
  {% else %}
    <div class="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
      <span class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-600"><i class="fa-solid fa-file-signature" aria-hidden="true"></i></span>
      <p class="mt-3 font-semibold text-slate-900">Aucun devis</p>
      <p class="mt-1 text-sm text-slate-600">{% if filtres_actifs %}Aucun résultat pour ces critères.{% else %}Préparez un devis pour un client avant de créer sa mission.{% endif %}</p>
    </div>
  {% endif %}
</div>
{% endblock %}
```

#### `apps/billing/templates/billing/proforma_modifier.html`

*51 lignes*

```django
{% extends "base.html" %}
{% block titre %}Modifier le devis{% endblock %}
{% block entete %}Devis{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-3xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'billing:proformas' %}" class="underline-offset-2 hover:underline">Devis</a>
    <span aria-hidden="true">/</span>
    <a href="{% url 'billing:proforma' proforma.pk %}" class="underline-offset-2 hover:underline">{{ proforma.numero|default:"Brouillon" }}</a>
    <span aria-hidden="true">/</span> Modifier
  </nav>
  <h1 class="mt-2 text-2xl font-bold text-slate-900">Modifier le devis</h1>
  {% if proforma.motif_contre_proposition %}
    <div role="alert" class="mt-4 rounded-lg border border-amber-400 bg-amber-50 px-4 py-3 text-sm text-amber-950">
      <p class="font-semibold">Contre-proposition</p>
      <p class="mt-1 whitespace-pre-line">{{ proforma.motif_contre_proposition }}</p>
    </div>
  {% endif %}

  <form method="post" novalidate class="mt-6 space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm" x-data="{ tva: '{{ form.taux_tva.value|default_if_none:'' }}' }">
    {% csrf_token %}
    {% if form.non_field_errors %}
      <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">{% for erreur in form.non_field_errors %}<p>{{ erreur }}</p>{% endfor %}</div>
    {% endif %}
    <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {% include "components/_champ.html" with champ=form.lieu_chargement %}
      {% include "components/_champ.html" with champ=form.lieu_livraison %}
    </div>
    <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {% include "components/_champ.html" with champ=form.nature_marchandise %}
      {% include "components/_champ.html" with champ=form.poids_t %}
    </div>
    <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {% include "components/_champ.html" with champ=form.date_depart_souhaitee %}
      {% include "components/_champ.html" with champ=form.prix_convenu %}
    </div>
    <div>
      <label for="{{ form.taux_tva.id_for_label }}" class="block text-sm font-medium text-slate-800">{{ form.taux_tva.label }}</label>
      <input type="number" name="taux_tva" id="{{ form.taux_tva.id_for_label }}" step="0.01" min="0" max="100" required
             x-model="tva" value="{{ form.taux_tva.value|default_if_none:'' }}"
             class="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-marque-600 focus:outline-none focus:ring-2 focus:ring-marque-600/30">
    </div>
    <div x-show="parseFloat(tva) === 0" x-cloak>{% include "components/_champ.html" with champ=form.motif_exoneration %}</div>
    <div class="flex items-center justify-end gap-3 border-t border-slate-100 pt-5">
      <a href="{% url 'billing:proforma' proforma.pk %}" class="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">Annuler</a>
      <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Enregistrer</button>
    </div>
  </form>
</div>
{% endblock %}
```

#### `apps/billing/templates/billing/proforma_print.html`

*49 lignes*

```django
{% load humanize static %}<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ proforma.numero|default:"Devis" }} · {{ proforma.client.raison_sociale }}</title>
  {% include "rapports/_style_impression.html" %}
  <style>
    .totaux { margin-left: auto; width: 320px; margin-top: 1rem; }
    .totaux div { display: flex; justify-content: space-between; padding: .25rem 0; }
    .total { border-top: 2px solid #111; font-weight: bold; font-size: 1.1rem; }
    .filigrane { color: #b91c1c; border: 2px solid #b91c1c; display: inline-block; padding: .2rem .8rem; font-weight: bold; margin-top: .5rem; }
  </style>
</head>
<body>
  {% include "rapports/_entete_impression.html" %}
  <div style="text-align:right">
    {% if proforma.date_envoi %}<div class="petit">Envoyé le {{ proforma.date_envoi|date:"d/m/Y" }} — Valable jusqu'au {{ proforma.date_validite|date:"d/m/Y" }}</div>{% endif %}
    {% if not proforma.numero %}<div class="filigrane">NON VALIDÉ</div>{% endif %}
  </div>

  <p style="margin-top:1.5rem">
    <strong>{{ proforma.client.raison_sociale }}</strong><br>
    <span class="petit">{{ proforma.client.adresse|linebreaksbr }}<br>NCC / NIF {{ proforma.client.ncc_nif }}</span>
  </p>

  <table>
    <thead><tr><th>Désignation</th><th class="droite">Poids</th><th class="droite">Montant HT</th></tr></thead>
    <tbody>
      <tr>
        <td>Transport : {{ proforma.lieu_chargement }} → {{ proforma.lieu_livraison }} ({{ proforma.nature_marchandise }})</td>
        <td class="droite">{{ proforma.poids_t|floatformat:"-2" }} t</td>
        <td class="droite">{{ proforma.montant_ht|floatformat:0|intcomma }}</td>
      </tr>
    </tbody>
  </table>

  <div class="totaux">
    <div><span>Total HT</span><span>{{ proforma.montant_ht|floatformat:0|intcomma }} FCFA</span></div>
    <div><span>TVA {% if proforma.taux_tva == 0 %}(exonérée : {{ proforma.get_motif_exoneration_display }}){% else %}({{ proforma.taux_tva|floatformat:"-2" }} %){% endif %}</span><span>{{ proforma.montant_tva|floatformat:0|intcomma }} FCFA</span></div>
    <div class="total"><span>Total TTC</span><span>{{ proforma.montant_ttc|floatformat:0|intcomma }} FCFA</span></div>
  </div>

  {% if proforma.date_depart_souhaitee %}<p class="petit" style="margin-top:1.5rem">Départ souhaité : {{ proforma.date_depart_souhaitee|date:"d/m/Y" }}</p>{% endif %}
  <p class="petit">Ce devis est valable 30 jours à compter de son envoi.</p>
  {% include "rapports/_pied_impression.html" %}
  <script src="{% static 'js/app.js' %}" defer></script>
</body>
</html>
```

#### `apps/finance/templates/finance/demande_detail.html`

*113 lignes*

```django
{% extends "base.html" %}
{% load ui humanize %}
{% block titre %}{{ demande.numero }}{% endblock %}
{% block entete %}Demandes de dépense{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-4xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'finance:demandes' %}" class="underline-offset-2 hover:underline">Demandes de dépense</a>
    <span aria-hidden="true">/</span> {{ demande.numero }}
  </nav>

  <div class="mt-2 flex flex-wrap items-center gap-3">
    <h1 class="text-2xl font-bold text-slate-900">{{ demande.numero }}</h1>
    {% badge demande.statut demande.get_statut_display %}
  </div>
  <p class="mt-1 text-sm text-slate-600">
    {{ demande.get_categorie_display }}{% if demande.vehicule %} · {{ demande.vehicule.immatriculation }}{% endif %}
    · {{ demande.get_origine_display }}
  </p>

  {% if demande.statut == "REFUSEE" and demande.motif_refus %}
    <div role="alert" class="mt-4 rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">
      <p class="font-semibold">Refusée par la direction</p>
      <p class="mt-1 whitespace-pre-line">{{ demande.motif_refus }}</p>
    </div>
  {% endif %}

  <section class="mt-5 rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-demande">
    <h2 id="titre-demande" class="text-base font-semibold text-slate-900">Détail de la demande</h2>
    <dl class="mt-3 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
      <div><dt class="text-slate-600">Montant estimé</dt><dd class="font-medium text-slate-900">{{ demande.montant_estime|floatformat:0|intcomma }} FCFA</dd></div>
      {% if demande.fournisseur %}<div><dt class="text-slate-600">Fournisseur</dt><dd class="font-medium text-slate-900">{{ demande.fournisseur }}</dd></div>{% endif %}
    </dl>
    <p class="mt-3 text-sm text-slate-700 whitespace-pre-line">{{ demande.motif }}</p>
    {% if demande.piece_jointe %}<a href="{{ demande.piece_jointe.url }}" target="_blank" rel="noopener" class="mt-2 inline-block text-sm font-medium text-marque-700 underline-offset-2 hover:underline">Voir la pièce jointe</a>{% endif %}
  </section>

  {% if form_decision %}
    <section class="mt-5 rounded-xl border border-marque-300 bg-marque-50/40 p-5" aria-labelledby="titre-decision" x-data="{ decision: '' }">
      <h2 id="titre-decision" class="text-base font-semibold text-slate-900">Votre décision</h2>
      <form method="post" action="{% url 'finance:demande_decider' demande.pk %}" class="mt-3 space-y-3">
        {% csrf_token %}
        <div class="flex gap-4">
          {% for valeur, libelle in form_decision.decision.field.choices %}
            <label class="flex items-center gap-2 text-sm text-slate-800">
              <input type="radio" name="decision" value="{{ valeur }}" x-model="decision" required class="h-4 w-4 border-slate-400 text-marque-700 focus:ring-marque-600"> {{ libelle }}
            </label>
          {% endfor %}
        </div>
        <div x-show="decision === 'VALIDER'" x-cloak>
          {% include "components/_champ.html" with champ=form_decision.montant_valide %}
        </div>
        <div x-show="decision === 'REFUSER'" x-cloak>
          {% include "components/_champ.html" with champ=form_decision.motif_refus %}
        </div>
        <button type="submit" class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700">Confirmer la décision</button>
      </form>
    </section>
  {% endif %}

  {% if ordre %}
    <section class="mt-5 rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-ordre">
      <div class="flex items-center justify-between gap-3">
        <h2 id="titre-ordre" class="text-base font-semibold text-slate-900">Ordre de décaissement {{ ordre.numero }}</h2>
        {% badge ordre.statut ordre.get_statut_display %}
      </div>
      <dl class="mt-3 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
        <div><dt class="text-slate-600">Montant validé</dt><dd class="font-medium text-slate-900">{{ ordre.montant_valide|floatformat:0|intcomma }} FCFA</dd></div>
        {% if ordre.montant_reel %}<div><dt class="text-slate-600">Montant réel {% if ordre.statut == "EN_ATTENTE_REVALIDATION" %}(tenté){% endif %}</dt><dd class="font-medium text-slate-900">{{ ordre.montant_reel|floatformat:0|intcomma }} FCFA</dd></div>{% endif %}
      </dl>

      {% if ordre.statut == "EN_ATTENTE_REVALIDATION" %}
        <p class="mt-3 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-900">
          Le montant réel dépasse de plus de 10 % le montant validé : l'exécution est bloquée jusqu'à revalidation.
        </p>
      {% endif %}

      {% if form_executer %}
        <form method="post" action="{% url 'finance:ordre_executer' ordre.pk %}" enctype="multipart/form-data" class="mt-4 space-y-3 rounded-lg bg-slate-50 p-4">
          {% csrf_token %}
          <h3 class="text-sm font-semibold text-slate-900">Exécuter</h3>
          <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {% include "components/_champ.html" with champ=form_executer.mode_paiement %}
            {% include "components/_champ.html" with champ=form_executer.montant_reel %}
          </div>
          {% include "components/_champ.html" with champ=form_executer.reference %}
          {% include "components/_champ.html" with champ=form_executer.justificatif %}
          <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700">Exécuter</button>
        </form>
      {% endif %}

      {% if form_revalider %}
        <form method="post" action="{% url 'finance:ordre_revalider' ordre.pk %}" class="mt-4 space-y-3 rounded-lg bg-slate-50 p-4">
          {% csrf_token %}
          <h3 class="text-sm font-semibold text-slate-900">Revalider le montant</h3>
          {% include "components/_champ.html" with champ=form_revalider.montant_valide %}
          <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700">Revalider</button>
        </form>
      {% endif %}
    </section>
  {% endif %}

  <section class="mt-5 rounded-xl border border-slate-200 bg-white p-5 text-sm shadow-sm">
    <h2 class="text-base font-semibold text-slate-900">Suivi</h2>
    <p class="mt-2 text-slate-700">
      {% if demande.demandeur %}Demandée par {{ demande.demandeur }}.{% else %}Ouverte automatiquement (dépassement d'enveloppe).{% endif %}
      {% if demande.valide_par %}<br>Décidée par {{ demande.valide_par }} le {{ demande.date_decision|date:"d/m/Y à H:i" }}.{% endif %}
      {% if ordre.execute_par %}<br>Exécuté par {{ ordre.execute_par }} le {{ ordre.date_execution|date:"d/m/Y à H:i" }}.{% endif %}
    </p>
  </section>
</div>
{% endblock %}
```

#### `apps/finance/templates/finance/demande_form.html`

*38 lignes*

```django
{% extends "base.html" %}
{% block titre %}Nouvelle demande de dépense{% endblock %}
{% block entete %}Demandes de dépense{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-2xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'finance:demandes' %}" class="underline-offset-2 hover:underline">Demandes de dépense</a>
    <span aria-hidden="true">/</span> Nouvelle demande
  </nav>
  <h1 class="mt-2 text-2xl font-bold text-slate-900">Nouvelle demande de dépense</h1>
  <p class="mt-1 text-sm text-slate-600">
    Pour un achat ou une réparation non routinière du parc auto. La direction valide avant tout
    engagement ; une fois validée, la finance exécute le paiement.
  </p>

  <form method="post" enctype="multipart/form-data" novalidate class="mt-6 space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
    {% csrf_token %}
    {% if form.non_field_errors %}
      <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">{% for erreur in form.non_field_errors %}<p>{{ erreur }}</p>{% endfor %}</div>
    {% endif %}
    <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {% include "components/_champ.html" with champ=form.categorie %}
      {% include "components/_champ.html" with champ=form.vehicule %}
    </div>
    <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {% include "components/_champ.html" with champ=form.montant_estime %}
      {% include "components/_champ.html" with champ=form.fournisseur %}
    </div>
    {% include "components/_champ.html" with champ=form.motif %}
    {% include "components/_champ.html" with champ=form.piece_jointe %}
    <div class="flex items-center justify-end gap-3 border-t border-slate-100 pt-5">
      <a href="{% url 'finance:demandes' %}" class="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">Annuler</a>
      <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2">Soumettre à la direction</button>
    </div>
  </form>
</div>
{% endblock %}
```

#### `apps/finance/templates/finance/demande_list.html`

*63 lignes*

```django
{% extends "base.html" %}
{% load ui humanize %}
{% block titre %}Demandes de dépense{% endblock %}
{% block entete %}Demandes de dépense{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-6xl">
  <div class="flex flex-wrap items-start justify-between gap-3">
    <div>
      <h1 class="text-2xl font-bold text-slate-900">Demandes de dépense</h1>
      <p class="mt-1 text-sm text-slate-600">{{ paginator.count|default:0 }} demande{{ paginator.count|pluralize }} — dépenses du parc auto pré-approuvées par la direction.</p>
    </div>
    <div class="flex flex-wrap items-center gap-2">
      {% if peut_definir_enveloppe %}
        <a href="{% url 'finance:enveloppes' %}" class="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50">
          <i class="fa-solid fa-gauge mr-1" aria-hidden="true"></i>Enveloppes mensuelles
        </a>
      {% endif %}
      {% if peut_soumettre %}
        <a href="{% url 'finance:demande_nouvelle' %}" class="inline-flex items-center gap-2 rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700">
          <i class="fa-solid fa-plus" aria-hidden="true"></i> Nouvelle demande
        </a>
      {% endif %}
    </div>
  </div>

  {% if demandes %}
    <div class="mt-5 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <caption class="sr-only">Liste des demandes de dépense</caption>
        <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr>
            <th scope="col" class="px-4 py-3">Demande</th>
            <th scope="col" class="px-4 py-3">Catégorie</th>
            <th scope="col" class="px-4 py-3">Camion</th>
            <th scope="col" class="px-4 py-3">Origine</th>
            <th scope="col" class="px-4 py-3 text-right">Montant estimé</th>
            <th scope="col" class="px-4 py-3">Statut</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          {% for d in demandes %}
            <tr class="hover:bg-slate-50">
              <td class="whitespace-nowrap px-4 py-3 font-semibold"><a href="{% url 'finance:demande' d.pk %}" class="text-marque-700 underline-offset-2 hover:underline">{{ d.numero }}</a></td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ d.get_categorie_display }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ d.vehicule.immatriculation|default:"—" }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ d.get_origine_display }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right text-slate-900">{{ d.montant_estime|floatformat:0|intcomma }}</td>
              <td class="whitespace-nowrap px-4 py-3">{% badge d.statut d.get_statut_display %}</td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% include "components/_pagination.html" %}
  {% else %}
    <div class="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
      <span class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-600"><i class="fa-solid fa-file-invoice" aria-hidden="true"></i></span>
      <p class="mt-3 font-semibold text-slate-900">Aucune demande</p>
    </div>
  {% endif %}
</div>
{% endblock %}
```

#### `apps/finance/templates/finance/enveloppe_list.html`

*65 lignes*

```django
{% extends "base.html" %}
{% load ui humanize %}
{% block titre %}Enveloppes de dépense{% endblock %}
{% block entete %}Demandes de dépense{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-4xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'finance:demandes' %}" class="underline-offset-2 hover:underline">Demandes de dépense</a>
    <span aria-hidden="true">/</span> Enveloppes mensuelles
  </nav>
  <h1 class="mt-2 text-2xl font-bold text-slate-900">Enveloppes mensuelles</h1>
  <p class="mt-1 text-sm text-slate-600">
    Tant que les dépenses automatiques du mois restent dans le plafond, elles se comptabilisent
    seules comme aujourd'hui. Le dépasser bloque la suivante et ouvre une demande à valider.
  </p>

  <form method="post" action="{% url 'finance:enveloppe_nouvelle' %}" class="mt-5 space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
    {% csrf_token %}
    <h2 class="text-sm font-semibold text-slate-900">Nouvelle enveloppe (ou mise à jour du même mois)</h2>
    <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {% include "components/_champ.html" with champ=form.categorie %}
      {% include "components/_champ.html" with champ=form.vehicule %}
    </div>
    <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
      {% include "components/_champ.html" with champ=form.annee %}
      {% include "components/_champ.html" with champ=form.mois %}
      {% include "components/_champ.html" with champ=form.montant_plafond %}
    </div>
    <button type="submit" class="rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700">Enregistrer</button>
  </form>

  {% if enveloppes %}
    <div class="mt-5 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table class="min-w-full divide-y divide-slate-200 text-sm">
        <caption class="sr-only">Liste des enveloppes</caption>
        <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr>
            <th scope="col" class="px-4 py-3">Mois</th>
            <th scope="col" class="px-4 py-3">Catégorie</th>
            <th scope="col" class="px-4 py-3">Camion</th>
            <th scope="col" class="px-4 py-3 text-right">Plafond</th>
            <th scope="col" class="px-4 py-3">Approuvée par</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          {% for e in enveloppes %}
            <tr class="hover:bg-slate-50">
              <td class="whitespace-nowrap px-4 py-3 text-slate-900">{{ e.mois|stringformat:"02d" }}/{{ e.annee }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ e.get_categorie_display }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ e.vehicule.immatriculation|default:"Tous les camions" }}</td>
              <td class="whitespace-nowrap px-4 py-3 text-right text-slate-900">{{ e.montant_plafond|floatformat:0|intcomma }} FCFA</td>
              <td class="whitespace-nowrap px-4 py-3 text-slate-700">{{ e.valide_par|default:"—" }}</td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  {% else %}
    <div class="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
      <p class="text-sm text-slate-600">Aucune enveloppe définie : les dépenses automatiques du parc auto restent illimitées.</p>
    </div>
  {% endif %}
</div>
{% endblock %}
```

#### `apps/finance/templates/finance/tresorerie_print.html`

*54 lignes*

```django
{% load static humanize %}<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Trésorerie · {{ entreprise.nom }}</title>
  {% include "rapports/_style_impression.html" %}
</head>
<body>
  {% include "rapports/_entete_impression.html" %}

  <div class="cartouche">
    <div><dt>Solde total</dt><dd>{{ solde_total|floatformat:0|intcomma }} FCFA</dd></div>
    {% for ligne in soldes_par_compte %}
      <div><dt>{{ ligne.libelle }}</dt><dd>{{ ligne.montant|floatformat:0|intcomma }} FCFA</dd></div>
    {% endfor %}
  </div>

  <h2>Synthèse de la période ({{ periode_debut|date:"d/m/Y" }} au {{ periode_fin|date:"d/m/Y" }})</h2>
  <div class="cartouche">
    <div><dt>Entrées</dt><dd>{{ synthese.entrees|floatformat:0|intcomma }} FCFA</dd></div>
    <div><dt>Sorties</dt><dd>{{ synthese.sorties|floatformat:0|intcomma }} FCFA</dd></div>
    <div><dt>Variation</dt><dd>{{ synthese.variation|floatformat:0|intcomma }} FCFA</dd></div>
  </div>

  <h2>Journal</h2>
  <p class="petit">
    {{ nombre }} mouvement{{ nombre|pluralize }}{% if tronque %} — limité aux {{ nombre }} plus récents ; affinez les filtres pour voir le reste{% endif %}
  </p>
  {% if journal %}
    <table>
      <thead><tr><th>Date</th><th>Libellé</th><th>Compte</th><th class="droite">Entrée</th><th class="droite">Sortie</th><th>Mode</th><th>Référence</th></tr></thead>
      <tbody>
        {% for m in journal %}
          <tr>
            <td>{{ m.date|date:"d/m/Y" }}</td>
            <td>{{ m.libelle }}</td>
            <td>{{ m.compte_libelle }}</td>
            <td class="droite">{% if m.sens == "ENTREE" %}{{ m.montant|floatformat:0|intcomma }}{% endif %}</td>
            <td class="droite">{% if m.sens == "SORTIE" %}{{ m.montant|floatformat:0|intcomma }}{% endif %}</td>
            <td>{{ m.mode_libelle }}</td>
            <td>{{ m.reference|default:"—" }}</td>
          </tr>
        {% endfor %}
      </tbody>
    </table>
  {% else %}
    <p>Aucun mouvement pour ces critères.</p>
  {% endif %}

  {% include "rapports/_pied_impression.html" %}
  <script src="{% static 'js/app.js' %}" defer></script>
</body>
</html>
```

#### `apps/finance/templates/finance/versement_confirmer.html`

*54 lignes*

```django
{% extends "base.html" %}
{% load humanize %}
{% block titre %}Confirmer le versement · {{ facture.numero }}{% endblock %}
{% block entete %}Trésorerie{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-3xl">
  <nav aria-label="Fil d'Ariane" class="text-sm text-slate-600">
    <a href="{% url 'finance:tresorerie' %}" class="underline-offset-2 hover:underline">Trésorerie</a>
    <span aria-hidden="true">/</span> Confirmer un versement
  </nav>
  <h1 class="mt-2 text-2xl font-bold text-slate-900">Confirmer le versement</h1>
  <p class="mt-1 text-sm text-slate-600">
    Vérifiez que l'argent est bien arrivé (relevé bancaire, caisse, mobile money) avant de confirmer.
    La confirmation ajoute une <strong>entrée</strong> à la trésorerie, sur le compte du mode de paiement choisi.
  </p>

  <section class="mt-6 rounded-xl border {% if echue %}border-red-300{% else %}border-slate-200{% endif %} bg-white p-5 shadow-sm" aria-labelledby="titre-facture">
    <h2 id="titre-facture" class="text-base font-semibold text-slate-900">
      <a href="{% url 'billing:facture' facture.pk %}" class="text-marque-700 underline-offset-2 hover:underline">Facture {{ facture.numero }}</a>
    </h2>
    <dl class="mt-4 grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
      <div><dt class="text-slate-600">Client</dt><dd class="mt-0.5 font-medium text-slate-900">{{ facture.client.raison_sociale }}</dd></div>
      <div><dt class="text-slate-600">Mission</dt><dd class="mt-0.5 font-medium text-slate-900">{{ facture.mission.numero }}</dd></div>
      <div><dt class="text-slate-600">Total TTC</dt><dd class="mt-0.5 font-medium text-slate-900">{{ facture.montant_ttc|floatformat:0|intcomma }} FCFA</dd></div>
      <div><dt class="text-slate-600">Déjà réglé</dt><dd class="mt-0.5 font-medium text-slate-900">{{ regle|floatformat:0|intcomma }} FCFA</dd></div>
      <div><dt class="text-slate-600">Reste à recouvrer</dt><dd class="mt-0.5 text-lg font-bold text-slate-900">{{ facture.reste|floatformat:0|intcomma }} FCFA</dd></div>
      <div><dt class="text-slate-600">Échéance</dt><dd class="mt-0.5 font-medium {% if echue %}text-red-800{% else %}text-slate-900{% endif %}">{{ facture.date_echeance|date:"d/m/Y"|default:"—" }}{% if echue %} (échue){% endif %}</dd></div>
    </dl>
  </section>

  <form method="post" novalidate class="mt-6 space-y-5 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
    {% csrf_token %}
    {% if form.non_field_errors %}
      <div role="alert" class="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">
        {% for erreur in form.non_field_errors %}<p>{{ erreur }}</p>{% endfor %}
      </div>
    {% endif %}
    <div class="grid grid-cols-1 gap-5 sm:grid-cols-2">
      {% include "components/_champ.html" with champ=form.montant %}
      {% include "components/_champ.html" with champ=form.date_reglement %}
      {% include "components/_champ.html" with champ=form.mode %}
      {% include "components/_champ.html" with champ=form.reference %}
    </div>
    <p class="text-xs text-slate-600">Un versement partiel (acompte) est possible : la facture reste à recouvrer pour le solde.</p>
    <div class="flex items-center justify-end gap-3 border-t border-slate-100 pt-5">
      <a href="{% url 'finance:tresorerie' %}" class="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">Annuler</a>
      <button type="submit" class="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-emerald-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 focus-visible:ring-offset-2">
        <i class="fa-solid fa-circle-check mr-1" aria-hidden="true"></i> Confirmer le versement
      </button>
    </div>
  </form>
</div>
{% endblock %}
```

#### `apps/accounts/tests/test_web.py`

*235 lignes* — Connexion, accueil, menu par rôle et garde d'accès.

```python
"""Connexion, accueil, menu par rôle et garde d'accès."""

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from apps.accounts import navigation
from apps.accounts.models import Role
from apps.audit.models import ActionChoices, AuditLog, StatutChoices

from .factories import UserFactory

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "Test-Passw0rd!"


def _connecte(client, role):
    utilisateur = UserFactory(role=role)
    client.force_login(utilisateur)
    return utilisateur


# --- connexion / déconnexion ---


def test_la_page_de_connexion_s_affiche(client):
    reponse = client.get(reverse("accounts:login"))

    assert reponse.status_code == 200
    assert "Se connecter" in reponse.content.decode()


def test_connexion_reussie_redirige_vers_l_accueil_et_est_tracee(client):
    utilisateur = UserFactory(username="awa", role=Role.DIRECTION)

    reponse = client.post(
        reverse("accounts:login"), {"username": "awa", "password": MOT_DE_PASSE}
    )

    assert reponse.status_code == 302
    assert reponse.url == reverse("home")
    assert AuditLog.objects.filter(
        action=ActionChoices.LOGIN, utilisateur=utilisateur, statut=StatutChoices.SUCCESS
    ).exists()


def test_connexion_avec_un_mauvais_mot_de_passe_affiche_une_erreur_et_est_tracee(client):
    UserFactory(username="awa")

    reponse = client.post(
        reverse("accounts:login"), {"username": "awa", "password": "faux"}
    )

    assert reponse.status_code == 200
    assert reponse.context["form"].non_field_errors()
    assert AuditLog.objects.filter(
        action=ActionChoices.LOGIN, statut=StatutChoices.FAILED
    ).exists()


def test_un_utilisateur_connecte_qui_ouvre_la_connexion_va_a_l_accueil(client):
    _connecte(client, Role.RH)

    reponse = client.get(reverse("accounts:login"))

    assert reponse.status_code == 302
    assert reponse.url == reverse("home")


def test_deconnexion_par_post_ferme_la_session_et_est_tracee(client):
    utilisateur = _connecte(client, Role.RH)

    reponse = client.post(reverse("accounts:logout"))

    assert reponse.status_code == 302
    assert reponse.url == reverse("accounts:login")
    assert client.get(reverse("home")).status_code == 302
    assert AuditLog.objects.filter(
        action=ActionChoices.LOGOUT, utilisateur=utilisateur
    ).exists()


def test_la_deconnexion_refuse_le_get(client):
    _connecte(client, Role.RH)

    assert client.get(reverse("accounts:logout")).status_code == 405


def test_la_deconnexion_est_protegee_par_csrf():
    client = Client(enforce_csrf_checks=True)
    client.force_login(UserFactory())

    assert client.post(reverse("accounts:logout")).status_code == 403


def test_la_session_expire_apres_30_minutes_d_inactivite():
    assert settings.SESSION_COOKIE_AGE == 30 * 60
    assert settings.SESSION_SAVE_EVERY_REQUEST is True


# --- accueil ---


def test_l_accueil_exige_une_connexion_et_conserve_la_destination(client):
    reponse = client.get(reverse("home"))

    assert reponse.status_code == 302
    assert reponse.url == f"{reverse('accounts:login')}?next=/"


def test_l_accueil_salue_l_utilisateur(client):
    utilisateur = UserFactory(role=Role.DIRECTION, first_name="Awa")
    client.force_login(utilisateur)

    contenu = client.get(reverse("home")).content.decode()

    assert "Bonjour Awa" in contenu
    assert "Direction" in contenu


def test_le_menu_depend_du_role(client):
    _connecte(client, Role.DIRECTION)
    assert 'href="/missions/"' in client.get(reverse("home")).content.decode()

    finances = Client()
    _connecte(finances, Role.FINANCES)  # seuls les congés sont ouverts à ce rôle pour l'instant
    contenu = finances.get(reverse("home")).content.decode()
    assert 'href="/missions/"' not in contenu
    assert 'href="/rh/conges/"' in contenu
    assert "Aucun écran n" not in contenu

    chauffeur = Client()
    _connecte(chauffeur, Role.CHAUFFEUR)  # passe par l'espace mobile : aucun écran web
    assert "Aucun écran n" in chauffeur.get(reverse("home")).content.decode()


def test_un_chauffeur_est_renvoye_vers_l_espace_mobile(client):
    _connecte(client, Role.CHAUFFEUR)

    assert "espace mobile" in client.get(reverse("home")).content.decode()


def test_un_superutilisateur_sans_role_agit_en_admin(client):
    admin = UserFactory(role="", is_superuser=True, is_staff=True)
    client.force_login(admin)

    assert admin.role_effectif == Role.ADMIN
    assert client.get(reverse("missions:liste")).status_code == 200


# --- pages d'erreur ---


def test_un_role_non_autorise_recoit_la_page_403(client):
    _connecte(client, Role.FINANCES)

    reponse = client.get(reverse("missions:liste"))

    assert reponse.status_code == 403
    assert "Accès refusé" in reponse.content.decode()


def test_une_page_inexistante_affiche_la_page_404(client, settings):
    settings.DEBUG = False
    settings.ALLOWED_HOSTS = ["testserver"]
    _connecte(client, Role.DIRECTION)

    reponse = client.get("/n-existe-pas/")

    assert reponse.status_code == 404
    assert "Page introuvable" in reponse.content.decode()


# --- navigation ---


def test_entrees_pour_filtre_par_role_trie_et_marque_l_entree_active(monkeypatch):
    accueil = navigation.EntreeMenu("Accueil", "home", "fa-house", None, ordre=0)
    reserve_rh = navigation.EntreeMenu(
        "Réservé RH", "missions:liste", "fa-flask", frozenset({Role.RH}), ordre=5
    )
    monkeypatch.setattr(
        navigation, "_ENTREES", {"missions:liste": reserve_rh, "home": accueil}
    )

    rh = navigation.entrees_pour(Role.RH, "/missions/")
    finances = navigation.entrees_pour(Role.FINANCES, "/missions/")

    assert [e["libelle"] for e in rh] == ["Accueil", "Réservé RH"]
    assert [e["actif"] for e in rh] == [False, True]
    assert [e["libelle"] for e in finances] == ["Accueil"]


def test_l_accueil_n_est_actif_que_sur_la_racine(monkeypatch):
    accueil = navigation.EntreeMenu("Accueil", "home", "fa-house", None, ordre=0)
    monkeypatch.setattr(navigation, "_ENTREES", {"home": accueil})

    assert navigation.entrees_pour(Role.RH, "/")[0]["actif"] is True
    assert navigation.entrees_pour(Role.RH, "/missions/")[0]["actif"] is False


def test_une_entree_dont_l_ecran_n_existe_pas_est_ignoree_sans_erreur(monkeypatch):
    accueil = navigation.EntreeMenu("Accueil", "home", "fa-house", None, ordre=0)
    fantome = navigation.EntreeMenu("Fantôme", "ecran:inexistant", "fa-ghost", None, ordre=1)
    monkeypatch.setattr(navigation, "_ENTREES", {"home": accueil, "ecran:inexistant": fantome})

    assert [e["libelle"] for e in navigation.entrees_pour(Role.RH, "/")] == ["Accueil"]


def test_aucun_commentaire_de_template_ne_fuit_dans_les_pages(client):
    """`{# ... #}` multi-lignes s'afficherait en texte brut : régression déjà vue."""
    pages = [reverse("accounts:login")]
    _connecte(client, Role.DIRECTION)
    pages += [reverse("home"), reverse("missions:liste"), reverse("missions:creer")]

    for url in pages:
        contenu = client.get(url).content.decode()
        assert "{#" not in contenu and "#}" not in contenu, url
        assert "{%" not in contenu and "%}" not in contenu, url


def test_un_seul_onglet_est_actif_meme_quand_deux_adresses_se_ressemblent():
    """« Dépenses » (/facturation/depenses/) est sous « Facturation » (/facturation/) : seul le plus précis
    s'allume, le clic sur un onglet ne doit pas en activer un autre."""
    actifs = lambda chemin: [e["libelle"] for e in navigation.entrees_pour(Role.ADMIN, chemin) if e["actif"]]

    assert actifs("/facturation/depenses/") == ["Dépenses"]
    assert actifs("/facturation/") == ["Facturation"]
    assert actifs("/facturation/12/") == ["Facturation"]
    assert actifs("/garage/incidents/3/") == ["Incidents"]
    assert actifs("/garage/") == ["Garage"]
    assert actifs("/") == ["Accueil"]
    assert actifs("/page-inconnue/") == []
```

#### `apps/billing/tests/test_proforma_views.py`

*254 lignes* — Écrans des devis (R5) : accès par rôle, cycle de vie, versions imprimable et modifiable.

```python
"""Écrans des devis (R5) : accès par rôle, cycle de vie, versions imprimable et modifiable."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services
from apps.billing.models import StatutProforma, SEUIL_VALIDATION_DIRECTION

from .helpers import (
    JOUR,
    charge_clientele,
    direction,
    finances,
    proforma_brouillon,
    proforma_envoyee,
    proforma_soumise,
    proforma_validee,
)

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    compte = UserFactory(role=role)
    client.force_login(compte)
    return compte


def _accepte(proforma):
    services.enregistrer_decision_client(proforma, charge_clientele(), acceptee=True)
    return proforma


@pytest.mark.parametrize(
    "role", [Role.ADMIN, Role.DIRECTION, Role.FINANCES, Role.RH, Role.CHARGE_CLIENTELE]
)
def test_les_devis_sont_accessibles_aux_roles_concernes(client, role):
    _connecte(client, role)
    proforma = proforma_brouillon()

    for url in (
        reverse("billing:proformas"),
        reverse("billing:proforma", args=[proforma.pk]),
        reverse("billing:proforma_imprimer", args=[proforma.pk]),
    ):
        assert client.get(url).status_code == 200, url


@pytest.mark.parametrize("role", [Role.PARCAUTO, Role.CHAUFFEUR])
def test_les_devis_sont_interdits_aux_autres_roles(client, role):
    _connecte(client, role)
    proforma = proforma_brouillon()

    for url in (
        reverse("billing:proformas"),
        reverse("billing:proforma", args=[proforma.pk]),
        reverse("billing:proforma_nouveau"),
    ):
        assert client.get(url).status_code == 403, url


def test_la_rh_consulte_les_devis_sans_pouvoir_en_creer(client):
    """Retour réunion : la RH fait tout ce que fait la FINANCES (consultation), mais la
    préparation d'un devis reste réservée au chargé clientèle, à la DIRECTION et à l'ADMIN."""
    _connecte(client, Role.RH)
    proforma = proforma_brouillon()

    for url in (reverse("billing:proformas"), reverse("billing:proforma", args=[proforma.pk])):
        assert client.get(url).status_code == 200, url
    assert client.get(reverse("billing:proforma_nouveau")).status_code == 403


def test_seuls_charge_clientele_admin_et_direction_voient_le_bouton_nouveau_devis(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    assert "Nouveau devis" in client.get(reverse("billing:proformas")).content.decode()

    # Retour réunion : la DIRECTION a la même largeur que l'ADMIN pour la saisie.
    _connecte(client, Role.DIRECTION)
    assert "Nouveau devis" in client.get(reverse("billing:proformas")).content.decode()

    _connecte(client, Role.FINANCES)
    assert "Nouveau devis" not in client.get(reverse("billing:proformas")).content.decode()


def test_creation_d_un_devis(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    from apps.customers.tests.factories import ClientFactory

    client_erp = ClientFactory()

    reponse = client.post(
        reverse("billing:proforma_nouveau"),
        {
            "client": client_erp.pk,
            "lieu_chargement": "Abidjan",
            "lieu_livraison": "Korhogo",
            "nature_marchandise": "Coton",
            "poids_t": "18",
            "prix_convenu": "450000",
        },
    )

    assert reponse.status_code == 302
    proforma = client_erp.proformas.get()
    assert proforma.statut == StatutProforma.BROUILLON


@pytest.mark.parametrize(
    "fabrique",
    [
        lambda: proforma_brouillon(),
        lambda: proforma_soumise(),
        lambda: proforma_soumise(prix=str(SEUIL_VALIDATION_DIRECTION)),
        lambda: proforma_validee(aujourd_hui=JOUR),
        lambda: proforma_envoyee(aujourd_hui=JOUR),
        lambda: _accepte(proforma_envoyee(aujourd_hui=JOUR)),
    ],
)
def test_la_fiche_devis_s_affiche_a_chaque_etape(client, fabrique):
    _connecte(client, Role.DIRECTION)
    proforma = fabrique()

    reponse = client.get(reverse("billing:proforma", args=[proforma.pk]))

    assert reponse.status_code == 200
    assert proforma.get_statut_display() in reponse.content.decode()


def test_la_fiche_devis_accepte_et_refuse(client):
    proforma = proforma_envoyee(aujourd_hui=JOUR)
    _connecte(client, Role.CHARGE_CLIENTELE)

    reponse = client.get(reverse("billing:proforma", args=[proforma.pk]))
    assert reponse.status_code == 200


def test_modification_par_le_chargé_clientele(client):
    proforma = proforma_brouillon(prix="300000")
    compte = _connecte(client, Role.CHARGE_CLIENTELE)

    reponse = client.post(
        reverse("billing:proforma_modifier", args=[proforma.pk]),
        {
            "lieu_chargement": proforma.lieu_chargement,
            "lieu_livraison": proforma.lieu_livraison,
            "nature_marchandise": proforma.nature_marchandise,
            "poids_t": str(proforma.poids_t),
            "prix_convenu": "350000",
            "taux_tva": str(proforma.taux_tva),
            "motif_exoneration": "",
        },
    )

    assert reponse.status_code == 302
    proforma.refresh_from_db()
    assert proforma.prix_convenu == Decimal("350000")


def test_cycle_complet_soumission_validation_envoi_decision(client):
    proforma = proforma_brouillon(prix="300000")

    _connecte(client, Role.CHARGE_CLIENTELE)
    reponse = client.post(reverse("billing:proforma_soumettre", args=[proforma.pk]))
    assert reponse.status_code == 302
    proforma.refresh_from_db()
    assert proforma.statut == StatutProforma.SOUMISE

    _connecte(client, Role.FINANCES)
    reponse = client.post(reverse("billing:proforma_valider_finances", args=[proforma.pk]))
    assert reponse.status_code == 302
    proforma.refresh_from_db()
    assert proforma.statut == StatutProforma.VALIDEE and proforma.numero

    _connecte(client, Role.CHARGE_CLIENTELE)
    reponse = client.post(reverse("billing:proforma_envoyer_client", args=[proforma.pk]))
    assert reponse.status_code == 302
    proforma.refresh_from_db()
    assert proforma.statut == StatutProforma.ENVOYEE_CLIENT

    reponse = client.post(
        reverse("billing:proforma_decision_client", args=[proforma.pk]),
        {"decision": "ACCEPTEE", "motif": ""},
    )
    assert reponse.status_code == 302
    proforma.refresh_from_db()
    assert proforma.statut == StatutProforma.ACCEPTEE


def test_devis_au_dela_du_seuil_transite_par_la_direction(client):
    proforma = proforma_soumise(prix=str(SEUIL_VALIDATION_DIRECTION))

    _connecte(client, Role.FINANCES)
    client.post(reverse("billing:proforma_valider_finances", args=[proforma.pk]))
    proforma.refresh_from_db()
    assert proforma.statut == StatutProforma.EN_ATTENTE_DIRECTION

    _connecte(client, Role.DIRECTION)
    reponse = client.post(reverse("billing:proforma_valider_direction", args=[proforma.pk]))
    assert reponse.status_code == 302
    proforma.refresh_from_db()
    assert proforma.statut == StatutProforma.VALIDEE and proforma.numero


def test_contre_proposition_renvoie_au_chargé_clientele(client):
    proforma = proforma_soumise()
    _connecte(client, Role.FINANCES)

    reponse = client.post(
        reverse("billing:proforma_contre_proposer", args=[proforma.pk]), {"motif": "Prix trop bas"}
    )

    assert reponse.status_code == 302
    proforma.refresh_from_db()
    assert proforma.statut == StatutProforma.CONTRE_PROPOSEE


def test_creer_la_mission_depuis_un_devis_accepte(client):
    proforma = proforma_envoyee(aujourd_hui=JOUR)
    services.enregistrer_decision_client(proforma, charge_clientele(), acceptee=True)
    _connecte(client, Role.CHARGE_CLIENTELE)

    reponse = client.post(reverse("billing:proforma_creer_mission", args=[proforma.pk]))

    assert reponse.status_code == 302
    proforma.refresh_from_db()
    assert proforma.statut == StatutProforma.CONVERTIE
    assert proforma.mission_creee.client == proforma.client


def test_creer_la_mission_est_interdit_aux_roles_hors_creation_mission(client):
    proforma = proforma_envoyee(aujourd_hui=JOUR)
    services.enregistrer_decision_client(proforma, charge_clientele(), acceptee=True)
    _connecte(client, Role.FINANCES)

    reponse = client.post(reverse("billing:proforma_creer_mission", args=[proforma.pk]))

    assert reponse.status_code == 403


def test_abandonner_un_devis(client):
    proforma = proforma_brouillon()
    _connecte(client, Role.CHARGE_CLIENTELE)

    reponse = client.post(reverse("billing:proforma_abandonner", args=[proforma.pk]))

    assert reponse.status_code == 302
    from apps.billing.models import Proforma

    assert not Proforma.objects.filter(pk=proforma.pk).exists()
```

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


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.FINANCES, Role.RH])
def test_la_facturation_est_accessible_a_admin_direction_finances_et_rh(client, role):
    _connecte(client, role)
    facture = brouillon()

    for url in (
        reverse("billing:factures"),
        reverse("billing:facture", args=[facture.pk]),
        reverse("billing:imprimer", args=[facture.pk]),
        reverse("billing:depenses"),
    ):
        assert client.get(url).status_code == 200, url


@pytest.mark.parametrize("role", [Role.PARCAUTO, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
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


def test_la_direction_et_la_rh_preparent_aussi_la_facturation(client):
    """Retour réunion : la DIRECTION (même largeur que l'ADMIN) et la RH (tout ce que fait
    la FINANCES) préparent désormais aussi une facture ou une dépense."""
    for role in (Role.DIRECTION, Role.RH):
        _connecte(client, role)
        assert client.get(reverse("billing:nouvelle")).status_code == 200
        assert client.get(reverse("billing:depense_nouvelle")).status_code == 200
        texte = client.get(reverse("billing:factures")).content.decode()
        assert "Nouvelle facture" in texte


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


def test_le_parc_auto_ne_peut_pas_soumettre_ni_regler(client):
    facture = emise()
    _connecte(client, Role.PARCAUTO)

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

#### `apps/core/tests/test_impression_listes.py`

*233 lignes* — Écrans d'impression des listes métier (``ImpressionListeMixin``) : accès, contenu, filtres repris.

```python
"""Écrans d'impression des listes métier (``ImpressionListeMixin``) : accès, contenu, filtres repris."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing.models import CategorieDepense, ModePaiement
from apps.billing.tests.helpers import brouillon, emise
from apps.customers.tests.factories import ClientFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.models import StatutVehicule
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel.tests.factories import PleinFactory
from apps.garage.models import LieuReparation, TypeOr
from apps.garage.tests.factories import OrdreReparationFactory
from apps.hr.models import Departement, StatutConge
from apps.hr.tests.factories import PersonnelFactory
from apps.inventory.tests.factories import ArticleFactory
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory

pytestmark = pytest.mark.django_db


def _texte(reponse) -> str:
    return reponse.content.decode().replace(" ", " ").replace("\xa0", " ")


# --- missions ---


def test_impression_des_missions(client):
    client.force_login(UserFactory(role=Role.DIRECTION))
    MissionFactory(numero="MIS-2026-0099", client=ClientFactory(raison_sociale="Bolloré"), statut=StatutMission.PLANIFIEE)

    reponse = client.get(reverse("missions:imprimer"), {"statut": "PLANIFIEE"})

    assert reponse.status_code == 200
    texte = _texte(reponse)
    assert "Missions" in texte and "MIS-2026-0099" in texte and "Bolloré" in texte
    assert "statut : Planifiée" in texte


def test_impression_des_missions_refusee_hors_role(client):
    client.force_login(UserFactory(role=Role.RH))

    assert client.get(reverse("missions:imprimer")).status_code == 403


# --- flotte ---


def test_impression_de_la_flotte(client):
    client.force_login(UserFactory(role=Role.PARCAUTO))
    VehiculeFactory(immatriculation="TEST 01 CI", statut=StatutVehicule.DISPONIBLE)

    reponse = client.get(reverse("fleet:imprimer"))

    assert "TEST 01 CI" in _texte(reponse) and "Flotte" in _texte(reponse)


# --- personnel et congés ---


def test_impression_du_personnel_sans_le_salaire(client):
    client.force_login(UserFactory(role=Role.RH))
    PersonnelFactory(nom="Diomandé", departement=Departement.EXPLOITATION, salaire_base=Decimal("999999"))

    texte = _texte(client.get(reverse("hr:personnel_imprimer"), {"departement": Departement.EXPLOITATION}))

    assert "Diomandé" in texte and "département : Exploitation" in texte
    assert "999" not in texte.replace("999999", "")  # le salaire n'est pas dans les colonnes imprimées


def test_impression_des_conges(client):
    rh = UserFactory(role=Role.RH)
    client.force_login(rh)
    chef = PersonnelFactory(nom="Chef", utilisateur=UserFactory(role=Role.PARCAUTO))
    employe = PersonnelFactory(nom="Koffi", superieur=chef)
    from apps.hr import services as hr_services

    hr_services.demander_conge(employe, date_debut=date(2026, 10, 5), date_fin=date(2026, 10, 9), motif="Repos")

    texte = _texte(client.get(reverse("hr:conges_imprimer"), {"vue": "tous"}))

    assert "Koffi" in texte and "tous les congés" in texte


# --- chauffeurs ---


def test_impression_des_chauffeurs(client):
    client.force_login(UserFactory(role=Role.RH))
    ChauffeurFactory(personnel__nom="Traoré", numero_permis="P-123")

    texte = _texte(client.get(reverse("drivers:imprimer")))

    assert "Traoré" in texte and "P-123" in texte


# --- stock ---


def test_impression_du_stock(client):
    client.force_login(UserFactory(role=Role.PARCAUTO))
    ArticleFactory(reference="PN-1", designation="Pneu", quantite=5, pump=Decimal("10000"))

    texte = _texte(client.get(reverse("inventory:articles_imprimer")))

    assert "PN-1" in texte and "Pneu" in texte and "50 000" in texte  # valeur en stock = 5 x 10 000


# --- garage : OR et incidents ---


def test_impression_des_or(client):
    client.force_login(UserFactory(role=Role.PARCAUTO))
    OrdreReparationFactory(numero="OR-2026-0099", type_or=TypeOr.CURATIF, lieu=LieuReparation.INTERNE)

    texte = _texte(client.get(reverse("garage:imprimer"), {"type": "CURATIF"}))

    assert "OR-2026-0099" in texte and "type : Curatif" in texte


# --- carburant ---


def test_impression_des_pleins(client):
    client.force_login(UserFactory(role=Role.PARCAUTO))
    PleinFactory(numero_ticket="TK-99", quantite_litres=Decimal("100"), prix_unitaire=Decimal("600"))

    texte = _texte(client.get(reverse("fuel:imprimer")))

    assert "TK-99" not in texte  # le ticket n'est pas dans les colonnes, mais le montant l'est
    assert "60 000" in texte


# --- clients ---


def test_impression_des_clients(client):
    client.force_login(UserFactory(role=Role.CHARGE_CLIENTELE))
    ClientFactory(raison_sociale="Sonatel Logistique")

    texte = _texte(client.get(reverse("customers:imprimer")))

    assert "Sonatel Logistique" in texte


# --- factures et dépenses ---


def test_impression_des_factures(client):
    client.force_login(UserFactory(role=Role.FINANCES))
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))
    brouillon(prix="500000")

    texte = _texte(client.get(reverse("billing:factures_imprimer"), {"statut": "EMISE"}))

    assert facture.numero in texte and "statut : Émise" in texte and "Sans numéro" not in texte


def test_impression_des_depenses_indique_l_origine(client):
    client.force_login(UserFactory(role=Role.FINANCES))
    from apps.billing import services as billing_services
    from apps.billing.tests.helpers import finances

    billing_services.enregistrer_depense(
        finances(), categorie="PEAGES", date_depense=date(2026, 9, 1), libelle="Péage",
        montant=Decimal("15000"), mode=ModePaiement.ESPECES,
    )
    from apps.fuel import services as fuel_services

    fuel_services.enregistrer_plein(
        vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory(), date_plein=date(2026, 9, 2), station="Total",
        quantite_litres=Decimal("50"), prix_unitaire=Decimal("600"), km_compteur=1000, numero_ticket="T-1",
    )

    texte = _texte(client.get(reverse("billing:depenses_imprimer")))

    assert "Péage" in texte and "Saisie" in texte
    assert "Carburant" in texte and "Automatique" in texte


# --- limite de lignes ---


def test_au_dela_de_la_limite_le_rapport_previent_et_tronque(monkeypatch, client):
    from apps.missions.views import MissionImprimerView

    monkeypatch.setattr(MissionImprimerView, "limite_impression", 2)
    client.force_login(UserFactory(role=Role.DIRECTION))
    for _ in range(3):
        MissionFactory(client=ClientFactory())

    reponse = client.get(reverse("missions:imprimer"))

    assert reponse.context["nombre"] == 2 and reponse.context["tronque"] is True
    assert "limité" in _texte(reponse)


# --- lien "Imprimer" présent sur chaque liste, avec les filtres actuels ---


@pytest.mark.parametrize(
    "role, url_liste, url_imprimer, requete",
    [
        (Role.DIRECTION, "missions:liste", "missions:imprimer", {"statut": "PLANIFIEE"}),
        (Role.PARCAUTO, "fleet:liste", "fleet:imprimer", {"statut": "DISPONIBLE"}),
        (Role.RH, "hr:personnel_liste", "hr:personnel_imprimer", {"departement": "RH"}),
        (Role.RH, "drivers:liste", "drivers:imprimer", {}),
        (Role.PARCAUTO, "inventory:articles", "inventory:articles_imprimer", {}),
        (Role.PARCAUTO, "garage:liste", "garage:imprimer", {}),
        (Role.PARCAUTO, "garage:incidents", "garage:incidents_imprimer", {}),
        (Role.PARCAUTO, "fuel:liste", "fuel:imprimer", {}),
        (Role.CHARGE_CLIENTELE, "customers:liste", "customers:imprimer", {}),
        (Role.FINANCES, "billing:factures", "billing:factures_imprimer", {}),
        (Role.FINANCES, "billing:depenses", "billing:depenses_imprimer", {}),
    ],
)
def test_le_lien_imprimer_reprend_les_filtres_de_la_liste(client, role, url_liste, url_imprimer, requete):
    client.force_login(UserFactory(role=role))

    page = client.get(reverse(url_liste), requete).content.decode()

    lien = reverse(url_imprimer)
    assert lien in page
    for cle, valeur in requete.items():
        assert f"{cle}%3D{valeur}" in page or f"{cle}={valeur}" in page
```

#### `apps/finance/tests/test_demandes_views.py`

*155 lignes* — Écrans des dépenses du parc auto pré-approuvées (R2) : accès, soumission, décision, exécution.

```python
"""Écrans des dépenses du parc auto pré-approuvées (R2) : accès, soumission, décision, exécution."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing.models import CategorieDepense, ModePaiement
from apps.finance import demandes as services
from apps.finance.models import StatutDemandeDepense, StatutOrdreDecaissement
from apps.fleet.tests.factories import VehiculeFactory

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    compte = UserFactory(role=role)
    client.force_login(compte)
    return compte


def _demande_manuelle(**surcharges):
    donnees = dict(
        categorie=CategorieDepense.PIECES, montant_estime=Decimal("200000"), motif="Pièce rare",
    )
    donnees.update(surcharges)
    return services.soumettre_demande(UserFactory(role=Role.PARCAUTO), **donnees)


@pytest.mark.parametrize(
    "role", [Role.ADMIN, Role.DIRECTION, Role.PARCAUTO, Role.FINANCES, Role.RH]
)
def test_les_demandes_sont_accessibles_aux_roles_concernes(client, role):
    _connecte(client, role)
    demande = _demande_manuelle()

    for url in (reverse("finance:demandes"), reverse("finance:demande", args=[demande.pk])):
        assert client.get(url).status_code == 200, url


@pytest.mark.parametrize("role", [Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_les_demandes_sont_interdites_aux_autres_roles(client, role):
    _connecte(client, role)
    demande = _demande_manuelle()

    assert client.get(reverse("finance:demandes")).status_code == 403
    assert client.get(reverse("finance:demande", args=[demande.pk])).status_code == 403


def test_seul_le_parc_auto_voit_le_bouton_nouvelle_demande(client):
    _connecte(client, Role.PARCAUTO)
    assert "Nouvelle demande" in client.get(reverse("finance:demandes")).content.decode()

    _connecte(client, Role.FINANCES)
    assert "Nouvelle demande" not in client.get(reverse("finance:demandes")).content.decode()


def test_le_parc_auto_soumet_une_demande(client):
    _connecte(client, Role.PARCAUTO)

    reponse = client.post(
        reverse("finance:demande_nouvelle"),
        {"categorie": CategorieDepense.MAINTENANCE, "montant_estime": "150000", "motif": "Réparation externe"},
    )

    assert reponse.status_code == 302
    assert services.demandes_queryset().count() == 1


def test_la_direction_valide_une_demande_qui_genere_un_ordre(client):
    demande = _demande_manuelle()
    _connecte(client, Role.DIRECTION)

    reponse = client.post(
        reverse("finance:demande_decider", args=[demande.pk]), {"decision": "VALIDER", "montant_valide": ""}
    )

    assert reponse.status_code == 302
    demande.refresh_from_db()
    assert demande.statut == StatutDemandeDepense.VALIDEE
    assert demande.ordre_decaissement.statut == StatutOrdreDecaissement.A_EXECUTER


def test_la_direction_refuse_une_demande_avec_motif(client):
    demande = _demande_manuelle()
    _connecte(client, Role.DIRECTION)

    reponse = client.post(
        reverse("finance:demande_decider", args=[demande.pk]),
        {"decision": "REFUSER", "motif_refus": "Budget insuffisant ce mois-ci"},
    )

    assert reponse.status_code == 302
    demande.refresh_from_db()
    assert demande.statut == StatutDemandeDepense.REFUSEE


def test_la_finance_execute_un_ordre(client):
    demande = _demande_manuelle()
    services.valider_demande(demande, UserFactory(role=Role.DIRECTION))
    ordre = demande.ordre_decaissement
    _connecte(client, Role.FINANCES)

    reponse = client.post(
        reverse("finance:ordre_executer", args=[ordre.pk]),
        {"mode_paiement": ModePaiement.ESPECES, "montant_reel": "205000", "reference": "FAC-1"},
    )

    assert reponse.status_code == 302
    ordre.refresh_from_db()
    assert ordre.statut == StatutOrdreDecaissement.EXECUTE


def test_un_depassement_via_l_ecran_bloque_puis_se_revalide(client):
    demande = _demande_manuelle(montant_estime=Decimal("200000"))
    services.valider_demande(demande, UserFactory(role=Role.DIRECTION))
    ordre = demande.ordre_decaissement
    _connecte(client, Role.FINANCES)

    client.post(
        reverse("finance:ordre_executer", args=[ordre.pk]),
        {"mode_paiement": ModePaiement.ESPECES, "montant_reel": "300000"},
    )
    ordre.refresh_from_db()
    assert ordre.statut == StatutOrdreDecaissement.EN_ATTENTE_REVALIDATION

    _connecte(client, Role.DIRECTION)
    reponse = client.post(reverse("finance:ordre_revalider", args=[ordre.pk]), {"montant_valide": "300000"})
    assert reponse.status_code == 302
    ordre.refresh_from_db()
    assert ordre.statut == StatutOrdreDecaissement.A_EXECUTER


def test_la_direction_definit_une_enveloppe_via_l_ecran(client):
    _connecte(client, Role.DIRECTION)
    camion = VehiculeFactory()

    reponse = client.post(
        reverse("finance:enveloppe_nouvelle"),
        {
            "categorie": CategorieDepense.CARBURANT, "vehicule": camion.pk,
            "annee": "2026", "mois": "9", "montant_plafond": "300000",
        },
    )

    assert reponse.status_code == 302
    assert services.enveloppes_queryset().count() == 1


def test_le_parc_auto_ne_voit_pas_l_ecran_des_enveloppes(client):
    _connecte(client, Role.PARCAUTO)

    assert client.get(reverse("finance:enveloppes")).status_code == 403
```

#### `apps/finance/tests/test_depenses_parc_auto.py`

*340 lignes* — Les dépenses du parc auto (plein, achat de pièces, main-d'œuvre d'OR) sont comptabilisées toutes seules :

```python
"""Les dépenses du parc auto (plein, achat de pièces, main-d'œuvre d'OR) sont comptabilisées toutes seules :
page Dépenses, trésorerie et charges donnent le même total."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services as billing
from apps.billing.exceptions import ActionFactureNonAutorisee, MontantInvalide
from apps.billing.forms import DepenseForm
from apps.billing.models import CategorieDepense, Depense, ModePaiement, OrigineDepense
from apps.billing.tests.helpers import finances
from apps.drivers.tests.factories import ChauffeurFactory
from apps.finance import services
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel import services as fuel
from apps.fuel.models import Plein
from apps.fuel.tests.factories import PleinFactory
from apps.garage import services as garage
from apps.garage.models import LieuReparation, TypeOr
from apps.inventory import services as stock
from apps.inventory.tests.factories import ArticleFactory

pytestmark = pytest.mark.django_db

AUJOURD_HUI = timezone.localdate()


def _plein(litres="100", prix="655", jour=None, ticket="T-1", camion=None, km=1000):
    return fuel.enregistrer_plein(
        vehicule=camion or VehiculeFactory(), chauffeur=ChauffeurFactory(), date_plein=jour or AUJOURD_HUI,
        station="Total", quantite_litres=Decimal(litres), prix_unitaire=Decimal(prix), km_compteur=km,
        numero_ticket=ticket,
    )


def _auto(origine):
    return Depense.objects.filter(origine=origine)


# --- plein ---


def test_un_plein_devient_une_depense_carburant_en_especes():
    plein = _plein("110", "655", jour=date(2026, 9, 3), ticket="TK-9")

    (depense,) = _auto(OrigineDepense.PLEIN)

    assert depense.origine_id == plein.pk
    assert depense.categorie == CategorieDepense.CARBURANT
    assert depense.montant == Decimal("72050.00")
    assert depense.date_depense == date(2026, 9, 3)
    assert depense.mode == ModePaiement.ESPECES and depense.reference == "TK-9"
    assert plein.vehicule.immatriculation in depense.libelle and "110 L" in depense.libelle
    assert depense.est_automatique and depense.saisi_par is None


def test_le_plein_sort_de_la_caisse_dans_la_tresorerie():
    avant = services.soldes_par_compte()

    _plein("100", "600")

    apres = services.soldes_par_compte()
    assert apres["CAISSE"] - avant["CAISSE"] == Decimal("-60000")
    assert apres["total"] - avant["total"] == Decimal("-60000")
    ligne = next(m for m in services.mouvements() if m["origine"] == "DEPENSE")
    assert (ligne["sens"], ligne["montant"], ligne["compte"]) == ("SORTIE", Decimal("60000.00"), "CAISSE")


def test_rejouer_la_meme_source_ne_cree_pas_de_doublon():
    plein = _plein()
    kwargs = dict(
        origine=OrigineDepense.PLEIN, origine_id=plein.pk, categorie=CategorieDepense.CARBURANT,
        date_depense=AUJOURD_HUI, libelle="x", montant=Decimal("1"),
    )

    premiere = billing.comptabiliser_depense_automatique(**kwargs)
    seconde = billing.comptabiliser_depense_automatique(**kwargs)

    assert premiere.pk == seconde.pk and _auto(OrigineDepense.PLEIN).count() == 1


def test_un_plein_refuse_ne_laisse_aucune_depense():
    _plein(ticket="DOUBLON")

    with pytest.raises(Exception):
        _plein(ticket="DOUBLON")

    assert Depense.objects.count() == 1


def test_une_depense_qui_ne_peut_pas_etre_ecrite_annule_le_plein(monkeypatch):
    def echec(**kwargs):
        raise RuntimeError("base indisponible")

    monkeypatch.setattr(billing, "comptabiliser_depense_automatique", echec)

    with pytest.raises(RuntimeError):
        _plein()

    assert Plein.objects.count() == 0  # pas de sortie d'argent non comptée


# --- pièces et main-d'œuvre ---


def test_un_achat_de_pieces_devient_une_depense_pieces():
    article = ArticleFactory(reference="PN-1", designation="Pneu", quantite=0)

    mouvement = stock.enregistrer_entree(article, quantite=4, prix_unitaire=Decimal("125000"))

    (depense,) = _auto(OrigineDepense.ACHAT_STOCK)
    assert depense.origine_id == mouvement.pk and depense.categorie == CategorieDepense.PIECES
    assert depense.montant == Decimal("500000.00") and depense.date_depense == AUJOURD_HUI
    assert "Pneu" in depense.libelle and "PN-1" in depense.libelle and "× 4" in depense.libelle


def test_sortir_des_pieces_pour_un_or_ne_recompte_pas_la_piece():
    ordre = garage.ouvrir_or(VehiculeFactory(), type_or=TypeOr.CURATIF, lieu=LieuReparation.INTERNE, motif="Freins")
    article = ArticleFactory(reference="P-2", quantite=0)
    stock.enregistrer_entree(article, quantite=10, prix_unitaire=Decimal("5000"))

    stock.sortir_pour_or(article, quantite=3, ordre=ordre)
    stock.ajuster_stock(article, variation=-1, motif="Casse")

    assert Depense.objects.count() == 1  # l'achat seul
    assert services.charges(AUJOURD_HUI, AUJOURD_HUI)["pieces"] == Decimal("50000")


def test_la_main_d_oeuvre_d_un_or_cloture_devient_une_depense_maintenance():
    ordre = garage.ouvrir_or(VehiculeFactory(), type_or=TypeOr.CURATIF, lieu=LieuReparation.EXTERNE, motif="Boîte")

    garage.cloturer_or(ordre, cout_main_oeuvre=Decimal("45000"))

    (depense,) = _auto(OrigineDepense.MAIN_OEUVRE_OR)
    assert depense.origine_id == ordre.pk and depense.categorie == CategorieDepense.MAINTENANCE
    assert depense.montant == Decimal("45000.00") and depense.reference == ordre.numero
    assert ordre.numero in depense.libelle


def test_un_or_sans_main_d_oeuvre_ne_cree_pas_de_depense():
    ordre = garage.ouvrir_or(VehiculeFactory(), type_or=TypeOr.PREVENTIF, lieu=LieuReparation.INTERNE, motif="Vidange")

    garage.cloturer_or(ordre)

    assert Depense.objects.count() == 0


# --- cohérence page Dépenses / trésorerie / charges ---


def test_depenses_tresorerie_et_charges_donnent_le_meme_total():
    billing.enregistrer_depense(
        finances(), categorie="PEAGES", date_depense=AUJOURD_HUI, libelle="Péage", montant=Decimal("10000"),
        mode=ModePaiement.WAVE,
    )
    _plein("100", "600")
    stock.enregistrer_entree(ArticleFactory(quantite=0), quantite=2, prix_unitaire=Decimal("7000"))
    ordre = garage.ouvrir_or(VehiculeFactory(), type_or=TypeOr.CURATIF, lieu=LieuReparation.INTERNE, motif="x")
    garage.cloturer_or(ordre, cout_main_oeuvre=Decimal("20000"))

    charges = services.charges(AUJOURD_HUI, AUJOURD_HUI)
    sorties = services.synthese_periode(AUJOURD_HUI, AUJOURD_HUI)["sorties"]

    assert charges["total"] == sorties == billing.total_depenses(AUJOURD_HUI, AUJOURD_HUI) == Decimal("104000")
    assert (charges["carburant"], charges["pieces"], charges["main_oeuvre"], charges["depenses"]) == (
        Decimal("60000"), Decimal("14000"), Decimal("20000"), Decimal("10000"),
    )


# --- saisie manuelle et correction du mode ---


@pytest.mark.parametrize("categorie", [CategorieDepense.CARBURANT, CategorieDepense.PIECES, CategorieDepense.MAINTENANCE])
def test_on_ne_saisit_pas_a_la_main_ce_qui_se_comptabilise_tout_seul(categorie):
    with pytest.raises(MontantInvalide, match="tout seuls"):
        billing.enregistrer_depense(
            finances(), categorie=categorie, date_depense=AUJOURD_HUI, libelle="x", montant=Decimal("1"),
            mode=ModePaiement.ESPECES,
        )


def test_le_formulaire_de_saisie_ne_propose_pas_les_categories_automatiques():
    codes = [code for code, _ in DepenseForm().fields["categorie"].choices]

    assert "PEAGES" in codes and "CARBURANT" not in codes and "PIECES" not in codes and "MAINTENANCE" not in codes


def test_la_finance_corrige_le_mode_et_le_compte_debite_change():
    _plein("100", "600")
    depense = _auto(OrigineDepense.PLEIN).get()

    billing.changer_mode_depense(depense, finances(), mode=ModePaiement.VIREMENT)

    soldes = services.soldes_par_compte()
    assert soldes["BANQUE"] == Decimal("-60000") and soldes["CAISSE"] == Decimal("0")


def test_seule_la_finance_corrige_et_seulement_les_depenses_automatiques():
    _plein()
    automatique = _auto(OrigineDepense.PLEIN).get()
    manuelle = billing.enregistrer_depense(
        finances(), categorie="PEAGES", date_depense=AUJOURD_HUI, libelle="Péage", montant=Decimal("5000"),
        mode=ModePaiement.ESPECES,
    )

    # Retour réunion : la DIRECTION a désormais la même largeur que l'ADMIN en saisie.
    with pytest.raises(ActionFactureNonAutorisee):
        billing.changer_mode_depense(automatique, UserFactory(role=Role.PARCAUTO), mode=ModePaiement.WAVE)
    with pytest.raises(ActionFactureNonAutorisee):
        billing.changer_mode_depense(manuelle, finances(), mode=ModePaiement.WAVE)
    with pytest.raises(MontantInvalide):
        billing.changer_mode_depense(automatique, finances(), mode="BITCOIN")


def test_ecran_depenses_montre_les_lignes_automatiques_et_le_changement_de_mode(client):
    client.force_login(UserFactory(role=Role.FINANCES))
    _plein("100", "600")
    depense = _auto(OrigineDepense.PLEIN).get()

    page = client.get(reverse("billing:depenses")).content.decode()
    assert "Automatique" in page and reverse("billing:depense_mode", args=[depense.pk]) in page

    reponse = client.post(reverse("billing:depense_mode", args=[depense.pk]), {"mode": "WAVE"}, follow=True)

    depense.refresh_from_db()
    assert depense.mode == ModePaiement.WAVE
    assert any("Wave" in str(m) for m in reponse.context["messages"])


def test_la_direction_voit_les_lignes_et_peut_changer_le_mode(client):
    """Retour réunion : la DIRECTION a la même largeur que l'ADMIN pour la saisie."""
    client.force_login(UserFactory(role=Role.DIRECTION))
    _plein()
    depense = _auto(OrigineDepense.PLEIN).get()

    page = client.get(reverse("billing:depenses")).content.decode()

    assert "Automatique" in page and reverse("billing:depense_mode", args=[depense.pk]) in page
    reponse = client.post(
        reverse("billing:depense_mode", args=[depense.pk]), {"mode": "WAVE"}, follow=True
    )
    depense.refresh_from_db()
    assert reponse.status_code == 200 and depense.mode == ModePaiement.WAVE


def test_le_parc_auto_n_a_pas_acces_a_l_ecran_des_depenses(client):
    """Le Parc Auto gère ses propres dépenses via l'écran des missions (FRAIS_CONSULTATION) ;
    l'écran de facturation/dépenses générales reste hors de sa portée."""
    client.force_login(UserFactory(role=Role.PARCAUTO))
    _plein()
    depense = _auto(OrigineDepense.PLEIN).get()

    assert client.get(reverse("billing:depenses")).status_code == 403
    assert client.post(reverse("billing:depense_mode", args=[depense.pk]), {"mode": "WAVE"}).status_code == 403


# --- reprise de l'historique (commande comptabiliser_historique_parc_auto, pas une migration :
#     sur une base avec un solde d'ouverture, reprendre sans --depuis compterait deux fois les
#     mouvements déjà compris dedans) ---


def _etat_avant_comptabilisation():
    """Des pleins, un achat et un OR déjà enregistrés, comme avant la mise en service de la
    comptabilisation automatique (``Depense`` vidée après coup, comme sur une base existante)."""
    PleinFactory(date_plein=date(2026, 8, 3), quantite_litres=Decimal("100"), prix_unitaire=Decimal("600"), numero_ticket="OLD-1")
    PleinFactory(date_plein=date(2026, 9, 10), quantite_litres=Decimal("50"), prix_unitaire=Decimal("700"), numero_ticket="OLD-2")
    article = ArticleFactory(quantite=0)
    stock.enregistrer_entree(article, quantite=3, prix_unitaire=Decimal("1000"))
    ordre = garage.ouvrir_or(VehiculeFactory(), type_or=TypeOr.CURATIF, lieu=LieuReparation.INTERNE, motif="x")
    garage.cloturer_or(ordre, cout_main_oeuvre=Decimal("8000"))
    Depense.objects.all().delete()


def test_la_reprise_de_l_existant_cree_les_depenses_manquantes_une_seule_fois():
    _etat_avant_comptabilisation()

    premiere = services.reprendre_depenses_parc_auto()
    seconde = services.reprendre_depenses_parc_auto()  # rejouable

    assert premiere == {"carburant": 2, "pieces": 1, "main_oeuvre": 1, "deja_comptabilisees": 0}
    assert seconde == {"carburant": 0, "pieces": 0, "main_oeuvre": 0, "deja_comptabilisees": 4}
    assert Depense.objects.count() == 4
    plein = _auto(OrigineDepense.PLEIN).filter(reference="OLD-1").get()
    assert plein.montant == Decimal("60000.00") and plein.date_depense == date(2026, 8, 3)
    assert _auto(OrigineDepense.ACHAT_STOCK).get().montant == Decimal("3000.00")
    assert _auto(OrigineDepense.MAIN_OEUVRE_OR).get().montant == Decimal("8000.00")
    assert set(Depense.objects.values_list("mode", flat=True)) == {ModePaiement.ESPECES}


def test_depuis_ignore_ce_qui_precede_un_solde_d_ouverture():
    """Un solde d'ouverture saisi au 01/09/2026 comprend déjà les mouvements antérieurs : ne pas les reprendre."""
    from apps.garage.models import OrdreReparation
    from apps.inventory.models import MouvementStock

    _etat_avant_comptabilisation()
    ancien = timezone.now().replace(year=2026, month=8, day=15)
    MouvementStock.objects.update(date_mouvement=ancien)
    OrdreReparation.objects.update(date_cloture=ancien)

    compteurs = services.reprendre_depenses_parc_auto(depuis=date(2026, 9, 1))

    assert compteurs["carburant"] == 1  # seulement OLD-2 (10/09), pas OLD-1 (03/08)
    assert compteurs["pieces"] == 0 and compteurs["main_oeuvre"] == 0  # l'achat et l'OR sont d'avant
    assert Depense.objects.count() == 1
    assert _auto(OrigineDepense.PLEIN).get().reference == "OLD-2"


def test_la_commande_de_gestion_rapporte_les_compteurs(capsys):
    from django.core.management import call_command

    _etat_avant_comptabilisation()

    call_command("comptabiliser_historique_parc_auto")

    assert Depense.objects.count() == 4
    assert "Carburant : 2" in capsys.readouterr().out


def test_dry_run_n_ecrit_rien(capsys):
    from django.core.management import call_command

    _etat_avant_comptabilisation()

    call_command("comptabiliser_historique_parc_auto", "--dry-run")

    assert Depense.objects.count() == 0
    assert "Simulation" in capsys.readouterr().out


def test_la_commande_refuse_une_date_invalide():
    from django.core.management import CommandError, call_command

    with pytest.raises(CommandError):
        call_command("comptabiliser_historique_parc_auto", "--depuis", "pas-une-date")
```

#### `apps/finance/tests/test_impression.py`

*120 lignes* — Rapport imprimable de la trésorerie : mêmes filtres que le journal, sans pagination.

```python
"""Rapport imprimable de la trésorerie : mêmes filtres que le journal, sans pagination."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services as billing
from apps.billing.models import ModePaiement
from apps.billing.tests.helpers import emise, finances

pytestmark = pytest.mark.django_db


def _texte(reponse) -> str:
    return reponse.content.decode().replace(" ", " ").replace("\xa0", " ")


def _connecte(client, role=Role.FINANCES):
    client.force_login(UserFactory(role=role))


def test_impression_de_la_tresorerie(client):
    _connecte(client)
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))
    billing.enregistrer_reglement(
        facture, finances(), montant=Decimal("500000"), mode=ModePaiement.VIREMENT, date_reglement=date(2026, 9, 10)
    )

    texte = _texte(client.get(reverse("finance:imprimer")))

    assert "Trésorerie" in texte and facture.numero in texte and "500 000" in texte
    assert "Banque" in texte and "Caisse" in texte and "Mobile Money" in texte


def test_impression_reprend_les_filtres_de_periode_et_de_compte(client):
    _connecte(client)
    ancien = emise(prix="100000", aujourd_hui=date(2026, 1, 1))
    billing.enregistrer_reglement(
        ancien, finances(), montant=Decimal("118000"), mode=ModePaiement.ESPECES, date_reglement=date(2026, 1, 5)
    )
    recent = emise(prix="200000", aujourd_hui=date(2026, 9, 1))
    billing.enregistrer_reglement(
        recent, finances(), montant=Decimal("236000"), mode=ModePaiement.VIREMENT, date_reglement=date(2026, 9, 10)
    )

    reponse = client.get(
        reverse("finance:imprimer"),
        {"date_debut": "2026-09-01", "date_fin": "2026-09-30", "compte": "BANQUE"},
    )
    texte = _texte(reponse)

    assert recent.numero in texte and ancien.numero not in texte
    assert "01/09/2026 au 30/09/2026" in texte and "compte : Banque" in texte


def test_seule_l_entree_ou_la_sortie_demandee_apparait(client):
    _connecte(client)
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))
    billing.enregistrer_reglement(
        facture, finances(), montant=Decimal("300000"), mode=ModePaiement.WAVE, date_reglement=date(2026, 9, 5)
    )
    billing.enregistrer_depense(
        finances(), categorie="PEAGES", date_depense=date(2026, 9, 6), libelle="Péage",
        montant=Decimal("10000"), mode=ModePaiement.ESPECES,
    )

    texte_entrees = _texte(client.get(reverse("finance:imprimer"), {"sens": "ENTREE"}))
    assert facture.numero in texte_entrees and "Péage" not in texte_entrees

    texte_sorties = _texte(client.get(reverse("finance:imprimer"), {"sens": "SORTIE"}))
    assert "Péage" in texte_sorties and facture.numero not in texte_sorties


def test_accessible_en_lecture_a_la_direction_et_a_la_rh_mais_pas_aux_autres(client):
    # Retour réunion : la RH fait tout ce que fait la FINANCES, y compris consulter la trésorerie.
    _connecte(client, Role.DIRECTION)
    assert client.get(reverse("finance:imprimer")).status_code == 200

    _connecte(client, Role.RH)
    assert client.get(reverse("finance:imprimer")).status_code == 200

    _connecte(client, Role.PARCAUTO)
    assert client.get(reverse("finance:imprimer")).status_code == 403


def test_sans_mouvement_le_rapport_le_dit(client):
    _connecte(client)

    texte = _texte(client.get(reverse("finance:imprimer")))

    assert "Aucun mouvement pour ces critères." in texte


def test_au_dela_de_la_limite_le_journal_est_tronque(monkeypatch, client):
    from apps.finance.views import TresorerieImprimerView

    monkeypatch.setattr(TresorerieImprimerView, "limite", 2)
    _connecte(client)
    for i in range(3):
        f = emise(prix="100000", aujourd_hui=date(2026, 9, 1 + i))
        billing.enregistrer_reglement(
            f, finances(), montant=Decimal("118000"), mode=ModePaiement.ESPECES, date_reglement=date(2026, 9, 15)
        )

    reponse = client.get(reverse("finance:imprimer"))

    assert reponse.context["nombre"] == 2 and reponse.context["tronque"] is True
    assert "limité" in _texte(reponse)


def test_le_lien_imprimer_est_sur_la_page_tresorerie_avec_les_filtres(client):
    _connecte(client)

    page = client.get(reverse("finance:tresorerie"), {"compte": "CAISSE"}).content.decode()

    assert reverse("finance:imprimer") in page and "compte%3DCAISSE" in page or "compte=CAISSE" in page
```

#### `apps/finance/tests/test_versements.py`

*249 lignes* — Versements attendus : la Finance confirme qu'une facture émise a été payée, et l'entrée apparaît en trésorerie.

```python
"""Versements attendus : la Finance confirme qu'une facture émise a été payée, et l'entrée apparaît en trésorerie."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services as billing
from apps.billing.exceptions import ActionFactureNonAutorisee, ReglementInvalide
from apps.billing.models import CompteTresorerie, ModePaiement, StatutFacture
from apps.billing.tests.helpers import a_valider, brouillon, emise, finances
from apps.finance import services

pytestmark = pytest.mark.django_db

JOUR_PAIEMENT = date(2026, 9, 10)  # après l'émission (2026-09-01), avant aujourd'hui


def _connecte(client, role):
    compte = UserFactory(role=role)
    client.force_login(compte)
    return compte


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


# --- versements attendus (service) ---


def test_les_versements_attendus_listent_les_factures_emises_non_soldees_les_plus_en_retard_d_abord():
    a_venir = emise(prix="500000", aujourd_hui=date(2026, 8, 1))  # échéance 31/08
    echue = emise(prix="1000000", aujourd_hui=date(2026, 7, 1))  # échéance 31/07
    brouillon(prix="300000")  # pas émise : rien à attendre
    a_valider(prix="300000")

    attendus = services.versements_attendus(aujourd_hui=date(2026, 8, 10))

    assert [ligne["facture"].pk for ligne in attendus["lignes"]] == [echue.pk, a_venir.pk]
    assert attendus["nombre"] == 2
    premiere, seconde = attendus["lignes"]
    assert (premiere["echue"], premiere["jours"]) == (True, 10)
    assert (seconde["echue"], seconde["jours"]) == (False, 21)
    assert premiere["reste"] == Decimal("1180000") and seconde["reste"] == Decimal("590000")
    assert attendus["total"] == Decimal("1770000")
    assert attendus["echu"] == Decimal("1180000")
    assert attendus["a_venir"] == Decimal("590000")


def test_un_acompte_reduit_le_versement_attendu_et_le_solde_le_retire():
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))
    billing.enregistrer_reglement(
        facture, finances(), montant=Decimal("400000"), mode=ModePaiement.VIREMENT, date_reglement=JOUR_PAIEMENT
    )

    reste = services.versements_attendus()["lignes"][0]["reste"]
    assert reste == Decimal("780000")

    billing.enregistrer_reglement(
        facture, finances(), montant=Decimal("780000"), mode=ModePaiement.ESPECES, date_reglement=JOUR_PAIEMENT
    )
    assert services.versements_attendus()["nombre"] == 0


def test_aucune_facture_a_encaisser():
    assert services.versements_attendus() == {
        "lignes": [], "nombre": 0, "total": Decimal("0"), "echu": Decimal("0"), "a_venir": Decimal("0"),
    }


# --- confirmation (service) ---


def test_confirmer_un_versement_l_ajoute_en_entree_de_tresorerie_sur_le_bon_compte():
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))
    avant = services.soldes_par_compte()

    reglement, compte = services.confirmer_versement(
        facture, finances(), montant=Decimal("1180000"), mode=ModePaiement.WAVE,
        date_reglement=JOUR_PAIEMENT, reference="WV-123",
    )

    facture.refresh_from_db()
    apres = services.soldes_par_compte()
    assert compte == CompteTresorerie.MOBILE_MONEY
    assert facture.statut == StatutFacture.PAYEE
    assert apres["MOBILE_MONEY"] - avant["MOBILE_MONEY"] == Decimal("1180000")
    assert apres["total"] - avant["total"] == Decimal("1180000")
    entree = next(m for m in services.mouvements() if m["origine"] == "REGLEMENT")
    assert (entree["sens"], entree["montant"], entree["reference"]) == ("ENTREE", Decimal("1180000"), "WV-123")
    assert facture.numero in entree["libelle"]


def test_on_ne_confirme_pas_plus_que_le_reste_a_recouvrer():
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))

    with pytest.raises(ReglementInvalide):
        services.confirmer_versement(
            facture, finances(), montant=Decimal("1180001"), mode=ModePaiement.VIREMENT, date_reglement=JOUR_PAIEMENT
        )

    assert services.soldes_par_compte()["total"] == Decimal("0")


def test_seule_la_saisie_facturation_confirme_un_versement():
    # Retour réunion : la DIRECTION a désormais la même largeur que l'ADMIN en saisie.
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))

    with pytest.raises(ActionFactureNonAutorisee):
        services.confirmer_versement(
            facture, UserFactory(role=Role.PARCAUTO), montant=Decimal("1000"),
            mode=ModePaiement.VIREMENT, date_reglement=JOUR_PAIEMENT,
        )


# --- écrans ---


def _url(facture):
    return reverse("finance:versement_confirmer", args=[facture.pk])


def test_la_tresorerie_liste_les_versements_a_confirmer_avec_le_bouton_pour_la_finance(client):
    _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))

    contenu = client.get(reverse("finance:tresorerie")).content.decode()

    assert "Versements à confirmer" in contenu
    assert facture.numero in contenu
    assert _url(facture) in contenu and "Confirmer le versement" in contenu


def test_la_direction_voit_les_versements_attendus_et_peut_desormais_les_confirmer(client):
    """Retour réunion : la DIRECTION a la même largeur que l'ADMIN pour la saisie."""
    _connecte(client, Role.DIRECTION)
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))

    reponse = client.get(reverse("finance:tresorerie"))

    assert facture.numero in reponse.content.decode()
    assert _url(facture) in reponse.content.decode()
    assert client.get(_url(facture)).status_code == 200


def test_le_solde_previsionnel_ajoute_les_versements_attendus_au_solde_reel(client):
    _connecte(client, Role.FINANCES)
    emise(prix="1000000", aujourd_hui=date(2026, 9, 1))

    reponse = client.get(reverse("finance:tresorerie"))

    assert reponse.context["soldes"]["total"] == Decimal("0")  # rien n'est encaissé : le solde réel ne bouge pas
    assert reponse.context["solde_previsionnel"] == Decimal("1180000")


def test_l_ecran_de_confirmation_propose_le_reste_a_recouvrer(client):
    _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))

    reponse = client.get(_url(facture))

    assert reponse.status_code == 200
    assert reponse.context["form"].initial["montant"] == Decimal("1180000")
    assert facture.numero in reponse.content.decode()


def test_confirmer_le_versement_ajoute_l_entree_et_solde_la_facture(client):
    _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))

    reponse = client.post(
        _url(facture),
        {"montant": "1180000", "date_reglement": JOUR_PAIEMENT.isoformat(), "mode": ModePaiement.VIREMENT, "reference": "VIR-9"},
        follow=True,
    )

    facture.refresh_from_db()
    assert reponse.redirect_chain[-1][0] == reverse("finance:tresorerie")
    assert facture.statut == StatutFacture.PAYEE
    assert any("confirmé" in m and "compte Banque" in m for m in _messages(reponse))
    assert reponse.context["soldes"]["BANQUE"] == Decimal("1180000")
    assert reponse.context["versements"]["nombre"] == 0  # plus rien à attendre pour cette facture


def test_un_versement_partiel_laisse_le_solde_dans_les_versements_attendus(client):
    _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))

    reponse = client.post(
        _url(facture),
        {"montant": "400000", "date_reglement": JOUR_PAIEMENT.isoformat(), "mode": ModePaiement.ESPECES},
        follow=True,
    )

    facture.refresh_from_db()
    assert facture.statut == StatutFacture.PARTIELLEMENT_PAYEE
    assert reponse.context["versements"]["total"] == Decimal("780000")
    assert reponse.context["soldes"]["CAISSE"] == Decimal("400000")


def test_un_montant_trop_eleve_reste_sur_le_formulaire_sans_rien_enregistrer(client):
    _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))

    reponse = client.post(
        _url(facture),
        {"montant": "9999999", "date_reglement": JOUR_PAIEMENT.isoformat(), "mode": ModePaiement.VIREMENT},
    )

    assert reponse.status_code == 200
    assert "dépasse le reste à recouvrer" in reponse.content.decode()
    assert services.soldes_par_compte()["total"] == Decimal("0")


def test_une_facture_deja_soldee_renvoie_a_la_tresorerie(client):
    _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))
    billing.enregistrer_reglement(
        facture, finances(), montant=Decimal("1180000"), mode=ModePaiement.VIREMENT, date_reglement=JOUR_PAIEMENT
    )

    reponse = client.get(_url(facture), follow=True)

    assert reponse.redirect_chain[-1][0] == reverse("finance:tresorerie")
    assert any("n'attend plus de versement" in m for m in _messages(reponse))


def test_une_facture_inconnue_est_introuvable(client):
    _connecte(client, Role.FINANCES)

    assert client.get(reverse("finance:versement_confirmer", args=[99999])).status_code == 404


def test_la_notification_de_validation_mene_a_l_ecran_de_confirmation(client):
    """Bout en bout : validation par la DIRECTION -> bouton dans la notification de la FINANCES -> confirmation."""
    finance = _connecte(client, Role.FINANCES)
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 1))

    page = client.get(reverse("notifications:liste")).content.decode()
    assert "Confirmer le versement" in page

    notification = finance.notifications.get(titre__contains="versement à confirmer")
    reponse = client.post(reverse("notifications:lire", args=[notification.pk]))

    assert reponse.status_code == 302 and reponse.url == _url(facture)
```

#### `apps/finance/tests/test_views.py`

*231 lignes* — Écran de trésorerie : accès, journal, soldes, mouvements manuels.

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


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.FINANCES, Role.RH])
def test_la_tresorerie_est_accessible_a_admin_direction_finances_et_rh(client, role):
    _connecte(client, role)

    assert client.get(reverse("finance:tresorerie")).status_code == 200


@pytest.mark.parametrize("role", [Role.PARCAUTO, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_la_tresorerie_est_interdite_aux_autres_roles(client, role):
    _connecte(client, role)

    assert client.get(reverse("finance:tresorerie")).status_code == 403


def test_la_tresorerie_exige_la_connexion(client):
    assert client.get(reverse("finance:tresorerie")).status_code == 302


def test_la_direction_et_la_rh_consultent_et_saisissent_desormais(client):
    """Retour réunion : la DIRECTION (même largeur que l'ADMIN) et la RH (tout ce que fait
    la FINANCES) peuvent désormais saisir un mouvement de trésorerie."""
    for role in (Role.DIRECTION, Role.RH):
        _connecte(client, role)
        texte = client.get(reverse("finance:tresorerie")).content.decode()
        assert "Autre mouvement" in texte
        assert client.post(reverse("finance:mouvement_creer"), _donnees()).status_code == 302


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

*147 lignes* — Notifications de facturation : soumission, validation, refus, factures échues.

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
        assert notification.action == "Examiner et valider"  # bouton d'accès direct à la validation
    assert _de(finance) == []


def test_finances_et_l_auteur_sont_prevenus_de_la_validation():
    chef = UserFactory(role=Role.DIRECTION)
    preparateur = UserFactory(role=Role.ADMIN)  # un ADMIN peut aussi préparer
    autre_finances = UserFactory(role=Role.FINANCES)
    facture = brouillon(acteur=preparateur)
    services.soumettre(facture, preparateur)

    services.valider(facture, chef, aujourd_hui=date(2026, 9, 1))

    # La FINANCES reçoit le bouton « Confirmer le versement » (écran de confirmation, pas la facture) ...
    notification = _de(autre_finances)[-1]
    assert notification.titre == f"Facture {facture.numero} validée : versement à confirmer"
    assert notification.niveau == NiveauNotification.INFO
    assert "échéance le 01/10/2026" in notification.message
    assert "ajouté en entrée de trésorerie" in notification.message
    assert notification.action == "Confirmer le versement"
    assert notification.url == reverse("finance:versement_confirmer", args=[facture.pk])
    # ... l'auteur qui n'est pas de la FINANCES est seulement prévenu, avec le lien de la facture.
    notification = _de(preparateur)[-1]
    assert notification.titre == f"Facture {facture.numero} validée"
    assert "échéance le 01/10/2026" in notification.message
    assert notification.action == "" and notification.url == reverse("billing:facture", args=[facture.pk])
    assert all("validée" not in n.titre for n in _de(chef))


def test_un_auteur_de_la_finances_ne_recoit_qu_une_notification_de_validation():
    chef = UserFactory(role=Role.DIRECTION)
    preparateur = UserFactory(role=Role.FINANCES)
    facture = brouillon(acteur=preparateur)
    services.soumettre(facture, preparateur)

    services.valider(facture, chef, aujourd_hui=date(2026, 9, 1))

    validations = [n for n in _de(preparateur) if "validée" in n.titre]
    assert len(validations) == 1 and validations[0].action == "Confirmer le versement"


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


def test_les_factures_echues_previennent_finances_direction_et_rh_une_seule_fois():
    """Retour réunion : la RH fait tout ce que fait la FINANCES, elle est donc prévenue aussi."""
    finance, chef, rh = UserFactory(role=Role.FINANCES), UserFactory(role=Role.DIRECTION), UserFactory(role=Role.RH)
    facture = emise(prix="1000000", aujourd_hui=date(2026, 7, 1))  # échéance 31/07/2026
    services.enregistrer_reglement(
        facture, finance, montant=Decimal("180000"), mode=ModePaiement.VIREMENT, date_reglement=date(2026, 7, 5)
    )
    aujourd_hui = date(2026, 8, 10)

    premiere = taches.alerter_factures_echues(aujourd_hui=aujourd_hui)
    seconde = taches.alerter_factures_echues(aujourd_hui=aujourd_hui + timedelta(days=1))

    destinataires = User.objects.filter(role__in=[Role.FINANCES, Role.DIRECTION, Role.RH]).count()
    assert premiere == destinataires >= 3 and seconde == 0  # un message par compte, jamais renvoyé
    for compte in (finance, chef, rh):
        alerte = [n for n in _de(compte) if "échue" in n.titre][0]
        assert alerte.niveau == NiveauNotification.URGENT
        assert alerte.titre == f"Facture {facture.numero} échue : {facture.client.raison_sociale}"
        assert "1 000 000 FCFA" in alerte.message.replace("\xa0", " ").replace(" ", " ")
        assert "échue depuis 10 jours" in alerte.message
    # La FINANCES (et désormais la RH) peuvent confirmer le versement d'un clic ; la DIRECTION,
    # qui ne saisit pas, consulte la facture.
    for compte in (finance, rh):
        alerte = [n for n in _de(compte) if "échue" in n.titre][0]
        assert alerte.action == "Confirmer le versement"
        assert alerte.url == reverse("finance:versement_confirmer", args=[facture.pk])
    alerte_direction = [n for n in _de(chef) if "échue" in n.titre][0]
    assert alerte_direction.action == ""
    assert alerte_direction.url == reverse("billing:facture", args=[facture.pk])


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
python -m pytest apps/accounts/tests/test_web.py apps/billing/tests/test_proforma_views.py apps/billing/tests/test_views.py apps/core/tests/test_impression_listes.py apps/finance/tests/test_demandes_views.py apps/finance/tests/test_depenses_parc_auto.py apps/finance/tests/test_impression.py apps/finance/tests/test_versements.py apps/finance/tests/test_views.py apps/notifications/tests/test_facturation.py -q --no-cov
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
