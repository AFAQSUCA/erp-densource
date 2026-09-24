"""Les champs date préremplis s'affichent : ``<input type="date">`` exige AAAA-MM-JJ, même en français."""

from datetime import date

import pytest
from django import forms
from django.utils import translation

from apps.billing.forms import ReglementForm
from apps.core.forms import StyleTailwindMixin
from apps.mobile_api.forms import PleinChauffeurForm


class _Formulaire(StyleTailwindMixin, forms.Form):
    jour = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    texte = forms.DateField(widget=forms.DateInput())  # champ texte : format de la langue conservé


def test_la_date_initiale_est_ecrite_au_format_attendu_par_le_navigateur():
    with translation.override("fr"):
        html = str(_Formulaire(initial={"jour": date(2026, 9, 24)})["jour"])

    assert 'value="2026-09-24"' in html


def test_un_champ_date_sans_type_date_garde_le_format_de_la_langue():
    with translation.override("fr"):
        html = str(_Formulaire(initial={"texte": date(2026, 9, 24)})["texte"])

    assert 'value="24/09/2026"' in html


def test_le_reglement_prerempli_avec_la_date_du_jour():
    with translation.override("fr"):
        html = str(ReglementForm(initial={"date_reglement": date(2026, 9, 24)})["date_reglement"])

    assert 'value="2026-09-24"' in html


@pytest.mark.django_db
def test_l_espace_mobile_utilise_le_meme_format():
    with translation.override("fr"):
        html = str(PleinChauffeurForm(initial={"date_plein": date(2026, 9, 24)})["date_plein"])

    assert 'value="2026-09-24"' in html
