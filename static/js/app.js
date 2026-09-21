// Comportements communs de l'interface. Aucun code n'est écrit dans les pages (CSP stricte) :
// les gabarits déclarent leur intention par des attributs « data-… » que ce fichier interprète.
//
//   <form data-confirm="Question ?">   demande confirmation avant l'envoi du formulaire
//   <button data-imprimer>             ouvre la fenêtre d'impression
(function () {
  "use strict";

  document.addEventListener("submit", function (evenement) {
    var formulaire = evenement.target;
    var question = formulaire && formulaire.dataset ? formulaire.dataset.confirm : "";
    if (question && !window.confirm(question)) {
      evenement.preventDefault();
    }
  });

  document.addEventListener("click", function (evenement) {
    var declencheur = evenement.target.closest ? evenement.target.closest("[data-imprimer]") : null;
    if (declencheur) {
      window.print();
    }
  });
})();
