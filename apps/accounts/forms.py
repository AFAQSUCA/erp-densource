from django import forms

from apps.core.forms import StyleTailwindMixin

from .models import Role


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


class _CoordonneesForm(StyleTailwindMixin, forms.Form):
    first_name = forms.CharField(label="Prénom", max_length=150)
    last_name = forms.CharField(label="Nom", max_length=150)
    email = forms.EmailField(label="Adresse e-mail", help_text="Sert à réinitialiser le mot de passe.")
    telephone = forms.CharField(label="Téléphone", max_length=20, required=False)
    role = forms.ChoiceField(label="Rôle", choices=Role.choices)


class UtilisateurCreationForm(_CoordonneesForm):
    """Nouveau compte : identifiant, coordonnées, rôle et mot de passe initial (à changer par la personne)."""

    username = forms.CharField(label="Identifiant de connexion", max_length=150)
    password1 = forms.CharField(
        label="Mot de passe initial", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="10 caractères au moins, ni trop courant, ni uniquement des chiffres, ni proche de l'identifiant.",
    )
    password2 = forms.CharField(
        label="Confirmer le mot de passe", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"})
    )
    field_order = ["username", "first_name", "last_name", "email", "telephone", "role", "password1", "password2"]

    def clean(self):
        donnees = super().clean()
        if donnees.get("password1") and donnees.get("password2") and donnees["password1"] != donnees["password2"]:
            self.add_error("password2", "Les deux mots de passe ne correspondent pas.")
        return donnees


class UtilisateurModificationForm(_CoordonneesForm):
    """Coordonnées et rôle d'un compte existant (l'identifiant et le mot de passe ne se changent pas ici)."""


class FiltreUtilisateursForm(StyleTailwindMixin, forms.Form):
    q = forms.CharField(label="Recherche", required=False)
    role = forms.ChoiceField(label="Rôle", choices=[("", "Tous les rôles")] + list(Role.choices), required=False)
    actif = forms.ChoiceField(
        label="Statut", choices=[("", "Tous"), ("oui", "Actifs"), ("non", "Désactivés")], required=False
    )
