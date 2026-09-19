from datetime import date

from django import forms
from django.core.validators import MaxValueValidator

from apps.core.forms import StyleTailwindMixin
from apps.drivers import services as drivers_services

from .models import TypeDocument


class VehiculeForm(StyleTailwindMixin, forms.Form):
    """Fiche véhicule (cahier-des-charges.md:88-90)."""

    immatriculation = forms.CharField(label="Immatriculation", max_length=20)
    marque = forms.CharField(label="Marque", max_length=50)
    modele = forms.CharField(label="Modèle", max_length=50)
    annee = forms.IntegerField(label="Année", min_value=1950)
    vin = forms.CharField(label="N° de châssis (VIN)", max_length=17)
    kilometrage = forms.IntegerField(label="Kilométrage du compteur", min_value=0, initial=0)
    capacite_charge_t = forms.DecimalField(
        label="Capacité de charge (tonnes)", min_value=0, decimal_places=2, max_digits=6
    )
    reservoir_l = forms.IntegerField(label="Réservoir (litres)", min_value=1)
    chauffeur_habituel = forms.ModelChoiceField(
        label="Chauffeur habituel", queryset=None, required=False, empty_label="Aucun"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        annee_max = date.today().year + 1
        self.fields["annee"].validators.append(MaxValueValidator(annee_max))
        self.fields["annee"].widget.attrs["max"] = annee_max
        self.fields["chauffeur_habituel"].queryset = drivers_services.chauffeurs_actifs()
        self.fields["chauffeur_habituel"].label_from_instance = lambda c: (
            f"{c.personnel.prenom} {c.personnel.nom} ({c.personnel.matricule})"
        )


class DocumentForm(StyleTailwindMixin, forms.Form):
    """Enregistrement ou renouvellement d'un document réglementaire."""

    type_document = forms.ChoiceField(label="Document", choices=TypeDocument.choices)
    date_delivrance = forms.DateField(
        label="Date de délivrance", widget=forms.DateInput(attrs={"type": "date"})
    )
    date_expiration = forms.DateField(
        label="Date d'expiration", widget=forms.DateInput(attrs={"type": "date"})
    )
