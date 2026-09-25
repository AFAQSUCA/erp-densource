"""Filtres du journal d'audit."""

from django import forms

from apps.core.forms import StyleTailwindMixin

from .models import ActionChoices, StatutChoices


class FiltreJournalForm(StyleTailwindMixin, forms.Form):
    """Filtres de la liste ; un paramètre invalide est ignoré."""

    q = forms.CharField(label="Rechercher", required=False, help_text="Utilisateur, entité, adresse IP…")
    module = forms.ChoiceField(label="Module", choices=[("", "Tous")], required=False)
    action = forms.ChoiceField(label="Action", choices=[("", "Toutes")] + ActionChoices.choices, required=False)
    statut = forms.ChoiceField(label="Statut", choices=[("", "Tous")] + StatutChoices.choices, required=False)
    date_debut = forms.DateField(label="Du", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    date_fin = forms.DateField(label="Au", required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, modules=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["module"].choices = [("", "Tous")] + [(m, m) for m in modules]

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
            "recherche": donnees.get("q") or "",
            "module": donnees.get("module") or "",
            "action": donnees.get("action") or "",
            "statut": donnees.get("statut") or "",
            "date_debut": donnees.get("date_debut"),
            "date_fin": donnees.get("date_fin"),
        }
