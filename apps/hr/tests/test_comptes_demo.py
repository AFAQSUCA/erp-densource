"""Commande ``creer_comptes_demo`` : un compte par rôle, hiérarchie utilisable pour les congés."""

from datetime import date, datetime
from datetime import timezone as dt_timezone
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import Role, User
from apps.drivers.models import Chauffeur
from apps.hr import services
from apps.hr.models import Personnel, StatutConge

pytestmark = pytest.mark.django_db

MAINTENANT = datetime(2026, 9, 1, 8, 0, tzinfo=dt_timezone.utc)


def _lancer(settings, *args):
    settings.DEBUG = True
    sortie = StringIO()
    call_command("creer_comptes_demo", *args, stdout=sortie)
    return sortie.getvalue()


def test_la_commande_est_refusee_hors_developpement(settings):
    settings.DEBUG = False

    with pytest.raises(CommandError, match="développement"):
        call_command("creer_comptes_demo", stdout=StringIO())
    assert not User.objects.exists()


def test_un_compte_par_role_avec_le_mot_de_passe_donne(settings):
    sortie = _lancer(settings, "--mot-de-passe", "Essai-2026!")

    assert {u.role for u in User.objects.all()} == set(Role.values)
    assert User.objects.count() == 7
    assert all(u.check_password("Essai-2026!") for u in User.objects.all())
    assert "Essai-2026!" in sortie
    assert User.objects.get(username="demo_admin").is_staff
    assert not User.objects.get(username="demo_rh").is_staff


def test_un_mot_de_passe_est_genere_quand_il_n_est_pas_donne(settings):
    sortie = _lancer(settings)

    mot_de_passe = sortie.rsplit(":", 1)[1].strip()
    assert len(mot_de_passe) >= 12
    assert User.objects.get(username="demo_rh").check_password(mot_de_passe)


def test_la_commande_est_rejouable_sans_doublon(settings):
    _lancer(settings, "--mot-de-passe", "Premier-1")
    _lancer(settings, "--mot-de-passe", "Second-2")

    assert User.objects.count() == 7 and Personnel.objects.count() == 7
    assert User.objects.get(username="demo_rh").check_password("Second-2")


def test_les_fiches_suivent_la_hierarchie_et_le_chauffeur_a_sa_fiche(settings):
    _lancer(settings)

    direction = Personnel.objects.get(utilisateur__username="demo_direction")
    assert direction.superieur is None
    assert Personnel.objects.get(utilisateur__username="demo_rh").superieur == direction
    parc = Personnel.objects.get(utilisateur__username="demo_parcauto")
    assert Personnel.objects.get(utilisateur__username="demo_chauffeur").superieur == parc
    assert Chauffeur.objects.filter(personnel__utilisateur__username="demo_chauffeur").exists()


def test_le_workflow_de_conges_fonctionne_avec_ces_comptes(settings):
    _lancer(settings)
    employe = Personnel.objects.get(utilisateur__username="demo_charge")
    conge = services.demander_conge(
        employe, date_debut=date(2026, 10, 5), date_fin=date(2026, 10, 9), motif="Essai",
        maintenant=MAINTENANT,
    )

    services.valider_n1(conge, User.objects.get(username="demo_direction"), maintenant=MAINTENANT)
    services.valider_n2(conge, User.objects.get(username="demo_rh"))

    assert conge.statut == StatutConge.APPROUVE
