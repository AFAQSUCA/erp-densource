"""Un même compte ne valide pas un congé en N1 puis en N2 — audit M11-11, décision du 12/10/2026.

Quand le supérieur direct de l'employé est un compte RH, le N2 revient à un autre compte RH ; s'il n'y en a pas,
la Direction le fait tout de suite, sans attendre le délai de 24 h.
"""

from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.hr import services
from apps.hr.exceptions import ActionNonAutorisee
from apps.hr.models import Conge, StatutConge
from apps.notifications.models import Notification

from .factories import PersonnelFactory

pytestmark = pytest.mark.django_db

DEBUT, FIN = date(2026, 10, 5), date(2026, 10, 9)


def _valide_n1_par_un_chef_rh():
    """Un employé dont le supérieur direct est un compte RH, qui a validé le N1."""
    chef_rh = UserFactory(role=Role.RH)
    employe = PersonnelFactory(superieur=PersonnelFactory(utilisateur=chef_rh))
    conge = services.demander_conge(employe, date_debut=DEBUT, date_fin=FIN, motif="Repos")
    services.valider_n1(conge, chef_rh)
    conge.refresh_from_db()
    return conge, chef_rh


def test_le_rh_qui_a_valide_le_n1_ne_valide_pas_le_n2():
    conge, chef_rh = _valide_n1_par_un_chef_rh()

    assert services.actions_disponibles(conge, chef_rh) == frozenset()
    assert conge not in services.conges_a_valider(chef_rh)
    with pytest.raises(ActionNonAutorisee):
        services.valider_n2(conge, chef_rh)
    with pytest.raises(ActionNonAutorisee):
        services.refuser(conge, chef_rh, commentaire="Non")


def test_un_autre_rh_valide_le_n2():
    conge, _ = _valide_n1_par_un_chef_rh()
    autre_rh = UserFactory(role=Role.RH)

    assert conge in services.conges_a_valider(autre_rh)
    services.valider_n2(conge, autre_rh)

    conge.refresh_from_db()
    assert conge.statut == StatutConge.APPROUVE


def test_sans_autre_rh_la_direction_valide_le_n2_sans_attendre_le_delai():
    conge, _ = _valide_n1_par_un_chef_rh()
    direction = UserFactory(role=Role.DIRECTION)
    assert conge.date_limite_n2 > timezone.now()  # délai de 24 h pas encore dépassé

    assert conge in services.conges_a_valider(direction)
    assert services.actions_disponibles(conge, direction) == {"valider", "refuser"}
    services.valider_conge(conge, direction)

    conge.refresh_from_db()
    assert conge.statut == StatutConge.APPROUVE


def test_avec_un_autre_rh_la_direction_attend_le_delai():
    conge, _ = _valide_n1_par_un_chef_rh()
    UserFactory(role=Role.RH)
    direction = UserFactory(role=Role.DIRECTION)

    assert conge not in services.conges_a_valider(direction)
    with pytest.raises(ActionNonAutorisee):
        services.valider_n2(conge, direction)


def _avises_du_n2(conge):
    avis = Notification.objects.filter(
        titre__startswith="Congé à valider en N2", url=reverse("hr:conges_detail", args=[conge.pk])
    )
    return set(avis.values_list("destinataire", flat=True))


def test_le_n2_est_notifie_aux_autres_rh_ou_a_defaut_a_la_direction():
    direction = UserFactory(role=Role.DIRECTION)  # existe avant la validation N1, qui envoie l'avis
    conge, _ = _valide_n1_par_un_chef_rh()

    assert _avises_du_n2(conge) == {direction.pk}

    autre_rh = UserFactory(role=Role.RH)
    conge2, chef_rh2 = _valide_n1_par_un_chef_rh()
    avises = _avises_du_n2(conge2)
    assert autre_rh.pk in avises and chef_rh2.pk not in avises and direction.pk not in avises


def test_la_direction_qui_a_remplace_le_n1_ne_remplace_pas_aussi_le_n2():
    chef = PersonnelFactory(utilisateur=UserFactory(role=Role.PARCAUTO))
    employe = PersonnelFactory(superieur=chef)
    conge = services.demander_conge(employe, date_debut=DEBUT, date_fin=FIN, motif="Repos")
    direction = UserFactory(role=Role.DIRECTION)
    Conge.objects.filter(pk=conge.pk).update(date_limite_n1=timezone.now() - timedelta(hours=1))
    conge.refresh_from_db()
    services.valider_n1(conge, direction)
    Conge.objects.filter(pk=conge.pk).update(date_limite_n2=timezone.now() - timedelta(hours=1))
    conge.refresh_from_db()

    assert services.actions_disponibles(conge, direction) == frozenset()
    with pytest.raises(ActionNonAutorisee):
        services.valider_n2(conge, direction)
    services.valider_n2(conge, UserFactory(role=Role.DIRECTION))  # une autre personne de la Direction le peut
