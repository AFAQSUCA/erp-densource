"""Rejoue les « essais dans le shell » du tutoriel et compare leur résultat à celui qui est annoncé.

    python outils/tester_tutoriel.py --jusqu-a 15 --garder      # reconstruit le projet (chapitres 1 à 15)
    python outils/verifier_essais.py <dossier conservé>          # exécute les essais dans l'ordre des chapitres

Chaque essai est une commande ``python manage.py …`` du tutoriel ; on vérifie que sa sortie contient le texte
que le chapitre annonce sous « Résultat attendu ». Les essais s'enchaînent : ils partagent la même base.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
PYTHON = str(RACINE / ".venv" / "Scripts" / "python.exe")

# (chapitre, arguments après « manage.py », textes attendus dans la sortie)
ESSAIS = [
    (2, ["shell", "-c", "from apps.core.search import normaliser; print(normaliser('TRAORÉ Moussa'))"], ["traore moussa"]),
    (2, ["shell", "-c", "from apps.core.formats import nombre, pourcentage_signe; print(nombre(1500.5, 1), pourcentage_signe(23.333))"],
     ["1 500,5 +23,3", "1\xa0500,5 +23,3", "1 500,5 +23,3"]),
    (3, ["shell", "-c", "from apps.accounts.models import User; u = User.objects.create_user('essai', password='Essai-de-mot-de-passe-1', role='RH'); print(u, u.role_effectif, u.check_password('Essai-de-mot-de-passe-1')); u.delete()"],
     ["essai RH True"]),
    (4, ["shell", "-c", "from apps.audit.services import log_action; from apps.audit.models import AuditLog, ActionChoices; e = log_action(action=ActionChoices.LOGIN, module='AUTH', entite='User'); print(e.date_heure is not None, AuditLog.objects.count())"],
     ["True 1"]),
    (5, ["initialiser_jours_feries", "2026"], ["jour(s) férié(s) créé(s) pour 2026."]),
    (5, ["shell", "-c", "from datetime import date; from apps.hr.services import calculer_jours; print(calculer_jours(date(2026, 9, 14), date(2026, 9, 20)))"], ["6"]),
    (6, ["creer_comptes_demo"], ["demo_direction", "demo_chauffeur", "Mot de passe commun :"]),
    (6, ["shell", "-c", "from apps.drivers.models import Chauffeur; print(list(Chauffeur.objects.values_list('personnel__matricule', 'statut')))"],
     ["[('DEMO-CHAUFFEUR', 'DISPONIBLE')]"]),
    (7, ["shell", "-c", "from apps.customers import services as s; c = s.creer_client(raison_sociale='Cimaf CI', ncc_nif='CI-0001', contact_principal='M. Kouassi', telephone='0700000000', adresse='Abidjan'); print(c.raison_sociale, c.taux_tva, c.delai_paiement_jours)"],
     ["Cimaf CI 18.00 30"]),
    (7, ["shell", "-c", "from apps.customers.models import Client; Client.objects.create(raison_sociale='ONG', ncc_nif='CI-0002', contact_principal='x', telephone='1', adresse='a', taux_tva=0)"],
     ["client_tva_zero_requiert_motif"]),
    (8, ["shell", "-c", "from decimal import Decimal; from apps.fleet import services as s; v = s.creer_vehicule(immatriculation='1234 ab 01', marque='Mercedes-Benz', modele='Actros', annee=2020, vin='vin00000000000001', kilometrage=120000, capacite_charge_t=Decimal('25'), reservoir_l=600); print(v.immatriculation, v.statut); print(s.calculer_statut(v.statut, or_ouverts=True, mission_active=True))"],
     ["1234 AB 01 DISPONIBLE", "EN_MAINTENANCE"]),
    (9, ["shell", "-c", "from apps.missions.services import generer_code; print(len(generer_code()))"], ["8"]),
    (9, ["shell", "-c", "from decimal import Decimal; from apps.customers.models import Client; from apps.missions import services as s; m = s.creer_mission(client=Client.objects.get(ncc_nif='CI-0001'), lieu_chargement='Abidjan', lieu_livraison='Bouaké', nature_marchandise='Ciment', poids_t=Decimal('22'), prix_convenu=Decimal('780000')); print(m.numero.startswith('MIS-'), m.statut, len(m.code_expediteur), m.code_expediteur != m.code_destinataire)"],
     ["True BROUILLON 8 True"]),
    (9, ["shell", "-c", "from apps.audit.models import AuditLog; l = AuditLog.objects.filter(entite='Mission').first(); print(l.action, 'code_expediteur' in l.nouvelle_valeur)"], ["CREATE False"]),
    (10, ["shell", "-c", "from decimal import Decimal; from apps.fleet.models import Vehicule; from apps.garage import services as g; v = Vehicule.objects.get(vin='VIN00000000000001'); o = g.ouvrir_or(v, type_or='CURATIF', lieu='INTERNE', motif='Bruit au freinage'); v.refresh_from_db(); print(o.numero.startswith('OR-'), v.statut); g.cloturer_or(o, cout_main_oeuvre=Decimal('45000')); v.refresh_from_db(); print(v.statut)"],
     ["True EN_MAINTENANCE", "DISPONIBLE"]),
    (11, ["shell", "-c", "from decimal import Decimal; from apps.inventory import services as s; a = s.creer_article(reference='pn-0455', designation='Pneu 315/80 R22.5', seuil_minimal=4); s.enregistrer_entree(a, quantite=10, prix_unitaire=Decimal('1000')); s.enregistrer_entree(a, quantite=10, prix_unitaire=Decimal('2000')); a.refresh_from_db(); print(a.reference, a.quantite, a.pump)"],
     ["PN-0455 20 1500.00"]),
    (12, ["shell", "-c", "from decimal import Decimal; from apps.fuel import services as s; c = s.calculer_consommation(Decimal('180'), 600); print(c); print(s.evaluer_ecart(Decimal('42'), Decimal('30'))); print(s.est_anomalie(Decimal('46')), s.est_anomalie(Decimal('45')))"],
     ["30.00", "Decimal('40.00')", "True False"]),
    (13, ["shell", "-c", "from decimal import Decimal; from apps.billing.services import arrondir_franc; print(arrondir_franc(Decimal('100530.5')), arrondir_franc(Decimal('100530.49')))"], ["100531 100530"]),
    (14, ["shell", "-c", "from apps.finance import services as s; t = s.soldes_par_compte(); print(sorted(t), t['total'])"], ["['BANQUE', 'CAISSE', 'MOBILE_MONEY', 'total'] 0"]),
    (15, ["shell", "-c", "from apps.accounts.models import User; from apps.notifications import services as s; u = User.objects.get(username='demo_rh'); s.notifier([u], categorie='CONGE', titre='Essai', cle='essai-1'); s.notifier([u], categorie='CONGE', titre='Essai', cle='essai-1'); print(s.nombre_non_lues(u))"], ["1"]),
    (15, ["taches_quotidiennes"], ["documents vehicules", "conges termines"]),
]


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    dossier = Path(sys.argv[1])
    echecs = 0
    for chapitre, arguments, attendus in ESSAIS:
        p = subprocess.run(
            [PYTHON, "manage.py", *arguments], cwd=dossier, capture_output=True, text=True, encoding="utf-8", errors="replace",
            env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
        )
        sortie = p.stdout + p.stderr
        if "pourcentage_signe" in arguments[-1]:  # deux écritures équivalentes (espaces insécables) : une suffit
            ok = any(a in sortie for a in attendus)
        else:
            ok = all(a in sortie for a in attendus)
        etat = "OK " if ok else "ÉCHEC"
        echecs += 0 if ok else 1
        resume = " | ".join(l.strip() for l in sortie.strip().split("\n")[-3:])
        print(f"{etat} ch.{chapitre:<2} {' '.join(arguments[:2])[:14]:<14} → {resume[:150]}")
        if not ok:
            print("      attendu :", attendus)
    print("\nRÉSULTAT :", "tous les essais correspondent" if echecs == 0 else f"{echecs} essai(s) ne correspondent pas")
    return 1 if echecs else 0


if __name__ == "__main__":
    raise SystemExit(main())
