"""Workflow de congés en 3 niveaux — cahier-des-charges.md:211-221."""

from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

import pytest

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.audit.models import ActionChoices, AuditLog
from apps.drivers import services as drivers_services
from apps.drivers.models import Chauffeur, StatutChauffeur
from apps.hr import services
from apps.hr.exceptions import (
    ActionNonAutorisee,
    CongeError,
    SoldeInsuffisant,
    TransitionInterdite,
)
from apps.hr.models import Conge, Departement, StatutConge

from .factories import PersonnelFactory

pytestmark = pytest.mark.django_db

MAINTENANT = datetime(2026, 9, 1, 8, 0, tzinfo=dt_timezone.utc)
DEBUT, FIN = date(2026, 10, 5), date(2026, 10, 9)  # 5 jours


def _employe(departement=Departement.EXPLOITATION, solde=30, **kwargs):
    kwargs.setdefault("poste", "Dispatcheur")
    return PersonnelFactory(departement=departement, solde_conges_jours=solde, **kwargs)


def _chef(departement=Departement.EXPLOITATION):
    user = UserFactory(role=Role.PARCAUTO)
    PersonnelFactory(departement=departement, est_chef_departement=True, utilisateur=user)
    return user


def _rh():
    return UserFactory(role=Role.RH)


def _demande(employe=None, debut=DEBUT, fin=FIN):
    employe = employe or _employe()
    return services.demander_conge(
        employe, date_debut=debut, date_fin=fin, motif="Repos", maintenant=MAINTENANT
    )


def _approuve(employe=None, debut=DEBUT, fin=FIN):
    conge = _demande(employe, debut, fin)
    services.valider_n1(conge, _chef(conge.employe.departement))
    services.valider_n2(conge, _rh())
    return conge


# --- étape 1 : demande ---


def test_demande_cree_un_conge_au_statut_demande_avec_jours_inclusifs():
    conge = _demande()

    assert conge.statut == StatutConge.DEMANDE
    assert conge.jours == 5


def test_demande_fixe_l_echeance_n1_a_48_heures():
    conge = _demande()

    assert conge.date_limite_n1 == MAINTENANT + timedelta(hours=48)
    assert conge.date_limite_n2 is None


def test_demande_bloquee_si_solde_insuffisant():
    employe = _employe(solde=4)

    with pytest.raises(SoldeInsuffisant):
        _demande(employe)

    assert not Conge.objects.exists()


def test_demande_acceptee_quand_le_solde_couvre_exactement_les_jours():
    assert _demande(_employe(solde=5)).statut == StatutConge.DEMANDE


def test_demande_refusee_si_fin_avant_debut():
    with pytest.raises(CongeError):
        _demande(debut=FIN, fin=DEBUT)


# --- étape 2 : validation N1 ---


def test_valider_n1_par_le_chef_du_departement():
    conge = _demande()

    services.valider_n1(conge, _chef(), commentaire="OK", maintenant=MAINTENANT)

    conge.refresh_from_db()
    assert conge.statut == StatutConge.VALIDATION_N1
    assert conge.date_limite_n2 == MAINTENANT + timedelta(hours=24)
    decision = conge.validations.get()
    assert (decision.niveau, decision.decision) == (1, "APPROUVE")
    assert decision.commentaire == "OK"


def test_valider_n1_refuse_pour_le_chef_d_un_autre_departement():
    conge = _demande()

    with pytest.raises(ActionNonAutorisee):
        services.valider_n1(conge, _chef(Departement.COMMERCIAL))


def test_valider_n1_refuse_pour_un_simple_utilisateur_sans_fiche_ou_non_chef():
    conge = _demande()
    simple = UserFactory(role=Role.PARCAUTO)
    PersonnelFactory(departement=Departement.EXPLOITATION, utilisateur=simple)

    with pytest.raises(ActionNonAutorisee):
        services.valider_n1(conge, simple)
    with pytest.raises(ActionNonAutorisee):
        services.valider_n1(conge, UserFactory(role=Role.PARCAUTO))


def test_un_chef_ne_peut_pas_valider_sa_propre_demande():
    user = UserFactory(role=Role.PARCAUTO)
    chef_fiche = PersonnelFactory(
        departement=Departement.EXPLOITATION,
        est_chef_departement=True,
        utilisateur=user,
        solde_conges_jours=30,
    )
    conge = _demande(chef_fiche)

    with pytest.raises(ActionNonAutorisee):
        services.valider_n1(conge, user)


def test_valider_n1_impossible_hors_statut_demande():
    conge = _demande()
    chef = _chef()
    services.valider_n1(conge, chef)

    with pytest.raises(TransitionInterdite):
        services.valider_n1(conge, chef)


# --- étape 3 : validation N2 ---


def test_valider_n2_par_la_rh_approuve_et_decompte_le_solde():
    employe = _employe(solde=30)
    conge = _demande(employe)
    services.valider_n1(conge, _chef())

    services.valider_n2(conge, _rh(), commentaire="Validé")

    conge.refresh_from_db()
    employe.refresh_from_db()
    assert conge.statut == StatutConge.APPROUVE
    assert employe.solde_conges_jours == 25
    assert conge.validations.filter(niveau=2, decision="APPROUVE").exists()


def test_valider_n2_refuse_hors_rh():
    conge = _demande()
    services.valider_n1(conge, _chef())

    with pytest.raises(ActionNonAutorisee):
        services.valider_n2(conge, UserFactory(role=Role.DIRECTION))


def test_valider_n2_impossible_sans_validation_n1():
    with pytest.raises(TransitionInterdite):
        services.valider_n2(_demande(), _rh())


def test_valider_n2_recontrole_le_solde_et_ne_change_rien_si_insuffisant():
    employe = _employe(solde=5)
    conge = _demande(employe)
    services.valider_n1(conge, _chef())
    employe.solde_conges_jours = 2
    employe.save()

    with pytest.raises(SoldeInsuffisant):
        services.valider_n2(conge, _rh())

    conge.refresh_from_db()
    assert conge.statut == StatutConge.VALIDATION_N1


def test_un_rh_ne_peut_pas_valider_sa_propre_demande():
    user = _rh()
    fiche = PersonnelFactory(
        departement=Departement.DIRECTION, utilisateur=user, solde_conges_jours=30
    )
    conge = _demande(fiche)
    services.valider_n1(conge, _chef(Departement.DIRECTION))

    with pytest.raises(ActionNonAutorisee):
        services.valider_n2(conge, user)


# --- refus ---


def test_refus_n1_par_le_chef_passe_le_conge_a_refuse():
    conge = _demande()

    services.refuser(conge, _chef(), commentaire="Période chargée")

    conge.refresh_from_db()
    assert conge.statut == StatutConge.REFUSE
    assert conge.motif_decision == "Période chargée"
    assert conge.validations.get().decision == "REFUSE"


def test_refus_n2_par_la_rh_ne_decompte_pas_le_solde():
    employe = _employe(solde=30)
    conge = _demande(employe)
    services.valider_n1(conge, _chef())

    services.refuser(conge, _rh())

    employe.refresh_from_db()
    assert employe.solde_conges_jours == 30
    assert Conge.objects.get().statut == StatutConge.REFUSE


def test_refus_a_l_etape_n1_refuse_pour_la_rh():
    with pytest.raises(ActionNonAutorisee):
        services.refuser(_demande(), _rh())


def test_refus_impossible_sur_un_conge_deja_approuve():
    with pytest.raises(TransitionInterdite):
        services.refuser(_approuve(), _rh())


# --- annulation (RH uniquement, cahier-des-charges.md:220-221) ---


def test_annulation_par_la_rh_restitue_le_solde():
    employe = _employe(solde=30)
    conge = _approuve(employe)

    services.annuler_conge_approuve(conge, _rh(), motif="Urgence client")

    employe.refresh_from_db()
    conge.refresh_from_db()
    assert employe.solde_conges_jours == 30
    assert conge.statut == StatutConge.REFUSE
    assert conge.motif_decision == "Urgence client"


def test_annulation_refusee_hors_rh():
    conge = _approuve()

    with pytest.raises(ActionNonAutorisee):
        services.annuler_conge_approuve(conge, _chef())


def test_annulation_impossible_si_le_conge_n_est_pas_approuve():
    with pytest.raises(TransitionInterdite):
        services.annuler_conge_approuve(_demande(), _rh())


# --- passage automatique EN_COURS / TERMINE et effet sur le chauffeur ---


def test_synchronisation_demarre_puis_termine_le_conge():
    conge = _approuve()

    avant = services.synchroniser_statuts_conges(aujourd_hui=DEBUT - timedelta(days=1))
    pendant = services.synchroniser_statuts_conges(aujourd_hui=DEBUT)
    apres = services.synchroniser_statuts_conges(aujourd_hui=FIN + timedelta(days=1))

    assert avant == {"demarres": 0, "termines": 0}
    assert pendant == {"demarres": 1, "termines": 0}
    assert apres == {"demarres": 0, "termines": 1}
    conge.refresh_from_db()
    assert conge.statut == StatutConge.TERMINE


def test_conge_rattrape_directement_en_termine_si_la_synchro_a_ete_manquee():
    conge = _approuve()

    resultat = services.synchroniser_statuts_conges(aujourd_hui=FIN + timedelta(days=3))

    assert resultat == {"demarres": 0, "termines": 1}
    conge.refresh_from_db()
    assert conge.statut == StatutConge.TERMINE


def test_chauffeur_passe_en_conge_au_demarrage_puis_redevient_disponible():
    employe = _employe(poste="Chauffeur")
    fiche = Chauffeur.objects.get(personnel=employe)
    _approuve(employe)

    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE  # pas avant le départ effectif

    services.synchroniser_statuts_conges(aujourd_hui=DEBUT)
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.EN_CONGE

    services.synchroniser_statuts_conges(aujourd_hui=FIN + timedelta(days=1))
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE


def test_fin_de_conge_conserve_un_statut_suspendu():
    employe = _employe(poste="Chauffeur")
    fiche = Chauffeur.objects.get(personnel=employe)
    _approuve(employe)
    services.synchroniser_statuts_conges(aujourd_hui=DEBUT)
    drivers_services.changer_statut(fiche, StatutChauffeur.SUSPENDU)

    services.synchroniser_statuts_conges(aujourd_hui=FIN + timedelta(days=1))

    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.SUSPENDU


def test_conge_d_un_non_chauffeur_ne_touche_aucune_fiche_chauffeur():
    _approuve(_employe(poste="Comptable"))

    services.synchroniser_statuts_conges(aujourd_hui=DEBUT)

    assert not Chauffeur.objects.exists()


# --- audit ---


def test_les_transitions_de_statut_sont_auditees():
    conge = _demande()
    services.valider_n1(conge, _chef())

    entrees = AuditLog.objects.filter(entite="Conge", entite_id=conge.pk)
    assert entrees.get(action=ActionChoices.CREATE).module == "RH"
    modif = entrees.filter(action=ActionChoices.UPDATE).latest("date_heure")
    assert modif.ancienne_valeur["statut"] == "DEMANDE"
    assert modif.nouvelle_valeur["statut"] == "VALIDATION_N1"
