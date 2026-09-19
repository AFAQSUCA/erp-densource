"""Envoi, dédoublonnage et lecture des notifications."""

import pytest
from django.core import mail

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.notifications import services
from apps.notifications.models import CategorieNotification, NiveauNotification, Notification

pytestmark = pytest.mark.django_db


def _notifier(destinataires, **surcharges):
    donnees = dict(categorie=CategorieNotification.STOCK, titre="Stock bas", message="Détail")
    donnees.update(surcharges)
    return services.notifier(destinataires, **donnees)


def test_une_notification_par_destinataire_avec_valeurs_par_defaut():
    a, b = UserFactory(), UserFactory()

    creees = _notifier([a, b], url="/stock/")

    assert {n.destinataire for n in creees} == {a, b}
    notification = Notification.objects.get(destinataire=a)
    assert notification.niveau == NiveauNotification.INFO
    assert notification.lue_le is None and not notification.est_lue
    assert notification.url == "/stock/"


def test_les_doublons_les_vides_et_les_inactifs_sont_ignores():
    actif = UserFactory()
    inactif = UserFactory(is_active=False)

    creees = _notifier([actif, actif, None, inactif])

    assert [n.destinataire for n in creees] == [actif]
    assert Notification.objects.count() == 1


def test_le_titre_est_tronque_a_la_longueur_du_champ():
    creees = _notifier([UserFactory()], titre="x" * 500)

    assert len(creees[0].titre) == 200


def test_une_cle_d_unicite_n_envoie_qu_une_fois_par_destinataire():
    a, b = UserFactory(), UserFactory()

    premiere = _notifier([a], cle="doc:1")
    deuxieme = _notifier([a, b], cle="doc:1")

    assert len(premiere) == 1
    assert [n.destinataire for n in deuxieme] == [b]  # a l'a déjà reçue
    assert Notification.objects.filter(cle_unicite="doc:1").count() == 2


def test_sans_cle_chaque_appel_cree_une_notification():
    a = UserFactory()

    _notifier([a])
    _notifier([a])

    assert Notification.objects.filter(destinataire=a).count() == 2


def test_utilisateurs_du_role_ne_liste_que_les_comptes_actifs():
    rh = UserFactory(role=Role.RH)
    UserFactory(role=Role.RH, is_active=False)
    UserFactory(role=Role.FINANCES)

    assert list(services.utilisateurs_du_role(Role.RH)) == [rh]
    assert services.utilisateurs_du_role(Role.RH, Role.FINANCES).count() == 2


# --- lecture ---


def test_comptage_et_marquage_de_lecture():
    a, b = UserFactory(), UserFactory()
    _notifier([a])
    _notifier([a])
    _notifier([b])

    assert services.nombre_non_lues(a) == 2
    premiere = services.notifications_de(a).first()
    services.marquer_lue(premiere)
    assert services.nombre_non_lues(a) == 1
    premiere.refresh_from_db()
    assert premiere.est_lue
    ancienne_date = premiere.lue_le
    services.marquer_lue(premiere)  # idempotent
    premiere.refresh_from_db()
    assert premiere.lue_le == ancienne_date

    assert services.marquer_toutes_lues(a) == 1
    assert services.nombre_non_lues(a) == 0
    assert services.nombre_non_lues(b) == 1  # celles des autres sont intactes


def test_le_filtre_non_lues():
    a = UserFactory()
    _notifier([a])
    _notifier([a])
    services.marquer_lue(services.notifications_de(a).first())

    assert services.notifications_de(a).count() == 2
    assert services.notifications_de(a, non_lues=True).count() == 1


# --- e-mail ---


def test_l_email_n_est_pas_envoye_quand_il_est_desactive(settings, django_capture_on_commit_callbacks):
    settings.NOTIFICATIONS_EMAIL = False

    with django_capture_on_commit_callbacks(execute=True):
        _notifier([UserFactory(email="a@ex.ci")])

    assert mail.outbox == []


def test_l_email_est_envoye_apres_validation_avec_le_lien_absolu(
    settings, django_capture_on_commit_callbacks
):
    settings.NOTIFICATIONS_EMAIL = True
    settings.NOTIFICATIONS_URL_BASE = "https://erp.example.ci/"
    destinataire = UserFactory(email="awa@example.ci")

    with django_capture_on_commit_callbacks(execute=True):
        creees = _notifier([destinataire], titre="Stock bas : frein", url="/stock/articles/3/")
        assert mail.outbox == []  # jamais avant la validation de la transaction

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ["awa@example.ci"] and message.subject == "Stock bas : frein"
    assert "Ouvrir : https://erp.example.ci/stock/articles/3/" in message.body
    creees[0].refresh_from_db()
    assert creees[0].email_envoye


def test_pas_d_email_sans_adresse(settings, django_capture_on_commit_callbacks):
    settings.NOTIFICATIONS_EMAIL = True

    with django_capture_on_commit_callbacks(execute=True):
        creees = _notifier([UserFactory(email="")])

    assert mail.outbox == []
    assert not creees[0].email_envoye


def test_un_email_en_echec_ne_fait_pas_echouer_l_operation(
    settings, django_capture_on_commit_callbacks, monkeypatch, caplog
):
    settings.NOTIFICATIONS_EMAIL = True

    def panne(*args, **kwargs):
        raise OSError("serveur SMTP injoignable")

    monkeypatch.setattr(services, "send_mail", panne)

    with django_capture_on_commit_callbacks(execute=True):
        creees = _notifier([UserFactory(email="a@ex.ci")])

    assert Notification.objects.count() == 1  # la notification reste dans l'application
    creees[0].refresh_from_db()
    assert not creees[0].email_envoye
    assert "par e-mail impossible" in caplog.text
