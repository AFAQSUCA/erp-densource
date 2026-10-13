"""Annuler un plein saisi par erreur — audit AUD-03, décision du 13/10/2026.

Le dernier plein d'un camion s'annule (Parc Auto, Direction, administrateur), avec un motif ; sa dépense est annulée,
son écriture comptable contre-passée et son pointage bancaire défait. Le compteur du camion n'est pas touché : s'il
a été gonflé par erreur, l'administrateur le corrige (``fleet.services.corriger_kilometrage``).
"""

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounting.models import EcritureComptable
from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services as billing
from apps.billing.models import Depense, ModePaiement, OrigineDepense
from apps.billing.tests.helpers import finances
from apps.drivers.tests.factories import ChauffeurFactory
from apps.finance import services as finance
from apps.finance.models import LigneReleve, SensMouvement
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel import services
from apps.fuel.exceptions import ActionCarburantNonAutorisee, SaisieInvalide
from apps.fuel.models import Plein

pytestmark = pytest.mark.django_db

AUJOURD_HUI = timezone.localdate()


def _plein(camion, *, ticket="T-1", km=1000):
    return services.enregistrer_plein(
        vehicule=camion, chauffeur=ChauffeurFactory(), date_plein=AUJOURD_HUI, station="Total",
        quantite_litres=Decimal("100"), prix_unitaire=Decimal("600"), km_compteur=km, numero_ticket=ticket,
    )


def _parcauto():
    return UserFactory(role=Role.PARCAUTO)


def _depense(plein):
    return Depense.all_objects.get(origine=OrigineDepense.PLEIN, origine_id=plein.pk)


def test_annuler_le_dernier_plein_annule_sa_depense_et_contre_passe_son_ecriture():
    plein = _plein(VehiculeFactory())
    depense = _depense(plein)

    services.annuler_plein(plein, _parcauto(), motif="Ticket saisi deux fois")

    plein = Plein.all_objects.get(pk=plein.pk)
    assert plein.is_deleted and plein.motif_annulation == "Ticket saisi deux fois"
    depense.refresh_from_db()
    assert depense.is_deleted and "Ticket saisi deux fois" in depense.motif_annulation
    ecritures = EcritureComptable.objects.filter(origine__in=["DEPENSE", "CONTRE_PASSATION"])
    assert ecritures.count() == 2  # l'écriture de la dépense et sa contre-passation
    assert billing.total_depenses(AUJOURD_HUI, AUJOURD_HUI) == 0


def test_le_ticket_d_un_plein_annule_peut_etre_ressaisi():
    camion = VehiculeFactory()
    services.annuler_plein(_plein(camion, ticket="T-9"), _parcauto(), motif="Erreur de camion")

    _plein(camion, ticket="T-9")

    assert Plein.objects.filter(numero_ticket="T-9").count() == 1


def test_seul_le_dernier_plein_du_camion_s_annule():
    camion = VehiculeFactory()
    premier = _plein(camion, ticket="T-1", km=1000)
    _plein(camion, ticket="T-2", km=1500)

    with pytest.raises(SaisieInvalide, match="dernier plein"):
        services.annuler_plein(premier, _parcauto(), motif="Erreur")

    assert Plein.objects.filter(pk=premier.pk).exists()


def test_le_motif_est_obligatoire_et_seuls_ceux_qui_saisissent_annulent():
    plein = _plein(VehiculeFactory())

    with pytest.raises(SaisieInvalide, match="motif"):
        services.annuler_plein(plein, _parcauto(), motif="  ")
    for role in (Role.FINANCES, Role.CHAUFFEUR, Role.CHARGE_CLIENTELE):
        with pytest.raises(ActionCarburantNonAutorisee):
            services.annuler_plein(plein, UserFactory(role=role), motif="Erreur")
    for role in (Role.DIRECTION, Role.ADMIN):
        assert services.peut_annuler(plein, UserFactory(role=role))

    assert Plein.objects.filter(pk=plein.pk).exists()


def test_le_pointage_bancaire_de_la_depense_est_defait():
    plein = _plein(VehiculeFactory())
    depense = _depense(plein)
    billing.changer_mode_depense(depense, finances(), mode=ModePaiement.VIREMENT)
    ligne = finance.saisir_ligne_releve(
        finances(), date_operation=AUJOURD_HUI, libelle="Carburant", montant=Decimal("60000"), sens=SensMouvement.SORTIE
    )
    finance.pointer_ligne_releve(ligne, finances(), origine="DEPENSE", mouvement_id=depense.pk)

    services.annuler_plein(plein, _parcauto(), motif="Erreur")

    assert not LigneReleve.objects.get(pk=ligne.pk).pointee


# --- écran ---


def test_l_ecran_annule_le_plein_avec_un_motif(client):
    plein = _plein(VehiculeFactory())
    client.force_login(_parcauto())
    url = reverse("fuel:annuler", args=[plein.pk])

    assert "Annuler le plein" in client.get(url).content.decode()
    assert url in client.get(reverse("fuel:liste")).content.decode()  # lien sur la ligne du dernier plein
    reponse = client.post(url, {"motif": "Ticket en double"}, follow=True)

    assert reponse.redirect_chain[-1][0] == reverse("fuel:liste")
    assert any("annulé" in str(m) for m in reponse.context["messages"])
    assert not Plein.objects.filter(pk=plein.pk).exists()


def test_l_ecran_refuse_un_plein_qui_n_est_pas_le_dernier_et_les_autres_roles(client):
    camion = VehiculeFactory()
    premier = _plein(camion, ticket="T-1", km=1000)
    _plein(camion, ticket="T-2", km=1500)
    client.force_login(_parcauto())

    reponse = client.post(reverse("fuel:annuler", args=[premier.pk]), {"motif": "x"}, follow=True)

    assert any("dernier plein" in str(m) for m in reponse.context["messages"])
    client.force_login(UserFactory(role=Role.FINANCES))
    assert client.get(reverse("fuel:annuler", args=[premier.pk])).status_code == 403
