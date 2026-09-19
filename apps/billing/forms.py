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
