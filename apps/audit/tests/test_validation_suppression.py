"""Audit M1-06 : les validations sortent en VALIDATE, une suppression physique est journalisée, le copilote est
audité ; M1-09 : le CSV contient aussi les anciennes/nouvelles valeurs et le user-agent."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounting import services as compta
from apps.accounting.models import Journal, LigneEcriture, SensEcriture
from apps.accounting.services import LigneSaisie
from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.audit.models import ActionChoices, AuditLog
from apps.billing.tests.helpers import direction, emise

pytestmark = pytest.mark.django_db


def test_la_validation_d_une_facture_est_journalisee_en_validate():
    facture = emise(prix="1000000")  # brouillon -> émise par la DIRECTION

    validations = AuditLog.objects.filter(action=ActionChoices.VALIDATE, entite="Facture", entite_id=facture.pk)

    assert validations.count() == 1
    assert validations.get().nouvelle_valeur["statut"] == "EMISE"
    # et non plus une simple « modification » du statut
    assert not AuditLog.objects.filter(
        action=ActionChoices.UPDATE, entite="Facture", entite_id=facture.pk, nouvelle_valeur__statut="EMISE"
    ).exists()


def test_la_validation_d_une_ecriture_manuelle_est_journalisee_en_validate():
    from apps.billing.tests.helpers import finances

    ecriture = compta.creer_ecriture_manuelle(finances(), date_ecriture=date(2026, 3, 1), libelle="Apport")
    compta.ajouter_ligne_manuelle(ecriture, finances(), compte="571000", sens=SensEcriture.DEBIT, montant=Decimal("500"))
    compta.ajouter_ligne_manuelle(ecriture, finances(), compte="101000", sens=SensEcriture.CREDIT, montant=Decimal("500"))

    compta.valider_ecriture_manuelle(ecriture, direction())

    assert AuditLog.objects.filter(action=ActionChoices.VALIDATE, entite="EcritureComptable", entite_id=ecriture.pk).count() == 1


def test_une_modification_ordinaire_reste_une_modification():
    from apps.billing.models import Facture

    facture = emise(prix="1000000")
    Facture.objects.filter(pk=facture.pk)  # lisible
    facture.refresh_from_db()
    facture.date_echeance = date(2027, 1, 31)
    facture.save()

    assert AuditLog.objects.filter(action=ActionChoices.UPDATE, entite="Facture", entite_id=facture.pk).exists()
    assert AuditLog.objects.filter(action=ActionChoices.VALIDATE, entite="Facture", entite_id=facture.pk).count() == 1


def test_une_suppression_physique_est_journalisee():
    ecriture = compta.creer_ecriture_manuelle(
        direction(), date_ecriture=date(2026, 3, 1), libelle="Brouillon à corriger"
    )
    ligne = compta.ajouter_ligne_manuelle(
        ecriture, direction(), compte="571000", sens=SensEcriture.DEBIT, montant=Decimal("500")
    )

    identifiant = ligne.pk  # Django remet le pk à None sur l'instance supprimée
    compta.supprimer_ligne_manuelle(ligne, direction())

    suppression = AuditLog.objects.get(action=ActionChoices.DELETE, entite="LigneEcriture", entite_id=identifiant)
    assert suppression.ancienne_valeur["montant"] == "500.00"
    assert suppression.nouvelle_valeur is None
    assert not LigneEcriture.objects.filter(pk=identifiant).exists()


def test_le_copilote_est_audite():
    from apps.drivers.models import Copilote
    from apps.hr.tests.factories import PersonnelFactory

    personnel = PersonnelFactory(poste="Copilote")
    copilote = Copilote.objects.get(personnel=personnel)
    copilote.statut = "SUSPENDU"
    copilote.save()

    assert AuditLog.objects.filter(entite="Copilote", entite_id=copilote.pk, action=ActionChoices.UPDATE).exists()


def test_le_csv_contient_les_valeurs_modifiees_et_le_user_agent(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    AuditLog.objects.create(
        action=ActionChoices.UPDATE, module="RH", entite="Personnel", entite_id=3,
        ancienne_valeur={"salaire": "100"}, nouvelle_valeur={"salaire": "200"}, user_agent="=cmd|' /C calc'!A0",
    )

    contenu = client.get(reverse("audit:export_csv"), {"module": "RH"}).content.decode("utf-8-sig")

    assert "Ancienne valeur;Nouvelle valeur;User-agent" in contenu
    assert '{""salaire"": ""100""}' in contenu and '{""salaire"": ""200""}' in contenu
    assert "'=cmd" in contenu  # le user-agent ne s'exécute pas comme une formule dans Excel


def _od_validee_par(auteur, validateur):
    ecriture = compta.creer_ecriture_manuelle(auteur, date_ecriture=date(2026, 3, 1), libelle="Apport")
    compta.ajouter_ligne_manuelle(ecriture, auteur, compte="571000", sens=SensEcriture.DEBIT, montant=Decimal("500"))
    compta.ajouter_ligne_manuelle(ecriture, auteur, compte="101000", sens=SensEcriture.CREDIT, montant=Decimal("500"))
    compta.valider_ecriture_manuelle(ecriture, validateur)
    return AuditLog.objects.get(action=ActionChoices.VALIDATE, entite="EcritureComptable", entite_id=ecriture.pk)


def test_une_validation_par_l_auteur_lui_meme_est_signalee_dans_le_journal():
    patron = direction()

    validation = _od_validee_par(patron, patron)

    assert validation.nouvelle_valeur["auto_validation"] is True


def test_une_validation_par_une_autre_personne_n_est_pas_signalee():
    from apps.billing.tests.helpers import finances

    validation = _od_validee_par(finances(), direction())

    assert "auto_validation" not in validation.nouvelle_valeur
