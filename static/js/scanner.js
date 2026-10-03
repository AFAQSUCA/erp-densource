/*
 * Lecture d'un code QR avec la caméra du téléphone (espace chauffeur).
 *
 * Deux méthodes, selon le navigateur :
 *  - l'API BarcodeDetector (Chrome sur Android) : rapide, intégrée ;
 *  - sinon (Safari sur iPhone, Firefox) : on copie l'image de la caméra dans un canvas et la bibliothèque
 *    jsQR (static/vendor/jsqr/jsQR.js, chargée seulement à ce moment-là) y cherche le QR.
 * Sans caméra accessible, le bouton de scan n'est pas proposé : le chauffeur saisit le code à la main.
 * Le QR ne contient que le code de la mission (8 caractères).
 */
(function () {
  const LARGEUR_ANALYSE = 480; // on réduit l'image : suffisant pour un QR et bien plus léger à analyser

  function chargerJsQR() {
    if (window.jsQR) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const balise = document.createElement("script");
      balise.src = document.body.dataset.jsqr;
      balise.onload = resolve;
      balise.onerror = () => reject(new Error("jsQR indisponible"));
      document.head.appendChild(balise);
    });
  }

  // Cherche un QR dans l'image courante de la vidéo avec jsQR ; renvoie son texte ou null.
  function lireAvecJsQR(video, canvas) {
    if (!video.videoWidth) return null;
    const echelle = Math.min(1, LARGEUR_ANALYSE / video.videoWidth);
    canvas.width = Math.round(video.videoWidth * echelle);
    canvas.height = Math.round(video.videoHeight * echelle);
    const contexte = canvas.getContext("2d", { willReadFrequently: true });
    contexte.drawImage(video, 0, 0, canvas.width, canvas.height);
    const image = contexte.getImageData(0, 0, canvas.width, canvas.height);
    const trouve = window.jsQR(image.data, image.width, image.height, { inversionAttempts: "dontInvert" });
    return trouve ? trouve.data : null;
  }

  window.lireQrDansImage = lireAvecJsQR; // exposé pour les vérifications

  window.scannerCode = function (idChamp) {
    return {
      disponible: !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia),
      actif: false,
      erreur: "",
      flux: null,
      minuteur: null,

      async ouvrir() {
        this.erreur = "";
        const natif = "BarcodeDetector" in window;
        try {
          if (!natif) await chargerJsQR();
        } catch (e) {
          this.erreur = "Lecteur de QR indisponible : saisissez le code à la main.";
          return;
        }
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
        const detecteur = natif ? new BarcodeDetector({ formats: ["qr_code"] }) : null;
        const canvas = document.createElement("canvas");
        this.minuteur = setInterval(async () => {
          try {
            let texte = null;
            if (detecteur) {
              const trouves = await detecteur.detect(video);
              if (trouves.length) texte = trouves[0].rawValue;
            } else {
              texte = lireAvecJsQR(video, canvas);
            }
            if (texte) {
              const champ = document.getElementById(idChamp);
              champ.value = texte.trim().toUpperCase();
              champ.dispatchEvent(new Event("input", { bubbles: true }));
              this.fermer();
            }
          } catch (e) { /* image pas encore prête : on réessaie */ }
        }, natif ? 400 : 250);
      },

      fermer() {
        clearInterval(this.minuteur);
        if (this.flux) this.flux.getTracks().forEach((t) => t.stop());
        this.flux = null;
        this.actif = false;
      },
    };
  };
})();
