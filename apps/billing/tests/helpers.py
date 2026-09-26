"""Aides de test : missions livrées, factures à tous les stades, comptes par rôle."""

from datetime import date
from decimal import Decimal

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services
from apps.customers.tests.factories import ClientFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory

JOUR = date(2026, 9, 1)


def finances():
    return UserFactory(role=Role.FINANCES)


def direction():
    return UserFactory(role=Role.DIRECTION)


def mission_livree(*, prix="1000000", client=None, statut=StatutMission.LIVREE, **surcharges):
    return MissionFactory(
        client=client or ClientFactory(),
        statut=statut,
        prix_convenu=Decimal(prix),
        vehicule=VehiculeFactory(),
        chauffeur=ChauffeurFactory(),
        **surcharges,
    )


def brouillon(*, prix="1000000", acteur=None, **surcharges):
    return services.creer_facture(mission_livree(prix=prix, **surcharges), acteur or finances())


def a_valider(**surcharges):
    facture = brouillon(**surcharges)
    services.soumettre(facture, finances())
    return facture


def emise(*, aujourd_hui=JOUR, **surcharges):
    facture = a_valider(**surcharges)
    services.valider(facture, direction(), aujourd_hui=aujourd_hui)
    return facture


# --- devis (R5) ---


def charge_clientele():
    return UserFactory(role=Role.CHARGE_CLIENTELE)


def proforma_brouillon(*, prix="300000", acteur=None, client=None, **surcharges):
    """Prix HT par défaut sous le seuil de validation direction (TTC 354 000 < 500 000)."""
    return services.creer_proforma(
        acteur or charge_clientele(),
        client=client or ClientFactory(),
        lieu_chargement=surcharges.pop("lieu_chargement", "Abidjan"),
        lieu_livraison=surcharges.pop("lieu_livraison", "Bouaké"),
        nature_marchandise=surcharges.pop("nature_marchandise", "Ciment"),
        poids_t=surcharges.pop("poids_t", Decimal("20")),
        prix_convenu=Decimal(prix),
        **surcharges,
    )


def proforma_soumise(**surcharges):
    proforma = proforma_brouillon(**surcharges)
    services.soumettre_proforma(proforma, charge_clientele())
    return proforma


def proforma_validee(*, aujourd_hui=JOUR, **surcharges):
    """Validée par la seule finance (montant sous le seuil par défaut : 1 000 000 FCFA)."""
    proforma = proforma_soumise(**surcharges)
    services.valider_proforma(proforma, finances(), aujourd_hui=aujourd_hui)
    return proforma


def proforma_envoyee(*, aujourd_hui=JOUR, **surcharges):
    proforma = proforma_validee(aujourd_hui=aujourd_hui, **surcharges)
    services.envoyer_proforma_au_client(proforma, charge_clientele(), aujourd_hui=aujourd_hui)
    return proforma
