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
