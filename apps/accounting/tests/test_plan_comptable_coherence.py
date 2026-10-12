"""Plan comptable : un numéro en chiffres, dont la classe SYSCOHADA s'accorde avec la nature — audit AV-08.

Le plan acceptait « abc » en passif ou 706999 (classe 7, produits) en charge : le bilan et le compte de résultat,
qui classent les comptes par nature, devenaient faux.
"""

import pytest
from django.urls import reverse

from apps.accounting import services
from apps.accounting.exceptions import CompteInconnu
from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing.tests.helpers import finances

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("numero", ["abc", "70 61", "7061a", "1", "012345", "12345678901"])
def test_un_numero_qui_n_est_pas_fait_de_2_a_10_chiffres_est_refuse(numero):
    with pytest.raises(CompteInconnu, match="chiffres"):
        services.creer_compte(finances(), numero=numero, libelle="Test", nature="CHARGE")


@pytest.mark.parametrize(
    "numero, nature",
    [
        ("706999", "CHARGE"), ("601999", "PRODUIT"), ("101999", "ACTIF"), ("241999", "PASSIF"),
        ("311999", "CHARGE"), ("811999", "ACTIF"), ("411999", "PRODUIT"),
    ],
)
def test_une_nature_contraire_a_la_classe_est_refusee(numero, nature):
    with pytest.raises(CompteInconnu, match=f"classe {numero[0]}"):
        services.creer_compte(finances(), numero=numero, libelle="Test", nature=nature)


@pytest.mark.parametrize(
    "numero, nature",
    [
        ("706999", "PRODUIT"), ("601999", "CHARGE"), ("101999", "PASSIF"), ("241999", "ACTIF"),
        ("401999", "PASSIF"), ("409999", "ACTIF"), ("521999", "ACTIF"), ("561999", "PASSIF"),
        ("811999", "CHARGE"), ("821999", "PRODUIT"), ("905000", "CHARGE"), ("12", "PASSIF"),
    ],
)
def test_une_nature_conforme_a_la_classe_est_acceptee(numero, nature):
    compte = services.creer_compte(finances(), numero=numero, libelle="Test", nature=nature)

    assert (compte.numero, compte.nature) == (numero, nature)


def test_l_ecran_affiche_l_incoherence_sans_creer_le_compte(client):
    client.force_login(UserFactory(role=Role.FINANCES))

    reponse = client.post(
        reverse("accounting:compte_nouveau"), {"numero": "706999", "libelle": "Erreur", "nature": "CHARGE"}
    )

    assert reponse.status_code == 200
    assert "classe 7" in reponse.content.decode()


def test_le_plan_comptable_livre_respecte_la_regle():
    from apps.accounting.models import Compte

    for compte in Compte.objects.all():
        services._exiger_classe_coherente(compte.numero, compte.nature)
