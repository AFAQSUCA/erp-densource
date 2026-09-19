"""Services de lecture et de décision utilisés par les écrans RH."""

from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal

import pytest

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.hr import services
from apps.hr.exceptions import ActionNonAutorisee, PersonnelError
from apps.hr.models import Conge, Departement, StatutConge

from .factories import PersonnelFactory

pytestmark = pytest.mark.django_db

MAINTENANT = datetime(2026, 9, 1, 8, 0, tzinfo=dt_timezone.utc)
DEBUT, FIN = date(2026, 10, 5), date(2026, 10, 9)


def _employe_avec_superieur():
    compte_sup = UserFactory(role=Role.PARCAUTO)
    superieur = PersonnelFactory(utilisateur=compte_sup, poste="Chef parc")
    compte = UserFactory(role=Role.CHARGE_CLIENTELE)
    employe = PersonnelFactory(superieur=superieur, utilisateur=compte)
    return employe, superieur, compte, compte_sup


def _rh():
    compte = UserFactory(role=Role.RH)
    return PersonnelFactory(utilisateur=compte), compte


# --- recherche du personnel ---


def test_rechercher_personnel_filtre_par_departement_et_texte():
    PersonnelFactory(nom="Bamba", prenom="Issa", departement=Departement.PARC_AUTO, poste="Mécanicien")
    PersonnelFactory(nom="Coulibaly", prenom="Awa", departement=Departement.COMMERCIAL)

    assert [p.nom for p in services.rechercher_personnel(departement=Departement.PARC_AUTO)] == ["Bamba"]
    assert [p.nom for p in services.rechercher_personnel(recherche="  mécan ")] == ["Bamba"]
    assert services.rechercher_personnel(recherche="introuvable").count() == 0
    assert services.rechercher_personnel().count() == 2


def test_comptes_disponibles_exclut_les_comptes_deja_rattaches_et_les_inactifs():
    libre = UserFactory(role=Role.FINANCES)
    UserFactory(role=Role.FINANCES, is_active=False)
    pris = UserFactory(role=Role.RH)
    fiche = PersonnelFactory(utilisateur=pris)

    assert set(services.comptes_disponibles()) == {libre}
    assert set(services.comptes_disponibles(garder=fiche)) == {libre, pris}


# --- recrutement et fiche ---


def test_recruter_refuse_un_matricule_deja_attribue_meme_supprime():
    ancien = PersonnelFactory(matricule="MAT-77")
    ancien.delete()

    with pytest.raises(PersonnelError, match="MAT-77"):
        services.recruter(
            matricule="MAT-77", nom="A", prenom="B", poste="Comptable",
            departement=Departement.COMPTABILITE, type_contrat="CDI",
            date_embauche=date(2026, 9, 1), salaire_base=Decimal("1"),
        )


def test_recruter_rattache_le_compte_utilisateur():
    compte = UserFactory(role=Role.FINANCES)

    personnel = services.recruter(
        matricule="MAT-78", nom="A", prenom="B", poste="Comptable",
        departement=Departement.COMPTABILITE, type_contrat="CDI",
        date_embauche=date(2026, 9, 1), salaire_base=Decimal("1"), utilisateur=compte,
    )

    assert personnel.utilisateur == compte


def test_recruter_refuse_un_compte_deja_rattache():
    compte = UserFactory(role=Role.FINANCES)
    PersonnelFactory(utilisateur=compte)

    with pytest.raises(PersonnelError, match="déjà rattaché"):
        services.recruter(
            matricule="MAT-79", nom="A", prenom="B", poste="Comptable",
            departement=Departement.COMPTABILITE, type_contrat="CDI",
            date_embauche=date(2026, 9, 1), salaire_base=Decimal("1"), utilisateur=compte,
        )


def _champs(personnel, **surcharges):
    champs = dict(
        nom=personnel.nom, prenom=personnel.prenom, poste=personnel.poste,
        departement=personnel.departement, type_contrat=personnel.type_contrat,
        salaire_base=personnel.salaire_base, superieur=personnel.superieur,
        utilisateur=personnel.utilisateur,
    )
    champs.update(surcharges)
    return champs


def test_modifier_personnel_met_a_jour_la_fiche_sans_toucher_matricule_ni_embauche():
    employe = PersonnelFactory(matricule="MAT-80")
    chef = PersonnelFactory()

    services.modifier_personnel(
        employe, **_champs(employe, poste="Chef comptable", salaire_base=Decimal("400000"), superieur=chef)
    )

    employe.refresh_from_db()
    assert (employe.poste, employe.salaire_base, employe.superieur) == ("Chef comptable", 400000, chef)
    assert employe.matricule == "MAT-80"
    assert employe.date_embauche == date(2024, 1, 15)


def test_modifier_personnel_refuse_d_etre_son_propre_superieur():
    employe = PersonnelFactory()

    with pytest.raises(PersonnelError, match="propre supérieur"):
        services.modifier_personnel(employe, **_champs(employe, superieur=employe))


def test_modifier_personnel_refuse_une_boucle_hierarchique():
    chef = PersonnelFactory()
    milieu = PersonnelFactory(superieur=chef)
    bas = PersonnelFactory(superieur=milieu)

    with pytest.raises(PersonnelError, match="boucle"):
        services.modifier_personnel(chef, **_champs(chef, superieur=bas))


def test_modifier_personnel_accepte_de_garder_son_propre_compte():
    compte = UserFactory(role=Role.FINANCES)
    employe = PersonnelFactory(utilisateur=compte)

    services.modifier_personnel(employe, **_champs(employe, poste="Autre"))

    employe.refresh_from_db()
    assert employe.utilisateur == compte


# --- congés à valider et actions possibles ---


def test_conges_a_valider_n1_ne_concerne_que_le_superieur():
    employe, superieur, compte, compte_sup = _employe_avec_superieur()
    conge = services.demander_conge(employe, date_debut=DEBUT, date_fin=FIN, motif="x", maintenant=MAINTENANT)

    assert list(services.conges_a_valider(compte_sup)) == [conge]
    assert list(services.conges_a_valider(compte)) == []
    assert list(services.conges_a_valider(UserFactory(role=Role.PARCAUTO))) == []


def test_conges_a_valider_n2_concerne_la_rh_sauf_sa_propre_demande():
    employe, superieur, compte, compte_sup = _employe_avec_superieur()
    conge = services.demander_conge(employe, date_debut=DEBUT, date_fin=FIN, motif="x", maintenant=MAINTENANT)
    services.valider_n1(conge, compte_sup, maintenant=MAINTENANT)
    rh, compte_rh = _rh()
    rh.superieur = superieur
    rh.save()
    propre = services.demander_conge(rh, date_debut=DEBUT, date_fin=FIN, motif="y", maintenant=MAINTENANT)
    services.valider_n1(propre, compte_sup, maintenant=MAINTENANT)

    assert list(services.conges_a_valider(compte_rh)) == [conge]


def test_le_directeur_valide_lui_meme_sa_demande_en_n1():
    compte = UserFactory(role=Role.DIRECTION)
    directeur = PersonnelFactory(utilisateur=compte)
    conge = services.demander_conge(directeur, date_debut=DEBUT, date_fin=FIN, motif="x", maintenant=MAINTENANT)

    assert list(services.conges_a_valider(compte)) == [conge]
    assert services.actions_disponibles(conge, compte) == {"valider", "refuser"}


def test_actions_disponibles_selon_le_statut_et_l_acteur():
    employe, superieur, compte, compte_sup = _employe_avec_superieur()
    rh, compte_rh = _rh()
    conge = services.demander_conge(employe, date_debut=DEBUT, date_fin=FIN, motif="x", maintenant=MAINTENANT)

    assert services.actions_disponibles(conge, compte_sup) == {"valider", "refuser"}
    assert services.actions_disponibles(conge, compte) == set()
    assert services.actions_disponibles(conge, compte_rh) == set()

    services.valider_n1(conge, compte_sup, maintenant=MAINTENANT)
    assert services.actions_disponibles(conge, compte_sup) == set()
    assert services.actions_disponibles(conge, compte_rh) == {"valider", "refuser"}

    services.valider_n2(conge, compte_rh)
    assert services.actions_disponibles(conge, compte_rh) == {"annuler"}
    assert services.actions_disponibles(conge, compte_sup) == set()

    services.annuler_conge_approuve(conge, compte_rh, motif="besoin de service")
    assert services.actions_disponibles(conge, compte_rh) == set()


def test_est_concerne_par_l_employe_et_son_superieur_seulement():
    employe, superieur, compte, compte_sup = _employe_avec_superieur()
    conge = services.demander_conge(employe, date_debut=DEBUT, date_fin=FIN, motif="x", maintenant=MAINTENANT)

    assert services.est_concerne_par(conge, compte)
    assert services.est_concerne_par(conge, compte_sup)
    assert not services.est_concerne_par(conge, UserFactory(role=Role.PARCAUTO))
    assert not services.est_concerne_par(conge, UserFactory(role=Role.ADMIN, is_superuser=True))


def test_valider_conge_choisit_le_niveau_selon_le_statut():
    employe, superieur, compte, compte_sup = _employe_avec_superieur()
    rh, compte_rh = _rh()
    conge = services.demander_conge(employe, date_debut=DEBUT, date_fin=FIN, motif="x", maintenant=MAINTENANT)

    with pytest.raises(ActionNonAutorisee):
        services.valider_conge(conge, compte_rh)
    services.valider_conge(conge, compte_sup)
    assert conge.statut == StatutConge.VALIDATION_N1
    services.valider_conge(conge, compte_rh)
    assert conge.statut == StatutConge.APPROUVE


def test_echeance_en_attente_et_retard():
    employe, superieur, compte, compte_sup = _employe_avec_superieur()
    conge = services.demander_conge(employe, date_debut=DEBUT, date_fin=FIN, motif="x", maintenant=MAINTENANT)

    niveau, limite, en_retard = services.echeance_en_attente(conge, maintenant=MAINTENANT)
    assert (niveau, limite, en_retard) == (1, MAINTENANT + timedelta(hours=48), False)
    assert services.echeance_en_attente(conge, maintenant=MAINTENANT + timedelta(hours=49))[2] is True

    services.valider_n1(conge, compte_sup, maintenant=MAINTENANT)
    assert services.echeance_en_attente(conge, maintenant=MAINTENANT)[:2] == (2, MAINTENANT + timedelta(hours=24))


def test_echeance_en_attente_est_vide_hors_attente():
    conge = Conge(statut=StatutConge.APPROUVE)
    assert services.echeance_en_attente(conge) is None
    assert services.echeance_en_attente(Conge(statut=StatutConge.DEMANDE, date_limite_n1=None)) is None


def test_peut_accorder_jours_reserve_a_la_rh_et_pas_pour_soi():
    employe = PersonnelFactory()
    rh, compte_rh = _rh()

    assert services.peut_accorder_jours(compte_rh, employe)
    assert not services.peut_accorder_jours(compte_rh, rh)
    assert not services.peut_accorder_jours(UserFactory(role=Role.ADMIN), employe)
