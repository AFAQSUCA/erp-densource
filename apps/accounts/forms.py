from django import forms

from apps.core.forms import StyleTailwindMixin


class CodeMFAForm(StyleTailwindMixin, forms.Form):
    """Code à 6 chiffres de l'application, ou code de secours (XXXXX-XXXXX)."""

    code = forms.CharField(
        label="Code",
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "one-time-code",
                "inputmode": "text",
                "autofocus": True,
                "placeholder": "123456",
                "spellcheck": "false",
            }
        ),
    )

    def clean_code(self):
        return self.cleaned_data["code"].strip()
