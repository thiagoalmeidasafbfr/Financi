// Financi: guarda a casca do app (página, estilos, scripts) no aparelho para abrir na hora, sem esperar o servidor
// acordar. Os dados (/api) sempre vêm da rede. A cada abertura a casca é conferida em segundo plano; se mudou,
// o cache é atualizado e o app mostra "Nova versão" (vale a partir da próxima abertura ou ao tocar em Atualizar).
const CACHE = "financi-shell-v1";
const SHELL = ["/", "/static/az/tokens.css", "/static/az/bundle.css", "/static/style.css", "/static/app.js",
  "/static/vendor/echarts.min.js", "/static/manifest.webmanifest", "/static/icons/icon-192.png"];
const WATCH = new Set(["/", "/static/app.js", "/static/style.css"]); // mudança nestes avisa a página

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL.map((u) => new Request(u, { cache: "no-cache" })))).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

// compara o conteúdo (não o ETag: no Vercel a página vem da função, e o ETag pode variar entre instâncias)
const changed = async (a, b) => (await a.clone().text()) !== (await b.clone().text());

async function notifyUpdated() {
  const clients = await self.clients.matchAll({ type: "window" });
  clients.forEach((c) => c.postMessage({ type: "updated" }));
}

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  const nav = req.mode === "navigate";
  if (!nav && !url.pathname.startsWith("/static/")) return; // /api e /sw.js: sempre da rede
  const key = nav ? "/" : url.pathname;
  e.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const cached = await cache.match(key);
    const before = cached && WATCH.has(key) ? cached.clone() : null; // a página consome o corpo de `cached`
    const update = fetch(nav ? "/" : req, { cache: "no-cache" }).then(async (res) => {
      if (res.ok && res.type === "basic") {
        const isNew = before && await changed(before, res);
        await cache.put(key, res.clone());
        if (isNew) await notifyUpdated();
      }
      return res;
    });
    if (cached) {
      e.waitUntil(update.catch(() => null));
      return cached;
    }
    return update;
  })());
});
