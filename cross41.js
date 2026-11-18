/* Turns the pre-written $41 trillion banner on. No network, no cookies.
   cross41Update(liveDollars, officialClose, asOfISO)
   cross41When(unixSeconds) -> {ct, et} rounded to the nearest second. */
(function () {
  var MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  function money(n, digits) {
    if (n == null || !isFinite(n)) return "—";
    return (n < 0 ? "−$" : "$") + Math.abs(n).toLocaleString("en-US", {minimumFractionDigits: digits, maximumFractionDigits: digits});
  }
  function asofText(s) {
    if (!/^\d{4}-\d\d-\d\d$/.test(s || "")) return s || "";
    var p = s.split("-");
    return MONTHS[+p[1] - 1].slice(0, 3) + " " + (+p[2]) + ", " + p[0];
  }
  function parts(ts, zone) {
    var out = {};
    new Intl.DateTimeFormat("en-US", {
      timeZone: zone, year: "numeric", month: "long", day: "numeric",
      hour: "numeric", minute: "2-digit", second: "2-digit", hour12: true
    }).formatToParts(new Date(ts * 1000)).forEach(function (p) { if (p.type !== "literal") out[p.type] = p.value; });
    return out.month + " " + out.day + ", " + out.year + ", " + out.hour + ":" + out.minute + ":" + out.second + " " + out.dayPeriod;
  }
  window.cross41When = function (ts) {
    if (!(ts > 0)) return null;
    var r = Math.floor(ts + 0.5);
    return {rounded: r, ct: parts(r, "America/Chicago") + " CT", et: parts(r, "America/New_York") + " ET"};
  };
  window.cross41Update = function (live, official, asof) {
    var el = document.getElementById("cross41");
    if (!el) return;
    var level = 41e12;
    var preview = /(?:^|[?&])cross41=preview(?:&|$)/.test(location.search);
    var off = money(official, 2), when = asofText(asof);
    el.querySelectorAll("[data-cross=official]").forEach(function (n) { n.textContent = off; });
    el.querySelectorAll("[data-cross=asof]").forEach(function (n) { n.textContent = when; });
    el.querySelectorAll("[data-cross=live]").forEach(function (n) { n.textContent = money(Math.round(live), 0); });
    var overOff = official >= level, overLive = live >= level;
    var liveP = document.getElementById("cross41-live");
    var offP = document.getElementById("cross41-official");
    var preP = document.getElementById("cross41-preview");
    el.querySelectorAll("[data-cross=live-wrap]").forEach(function (n) { n.hidden = !overLive; });
    if (overOff) {
      el.hidden = false; el.classList.remove("preview");
      if (liveP) liveP.hidden = true; if (offP) offP.hidden = false; if (preP) preP.hidden = true;
    } else if (overLive) {
      el.hidden = false; el.classList.remove("preview");
      if (liveP) liveP.hidden = false; if (offP) offP.hidden = true; if (preP) preP.hidden = true;
    } else if (preview) {
      el.hidden = false; el.classList.add("preview");
      if (liveP) liveP.hidden = false; if (offP) offP.hidden = true; if (preP) preP.hidden = false;
    } else {
      el.hidden = true; el.classList.remove("preview");
    }
  };
})();
