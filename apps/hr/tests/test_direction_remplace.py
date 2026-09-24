"""La DIRECTION se substitue au validateur d'un niveau dont le délai est dépassé (sinon l'alerte « validation
en retard » qui lui est adressée n'aurait aucune suite possible)."""

from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.hr import services
from apps.hr.exceptions import ActionNonAutorisee
from apps.hr.models import Conge, StatutConge

from .factories import PersonnelFactory

pytestmark = pytest.mark.django_db

DEBUT, FIN = date(2026, 10, 5), date(2026, 10, 9)


def _demande():
    chef = PersonnelFactory(utilisateur=UserFactory(role=Role.PARCAUTO))
    employe = PersonnelFactory(superieur=chef)
    conge = services.demander_conge(employe, date_debut=DEBUT, date_fin=FIN, motif="Repos")
    return conge, chef.utilisateur


def _en_retard(conge, *, niveau=1, retard=True):
    limite = timezone.now() + timedelta(hours=-1 if retard else 1)
    Conge.objects.filter(pk=conge.pk).update(**{f"date_limite_n{niveau}": limite})
    conge.refresh_from_db()


def _direction():
    return UserFactory(role=Role.DIRECTION)


# --- N1 ---


def test_la_direction_valide_le_n1_quand_le_delai_du_superieur_est_depasse():
    conge, _ = _demande()
    _en_retard(conge)

    assert services.actions_disponibles(conge, _direction()) == {"valider", "refuser"}
    services.valider_conge(conge, _direction())

    conge.refresh_from_db()
    assert conge.statut == StatutConge.VALIDATION_N1


def test_la_direction_refuse_le_n1_en_retard():
    conge, _ = _demande()
    _en_retard(conge)

    services.refuser(conge, _direction(), commentaire="Période de forte activité")

    conge.refresh_from_db()
    assert conge.statut == StatutConge.REFUSE


def test_avant_l_echeance_la_direction_ne_decide_pas_a_la_place_du_superieur():
    conge, _ = _demande()
    _en_retard(conge, retard=False)

    assert services.actions_disponibles(conge, _direction()) == frozenset()
    with pytest.raises(ActionNonAutorisee):
        services.valider_n1(conge, _direction())
    with pytest.raises(ActionNonAutorisee):
        services.refuser(conge, _direction())


# --- N2 ---


def test_la_direction_valide_le_n2_quand_le_delai_de_la_rh_est_depasse():
    conge, superieur = _demande()
    services.valider_n1(conge, superieur)
    _en_retard(conge, niveau=2)

    assert services.actions_disponibles(conge, _direction()) == {"valider", "refuser"}
    services.valider_conge(conge, _direction())

    conge.refresh_from_db()
    assert conge.statut == StatutConge.APPROUVE


def test_le_n2_n_est_pas_ouvert_a_la_direction_avant_l_echeance():
    conge, superieur = _demande()
    services.valider_n1(conge, superieur)
    _en_retard(conge, niveau=2, retard=False)

    with pytest.raises(ActionNonAutorisee):
        services.valider_n2(conge, _direction())


# --- limites ---


def test_les_autres_roles_n_ont_pas_ce_pouvoir_meme_en_retard():
    conge, _ = _demande()
    _en_retard(conge)

    for role in (Role.FINANCES, Role.CHARGE_CLIENTELE, Role.PARCAUTO, Role.ADMIN):
        assert services.actions_disponibles(conge, UserFactory(role=role)) == frozenset()


def test_la_direction_ne_decide_jamais_sur_sa_propre_demande_a_la_place_d_un_autre():
    direction = _direction()
    fiche = PersonnelFactory(utilisateur=direction, superieur=PersonnelFactory())
    conge = services.demander_conge(fiche, date_debut=DEBUT, date_fin=FIN, motif="Repos")
    _en_retard(conge)

    assert services.actions_disponibles(conge, direction) == frozenset()
    assert conge not in services.conges_a_valider(direction)


def test_les_demandes_en_retard_apparaissent_dans_la_liste_a_valider_de_la_direction():
    en_retard, _ = _demande()
    _en_retard(en_retard)
    dans_les_temps, _ = _demande()
    _en_retard(dans_les_temps, retard=False)

    a_valider = list(services.conges_a_valider(_direction()))

    assert en_retard in a_valider and dans_les_temps not in a_valider


def test_l_ecran_du_conge_propose_les_boutons_a_la_direction(client):
    conge, _ = _demande()
    _en_retard(conge)
    client.force_login(_direction())

    page = client.get(reverse("hr:conges_detail", args=[conge.pk])).content.decode()

    assert "Valider" in page and "Refuser" in page


def test_l_ecran_explique_pourquoi_la_direction_peut_decider(client):
    conge, superieur = _demande()
    _en_retard(conge)

    client.force_login(_direction())
    assert "à la place du validateur habituel" in client.get(reverse("hr:conges_detail", args=[conge.pk])).content.decode()

    client.force_login(superieur)  # le supérieur lui-même décide normalement : pas de mention
    assert "à la place du validateur habituel" not in client.get(reverse("hr:conges_detail", args=[conge.pk])).content.decode()
