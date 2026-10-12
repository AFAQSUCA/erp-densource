from django import forms

from apps.core.forms import StyleTailwindMixin

from .models import Parametres
from .services import CHAMPS


class ParametresForm(StyleTailwindMixin, forms.ModelForm):
    """Contrôle de forme seulement (types, bornes du modèle) : la cohérence entre seuils est vérifiée par
    ``services.modifier_parametres``."""

    class Meta:
        model = Parametres
        fields = CHAMPS
