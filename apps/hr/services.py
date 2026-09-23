"""Logique métier RH : recrutement et workflow de congés en 3 niveaux.

Réf. cahier-des-charges.md:204-221, glossaire-metier.md:133-144.

Statuts : DEMANDE → VALIDATION_N1 → APPROUVE → EN_COURS → TERMINE
(ou REFUSE). Les passages à EN_COURS / TERMINE sont automatiques
(:func:`synchroniser_statuts_conges`, à planifier par Celery Beat).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import openpyxl
from django.db import transaction
from django.db.models import Count, F, Q, QuerySet, Sum
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.core.search import filtrer_par_texte
from apps.core.services import prochain_numero

from . import signals
from .exceptions import (
    ActionNonAutorisee,
    CongeError,
    ImportPersonnelError,
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
    StatutConge,
    ValidationConge,
)

DELAI_VALIDATION_N1 = timedelta(hours=48)  # cahier-des-charges.md:213
DELAI_VALIDATION_N2 = timedelta(hours=24)  # cahier-des-charges.md:214

PREFIXE_MATRICULE = "PERS"  # matricule auto-généré : PERS-AAAA-XXXX (voir recruter)

# Droit annuel : 2 semaines, comptées en jours ouvrables (lundi-samedi) selon
# le droit ivoirien, soit 2 x 6 = 12 jours (cahier-des-charges.md:219-221).
DROIT_ANNUEL_JOURS = 12
STATUTS_DECOMPTES = (StatutConge.APPROUVE, StatutConge.EN_COURS, StatutConge.TERMINE)
DIMANCHE = 6


# --- fiche du personnel et recrutement ---


def personnel_queryset() -> QuerySet[Personnel]:
    return Personnel.objects.select_related("superieur", "utilisateur")


def rechercher_personnel(*, departement: str = "", recherche: str = "") -> QuerySet[Personnel]:
    """Personnel filtré par département et par texte (nom, prénom, matricule, poste)."""
    resultat = personnel_queryset()
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


@transaction.atomic
def importer_personnel(fichier) -> list[Personnel]:
    """Recrutement en masse depuis un classeur Excel (colonnes : voir ``COLONNES_IMPORT``).

    Tout ou rien (aucune saisie individuelle du poste ou du département à corriger dans
    l'urgence après coup) : la moindre ligne invalide fait échouer tout l'import
    (``ImportPersonnelError``, un message par ligne fautive) — aucune fiche n'est créée tant
    que le fichier entier n'est pas correct.
    """
    classeur = openpyxl.load_workbook(fichier, data_only=True)
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
            if salaire_base < 0:
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

    return [recruter(**champs) for champs in a_creer]


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
    """Droits de congé d'un employé pour une année (en jours ouvrables).

    ``disponible`` = droit annuel + jours exceptionnels - jours déjà décomptés
    (congés approuvés, en cours ou terminés commençant cette année-là). Les
    demandes en attente ne sont pas décomptées avant la validation N2.
    """
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
        "droit_annuel": DROIT_ANNUEL_JOURS,
        "exceptionnels": exceptionnels,
        "consommes": consommes,
        "disponible": DROIT_ANNUEL_JOURS + exceptionnels - consommes,
    }


def _exiger_solde(employe: Personnel, annee: int, jours: int) -> None:
    disponible = droits_conges(employe, annee)["disponible"]
    if jours > disponible:
        raise SoldeInsuffisant(
            f"Solde insuffisant en {annee} : {jours} jour(s) ouvrable(s) demandé(s), "
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
    if acteur.role == Role.RH:
        conditions |= Q(statut=StatutConge.VALIDATION_N1)
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
    if conge.statut == StatutConge.DEMANDE and _est_superieur_de(acteur, conge.employe):
        return frozenset({ACTION_VALIDER, ACTION_REFUSER})
    if _est_rh_pour(acteur, conge.employe):
        if conge.statut == StatutConge.VALIDATION_N1:
            return frozenset({ACTION_VALIDER, ACTION_REFUSER})
        if conge.statut == StatutConge.APPROUVE:
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
    """Effectif par département (tous les départements, y compris à 0) et total."""
    comptes = dict(
        Personnel.objects.values_list("departement").annotate(n=Count("pk")).order_by()
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
    """Demandes dont le délai de validation (48 h en N1, 24 h en N2) est dépassé."""
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
    """Jours ouvrables entre deux dates, bornes incluses.

    Droit ivoirien : tous les jours sauf le dimanche (repos hebdomadaire) et
    les jours fériés légaux enregistrés dans ``JourFerie``.
    """
    feries = set(
        JourFerie.objects.filter(date__range=(date_debut, date_fin)).values_list(
            "date", flat=True
        )
    )
    total, jour = 0, date_debut
    while jour <= date_fin:
        if jour.weekday() != DIMANCHE and jour not in feries:
            total += 1
        jour += timedelta(days=1)
    return total


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
        raise CongeError("Aucun jour ouvrable dans la période demandée.")
    _exiger_solde(_verrouiller_employe(employe), date_debut.year, jours)

    maintenant = maintenant or timezone.now()
    conge = Conge.objects.create(
        employe=employe,
        date_debut=date_debut,
        date_fin=date_fin,
        jours=jours,
        motif=motif,
        date_limite_n1=maintenant + DELAI_VALIDATION_N1,
    )
    signals.emettre(signals.conge_soumis, conge=conge)
    return conge


@transaction.atomic
def valider_n1(
    conge: Conge, acteur, *, commentaire: str = "", maintenant: datetime | None = None
) -> Conge:
    """Étape 2 : validation N1 par le supérieur hiérarchique de l'employé (48 h)."""
    _recharger(conge)
    if conge.statut != StatutConge.DEMANDE:
        raise TransitionInterdite("Seule une demande peut être validée en N1.")
    if not _est_superieur_de(acteur, conge.employe):
        raise ActionNonAutorisee(
            "Validation N1 réservée au supérieur hiérarchique de l'employé."
        )

    ValidationConge.objects.create(
        conge=conge,
        niveau=NiveauValidation.N1,
        validateur=acteur,
        decision=DecisionConge.APPROUVE,
        commentaire=commentaire,
    )
    conge.statut = StatutConge.VALIDATION_N1
    conge.date_limite_n2 = (maintenant or timezone.now()) + DELAI_VALIDATION_N2
    conge.save(update_fields=["statut", "date_limite_n2", "updated_at"])
    signals.emettre(signals.conge_valide_n1, conge=conge)
    return conge


@transaction.atomic
def valider_n2(conge: Conge, acteur, *, commentaire: str = "") -> Conge:
    """Étape 3 : validation N2 par la RH (24 h). Le solde est recontrôlé, puis
    le congé approuvé est décompté du droit de l'année."""
    _recharger(conge)
    if conge.statut != StatutConge.VALIDATION_N1:
        raise TransitionInterdite("Seul un congé validé N1 peut être validé en N2.")
    if not _est_rh_pour(acteur, conge.employe):
        raise ActionNonAutorisee("Validation N2 réservée à la RH.")

    _exiger_solde(_verrouiller_employe(conge.employe), conge.date_debut.year, conge.jours)

    ValidationConge.objects.create(
        conge=conge,
        niveau=NiveauValidation.N2,
        validateur=acteur,
        decision=DecisionConge.APPROUVE,
        commentaire=commentaire,
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
        niveau, autorise = NiveauValidation.N1, _est_superieur_de(acteur, conge.employe)
    elif conge.statut == StatutConge.VALIDATION_N1:
        niveau, autorise = NiveauValidation.N2, _est_rh_pour(acteur, conge.employe)
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
    musulmanes saisies à la main).
    """
    existants = set(
        JourFerie.objects.filter(date__year=annee).values_list("date", flat=True)
    )
    a_creer = [
        JourFerie(date=jour, libelle=libelle)
        for jour, libelle in jours_feries_legaux(annee).items()
        if jour not in existants
    ]
    JourFerie.objects.bulk_create(a_creer)
    return len(a_creer)
