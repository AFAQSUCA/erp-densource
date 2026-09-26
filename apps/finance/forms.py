from django import forms
from django.utils import timezone

from apps.billing.models import CATEGORIES_AUTOMATIQUES, CategorieDepense, CompteTresorerie, ModePaiement
from apps.core.forms import StyleTailwindMixin
from apps.fleet import services as fleet_services

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


CATEGORIES_PARC_AUTO = [c for c in CategorieDepense.choices if c[0] in CATEGORIES_AUTOMATIQUES]


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
