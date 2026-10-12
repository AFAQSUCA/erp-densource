"""Jours fériés entretenus par la RH depuis l'application — audit M11-26.

Le décompte des congés exclut les jours fériés enregistrés : sans saisie ni génération, il n'en exclut aucun.
"""

from datetime import date

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.hr import services
from apps.hr.exceptions import JourFerieInvalide
from apps.hr.models import JourFerie
from apps.notifications.taches import executer_taches_quotidiennes

pytestmark = pytest.mark.django_db

TABASKI = date(2026, 5, 27)


def _rh():
    return UserFactory(role=Role.RH)


# --- services ---


def test_la_rh_ajoute_une_fete_musulmane_et_le_decompte_en_tient_compte():
    assert services.calculer_jours(date(2026, 5, 25), date(2026, 5, 29)) == 5

    services.ajouter_jour_ferie(_rh(), jour=TABASKI, libelle="  Tabaski ")

    assert JourFerie.objects.get().libelle == "Tabaski"
    assert services.calculer_jours(date(2026, 5, 25), date(2026, 5, 29)) == 4


def test_un_jour_deja_ferie_ou_sans_libelle_est_refuse():
    services.ajouter_jour_ferie(_rh(), jour=TABASKI, libelle="Tabaski")

    with pytest.raises(JourFerieInvalide, match="déjà un jour férié"):
        services.ajouter_jour_ferie(_rh(), jour=TABASKI, libelle="Autre")
    with pytest.raises(JourFerieInvalide, match="libellé est obligatoire"):
        services.ajouter_jour_ferie(_rh(), jour=date(2026, 3, 31), libelle=" ")


def test_seuls_la_rh_la_direction_et_l_admin_gerent_les_jours_feries():
    with pytest.raises(JourFerieInvalide, match="Seules la RH"):
        services.ajouter_jour_ferie(UserFactory(role=Role.FINANCES), jour=TABASKI, libelle="Tabaski")
    for role in (Role.DIRECTION, Role.ADMIN):
        services.supprimer_jour_ferie(
            UserFactory(role=role), services.ajouter_jour_ferie(UserFactory(role=role), jour=TABASKI, libelle="T")
        )


def test_un_jour_ferie_supprime_n_est_pas_recree_par_la_generation_automatique():
    services.initialiser_jours_feries(2026)
    pentecote = JourFerie.objects.get(libelle="Lundi de Pentecôte")

    services.supprimer_jour_ferie(_rh(), pentecote)

    assert services.initialiser_jours_feries(2026) == 0
    assert not services.jours_feries_de(2026).filter(libelle="Lundi de Pentecôte").exists()
    services.ajouter_jour_ferie(_rh(), jour=pentecote.date, libelle="Lundi de Pentecôte")  # la RH peut le remettre


def test_la_tache_quotidienne_genere_les_feries_de_l_annee_et_de_la_suivante():
    resultat = executer_taches_quotidiennes(aujourd_hui=date(2026, 12, 20))

    assert resultat["jours_feries_crees"] == 20
    assert services.jours_feries_de(2027).filter(libelle="Jour de l'An").exists()
    assert executer_taches_quotidiennes(aujourd_hui=date(2026, 12, 21))["jours_feries_crees"] == 0


# --- écran ---


def test_l_ecran_liste_les_feries_de_l_annee_choisie(client):
    services.initialiser_jours_feries(2026)
    client.force_login(_rh())

    page = client.get(reverse("hr:jours_feries"), {"annee": 2026}).content.decode()

    assert "Fête de l&#x27;Indépendance" in page and "07/08/2026" in page
    assert "Les fêtes musulmanes" in page


def test_l_ecran_ajoute_genere_et_supprime(client):
    client.force_login(_rh())
    url = reverse("hr:jours_feries")

    client.post(url, {"action": "ajouter", "date": "2026-05-27", "libelle": "Tabaski"})
    client.post(url, {"action": "generer", "annee": "2026"})
    assert services.jours_feries_de(2026).count() == 11

    tabaski = JourFerie.objects.get(libelle="Tabaski")
    reponse = client.post(url, {"action": "supprimer", "jour_ferie": tabaski.pk}, follow=True)

    assert services.jours_feries_de(2026).count() == 10
    assert any("supprimé" in str(m) for m in reponse.context["messages"])


def test_une_erreur_de_saisie_s_affiche_sans_erreur_500(client):
    client.force_login(_rh())
    services.ajouter_jour_ferie(_rh(), jour=TABASKI, libelle="Tabaski")

    reponse = client.post(
        reverse("hr:jours_feries"), {"action": "ajouter", "date": "2026-05-27", "libelle": "Doublon"}, follow=True
    )

    assert reponse.status_code == 200
    assert any("déjà un jour férié" in str(m) for m in reponse.context["messages"])


def test_l_ecran_est_interdit_aux_autres_roles_et_present_dans_le_menu_rh(client):
    client.force_login(UserFactory(role=Role.FINANCES))
    assert client.get(reverse("hr:jours_feries")).status_code == 403

    client.force_login(_rh())
    assert 'href="/rh/jours-feries/"' in client.get(reverse("home")).content.decode()
