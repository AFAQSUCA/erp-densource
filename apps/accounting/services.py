"""Moteur d'écritures comptables — conventions.md §2.

``passer_ecriture`` est le seul point d'entrée qui écrit une ``EcritureComptable`` : il garantit
lui-même l'équilibre (jamais l'appelant), à l'image de ``_exiger_role``/``_exiger_statut`` dans
``apps.billing.services``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Sequence

from django.db import transaction
from django.db.models import Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.billing.models import COMPTE_DU_MODE
from apps.core.services import prochain_numero

from .constants import (
    CATEGORIE_DEPENSE_VERS_COMPTE,
    COMPTE_CLIENTS,
    COMPTE_TRESORERIE_VERS_COMPTE,
    COMPTE_TRESORERIE_VERS_JOURNAL,
    COMPTE_TVA_COLLECTEE,
    COMPTE_VENTES_TRANSPORT,
    NATURE_MOUVEMENT_VERS_COMPTE,
)
from . import permissions
from .exceptions import (
    ActionComptableNonAutorisee,
    ClotureImpossible,
    CompteInconnu,
    EcritureNonEquilibree,
    EcritureVerrouillee,
    ExerciceCloture,
)
from .models import (
    Compte,
    EcritureComptable,
    ExerciceComptable,
    Journal,
    LigneEcriture,
    NatureCompte,
    SensEcriture,
    StatutEcriture,
    StatutExercice,
)

ZERO = Decimal("0")


@dataclass(frozen=True)
class LigneSaisie:
    """Une ligne débit ou crédit à passer, avant résolution du ``Compte``."""

    compte: str
    sens: str
    montant: Decimal
    libelle: str = ""
    tiers_type: str = ""
    tiers_id: int | None = None


def _exiger_role(acteur, roles, action: str, *, strict: bool = False) -> None:
    role = acteur.role if strict else acteur.role_effectif
    if role not in roles:
        raise ActionComptableNonAutorisee(f"Vous n'avez pas le droit de {action}.")


def _exiger_brouillon(ecriture: EcritureComptable, action: str) -> None:
    if ecriture.statut != StatutEcriture.BROUILLON:
        raise EcritureVerrouillee(f"Impossible de {action} : l'écriture est « {ecriture.get_statut_display()} ».")


def exercice_pour(date_ecriture: date) -> ExerciceComptable:
    """Renvoie l'exercice comptable (année civile) de cette date, le crée ``OUVERT`` s'il
    n'existe pas encore — même principe que ``core.services.prochain_numero`` : aucun geste
    explicite n'est requis pour « ouvrir » une nouvelle année."""
    exercice, _ = ExerciceComptable.objects.get_or_create(
        annee=date_ecriture.year,
        defaults={
            "date_debut": date(date_ecriture.year, 1, 1),
            "date_fin": date(date_ecriture.year, 12, 31),
        },
    )
    return exercice


def _exiger_exercice_ouvert(date_ecriture: date) -> None:
    exercice = exercice_pour(date_ecriture)
    if exercice.statut == StatutExercice.CLOTURE:
        raise ExerciceCloture(
            f"L'exercice {exercice.annee} est clôturé : aucune écriture ne peut plus y être datée."
        )


@transaction.atomic
def cloturer_exercice(exercice: ExerciceComptable, acteur) -> ExerciceComptable:
    """Clôture un exercice : verrouille toute nouvelle écriture datée dans sa période. Refusé s'il
    reste des brouillons (saisie manuelle non validée) dans la période — à valider ou abandonner
    avant de clôturer, pour ne jamais clôturer une année à l'insu d'une saisie en attente.
    Contrôle **strict** (``acteur.role``) : réservé à la DIRECTION, comme ``Facture.valider`` —
    jamais l'ADMIN ni un superutilisateur à sa place. Jamais rouvert ensuite."""
    _exiger_role(acteur, permissions.CLOTURE_EXERCICE, "clôturer un exercice", strict=True)
    if exercice.statut == StatutExercice.CLOTURE:
        raise ExerciceCloture(f"L'exercice {exercice.annee} est déjà clôturé.")
    brouillons = EcritureComptable.objects.filter(
        statut=StatutEcriture.BROUILLON,
        date_ecriture__gte=exercice.date_debut,
        date_ecriture__lte=exercice.date_fin,
    ).count()
    if brouillons:
        raise ClotureImpossible(
            f"{brouillons} écriture(s) en brouillon reste(nt) dans cette période : "
            "validez-les ou abandonnez-les avant de clôturer."
        )
    exercice.statut = StatutExercice.CLOTURE
    exercice.cloture_par = acteur
    exercice.date_cloture = timezone.now()
    exercice.save(update_fields=["statut", "cloture_par", "date_cloture", "updated_at"])
    return exercice


def _comptes_actifs(numeros: set[str]) -> dict[str, Compte]:
    comptes = {c.numero: c for c in Compte.objects.filter(numero__in=numeros, actif=True)}
    manquants = numeros - comptes.keys()
    if manquants:
        raise CompteInconnu(
            f"Compte(s) inconnu(s) ou inactif(s) dans le plan comptable : {', '.join(sorted(manquants))}."
        )
    return comptes


@transaction.atomic
def passer_ecriture(
    *,
    journal: str,
    date_ecriture: date,
    libelle: str,
    lignes: Sequence[LigneSaisie],
    origine: str = "",
    origine_id: int | None = None,
    piece_reference: str = "",
) -> EcritureComptable:
    """Crée une écriture équilibrée (débit == crédit) et ses lignes.

    Idempotente par ``(origine, origine_id)`` : rejouer le même événement source renvoie
    l'écriture déjà comptabilisée, sans en recréer une seconde. Tout est vérifié avant la
    moindre écriture en base : au moins 2 lignes, montants strictement positifs, comptes
    existants et actifs, total débit égal au total crédit.
    """
    if origine:
        existante = EcritureComptable.objects.filter(origine=origine, origine_id=origine_id).first()
        if existante is not None:
            return existante

    _exiger_exercice_ouvert(date_ecriture)

    if len(lignes) < 2:
        raise EcritureNonEquilibree("Une écriture comptable a au moins 2 lignes.")
    for ligne in lignes:
        if ligne.montant <= 0:
            raise EcritureNonEquilibree("Chaque montant doit être strictement positif.")

    comptes = _comptes_actifs({ligne.compte for ligne in lignes})

    total_debit = sum((l.montant for l in lignes if l.sens == SensEcriture.DEBIT), Decimal("0"))
    total_credit = sum((l.montant for l in lignes if l.sens == SensEcriture.CREDIT), Decimal("0"))
    if total_debit != total_credit:
        raise EcritureNonEquilibree(
            f"Écriture déséquilibrée : débit {total_debit} FCFA, crédit {total_credit} FCFA."
        )

    ecriture = EcritureComptable.objects.create(
        numero=prochain_numero(journal, date_ecriture.year),
        journal=journal,
        date_ecriture=date_ecriture,
        libelle=libelle,
        piece_reference=piece_reference,
        origine=origine,
        origine_id=origine_id,
        statut=StatutEcriture.VALIDEE,
    )
    LigneEcriture.objects.bulk_create(
        LigneEcriture(
            ecriture=ecriture,
            compte=comptes[ligne.compte],
            sens=ligne.sens,
            montant=ligne.montant,
            libelle=ligne.libelle,
            tiers_type=ligne.tiers_type,
            tiers_id=ligne.tiers_id,
        )
        for ligne in lignes
    )
    return ecriture


def comptabiliser_facture_validee(facture) -> EcritureComptable:
    """Écriture d'une facture validée : débite le client (TTC), crédite les ventes (HT) et la
    TVA collectée (si le taux n'est pas nul) — cahier-des-charges.md:340. Idempotent (voir
    :func:`passer_ecriture`) : reprendre une facture déjà comptabilisée ne recrée rien."""
    lignes = [
        LigneSaisie(
            compte=COMPTE_CLIENTS,
            sens=SensEcriture.DEBIT,
            montant=facture.montant_ttc,
            tiers_type="CLIENT",
            tiers_id=facture.client_id,
        ),
        LigneSaisie(
            compte=COMPTE_VENTES_TRANSPORT, sens=SensEcriture.CREDIT, montant=facture.montant_ht
        ),
    ]
    if facture.montant_tva > 0:
        lignes.append(
            LigneSaisie(
                compte=COMPTE_TVA_COLLECTEE, sens=SensEcriture.CREDIT, montant=facture.montant_tva
            )
        )
    return passer_ecriture(
        journal=Journal.VENTES,
        date_ecriture=facture.date_emission,
        libelle=f"Facture {facture.numero} — {facture.client}",
        lignes=lignes,
        origine="FACTURE",
        origine_id=facture.pk,
        piece_reference=facture.numero,
    )


def comptabiliser_un_reglement(reglement) -> EcritureComptable:
    """Écriture d'un règlement encaissé : débite la trésorerie (banque/caisse/mobile money selon
    le mode de paiement), crédite le client (411) — solde la créance. Idempotent (voir
    :func:`passer_ecriture`)."""
    compte_tresorerie = COMPTE_DU_MODE[reglement.mode]
    lignes = [
        LigneSaisie(
            compte=COMPTE_TRESORERIE_VERS_COMPTE[compte_tresorerie],
            sens=SensEcriture.DEBIT,
            montant=reglement.montant,
        ),
        LigneSaisie(
            compte=COMPTE_CLIENTS,
            sens=SensEcriture.CREDIT,
            montant=reglement.montant,
            tiers_type="CLIENT",
            tiers_id=reglement.facture.client_id,
        ),
    ]
    return passer_ecriture(
        journal=COMPTE_TRESORERIE_VERS_JOURNAL[compte_tresorerie],
        date_ecriture=reglement.date_reglement,
        libelle=f"Règlement {reglement.facture.numero} — {reglement.facture.client}",
        lignes=lignes,
        origine="REGLEMENT",
        origine_id=reglement.pk,
        piece_reference=reglement.facture.numero,
    )


def comptabiliser_une_depense_automatique(depense) -> EcritureComptable:
    """Écriture d'une dépense automatique (plein, achat de pièces, main-d'œuvre d'OR, frais de
    mission, ordre de décaissement) : débite la charge selon la catégorie, crédite la trésorerie
    selon le mode de paiement. Le mode est provisoire (Caisse par défaut) sauf pour un ordre de
    décaissement, dont le mode réel est connu dès l'exécution — voir :func:`reclasser_mode_depense`
    pour la correction ultérieure. Idempotent (voir :func:`passer_ecriture`)."""
    compte_tresorerie = COMPTE_DU_MODE[depense.mode]
    lignes = [
        LigneSaisie(
            compte=CATEGORIE_DEPENSE_VERS_COMPTE[depense.categorie],
            sens=SensEcriture.DEBIT,
            montant=depense.montant,
        ),
        LigneSaisie(
            compte=COMPTE_TRESORERIE_VERS_COMPTE[compte_tresorerie],
            sens=SensEcriture.CREDIT,
            montant=depense.montant,
        ),
    ]
    return passer_ecriture(
        journal=COMPTE_TRESORERIE_VERS_JOURNAL[compte_tresorerie],
        date_ecriture=depense.date_depense,
        libelle=depense.libelle,
        lignes=lignes,
        origine="DEPENSE",
        origine_id=depense.pk,
        piece_reference=depense.reference,
    )


def reclasser_mode_depense(depense, ancien_mode: str) -> EcritureComptable | None:
    """Corrige le compte de trésorerie d'une dépense automatique après coup (Finance corrige le
    mode réel via ``billing.services.changer_mode_depense``) : contre-passe l'ancien compte,
    impute le nouveau, plutôt que de modifier l'écriture d'origine (append-only). Ne crée rien si
    l'ancien et le nouveau mode partagent le même compte de trésorerie (ex. virement → chèque,
    tous deux Banque).

    Non idempotente (pas d'``origine``/``origine_id``) : une correction manuelle rejouée deux fois
    créerait deux reclassements — cas rare, accepté pour cette phase (voir « Limite connue »,
    avenant-comptabilite-syscohada.md)."""
    ancien_compte_tresorerie = COMPTE_DU_MODE[ancien_mode]
    nouveau_compte_tresorerie = COMPTE_DU_MODE[depense.mode]
    if ancien_compte_tresorerie == nouveau_compte_tresorerie:
        return None
    lignes = [
        LigneSaisie(
            compte=COMPTE_TRESORERIE_VERS_COMPTE[nouveau_compte_tresorerie],
            sens=SensEcriture.DEBIT,
            montant=depense.montant,
        ),
        LigneSaisie(
            compte=COMPTE_TRESORERIE_VERS_COMPTE[ancien_compte_tresorerie],
            sens=SensEcriture.CREDIT,
            montant=depense.montant,
        ),
    ]
    return passer_ecriture(
        journal=Journal.OPERATIONS_DIVERSES,
        date_ecriture=timezone.localdate(),
        libelle=f"Reclassement du mode de paiement — {depense.libelle}",
        lignes=lignes,
    )


def comptabiliser_un_mouvement_manuel(mouvement) -> EcritureComptable:
    """Écriture d'un mouvement manuel de trésorerie (solde d'ouverture, apport, retrait, frais
    bancaires…) : la contrepartie se déduit de sa nature (``finance.models.NatureMouvement``).
    Une entrée débite la trésorerie et crédite la contrepartie ; une sortie fait l'inverse.
    Idempotent (voir :func:`passer_ecriture`)."""
    from apps.finance.models import SensMouvement

    compte_tresorerie = COMPTE_DU_MODE[mouvement.mode]
    compte_contrepartie = NATURE_MOUVEMENT_VERS_COMPTE[mouvement.nature]
    if mouvement.sens == SensMouvement.ENTREE:
        lignes = [
            LigneSaisie(compte=COMPTE_TRESORERIE_VERS_COMPTE[compte_tresorerie], sens=SensEcriture.DEBIT, montant=mouvement.montant),
            LigneSaisie(compte=compte_contrepartie, sens=SensEcriture.CREDIT, montant=mouvement.montant),
        ]
    else:
        lignes = [
            LigneSaisie(compte=compte_contrepartie, sens=SensEcriture.DEBIT, montant=mouvement.montant),
            LigneSaisie(compte=COMPTE_TRESORERIE_VERS_COMPTE[compte_tresorerie], sens=SensEcriture.CREDIT, montant=mouvement.montant),
        ]
    return passer_ecriture(
        journal=COMPTE_TRESORERIE_VERS_JOURNAL[compte_tresorerie],
        date_ecriture=mouvement.date_mouvement,
        libelle=mouvement.libelle,
        lignes=lignes,
        origine="MOUVEMENT",
        origine_id=mouvement.pk,
        piece_reference=mouvement.reference,
    )


# --- saisie manuelle (opérations diverses) ---


@transaction.atomic
def creer_ecriture_manuelle(acteur, *, date_ecriture: date, libelle: str) -> EcritureComptable:
    """Ouvre un brouillon d'écriture manuelle (journal Opérations diverses) : pas de numéro tant
    qu'elle n'est pas validée (comme ``Facture``, pour ne pas laisser de trou de numérotation si
    elle est abandonnée), pas de ligne encore."""
    _exiger_role(acteur, permissions.SAISIE_OD, "saisir une écriture")
    if not libelle.strip():
        raise EcritureNonEquilibree("Le libellé est obligatoire.")
    _exiger_exercice_ouvert(date_ecriture)
    return EcritureComptable.objects.create(
        journal=Journal.OPERATIONS_DIVERSES,
        date_ecriture=date_ecriture,
        libelle=libelle.strip(),
        statut=StatutEcriture.BROUILLON,
        cree_par=acteur,
    )


@transaction.atomic
def ajouter_ligne_manuelle(
    ecriture: EcritureComptable, acteur, *, compte: str, sens: str, montant: Decimal, libelle: str = ""
) -> LigneEcriture:
    """Ajoute une ligne à un brouillon d'écriture manuelle."""
    _exiger_role(acteur, permissions.SAISIE_OD, "saisir une écriture")
    _exiger_brouillon(ecriture, "ajouter une ligne")
    montant = Decimal(montant)
    if montant <= 0:
        raise EcritureNonEquilibree("Le montant doit être strictement positif.")
    comptes = _comptes_actifs({compte})
    return LigneEcriture.objects.create(
        ecriture=ecriture, compte=comptes[compte], sens=sens, montant=montant, libelle=libelle.strip()
    )


def supprimer_ligne_manuelle(ligne: LigneEcriture, acteur) -> None:
    """Retire une ligne d'un brouillon d'écriture manuelle."""
    _exiger_role(acteur, permissions.SAISIE_OD, "modifier une écriture")
    _exiger_brouillon(ligne.ecriture, "retirer une ligne")
    ligne.delete()


@transaction.atomic
def abandonner_ecriture_manuelle(ecriture: EcritureComptable, acteur) -> None:
    """Abandonne un brouillon d'écriture manuelle (soft delete) : aucun numéro n'a encore été
    attribué, rien à contre-passer."""
    _exiger_role(acteur, permissions.SAISIE_OD, "abandonner une écriture")
    _exiger_brouillon(ecriture, "abandonner l'écriture")
    ecriture.delete(deleted_by=acteur)


@transaction.atomic
def valider_ecriture_manuelle(ecriture: EcritureComptable, acteur) -> EcritureComptable:
    """Verrouille un brouillon d'écriture manuelle : vérifie l'équilibre (au moins 2 lignes,
    débit == crédit), attribue son numéro, la statut passe à ``VALIDEE`` — définitif, réservé à la
    DIRECTION (contrôle strict, comme ``Facture.valider`` : jamais l'ADMIN ni un superutilisateur
    à sa place)."""
    _exiger_role(acteur, permissions.VALIDATION_OD, "valider une écriture", strict=True)
    _exiger_brouillon(ecriture, "valider l'écriture")
    _exiger_exercice_ouvert(ecriture.date_ecriture)
    lignes = list(ecriture.lignes.all())
    if len(lignes) < 2:
        raise EcritureNonEquilibree("Une écriture comptable a au moins 2 lignes.")
    total_debit = sum((l.montant for l in lignes if l.sens == SensEcriture.DEBIT), Decimal("0"))
    total_credit = sum((l.montant for l in lignes if l.sens == SensEcriture.CREDIT), Decimal("0"))
    if total_debit != total_credit:
        raise EcritureNonEquilibree(
            f"Écriture déséquilibrée : débit {total_debit} FCFA, crédit {total_credit} FCFA."
        )
    ecriture.numero = prochain_numero(ecriture.journal, ecriture.date_ecriture.year)
    ecriture.statut = StatutEcriture.VALIDEE
    ecriture.valide_par = acteur
    ecriture.date_validation = timezone.now()
    ecriture.save(update_fields=["numero", "statut", "valide_par", "date_validation", "updated_at"])
    return ecriture


def grand_livre(
    compte: Compte, *, debut: date | None = None, fin: date | None = None
) -> QuerySet[LigneEcriture]:
    """Lignes d'un compte, triées par date d'écriture."""
    lignes = LigneEcriture.objects.filter(compte=compte).select_related("ecriture", "compte")
    if debut is not None:
        lignes = lignes.filter(ecriture__date_ecriture__gte=debut)
    if fin is not None:
        lignes = lignes.filter(ecriture__date_ecriture__lte=fin)
    return lignes.order_by("ecriture__date_ecriture", "pk")


def grand_livre_avec_solde(
    compte: Compte, *, debut: date | None = None, fin: date | None = None
) -> list[dict]:
    """Lignes du compte avec leur solde cumulé (débit augmente le solde, crédit le diminue —
    convention SYSCOHADA, valable pour un compte d'actif/charge ; un compte de passif/produit se
    lit alors en négatif, ce qui reste correct pour vérifier l'équilibre ligne à ligne)."""
    solde = ZERO
    resultat = []
    for ligne in grand_livre(compte, debut=debut, fin=fin):
        solde += ligne.montant if ligne.sens == SensEcriture.DEBIT else -ligne.montant
        resultat.append({"ligne": ligne, "solde_cumule": solde})
    return resultat


def _agreger_par_compte(lignes: QuerySet[LigneEcriture]) -> list[dict]:
    """Total débit/crédit par compte mouvementé dans ``lignes``."""
    return list(
        lignes.values("compte__id", "compte__numero", "compte__libelle", "compte__nature")
        .annotate(
            total_debit=Coalesce(Sum("montant", filter=Q(sens=SensEcriture.DEBIT)), Value(ZERO)),
            total_credit=Coalesce(Sum("montant", filter=Q(sens=SensEcriture.CREDIT)), Value(ZERO)),
        )
        .order_by("compte__numero")
    )


def balance(*, debut: date | None = None, fin: date | None = None) -> list[dict]:
    """Balance générale : total débit/crédit et solde de chaque compte mouvementé sur la période
    (tous comptes confondus, toutes dates si ``debut``/``fin`` omis)."""
    lignes = LigneEcriture.objects.all()
    if debut is not None:
        lignes = lignes.filter(ecriture__date_ecriture__gte=debut)
    if fin is not None:
        lignes = lignes.filter(ecriture__date_ecriture__lte=fin)
    resultat = []
    for ligne in _agreger_par_compte(lignes):
        solde = ligne["total_debit"] - ligne["total_credit"]
        resultat.append(
            {
                **ligne,
                "solde_debiteur": solde if solde > 0 else ZERO,
                "solde_crediteur": -solde if solde < 0 else ZERO,
            }
        )
    return resultat


def compte_de_resultat(exercice: ExerciceComptable) -> dict:
    """Produits moins charges de l'exercice = résultat net (bénéfice ou perte). Calculé à la
    demande à partir des lignes de la période (rapport de situation) : aucune écriture de
    clôture n'existe encore pour transférer ce résultat dans le bilan de l'exercice suivant —
    voir « Limite connue », avenant-comptabilite-syscohada.md § P6."""
    lignes = LigneEcriture.objects.filter(
        ecriture__date_ecriture__gte=exercice.date_debut,
        ecriture__date_ecriture__lte=exercice.date_fin,
        compte__nature__in=[NatureCompte.CHARGE, NatureCompte.PRODUIT],
    )
    charges, produits = [], []
    total_charges = total_produits = ZERO
    for ligne in _agreger_par_compte(lignes):
        if ligne["compte__nature"] == NatureCompte.CHARGE:
            montant = ligne["total_debit"] - ligne["total_credit"]
            charges.append({**ligne, "montant": montant})
            total_charges += montant
        else:
            montant = ligne["total_credit"] - ligne["total_debit"]
            produits.append({**ligne, "montant": montant})
            total_produits += montant
    return {
        "charges": charges,
        "produits": produits,
        "total_charges": total_charges,
        "total_produits": total_produits,
        "resultat_net": total_produits - total_charges,
    }


def bilan(exercice: ExerciceComptable) -> dict:
    """Actif et passif cumulés depuis l'origine jusqu'à la fin de l'exercice (un bilan est une
    photo à une date, pas une période — contrairement au compte de résultat). Le résultat net de
    l'exercice (voir :func:`compte_de_resultat`) est ajouté au passif pour équilibrer le bilan,
    puisqu'il n'existe pas encore d'écriture de clôture qui l'impute au compte 120000."""
    lignes = LigneEcriture.objects.filter(
        ecriture__date_ecriture__lte=exercice.date_fin,
        compte__nature__in=[NatureCompte.ACTIF, NatureCompte.PASSIF],
    )
    actif, passif = [], []
    total_actif = total_passif = ZERO
    for ligne in _agreger_par_compte(lignes):
        if ligne["compte__nature"] == NatureCompte.ACTIF:
            montant = ligne["total_debit"] - ligne["total_credit"]
            actif.append({**ligne, "montant": montant})
            total_actif += montant
        else:
            montant = ligne["total_credit"] - ligne["total_debit"]
            passif.append({**ligne, "montant": montant})
            total_passif += montant
    resultat_net = compte_de_resultat(exercice)["resultat_net"]
    return {
        "actif": actif,
        "passif": passif,
        "total_actif": total_actif,
        "total_passif": total_passif,
        "resultat_net": resultat_net,
        "total_passif_avec_resultat": total_passif + resultat_net,
    }
