/* Every Debt Clock. Caches the shell (CSS, JS, icons). Never caches figures.
   api/, data/, JSON, and embed widgets are always requested from the network. */
var SHELL = "edc-shell-v1";
var SHELL_URLS = [
  "/style.css",
  "/app.js",
  "/core.js",
  "/cross41.js",
  "/manifest.json",
  "/icon-512.png",
  "/icon-192.png",
  "/apple-touch-icon.png",
  "/favicon.ico",
  "/favicon-32.png",
  "/icon.svg"
];

self.addEventListener("install", function (event) {
  event.waitUntil(caches.open(SHELL).then(function (cache) {
    return Promise.all(SHELL_URLS.map(function (url) {
      return cache.add(url).catch(function () { return null; });
    }));
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (event) {
  event.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (key) { return key !== SHELL; }).map(function (key) {
      return caches.delete(key);
    }));
  }).then(function () { return self.clients.claim(); }));
});

function isFresh(url) {
  var path = url.pathname;
  return path.indexOf("/api/") === 0 || path.indexOf("/data/") === 0 || path.indexOf("/embed/") === 0 || /\.json$/i.test(path);
}

function isShell(url) {
  return /\.(?:css|js|png|svg|ico|webmanifest)$/i.test(url.pathname) || url.pathname === "/manifest.json";
}

self.addEventListener("fetch", function (event) {
  var url = new URL(event.request.url);
  if (url.origin !== self.location.origin || event.request.method !== "GET") return;
  if (isFresh(url)) {
    event.respondWith(fetch(event.request, {cache: "no-store"}));
    return;
  }
  if (event.request.mode === "navigate" || (event.request.headers.get("accept") || "").indexOf("text/html") !== -1) {
    event.respondWith(fetch(event.request));
    return;
  }
  if (!isShell(url)) return;
  event.respondWith(caches.open(SHELL).then(function (cache) {
    return cache.match(event.request).then(function (hit) {
      var net = fetch(event.request).then(function (res) {
        if (res && res.ok) cache.put(event.request, res.clone());
        return res;
      });
      return hit || net;
    });
  }));
});
