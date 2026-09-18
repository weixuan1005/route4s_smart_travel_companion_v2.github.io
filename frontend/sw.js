/*
 * Smart Travel Companion - service worker
 * =======================================
 *
 * The brief asks what the app does between stations, where there is no signal. This is that
 * answer: the app shell and its data files are cached on install, so the app opens and the
 * journey stays readable underground, and anything from the network carries the time it was
 * fetched so the app can say how old it is rather than passing stale data off as live.
 *
 *   app shell (HTML, vendor JS and CSS, bus and shelter data)
 *       cache first, then network. These change only when the app is deployed.
 *
 *   /api/* (alerts, crowding, weather, arrivals, planned works)
 *       network first with a 6 second timeout, falling back to the last good response.
 *       A fallback answer is tagged so the UI can show when it was fetched.
 *
 *   map/singapore.pmtiles
 *       never cached. It is tens of megabytes and is read with byte-range requests, which
 *       the Cache API does not serve usefully; caching it would blow the storage quota for
 *       no benefit. Underground the map keeps whatever tiles the page already holds.
 *
 * Bump CACHE when the shell changes: install pre-caches the new one and activate deletes
 * every older cache, so a stale shell cannot outlive a deploy.
 */
const CACHE = "stc-shell-v2";
const DATA_CACHE = "stc-api-v2";
const API_TIMEOUT = 6000;

/* Relative so this works both at the site root and under /frontend/ on project Pages. */
const SHELL = [
  "./",
  "./index.html",
  "./vendor/leaflet/leaflet.js",
  "./vendor/leaflet/leaflet.css",
  "./vendor/protomaps-leaflet/protomaps-leaflet.js",
  "./busdata.json",
  "./covered.json",
];

self.addEventListener("install", event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    /* addAll fails the whole install if one file 404s, and busdata.json or covered.json may
       not have been generated. Cache what is there and let the rest be. */
    await Promise.all(SHELL.map(url => cache.add(url).catch(() => {})));
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    const keep = [CACHE, DATA_CACHE];
    await Promise.all((await caches.keys()).filter(k => !keep.includes(k)).map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

const isApi = url => url.pathname.includes("/api/");
const isMap = url => url.pathname.endsWith(".pmtiles");

/* A cached API answer is still useful underground, but the app must be able to say how old it
   is, so the age rides along in a header the page can read. */
function stamped(response, fetchedAt) {
  const headers = new Headers(response.headers);
  headers.set("X-Cached-At", String(fetchedAt));
  return new Response(response.body, {status: response.status, statusText: response.statusText, headers});
}

async function networkFirst(request) {
  const cache = await caches.open(DATA_CACHE);
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), API_TIMEOUT);
    /* no-store, deliberately: without it the browser's own HTTP cache can answer while the
       device is offline, the worker believes it reached the network, and the app reports
       stale conditions as live. The point of this path is to know which one it got. */
    const fresh = await fetch(request, {signal: controller.signal, cache: "no-store"});
    clearTimeout(timer);
    if (fresh.ok) {
      await cache.put(request, stamped(fresh.clone(), Date.now()));
      return fresh;
    }
    throw new Error("HTTP " + fresh.status);
  } catch (e) {
    const cached = await cache.match(request);
    if (cached) return cached;
    /* Nothing cached and nothing reachable: say so in the shape the app already handles,
       rather than letting the fetch reject and the caller guess. */
    return new Response(JSON.stringify({source: "offline", error: "No signal and nothing cached"}),
                        {status: 503, headers: {"Content-Type": "application/json", "X-Cached-At": "0"}});
  }
}

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const fresh = await fetch(request);
  if (fresh.ok && request.method === "GET") (await caches.open(CACHE)).put(request, fresh.clone());
  return fresh;
}

self.addEventListener("fetch", event => {
  const {request} = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;   /* leave third parties alone */
  if (isMap(url)) return;                            /* range requests: straight to the network */
  event.respondWith(isApi(url) ? networkFirst(request) : cacheFirst(request));
});
