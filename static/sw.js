const CACHE_NAME = "quiz-app-v1";
const urlsToCache = ["/", "/static/manifest.json", "/static/icons/icon-192x192.png"];
self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(urlsToCache)));
});
self.addEventListener("fetch", e => {
  e.respondWith(
    caches.match(e.request).then(resp => resp || fetch(e.request))
  );
});