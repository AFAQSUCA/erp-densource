from django import forms

from apps.core.forms import StyleTailwindMixin

from . import services
from .models import CategoriePermis, StatutChauffeur


class ChauffeurForm(StyleTailwindMixin, forms.Form):
    """Informations propres au chauffeur (cahier-des-charges.md:109-111).

    Matricule, nom et prénom viennent de la fiche du personnel : ils ne sont pas
    modifiables ici.
    """

    telephone = forms.CharField(label="Téléphone", max_length=20, required=False)
    contact_urgence = forms.CharField(label="Contact d'urgence", max_length=150, required=False)
    numero_permis = forms.CharField(label="N° de permis", max_length=50, required=False)
    categories_permis = forms.MultipleChoiceField(
        label="Catégories de permis",
        choices=CategoriePermis.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    date_expiration_permis = forms.DateField(
        label="Expiration du permis",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    date_expiration_visite_medicale = forms.DateField(
        label="Expiration de la visite médicale",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categories_permis"].widget.attrs["class"] = (
            "h-4 w-4 rounded border-slate-400 text-marque-700 focus:ring-marque-600"
        )


class StatutForm(StyleTailwindMixin, forms.Form):
    """Statuts qui se posent à la main (les autres viennent des missions et congés)."""

    statut = forms.ChoiceField(
        label="Nouveau statut",
        choices=[
            (code, libelle)
            for code, libelle in StatutChauffeur.choices
            if code in services.STATUTS_MANUELS
        ],
    )
