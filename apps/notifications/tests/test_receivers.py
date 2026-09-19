"""Qui est prévenu de quoi : congés, stock, carburant, départ de mission."""

from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.customers.tests.factories import ClientFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel import services as fuel
from apps.hr import services as hr
from apps.hr.tests.factories import PersonnelFactory
from apps.inventory import services as stock
from apps.inventory.tests.factories import ArticleFactory
from apps.missions import services as missions
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory
from apps.notifications import receivers
from apps.notifications.models import CategorieNotification, NiveauNotification, Notification

pytestmark = pytest.mark.django_db

MAINTENANT = datetime(2026, 9, 1, 8, 0, tzinfo=dt_timezone.utc)
DEBUT, FIN = date(2026, 10, 5), date(2026, 10, 9)


def _de(utilisateur):
    return list(Notification.objects.filter(destinataire=utilisateur).order_by("pk"))


class Equipe:
    def __init__(self):
        self.compte_sup = UserFactory(role=Role.PARCAUTO)
        self.superieur = PersonnelFactory(utilisateur=self.compte_sup)
        self.compte = UserFactory(role=Role.CHARGE_CLIENTELE)
        self.employe = PersonnelFactory(
            superieur=self.superieur, utilisateur=self.compte, nom="Bamba", prenom="Issa"
        )
        self.compte_rh = UserFactory(role=Role.RH)
        self.rh = PersonnelFactory(utilisateur=self.compte_rh, superieur=self.superieur)

    def demander(self, employe=None):
        return hr.demander_conge(
            employe or self.employe, date_debut=DEBUT, date_fin=FIN, motif="Repos",
            maintenant=MAINTENANT,
        )


@pytest.fixture
def equipe():
    return Equipe()


# --- congés ---


def test_le_superieur_est_prevenu_d_une_demande(equipe):
    conge = equipe.demander()

    (notification,) = _de(equipe.compte_sup)
    assert notification.categorie == CategorieNotification.CONGE
    assert notification.niveau == NiveauNotification.ATTENTION
    assert "Issa Bamba" in notification.titre
    assert "5 jours ouvrables du 05/10/2026 au 09/10/2026" in notification.message
    assert "03/09/2026" in notification.message  # 48 h après la demande
    assert notification.url == reverse("hr:conges_detail", args=[conge.pk])
    assert _de(equipe.compte) == [] and _de(equipe.compte_rh) == []


def test_une_mission_prevue_declenche_une_alerte_supplementaire_pour_le_validateur():
    compte_sup = UserFactory(role=Role.PARCAUTO)
    superieur = PersonnelFactory(utilisateur=compte_sup)
    fiche = ChauffeurFactory(personnel=PersonnelFactory(poste="Chauffeur", superieur=superieur))
    mission = MissionFactory(
        chauffeur=fiche, statut=StatutMission.PLANIFIEE, date_depart_prevue=date(2026, 10, 7)
    )

    hr.demander_conge(
        fiche.personnel, date_debut=DEBUT, date_fin=FIN, motif="x", maintenant=MAINTENANT
    )

    demande, alerte = _de(compte_sup)
    assert demande.niveau == NiveauNotification.ATTENTION
    assert alerte.niveau == NiveauNotification.URGENT
    assert "Mission prévue" in alerte.titre and mission.numero in alerte.message


def test_le_directeur_est_prevenu_de_sa_propre_demande():
    compte = UserFactory(role=Role.DIRECTION)
    directeur = PersonnelFactory(utilisateur=compte)

    hr.demander_conge(directeur, date_debut=DEBUT, date_fin=FIN, motif="x", maintenant=MAINTENANT)

    assert len(_de(compte)) == 1


def test_sans_compte_pour_le_superieur_la_demande_reste_possible_et_personne_n_est_prevenu():
    superieur = PersonnelFactory()  # fiche sans compte utilisateur
    employe = PersonnelFactory(superieur=superieur, utilisateur=UserFactory())

    conge = hr.demander_conge(
        employe, date_debut=DEBUT, date_fin=FIN, motif="x", maintenant=MAINTENANT
    )

    assert conge.pk and Notification.objects.count() == 0


def test_la_rh_est_prevenue_apres_la_validation_n1(equipe):
    conge = equipe.demander()

    hr.valider_n1(conge, equipe.compte_sup, maintenant=MAINTENANT)

    (notification,) = _de(equipe.compte_rh)
    assert "N2" in notification.titre and "Issa Bamba" in notification.titre
    assert "03/09/2026" not in notification.message and "02/09/2026" in notification.message  # 24 h
    assert _de(equipe.compte) == []


def test_la_rh_n_est_pas_prevenue_de_sa_propre_demande(equipe):
    conge = equipe.demander(equipe.rh)
    hr.valider_n1(conge, equipe.compte_sup, maintenant=MAINTENANT)

    assert _de(equipe.compte_rh) == []


def test_l_employe_est_prevenu_de_l_approbation(equipe):
    conge = equipe.demander()
    hr.valider_n1(conge, equipe.compte_sup, maintenant=MAINTENANT)

    hr.valider_n2(conge, equipe.compte_rh)

    (notification,) = _de(equipe.compte)
    assert notification.titre == "Votre congé est approuvé"
    assert "5 jours ouvrables du 05/10/2026 au 09/10/2026" in notification.message


def test_l_employe_est_prevenu_du_refus_avec_le_motif(equipe):
    conge = equipe.demander()

    hr.refuser(conge, equipe.compte_sup, commentaire="Période de forte activité")

    (notification,) = _de(equipe.compte)
    assert notification.titre == "Votre demande de congé est refusée"
    assert "Période de forte activité" in notification.message
    assert notification.niveau == NiveauNotification.ATTENTION


def test_l_employe_est_prevenu_de_l_annulation_par_la_rh(equipe):
    conge = equipe.demander()
    hr.valider_n1(conge, equipe.compte_sup, maintenant=MAINTENANT)
    hr.valider_n2(conge, equipe.compte_rh)

    hr.annuler_conge_approuve(conge, equipe.compte_rh, motif="Besoin de service")

    annulation = _de(equipe.compte)[-1]
    assert annulation.titre == "Votre congé approuvé a été annulé"
    assert "Besoin de service" in annulation.message and "restitués" in annulation.message
    assert annulation.niveau == NiveauNotification.URGENT


def test_un_employe_sans_compte_ne_bloque_pas_la_decision(equipe):
    sans_compte = PersonnelFactory(superieur=equipe.superieur)
    conge = equipe.demander(sans_compte)

    hr.refuser(conge, equipe.compte_sup, commentaire="Non")

    assert Notification.objects.filter(titre__startswith="Votre").count() == 0


def test_une_notification_en_erreur_ne_bloque_jamais_un_conge(equipe, monkeypatch, caplog):
    def panne(*args, **kwargs):
        raise RuntimeError("panne de notification")

    monkeypatch.setattr(receivers, "notifier", panne)

    conge = equipe.demander()
    hr.valider_n1(conge, equipe.compte_sup, maintenant=MAINTENANT)
    hr.valider_n2(conge, equipe.compte_rh)

    conge.refresh_from_db()
    assert conge.statut == "APPROUVE"
    assert "en erreur" in caplog.text


# --- stock ---


def test_le_parc_auto_est_prevenu_d_un_stock_bas():
    parc, autre, rh = UserFactory(role=Role.PARCAUTO), UserFactory(role=Role.PARCAUTO), UserFactory(role=Role.RH)
    article = stock.creer_article(reference="FR-1", designation="Plaquettes", seuil_minimal=5)
    stock.enregistrer_entree(article, quantite=8, prix_unitaire=Decimal("1000"))

    stock.ajuster_stock(article, variation=-4, motif="Casse")  # 4 <= seuil 5

    for compte in (parc, autre):
        (notification,) = _de(compte)
        assert notification.categorie == CategorieNotification.STOCK
        assert "Plaquettes" in notification.titre
        assert "FR-1 : 4 en stock pour un seuil minimal de 5" in notification.message
        assert notification.url == reverse("inventory:article_detail", args=[article.pk])
    assert _de(rh) == []


def test_le_stock_bas_n_est_signale_qu_au_franchissement_du_seuil():
    parc = UserFactory(role=Role.PARCAUTO)
    article = stock.creer_article(reference="FR-2", designation="Filtre", seuil_minimal=5)
    stock.enregistrer_entree(article, quantite=8, prix_unitaire=Decimal("1000"))

    stock.ajuster_stock(article, variation=-4, motif="Casse")
    stock.ajuster_stock(article, variation=-1, motif="Casse")  # déjà sous le seuil

    assert len(_de(parc)) == 1


# --- carburant ---


def _serie_pleins(consommations):
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    jour = timezone.localdate() - timedelta(days=40)
    km = 1000
    fuel.enregistrer_plein(
        vehicule=camion, chauffeur=chauffeur, date_plein=jour, station="T",
        quantite_litres=Decimal("100"), prix_unitaire=Decimal("655"), km_compteur=km,
        numero_ticket=f"T-{camion.pk}-0",
    )
    pleins = []
    for rang, conso in enumerate(consommations, start=1):
        km += 400
        pleins.append(
            fuel.enregistrer_plein(
                vehicule=camion, chauffeur=chauffeur, date_plein=jour + timedelta(days=rang),
                station="T", quantite_litres=Decimal(str(conso)) * 4,
                prix_unitaire=Decimal("655"), km_compteur=km,
                numero_ticket=f"T-{camion.pk}-{rang}", confirmer_alerte_saisie=True,
            )
        )
    return camion, pleins


def test_une_surconsommation_rouge_previent_le_parc_auto_et_la_direction():
    parc, direction, rh = (UserFactory(role=r) for r in (Role.PARCAUTO, Role.DIRECTION, Role.RH))

    camion, _ = _serie_pleins([30, 30, 30, 44])  # +46,7 % : rouge

    for compte in (parc, direction):
        (notification,) = _de(compte)
        assert notification.categorie == CategorieNotification.CARBURANT
        assert notification.niveau == NiveauNotification.URGENT
        assert f"alerte rouge sur {camion.immatriculation}" in notification.titre
        assert "44,0 L/100 km" in notification.message and "+46,7 %" in notification.message
        assert notification.url == f"{reverse('fuel:liste')}?vehicule={camion.pk}"
    assert _de(rh) == []


def test_une_alerte_jaune_est_de_niveau_attention():
    parc = UserFactory(role=Role.PARCAUTO)

    _serie_pleins([30, 30, 30, 37])  # +23,3 % : jaune

    (notification,) = _de(parc)
    assert notification.niveau == NiveauNotification.ATTENTION
    assert "alerte jaune" in notification.titre


def test_une_consommation_normale_ne_notifie_rien():
    UserFactory(role=Role.PARCAUTO)

    _serie_pleins([30, 30, 30, 31])

    assert Notification.objects.count() == 0


def test_une_notification_en_erreur_ne_bloque_pas_la_saisie_du_plein(monkeypatch, caplog):
    UserFactory(role=Role.PARCAUTO)

    def panne(*args, **kwargs):
        raise RuntimeError("panne")

    monkeypatch.setattr(receivers, "notifier", panne)

    _, pleins = _serie_pleins([30, 30, 30, 44])

    assert len(pleins) == 4 and "en erreur" in caplog.text


# --- missions ---


def _mission_affectee(client):
    mission = missions.creer_mission(
        client=client, lieu_chargement="Abidjan", lieu_livraison="Bouaké",
        nature_marchandise="Ciment", poids_t=Decimal("20"), prix_convenu=Decimal("850000"),
    )
    missions.planifier_mission(mission)
    return missions.affecter_mission(
        mission, vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory()
    )


def test_le_depart_previent_le_charge_clientele_attitre_du_client():
    attitre = UserFactory(role=Role.CHARGE_CLIENTELE)
    autre = UserFactory(role=Role.CHARGE_CLIENTELE)
    mission = _mission_affectee(ClientFactory(charge_clientele=attitre, raison_sociale="Cimaf"))

    missions.demarrer_mission(mission)

    (notification,) = _de(attitre)
    assert notification.titre == f"En cours de route : {mission.numero}"
    assert "Cimaf" in notification.message and "Abidjan" in notification.message
    assert "Bouaké" in notification.message
    assert notification.url == reverse("missions:detail", args=[mission.pk])
    assert _de(autre) == []


def test_sans_charge_attitre_tous_les_charges_clientele_sont_prevenus():
    a, b = UserFactory(role=Role.CHARGE_CLIENTELE), UserFactory(role=Role.CHARGE_CLIENTELE)
    mission = _mission_affectee(ClientFactory())

    missions.demarrer_mission(mission)

    assert len(_de(a)) == 1 and len(_de(b)) == 1
