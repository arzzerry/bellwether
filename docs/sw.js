const CACHE = "bellwether-v2.2";
const ASSETS = ["./", "./index.html", "./manifest.webmanifest", "./icon-192.png", "./icon-512.png", "./apple-touch-icon.png"];
self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  const url = new URL(e.request.url);
  /* Never cache the price providers: stale quotes are worse than none. */
  if (url.origin !== location.origin) return;

  /* The page and the manifest go to the network first. Cache-first here means
     the first load after a deploy serves the PREVIOUS version and only the
     second load shows the new one, which reads as "my change did not ship".
     Offline still works: the fetch fails and we fall back to the cache. */
  const isDoc = e.request.mode === "navigate"
             || url.pathname.endsWith("/")
             || url.pathname.endsWith(".html")
             || url.pathname.endsWith(".webmanifest");

  if (isDoc) {
    e.respondWith(
      fetch(e.request).then(res => {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, copy));
        return res;
      }).catch(() => caches.match(e.request).then(hit => hit || caches.match("./index.html")))
    );
    return;
  }

  /* Static assets are content-addressed by the cache name, so cache-first. */
  e.respondWith(
    caches.match(e.request).then(hit => hit || fetch(e.request).then(res => {
      const copy = res.clone();
      caches.open(CACHE).then(c => c.put(e.request, copy));
      return res;
    }))
  );
});
