"""La fiche chauffeur ou copilote suit la fiche personnel (audit M3-04, cahier-des-charges.md:106 « Chauffeur =
employé ») : poste quitté ou fiche supprimée → « Inactif », plus jamais affectable."""

import pytest

from apps.drivers import services
from apps.drivers.models import Chauffeur, Copilote, StatutChauffeur
from apps.hr import services as hr_services
from apps.hr.exceptions import PersonnelError
from apps.hr.models import Personnel
from apps.hr.tests.factories import PersonnelFactory

from .factories import ChauffeurFactory, CopiloteFactory

pytestmark = pytest.mark.django_db


def _changer_poste(personnel: Personnel, poste: str) -> Personnel:
    return hr_services.modifier_personnel(
        personnel, nom=personnel.nom, prenom=personnel.prenom, poste=poste, departement=personnel.departement,
        type_contrat=personnel.type_contrat, salaire_base=personnel.salaire_base, superieur=personnel.superieur,
        utilisateur=personnel.utilisateur,
    )


def _statut(fiche):
    return type(fiche).all_objects.get(pk=fiche.pk).statut


def test_un_chauffeur_qui_change_de_poste_n_est_plus_affectable():
    fiche = ChauffeurFactory()

    _changer_poste(fiche.personnel, "Magasinier")

    assert _statut(fiche) == StatutChauffeur.INACTIF
    assert fiche not in services.chauffeurs_actifs() and fiche not in services.chauffeurs_disponibles()


def test_un_copilote_qui_change_de_poste_devient_inactif():
    fiche = CopiloteFactory()

    _changer_poste(fiche.personnel, "Mécanicien")

    assert _statut(fiche) == StatutChauffeur.INACTIF
    assert fiche not in services.copilotes_disponibles()


@pytest.mark.parametrize("fabrique", [ChauffeurFactory, CopiloteFactory])
def test_supprimer_la_fiche_personnel_desactive_la_fiche(fabrique):
    fiche = fabrique()

    fiche.personnel.delete()

    assert _statut(fiche) == StatutChauffeur.INACTIF


def test_le_poste_ne_change_pas_pendant_une_mission():
    fiche = ChauffeurFactory(statut=StatutChauffeur.EN_MISSION)

    with pytest.raises(PersonnelError, match="est en mission : changez son poste après la livraison"):
        _changer_poste(fiche.personnel, "Magasinier")

    assert Personnel.objects.get(pk=fiche.personnel_id).poste == "Chauffeur"  # rien n'est enregistré
    assert _statut(fiche) == StatutChauffeur.EN_MISSION


def test_revenir_au_poste_de_chauffeur_ne_reactive_pas_la_fiche_toute_seule():
    fiche = ChauffeurFactory()
    _changer_poste(fiche.personnel, "Magasinier")

    _changer_poste(Personnel.objects.get(pk=fiche.personnel_id), "Chauffeur")

    assert Chauffeur.objects.filter(personnel_id=fiche.personnel_id).count() == 1  # pas de doublon
    assert _statut(fiche) == StatutChauffeur.INACTIF  # réactivation à la main par la RH


def test_modifier_un_chauffeur_sans_changer_son_poste_ne_touche_pas_a_son_statut():
    fiche = ChauffeurFactory(statut=StatutChauffeur.SUSPENDU)

    _changer_poste(fiche.personnel, "Chauffeur")

    assert _statut(fiche) == StatutChauffeur.SUSPENDU


def test_un_employe_qui_n_a_jamais_ete_chauffeur_n_a_pas_de_fiche():
    employe = PersonnelFactory(poste="Comptable")

    _changer_poste(employe, "Magasinier")

    assert not Chauffeur.all_objects.filter(personnel=employe).exists()
    assert not Copilote.all_objects.filter(personnel=employe).exists()
