from django import forms

from apps.core.forms import StyleTailwindMixin
from apps.customers import services as customers_services
from apps.drivers import services as drivers_services
from apps.fleet import services as fleet_services


class MissionForm(StyleTailwindMixin, forms.Form):
    """Création d'une mission (cahier-des-charges.md:129-131)."""

    client = forms.ModelChoiceField(queryset=None, label="Client")
    # « list » relie le champ à la liste de suggestions « lieux-missions » (mission_form.html) :
    # les lieux déjà utilisés s'affichent dès les premières lettres, la saisie libre reste possible.
    lieu_chargement = forms.CharField(
        label="Lieu de chargement",
        max_length=200,
        widget=forms.TextInput(attrs={"list": "lieux-missions", "autocomplete": "off"}),
    )
    lieu_livraison = forms.CharField(
        label="Lieu de livraison",
        max_length=200,
        widget=forms.TextInput(attrs={"list": "lieux-missions", "autocomplete": "off"}),
    )
    nature_marchandise = forms.CharField(label="Nature de la marchandise", max_length=200)
    poids_t = forms.DecimalField(
        label="Poids (tonnes)", min_value=0, decimal_places=2, max_digits=8
    )
    prix_convenu = forms.DecimalField(
        label="Prix convenu (FCFA)", min_value=0, decimal_places=2, max_digits=12
    )
    date_depart_prevue = forms.DateField(
        label="Départ prévu",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Facultatif. Sert à repérer les conflits avec les congés des chauffeurs.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = customers_services.clients_pour_selection()


class AffectationForm(StyleTailwindMixin, forms.Form):
    """Affectation d'un camion et d'un chauffeur disponibles."""

    vehicule = forms.ModelChoiceField(queryset=None, label="Camion disponible")
    chauffeur = forms.ModelChoiceField(queryset=None, label="Chauffeur disponible")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vehicule"].queryset = fleet_services.vehicules_disponibles()
        self.fields["vehicule"].label_from_instance = lambda v: (
            f"{v.immatriculation} - {v.marque} {v.modele} ({v.capacite_charge_t} t)"
        )
        self.fields["chauffeur"].queryset = drivers_services.chauffeurs_disponibles()


class CodeForm(StyleTailwindMixin, forms.Form):
    """Saisie du code remis à l'expéditeur ou au destinataire."""

    code = forms.CharField(
        label="Code", max_length=12, widget=forms.TextInput(attrs={"autocomplete": "off"})
    )


class LivraisonForm(CodeForm):
    km_arrivee = forms.IntegerField(label="Kilométrage à l'arrivée", min_value=0)
