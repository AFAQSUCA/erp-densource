"""Écrans du carburant : liste, saisie (avec confirmation d'une saisie suspecte), analyse."""

import itertools
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.models import StatutChauffeur
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel import services
from apps.fuel.models import NiveauAlerte, Plein

pytestmark = pytest.mark.django_db

_tickets = itertools.count(1)


def _connecte(client, role):
    utilisateur = UserFactory(role=role)
    client.force_login(utilisateur)
    return utilisateur


def _messages(reponse):
    return [(m.level_tag, str(m)) for m in reponse.context["messages"]]


def _jour(decalage):
    """Date relative à aujourd'hui : décalage négatif = dans le passé."""
    return timezone.localdate() + timedelta(days=decalage)


def _plein(camion, chauffeur, *, km, litres, decalage, **surcharges):
    donnees = dict(
        vehicule=camion,
        chauffeur=chauffeur,
        date_plein=_jour(decalage),
        station="Total",
        quantite_litres=Decimal(str(litres)),
        prix_unitaire=Decimal("655"),
        km_compteur=km,
        numero_ticket=f"V-{next(_tickets)}",
        confirmer_alerte_saisie=True,
    )
    donnees.update(surcharges)
    return services.enregistrer_plein(**donnees)


def _serie(camion, chauffeur, consommations):
    """Plein initial à 1000 km puis un plein de 400 km par consommation (dans le passé)."""
    debut = -30
    _plein(camion, chauffeur, km=1000, litres=100, decalage=debut)
    for rang, conso in enumerate(consommations, start=1):
        _plein(
            camion,
            chauffeur,
            km=1000 + rang * 400,
            litres=Decimal(str(conso)) * 4,
            decalage=debut + rang,
        )
    return 1000 + len(consommations) * 400


def _donnees(camion, chauffeur, **surcharges):
    donnees = {
        "vehicule": camion.pk,
        "chauffeur": chauffeur.pk,
        "date_plein": _jour(0).isoformat(),
        "station": "Total Yopougon",
        "quantite_litres": "120",
        "prix_unitaire": "655",
        "km_compteur": "5000",
        "numero_ticket": f"F-{next(_tickets)}",
    }
    donnees.update(surcharges)
    return donnees


# --- accès par rôle ---


@pytest.mark.parametrize("role", [Role.ADMIN, Role.DIRECTION, Role.PARCAUTO])
def test_le_carburant_est_consultable_par_le_parc_auto_la_direction_et_l_admin(client, role):
    _connecte(client, role)

    assert client.get(reverse("fuel:liste")).status_code == 200
    assert client.get(reverse("fuel:analyse")).status_code == 200


@pytest.mark.parametrize("role", [Role.RH, Role.FINANCES, Role.CHARGE_CLIENTELE, Role.CHAUFFEUR])
def test_le_carburant_est_interdit_aux_autres_roles(client, role):
    _connecte(client, role)

    for nom in ("fuel:liste", "fuel:creer", "fuel:analyse"):
        assert client.get(reverse(nom)).status_code == 403, nom


def test_la_direction_ne_peut_pas_saisir_de_plein(client):
    _connecte(client, Role.DIRECTION)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()

    assert client.get(reverse("fuel:creer")).status_code == 403
    assert client.post(reverse("fuel:creer"), _donnees(camion, chauffeur)).status_code == 403
    assert Plein.objects.count() == 0


def test_un_visiteur_non_connecte_est_renvoye_vers_la_connexion(client):
    reponse = client.get(reverse("fuel:liste"))

    assert reponse.status_code == 302
    assert reponse.url.startswith(reverse("accounts:login"))


def test_le_menu_carburant_est_visible_du_parc_auto_pas_de_la_rh(client):
    _connecte(client, Role.PARCAUTO)
    assert 'href="/carburant/"' in client.get(reverse("home")).content.decode()

    autre = Client()
    _connecte(autre, Role.RH)
    assert 'href="/carburant/"' not in autre.get(reverse("home")).content.decode()


# --- liste ---


def test_la_liste_affiche_les_pleins_avec_consommation_et_ecart(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(immatriculation="4444 KL 01"), ChauffeurFactory()
    _serie(camion, chauffeur, ["30", "37"])  # le dernier : +23 % → jaune

    reponse = client.get(reverse("fuel:liste"))
    contenu = reponse.content.decode()

    assert "4444 KL 01" in contenu
    assert "37,0" in contenu and "+23,3 %" in contenu
    assert "Jaune" in contenu


def test_la_liste_affiche_les_indicateurs(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _serie(camion, chauffeur, ["30", "44"])  # 44 : rouge

    reponse = client.get(reverse("fuel:liste"))

    assert reponse.context["consommation_moyenne"] == Decimal("37.00")
    assert reponse.context["nombre_a_surveiller"] == 1
    assert "Pleins à surveiller" in reponse.content.decode()


def test_la_liste_vide_affiche_un_message(client):
    _connecte(client, Role.PARCAUTO)

    reponse = client.get(reverse("fuel:liste"))

    assert "Aucun plein trouvé" in reponse.content.decode()
    assert "Pas encore de donnée" in reponse.content.decode()


def test_la_liste_filtre_par_camion_chauffeur_periode_texte_et_alerte(client):
    _connecte(client, Role.PARCAUTO)
    camion_a, camion_b = VehiculeFactory(), VehiculeFactory()
    chauffeur_a, chauffeur_b = ChauffeurFactory(), ChauffeurFactory()
    _serie(camion_a, chauffeur_a, ["30", "44"])
    autre = _plein(camion_b, chauffeur_b, km=900, litres=100, decalage=-1, station="Shell Cocody")

    par_camion = client.get(reverse("fuel:liste"), {"vehicule": camion_b.pk})
    par_chauffeur = client.get(reverse("fuel:liste"), {"chauffeur": chauffeur_b.pk})
    par_texte = client.get(reverse("fuel:liste"), {"q": "cocody"})
    par_periode = client.get(
        reverse("fuel:liste"), {"date_debut": _jour(-1).isoformat(), "date_fin": _jour(-1).isoformat()}
    )
    par_alerte = client.get(reverse("fuel:liste"), {"alerte": "ROUGE"})

    for reponse in (par_camion, par_chauffeur, par_texte, par_periode):
        assert list(reponse.context["pleins"]) == [autre]
    assert [p.niveau_alerte for p in par_alerte.context["pleins"]] == [NiveauAlerte.ROUGE]


def test_la_consommation_moyenne_suit_le_filtre_camion(client):
    _connecte(client, Role.PARCAUTO)
    camion_a, camion_b = VehiculeFactory(), VehiculeFactory()
    chauffeur = ChauffeurFactory()
    _serie(camion_a, chauffeur, ["30"])
    _serie(camion_b, chauffeur, ["40"])

    reponse = client.get(reverse("fuel:liste"), {"vehicule": camion_b.pk})

    assert reponse.context["consommation_moyenne"] == Decimal("40.00")
    assert "selon le filtre" in reponse.content.decode()


@pytest.mark.parametrize(
    "parametres",
    [{"date_debut": "pas-une-date"}, {"vehicule": "999999"}, {"alerte": "???"}, {"chauffeur": "abc"}],
)
def test_un_filtre_invalide_est_ignore_sans_faire_echouer_la_page(client, parametres):
    _connecte(client, Role.PARCAUTO)
    _plein(VehiculeFactory(), ChauffeurFactory(), km=1000, litres=100, decalage=-1)

    reponse = client.get(reverse("fuel:liste"), parametres)

    assert reponse.status_code == 200
    assert len(reponse.context["pleins"]) == 1


def test_la_liste_est_paginee_par_20(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _plein(camion, chauffeur, km=1000, litres=100, decalage=-60)
    for rang in range(1, 21):
        _plein(camion, chauffeur, km=1000 + rang * 400, litres=120, decalage=-60 + rang)

    assert len(client.get(reverse("fuel:liste"), {"page": 2}).context["pleins"]) == 1


def test_la_liste_n_effectue_pas_une_requete_par_plein(client, django_assert_max_num_queries):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _plein(camion, chauffeur, km=1000, litres=100, decalage=-30)
    for rang in range(1, 15):
        _plein(camion, chauffeur, km=1000 + rang * 400, litres=120, decalage=-30 + rang)

    with django_assert_max_num_queries(14):
        client.get(reverse("fuel:liste"))


def test_les_donnees_saisies_sont_echappees_contre_le_xss(client):
    _connecte(client, Role.PARCAUTO)
    _plein(VehiculeFactory(), ChauffeurFactory(), km=1000, litres=100, decalage=-1, station="<script>alert(1)</script>")

    contenu = client.get(reverse("fuel:liste")).content.decode()

    assert "<script>alert(1)</script>" not in contenu
    assert "&lt;script&gt;" in contenu


# --- saisie ---


def test_le_formulaire_de_saisie_est_prerempli_avec_la_date_du_jour(client):
    _connecte(client, Role.PARCAUTO)

    reponse = client.get(reverse("fuel:creer"))

    assert reponse.status_code == 200
    assert reponse.context["form"].initial["date_plein"] == timezone.localdate()


def test_le_choix_du_chauffeur_exclut_les_inactifs(client):
    _connecte(client, Role.PARCAUTO)
    actif = ChauffeurFactory()
    ChauffeurFactory(statut=StatutChauffeur.INACTIF)

    reponse = client.get(reverse("fuel:creer"))

    assert list(reponse.context["form"].fields["chauffeur"].queryset) == [actif]


def test_le_premier_plein_d_un_camion_est_enregistre_sans_consommation(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(kilometrage=100), ChauffeurFactory()

    reponse = client.post(reverse("fuel:creer"), _donnees(camion, chauffeur), follow=True)

    plein = Plein.objects.get()
    assert plein.consommation is None
    assert reponse.redirect_chain[-1][0] == reverse("fuel:liste")
    assert any("Premier plein" in texte for _, texte in _messages(reponse))
    camion.refresh_from_db()
    assert camion.kilometrage == 5000  # le compteur du camion est relevé


def test_un_plein_normal_annonce_la_consommation_sans_alerte(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _serie(camion, chauffeur, ["30"])  # dernier km : 1400

    reponse = client.post(
        reverse("fuel:creer"),
        _donnees(camion, chauffeur, km_compteur="1800", quantite_litres="120"),
        follow=True,
    )

    messages = _messages(reponse)
    assert any(niveau == "success" and "30,0 L/100 km" in texte for niveau, texte in messages)
    assert not any(niveau == "warning" for niveau, _ in messages)


def test_un_plein_en_surconsommation_signale_l_alerte_et_l_ecart(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _serie(camion, chauffeur, ["30"])

    reponse = client.post(
        reverse("fuel:creer"),
        _donnees(camion, chauffeur, km_compteur="1800", quantite_litres="148"),  # 37 L/100
        follow=True,
    )

    avertissements = [texte for niveau, texte in _messages(reponse) if niveau == "warning"]
    assert any("Jaune" in texte and "+23,3 %" in texte for texte in avertissements)
    assert Plein.objects.latest("pk").niveau_alerte == NiveauAlerte.JAUNE


def test_une_anomalie_est_signalee(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _serie(camion, chauffeur, ["30"])

    reponse = client.post(
        reverse("fuel:creer"),
        _donnees(camion, chauffeur, km_compteur="1800", quantite_litres="180.04"),  # 45,01
        follow=True,
    )

    assert any(niveau == "warning" and "Anomalie" in texte for niveau, texte in _messages(reponse))


# --- saisie suspecte : avertissement puis confirmation ---


def _saisie_suspecte(camion, chauffeur, **surcharges):
    """Écart de +66,7 % : 200 L sur 400 km = 50 L/100 km face à une moyenne de 30."""
    return _donnees(camion, chauffeur, km_compteur="1800", quantite_litres="200", **surcharges)


def test_une_saisie_suspecte_n_est_pas_enregistree_et_demande_confirmation(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _serie(camion, chauffeur, ["30"])
    avant = Plein.objects.count()

    reponse = client.post(reverse("fuel:creer"), _saisie_suspecte(camion, chauffeur))

    contenu = reponse.content.decode()
    assert reponse.status_code == 200
    assert Plein.objects.count() == avant
    assert "Vérifiez cette saisie" in contenu
    assert "+66,7 %" in contenu and "50,0 L/100 km" in contenu
    assert 'name="confirmer"' in contenu and "Confirmer" in contenu


def test_la_page_d_avertissement_conserve_les_valeurs_saisies(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _serie(camion, chauffeur, ["30"])

    reponse = client.post(
        reverse("fuel:creer"), _saisie_suspecte(camion, chauffeur, station="Shell Marcory")
    )

    assert reponse.context["form"]["station"].value() == "Shell Marcory"
    assert reponse.context["form"]["quantite_litres"].value() == "200"
    assert "Shell Marcory" in reponse.content.decode()


def test_confirmer_une_saisie_suspecte_l_enregistre_avec_la_mention(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _serie(camion, chauffeur, ["30"])

    donnees = _saisie_suspecte(camion, chauffeur)
    donnees["confirmer"] = "1"
    reponse = client.post(reverse("fuel:creer"), donnees, follow=True)

    plein = Plein.objects.latest("pk")
    assert plein.alerte_saisie is True
    assert plein.consommation == Decimal("50.00")
    assert reponse.redirect_chain[-1][0] == reverse("fuel:liste")
    assert "Saisie confirmée" in reponse.content.decode()


def test_corriger_la_saisie_apres_l_avertissement_l_enregistre_normalement(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _serie(camion, chauffeur, ["30"])
    donnees = _saisie_suspecte(camion, chauffeur)
    client.post(reverse("fuel:creer"), donnees)  # avertissement

    donnees["quantite_litres"] = "120"  # l'erreur était dans les litres
    reponse = client.post(reverse("fuel:creer"), donnees, follow=True)

    plein = Plein.objects.latest("pk")
    assert plein.alerte_saisie is False and plein.consommation == Decimal("30.00")
    assert any("Plein enregistré" in texte for _, texte in _messages(reponse))


def test_un_ecart_de_60_pour_cent_pile_n_exige_pas_de_confirmation(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _serie(camion, chauffeur, ["30"])

    reponse = client.post(
        reverse("fuel:creer"),
        _donnees(camion, chauffeur, km_compteur="1800", quantite_litres="192"),  # 48 L/100 = +60 %
    )

    assert reponse.status_code == 302


# --- erreurs de saisie ---


def test_un_kilometrage_qui_n_augmente_pas_est_refuse_avec_un_message(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _serie(camion, chauffeur, ["30"])
    avant = Plein.objects.count()

    reponse = client.post(reverse("fuel:creer"), _donnees(camion, chauffeur, km_compteur="1400"))

    assert reponse.status_code == 200
    assert "doit dépasser" in reponse.content.decode()
    assert Plein.objects.count() == avant


def test_un_ticket_deja_enregistre_est_refuse(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _plein(camion, chauffeur, km=1000, litres=100, decalage=-5, numero_ticket="DOUBLON-1")

    reponse = client.post(
        reverse("fuel:creer"), _donnees(camion, chauffeur, km_compteur="1400", numero_ticket="DOUBLON-1")
    )

    assert "déjà enregistré" in reponse.content.decode()
    assert Plein.objects.count() == 1


def test_un_plein_anterieur_au_dernier_est_refuse(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    _plein(camion, chauffeur, km=1000, litres=100, decalage=-2)

    reponse = client.post(
        reverse("fuel:creer"),
        _donnees(camion, chauffeur, km_compteur="1400", date_plein=_jour(-5).isoformat()),
    )

    assert "dans l'ordre" in reponse.content.decode()
    assert Plein.objects.count() == 1


def test_une_date_dans_le_futur_est_refusee_par_le_formulaire(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()

    reponse = client.post(
        reverse("fuel:creer"), _donnees(camion, chauffeur, date_plein=_jour(3).isoformat())
    )

    assert "date_plein" in reponse.context["form"].errors
    assert Plein.objects.count() == 0


@pytest.mark.parametrize(
    "champ",
    [
        {"quantite_litres": "0"},
        {"quantite_litres": "-5"},
        {"quantite_litres": "abc"},
        {"prix_unitaire": "-1"},
        {"km_compteur": "-3"},
        {"numero_ticket": ""},
        {"station": ""},
        {"vehicule": "999999"},
        {"date_plein": "31/02/2026"},
    ],
)
def test_une_saisie_invalide_est_refusee_par_le_formulaire(client, champ):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()

    reponse = client.post(reverse("fuel:creer"), _donnees(camion, chauffeur, **champ))

    assert reponse.status_code == 200 and reponse.context["form"].errors
    assert Plein.objects.count() == 0


def test_un_prix_nul_est_refuse_par_le_service_avec_un_message(client):
    _connecte(client, Role.PARCAUTO)
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()

    reponse = client.post(reverse("fuel:creer"), _donnees(camion, chauffeur, prix_unitaire="0"))

    assert "strictement positif" in reponse.content.decode()
    assert Plein.objects.count() == 0


def test_la_saisie_est_protegee_par_csrf():
    client = Client(enforce_csrf_checks=True)
    client.force_login(UserFactory(role=Role.PARCAUTO))
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()

    assert client.post(reverse("fuel:creer"), _donnees(camion, chauffeur)).status_code == 403
    assert Plein.objects.count() == 0


# --- analyse ---


def test_l_analyse_affiche_les_tableaux_par_camion_et_par_chauffeur(client):
    _connecte(client, Role.DIRECTION)
    camion_a = VehiculeFactory(immatriculation="1111 AA 01")
    camion_b = VehiculeFactory(immatriculation="2222 BB 01")
    chauffeur_a = ChauffeurFactory(personnel__prenom="Awa", personnel__nom="Koné")
    chauffeur_b = ChauffeurFactory(personnel__prenom="Issa", personnel__nom="Bamba")
    _serie(camion_a, chauffeur_a, ["30", "30"])
    _serie(camion_b, chauffeur_b, ["40"])

    reponse = client.get(reverse("fuel:analyse"))
    contenu = reponse.content.decode()

    assert reponse.context["consommation_flotte"] == Decimal("33.33")
    assert "1111 AA 01" in contenu and "2222 BB 01" in contenu
    assert "Awa Koné" in contenu and "Issa Bamba" in contenu
    assert "+20,0 %" in contenu and "-10,0 %" in contenu


def test_l_analyse_sans_donnee_affiche_un_message(client):
    _connecte(client, Role.PARCAUTO)

    contenu = client.get(reverse("fuel:analyse")).content.decode()

    assert contenu.count("Aucune consommation calculée") == 2
    assert "Pas encore de donnée" in contenu


def test_une_periode_a_l_envers_est_signalee_et_ignoree(client):
    _connecte(client, Role.PARCAUTO)
    _plein(VehiculeFactory(), ChauffeurFactory(), km=1000, litres=100, decalage=-5)

    reponse = client.get(
        reverse("fuel:liste"), {"date_debut": "2026-12-31", "date_fin": "2026-01-01"}
    )

    assert reponse.status_code == 200
    assert "période ignorée" in reponse.content.decode()
    assert len(reponse.context["pleins"]) == 1  # aucun filtre de date appliqué


def test_une_date_illisible_est_signalee_sans_erreur(client):
    _connecte(client, Role.PARCAUTO)

    reponse = client.get(reverse("fuel:liste"), {"date_debut": "pas-une-date"})

    assert reponse.status_code == 200
    assert "Saisissez une date valide" in reponse.content.decode()
