from django import forms

from apps.core.forms import StyleTailwindMixin

from .models import GraviteIncident, StatutIncident

ACTION_PRENDRE, ACTION_CLORE = "prendre", "clore"


class FiltreIncidentsForm(StyleTailwindMixin, forms.Form):
    """Filtres de la liste ; un paramètre invalide est ignoré."""

    q = forms.CharField(label="Rechercher", required=False)
    statut = forms.ChoiceField(
        label="Statut", choices=[("", "Tous les statuts")] + StatutIncident.choices, required=False
    )
    gravite = forms.ChoiceField(
        label="Gravité", choices=[("", "Toutes")] + GraviteIncident.choices, required=False
    )

    def criteres(self) -> dict:
        self.is_valid()
        donnees = getattr(self, "cleaned_data", {})
        return {
            "recherche": donnees.get("q") or "",
            "statut": donnees.get("statut") or "",
            "gravite": donnees.get("gravite") or "",
        }


class TraitementIncidentForm(StyleTailwindMixin, forms.Form):
    """Prise en compte ou clôture d'un incident, avec la suite donnée."""

    action = forms.ChoiceField(
        choices=[(ACTION_PRENDRE, "Prendre en compte"), (ACTION_CLORE, "Clore")],
        widget=forms.HiddenInput,
    )
    note = forms.CharField(
        label="Suite donnée", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )

    def clean(self):
        donnees = super().clean()
        if donnees.get("action") == ACTION_CLORE and not donnees.get("note", "").strip():
            self.add_error("note", "Indiquez la suite donnée pour clore l'incident.")
        return donnees


class FiltreChecklistsForm(StyleTailwindMixin, forms.Form):
    q = forms.CharField(label="Rechercher", required=False)
    anomalies = forms.BooleanField(label="Avec points KO seulement", required=False)

    def criteres(self) -> dict:
        self.is_valid()
        donnees = getattr(self, "cleaned_data", {})
        return {"recherche": donnees.get("q") or "", "avec_anomalies": bool(donnees.get("anomalies"))}
