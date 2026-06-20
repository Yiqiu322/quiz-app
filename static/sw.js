const CACHE = "quiz-v2";
const STATIC = ["/static/manifest.json", "/static/icons/icon-192x192.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(STATIC)));
  self.skipWaiting();
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.map(k => { if (k !== CACHE) return caches.delete(k); }))));
  self.clients.claim();
});

self.addEventListener("fetch", e => {
  // HTML 页面始终从网络获取（不缓存）
  if (e.request.mode === "navigate") {
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
    return;
  }
  // 静态资源优先缓存
  e.respondWith(
    caches.match(e.request).then(r => r || fetch(e.request).then(resp => {
      const copy = resp.clone();
      caches.open(CACHE).then(c => c.put(e.request, copy));
      return resp;
    }))
  );
});
