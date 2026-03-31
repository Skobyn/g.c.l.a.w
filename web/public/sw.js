/**
 * GClaw Service Worker — network-first strategy.
 *
 * For every fetch request, attempt the network first.
 * If the network succeeds, cache the response.
 * If the network fails, serve from cache if available.
 */

const CACHE_NAME = "gclaw-v1";

self.addEventListener("install", (event) => {
  // Activate immediately without waiting for existing clients to close
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  // Take control of all clients immediately
  event.waitUntil(self.clients.claim());

  // Remove old caches
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(
        names
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      )
    )
  );
});

self.addEventListener("fetch", (event) => {
  // Only handle GET requests; skip non-http(s) schemes
  if (
    event.request.method !== "GET" ||
    !event.request.url.startsWith("http")
  ) {
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        // Cache a clone of the successful network response
        if (networkResponse.ok) {
          const responseClone = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return networkResponse;
      })
      .catch(() =>
        // Network failed — try the cache
        caches.match(event.request)
      )
  );
});
