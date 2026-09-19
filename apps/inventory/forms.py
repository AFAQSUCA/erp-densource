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


class ArticleForm(StyleTailwindMixin, forms.Form):
    """Fiche article (cahier-des-charges.md:177-178)."""

    designation = forms.CharField(label="Désignation", max_length=200)
    categorie = forms.CharField(label="Catégorie", max_length=100, required=False)
    emplacement = forms.CharField(label="Emplacement", max_length=100, required=False)
    seuil_minimal = forms.IntegerField(
        label="Seuil minimal",
        min_value=0,
        initial=0,
        help_text="Une alerte s'affiche quand le stock atteint ce niveau. 0 = pas d'alerte.",
    )


class ArticleCreationForm(ArticleForm):
    """Création : la référence se saisit une seule fois, elle ne change plus ensuite."""

    reference = forms.CharField(label="Référence", max_length=50)
    field_order = ["reference", "designation", "categorie", "emplacement", "seuil_minimal"]


class EntreeForm(StyleTailwindMixin, forms.Form):
    """Entrée en stock (achat) : le PUMP est recalculé avec le prix d'achat."""

    quantite = forms.IntegerField(label="Quantité achetée", min_value=1)
    prix_unitaire = forms.DecimalField(
        label="Prix d'achat unitaire (FCFA)",
        min_value=0,
        decimal_places=2,
        max_digits=12,
    )


class AjustementForm(StyleTailwindMixin, forms.Form):
    """Ajustement d'inventaire : correction (+ ou -), toujours justifiée."""

    variation = forms.IntegerField(
        label="Variation (+ pour ajouter, - pour retirer)",
        help_text="Écart constaté entre le stock informatique et le stock compté.",
    )
    motif = forms.CharField(label="Motif", widget=forms.Textarea(attrs={"rows": 2}))

    def clean_variation(self):
        variation = self.cleaned_data["variation"]
        if variation == 0:
            raise forms.ValidationError("La variation ne peut pas être nulle.")
        return variation
