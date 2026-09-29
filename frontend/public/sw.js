/* LisheBora service worker: keeps field pages usable without a connection.
   - Pages: network first, falling back to the last copy seen, then to /offline.
   - Next.js static assets and brand files: cache first (they are content-hashed).
   - API calls are never cached here; the app's own offline queue handles writes. */
const VERSION = "lb-v6";
const SHELL = ["/offline", "/manifest.webmanifest", "/icon-192.png", "/brand/aatf-logo.png"];
const FIELD = ["/app", "/app/aggregation", "/app/quality", "/app/deliveries", "/app/inventory", "/app/trace"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL).then(() => Promise.allSettled(FIELD.map((u) => c.add(u))))).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;
  if (url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/brand/") || /\.(png|svg|ico|woff2?)$/.test(url.pathname)) {
    e.respondWith(caches.match(req).then((hit) => hit || fetch(req).then((res) => { const copy = res.clone(); caches.open(VERSION).then((c) => c.put(req, copy)); return res; })));
    return;
  }
  if (req.mode === "navigate") {
    e.respondWith(fetch(req).then((res) => { const copy = res.clone(); caches.open(VERSION).then((c) => c.put(req, copy)); return res; })
      .catch(() => caches.match(req).then((hit) => hit || caches.match("/offline"))));
  }
});
