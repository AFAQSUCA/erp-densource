// Service worker de l'espace chauffeur.
// Il ne met en cache que la page « hors connexion » et l'icône : les pages du chauffeur
// (missions, codes) sont privées et ne sont jamais conservées. Sans réseau, une navigation
// affiche la page « hors connexion ». La saisie hors ligne n'est pas prise en charge.
const CACHE = "den-chauffeur-v1";
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
