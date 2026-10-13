"""Logique métier RH : recrutement et workflow de congés en 3 niveaux.

Réf. cahier-des-charges.md:204-221, glossaire-metier.md:133-144.

Statuts : DEMANDE → VALIDATION_N1 → APPROUVE → EN_COURS → TERMINE
(ou REFUSE). Les passages à EN_COURS / TERMINE sont automatiques
(:func:`synchroniser_statuts_conges`, à planifier par Celery Beat).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import openpyxl
from django.db import transaction
from django.db.models import Count, F, Q, QuerySet, Sum
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.core.classeurs import ClasseurSuspect, exiger_classeur_raisonnable
from apps.core.search import filtrer_par_texte, normaliser
from apps.core.services import prochain_numero
from apps.parametres import services as parametres_services

from . import permissions, signals, sorties
from .exceptions import (
    ActionNonAutorisee,
    CongeError,
    ImportPersonnelError,
    JourFerieInvalide,
    PersonnelError,
    SoldeInsuffisant,
    TransitionInterdite,
)
from .models import (
    AttributionConge,
    Conge,
    DecisionConge,
    Departement,
    JourFerie,
    NiveauValidation,
    Personnel,
    POSTES_COURANTS,
    ReportConge,
    StatutConge,
    StatutReport,
    ValidationConge,
)

# Délais de validation N1 (48 h, cahier-des-charges.md:213) et N2 (24 h, :214) et droit annuel de congé (26 jours
# ouvrés, avenant R7) : valeurs par défaut des paramètres (``apps.parametres``), lues à chaque opération.

PREFIXE_MATRICULE = "PERS"  # matricule auto-généré : PERS-AAAA-XXXX (voir recruter)

STATUTS_DECOMPTES = (StatutConge.APPROUVE, StatutConge.EN_COURS, StatutConge.TERMINE)
JOURS_NON_OUVRES = (5, 6)  # samedi, dimanche (weekday()) : jours ouvrés, pas ouvrables


# --- fiche du personnel et recrutement ---


def personnel_queryset() -> QuerySet[Personnel]:
    return Personnel.objects.select_related("superieur", "utilisateur")


def rechercher_personnel(
    *, departement: str = "", recherche: str = "", presence: str = sorties.PRESENCE_PRESENTS
) -> QuerySet[Personnel]:
    """Personnel filtré par présence (présents par défaut, sortis, tous), département et texte (nom, prénom,
    matricule, poste), annoté de sa sortie éventuelle."""
    resultat = sorties.annoter_sortie(sorties.filtrer_presence(personnel_queryset(), presence))
    if departement:
        resultat = resultat.filter(departement=departement)
    resultat = filtrer_par_texte(resultat, recherche, "nom", "prenom", "matricule", "poste")
    return resultat


def comptes_disponibles(*, garder: Personnel | None = None) -> QuerySet[User]:
    """Comptes actifs pas encore rattachés à une fiche (et celui de ``garder``)."""
    filtre = Q(personnel__isnull=True)
    if garder is not None and garder.utilisateur_id:
        filtre |= Q(pk=garder.utilisateur_id)
    return User.objects.filter(filtre, is_active=True).order_by(
        "last_name", "first_name", "username"
    )


def _verifier_rattachements(personnel: Personnel | None, superieur, utilisateur) -> None:
    """Le supérieur ne doit pas créer de boucle ; un compte ne sert qu'à une seule fiche."""
    if superieur is not None and personnel is not None:
        courant, vus = superieur, set()
        while courant is not None and courant.pk not in vus:
            if courant.pk == personnel.pk:
                raise PersonnelError(
                    "Ce supérieur dépend déjà de cet employé : "
                    "la hiérarchie ne peut pas former une boucle."
                )
            vus.add(courant.pk)
            courant = courant.superieur
    if utilisateur is not None:
        deja = Personnel.all_objects.filter(utilisateur=utilisateur)
        if personnel is not None:
            deja = deja.exclude(pk=personnel.pk)
        if deja.exists():
            raise PersonnelError("Ce compte utilisateur est déjà rattaché à une autre fiche.")


@transaction.atomic
def recruter(
    *,
    nom: str,
    prenom: str,
    poste: str,
    departement: str,
    type_contrat: str,
    date_embauche: date,
    salaire_base: Decimal,
    superieur: Personnel | None = None,
    utilisateur: User | None = None,
    matricule: str | None = None,
) -> Personnel:
    """Enregistre un recrutement (cahier-des-charges.md:209-210).

    Le matricule est généré automatiquement (``PERS-AAAA-XXXX``, :func:`apps.core.services.
    prochain_numero` — même mécanisme que les numéros de mission, d'OR et de facture) et n'est
    jamais ressaisi par l'utilisateur (formulaire de recrutement : voir ``forms.PersonnelForm``).
    En préciser un explicitement ne sert qu'aux données de démonstration et aux tests.

    Si le poste est « Chauffeur », la fiche chauffeur est créée par le signal
    de ``drivers`` (cahier-des-charges.md:108). Le matricule reste réservé même
    après suppression logique (cahier-des-charges.md:107).
    """
    if matricule is None:
        matricule = prochain_numero(PREFIXE_MATRICULE)
    elif Personnel.all_objects.filter(matricule=matricule).exists():
        raise PersonnelError(f"Le matricule {matricule} est déjà attribué.")
    _verifier_rattachements(None, superieur, utilisateur)
    return Personnel.objects.create(
        matricule=matricule,
        nom=nom,
        prenom=prenom,
        poste=poste,
        departement=departement,
        type_contrat=type_contrat,
        date_embauche=date_embauche,
        salaire_base=salaire_base,
        superieur=superieur,
        utilisateur=utilisateur,
    )


@transaction.atomic
def modifier_personnel(
    personnel: Personnel,
    *,
    nom: str,
    prenom: str,
    poste: str,
    departement: str,
    type_contrat: str,
    salaire_base: Decimal,
    superieur: Personnel | None,
    utilisateur: User | None,
) -> Personnel:
    """Met à jour la fiche. Le matricule et la date d'embauche ne changent pas."""
    if superieur is not None and superieur.pk == personnel.pk:
        raise PersonnelError("Un employé ne peut pas être son propre supérieur.")
    _verifier_rattachements(personnel, superieur, utilisateur)
    personnel.nom, personnel.prenom, personnel.poste = nom, prenom, poste
    personnel.departement, personnel.type_contrat = departement, type_contrat
    personnel.salaire_base, personnel.superieur = salaire_base, superieur
    personnel.utilisateur = utilisateur
    personnel.save()
    return personnel


# --- recrutement en masse (Excel) ---

# Ordre et intitulés attendus dans le fichier (ligne 1) — voir modele_import_personnel (views.py) et
# templates/hr/personnel_import.html. Le matricule (généré), le supérieur et le compte utilisateur
# ne se règlent pas depuis le fichier : à compléter ensuite fiche par fiche si besoin.
# Plus grand salaire que la base accepte (``Personnel.salaire_base`` : 12 chiffres dont 2 décimales).
SALAIRE_MAX = Decimal("9999999999")

COLONNES_IMPORT = [
    "Nom", "Prénom", "Poste", "Département", "Type de contrat", "Date d'embauche", "Salaire de base",
]


def _poste_importe(brut) -> str | None:
    brut = str(brut or "").strip()
    for poste in POSTES_COURANTS:
        if poste.casefold() == brut.casefold():
            return poste
    return None


def _departement_importe(brut) -> str | None:
    brut = str(brut or "").strip()
    for code, libelle in Departement.choices:
        if brut.casefold() in (code.casefold(), str(libelle).casefold()):
            return code
    return None


def _date_importee(brut) -> date | None:
    if isinstance(brut, datetime):
        return brut.date()
    if isinstance(brut, date):
        return brut
    brut = str(brut or "").strip()
    for format_ in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(brut, format_).date()
        except ValueError:
            continue
    return None


# Lecture tolérante des cellules d'un classeur, partagée avec l'import général (``apps.importation``).
poste_importe = _poste_importe
departement_importe = _departement_importe
date_importee = _date_importee


@dataclass
class ResultatImportPersonnel:
    crees: list[Personnel] = field(default_factory=list)
    deja_presents: list[str] = field(default_factory=list)  # « Nom Prénom » tels qu'écrits dans le fichier


def _cle_nom(nom: str, prenom: str) -> tuple[str, str]:
    """Même clé que l'import général (``apps.importation``) : sans accents, sans majuscules, espaces réduits."""
    return " ".join(normaliser(nom).split()), " ".join(normaliser(prenom).split())


@transaction.atomic
def importer_personnel(fichier) -> ResultatImportPersonnel:
    """Recrutement en masse depuis un classeur Excel (colonnes : voir ``COLONNES_IMPORT``).

    Tout ou rien (aucune saisie individuelle du poste ou du département à corriger dans
    l'urgence après coup) : la moindre ligne invalide fait échouer tout l'import
    (``ImportPersonnelError``, un message par ligne fautive) — aucune fiche n'est créée tant
    que le fichier entier n'est pas correct.

    Réimporter le même fichier ne crée pas de doublon : un employé déjà présent (même nom et prénom, comme
    l'import général) est listé dans ``deja_presents`` et laissé tel quel (audit M11-08, AV-17).
    """
    try:
        exiger_classeur_raisonnable(fichier)  # archive piégée refusée avant ouverture (audit AV-16)
    except ClasseurSuspect as erreur:
        raise ImportPersonnelError([str(erreur)]) from erreur
    try:
        classeur = openpyxl.load_workbook(fichier, data_only=True)
    except Exception as erreur:  # fichier corrompu, renommé en .xlsx, archive illisible...
        raise ImportPersonnelError(["Ce fichier n'est pas un classeur Excel (.xlsx) lisible."]) from erreur
    feuille = classeur.active

    en_tete = next(feuille.iter_rows(min_row=1, max_row=1, values_only=True), None)
    recu = tuple(str(cellule or "").strip() for cellule in (en_tete or ()))
    if recu[: len(COLONNES_IMPORT)] != tuple(COLONNES_IMPORT):
        raise ImportPersonnelError([
            "En-têtes de colonnes inattendus. Téléchargez le modèle et gardez son ordre de "
            "colonnes : " + ", ".join(COLONNES_IMPORT) + "."
        ])

    erreurs: list[str] = []
    a_creer: list[dict] = []
    resultat = ResultatImportPersonnel()
    connus = {_cle_nom(p.nom, p.prenom) for p in Personnel.objects.all()}
    # Fiche supprimée : erreur de ligne, ni recréée ni ignorée (audit AV-15, décision du 12/10/2026).
    supprimes = {_cle_nom(p.nom, p.prenom) for p in Personnel.all_objects.filter(is_deleted=True)}
    for numero, ligne in enumerate(feuille.iter_rows(min_row=2, values_only=True), start=2):
        if not ligne or all(cellule in (None, "") for cellule in ligne):
            continue  # ligne vide (fin de tableau…) : ignorée, ce n'est pas une erreur

        cellules = (list(ligne) + [None] * len(COLONNES_IMPORT))[: len(COLONNES_IMPORT)]
        nom_brut, prenom_brut, poste_brut, departement_brut, type_contrat_brut, date_brut, salaire_brut = cellules

        nom, prenom = str(nom_brut or "").strip(), str(prenom_brut or "").strip()
        if not nom:
            erreurs.append(f"Ligne {numero} : le nom est obligatoire.")
        if not prenom:
            erreurs.append(f"Ligne {numero} : le prénom est obligatoire.")
        if nom and prenom:
            if _cle_nom(nom, prenom) in supprimes and _cle_nom(nom, prenom) not in connus:
                erreurs.append(
                    f"Ligne {numero} : {nom} {prenom} a été supprimé(e) de l'ERP : restaurez la fiche "
                    "(administration) ou retirez la ligne."
                )
                continue
            if _cle_nom(nom, prenom) in connus:
                resultat.deja_presents.append(f"{nom} {prenom}")
                continue
            connus.add(_cle_nom(nom, prenom))

        poste = _poste_importe(poste_brut)
        if poste is None:
            erreurs.append(
                f"Ligne {numero} : poste « {poste_brut} » inconnu. Postes acceptés : "
                + ", ".join(POSTES_COURANTS) + "."
            )

        departement = _departement_importe(departement_brut)
        if departement is None:
            erreurs.append(
                f"Ligne {numero} : département « {departement_brut} » inconnu. Départements "
                "acceptés : " + ", ".join(str(libelle) for _, libelle in Departement.choices) + "."
            )

        date_embauche = _date_importee(date_brut)
        if date_embauche is None:
            erreurs.append(
                f"Ligne {numero} : date d'embauche « {date_brut} » invalide (attendu JJ/MM/AAAA)."
            )

        try:
            salaire_base = Decimal(str(salaire_brut))
            # NaN, Infinity ou montant que la base refuserait : erreur de ligne, pas erreur 500 (audit AV-13).
            if not salaire_base.is_finite() or not 0 <= salaire_base <= SALAIRE_MAX:
                raise InvalidOperation
        except (TypeError, InvalidOperation):
            salaire_base = None
            erreurs.append(f"Ligne {numero} : salaire de base « {salaire_brut} » invalide.")

        a_creer.append(dict(
            nom=nom,
            prenom=prenom,
            poste=poste,
            departement=departement,
            type_contrat=str(type_contrat_brut or "").strip(),
            date_embauche=date_embauche,
            salaire_base=salaire_base,
        ))

    if erreurs:
        raise ImportPersonnelError(erreurs)

    resultat.crees = [recruter(**champs) for champs in a_creer]
    return resultat


# --- droits des validateurs ---


def _fiche_de(acteur) -> Personnel | None:
    return getattr(acteur, "personnel", None)


def _est_sommet_hierarchie(employe: Personnel) -> bool:
    """Directeur : sans supérieur et titulaire d'un compte de rôle DIRECTION.

    Il valide lui-même son N1. Sans supérieur ni compte DIRECTION, l'absence de
    supérieur reste une erreur de saisie et non une autorisation d'auto-validation.
    """
    compte = employe.utilisateur
    return employe.superieur_id is None and compte is not None and compte.role == Role.DIRECTION


def _decide_pour_lui_meme(acteur, conge: Conge) -> bool:
    """Vrai si le validateur est l'employé lui-même (le directeur sur son propre N1) : marqué sur la décision."""
    return acteur is not None and conge.employe.utilisateur_id == acteur.pk


def _est_superieur_de(acteur, employe: Personnel) -> bool:
    """Vrai si ``acteur`` peut faire la validation N1 de la demande de l'employé.

    C'est le compte de son supérieur hiérarchique direct ; pour le directeur
    (:func:`_est_sommet_hierarchie`), c'est lui-même.
    """
    if acteur is None:
        return False
    if _est_sommet_hierarchie(employe):
        return employe.utilisateur_id == acteur.pk
    superieur = employe.superieur
    return bool(
        superieur is not None
        and superieur.pk != employe.pk
        and superieur.utilisateur_id == acteur.pk
    )


def _est_rh_pour(acteur, employe: Personnel) -> bool:
    """Utilisateur de rôle RH, jamais pour sa propre demande."""
    if acteur is None or acteur.role != Role.RH:
        return False
    fiche = _fiche_de(acteur)
    return fiche is None or fiche.pk != employe.pk


def _direction_remplace(acteur, conge: Conge, *, maintenant: datetime | None = None) -> bool:
    """La DIRECTION peut se substituer au validateur d'un niveau dont le délai est dépassé.

    Sans cela, l'alerte « validation en retard » lui serait adressée sans qu'elle puisse agir : le
    supérieur absent ou la RH indisponible ne doivent pas bloquer un employé. Jamais pour sa propre
    demande (la Direction, sans supérieur, valide déjà son N1 : :func:`_est_sommet_hierarchie`).
    """
    if acteur is None or acteur.role != Role.DIRECTION:
        return False
    fiche = _fiche_de(acteur)
    if fiche is not None and fiche.pk == conge.employe_id:
        return False
    attente = echeance_en_attente(conge, maintenant=maintenant)
    return bool(attente and attente[2])


def decide_en_remplacement(conge: Conge, acteur) -> bool:
    """La Direction décide ici à la place du validateur habituel (délai dépassé), pour l'expliquer à l'écran."""
    return (
        _direction_remplace(acteur, conge)
        and not _est_superieur_de(acteur, conge.employe)
        and not _est_rh_pour(acteur, conge.employe)
    )


def _recharger(conge: Conge) -> Conge:
    """Verrouille et relit le congé pour éviter deux décisions concurrentes."""
    Conge.objects.select_for_update().filter(pk=conge.pk).first()
    conge.refresh_from_db()
    return conge


def _verrouiller_employe(employe: Personnel) -> Personnel:
    Personnel.objects.select_for_update().filter(pk=employe.pk).first()
    employe.refresh_from_db()
    return employe


def droits_conges(employe: Personnel, annee: int) -> dict[str, int]:
    """Droits de congé d'un employé pour une année (en jours ouvrés).

    ``disponible`` = droit annuel + jours exceptionnels - jours déjà décomptés
    (congés approuvés, en cours ou terminés commençant cette année-là). Les
    demandes en attente ne sont pas décomptées avant la validation N2. Le droit annuel est celui des paramètres
    au moment de la lecture, quelle que soit l'année.
    """
    droit_annuel = parametres_services.parametres().droit_annuel_jours
    exceptionnels = (
        AttributionConge.objects.filter(employe=employe, annee=annee).aggregate(
            total=Sum("jours")
        )["total"]
        or 0
    )
    consommes = (
        Conge.objects.filter(
            employe=employe, statut__in=STATUTS_DECOMPTES, date_debut__year=annee
        ).aggregate(total=Sum("jours"))["total"]
        or 0
    )
    return {
        "droit_annuel": droit_annuel,
        "exceptionnels": exceptionnels,
        "consommes": consommes,
        "disponible": droit_annuel + exceptionnels - consommes,
    }


def _exiger_solde(employe: Personnel, annee: int, jours: int) -> None:
    disponible = droits_conges(employe, annee)["disponible"]
    if jours > disponible:
        raise SoldeInsuffisant(
            f"Solde insuffisant en {annee} : {jours} jour(s) ouvré(s) demandé(s), "
            f"{disponible} disponible(s)."
        )


@transaction.atomic
def accorder_jours_exceptionnels(
    employe: Personnel, acteur, *, annee: int, jours: int, motif: str
) -> AttributionConge:
    """Exception au droit annuel : la RH accorde des jours supplémentaires.

    Motif obligatoire ; la RH ne peut pas s'en accorder à elle-même.
    """
    if not _est_rh_pour(acteur, employe):
        raise ActionNonAutorisee("Attribution exceptionnelle réservée à la RH.")
    if jours < 1:
        raise CongeError("Le nombre de jours accordés doit être positif.")
    if not motif.strip():
        raise CongeError("Un motif est obligatoire pour une attribution exceptionnelle.")
    return AttributionConge.objects.create(
        employe=employe, annee=annee, jours=jours, motif=motif, accorde_par=acteur
    )


# --- lecture et actions possibles (écrans) ---


def validateur_n1(employe: Personnel) -> User | None:
    """Compte qui valide en N1 la demande de l'employé (son supérieur, ou lui-même s'il
    est le directeur) ; ``None`` si aucun compte n'est rattaché."""
    if _est_sommet_hierarchie(employe):
        return employe.utilisateur
    superieur = employe.superieur
    return superieur.utilisateur if superieur is not None else None


def comptes_rh(*, sauf: Personnel | None = None) -> QuerySet[User]:
    """Comptes RH actifs qui peuvent valider en N2 (sauf pour leur propre demande)."""
    comptes = User.objects.filter(role=Role.RH, is_active=True)
    if sauf is not None and sauf.utilisateur_id:
        comptes = comptes.exclude(pk=sauf.utilisateur_id)
    return comptes


def _validateur_n1_du(conge: Conge) -> int | None:
    """Compte qui a approuvé le N1 de ce congé (``None`` tant qu'il n'est pas validé N1)."""
    return (
        conge.validations.filter(niveau=NiveauValidation.N1, decision=DecisionConge.APPROUVE)
        .order_by("-created_at")
        .values_list("validateur_id", flat=True)
        .first()
    )


def _ids_rh_actifs() -> set[int]:
    return set(comptes_rh().values_list("pk", flat=True))


def _direction_sans_attendre(conge: Conge, n1: int | None, ids_rh: set[int]) -> bool:
    """Le N1 a été validé par le seul compte RH disponible : la Direction décide du N2 sans attendre le délai
    (audit M11-11, décision du 12/10/2026). Sans aucun compte RH, la règle reste celle du délai dépassé."""
    return n1 in ids_rh and not ids_rh - {n1, conge.employe.utilisateur_id}


def validateurs_n2(conge: Conge) -> QuerySet[User]:
    """Comptes qui décident du N2 sans attendre le délai : la RH, sauf l'employé lui-même et le compte qui a
    validé le N1 (un même compte ne valide pas les deux niveaux) ; si ce compte était le seul RH, la Direction."""
    n1, ids_rh = _validateur_n1_du(conge), _ids_rh_actifs()
    if _direction_sans_attendre(conge, n1, ids_rh):
        comptes = User.objects.filter(role=Role.DIRECTION, is_active=True)
    else:
        comptes = User.objects.filter(pk__in=ids_rh)
    return comptes.exclude(pk=n1).exclude(pk=conge.employe.utilisateur_id)


def _peut_decider_n2(acteur, conge: Conge, *, n1: int | None = None, ids_rh: set[int] | None = None) -> bool:
    """Valider ou refuser le N2 : la RH ou, à défaut (:func:`_direction_sans_attendre`), la Direction, ou la
    Direction qui remplace une RH en retard ; jamais l'employé lui-même ni le compte qui a validé le N1.
    ``n1`` et ``ids_rh`` évitent de relire la base pour chaque congé d'une liste."""
    if acteur is None:
        return False
    n1 = _validateur_n1_du(conge) if n1 is None else n1
    if acteur.pk in (n1, conge.employe.utilisateur_id):
        return False
    if acteur.role == Role.RH:
        return acteur.is_active
    if acteur.role == Role.DIRECTION:
        ids_rh = _ids_rh_actifs() if ids_rh is None else ids_rh
        return _direction_sans_attendre(conge, n1, ids_rh) or _direction_remplace(acteur, conge)
    return False


def fiche_personnel(acteur) -> Personnel | None:
    """Fiche de l'employé rattachée au compte, ou ``None``."""
    return _fiche_de(acteur)


def peut_accorder_jours(acteur, employe: Personnel) -> bool:
    return _est_rh_pour(acteur, employe)


def conges_queryset() -> QuerySet[Conge]:
    return Conge.objects.select_related("employe", "employe__superieur", "employe__utilisateur")


def conges_de(employe: Personnel) -> QuerySet[Conge]:
    return conges_queryset().filter(employe=employe)


def conges_a_valider(acteur) -> QuerySet[Conge]:
    """Demandes qui attendent la décision de ``acteur`` (N1 hiérarchique et/ou N2 RH)."""
    n1 = Q(employe__superieur__utilisateur=acteur) & ~Q(employe__superieur=F("employe"))
    if acteur.role == Role.DIRECTION:
        n1 |= Q(employe__superieur__isnull=True, employe__utilisateur=acteur)
    conditions = Q(statut=StatutConge.DEMANDE) & n1
    fiche = _fiche_de(acteur)
    if acteur.role in (Role.RH, Role.DIRECTION):
        # Une seule lecture pour tous les congés en attente de N2 et leur validateur N1 (liste à requêtes constantes).
        validations_n1 = ValidationConge.objects.filter(
            conge__statut=StatutConge.VALIDATION_N1, niveau=NiveauValidation.N1, decision=DecisionConge.APPROUVE
        ).select_related("conge__employe").order_by("created_at")
        en_n2 = {v.conge_id: (v.conge, v.validateur_id) for v in validations_n1}
        ids_rh = _ids_rh_actifs() if acteur.role == Role.DIRECTION else set()
        a_decider_n2 = [
            pk for pk, (conge, n1) in en_n2.items() if _peut_decider_n2(acteur, conge, n1=n1, ids_rh=ids_rh)
        ]
        conditions |= Q(pk__in=a_decider_n2)
    if acteur.role == Role.DIRECTION:
        en_retard = Q(statut=StatutConge.DEMANDE, date_limite_n1__lt=timezone.now())
        if fiche is not None:
            en_retard &= ~Q(employe=fiche)
        conditions |= en_retard
    resultat = conges_queryset().filter(conditions)
    if acteur.role == Role.RH and fiche is not None:
        # La RH ne valide pas sa propre demande en N2 (:func:`_est_rh_pour`).
        resultat = resultat.exclude(statut=StatutConge.VALIDATION_N1, employe=fiche)
    return resultat


def est_concerne_par(conge: Conge, acteur) -> bool:
    """L'employé lui-même ou son supérieur hiérarchique direct."""
    fiche = _fiche_de(acteur)
    return (fiche is not None and fiche.pk == conge.employe_id) or _est_superieur_de(
        acteur, conge.employe
    )


ACTION_VALIDER, ACTION_REFUSER, ACTION_ANNULER = "valider", "refuser", "annuler"


def actions_disponibles(conge: Conge, acteur) -> frozenset[str]:
    """Actions que ``acteur`` peut faire sur ce congé dans son état actuel."""
    if conge.statut == StatutConge.DEMANDE and (
        _est_superieur_de(acteur, conge.employe) or _direction_remplace(acteur, conge)
    ):
        return frozenset({ACTION_VALIDER, ACTION_REFUSER})
    if conge.statut == StatutConge.VALIDATION_N1 and _peut_decider_n2(acteur, conge):
        return frozenset({ACTION_VALIDER, ACTION_REFUSER})
    if conge.statut == StatutConge.APPROUVE and _est_rh_pour(acteur, conge.employe):
        return frozenset({ACTION_ANNULER})
    return frozenset()


def echeance_en_attente(conge: Conge, *, maintenant: datetime | None = None):
    """Échéance de la décision attendue : ``(niveau, limite, en_retard)`` ou ``None``."""
    if conge.statut == StatutConge.DEMANDE:
        niveau, limite = NiveauValidation.N1, conge.date_limite_n1
    elif conge.statut == StatutConge.VALIDATION_N1:
        niveau, limite = NiveauValidation.N2, conge.date_limite_n2
    else:
        return None
    if limite is None:
        return None
    return niveau, limite, limite < (maintenant or timezone.now())


# --- indicateurs (tableau de bord RH, cahier-des-charges.md:233-235) ---


def effectif_par_departement() -> list[dict]:
    """Effectif par département (tous les départements, y compris à 0) et total, sans le personnel sorti."""
    comptes = dict(
        sorties.presents(Personnel.objects.all()).values_list("departement").annotate(n=Count("pk")).order_by()
    )
    return [
        {"code": code, "libelle": libelle, "nombre": comptes.get(code, 0)}
        for code, libelle in Departement.choices
    ]


def absents_du_jour(jour: date | None = None) -> QuerySet[Conge]:
    """Congés approuvés ou en cours qui couvrent ``jour`` (avant la synchronisation
    quotidienne, un congé approuvé dont la date est arrivée compte déjà comme absent)."""
    jour = jour or timezone.localdate()
    return conges_queryset().filter(
        statut__in=[StatutConge.APPROUVE, StatutConge.EN_COURS],
        date_debut__lte=jour,
        date_fin__gte=jour,
    )


def prochains_conges(jour: date | None = None, *, jours: int = 30) -> QuerySet[Conge]:
    """Congés approuvés qui commencent dans les ``jours`` prochains jours."""
    jour = jour or timezone.localdate()
    return conges_queryset().filter(
        statut=StatutConge.APPROUVE,
        date_debut__gt=jour,
        date_debut__lte=jour + timedelta(days=jours),
    ).order_by("date_debut")


def conges_en_attente() -> dict[str, int]:
    """Demandes en attente : ``n1`` (supérieur) et ``n2`` (RH)."""
    return {
        "n1": Conge.objects.filter(statut=StatutConge.DEMANDE).count(),
        "n2": Conge.objects.filter(statut=StatutConge.VALIDATION_N1).count(),
    }


def conges_en_retard(maintenant: datetime | None = None) -> QuerySet[Conge]:
    """Demandes dont le délai de validation (paramètres : 48 h en N1, 24 h en N2) est dépassé."""
    maintenant = maintenant or timezone.now()
    return conges_queryset().filter(
        Q(statut=StatutConge.DEMANDE, date_limite_n1__lt=maintenant)
        | Q(statut=StatutConge.VALIDATION_N1, date_limite_n2__lt=maintenant)
    )


def valider_conge(conge: Conge, acteur, *, commentaire: str = "") -> Conge:
    """Validation du niveau en cours : N1 sur une demande, N2 sur un congé validé N1."""
    if conge.statut == StatutConge.DEMANDE:
        return valider_n1(conge, acteur, commentaire=commentaire)
    return valider_n2(conge, acteur, commentaire=commentaire)


# --- workflow ---


def calculer_jours(date_debut: date, date_fin: date) -> int:
    """Jours ouvrés entre deux dates, bornes incluses : lundi à vendredi, hors jours fériés légaux
    enregistrés dans ``JourFerie`` (avenant-separation-des-taches.md § R7 ; remplace le calcul en
    jours ouvrables — samedi compris — du cahier-des-charges.md d'origine)."""
    feries = set(
        JourFerie.objects.filter(date__range=(date_debut, date_fin)).values_list(
            "date", flat=True
        )
    )
    total, jour = 0, date_debut
    while jour <= date_fin:
        if jour.weekday() not in JOURS_NON_OUVRES and jour not in feries:
            total += 1
        jour += timedelta(days=1)
    return total


def _exiger_pas_de_chevauchement(employe: Personnel, date_debut: date, date_fin: date) -> None:
    """Refuse une demande qui recouvre un autre congé de l'employé (en attente, approuvé, en cours ou
    terminé) : sans cela, les mêmes jours seraient décomptés deux fois du solde. Un congé refusé ou annulé
    ne compte pas."""
    autre = (
        Conge.objects.filter(employe=employe, date_debut__lte=date_fin, date_fin__gte=date_debut)
        .exclude(statut=StatutConge.REFUSE)
        .order_by("date_debut")
        .first()
    )
    if autre is not None:
        etat = (
            "en attente de validation"
            if autre.statut in (StatutConge.DEMANDE, StatutConge.VALIDATION_N1)
            else autre.get_statut_display().lower()
        )
        raise CongeError(
            f"Cette période chevauche un congé déjà demandé du {autre.date_debut:%d/%m/%Y} au "
            f"{autre.date_fin:%d/%m/%Y} ({etat})."
        )


@transaction.atomic
def demander_conge(
    employe: Personnel,
    *,
    date_debut: date,
    date_fin: date,
    motif: str,
    maintenant: datetime | None = None,
) -> Conge:
    """Étape 1 : demande de l'employé (dates + motif), bloquée si solde insuffisant.

    Chacun adresse sa demande à son supérieur hiérarchique ; le directeur, qui
    n'en a pas, valide lui-même. Tout autre employé sans supérieur renseigné
    ne peut pas faire de demande.
    """
    if date_fin < date_debut:
        raise CongeError("La date de fin précède la date de début.")
    if employe.superieur_id is None and not _est_sommet_hierarchie(employe):
        raise CongeError("Aucun supérieur hiérarchique renseigné pour cet employé.")
    jours = calculer_jours(date_debut, date_fin)
    if jours == 0:
        raise CongeError("Aucun jour ouvré dans la période demandée.")
    employe = _verrouiller_employe(employe)
    _exiger_pas_de_chevauchement(employe, date_debut, date_fin)
    _exiger_solde(employe, date_debut.year, jours)

    maintenant = maintenant or timezone.now()
    conge = Conge.objects.create(
        employe=employe,
        date_debut=date_debut,
        date_fin=date_fin,
        jours=jours,
        motif=motif,
        date_limite_n1=maintenant + timedelta(hours=parametres_services.parametres().delai_validation_n1_heures),
    )
    signals.emettre(signals.conge_soumis, conge=conge)
    return conge


@transaction.atomic
def valider_n1(
    conge: Conge, acteur, *, commentaire: str = "", maintenant: datetime | None = None
) -> Conge:
    """Étape 2 : validation N1 par le supérieur hiérarchique de l'employé (délai des paramètres, 48 h)."""
    _recharger(conge)
    if conge.statut != StatutConge.DEMANDE:
        raise TransitionInterdite("Seule une demande peut être validée en N1.")
    if not (_est_superieur_de(acteur, conge.employe) or _direction_remplace(acteur, conge)):
        raise ActionNonAutorisee(
            "Validation N1 réservée au supérieur hiérarchique de l'employé "
            "(ou à la Direction une fois le délai dépassé)."
        )

    ValidationConge.objects.create(
        conge=conge,
        niveau=NiveauValidation.N1,
        validateur=acteur,
        decision=DecisionConge.APPROUVE,
        commentaire=commentaire,
        auto_validation=_decide_pour_lui_meme(acteur, conge),
    )
    conge.statut = StatutConge.VALIDATION_N1
    conge.date_limite_n2 = (maintenant or timezone.now()) + timedelta(
        hours=parametres_services.parametres().delai_validation_n2_heures
    )
    conge.save(update_fields=["statut", "date_limite_n2", "updated_at"])
    signals.emettre(signals.conge_valide_n1, conge=conge)
    return conge


@transaction.atomic
def valider_n2(conge: Conge, acteur, *, commentaire: str = "") -> Conge:
    """Étape 3 : validation N2 par la RH (délai des paramètres, 24 h). Le solde est recontrôlé, puis
    le congé approuvé est décompté du droit de l'année."""
    _recharger(conge)
    if conge.statut != StatutConge.VALIDATION_N1:
        raise TransitionInterdite("Seul un congé validé N1 peut être validé en N2.")
    if not _peut_decider_n2(acteur, conge):
        raise ActionNonAutorisee(
            "Validation N2 réservée à la RH, par un autre compte que celui qui a validé le N1 (à défaut d'autre "
            "compte RH, à la Direction ; sinon à la Direction une fois le délai dépassé)."
        )

    _exiger_solde(_verrouiller_employe(conge.employe), conge.date_debut.year, conge.jours)

    ValidationConge.objects.create(
        conge=conge,
        niveau=NiveauValidation.N2,
        validateur=acteur,
        decision=DecisionConge.APPROUVE,
        commentaire=commentaire,
        auto_validation=_decide_pour_lui_meme(acteur, conge),
    )
    conge.statut = StatutConge.APPROUVE
    conge.save(update_fields=["statut", "updated_at"])
    signals.emettre(
        signals.conge_decide, conge=conge, decision=signals.DECISION_APPROUVE, acteur=acteur
    )
    return conge


@transaction.atomic
def refuser(conge: Conge, acteur, *, commentaire: str = "") -> Conge:
    """Refus par le validateur du niveau en cours (N1 sur DEMANDE, N2 sur VALIDATION_N1)."""
    _recharger(conge)
    if conge.statut == StatutConge.DEMANDE:
        niveau = NiveauValidation.N1
        autorise = _est_superieur_de(acteur, conge.employe) or _direction_remplace(acteur, conge)
    elif conge.statut == StatutConge.VALIDATION_N1:
        niveau = NiveauValidation.N2
        autorise = _peut_decider_n2(acteur, conge)
    else:
        raise TransitionInterdite("Ce congé n'est plus en attente de validation.")
    if not autorise:
        raise ActionNonAutorisee("Vous n'êtes pas le validateur de ce niveau.")

    ValidationConge.objects.create(
        conge=conge,
        niveau=niveau,
        validateur=acteur,
        decision=DecisionConge.REFUSE,
        commentaire=commentaire,
        auto_validation=_decide_pour_lui_meme(acteur, conge),
    )
    conge.statut = StatutConge.REFUSE
    conge.motif_decision = commentaire
    conge.save(update_fields=["statut", "motif_decision", "updated_at"])
    signals.emettre(
        signals.conge_decide, conge=conge, decision=signals.DECISION_REFUSE, acteur=acteur
    )
    return conge


@transaction.atomic
def annuler_conge_approuve(conge: Conge, acteur, *, motif: str = "") -> Conge:
    """Annulation d'un congé approuvé : RH uniquement (cahier-des-charges.md:220-221).

    Le CDC ne prévoit pas de statut « annulé » : le congé passe à REFUSE avec
    le motif. Les jours sont restitués automatiquement : un congé REFUSE
    n'est plus décompté par :func:`droits_conges`.
    """
    _recharger(conge)
    if conge.statut != StatutConge.APPROUVE:
        raise TransitionInterdite("Seul un congé approuvé peut être annulé.")
    if not _est_rh_pour(acteur, conge.employe):
        raise ActionNonAutorisee("Annulation d'un congé approuvé réservée à la RH.")

    conge.statut = StatutConge.REFUSE
    conge.motif_decision = motif
    conge.save(update_fields=["statut", "motif_decision", "updated_at"])
    signals.emettre(
        signals.conge_decide, conge=conge, decision=signals.DECISION_ANNULE, acteur=acteur
    )
    return conge


# --- report du solde d'un congé en cours (avenant-separation-des-taches.md § R7) ---


def _recharger_report(report: ReportConge) -> ReportConge:
    ReportConge.objects.select_for_update().filter(pk=report.pk).first()
    report.refresh_from_db()
    return report


def peut_demander_report(conge: Conge, acteur) -> bool:
    """Vrai si ``acteur`` est l'employé de ce congé, actuellement en cours : lui seul peut en
    demander le report, et seulement pendant qu'il y est (bouton sur sa propre ligne)."""
    fiche = _fiche_de(acteur)
    return (
        conge.statut == StatutConge.EN_COURS
        and fiche is not None
        and fiche.pk == conge.employe_id
    )


@transaction.atomic
def demander_report(
    conge: Conge, acteur, *, date_reprise: date, motif: str, aujourd_hui: date | None = None
) -> ReportConge:
    """L'employé en congé écourte son congé et demande à garder le solde non pris. Sans validation de
    la RH, la demande n'a aucun effet : le congé continue normalement jusqu'à sa fin initiale.
    """
    _recharger(conge)
    if not peut_demander_report(conge, acteur):
        raise ActionNonAutorisee(
            "Seul l'employé actuellement en congé peut en demander le report."
        )
    aujourd_hui = aujourd_hui or timezone.localdate()
    # ``date_reprise`` : le jour où l'employé revient au travail ; ce jour-là n'est plus un jour de congé (décision
    # du 13/10/2026, audit AV-01). Le congé s'arrêtera la veille.
    if date_reprise < aujourd_hui:
        raise CongeError("La date de reprise ne peut pas être dans le passé.")
    if not (conge.date_debut < date_reprise <= conge.date_fin):
        raise CongeError(
            "La date de reprise doit être comprise entre le lendemain du début du congé et sa fin actuelle "
            f"(du {conge.date_debut + timedelta(days=1):%d/%m/%Y} au {conge.date_fin:%d/%m/%Y})."
        )
    if ReportConge.objects.filter(conge=conge, statut=StatutReport.DEMANDE).exists():
        raise CongeError("Une demande de report est déjà en attente pour ce congé.")
    if not motif.strip():
        raise CongeError("Un motif est obligatoire pour un report.")

    jours_restants = calculer_jours(date_reprise, conge.date_fin)  # jour de reprise compris : il est reversé
    if jours_restants == 0:
        raise CongeError("Aucun jour ouvré à reporter avec cette date de reprise.")

    report = ReportConge.objects.create(
        conge=conge, date_reprise=date_reprise, jours_restants=jours_restants, motif=motif.strip(),
    )
    signals.emettre(signals.report_demande, report=report)
    return report


@transaction.atomic
def approuver_report(
    report: ReportConge, acteur, *, commentaire: str = "", aujourd_hui: date | None = None
) -> ReportConge:
    """La RH valide le report : le congé est raccourci à la nouvelle date de reprise, ce qui libère
    aussitôt le solde (``droits_conges`` ne décompte que ``conge.jours``, réduit d'autant)."""
    _recharger_report(report)
    if report.statut != StatutReport.DEMANDE:
        raise TransitionInterdite("Cette demande de report a déjà été décidée.")
    conge = _recharger(report.conge)
    if not _est_rh_pour(acteur, conge.employe):
        raise ActionNonAutorisee("Validation d'un report réservée à la RH.")
    if conge.statut != StatutConge.EN_COURS:
        raise TransitionInterdite(
            "Le congé n'est plus en cours : cette demande de report n'est plus recevable."
        )

    aujourd_hui = aujourd_hui or timezone.localdate()
    conge.date_fin = report.date_reprise - timedelta(days=1)  # dernier jour de congé : la veille de la reprise
    conge.jours = conge.jours - report.jours_restants
    conge.statut = StatutConge.TERMINE if conge.date_fin < aujourd_hui else StatutConge.EN_COURS
    conge.save(update_fields=["date_fin", "jours", "statut", "updated_at"])

    report.statut = StatutReport.APPROUVE
    report.motif_decision = commentaire
    report.valide_par = acteur
    report.date_decision = timezone.now()
    report.save(
        update_fields=["statut", "motif_decision", "valide_par", "date_decision", "updated_at"]
    )
    signals.emettre(
        signals.report_decide, report=report, decision=signals.DECISION_APPROUVE, acteur=acteur
    )
    return report


@transaction.atomic
def refuser_report(report: ReportConge, acteur, *, motif: str) -> ReportConge:
    """La RH refuse le report : le congé continue sans changement jusqu'à sa fin initiale."""
    _recharger_report(report)
    if report.statut != StatutReport.DEMANDE:
        raise TransitionInterdite("Cette demande de report a déjà été décidée.")
    if not _est_rh_pour(acteur, report.conge.employe):
        raise ActionNonAutorisee("Validation d'un report réservée à la RH.")
    if not motif.strip():
        raise CongeError("Un motif est obligatoire pour refuser un report.")

    report.statut = StatutReport.REFUSE
    report.motif_decision = motif.strip()
    report.valide_par = acteur
    report.date_decision = timezone.now()
    report.save(
        update_fields=["statut", "motif_decision", "valide_par", "date_decision", "updated_at"]
    )
    signals.emettre(
        signals.report_decide, report=report, decision=signals.DECISION_REFUSE, acteur=acteur
    )
    return report


def report_en_attente(conge: Conge) -> ReportConge | None:
    """Demande de report en attente de décision pour ce congé, s'il y en a une."""
    return conge.reports.filter(statut=StatutReport.DEMANDE).order_by("-created_at").first()


def peut_decider_report(report: ReportConge, acteur) -> bool:
    """Vrai si ``acteur`` est la RH habilitée à valider/refuser cette demande de report."""
    return report.statut == StatutReport.DEMANDE and _est_rh_pour(acteur, report.conge.employe)


def synchroniser_statuts_conges(*, aujourd_hui: date | None = None) -> dict[str, int]:
    """Fait avancer les congés selon le calendrier : APPROUVE → EN_COURS → TERMINE.

    À exécuter chaque jour (Celery Beat, étape 5). Chaque changement de statut
    déclenche un signal : ``drivers`` y met le chauffeur « En congé » puis le
    remet « Disponible ».
    """
    aujourd_hui = aujourd_hui or timezone.localdate()
    resultat = {"demarres": 0, "termines": 0}
    candidats = Conge.objects.select_related("employe").filter(
        statut__in=[StatutConge.APPROUVE, StatutConge.EN_COURS]
    )
    for conge in candidats:
        if conge.date_fin < aujourd_hui:
            conge.statut = StatutConge.TERMINE
            resultat["termines"] += 1
        elif conge.statut == StatutConge.APPROUVE and conge.date_debut <= aujourd_hui:
            conge.statut = StatutConge.EN_COURS
            resultat["demarres"] += 1
        else:
            continue
        conge.save(update_fields=["statut", "updated_at"])
    return resultat


# --- jours fériés (droit ivoirien) ---


def date_paques(annee: int) -> date:
    """Dimanche de Pâques (algorithme grégorien de Meeus/Jones/Butcher)."""
    a, b, c = annee % 19, annee // 100, annee % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    mois = (h + m - 7 * n + 114) // 31
    jour = (h + m - 7 * n + 114) % 31 + 1
    return date(annee, mois, jour)


def jours_feries_legaux(annee: int) -> dict[date, str]:
    """Fêtes fixes et chrétiennes mobiles de l'année.

    Les fêtes musulmanes (fin du Ramadan, Tabaski, Maouloud) dépendent d'un
    décret annuel : elles ne sont pas calculées ici mais saisies par la RH.
    """
    paques = date_paques(annee)
    return {
        date(annee, 1, 1): "Jour de l'An",
        paques + timedelta(days=1): "Lundi de Pâques",
        date(annee, 5, 1): "Fête du Travail",
        paques + timedelta(days=39): "Ascension",
        paques + timedelta(days=50): "Lundi de Pentecôte",
        date(annee, 8, 7): "Fête de l'Indépendance",
        date(annee, 8, 15): "Assomption",
        date(annee, 11, 1): "Toussaint",
        date(annee, 11, 15): "Journée nationale de la Paix",
        date(annee, 12, 25): "Noël",
    }


@transaction.atomic
def initialiser_jours_feries(annee: int) -> int:
    """Crée les jours fériés fixes et chrétiens manquants ; retourne le nombre créé.

    Idempotent : ne recrée pas un jour déjà présent (et ne touche pas aux fêtes
    musulmanes saisies à la main). Un jour **supprimé** par la RH (par exemple un férié
    qui ne l'est pas cette année-là) n'est pas recréé non plus : la tâche quotidienne
    appelle cette fonction (audit M11-26).
    """
    existants = set(
        JourFerie.all_objects.filter(date__year=annee).values_list("date", flat=True)
    )
    a_creer = [
        JourFerie(date=jour, libelle=libelle)
        for jour, libelle in jours_feries_legaux(annee).items()
        if jour not in existants
    ]
    JourFerie.objects.bulk_create(a_creer)
    return len(a_creer)


# --- jours fériés entretenus par la RH (audit M11-26) ---


def jours_feries_de(annee: int) -> QuerySet[JourFerie]:
    return JourFerie.objects.filter(date__year=annee)


def _exiger_gestion_jours_feries(acteur) -> None:
    if acteur is None or acteur.role_effectif not in permissions.PERSONNEL_MODIFICATION:
        raise JourFerieInvalide("Seules la RH, la Direction et l'administrateur gèrent les jours fériés.")


@transaction.atomic
def ajouter_jour_ferie(acteur, *, jour: date, libelle: str) -> JourFerie:
    """Saisie d'un jour férié, en particulier des fêtes musulmanes fixées chaque année par décret. Les congés
    demandés ensuite l'excluent de leur décompte ; ceux déjà demandés ne sont pas recalculés."""
    _exiger_gestion_jours_feries(acteur)
    libelle = (libelle or "").strip()
    if not libelle:
        raise JourFerieInvalide("Le libellé est obligatoire (par exemple « Tabaski »).")
    if JourFerie.objects.filter(date=jour).exists():
        raise JourFerieInvalide(f"Le {jour:%d/%m/%Y} est déjà un jour férié.")
    return JourFerie.objects.create(date=jour, libelle=libelle[:100])


@transaction.atomic
def supprimer_jour_ferie(acteur, jour_ferie: JourFerie) -> None:
    """Suppression (douce, journalisée) : la génération automatique ne le recrée pas."""
    _exiger_gestion_jours_feries(acteur)
    jour_ferie.delete(deleted_by=acteur)


def attributions_de(employe: Personnel) -> QuerySet[AttributionConge]:
    """Jours de congé exceptionnels accordés à l'employé (audit TECH-26 : lus par l'écran via ce service)."""
    return AttributionConge.objects.filter(employe=employe).select_related("accorde_par")
