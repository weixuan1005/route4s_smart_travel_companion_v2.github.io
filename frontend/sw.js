/*
 * Smart Travel Companion - service worker
 * =======================================
 *
 * The brief asks what the app does between stations, where there is no signal. This is that
 * answer: the app shell and its data files are cached on install, so the app opens and the
 * journey stays readable underground, and anything from the network carries the time it was
 * fetched so the app can say how old it is rather than passing stale data off as live.
 *
 *   index.html (the whole app)
 *       network first with a short timeout, falling back to the cache. It was cache-first,
 *       which meant a deployed change stayed invisible until someone remembered to bump
 *       CACHE below - a returning phone kept running the old app. Offline still works: the
 *       fallback is the same cached copy as before.
 *
 *   vendor JS and CSS, bus and shelter data
 *       cache first for an instant open, then refreshed in the background, so a stale file
 *       heals itself on the next visit instead of living until the next cache bump.
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
 * Bumping CACHE still clears everything older on activate, but nothing depends on my
 * remembering to do it any more.
 */
const CACHE = "stc-shell-v3";
const DATA_CACHE = "stc-api-v2";
const API_TIMEOUT = 6000;
const SHELL_TIMEOUT = 3000;

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
/* The app itself: a navigation, or index.html asked for by name. */
const isAppDoc = (url, request) =>
  request.mode === "navigate" || url.pathname.endsWith("/") || url.pathname.endsWith("/index.html");

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

/* The app itself. Fresh when there is a network, the last deploy when there is not. Without
   this a phone that has opened the app once keeps running that version for ever. */
async function appDoc(request) {
  const cache = await caches.open(CACHE);
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), SHELL_TIMEOUT);
    /* reload, not default: the browser's own HTTP cache would otherwise hand back the same
       stale page this function exists to get past. */
    const fresh = await fetch(request, {signal: controller.signal, cache: "reload"});
    clearTimeout(timer);
    if (!fresh.ok) throw new Error("HTTP " + fresh.status);
    /* Under both names install used. "/" and "/index.html" are separate cache entries, and
       leaving the other one behind keeps a stale copy alive to be served offline later. */
    await Promise.all([request, "./", "./index.html"].map(k => cache.put(k, fresh.clone())));
    return fresh;
  } catch (e) {
    const cached = await cache.match(request) || await cache.match("./index.html") || await cache.match("./");
    if (cached) return cached;
    throw e;
  }
}

/* Everything else in the shell: answer from cache at once, then quietly replace it, so a file
   that changed in a deploy is right on the next visit rather than at the next cache bump. */
async function cacheFirst(request) {
  const cache = await caches.open(CACHE);
  const cached = await cache.match(request);
  const network = fetch(request).then(fresh => {
    if (fresh.ok) cache.put(request, fresh.clone());
    return fresh;
  });
  if (cached) { network.catch(() => {}); return cached; }
  return network;
}

self.addEventListener("fetch", event => {
  const {request} = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;   /* leave third parties alone */
  if (isMap(url)) return;                            /* range requests: straight to the network */
  if (isApi(url)) return event.respondWith(networkFirst(request));
  event.respondWith(isAppDoc(url, request) ? appDoc(request) : cacheFirst(request));
});
