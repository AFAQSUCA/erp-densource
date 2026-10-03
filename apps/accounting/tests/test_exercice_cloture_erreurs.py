"""Exercice clôturé : l'erreur est un message, jamais une erreur 500, et on ne clôture pas une année en cours
(audit : ACC-08)."""

from datetime import date

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounting import services
from apps.accounting.exceptions import (
    AccountingError,
    ActionComptableNonAutorisee,
    ClotureImpossible,
    ExerciceCloture,
)
from apps.accounting.models import StatutExercice
from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.api.exceptions import gestionnaire_erreurs
from apps.billing.models import ModePaiement
from apps.billing.tests.helpers import direction
from apps.core.exceptions import ErreurMetier
from apps.finance.models import MouvementManuel, SensMouvement

pytestmark = pytest.mark.django_db

PASSE = date(2024, 6, 5)


def test_une_erreur_comptable_est_une_erreur_metier():
    assert issubclass(AccountingError, ErreurMetier)


def test_on_ne_cloture_pas_l_annee_en_cours():
    aujourd_hui = timezone.localdate()
    exercice = services.exercice_pour(aujourd_hui)

    with pytest.raises(ClotureImpossible, match=r"qu'après le 31/12/%d" % aujourd_hui.year):
        services.cloturer_exercice(exercice, direction())

    exercice.refresh_from_db()
    assert exercice.statut == StatutExercice.OUVERT


def test_la_cloture_n_est_possible_que_le_lendemain_de_la_fin_de_l_annee(monkeypatch):
    exercice = services.exercice_pour(date(2025, 3, 1))
    monkeypatch.setattr(services.timezone, "localdate", lambda *a, **k: date(2025, 12, 31))

    with pytest.raises(ClotureImpossible):
        services.cloturer_exercice(exercice, direction())

    monkeypatch.setattr(services.timezone, "localdate", lambda *a, **k: date(2026, 1, 1))
    services.cloturer_exercice(exercice, direction())

    exercice.refresh_from_db()
    assert exercice.statut == StatutExercice.CLOTURE


def test_une_operation_datee_dans_un_exercice_clos_affiche_le_motif_au_lieu_d_une_erreur_500(client):
    services.cloturer_exercice(services.exercice_pour(PASSE), direction())
    client.force_login(UserFactory(role=Role.FINANCES))
    url = reverse("finance:tresorerie")

    reponse = client.post(
        reverse("finance:mouvement_creer"),
        {
            "sens": SensMouvement.ENTREE, "nature": "SOLDE_OUVERTURE", "date_mouvement": PASSE.isoformat(),
            "libelle": "Trop tard", "montant": "1000", "mode": ModePaiement.VIREMENT, "reference": "",
        },
        HTTP_REFERER=url, follow=True,
    )

    messages = [str(m) for m in reponse.context["messages"]]
    assert reponse.status_code == 200
    assert any("clôturé" in m for m in messages)
    assert not MouvementManuel.objects.exists()  # l'opération d'origine est annulée avec l'écriture refusée


def test_l_api_traduit_les_erreurs_comptables():
    refus = gestionnaire_erreurs(ExerciceCloture("L'exercice 2024 est clôturé."), {})
    droit = gestionnaire_erreurs(ActionComptableNonAutorisee("Interdit."), {})

    assert refus.status_code == 400
    assert refus.data == {"code": "exercice_cloture", "detail": "L'exercice 2024 est clôturé."}
    assert droit.status_code == 403
