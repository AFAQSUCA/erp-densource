"""Comptes utilisés par les écritures automatiques : jamais désactivables — audit AV-05.

Désactiver 411000 (Clients) bloquait la validation de toute facture : l'écriture automatique refusait un compte
inactif et annulait la validation.
"""

import pytest
from django.contrib.admin.sites import site
from django.urls import reverse

from apps.accounting import services
from apps.accounting.constants import COMPTES_UTILISES_PAR_LE_CODE, COMPTE_CLIENTS
from apps.accounting.exceptions import CompteProtege
from apps.accounting.models import Compte
from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing.tests.helpers import finances

pytestmark = pytest.mark.django_db


def test_chaque_compte_utilise_par_le_code_existe_dans_le_plan_comptable():
    presents = set(Compte.objects.filter(numero__in=COMPTES_UTILISES_PAR_LE_CODE).values_list("numero", flat=True))

    assert presents == COMPTES_UTILISES_PAR_LE_CODE
    assert {"411000", "706100", "443300", "445200", "120000", "521000", "571000", "521900"} <= presents


def test_un_compte_utilise_par_le_code_ne_se_desactive_pas_mais_son_libelle_se_corrige():
    clients = Compte.objects.get(numero=COMPTE_CLIENTS)

    with pytest.raises(CompteProtege, match="411000 est utilisé par les écritures automatiques"):
        services.modifier_compte(clients, finances(), libelle=clients.libelle, actif=False)
    services.modifier_compte(clients, finances(), libelle="Clients (transport)", actif=True)

    clients.refresh_from_db()
    assert clients.actif and clients.libelle == "Clients (transport)"


def test_un_compte_que_le_code_n_utilise_pas_se_desactive_toujours():
    fournisseurs = Compte.objects.get(numero="401000")
    assert "401000" not in COMPTES_UTILISES_PAR_LE_CODE

    services.modifier_compte(fournisseurs, finances(), libelle=fournisseurs.libelle, actif=False)

    fournisseurs.refresh_from_db()
    assert not fournisseurs.actif


def test_l_ecran_grise_la_case_et_explique_pourquoi(client):
    clients = Compte.objects.get(numero=COMPTE_CLIENTS)
    client.force_login(UserFactory(role=Role.FINANCES))
    url = reverse("accounting:compte_modifier", args=[clients.pk])

    page = client.get(url).content.decode()
    client.post(url, {"libelle": clients.libelle})  # case décochée : ignorée, le champ est désactivé

    assert "utilisé par les écritures automatiques" in page and "disabled" in page
    clients.refresh_from_db()
    assert clients.actif


def test_l_admin_django_ne_desactive_ni_ne_supprime_un_compte_protege(rf):
    admin_compte = site._registry[Compte]
    requete = rf.get("/")
    requete.user = UserFactory(role=Role.ADMIN, is_superuser=True, is_staff=True)
    clients = Compte.objects.get(numero=COMPTE_CLIENTS)
    fournisseurs = Compte.objects.get(numero="401000")

    assert "actif" in admin_compte.get_readonly_fields(requete, clients)
    assert "actif" not in admin_compte.get_readonly_fields(requete, fournisseurs)
    assert not admin_compte.has_delete_permission(requete, clients)
