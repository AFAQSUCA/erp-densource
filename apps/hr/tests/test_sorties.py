"""Sortie du personnel (audit M1-22) : enregistrement, effets à la date, préavis, annulation."""

from datetime import date, timedelta

import pytest

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditLog
from apps.hr import services, sorties
from apps.hr.exceptions import SortieImpossible
from apps.hr.models import Conge, MotifSortie, Personnel, SortiePersonnel, StatutConge

from .factories import PersonnelFactory

pytestmark = pytest.mark.django_db

AUJOURD_HUI = date(2026, 10, 12)


def _rh():
    return UserFactory(role=Role.RH)


def _conge(employe, statut, debut, jours=5):
    return Conge.objects.create(
        employe=employe, date_debut=debut, date_fin=debut + timedelta(days=jours - 1), jours=jours,
        motif="Vacances", statut=statut,
    )


def _sortir(employe, acteur=None, *, le=AUJOURD_HUI, motif=MotifSortie.DEMISSION, **autres):
    return sorties.enregistrer_sortie(
        employe, acteur or _rh(), date_sortie=le, motif=motif, aujourd_hui=AUJOURD_HUI, **autres
    )


# --- enregistrement ---


@pytest.mark.parametrize("role", [Role.RH, Role.DIRECTION, Role.ADMIN])
def test_la_rh_la_direction_et_l_admin_enregistrent_une_sortie(role):
    employe = PersonnelFactory()

    sortie, _ = _sortir(employe, UserFactory(role=role), commentaire="Départ volontaire")

    assert sortie.motif == MotifSortie.DEMISSION and sortie.commentaire == "Départ volontaire"
    assert sortie.appliquee_le is not None  # date du jour : effets immédiats
    assert AuditLog.objects.filter(module="RH", entite="SortiePersonnel", entite_id=sortie.pk).exists()


@pytest.mark.parametrize("role", [Role.FINANCES, Role.PARCAUTO, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_les_autres_roles_n_enregistrent_pas_de_sortie(role):
    with pytest.raises(SortieImpossible, match="Seules la RH"):
        _sortir(PersonnelFactory(), UserFactory(role=role))
    assert not SortiePersonnel.objects.exists()


def test_personne_n_enregistre_sa_propre_sortie():
    compte = _rh()
    employe = PersonnelFactory(utilisateur=compte)

    with pytest.raises(SortieImpossible, match="propre sortie"):
        _sortir(employe, compte)


def test_une_seule_sortie_active_par_employe():
    employe = PersonnelFactory()
    _sortir(employe, le=AUJOURD_HUI + timedelta(days=30))

    with pytest.raises(SortieImpossible, match="déjà enregistrée"):
        _sortir(employe)


def test_le_motif_autre_exige_un_commentaire():
    with pytest.raises(SortieImpossible, match="Précisez"):
        _sortir(PersonnelFactory(), motif=MotifSortie.AUTRE, commentaire="  ")


def test_un_motif_inconnu_est_refuse():
    with pytest.raises(SortieImpossible, match="inconnu"):
        _sortir(PersonnelFactory(), motif="FUITE")


def test_la_date_de_sortie_ne_precede_pas_l_embauche():
    with pytest.raises(SortieImpossible, match="embauche"):
        _sortir(PersonnelFactory(date_embauche=date(2026, 1, 5)), le=date(2025, 12, 31))


# --- effets ---


def test_le_compte_du_partant_est_desactive():
    compte = UserFactory(role=Role.CHARGE_CLIENTELE, username="awa")
    employe = PersonnelFactory(utilisateur=compte)

    _, bilan = _sortir(employe)

    compte.refresh_from_db()
    assert compte.is_active is False and bilan["compte_desactive"] == "awa"


def test_un_compte_superutilisateur_n_est_pas_touche_mais_signale():
    compte = UserFactory(role=Role.ADMIN, is_superuser=True, username="root")
    employe = PersonnelFactory(utilisateur=compte)

    _, bilan = _sortir(employe)

    compte.refresh_from_db()
    assert compte.is_active is True and bilan["compte_superutilisateur"] == "root"


def test_les_conges_a_venir_sont_annules_et_les_autres_conserves():
    employe = PersonnelFactory()
    demande = _conge(employe, StatutConge.DEMANDE, AUJOURD_HUI + timedelta(days=40))
    valide_n1 = _conge(employe, StatutConge.VALIDATION_N1, AUJOURD_HUI + timedelta(days=50))
    approuve_futur = _conge(employe, StatutConge.APPROUVE, AUJOURD_HUI + timedelta(days=60))
    en_cours = _conge(employe, StatutConge.EN_COURS, AUJOURD_HUI - timedelta(days=2))
    termine = _conge(employe, StatutConge.TERMINE, date(2026, 3, 2))

    _, bilan = _sortir(employe)

    statuts = {c.pk: c.statut for c in Conge.objects.filter(employe=employe)}
    assert statuts[demande.pk] == statuts[valide_n1.pk] == statuts[approuve_futur.pk] == StatutConge.REFUSE
    assert statuts[en_cours.pk] == StatutConge.EN_COURS and statuts[termine.pk] == StatutConge.TERMINE
    assert Conge.objects.get(pk=approuve_futur.pk).motif_decision == "Sortie du personnel le 12/10/2026."
    assert bilan["conges_annules"] == 3


def test_l_equipe_du_partant_passe_a_son_superieur():
    directeur = PersonnelFactory(nom="Kone")
    chef = PersonnelFactory(superieur=directeur)
    equipe = [PersonnelFactory(superieur=chef) for _ in range(2)]

    _, bilan = _sortir(chef)

    assert all(Personnel.objects.get(pk=e.pk).superieur == directeur for e in equipe)
    assert bilan["subordonnes"] == 2 and bilan["nouveau_superieur"] == directeur


def test_l_equipe_d_un_partant_sans_superieur_n_a_plus_de_superieur():
    chef = PersonnelFactory()
    membre = PersonnelFactory(superieur=chef)

    _sortir(chef)

    assert Personnel.objects.get(pk=membre.pk).superieur is None


def test_le_partant_n_est_plus_compte_dans_l_effectif():
    restant, partant = PersonnelFactory(), PersonnelFactory()
    avant = sum(d["nombre"] for d in services.effectif_par_departement())

    _sortir(partant)

    assert sum(d["nombre"] for d in services.effectif_par_departement()) == avant - 1
    assert list(sorties.presents(Personnel.objects.all())) == [restant]
    assert list(sorties.sortis(Personnel.objects.all())) == [partant]


# --- préavis ---


def test_une_sortie_a_venir_n_a_aucun_effet_avant_sa_date():
    compte = UserFactory(role=Role.PARCAUTO)
    employe = PersonnelFactory(utilisateur=compte)
    demande = _conge(employe, StatutConge.DEMANDE, AUJOURD_HUI + timedelta(days=5))

    sortie, bilan = _sortir(employe, le=AUJOURD_HUI + timedelta(days=30))

    compte.refresh_from_db()
    assert bilan == {} and sortie.appliquee_le is None and compte.is_active
    assert Conge.objects.get(pk=demande.pk).statut == StatutConge.DEMANDE
    assert list(sorties.presents(Personnel.objects.filter(pk=employe.pk))) == [employe]


def test_la_tache_du_jour_applique_les_sorties_arrivees_a_echeance():
    compte = UserFactory(role=Role.PARCAUTO)
    employe = PersonnelFactory(utilisateur=compte)
    sortie, _ = _sortir(employe, le=AUJOURD_HUI + timedelta(days=30))
    lointaine, _ = _sortir(PersonnelFactory(), le=AUJOURD_HUI + timedelta(days=90))

    resultat = sorties.appliquer_sorties_echues(aujourd_hui=AUJOURD_HUI + timedelta(days=30))

    sortie.refresh_from_db(), lointaine.refresh_from_db(), compte.refresh_from_db()
    assert resultat == {"appliquees": 1, "reportees": []}
    assert sortie.appliquee_le is not None and lointaine.appliquee_le is None
    assert compte.is_active is False


def test_une_sortie_n_est_appliquee_qu_une_fois():
    sortie, _ = _sortir(PersonnelFactory())
    premiere = SortiePersonnel.objects.get(pk=sortie.pk).appliquee_le

    assert sorties.appliquer_sortie(sortie) == {}
    assert sorties.appliquer_sorties_echues(aujourd_hui=AUJOURD_HUI)["appliquees"] == 0
    assert SortiePersonnel.objects.get(pk=sortie.pk).appliquee_le == premiere


# --- annulation ---


def test_la_rh_annule_une_sortie_avec_motif_et_l_employe_redevient_present():
    employe = PersonnelFactory()
    sortie, _ = _sortir(employe)
    rh = _rh()

    sorties.annuler_sortie(sortie, rh, motif="Erreur de fiche")

    sortie.refresh_from_db()
    assert sortie.annulee_par == rh and sortie.motif_annulation == "Erreur de fiche"
    assert sorties.sortie_active(employe) is None
    assert list(sorties.presents(Personnel.objects.filter(pk=employe.pk))) == [employe]
    assert list(sorties.historique(employe)) == [sortie]


def test_apres_annulation_une_nouvelle_sortie_peut_etre_enregistree():
    employe = PersonnelFactory()
    sortie, _ = _sortir(employe)
    sorties.annuler_sortie(sortie, _rh(), motif="Réintégration")

    nouvelle, _ = _sortir(employe, motif=MotifSortie.RETRAITE)

    assert sorties.sortie_active(employe) == nouvelle


def test_une_sortie_annulee_avant_sa_date_n_est_jamais_appliquee():
    sortie, _ = _sortir(PersonnelFactory(), le=AUJOURD_HUI + timedelta(days=10))
    sorties.annuler_sortie(sortie, _rh(), motif="Le salarié reste")

    assert sorties.appliquer_sorties_echues(aujourd_hui=AUJOURD_HUI + timedelta(days=10))["appliquees"] == 0


def test_l_annulation_exige_un_motif_et_n_a_lieu_qu_une_fois():
    sortie, _ = _sortir(PersonnelFactory())

    with pytest.raises(SortieImpossible, match="motif"):
        sorties.annuler_sortie(sortie, _rh(), motif=" ")
    sorties.annuler_sortie(sortie, _rh(), motif="Erreur")
    with pytest.raises(SortieImpossible, match="déjà annulée"):
        sorties.annuler_sortie(sortie, _rh(), motif="Encore")


def test_l_annulation_ne_reactive_pas_le_compte():
    compte = UserFactory(role=Role.PARCAUTO)
    sortie, _ = _sortir(PersonnelFactory(utilisateur=compte))

    sorties.annuler_sortie(sortie, _rh(), motif="Erreur")

    compte.refresh_from_db()
    assert compte.is_active is False  # se réactive à la main (écran Utilisateurs)


def test_seuls_les_gestionnaires_annulent():
    sortie, _ = _sortir(PersonnelFactory())

    with pytest.raises(SortieImpossible, match="Seules la RH"):
        sorties.annuler_sortie(sortie, UserFactory(role=Role.FINANCES), motif="Erreur")


def test_peut_gerer():
    compte = _rh()
    assert sorties.peut_gerer(compte, PersonnelFactory())
    assert not sorties.peut_gerer(compte, PersonnelFactory(utilisateur=compte))
    assert not sorties.peut_gerer(UserFactory(role=Role.FINANCES), PersonnelFactory())
