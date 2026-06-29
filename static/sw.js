const CACHE_NAME = 'visma-v2';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(clients.claim());
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // API responses are live data — bypass the HTTP cache entirely so a saved
  // edit is never masked by a stale cached response on the next load. Without
  // this, fetch() here could return a previously cached /api/... body (so the
  // server's no-store header never even gets a chance to apply).
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(fetch(event.request, { cache: 'no-store' }));
    return;
  }

  // Everything else: network-first, fall back to any cached copy when offline.
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
