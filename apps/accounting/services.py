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
from django.db.models import QuerySet
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
    CompteInconnu,
    EcritureNonEquilibree,
    EcritureVerrouillee,
)
from .models import Compte, EcritureComptable, Journal, LigneEcriture, SensEcriture, StatutEcriture


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
    """Lignes d'un compte, triées par date d'écriture — lecture de vérification (le grand livre
    complet, avec soldes cumulés, vient de la Phase 6)."""
    lignes = LigneEcriture.objects.filter(compte=compte).select_related("ecriture", "compte")
    if debut is not None:
        lignes = lignes.filter(ecriture__date_ecriture__gte=debut)
    if fin is not None:
        lignes = lignes.filter(ecriture__date_ecriture__lte=fin)
    return lignes.order_by("ecriture__date_ecriture", "pk")
