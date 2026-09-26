"""Droit annuel (26 jours ouvrés) et exceptions accordées par la RH."""

from datetime import date

import pytest

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditLog
from apps.hr import services
from apps.hr.exceptions import ActionNonAutorisee, CongeError, SoldeInsuffisant
from apps.hr.models import JourFerie, StatutConge

from .factories import PersonnelFactory
from .test_conges import _approuve, _demande, _hierarchie, _rh

pytestmark = pytest.mark.django_db


def _droits(employe, annee=2026):
    return services.droits_conges(employe, annee)


# --- droit de base ---


def test_droit_de_base_26_jours_ouvres_sans_exception_ni_conge():
    employe = PersonnelFactory()

    assert _droits(employe) == {
        "droit_annuel": 26,
        "exceptionnels": 0,
        "consommes": 0,
        "disponible": 26,
    }


def test_une_demande_en_attente_n_est_pas_decomptee():
    conge, _ = _demande()

    assert _droits(conge.employe)["consommes"] == 0


def test_un_conge_approuve_est_decompte():
    conge = _approuve()

    assert _droits(conge.employe) == {
        "droit_annuel": 26,
        "exceptionnels": 0,
        "consommes": 5,
        "disponible": 21,
    }


def test_un_conge_termine_reste_decompte():
    conge = _approuve()
    services.synchroniser_statuts_conges(aujourd_hui=date(2026, 12, 1))

    conge.refresh_from_db()
    assert conge.statut == StatutConge.TERMINE
    assert _droits(conge.employe)["consommes"] == 5


def test_le_droit_est_calcule_par_annee_de_debut_du_conge():
    hierarchie = _hierarchie()
    _approuve(hierarchie, date(2026, 12, 7), date(2026, 12, 12))  # lun-sam : 5 jours ouvrés (pas le samedi)
    employe = hierarchie[0]

    assert _droits(employe, 2026)["disponible"] == 21
    assert _droits(employe, 2027)["disponible"] == 26


def test_apres_avoir_pris_5_jours_une_demande_de_22_jours_est_refusee_mais_21_passe():
    hierarchie = _hierarchie()
    _approuve(hierarchie)  # 5 jours, solde restant 21

    with pytest.raises(SoldeInsuffisant):
        _demande(hierarchie, date(2026, 11, 2), date(2026, 12, 1))  # 22 jours ouvrés
    conge, _ = _demande(hierarchie, date(2026, 11, 2), date(2026, 11, 30))  # 21 jours ouvrés

    assert conge.jours == 21


# --- exceptions accordées par la RH ---


def test_la_rh_peut_accorder_des_jours_exceptionnels():
    employe = PersonnelFactory()

    attribution = services.accorder_jours_exceptionnels(
        employe, _rh(), annee=2026, jours=5, motif="Mariage"
    )

    assert attribution.motif == "Mariage"
    assert _droits(employe) == {
        "droit_annuel": 26,
        "exceptionnels": 5,
        "consommes": 0,
        "disponible": 31,
    }


def test_les_jours_exceptionnels_permettent_de_depasser_le_droit_de_base():
    hierarchie = _hierarchie()
    employe = hierarchie[0]
    services.accorder_jours_exceptionnels(
        employe, _rh(), annee=2026, jours=3, motif="Décès d'un proche"
    )

    conge, _ = _demande(hierarchie, date(2026, 11, 2), date(2026, 12, 4))  # 25 jours ouvrés (26 + 3 - 4 de marge)

    assert conge.jours == 25


def test_les_jours_exceptionnels_d_une_autre_annee_ne_comptent_pas():
    employe = PersonnelFactory()
    services.accorder_jours_exceptionnels(
        employe, _rh(), annee=2025, jours=5, motif="Mariage"
    )

    assert _droits(employe, 2026)["disponible"] == 26


def test_attribution_refusee_hors_rh():
    with pytest.raises(ActionNonAutorisee):
        services.accorder_jours_exceptionnels(
            PersonnelFactory(),
            UserFactory(role=Role.DIRECTION),
            annee=2026,
            jours=3,
            motif="x",
        )


def test_la_rh_ne_peut_pas_s_accorder_des_jours_a_elle_meme():
    compte_rh = _rh()
    fiche = PersonnelFactory(utilisateur=compte_rh)

    with pytest.raises(ActionNonAutorisee):
        services.accorder_jours_exceptionnels(
            fiche, compte_rh, annee=2026, jours=3, motif="x"
        )


@pytest.mark.parametrize("motif", ["", "   "])
def test_attribution_refusee_sans_motif(motif):
    with pytest.raises(CongeError, match="motif"):
        services.accorder_jours_exceptionnels(
            PersonnelFactory(), _rh(), annee=2026, jours=3, motif=motif
        )


def test_attribution_refusee_avec_zero_jour():
    with pytest.raises(CongeError):
        services.accorder_jours_exceptionnels(
            PersonnelFactory(), _rh(), annee=2026, jours=0, motif="x"
        )


def test_attribution_exceptionnelle_est_auditee():
    attribution = services.accorder_jours_exceptionnels(
        PersonnelFactory(), _rh(), annee=2026, jours=2, motif="Mariage"
    )

    entree = AuditLog.objects.get(entite="AttributionConge", entite_id=attribution.pk)
    assert entree.module == "RH"
    assert entree.nouvelle_valeur["jours"] == 2


# --- jours ouvrés (avenant-separation-des-taches.md § R7 : lundi-vendredi, hors jours fériés) ---


@pytest.mark.parametrize(
    ("debut", "fin", "attendu"),
    [
        (date(2026, 10, 5), date(2026, 10, 9), 5),  # lundi-vendredi
        (date(2026, 10, 5), date(2026, 10, 10), 5),  # le samedi ne compte pas
        (date(2026, 10, 5), date(2026, 10, 11), 5),  # ni le dimanche
        (date(2026, 10, 10), date(2026, 10, 11), 0),  # un week-end complet
        (date(2026, 10, 5), date(2026, 10, 5), 1),  # un seul jour
    ],
)
def test_calculer_jours_exclut_le_samedi_et_le_dimanche(debut, fin, attendu):
    assert services.calculer_jours(debut, fin) == attendu


def test_calculer_jours_exclut_les_jours_feries_enregistres():
    JourFerie.objects.create(date=date(2026, 8, 7), libelle="Fête de l'Indépendance")  # un vendredi

    assert services.calculer_jours(date(2026, 8, 3), date(2026, 8, 8)) == 4  # lun-jeu (ven férié, sam exclu)


def test_un_jour_ferie_supprime_logiquement_redevient_ouvre():
    ferie = JourFerie.objects.create(date=date(2026, 8, 7), libelle="Indépendance")
    ferie.delete()

    assert services.calculer_jours(date(2026, 8, 3), date(2026, 8, 8)) == 5  # lun-ven (sam toujours exclu)
