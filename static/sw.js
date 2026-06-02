const CACHE_NAME = "meta-weather-v2";

// Кешируем базовые ресурсы
const urlsToCache = [
  "/",
  "/static/manifest.json",
  "/static/favicon-192.png",
  "/static/favicon-512.png"
];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(urlsToCache);
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.filter(k => k !== CACHE_NAME)
            .map(k => caches.delete(k))
      );
    })
  );
  self.clients.claim();
});

// NETWORK FIRST (для погоды важно)
self.addEventListener("fetch", event => {
  event.respondWith(
    fetch(event.request)
      .then(response => {
        // обновляем кеш
        let clone = response.clone();
        caches.open(CACHE_NAME).then(cache => {
          cache.put(event.request, clone);
        });
        return response;
      })
      .catch(() => {
        return caches.match(event.request);
      })
  );
});