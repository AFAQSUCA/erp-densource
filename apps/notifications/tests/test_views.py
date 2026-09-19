"""Page « Notifications » et cloche de l'en-tête."""

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.notifications import services
from apps.notifications.models import CategorieNotification, Notification

pytestmark = pytest.mark.django_db


def _notifier(utilisateur, titre="Stock bas", **surcharges):
    donnees = dict(categorie=CategorieNotification.STOCK, titre=titre, message="Détail")
    donnees.update(surcharges)
    return services.notifier([utilisateur], **donnees)[0]


@pytest.mark.parametrize("role", list(Role.values))
def test_tous_les_roles_ont_leur_page_de_notifications(client, role):
    client.force_login(UserFactory(role=role))

    assert client.get(reverse("notifications:liste")).status_code == 200


def test_la_page_exige_la_connexion(client):
    assert client.get(reverse("notifications:liste")).status_code == 302


def test_chacun_ne_voit_que_ses_notifications(client):
    moi, autre = UserFactory(), UserFactory()
    _notifier(moi, "Pour moi")
    _notifier(autre, "Pour un autre")
    client.force_login(moi)

    texte = client.get(reverse("notifications:liste")).content.decode()

    assert "Pour moi" in texte and "Pour un autre" not in texte


def test_le_filtre_non_lues(client):
    moi = UserFactory()
    lue = _notifier(moi, "Déjà lue")
    _notifier(moi, "Nouvelle")
    services.marquer_lue(lue)
    client.force_login(moi)

    toutes = client.get(reverse("notifications:liste")).content.decode()
    non_lues = client.get(reverse("notifications:liste"), {"non_lues": "1"}).content.decode()

    assert "Déjà lue" in toutes and "Nouvelle" in toutes
    assert "Déjà lue" not in non_lues and "Nouvelle" in non_lues


def test_la_page_vide_est_expliquee(client):
    client.force_login(UserFactory())

    assert "Aucune notification" in client.get(reverse("notifications:liste")).content.decode()


def test_ouvrir_une_notification_la_marque_lue_et_redirige_vers_son_lien(client):
    moi = UserFactory()
    notification = _notifier(moi, url="/stock/articles/3/")
    client.force_login(moi)

    reponse = client.post(reverse("notifications:lire", args=[notification.pk]))

    assert reponse.status_code == 302 and reponse["Location"] == "/stock/articles/3/"
    notification.refresh_from_db()
    assert notification.est_lue


def test_sans_lien_on_revient_a_la_liste(client):
    moi = UserFactory()
    notification = _notifier(moi)
    client.force_login(moi)

    reponse = client.post(reverse("notifications:lire", args=[notification.pk]))

    assert reponse["Location"] == reverse("notifications:liste")


@pytest.mark.parametrize("lien", ["https://pirate.example/", "//pirate.example/", "javascript:alert(1)"])
def test_un_lien_externe_n_est_jamais_suivi(client, lien):
    moi = UserFactory()
    notification = _notifier(moi, url=lien)
    client.force_login(moi)

    reponse = client.post(reverse("notifications:lire", args=[notification.pk]))

    assert reponse["Location"] == reverse("notifications:liste")


def test_on_ne_peut_pas_lire_la_notification_d_un_autre(client):
    autre = UserFactory()
    notification = _notifier(autre)
    client.force_login(UserFactory())

    assert client.post(reverse("notifications:lire", args=[notification.pk])).status_code == 404
    notification.refresh_from_db()
    assert not notification.est_lue


def test_tout_marquer_comme_lu_ne_touche_que_mes_notifications(client):
    moi, autre = UserFactory(), UserFactory()
    _notifier(moi)
    _notifier(moi)
    _notifier(autre)
    client.force_login(moi)

    client.post(reverse("notifications:tout_lire"))

    assert services.nombre_non_lues(moi) == 0
    assert services.nombre_non_lues(autre) == 1


def test_les_actions_sont_en_post_avec_csrf():
    moi = UserFactory()
    notification = _notifier(moi)
    client = Client(enforce_csrf_checks=True)
    client.force_login(moi)

    assert client.get(reverse("notifications:tout_lire")).status_code == 405
    assert client.get(reverse("notifications:lire", args=[notification.pk])).status_code == 405
    assert client.post(reverse("notifications:tout_lire")).status_code == 403
    assert client.post(reverse("notifications:lire", args=[notification.pk])).status_code == 403
    assert services.nombre_non_lues(moi) == 1


def test_les_textes_sont_echappes(client):
    moi = UserFactory()
    _notifier(moi, "<script>alert(1)</script>", message="<img src=x onerror=alert(2)>")
    client.force_login(moi)

    texte = client.get(reverse("notifications:liste")).content.decode()

    assert "<script>alert(1)</script>" not in texte and "<img src=x" not in texte


def test_les_pages_du_site_affichent_le_nombre_de_notifications_non_lues(client):
    moi = UserFactory(role=Role.DIRECTION)
    _notifier(moi)
    _notifier(moi)
    client.force_login(moi)

    texte = client.get(reverse("home")).content.decode()

    assert "Notifications : 2 non lues" in texte


def test_la_cloche_disparait_de_la_page_de_connexion_sans_erreur(client):
    assert client.get(reverse("accounts:login")).status_code == 200


def test_la_liste_est_paginee_et_tolere_une_page_invalide(client):
    moi = UserFactory()
    for i in range(25):
        _notifier(moi, f"Notification {i}")
    client.force_login(moi)

    page_1 = client.get(reverse("notifications:liste"))
    inconnue = client.get(reverse("notifications:liste"), {"page": 99})

    assert len(page_1.context["notifications"]) == 20
    assert inconnue.status_code == 200 and inconnue.context["page_obj"].number == 2


def test_la_liste_reste_a_requetes_constantes(client, django_assert_max_num_queries):
    moi = UserFactory()
    for i in range(15):
        _notifier(moi, f"Notification {i}")
    client.force_login(moi)

    with django_assert_max_num_queries(8):
        assert client.get(reverse("notifications:liste")).status_code == 200
    assert Notification.objects.count() == 15
