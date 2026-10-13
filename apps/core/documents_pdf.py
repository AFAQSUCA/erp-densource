"""PDF préparés en tâche de fond par Celery (cahier-des-charges.md:294 « Tâches async Celery (… PDF) » ; décision
du 13/10/2026, audit TECH-70).

La requête rassemble les données du rapport (droits, filtres : rien ne change pour eux), les range dans un
:class:`~apps.core.models.DocumentPdf` et rend la main tout de suite : la mise en page ReportLab, la partie lente,
se fait dans le processus ``celery worker``. L'utilisateur arrive sur une page « Préparation de votre PDF » qui se
recharge seule et lance le téléchargement dès que le fichier est prêt. Seul le demandeur peut le télécharger ; les
fichiers sont effacés après ``PDF_CONSERVATION_HEURES`` (tâches quotidiennes).

Sans worker (développement, tests : ``PDF_EN_TACHE_DE_FOND`` désactivé), le PDF est rendu dans la requête, comme
avant. Restent toujours générés dans la requête, sans jamais être stockés : les codes d'une mission (un secret) et
l'autorisation de congé (document personnel d'une page).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import TemplateView, View

from . import pdf
from .models import DocumentPdf, StatutDocumentPdf

logger = logging.getLogger(__name__)

# Au-delà, un document toujours « en préparation » signale un worker arrêté : la page cesse de se recharger.
DELAI_ATTENTE_MAX = timedelta(minutes=5)


def _adresse_de_retour(request) -> str:
    """La page d'où vient la demande, sans ``format=pdf`` (sinon « Retour » relancerait la génération)."""
    parametres = request.GET.copy()
    parametres.pop("format", None)
    return f"{request.path}?{parametres.urlencode()}" if parametres else request.path


def telecharger(
    request, *, titre: str, sous_titre: str = "", blocs: list, entreprise: dict, genere_par: str,
    genere_le: datetime, paysage: bool | None = None,
) -> HttpResponse:
    """Réponse à un « Télécharger en PDF » : le fichier lui-même (sans worker), ou la page d'attente du document
    confié à Celery."""
    if not settings.PDF_EN_TACHE_DE_FOND:
        contenu = pdf.generer_pdf(
            titre=titre, sous_titre=sous_titre, blocs=blocs, entreprise=entreprise, genere_par=genere_par,
            genere_le=genere_le, paysage=paysage,
        )
        return pdf.reponse_pdf(contenu, titre)

    from .tasks import generer_document_pdf

    document = DocumentPdf.objects.create(
        demande_par=request.user,
        titre=titre[:200],
        nom_fichier=pdf.nom_fichier_pdf(titre),
        url_retour=_adresse_de_retour(request)[:500],
        parametres={
            "titre": titre, "sous_titre": sous_titre, "blocs": pdf.blocs_vers_donnees(blocs),
            "entreprise": entreprise, "genere_par": genere_par, "genere_le": genere_le.isoformat(),
            "paysage": paysage,
        },
    )
    # Après la validation de la transaction : le worker doit trouver le document en base.
    transaction.on_commit(lambda: generer_document_pdf.delay(document.pk))
    return redirect("document_pdf", cle=document.cle)


def preparer(document_id: int) -> None:
    """Met en page le PDF d'un document en attente et l'enregistre (appelé par la tâche Celery). Rejouer la tâche
    ne refait rien : seul un document encore « en préparation » est traité."""
    document = DocumentPdf.objects.filter(pk=document_id, statut=StatutDocumentPdf.EN_ATTENTE).first()
    if document is None:
        return
    p = document.parametres
    try:
        contenu = pdf.generer_pdf(
            titre=p["titre"], sous_titre=p["sous_titre"], blocs=pdf.blocs_depuis_donnees(p["blocs"]),
            entreprise=p["entreprise"], genere_par=p["genere_par"], genere_le=datetime.fromisoformat(p["genere_le"]),
            paysage=p.get("paysage"),
        )
    except Exception as erreur:  # le demandeur doit l'apprendre, pas attendre indéfiniment
        logger.exception("Échec de la génération du PDF %s", document.pk)
        document.statut = StatutDocumentPdf.ECHEC
        document.erreur = str(erreur)[:500]
    else:
        document.fichier.save(f"{document.cle}.pdf", ContentFile(contenu), save=False)
        document.statut = StatutDocumentPdf.PRET
    document.parametres = {}  # les données du rapport ne servent plus
    document.termine_le = timezone.now()
    document.save()


def purger(*, maintenant: datetime | None = None) -> int:
    """Efface les documents (et leurs fichiers) plus vieux que ``PDF_CONSERVATION_HEURES``. Tâches quotidiennes."""
    limite = (maintenant or timezone.now()) - timedelta(hours=settings.PDF_CONSERVATION_HEURES)
    purges = 0
    for document in DocumentPdf.objects.filter(created_at__lt=limite):
        if document.fichier:
            document.fichier.delete(save=False)
        document.delete()
        purges += 1
    return purges


def _document_du_demandeur(request, cle) -> DocumentPdf:
    """Le document, s'il a été demandé par l'utilisateur connecté : 404 pour tout autre (même l'ADMIN), comme un
    lien qui n'existe pas."""
    return get_object_or_404(DocumentPdf, cle=cle, demande_par=request.user)


class DocumentPdfView(LoginRequiredMixin, TemplateView):
    """Page d'attente : se recharge toutes les 2 secondes, puis lance le téléchargement."""

    template_name = "core/document_pdf.html"

    def get_context_data(self, **kwargs):
        document = _document_du_demandeur(self.request, kwargs["cle"])
        en_attente = document.statut == StatutDocumentPdf.EN_ATTENTE
        return super().get_context_data(
            document=document,
            en_attente=en_attente,
            bloque=en_attente and document.created_at < timezone.now() - DELAI_ATTENTE_MAX,
            heures_conservation=settings.PDF_CONSERVATION_HEURES,
            **kwargs,
        )


class DocumentPdfTelechargerView(LoginRequiredMixin, View):
    http_method_names = ["get"]

    def get(self, request, cle):
        document = _document_du_demandeur(request, cle)
        if document.statut != StatutDocumentPdf.PRET or not document.fichier:
            raise Http404
        if getattr(settings, "MEDIA_ACCEL_REDIRECT", False):
            # Nginx envoie le fichier depuis son emplacement interne (comme les fichiers téléversés, core.medias).
            reponse = HttpResponse(content_type="application/pdf")
            reponse["X-Accel-Redirect"] = "/medias-internes/" + document.fichier.name
        else:
            try:
                reponse = FileResponse(document.fichier.open("rb"), content_type="application/pdf")
            except FileNotFoundError:
                raise Http404
        reponse["Content-Disposition"] = f'attachment; filename="{document.nom_fichier}"'
        reponse["X-Content-Type-Options"] = "nosniff"
        reponse["Cache-Control"] = "private, no-store"
        return reponse
