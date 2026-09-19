from django import forms
from django.utils import timezone

from apps.core.forms import StyleTailwindMixin

from . import services
from .models import Departement, Personnel


class CongeForm(StyleTailwindMixin, forms.Form):
    """Demande de congé : dates et motif (cahier-des-charges.md:212)."""

    date_debut = forms.DateField(
        label="Premier jour de congé", widget=forms.DateInput(attrs={"type": "date"})
    )
    date_fin = forms.DateField(
        label="Dernier jour de congé", widget=forms.DateInput(attrs={"type": "date"})
    )
    motif = forms.CharField(label="Motif", widget=forms.Textarea(attrs={"rows": 3}))

    def clean(self):
        donnees = super().clean()
        debut, fin = donnees.get("date_debut"), donnees.get("date_fin")
        if debut and fin and fin < debut:
            self.add_error("date_fin", "La date de fin précède la date de début.")
        return donnees


class DecisionForm(StyleTailwindMixin, forms.Form):
    """Décision sur un congé : valider, refuser ou annuler (avec commentaire)."""

    action = forms.ChoiceField(
        choices=[
            (services.ACTION_VALIDER, "Valider"),
            (services.ACTION_REFUSER, "Refuser"),
            (services.ACTION_ANNULER, "Annuler"),
        ],
        widget=forms.HiddenInput,
    )
    commentaire = forms.CharField(
        label="Commentaire", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )

    def clean(self):
        donnees = super().clean()
        action = donnees.get("action")
        if (
            action in (services.ACTION_REFUSER, services.ACTION_ANNULER)
            and not donnees.get("commentaire", "").strip()
        ):
            self.add_error("commentaire", "Indiquez le motif : il sera communiqué à l'employé.")
        return donnees


class AttributionForm(StyleTailwindMixin, forms.Form):
    """Jours de congé exceptionnels accordés par la RH (motif obligatoire)."""

    annee = forms.IntegerField(label="Année", min_value=2000, max_value=2100)
    jours = forms.IntegerField(label="Jours ouvrables accordés", min_value=1, max_value=60)
    motif = forms.CharField(label="Motif", widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["annee"].initial = timezone.localdate().year


def _libelle_employe(p: Personnel) -> str:
    return f"{p.prenom} {p.nom} ({p.matricule})"


def _libelle_compte(u) -> str:
    return f"{u.get_full_name() or u.username} - {u.get_role_display()}"


class PersonnelForm(StyleTailwindMixin, forms.Form):
    """Recrutement ou modification d'une fiche (cahier-des-charges.md:206-210).

    À la modification, le matricule et la date d'embauche ne se changent pas.
    """

    matricule = forms.CharField(label="Matricule", max_length=20)
    nom = forms.CharField(label="Nom", max_length=100)
    prenom = forms.CharField(label="Prénom", max_length=100)
    poste = forms.CharField(label="Poste", max_length=100)
    departement = forms.ChoiceField(label="Département", choices=Departement.choices)
    type_contrat = forms.CharField(
        label="Type de contrat", max_length=30, required=False, help_text="Ex. : CDI, CDD, stage."
    )
    date_embauche = forms.DateField(
        label="Date d'embauche", widget=forms.DateInput(attrs={"type": "date"})
    )
    salaire_base = forms.DecimalField(
        label="Salaire de base (FCFA)", min_value=0, max_digits=12, decimal_places=2
    )
    superieur = forms.ModelChoiceField(
        label="Supérieur hiérarchique",
        queryset=None,
        required=False,
        help_text="Il valide en N1 les congés de cet employé. Vide uniquement pour le directeur.",
    )
    utilisateur = forms.ModelChoiceField(
        label="Compte utilisateur",
        queryset=None,
        required=False,
        help_text="Nécessaire pour que l'employé demande ou valide des congés.",
    )

    def __init__(self, *args, personnel: Personnel | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.personnel = personnel
        superieurs = services.personnel_queryset().order_by("nom", "prenom")
        if personnel is not None:
            superieurs = superieurs.exclude(pk=personnel.pk)
            del self.fields["matricule"]
            del self.fields["date_embauche"]
        self.fields["superieur"].queryset = superieurs
        self.fields["superieur"].label_from_instance = _libelle_employe
        self.fields["utilisateur"].queryset = services.comptes_disponibles(garder=personnel)
        self.fields["utilisateur"].label_from_instance = _libelle_compte
