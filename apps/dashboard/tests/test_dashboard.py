"""Tableau de bord : visibilité par rôle, centre d'alertes, indicateurs, cache, performance."""

from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.customers.tests.factories import ClientFactory
from apps.dashboard import services
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.models import StatutVehicule, TypeDocument
from apps.fleet.tests.factories import DocumentReglementaireFactory, VehiculeFactory
from apps.fuel import services as fuel_services
from apps.hr import services as hr_services
from apps.hr.models import Conge, StatutConge
from apps.hr.tests.factories import PersonnelFactory
from apps.inventory.tests.factories import ArticleFactory
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory

pytestmark = pytest.mark.django_db

AUJOURD_HUI = date(2026, 9, 1)


def _utilisateur(role):
    return UserFactory(role=role)


def _page(client, role):
    client.force_login(_utilisateur(role))
    return client.get(reverse("home"))


# --- accès et visibilité ---


@pytest.mark.parametrize("role", list(Role.values))
def test_tous_les_roles_ouvrent_le_tableau_de_bord(client, role):
    assert _page(client, role).status_code == 200


def test_le_tableau_de_bord_exige_la_connexion(client):
    assert client.get(reverse("home")).status_code == 302


VISIBLE = {
    #  exploitation, alertes, rh, clientele, finances_a_venir
    Role.ADMIN: (True, True, True, True, True),
    Role.DIRECTION: (True, True, True, True, True),
    Role.RH: (False, True, True, False, False),
    Role.CHARGE_CLIENTELE: (False, False, False, True, False),
    Role.PARCAUTO: (True, True, False, False, False),
    Role.FINANCES: (False, False, False, False, True),
    Role.CHAUFFEUR: (False, False, False, False, False),
}


@pytest.mark.parametrize("role", list(VISIBLE))
def test_chaque_role_ne_voit_que_ses_blocs(role):
    tableau = services.tableau_de_bord(_utilisateur(role), aujourd_hui=AUJOURD_HUI)

    attendu = VISIBLE[role]
    assert (
        tableau["exploitation"] is not None,
        tableau["alertes"] is not None,
        tableau["ressources_humaines"] is not None,
        tableau["clientele"] is not None,
        tableau["finances_a_venir"],
    ) == attendu
    assert tableau["espace_mobile"] == (role == Role.CHAUFFEUR)


def test_un_superutilisateur_sans_role_voit_le_tableau_de_bord_de_l_admin(client):
    client.force_login(UserFactory(role="", is_superuser=True, is_staff=True))

    reponse = client.get(reverse("home"))

    assert reponse.status_code == 200 and reponse.context["exploitation"] is not None


def test_le_chauffeur_est_renvoye_vers_l_espace_mobile(client):
    texte = _page(client, Role.CHAUFFEUR).content.decode()

    assert "espace mobile" in texte and "Centre d'alertes" not in texte


def test_les_finances_voient_l_annonce_des_indicateurs_financiers_et_pas_de_faux_chiffres(client):
    texte = _page(client, Role.FINANCES).content.decode()

    assert "Indicateurs financiers" in texte
    assert "avec le module de facturation" in texte


def test_les_blocs_interdits_ne_sont_pas_dans_la_page_du_charge_clientele(client):
    texte = _page(client, Role.CHARGE_CLIENTELE).content.decode()

    assert "Clientèle" in texte
    for titre in ("Centre d'alertes", "Ressources humaines", "Indicateurs financiers"):
        assert titre not in texte


# --- exploitation ---


def test_indicateurs_d_exploitation():
    for statut in (StatutVehicule.DISPONIBLE, StatutVehicule.DISPONIBLE, StatutVehicule.EN_MISSION,
                   StatutVehicule.EN_MAINTENANCE, StatutVehicule.IMMOBILISE):
        VehiculeFactory(statut=statut)
    MissionFactory(statut=StatutMission.PLANIFIEE)
    MissionFactory(statut=StatutMission.LIVREE, vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory())

    exploitation = services.exploitation()

    assert exploitation["camions"] == {
        "total": 6, "disponibles": 3, "en_mission": 1, "au_garage": 1,
        "immobilises": 1, "hors_service": 0,
    }
    assert exploitation["missions_a_affecter"] == 1 and exploitation["missions_a_cloturer"] == 1
    assert exploitation["missions_en_cours"] == 0
    assert exploitation["consommation"] is None


def test_la_consommation_moyenne_globale_s_affiche(client):
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    jour = timezone.localdate() - timedelta(days=10)
    for rang, (km, litres) in enumerate([(1000, 100), (1400, 120)]):
        fuel_services.enregistrer_plein(
            vehicule=camion, chauffeur=chauffeur, date_plein=jour + timedelta(days=rang),
            station="T", quantite_litres=Decimal(litres), prix_unitaire=Decimal("655"),
            km_compteur=km, numero_ticket=f"C-{rang}",
        )

    texte = _page(client, Role.PARCAUTO).content.decode()

    assert "30,0" in texte and "L/100 km" in texte


def test_sans_donnees_la_page_reste_lisible(client):
    texte = _page(client, Role.ADMIN).content.decode()

    assert "Pas encore de plein" in texte
    assert "Aucune alerte" in texte
    assert "Personne n" in texte and "Aucun départ prévu" in texte


# --- centre d'alertes ---


def _groupes(role, **kwargs):
    return {g["code"]: g for g in services.centre_alertes(role, aujourd_hui=AUJOURD_HUI, **kwargs)}


def test_alerte_documents_avec_niveau_et_comptes():
    DocumentReglementaireFactory(
        type_document=TypeDocument.ASSURANCE, date_expiration=AUJOURD_HUI + timedelta(days=10)
    )
    DocumentReglementaireFactory(date_expiration=AUJOURD_HUI + timedelta(days=200))  # pas concerné

    groupe = _groupes(Role.PARCAUTO)["documents"]

    assert groupe["nombre"] == 1 and groupe["niveau"] == "ATTENTION"
    assert groupe["lignes"][0]["detail"] == "expire dans 10 j"
    assert groupe["lignes"][0]["libelle"].startswith("Assurance · ")


def test_un_document_expire_rend_l_alerte_urgente():
    DocumentReglementaireFactory(date_expiration=AUJOURD_HUI - timedelta(days=4))

    groupe = _groupes(Role.PARCAUTO)["documents"]

    assert groupe["niveau"] == "URGENT" and groupe["lignes"][0]["detail"] == "expiré depuis 4 j"


def test_un_groupe_n_affiche_que_5_lignes_mais_compte_toutes_les_alertes():
    for i in range(8):
        DocumentReglementaireFactory(date_expiration=AUJOURD_HUI + timedelta(days=i + 1))

    groupe = _groupes(Role.PARCAUTO)["documents"]

    assert groupe["nombre"] == 8 and len(groupe["lignes"]) == 5 and groupe["autres"] == 3
    delais = [ligne["detail"] for ligne in groupe["lignes"]]
    assert delais[0] == "expire dans 1 j"  # les plus proches d'abord


def test_alerte_chauffeurs_par_document_les_plus_proches_d_abord():
    ChauffeurFactory(
        date_expiration_permis=AUJOURD_HUI + timedelta(days=20),
        date_expiration_visite_medicale=AUJOURD_HUI + timedelta(days=3),
    )

    groupe = _groupes(Role.RH)["chauffeurs"]

    assert groupe["nombre"] == 2
    assert groupe["lignes"][0]["libelle"].startswith("Visite médicale · ")
    assert groupe["lignes"][1]["libelle"].startswith("Permis · ")


def test_un_chauffeur_inactif_n_apparait_pas_dans_les_alertes():
    ChauffeurFactory(statut="INACTIF", date_expiration_permis=AUJOURD_HUI - timedelta(days=9))

    assert "chauffeurs" not in _groupes(Role.RH)


def test_alerte_stock_rupture_urgente_et_stock_bas_attention():
    ArticleFactory(designation="Filtre", reference="F-1", quantite=3, seuil_minimal=5)
    assert _groupes(Role.PARCAUTO)["stock"]["niveau"] == "ATTENTION"

    ArticleFactory(designation="Courroie", reference="C-1", quantite=0, seuil_minimal=2)
    groupe = _groupes(Role.PARCAUTO)["stock"]

    assert groupe["niveau"] == "URGENT" and groupe["nombre"] == 2
    assert groupe["lignes"][0]["detail"] == "rupture"  # les ruptures d'abord
    assert "3 en stock, seuil 5" in groupe["lignes"][1]["detail"]


def test_un_article_sans_seuil_n_est_pas_surveille():
    ArticleFactory(quantite=0, seuil_minimal=0)

    assert "stock" not in _groupes(Role.PARCAUTO)


def _plein_a_surveiller(jours_avant, litres_second=200):
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    aujourd_hui = timezone.localdate()
    fuel_services.enregistrer_plein(
        vehicule=camion, chauffeur=chauffeur, date_plein=aujourd_hui - timedelta(days=jours_avant + 5),
        station="T", quantite_litres=Decimal("100"), prix_unitaire=Decimal("655"),
        km_compteur=1000, numero_ticket=f"K-{camion.pk}-0",
    )
    fuel_services.enregistrer_plein(
        vehicule=camion, chauffeur=chauffeur, date_plein=aujourd_hui - timedelta(days=jours_avant),
        station="T", quantite_litres=Decimal(litres_second), prix_unitaire=Decimal("655"),
        km_compteur=1400, numero_ticket=f"K-{camion.pk}-1", confirmer_alerte_saisie=True,
    )
    return camion


def test_alerte_carburant_sur_les_30_derniers_jours_seulement():
    recent = _plein_a_surveiller(5)  # 50 L/100 km : anomalie
    _plein_a_surveiller(50)

    groupes = services.centre_alertes(Role.PARCAUTO, aujourd_hui=timezone.localdate())
    carburant = next(g for g in groupes if g["code"] == "carburant")

    assert carburant["nombre"] == 1 and carburant["niveau"] == "URGENT"
    assert carburant["lignes"][0]["libelle"].startswith(recent.immatriculation)
    assert "50,0 L/100 km" in carburant["lignes"][0]["detail"]


def test_alerte_conges_en_retard_pour_la_rh_la_direction_et_l_admin():
    employe = PersonnelFactory(nom="Bamba", prenom="Issa")
    Conge.objects.create(
        employe=employe, date_debut=date(2026, 10, 1), date_fin=date(2026, 10, 5), jours=5,
        motif="x", statut=StatutConge.DEMANDE,
        date_limite_n1=timezone.now() - timedelta(hours=5),
    )

    for role in (Role.RH, Role.DIRECTION, Role.ADMIN):
        groupe = _groupes(role)["conges"]
        assert groupe["lignes"][0]["libelle"] == "Issa Bamba"
        assert groupe["lignes"][0]["detail"] == "validation N1 en retard"


def test_chaque_role_ne_recoit_que_les_alertes_de_ses_ecrans():
    DocumentReglementaireFactory(date_expiration=AUJOURD_HUI + timedelta(days=2))
    ChauffeurFactory(date_expiration_permis=AUJOURD_HUI + timedelta(days=2))
    ArticleFactory(quantite=0, seuil_minimal=2)

    assert set(_groupes(Role.PARCAUTO)) == {"documents", "stock"}
    assert set(_groupes(Role.RH)) == {"chauffeurs"}
    assert set(_groupes(Role.DIRECTION)) == {"documents", "chauffeurs", "stock"}
    assert services.centre_alertes(Role.FINANCES, aujourd_hui=AUJOURD_HUI) is None
    assert services.centre_alertes(Role.CHAUFFEUR, aujourd_hui=AUJOURD_HUI) is None


def test_la_page_liste_les_alertes_avec_liens_et_voir_tout(client):
    document = DocumentReglementaireFactory(
        date_expiration=timezone.localdate() + timedelta(days=5)
    )

    texte = _page(client, Role.PARCAUTO).content.decode()

    assert "Centre d'alertes" in texte and "Documents des camions à renouveler" in texte
    assert reverse("fleet:detail", args=[document.vehicule_id]) in texte
    assert f"{reverse('fleet:liste')}?alerte=1" in texte
    assert "Aucune alerte" not in texte


def test_les_textes_saisis_sont_echappes_dans_les_alertes(client):
    ArticleFactory(designation="<script>alert(1)</script>", quantite=0, seuil_minimal=2)

    texte = _page(client, Role.PARCAUTO).content.decode()

    assert "<script>alert(1)</script>" not in texte
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in texte


# --- ressources humaines ---


def test_bloc_ressources_humaines(client):
    aujourd_hui = timezone.localdate()
    absent, futur, demandeur = PersonnelFactory(nom="Absent"), PersonnelFactory(nom="Futur"), PersonnelFactory()
    Conge.objects.create(employe=absent, date_debut=aujourd_hui - timedelta(days=1),
                         date_fin=aujourd_hui + timedelta(days=2), jours=3, motif="x",
                         statut=StatutConge.EN_COURS)
    Conge.objects.create(employe=futur, date_debut=aujourd_hui + timedelta(days=10),
                         date_fin=aujourd_hui + timedelta(days=14), jours=5, motif="x",
                         statut=StatutConge.APPROUVE)
    Conge.objects.create(employe=demandeur, date_debut=aujourd_hui + timedelta(days=40),
                         date_fin=aujourd_hui + timedelta(days=44), jours=5, motif="x",
                         statut=StatutConge.DEMANDE)

    reponse = _page(client, Role.RH)
    rh = reponse.context["ressources_humaines"]

    assert rh["effectif"] == 3 and rh["nombre_absents"] == 1
    assert [c.employe.nom for c in rh["absents"]] == ["Absent"]
    assert [c.employe.nom for c in rh["prochains"]] == ["Futur"]
    assert rh["en_attente"] == {"n1": 1, "n2": 0}
    texte = reponse.content.decode()
    assert "Absents aujourd" in texte and "Prochains départs en congé" in texte


# --- clientèle ---


def test_bloc_clientele(client):
    gros, petit = ClientFactory(raison_sociale="Gros Client"), ClientFactory(raison_sociale="Petit Client")
    for client_mission, montant in ((gros, "900000"), (petit, "100000")):
        mission = MissionFactory(
            client=client_mission, statut=StatutMission.LIVREE, prix_convenu=Decimal(montant),
            vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory(),
        )
        type(mission).objects.filter(pk=mission.pk).update(date_livraison=timezone.now())

    reponse = _page(client, Role.CHARGE_CLIENTELE)

    assert reponse.context["clientele"]["clients_actifs"] == 2
    texte = reponse.content.decode()
    assert texte.index("Gros Client") < texte.index("Petit Client")
    assert "900 000 FCFA" in texte.replace("\xa0", " ") or "900 000 FCFA" in texte.replace("\xa0", " ").replace(" ", " ")
    assert "Top 3 des clients" in texte


# --- cache ---


def test_les_indicateurs_sont_mis_en_cache_selon_le_reglage(settings):
    settings.DASHBOARD_CACHE_SECONDS = 60
    cache.clear()
    VehiculeFactory(statut=StatutVehicule.DISPONIBLE)
    premier = services.exploitation()

    VehiculeFactory(statut=StatutVehicule.DISPONIBLE)
    en_cache = services.exploitation()

    assert premier["camions"]["total"] == 1 and en_cache["camions"]["total"] == 1
    cache.clear()
    assert services.exploitation()["camions"]["total"] == 2


def test_sans_cache_les_indicateurs_sont_toujours_a_jour(settings):
    settings.DASHBOARD_CACHE_SECONDS = 0
    VehiculeFactory()
    assert services.exploitation()["camions"]["total"] == 1
    VehiculeFactory()
    assert services.exploitation()["camions"]["total"] == 2


def test_le_centre_d_alertes_n_est_jamais_mis_en_cache(settings):
    settings.DASHBOARD_CACHE_SECONDS = 60
    cache.clear()
    assert services.centre_alertes(Role.PARCAUTO, aujourd_hui=AUJOURD_HUI) == []

    DocumentReglementaireFactory(date_expiration=AUJOURD_HUI + timedelta(days=1))

    assert len(services.centre_alertes(Role.PARCAUTO, aujourd_hui=AUJOURD_HUI)) == 1
    cache.clear()


# --- performance ---


def test_le_tableau_de_bord_de_l_admin_reste_a_requetes_constantes(client, django_assert_max_num_queries):
    for i in range(15):
        VehiculeFactory()
        DocumentReglementaireFactory(date_expiration=timezone.localdate() + timedelta(days=i))
        ArticleFactory(quantite=0, seuil_minimal=2)
        ChauffeurFactory(date_expiration_permis=timezone.localdate() + timedelta(days=i))
        MissionFactory(client=ClientFactory())
    client.force_login(_utilisateur(Role.ADMIN))

    with django_assert_max_num_queries(25):
        assert client.get(reverse("home")).status_code == 200
