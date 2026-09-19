from django import forms
from django.utils import timezone

from apps.core.forms import StyleTailwindMixin

from . import services
from .models import TVA_DEFAUT, MotifExoneration, TypeInteraction


def _libelle_compte(u) -> str:
    return u.get_full_name() or u.username


class ClientForm(StyleTailwindMixin, forms.Form):
    """Fiche client (cahier-des-charges.md:119-122)."""

    raison_sociale = forms.CharField(label="Raison sociale", max_length=200)
    ncc_nif = forms.CharField(label="NCC / NIF", max_length=50)
    contact_principal = forms.CharField(label="Contact principal", max_length=150)
    telephone = forms.CharField(label="Téléphone", max_length=20)
    email = forms.EmailField(label="Email", required=False)
    adresse = forms.CharField(label="Adresse / siège", widget=forms.Textarea(attrs={"rows": 2}))
    charge_clientele = forms.ModelChoiceField(
        label="Chargé clientèle attitré", queryset=None, required=False
    )
    taux_tva = forms.DecimalField(
        label="Taux de TVA (%)",
        min_value=0,
        max_value=100,
        max_digits=5,
        decimal_places=2,
        initial=TVA_DEFAUT,
        help_text="18 % par défaut ; 0 % pour un client exonéré (motif obligatoire).",
    )
    motif_exoneration = forms.ChoiceField(
        label="Motif d'exonération",
        choices=[("", "—")] + MotifExoneration.choices,
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["charge_clientele"].queryset = services.charges_clientele()
        self.fields["charge_clientele"].label_from_instance = _libelle_compte

    def clean(self):
        donnees = super().clean()
        taux = donnees.get("taux_tva")
        if taux is not None and taux == 0 and not donnees.get("motif_exoneration"):
            self.add_error("motif_exoneration", "Motif obligatoire quand la TVA est à 0 %.")
        return donnees


class InteractionForm(StyleTailwindMixin, forms.Form):
    """Interaction commerciale : appel, mail, réunion, devis, réclamation."""

    type_interaction = forms.ChoiceField(label="Type", choices=TypeInteraction.choices)
    date_interaction = forms.DateTimeField(
        label="Date et heure",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"],
    )
    resume = forms.CharField(label="Résumé de l'échange", widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date_interaction"].initial = timezone.localtime().strftime("%Y-%m-%dT%H:%M")


class FiltreClientsForm(forms.Form):
    """Filtres de la liste ; les paramètres invalides sont ignorés."""

    q = forms.CharField(required=False)
    mes_clients = forms.BooleanField(required=False)
    exonere = forms.BooleanField(required=False)

    def criteres(self, utilisateur) -> dict:
        self.is_valid()
        donnees = getattr(self, "cleaned_data", {})
        return {
            "recherche": donnees.get("q", ""),
            "charge_clientele": utilisateur if donnees.get("mes_clients") else None,
            "exonere": bool(donnees.get("exonere")),
        }
