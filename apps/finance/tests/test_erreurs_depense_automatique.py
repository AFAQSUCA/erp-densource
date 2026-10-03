"""Une dépense automatique refusée (enveloppe dépassée, décision de la direction en attente) annule
l'opération d'origine : l'utilisateur doit en voir le motif, pas une erreur 500 (audit : M6-08, M7-08, M8-07)."""

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing.exceptions import BillingError
from apps.billing.models import CategorieDepense
from apps.core.exceptions import ErreurMetier
from apps.drivers.tests.factories import ChauffeurFactory
from apps.finance import demandes
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel import services as fuel
from apps.fuel.models import Plein
from apps.garage import services as garage
from apps.garage.models import LieuReparation, OrdreReparation, StatutOr, TypeOr
from apps.inventory import services as stock
from apps.inventory.models import MouvementStock
from apps.inventory.tests.factories import ArticleFactory

pytestmark = pytest.mark.django_db


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


def _enveloppe(categorie, plafond="50000"):
    aujourd_hui = timezone.localdate()
    demandes.definir_enveloppe(
        UserFactory(role=Role.DIRECTION), categorie=categorie, annee=aujourd_hui.year, mois=aujourd_hui.month,
        montant_plafond=Decimal(plafond),
    )


def _plein(ticket, litres="100"):
    return fuel.enregistrer_plein(
        vehicule=VehiculeFactory(), chauffeur=ChauffeurFactory(), date_plein=timezone.localdate(),
        station="Total", quantite_litres=Decimal(litres), prix_unitaire=Decimal("655"),
        km_compteur=1000, numero_ticket=ticket,
    )


def test_la_base_commune_des_erreurs_metier():
    assert issubclass(BillingError, ErreurMetier)


def test_un_plein_refuse_par_l_enveloppe_affiche_le_motif_au_lieu_d_une_erreur_500(client):
    client.force_login(UserFactory(role=Role.PARCAUTO))
    _enveloppe(CategorieDepense.CARBURANT)
    _plein("T-1")  # 65 500 FCFA > 50 000 : ouvre une demande de dépassement
    camion, chauffeur = VehiculeFactory(), ChauffeurFactory()
    url = reverse("fuel:creer")

    reponse = client.post(
        url,
        {
            "vehicule": camion.pk, "chauffeur": chauffeur.pk, "date_plein": timezone.localdate().isoformat(),
            "station": "Total", "quantite_litres": "10", "prix_unitaire": "655", "km_compteur": "5000",
            "numero_ticket": "T-2",
        },
        HTTP_REFERER=url, follow=True,
    )

    assert reponse.status_code == 200
    assert any("dépassée" in m for m in _messages(reponse))
    assert not Plein.objects.filter(numero_ticket="T-2").exists()


def test_une_cloture_d_or_refusee_par_l_enveloppe_laisse_l_or_ouvert_avec_un_message(client):
    client.force_login(UserFactory(role=Role.PARCAUTO))
    _enveloppe(CategorieDepense.MAINTENANCE, plafond="10000")
    premier = garage.ouvrir_or(VehiculeFactory(), type_or=TypeOr.CURATIF, lieu=LieuReparation.INTERNE, motif="A")
    garage.cloturer_or(premier, cout_main_oeuvre=Decimal("30000"))  # dépasse : ouvre une demande
    second = garage.ouvrir_or(VehiculeFactory(), type_or=TypeOr.CURATIF, lieu=LieuReparation.INTERNE, motif="B")
    detail = reverse("garage:detail", args=[second.pk])

    reponse = client.post(
        reverse("garage:cloturer", args=[second.pk]), {"cout_main_oeuvre": "5000"},
        HTTP_REFERER=detail, follow=True,
    )

    second.refresh_from_db()
    assert reponse.status_code == 200
    assert any("dépassée" in m for m in _messages(reponse))
    assert second.statut == StatutOr.OUVERT
    assert OrdreReparation.objects.filter(pk=second.pk, statut=StatutOr.OUVERT).exists()


def test_une_entree_de_stock_refusee_par_l_enveloppe_affiche_le_motif(client):
    client.force_login(UserFactory(role=Role.PARCAUTO))
    _enveloppe(CategorieDepense.PIECES)
    article = ArticleFactory()
    stock.enregistrer_entree(article, quantite=10, prix_unitaire=Decimal("10000"))  # 100 000 > 50 000
    avant = MouvementStock.objects.count()
    detail = reverse("inventory:article_detail", args=[article.pk])

    reponse = client.post(
        reverse("inventory:entree", args=[article.pk]), {"quantite": "1", "prix_unitaire": "1000"},
        HTTP_REFERER=detail, follow=True,
    )

    assert reponse.status_code == 200
    assert any("dépassée" in m for m in _messages(reponse))
    assert MouvementStock.objects.count() == avant


def test_un_get_qui_echoue_sans_page_d_origine_n_est_pas_masque(rf):
    from apps.core.middleware import ErreurMetierMiddleware

    middleware = ErreurMetierMiddleware(lambda request: None)
    requete = rf.get("/stock/")
    requete.user = UserFactory()

    assert middleware.process_exception(requete, ErreurMetier("x")) is None


def test_le_middleware_ignore_l_api_et_les_autres_exceptions(rf):
    from apps.core.middleware import ErreurMetierMiddleware

    middleware = ErreurMetierMiddleware(lambda request: None)
    requete = rf.post("/api/v1/pleins/", HTTP_REFERER="http://testserver/x/")

    assert middleware.process_exception(requete, ErreurMetier("x")) is None
    assert middleware.process_exception(rf.post("/x/"), ValueError("autre")) is None


def test_une_page_d_origine_d_un_autre_site_est_ignoree(client):
    client.force_login(UserFactory(role=Role.PARCAUTO))
    _enveloppe(CategorieDepense.PIECES)
    article = ArticleFactory()
    stock.enregistrer_entree(article, quantite=10, prix_unitaire=Decimal("10000"))

    reponse = client.post(
        reverse("inventory:entree", args=[article.pk]), {"quantite": "1", "prix_unitaire": "1000"},
        HTTP_REFERER="https://evil.example/piege",
    )

    assert reponse.status_code == 302 and "evil.example" not in reponse["Location"]
