# Chapitre 29 — Le suivi des sauvegardes : l'app sauvegardes

> 10 fichier(s) dans ce chapitre, 420 lignes de code.

## Ce que vous allez construire

**`sauvegardes`** : l'écran où l'**ADMIN suit les sauvegardes** et en demande une immédiatement
(`avenant-sauvegardes.md`). L'application ne sauvegarde rien elle-même : un **service dédié** de la mise en
production (Docker, chapitre 34) sauvegarde la base et les fichiers déposés chaque nuit, chiffrés. L'application,
elle, **lit son journal** et **dépose des demandes**.

| Élément | Règle |
|---|---|
| **Journal** | un fichier `journal.jsonl` écrit par le service : une ligne JSON par essai (début, fin, statut, taille et empreinte de chaque fichier) ; une ligne illisible est ignorée sans masquer les autres |
| **Statuts** | `OK` ; `ALERTE` (sauvegarde faite, copie hors serveur échouée) ; `ECHEC` |
| **« Sauvegarder maintenant »** | dépose un fichier de demande que le service exécute dans la minute ; refusé si une sauvegarde est déjà en cours ou demandée (double clic) |
| **Alerte** | au centre d'alertes de l'ADMIN : aucune sauvegarde réussie, ou la dernière a plus de 26 h (urgent) ; dernier essai en échec (attention) |
| **Droits** | ADMIN seulement ; chaque demande va au journal d'audit |

Pourquoi maintenant ? Le **tableau de bord** du chapitre suivant affiche cette alerte : il lit `sauvegardes`, qui doit
donc exister avant lui.

## Prérequis

- Chapitres 1 à 28 terminés (l'écran utilise le socle de l'interface du chapitre 18).

## Ce que ce chapitre apporte de nouveau

- **Une app sans modèle** : tout son état vit dans des **fichiers** partagés avec le service de sauvegarde
  (`settings.SAUVEGARDES_DIR`). Pas de migration.
- **Séparer les privilèges** : l'application n'a accès ni à Docker ni aux fichiers chiffrés. Elle se contente de
  **déposer une demande** ; seul le service, qui tourne à part, a le droit de sauvegarder.
- **Écriture atomique** : la demande est écrite dans un fichier temporaire puis **renommée** (`os.replace`) : le
  service ne lit jamais un fichier à moitié écrit.
- **Une jauge pour Prometheus** : au démarrage, `ready()` inscrit l'âge de la dernière sauvegarde réussie parmi les
  mesures du socle (`apps/core/mesures.py`, chapitre 2), sans que `core` ait à connaître `sauvegardes`.

## Étape 1 — Créer l'application

```bash
mkdir -p apps/sauvegardes/tests templates/sauvegardes
```

#### Fichiers vides à créer

Ces fichiers n'ont aucun contenu ; ils servent à faire de leur dossier un *paquet Python* (sans eux, `import apps.xxx` échouerait). Créez d'abord les dossiers, puis les fichiers :

```bash
mkdir -p apps\sauvegardes apps\sauvegardes\tests
touch apps/sauvegardes/__init__.py
touch apps/sauvegardes/tests/__init__.py
```

> Sous PowerShell, `mkdir -p` s'écrit `New-Item -ItemType Directory -Force <dossier>` et `touch fichier` s'écrit `New-Item -ItemType File -Force fichier`. Vous pouvez aussi créer ces fichiers avec votre éditeur.

## Étape 2 — Lire le journal, déposer une demande

#### `apps/sauvegardes/README.md`

*22 lignes* — sauvegardes

```markdown
# sauvegardes

Rôle : suivi des sauvegardes par l'ADMIN — cahier-des-charges.md:48 (« ADMIN : … sauvegardes ») et :282 (« sauvegardes
chiffrées et testées ») ; décision du 12/10/2026 (`avenant-sauvegardes.md`). Écran `/sauvegardes/`, menu « Sauvegardes »,
ADMIN seulement. Dépend de `core`, `accounts`, `audit` ; lu par `dashboard` (architecture.md).

- **Qui sauvegarde** : le service `sauvegarde` de `docker-compose.yml` (`ops/planificateur-sauvegarde.sh`, image
  `ops/Dockerfile.sauvegarde`) appelle `ops/sauvegarde.sh` chaque nuit (`SAUVEGARDE_HEURE`) et à la demande. Base
  (`pg_dump`) et fichiers déposés (`tar` du volume `media_data`), chiffrés GPG, rotation, copie hors serveur facultative.
- **Ce que fait l'application** : elle **lit** le journal (`journal.jsonl`, une ligne JSON par essai) et
  `en_cours.json`, et **dépose une demande** (`demandes/<horodatage>.demande`, écriture atomique) quand l'ADMIN clique
  sur « Sauvegarder maintenant ». Elle n'a aucun accès à Docker ni aux fichiers chiffrés (droits 600, propriétaire root).
  Dossier partagé : `settings.SAUVEGARDES_DIR` (volume `sauvegardes_data`, monté sur `/app/sauvegardes`).
- **Statuts** : `OK` ; `ALERTE` (sauvegarde faite, copie hors serveur échouée) ; `ECHEC` (rien n'est gardé, aucun
  fichier tronqué). Une ligne illisible du journal est ignorée sans masquer les autres.
- **Double clic** : une demande est refusée tant qu'une autre attend ou qu'une sauvegarde est en cours.
- **Alerte** (`services.alerte`, centre d'alertes de l'ADMIN) : aucune sauvegarde réussie, dernière réussie de plus de
  26 h (urgent) ; dernier essai en échec, copie hors serveur échouée (attention). Seulement si
  `SAUVEGARDES_SURVEILLEES` (vrai par défaut en production, faux en développement où le service ne tourne pas).
- **Audit** : chaque demande est journalisée (module `SAUVEGARDES`, entité `DemandeSauvegarde`).
- **Restauration** : `ops/restauration.sh` (base : `.dump.gpg` ; fichiers : `.tar.gz.gpg` avec `RESTAURATION_MEDIAS`),
  essai mensuel décrit dans GUIDE-DEPLOIEMENT.md § 9.
```

#### `apps/sauvegardes/permissions.py`

*6 lignes* — Qui suit et lance les sauvegardes : l'ADMIN (cahier-des-charges.md:48). Un superutilisateur agit en ADMIN.

```python
"""Qui suit et lance les sauvegardes : l'ADMIN (cahier-des-charges.md:48). Un superutilisateur agit en ADMIN."""

from apps.accounts.models import Role

CONSULTATION = frozenset({Role.ADMIN})
LANCEMENT = frozenset({Role.ADMIN})
```

#### `apps/sauvegardes/services.py`

*204 lignes* — Suivi des sauvegardes par l'ADMIN (cahier-des-charges.md:48 « ADMIN : … sauvegardes », :282 « sauvegardes

```python
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


def age_derniere_sauvegarde(*, maintenant: datetime | None = None) -> float | None:
    """Secondes écoulées depuis la dernière sauvegarde réussie, pour Prometheus (audit TECH-24) ; rien là où le
    service de sauvegarde ne tourne pas (développement) ou s'il n'a encore rien réussi."""
    if not settings.SAUVEGARDES_SURVEILLEES:
        return None
    derniere = derniere_reussie()
    if derniere is None:
        return None
    return max(((maintenant or timezone.now()) - derniere["fin"]).total_seconds(), 0)


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
```

- **`journal()`** et **`derniere_reussie()`** relisent `journal.jsonl` du plus récent au plus ancien.
- **`demander_sauvegarde`** contrôle le rôle, refuse un doublon, écrit la demande de façon atomique puis la
  journalise.
- **`alerte()`** ne dit rien tant que `SAUVEGARDES_SURVEILLEES` est faux : en développement, aucun service de
  sauvegarde ne tourne, l'alerte serait permanente.

#### `apps/sauvegardes/apps.py`

*24 lignes*

```python
from django.apps import AppConfig


class SauvegardesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sauvegardes"
    label = "sauvegardes"
    verbose_name = "Sauvegardes"

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer

        from . import permissions

        enregistrer(EntreeMenu("Sauvegardes", "sauvegardes:liste", "fa-database", permissions.CONSULTATION, ordre=91))

        from apps.core.mesures import enregistrer_jauge

        from .services import age_derniere_sauvegarde

        enregistrer_jauge(
            "erp_sauvegarde_age_secondes", "Âge de la dernière sauvegarde réussie (service `sauvegarde`).",
            age_derniere_sauvegarde,
        )
```

## Étape 3 — L'écran

#### `templates/sauvegardes/_fichier.html`

*7 lignes* — Cellule d'un fichier de sauvegarde : {% include "sauvegardes/_fichier.html" with fichier=essai.base %}

```django
{# Cellule d'un fichier de sauvegarde : {% include "sauvegardes/_fichier.html" with fichier=essai.base %} #}
<td class="px-4 py-2 text-slate-700">
  {% if fichier %}
    {{ fichier.taille|filesizeformat }}
    <span class="block break-all font-mono text-xs text-slate-600" title="Empreinte SHA-256 : à comparer avant une restauration">{{ fichier.sha256|truncatechars:17 }}</span>
  {% else %}—{% endif %}
</td>
```

#### `templates/sauvegardes/sauvegardes.html`

*100 lignes*

```django
{% extends "base.html" %}
{% block titre %}Sauvegardes{% endblock %}
{% block entete %}Administration{% endblock %}
{% block head_extra %}{% if rafraichir %}<meta http-equiv="refresh" content="20">{% endif %}{% endblock %}

{% block contenu %}
<div class="mx-auto max-w-5xl">
  <div class="flex flex-wrap items-start justify-between gap-3">
    <div>
      <h1 class="text-2xl font-bold text-slate-900">Sauvegardes</h1>
      <p class="mt-1 text-sm text-slate-600">
        Chaque nuit, la base et les fichiers déposés (justificatifs, pièces jointes) sont sauvegardés et chiffrés par le
        service de sauvegarde du serveur. Les fichiers chiffrés restent sur le serveur (et sa copie hors serveur si elle
        est configurée) : ils ne se téléchargent pas depuis l'ERP.
      </p>
    </div>
    {% if peut_demander %}
      <form method="post">
        {% csrf_token %}
        <button type="submit" {% if en_cours or demande %}disabled aria-disabled="true"{% endif %}
                class="inline-flex items-center gap-2 rounded-lg bg-marque-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:bg-slate-400">
          <i class="fa-solid fa-floppy-disk" aria-hidden="true"></i> Sauvegarder maintenant
        </button>
      </form>
    {% endif %}
  </div>

  {% if en_cours %}
    <p role="status" class="mt-5 rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm text-indigo-900">
      <i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i>
      Sauvegarde en cours depuis {{ en_cours.debut|date:"H:i" }} ({{ en_cours.declencheur }}). Cette page se met à jour toute seule.
    </p>
  {% elif demande %}
    <p role="status" class="mt-5 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
      Sauvegarde demandée à {{ demande.depuis|date:"H:i" }}{% if demande.par %} par {{ demande.par }}{% endif %} : elle démarre dans la minute.
      {% if demande.depuis %}Si rien ne se passe après quelques minutes, le service de sauvegarde ne tourne pas (<code>docker compose ps sauvegarde</code>).{% endif %}
    </p>
  {% endif %}

  {% if alerte %}
    <p role="alert" class="mt-5 rounded-lg border {% if alerte.niveau == 'URGENT' %}border-red-300 bg-red-50 text-red-900{% else %}border-amber-300 bg-amber-50 text-amber-900{% endif %} px-4 py-3 text-sm">
      <i class="fa-solid fa-triangle-exclamation" aria-hidden="true"></i> Attention : {{ alerte.detail }}.
    </p>
  {% endif %}

  <section class="mt-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="titre-derniere">
    <h2 id="titre-derniere" class="text-base font-semibold text-slate-900">Dernière sauvegarde réussie</h2>
    {% if derniere %}
      <p class="mt-2 text-sm text-slate-700">
        Le {{ derniere.fin|date:"d/m/Y à H:i" }} ({{ derniere.declencheur }}){% if derniere.statut == "ALERTE" %} — <strong class="text-amber-800">{{ derniere.message }}</strong>{% endif %}.
      </p>
    {% else %}
      <p class="mt-2 text-sm text-slate-700">Aucune sauvegarde réussie n'est enregistrée{% if not surveillees %} (le service de sauvegarde ne tourne qu'en production){% endif %}.</p>
    {% endif %}
  </section>

  <section class="mt-6" aria-labelledby="titre-journal">
    <h2 id="titre-journal" class="text-base font-semibold text-slate-900">Derniers essais</h2>
    {% if essais %}
      <div class="mt-3 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table class="min-w-full divide-y divide-slate-200 text-sm">
          <caption class="sr-only">Journal des sauvegardes, du plus récent au plus ancien</caption>
          <thead class="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
            <tr>
              <th scope="col" class="px-4 py-2">Fin</th>
              <th scope="col" class="px-4 py-2">Résultat</th>
              <th scope="col" class="px-4 py-2">Origine</th>
              <th scope="col" class="px-4 py-2">Base</th>
              <th scope="col" class="px-4 py-2">Fichiers</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            {% for essai in essais %}
              <tr>
                <td class="whitespace-nowrap px-4 py-2 text-slate-800">{{ essai.fin|date:"d/m/Y H:i" }}</td>
                <td class="px-4 py-2">
                  {% if essai.statut == "OK" %}<span class="font-medium text-emerald-800">Réussie</span>
                  {% elif essai.statut == "ALERTE" %}<span class="font-medium text-amber-800">Réussie, copie hors serveur échouée</span>
                  {% else %}<span class="font-semibold text-red-800">Échec</span>{% endif %}
                  {% if essai.statut == "ECHEC" and essai.message %}<span class="block text-xs text-slate-600">{{ essai.message }}</span>{% endif %}
                </td>
                <td class="px-4 py-2 text-slate-700">{{ essai.declencheur }}</td>
                {% include "sauvegardes/_fichier.html" with fichier=essai.base %}
                {% include "sauvegardes/_fichier.html" with fichier=essai.medias %}
              </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    {% else %}
      <p class="mt-2 text-sm text-slate-600">Aucun essai enregistré pour l'instant.</p>
    {% endif %}
  </section>

  <p class="mt-6 text-xs text-slate-600">
    Une sauvegarde n'est fiable que si sa restauration a été essayée : une fois par mois, restaurer la dernière dans une
    base à part (GUIDE-DEPLOIEMENT.md, « Tester une restauration »).
  </p>
</div>
{% endblock %}
```

#### `apps/sauvegardes/views.py`

*38 lignes* — Écran « Sauvegardes » (ADMIN). Les règles sont dans ``sauvegardes.services`` ; la vue n'ajoute que l'affichage.

```python
"""Écran « Sauvegardes » (ADMIN). Les règles sont dans ``sauvegardes.services`` ; la vue n'ajoute que l'affichage."""

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.views.generic import TemplateView

from apps.accounts.mixins import RoleRequiredMixin

from . import permissions, services


class SauvegardesView(RoleRequiredMixin, TemplateView):
    roles = permissions.CONSULTATION
    template_name = "sauvegardes/sauvegardes.html"

    def get_context_data(self, **kwargs):
        en_cours, demande = services.en_cours(), services.demande_en_attente()
        return super().get_context_data(
            essais=services.journal(),
            derniere=services.derniere_reussie(),
            alerte=services.alerte(),
            en_cours=en_cours,
            demande=demande,
            rafraichir=en_cours is not None or demande is not None,
            surveillees=settings.SAUVEGARDES_SURVEILLEES,
            peut_demander=services.peut_demander(self.request.user),
            **kwargs,
        )

    def post(self, request):
        try:
            services.demander_sauvegarde(request.user, request=request)
        except services.SauvegardeError as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, "Sauvegarde demandée : elle démarre dans la minute. Cette page se met à jour.")
        return redirect("sauvegardes:liste")
```

#### `apps/sauvegardes/urls.py`

*9 lignes*

```python
from django.urls import path

from . import views

app_name = "sauvegardes"

urlpatterns = [
    path("", views.SauvegardesView.as_view(), name="liste"),
]
```

La page se **recharge seule** tant qu'une sauvegarde est demandée ou en cours (`rafraichir`), pour afficher le
résultat dès qu'il arrive.

## Étape 4 — Déclarer l'application

#### `config/settings/base.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/settings/base.py (avant)
+++ config/settings/base.py (après)
@@ -67,4 +67,5 @@
     "apps.accounting",
     "apps.parametres",
+    "apps.sauvegardes",
     "apps.notifications",
 ]
```

#### `config/urls.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/urls.py (avant)
+++ config/urls.py (après)
@@ -35,4 +35,5 @@
     path("audit/", include("apps.audit.urls")),
     path("parametres/", include("apps.parametres.urls")),
+    path("sauvegardes/", include("apps.sauvegardes.urls")),
     path("notifications/", include("apps.notifications.urls")),
     path("admin/", admin.site.urls),
```

```bash
cd frontend && npm run build:css && cd ..
python manage.py check
```

**Résultat attendu :** `System check identified no issues (0 silenced).` (pas de `makemigrations` : l'app n'a pas de
modèle).

## Vérifier le chapitre

Les tests de `sauvegardes` vérifient aussi l'alerte du tableau de bord : ils sont présentés au chapitre suivant.
Vérifiez à la main, avec un compte ADMIN (`python manage.py runserver`, menu « Sauvegardes ») : la page indique
qu'aucune sauvegarde n'est encore enregistrée ; « Sauvegarder maintenant » crée un fichier dans
`sauvegardes/demandes/` et un second clic est refusé avec le message « Une sauvegarde est déjà demandée ».
Supprimez ensuite ce fichier de demande : en développement, aucun service ne viendra le traiter.

## Ce qu'il faut retenir

- Une application web n'a pas à détenir tous les droits : elle peut **demander** une action à un service qui, lui,
  a le privilège de l'exécuter.
- Écrire puis renommer un fichier rend son apparition **atomique** pour celui qui le lit.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 29 : app sauvegardes (suivi des sauvegardes, demande immédiate, alerte)"
```

---

[← Chapitre 28](28-ecrans-comptabilite.md) · [Sommaire](README.md) · [Chapitre 30 →](30-tableau-de-bord.md)
