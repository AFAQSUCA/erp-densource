"""Le chauffeur demande lui-même ses congés depuis l'espace mobile (audit : M11-03).

Mêmes règles que pour tout employé (solde, supérieur hiérarchique, pas de chevauchement) : le chauffeur n'a
pas d'écran RH, mais sa demande suit le même workflow (supérieur en N1, RH en N2)."""

from datetime import date
from datetime import datetime
from datetime import timezone as dt_timezone

import pytest
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.hr import services as hr_services
from apps.hr.exceptions import CongeError, SoldeInsuffisant
from apps.hr.models import Conge, Departement, StatutConge
from apps.hr.tests.factories import PersonnelFactory
from apps.mobile_api import services
from apps.notifications.models import CategorieNotification, Notification

from .helpers import chauffeur_avec_compte

pytestmark = pytest.mark.django_db

DEBUT, FIN = date(2026, 10, 5), date(2026, 10, 9)  # lundi-vendredi = 5 jours ouvrés
DONNEES = {"date_debut": DEBUT.isoformat(), "date_fin": FIN.isoformat(), "motif": "Repos"}


@pytest.fixture(autouse=True)
def _vider_le_cache():
    cache.clear()


def _chauffeur_avec_superieur():
    """Chauffeur (compte CHAUFFEUR) dont le supérieur hiérarchique a un compte PARCAUTO."""
    fiche, compte = chauffeur_avec_compte()
    chef_compte = UserFactory(role=Role.PARCAUTO)
    chef = PersonnelFactory(poste="Responsable parc auto", departement=Departement.DIRECTION, utilisateur=chef_compte)
    fiche.personnel.superieur = chef
    fiche.personnel.save()
    return fiche, compte, chef_compte


@pytest.fixture
def chauffeur(client):
    fiche, compte, chef_compte = _chauffeur_avec_superieur()
    client.force_login(compte)
    return fiche, compte, chef_compte


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


# --- services ---


def test_un_chauffeur_demande_un_conge_en_jours_ouvres():
    fiche, _, _ = _chauffeur_avec_superieur()

    conge = services.demander_conge(fiche, date_debut=DEBUT, date_fin=FIN, motif="Repos")

    assert conge.employe_id == fiche.personnel_id
    assert (conge.jours, conge.statut) == (5, StatutConge.DEMANDE)


def test_la_demande_du_chauffeur_previent_son_superieur_pour_la_validation_n1():
    fiche, _, chef_compte = _chauffeur_avec_superieur()

    services.demander_conge(fiche, date_debut=DEBUT, date_fin=FIN, motif="Repos")

    notification = Notification.objects.get(destinataire=chef_compte, categorie=CategorieNotification.CONGE)
    assert fiche.personnel.nom in notification.titre


def test_un_chauffeur_sans_superieur_ne_peut_pas_demander_de_conge():
    fiche, _ = chauffeur_avec_compte()

    with pytest.raises(CongeError, match="supérieur"):
        services.demander_conge(fiche, date_debut=DEBUT, date_fin=FIN, motif="Repos")


def test_la_demande_est_refusee_si_le_solde_est_insuffisant():
    fiche, _, _ = _chauffeur_avec_superieur()

    with pytest.raises(SoldeInsuffisant):
        services.demander_conge(fiche, date_debut=date(2026, 10, 5), date_fin=date(2026, 12, 31), motif="Long")


def test_le_solde_et_les_demandes_sont_ceux_du_chauffeur_seulement():
    fiche, _, _ = _chauffeur_avec_superieur()
    autre, _, _ = _chauffeur_avec_superieur()
    services.demander_conge(autre, date_debut=DEBUT, date_fin=FIN, motif="Repos")

    assert list(services.conges_du_chauffeur(fiche)) == []
    droits = services.droits_conges_du_chauffeur(fiche, aujourd_hui=date(2026, 10, 3))
    assert droits["annee"] == 2026 and droits["disponible"] == droits["droit_annuel"]


def test_la_liste_se_limite_au_nombre_demande():
    fiche, _, _ = _chauffeur_avec_superieur()
    for decalage in range(3):
        debut = date(2026, 10, 5 + 7 * decalage)
        services.demander_conge(fiche, date_debut=debut, date_fin=debut, motif="Un jour")

    assert services.conges_du_chauffeur(fiche).count() == 3
    assert len(services.conges_du_chauffeur(fiche, limite=2)) == 2


# --- règle RH : pas de chevauchement (valable pour tout employé) ---


def _demande(fiche, debut, fin):
    return services.demander_conge(fiche, date_debut=debut, date_fin=fin, motif="Repos")


def test_une_demande_qui_chevauche_un_autre_conge_est_refusee():
    fiche, _, _ = _chauffeur_avec_superieur()
    _demande(fiche, date(2026, 10, 5), date(2026, 10, 9))

    with pytest.raises(CongeError, match="chevauche"):
        _demande(fiche, date(2026, 10, 8), date(2026, 10, 14))
    assert Conge.objects.filter(employe=fiche.personnel).count() == 1


@pytest.mark.parametrize(
    ("debut", "fin"),
    [(date(2026, 10, 12), date(2026, 10, 14)), (date(2026, 9, 28), date(2026, 10, 2))],
)
def test_une_demande_a_cote_d_un_autre_conge_est_acceptee(debut, fin):
    fiche, _, _ = _chauffeur_avec_superieur()
    _demande(fiche, date(2026, 10, 5), date(2026, 10, 9))

    assert _demande(fiche, debut, fin).pk


def test_un_conge_refuse_ne_bloque_pas_une_nouvelle_demande():
    fiche, _, chef_compte = _chauffeur_avec_superieur()
    conge = _demande(fiche, DEBUT, FIN)
    hr_services.refuser(conge, chef_compte, commentaire="Période chargée")

    assert _demande(fiche, DEBUT, FIN).pk != conge.pk


def test_un_conge_deja_decide_bloque_aussi_une_demande_qui_le_recouvre():
    fiche, _, chef_compte = _chauffeur_avec_superieur()
    conge = _demande(fiche, DEBUT, FIN)
    hr_services.valider_n1(conge, chef_compte)
    hr_services.valider_n2(conge, UserFactory(role=Role.RH))
    conge.refresh_from_db()
    assert conge.statut == StatutConge.APPROUVE

    with pytest.raises(CongeError, match=r"approuvé|chevauche"):
        _demande(fiche, DEBUT, DEBUT)


def test_le_chevauchement_message_donne_les_dates_du_conge_existant():
    fiche, _, _ = _chauffeur_avec_superieur()
    _demande(fiche, DEBUT, FIN)

    with pytest.raises(CongeError, match=r"05/10/2026 au 09/10/2026 \(en attente de validation\)"):
        _demande(fiche, DEBUT, DEBUT)


# --- écran mobile ---


def test_l_ecran_des_conges_est_reserve_au_chauffeur(client):
    assert client.get(reverse("chauffeur:conges")).status_code == 302
    for role in (Role.ADMIN, Role.DIRECTION, Role.PARCAUTO, Role.RH, Role.FINANCES, Role.CHARGE_CLIENTELE):
        client.force_login(UserFactory(role=role))
        assert client.get(reverse("chauffeur:conges")).status_code == 403, role


def test_un_compte_chauffeur_sans_fiche_n_a_pas_l_ecran_des_conges(client):
    client.force_login(UserFactory(role=Role.CHAUFFEUR))

    assert client.get(reverse("chauffeur:conges")).status_code == 403


def test_l_ecran_affiche_le_solde_les_demandes_et_l_onglet(chauffeur, client):
    fiche, _, _ = chauffeur
    _demande(fiche, DEBUT, FIN)

    reponse = client.get(reverse("chauffeur:conges"))
    texte = reponse.content.decode()

    assert reponse.status_code == 200
    assert reponse.context["droits"]["disponible"] == reponse.context["droits"]["droit_annuel"]
    assert "05/10/2026" in texte and "09/10/2026" in texte and "5 jours ouvrés" in texte
    assert reverse("chauffeur:conges") in texte  # l'onglet « Congés » de la barre de navigation
    assert "Aucune demande" not in texte


def test_l_ecran_sans_demande_l_indique(chauffeur, client):
    assert "Aucune demande" in client.get(reverse("chauffeur:conges")).content.decode()


def test_le_chauffeur_envoie_sa_demande_depuis_l_ecran(chauffeur, client):
    fiche, _, chef_compte = chauffeur

    reponse = client.post(reverse("chauffeur:conges"), DONNEES, follow=True)

    conge = Conge.objects.get(employe=fiche.personnel)
    assert (conge.date_debut, conge.date_fin, conge.jours) == (DEBUT, FIN, 5)
    assert any("Demande envoyée : 5 jours ouvrés" in m for m in _messages(reponse))
    assert Notification.objects.filter(destinataire=chef_compte, categorie=CategorieNotification.CONGE).exists()


@pytest.mark.parametrize(
    "surcharges",
    [{"date_fin": "2026-10-01"}, {"motif": ""}, {"date_debut": ""}, {"date_fin": "pas une date"}],
)
def test_une_demande_invalide_reste_sur_le_formulaire_sans_rien_creer(chauffeur, client, surcharges):
    reponse = client.post(reverse("chauffeur:conges"), {**DONNEES, **surcharges})

    assert reponse.status_code == 200 and reponse.context["form"].errors
    assert not Conge.objects.exists()


def test_une_demande_qui_chevauche_affiche_le_motif_du_refus(chauffeur, client):
    fiche, _, _ = chauffeur
    _demande(fiche, DEBUT, FIN)

    reponse = client.post(reverse("chauffeur:conges"), DONNEES)

    assert reponse.status_code == 200
    assert any("chevauche" in e for e in reponse.context["form"].non_field_errors())
    assert Conge.objects.filter(employe=fiche.personnel).count() == 1


def test_un_chauffeur_sans_superieur_voit_le_motif_au_lieu_d_une_erreur(client):
    _, compte = chauffeur_avec_compte()
    client.force_login(compte)

    reponse = client.post(reverse("chauffeur:conges"), DONNEES)

    assert reponse.status_code == 200
    assert any("supérieur" in e for e in reponse.context["form"].non_field_errors())


# --- API mobile ---


def _api(compte):
    client = APIClient()
    client.force_authenticate(compte)
    return client


@pytest.mark.parametrize("nom", ["api:mobile:conges", "api:mobile:conges_solde"])
def test_l_api_des_conges_exige_un_compte_chauffeur(nom):
    assert APIClient().get(reverse(nom)).status_code == 401
    for role in (Role.ADMIN, Role.DIRECTION, Role.PARCAUTO, Role.RH, Role.FINANCES, Role.CHARGE_CLIENTELE):
        assert _api(UserFactory(role=role)).get(reverse(nom)).status_code == 403, (nom, role)


def test_l_api_cree_et_liste_les_demandes_du_chauffeur():
    fiche, compte, _ = _chauffeur_avec_superieur()
    api = _api(compte)

    cree = api.post(reverse("api:mobile:conges"), DONNEES, format="json")
    liste = api.get(reverse("api:mobile:conges"))

    assert cree.status_code == 201
    assert (cree.data["jours"], cree.data["statut"], cree.data["statut_libelle"]) == (5, "DEMANDE", "Demande")
    assert [c["id"] for c in liste.data] == [cree.data["id"]]


def test_l_api_ne_montre_pas_les_conges_d_un_autre_chauffeur():
    _, compte, _ = _chauffeur_avec_superieur()
    autre, _, _ = _chauffeur_avec_superieur()
    _demande(autre, DEBUT, FIN)

    assert _api(compte).get(reverse("api:mobile:conges")).data == []


def test_l_api_refuse_une_periode_inversee():
    _, compte, _ = _chauffeur_avec_superieur()

    reponse = _api(compte).post(
        reverse("api:mobile:conges"), {**DONNEES, "date_fin": "2026-10-01"}, format="json"
    )

    assert reponse.status_code == 400 and "date_fin" in reponse.data


def test_l_api_traduit_les_refus_metier_en_400():
    fiche, compte, _ = _chauffeur_avec_superieur()
    _demande(fiche, DEBUT, FIN)

    reponse = _api(compte).post(reverse("api:mobile:conges"), DONNEES, format="json")

    assert reponse.status_code == 400
    assert reponse.data["code"] == "conge_error"
    assert "chevauche" in reponse.data["detail"]


def test_l_api_donne_le_solde_de_l_annee():
    fiche, compte, _ = _chauffeur_avec_superieur()

    solde = _api(compte).get(reverse("api:mobile:conges_solde")).data

    assert set(solde) == {"annee", "droit_annuel", "exceptionnels", "consommes", "disponible"}
    assert solde["disponible"] == solde["droit_annuel"]
