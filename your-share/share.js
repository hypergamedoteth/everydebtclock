/* Your share of the US debt. All math is in this file, in the browser.
   Nothing here is stored, sent, or written to a cookie.

   Your share = latest official total public debt / US resident population.
   That is the official figure on /national-debt-per-person/, not the live projection.

   Birth year = Treasury Historical Debt Outstanding at that fiscal year end.
   Growth = latest official total / that fiscal-year-end total.
   Birth-year per person = that fiscal-year-end total / July 1 population, and only
   when that July 1 count is in the Census series. A missing year is left missing.

   State per person = official state debt total / state resident population
   (the state page's official basis, not its projected clock).

   Household = the per-person share times the size you type.
   Income years = that household total, or the per-person share, divided by the
   annual income you type. */
(function (root) {
  "use strict";

  function money(n, digits) {
    if (n == null || !isFinite(n)) return "—";
    var sign = n < 0 ? "−$" : "$";
    var s = Math.abs(n).toFixed(digits);
    var parts = s.split(".");
    var whole = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    return digits ? sign + whole + "." + parts[1] : sign + whole;
  }

  function moneyExact(n) {
    if (n == null || !isFinite(n)) return "—";
    var cents = Math.round(Math.abs(n) * 100);
    var sign = n < 0 ? "−$" : "$";
    var whole = Math.floor(cents / 100);
    var frac = cents % 100;
    var body = String(whole).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    if (!frac) return sign + body;
    return sign + body + "." + (frac < 10 ? "0" : "") + frac;
  }

  function times(m) {
    if (!(m > 0) || !isFinite(m)) return null;
    if (m >= 100) return m.toFixed(0);
    if (m >= 10) return m.toFixed(1);
    return m.toFixed(2);
  }

  function growthClause(m) {
    var t = times(m);
    if (!t) return "a growth multiple is not available for that total.";
    var n = parseFloat(t);
    if (n > 1) return "it has grown " + t + "× since.";
    if (n < 1) return "it is now " + t + "× that level.";
    return "it is about the same size.";
  }

  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function fdate(s) {
    if (!s || String(s).length < 10) return s || "";
    var y = +s.slice(0, 4), m = +s.slice(5, 7), d = +s.slice(8, 10);
    if (!y || !m || !d) return s;
    return MONTHS[m - 1] + " " + d + ", " + y;
  }

  function commas(n) {
    return Math.round(n).toLocaleString("en-US");
  }

  function numOrNull(raw) {
    if (raw == null) return null;
    var s = String(raw).replace(/[$,\s]/g, "");
    if (!s) return null;
    var n = Number(s);
    return isFinite(n) ? n : NaN;
  }

  function compute(D, q) {
    q = q || {};
    var share = D.debt / D.population;
    var r = {
      share: share,
      year: null,
      yearError: "",
      yearMissing: false,
      yearDebt: null,
      yearDebtDate: null,
      yearPop: null,
      yearSeries: null,
      yearPer: null,
      yearPopMissing: false,
      multiple: null,
      state: null,
      stateError: "",
      household: null,
      hhError: "",
      income: null,
      incomeError: "",
      incomeYears: null
    };
    var bornRaw = q.born == null ? "" : String(q.born).trim();
    if (bornRaw) {
      if (!/^\d{4}$/.test(bornRaw)) {
        r.yearError = "Enter a four-digit birth year, or leave it blank.";
      } else {
        var y = +bornRaw;
        r.year = y;
        var row = D.years[bornRaw];
        if (!row) {
          r.yearMissing = true;
        } else {
          r.yearDebt = row[0];
          r.yearDebtDate = row[1];
          if (row[0] > 0) r.multiple = D.debt / row[0];
          if (row[2] == null) r.yearPopMissing = true;
          else {
            r.yearPop = row[2];
            r.yearSeries = row[3];
            r.yearPer = row[0] / row[2];
          }
        }
      }
    }
    var stateRaw = q.state ? String(q.state).trim().toLowerCase() : "";
    if (stateRaw) {
      var st = null;
      for (var i = 0; i < D.states.length; i++) if (D.states[i].slug === stateRaw) st = D.states[i];
      if (!st) r.stateError = "That state is not in the state debt files on this site.";
      else r.state = st;
    }
    var hhRaw = q.hh == null ? "" : String(q.hh).trim();
    if (hhRaw) {
      var hh = numOrNull(hhRaw);
      if (!isFinite(hh) || Math.round(hh) !== hh || hh < 1 || hh > 20) {
        r.hhError = "Enter a household size from 1 to 20, or leave it blank.";
      } else {
        r.household = share * hh;
        r.hh = hh;
      }
    }
    var incRaw = q.income == null ? "" : String(q.income).trim();
    if (incRaw) {
      var inc = numOrNull(incRaw);
      if (!isFinite(inc) || inc <= 0 || inc > 1e9) {
        r.incomeError = "Enter an annual income from $1 to $1 billion, or leave it blank.";
      } else {
        r.income = inc;
        var base = r.household != null ? r.household : share;
        r.incomeYears = base / inc;
      }
    }
    return r;
  }

  function sentence(r) {
    var s = "Your share of the US debt: " + money(r.share, 2) + ".";
    if (r.yearError || !r.year) return s;
    if (r.yearMissing) {
      return s + " Historical Debt Outstanding on this site does not include " + r.year + ", so the debt that year is not shown. We don't estimate it.";
    }
    s += " When you were born (" + r.year + ") the debt was " + moneyExact(r.yearDebt) + "; " + growthClause(r.multiple);
    return s;
  }

  function popMissingText(D, r) {
    var latest = D.popLatest;
    var tail = latest ? " The latest July 1 estimate in that series is " + latest + "." : "";
    return "There is no July 1 resident population for " + r.year + " in the Census series this site uses, so there is no per-person figure for that year. We don't estimate one." + tail;
  }

  function shortTimes(m) {
    var t = times(m);
    return t ? t + "×" : "—";
  }

  /* Canvas card. Wide is 1200×630, square is 1200×1200. System fonts; the
     pre-rendered PNG uses the same layout in DejaVu for crawlers. */
  function roundRect(ctx, x, y, w, h, rad) {
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(x, y, w, h, rad);
    else {
      var r = Math.min(rad, w / 2, h / 2);
      ctx.moveTo(x + r, y);
      ctx.arcTo(x + w, y, x + w, y + h, r);
      ctx.arcTo(x + w, y + h, x, y + h, r);
      ctx.arcTo(x, y + h, x, y, r);
      ctx.arcTo(x, y, x + w, y, r);
      ctx.closePath();
    }
  }

  function fit(ctx, text, weight, max, start) {
    var size = start;
    while (size > 18) {
      ctx.font = weight + " " + size + "px ui-monospace, Menlo, Consolas, monospace";
      if (ctx.measureText(text).width <= max) return size;
      size -= 2;
    }
    return size;
  }

  function chipModel(D, r) {
    if (r.year && !r.yearError && !r.yearMissing) {
      return [
        ["DEBT IN " + r.year, moneyExact(r.yearDebt)],
        ["SINCE THEN", shortTimes(r.multiple)]
      ];
    }
    return [
      ["TOTAL PUBLIC DEBT", moneyExact(D.debt)],
      ["US RESIDENTS", commas(D.population)]
    ];
  }

  function noteLines(D, r) {
    var lines = [
      "Treasury Debt to the Penny, " + fdate(D.debtDate),
      "÷ Census residents, " + fdate(D.populationDate)
    ];
    if (r.state) lines.push(r.state.name + ": " + money(r.state.debt / r.state.pop, 2) + " per " + r.state.demonym);
    if (r.household != null) lines.push("Household of " + r.hh + ": " + money(r.household, 2));
    if (r.incomeYears != null) lines.push(times(r.incomeYears) + " years of " + moneyExact(r.income));
    return lines;
  }

  function drawCard(canvas, D, r) {
    var square = canvas.dataset.variant === "sq";
    var W = 1200, H = square ? 1200 : 630;
    canvas.width = W;
    canvas.height = H;
    var ctx = canvas.getContext("2d");
    ctx.fillStyle = "#07090d";
    ctx.fillRect(0, 0, W, H);
    var g = ctx.createLinearGradient(0, 0, 0, 380);
    g.addColorStop(0, "#142033");
    g.addColorStop(1, "#07090d");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, 380);
    ctx.fillStyle = "#ff4d5e";
    ctx.fillRect(0, 0, W, 10);

    function wordmark(y) {
      ctx.font = "800 30px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
      var x = 60;
      ctx.fillStyle = "#e8edf5";
      ctx.fillText("EVERY ", x, y);
      x += ctx.measureText("EVERY ").width;
      ctx.fillStyle = "#ff4d5e";
      ctx.fillText("DEBT ", x, y);
      x += ctx.measureText("DEBT ").width;
      ctx.fillStyle = "#e8edf5";
      ctx.fillText("CLOCK", x, y);
    }
    wordmark(square ? 90 : 78);
    ctx.fillStyle = "#38d39f";
    ctx.beginPath();
    ctx.arc(W - 188, square ? 80 : 68, 7, 0, Math.PI * 2);
    ctx.fill();
    ctx.font = "800 24px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
    ctx.fillText("OFFICIAL", W - 172, square ? 88 : 76);

    var title = r.year && !r.yearMissing && !r.yearError ? "Born in " + r.year : "Your share of the US debt";
    ctx.fillStyle = "#c9d3e2";
    ctx.font = "700 " + (square ? 48 : 40) + "px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
    ctx.fillText(title, 60, square ? 190 : 155);

    var big = money(r.share, 2);
    var bigSize = fit(ctx, big, "700", W - 140, square ? 112 : 92);
    ctx.font = "700 " + bigSize + "px ui-monospace, Menlo, Consolas, monospace";
    ctx.fillStyle = "#ffffff";
    ctx.fillText(big, 56, square ? 330 : 265);

    var chips = chipModel(D, r);
    var notes = noteLines(D, r);
    var chipW = square ? W - 120 : 540;
    var chipH = square ? 120 : 78;
    var top = square ? 400 : 330;
    chips.forEach(function (c, i) {
      var cy = top + i * (chipH + (square ? 18 : 12));
      ctx.fillStyle = "#121925";
      roundRect(ctx, 60, cy, chipW, chipH, 12);
      ctx.fill();
      ctx.fillStyle = "#8a97ab";
      ctx.font = "700 18px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
      ctx.fillText(c[0], 82, cy + (square ? 42 : 30));
      var vs = fit(ctx, c[1], "700", chipW - 48, square ? 40 : 32);
      ctx.font = "700 " + vs + "px ui-monospace, Menlo, Consolas, monospace";
      ctx.fillStyle = "#ffffff";
      ctx.fillText(c[1], 82, cy + (square ? 92 : 62));
    });
    ctx.fillStyle = "#8a97ab";
    ctx.font = "400 " + (square ? 28 : 24) + "px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
    var nx = square ? 60 : 640;
    var ny = square ? top + chips.length * (chipH + 18) + 36 : 360;
    notes.forEach(function (line, i) {
      ctx.fillText(line, nx, ny + i * (square ? 40 : 34));
    });

    ctx.fillStyle = "#5aa9ff";
    ctx.font = "700 24px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
    ctx.fillText("everydebtclock.com/your-share/", 60, H - 42);
    ctx.fillStyle = "#5c687a";
    ctx.font = "400 20px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
    var foot = "Not a bill";
    ctx.fillText(foot, W - 60 - ctx.measureText(foot).width, H - 42);
    return canvas;
  }

  function sharePath(D, q) {
    var y = q.born && /^\d{4}$/.test(String(q.born).trim()) ? String(q.born).trim() : "";
    var params = new URLSearchParams();
    if (q.state) params.set("state", String(q.state).trim().toLowerCase());
    if (q.hh) params.set("hh", String(q.hh).trim());
    if (q.income) params.set("income", String(q.income).replace(/[$,\s]/g, ""));
    var og = y && D.years[y] && +y >= D.ogMin && +y <= D.ogMax;
    if (!og && y) params.set("born", y);
    var qs = params.toString();
    var path = og ? "/your-share/born/" + y + "/" : "/your-share/";
    return path + (qs ? "?" + qs : "");
  }

  function queryPath(q) {
    var params = new URLSearchParams();
    var path = location.pathname.endsWith("/") ? location.pathname : location.pathname + "/";
    var onYear = /\/born\/\d{4}\/$/.test(path);
    if (!onYear && q.born && String(q.born).trim()) params.set("born", String(q.born).trim());
    if (q.state) params.set("state", String(q.state).trim().toLowerCase());
    if (q.hh && String(q.hh).trim()) params.set("hh", String(q.hh).trim());
    if (q.income && String(q.income).trim()) params.set("income", String(q.income).replace(/[$,\s]/g, ""));
    var qs = params.toString();
    return path + (qs ? "?" + qs : "");
  }

  function readForm(form) {
    return {
      born: form.born.value,
      state: form.state.value,
      hh: form.hh.value,
      income: form.income.value
    };
  }

  function el(tag, text, cls) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function linkLine(prefix, links) {
    var p = el("p", null);
    p.appendChild(document.createTextNode(prefix));
    links.forEach(function (pair, i) {
      if (i) p.appendChild(document.createTextNode(" · "));
      var a = document.createElement("a");
      a.href = pair[1];
      a.rel = "noopener";
      a.textContent = pair[0];
      p.appendChild(a);
    });
    return p;
  }

  function render(D, r) {
    document.getElementById("share-num").textContent = money(r.share, 2);
    document.getElementById("asof").textContent = "As of Treasury's " + fdate(D.debtDate) + " close · Census population " + fdate(D.populationDate);
    document.getElementById("sentence").textContent = sentence(r);
    var box = document.getElementById("details");
    box.replaceChildren();
    if (r.yearError) box.appendChild(el("p", r.yearError, "miss"));
    if (r.year && !r.yearError && !r.yearMissing) {
      box.appendChild(el("p", "The debt in " + r.year + " is Treasury's total public debt at the end of fiscal year " + r.year + " (" + fdate(r.yearDebtDate) + "), from Historical Debt Outstanding. It is not the debt on a particular birthday. Growth is the " + fdate(D.debtDate) + " close divided by that total: " + moneyExact(D.debt) + " ÷ " + moneyExact(r.yearDebt) + " = " + (times(r.multiple) || "—") + "×."));
      if (r.yearPopMissing) box.appendChild(el("p", popMissingText(D, r), "miss"));
      else {
        var src = (D.popSources && D.popSources[r.yearSeries]) || null;
        box.appendChild(el("p", "Per person in fiscal year " + r.year + " was " + money(r.yearPer, 2) + ": " + moneyExact(r.yearDebt) + " ÷ " + commas(r.yearPop) + " residents on July 1, " + r.year + (src ? " (" + src[0] + ")" : "") + ". The two dates are not the same day. This is the same division as the by-year table on the per-person page."));
      }
    }
    if (r.yearMissing) box.appendChild(el("p", "Historical Debt Outstanding on this site has no total for " + r.year + ". Nothing is filled in for that year.", "miss"));
    if (r.stateError) box.appendChild(el("p", r.stateError, "miss"));
    if (r.state) {
      var per = r.state.debt / r.state.pop;
      box.appendChild(el("p", r.state.name + " " + r.state.label + " per " + r.state.demonym + " is " + money(per, 2) + ": " + moneyExact(r.state.debt) + " official as of " + fdate(r.state.debtDate) + ", divided by " + commas(r.state.pop) + " residents on " + fdate(r.state.popDate) + ". This is the state page's official basis, not its projected clock, and it is not a different share of the federal debt. The federal share above is the same in every state."));
      var links = (r.state.debtSources || []).concat(r.state.popSource ? [r.state.popSource] : []);
      if (links.length) box.appendChild(linkLine("Sources for " + r.state.name + ": ", links));
    }
    if (r.yearPer != null && D.popSources && D.popSources[r.yearSeries]) {
      box.appendChild(linkLine("Population series for " + r.year + ": ", [D.popSources[r.yearSeries]]));
    }
    if (r.hhError) box.appendChild(el("p", r.hhError, "miss"));
    if (r.household != null) {
      box.appendChild(el("p", "A household of " + r.hh + " is " + r.hh + " × the per-person share, " + money(r.household, 2) + ". That is the size you entered times one equal share. It is not Census's per-household figure, which divides the same debt by the household count (" + commas(D.households.count) + " households, " + money(D.debt / D.households.count, 2) + ")."));
    }
    if (r.incomeError) box.appendChild(el("p", r.incomeError, "miss"));
    if (r.incomeYears != null) {
      var basis = r.household != null ? "the household total above" : "the per-person share";
      box.appendChild(el("p", basis.charAt(0).toUpperCase() + basis.slice(1) + " equals " + times(r.incomeYears) + " years of the " + moneyExact(r.income) + " annual income you entered (" + money(r.household != null ? r.household : r.share, 2) + " ÷ " + moneyExact(r.income) + "). That income is only what you typed. It is not a published statistic, and it is not stored."));
    }

    var worked = document.getElementById("worked");
    if (worked) {
      worked.replaceChildren();
      function row(a, b, c) {
        var tr = document.createElement("tr");
        tr.appendChild(el("td", a));
        var nb = el("td", b);
        nb.className = "num";
        tr.appendChild(nb);
        tr.appendChild(el("td", c));
        worked.appendChild(tr);
      }
      row("Your share", money(r.share, 2), moneyExact(D.debt) + " ÷ " + commas(D.population));
      if (r.year && !r.yearMissing && !r.yearError) {
        row("Debt in " + r.year, moneyExact(r.yearDebt), "FY" + r.year + " end, " + fdate(r.yearDebtDate));
        row("Growth", shortTimes(r.multiple), moneyExact(D.debt) + " ÷ " + moneyExact(r.yearDebt));
        if (r.yearPer != null) row("Per person then", money(r.yearPer, 2), moneyExact(r.yearDebt) + " ÷ " + commas(r.yearPop));
      }
      if (r.state) row(r.state.name, money(r.state.debt / r.state.pop, 2), moneyExact(r.state.debt) + " ÷ " + commas(r.state.pop));
      if (r.household != null) row("Household of " + r.hh, money(r.household, 2), r.hh + " × " + money(r.share, 2));
      if (r.incomeYears != null) row("Years of entered income", times(r.incomeYears), money(r.household != null ? r.household : r.share, 2) + " ÷ " + moneyExact(r.income));
    }

    var personalized = !!(r.state || r.household != null || r.incomeYears != null);
    var img = document.getElementById("preview");
    var canvas = document.getElementById("card");
    var yearOk = r.year && !r.yearMissing && !r.yearError && r.year >= D.ogMin && r.year <= D.ogMax && D.years[String(r.year)];
    if (!personalized && (yearOk || !r.year)) {
      canvas.hidden = true;
      img.hidden = false;
      var file = yearOk ? r.year + ".png" : "default.png";
      img.src = "/your-share/og/" + file;
      img.alt = sentence(r);
    } else {
      img.hidden = true;
      canvas.hidden = false;
      canvas.dataset.variant = "wide";
      drawCard(canvas, D, r);
      canvas.setAttribute("aria-label", sentence(r));
    }
    var wide = document.getElementById("dl-wide");
    var sq = document.getElementById("dl-sq");
    if (yearOk && !personalized) {
      wide.href = "/your-share/og/" + r.year + ".png";
      sq.href = "/your-share/og/" + r.year + "-sq.png";
    } else if (!r.year && !personalized) {
      wide.href = "/your-share/og/default.png";
      sq.href = "/your-share/og/default-sq.png";
    }
    wide.dataset.mode = personalized ? "canvas" : "file";
    sq.dataset.mode = personalized ? "canvas" : "file";
    document.getElementById("link").value = D.site.replace(/\/$/, "") + sharePath(D, readForm(document.getElementById("f")));
  }

  function canvasFile(D, r, variant, name) {
    var c = document.createElement("canvas");
    c.dataset.variant = variant;
    drawCard(c, D, r);
    return new Promise(function (resolve) {
      c.toBlob(function (blob) { resolve(new File([blob], name, {type: "image/png"})); }, "image/png");
    });
  }

  function downloadBlob(blob, name) {
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1500);
  }

  function mount(D) {
    var form = document.getElementById("f");
    var pageYear = document.body.dataset.born || "";
    function current() { return readForm(form); }
    function paint() {
      var q = current();
      if (pageYear && q.born && /^\d{4}$/.test(q.born.trim()) && q.born.trim() !== pageYear) {
        location.assign(sharePath(D, q));
        return;
      }
      render(D, compute(D, q));
      var next = queryPath(q);
      if (next !== location.pathname + location.search) history.replaceState(null, "", next);
    }
    var params = new URLSearchParams(location.search);
    if (!form.born.value && (params.get("born") || pageYear)) form.born.value = params.get("born") || pageYear;
    if (params.get("state")) form.state.value = params.get("state");
    if (params.get("hh")) form.hh.value = params.get("hh");
    if (params.get("income")) form.income.value = params.get("income");
    form.addEventListener("input", paint);
    form.addEventListener("submit", function (e) { e.preventDefault(); paint(); });
    document.getElementById("copy").addEventListener("click", function () {
      var v = document.getElementById("link").value;
      var btn = document.getElementById("copy");
      function done() { btn.textContent = "Copied"; setTimeout(function () { btn.textContent = "Copy link"; }, 1500); }
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(v).then(done, function () { done(); });
      else done();
    });
    document.getElementById("x").addEventListener("click", function (e) {
      e.preventDefault();
      var r = compute(D, current());
      var text = sentence(r);
      var url = document.getElementById("link").value;
      window.open("https://x.com/intent/post?text=" + encodeURIComponent(text) + "&url=" + encodeURIComponent(url), "_blank", "noopener");
    });
    function onDownload(ev, variant) {
      var btn = ev.currentTarget;
      if (btn.dataset.mode !== "canvas") return;
      ev.preventDefault();
      var r = compute(D, current());
      var name = variant === "sq" ? "your-share-square.png" : "your-share.png";
      canvasFile(D, r, variant, name).then(function (file) { downloadBlob(file, name); });
    }
    document.getElementById("dl-wide").addEventListener("click", function (e) { onDownload(e, "wide"); });
    document.getElementById("dl-sq").addEventListener("click", function (e) { onDownload(e, "sq"); });
    document.getElementById("native").addEventListener("click", function () {
      var r = compute(D, current());
      var url = document.getElementById("link").value;
      var text = sentence(r);
      function plain() {
        if (navigator.share) navigator.share({title: "Your share of the US debt", text: text, url: url}).catch(function () {});
      }
      var wantFile = document.getElementById("dl-wide").dataset.mode === "canvas";
      if (!wantFile) { plain(); return; }
      canvasFile(D, r, "wide", "your-share.png").then(function (file) {
        if (navigator.canShare && navigator.canShare({files: [file]})) {
          navigator.share({files: [file], title: "Your share of the US debt", text: text, url: url}).catch(function () {});
        } else plain();
      });
    });
    if (!navigator.share) document.getElementById("native").hidden = true;
    paint();
  }

  root.EDCShare = {
    compute: compute,
    sentence: sentence,
    money: money,
    moneyExact: moneyExact,
    times: times,
    growthClause: growthClause,
    fdate: fdate,
    sharePath: sharePath,
    popMissingText: popMissingText,
    drawCard: drawCard
  };

  if (typeof document === "undefined") return;
  function start() {
    var status = document.getElementById("status");
    fetch("/your-share/data.json", {credentials: "omit", cache: "no-store"}).then(function (res) {
      if (!res.ok) throw new Error("bad status");
      return res.json();
    }).then(function (D) {
      if (status) status.remove();
      mount(D);
    }).catch(function () {
      if (status) status.textContent = "The figures could not be loaded. Refresh the page. Nothing was estimated.";
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})(typeof window !== "undefined" ? window : globalThis);
