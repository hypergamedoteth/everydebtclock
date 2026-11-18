"""Milestone, president, per-person, and interest pages.

The live figure is the first block. The summary sits directly under it.
Numbers come from cache/history_pages.json (Treasury and Census) and from the
same debt_total base and per-second rate the homepage clock uses.

Add a future countdown by appending its trillion level to MILESTONE_PAGES.
"""
import datetime as dt, html, json, os
from zoneinfo import ZoneInfo

import explore

CT = ZoneInfo("America/Chicago")
# /41-trillion/ now. A crossed page counts toward the next trillion on its own;
# listing the next level here is what publishes /42-trillion/.
MILESTONE_PAGES = [41]

TOPIC_CSS = """
:root{--bg:#07090d;--panel:#121925;--panel2:#121925;--line:#1c2533;--txt:#e8edf5;--mut:#8a97ab;--dim:#5c687a;--red:#ff4d5e;--blue:#5aa9ff;--green:#38d39f}
body{margin:0;background:#07090d;color:var(--txt);font-family:-apple-system,BlinkMacSystemFont,Inter,Segoe UI,Roboto,sans-serif;line-height:1.5}
main{max-width:920px;margin:0 auto;padding:8px 16px 48px}a{color:#5aa9ff;text-decoration:none}
.brand{font-weight:800;letter-spacing:.06em;font-size:14px;display:inline-block;margin:8px 0 4px}.brand b{color:#ff4d5e}
h1{font-size:22px;margin:0 0 6px}h2{font-size:17px;margin:22px 0 6px}
p{color:#c2ccda;font-size:15px;margin:0 0 10px}
.hero{border:1px solid var(--line);background:linear-gradient(180deg,#101828,#0b0f16);border-radius:18px;padding:16px 16px 14px;margin:8px 0 0}
.hero .k{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--mut);margin:0}
.hero .big{font:700 clamp(22px,5.4vw,56px)/1.05 ui-monospace,Menlo,monospace;font-variant-numeric:tabular-nums;color:#fff;margin:6px 0 2px}
.hero .sub{color:#c2ccda;font-size:14.5px;margin:4px 0 0}
.trio{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:12px}
.trio div{background:rgba(255,255,255,.03);border:1px solid var(--line);border-radius:12px;padding:8px 10px}
.trio .l{display:block;font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em}
.trio .n{font:600 clamp(15px,3vw,22px) ui-monospace,Menlo,monospace}
.intro{margin:12px 2px 4px}
table{border-collapse:collapse;width:100%;font-size:13.5px;margin:8px 0 14px}
th,td{border-bottom:1px solid #1c2533;padding:6px 8px;text-align:left;vertical-align:top}
th{color:#8a97ab;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.05em}
td.num{font-family:ui-monospace,Menlo,monospace;text-align:right;white-space:nowrap}
td .when{display:block;color:#8a97ab;font-size:12px;font-weight:400;white-space:normal}
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch}
.note{border:1px solid #5a3a12;background:#20170a;color:#ffb547;border-radius:10px;padding:10px 12px;font-size:13.5px}
.cta{display:inline-block;margin:14px 0;background:#ff4d5e;color:#fff;border-radius:10px;padding:10px 16px;font-weight:700}
details summary{cursor:pointer;color:#5aa9ff;margin:8px 0}
.rel a{display:inline-block;margin:4px 10px 4px 0;font-size:13.5px}
footer{color:#5c687a;font-size:12px;margin-top:28px}
.faq h2{font-size:17px;margin:22px 0 6px}.faq h3{font-size:16px;margin:16px 0 4px}.faq p{margin:0 0 8px}
.srchrow{max-width:920px;margin:0 auto;padding:8px 16px 0}
@media (max-width:560px){.trio{grid-template-columns:1fr}}
"""

COUNT_JS = r"""
<script>
(function(){
  const C = DC(window.DEBTCLOCK_DATA);
  const lead = document.getElementById('lead');
  const mode = lead.dataset.mode;
  const k = document.getElementById('lead-k'), v = document.getElementById('lead-v'), sub = document.getElementById('lead-sub');
  const usd0 = n => (n == null || !isFinite(n)) ? '—' : (n < 0 ? '−$' : '$') + Math.abs(Math.round(n)).toLocaleString('en-US');
  const usd2 = n => (n == null || !isFinite(n)) ? '—' : (n < 0 ? '−$' : '$') + Math.abs(n).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  function tick(){
    const t = Date.now() / 1000;
    if (mode === 'debt') {
      v.textContent = usd0(C.val('debt_total', t));
    } else if (mode === 'person') {
      const d = C.val('debt_total', t), pop = C.pop(t), per = usd2(d / pop);
      v.textContent = per;
      const p = document.getElementById('pp-p'), h = document.getElementById('pp-h'), r = document.getElementById('pp-r');
      if (p) p.textContent = per;
      if (h) h.textContent = usd2(d / C.T.households.base);
      if (r) r.textContent = usd2(d / C.tax);
    } else if (mode === 'interest') {
      v.textContent = usd0(C.val('interest_cash', t));
    } else if (mode === 'count') {
      const d = C.val('debt_total', t);
      const target = +lead.dataset.target, next = +lead.dataset.next, rate = +lead.dataset.rate;
      const official = lead.dataset.passed === '1';
      const over = official || d >= target;
      const nextOk = lead.dataset.nextOk === '1';
      if (over && !nextOk) {
        k.textContent = official ? ('The debt passed $' + lead.dataset.level + ' trillion on ' + lead.dataset.passedDate) : 'The running total passed $' + lead.dataset.level + ' trillion';
        v.textContent = usd0(d);
        sub.textContent = lead.dataset.hold;
      } else if (over) {
        const left = next - d;
        v.textContent = usd0(Math.max(left, 0));
        k.textContent = official ? ('The debt passed $' + lead.dataset.level + ' trillion on ' + lead.dataset.passedDate) : 'The running total passed $' + lead.dataset.level + ' trillion';
        sub.textContent = rate > 0 ? ('$' + lead.dataset.nextLevel + ' trillion is ' + countdown(left / rate) + ' out · ' + usd0(d) + ' now') : (usd0(d) + ' now');
      } else if (!(rate > 0)) {
        v.textContent = usd0(Math.max(target - d, 0));
        sub.textContent = 'No projected date while the debt is not growing · ' + usd0(d) + ' now';
      } else {
        const left = target - d;
        v.textContent = usd0(Math.max(left, 0));
        sub.textContent = countdown(left / rate) + ' · ' + lead.dataset.when + ' · ' + usd0(d) + ' now';
      }
    }
    requestAnimationFrame(tick);
  }
  function countdown(sec){
    if (!(sec >= 0)) return 'at the level';
    const s = Math.floor(sec), dd = Math.floor(s / 86400), hh = Math.floor(s % 86400 / 3600), mm = Math.floor(s % 3600 / 60), ss = s % 60;
    return dd + 'd ' + hh + 'h ' + mm + 'm ' + ss + 's';
  }
  requestAnimationFrame(tick);
})();
</script>
"""


def _ord(n):
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _load(R):
    p = os.path.join(R, "cache", "history_pages.json")
    if not os.path.exists(p):
        raise SystemExit("topics: cache/history_pages.json is missing. Run python3 pipeline/series.py")
    return json.load(open(p))["data"]


def _clock(T, keys, meta):
    blob = {"tickers": {k: T[k] for k in keys if k in T}, "meta": {"fy_end_epoch": meta["fy_end_epoch"], "fy": meta["fy"]}, "derived": {}}
    return json.dumps(blob, separators=(",", ":")).replace("</", "<\\/")


def _page(ctx, slug, title, desc, ld, hero, intro, body, faqs=None):
    R, SITE, E = ctx["R"], ctx["SITE"], html.escape
    url = f"{SITE}/{slug}/"
    more = "".join(f'<a href="../{a}/">{E(t)}</a>' for a, t in ctx["ANSWERS"] if a != slug)
    places, calc, gdp = ctx["places"], ctx["calc"], ctx["gdp"]
    related = explore.explore("../", places, calc, topic=slug, gdp=gdp) if places else ""
    search = explore.search_box("../") if places else ""
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}"><link rel="canonical" href="{url}">
<meta property="og:type" content="article"><meta property="og:site_name" content="Every Debt Clock"><meta property="og:url" content="{url}">
<meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc)}">
<meta property="og:image" content="{SITE}/og/home.png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{E(title)}">
<meta name="twitter:description" content="{E(desc)}"><meta name="twitter:image" content="{SITE}/og/home.png">
<meta name="theme-color" content="#07090d"><link rel="apple-touch-icon" href="../apple-touch-icon.png">
<style>{TOPIC_CSS}{explore.CSS}</style>
{ld}</head><body>
{search}
<main>
<a class="brand" href="../">EVERY <b>DEBT</b> CLOCK</a><a class="navembed" href="../embed/" style="margin-left:12px;font-size:13px;font-weight:650">Embed</a>
{hero}
<section class="intro" id="intro">{intro}</section>
{body}
{_faq_html(faqs) if faqs else ""}
<a class="cta" href="../">Open the live national debt clock →</a>
{related}
<div class="rel"><b>More answers:</b><br>{more}<a href="../t/debt_total.html">US national debt, live</a></div>
<footer class="site-foot">The figure at the top uses the same Treasury base and per-second rate as the homepage clock. Other figures are official records unless a line says projected. Built {E(ctx["STAMP"])}. · <a href="../methodology/">Methodology</a> · <a href="../privacy/">Privacy</a> · Independent site, not affiliated with the U.S. government. Not financial advice.</footer>
</main>
<script>window.DEBTCLOCK_DATA={ctx["clock"]};</script><script src="../core.js"></script>
{COUNT_JS}
</body></html>"""
    os.makedirs(os.path.join(R, slug), exist_ok=True)
    open(os.path.join(R, slug, "index.html"), "w").write(ctx["with_analytics"](doc))


def _hit_ts(base, rate, t0, freeze, target):
    if not rate or rate <= 0 or base >= target:
        return None
    ts = t0 + (target - base) / rate
    if freeze and ts > freeze:
        return None
    return ts


def _when_label(ts):
    if not ts:
        return None
    d = dt.datetime.fromtimestamp(ts, CT)
    return d.strftime("%B %-d, %Y")


def _faq_html(pairs):
    return ('<section class="faq" id="faq"><h2>Questions</h2>'
            + "".join(f"<h3>{html.escape(q)}</h3><p>{html.escape(a)}</p>" for q, a in pairs)
            + "</section>")


def interest_day_answer(T, val, now, fdate, usd0, bil, built_label):
    """Plain answer for 'how much interest per day'.

    Two figures the site already computes, kept distinct:
    - interest cost per day: projected debt × Treasury's average rate on
      interest-bearing debt ÷ 365.25 (the homepage tile)
    - accrual run-rate: the interest-expense dataset's last 12 reported
      months, spread over a year (rate × 86,400, same number the interest page prints)
    Neither is cash paid on one calendar day.
    """
    debt = val("debt_total", now) if val else None
    rate = T.get("rate_all") or {}
    ig = T.get("interest_gross") or {}
    bits = []
    if debt and rate.get("base") is not None:
        per = debt * rate["base"] / 100 / 365.25
        bits.append(
            f"The clock's interest cost per day is {usd0(per)} as of {built_label}. "
            f"That is the national debt projected from Treasury's Debt to the Penny, times the {rate['base']:.2f}% average rate "
            f"on interest-bearing debt as of {fdate(rate.get('as_of'))}, divided by 365.25."
        )
    if ig.get("status") == "ok" and ig.get("ttm") and ig.get("rate") and ig.get("as_of"):
        bits.append(
            f"Treasury's interest-expense dataset totaled {usd0(ig['ttm'])} in the 12 months ending {fdate(ig['as_of'])}, "
            f"about {bil(ig['rate'] * 86400)} a day on an accrual basis."
        )
    if not bits:
        return None
    bits.append("Neither figure is the cash paid on a single day. Cash interest is paid in lumps.")
    return " ".join(bits)


def milestone_state(ctx, H, n):
    """Countdown facts for $n trillion. `summary` is the sentence on /{n}-trillion/.
    `quote` is that sentence without the words that point at the hero on that page."""
    T = ctx["T"]["debt_total"]
    base, t0 = T["base"], T["t0"]
    live_rate = T["rate"]
    freeze = T.get("freeze_t")
    fdate, usd0, usd2, bil = ctx["fdate"], ctx["usd0"], ctx["usd2"], ctx["bil"]
    now = ctx["NOW"]
    debt_now = ctx["val"]("debt_total", now)
    by_n = {c["trillion"]: c for c in H["crossings"]}
    target = n * 1e12
    nxt = (n + 1) * 1e12
    official = by_n.get(n)
    passed = official is not None or (debt_now is not None and debt_now >= target)
    per_day = live_rate * 86400
    lim = (ctx["T"].get("debt_limit") or {}).get("base")
    subj_t = ctx["T"].get("debt_subject_limit") or {}
    not_subj = ctx["OFF_V"] - subj_t["base"] if subj_t.get("base") and subj_t.get("as_of") == ctx["OFF_D"] else None
    total_at_limit = lim + not_subj if lim and not_subj is not None else None
    next_ok = (nxt < total_at_limit) if total_at_limit is not None else (_hit_ts(base, live_rate, t0, freeze, nxt) is not None)
    goal_ts = _hit_ts(base, live_rate, t0, freeze, nxt if passed and next_ok else target)
    when = _when_label(goal_ts)
    lim_when = _when_label(freeze) if freeze else None
    hold = (f"The statutory limit would bind before ${n+1} trillion. Once it binds, the clock holds at the official figure. "
            f"It counts toward ${n+1} trillion only if Congress raises or suspends the limit.")
    if official and next_ok:
        kicker = f"The debt passed ${n} trillion on {fdate(official['date'])}"
        passed_date = fdate(official["date"])
        title = f"The US Debt Passed ${n} Trillion on {fdate(official['date'])}"
        left = nxt - (debt_now if debt_now is not None else base)
        quote = (f"The debt passed ${n} trillion on {fdate(official['date'])}, when Treasury's close was {usd2(official['amount'])}. "
                 + (f"At the same per-second rate as the homepage clock, about {bil(per_day)} a day, ${n+1} trillion falls on {when}."
                    if when else f"The homepage clock is not projecting a date for ${n+1} trillion."))
        summary = (f"The debt passed ${n} trillion on {fdate(official['date'])}, when Treasury's close was {usd2(official['amount'])}. "
                   f"The figure above is what is left until ${n+1} trillion, at the same per-second rate as the homepage clock"
                   + (f", about {bil(per_day)} a day. That next level falls on {when}." if when else "."))
        h1 = f"The debt passed ${n} trillion on {fdate(official['date'])}"
    elif official:
        kicker = f"The debt passed ${n} trillion on {fdate(official['date'])}"
        passed_date = fdate(official["date"])
        title = f"The US Debt Passed ${n} Trillion on {fdate(official['date'])}"
        left = debt_now if debt_now is not None else base
        quote = (f"The debt passed ${n} trillion on {fdate(official['date'])}, when Treasury's close was {usd2(official['amount'])}. {hold}")
        summary = quote
        h1 = f"The debt passed ${n} trillion on {fdate(official['date'])}"
    elif debt_now is not None and debt_now >= target:
        kicker = f"The running total passed ${n} trillion"
        passed_date = ""
        title = f"When Will the US Debt Hit ${n} Trillion? Live Countdown"
        left = (nxt - debt_now) if next_ok else debt_now
        quote = (f"The running total is past ${n} trillion. Treasury has not published that close yet, so there is no Treasury date for it. "
                 + (f"At the homepage clock's pace, about {bil(per_day)} a day, ${n+1} trillion falls on {when}." if next_ok and when else
                    (f"The countdown toward ${n+1} trillion uses the homepage clock's pace." if next_ok else hold)))
        summary = (f"The running total is past ${n} trillion. Treasury has not published that close yet, so this page does not give it a date. "
                   + (f"The figure above counts what is left until ${n+1} trillion." if next_ok else hold))
        h1 = f"When will the US debt hit ${n} trillion?"
    else:
        kicker = f"Left until ${n} trillion"
        passed_date = ""
        left = target - (debt_now if debt_now is not None else base)
        title = f"When Will the US Debt Hit ${n} Trillion? Live Countdown"
        if when:
            quote = (f"The debt was {usd2(ctx['OFF_V'])} as of {fdate(ctx['OFF_D'])}, {bil(target - ctx['OFF_V'])} short of ${n} trillion. "
                     f"At the homepage clock's 90-day pace, about {bil(per_day)} a day, ${n} trillion falls on {when}. "
                     f"It is a projection, not a Treasury forecast.")
            summary = quote + " The figure above is what is left after projecting forward from that close."
        else:
            quote = (f"The debt was {usd2(ctx['OFF_V'])} as of {fdate(ctx['OFF_D'])}, {bil(target - ctx['OFF_V'])} short of ${n} trillion. "
                     f"The clock is not projecting a date, because the debt is not growing past the statutory limit.")
            summary = quote
        h1 = f"When will the US debt hit ${n} trillion?"
    return {
        "n": n, "target": target, "nxt": nxt, "base": base, "t0": t0, "live_rate": live_rate, "freeze": freeze,
        "debt_now": debt_now, "official": official, "passed": passed, "per_day": per_day, "lim": lim, "subj_t": subj_t,
        "not_subj": not_subj, "total_at_limit": total_at_limit, "next_ok": next_ok, "goal_ts": goal_ts, "when": when,
        "lim_when": lim_when, "hold": hold, "kicker": kicker, "passed_date": passed_date, "title": title, "left": left,
        "quote": quote, "summary": summary, "h1": h1, "T": T,
    }


def _point(day, H, hdo):
    """Debt on or before a calendar date. Daily close once Debt to the Penny has started, otherwise the annual record."""
    if day is None:
        return None
    start = H["series_start"]["date"]
    if day >= start and day in H["on_or_before"]:
        rec = H["on_or_before"][day]
        return {"date": rec["date"], "amount": rec["amount"], "basis": "dtp", "requested": day}
    best = None
    for fy, date, amt in hdo:
        if date <= day and (best is None or date > best["date"]):
            best = {"date": date, "amount": amt, "fy": fy, "basis": "hdo", "requested": day}
    return best


def _basis_label(p, fdate, open_term=False):
    if not p:
        return "No Treasury record on or before this date"
    shown = fdate(p["date"])
    if open_term:
        return f"{shown} · latest close, term in progress"
    if p["basis"] == "dtp":
        return f"{shown} · Debt to the Penny, last close on or before the date"
    return f"{shown} · Historical Debt Outstanding, annual record (not inauguration day)"


def build(ctx):
    H = _load(ctx["R"])
    ctx = dict(ctx)
    ctx["H"] = H
    keys = ["debt_total", "population", "households", "tax_returns", "interest_cash", "interest_gross"]
    ctx["clock"] = _clock(ctx["T"], keys, ctx["M"])
    _milestone_pages(ctx, H)
    import presidents_build
    pres_urls = presidents_build.build(ctx)
    _president_page(ctx, H)
    _person_page(ctx, H)
    _interest_page(ctx, H)
    return pres_urls


def _milestone_pages(ctx, H):
    fdate, usd0, usd2, bil = ctx["fdate"], ctx["usd0"], ctx["usd2"], ctx["bil"]
    for n in MILESTONE_PAGES:
        s = milestone_state(ctx, H, n)
        target, nxt, live_rate = s["target"], s["nxt"], s["live_rate"]
        official, per_day = s["official"], s["per_day"]
        lim, subj_t, not_subj = s["lim"], s["subj_t"], s["not_subj"]
        next_ok, when, lim_when = s["next_ok"], s["when"], s["lim_when"]
        hold, freeze, goal_ts = s["hold"], s["freeze"], s["goal_ts"]
        kicker, passed_date, title = s["kicker"], s["passed_date"], s["title"]
        left, summary, h1 = s["left"], s["summary"], s["h1"]
        debt_now, base, T = s["debt_now"], s["base"], s["T"]
        passed = s["passed"]
        desc = (summary
                .replace(" The figure above is what is left after projecting forward from that close.", "")
                .replace(" The figure above is what is left.", "")
                .replace("The figure above is what is left until", "Amount left until")
                .replace("The figure above counts what is left until", "Amount left until"))
        if len(desc) > 320:
            desc = desc[:317].rsplit(" ", 1)[0] + "."
        hero = f"""<div class="hero lead" id="lead" data-mode="count" data-target="{target}" data-next="{nxt}" data-rate="{live_rate}" data-level="{n}" data-next-level="{n+1}" data-passed="{'1' if official else '0'}" data-passed-date="{html.escape(passed_date)}" data-when="{html.escape(when or '')}" data-next-ok="{'1' if next_ok else '0'}" data-hold="{html.escape(hold, quote=True)}">
<div class="k" id="lead-k">{html.escape(kicker)}</div>
<div class="big num" id="lead-v">{usd0(max(left, 0))}</div>
<div class="sub" id="lead-sub">{html.escape(when or 'Debt to the Penny')} · {usd0(debt_now if debt_now is not None else base)} now</div>
</div>"""
        intro = f"<h1>{html.escape(h1)}</h1><p class=\"answer\">{summary} Source: <a href=\"{ctx['DTP']}\" rel=\"noopener\">Treasury, Debt to the Penny</a>.</p>"
        rows = []
        for c in reversed(H["crossings"]):
            rows.append(f"<tr><td>${c['trillion']} trillion</td><td>{fdate(c['date'])}</td><td class=\"num\">{usd2(c['amount'])}</td>"
                        f"<td class=\"num\">{usd2(c['prior_amount'])}<span class=\"when\">prior close {fdate(c['prior_date'])}</span></td></tr>")
        start = H["series_start"]
        # Intervals between the last few observed crossings, from the record dates only.
        xs = H["crossings"]
        gaps = []
        for a, b in zip(xs[-6:], xs[-5:]):
            days = (dt.date.fromisoformat(b["date"]) - dt.date.fromisoformat(a["date"])).days
            gaps.append(f"<li>${a['trillion']} trillion on {fdate(a['date'])} to ${b['trillion']} trillion on {fdate(b['date'])}: {days} days, {bil(b['amount'] - a['amount'])}.</li>")
        pace = (f"<p>The homepage clock adds about {bil(per_day)} a day, ${live_rate:,.2f} a second. "
                f"That rate is the 90-day least-squares slope of Debt to the Penny"
                + (f" ({T.get('calc', {}).get('n', '—')} closes, {T.get('calc', {}).get('window', '')})." if T.get("calc") else ".")
                + " Daily changes are lumpy, so the crossing can land days either side of the projected date.</p>")
        limit = ""
        if lim and subj_t.get("base"):
            limit = (f"<h2>The debt limit</h2><p>The statutory debt limit is <b>{usd0(lim)}</b> ({ctx['tril'](lim, 3)}), per Treasury's Daily Treasury Statement. "
                     f"It applies to <i>debt subject to the limit</i>, which was {usd0(subj_t['base'])} on {fdate(subj_t.get('as_of'))}, leaving {bil(lim - subj_t['base'])} of room.")
            if not_subj is not None:
                subj_at = target - not_subj
                total_at = lim + not_subj
                limit += (f" About {bil(not_subj)} of the total debt is not subject to the limit, so total debt reaches ${n} trillion when debt subject to the limit is about "
                          f"{ctx['tril'](subj_at, 3)}" + (", still under the limit" if subj_at < lim else ", which is above the limit, so that level waits on Congress")
                          + f". The limit itself would bind with total debt near {ctx['tril'](total_at, 2)}.")
            if lim_when:
                limit += f" At the 90-day pace of debt subject to the limit, the limit would be reached around {lim_when} (our projection)."
                if when and not passed and freeze and goal_ts and freeze < goal_ts:
                    limit += " That is before the projected date, so the crossing may wait until Congress acts."
            limit += (" Once the limit binds, Treasury uses extraordinary measures and the debt goes roughly flat; our clock then stops projecting growth and holds at the official figure. "
                      f"This page counts toward ${n+1} trillion only if Congress raises or suspends the limit before then.</p>")
        body = f"""<h2>How fast the debt is growing</h2>
{pace}
<ul>{''.join(gaps)}</ul>
<h2>Trillion levels in Debt to the Penny</h2>
<p>The daily series starts {fdate(start['date'])} at {usd2(start['amount'])}. It was already above $4 trillion, so this table starts at the first level the series actually crosses. Each date is the first close at or above that level, and the prior close was below it.</p>
<div class="tw"><table><tr><th>Level</th><th>First close at or above</th><th>Amount</th><th>Prior close</th></tr>{''.join(rows)}</table></div>
{limit}
{ctx['src']([("Treasury, Debt to the Penny", ctx['DTP']), ("Treasury, Daily Treasury Statement Table III-C", "https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/debt-subject-to-limit")])}"""
        growth = (f"About {bil(per_day)} a day as of {fdate(ctx['OFF_D'])}, ${live_rate:,.2f} a second. "
                  f"That is the homepage clock's 90-day least-squares trend of Debt to the Penny. Daily changes are lumpy."
                  if live_rate else
                  "The clock is not projecting growth. Debt subject to the limit is at the statutory limit, so the clock holds at Treasury's latest close.")
        faqs = [
            (f"When will the US national debt hit ${n} trillion?", s["quote"]),
            ("How is that date calculated?",
             f"From Treasury's {fdate(ctx['OFF_D'])} Debt to the Penny close of {usd2(ctx['OFF_V'])}, plus ${live_rate:,.2f} per second, the homepage clock's 90-day trend. It is a projection."),
            ("How fast is the national debt growing?", growth),
            (f"When did the national debt hit ${xs[-1]['trillion']} trillion?",
             f"The first Debt to the Penny close at or above ${xs[-1]['trillion']} trillion was {fdate(xs[-1]['date'])}, at {usd2(xs[-1]['amount'])}."),
            (f"What does this page do after the debt passes ${n} trillion?",
             f"It says the debt passed ${n} trillion on the Treasury date of the first close at or above that level. "
             + (f"The countdown then switches to ${n+1} trillion, which the current pace still reaches before the statutory limit."
                if next_ok else
                f"${n+1} trillion is past the point where the statutory limit would bind, so the page does not count toward ${n+1} trillion unless Congress raises or suspends the limit. Once the limit binds, the clock holds at the official figure.")),
        ]
        ld = ctx["dataset_ld"](f"US national debt countdown to ${n} trillion", desc, f"{ctx['SITE']}/{n}-trillion/",
                               based=[ctx["DTP"]]) + ctx["faq_ld"](faqs)
        _page(ctx, f"{n}-trillion", title, desc, ld, hero, intro, body, faqs)


def _president_page(ctx, H):
    terms = ctx["terms"]
    hdo = ctx["hdo"]
    fdate, usd0, usd2, bil = ctx["fdate"], ctx["usd0"], ctx["usd2"], ctx["bil"]
    rows = []
    for name, n, start, end in reversed(terms):
        a = _point(start, H, hdo)
        if end is None:
            b = {"date": ctx["OFF_D"], "amount": ctx["OFF_V"], "basis": "dtp", "requested": ctx["OFF_D"]}
            open_term = True
        else:
            b = _point(end, H, hdo)
            open_term = False
        same = a and b and a["date"] == b["date"]
        if a and b and not same:
            ch = b["amount"] - a["amount"]
            pct = ch / a["amount"] * 100 if a["amount"] else None
            ch_s = usd0(ch)
            pct_s = "—" if pct is None else f"{pct:+,.1f}%"
        else:
            ch_s = pct_s = "—"
        term = f"{fdate(start)} – " + ("in progress" if open_term else fdate(end))
        def cell(p, open_=False):
            if not p:
                return "<td>No record on or before this date</td>"
            return f"<td class=\"num\">{usd0(p['amount'])}<span class=\"when\">{html.escape(_basis_label(p, fdate, open_))}</span></td>"
        slug = (ctx.get("president_pages") or {}).get(name)
        who = f'<a href="{html.escape(slug)}/">{html.escape(name)}</a>' if slug else html.escape(name)
        rows.append(f"<tr><td>{who}<span class=\"when\">{_ord(n)} term</span></td><td>{term}</td>{cell(a)}{cell(b, open_term)}"
                    f"<td class=\"num\">{ch_s}</td><td class=\"num\">{pct_s}</td></tr>")
    end = H["series_end"]
    intro = (f"<h1>National debt by president</h1>"
             f"<p class=\"answer\">Each row is total public debt outstanding at the start and end of one term. "
             f"From {fdate(H['series_start']['date'])} on, the figure is the last Debt to the Penny close on or before the date. "
             f"Earlier, it is the last <a href=\"{H['sources']['debt_outstanding']}\" rel=\"noopener\">Historical Debt Outstanding</a> record on or before the date, an annual total, not the debt on inauguration day. "
             f"The current term ends at the latest close, {usd2(ctx['OFF_V'])} as of {fdate(ctx['OFF_D'])}. "
             f'Sources: <a href="{ctx["DTP"]}" rel="noopener">Treasury, Debt to the Penny</a> and '
             f'<a href="{html.escape(H["sources"]["debt_outstanding"])}" rel="noopener">Historical Debt Outstanding</a>.</p>'
             f"<p>The change is the difference between those two Treasury figures. Terms are not the same length, and Congress writes taxing and spending laws, so the change is not a score for the person in office. "
             f"A term that starts after a death or resignation is still listed as that president's term: Tyler, Fillmore, Andrew Johnson, Arthur, Theodore Roosevelt, Coolidge, Truman, Lyndon Johnson, and Ford.</p>")
    hero_debt = ctx["val"]("debt_total", ctx["NOW"])
    hero = f"""<div class="hero lead" id="lead" data-mode="debt">
<div class="k" id="lead-k">US national debt · live</div>
<div class="big num" id="lead-v">{usd0(hero_debt)}</div>
<div class="sub" id="lead-sub">Same clock as the homepage · official close {html.escape(fdate(ctx['OFF_D']))} {html.escape(usd2(ctx['OFF_V']))}</div>
</div>"""
    body = f"""<div class="tw"><table><tr><th>President</th><th>Term</th><th>Debt at start</th><th>Debt at end</th><th>Change</th><th>Change %</th></tr>{''.join(rows)}</table></div>
<p>A dash means there are not two different Treasury records to subtract. That happens when the annual series has only one reading in the term, or no record on or before the start. Debt to the Penny's latest row in this extract is {fdate(end['date'])}, {usd2(end['amount'])}.</p>
{ctx['src']([("Treasury, Debt to the Penny", ctx['DTP']), ("Treasury, Historical Debt Outstanding", H['sources']['debt_outstanding'])])}"""
    desc = f"US national debt at the start and end of each presidential term. Daily Treasury closes from {fdate(H['series_start']['date'])}; annual Historical Debt Outstanding before that."
    faqs = [
        ("Is this the debt on inauguration day?",
         f"Where Debt to the Penny has a record, yes: the last close on or before the date. Before {fdate(H['series_start']['date'])}, the table uses Treasury's annual Historical Debt Outstanding record on or before the date, which is not inauguration day."),
        ("Does the change show what a president added to the debt?",
         "No. It is the difference between the Treasury total at the start and at the end. Term lengths differ, and spending and tax laws are passed by Congress."),
        ("How does the table treat a term that started after a death or resignation?",
         "That term is listed under the person who took office: Tyler, Fillmore, Andrew Johnson, Arthur, Theodore Roosevelt, Coolidge, Truman, Lyndon Johnson, and Ford. The amounts are still the Treasury records on those dates."),
    ]
    open_term = next((t for t in terms if t[3] is None), None)
    if open_term:
        oname, _on, ostart, _oend = open_term
        oa = _point(ostart, H, hdo)
        if oa and oa.get("amount"):
            ch = ctx["OFF_V"] - oa["amount"]
            basis = ("Debt to the Penny, the last close on or before the date" if oa["basis"] == "dtp"
                     else "Historical Debt Outstanding, an annual record, not the debt on that calendar day")
            faqs.append((
                f"What is the national debt in the {oname} term that started {fdate(ostart)}?",
                f"That term is still in progress. Debt at the start was {usd0(oa['amount'])} as of {fdate(oa['date'])} ({basis}). "
                f"The latest Debt to the Penny close is {usd2(ctx['OFF_V'])} as of {fdate(ctx['OFF_D'])}. "
                f"The change between those two Treasury figures is {usd0(ch)}.",
            ))
    faqs.append((
        "Where do the debt-by-president figures come from?",
        f"From {fdate(H['series_start']['date'])} on, each amount is the last Debt to the Penny close on or before the date. "
        f"Earlier amounts are the last Historical Debt Outstanding record on or before the date. "
        f"The current term ends at the latest close, {usd2(ctx['OFF_V'])} as of {fdate(ctx['OFF_D'])}.",
    ))
    ld = ctx["dataset_ld"]("US national debt by presidential term", desc, f"{ctx['SITE']}/national-debt-by-president/",
                           based=[ctx["DTP"], H["sources"]["debt_outstanding"]]) + ctx["faq_ld"](faqs)
    _page(ctx, "national-debt-by-president", "National Debt by President: Start and End of Each Term", desc, ld, hero, intro, body, faqs)


def _person_page(ctx, H):
    fdate, usd0, usd2, bil = ctx["fdate"], ctx["usd0"], ctx["usd2"], ctx["bil"]
    pp = ctx["OFF_V"] / ctx["POP_OFF"]
    debt_now = ctx["val"]("debt_total", ctx["NOW"])
    pop_now = ctx["val"]("population", ctx["NOW"])
    live = debt_now / pop_now if debt_now and pop_now else pp
    hh, tax = ctx["HH"], ctx["TAX"]
    hero = f"""<div class="hero lead" id="lead" data-mode="person">
<div class="k" id="lead-k">National debt per person · live</div>
<div class="big num" id="lead-v">{usd2(live)}</div>
<div class="sub" id="lead-sub">Debt clock ÷ population projected from the Census estimate for {fdate(ctx['POP_OFF_DATE'])}</div>
<div class="trio"><div><span class="l">Per person</span><span class="n" id="pp-p">{usd2(live)}</span></div>
<div><span class="l">Per household</span><span class="n" id="pp-h">{usd2(debt_now / hh)}</span></div>
<div><span class="l">Per tax return filed</span><span class="n" id="pp-r">{usd2(debt_now / tax)}</span></div></div>
</div>"""
    intro = (f"<h1>National debt per person</h1>"
             f"<p class=\"answer\">On the official figures, the debt per person is <b>{usd2(pp)}</b> as of {fdate(ctx['OFF_D'])}: Treasury's total of {usd2(ctx['OFF_V'])} "
             f"divided by the Census Bureau's {ctx['POP_OFF']:,.0f} residents on {fdate(ctx['POP_OFF_DATE'])} (Vintage 2025). "
             f"The number above moves with the debt clock and with Census's stated population growth. "
             f"Per household is {usd2(ctx['OFF_V'] / hh)} ({hh:,.0f} households). "
             f"Per tax return filed is {usd2(ctx['OFF_V'] / tax)} ({tax:,.0f} individual returns in FY2025). A joint return counts once. "
             f'Sources: <a href="{ctx["DTP"]}" rel="noopener">Treasury, Debt to the Penny</a> and '
             f'<a href="{html.escape(H["population_sources"][-1]["page"])}" rel="noopener">Census Vintage 2025</a>.</p>'
             f"<p><a class=\"cta\" href=\"../your-share/\">Your share of the national debt</a></p>"
             f"<p>Enter a birth year. Your share uses this same Treasury total divided by this same Census population. "
             f"A state, household size, and income are optional. The math runs in your browser and nothing is stored.</p>")
    by_fy = {int(r[0]): (r[1], r[2]) for r in (ctx["M"].get("debt_by_fy") or [])}
    pops = {p["year"]: p for p in H["population_by_year"]}
    def rows_for(years, require_pop):
        out = []
        for y in years:
            debt = by_fy.get(y)
            if not debt:
                continue
            pop = pops.get(y)
            if not pop and require_pop:
                continue
            if pop:
                per = debt[1] / pop["population"]
                short = {"historical-1900-1999": "1900–1999 estimates", "intercensal-2000-2010": "2000–2010 intercensal",
                         "vintage-2020": "Vintage 2020", "vintage-2025": "Vintage 2025"}.get(pop["series"], pop["series"])
                pop_cell = f"{pop['population']:,}<span class=\"when\">July 1, {y}</span>"
                per_cell = usd2(per)
                series_cell = html.escape(short)
            else:
                pop_cell = per_cell = series_cell = "—"
            out.append(f"<tr><td>FY{y}</td><td class=\"num\">{usd0(debt[1])}<span class=\"when\">{fdate(debt[0])}</span></td>"
                       f"<td class=\"num\">{pop_cell}</td><td class=\"num\">{per_cell}</td><td>{series_cell}</td></tr>")
        return "".join(out)
    recent = [y for y in sorted(by_fy, reverse=True) if y >= 2000]
    older = [y for y in sorted(set(by_fy) & set(pops), reverse=True) if y < 2000]
    srcs = [(s["name"], s["page"]) for s in H["population_sources"]]
    body = f"""<h2>By fiscal year</h2>
<p>Debt is Treasury's total at the fiscal-year-end record date. Population is the Census July 1 resident estimate for that calendar year. The two dates are not the same day. Each population column names its Census series. Those series are separate publications, not one revised vintage. A dash means Census has not published the July 1 estimate for that year yet.</p>
<div class="tw"><table><tr><th>Fiscal year</th><th>Debt</th><th>Population</th><th>Per person</th><th>Population series</th></tr>{rows_for(recent, False)}</table></div>
<details><summary>FY{older[0] if older else ''} back to FY{older[-1] if older else ''}</summary>
<div class="tw"><table><tr><th>Fiscal year</th><th>Debt</th><th>Population</th><th>Per person</th><th>Population series</th></tr>{rows_for(older, True)}</table></div></details>
<p>Per person here divides the debt by every resident, including children. It is not a bill. Households are Census CPS ASEC 2025. Tax returns are IRS Data Book FY2025, Table 1-2, not a count of taxpayers.</p>
{ctx['src']([("Treasury, Debt to the Penny", ctx['DTP']), ("Treasury, Historical Debt Outstanding", H['sources']['debt_outstanding'])] + srcs + [("Census Bureau, CPS ASEC 2025, Table HH-1", ctx['HH_URL']), ("IRS Data Book FY2025, Table 1-2", ctx['IRS_URL'])])}"""
    desc = (f"US national debt per person: {usd2(pp)}, Treasury's {fdate(ctx['OFF_D'])} total divided by Census's {ctx['POP_OFF']:,.0f} residents on {fdate(ctx['POP_OFF_DATE'])}. "
            f"Live per person, per household, and per tax return, plus a by-year table.")
    faqs = [
        ("How much is the national debt per person?",
         f"{usd2(pp)} as of {fdate(ctx['OFF_D'])}. Treasury's total of {usd2(ctx['OFF_V'])} divided by the Census Vintage 2025 estimate of {ctx['POP_OFF']:,.0f} residents on {fdate(ctx['POP_OFF_DATE'])}."),
        ("What population is used?",
         f"The official per-person figure uses the Census Vintage 2025 estimate of {ctx['POP_OFF']:,.0f} residents on {fdate(ctx['POP_OFF_DATE'])}, with no projection. The live figure at the top projects that estimate forward at the rate Census states. The by-year table uses the July 1 estimate from the Census series named in each row."),
        ("How much is the national debt per household?",
         f"{usd2(ctx['OFF_V'] / hh)} as of {fdate(ctx['OFF_D'])}. Treasury's {fdate(ctx['OFF_D'])} total divided by {hh:,.0f} households in Census CPS ASEC 2025."),
        ("How much is the national debt per tax return?",
         f"{usd2(ctx['OFF_V'] / tax)} as of {fdate(ctx['OFF_D'])}. Treasury's {fdate(ctx['OFF_D'])} total divided by {tax:,.0f} individual income tax returns filed in FY2025 (IRS Data Book, Table 1-2). A joint return counts once."),
        ("Why is the number at the top different from the official per-person figure?",
         f"The number at the top divides the live debt clock by population projected from the Census estimate for {fdate(ctx['POP_OFF_DATE'])}. "
         f"{usd2(pp)} divides the {fdate(ctx['OFF_D'])} Treasury close by the {ctx['POP_OFF']:,.0f} residents Census estimated for that date, with no projection."),
    ]
    ld = ctx["dataset_ld"]("US national debt per person", desc, f"{ctx['SITE']}/national-debt-per-person/",
                           based=[ctx["DTP"], H["population_sources"][-1]["page"]]) + ctx["faq_ld"](faqs)
    _page(ctx, "national-debt-per-person",
          f"National Debt Per Person: {usd0(pp)} (Treasury ÷ Census)", desc, ld, hero, intro, body, faqs)


def _interest_page(ctx, H):
    fdate, usd0, usd2, bil = ctx["fdate"], ctx["usd0"], ctx["usd2"], ctx["bil"]
    cash = ctx["T"].get("interest_cash") or {}
    gross = ctx["T"].get("interest_gross") or {}
    now = ctx["NOW"]
    # Official cash interest is the DTS close (Table II), not the number the hero has ticked to since then.
    official_paid = cash.get("base") if cash.get("status") == "ok" else None
    official_as_of = cash.get("as_of")
    live_paid = ctx["val"]("interest_cash", now) if official_paid is not None else None
    pace = (gross.get("rate") or 0) * 86400 if gross.get("status") == "ok" else None
    expenses = {r["fy"]: r for r in H["interest_expense_by_fy"]}
    latest_net = H.get("net_interest_latest") or {}
    rows = []
    years = sorted(set(expenses) | {r["fy"] for r in H["net_interest_by_fy"]}, reverse=True)
    for y in years:
        n = next((r for r in H["net_interest_by_fy"] if r["fy"] == y), None)
        e = expenses.get(y)
        if not n and not e:
            continue
        if n:
            ncell = f"{usd0(n['amount'])}<span class=\"when\">{fdate(n['date'])}</span>"
        elif latest_net and latest_net.get("fy") == y:
            ncell = f"{usd0(latest_net['amount'])}<span class=\"when\">{fdate(latest_net['date'])} · year to date</span>"
        else:
            ncell = "—"
        if e and e["complete"]:
            ecell = f"{usd0(e['amount'])}<span class=\"when\">{fdate(e['date'])}</span>"
        elif e:
            ecell = f"{usd0(e['amount'])}<span class=\"when\">{fdate(e['date'])} · year to date, not a full year</span>"
        else:
            ecell = "—"
        rows.append(f"<tr><td>FY{y}</td><td class=\"num\">{ncell}</td><td class=\"num\">{ecell}</td></tr>")
    fy_now = ctx["M"].get("fy")
    latest_line = ""
    if latest_net and latest_net.get("date", "")[5:7] != "09":
        latest_line = (f" MTS net interest for FY{latest_net['fy']} through {fdate(latest_net['date'])} is {usd0(latest_net['amount'])}. "
                       f"That is a year-to-date total, not a finished year.")
    off_s = usd0(official_paid) if official_paid is not None else "unavailable"
    live_s = usd0(live_paid) if live_paid is not None else "—"
    as_of_s = fdate(official_as_of) if official_as_of else "the latest close"
    pace_s = bil(pace) + " a day" if pace else "unavailable"
    full = next((r for r in H["net_interest_by_fy"][::-1]), None)
    intro = (f"<h1>Interest on the national debt</h1>"
             f"<p class=\"answer\">Cash interest paid on Treasury securities was <b>{off_s}</b> as of {as_of_s}, the Daily Treasury Statement close. "
             f"The figure above is a projection from that close and has moved since then. Payments land in lumps, so the digits jump on coupon dates. "
             f"On an accrual basis, Treasury's interest-expense dataset is running at about {pace_s}, the last 12 reported months spread over the year."
             + (f" Net interest, the budget total, was {usd0(full['amount'])} in FY{full['fy']}." if full else "")
             + latest_line
             + f' Source: <a href="{html.escape(H["sources"]["dts_interest_paid"])}" rel="noopener">Treasury, Daily Treasury Statement</a>.</p>')
    hero = f"""<div class="hero lead" id="lead" data-mode="interest">
<div class="k" id="lead-k">Interest paid this fiscal year · projected</div>
<div class="big num" id="lead-v">{live_s}</div>
<div class="sub" id="lead-sub">Projected from the {html.escape(as_of_s)} Daily Treasury Statement close of {html.escape(off_s)}. FY{fy_now}.</div>
</div>"""
    body = f"""<h2>By fiscal year</h2>
<p>Net interest is MTS Table 9, line 320, the September year-to-date total. Interest expense is the sum of every line in Treasury's Interest Expense on the Public Debt Outstanding dataset for that September. The dataset total is larger. It counts interest on all Treasury securities, including securities held by government accounts. Net interest is the budget figure after interest the government receives.</p>
<div class="tw"><table><tr><th>Fiscal year</th><th>Net interest (MTS)</th><th>Interest expense (dataset)</th></tr>{''.join(rows)}</table></div>
<p>The MTS series on this feed starts in FY{H['net_interest_by_fy'][0]['fy']}. The interest-expense file's first September is FY{min(r['fy'] for r in H['interest_expense_by_fy'] if r['complete'])}; that first year does not have 12 monthly rows in the file, and the amount shown is the September year-to-date total.</p>
{ctx['src']([("Treasury, Monthly Treasury Statement (net interest, line 320)", H['sources']['mts_net_interest']), ("Treasury, Interest Expense on the Public Debt Outstanding", H['sources']['interest_expense']), ("Treasury, Daily Treasury Statement (interest paid)", H['sources']['dts_interest_paid'])])}"""
    desc = (f"Cash interest on Treasury securities was {off_s} through {as_of_s} (Daily Treasury Statement). "
            f"The page projects forward from that close. Net interest by fiscal year is from the Monthly Treasury Statement, and interest expense is from Treasury's debt-outstanding dataset.")
    faqs = [
        ("How much interest has the US paid this fiscal year?",
         f"{off_s} in cash interest on Treasury securities as of {as_of_s}, from the Daily Treasury Statement. The number at the top of the page is a projection and has moved since that close."),
        ("What is net interest on the national debt?",
         f"Net interest was {usd0(full['amount'])} in FY{full['fy']} (Monthly Treasury Statement, line 320). It is the budget total, smaller than the interest-expense dataset because interest received by the government is netted out." if full else "Net interest is MTS Table 9, line 320."),
    ]
    day = interest_day_answer(ctx["T"], ctx["val"], ctx["NOW"], fdate, usd0, bil, ctx["STAMP"])
    if day:
        faqs.append(("How much interest does the US pay per day?", day))
    faqs.append((
        "Is the number at the top the official interest total?",
        f"No. The figure at the top is projected forward from the Daily Treasury Statement close of {off_s} as of {as_of_s}. Payments land on coupon dates, so the official cash total stays flat between those dates and then jumps.",
    ))
    faqs.append((
        "Where do the interest figures come from?",
        "Cash interest this fiscal year is the Daily Treasury Statement. Net interest by fiscal year is Monthly Treasury Statement Table 9, line 320. "
        "Interest expense by fiscal year is Treasury's Interest Expense on the Public Debt Outstanding dataset. They measure different things.",
    ))
    ld = ctx["dataset_ld"]("Interest on the US national debt", desc, f"{ctx['SITE']}/interest-on-the-national-debt/",
                           based=[H["sources"]["mts_net_interest"], H["sources"]["interest_expense"], H["sources"]["dts_interest_paid"]]) + ctx["faq_ld"](faqs)
    _page(ctx, "interest-on-the-national-debt", "Interest on the National Debt, by Year and This Year", desc, ld, hero, intro, body, faqs)
