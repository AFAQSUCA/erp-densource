from django import forms
from django.utils import timezone

from apps.core.forms import StyleTailwindMixin
from apps.drivers import services as drivers_services
from apps.fleet import services as fleet_services


def _libelle_camion(v):
    return f"{v.immatriculation} - {v.marque} {v.modele}"


def _libelle_chauffeur(c):
    return f"{c.personnel.prenom} {c.personnel.nom} ({c.personnel.matricule})"


class PleinForm(StyleTailwindMixin, forms.Form):
    """Saisie d'un plein (cahier-des-charges.md:148-150)."""

    vehicule = forms.ModelChoiceField(label="Camion", queryset=None)
    chauffeur = forms.ModelChoiceField(label="Chauffeur", queryset=None)
    date_plein = forms.DateField(
        label="Date du plein", widget=forms.DateInput(attrs={"type": "date"})
    )
    station = forms.CharField(label="Station", max_length=100)
    quantite_litres = forms.DecimalField(
        label="Quantité (litres)", min_value=0, decimal_places=2, max_digits=8
    )
    prix_unitaire = forms.DecimalField(
        label="Prix unitaire (FCFA / litre)", min_value=0, decimal_places=2, max_digits=10
    )
    km_compteur = forms.IntegerField(label="Kilométrage du compteur", min_value=0)
    numero_ticket = forms.CharField(label="N° de ticket / reçu", max_length=50)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vehicule"].queryset = fleet_services.vehicules_queryset().order_by(
            "immatriculation"
        )
        self.fields["vehicule"].label_from_instance = _libelle_camion
        self.fields["chauffeur"].queryset = drivers_services.chauffeurs_actifs()
        self.fields["chauffeur"].label_from_instance = _libelle_chauffeur

    def clean_date_plein(self):
        date_plein = self.cleaned_data["date_plein"]
        if date_plein > timezone.localdate():
            raise forms.ValidationError("La date du plein ne peut pas être dans le futur.")
        return date_plein


class FiltrePleinsForm(StyleTailwindMixin, forms.Form):
    """Filtres de la liste (GET). Une valeur invalide est simplement ignorée."""

    ALERTES = [
        ("", "Toutes"),
        ("A_SURVEILLER", "À surveiller (toutes alertes)"),
        ("JAUNE", "Alerte jaune (> +20 %)"),
        ("ROUGE", "Alerte rouge (> +40 %)"),
        ("ANOMALIE", "Anomalie (> 45 ou < 20 L/100 km)"),
        ("SAISIE", "Saisie suspecte confirmée"),
    ]

    q = forms.CharField(label="Rechercher", required=False)
    vehicule = forms.ModelChoiceField(label="Camion", queryset=None, required=False, empty_label="Tous")
    chauffeur = forms.ModelChoiceField(label="Chauffeur", queryset=None, required=False, empty_label="Tous")
    date_debut = forms.DateField(
        label="Du", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    date_fin = forms.DateField(
        label="Au", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    alerte = forms.ChoiceField(label="Alerte", choices=ALERTES, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vehicule"].queryset = fleet_services.vehicules_queryset().order_by(
            "immatriculation"
        )
        self.fields["vehicule"].label_from_instance = _libelle_camion
        self.fields["chauffeur"].queryset = drivers_services.chauffeurs_actifs()
        self.fields["chauffeur"].label_from_instance = _libelle_chauffeur

    def criteres(self) -> dict:
        """Critères prêts pour ``services.rechercher_pleins``.

        ``is_valid()`` remplit ``cleaned_data`` avec les seuls champs valides : un
        paramètre d'URL invalide est donc ignoré au lieu de faire échouer la page.
        """
        self.is_valid()
        donnees = self.cleaned_data
        return {
            "recherche": donnees.get("q") or "",
            "vehicule": donnees.get("vehicule"),
            "chauffeur": donnees.get("chauffeur"),
            "date_debut": donnees.get("date_debut"),
            "date_fin": donnees.get("date_fin"),
            "alerte": donnees.get("alerte") or "",
        }
