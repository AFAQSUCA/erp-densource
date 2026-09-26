from django import forms
from django.utils import timezone

from apps.core.forms import StyleTailwindMixin

from . import services
from .models import Departement, Personnel, POSTES_COURANTS

POSTE_AUTRE = "AUTRE"


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


class ReportForm(StyleTailwindMixin, forms.Form):
    """Demande de report du solde non pris d'un congé en cours (avenant § R7)."""

    nouvelle_date_fin = forms.DateField(
        label="Je reprends le travail le", widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Dernier jour de congé réellement pris ; les jours ouvrés restants jusqu'à la fin "
        "initialement prévue vous sont reversés une fois la RH d'accord.",
    )
    motif = forms.CharField(label="Motif", widget=forms.Textarea(attrs={"rows": 3}))


class DecisionReportForm(StyleTailwindMixin, forms.Form):
    """Décision de la RH sur une demande de report : valider ou refuser (motif obligatoire)."""

    action = forms.ChoiceField(
        choices=[("valider", "Valider"), ("refuser", "Refuser")], widget=forms.HiddenInput,
    )
    commentaire = forms.CharField(
        label="Commentaire", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )

    def clean(self):
        donnees = super().clean()
        if donnees.get("action") == "refuser" and not donnees.get("commentaire", "").strip():
            self.add_error("commentaire", "Indiquez le motif du refus : il sera visible par l'employé.")
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

    Le matricule n'est jamais un champ du formulaire : ``services.recruter`` le génère
    automatiquement (``PERS-AAAA-XXXX``). À la modification, la date d'embauche ne change pas non
    plus (champ retiré ci-dessous).
    """

    nom = forms.CharField(label="Nom", max_length=100)
    prenom = forms.CharField(label="Prénom", max_length=100)
    poste = forms.ChoiceField(
        label="Poste",
        choices=[(p, p) for p in POSTES_COURANTS] + [(POSTE_AUTRE, "Autre…")],
        widget=forms.Select(attrs={"x-ref": "poste", "x-model": "poste", "@change": "poste = $event.target.value"}),
    )
    poste_autre = forms.CharField(
        label="Préciser le poste",
        max_length=100,
        required=False,
        help_text="Le poste n'apparaît pas dans la liste ci-dessus.",
    )
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
            del self.fields["date_embauche"]
            if personnel.poste not in POSTES_COURANTS:
                # Poste antérieur hors liste (saisi avant l'existence de la liste, ou via « Autre ») :
                # préremplir « Autre » + son intitulé, plutôt que de perdre la valeur ou de refuser
                # la fiche à la prochaine modification qui ne touche pas ce champ.
                self.initial["poste"] = POSTE_AUTRE
                self.initial["poste_autre"] = personnel.poste
        self.fields["superieur"].queryset = superieurs
        self.fields["superieur"].label_from_instance = _libelle_employe
        self.fields["utilisateur"].queryset = services.comptes_disponibles(garder=personnel)
        self.fields["utilisateur"].label_from_instance = _libelle_compte

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("poste") == POSTE_AUTRE:
            autre = cleaned.get("poste_autre", "").strip()
            if not autre:
                self.add_error("poste_autre", "Précisez le poste.")
            else:
                cleaned["poste"] = autre
        cleaned.pop("poste_autre", None)  # jamais transmis à services.recruter/modifier_personnel
        return cleaned


class ImportPersonnelForm(StyleTailwindMixin, forms.Form):
    """Recrutement en masse : un classeur Excel (.xlsx), colonnes voir services.COLONNES_IMPORT."""

    fichier = forms.FileField(
        label="Fichier Excel (.xlsx)",
        help_text="Téléchargez le modèle ci-dessous, remplissez-le, puis déposez-le ici.",
    )

    def clean_fichier(self):
        fichier = self.cleaned_data["fichier"]
        if not fichier.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Le fichier doit être un classeur Excel (.xlsx).")
        return fichier
