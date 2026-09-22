# Chapitre 14 — La trésorerie : l'app finance

> 8 fichier(s) dans ce chapitre, 566 lignes de code.

## Ce que vous allez construire

**`finance`** : la **trésorerie** et les **indicateurs financiers**. Cette app est une **couche au-dessus** de
`billing` : elle lit ce que les autres ont enregistré et en tire des chiffres.

**La trésorerie = ce qui a réellement bougé.** Trois sources :

| Source | Sens |
|---|---|
| **Règlements** reçus (`billing`) | entrées |
| **Dépenses** payées (`billing`) | sorties |
| **Mouvements manuels** (`finance`) : solde d'ouverture, apport, frais bancaires, retrait | entrées ou sorties |

Le **compte** (Banque, Caisse, Mobile Money) se **déduit du mode de paiement** : virement et chèque → banque,
espèces → caisse, Wave / Orange Money / MTN → mobile money.

**Les indicateurs du mois** :

- **CA facturé** = total **HT** des factures émises ; **encaissé** = règlements du mois ;
- **charges** = dépenses saisies **+** carburant (litres × prix des pleins) **+** coût des OR clôturés
  (main-d'œuvre et pièces au PUMP). Les trois composantes restent visibles séparément ;
- **marge nette** = CA HT − charges ; **créances** = reste à recouvrer (dont échu) ; **trésorerie** = solde.

> Les **charges** (vue économique) et la **trésorerie** (vue réelle) ne sont volontairement **pas les mêmes
> chiffres**. Le rapprochement bancaire et les écritures comptables ne sont pas gérés (décision du client).

## Prérequis

- Chapitres 1 à 13 terminés.

## Notions Django de ce chapitre

- **Une app « de lecture »** : `finance` réutilise les services de `billing`, `fuel` et `inventory`
  **sans les dupliquer** : la règle du carburant reste dans `fuel`, le PUMP dans `inventory`.
- **Agrégation SQL** avec `Sum` et `values_list(...).annotate(...)` : le total est calculé par la base, pas
  par une boucle Python.
- **`order_by()` vide** pour neutraliser un tri par défaut qui fausserait un regroupement (`GROUP BY`).
- **Annulation logique d'un mouvement** (avec motif) : on n'efface pas un mouvement de trésorerie.
- **Dictionnaires de résultats** : les services renvoient des dictionnaires prêts à afficher (soldes,
  indicateurs).

## Étape 1 — Créer l'application

```bash
mkdir -p apps/finance/tests
```

#### Fichiers vides à créer

Ces fichiers n'ont aucun contenu ; ils servent à faire de leur dossier un *paquet Python* (sans eux, `import apps.xxx` échouerait). Créez d'abord les dossiers, puis les fichiers :

```bash
mkdir -p apps\finance apps\finance\tests
touch apps/finance/__init__.py
touch apps/finance/tests/__init__.py
```

> Sous PowerShell, `mkdir -p` s'écrit `New-Item -ItemType Directory -Force <dossier>` et `touch fichier` s'écrit `New-Item -ItemType File -Force fichier`. Vous pouvez aussi créer ces fichiers avec votre éditeur.

## Étape 2 — Modèle et services

#### `apps/finance/models.py`

*42 lignes*

```python
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.billing.models import ModePaiement
from apps.core.models import BaseModel


class SensMouvement(models.TextChoices):
    ENTREE = "ENTREE", _("Entrée")
    SORTIE = "SORTIE", _("Sortie")


class MouvementManuel(BaseModel):
    """Entrée ou sortie de trésorerie qui n'est ni un règlement ni une dépense.

    Exemples : solde d'ouverture, apport, frais bancaires, retrait. Les règlements de factures
    et les dépenses alimentent la trésorerie tout seuls (cahier-des-charges.md:196-198).
    """

    sens = models.CharField(_("sens"), max_length=6, choices=SensMouvement.choices)
    date_mouvement = models.DateField(_("date"))
    libelle = models.CharField(_("libellé"), max_length=200)
    montant = models.DecimalField(_("montant (FCFA)"), max_digits=14, decimal_places=2)
    mode = models.CharField(_("mode"), max_length=14, choices=ModePaiement.choices)
    reference = models.CharField(_("référence"), max_length=100, blank=True)
    saisi_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    motif_annulation = models.TextField(_("motif d'annulation"), blank=True)

    class Meta:
        verbose_name = _("mouvement de trésorerie")
        verbose_name_plural = _("mouvements de trésorerie")
        ordering = ["-date_mouvement", "-pk"]
        constraints = [
            models.CheckConstraint(condition=Q(montant__gt=0), name="mouvement_montant_positif"),
        ]

    def __str__(self):
        return f"{self.get_sens_display()} {self.montant} : {self.libelle}"
```

Un seul modèle : `MouvementManuel`. Tout le reste de la trésorerie vient des modèles de `billing`.

#### `apps/finance/services.py`

*227 lignes* — Trésorerie et indicateurs financiers — cahier-des-charges.md:195-199.

```python
"""Trésorerie et indicateurs financiers — cahier-des-charges.md:195-199.

Trésorerie = ce qui a réellement bougé : règlements reçus (entrées), dépenses payées (sorties)
et mouvements manuels. Le compte (banque, caisse, mobile money) se déduit du mode de paiement.

Charges du mois (indicateur, distinct de la trésorerie) = dépenses saisies + carburant (pleins)
+ coût des OR clôturés (main-d'œuvre et pièces). Marge nette = CA HT - charges. Les trois
composantes restent visibles séparément. Le rapprochement bancaire n'est pas géré (décision
de l'utilisateur) ; les écritures comptables non plus.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.billing import permissions as billing_permissions
from apps.billing import services as billing_services
from apps.billing.exceptions import ActionFactureNonAutorisee, MontantInvalide
from apps.billing.models import COMPTE_DU_MODE, CompteTresorerie, Depense, ModePaiement, Reglement
from apps.fuel import services as fuel_services
from apps.inventory import services as inventory_services

from .models import MouvementManuel, SensMouvement

ZERO = Decimal("0")


def _compte(mode: str) -> str:
    return COMPTE_DU_MODE[ModePaiement(mode)]


# --- mouvements manuels ---


@transaction.atomic
def enregistrer_mouvement(
    acteur,
    *,
    sens: str,
    date_mouvement: date,
    libelle: str,
    montant: Decimal,
    mode: str,
    reference: str = "",
) -> MouvementManuel:
    if acteur.role_effectif not in billing_permissions.SAISIE:
        raise ActionFactureNonAutorisee("Vous n'avez pas le droit de saisir un mouvement.")
    libelle = libelle.strip()
    if not libelle:
        raise MontantInvalide("Le libellé est obligatoire.")
    montant = Decimal(montant)
    if montant <= 0:
        raise MontantInvalide("Le montant doit être strictement positif.")
    if date_mouvement > timezone.localdate():
        raise MontantInvalide("La date du mouvement ne peut pas être dans le futur.")
    return MouvementManuel.objects.create(
        sens=sens,
        date_mouvement=date_mouvement,
        libelle=libelle,
        montant=montant,
        mode=mode,
        reference=reference.strip(),
        saisi_par=acteur,
    )


@transaction.atomic
def annuler_mouvement(mouvement: MouvementManuel, acteur, *, motif: str) -> None:
    """Annule (logiquement) un mouvement manuel saisi par erreur."""
    if acteur.role_effectif not in billing_permissions.SAISIE:
        raise ActionFactureNonAutorisee("Vous n'avez pas le droit d'annuler un mouvement.")
    if not motif.strip():
        raise MontantInvalide("Le motif de l'annulation est obligatoire.")
    mouvement.motif_annulation = motif.strip()
    mouvement.save(update_fields=["motif_annulation", "updated_at"])
    mouvement.delete(deleted_by=acteur)


# --- lecture ---


def mouvements(
    *,
    date_debut: date | None = None,
    date_fin: date | None = None,
    sens: str = "",
    compte: str = "",
) -> list[dict]:
    """Journal de trésorerie, du plus récent au plus ancien.

    Chaque ligne : ``date``, ``libelle``, ``sens``, ``montant``, ``mode``, ``compte``,
    ``origine`` (REGLEMENT, DEPENSE ou MANUEL), ``reference``, ``objet`` (pour le lien).
    """
    lignes: list[dict] = []
    reglements = Reglement.objects.select_related("facture__client")
    depenses = Depense.objects.all()
    manuels = MouvementManuel.objects.all()
    if date_debut:
        reglements = reglements.filter(date_reglement__gte=date_debut)
        depenses = depenses.filter(date_depense__gte=date_debut)
        manuels = manuels.filter(date_mouvement__gte=date_debut)
    if date_fin:
        reglements = reglements.filter(date_reglement__lte=date_fin)
        depenses = depenses.filter(date_depense__lte=date_fin)
        manuels = manuels.filter(date_mouvement__lte=date_fin)
    if sens != SensMouvement.SORTIE:
        for r in reglements:
            lignes.append(
                {
                    "date": r.date_reglement,
                    "libelle": f"Règlement {r.facture.numero} · {r.facture.client.raison_sociale}",
                    "sens": SensMouvement.ENTREE,
                    "montant": r.montant,
                    "mode": r.mode,
                    "mode_libelle": r.get_mode_display(),
                    "reference": r.reference,
                    "origine": "REGLEMENT",
                    "objet": r,
                    "pk": r.pk,
                }
            )
    if sens != SensMouvement.ENTREE:
        for d in depenses:
            lignes.append(
                {
                    "date": d.date_depense,
                    "libelle": f"Dépense : {d.libelle}",
                    "sens": SensMouvement.SORTIE,
                    "montant": d.montant,
                    "mode": d.mode,
                    "mode_libelle": d.get_mode_display(),
                    "reference": d.reference,
                    "origine": "DEPENSE",
                    "objet": d,
                    "pk": d.pk,
                }
            )
    for m in manuels:
        if sens and m.sens != sens:
            continue
        lignes.append(
            {
                "date": m.date_mouvement,
                "libelle": m.libelle,
                "sens": m.sens,
                "montant": m.montant,
                "mode": m.mode,
                "mode_libelle": m.get_mode_display(),
                "reference": m.reference,
                "origine": "MANUEL",
                "objet": m,
                "pk": m.pk,
            }
        )
    for ligne in lignes:
        ligne["compte"] = _compte(ligne["mode"])
        ligne["compte_libelle"] = CompteTresorerie(ligne["compte"]).label
    if compte:
        lignes = [ligne for ligne in lignes if ligne["compte"] == compte]
    lignes.sort(key=lambda l: (l["date"], l["origine"], l["pk"]), reverse=True)
    return lignes


def _somme(queryset, champ: str = "montant") -> Decimal:
    return queryset.aggregate(total=Sum(champ))["total"] or ZERO


def soldes_par_compte() -> dict:
    """Solde en temps réel de chaque compte (entrées - sorties, depuis l'origine) et total."""
    soldes = {code: ZERO for code in CompteTresorerie.values}
    for reglement_mode, total in Reglement.objects.values_list("mode").annotate(t=Sum("montant")).order_by():
        soldes[_compte(reglement_mode)] += total
    for mode, total in Depense.objects.values_list("mode").annotate(t=Sum("montant")).order_by():
        soldes[_compte(mode)] -= total
    for mode, sens, total in (
        MouvementManuel.objects.values_list("mode", "sens").annotate(t=Sum("montant")).order_by()
    ):
        soldes[_compte(mode)] += total if sens == SensMouvement.ENTREE else -total
    soldes["total"] = sum(soldes.values(), ZERO)
    return soldes


def synthese_periode(debut: date, fin: date) -> dict:
    """Entrées, sorties et variation de la trésorerie sur la période (bornes incluses)."""
    entrees = billing_services.encaissements(debut, fin) + _somme(
        MouvementManuel.objects.filter(
            sens=SensMouvement.ENTREE, date_mouvement__range=(debut, fin)
        )
    )
    sorties = billing_services.total_depenses(debut, fin) + _somme(
        MouvementManuel.objects.filter(
            sens=SensMouvement.SORTIE, date_mouvement__range=(debut, fin)
        )
    )
    return {"entrees": entrees, "sorties": sorties, "variation": entrees - sorties}


def charges(debut: date, fin: date) -> dict:
    """Charges de la période : dépenses saisies, carburant, coût des OR clôturés."""
    depenses = billing_services.total_depenses(debut, fin)
    carburant = fuel_services.cout_carburant(debut, fin)
    maintenance = inventory_services.cout_des_or_clotures(debut, fin)
    return {
        "depenses": depenses,
        "carburant": carburant,
        "maintenance": maintenance,
        "total": depenses + carburant + maintenance,
    }


def indicateurs(debut: date, fin: date, *, aujourd_hui: date | None = None) -> dict:
    """Indicateurs financiers de la période (cahier-des-charges.md:227-228, 199)."""
    ca = billing_services.chiffre_affaires(debut, fin)
    charges_periode = charges(debut, fin)
    return {
        "chiffre_affaires": ca,
        "encaisse": billing_services.encaissements(debut, fin),
        "charges": charges_periode,
        "marge_nette": ca - charges_periode["total"],
        "creances": billing_services.creances(aujourd_hui),
        "tresorerie": soldes_par_compte()["total"],
    }
```

À lire :

1. **`_compte`** : traduit un mode de paiement en compte grâce à `COMPTE_DU_MODE`.
2. **`enregistrer_mouvement`** / **`annuler_mouvement`** : contrôlent le rôle (`billing.permissions.SAISIE`), le
   montant (strictement positif) et le motif d'annulation.
3. **`soldes_par_compte`** : additionne règlements, soustrait dépenses, applique les mouvements manuels, et
   ajoute le **total**.
4. **`synthese_periode`** : entrées, sorties et variation sur une période.
5. **`charges`** et **`indicateurs`** : les chiffres du mois, en appelant `fuel.cout_carburant` et
   `inventory.cout_des_or_clotures`.

#### `apps/finance/permissions.py`

*9 lignes* — Qui peut consulter et alimenter la trésorerie.

```python
"""Qui peut consulter et alimenter la trésorerie.

Mêmes droits que la facturation (cahier-des-charges.md:53) : FINANCES saisit et suit la
trésorerie, la DIRECTION consulte, l'ADMIN a tous les accès.
"""

from apps.billing.permissions import CONSULTATION, SAISIE

__all__ = ["CONSULTATION", "SAISIE"]
```

Elle **réutilise** celles de `billing` : mêmes droits, écrits une seule fois.

#### `apps/finance/apps.py`

*21 lignes*

```python
from django.apps import AppConfig


class FinanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.finance'
    label = 'finance'

    def ready(self):
        from apps.accounts.navigation import EntreeMenu, enregistrer
        from apps.audit.registry import audit_model

        from . import permissions
        from .models import MouvementManuel

        audit_model(MouvementManuel, module="FINANCES")
        enregistrer(
            EntreeMenu(
                "Trésorerie", "finance:tresorerie", "fa-wallet", permissions.CONSULTATION, ordre=62
            )
        )
```

#### `apps/finance/README.md`

*20 lignes* — finance

```markdown
# finance

Rôle : trésorerie et indicateurs financiers — cahier-des-charges.md:195-199. Interface sous
`/finances/`. Couche au-dessus de `billing`.

**Trésorerie** = ce qui a réellement bougé : règlements reçus (entrées), dépenses payées (sorties) et
`MouvementManuel` (solde d'ouverture, apport, frais bancaires, retrait...). Le compte (Banque, Caisse,
Mobile Money) se déduit du mode de paiement : Virement et Chèque → Banque, Espèces → Caisse, Wave,
Orange et MTN → Mobile Money. Solde en temps réel par compte et total ; journal filtrable.

**Indicateurs du mois** (`services.indicateurs`, affichés au tableau de bord) :
- CA facturé = total **HT** des factures émises ; encaissé = règlements du mois ;
- charges = dépenses saisies + carburant (litres x prix des pleins) + coût des OR clôturés
  (main-d'œuvre et pièces au PUMP). Les trois composantes restent visibles ; ne pas saisir en
  dépense ce qui vient déjà des pleins et des OR ;
- marge nette = CA HT - charges ; créances = reste à recouvrer (dont échu) ; trésorerie = solde.
  Les charges (économiques) et la trésorerie (réelle) ne sont volontairement pas les mêmes chiffres.

Pas encore fait : **rapprochement bancaire** (écarté sur décision de l'utilisateur : trésorerie
seulement), import de relevés, écritures comptables, grand livre.
```

#### `apps/finance/tests/test_services.py`

*239 lignes* — Trésorerie (règlements, dépenses, mouvements manuels) et indicateurs financiers.

```python
"""Trésorerie (règlements, dépenses, mouvements manuels) et indicateurs financiers."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.billing import services as billing
from apps.billing.exceptions import ActionFactureNonAutorisee, MontantInvalide
from apps.billing.models import ModePaiement
from apps.billing.tests.helpers import JOUR, direction, emise, finances
from apps.drivers.tests.factories import ChauffeurFactory
from apps.finance import services
from apps.finance.models import MouvementManuel, SensMouvement
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel import services as fuel
from apps.garage import services as garage
from apps.garage.models import LieuReparation, TypeOr
from apps.inventory import services as stock
from apps.inventory.tests.factories import ArticleFactory

pytestmark = pytest.mark.django_db

SEPT = (date(2026, 9, 1), date(2026, 9, 30))


def _manuel(sens=SensMouvement.ENTREE, montant="100000", *, mode=ModePaiement.VIREMENT, jour=JOUR,
            libelle="Apport", acteur=None):
    return services.enregistrer_mouvement(
        acteur or finances(), sens=sens, date_mouvement=jour, libelle=libelle,
        montant=Decimal(montant), mode=mode,
    )


def _reglement(facture, montant, mode=ModePaiement.VIREMENT, jour=JOUR):
    return billing.enregistrer_reglement(
        facture, finances(), montant=Decimal(montant), mode=mode, date_reglement=jour
    )


def _depense(montant, mode=ModePaiement.ESPECES, jour=JOUR, categorie="PEAGES"):
    return billing.enregistrer_depense(
        finances(), categorie=categorie, date_depense=jour, libelle="Péage", montant=Decimal(montant), mode=mode
    )


# --- mouvements manuels ---


def test_un_mouvement_manuel_s_enregistre_et_s_annule_avec_un_motif():
    mouvement = _manuel()

    services.annuler_mouvement(mouvement, finances(), motif="Doublon")

    assert not MouvementManuel.objects.filter(pk=mouvement.pk).exists()
    assert MouvementManuel.all_objects.get(pk=mouvement.pk).motif_annulation == "Doublon"


@pytest.mark.parametrize(
    ("libelle", "montant", "jour", "message"),
    [
        ("  ", "10", JOUR, "libellé"),
        ("x", "0", JOUR, "strictement positif"),
        ("x", "10", date(2999, 1, 1), "futur"),
    ],
)
def test_mouvements_invalides(libelle, montant, jour, message):
    with pytest.raises(MontantInvalide, match=message):
        _manuel(libelle=libelle, montant=montant, jour=jour)


def test_les_mouvements_sont_reserves_a_finances_et_admin():
    with pytest.raises(ActionFactureNonAutorisee):
        _manuel(acteur=direction())
    mouvement = _manuel()
    with pytest.raises(ActionFactureNonAutorisee):
        services.annuler_mouvement(mouvement, direction(), motif="x")
    with pytest.raises(MontantInvalide, match="motif"):
        services.annuler_mouvement(mouvement, finances(), motif=" ")


# --- journal et soldes ---


def test_le_solde_reunit_reglements_depenses_et_mouvements_par_compte():
    facture = emise(prix="1000000")  # TTC 1 180 000
    _reglement(facture, "500000", ModePaiement.VIREMENT)
    _reglement(facture, "100000", ModePaiement.WAVE)
    _depense("20000", ModePaiement.ESPECES)
    _manuel(SensMouvement.ENTREE, "50000", mode=ModePaiement.ESPECES, libelle="Solde de caisse")
    _manuel(SensMouvement.SORTIE, "5000", mode=ModePaiement.VIREMENT, libelle="Frais bancaires")

    soldes = services.soldes_par_compte()

    assert soldes["BANQUE"] == Decimal("495000")  # 500 000 - 5 000
    assert soldes["CAISSE"] == Decimal("30000")  # 50 000 - 20 000
    assert soldes["MOBILE_MONEY"] == Decimal("100000")
    assert soldes["total"] == Decimal("625000")


def test_un_reglement_annule_ne_compte_plus():
    facture = emise(prix="1000000")
    reglement = _reglement(facture, "300000")
    billing.annuler_reglement(reglement, finances(), motif="Erreur")

    assert services.soldes_par_compte()["total"] == 0
    assert services.mouvements() == []


def test_le_journal_est_trie_et_decrit_chaque_origine():
    facture = emise(prix="1000000")
    _reglement(facture, "100000", jour=date(2026, 9, 3))
    _depense("5000", jour=date(2026, 9, 5))
    _manuel(jour=date(2026, 9, 4), libelle="Apport")

    journal = services.mouvements()

    assert [(m["origine"], m["sens"]) for m in journal] == [
        ("DEPENSE", "SORTIE"), ("MANUEL", "ENTREE"), ("REGLEMENT", "ENTREE"),
    ]
    assert journal[2]["libelle"].startswith(f"Règlement {facture.numero} · ")
    assert journal[2]["compte"] == "BANQUE" and journal[0]["compte"] == "CAISSE"


def test_le_journal_se_filtre_par_periode_sens_et_compte():
    facture = emise(prix="1000000")
    _reglement(facture, "100000", ModePaiement.WAVE, date(2026, 9, 3))
    _depense("5000", ModePaiement.ESPECES, date(2026, 9, 10))
    _manuel(SensMouvement.SORTIE, "1000", mode=ModePaiement.VIREMENT, jour=date(2026, 9, 15), libelle="Frais")

    assert len(services.mouvements(date_debut=date(2026, 9, 5))) == 2
    assert len(services.mouvements(date_fin=date(2026, 9, 5))) == 1
    assert [m["origine"] for m in services.mouvements(sens="ENTREE")] == ["REGLEMENT"]
    assert sorted(m["origine"] for m in services.mouvements(sens="SORTIE")) == ["DEPENSE", "MANUEL"]
    assert [m["origine"] for m in services.mouvements(compte="MOBILE_MONEY")] == ["REGLEMENT"]
    assert services.mouvements(compte="CAISSE")[0]["origine"] == "DEPENSE"


def test_synthese_de_periode_entrees_sorties_variation():
    facture = emise(prix="1000000")
    _reglement(facture, "400000", jour=date(2026, 9, 3))
    _manuel(SensMouvement.ENTREE, "100000", jour=date(2026, 9, 4))
    _depense("30000", jour=date(2026, 9, 6))
    _manuel(SensMouvement.SORTIE, "20000", jour=date(2026, 9, 7), libelle="Frais")
    _depense("999", jour=date(2026, 8, 6))  # hors période

    assert services.synthese_periode(*SEPT) == {
        "entrees": Decimal("500000"), "sorties": Decimal("50000"), "variation": Decimal("450000"),
    }


def test_sans_mouvement_tout_est_a_zero():
    assert services.soldes_par_compte()["total"] == 0
    assert services.synthese_periode(*SEPT)["variation"] == 0


# --- charges et indicateurs ---


def _or_cloture(jour_cloture, main_oeuvre="30000", pieces=2):
    ordre = garage.ouvrir_or(
        VehiculeFactory(), type_or=TypeOr.CURATIF, lieu=LieuReparation.INTERNE, motif="Freins"
    )
    article = ArticleFactory(reference=f"P-{ordre.pk}", quantite=0)
    stock.enregistrer_entree(article, quantite=10, prix_unitaire=Decimal("5000"))
    stock.sortir_pour_or(article, quantite=pieces, ordre=ordre)
    garage.cloturer_or(ordre, cout_main_oeuvre=Decimal(main_oeuvre))
    type(ordre).objects.filter(pk=ordre.pk).update(
        date_cloture=timezone.now().replace(year=jour_cloture.year, month=jour_cloture.month, day=jour_cloture.day)
    )
    return ordre


def _plein(litres, prix, jour, camion=None, km=1000, ticket="T"):
    return fuel.enregistrer_plein(
        vehicule=camion or VehiculeFactory(), chauffeur=ChauffeurFactory(), date_plein=jour, station="T",
        quantite_litres=Decimal(litres), prix_unitaire=Decimal(prix), km_compteur=km, numero_ticket=ticket,
    )


def test_le_cout_du_carburant_est_litres_fois_prix_sur_la_periode():
    _plein("100", "655", date(2026, 9, 3), ticket="A")
    _plein("50", "660", date(2026, 9, 8), ticket="B")
    _plein("999", "700", date(2026, 8, 30), ticket="C")  # hors période

    assert fuel.cout_carburant(*SEPT) == Decimal("98500")  # 65 500 + 33 000


def test_le_cout_des_or_clotures_compte_main_d_oeuvre_et_pieces_de_la_periode():
    _or_cloture(date(2026, 9, 10), main_oeuvre="30000", pieces=2)  # 30 000 + 2 x 5 000
    _or_cloture(date(2026, 8, 10), main_oeuvre="99999", pieces=1)  # hors période

    assert stock.cout_des_or_clotures(*SEPT) == Decimal("40000")


def test_charges_regroupe_depenses_carburant_et_maintenance():
    _depense("20000", jour=date(2026, 9, 2))
    _plein("100", "655", date(2026, 9, 3))
    _or_cloture(date(2026, 9, 10), main_oeuvre="30000", pieces=2)

    charges = services.charges(*SEPT)

    assert charges == {
        "depenses": Decimal("20000"),
        "carburant": Decimal("65500"),
        "maintenance": Decimal("40000"),
        "total": Decimal("125500"),
    }


def test_indicateurs_du_mois():
    facture = emise(prix="1000000", aujourd_hui=date(2026, 9, 10))
    emise(prix="500000", aujourd_hui=date(2026, 9, 12))  # créance non échue au 20/09
    _reglement(facture, "600000", jour=date(2026, 9, 15))
    _depense("100000", jour=date(2026, 9, 5))

    kpi = services.indicateurs(*SEPT, aujourd_hui=date(2026, 9, 20))

    assert kpi["chiffre_affaires"] == Decimal("1500000")  # HT
    assert kpi["encaisse"] == Decimal("600000")
    assert kpi["charges"]["total"] == Decimal("100000")
    assert kpi["marge_nette"] == Decimal("1400000")
    assert kpi["creances"]["total"] == Decimal("1180000") - Decimal("600000") + Decimal("590000")
    assert kpi["creances"]["nombre_echues"] == 0
    assert kpi["tresorerie"] == Decimal("500000")  # 600 000 encaissés - 100 000 dépensés


def test_la_marge_peut_etre_negative():
    _depense("300000", jour=date(2026, 9, 5))

    assert services.indicateurs(*SEPT)["marge_nette"] == Decimal("-300000")


def test_un_utilisateur_de_role_rh_ne_saisit_rien():
    with pytest.raises(ActionFactureNonAutorisee):
        _manuel(acteur=UserFactory(role=Role.RH))
```

## Étape 3 — Déclarer l'application et migrer

#### `config/settings/base.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/settings/base.py (avant)
+++ config/settings/base.py (après)
@@ -61,4 +61,5 @@
     "apps.fuel",
     "apps.billing",
+    "apps.finance",
 ]
 
```

```bash
python manage.py makemigrations finance
python manage.py migrate
```

**Résultat attendu :** `Create model MouvementManuel`, puis `Applying finance.0001_initial... OK`.

## Vérifier le chapitre

```bash
python manage.py check
```

```bash
python -m pytest apps/finance/tests/test_services.py -q --no-cov
```

**Résultat attendu :** `17 passed` (pour les 1 fichier(s) de tests présentés dans ce chapitre).

Essai dans le shell (base sans règlement ni dépense) :

```bash
python manage.py shell -c "from apps.finance import services as s; t = s.soldes_par_compte(); print(sorted(t), t['total'])"
```

**Résultat attendu :** `['BANQUE', 'CAISSE', 'MOBILE_MONEY', 'total'] 0`.

## Ce qu'il faut retenir

- Une app qui **agrège** doit **appeler** les services des autres, pas recopier leurs règles.
- Ne pas confondre **économique** (charges, marge) et **réel** (trésorerie) : deux vérités, deux chiffres.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 14 : app finance (trésorerie par compte, indicateurs du mois)"
```

---

[← Chapitre 13](13-billing.md) · [Sommaire](README.md) · [Chapitre 15 →](15-notifications.md)
