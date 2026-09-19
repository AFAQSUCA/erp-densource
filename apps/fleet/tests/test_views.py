"""Écrans de la flotte : accès par rôle, liste, fiche, création, documents."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.models import DocumentReglementaire, StatutVehicule, TypeDocument, Vehicule

from .factories import DocumentReglementaireFactory, VehiculeFactory

pytestmark = pytest.mark.django_db


def _connecte(client, role):
    utilisateur = UserFactory(role=role)
    client.force_login(utilisateur)
    return utilisateur


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _donnees_formulaire(**surcharges):
    donnees = {
        "immatriculation": "4321 CD 01",
        "marque": "Renault",
        "modele": "T480",
        "annee": "2022",
        "vin": "VF6T480000000001A",
        "kilometrage": "12000",
        "capacite_charge_t": "26.5",
        "reservoir_l": "700",
        "chauffeur_habituel": "",
    }
    donnees.update(surcharges)
    return donnees


# --- accès par rôle ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.PARCAUTO])
def test_la_flotte_est_accessible_aux_roles_du_parc_auto(client, role):
    _connecte(client, role)

    assert client.get(reverse("fleet:liste")).status_code == 200


@pytest.mark.parametrize(
    "role", [Role.RH, Role.FINANCES, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR]
)
def test_la_flotte_est_interdite_aux_autres_roles(client, role):
    _connecte(client, role)
    camion = VehiculeFactory()

    assert client.get(reverse("fleet:liste")).status_code == 403
    assert client.get(reverse("fleet:detail", args=[camion.pk])).status_code == 403
    assert client.get(reverse("fleet:creer")).status_code == 403
    assert client.post(reverse("fleet:modifier", args=[camion.pk]), {}).status_code == 403
    assert client.post(reverse("fleet:document", args=[camion.pk]), {}).status_code == 403


def test_un_visiteur_non_connecte_est_renvoye_vers_la_connexion(client):
    reponse = client.get(reverse("fleet:liste"))

    assert reponse.status_code == 302
    assert reponse.url.startswith(reverse("accounts:login"))


def test_le_menu_flotte_est_visible_du_parc_auto_seulement(client):
    _connecte(client, Role.PARCAUTO)
    assert 'href="/flotte/"' in client.get(reverse("home")).content.decode()

    autre = Client()
    _connecte(autre, Role.FINANCES)
    assert 'href="/flotte/"' not in autre.get(reverse("home")).content.decode()


# --- liste ---


def test_la_liste_affiche_les_camions(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory(immatriculation="7777 GH 01", marque="DAF", modele="XF")

    contenu = client.get(reverse("fleet:liste")).content.decode()

    assert "7777 GH 01" in contenu and "DAF XF" in contenu
    assert "Disponible" in contenu
    assert reverse("fleet:detail", args=[camion.pk]) in contenu


def test_la_liste_vide_affiche_un_message(client):
    _connecte(client, Role.PARCAUTO)

    assert "Aucun camion trouvé" in client.get(reverse("fleet:liste")).content.decode()


def test_la_liste_filtre_par_statut_et_recherche(client):
    _connecte(client, Role.DIRECTION)
    libre = VehiculeFactory(immatriculation="1000 AA 01", marque="Volvo")
    VehiculeFactory(immatriculation="2000 BB 01", statut=StatutVehicule.EN_MISSION)

    par_statut = client.get(reverse("fleet:liste"), {"statut": "DISPONIBLE"})
    par_texte = client.get(reverse("fleet:liste"), {"q": "volvo"})

    assert list(par_statut.context["vehicules"]) == [libre]
    assert list(par_texte.context["vehicules"]) == [libre]


def test_la_liste_signale_les_documents_a_renouveler_et_filtre_dessus(client):
    _connecte(client, Role.PARCAUTO)
    aujourdhui = timezone.localdate()
    alerte = VehiculeFactory(immatriculation="1111 AA 01")
    DocumentReglementaireFactory(
        vehicule=alerte,
        date_delivrance=aujourdhui - timedelta(days=300),
        date_expiration=aujourdhui + timedelta(days=10),
    )
    VehiculeFactory(immatriculation="2222 BB 01")

    complet = client.get(reverse("fleet:liste"))
    filtre = client.get(reverse("fleet:liste"), {"alerte": "1"})

    assert "À renouveler" in complet.content.decode()
    assert list(filtre.context["vehicules"]) == [alerte]


def test_la_liste_est_paginee_par_20(client):
    _connecte(client, Role.PARCAUTO)
    for _ in range(21):
        VehiculeFactory()

    page2 = client.get(reverse("fleet:liste"), {"page": 2})

    assert len(page2.context["vehicules"]) == 1


def test_la_liste_n_effectue_pas_une_requete_par_camion(client, django_assert_max_num_queries):
    _connecte(client, Role.PARCAUTO)
    for _ in range(15):
        VehiculeFactory(chauffeur_habituel=ChauffeurFactory())

    with django_assert_max_num_queries(10):
        client.get(reverse("fleet:liste"))


def test_les_donnees_saisies_sont_echappees_contre_le_xss(client):
    _connecte(client, Role.PARCAUTO)
    VehiculeFactory(marque="<script>alert(1)</script>")

    contenu = client.get(reverse("fleet:liste")).content.decode()

    assert "<script>alert(1)</script>" not in contenu
    assert "&lt;script&gt;" in contenu


# --- fiche ---


def test_la_fiche_affiche_les_caracteristiques_et_le_chauffeur_habituel(client):
    _connecte(client, Role.PARCAUTO)
    chauffeur = ChauffeurFactory(personnel__nom="Traoré", personnel__prenom="Moussa")
    camion = VehiculeFactory(kilometrage=123456, chauffeur_habituel=chauffeur)

    contenu = client.get(reverse("fleet:detail", args=[camion.pk])).content.decode()

    assert camion.vin in contenu
    assert "Moussa Traoré" in contenu
    assert "123" in contenu and "456" in contenu  # séparateur de milliers selon la locale


def test_la_fiche_d_un_camion_inconnu_est_introuvable(client):
    _connecte(client, Role.PARCAUTO)

    assert client.get(reverse("fleet:detail", args=[999999])).status_code == 404


def test_la_fiche_montre_les_4_documents_avec_leur_etat(client):
    _connecte(client, Role.PARCAUTO)
    aujourdhui = timezone.localdate()
    camion = VehiculeFactory()
    DocumentReglementaireFactory(
        vehicule=camion,
        type_document=TypeDocument.ASSURANCE,
        date_delivrance=aujourdhui - timedelta(days=400),
        date_expiration=aujourdhui - timedelta(days=5),
    )
    DocumentReglementaireFactory(
        vehicule=camion,
        type_document=TypeDocument.PATENTE,
        date_delivrance=aujourdhui - timedelta(days=100),
        date_expiration=aujourdhui + timedelta(days=12),
    )

    reponse = client.get(reverse("fleet:detail", args=[camion.pk]))
    contenu = reponse.content.decode()

    etats = {d["code"]: d["etat"] for d in reponse.context["documents"]}
    assert etats == {
        "CARTE_GRISE": "MANQUANT",
        "ASSURANCE": "EXPIRE",
        "VISITE_TECHNIQUE": "MANQUANT",
        "PATENTE": "A_RENOUVELER",
    }
    assert "Expiré" in contenu and "depuis 5 j" in contenu
    assert "dans 12 j" in contenu
    assert "Non enregistré" in contenu


def test_le_formulaire_de_document_est_prerempli_par_le_lien_renouveler(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()

    reponse = client.get(reverse("fleet:detail", args=[camion.pk]), {"document": "PATENTE"})

    assert reponse.context["form_document"].initial["type_document"] == "PATENTE"


def test_un_type_de_document_inconnu_dans_l_url_est_ignore(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()

    reponse = client.get(reverse("fleet:detail", args=[camion.pk]), {"document": "<x>"})

    assert reponse.context["form_document"].initial["type_document"] is None


# --- création ---


def test_le_formulaire_de_creation_s_affiche(client):
    _connecte(client, Role.DIRECTION)

    reponse = client.get(reverse("fleet:creer"))

    assert reponse.status_code == 200
    assert "Nouveau camion" in reponse.content.decode()


def test_creer_un_camion_valide(client):
    _connecte(client, Role.PARCAUTO)
    chauffeur = ChauffeurFactory()

    reponse = client.post(
        reverse("fleet:creer"),
        _donnees_formulaire(chauffeur_habituel=chauffeur.pk),
        follow=True,
    )

    camion = Vehicule.objects.get()
    assert reponse.redirect_chain[-1][0] == reverse("fleet:detail", args=[camion.pk])
    assert (camion.immatriculation, camion.capacite_charge_t) == ("4321 CD 01", Decimal("26.50"))
    assert camion.chauffeur_habituel == chauffeur
    assert any("4321 CD 01" in m for m in _messages(reponse))


def test_creer_un_doublon_affiche_l_erreur_sans_creer(client):
    _connecte(client, Role.PARCAUTO)
    VehiculeFactory(immatriculation="4321 CD 01")

    reponse = client.post(reverse("fleet:creer"), _donnees_formulaire())

    assert reponse.status_code == 200
    assert "déjà utilisée" in reponse.content.decode()
    assert Vehicule.objects.count() == 1


@pytest.mark.parametrize(
    "champ", [{"annee": "1900"}, {"annee": "2999"}, {"reservoir_l": "0"}, {"kilometrage": "-1"}, {"marque": ""}]
)
def test_creer_avec_des_donnees_invalides_est_refuse_par_le_formulaire(client, champ):
    _connecte(client, Role.PARCAUTO)

    reponse = client.post(reverse("fleet:creer"), _donnees_formulaire(**champ))

    assert reponse.status_code == 200
    assert reponse.context["form"].errors
    assert Vehicule.objects.count() == 0


def test_le_choix_du_chauffeur_habituel_exclut_les_inactifs(client):
    from apps.drivers.models import StatutChauffeur

    _connecte(client, Role.PARCAUTO)
    actif = ChauffeurFactory()
    ChauffeurFactory(statut=StatutChauffeur.INACTIF)

    reponse = client.get(reverse("fleet:creer"))

    assert list(reponse.context["form"].fields["chauffeur_habituel"].queryset) == [actif]


# --- modification ---


def test_le_formulaire_de_modification_est_prerempli(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory(immatriculation="8888 KL 01", kilometrage=4000)

    reponse = client.get(reverse("fleet:modifier", args=[camion.pk]))

    assert reponse.context["form"].initial["immatriculation"] == "8888 KL 01"
    assert reponse.context["form"].initial["kilometrage"] == 4000


def test_modifier_un_camion(client):
    _connecte(client, Role.DIRECTION)
    camion = VehiculeFactory(kilometrage=1000)

    client.post(
        reverse("fleet:modifier", args=[camion.pk]),
        _donnees_formulaire(marque="Volvo", kilometrage="1500"),
    )

    camion.refresh_from_db()
    assert (camion.marque, camion.kilometrage) == ("Volvo", 1500)


def test_modifier_avec_un_compteur_en_recul_affiche_l_erreur(client):
    _connecte(client, Role.DIRECTION)
    camion = VehiculeFactory(kilometrage=9000)

    reponse = client.post(
        reverse("fleet:modifier", args=[camion.pk]), _donnees_formulaire(kilometrage="8000")
    )

    camion.refresh_from_db()
    assert camion.kilometrage == 9000
    assert "ne peut pas diminuer" in reponse.content.decode()


def test_modifier_un_camion_inconnu_est_introuvable(client):
    _connecte(client, Role.DIRECTION)

    assert client.get(reverse("fleet:modifier", args=[999999])).status_code == 404


# --- documents ---


def test_enregistrer_un_document_par_l_ecran(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()

    reponse = client.post(
        reverse("fleet:document", args=[camion.pk]),
        {
            "type_document": "ASSURANCE",
            "date_delivrance": "2026-01-01",
            "date_expiration": "2027-01-01",
        },
        follow=True,
    )

    document = DocumentReglementaire.objects.get(vehicule=camion)
    assert str(document.date_expiration) == "2027-01-01"
    assert "Assurance enregistré." in _messages(reponse)


def test_renouveler_un_document_par_l_ecran(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()
    ancien = DocumentReglementaireFactory(
        vehicule=camion,
        type_document=TypeDocument.ASSURANCE,
        date_delivrance=date(2025, 1, 1),
        date_expiration=date(2026, 1, 1),
    )

    reponse = client.post(
        reverse("fleet:document", args=[camion.pk]),
        {
            "type_document": "ASSURANCE",
            "date_delivrance": "2026-01-01",
            "date_expiration": "2027-01-01",
        },
        follow=True,
    )

    ancien.refresh_from_db()
    assert str(ancien.date_expiration) == "2027-01-01"
    assert "Assurance renouvelé." in _messages(reponse)


def test_un_document_avec_des_dates_incoherentes_est_refuse(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()

    reponse = client.post(
        reverse("fleet:document", args=[camion.pk]),
        {
            "type_document": "PATENTE",
            "date_delivrance": "2026-05-01",
            "date_expiration": "2026-04-01",
        },
        follow=True,
    )

    assert DocumentReglementaire.objects.count() == 0
    assert any("précéder" in m for m in _messages(reponse))


def test_un_document_incomplet_est_refuse_par_le_formulaire(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()

    client.post(reverse("fleet:document", args=[camion.pk]), {"type_document": "PATENTE"})

    assert DocumentReglementaire.objects.count() == 0


def test_l_enregistrement_d_un_document_refuse_le_get(client):
    _connecte(client, Role.PARCAUTO)
    camion = VehiculeFactory()

    assert client.get(reverse("fleet:document", args=[camion.pk])).status_code == 405


def test_les_formulaires_de_la_flotte_sont_proteges_par_csrf():
    client = Client(enforce_csrf_checks=True)
    client.force_login(UserFactory(role=Role.PARCAUTO))

    assert client.post(reverse("fleet:creer"), _donnees_formulaire()).status_code == 403
    assert Vehicule.objects.count() == 0
