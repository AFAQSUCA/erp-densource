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
