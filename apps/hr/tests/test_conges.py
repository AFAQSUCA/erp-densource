"""Workflow de congés en 3 niveaux — cahier-des-charges.md:211-221.

N1 = supérieur hiérarchique direct de l'employé ; N2 = RH ; décompte en jours
ouvrables (lundi-samedi, hors jours fériés) sur un droit annuel de 12 jours.
"""

from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

import pytest
from django.utils import timezone

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
DEBUT, FIN = date(2026, 10, 5), date(2026, 10, 9)  # lundi-vendredi = 5 jours ouvrables


def _hierarchie(poste="Dispatcheur"):
    """Un employé et le compte utilisateur de son supérieur direct.

    Le supérieur est volontairement dans un autre département : la validation
    N1 suit la hiérarchie, pas le département.
    """
    user = UserFactory(role=Role.PARCAUTO)
    chef = PersonnelFactory(
        poste="Chef", departement=Departement.DIRECTION, utilisateur=user
    )
    employe = PersonnelFactory(
        poste=poste, departement=Departement.EXPLOITATION, superieur=chef
    )
    return employe, user


def _rh():
    return UserFactory(role=Role.RH)


def _demande(hierarchie=None, debut=DEBUT, fin=FIN):
    employe, superieur = hierarchie or _hierarchie()
    conge = services.demander_conge(
        employe, date_debut=debut, date_fin=fin, motif="Repos", maintenant=MAINTENANT
    )
    return conge, superieur


def _delai_en_cours(conge):
    """Le délai de décision n'est pas dépassé (la Direction ne peut donc pas se substituer au validateur)."""
    Conge.objects.filter(pk=conge.pk).update(date_limite_n1=timezone.now() + timedelta(hours=24))
    conge.refresh_from_db()


def _approuve(hierarchie=None, debut=DEBUT, fin=FIN):
    conge, superieur = _demande(hierarchie, debut, fin)
    services.valider_n1(conge, superieur)
    services.valider_n2(conge, _rh())
    return conge


def _disponible(employe, annee=2026):
    return services.droits_conges(employe, annee)["disponible"]


# --- étape 1 : demande ---


def test_demande_cree_un_conge_au_statut_demande_en_jours_ouvrables():
    conge, _ = _demande()

    assert conge.statut == StatutConge.DEMANDE
    assert conge.jours == 5


def test_demande_fixe_l_echeance_n1_a_48_heures():
    conge, _ = _demande()

    assert conge.date_limite_n1 == MAINTENANT + timedelta(hours=48)
    assert conge.date_limite_n2 is None


def test_demande_bloquee_au_dela_de_12_jours_ouvrables_par_an():
    hierarchie = _hierarchie()

    with pytest.raises(SoldeInsuffisant):
        _demande(hierarchie, date(2026, 10, 5), date(2026, 10, 19))  # 13 jours

    assert not Conge.objects.exists()


def test_demande_acceptee_pour_exactement_2_semaines():
    conge, _ = _demande(debut=date(2026, 10, 5), fin=date(2026, 10, 17))

    assert conge.jours == 12


def test_demande_refusee_si_fin_avant_debut():
    with pytest.raises(CongeError):
        _demande(debut=FIN, fin=DEBUT)


def test_demande_refusee_sans_superieur_hierarchique():
    employe = PersonnelFactory(superieur=None)

    with pytest.raises(CongeError, match="supérieur"):
        services.demander_conge(employe, date_debut=DEBUT, date_fin=FIN, motif="x")


def test_demande_refusee_si_la_periode_ne_contient_aucun_jour_ouvrable():
    with pytest.raises(CongeError, match="jour ouvrable"):
        _demande(debut=date(2026, 10, 11), fin=date(2026, 10, 11))  # un dimanche


# --- étape 2 : validation N1 par le supérieur hiérarchique ---


def test_valider_n1_par_le_superieur_direct_meme_dans_un_autre_departement():
    conge, superieur = _demande()

    services.valider_n1(conge, superieur, commentaire="OK", maintenant=MAINTENANT)

    conge.refresh_from_db()
    assert conge.statut == StatutConge.VALIDATION_N1
    assert conge.date_limite_n2 == MAINTENANT + timedelta(hours=24)
    decision = conge.validations.get()
    assert (decision.niveau, decision.decision) == (1, "APPROUVE")
    assert decision.commentaire == "OK"


def test_valider_n1_refuse_pour_un_utilisateur_qui_n_est_pas_le_superieur():
    conge, _ = _demande()
    autre = UserFactory(role=Role.PARCAUTO)
    PersonnelFactory(departement=Departement.EXPLOITATION, utilisateur=autre)

    with pytest.raises(ActionNonAutorisee):
        services.valider_n1(conge, autre)
    with pytest.raises(ActionNonAutorisee):
        services.valider_n1(conge, UserFactory(role=Role.PARCAUTO))  # sans fiche


def test_valider_n1_refuse_pour_le_superieur_du_superieur():
    employe, superieur = _hierarchie()
    directeur = UserFactory(role=Role.DIRECTION)
    chef = employe.superieur
    chef.superieur = PersonnelFactory(utilisateur=directeur)
    chef.save()
    conge, _ = _demande((employe, superieur))
    _delai_en_cours(conge)

    with pytest.raises(ActionNonAutorisee):
        services.valider_n1(conge, directeur)


def test_l_employe_ne_peut_pas_valider_sa_propre_demande():
    hierarchie = _hierarchie()
    compte = UserFactory(role=Role.PARCAUTO)
    hierarchie[0].utilisateur = compte
    hierarchie[0].save()
    conge, _ = _demande(hierarchie)

    with pytest.raises(ActionNonAutorisee):
        services.valider_n1(conge, compte)


def test_la_demande_d_un_chef_est_validee_par_son_propre_superieur():
    _, chef_user = _hierarchie()  # chef_user est le compte du « chef »
    chef_fiche = chef_user.personnel
    directeur = UserFactory(role=Role.DIRECTION)
    chef_fiche.superieur = PersonnelFactory(utilisateur=directeur)
    chef_fiche.save()
    conge, _ = _demande((chef_fiche, chef_user))

    with pytest.raises(ActionNonAutorisee):
        services.valider_n1(conge, chef_user)
    services.valider_n1(conge, directeur)

    conge.refresh_from_db()
    assert conge.statut == StatutConge.VALIDATION_N1


def test_valider_n1_impossible_hors_statut_demande():
    conge, superieur = _demande()
    services.valider_n1(conge, superieur)

    with pytest.raises(TransitionInterdite):
        services.valider_n1(conge, superieur)


# --- étape 3 : validation N2 par la RH ---


def test_valider_n2_par_la_rh_approuve_et_decompte_le_droit_annuel():
    conge, superieur = _demande()
    services.valider_n1(conge, superieur)

    services.valider_n2(conge, _rh(), commentaire="Validé")

    conge.refresh_from_db()
    assert conge.statut == StatutConge.APPROUVE
    assert _disponible(conge.employe) == 7
    assert conge.validations.filter(niveau=2, decision="APPROUVE").exists()


def test_valider_n2_refuse_hors_rh():
    conge, superieur = _demande()
    services.valider_n1(conge, superieur)

    with pytest.raises(ActionNonAutorisee):
        services.valider_n2(conge, UserFactory(role=Role.DIRECTION))


def test_valider_n2_impossible_sans_validation_n1():
    conge, _ = _demande()

    with pytest.raises(TransitionInterdite):
        services.valider_n2(conge, _rh())


def test_valider_n2_recontrole_le_droit_quand_deux_demandes_etaient_en_attente():
    hierarchie = _hierarchie()
    premiere, superieur = _demande(hierarchie, date(2026, 10, 5), date(2026, 10, 13))  # 8 j
    seconde, _ = _demande(hierarchie, date(2026, 11, 2), date(2026, 11, 10))  # 8 j
    services.valider_n1(premiere, superieur)
    services.valider_n1(seconde, superieur)
    rh = _rh()
    services.valider_n2(premiere, rh)

    with pytest.raises(SoldeInsuffisant):
        services.valider_n2(seconde, rh)

    seconde.refresh_from_db()
    assert seconde.statut == StatutConge.VALIDATION_N1


def test_un_rh_ne_peut_pas_valider_sa_propre_demande():
    employe, superieur = _hierarchie()
    compte_rh = _rh()
    employe.utilisateur = compte_rh
    employe.save()
    conge, _ = _demande((employe, superieur))
    services.valider_n1(conge, superieur)

    with pytest.raises(ActionNonAutorisee):
        services.valider_n2(conge, compte_rh)


# --- refus ---


def test_refus_n1_par_le_superieur_passe_le_conge_a_refuse():
    conge, superieur = _demande()

    services.refuser(conge, superieur, commentaire="Période chargée")

    conge.refresh_from_db()
    assert conge.statut == StatutConge.REFUSE
    assert conge.motif_decision == "Période chargée"
    assert conge.validations.get().decision == "REFUSE"


def test_refus_n2_par_la_rh_ne_decompte_rien():
    conge, superieur = _demande()
    services.valider_n1(conge, superieur)

    services.refuser(conge, _rh())

    assert _disponible(conge.employe) == 12
    assert Conge.objects.get().statut == StatutConge.REFUSE


def test_refus_a_l_etape_n1_refuse_pour_la_rh():
    conge, _ = _demande()

    with pytest.raises(ActionNonAutorisee):
        services.refuser(conge, _rh())


def test_refus_impossible_sur_un_conge_deja_approuve():
    with pytest.raises(TransitionInterdite):
        services.refuser(_approuve(), _rh())


# --- annulation (RH uniquement, cahier-des-charges.md:220-221) ---


def test_annulation_par_la_rh_restitue_les_jours():
    conge = _approuve()
    assert _disponible(conge.employe) == 7

    services.annuler_conge_approuve(conge, _rh(), motif="Urgence client")

    conge.refresh_from_db()
    assert _disponible(conge.employe) == 12
    assert conge.statut == StatutConge.REFUSE
    assert conge.motif_decision == "Urgence client"


def test_annulation_refusee_hors_rh():
    conge = _approuve()

    with pytest.raises(ActionNonAutorisee):
        services.annuler_conge_approuve(conge, conge.employe.superieur.utilisateur)


def test_annulation_impossible_si_le_conge_n_est_pas_approuve():
    conge, _ = _demande()

    with pytest.raises(TransitionInterdite):
        services.annuler_conge_approuve(conge, _rh())


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
    hierarchie = _hierarchie(poste="Chauffeur")
    fiche = Chauffeur.objects.get(personnel=hierarchie[0])
    _approuve(hierarchie)

    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE  # pas avant le départ effectif

    services.synchroniser_statuts_conges(aujourd_hui=DEBUT)
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.EN_CONGE

    services.synchroniser_statuts_conges(aujourd_hui=FIN + timedelta(days=1))
    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.DISPONIBLE


def test_fin_de_conge_conserve_un_statut_suspendu():
    hierarchie = _hierarchie(poste="Chauffeur")
    fiche = Chauffeur.objects.get(personnel=hierarchie[0])
    _approuve(hierarchie)
    services.synchroniser_statuts_conges(aujourd_hui=DEBUT)
    drivers_services.changer_statut(fiche, StatutChauffeur.SUSPENDU)

    services.synchroniser_statuts_conges(aujourd_hui=FIN + timedelta(days=1))

    fiche.refresh_from_db()
    assert fiche.statut == StatutChauffeur.SUSPENDU


def test_conge_d_un_non_chauffeur_ne_touche_aucune_fiche_chauffeur():
    _approuve(_hierarchie(poste="Comptable"))

    services.synchroniser_statuts_conges(aujourd_hui=DEBUT)

    assert not Chauffeur.objects.exists()


# --- audit ---


def test_les_transitions_de_statut_sont_auditees():
    conge, superieur = _demande()
    services.valider_n1(conge, superieur)

    entrees = AuditLog.objects.filter(entite="Conge", entite_id=conge.pk)
    assert entrees.get(action=ActionChoices.CREATE).module == "RH"
    modif = entrees.filter(action=ActionChoices.UPDATE).latest("date_heure")
    assert modif.ancienne_valeur["statut"] == "DEMANDE"
    assert modif.nouvelle_valeur["statut"] == "VALIDATION_N1"


# --- le directeur (sans supérieur) valide lui-même son N1 ---


def _directeur():
    compte = UserFactory(role=Role.DIRECTION)
    fiche = PersonnelFactory(
        poste="Directeur", departement=Departement.DIRECTION, utilisateur=compte
    )
    return fiche, compte


def test_le_directeur_valide_lui_meme_son_n1_puis_la_rh_valide_en_n2():
    fiche, compte = _directeur()
    conge, _ = _demande((fiche, compte))

    services.valider_n1(conge, compte)
    services.valider_n2(conge, _rh())

    conge.refresh_from_db()
    assert conge.statut == StatutConge.APPROUVE
    assert conge.validations.get(niveau=1).validateur == compte


def test_le_directeur_ne_peut_pas_sauter_la_validation_n2_de_la_rh():
    fiche, compte = _directeur()
    conge, _ = _demande((fiche, compte))
    services.valider_n1(conge, compte)

    with pytest.raises(ActionNonAutorisee):
        services.valider_n2(conge, compte)


def test_un_employe_sans_superieur_et_sans_compte_direction_ne_peut_pas_demander():
    compte = UserFactory(role=Role.PARCAUTO)
    fiche = PersonnelFactory(superieur=None, utilisateur=compte)

    with pytest.raises(CongeError, match="supérieur"):
        services.demander_conge(fiche, date_debut=DEBUT, date_fin=FIN, motif="x")


def test_un_directeur_sans_compte_utilisateur_ne_peut_pas_demander():
    fiche = PersonnelFactory(poste="Directeur", superieur=None, utilisateur=None)

    with pytest.raises(CongeError, match="supérieur"):
        services.demander_conge(fiche, date_debut=DEBUT, date_fin=FIN, motif="x")


def test_un_autre_utilisateur_direction_ne_valide_pas_le_n1_du_directeur():
    fiche, compte = _directeur()
    conge, _ = _demande((fiche, compte))
    _delai_en_cours(conge)

    with pytest.raises(ActionNonAutorisee):
        services.valider_n1(conge, UserFactory(role=Role.DIRECTION))


def test_le_directeur_valide_le_n1_d_un_subordonne_seulement_s_il_est_son_superieur():
    fiche, compte = _directeur()
    employe = PersonnelFactory(superieur=fiche, poste="Comptable")
    conge, _ = _demande((employe, compte))

    services.valider_n1(conge, compte)

    conge.refresh_from_db()
    assert conge.statut == StatutConge.VALIDATION_N1


def test_valider_n1_sans_acteur_est_refuse():
    conge, _ = _demande()

    with pytest.raises(ActionNonAutorisee):
        services.valider_n1(conge, None)
