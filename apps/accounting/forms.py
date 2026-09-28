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
