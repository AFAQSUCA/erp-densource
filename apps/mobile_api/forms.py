"""Formulaires de l'espace mobile du chauffeur (grands champs tactiles)."""

from django import forms
from django.utils import timezone

from apps.core.forms import corriger_format_date
from apps.garage.models import POINTS_CHECKLIST, GraviteIncident, TypeIncident

CHAMP_TACTILE = (
    "block w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-base text-slate-900 "
    "shadow-sm placeholder:text-slate-400 focus:border-marque-600 focus:outline-none "
    "focus:ring-2 focus:ring-marque-600/30"
)


class StyleTactileMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in self.fields.values():
            champ.widget.attrs.setdefault("class", CHAMP_TACTILE)
            corriger_format_date(champ.widget)


class CodeForm(StyleTactileMixin, forms.Form):
    code = forms.CharField(
        label="Code", max_length=12,
        widget=forms.TextInput(attrs={"autocomplete": "off", "autocapitalize": "characters",
                                      "inputmode": "text", "class": CHAMP_TACTILE + " text-center font-mono text-2xl tracking-widest"}),
    )


class LivraisonForm(CodeForm):
    km_arrivee = forms.IntegerField(
        label="Kilométrage à l'arrivée", min_value=0,
        widget=forms.NumberInput(attrs={"inputmode": "numeric"}),
    )


class PleinChauffeurForm(StyleTactileMixin, forms.Form):
    station = forms.CharField(label="Station", max_length=100)
    quantite_litres = forms.DecimalField(
        label="Litres", min_value=0, decimal_places=2, max_digits=8,
        widget=forms.NumberInput(attrs={"inputmode": "decimal", "step": "0.01"}),
    )
    prix_unitaire = forms.DecimalField(
        label="Prix du litre (FCFA)", min_value=0, decimal_places=2, max_digits=10,
        widget=forms.NumberInput(attrs={"inputmode": "decimal", "step": "0.01"}),
    )
    km_compteur = forms.IntegerField(
        label="Kilométrage du compteur", min_value=0, widget=forms.NumberInput(attrs={"inputmode": "numeric"})
    )
    numero_ticket = forms.CharField(label="N° du ticket ou du reçu", max_length=50)
    date_plein = forms.DateField(label="Date", widget=forms.DateInput(attrs={"type": "date"}))

    def clean_date_plein(self):
        jour = self.cleaned_data["date_plein"]
        if jour > timezone.localdate():
            raise forms.ValidationError("La date du plein ne peut pas être dans le futur.")
        return jour


class IncidentChauffeurForm(StyleTactileMixin, forms.Form):
    type_incident = forms.ChoiceField(label="Nature", choices=TypeIncident.choices)
    gravite = forms.ChoiceField(label="Gravité", choices=GraviteIncident.choices)
    description = forms.CharField(label="Ce qui s'est passé", widget=forms.Textarea(attrs={"rows": 4}))
    lieu = forms.CharField(label="Où êtes-vous ?", max_length=200, required=False)
    mission = forms.TypedChoiceField(label="Mission concernée", required=False, coerce=int, empty_value=None)

    def __init__(self, *args, missions=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["mission"].choices = [("", "Aucune")] + [
            (m.pk, f"{m.numero} : {m.lieu_chargement} → {m.lieu_livraison}") for m in missions
        ]


class FraisImprevuChauffeurForm(StyleTactileMixin, forms.Form):
    """Déclaration d'un imprévu (panne, incident) sur la mission en cours, avec une preuve."""

    mission = forms.TypedChoiceField(label="Mission concernée", coerce=int)
    montant = forms.DecimalField(
        label="Montant (FCFA)", min_value=0, decimal_places=2, max_digits=12,
        widget=forms.NumberInput(attrs={"inputmode": "decimal", "step": "1"}),
    )
    description = forms.CharField(label="Ce qui s'est passé", widget=forms.Textarea(attrs={"rows": 3}))
    justificatif = forms.FileField(label="Preuve (photo, facture)")

    def __init__(self, *args, missions=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["mission"].choices = [
            (m.pk, f"{m.numero} : {m.lieu_chargement} → {m.lieu_livraison}") for m in missions
        ]
        self.fields["justificatif"].widget.attrs["class"] = "block w-full text-sm text-slate-700"


class ChecklistForm(forms.Form):
    """Un choix OK / KO par point, et une remarque (obligatoire si KO, contrôlé par le service)."""

    remarque = forms.CharField(label="Remarque générale", required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["remarque"].widget.attrs["class"] = CHAMP_TACTILE
        for code, libelle in POINTS_CHECKLIST:
            self.fields[f"ok_{code}"] = forms.ChoiceField(
                label=libelle, choices=[("1", "OK"), ("0", "KO")], widget=forms.RadioSelect
            )
            self.fields[f"remarque_{code}"] = forms.CharField(
                label="Problème constaté", required=False,
                widget=forms.TextInput(attrs={"class": CHAMP_TACTILE, "placeholder": "Décrivez le problème"}),
            )

    def points(self):
        """Les 8 points, pour l'affichage : (code, libellé, champ OK/KO, champ remarque)."""
        return [
            (code, libelle, self[f"ok_{code}"], self[f"remarque_{code}"])
            for code, libelle in POINTS_CHECKLIST
        ]

    def resultats(self) -> list[dict]:
        return [
            {
                "code": code,
                "ok": self.cleaned_data[f"ok_{code}"] == "1",
                "remarque": self.cleaned_data.get(f"remarque_{code}", ""),
            }
            for code, _libelle in POINTS_CHECKLIST
        ]
