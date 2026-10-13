"""Tâches Celery du socle commun."""

from __future__ import annotations

from celery import shared_task

from . import documents_pdf


@shared_task
def generer_document_pdf(document_id: int) -> None:
    """Met en page un PDF demandé depuis un écran (audit TECH-70) — hors du chemin de la requête."""
    documents_pdf.preparer(document_id)
