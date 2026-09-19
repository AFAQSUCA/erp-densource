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
