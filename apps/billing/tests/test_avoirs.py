"""Avoirs sur facture émise — décision du 13/10/2026, audit AV-11.

Saisi par la Finance avec un motif, validé par la Direction : numéro AV-AAAA-XXXX, reste à recouvrer et chiffre
d'affaires réduits, écriture comptable inverse. La facture d'origine reste intacte.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounting.models import EcritureComptable
from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services
from apps.billing.exceptions import ActionFactureNonAutorisee, MontantInvalide, TransitionFactureInterdite
from apps.billing.models import Avoir, ModePaiement, StatutAvoir, StatutFacture
from apps.billing.tests.helpers import direction, emise, finances

pytestmark = pytest.mark.django_db


def _facture():
    return emise(prix="1000000")  # HT 1 000 000, TVA 18 % : TTC 1 180 000


def _avoir_valide(facture, montant_ht="100000"):
    avoir = services.creer_avoir(facture, finances(), montant_ht=Decimal(montant_ht), motif="Retard de livraison")
    return services.valider_avoir(avoir, direction())


def test_un_avoir_partiel_valide_reduit_le_reste_et_porte_un_numero():
    facture = _facture()

    avoir = _avoir_valide(facture)

    assert (avoir.montant_ht, avoir.montant_tva, avoir.montant_ttc) == (100000, 18000, 118000)
    assert avoir.statut == StatutAvoir.VALIDE and avoir.numero.startswith(f"AV-{timezone.localdate().year}-")
    facture.refresh_from_db()
    assert services.reste_a_recouvrer(facture) == Decimal("1062000")
    assert services.factures_queryset().get(pk=facture.pk).reste == Decimal("1062000")
    assert facture.montant_ttc == Decimal("1180000")  # la facture d'origine n'est jamais modifiée


def test_un_avoir_total_solde_la_facture():
    facture = _facture()

    _avoir_valide(facture, montant_ht="1000000")

    facture.refresh_from_db()
    assert services.reste_a_recouvrer(facture) == 0 and facture.statut == StatutFacture.PAYEE


def test_l_avoir_passe_l_ecriture_inverse_de_la_facture():
    facture = _facture()

    avoir = _avoir_valide(facture)

    ecriture = EcritureComptable.objects.get(origine="AVOIR", origine_id=avoir.pk)
    sens = {(l.compte.numero, l.sens, l.montant) for l in ecriture.lignes.all()}
    assert sens == {("706100", "DEBIT", 100000), ("443300", "DEBIT", 18000), ("411000", "CREDIT", 118000)}


def test_l_avoir_reduit_le_chiffre_d_affaires_de_sa_periode():
    facture = _facture()
    jour = facture.date_emission
    avoir = services.creer_avoir(facture, finances(), montant_ht=Decimal("100000"), motif="Retard de livraison")
    services.valider_avoir(avoir, direction(), aujourd_hui=jour)  # même mois que la facture

    assert services.chiffre_affaires(jour, jour) == Decimal("900000")
    assert services.chiffre_affaires_par_mois(jour, jour)[(jour.year, jour.month)] == Decimal("900000")


def test_un_avoir_ne_depasse_pas_le_reste_a_recouvrer():
    facture = _facture()
    services.enregistrer_reglement(
        facture, finances(), montant=Decimal("1180000"), mode=ModePaiement.VIREMENT, date_reglement=timezone.localdate()
    )

    with pytest.raises(MontantInvalide, match="rembours"):
        services.creer_avoir(facture, finances(), montant_ht=Decimal("1000"), motif="Remise")


def test_les_regles_de_saisie_et_de_decision():
    facture = _facture()

    with pytest.raises(ActionFactureNonAutorisee):
        services.creer_avoir(facture, UserFactory(role=Role.CHARGE_CLIENTELE), montant_ht=Decimal("1000"), motif="x")
    with pytest.raises(MontantInvalide, match="motif"):
        services.creer_avoir(facture, finances(), montant_ht=Decimal("1000"), motif=" ")
    avoir = services.creer_avoir(facture, finances(), montant_ht=Decimal("1000"), motif="Remise")
    with pytest.raises(TransitionFactureInterdite, match="attend déjà"):
        services.creer_avoir(facture, finances(), montant_ht=Decimal("1000"), motif="Remise")
    with pytest.raises(ActionFactureNonAutorisee):
        services.valider_avoir(avoir, finances())  # la Direction seule

    services.refuser_avoir(avoir, direction(), motif="Pas justifié")
    avoir.refresh_from_db()
    assert avoir.statut == StatutAvoir.REFUSE and not avoir.numero
    assert services.reste_a_recouvrer(facture) == Decimal("1180000")


def test_un_brouillon_n_accepte_pas_d_avoir():
    from apps.billing.tests.helpers import brouillon

    with pytest.raises(TransitionFactureInterdite, match="émise"):
        services.creer_avoir(brouillon(prix="1000000"), finances(), montant_ht=Decimal("1000"), motif="x")


# --- écran ---


def test_la_finance_saisit_et_la_direction_valide_depuis_la_fiche(client):
    facture = _facture()
    client.force_login(finances())
    client.post(reverse("billing:avoir_ajouter", args=[facture.pk]), {"montant_ht": "100000", "motif": "Retard"})
    avoir = Avoir.objects.get()

    client.force_login(direction())
    page = client.get(reverse("billing:facture", args=[facture.pk])).content.decode()
    reponse = client.post(reverse("billing:avoir_valider", args=[facture.pk, avoir.pk]), follow=True)

    assert "Avoir" in page and reverse("billing:avoir_valider", args=[facture.pk, avoir.pk]) in page
    avoir.refresh_from_db()
    assert avoir.statut == StatutAvoir.VALIDE
    assert any("validé" in str(m) for m in reponse.context["messages"])
    pdf = client.get(reverse("billing:avoir_imprimer", args=[facture.pk, avoir.pk]), {"format": "pdf"})
    assert pdf.status_code == 200 and pdf["Content-Type"] == "application/pdf"
