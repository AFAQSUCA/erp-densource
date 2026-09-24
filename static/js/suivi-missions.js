// Suivi des missions en direct : ouvre la WebSocket du serveur et rafraîchit l'écran dès qu'une mission
// change (par exemple quand le chauffeur saisit ou scanne un code depuis son téléphone).
//
// Aucun code n'est écrit dans les pages (CSP stricte) ; le gabarit déclare son intention :
//   <div data-suivi-missions data-ws-chemin="/ws/missions/suivi/" data-mission-id="12">
//       data-mission-id : ne réagit qu'aux changements de cette mission (fiche) ; absent : toute
//       mission (liste).
//   <div data-suivi-zone="nom">   zone remplacée par la même zone de la page rechargée
//   #suivi-voyant [data-etat=connecte|reconnexion|hors_ligne], #suivi-annonce (lecteurs d'écran),
//   #suivi-bandeau + #suivi-actualiser (changement arrivé pendant une saisie).
//
// Le message reçu ne contient que « quelle mission, quel statut » : les données, elles, sont relues par
// une requête ordinaire, avec les droits de l'utilisateur. Rien de secret ne transite par la WebSocket.
(function () {
  "use strict";

  var racine = document.querySelector("[data-suivi-missions]");
  if (!racine || !("WebSocket" in window)) {
    return;
  }

  var chemin = racine.getAttribute("data-ws-chemin");
  var missionId = racine.getAttribute("data-mission-id");
  var voyant = document.getElementById("suivi-voyant");
  var annonce = document.getElementById("suivi-annonce");
  var bandeau = document.getElementById("suivi-bandeau");
  var bouton = document.getElementById("suivi-actualiser");

  var delai = 1000;      // attente avant de se reconnecter, doublée à chaque échec (15 s au plus)
  var echecs = 0;        // échecs de connexion consécutifs avant la toute première ouverture
  var dejaOuverte = false;
  var minuterie = null;

  function montrerEtat(etat) {
    if (!voyant) {
      return;
    }
    var pastilles = voyant.querySelectorAll("[data-etat]");
    for (var i = 0; i < pastilles.length; i++) {
      pastilles[i].classList.toggle("hidden", pastilles[i].getAttribute("data-etat") !== etat);
    }
  }

  function saisieEnCours(zone) {
    var actif = document.activeElement;
    return !!actif && zone.contains(actif) && /^(INPUT|SELECT|TEXTAREA)$/.test(actif.tagName);
  }

  // Relit la page et remplace les zones ; une zone où l'on est en train de saisir est laissée telle
  // quelle (on ne perd pas une saisie) et un bandeau propose d'actualiser.
  function actualiser() {
    fetch(window.location.href, { credentials: "same-origin", headers: { "X-Requested-With": "suivi" } })
      .then(function (reponse) {
        if (!reponse.ok || reponse.redirected) {
          window.location.reload(); // session expirée, page disparue : on laisse le serveur décider
          return null;
        }
        return reponse.text();
      })
      .then(function (html) {
        if (html === null) {
          return;
        }
        var page = new DOMParser().parseFromString(html, "text/html");
        var occupee = false;
        var zones = document.querySelectorAll("[data-suivi-zone]");
        for (var i = 0; i < zones.length; i++) {
          var nouvelle = page.querySelector('[data-suivi-zone="' + zones[i].getAttribute("data-suivi-zone") + '"]');
          if (!nouvelle) {
            continue;
          }
          if (saisieEnCours(zones[i])) {
            occupee = true;
          } else {
            zones[i].replaceWith(nouvelle);
          }
        }
        if (bandeau) {
          bandeau.classList.toggle("hidden", !occupee);
        }
      })
      .catch(function () {
        /* réseau coupé : la reconnexion et l'actualisation qui suit rattraperont le retard */
      });
  }

  function planifierActualisation() {
    window.clearTimeout(minuterie);
    minuterie = window.setTimeout(actualiser, 250); // regroupe des changements rapprochés
  }

  function annoncer(mission) {
    if (annonce) {
      annonce.textContent = "Mission " + mission.numero + " : " + mission.statut_libelle + ".";
    }
  }

  function connecter() {
    var protocole = window.location.protocol === "https:" ? "wss://" : "ws://";
    var socket = new WebSocket(protocole + window.location.host + chemin);

    socket.onopen = function () {
      delai = 1000;
      echecs = 0;
      montrerEtat("connecte");
      if (dejaOuverte) {
        planifierActualisation(); // reconnecté : rattrape ce qui a changé pendant la coupure
      }
      dejaOuverte = true;
    };

    socket.onmessage = function (evenement) {
      var mission;
      try {
        mission = JSON.parse(evenement.data);
      } catch (erreur) {
        return;
      }
      if (missionId && String(mission.id) !== missionId) {
        return;
      }
      annoncer(mission);
      planifierActualisation();
    };

    socket.onclose = function () {
      if (!dejaOuverte && ++echecs >= 4) {
        montrerEtat("hors_ligne"); // refusée (droits, MFA) ou serveur sans WebSocket : inutile d'insister
        return;
      }
      montrerEtat("reconnexion");
      window.setTimeout(connecter, delai);
      delai = Math.min(delai * 2, 15000);
    };
  }

  if (bouton) {
    bouton.addEventListener("click", function () {
      window.location.reload();
    });
  }
  connecter();
})();
