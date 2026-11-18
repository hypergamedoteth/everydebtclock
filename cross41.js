/* Fills the $41 trillion banner in the browser. No network, no cookies.
   The sentences are not in the HTML. This file creates them only after the
   live clock passes $41 trillion, or when the address has ?cross41=preview.
   cross41Update(liveDollars, officialClose, asOfISO)
   cross41When(unixSeconds) -> {ct, et} rounded to the nearest second. */
(function () {
  var MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  var LEVEL = 41e12;
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
  function sentence(kind, off, when, live) {
    var level = "$" + "41" + " trillion";
    if (kind === "official") {
      return "<b>Treasury's figure is at or above " + level + ".</b> Debt to the Penny's " + when +
        " close was " + off + ". That is the official total. The digits still moving on this page are the live projection from that close. <a href=\"/press/\">Press figures</a>.";
    }
    var preview = kind === "preview" ? "<b>Preview.</b> This is not a report that the debt has crossed. " : "";
    var liveBit = live ? " (" + live + ")" : "";
    return preview + "<b>Live estimate, not Treasury's figure.</b> This clock is past " + level + liveBit +
      ". Treasury has not posted a Debt to the Penny close at that level. The latest official close is still " +
      off + " on " + when + ". Treasury posts the prior business day's close on the next business day, usually in the afternoon (around 3 PM Central). <a href=\"/press/\">Press figures</a>.";
  }
  window.cross41When = function (ts) {
    if (!(ts > 0)) return null;
    var r = Math.floor(ts + 0.5);
    return {rounded: r, ct: parts(r, "America/Chicago") + " CT", et: parts(r, "America/New_York") + " ET"};
  };
  window.cross41Update = function (live, official, asof) {
    var el = document.getElementById("cross41");
    if (!el) return;
    var preview = /(?:^|[?&])cross41=preview(?:&|$)/.test(location.search);
    var overOff = official >= LEVEL, overLive = live >= LEVEL;
    var kind = overOff ? "official" : (overLive || preview) ? (preview && !overLive ? "preview" : "live") : "";
    if (!kind) {
      el.hidden = true;
      el.classList.remove("preview");
      el.textContent = "";
      return;
    }
    el.hidden = false;
    el.classList.toggle("preview", kind === "preview");
    el.innerHTML = "<p>" + sentence(kind, money(official, 2), asofText(asof), overLive ? money(Math.round(live), 0) : "") + "</p>";
  };
})();
