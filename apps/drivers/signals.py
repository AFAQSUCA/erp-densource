from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.hr.models import Conge, Personnel, StatutConge

from . import services
from .models import Chauffeur, Copilote


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


@receiver(post_save, sender=Personnel)
def creer_fiche_copilote(sender, instance, raw=False, **kwargs):
    """Poste « Copilote » → fiche copilote créée, même principe que le chauffeur."""
    if raw or instance.is_deleted:
        return
    if instance.est_copilote:
        services.assurer_fiche_copilote(instance)


@receiver(post_save, sender=Conge)
def aligner_statut_chauffeur_sur_conge(sender, instance, raw=False, **kwargs):
    """Congé d'un chauffeur en cours → « En congé » (cahier-des-charges.md:216).

    Appliqué au démarrage effectif du congé (EN_COURS) et non à l'approbation,
    pour ne pas immobiliser le chauffeur des semaines avant son départ.
    """
    if raw or instance.statut not in (StatutConge.EN_COURS, StatutConge.TERMINE):
        return
    fiche = Chauffeur.objects.filter(personnel_id=instance.employe_id).first()
    if fiche is not None:
        if instance.statut == StatutConge.EN_COURS:
            services.mettre_en_conge(fiche)
        else:
            services.rappeler_de_conge(fiche)
    copilote = Copilote.objects.filter(personnel_id=instance.employe_id).first()
    if copilote is not None:
        if instance.statut == StatutConge.EN_COURS:
            services.mettre_copilote_en_conge(copilote)
        else:
            services.rappeler_copilote_de_conge(copilote)
