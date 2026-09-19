from datetime import date

import pytest

from apps.drivers import services
from apps.drivers.models import Chauffeur, StatutChauffeur
from apps.hr.tests.factories import PersonnelFactory

from .factories import ChauffeurFactory

pytestmark = pytest.mark.django_db


# --- création automatique de la fiche (cahier-des-charges.md:108) ---


def test_poste_chauffeur_cree_automatiquement_la_fiche():
    personnel = PersonnelFactory(poste="Chauffeur")

    assert Chauffeur.objects.filter(personnel=personnel).exists()


def test_autre_poste_ne_cree_pas_de_fiche_chauffeur():
    personnel = PersonnelFactory(poste="Comptable")

    assert not Chauffeur.objects.filter(personnel=personnel).exists()


def test_passage_au_poste_chauffeur_cree_la_fiche_plus_tard():
    personnel = PersonnelFactory(poste="Magasinier")

    personnel.poste = "Chauffeur"
    personnel.save()

    assert Chauffeur.objects.filter(personnel=personnel).exists()


def test_assurer_fiche_chauffeur_est_idempotent():
    personnel = PersonnelFactory(poste="Chauffeur")

    fiche, creee = services.assurer_fiche_chauffeur(personnel)

    assert creee is False
    assert Chauffeur.all_objects.filter(personnel=personnel).count() == 1
    assert fiche.personnel == personnel


def test_assurer_fiche_chauffeur_restaure_une_fiche_supprimee_logiquement():
    fiche = ChauffeurFactory()
    fiche.delete()

    restauree, creee = services.assurer_fiche_chauffeur(fiche.personnel)

    assert creee is False
    assert restauree.is_deleted is False
    assert Chauffeur.objects.filter(pk=fiche.pk).exists()


def test_personnel_supprime_ne_cree_pas_de_fiche():
    personnel = PersonnelFactory(poste="Chauffeur")
    Chauffeur.all_objects.filter(personnel=personnel).delete()
    personnel.delete()

    assert not Chauffeur.all_objects.filter(personnel=personnel).exists()


# --- statuts ---


def test_changer_statut_enregistre_le_nouveau_statut():
    fiche = ChauffeurFactory()

    services.changer_statut(fiche, StatutChauffeur.EN_CONGE)

    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.EN_CONGE


def test_changer_statut_refuse_un_statut_inconnu():
    fiche = ChauffeurFactory()

    with pytest.raises(ValueError):
        services.changer_statut(fiche, "VOLANT")


# --- alertes 30 jours ---


def test_chauffeurs_a_renouveler_inclut_permis_qui_expire_dans_30_jours():
    proche = ChauffeurFactory(date_expiration_permis=date(2026, 10, 10))
    lointain = ChauffeurFactory(date_expiration_permis=date(2027, 6, 1))

    resultat = services.chauffeurs_a_renouveler(aujourd_hui=date(2026, 9, 20))

    assert proche in resultat
    assert lointain not in resultat


def test_chauffeurs_a_renouveler_inclut_visite_medicale_et_documents_expires():
    visite = ChauffeurFactory(date_expiration_visite_medicale=date(2026, 9, 25))
    expire = ChauffeurFactory(date_expiration_permis=date(2026, 1, 1))

    resultat = services.chauffeurs_a_renouveler(aujourd_hui=date(2026, 9, 20))

    assert visite in resultat
    assert expire in resultat


def test_chauffeurs_a_renouveler_ignore_les_dates_non_renseignees():
    sans_dates = ChauffeurFactory()

    resultat = services.chauffeurs_a_renouveler(aujourd_hui=date(2026, 9, 20))

    assert sans_dates not in resultat


# --- missions ---


def test_mettre_en_mission_puis_rappeler_remet_disponible():
    fiche = ChauffeurFactory()

    services.mettre_en_mission(fiche)
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.EN_MISSION

    services.rappeler_de_mission(fiche)
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE


@pytest.mark.parametrize(
    "statut",
    [StatutChauffeur.EN_CONGE, StatutChauffeur.SUSPENDU, StatutChauffeur.INACTIF],
)
def test_rappeler_de_mission_conserve_un_autre_statut(statut):
    fiche = ChauffeurFactory(statut=statut)

    services.rappeler_de_mission(fiche)

    fiche.refresh_from_db()
    assert fiche.statut == statut
