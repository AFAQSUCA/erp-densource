# Chapitre 27 — L'espace mobile du chauffeur

> 29 fichier(s) dans ce chapitre, 2291 lignes de code.

## Ce que vous allez construire

L'**espace mobile du chauffeur**, sous `/chauffeur/` : des pages **tactiles** (grands boutons, peu de texte),
**installables** sur l'écran d'accueil du téléphone comme une application (PWA).

| Écran | Adresse | Ce que fait le chauffeur |
|---|---|---|
| **Accueil** | `/chauffeur/` | mission du jour, camion, kilomètres du mois, consommation |
| **Missions** | `/chauffeur/missions/` | à faire, en cours, livrées cette semaine |
| **Une mission** | `/chauffeur/missions/<id>/` | **check-list**, **démarrer**, **confirmer la récupération** puis **la livraison** (code ou **scan du QR**) |
| **Plein** | `/chauffeur/plein/` | saisir un plein (avec la confirmation d'une saisie suspecte) |
| **Panne** | `/chauffeur/incident/` | signaler un incident |
| Fichiers de l'application | `manifest.webmanifest`, `sw.js`, `hors-ligne/` | installation, page « hors connexion » |

**Règles de sécurité** propres à cet espace :

- Le chauffeur ne voit **que ses données** : la mission d'un autre chauffeur est traitée comme **inexistante**
  (erreur 404).
- Il ne voit **ni le prix ni les codes secrets**.
- Il ne saisit un plein ou un incident **que sur son propre camion**.
- Sa session dure **15 minutes** d'inactivité (30 pour le bureau).
- Le *service worker* ne met en cache **que** la page « hors connexion », jamais une page privée.

## Prérequis

- Chapitres 1 à 26 terminés.

## Notions de ce chapitre

- **Trois couches sur les mêmes règles** : `services.py` (ce qu'un chauffeur voit et fait, sur ses données
  seulement), l'**API mobile** (`views.py`, chapitre 28) et les **écrans** (`views_web.py`). Les écrans et l'API
  appellent **les mêmes services** : une règle écrite une fois, vraie partout.
- **Une couche de service qui orchestre plusieurs apps** : `mobile_api.services` appelle `missions`, `fuel` et
  `garage` en ajoutant la règle « seulement pour ce chauffeur ».
- **PWA (Progressive Web App)** : un site qu'on peut « installer ». Il faut un **manifeste** (nom, icônes,
  couleurs, page de départ) et un **service worker** (un script que le navigateur exécute en tâche de fond).
- **Servir un fichier depuis une vue** : `sw.js` et `manifest.webmanifest` sont fabriqués par des vues
  (`ServiceWorkerView`, `ManifesteView`) pour connaître le bon préfixe d'adresse et rester à jour.
- **`BarcodeDetector`** : une API du navigateur (Chrome sur Android) qui lit un code QR avec la caméra.
  `scanner.js` l'utilise ; quand elle n'existe pas, le bouton n'apparaît pas et le chauffeur **saisit le code à la
  main**.
- **Pas de JavaScript en ligne** : même le *service worker* est enregistré par `sw-register.js`, à qui la
  page transmet l'adresse par `data-sw`.
- **Alpine.js** : le composant `scannerCode` pilote l'ouverture de la caméra (`x-data="scannerCode(…)"`).

## Étape 1 — Créer l'application

```bash
mkdir -p apps/mobile_api/templates/mobile apps/mobile_api/tests
```

#### Fichiers vides à créer

Ces fichiers n'ont aucun contenu ; ils servent à faire de leur dossier un *paquet Python* (sans eux, `import apps.xxx` échouerait). Créez d'abord les dossiers, puis les fichiers :

```bash
mkdir -p apps\mobile_api apps\mobile_api\tests
touch apps/mobile_api/__init__.py
touch apps/mobile_api/tests/__init__.py
```

> Sous PowerShell, `mkdir -p` s'écrit `New-Item -ItemType Directory -Force <dossier>` et `touch fichier` s'écrit `New-Item -ItemType File -Force fichier`. Vous pouvez aussi créer ces fichiers avec votre éditeur.

## Étape 2 — La couche de service du chauffeur

#### `apps/mobile_api/exceptions.py`

*10 lignes*

```python
class MobileError(Exception):
    """Erreur propre à l'espace chauffeur (camion introuvable, saisie hors périmètre...)."""


class MissionIntrouvable(MobileError):
    """La mission n'existe pas ou n'est pas affectée à ce chauffeur (jamais de fuite : 404)."""


class AucunCamion(MobileError):
    """Le chauffeur n'a aucun camion : pas de mission active, pas de camion habituel."""
```

#### `apps/mobile_api/services.py`

*233 lignes* — Services de l'espace chauffeur : ce qu'un chauffeur voit et fait, sur SES données seulement.

```python
"""Services de l'espace chauffeur : ce qu'un chauffeur voit et fait, sur SES données seulement.

Partagés par l'API mobile (JWT) et par les écrans mobiles (session) : la règle n'est écrite
qu'une fois. Chaque fonction reçoit le ``chauffeur`` et n'agit que sur ses missions ; une
mission d'un autre chauffeur est traitée comme inexistante (404), sans rien révéler.

Les règles métier restent dans ``missions``, ``fuel`` et ``garage`` ; ce module ne fait que
vérifier l'appartenance et orchestrer (cahier-des-charges.md:54, 132-143).
"""

from __future__ import annotations

from datetime import date, timedelta

from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.drivers.models import Chauffeur
from apps.fleet.models import Vehicule
from apps.fuel import services as fuel_services
from apps.fuel.models import Plein
from apps.garage import terrain as garage_terrain
from apps.garage.models import ChecklistVehicule, Incident
from apps.missions import services as missions_services
from apps.missions.models import Mission, StatutMission

from .exceptions import AucunCamion, MissionIntrouvable

STATUTS_EN_COURS = (StatutMission.EN_COURS_DEPART, StatutMission.EN_COURS_COLIS_RECUPERE)
JOURS_MISSIONS_LIVREES = 7  # une mission livrée reste visible une semaine


# --- missions ---


def missions_du_chauffeur(chauffeur: Chauffeur, *, aujourd_hui: date | None = None) -> QuerySet[Mission]:
    """Missions à faire, en cours, ou livrées depuis moins d'une semaine (les plus récentes d'abord)."""
    aujourd_hui = aujourd_hui or timezone.localdate()
    limite = timezone.now() - timedelta(days=JOURS_MISSIONS_LIVREES)
    return (
        missions_services.missions_queryset()
        .filter(chauffeur=chauffeur)
        .filter(
            Q(statut=StatutMission.AFFECTEE)
            | Q(statut__in=STATUTS_EN_COURS)
            | Q(statut=StatutMission.LIVREE, date_livraison__gte=limite)
        )
        .order_by("-date_depart_prevue", "-pk")
    )


def mission_du_chauffeur(chauffeur: Chauffeur, pk: int) -> Mission:
    """Une mission de ce chauffeur, quel que soit son statut ; sinon ``MissionIntrouvable``."""
    mission = missions_services.missions_queryset().filter(pk=pk, chauffeur=chauffeur).first()
    if mission is None:
        raise MissionIntrouvable("Mission introuvable.")
    return mission


def checklist_faite(mission: Mission) -> bool:
    return ChecklistVehicule.objects.filter(mission=mission).exists()


def actions_possibles(mission: Mission) -> dict[str, bool]:
    """Boutons proposés selon le statut : démarrer, confirmer la récupération, livrer."""
    return {
        "checklist": mission.statut == StatutMission.AFFECTEE and not checklist_faite(mission),
        "demarrer": mission.statut == StatutMission.AFFECTEE,
        "recuperation": mission.statut == StatutMission.EN_COURS_DEPART,
        "livraison": mission.statut == StatutMission.EN_COURS_COLIS_RECUPERE,
    }


def demarrer(chauffeur: Chauffeur, pk: int) -> Mission:
    mission = mission_du_chauffeur(chauffeur, pk)
    return missions_services.demarrer_mission(mission)


def confirmer_recuperation(chauffeur: Chauffeur, pk: int, *, code: str) -> Mission:
    """Colis récupéré : le code de l'expéditeur est saisi ou scanné sur le téléphone du chauffeur."""
    mission = mission_du_chauffeur(chauffeur, pk)
    return missions_services.confirmer_recuperation(mission, code=code)


def livrer(chauffeur: Chauffeur, pk: int, *, code: str, km_arrivee: int) -> Mission:
    """Livraison : code du destinataire et compteur à l'arrivée."""
    mission = mission_du_chauffeur(chauffeur, pk)
    return missions_services.livrer_mission(mission, code=code, km_arrivee=km_arrivee)


# --- camion et carburant ---


def vehicule_courant(chauffeur: Chauffeur) -> Vehicule | None:
    """Camion de la mission en cours, sinon de la prochaine mission, sinon son camion habituel."""
    missions = missions_services.missions_queryset().filter(chauffeur=chauffeur)
    mission = (
        missions.filter(statut__in=STATUTS_EN_COURS).order_by("-date_depart", "-pk").first()
        or missions.filter(statut=StatutMission.AFFECTEE).order_by("date_depart_prevue", "pk").first()
    )
    if mission is not None and mission.vehicule is not None:
        return mission.vehicule
    return Vehicule.objects.filter(chauffeur_habituel=chauffeur).order_by("immatriculation").first()


def _vehicules_autorises(chauffeur: Chauffeur) -> set[int]:
    """Camions sur lesquels ce chauffeur peut déclarer un plein ou un incident."""
    de_ses_missions = (
        Mission.objects.filter(chauffeur=chauffeur, statut__in=(StatutMission.AFFECTEE, *STATUTS_EN_COURS))
        .exclude(vehicule=None)
        .values_list("vehicule_id", flat=True)
    )
    habituels = Vehicule.objects.filter(chauffeur_habituel=chauffeur).values_list("pk", flat=True)
    return set(de_ses_missions) | set(habituels)


def _resoudre_vehicule(chauffeur: Chauffeur, vehicule_id: int | None) -> Vehicule:
    if vehicule_id is None:
        vehicule = vehicule_courant(chauffeur)
        if vehicule is None:
            raise AucunCamion("Aucun camion ne vous est affecté : contactez le Parc Auto.")
        return vehicule
    if vehicule_id not in _vehicules_autorises(chauffeur):
        raise AucunCamion("Ce camion n'est pas le vôtre.")
    return Vehicule.objects.get(pk=vehicule_id)


def saisir_plein(
    chauffeur: Chauffeur,
    *,
    station: str,
    quantite_litres,
    prix_unitaire,
    km_compteur: int,
    numero_ticket: str,
    date_plein: date | None = None,
    vehicule_id: int | None = None,
    confirmer: bool = False,
) -> Plein:
    """Saisie d'un plein par le chauffeur (cahier-des-charges.md:142-143, 148-155).

    Sans ``vehicule_id``, c'est le camion courant. Un écart de plus de 60 % lève
    ``SaisieSuspecte`` : le chauffeur vérifie puis renvoie avec ``confirmer=True``.
    """
    vehicule = _resoudre_vehicule(chauffeur, vehicule_id)
    return fuel_services.enregistrer_plein(
        vehicule=vehicule,
        chauffeur=chauffeur,
        date_plein=date_plein or timezone.localdate(),
        station=station,
        quantite_litres=quantite_litres,
        prix_unitaire=prix_unitaire,
        km_compteur=km_compteur,
        numero_ticket=numero_ticket,
        confirmer_alerte_saisie=confirmer,
    )


def pleins_du_chauffeur(chauffeur: Chauffeur, *, limite: int = 20) -> QuerySet[Plein]:
    return (
        Plein.objects.filter(chauffeur=chauffeur)
        .select_related("vehicule")
        .order_by("-date_plein", "-pk")[:limite]
    )


# --- check-list et incidents ---


def enregistrer_checklist(chauffeur: Chauffeur, pk: int, *, resultats: list[dict], remarque: str = ""):
    mission = mission_du_chauffeur(chauffeur, pk)
    return garage_terrain.enregistrer_checklist(
        chauffeur=chauffeur, mission=mission, resultats=resultats, remarque=remarque
    )


def declarer_incident(
    chauffeur: Chauffeur,
    *,
    type_incident: str,
    gravite: str,
    description: str,
    lieu: str = "",
    mission_id: int | None = None,
    vehicule_id: int | None = None,
) -> Incident:
    """Signale une panne ou un incident ; sans mission, sur le camion courant du chauffeur."""
    mission = mission_du_chauffeur(chauffeur, mission_id) if mission_id else None
    vehicule = None if mission else _resoudre_vehicule(chauffeur, vehicule_id)
    return garage_terrain.declarer_incident(
        chauffeur=chauffeur,
        type_incident=type_incident,
        gravite=gravite,
        description=description,
        lieu=lieu,
        mission=mission,
        vehicule=vehicule,
    )


def incidents_du_chauffeur(chauffeur: Chauffeur, *, limite: int = 20) -> QuerySet[Incident]:
    return Incident.objects.filter(chauffeur=chauffeur).select_related("vehicule").order_by("-created_at", "-pk")[:limite]


# --- tableau de bord du chauffeur (cahier-des-charges.md:238-239) ---


def tableau(chauffeur: Chauffeur, *, aujourd_hui: date | None = None) -> dict:
    """Course du jour, km parcourus, consommation, état du véhicule, prochaine mission."""
    aujourd_hui = aujourd_hui or timezone.localdate()
    missions = missions_services.missions_queryset().filter(chauffeur=chauffeur)
    en_cours = missions.filter(statut__in=STATUTS_EN_COURS).order_by("-date_depart", "-pk").first()
    a_venir = list(
        missions.filter(statut=StatutMission.AFFECTEE).order_by("date_depart_prevue", "pk")[:5]
    )
    debut_mois = aujourd_hui.replace(day=1)
    livrees = missions.filter(
        statut__in=(StatutMission.LIVREE, StatutMission.CLOTUREE),
        date_livraison__date__gte=debut_mois,
        km_depart__isnull=False,
        km_arrivee__isnull=False,
    ).values_list("km_depart", "km_arrivee")
    km_mois = sum(arrivee - depart for depart, arrivee in livrees if arrivee > depart)
    vehicule = vehicule_courant(chauffeur)
    return {
        "chauffeur": chauffeur,
        "mission_du_jour": en_cours or (a_venir[0] if a_venir else None),
        "en_cours": en_cours is not None,
        "prochaines": a_venir,
        "vehicule": vehicule,
        "km_mois": km_mois,
        "consommation": fuel_services.consommation_moyenne(chauffeur=chauffeur),
    }
```

À lire :

1. **`missions_du_chauffeur`**, **`mission_du_chauffeur`** : ne renvoient **que** les missions du chauffeur ;
   une autre mission lève `MissionIntrouvable`.
2. **`actions_possibles`** : ce que le chauffeur peut faire selon le statut (démarrer, récupérer, livrer).
3. **`demarrer`**, **`confirmer_recuperation`**, **`livrer`** : délèguent à `missions.services` après avoir
   contrôlé que la mission est bien à lui.
4. **`vehicule_courant`**, **`_vehicules_autorises`**, **`saisir_plein`** : un plein n'est accepté que sur *son*
   camion (mission en cours ou à venir, ou camion habituel).
5. **`enregistrer_checklist`**, **`declarer_incident`** : délèguent à `garage.terrain`.
6. **`tableau`** : les chiffres de l'accueil.

#### `apps/mobile_api/permissions.py`

*18 lignes*

```python
from rest_framework.permissions import BasePermission

from apps.accounts.models import Role
from apps.drivers import services as drivers_services


class EstChauffeur(BasePermission):
    """Compte de rôle CHAUFFEUR rattaché à une fiche chauffeur (architecture.md:435)."""

    message = "Cette ressource est réservée aux chauffeurs."

    def has_permission(self, request, view):
        utilisateur = request.user
        if not (utilisateur and utilisateur.is_authenticated):
            return False
        if utilisateur.role_effectif != Role.CHAUFFEUR:
            return False
        return drivers_services.chauffeur_de(utilisateur) is not None
```

#### `apps/mobile_api/serializers.py`

*113 lignes* — Représentation JSON de l'espace chauffeur.

```python
"""Représentation JSON de l'espace chauffeur.

Le chauffeur ne voit ni le prix convenu (donnée commerciale) ni les codes secrets de la mission :
ce sont l'expéditeur et le destinataire qui les détiennent, le chauffeur ne fait que les saisir.
"""

from rest_framework import serializers

from apps.fuel.models import Plein
from apps.garage.models import GraviteIncident, Incident, TypeIncident
from apps.missions.models import Mission

from . import services


class MissionMobileSerializer(serializers.ModelSerializer):
    client = serializers.CharField(source="client.raison_sociale")
    vehicule = serializers.CharField(source="vehicule.immatriculation", default=None)
    statut_libelle = serializers.CharField(source="get_statut_display")
    checklist_faite = serializers.SerializerMethodField()
    actions = serializers.SerializerMethodField()

    class Meta:
        model = Mission
        fields = (
            "id", "numero", "client", "lieu_chargement", "lieu_livraison", "nature_marchandise",
            "poids_t", "date_depart_prevue", "statut", "statut_libelle", "vehicule", "km_depart",
            "km_arrivee", "checklist_faite", "actions",
        )
        read_only_fields = fields

    def get_checklist_faite(self, mission) -> bool:
        return services.checklist_faite(mission)

    def get_actions(self, mission) -> dict:
        return services.actions_possibles(mission)


class CodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=12, help_text="Code saisi ou lu sur le QR de l'expéditeur.")


class LivraisonSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=12, help_text="Code du destinataire.")
    km_arrivee = serializers.IntegerField(min_value=0, help_text="Compteur à l'arrivée.")


class PleinEntreeSerializer(serializers.Serializer):
    station = serializers.CharField(max_length=100)
    quantite_litres = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=0)
    prix_unitaire = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    km_compteur = serializers.IntegerField(min_value=0)
    numero_ticket = serializers.CharField(max_length=50)
    date_plein = serializers.DateField(required=False, help_text="Aujourd'hui par défaut.")
    vehicule = serializers.IntegerField(required=False, help_text="Camion courant par défaut.")
    confirmer = serializers.BooleanField(
        required=False, default=False,
        help_text="À vrai pour confirmer un plein dont l'écart dépasse 60 %.",
    )


class PleinSerializer(serializers.ModelSerializer):
    vehicule = serializers.CharField(source="vehicule.immatriculation")

    class Meta:
        model = Plein
        fields = (
            "id", "date_plein", "vehicule", "station", "quantite_litres", "prix_unitaire",
            "km_compteur", "consommation", "ecart_pct", "niveau_alerte", "anomalie",
        )
        read_only_fields = fields


class PointChecklistSerializer(serializers.Serializer):
    code = serializers.CharField()
    ok = serializers.BooleanField()
    remarque = serializers.CharField(required=False, allow_blank=True, default="")


class ChecklistEntreeSerializer(serializers.Serializer):
    points = PointChecklistSerializer(many=True)
    remarque = serializers.CharField(required=False, allow_blank=True, default="")


class ChecklistSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nb_anomalies = serializers.IntegerField()
    points = serializers.ListField(child=serializers.DictField())
    remarque = serializers.CharField()


class IncidentEntreeSerializer(serializers.Serializer):
    type_incident = serializers.ChoiceField(choices=TypeIncident.choices)
    gravite = serializers.ChoiceField(choices=GraviteIncident.choices)
    description = serializers.CharField()
    lieu = serializers.CharField(required=False, allow_blank=True, default="")
    mission = serializers.IntegerField(required=False, help_text="Mission concernée (son camion est repris).")
    vehicule = serializers.IntegerField(required=False, help_text="Camion concerné, sans mission.")


class IncidentSerializer(serializers.ModelSerializer):
    vehicule = serializers.CharField(source="vehicule.immatriculation")
    type_libelle = serializers.CharField(source="get_type_incident_display")
    gravite_libelle = serializers.CharField(source="get_gravite_display")
    statut_libelle = serializers.CharField(source="get_statut_display")

    class Meta:
        model = Incident
        fields = (
            "id", "vehicule", "type_incident", "type_libelle", "gravite", "gravite_libelle",
            "description", "lieu", "statut", "statut_libelle", "created_at",
        )
        read_only_fields = fields
```

`permissions.py` et `serializers.py` servent surtout à l'**API mobile** du chapitre 28 ; ils sont écrits ici parce
qu'ils appartiennent à la même couche.

#### `apps/mobile_api/apps.py`

*7 lignes*

```python
from django.apps import AppConfig


class MobileApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.mobile_api'
    label = 'mobile_api'
```

## Étape 3 — Formulaires, vues, adresses de l'espace mobile

#### `apps/mobile_api/forms.py`

*106 lignes* — Formulaires de l'espace mobile du chauffeur (grands champs tactiles).

```python
"""Formulaires de l'espace mobile du chauffeur (grands champs tactiles)."""

from django import forms
from django.utils import timezone

from apps.garage.models import POINTS_CHECKLIST, GraviteIncident, TypeIncident

CHAMP_TACTILE = (
    "block w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-base text-slate-900 "
    "shadow-sm placeholder:text-slate-400 focus:border-marque-600 focus:outline-none "
    "focus:ring-2 focus:ring-marque-600/30"
)


class StyleTactileMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in self.fields.values():
            champ.widget.attrs.setdefault("class", CHAMP_TACTILE)


class CodeForm(StyleTactileMixin, forms.Form):
    code = forms.CharField(
        label="Code", max_length=12,
        widget=forms.TextInput(attrs={"autocomplete": "off", "autocapitalize": "characters",
                                      "inputmode": "text", "class": CHAMP_TACTILE + " text-center font-mono text-2xl tracking-widest"}),
    )


class LivraisonForm(CodeForm):
    km_arrivee = forms.IntegerField(
        label="Kilométrage à l'arrivée", min_value=0,
        widget=forms.NumberInput(attrs={"inputmode": "numeric"}),
    )


class PleinChauffeurForm(StyleTactileMixin, forms.Form):
    station = forms.CharField(label="Station", max_length=100)
    quantite_litres = forms.DecimalField(
        label="Litres", min_value=0, decimal_places=2, max_digits=8,
        widget=forms.NumberInput(attrs={"inputmode": "decimal", "step": "0.01"}),
    )
    prix_unitaire = forms.DecimalField(
        label="Prix du litre (FCFA)", min_value=0, decimal_places=2, max_digits=10,
        widget=forms.NumberInput(attrs={"inputmode": "decimal", "step": "0.01"}),
    )
    km_compteur = forms.IntegerField(
        label="Kilométrage du compteur", min_value=0, widget=forms.NumberInput(attrs={"inputmode": "numeric"})
    )
    numero_ticket = forms.CharField(label="N° du ticket ou du reçu", max_length=50)
    date_plein = forms.DateField(label="Date", widget=forms.DateInput(attrs={"type": "date"}))

    def clean_date_plein(self):
        jour = self.cleaned_data["date_plein"]
        if jour > timezone.localdate():
            raise forms.ValidationError("La date du plein ne peut pas être dans le futur.")
        return jour


class IncidentChauffeurForm(StyleTactileMixin, forms.Form):
    type_incident = forms.ChoiceField(label="Nature", choices=TypeIncident.choices)
    gravite = forms.ChoiceField(label="Gravité", choices=GraviteIncident.choices)
    description = forms.CharField(label="Ce qui s'est passé", widget=forms.Textarea(attrs={"rows": 4}))
    lieu = forms.CharField(label="Où êtes-vous ?", max_length=200, required=False)
    mission = forms.TypedChoiceField(label="Mission concernée", required=False, coerce=int, empty_value=None)

    def __init__(self, *args, missions=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["mission"].choices = [("", "Aucune")] + [
            (m.pk, f"{m.numero} : {m.lieu_chargement} → {m.lieu_livraison}") for m in missions
        ]


class ChecklistForm(forms.Form):
    """Un choix OK / KO par point, et une remarque (obligatoire si KO, contrôlé par le service)."""

    remarque = forms.CharField(label="Remarque générale", required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["remarque"].widget.attrs["class"] = CHAMP_TACTILE
        for code, libelle in POINTS_CHECKLIST:
            self.fields[f"ok_{code}"] = forms.ChoiceField(
                label=libelle, choices=[("1", "OK"), ("0", "KO")], widget=forms.RadioSelect
            )
            self.fields[f"remarque_{code}"] = forms.CharField(
                label="Problème constaté", required=False,
                widget=forms.TextInput(attrs={"class": CHAMP_TACTILE, "placeholder": "Décrivez le problème"}),
            )

    def points(self):
        """Les 8 points, pour l'affichage : (code, libellé, champ OK/KO, champ remarque)."""
        return [
            (code, libelle, self[f"ok_{code}"], self[f"remarque_{code}"])
            for code, libelle in POINTS_CHECKLIST
        ]

    def resultats(self) -> list[dict]:
        return [
            {
                "code": code,
                "ok": self.cleaned_data[f"ok_{code}"] == "1",
                "remarque": self.cleaned_data.get(f"remarque_{code}", ""),
            }
            for code, _libelle in POINTS_CHECKLIST
        ]
```

#### `apps/mobile_api/views_web.py`

*340 lignes* — Espace mobile du chauffeur (PWA) : pages tactiles servies sous ``/chauffeur/``.

```python
"""Espace mobile du chauffeur (PWA) : pages tactiles servies sous ``/chauffeur/``.

Comme le reste de l'interface, aucune règle métier ici : chaque vue identifie le chauffeur du
compte connecté et délègue à ``services.py`` (les mêmes que l'API mobile). Session de 15 minutes
d'inactivité pour ce rôle (cahier-des-charges.md:285). L'application est installable
(manifeste + service worker) ; la saisie hors ligne n'est pas gérée : une page « hors connexion »
s'affiche à la place quand le réseau manque.
"""

import json

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.mixins import RoleRequiredMixin
from apps.accounts.models import Role
from apps.core.formats import nombre, pourcentage_signe
from apps.drivers import services as drivers_services
from apps.fuel.exceptions import CarburantError, SaisieSuspecte
from apps.fuel.models import NiveauAlerte
from apps.garage.exceptions import GarageError
from apps.missions.exceptions import MissionError

from . import services
from .exceptions import MissionIntrouvable, MobileError
from .forms import ChecklistForm, CodeForm, IncidentChauffeurForm, LivraisonForm, PleinChauffeurForm

ERREURS = (MissionError, CarburantError, GarageError, MobileError)


class ChauffeurRequisMixin(RoleRequiredMixin):
    """Réservé aux comptes CHAUFFEUR rattachés à une fiche chauffeur."""

    roles = frozenset({Role.CHAUFFEUR})

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["navigation"] = [
            ("accueil", reverse("chauffeur:accueil"), "fa-house", "Accueil"),
            ("missions", reverse("chauffeur:missions"), "fa-truck-fast", "Missions"),
            ("plein", reverse("chauffeur:plein"), "fa-gas-pump", "Plein"),
            ("incident", reverse("chauffeur:incident"), "fa-triangle-exclamation", "Panne"),
        ]
        return contexte

    def dispatch(self, request, *args, **kwargs):
        utilisateur = request.user
        if utilisateur.is_authenticated and utilisateur.role_effectif in self.roles:
            self.chauffeur = drivers_services.chauffeur_de(utilisateur)
            if self.chauffeur is None:
                raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


def _mission_ou_404(chauffeur, pk):
    try:
        return services.mission_du_chauffeur(chauffeur, pk)
    except MissionIntrouvable as erreur:
        raise Http404 from erreur


class AccueilView(ChauffeurRequisMixin, TemplateView):
    template_name = "mobile/accueil.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        tableau = services.tableau(self.chauffeur)
        mission = tableau["mission_du_jour"]
        contexte.update(
            tableau,
            actions=services.actions_possibles(mission) if mission else {},
            nav="accueil",
        )
        return contexte


class MissionsView(ChauffeurRequisMixin, TemplateView):
    template_name = "mobile/missions.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(missions=services.missions_du_chauffeur(self.chauffeur), nav="missions")
        return contexte


class MissionView(ChauffeurRequisMixin, TemplateView):
    template_name = "mobile/mission.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        mission = _mission_ou_404(self.chauffeur, self.kwargs["pk"])
        actions = services.actions_possibles(mission)
        contexte.update(
            mission=mission,
            actions=actions,
            checklist_faite=services.checklist_faite(mission),
            form_recuperation=CodeForm() if actions["recuperation"] else None,
            form_livraison=LivraisonForm() if actions["livraison"] else None,
            nav="missions",
        )
        return contexte


class _ActionMission(ChauffeurRequisMixin, View):
    """Action en POST sur une mission du chauffeur, puis retour à sa fiche."""

    http_method_names = ["post"]
    form_class = None

    def executer(self, pk, donnees):
        raise NotImplementedError  # pragma: no cover

    def message(self, mission):
        raise NotImplementedError  # pragma: no cover

    def post(self, request, pk):
        donnees = {}
        if self.form_class is not None:
            form = self.form_class(request.POST)
            if not form.is_valid():
                for erreurs in form.errors.values():
                    for erreur in erreurs:
                        messages.error(request, erreur)
                return redirect("chauffeur:mission", pk=pk)
            donnees = form.cleaned_data
        try:
            mission = self.executer(pk, donnees)
        except MissionIntrouvable as erreur:
            raise Http404 from erreur
        except ERREURS as erreur:
            messages.error(request, str(erreur))
        else:
            messages.success(request, self.message(mission))
        return redirect("chauffeur:mission", pk=pk)


class DemarrerView(_ActionMission):
    def executer(self, pk, donnees):
        return services.demarrer(self.chauffeur, pk)

    def message(self, mission):
        return "C'est parti ! Bonne route."


class RecuperationView(_ActionMission):
    form_class = CodeForm

    def executer(self, pk, donnees):
        return services.confirmer_recuperation(self.chauffeur, pk, code=donnees["code"])

    def message(self, mission):
        return "Colis récupéré. Vous pouvez prendre la route vers la livraison."


class LivraisonView(_ActionMission):
    form_class = LivraisonForm

    def executer(self, pk, donnees):
        return services.livrer(self.chauffeur, pk, code=donnees["code"], km_arrivee=donnees["km_arrivee"])

    def message(self, mission):
        return "Livraison confirmée. Merci !"


class ChecklistView(ChauffeurRequisMixin, TemplateView):
    template_name = "mobile/checklist.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            mission=_mission_ou_404(self.chauffeur, self.kwargs["pk"]),
            form=kwargs.get("form") or ChecklistForm(),
            nav="missions",
        )
        return contexte

    def post(self, request, pk):
        form = ChecklistForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        try:
            checklist = services.enregistrer_checklist(
                self.chauffeur, pk, resultats=form.resultats(), remarque=form.cleaned_data["remarque"]
            )
        except MissionIntrouvable as erreur:
            raise Http404 from erreur
        except ERREURS as erreur:
            form.add_error(None, str(erreur))
            return self.render_to_response(self.get_context_data(form=form))
        if checklist.nb_anomalies:
            messages.warning(
                request,
                f"Check-list enregistrée : {checklist.nb_anomalies} point(s) KO. "
                "Le Parc Auto est prévenu ; vous pouvez partir.",
            )
        else:
            messages.success(request, "Check-list enregistrée : tout est OK.")
        return redirect("chauffeur:mission", pk=pk)


class PleinView(ChauffeurRequisMixin, TemplateView):
    """Saisie d'un plein ; un écart de plus de 60 % demande une confirmation explicite."""

    template_name = "mobile/plein.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            form=kwargs.get("form") or PleinChauffeurForm(initial={"date_plein": timezone.localdate()}),
            saisie_suspecte=kwargs.get("saisie_suspecte"),
            vehicule=services.vehicule_courant(self.chauffeur),
            derniers=services.pleins_du_chauffeur(self.chauffeur, limite=5),
            nav="plein",
        )
        return contexte

    def post(self, request):
        form = PleinChauffeurForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        try:
            plein = services.saisir_plein(
                self.chauffeur,
                confirmer=request.POST.get("confirmer") == "1",
                **form.cleaned_data,
            )
        except SaisieSuspecte as avertissement:
            return self.render_to_response(self.get_context_data(form=form, saisie_suspecte=avertissement))
        except ERREURS as erreur:
            form.add_error(None, str(erreur))
            return self.render_to_response(self.get_context_data(form=form))
        if plein.consommation is None:
            messages.success(request, "Premier plein enregistré : la consommation sera calculée au suivant.")
        else:
            messages.success(request, f"Plein enregistré : {nombre(plein.consommation, 1)} L/100 km.")
        if plein.niveau_alerte != NiveauAlerte.AUCUNE:
            messages.warning(
                request,
                f"Surconsommation : {pourcentage_signe(plein.ecart_pct)} % par rapport à votre moyenne récente.",
            )
        return redirect("chauffeur:accueil")


class IncidentView(ChauffeurRequisMixin, TemplateView):
    template_name = "mobile/incident.html"

    def _missions(self):
        return list(services.missions_du_chauffeur(self.chauffeur))

    def _formulaire_vide(self):
        mission = self.request.GET.get("mission", "")
        return IncidentChauffeurForm(
            missions=self._missions(), initial={"mission": mission} if mission.isdigit() else {}
        )

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            form=kwargs.get("form") or self._formulaire_vide(),
            derniers=services.incidents_du_chauffeur(self.chauffeur, limite=5),
            nav="incident",
        )
        return contexte

    def post(self, request):
        form = IncidentChauffeurForm(request.POST, missions=self._missions())
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        donnees = form.cleaned_data
        try:
            services.declarer_incident(
                self.chauffeur,
                type_incident=donnees["type_incident"],
                gravite=donnees["gravite"],
                description=donnees["description"],
                lieu=donnees["lieu"],
                mission_id=donnees["mission"],
            )
        except MissionIntrouvable as erreur:
            raise Http404 from erreur
        except ERREURS as erreur:
            form.add_error(None, str(erreur))
            return self.render_to_response(self.get_context_data(form=form))
        messages.success(request, "Incident signalé : le Parc Auto et la Direction sont prévenus.")
        return redirect("chauffeur:accueil")


# --- application installable (PWA) ---


class ManifesteView(View):
    """Manifeste de l'application : nom, couleurs, icônes, page de démarrage."""

    def get(self, request):
        manifeste = {
            "name": "DEN Source Group : espace chauffeur",
            "short_name": "DEN Chauffeur",
            "description": "Missions, plein de carburant, check-list et signalement d'incident.",
            "lang": "fr",
            "start_url": reverse("chauffeur:accueil"),
            "scope": reverse("chauffeur:accueil"),
            "display": "standalone",
            "orientation": "portrait",
            "background_color": "#ffffff",
            "theme_color": "#8b0319",
            "icons": [
                {"src": static("img/icon-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "any"},
                {"src": static("img/icon-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any"},
            ],
        }
        return HttpResponse(json.dumps(manifeste), content_type="application/manifest+json")


class ServiceWorkerView(View):
    """Service worker : ne met en cache que la page « hors connexion » et les icônes.

    Les pages du chauffeur (missions, codes...) ne sont jamais mises en cache : elles contiennent
    des données privées et doivent toujours être à jour.
    """

    def get(self, request):
        reponse = render(
            request, "mobile/sw.js",
            {"hors_ligne": reverse("chauffeur:hors_ligne"), "icone": static("img/icon-192.png")},
            content_type="application/javascript",
        )
        reponse["Service-Worker-Allowed"] = reverse("chauffeur:accueil")
        reponse["Cache-Control"] = "no-cache"
        return reponse


class HorsLigneView(TemplateView):
    template_name = "mobile/hors_ligne.html"
```

Repérez `ChauffeurRequisMixin` : il exige un compte **CHAUFFEUR rattaché à une fiche chauffeur** (`chauffeur_de`),
sinon 403. Toutes les vues s'appuient dessus.

#### `apps/mobile_api/urls_web.py`

*22 lignes* — Écrans mobiles du chauffeur, montés sous ``/chauffeur/`` par ``config/urls.py``.

```python
"""Écrans mobiles du chauffeur, montés sous ``/chauffeur/`` par ``config/urls.py``."""

from django.urls import path

from . import views_web as v

app_name = "chauffeur"

urlpatterns = [
    path("", v.AccueilView.as_view(), name="accueil"),
    path("missions/", v.MissionsView.as_view(), name="missions"),
    path("missions/<int:pk>/", v.MissionView.as_view(), name="mission"),
    path("missions/<int:pk>/demarrer/", v.DemarrerView.as_view(), name="demarrer"),
    path("missions/<int:pk>/recuperation/", v.RecuperationView.as_view(), name="recuperation"),
    path("missions/<int:pk>/livraison/", v.LivraisonView.as_view(), name="livraison"),
    path("missions/<int:pk>/checklist/", v.ChecklistView.as_view(), name="checklist"),
    path("plein/", v.PleinView.as_view(), name="plein"),
    path("incident/", v.IncidentView.as_view(), name="incident"),
    path("manifest.webmanifest", v.ManifesteView.as_view(), name="manifeste"),
    path("sw.js", v.ServiceWorkerView.as_view(), name="sw"),
    path("hors-ligne/", v.HorsLigneView.as_view(), name="hors_ligne"),
]
```

#### `apps/mobile_api/views.py`

*151 lignes* — API mobile du chauffeur : ``/api/v1/mobile/``.

```python
"""API mobile du chauffeur : ``/api/v1/mobile/``.

Aucune règle métier ici : chaque vue identifie le chauffeur du compte, valide les données reçues
et délègue à ``services.py`` (missions, plein, check-list, incident). Les erreurs métier sont
traduites en HTTP par ``apps.api.exceptions.gestionnaire_erreurs``.
"""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.drivers import services as drivers_services

from . import services
from .permissions import EstChauffeur
from .serializers import (
    ChecklistEntreeSerializer,
    ChecklistSerializer,
    CodeSerializer,
    IncidentEntreeSerializer,
    IncidentSerializer,
    LivraisonSerializer,
    MissionMobileSerializer,
    PleinEntreeSerializer,
    PleinSerializer,
)

TAG = ["mobile"]


class ChauffeurAPIView(APIView):
    """Base : réservée aux chauffeurs ; ``self.chauffeur`` est la fiche du compte connecté."""

    permission_classes = [IsAuthenticated, EstChauffeur]

    @property
    def chauffeur(self):
        return drivers_services.chauffeur_de(self.request.user)


class MissionsView(ChauffeurAPIView):
    @extend_schema(tags=TAG, summary="Mes missions (à faire, en cours, livrées cette semaine)",
                   responses=MissionMobileSerializer(many=True))
    def get(self, request):
        missions = services.missions_du_chauffeur(self.chauffeur)
        return Response(MissionMobileSerializer(missions, many=True).data)


class MissionView(ChauffeurAPIView):
    @extend_schema(tags=TAG, summary="Détail d'une de mes missions", responses=MissionMobileSerializer)
    def get(self, request, pk):
        return Response(MissionMobileSerializer(services.mission_du_chauffeur(self.chauffeur, pk)).data)


class DemarrerView(ChauffeurAPIView):
    @extend_schema(tags=TAG, summary="Démarrer la mission (Affectée → En cours : départ)",
                   request=None, responses=MissionMobileSerializer)
    def post(self, request, pk):
        return Response(MissionMobileSerializer(services.demarrer(self.chauffeur, pk)).data)


class RecuperationView(ChauffeurAPIView):
    @extend_schema(tags=TAG, summary="Confirmer la récupération du colis (code de l'expéditeur)",
                   request=CodeSerializer, responses=MissionMobileSerializer)
    def post(self, request, pk):
        donnees = CodeSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        mission = services.confirmer_recuperation(self.chauffeur, pk, code=donnees.validated_data["code"])
        return Response(MissionMobileSerializer(mission).data)


class LivraisonView(ChauffeurAPIView):
    @extend_schema(tags=TAG, summary="Confirmer la livraison (code du destinataire et compteur)",
                   request=LivraisonSerializer, responses=MissionMobileSerializer)
    def post(self, request, pk):
        donnees = LivraisonSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        mission = services.livrer(self.chauffeur, pk, **donnees.validated_data)
        return Response(MissionMobileSerializer(mission).data)


class ChecklistView(ChauffeurAPIView):
    @extend_schema(tags=TAG, summary="Remplir la check-list du véhicule avant le départ",
                   request=ChecklistEntreeSerializer, responses={201: ChecklistSerializer})
    def post(self, request, pk):
        donnees = ChecklistEntreeSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        checklist = services.enregistrer_checklist(
            self.chauffeur, pk,
            resultats=[dict(p) for p in donnees.validated_data["points"]],
            remarque=donnees.validated_data["remarque"],
        )
        return Response(ChecklistSerializer(checklist).data, status=status.HTTP_201_CREATED)


class PleinsView(ChauffeurAPIView):
    @extend_schema(tags=TAG, summary="Mes derniers pleins", responses=PleinSerializer(many=True))
    def get(self, request):
        return Response(PleinSerializer(services.pleins_du_chauffeur(self.chauffeur), many=True).data)

    @extend_schema(
        tags=TAG,
        summary="Saisir un plein de carburant",
        description=(
            "Un écart de plus de 60 % avec la moyenne renvoie 409 (`saisie_suspecte`) : vérifiez "
            "litres et kilométrage, puis renvoyez la même demande avec `confirmer=true`."
        ),
        request=PleinEntreeSerializer, responses={201: PleinSerializer},
    )
    def post(self, request):
        donnees = PleinEntreeSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        valeurs = dict(donnees.validated_data)
        plein = services.saisir_plein(
            self.chauffeur,
            station=valeurs["station"],
            quantite_litres=valeurs["quantite_litres"],
            prix_unitaire=valeurs["prix_unitaire"],
            km_compteur=valeurs["km_compteur"],
            numero_ticket=valeurs["numero_ticket"],
            date_plein=valeurs.get("date_plein"),
            vehicule_id=valeurs.get("vehicule"),
            confirmer=valeurs["confirmer"],
        )
        return Response(PleinSerializer(plein).data, status=status.HTTP_201_CREATED)


class IncidentsView(ChauffeurAPIView):
    @extend_schema(tags=TAG, summary="Mes incidents signalés", responses=IncidentSerializer(many=True))
    def get(self, request):
        return Response(IncidentSerializer(services.incidents_du_chauffeur(self.chauffeur), many=True).data)

    @extend_schema(tags=TAG, summary="Signaler une panne ou un incident",
                   description="Prévient le Parc Auto et la Direction ; aucune action automatique sur le camion.",
                   request=IncidentEntreeSerializer, responses={201: IncidentSerializer})
    def post(self, request):
        donnees = IncidentEntreeSerializer(data=request.data)
        donnees.is_valid(raise_exception=True)
        valeurs = dict(donnees.validated_data)
        incident = services.declarer_incident(
            self.chauffeur,
            type_incident=valeurs["type_incident"],
            gravite=valeurs["gravite"],
            description=valeurs["description"],
            lieu=valeurs["lieu"],
            mission_id=valeurs.get("mission"),
            vehicule_id=valeurs.get("vehicule"),
        )
        return Response(IncidentSerializer(incident).data, status=status.HTTP_201_CREATED)
```

#### `apps/mobile_api/urls.py`

*18 lignes* — Routes de l'API mobile : montées sous ``/api/v1/mobile/`` par ``apps.api.urls``.

```python
"""Routes de l'API mobile : montées sous ``/api/v1/mobile/`` par ``apps.api.urls``."""

from django.urls import path

from . import views

app_name = "mobile"

urlpatterns = [
    path("missions/", views.MissionsView.as_view(), name="missions"),
    path("missions/<int:pk>/", views.MissionView.as_view(), name="mission"),
    path("missions/<int:pk>/demarrer/", views.DemarrerView.as_view(), name="demarrer"),
    path("missions/<int:pk>/recuperation/", views.RecuperationView.as_view(), name="recuperation"),
    path("missions/<int:pk>/livraison/", views.LivraisonView.as_view(), name="livraison"),
    path("missions/<int:pk>/checklist/", views.ChecklistView.as_view(), name="checklist"),
    path("pleins/", views.PleinsView.as_view(), name="pleins"),
    path("incidents/", views.IncidentsView.as_view(), name="incidents"),
]
```

(Les deux derniers fichiers sont l'**API mobile** ; ils seront montés au chapitre 28.)

## Étape 4 — Gabarits, JavaScript et service worker

#### `apps/mobile_api/templates/mobile/base.html`

*48 lignes*

```django
{% load static %}<!DOCTYPE html>
<html lang="fr" class="h-full bg-slate-100">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#8b0319">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <title>{% block titre %}Espace chauffeur{% endblock %} · DEN Source</title>
  <link rel="manifest" href="{% url 'chauffeur:manifeste' %}">
  <link rel="icon" type="image/png" href="{% static 'img/favicon.png' %}">
  <link rel="apple-touch-icon" href="{% static 'img/icon-192.png' %}">
  {% include "components/_assets.html" %}
  <script src="{% static 'js/scanner.js' %}"></script>
</head>
<body class="min-h-full pb-28 text-slate-900 antialiased">
  <header class="sticky top-0 z-20 bg-marque-800 text-white shadow">
    <div class="mx-auto flex max-w-lg items-center justify-between gap-3 px-4 py-3">
      <a href="{% url 'chauffeur:accueil' %}" class="flex items-center gap-3 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-400">
        <span class="flex h-10 w-12 items-center justify-center rounded-lg bg-white p-1"><img src="{% static 'img/logo-emblem.jpg' %}" alt="" class="h-full w-auto"></span>
        <span class="leading-tight"><span class="block text-sm font-extrabold tracking-wide">DEN Chauffeur</span><span class="block text-xs text-marque-100">{{ user.first_name|default:user.username }}</span></span>
      </a>
      <form method="post" action="{% url 'accounts:logout' %}">{% csrf_token %}
        <button type="submit" class="rounded-lg border border-white/30 px-3 py-2 text-sm font-medium hover:bg-white/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-400"><i class="fa-solid fa-right-from-bracket mr-1" aria-hidden="true"></i>Sortir</button>
      </form>
    </div>
  </header>

  <main class="mx-auto max-w-lg px-4 py-4">
    {% include "components/_messages.html" %}
    {% block contenu %}{% endblock %}
  </main>

  <nav aria-label="Navigation de l'espace chauffeur" class="fixed inset-x-0 bottom-0 z-20 border-t border-slate-200 bg-white pb-[env(safe-area-inset-bottom)] shadow-[0_-2px_8px_rgba(0,0,0,0.06)]">
    <ul class="mx-auto grid max-w-lg grid-cols-4">
      {% for cle, url, icone, libelle in navigation %}
        <li>
          <a href="{{ url }}" {% if nav == cle %}aria-current="page"{% endif %}
             class="flex flex-col items-center gap-1 px-2 py-3 text-xs font-semibold focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600 {% if nav == cle %}text-marque-700{% else %}text-slate-600{% endif %}">
            <i class="fa-solid {{ icone }} text-xl" aria-hidden="true"></i>{{ libelle }}
          </a>
        </li>
      {% endfor %}
    </ul>
  </nav>

  <script src="{% static 'js/sw-register.js' %}" data-sw="{% url 'chauffeur:sw' %}" defer></script>
</body>
</html>
```

`base.html` de l'espace mobile : la barre de navigation du bas (Accueil, Missions, Plein, Panne), le manifeste,
le service worker (enregistré par `sw-register.js`, **sans code en ligne**).

#### `apps/mobile_api/templates/mobile/accueil.html`

*47 lignes*

```django
{% extends "mobile/base.html" %}
{% load ui %}
{% block titre %}Accueil{% endblock %}

{% block contenu %}
<h1 class="text-xl font-bold text-slate-900">Bonjour {{ user.first_name|default:user.username }}</h1>
<p class="text-sm text-slate-600">{% now "l j F" %}</p>

<section class="mt-4" aria-labelledby="titre-course">
  <h2 id="titre-course" class="text-sm font-semibold uppercase tracking-wide text-slate-600">{% if en_cours %}Course en cours{% else %}Prochaine mission{% endif %}</h2>
  {% if mission_du_jour %}
    <div class="mt-2">{% include "mobile/_carte_mission.html" with mission=mission_du_jour %}</div>
    {% if actions.checklist %}
      <a href="{% url 'chauffeur:checklist' mission_du_jour.pk %}" class="mt-3 flex items-center justify-center gap-2 rounded-2xl bg-accent-500 px-4 py-4 text-lg font-bold text-slate-900 shadow active:bg-accent-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-700"><i class="fa-solid fa-list-check" aria-hidden="true"></i> Faire la check-list du camion</a>
    {% endif %}
  {% else %}
    <p class="mt-2 rounded-2xl border border-dashed border-slate-300 bg-white p-5 text-center text-slate-700">Aucune mission ne vous est affectée pour le moment.</p>
  {% endif %}
</section>

<div class="mt-5 grid grid-cols-2 gap-3">
  <a href="{% url 'chauffeur:plein' %}" class="flex flex-col items-center gap-2 rounded-2xl bg-marque-600 px-3 py-5 text-center font-bold text-white shadow active:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-800"><i class="fa-solid fa-gas-pump text-3xl" aria-hidden="true"></i>Saisir un plein</a>
  <a href="{% url 'chauffeur:incident' %}" class="flex flex-col items-center gap-2 rounded-2xl bg-slate-900 px-3 py-5 text-center font-bold text-white shadow active:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900"><i class="fa-solid fa-triangle-exclamation text-3xl" aria-hidden="true"></i>Signaler une panne</a>
</div>

<section class="mt-6" aria-labelledby="titre-chiffres">
  <h2 id="titre-chiffres" class="text-sm font-semibold uppercase tracking-wide text-slate-600">Mon activité</h2>
  <dl class="mt-2 grid grid-cols-2 gap-3">
    <div class="rounded-2xl border border-slate-200 bg-white p-4"><dt class="text-xs text-slate-600">Km ce mois-ci</dt><dd class="mt-1 text-2xl font-bold">{{ km_mois }}</dd></div>
    <div class="rounded-2xl border border-slate-200 bg-white p-4"><dt class="text-xs text-slate-600">Consommation</dt><dd class="mt-1 text-2xl font-bold">{% if consommation %}{{ consommation|floatformat:1 }}<span class="text-xs font-medium text-slate-600"> L/100 km</span>{% else %}<span class="text-base font-medium text-slate-600">Pas encore</span>{% endif %}</dd></div>
    <div class="col-span-2 rounded-2xl border border-slate-200 bg-white p-4"><dt class="text-xs text-slate-600">Mon camion</dt>
      <dd class="mt-1 font-bold">{% if vehicule %}{{ vehicule.immatriculation }} <span class="font-medium text-slate-600">· {{ vehicule.marque }} {{ vehicule.modele }}</span> {% badge vehicule.statut vehicule.get_statut_display %}<span class="mt-1 block text-sm font-medium text-slate-600">{{ vehicule.kilometrage }} km au compteur</span>{% else %}<span class="font-medium text-slate-600">Aucun camion affecté</span>{% endif %}</dd></div>
  </dl>
</section>

{% if prochaines and en_cours %}
  <section class="mt-6" aria-labelledby="titre-suite">
    <h2 id="titre-suite" class="text-sm font-semibold uppercase tracking-wide text-slate-600">À venir</h2>
    <div class="mt-2 space-y-3">{% for m in prochaines %}{% include "mobile/_carte_mission.html" with mission=m %}{% endfor %}</div>
  </section>
{% elif prochaines|length > 1 %}
  <section class="mt-6" aria-labelledby="titre-suite">
    <h2 id="titre-suite" class="text-sm font-semibold uppercase tracking-wide text-slate-600">Ensuite</h2>
    <div class="mt-2 space-y-3">{% for m in prochaines|slice:"1:" %}{% include "mobile/_carte_mission.html" with mission=m %}{% endfor %}</div>
  </section>
{% endif %}
{% endblock %}
```

#### `apps/mobile_api/templates/mobile/missions.html`

*14 lignes*

```django
{% extends "mobile/base.html" %}
{% block titre %}Mes missions{% endblock %}

{% block contenu %}
<h1 class="text-xl font-bold text-slate-900">Mes missions</h1>
<p class="text-sm text-slate-600">À faire, en cours, et livrées cette semaine.</p>
<div class="mt-4 space-y-3">
  {% for mission in missions %}
    {% include "mobile/_carte_mission.html" %}
  {% empty %}
    <p class="rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-center text-slate-700">Aucune mission pour le moment.</p>
  {% endfor %}
</div>
{% endblock %}
```

#### `apps/mobile_api/templates/mobile/_carte_mission.html`

*9 lignes*

```django
{% load ui %}
<a href="{% url 'chauffeur:mission' mission.pk %}" class="block rounded-2xl border border-slate-200 bg-white p-4 shadow-sm active:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
  <div class="flex items-start justify-between gap-2">
    <p class="text-sm font-semibold text-slate-600">{{ mission.numero }} · {{ mission.client.raison_sociale }}</p>
    {% badge mission.statut mission.get_statut_display %}
  </div>
  <p class="mt-2 text-lg font-bold leading-snug text-slate-900">{{ mission.lieu_chargement }} <i class="fa-solid fa-arrow-right mx-1 text-marque-600" aria-hidden="true"></i> {{ mission.lieu_livraison }}</p>
  <p class="mt-1 text-sm text-slate-700">{{ mission.nature_marchandise }} · {{ mission.poids_t|floatformat:"-2" }} t{% if mission.date_depart_prevue %} · départ le {{ mission.date_depart_prevue|date:"d/m" }}{% endif %}</p>
</a>
```

#### `apps/mobile_api/templates/mobile/mission.html`

*73 lignes*

```django
{% extends "mobile/base.html" %}
{% load ui %}
{% block titre %}Mission {{ mission.numero }}{% endblock %}

{% block contenu %}
<a href="{% url 'chauffeur:missions' %}" class="text-sm font-medium text-marque-700 underline-offset-2 hover:underline"><i class="fa-solid fa-chevron-left mr-1" aria-hidden="true"></i>Mes missions</a>

<div class="mt-2 flex items-start justify-between gap-2">
  <h1 class="text-xl font-bold text-slate-900">{{ mission.numero }}</h1>
  {% badge mission.statut mission.get_statut_display %}
</div>

<section class="mt-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm" aria-labelledby="titre-trajet">
  <h2 id="titre-trajet" class="sr-only">Trajet</h2>
  <p class="text-lg font-bold leading-snug">{{ mission.lieu_chargement }} <i class="fa-solid fa-arrow-right mx-1 text-marque-600" aria-hidden="true"></i> {{ mission.lieu_livraison }}</p>
  <dl class="mt-3 space-y-2 text-sm">
    <div class="flex justify-between gap-3"><dt class="text-slate-600">Client</dt><dd class="text-right font-medium">{{ mission.client.raison_sociale }}</dd></div>
    <div class="flex justify-between gap-3"><dt class="text-slate-600">Marchandise</dt><dd class="text-right font-medium">{{ mission.nature_marchandise }} · {{ mission.poids_t|floatformat:"-2" }} t</dd></div>
    {% if mission.date_depart_prevue %}<div class="flex justify-between gap-3"><dt class="text-slate-600">Départ prévu</dt><dd class="font-medium">{{ mission.date_depart_prevue|date:"l j F" }}</dd></div>{% endif %}
    {% if mission.vehicule %}<div class="flex justify-between gap-3"><dt class="text-slate-600">Camion</dt><dd class="font-medium">{{ mission.vehicule.immatriculation }}</dd></div>{% endif %}
    {% if mission.km_depart %}<div class="flex justify-between gap-3"><dt class="text-slate-600">Km au départ</dt><dd class="font-medium">{{ mission.km_depart }}</dd></div>{% endif %}
    {% if mission.km_arrivee %}<div class="flex justify-between gap-3"><dt class="text-slate-600">Km à l'arrivée</dt><dd class="font-medium">{{ mission.km_arrivee }}</dd></div>{% endif %}
  </dl>
</section>

{% if mission.statut == "AFFECTEE" %}
  <section class="mt-4 space-y-3" aria-labelledby="titre-depart">
    <h2 id="titre-depart" class="text-sm font-semibold uppercase tracking-wide text-slate-600">Avant le départ</h2>
    {% if actions.checklist %}
      <a href="{% url 'chauffeur:checklist' mission.pk %}" class="flex items-center justify-center gap-2 rounded-2xl bg-accent-500 px-4 py-4 text-lg font-bold text-slate-900 shadow active:bg-accent-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-700"><i class="fa-solid fa-list-check" aria-hidden="true"></i> Check-list du camion</a>
    {% elif checklist_faite %}
      <p class="rounded-2xl border border-emerald-300 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-900"><i class="fa-solid fa-circle-check mr-2" aria-hidden="true"></i>Check-list du camion faite.</p>
    {% endif %}
    <form method="post" action="{% url 'chauffeur:demarrer' mission.pk %}" data-confirm="Démarrer la mission maintenant ?">{% csrf_token %}
      <button type="submit" class="flex w-full items-center justify-center gap-2 rounded-2xl bg-emerald-700 px-4 py-4 text-lg font-bold text-white shadow active:bg-emerald-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-800"><i class="fa-solid fa-truck-fast" aria-hidden="true"></i> Démarrer la mission</button>
    </form>
  </section>
{% endif %}

{% if form_recuperation %}
  <section class="mt-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm" aria-labelledby="titre-recup">
    <h2 id="titre-recup" class="text-base font-bold">Récupération du colis</h2>
    <p class="mt-1 text-sm text-slate-700">L'expéditeur vous donne son code ou vous montre son QR : scannez-le ou saisissez-le.</p>
    <form method="post" action="{% url 'chauffeur:recuperation' mission.pk %}" class="mt-3 space-y-3" x-data="scannerCode('id_code')">{% csrf_token %}
      {% include "mobile/_scanner.html" %}
      {{ form_recuperation.code }}
      <button type="submit" class="w-full rounded-2xl bg-marque-600 px-4 py-4 text-lg font-bold text-white shadow active:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-800">Confirmer la récupération</button>
    </form>
  </section>
{% endif %}

{% if form_livraison %}
  <section class="mt-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm" aria-labelledby="titre-livraison">
    <h2 id="titre-livraison" class="text-base font-bold">Livraison</h2>
    <p class="mt-1 text-sm text-slate-700">Le destinataire vous donne son code (ou son QR). Indiquez aussi le kilométrage à l'arrivée.</p>
    <form method="post" action="{% url 'chauffeur:livraison' mission.pk %}" class="mt-3 space-y-3" x-data="scannerCode('id_code')">{% csrf_token %}
      {% include "mobile/_scanner.html" %}
      {{ form_livraison.code }}
      <div>
        <label for="{{ form_livraison.km_arrivee.id_for_label }}" class="block text-sm font-medium text-slate-800">{{ form_livraison.km_arrivee.label }}</label>
        <div class="mt-1">{{ form_livraison.km_arrivee }}</div>
      </div>
      <button type="submit" class="w-full rounded-2xl bg-marque-600 px-4 py-4 text-lg font-bold text-white shadow active:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-800">Confirmer la livraison</button>
    </form>
  </section>
{% endif %}

{% if mission.statut == "LIVREE" or mission.statut == "CLOTUREE" %}
  <p class="mt-4 rounded-2xl border border-emerald-300 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-900"><i class="fa-solid fa-circle-check mr-2" aria-hidden="true"></i>Mission livrée. Merci !</p>
{% endif %}

<a href="{% url 'chauffeur:incident' %}?mission={{ mission.pk }}" class="mt-6 flex items-center justify-center gap-2 rounded-2xl border border-slate-300 bg-white px-4 py-3 font-semibold text-slate-800 active:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600"><i class="fa-solid fa-triangle-exclamation" aria-hidden="true"></i> Signaler un problème sur cette mission</a>
{% endblock %}
```

#### `apps/mobile_api/templates/mobile/checklist.html`

*40 lignes*

```django
{% extends "mobile/base.html" %}
{% block titre %}Check-list du camion{% endblock %}

{% block contenu %}
<a href="{% url 'chauffeur:mission' mission.pk %}" class="text-sm font-medium text-marque-700 underline-offset-2 hover:underline"><i class="fa-solid fa-chevron-left mr-1" aria-hidden="true"></i>Mission {{ mission.numero }}</a>
<h1 class="mt-2 text-xl font-bold text-slate-900">Check-list du camion</h1>
<p class="text-sm text-slate-600">{{ mission.vehicule.immatriculation }} · à remplir avant le départ. Un point KO prévient le Parc Auto, sans vous empêcher de partir.</p>

<form method="post" class="mt-4 space-y-3" novalidate>
  {% csrf_token %}
  {% if form.non_field_errors %}
    <div role="alert" class="rounded-2xl border border-red-300 bg-red-50 px-4 py-3 text-sm font-medium text-red-900">{% for e in form.non_field_errors %}<p>{{ e }}</p>{% endfor %}</div>
  {% endif %}

  {% for code, libelle, champ_ok, champ_remarque in form.points %}
    <fieldset class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm" x-data="{ ko: {% if champ_ok.value == '0' %}true{% else %}false{% endif %} }">
      <legend class="px-1 text-base font-semibold text-slate-900">{{ libelle }}</legend>
      <div class="mt-2 grid grid-cols-2 gap-3">
        <label class="flex cursor-pointer items-center justify-center gap-2 rounded-xl border-2 px-3 py-3 text-base font-bold has-[:checked]:border-emerald-600 has-[:checked]:bg-emerald-50 has-[:checked]:text-emerald-900 border-slate-300 text-slate-700">
          <input type="radio" name="{{ champ_ok.html_name }}" value="1" class="sr-only" {% if champ_ok.value == "1" %}checked{% endif %} @change="ko = false" required> <i class="fa-solid fa-check" aria-hidden="true"></i> OK
        </label>
        <label class="flex cursor-pointer items-center justify-center gap-2 rounded-xl border-2 px-3 py-3 text-base font-bold has-[:checked]:border-red-600 has-[:checked]:bg-red-50 has-[:checked]:text-red-900 border-slate-300 text-slate-700">
          <input type="radio" name="{{ champ_ok.html_name }}" value="0" class="sr-only" {% if champ_ok.value == "0" %}checked{% endif %} @change="ko = true"> <i class="fa-solid fa-xmark" aria-hidden="true"></i> KO
        </label>
      </div>
      {% for e in champ_ok.errors %}<p class="mt-2 text-sm font-medium text-red-700" role="alert">{{ e }}</p>{% endfor %}
      <div class="mt-3" x-show="ko" x-cloak>
        <label for="{{ champ_remarque.id_for_label }}" class="block text-sm font-medium text-slate-800">Quel est le problème ? <span class="text-red-700" aria-hidden="true">*</span></label>
        <div class="mt-1">{{ champ_remarque }}</div>
      </div>
    </fieldset>
  {% endfor %}

  <div>
    <label for="{{ form.remarque.id_for_label }}" class="block text-sm font-medium text-slate-800">{{ form.remarque.label }}</label>
    <div class="mt-1">{{ form.remarque }}</div>
  </div>
  <button type="submit" class="w-full rounded-2xl bg-marque-600 px-4 py-4 text-lg font-bold text-white shadow active:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-800">Enregistrer la check-list</button>
</form>
{% endblock %}
```

#### `apps/mobile_api/templates/mobile/plein.html`

*46 lignes*

```django
{% extends "mobile/base.html" %}
{% load ui %}
{% block titre %}Plein de carburant{% endblock %}

{% block contenu %}
<h1 class="text-xl font-bold text-slate-900">Plein de carburant</h1>
<p class="text-sm text-slate-600">{% if vehicule %}Camion {{ vehicule.immatriculation }}{% else %}<strong class="text-red-800">Aucun camion ne vous est affecté : contactez le Parc Auto.</strong>{% endif %}</p>

<form method="post" class="mt-4 space-y-4" novalidate>
  {% csrf_token %}

  {% if saisie_suspecte %}
    <div role="alert" class="rounded-2xl border border-amber-400 bg-amber-50 p-4 text-sm text-amber-950">
      <p class="text-base font-semibold"><i class="fa-solid fa-triangle-exclamation mr-2" aria-hidden="true"></i>Vérifiez votre saisie</p>
      <p class="mt-2">Consommation calculée : <strong>{{ saisie_suspecte.consommation|floatformat:1 }} L/100 km</strong> ({{ saisie_suspecte.ecart_pct|pourcentage_signe }} % par rapport à votre moyenne de {{ saisie_suspecte.moyenne|floatformat:1 }}). Une erreur sur les <strong>litres</strong> ou le <strong>kilométrage</strong> est probable.</p>
      <p class="mt-2">Corrigez, ou confirmez si les valeurs sont exactes.</p>
    </div>
  {% endif %}
  {% if form.non_field_errors %}
    <div role="alert" class="rounded-2xl border border-red-300 bg-red-50 px-4 py-3 text-sm font-medium text-red-900">{% for e in form.non_field_errors %}<p>{{ e }}</p>{% endfor %}</div>
  {% endif %}

  {% include "components/_champ.html" with champ=form.station %}
  {% include "components/_champ.html" with champ=form.quantite_litres %}
  {% include "components/_champ.html" with champ=form.prix_unitaire %}
  {% include "components/_champ.html" with champ=form.km_compteur %}
  {% include "components/_champ.html" with champ=form.numero_ticket %}
  {% include "components/_champ.html" with champ=form.date_plein %}

  {% if saisie_suspecte %}
    <button type="submit" name="confirmer" value="1" class="w-full rounded-2xl bg-accent-500 px-4 py-4 text-lg font-bold text-slate-900 shadow active:bg-accent-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-700">Confirmer : les valeurs sont exactes</button>
  {% endif %}
  <button type="submit" class="w-full rounded-2xl bg-marque-600 px-4 py-4 text-lg font-bold text-white shadow active:bg-marque-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-800">{% if saisie_suspecte %}Enregistrer avec mes corrections{% else %}Enregistrer le plein{% endif %}</button>
</form>

{% if derniers %}
  <section class="mt-6" aria-labelledby="titre-derniers">
    <h2 id="titre-derniers" class="text-sm font-semibold uppercase tracking-wide text-slate-600">Mes derniers pleins</h2>
    <ul class="mt-2 divide-y divide-slate-200 rounded-2xl border border-slate-200 bg-white text-sm">
      {% for p in derniers %}
        <li class="flex items-center justify-between gap-3 px-4 py-3"><span>{{ p.date_plein|date:"d/m" }} · {{ p.quantite_litres|floatformat:"-2" }} L</span><span class="font-medium">{% if p.consommation %}{{ p.consommation|floatformat:1 }} L/100{% else %}—{% endif %}{% if p.niveau_alerte != "AUCUNE" %} {% badge p.niveau_alerte "!" %}{% endif %}</span></li>
      {% endfor %}
    </ul>
  </section>
{% endif %}
{% endblock %}
```

#### `apps/mobile_api/templates/mobile/incident.html`

*32 lignes*

```django
{% extends "mobile/base.html" %}
{% load ui %}
{% block titre %}Signaler un incident{% endblock %}

{% block contenu %}
<h1 class="text-xl font-bold text-slate-900">Signaler une panne ou un incident</h1>
<p class="text-sm text-slate-600">Le Parc Auto et la Direction sont prévenus tout de suite. Ils décident de la suite.</p>

<form method="post" class="mt-4 space-y-4" novalidate>
  {% csrf_token %}
  {% if form.non_field_errors %}
    <div role="alert" class="rounded-2xl border border-red-300 bg-red-50 px-4 py-3 text-sm font-medium text-red-900">{% for e in form.non_field_errors %}<p>{{ e }}</p>{% endfor %}</div>
  {% endif %}
  {% include "components/_champ.html" with champ=form.type_incident %}
  {% include "components/_champ.html" with champ=form.gravite %}
  {% include "components/_champ.html" with champ=form.description %}
  {% include "components/_champ.html" with champ=form.lieu %}
  {% include "components/_champ.html" with champ=form.mission %}
  <button type="submit" class="w-full rounded-2xl bg-slate-900 px-4 py-4 text-lg font-bold text-white shadow active:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900"><i class="fa-solid fa-paper-plane mr-2" aria-hidden="true"></i>Envoyer le signalement</button>
</form>

{% if derniers %}
  <section class="mt-6" aria-labelledby="titre-derniers">
    <h2 id="titre-derniers" class="text-sm font-semibold uppercase tracking-wide text-slate-600">Mes derniers signalements</h2>
    <ul class="mt-2 divide-y divide-slate-200 rounded-2xl border border-slate-200 bg-white text-sm">
      {% for i in derniers %}
        <li class="px-4 py-3"><div class="flex items-center justify-between gap-2"><span class="font-medium">{{ i.get_type_incident_display }} · {{ i.vehicule.immatriculation }}</span>{% badge i.statut i.get_statut_display %}</div><p class="mt-1 text-slate-700">{{ i.description|truncatechars:80 }}</p></li>
      {% endfor %}
    </ul>
  </section>
{% endif %}
{% endblock %}
```

#### `apps/mobile_api/templates/mobile/_scanner.html`

*12 lignes* — Bouton et aperçu de la caméra du composant scannerCode (static/js/scanner.js). Absent si le téléphone ne sait pas lire les QR.

```django
{# Bouton et aperçu de la caméra du composant scannerCode (static/js/scanner.js). Absent si le téléphone ne sait pas lire les QR. #}
<div x-show="disponible" x-cloak>
  <button type="button" @click="ouvrir()" x-show="!actif"
          class="flex w-full items-center justify-center gap-2 rounded-2xl border-2 border-marque-600 bg-white px-4 py-3 text-base font-bold text-marque-700 active:bg-marque-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-marque-600">
    <i class="fa-solid fa-qrcode" aria-hidden="true"></i> Scanner le QR
  </button>
  <div x-show="actif" x-cloak class="space-y-2">
    <video x-ref="video" playsinline muted class="w-full rounded-2xl bg-black"></video>
    <button type="button" @click="fermer()" class="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 font-semibold text-slate-800">Fermer la caméra</button>
  </div>
  <p x-show="erreur" x-text="erreur" class="mt-2 text-sm font-medium text-red-700" role="alert"></p>
</div>
```

#### `static/js/scanner.js`

*50 lignes*

```javascript
/*
 * Lecture d'un code QR avec la caméra du téléphone (espace chauffeur).
 *
 * S'appuie sur l'API navigateur BarcodeDetector (Chrome sur Android). Quand elle n'existe pas,
 * le bouton de scan n'est pas proposé : le chauffeur saisit le code à la main.
 * Le QR ne contient que le code de la mission (8 caractères).
 */
window.scannerCode = function (idChamp) {
  return {
    disponible: "BarcodeDetector" in window && !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia),
    actif: false,
    erreur: "",
    flux: null,
    minuteur: null,

    async ouvrir() {
      this.erreur = "";
      try {
        this.flux = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      } catch (e) {
        this.erreur = "Caméra inaccessible : saisissez le code à la main.";
        return;
      }
      this.actif = true;
      await this.$nextTick();
      const video = this.$refs.video;
      video.srcObject = this.flux;
      await video.play();
      const detecteur = new BarcodeDetector({ formats: ["qr_code"] });
      this.minuteur = setInterval(async () => {
        try {
          const trouves = await detecteur.detect(video);
          if (trouves.length) {
            const champ = document.getElementById(idChamp);
            champ.value = trouves[0].rawValue.trim().toUpperCase();
            champ.dispatchEvent(new Event("input", { bubbles: true }));
            this.fermer();
          }
        } catch (e) { /* image pas encore prête : on réessaie */ }
      }, 400);
    },

    fermer() {
      clearInterval(this.minuteur);
      if (this.flux) this.flux.getTracks().forEach((t) => t.stop());
      this.flux = null;
      this.actif = false;
    },
  };
};
```

#### `static/js/sw-register.js`

*10 lignes*

```javascript
// Enregistre le service worker de l'espace chauffeur. L'adresse du service worker vient de
// l'attribut data-sw de la balise script (pas de code en ligne dans la page).
(function () {
  "use strict";
  var balise = document.currentScript;
  var adresse = balise && balise.dataset ? balise.dataset.sw : "";
  if (adresse && "serviceWorker" in navigator) {
    navigator.serviceWorker.register(adresse).catch(function () {});
  }
})();
```

#### `apps/mobile_api/templates/mobile/sw.js`

*28 lignes*

```javascript
// Service worker de l'espace chauffeur.
// Il ne met en cache que la page « hors connexion » et l'icône : les pages du chauffeur
// (missions, codes) sont privées et ne sont jamais conservées. Sans réseau, une navigation
// affiche la page « hors connexion ». La saisie hors ligne n'est pas prise en charge.
const CACHE = "den-chauffeur-v2"; // v2 : page hors connexion sans code en ligne (CSP)
const HORS_LIGNE = "{{ hors_ligne }}";
const FICHIERS = [HORS_LIGNE, "{{ icone }}"];

self.addEventListener("install", (evenement) => {
  evenement.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(FICHIERS)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (evenement) => {
  evenement.waitUntil(
    caches
      .keys()
      .then((noms) => Promise.all(noms.filter((n) => n !== CACHE).map((n) => caches.delete(n))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (evenement) => {
  if (evenement.request.mode === "navigate") {
    evenement.respondWith(fetch(evenement.request).catch(() => caches.match(HORS_LIGNE)));
  }
});
```

Le *service worker* met en cache **uniquement** la page « hors connexion » et l'icône. Pour toute navigation, il
tente le réseau et, s'il échoue, affiche la page « hors connexion ». Les pages privées ne sont **jamais**
stockées.

#### `apps/mobile_api/templates/mobile/hors_ligne.html`

*26 lignes*

```django
{% load static %}<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#8b0319">
  <title>Hors connexion · DEN Chauffeur</title>
  <style>
    body { margin: 0; font-family: system-ui, sans-serif; background: #f1f5f9; color: #0f172a; display: flex; min-height: 100vh; align-items: center; justify-content: center; padding: 1.5rem; }
    main { max-width: 26rem; text-align: center; }
    img { width: 96px; height: 96px; border-radius: 1rem; }
    h1 { font-size: 1.4rem; margin: 1rem 0 .5rem; }
    p { color: #334155; line-height: 1.5; }
    .bouton { display: block; box-sizing: border-box; text-decoration: none; margin-top: 1rem; width: 100%; padding: 1rem; font-size: 1.1rem; font-weight: 700; border: 0; border-radius: 1rem; background: #a80c26; color: #fff; }
  </style>
</head>
<body>
  <main>
    <img src="{% static 'img/icon-192.png' %}" alt="">
    <h1>Vous êtes hors connexion</h1>
    <p>Le réseau est indisponible. Vos missions et vos saisies demandent une connexion : rien n'est enregistré tant que vous n'êtes pas reconnecté.</p>
    <p>Si vous êtes en panne, appelez directement le Parc Auto.</p>
    <a class="bouton" href="{% url 'chauffeur:accueil' %}">Réessayer</a>
  </main>
</body>
</html>
```

Cette page est **autonome** : aucun script, aucune ressource externe, un simple lien « Réessayer », pour qu'elle
s'affiche même sans réseau.

## Étape 5 — Tests

#### `apps/mobile_api/README.md`

*30 lignes* — mobile_api

```markdown
# mobile_api

Rôle : espace mobile du chauffeur — cahier-des-charges.md:54, 132-143, 301-303 ; architecture.md ADR-005.
Trois couches sur les mêmes règles :

- `services.py` : ce qu'un chauffeur voit et fait, **sur ses seules données** (une mission d'un autre
  chauffeur est traitée comme inexistante : 404). Il orchestre `missions`, `fuel` et `garage`.
- `views.py` + `urls.py` : **API mobile** `/api/v1/mobile/` (JWT, permission `EstChauffeur`).
- `views_web.py` + `urls_web.py` + `templates/mobile/` : **écrans mobiles** `/chauffeur/`, tactiles,
  installables (manifeste, service worker, icônes).

Ce que fait le chauffeur : voir ses missions (à faire, en cours, livrées cette semaine), faire la
**check-list** du camion, **démarrer**, confirmer la **récupération** puis la **livraison** en scannant
ou saisissant le code (QR), saisir un **plein** (avec la confirmation d'une saisie suspecte),
signaler un **incident**. L'accueil est son tableau de bord : course du jour, km du mois,
consommation, état du camion.

Points de sécurité : le chauffeur ne voit jamais les codes secrets ni le prix convenu ; il ne saisit
un plein ou un incident que sur son camion (mission en cours ou à venir, ou camion habituel) ; session
de 15 minutes d'inactivité (jeton d'accès de 15 minutes pour l'API) ; le service worker ne met en cache
que la page « hors connexion », jamais les pages privées.

Lecture des QR : `static/js/scanner.js` (API `BarcodeDetector`, Chrome sur Android). Sur un navigateur
qui ne la propose pas, le bouton n'apparaît pas et le chauffeur saisit le code (8 caractères).

Pas encore fait :
- **Mode hors ligne** (file d'attente des saisies, synchronisation différée, conflits) : écarté sur
  décision de l'utilisateur pour cette étape. Sans réseau, une page « hors connexion » s'affiche.
- Photos des incidents (stockage S3 ou MinIO, étape 7) ; notifications push (Firebase).
- Avoir une position GPS ; envoi du code par SMS à l'expéditeur.
```

#### `apps/mobile_api/tests/helpers.py`

*41 lignes* — Aides de test de l'espace chauffeur.

```python
"""Aides de test de l'espace chauffeur."""

from decimal import Decimal

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.customers.tests.factories import ClientFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.garage.models import CODES_CHECKLIST
from apps.missions.models import StatutMission
from apps.missions.tests.factories import MissionFactory

CODE_EXPEDITEUR = "ABCD2345"
CODE_DESTINATAIRE = "WXYZ6789"


def chauffeur_avec_compte(**surcharges):
    """Chauffeur dont la fiche du personnel est rattachée à un compte de rôle CHAUFFEUR."""
    fiche = ChauffeurFactory(**surcharges)
    compte = UserFactory(role=Role.CHAUFFEUR)
    fiche.personnel.utilisateur = compte
    fiche.personnel.save()
    return fiche, compte


def mission_de(chauffeur, statut=StatutMission.AFFECTEE, **surcharges):
    donnees = dict(
        statut=statut, chauffeur=chauffeur, vehicule=VehiculeFactory(), client=ClientFactory(),
        code_expediteur=CODE_EXPEDITEUR, code_destinataire=CODE_DESTINATAIRE,
        prix_convenu=Decimal("850000"),
    )
    donnees.update(surcharges)
    return MissionFactory(**donnees)


def checklist_ok(**ko):
    """Réponses de check-list : tout est OK, sauf les points donnés (code → remarque)."""
    return [
        {"code": c, "ok": c not in ko, "remarque": ko.get(c, "")} for c in CODES_CHECKLIST
    ]
```

#### `apps/mobile_api/tests/test_services.py`

*269 lignes* — Services de l'espace chauffeur : périmètre, cycle de la mission, plein, check-list, incident.

```python
"""Services de l'espace chauffeur : périmètre, cycle de la mission, plein, check-list, incident."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.fuel.exceptions import KilometrageInvalide, SaisieSuspecte
from apps.garage.exceptions import ChecklistDejaRemplie, IncidentInvalide
from apps.garage.models import GraviteIncident, TypeIncident
from apps.missions.exceptions import CodeInvalide, TransitionMissionInterdite
from apps.missions.models import StatutMission
from apps.mobile_api import services
from apps.mobile_api.exceptions import AucunCamion, MissionIntrouvable

from .helpers import CODE_DESTINATAIRE, CODE_EXPEDITEUR, checklist_ok, chauffeur_avec_compte, mission_de

pytestmark = pytest.mark.django_db


# --- périmètre ---


def test_le_chauffeur_ne_voit_que_ses_missions_a_faire_en_cours_ou_livrees_cette_semaine():
    moi, _ = chauffeur_avec_compte()
    autre = ChauffeurFactory()
    affectee = mission_de(moi)
    en_cours = mission_de(moi, StatutMission.EN_COURS_DEPART)
    livree_recente = mission_de(moi, StatutMission.LIVREE, date_livraison=timezone.now() - timedelta(days=2))
    mission_de(moi, StatutMission.LIVREE, date_livraison=timezone.now() - timedelta(days=9))  # trop ancienne
    mission_de(moi, StatutMission.PLANIFIEE)
    mission_de(moi, StatutMission.CLOTUREE, date_livraison=timezone.now() - timedelta(days=1))
    mission_de(autre)

    assert set(services.missions_du_chauffeur(moi)) == {affectee, en_cours, livree_recente}


def test_la_mission_d_un_autre_chauffeur_est_introuvable():
    moi, _ = chauffeur_avec_compte()
    mission_autre = mission_de(ChauffeurFactory())

    with pytest.raises(MissionIntrouvable):
        services.mission_du_chauffeur(moi, mission_autre.pk)
    with pytest.raises(MissionIntrouvable):
        services.mission_du_chauffeur(moi, 999999)
    with pytest.raises(MissionIntrouvable):
        services.demarrer(moi, mission_autre.pk)
    with pytest.raises(MissionIntrouvable):
        services.confirmer_recuperation(moi, mission_autre.pk, code=CODE_EXPEDITEUR)
    with pytest.raises(MissionIntrouvable):
        services.livrer(moi, mission_autre.pk, code=CODE_DESTINATAIRE, km_arrivee=999999)


def test_actions_proposees_selon_le_statut():
    moi, _ = chauffeur_avec_compte()

    affectee = mission_de(moi)
    assert services.actions_possibles(affectee) == {
        "checklist": True, "demarrer": True, "recuperation": False, "livraison": False,
    }
    services.enregistrer_checklist(moi, affectee.pk, resultats=checklist_ok())
    assert services.actions_possibles(affectee)["checklist"] is False
    assert services.actions_possibles(mission_de(moi, StatutMission.EN_COURS_DEPART))["recuperation"] is True
    assert services.actions_possibles(mission_de(moi, StatutMission.EN_COURS_COLIS_RECUPERE))["livraison"] is True
    assert not any(services.actions_possibles(mission_de(moi, StatutMission.LIVREE)).values())


# --- cycle de la mission ---


def test_cycle_complet_demarrer_recuperer_livrer():
    moi, _ = chauffeur_avec_compte()
    mission = mission_de(moi)

    assert services.demarrer(moi, mission.pk).statut == StatutMission.EN_COURS_DEPART
    assert services.confirmer_recuperation(moi, mission.pk, code=CODE_EXPEDITEUR).statut == (
        StatutMission.EN_COURS_COLIS_RECUPERE
    )
    livree = services.livrer(moi, mission.pk, code=CODE_DESTINATAIRE, km_arrivee=mission.vehicule.kilometrage + 300)

    assert livree.statut == StatutMission.LIVREE


def test_un_code_faux_ou_un_statut_incorrect_est_refuse_par_le_metier():
    moi, _ = chauffeur_avec_compte()
    mission = mission_de(moi)

    with pytest.raises(TransitionMissionInterdite):
        services.confirmer_recuperation(moi, mission.pk, code=CODE_EXPEDITEUR)  # pas encore parti
    services.demarrer(moi, mission.pk)
    with pytest.raises(CodeInvalide):
        services.confirmer_recuperation(moi, mission.pk, code="FAUX0000")
    with pytest.raises(TransitionMissionInterdite):
        services.demarrer(moi, mission.pk)  # déjà parti


# --- camion et carburant ---


def test_le_camion_courant_suit_la_mission_en_cours_puis_la_prochaine_puis_l_habituel():
    moi, _ = chauffeur_avec_compte()
    habituel = VehiculeFactory(chauffeur_habituel=moi)
    assert services.vehicule_courant(moi) == habituel

    prochaine = mission_de(moi, date_depart_prevue=date(2026, 10, 1))
    assert services.vehicule_courant(moi) == prochaine.vehicule
    en_cours = mission_de(moi, StatutMission.EN_COURS_DEPART)
    assert services.vehicule_courant(moi) == en_cours.vehicule


def test_sans_mission_ni_camion_habituel_il_n_y_a_pas_de_camion():
    moi, _ = chauffeur_avec_compte()

    assert services.vehicule_courant(moi) is None


def _plein(moi, **surcharges):
    donnees = dict(station="Total", quantite_litres=Decimal("100"), prix_unitaire=Decimal("655"),
                   km_compteur=1000, numero_ticket="T-001")
    donnees.update(surcharges)
    return services.saisir_plein(moi, **donnees)


def test_un_plein_est_saisi_sur_le_camion_courant_a_la_date_du_jour():
    moi, _ = chauffeur_avec_compte()
    mission = mission_de(moi)

    plein = _plein(moi)

    assert plein.vehicule == mission.vehicule and plein.chauffeur == moi
    assert plein.date_plein == timezone.localdate()
    assert list(services.pleins_du_chauffeur(moi)) == [plein]


def test_pas_de_plein_sans_camion_ni_sur_le_camion_d_un_autre():
    moi, _ = chauffeur_avec_compte()
    with pytest.raises(AucunCamion, match="Aucun camion"):
        _plein(moi)

    mission_de(moi)
    camion_d_un_autre = VehiculeFactory()
    with pytest.raises(AucunCamion, match="n'est pas le vôtre"):
        _plein(moi, vehicule_id=camion_d_un_autre.pk)


def test_le_chauffeur_peut_designer_son_camion_explicitement():
    moi, _ = chauffeur_avec_compte()
    mission = mission_de(moi)
    habituel = VehiculeFactory(chauffeur_habituel=moi)

    assert _plein(moi, vehicule_id=habituel.pk, numero_ticket="T-9").vehicule == habituel
    assert _plein(moi, vehicule_id=mission.vehicule.pk, numero_ticket="T-8").vehicule == mission.vehicule


def test_les_regles_du_carburant_s_appliquent_au_plein_du_chauffeur():
    moi, _ = chauffeur_avec_compte()
    mission_de(moi)
    _plein(moi, km_compteur=1000)

    with pytest.raises(KilometrageInvalide):
        _plein(moi, km_compteur=900, numero_ticket="T-002")


def test_une_saisie_suspecte_se_confirme():
    moi, _ = chauffeur_avec_compte()
    mission_de(moi)
    aujourd_hui = timezone.localdate()
    _plein(moi, km_compteur=1000, quantite_litres=Decimal("100"), numero_ticket="T-1",
           date_plein=aujourd_hui - timedelta(days=10))
    for rang, km in enumerate((1400, 1800, 2200), start=2):
        _plein(moi, km_compteur=km, quantite_litres=Decimal("120"), numero_ticket=f"T-{rang}",
               date_plein=aujourd_hui - timedelta(days=10 - rang))

    with pytest.raises(SaisieSuspecte):
        _plein(moi, km_compteur=2600, quantite_litres=Decimal("300"), numero_ticket="T-9")
    plein = _plein(moi, km_compteur=2600, quantite_litres=Decimal("300"), numero_ticket="T-9", confirmer=True)

    assert plein.alerte_saisie is True


# --- check-list et incident ---


def test_la_checklist_passe_par_la_mission_du_chauffeur():
    moi, _ = chauffeur_avec_compte()
    mission = mission_de(moi)

    checklist = services.enregistrer_checklist(
        moi, mission.pk, resultats=checklist_ok(FREINS="Spongieux"), remarque="Attention"
    )

    assert checklist.nb_anomalies == 1 and checklist.chauffeur == moi
    with pytest.raises(ChecklistDejaRemplie):
        services.enregistrer_checklist(moi, mission.pk, resultats=checklist_ok())
    with pytest.raises(MissionIntrouvable):
        services.enregistrer_checklist(moi, mission_de(ChauffeurFactory()).pk, resultats=checklist_ok())


def test_un_incident_sur_la_mission_reprend_son_camion():
    moi, _ = chauffeur_avec_compte()
    mission = mission_de(moi)

    incident = services.declarer_incident(
        moi, type_incident=TypeIncident.PANNE, gravite=GraviteIncident.GRAVE,
        description="Moteur", mission_id=mission.pk,
    )

    assert incident.vehicule == mission.vehicule and incident.mission == mission
    assert list(services.incidents_du_chauffeur(moi)) == [incident]


def test_un_incident_sans_mission_prend_le_camion_courant_et_refuse_un_camion_etranger():
    moi, _ = chauffeur_avec_compte()
    habituel = VehiculeFactory(chauffeur_habituel=moi)

    incident = services.declarer_incident(
        moi, type_incident=TypeIncident.AUTRE, gravite=GraviteIncident.FAIBLE, description="Rétro cassé"
    )
    assert incident.vehicule == habituel and incident.mission is None
    with pytest.raises(AucunCamion):
        services.declarer_incident(
            moi, type_incident=TypeIncident.AUTRE, gravite=GraviteIncident.FAIBLE,
            description="x", vehicule_id=VehiculeFactory().pk,
        )
    with pytest.raises(IncidentInvalide):
        services.declarer_incident(moi, type_incident="AUTRE", gravite="FAIBLE", description=" ")


def test_le_chauffeur_ne_voit_que_ses_incidents_et_ses_pleins():
    moi, _ = chauffeur_avec_compte()
    autre, _ = chauffeur_avec_compte()
    VehiculeFactory(chauffeur_habituel=moi)
    VehiculeFactory(chauffeur_habituel=autre)
    services.declarer_incident(moi, type_incident="AUTRE", gravite="FAIBLE", description="A")
    services.declarer_incident(autre, type_incident="AUTRE", gravite="FAIBLE", description="B")

    assert [i.description for i in services.incidents_du_chauffeur(moi)] == ["A"]


# --- tableau de bord du chauffeur ---


def test_le_tableau_reunit_course_du_jour_km_consommation_et_camion():
    moi, _ = chauffeur_avec_compte()
    livree = mission_de(moi, StatutMission.LIVREE, km_depart=1000, km_arrivee=1450,
                        date_livraison=timezone.now())
    prochaine = mission_de(moi, date_depart_prevue=date(2026, 10, 1))
    mission_de(moi, StatutMission.LIVREE, km_depart=10, km_arrivee=90,
               date_livraison=timezone.now() - timedelta(days=90))  # hors du mois

    tableau = services.tableau(moi)

    assert tableau["mission_du_jour"] == prochaine and tableau["en_cours"] is False
    assert tableau["prochaines"] == [prochaine] and tableau["km_mois"] == 450
    assert tableau["vehicule"] == prochaine.vehicule and tableau["consommation"] is None
    assert livree.pk


def test_en_cours_la_mission_du_jour_est_la_mission_demarree():
    moi, _ = chauffeur_avec_compte()
    mission_de(moi)
    en_cours = mission_de(moi, StatutMission.EN_COURS_DEPART, date_depart=timezone.now())

    tableau = services.tableau(moi)

    assert tableau["mission_du_jour"] == en_cours and tableau["en_cours"] is True
```

#### `apps/mobile_api/tests/test_web.py`

*469 lignes* — Espace mobile du chauffeur (PWA) : accès, parcours d'une mission, check-list, plein, incident.

```python
"""Espace mobile du chauffeur (PWA) : accès, parcours d'une mission, check-list, plein, incident."""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.staticfiles import finders
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import UserFactory
from apps.drivers.tests.factories import ChauffeurFactory
from apps.fleet.tests.factories import VehiculeFactory
from apps.garage.models import ChecklistVehicule, Incident
from apps.missions.models import StatutMission
from apps.mobile_api import services

from .helpers import CODE_DESTINATAIRE, CODE_EXPEDITEUR, chauffeur_avec_compte, mission_de

pytestmark = pytest.mark.django_db


@pytest.fixture
def chauffeur(client):
    fiche, compte = chauffeur_avec_compte()
    client.force_login(compte)
    return fiche, compte


def _messages(reponse):
    return [str(m) for m in reponse.context["messages"]]


PAGES = ["chauffeur:accueil", "chauffeur:missions", "chauffeur:plein", "chauffeur:incident"]


# --- accès ---


@pytest.mark.parametrize("nom", PAGES)
def test_les_pages_du_chauffeur_lui_sont_reservees(client, nom):
    fiche, compte = chauffeur_avec_compte()

    assert client.get(reverse(nom)).status_code == 302  # non connecté : page de connexion
    for role in (Role.ADMIN, Role.DIRECTION, Role.PARCAUTO, Role.RH, Role.FINANCES, Role.CHARGE_CLIENTELE):
        client.force_login(UserFactory(role=role))
        assert client.get(reverse(nom)).status_code == 403, (nom, role)
    client.force_login(UserFactory(role=Role.CHAUFFEUR))  # compte sans fiche du personnel
    assert client.get(reverse(nom)).status_code == 403
    client.force_login(compte)
    assert client.get(reverse(nom)).status_code == 200


def test_la_page_de_bureau_redirige_le_chauffeur_vers_son_espace(client, chauffeur):
    reponse = client.get(reverse("home"))

    assert reponse.status_code == 302 and reponse["Location"] == reverse("chauffeur:accueil")


def test_un_compte_chauffeur_sans_fiche_garde_la_page_d_explication(client):
    client.force_login(UserFactory(role=Role.CHAUFFEUR))

    reponse = client.get(reverse("home"))

    assert reponse.status_code == 200 and "espace mobile" in reponse.content.decode()


def test_la_session_du_chauffeur_dure_15_minutes_celle_du_bureau_30(client):
    compte = UserFactory(role=Role.CHAUFFEUR)
    bureau = UserFactory(role=Role.DIRECTION)

    client.post(reverse("accounts:login"), {"username": compte.username, "password": "Test-Passw0rd!"})
    assert client.session.get_expiry_age() == 15 * 60
    autre = Client()
    autre.post(reverse("accounts:login"), {"username": bureau.username, "password": "Test-Passw0rd!"})
    assert autre.session.get_expiry_age() == 30 * 60


# --- application installable ---


def test_le_manifeste_est_public_et_decrit_l_application(client):
    reponse = client.get(reverse("chauffeur:manifeste"))
    manifeste = json.loads(reponse.content)

    assert reponse.status_code == 200 and reponse["Content-Type"] == "application/manifest+json"
    assert manifeste["start_url"] == "/chauffeur/" == manifeste["scope"]
    assert manifeste["display"] == "standalone" and manifeste["theme_color"] == "#8b0319"
    assert {i["sizes"] for i in manifeste["icons"]} == {"192x192", "512x512"}
    for icone in manifeste["icons"]:  # les fichiers d'icônes existent bien dans les fichiers statiques
        assert finders.find(icone["src"].removeprefix("/static/")), icone["src"]


def test_le_service_worker_ne_met_en_cache_que_la_page_hors_connexion(client):
    reponse = client.get(reverse("chauffeur:sw"))
    texte = reponse.content.decode()

    assert reponse.status_code == 200 and reponse["Content-Type"].startswith("application/javascript")
    assert reponse["Service-Worker-Allowed"] == "/chauffeur/" and reponse["Cache-Control"] == "no-cache"
    assert reverse("chauffeur:hors_ligne") in texte
    assert 'mode === "navigate"' in texte and "/chauffeur/missions/" not in texte


def test_la_page_hors_connexion_est_publique_et_autonome(client):
    reponse = client.get(reverse("chauffeur:hors_ligne"))
    texte = reponse.content.decode()

    assert reponse.status_code == 200 and "hors connexion" in texte
    assert "cdn." not in texte  # doit s'afficher sans réseau : aucune ressource externe


def test_les_pages_declarent_le_manifeste_et_enregistrent_le_service_worker(client, chauffeur):
    texte = client.get(reverse("chauffeur:accueil")).content.decode()

    assert reverse("chauffeur:manifeste") in texte and reverse("chauffeur:sw") in texte
    assert 'name="theme-color"' in texte and "viewport-fit=cover" in texte
    assert 'aria-current="page"' in texte  # onglet actif de la navigation du bas


# --- accueil et missions ---


def test_l_accueil_montre_la_mission_du_jour_le_camion_et_les_chiffres(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche, lieu_chargement="Abidjan", lieu_livraison="Bouaké")

    reponse = client.get(reverse("chauffeur:accueil"))
    texte = reponse.content.decode()

    assert reponse.context["mission_du_jour"] == mission
    assert "Prochaine mission" in texte and "Abidjan" in texte and "Bouaké" in texte
    assert mission.vehicule.immatriculation in texte
    assert "Faire la check-list du camion" in texte and "Saisir un plein" in texte


def test_l_accueil_sans_mission(client, chauffeur):
    texte = client.get(reverse("chauffeur:accueil")).content.decode()

    assert "Aucune mission ne vous est affectée" in texte and "Aucun camion affecté" in texte


def test_l_accueil_d_une_course_en_cours(client, chauffeur):
    fiche, _ = chauffeur
    mission_de(fiche, StatutMission.EN_COURS_DEPART, date_depart=timezone.now())

    texte = client.get(reverse("chauffeur:accueil")).content.decode()

    assert "Course en cours" in texte and "Faire la check-list" not in texte


def test_la_liste_ne_montre_que_mes_missions(client, chauffeur):
    fiche, _ = chauffeur
    a_moi = mission_de(fiche)
    autre = mission_de(ChauffeurFactory())

    texte = client.get(reverse("chauffeur:missions")).content.decode()

    assert a_moi.numero in texte and autre.numero not in texte


def test_la_fiche_d_une_mission_d_un_autre_chauffeur_est_un_404(client, chauffeur):
    autre = mission_de(ChauffeurFactory())

    assert client.get(reverse("chauffeur:mission", args=[autre.pk])).status_code == 404
    assert client.get(reverse("chauffeur:checklist", args=[autre.pk])).status_code == 404


def test_les_codes_secrets_et_le_prix_n_apparaissent_jamais_sur_l_ecran_du_chauffeur(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche)

    for url in (reverse("chauffeur:accueil"), reverse("chauffeur:missions"), reverse("chauffeur:mission", args=[mission.pk])):
        texte = client.get(url).content.decode()
        assert CODE_EXPEDITEUR not in texte and CODE_DESTINATAIRE not in texte, url
        assert "850000" not in texte and "850 000" not in texte, url


def test_boutons_selon_le_statut_de_la_mission(client, chauffeur):
    fiche, _ = chauffeur
    affectee = mission_de(fiche)
    en_cours = mission_de(fiche, StatutMission.EN_COURS_DEPART)
    recuperee = mission_de(fiche, StatutMission.EN_COURS_COLIS_RECUPERE)

    a = client.get(reverse("chauffeur:mission", args=[affectee.pk])).content.decode()
    b = client.get(reverse("chauffeur:mission", args=[en_cours.pk])).content.decode()
    c = client.get(reverse("chauffeur:mission", args=[recuperee.pk])).content.decode()

    assert "Démarrer la mission" in a and "Check-list du camion" in a and "Confirmer la récupération" not in a
    assert "Confirmer la récupération" in b and "Démarrer la mission" not in b and "Scanner le QR" in b
    assert "Confirmer la livraison" in c and "Kilométrage à l" in c


# --- parcours d'une mission ---


def test_parcours_complet_par_les_ecrans(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche)
    km = mission.vehicule.kilometrage

    r1 = client.post(reverse("chauffeur:demarrer", args=[mission.pk]), follow=True)
    r2 = client.post(reverse("chauffeur:recuperation", args=[mission.pk]), {"code": CODE_EXPEDITEUR.lower()}, follow=True)
    r3 = client.post(
        reverse("chauffeur:livraison", args=[mission.pk]), {"code": CODE_DESTINATAIRE, "km_arrivee": km + 350}, follow=True
    )

    mission.refresh_from_db()
    assert mission.statut == StatutMission.LIVREE and mission.km_arrivee == km + 350
    assert any("C'est parti" in m for m in _messages(r1))
    assert any("Colis récupéré" in m for m in _messages(r2))
    assert any("Livraison confirmée" in m for m in _messages(r3))


def test_un_code_faux_ou_une_etape_incorrecte_donne_un_message_sans_rien_changer(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche)

    trop_tot = client.post(reverse("chauffeur:recuperation", args=[mission.pk]), {"code": CODE_EXPEDITEUR}, follow=True)
    client.post(reverse("chauffeur:demarrer", args=[mission.pk]))
    faux = client.post(reverse("chauffeur:recuperation", args=[mission.pk]), {"code": "FAUX0000"}, follow=True)

    mission.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_DEPART
    assert _messages(trop_tot) and any("incorrect" in m.lower() for m in _messages(faux))


def test_champs_manquants_a_la_livraison(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche, StatutMission.EN_COURS_COLIS_RECUPERE)

    reponse = client.post(reverse("chauffeur:livraison", args=[mission.pk]), {"code": CODE_DESTINATAIRE}, follow=True)

    mission.refresh_from_db()
    assert mission.statut == StatutMission.EN_COURS_COLIS_RECUPERE and _messages(reponse)


def test_agir_sur_la_mission_d_un_autre_donne_un_404_et_ne_change_rien(client, chauffeur):
    autre = mission_de(ChauffeurFactory())

    assert client.post(reverse("chauffeur:demarrer", args=[autre.pk])).status_code == 404
    assert client.post(reverse("chauffeur:recuperation", args=[autre.pk]), {"code": CODE_EXPEDITEUR}).status_code == 404
    assert client.post(reverse("chauffeur:livraison", args=[autre.pk]), {"code": "X", "km_arrivee": 1}).status_code == 404
    autre.refresh_from_db()
    assert autre.statut == StatutMission.AFFECTEE


def test_les_actions_de_mission_exigent_post_et_csrf():
    fiche, compte = chauffeur_avec_compte()
    mission = mission_de(fiche)
    http = Client(enforce_csrf_checks=True)
    http.force_login(compte)

    for nom in ("demarrer", "recuperation", "livraison"):
        url = reverse(f"chauffeur:{nom}", args=[mission.pk])
        assert http.get(url).status_code == 405, nom
        assert http.post(url, {"code": CODE_EXPEDITEUR}).status_code == 403, nom
    mission.refresh_from_db()
    assert mission.statut == StatutMission.AFFECTEE


# --- check-list ---


def _reponses_checklist(ko=None):
    from apps.garage.models import CODES_CHECKLIST

    donnees = {}
    for code in CODES_CHECKLIST:
        donnees[f"ok_{code}"] = "0" if ko and code in ko else "1"
        donnees[f"remarque_{code}"] = (ko or {}).get(code, "")
    return donnees


def test_la_page_de_checklist_liste_les_huit_points(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche)

    texte = client.get(reverse("chauffeur:checklist", args=[mission.pk])).content.decode()

    for libelle in ("Pneus", "Freins", "Feux", "huile", "Extincteur"):
        assert libelle in texte
    assert texte.count('value="1"') == 8 and texte.count('value="0"') == 8


def test_checklist_tout_ok(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche)

    reponse = client.post(reverse("chauffeur:checklist", args=[mission.pk]), _reponses_checklist(), follow=True)

    assert ChecklistVehicule.objects.get().nb_anomalies == 0
    assert any("tout est OK" in m for m in _messages(reponse))
    assert "Check-list du camion faite" in reponse.content.decode()


def test_checklist_avec_ko_previent_sans_bloquer(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche)

    reponse = client.post(
        reverse("chauffeur:checklist", args=[mission.pk]), _reponses_checklist(ko={"FREINS": "Pédale molle"}), follow=True
    )

    assert ChecklistVehicule.objects.get().nb_anomalies == 1
    assert any("1 point(s) KO" in m and "vous pouvez partir" in m for m in _messages(reponse))
    assert client.post(reverse("chauffeur:demarrer", args=[mission.pk])).status_code == 302


def test_un_ko_sans_remarque_reste_sur_le_formulaire(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche)

    reponse = client.post(reverse("chauffeur:checklist", args=[mission.pk]), _reponses_checklist(ko={"FREINS": ""}))

    assert reponse.status_code == 200 and "Précisez le problème pour" in reponse.content.decode()
    assert not ChecklistVehicule.objects.exists()


def test_une_checklist_incomplete_est_refusee_et_le_doublon_aussi(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche)
    url = reverse("chauffeur:checklist", args=[mission.pk])
    incomplete = _reponses_checklist()
    del incomplete["ok_PNEUS"]

    assert client.post(url, incomplete).status_code == 200 and not ChecklistVehicule.objects.exists()
    client.post(url, _reponses_checklist())
    doublon = client.post(url, _reponses_checklist())
    assert doublon.status_code == 200 and "déjà remplie" in doublon.content.decode()


# --- plein ---


def _plein(**surcharges):
    donnees = {"station": "Total", "quantite_litres": "100", "prix_unitaire": "655", "km_compteur": "1000",
               "numero_ticket": "T-001", "date_plein": timezone.localdate().isoformat()}
    donnees.update(surcharges)
    return donnees


def test_la_page_plein_annonce_le_camion(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche)

    texte = client.get(reverse("chauffeur:plein")).content.decode()

    assert f"Camion {mission.vehicule.immatriculation}" in texte


def test_saisie_d_un_plein_depuis_le_telephone(client, chauffeur):
    fiche, _ = chauffeur
    mission_de(fiche)

    reponse = client.post(reverse("chauffeur:plein"), _plein(), follow=True)

    assert reponse.redirect_chain[-1][0] == reverse("chauffeur:accueil")
    assert any("Premier plein enregistré" in m for m in _messages(reponse))
    assert services.pleins_du_chauffeur(fiche).count() == 1


def test_plein_sans_camion_ou_invalide_reste_sur_le_formulaire(client, chauffeur):
    fiche, _ = chauffeur

    sans_camion = client.post(reverse("chauffeur:plein"), _plein())
    mission_de(fiche)
    invalide = client.post(reverse("chauffeur:plein"), _plein(quantite_litres="-3", date_plein="2999-01-01"))

    assert sans_camion.status_code == 200 and "Aucun camion ne vous est affecté" in sans_camion.content.decode()
    assert invalide.status_code == 200 and services.pleins_du_chauffeur(fiche).count() == 0


def test_saisie_suspecte_avertit_puis_se_confirme(client, chauffeur):
    fiche, _ = chauffeur
    mission_de(fiche)
    aujourd_hui = timezone.localdate()
    for rang, (km, litres) in enumerate(((1000, "100"), (1400, "120"), (1800, "120"), (2200, "120")), start=1):
        services.saisir_plein(
            fiche, station="T", quantite_litres=Decimal(litres), prix_unitaire=Decimal("655"),
            km_compteur=km, numero_ticket=f"H-{rang}", date_plein=aujourd_hui - timedelta(days=10 - rang),
        )
    suspect = _plein(km_compteur="2600", quantite_litres="300", numero_ticket="S-1")

    avertie = client.post(reverse("chauffeur:plein"), suspect)
    texte = avertie.content.decode()
    assert avertie.status_code == 200 and "Vérifiez votre saisie" in texte
    assert "Confirmer : les valeurs sont exactes" in texte and 'name="confirmer"' in texte
    assert services.pleins_du_chauffeur(fiche).count() == 4  # rien d'enregistré

    confirmee = client.post(reverse("chauffeur:plein"), {**suspect, "confirmer": "1"}, follow=True)
    assert services.pleins_du_chauffeur(fiche).count() == 5
    assert any("Surconsommation" in m for m in _messages(confirmee))


# --- incident ---


def _incident(**surcharges):
    donnees = {"type_incident": "PANNE", "gravite": "MOYENNE", "description": "Moteur qui chauffe",
               "lieu": "Km 120", "mission": ""}
    donnees.update(surcharges)
    return donnees


def test_signalement_d_un_incident_depuis_le_telephone(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche)

    reponse = client.post(reverse("chauffeur:incident"), _incident(mission=mission.pk), follow=True)

    incident = Incident.objects.get()
    assert incident.mission == mission and incident.vehicule == mission.vehicule and incident.chauffeur == fiche
    assert any("Parc Auto et la Direction sont prévenus" in m for m in _messages(reponse))


def test_incident_sans_mission_sur_le_camion_courant(client, chauffeur):
    fiche, _ = chauffeur
    habituel = VehiculeFactory(chauffeur_habituel=fiche)

    client.post(reverse("chauffeur:incident"), _incident())

    assert Incident.objects.get().vehicule == habituel


def test_la_mission_est_preselectionnee_depuis_la_fiche(client, chauffeur):
    fiche, _ = chauffeur
    mission = mission_de(fiche)

    reponse = client.get(reverse("chauffeur:incident"), {"mission": mission.pk})

    assert reponse.context["form"].initial["mission"] == str(mission.pk)
    assert f'value="{mission.pk}" selected' in reponse.content.decode()


def test_incident_invalide_ou_sur_la_mission_d_un_autre(client, chauffeur):
    fiche, _ = chauffeur
    autre = mission_de(ChauffeurFactory())

    vide = client.post(reverse("chauffeur:incident"), _incident(description=""))
    etrangere = client.post(reverse("chauffeur:incident"), _incident(mission=autre.pk))
    sans_camion = client.post(reverse("chauffeur:incident"), _incident())

    assert vide.status_code == 200 and etrangere.status_code == 200 and sans_camion.status_code == 200
    assert "Aucun camion ne vous est affecté" in sans_camion.content.decode()
    assert not Incident.objects.exists()


def test_les_textes_de_l_incident_sont_echappes(client, chauffeur):
    fiche, _ = chauffeur
    VehiculeFactory(chauffeur_habituel=fiche)
    client.post(reverse("chauffeur:incident"), _incident(description="<script>alert(1)</script>"))

    texte = client.get(reverse("chauffeur:incident")).content.decode()

    assert "<script>alert(1)</script>" not in texte and "&lt;script&gt;" in texte


def test_les_formulaires_du_chauffeur_exigent_le_csrf():
    fiche, compte = chauffeur_avec_compte()
    mission_de(fiche)
    http = Client(enforce_csrf_checks=True)
    http.force_login(compte)

    assert http.post(reverse("chauffeur:plein"), _plein()).status_code == 403
    assert http.post(reverse("chauffeur:incident"), _incident()).status_code == 403
    assert not Incident.objects.exists()
```

## Étape 6 — Brancher dans les réglages et les adresses

#### `config/settings/base.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/settings/base.py (avant)
+++ config/settings/base.py (après)
@@ -64,4 +64,5 @@
     "apps.notifications",
     "apps.dashboard",
+    "apps.mobile_api",
 ]
 
```

#### `config/urls.py` — modifications

*Les lignes précédées de `+` sont à ajouter ; les autres sont là pour vous repérer.*

```diff
--- config/urls.py (avant)
+++ config/urls.py (après)
@@ -28,4 +28,5 @@
     path("finances/", include("apps.finance.urls")),
     path("notifications/", include("apps.notifications.urls")),
+    path("chauffeur/", include("apps.mobile_api.urls_web")),
     path("admin/", admin.site.urls),
 ]
```

```bash
cd frontend
npm run build:css
cd ..
```

## Vérifier le chapitre

```bash
python manage.py check
```

```bash
python -m pytest apps/mobile_api/tests/test_services.py apps/mobile_api/tests/test_web.py -q --no-cov
```

**Résultat attendu :** `56 passed` (pour les 2 fichier(s) de tests présentés dans ce chapitre).

**Dans le navigateur.** Sur un ordinateur, ouvrez les outils de développement (`F12`) puis le **mode appareil
mobile** (icône téléphone/tablette). Lancez `python manage.py runserver`.

1. Créez une mission (`demo_charge`), planifiez-la et **affectez-la** (`demo_direction`) au chauffeur `Moussa
   Ouattara` et au camion `1234 AB 01` (chapitre 21).
2. Connectez-vous avec **`demo_chauffeur`** : vous arrivez **directement** sur `/chauffeur/`. L'accueil montre la
   mission du jour, le camion, les kilomètres et la consommation. Le **prix** et les **codes** n'apparaissent
   nulle part.
3. Ouvrez la mission : faites la **check-list** (mettez « Freins » en **KO** avec une remarque : le Parc Auto est
   prévenu, la cloche de `demo_parcauto` le montre), puis **Démarrer**.
4. **Récupération** : saisissez le code de l'expéditeur (visible sur la fiche de bureau, chapitre 21). Puis
   **Livraison** avec le code du destinataire et le kilométrage. (Sur un vrai téléphone Android avec Chrome, le
   bouton **Scanner** ouvre la caméra ; sinon on tape le code.)
5. **Plein** : saisissez un plein sur le camion de la mission. **Panne** : signalez un incident grave : la cloche
   de `demo_parcauto` et de `demo_direction` compte l'alerte.
6. Essayez `/missions/` : le chauffeur reçoit **Accès refusé**. Essayez l'adresse de la mission d'un **autre**
   chauffeur : **404**.
7. Dans les outils de développement (onglet *Application*), le **service worker** est enregistré et le
   **manifeste** est lu. Coupez le réseau (case *Offline*) et rechargez : la page « **hors connexion** » s'affiche.

## Ce qu'il faut retenir

- **Une seule couche de règles** : l'API et les écrans appellent les mêmes services, donc restent cohérents.
- Le **chauffeur** n'accède qu'à **ses** données : c'est le **service** qui le garantit, pas seulement l'affichage.
- Une **PWA** = manifeste + service worker + page hors connexion ; ici on n'y met **jamais** de page privée.
- Un secret n'est jamais envoyé à qui n'en a pas besoin : les **codes ne sont pas dans les pages du chauffeur**.

## Valider avec Git

```bash
git add -A
git commit -m "chapitre 27 : espace mobile du chauffeur (PWA, check-list, codes, plein, incident)"
```

---

[← Chapitre 26](26-tableau-de-bord.md) · [Sommaire](README.md) · [Chapitre 28 →](28-api.md)
