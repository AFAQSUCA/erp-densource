"""Suivi des sauvegardes par l'ADMIN (cahier-des-charges.md:48 « ADMIN : … sauvegardes », :282 « sauvegardes
chiffrées et testées » ; décision du 12/10/2026 : avenant-sauvegardes.md).

Le service `sauvegarde` de docker-compose.yml (ops/planificateur-sauvegarde.sh) fait les sauvegardes et tient le
journal ; l'application se contente de **lire** ce journal et d'y **déposer une demande** (bouton « Sauvegarder
maintenant »). Elle n'a aucun accès à Docker, et les fichiers chiffrés ne lui sont pas lisibles.

Fichiers du dossier ``settings.SAUVEGARDES_DIR`` (volume partagé avec le service) :
- ``journal.jsonl`` : une ligne JSON par essai (``ops/sauvegarde.sh``) ;
- ``en_cours.json`` : présent pendant une sauvegarde ;
- ``demandes/*.demande`` : demandes en attente, prises en charge dans les 30 secondes.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.audit import services as audit_services
from apps.audit.models import ActionChoices
from apps.core.exceptions import ErreurMetier

from . import permissions

STATUT_OK, STATUT_ALERTE, STATUT_ECHEC = "OK", "ALERTE", "ECHEC"
STATUTS_REUSSIS = (STATUT_OK, STATUT_ALERTE)  # ALERTE : sauvegarde faite, copie hors serveur à vérifier
DELAI_ALERTE = timedelta(hours=26)  # une sauvegarde par nuit, avec deux heures de marge
LIGNES_AFFICHEES = 30


class SauvegardeError(ErreurMetier):
    """Erreur métier sur les sauvegardes (message affichable tel quel)."""


class ActionNonAutorisee(SauvegardeError):
    """L'acteur n'a pas le droit de demander une sauvegarde."""


def _dossier() -> Path:
    return Path(settings.SAUVEGARDES_DIR)


def _date(texte) -> datetime | None:
    try:
        valeur = parse_datetime(str(texte or ""))
    except ValueError:
        return None
    return valeur if valeur is not None and timezone.is_aware(valeur) else None


def libelle_declencheur(code: str) -> str:
    if code == "planifiee":
        return "Planifiée (nuit)"
    if code == "manuelle":
        return "Lancée sur le serveur"
    if code.startswith("demande:"):
        return f"Demandée par {code.removeprefix('demande:')}"
    return code or "—"


def _fichier(description) -> dict | None:
    if not isinstance(description, dict):
        return None
    try:
        taille = int(description.get("taille"))
    except (TypeError, ValueError):
        taille = None
    return {"nom": str(description.get("nom", "")), "taille": taille, "sha256": str(description.get("sha256", ""))}


def _essais() -> Iterator[dict]:
    """Essais du journal, du plus récent au plus ancien. Une ligne illisible est ignorée : le journal est écrit
    par un script, une ligne tronquée (disque plein, arrêt brutal) ne doit pas masquer les autres."""
    try:
        lignes = (_dossier() / "journal.jsonl").read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, NotADirectoryError):
        return
    for brute in reversed(lignes):
        try:
            essai = json.loads(brute)
        except ValueError:
            continue
        fin = _date(essai.get("fin")) if isinstance(essai, dict) else None
        if fin is None:
            continue
        statut = essai.get("statut")
        yield {
            "debut": _date(essai.get("debut")),
            "fin": fin,
            "statut": statut if statut in (STATUT_OK, STATUT_ALERTE) else STATUT_ECHEC,
            "declencheur": libelle_declencheur(str(essai.get("declencheur", ""))),
            "message": str(essai.get("message", "")),
            "base": _fichier(essai.get("base")),
            "medias": _fichier(essai.get("medias")),
        }


def journal(limite: int = LIGNES_AFFICHEES) -> list[dict]:
    """Les ``limite`` derniers essais, réussis ou non, du plus récent au plus ancien."""
    essais = []
    for essai in _essais():
        essais.append(essai)
        if len(essais) >= limite:
            break
    return essais


def derniere_reussie() -> dict | None:
    return next((e for e in _essais() if e["statut"] in STATUTS_REUSSIS), None)


def en_cours() -> dict | None:
    """La sauvegarde en cours d'exécution, s'il y en a une : ``{"debut", "declencheur"}``."""
    try:
        donnees = json.loads((_dossier() / "en_cours.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, NotADirectoryError, ValueError):
        return None
    if not isinstance(donnees, dict):
        return None
    return {"debut": _date(donnees.get("debut")), "declencheur": libelle_declencheur(str(donnees.get("declencheur", "")))}


def demande_en_attente() -> dict | None:
    """La plus ancienne demande pas encore prise en charge : ``{"depuis", "par"}``."""
    for demande in sorted((_dossier() / "demandes").glob("*.demande")):  # dossier absent : aucune demande
        try:
            par = demande.read_text(encoding="utf-8").strip()
            depuis = datetime.fromtimestamp(demande.stat().st_mtime, tz=timezone.get_current_timezone())
        except FileNotFoundError:  # prise en charge entre-temps
            continue
        return {"depuis": depuis, "par": par}
    return None


def peut_demander(utilisateur) -> bool:
    return getattr(utilisateur, "role_effectif", None) in permissions.LANCEMENT


def demander_sauvegarde(acteur, *, request=None) -> None:
    """Dépose une demande de sauvegarde immédiate (ADMIN). Refusée si une sauvegarde est déjà demandée ou en cours
    (évite d'en empiler sur un double clic). Écriture atomique : le service ne voit jamais un fichier à moitié écrit.
    Journalisée (module ``SAUVEGARDES``)."""
    if not peut_demander(acteur):
        raise ActionNonAutorisee("Seul l'administrateur peut lancer une sauvegarde.")
    if en_cours() is not None:
        raise SauvegardeError("Une sauvegarde est déjà en cours : son résultat s'affichera ici à la fin.")
    if demande_en_attente() is not None:
        raise SauvegardeError("Une sauvegarde est déjà demandée : elle démarre dans la minute.")
    dossier = _dossier() / "demandes"
    dossier.mkdir(parents=True, exist_ok=True)
    maintenant = timezone.now()
    descripteur, temporaire = tempfile.mkstemp(dir=dossier, suffix=".tmp")
    with os.fdopen(descripteur, "w", encoding="utf-8") as fichier:
        fichier.write(acteur.username)
    os.replace(temporaire, dossier / f"{maintenant:%Y%m%dT%H%M%S%f}.demande")
    audit_services.log_action(
        action=ActionChoices.CREATE,
        module="SAUVEGARDES",
        entite="DemandeSauvegarde",
        utilisateur=acteur,
        nouvelle_valeur={"demandee_le": maintenant.isoformat()},
        request=request,
    )


def alerte(*, maintenant: datetime | None = None) -> dict | None:
    """Problème de sauvegarde à signaler à l'ADMIN (centre d'alertes) : ``{"niveau", "detail"}``, ou ``None``.

    Seulement si la surveillance est active (``settings.SAUVEGARDES_SURVEILLEES`` : vrai en production, faux en
    développement où aucun service de sauvegarde ne tourne)."""
    if not settings.SAUVEGARDES_SURVEILLEES:
        return None
    maintenant = maintenant or timezone.now()
    reussie = derniere_reussie()
    if reussie is None:
        return {"niveau": "URGENT", "detail": "aucune sauvegarde réussie enregistrée"}
    age = maintenant - reussie["fin"]
    if age > DELAI_ALERTE:
        return {"niveau": "URGENT", "detail": f"dernière sauvegarde réussie il y a {age.days * 24 + age.seconds // 3600} h"}
    dernier = journal(limite=1)[0]
    if dernier["statut"] == STATUT_ECHEC:
        return {"niveau": "ATTENTION", "detail": "le dernier essai a échoué"}
    if reussie["statut"] == STATUT_ALERTE:
        return {"niveau": "ATTENTION", "detail": "la copie hors serveur a échoué"}
    return None
