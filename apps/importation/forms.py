from django import forms

from apps.core.forms import StyleTailwindMixin

TAILLE_MAX = 5 * 1024 * 1024  # 5 Mo : un classeur de collecte pèse quelques dizaines de ko


class ImportForm(StyleTailwindMixin, forms.Form):
    fichier = forms.FileField(label="Classeur Excel rempli (.xlsx)")
    simulation = forms.BooleanField(
        label="Simulation : vérifier le fichier sans rien enregistrer",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-slate-300"}),
    )

    def clean_fichier(self):
        fichier = self.cleaned_data["fichier"]
        if not fichier.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Le fichier doit être un classeur Excel (.xlsx).")
        if fichier.size > TAILLE_MAX:
            raise forms.ValidationError("Le fichier dépasse 5 Mo : ce n'est pas un classeur de collecte.")
        return fichier
