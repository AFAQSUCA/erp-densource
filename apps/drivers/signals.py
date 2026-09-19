from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.hr.models import Personnel

from . import services


@receiver(post_save, sender=Personnel)
def creer_fiche_chauffeur(sender, instance, raw=False, **kwargs):
    """Poste « Chauffeur » → fiche chauffeur créée (cahier-des-charges.md:108).

    C'est ``drivers`` qui écoute ``hr`` (et non l'inverse) pour respecter le
    sens des dépendances de architecture.md:161-163.
    """
    if raw or instance.is_deleted:
        return
    if instance.est_chauffeur:
        services.assurer_fiche_chauffeur(instance)
