"""Comptes d'essai : un compte par rôle, chacun rattaché à une fiche du personnel.

Réservé au développement (``DEBUG`` actif). Les fiches suivent une hiérarchie réaliste pour
que le workflow de congés fonctionne : la direction est au sommet (elle valide elle-même
son N1), le chauffeur dépend du parc auto, tous les autres de la direction.
"""

import secrets
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Role, User
from apps.hr import services
from apps.hr.models import Departement, Personnel

# (identifiant, rôle, prénom, nom, poste, département, supérieur)
COMPTES = (
    ("demo_direction", Role.DIRECTION, "Awa", "Koné", "Directrice générale", Departement.DIRECTION, None),
    ("demo_admin", Role.ADMIN, "Ibrahim", "Sanogo", "Administrateur système", Departement.DIRECTION, "demo_direction"),
    ("demo_rh", Role.RH, "Marie", "Yao", "Responsable RH", Departement.EXPLOITATION, "demo_direction"),
    ("demo_charge", Role.CHARGE_CLIENTELE, "Ali", "Traoré", "Chargé clientèle", Departement.COMMERCIAL, "demo_direction"),
    ("demo_parcauto", Role.PARCAUTO, "Issa", "Bamba", "Responsable parc auto", Departement.PARC_AUTO, "demo_direction"),
    ("demo_finances", Role.FINANCES, "Fatou", "Diallo", "Comptable", Departement.COMPTABILITE, "demo_direction"),
    ("demo_chauffeur", Role.CHAUFFEUR, "Moussa", "Ouattara", "Chauffeur", Departement.EXPLOITATION, "demo_parcauto"),
)


class Command(BaseCommand):
    help = "Crée (ou remet à jour) un compte d'essai par rôle, avec sa fiche du personnel."

    def add_arguments(self, parser):
        parser.add_argument(
            "--mot-de-passe",
            help="Mot de passe commun des comptes d'essai (généré au hasard si absent).",
        )

    def handle(self, *args, mot_de_passe=None, **options):
        if not settings.DEBUG:
            raise CommandError("Comptes d'essai réservés au développement (DEBUG doit être actif).")
        mot_de_passe = mot_de_passe or secrets.token_urlsafe(9)

        fiches: dict[str, Personnel] = {}
        for identifiant, role, prenom, nom, poste, departement, superieur in COMPTES:
            compte, _ = User.objects.get_or_create(username=identifiant)
            compte.role, compte.first_name, compte.last_name = role, prenom, nom
            compte.email = f"{identifiant}@densourcegroup.ci"
            compte.is_active = True
            compte.is_staff = role == Role.ADMIN
            compte.set_password(mot_de_passe)
            compte.save()

            fiche = Personnel.objects.filter(utilisateur=compte).first()
            if fiche is None:
                fiche = services.recruter(
                    matricule=f"DEMO-{identifiant.removeprefix('demo_').upper()}",
                    nom=nom,
                    prenom=prenom,
                    poste=poste,
                    departement=departement,
                    type_contrat="CDI",
                    date_embauche=date(2023, 3, 1),
                    salaire_base=Decimal("450000"),
                    superieur=fiches.get(superieur),
                    utilisateur=compte,
                )
            fiches[identifiant] = fiche
            self.stdout.write(f"{identifiant:<16} {role.label}")

        self.stdout.write(self.style.SUCCESS(f"\nMot de passe commun : {mot_de_passe}"))
