/* Service worker de Radar: shell offline y último feed. Nunca cachea chat, ajustes ni auth. */
const SHELL = "radar-shell-v1";
const API = "radar-api-v1";
const CACHEABLE_API = ["/api/today", "/api/applications", "/api/skills/impact"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL).then((c) => c.addAll(["/m"])).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== SHELL && k !== API).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;

  if (url.pathname.startsWith("/api/")) {
    if (!CACHEABLE_API.includes(url.pathname)) return;
    event.respondWith(
      fetch(request).then((response) => {
        if (response.ok) { const copy = response.clone(); caches.open(API).then((c) => c.put(url.pathname, copy)); }
        return response;
      }).catch(() => caches.match(url.pathname, { cacheName: API }).then((hit) => hit || Response.error())),
    );
    return;
  }
  if (url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/icon-")) {
    event.respondWith(caches.match(request).then((hit) => hit || fetch(request).then((response) => {
      const copy = response.clone(); caches.open(SHELL).then((c) => c.put(request, copy)); return response;
    })));
    return;
  }
  if (request.mode === "navigate" && url.pathname === "/m") {
    event.respondWith(fetch(request).then((response) => {
      const copy = response.clone(); caches.open(SHELL).then((c) => c.put("/m", copy)); return response;
    }).catch(() => caches.match("/m")));
  }
});
