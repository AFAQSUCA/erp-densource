"""Écrans de congés : demande, liste, fiche, décisions N1/N2, accès."""

from datetime import date, datetime
from datetime import timezone as dt_timezone

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.hr import services
from apps.hr.models import Conge, StatutConge

from .factories import PersonnelFactory

pytestmark = pytest.mark.django_db

MAINTENANT = datetime(2026, 9, 1, 8, 0, tzinfo=dt_timezone.utc)
DEBUT, FIN = date(2026, 10, 5), date(2026, 10, 9)  # 5 jours ouvrés


class Equipe:
    """Un employé, son supérieur hiérarchique, la RH et un tiers, chacun avec son compte."""

    def __init__(self):
        self.compte_sup = UserFactory(role=Role.PARCAUTO)
        self.superieur = PersonnelFactory(utilisateur=self.compte_sup, poste="Chef parc")
        self.compte = UserFactory(role=Role.CHARGE_CLIENTELE)
        self.employe = PersonnelFactory(
            superieur=self.superieur, utilisateur=self.compte, nom="Bamba", prenom="Issa"
        )
        self.compte_rh = UserFactory(role=Role.RH)
        self.rh = PersonnelFactory(utilisateur=self.compte_rh, superieur=self.superieur)
        self.tiers = UserFactory(role=Role.FINANCES)
        PersonnelFactory(utilisateur=self.tiers, superieur=self.superieur)

    def conge(self, **surcharges):
        donnees = dict(date_debut=DEBUT, date_fin=FIN, motif="Mariage de ma sœur", maintenant=MAINTENANT)
        donnees.update(surcharges)
        return services.demander_conge(self.employe, **donnees)

    def approuve(self):
        conge = self.conge()
        services.valider_n1(conge, self.compte_sup, maintenant=MAINTENANT)
        services.valider_n2(conge, self.compte_rh)
        return conge


@pytest.fixture
def equipe():
    return Equipe()


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _donnees(**surcharges):
    donnees = {"date_debut": "2026-10-05", "date_fin": "2026-10-09", "motif": "Voyage familial"}
    donnees.update(surcharges)
    return donnees


def _decision(client, conge, action, commentaire="", suivre=True):
    return client.post(
        reverse("hr:conges_decision", args=[conge.pk]),
        {"action": action, "commentaire": commentaire},
        follow=suivre,
    )


# --- accès ---


@pytest.mark.parametrize(
    "role",
    [Role.ADMIN, Role.DIRECTION, Role.RH, Role.CHARGE_CLIENTELE, Role.PARCAUTO, Role.FINANCES],
)
def test_la_liste_des_conges_est_ouverte_aux_roles_de_bureau(client, role):
    client.force_login(UserFactory(role=role))

    assert client.get(reverse("hr:conges_liste")).status_code == 200


def test_les_chauffeurs_passent_par_le_mobile_pas_par_les_conges_web(client):
    client.force_login(UserFactory(role=Role.CHAUFFEUR))

    assert client.get(reverse("hr:conges_liste")).status_code == 403


def test_les_conges_exigent_la_connexion(client):
    reponse = client.get(reverse("hr:conges_liste"))

    assert reponse.status_code == 302
    assert "/connexion" in reponse["Location"] or "login" in reponse["Location"]


# --- demande ---


def test_un_employe_demande_un_conge(client, equipe):
    client.force_login(equipe.compte)

    reponse = client.post(reverse("hr:conges_nouveau"), _donnees(), follow=True)

    conge = Conge.objects.get(employe=equipe.employe)
    assert conge.statut == StatutConge.DEMANDE and conge.jours == 5
    assert reponse.redirect_chain[-1][0] == reverse("hr:conges_detail", args=[conge.pk])
    assert any("5 jours" in m and "48 h" in m for m in _messages(reponse))


def test_le_formulaire_de_demande_affiche_le_solde(client, equipe):
    client.force_login(equipe.compte)

    texte = client.get(reverse("hr:conges_nouveau")).content.decode()

    assert "26 jours" in texte


def test_une_demande_au_dela_du_solde_est_refusee_avec_le_message_du_service(client, equipe):
    client.force_login(equipe.compte)

    reponse = client.post(
        reverse("hr:conges_nouveau"), _donnees(date_debut="2026-10-05", date_fin="2026-11-10")
    )

    assert reponse.status_code == 200
    assert "Solde insuffisant" in reponse.content.decode()
    assert not Conge.objects.exists()


def test_une_periode_a_l_envers_est_refusee(client, equipe):
    client.force_login(equipe.compte)

    reponse = client.post(
        reverse("hr:conges_nouveau"), _donnees(date_debut="2026-10-09", date_fin="2026-10-05")
    )

    assert "précède la date de début" in reponse.content.decode()
    assert not Conge.objects.exists()


def test_le_motif_est_obligatoire(client, equipe):
    client.force_login(equipe.compte)

    reponse = client.post(reverse("hr:conges_nouveau"), _donnees(motif=""))

    assert reponse.status_code == 200
    assert not Conge.objects.exists()


def test_sans_fiche_du_personnel_on_ne_peut_pas_demander(client):
    client.force_login(UserFactory(role=Role.FINANCES))

    reponse = client.get(reverse("hr:conges_nouveau"), follow=True)

    assert reponse.redirect_chain[-1][0] == reverse("hr:conges_liste")
    assert any("aucune fiche" in m for m in _messages(reponse))


def test_sans_superieur_la_demande_est_refusee(client):
    compte = UserFactory(role=Role.FINANCES)
    PersonnelFactory(utilisateur=compte)
    client.force_login(compte)

    reponse = client.post(reverse("hr:conges_nouveau"), _donnees())

    assert "Aucun supérieur hiérarchique" in reponse.content.decode()


def test_le_formulaire_de_demande_exige_le_csrf(equipe):
    client = Client(enforce_csrf_checks=True)
    client.force_login(equipe.compte)

    assert client.post(reverse("hr:conges_nouveau"), _donnees()).status_code == 403


# --- liste ---


def test_la_liste_montre_mes_demandes_et_le_solde(client, equipe):
    equipe.conge()
    client.force_login(equipe.compte)

    reponse = client.get(reverse("hr:conges_liste"))

    assert reponse.context["vue"] == "mes"
    assert [c.employe for c in reponse.context["conges"]] == [equipe.employe]
    assert reponse.context["droits"]["disponible"] == 26
    assert reponse.context["vues"] == ["mes", "a_valider"]


def test_le_superieur_arrive_sur_les_demandes_a_valider(client, equipe):
    equipe.conge()
    client.force_login(equipe.compte_sup)

    reponse = client.get(reverse("hr:conges_liste"))

    assert reponse.context["vue"] == "a_valider"
    assert reponse.context["nombre_a_valider"] == 1
    assert "Bamba" in reponse.content.decode()


def test_la_rh_voit_les_conges_de_tous_et_ceux_a_valider_en_n2(client, equipe):
    conge = equipe.conge()
    services.valider_n1(conge, equipe.compte_sup, maintenant=MAINTENANT)
    client.force_login(equipe.compte_rh)

    a_valider = client.get(reverse("hr:conges_liste"))
    tous = client.get(reverse("hr:conges_liste"), {"vue": "tous"})

    assert a_valider.context["vue"] == "a_valider"
    assert [c.pk for c in a_valider.context["conges"]] == [conge.pk]
    assert "tous" in tous.context["vues"] and tous.context["vue"] == "tous"


def test_un_employe_ordinaire_ne_peut_pas_afficher_tous_les_conges(client, equipe):
    equipe.conge()
    client.force_login(equipe.tiers)

    reponse = client.get(reverse("hr:conges_liste"), {"vue": "tous"})

    assert "tous" not in reponse.context["vues"]
    assert reponse.context["vue"] != "tous"
    assert list(reponse.context["conges"]) == []


def test_le_filtre_de_statut_de_la_liste(client, equipe):
    equipe.conge()
    client.force_login(equipe.compte_rh)

    demande = client.get(reverse("hr:conges_liste"), {"vue": "tous", "statut": "DEMANDE"})
    refuse = client.get(reverse("hr:conges_liste"), {"vue": "tous", "statut": "REFUSE"})
    inconnu = client.get(reverse("hr:conges_liste"), {"vue": "tous", "statut": "N_IMPORTE_QUOI"})

    assert len(demande.context["conges"]) == 1
    assert len(refuse.context["conges"]) == 0
    assert len(inconnu.context["conges"]) == 1  # statut inconnu ignoré


def test_la_liste_indique_le_retard_de_validation(client, equipe):
    equipe.conge()
    client.force_login(equipe.compte_rh)

    texte = client.get(reverse("hr:conges_liste"), {"vue": "tous"}).content.decode()

    assert "en retard" in texte  # échéance fixée en 2026-09-03, dépassée à la date d'exécution


def test_la_liste_des_conges_reste_a_requetes_constantes(client, equipe, django_assert_max_num_queries):
    conge = equipe.conge()
    services.valider_n1(conge, equipe.compte_sup, maintenant=MAINTENANT)
    for _ in range(8):
        autre = PersonnelFactory(superieur=equipe.superieur)
        services.demander_conge(autre, date_debut=DEBUT, date_fin=FIN, motif="x", maintenant=MAINTENANT)
    client.force_login(equipe.compte_rh)

    with django_assert_max_num_queries(16):
        assert client.get(reverse("hr:conges_liste"), {"vue": "tous"}).status_code == 200


# --- fiche d'un congé ---


def test_la_fiche_d_un_conge_est_visible_par_l_employe_son_superieur_et_la_rh(client, equipe):
    conge = equipe.conge()

    for compte in (equipe.compte, equipe.compte_sup, equipe.compte_rh):
        client.force_login(compte)
        reponse = client.get(reverse("hr:conges_detail", args=[conge.pk]))
        assert reponse.status_code == 200, compte.role
        assert "Mariage de ma sœur" in reponse.content.decode()


def test_la_fiche_d_un_conge_est_interdite_a_un_tiers(client, equipe):
    conge = equipe.conge()
    client.force_login(equipe.tiers)

    assert client.get(reverse("hr:conges_detail", args=[conge.pk])).status_code == 403


def test_les_actions_ne_sont_proposees_qu_au_validateur_du_niveau(client, equipe):
    conge = equipe.conge()
    url = reverse("hr:conges_detail", args=[conge.pk])

    client.force_login(equipe.compte_sup)
    assert "Votre décision" in client.get(url).content.decode()
    client.force_login(equipe.compte)
    assert "Votre décision" not in client.get(url).content.decode()
    client.force_login(equipe.compte_rh)
    assert "Votre décision" not in client.get(url).content.decode()


def test_le_motif_saisi_est_echappe(client, equipe):
    conge = equipe.conge(motif="<script>alert(1)</script>")
    client.force_login(equipe.compte_sup)

    texte = client.get(reverse("hr:conges_detail", args=[conge.pk])).content.decode()

    assert "<script>alert(1)</script>" not in texte
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in texte


def test_la_fiche_affiche_le_suivi_et_le_delai_depasse(client, equipe):
    conge = equipe.conge()
    services.valider_n1(conge, equipe.compte_sup, commentaire="Bon voyage", maintenant=MAINTENANT)
    client.force_login(equipe.compte_rh)

    texte = client.get(reverse("hr:conges_detail", args=[conge.pk])).content.decode()

    assert "Bon voyage" in texte
    assert "validé" in texte
    assert "le délai est dépassé" in texte


# --- décisions ---


def test_le_superieur_valide_en_n1(client, equipe):
    conge = equipe.conge()
    client.force_login(equipe.compte_sup)

    reponse = _decision(client, conge, "valider", "Accordé")

    conge.refresh_from_db()
    assert conge.statut == StatutConge.VALIDATION_N1
    assert any("validée en N1" in m for m in _messages(reponse))


def test_la_rh_valide_en_n2_et_le_message_indique_les_jours_decomptes(client, equipe):
    conge = equipe.conge()
    services.valider_n1(conge, equipe.compte_sup, maintenant=MAINTENANT)
    client.force_login(equipe.compte_rh)

    reponse = _decision(client, conge, "valider")

    conge.refresh_from_db()
    assert conge.statut == StatutConge.APPROUVE
    assert any("5 jours" in m and "2026" in m for m in _messages(reponse))


def test_l_employe_ne_peut_pas_valider_sa_propre_demande(client, equipe):
    conge = equipe.conge()
    client.force_login(equipe.compte)

    reponse = _decision(client, conge, "valider")

    conge.refresh_from_db()
    assert conge.statut == StatutConge.DEMANDE
    assert any("supérieur hiérarchique" in m for m in _messages(reponse))


def test_la_rh_ne_peut_pas_valider_en_n1(client, equipe):
    conge = equipe.conge()
    client.force_login(equipe.compte_rh)

    _decision(client, conge, "valider")

    conge.refresh_from_db()
    assert conge.statut == StatutConge.DEMANDE


def test_un_refus_exige_un_motif(client, equipe):
    conge = equipe.conge()
    client.force_login(equipe.compte_sup)

    reponse = _decision(client, conge, "refuser", "  ")

    conge.refresh_from_db()
    assert conge.statut == StatutConge.DEMANDE
    assert any("motif" in m.lower() for m in _messages(reponse))


def test_un_refus_est_enregistre_avec_son_motif(client, equipe):
    conge = equipe.conge()
    client.force_login(equipe.compte_sup)

    reponse = _decision(client, conge, "refuser", "Période de forte activité")

    conge.refresh_from_db()
    assert conge.statut == StatutConge.REFUSE
    assert conge.motif_decision == "Période de forte activité"
    assert "Période de forte activité" in reponse.content.decode()


def test_la_rh_annule_un_conge_approuve_et_les_jours_sont_restitues(client, equipe):
    conge = equipe.approuve()
    assert services.droits_conges(equipe.employe, 2026)["disponible"] == 21
    client.force_login(equipe.compte_rh)

    reponse = _decision(client, conge, "annuler", "Besoin de service")

    conge.refresh_from_db()
    assert conge.statut == StatutConge.REFUSE
    assert services.droits_conges(equipe.employe, 2026)["disponible"] == 26
    assert any("restitués" in m for m in _messages(reponse))


def test_le_superieur_ne_peut_pas_annuler_un_conge_approuve(client, equipe):
    conge = equipe.approuve()
    client.force_login(equipe.compte_sup)

    _decision(client, conge, "annuler", "Non")

    conge.refresh_from_db()
    assert conge.statut == StatutConge.APPROUVE


def test_une_decision_sur_un_conge_deja_traite_est_signalee(client, equipe):
    conge = equipe.approuve()
    client.force_login(equipe.compte_sup)

    reponse = _decision(client, conge, "valider")

    assert any("validé N1" in m for m in _messages(reponse))


def test_un_tiers_ne_peut_pas_decider(client, equipe):
    conge = equipe.conge()
    client.force_login(equipe.tiers)

    assert _decision(client, conge, "valider", suivre=False).status_code == 403
    conge.refresh_from_db()
    assert conge.statut == StatutConge.DEMANDE


def test_une_action_inconnue_est_refusee(client, equipe):
    conge = equipe.conge()
    client.force_login(equipe.compte_sup)

    _decision(client, conge, "supprimer")

    conge.refresh_from_db()
    assert conge.statut == StatutConge.DEMANDE


def test_la_decision_n_accepte_que_post_et_exige_le_csrf(equipe):
    conge = equipe.conge()
    client = Client(enforce_csrf_checks=True)
    client.force_login(equipe.compte_sup)
    url = reverse("hr:conges_decision", args=[conge.pk])

    assert client.get(url).status_code == 405
    assert client.post(url, {"action": "valider"}).status_code == 403
    conge.refresh_from_db()
    assert conge.statut == StatutConge.DEMANDE


def test_le_directeur_valide_lui_meme_sa_demande_de_conge(client):
    compte = UserFactory(role=Role.DIRECTION)
    directeur = PersonnelFactory(utilisateur=compte)
    conge = services.demander_conge(directeur, date_debut=DEBUT, date_fin=FIN, motif="Repos", maintenant=MAINTENANT)
    client.force_login(compte)

    assert client.get(reverse("hr:conges_liste")).context["vue"] == "a_valider"
    _decision(client, conge, "valider")

    conge.refresh_from_db()
    assert conge.statut == StatutConge.VALIDATION_N1
