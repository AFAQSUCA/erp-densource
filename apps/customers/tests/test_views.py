"""Écrans clients : accès par rôle, portefeuille, fiche, création, interactions."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client as HttpClient
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.customers import services
from apps.customers.models import Client, Interaction, TypeInteraction
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory

from .factories import ClientFactory

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    compte = UserFactory(role=role)
    client.force_login(compte)
    return compte


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _donnees(**surcharges):
    donnees = {
        "raison_sociale": "Cimaf CI",
        "ncc_nif": "CI-1234567A",
        "contact_principal": "Awa Coulibaly",
        "telephone": "+2250700000000",
        "email": "awa@cimaf.ci",
        "adresse": "Abidjan, Plateau",
        "charge_clientele": "",
        "taux_tva": "18",
        "motif_exoneration": "",
        "delai_paiement_jours": "30",
    }
    donnees.update(surcharges)
    return donnees


def _interaction(**surcharges):
    donnees = {
        "type_interaction": "APPEL",
        "date_interaction": (timezone.localtime() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
        "resume": "Point sur la livraison de mardi",
    }
    donnees.update(surcharges)
    return donnees


# --- accès ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.CHARGE_CLIENTELE])
def test_les_clients_sont_accessibles_a_admin_direction_et_charge_clientele(client, role):
    _connecte(client, role)
    fiche = ClientFactory()

    assert client.get(reverse("customers:liste")).status_code == 200
    assert client.get(reverse("customers:detail", args=[fiche.pk])).status_code == 200


@pytest.mark.parametrize("role", [Role.RH, Role.PARCAUTO, Role.FINANCES, Role.CHAUFFEUR])
def test_les_clients_sont_interdits_aux_autres_roles(client, role):
    _connecte(client, role)
    fiche = ClientFactory()

    for url in (
        reverse("customers:liste"),
        reverse("customers:detail", args=[fiche.pk]),
        reverse("customers:creer"),
        reverse("customers:modifier", args=[fiche.pk]),
    ):
        assert client.get(url).status_code == 403, url


def test_la_direction_peut_desormais_modifier(client):
    """Retour réunion : la DIRECTION a la même largeur que l'ADMIN pour la saisie/modification."""
    _connecte(client, Role.DIRECTION)
    fiche = ClientFactory()

    assert client.get(reverse("customers:creer")).status_code == 200
    assert client.get(reverse("customers:modifier", args=[fiche.pk])).status_code == 200
    assert client.post(reverse("customers:interaction", args=[fiche.pk]), _interaction()).status_code != 403
    texte = client.get(reverse("customers:detail", args=[fiche.pk])).content.decode()
    assert "Modifier" in texte and "Ajouter une interaction" in texte


def test_les_clients_exigent_la_connexion(client):
    assert client.get(reverse("customers:liste")).status_code == 302


# --- liste ---


def test_la_liste_affiche_les_clients_et_filtre(client):
    charge = _connecte(client, Role.CHARGE_CLIENTELE)
    ClientFactory(raison_sociale="Cimaf", charge_clientele=charge)
    ClientFactory(raison_sociale="Solibra", taux_tva=Decimal("0"), motif_exoneration="ONG")

    tous = client.get(reverse("customers:liste"))
    recherche = client.get(reverse("customers:liste"), {"q": "soli"})
    portefeuille = client.get(reverse("customers:liste"), {"mes_clients": "on"})
    exonere = client.get(reverse("customers:liste"), {"exonere": "on"})

    assert len(tous.context["clients"]) == 2
    assert [c.raison_sociale for c in recherche.context["clients"]] == ["Solibra"]
    assert [c.raison_sociale for c in portefeuille.context["clients"]] == ["Cimaf"]
    assert [c.raison_sociale for c in exonere.context["clients"]] == ["Solibra"]
    assert "Mon portefeuille" in tous.content.decode()
    assert "Exonéré" in exonere.content.decode()


def test_le_filtre_portefeuille_n_est_propose_qu_au_charge_clientele(client):
    _connecte(client, Role.DIRECTION)

    assert "Mon portefeuille" not in client.get(reverse("customers:liste")).content.decode()


def test_la_liste_vide_invite_a_creer_un_client(client):
    _connecte(client, Role.CHARGE_CLIENTELE)

    texte = client.get(reverse("customers:liste")).content.decode()

    assert "Créez la fiche du premier client" in texte


def test_la_liste_signale_les_reclamations(client):
    auteur = _connecte(client, Role.CHARGE_CLIENTELE)
    fiche = ClientFactory()
    services.enregistrer_interaction(
        fiche, auteur, type_interaction=TypeInteraction.RECLAMATION, resume="Retard"
    )

    reponse = client.get(reverse("customers:liste"))

    assert reponse.context["clients"][0].nb_reclamations == 1


def test_la_liste_des_clients_reste_a_requetes_constantes(client, django_assert_max_num_queries):
    auteur = _connecte(client, Role.CHARGE_CLIENTELE)
    for _ in range(12):
        fiche = ClientFactory(charge_clientele=auteur)
        services.enregistrer_interaction(fiche, auteur, type_interaction=TypeInteraction.MAIL, resume="x")

    with django_assert_max_num_queries(8):
        assert client.get(reverse("customers:liste")).status_code == 200


# --- fiche ---


def test_la_fiche_affiche_les_informations_et_l_historique(client):
    auteur = _connecte(client, Role.CHARGE_CLIENTELE)
    fiche = ClientFactory(raison_sociale="Cimaf CI", taux_tva=Decimal("0"), motif_exoneration="ONG")
    services.enregistrer_interaction(
        fiche, auteur, type_interaction=TypeInteraction.REUNION, resume="Réunion de cadrage"
    )

    texte = client.get(reverse("customers:detail", args=[fiche.pk])).content.decode()

    assert "Cimaf CI" in texte and "Exonéré : ONG" in texte
    assert "Réunion de cadrage" in texte and "Historique commercial (1)" in texte


def test_la_fiche_liste_les_missions_du_client(client):
    _connecte(client, Role.DIRECTION)
    fiche = ClientFactory()
    mission = MissionFactory(client=fiche, statut=StatutMission.PLANIFIEE)
    MissionFactory(client=ClientFactory())  # mission d'un autre client

    texte = client.get(reverse("customers:detail", args=[fiche.pk])).content.decode()

    assert "Missions (1)" in texte and mission.numero in texte


def test_les_textes_saisis_sont_echappes(client):
    auteur = _connecte(client, Role.CHARGE_CLIENTELE)
    fiche = ClientFactory(raison_sociale="<script>alert(1)</script>")
    services.enregistrer_interaction(
        fiche, auteur, type_interaction=TypeInteraction.MAIL, resume="<img src=x onerror=alert(2)>"
    )

    texte = client.get(reverse("customers:detail", args=[fiche.pk])).content.decode()

    assert "<script>alert(1)</script>" not in texte
    assert "<img src=x" not in texte
    assert "&lt;img src=x onerror=alert(2)&gt;" in texte


def test_un_client_inexistant_donne_404(client):
    _connecte(client, Role.ADMIN)

    assert client.get(reverse("customers:detail", args=[999])).status_code == 404


# --- création et modification ---


def test_le_charge_clientele_cree_un_client(client):
    charge = _connecte(client, Role.CHARGE_CLIENTELE)

    reponse = client.post(
        reverse("customers:creer"), _donnees(charge_clientele=charge.pk), follow=True
    )

    fiche = Client.objects.get(ncc_nif="CI-1234567A")
    assert fiche.charge_clientele == charge and fiche.taux_tva == Decimal("18")
    assert reponse.redirect_chain[-1][0] == reverse("customers:detail", args=[fiche.pk])
    assert any("Cimaf CI" in m for m in _messages(reponse))


def test_creation_d_un_client_exonere_sans_motif_est_refusee(client):
    _connecte(client, Role.ADMIN)

    reponse = client.post(reverse("customers:creer"), _donnees(taux_tva="0"))

    assert reponse.status_code == 200
    assert "Motif obligatoire" in reponse.content.decode()
    assert not Client.objects.exists()


def test_creation_d_un_client_exonere_avec_motif(client):
    _connecte(client, Role.ADMIN)

    client.post(reverse("customers:creer"), _donnees(taux_tva="0", motif_exoneration="EXPORT"))

    assert Client.objects.get().motif_exoneration == "EXPORT"


def test_un_nif_deja_utilise_est_signale(client):
    _connecte(client, Role.ADMIN)
    ClientFactory(ncc_nif="CI-1234567A")

    reponse = client.post(reverse("customers:creer"), _donnees())

    assert "déjà utilisé" in reponse.content.decode()
    assert Client.objects.count() == 1


def test_le_formulaire_ne_propose_que_les_charges_clientele_actifs(client):
    _connecte(client, Role.ADMIN)
    bon = UserFactory(role=Role.CHARGE_CLIENTELE)
    autre = UserFactory(role=Role.FINANCES)

    propositions = set(
        client.get(reverse("customers:creer")).context["form"].fields["charge_clientele"].queryset
    )

    assert bon in propositions and autre not in propositions


def test_la_modification_met_a_jour_la_fiche(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    fiche = ClientFactory(ncc_nif="CI-0000001A")

    reponse = client.post(
        reverse("customers:modifier", args=[fiche.pk]),
        _donnees(ncc_nif="CI-0000001A", telephone="+2250101010101"),
        follow=True,
    )

    fiche.refresh_from_db()
    assert fiche.telephone == "+2250101010101" and fiche.raison_sociale == "Cimaf CI"
    assert any("mise à jour" in m for m in _messages(reponse))


def test_le_formulaire_de_modification_est_prerempli(client):
    _connecte(client, Role.ADMIN)
    fiche = ClientFactory(raison_sociale="Solibra")

    reponse = client.get(reverse("customers:modifier", args=[fiche.pk]))

    assert reponse.context["form"].initial["raison_sociale"] == "Solibra"


def test_la_creation_exige_le_csrf():
    http = HttpClient(enforce_csrf_checks=True)
    http.force_login(UserFactory(role=Role.ADMIN))

    assert http.post(reverse("customers:creer"), _donnees()).status_code == 403


# --- interactions ---


def test_le_charge_clientele_ajoute_une_interaction(client):
    auteur = _connecte(client, Role.CHARGE_CLIENTELE)
    fiche = ClientFactory()

    reponse = client.post(reverse("customers:interaction", args=[fiche.pk]), _interaction(), follow=True)

    interaction = Interaction.objects.get()
    assert interaction.auteur == auteur and interaction.client == fiche
    assert any("ajoutée" in m for m in _messages(reponse))
    assert "Point sur la livraison de mardi" in reponse.content.decode()


def test_une_interaction_sans_resume_est_refusee(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    fiche = ClientFactory()

    reponse = client.post(
        reverse("customers:interaction", args=[fiche.pk]), _interaction(resume=""), follow=True
    )

    assert not Interaction.objects.exists()
    assert _messages(reponse)


def test_une_interaction_dans_le_futur_est_refusee(client):
    _connecte(client, Role.CHARGE_CLIENTELE)
    fiche = ClientFactory()
    demain = (timezone.localtime() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")

    reponse = client.post(
        reverse("customers:interaction", args=[fiche.pk]),
        _interaction(date_interaction=demain),
        follow=True,
    )

    assert not Interaction.objects.exists()
    assert any("futur" in m for m in _messages(reponse))


def test_l_interaction_n_accepte_que_post_et_exige_le_csrf():
    http = HttpClient(enforce_csrf_checks=True)
    http.force_login(UserFactory(role=Role.CHARGE_CLIENTELE))
    fiche = ClientFactory()
    url = reverse("customers:interaction", args=[fiche.pk])

    assert http.get(url).status_code == 405
    assert http.post(url, _interaction()).status_code == 403


def test_la_modification_refuse_le_nif_d_un_autre_client(client):
    _connecte(client, Role.ADMIN)
    ClientFactory(ncc_nif="CI-0000009A")
    fiche = ClientFactory(ncc_nif="CI-0000001A")

    reponse = client.post(
        reverse("customers:modifier", args=[fiche.pk]), _donnees(ncc_nif="CI-0000009A")
    )

    assert "déjà utilisé" in reponse.content.decode()
    fiche.refresh_from_db()
    assert fiche.ncc_nif == "CI-0000001A"


def test_le_delai_de_paiement_se_saisit_et_s_affiche(client):
    _connecte(client, Role.ADMIN)

    reponse = client.post(
        reverse("customers:creer"), _donnees(delai_paiement_jours="45"), follow=True
    )

    fiche = Client.objects.get(ncc_nif="CI-1234567A")
    assert fiche.delai_paiement_jours == 45
    assert "45 jours" in reponse.content.decode()


def test_le_delai_de_paiement_doit_etre_entre_1_et_365_jours(client):
    _connecte(client, Role.ADMIN)

    for valeur in ("0", "366", "abc"):
        reponse = client.post(reverse("customers:creer"), _donnees(delai_paiement_jours=valeur))
        assert reponse.status_code == 200, valeur
    assert not Client.objects.exists()
