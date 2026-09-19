from django import forms

from apps.core.forms import StyleTailwindMixin

from . import services


class SortieForm(StyleTailwindMixin, forms.Form):
    """Sortie de pièces pour un OR (cahier-des-charges.md:180-181)."""

    article = forms.ModelChoiceField(label="Pièce", queryset=None)
    quantite = forms.IntegerField(label="Quantité", min_value=1, initial=1)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["article"].queryset = services.articles_en_stock()
        self.fields["article"].label_from_instance = lambda a: (
            f"{a.reference} - {a.designation} ({a.quantite} en stock)"
        )
