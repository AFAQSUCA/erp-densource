// Comportements communs de l'interface. Aucun code n'est écrit dans les pages (CSP stricte) :
// les gabarits déclarent leur intention par des attributs « data-… » que ce fichier interprète.
//
//   <form data-confirm="Question ?">   demande confirmation avant l'envoi du formulaire
//   <button data-imprimer>             ouvre la fenêtre d'impression
//   <form data-renvoi-permis>          autorise plusieurs envois sans recharger la page (par défaut, un
//                                      formulaire POST n'est envoyé qu'une fois : double clic, audit AUD-06)
(function () {
  "use strict";

  document.addEventListener("submit", function (evenement) {
    var formulaire = evenement.target;
    var question = formulaire && formulaire.dataset ? formulaire.dataset.confirm : "";
    if (question && !window.confirm(question)) {
      evenement.preventDefault();
      return;
    }
    // Un formulaire POST n'est envoyé qu'une fois : un double clic ne crée pas deux règlements. Le bouton n'est
    // pas désactivé (il n'enverrait plus son nom ni sa valeur) : le formulaire est marqué, le second envoi ignoré.
    if ((formulaire.method || "").toLowerCase() !== "post" || formulaire.hasAttribute("data-renvoi-permis")) {
      return;
    }
    if (formulaire.dataset.envoye === "1") {
      evenement.preventDefault();
      return;
    }
    formulaire.dataset.envoye = "1";
    formulaire.setAttribute("aria-busy", "true");
  });

  // Retour arrière du navigateur vers une page gardée en cache : le formulaire doit redevenir utilisable.
  window.addEventListener("pageshow", function (evenement) {
    if (!evenement.persisted) {
      return;
    }
    document.querySelectorAll("form[data-envoye]").forEach(function (formulaire) {
      delete formulaire.dataset.envoye;
      formulaire.removeAttribute("aria-busy");
    });
  });

  document.addEventListener("click", function (evenement) {
    var declencheur = evenement.target.closest ? evenement.target.closest("[data-imprimer]") : null;
    if (declencheur) {
      window.print();
    }
  });
})();
