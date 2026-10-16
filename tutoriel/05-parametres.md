# Chapitre 5 — Les réglages modifiables à l'écran : l'app parametres

> 7 fichier(s) dans ce chapitre, 273 lignes de code.

## Ce que vous allez construire

**`parametres`** : les **réglages de l'application modifiables à l'écran**, sans toucher au code. Le cahier des charges
confie à l'ADMIN « config, seuils d'alerte » ; l'entreprise a décidé que la DIRECTION les modifie aussi
(`avenant-parametres.md`).

| Élément | Règle |
|---|---|
| `Parametres` | **une seule ligne** (`pk = 1`, garantie par une contrainte en base) de 12 valeurs |
| **Valeurs par défaut** | celles du cahier des charges : alerte à 30 jours, seuils carburant 20 / 40 / ± 60 %, plage plausible 20-45 L/100 km, TVA 18 %, délai de paiement 30 jours, congés N1 48 h / N2 24 h, droit annuel 26 jours ouvrés |
| **Lecture** | toujours `services.parametres()`, jamais une constante ; **rien n'est écrit en base** tant que personne n'a enregistré l'écran |
| **Modification** | ADMIN et DIRECTION ; bornes de chaque champ, puis cohérence (jaune < rouge < saisie suspecte, consommation minimale < maximale) ; **tout est vérifié avant d'écrire** |
| **Traçabilité** | chaque modification va au journal d'audit du chapitre 4 (ancienne et nouvelle valeur) |

Pourquoi si tôt ? Parce que presque toutes les apps suivantes **lisent** ces réglages : les congés (`hr`, chapitre 6),
les échéances des chauffeurs et des camions, les seuils du carburant, la TVA proposée aux nouveaux clients. Une app
ne peut lire que ce qui existe déjà : `parametres` passe donc avant elles. Son **écran** viendra avec le socle de
l'interface, au chapitre 18.

## Prérequis

- Chapitres 1 à 4 terminés.

## Notions Django de ce chapitre

- **Une table d'une seule ligne** (*singleton*) : `CheckConstraint(condition=Q(pk=1))` interdit toute autre ligne,
  même en contournant le code.
- **Lire sans écrire** : `Parametres.objects.filter(pk=1).first() or Parametres(pk=1)` renvoie un objet **non
  enregistré** portant les valeurs par défaut des champs. Tant que l'écran n'a jamais servi, la table reste vide.
- **Validateurs de champ** (`MinValueValidator`, `MaxValueValidator`) et **`full_clean()`** : Django vérifie les
  bornes de chaque champ avant l'enregistrement ; le service y ajoute les règles **entre** champs.
- **Une erreur qui porte plusieurs messages** : `ParametresInvalides` garde un dictionnaire « champ → messages »,
  que l'écran affichera sous chaque champ.
- **`select_for_update()`** : deux personnes qui enregistrent l'écran en même temps ne s'écrasent pas.

## Étape 1 — Créer l'application

```bash
mkdir -p apps/parametres/tests
```

#### Fichiers vides à créer

Ces fichiers n'ont aucun contenu ; ils servent à faire de leur dossier un *paquet Python* (sans eux, `import apps.xxx` échouerait). Créez d'abord les dossiers, puis les fichiers :

```bash
mkdir -p apps\parametres apps\parametres\tests
touch apps/parametres/__init__.py
touch apps/parametres/tests/__init__.py
```

> Sous PowerShell, `mkdir -p` s'écrit `New-Item -ItemType Directory -Force <dossier>` et `touch fichier` s'écrit `New-Item -ItemType File -Force fichier`. Vous pouvez aussi créer ces fichiers avec votre éditeur.

## Étape 2 — Le modèle et ses valeurs par défaut

#### `apps/parametres/README.md`

*24 lignes* — parametres

```markdown
# parametres

Rôle : réglages de l'application modifiables sans mise à jour du code — cahier-des-charges.md:48 (« ADMIN : config,
seuils d'alerte ») ; périmètre et droits décidés le 12/10/2026 (`avenant-parametres.md`). Écran `/parametres/`, menu
« Paramètres ». Dépend de `core`, `accounts`, `audit` ; lu par `fleet`, `drivers`, `fuel`, `missions`, `customers`,
`hr`, `dashboard`, `notifications` (architecture.md).

- **Une seule ligne** (`Parametres`, `pk = 1`, contrainte en base) : 12 valeurs — délai d'alerte avant expiration
  (30 j) ; seuils carburant (écart jaune 20 %, rouge 40 %, saisie suspecte ± 60 %, plage plausible 20-45 L/100 km) ;
  distance maximale entre deux relevés du compteur (5 000 km) ; TVA (18 %) et délai de paiement (30 j) proposés aux
  nouveaux clients ; délais de validation d'un congé (N1 48 h, N2 24 h) ; droit annuel de congé (26 jours ouvrés).
- **Valeurs par défaut = cahier des charges et avenants** : tant que l'écran n'a jamais été enregistré, la table est
  vide et `services.parametres()` renvoie ces valeurs **sans rien écrire**.
- **Lecture** : toujours `services.parametres()` (ou `services.delai_alerte(jours)`), jamais une constante. Pas de
  cache partagé : une requête sur une table d'une ligne, et pas de valeur fantôme après l'annulation d'une transaction.
  Dans une boucle, lire une fois et passer la valeur (`jours=`, `reglages=`). Dans un gabarit :
  `{{ reglages.delai_validation_n1_heures }}` (`context_processors.parametres`, paresseux : aucune requête si la page
  ne s'en sert pas).
- **Pas de rétroactivité** : un niveau d'alerte de plein, une date limite de validation déjà calculés restent tels
  quels. Exception : le droit annuel, recalculé à chaque lecture d'un solde (année en cours comprise).
- **Modification** (`services.modifier_parametres`) : ADMIN et DIRECTION (`permissions.MODIFICATION`, superutilisateur
  = ADMIN). Bornes de chaque champ (validateurs du modèle) puis cohérence : jaune < rouge < saisie suspecte,
  consommation minimale < maximale, TVA par défaut > 0. Tout est vérifié avant d'écrire.
- **Audit** : `audit_model(Parametres, module="PARAMETRES")` — ancienne et nouvelle valeur de chaque changement.
```

#### `apps/parametres/models.py`

*109 lignes* — Paramètres de l'application : une seule ligne (``pk = 1``), modifiable par l'ADMIN et la DIRECTION.

```python
"""Paramètres de l'application : une seule ligne (``pk = 1``), modifiable par l'ADMIN et la DIRECTION.

Les valeurs par défaut sont celles du cahier des charges et de ses avenants : tant que personne n'a enregistré
l'écran « Paramètres », la table est vide et l'application lit ces valeurs (``services.parametres``).
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.constants import DELAI_ALERTE_JOURS

PK_UNIQUE = 1

# Valeurs du cahier des charges (et des avenants), reprises tant qu'aucun paramètre n'est enregistré.
SEUIL_CONSO_JAUNE_PCT = Decimal("20")  # cahier-des-charges.md:153
SEUIL_CONSO_ROUGE_PCT = Decimal("40")  # cahier-des-charges.md:154
SEUIL_CONSO_SAISIE_PCT = Decimal("60")  # cahier-des-charges.md:155
CONSO_MIN_L100 = Decimal("20")  # cahier-des-charges.md:157
CONSO_MAX_L100 = Decimal("45")  # cahier-des-charges.md:157
# Distance maximale crédible entre deux relevés du compteur d'un même camion (deux pleins, ou le départ et
# l'arrivée d'une mission) : au-delà, c'est une faute de frappe plutôt qu'un trajet (audit M5-10 / M6-09).
ECART_KM_MAX = 5000
TVA_DEFAUT = Decimal("18.00")  # cahier-des-charges.md:120,185
DELAI_PAIEMENT_DEFAUT = 30  # jours ; échéance d'une facture = émission + délai du client
DELAI_VALIDATION_N1_HEURES = 48  # cahier-des-charges.md:213
DELAI_VALIDATION_N2_HEURES = 24  # cahier-des-charges.md:214
# 26 jours ouvrés (lundi-vendredi), au-delà du minimum légal ivoirien de 2,2 jours ouvrables par mois : avantage
# social décidé par l'entreprise (avenant-separation-des-taches.md § R7, remplace les 12 jours du CDC d'origine).
DROIT_ANNUEL_JOURS = 26


def _bornes(minimum, maximum):
    return [MinValueValidator(minimum), MaxValueValidator(maximum)]


class Parametres(models.Model):
    """Réglages modifiables sans mise à jour de l'application (avenant-parametres.md)."""

    # --- alertes ---
    delai_alerte_jours = models.PositiveSmallIntegerField(
        _("délai d'alerte avant expiration (jours)"), default=DELAI_ALERTE_JOURS, validators=_bornes(1, 365),
        help_text=_("Documents des camions, permis et visite médicale des chauffeurs."),
    )
    seuil_conso_jaune_pct = models.DecimalField(
        _("alerte jaune : écart de consommation (%)"), max_digits=5, decimal_places=2,
        default=SEUIL_CONSO_JAUNE_PCT, validators=_bornes(Decimal("1"), Decimal("500")),
        help_text=_("Au-delà de la moyenne des 3 derniers pleins du camion."),
    )
    seuil_conso_rouge_pct = models.DecimalField(
        _("alerte rouge : écart de consommation (%)"), max_digits=5, decimal_places=2,
        default=SEUIL_CONSO_ROUGE_PCT, validators=_bornes(Decimal("1"), Decimal("500")),
    )
    seuil_conso_saisie_pct = models.DecimalField(
        _("saisie suspecte : écart de consommation (± %)"), max_digits=5, decimal_places=2,
        default=SEUIL_CONSO_SAISIE_PCT, validators=_bornes(Decimal("1"), Decimal("500")),
    )
    conso_min_l100 = models.DecimalField(
        _("consommation minimale plausible (L/100 km)"), max_digits=5, decimal_places=2,
        default=CONSO_MIN_L100, validators=_bornes(Decimal("1"), Decimal("200")),
    )
    conso_max_l100 = models.DecimalField(
        _("consommation maximale plausible (L/100 km)"), max_digits=5, decimal_places=2,
        default=CONSO_MAX_L100, validators=_bornes(Decimal("1"), Decimal("200")),
    )
    ecart_km_max = models.PositiveIntegerField(
        _("distance maximale entre deux relevés (km)"), default=ECART_KM_MAX, validators=_bornes(100, 50000),
        help_text=_("Au-delà, la saisie du compteur est refusée (faute de frappe probable)."),
    )
    # --- clients et facturation ---
    tva_defaut = models.DecimalField(
        _("taux de TVA proposé aux nouveaux clients (%)"), max_digits=5, decimal_places=2, default=TVA_DEFAUT,
        validators=_bornes(Decimal("0.01"), Decimal("100")),
        help_text=_("Un client exonéré se règle sur sa fiche (0 % avec motif)."),
    )
    delai_paiement_defaut_jours = models.PositiveSmallIntegerField(
        _("délai de paiement proposé aux nouveaux clients (jours)"), default=DELAI_PAIEMENT_DEFAUT,
        validators=_bornes(1, 365),
    )
    # --- ressources humaines ---
    delai_validation_n1_heures = models.PositiveSmallIntegerField(
        _("délai de validation N1 d'un congé (heures)"), default=DELAI_VALIDATION_N1_HEURES,
        validators=_bornes(1, 720),
    )
    delai_validation_n2_heures = models.PositiveSmallIntegerField(
        _("délai de validation N2 d'un congé (heures)"), default=DELAI_VALIDATION_N2_HEURES,
        validators=_bornes(1, 720),
    )
    droit_annuel_jours = models.PositiveSmallIntegerField(
        _("droit annuel de congé (jours ouvrés)"), default=DROIT_ANNUEL_JOURS, validators=_bornes(1, 60),
        help_text=_("S'applique au calcul de tous les soldes, année en cours comprise."),
    )

    modifie_le = models.DateTimeField(_("modifié le"), auto_now=True)
    modifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("modifié par"), null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )

    class Meta:
        verbose_name = _("paramètres")
        verbose_name_plural = _("paramètres")
        constraints = [models.CheckConstraint(condition=models.Q(pk=PK_UNIQUE), name="parametres_ligne_unique")]

    def __str__(self) -> str:
        return "Paramètres de l'application"
```

Repérez les constantes `TVA_DEFAUT` et `DELAI_PAIEMENT_DEFAUT` : `customers` (chapitre 8) les réutilisera pour ses
propres valeurs par défaut.

## Étape 3 — Lire et modifier

#### `apps/parametres/permissions.py`

*6 lignes* — Qui consulte et modifie les paramètres : l'ADMIN (cahier-des-charges.md:48) et la DIRECTION (décision du

```python
"""Qui consulte et modifie les paramètres : l'ADMIN (cahier-des-charges.md:48) et la DIRECTION (décision du
12/10/2026, avenant-parametres.md). Un superutilisateur agit en ADMIN."""

from apps.accounts.models import Role

MODIFICATION = frozenset({Role.ADMIN, Role.DIRECTION})
```

#### `apps/parametres/services.py`

*109 lignes* — Lecture et modification des paramètres de l'application (cahier-des-charges.md:48 « config, seuils d'alerte » ;

```python
"""Lecture et modification des paramètres de l'application (cahier-des-charges.md:48 « config, seuils d'alerte » ;
décision du 12/10/2026 : avenant-parametres.md).

Les autres apps lisent toujours la valeur ici (``parametres()``), jamais une constante : un changement fait à
l'écran s'applique dès l'opération suivante, sans redémarrage. Il ne s'applique **jamais rétroactivement** à ce
qui a déjà été enregistré (niveau d'alerte d'un plein, date limite de validation d'un congé déjà demandé), sauf le
droit annuel de congé, qui est recalculé à chaque lecture du solde.

Pas de cache partagé : une lecture coûte une requête sur une table d'une ligne, et un cache survivrait à
l'annulation d'une transaction (valeur fantôme).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.exceptions import ErreurMetier

from . import permissions
from .models import PK_UNIQUE, Parametres

CHAMPS = (
    "delai_alerte_jours",
    "seuil_conso_jaune_pct",
    "seuil_conso_rouge_pct",
    "seuil_conso_saisie_pct",
    "conso_min_l100",
    "conso_max_l100",
    "ecart_km_max",
    "tva_defaut",
    "delai_paiement_defaut_jours",
    "delai_validation_n1_heures",
    "delai_validation_n2_heures",
    "droit_annuel_jours",
)


class ParametresError(ErreurMetier):
    """Erreur métier sur les paramètres (message affichable tel quel)."""


class ModificationNonAutorisee(ParametresError):
    """L'acteur n'a pas le droit de modifier les paramètres."""


class ParametresInvalides(ParametresError):
    """Une valeur est hors bornes ou incohérente avec une autre ; ``erreurs`` : champ -> messages."""

    def __init__(self, erreurs: dict[str, list[str]]):
        self.erreurs = erreurs
        super().__init__(" ".join(m for messages in erreurs.values() for m in messages))


def parametres() -> Parametres:
    """Les paramètres en vigueur ; ceux du cahier des charges tant que rien n'a été enregistré (sans rien écrire)."""
    return Parametres.objects.filter(pk=PK_UNIQUE).first() or Parametres(pk=PK_UNIQUE)


def delai_alerte(jours: int | None = None) -> int:
    """Délai d'alerte avant expiration : ``jours`` s'il est fourni (tests, appel explicite), sinon le paramètre."""
    return parametres().delai_alerte_jours if jours is None else jours


def peut_modifier(utilisateur) -> bool:
    return getattr(utilisateur, "role_effectif", None) in permissions.MODIFICATION


def _verifier_coherence(p: Parametres) -> dict[str, list[str]]:
    erreurs: dict[str, list[str]] = {}
    if p.seuil_conso_rouge_pct <= p.seuil_conso_jaune_pct:
        erreurs.setdefault("seuil_conso_rouge_pct", []).append(
            "Le seuil de l'alerte rouge doit être supérieur à celui de l'alerte jaune."
        )
    if p.seuil_conso_saisie_pct <= p.seuil_conso_rouge_pct:
        erreurs.setdefault("seuil_conso_saisie_pct", []).append(
            "Le seuil de saisie suspecte doit être supérieur à celui de l'alerte rouge."
        )
    if p.conso_max_l100 <= p.conso_min_l100:
        erreurs.setdefault("conso_max_l100", []).append(
            "La consommation maximale doit être supérieure à la consommation minimale."
        )
    return erreurs


@transaction.atomic
def modifier_parametres(acteur, **valeurs) -> Parametres:
    """Enregistre de nouvelles valeurs (ADMIN, DIRECTION). Tout est vérifié avant d'écrire : bornes de chaque champ
    et cohérence entre seuils. Seuls les champs de ``CHAMPS`` sont acceptés ; un champ absent garde sa valeur.
    Journalisé (``audit_model``, module ``PARAMETRES``) avec l'ancienne et la nouvelle valeur."""
    if not peut_modifier(acteur):
        raise ModificationNonAutorisee("Seuls l'administrateur et la direction modifient les paramètres.")
    inconnus = set(valeurs) - set(CHAMPS)
    if inconnus:
        raise ParametresError(f"Paramètre inconnu : {', '.join(sorted(inconnus))}.")

    p = Parametres.objects.select_for_update().filter(pk=PK_UNIQUE).first() or Parametres(pk=PK_UNIQUE)
    for champ, valeur in valeurs.items():
        setattr(p, champ, valeur)
    try:
        p.full_clean(exclude=["modifie_par"], validate_unique=False, validate_constraints=False)
    except ValidationError as erreur:
        raise ParametresInvalides(erreur.message_dict) from None
    erreurs = _verifier_coherence(p)
    if erreurs:
        raise ParametresInvalides(erreurs)
    p.modifie_par = acteur
    p.save()
    return p
```

- **`parametres()`** est la seule porte d'entrée en lecture. Dans une boucle, lisez-la **une fois** et passez la
  valeur, plutôt que de relire la base à chaque tour.
- **`delai_alerte(jours=None)`** : un test ou un appel explicite peut imposer son délai, sinon le paramètre
  s'applique.
- **`modifier_parametres`** refuse un champ inconnu, vérifie les bornes (`full_clean`) puis la cohérence ; rien
  n'est écrit si une seule règle est fausse.

## Étape 4 — Démarrage : audit et menu

#### `apps/parametres/apps.py`

*18 lignes*

```python
from django.apps import AppConfig


class ParametresConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.parametres"
    label = "parametres"
    verbose_name = "Paramètres"

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.audit.registry import audit_model

        from . import permissions
        from .models import Parametres

        audit_model(Parametres, module="PARAMETRES", exclure=("modifie_le", "modifie_par"))
        enregistrer(EntreeMenu("Paramètres", "parametres:modifier", "fa-sliders", permissions.MODIFICATION, ordre=90))
```

`ready()` branche le journal d'audit (chapitre 4) et inscrit l'entrée « Paramètres » dans le menu (chapitre 3) :
l'entrée n'apparaîtra qu'aux rôles de `permissions.MODIFICATION`.


## Étape 5 — Déclarer l'application et migrer

#### `config/settings/base.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/settings/base.py (avant)
+++ config/settings/base.py (après)
@@ -55,4 +55,5 @@
     "apps.accounts",
     "apps.audit",
+    "apps.parametres",
 ]
 
```

```bash
python manage.py makemigrations parametres
python manage.py migrate
```

**Résultat attendu :** `Create model Parametres`, puis `Applying parametres.0001_initial... OK`.

## Vérifier le chapitre

Les tests de `parametres` ouvrent son écran : ils sont présentés au chapitre 18. Vérifiez à la main que les valeurs
du cahier des charges s'appliquent **sans rien écrire** :

```bash
python manage.py shell -c "from apps.parametres.models import Parametres; from apps.parametres.services import parametres; p = parametres(); print(p.delai_alerte_jours, p.droit_annuel_jours, p.tva_defaut, Parametres.objects.count())"
```

**Résultat attendu :** `30 26 18.00 0` (les valeurs par défaut, et toujours aucune ligne en base).

Puis qu'une incohérence est refusée avant toute écriture :

```bash
python manage.py shell -c "from apps.accounts.models import User; from apps.parametres import services as s; d = User.objects.create_user(username='direction-essai', password='Mot-de-passe-1', role='DIRECTION'); s.modifier_parametres(d, seuil_conso_rouge_pct=10)"
```

**Résultat attendu :** une erreur `ParametresInvalides: Le seuil de l'alerte rouge doit être supérieur à celui de
l'alerte jaune.`

## Ce qu'il faut retenir

- Un réglage qui peut changer ne s'écrit pas en constante : il se **lit** au moment où il sert.
- Les valeurs par défaut vivent dans le modèle : l'application se comporte comme le cahier des charges tant que
  personne n'a rien modifié.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 5 : app parametres (réglages modifiables, valeurs du cahier des charges par défaut)"
```

---

[← Chapitre 4](04-audit.md) · [Sommaire](README.md) · [Chapitre 6 →](06-hr.md)
