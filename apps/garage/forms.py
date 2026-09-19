from django import forms

from apps.core.forms import StyleTailwindMixin
from apps.fleet import services as fleet_services

from .models import LieuReparation, TypeOr


class OrForm(StyleTailwindMixin, forms.Form):
    """Ouverture d'un ordre de réparation (cahier-des-charges.md:163-165)."""

    vehicule = forms.ModelChoiceField(label="Camion", queryset=None)
    type_or = forms.ChoiceField(label="Type d'intervention", choices=TypeOr.choices)
    lieu = forms.ChoiceField(label="Lieu de la réparation", choices=LieuReparation.choices)
    motif = forms.CharField(
        label="Motif / symptômes", widget=forms.Textarea(attrs={"rows": 4})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vehicule"].queryset = fleet_services.vehicules_queryset().order_by(
            "immatriculation"
        )
        self.fields["vehicule"].label_from_instance = lambda v: (
            f"{v.immatriculation} - {v.marque} {v.modele} ({v.get_statut_display()})"
        )


class ClotureForm(StyleTailwindMixin, forms.Form):
    """Clôture : saisie de la main-d'œuvre (les pièces se déduisent du stock)."""

    cout_main_oeuvre = forms.DecimalField(
        label="Coût de la main-d'œuvre (FCFA)",
        min_value=0,
        decimal_places=2,
        max_digits=12,
        initial=0,
    )
