"""World Government Debt Clock (/world-government-debt/) and IMF estimate country clocks.

Reads data/world_weo_debt.json (pipeline/fetch_world.py). The panel is every IMF economy with a positive
2025 and 2026 general-government gross debt stock: GGXWDG_NGDP / 100 × NGDPD, in current US dollars.
The ticker runs from the end-2025 stock at 2026-01-01 00:00 UTC to the end-2026 stock at 2027-01-01 00:00 UTC.

Economies that already have an official clock keep that page. This module adds pages only for the rest.
The United States stays on the Treasury clock; the IMF figure appears only on the world government debt page.
Called from build.py.
"""
import datetime as dt
import json
import os
import html

import explore as ex
import places_build as pb
import world_build

ISO2 = dict(world_build.ISO3)
ISO2["EL"] = "GRC"

E = html.escape
RATIO_URL = "https://www.imf.org/external/datamapper/GGXWDG_NGDP@WEO"
GDP_URL = "https://www.imf.org/external/datamapper/NGDPD@WEO"
SRC = ('Source: IMF World Economic Outlook, October 2026. General government gross debt is GGXWDG_NGDP '
       '(percent of GDP) times NGDPD (GDP in current US dollars).')

def load(R):
    path = f"{R}/data/world_weo_debt.json"
    if not os.path.exists(path): return None
    return json.load(open(path))

def _t0(D):
    return dt.datetime.fromisoformat(D["anchor"]).timestamp()

def _now(debt_2025, rate, now, t0):
    return debt_2025 + rate * (now - t0)

def _money0(x):
    return ("−" if x < 0 else "") + f"${abs(x):,.0f}"

def _money(x):
    ax = abs(x)
    s = "−" if x < 0 else ""
    if ax >= 1e12: return s + f"${ax/1e12:,.2f} trillion"
    if ax >= 1e9: return s + f"${ax/1e9:,.2f} billion"
    if ax >= 1e6: return s + f"${ax/1e6:,.2f} million"
    return _money0(x)

def _signed(x):
    """Signed amount with the sign before the dollar symbol. Small rates keep extra digits so a tiny clock is not shown as zero."""
    if x == 0: return "$0"
    sign = "+" if x > 0 else "−"
    ax = abs(x)
    if ax >= 1e12: body = f"${ax/1e12:,.2f} trillion"
    elif ax >= 1e9: body = f"${ax/1e9:,.2f} billion"
    elif ax >= 1e6: body = f"${ax/1e6:,.2f} million"
    elif ax >= 100: body = f"${ax:,.0f}"
    elif ax >= 1: body = f"${ax:,.2f}"
    else: body = f"${ax:.4f}"
    return sign + body

def _src_html():
    return (f'<p class="src">{E(SRC)} <a href="{RATIO_URL}" rel="noopener">GGXWDG_NGDP</a>'
            f' · <a href="{GDP_URL}" rel="noopener">NGDPD</a>.</p>')

def _faq_ld(pairs):
    ld = {"@context": "https://schema.org", "@type": "FAQPage",
          "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in pairs]}
    return '<script type="application/ld+json">' + json.dumps(ld).replace("</", "<\\/") + "</script>"

def _dataset_ld(name, desc, url):
    ld = {"@context": "https://schema.org", "@type": "Dataset", "name": name, "description": desc, "url": url,
          "isAccessibleForFree": True, "creator": {"@type": "Organization", "name": "Every Debt Clock", "url": "https://everydebtclock.com/"},
          "isBasedOn": [RATIO_URL, GDP_URL], "temporalCoverage": "2025/2026"}
    return '<script type="application/ld+json">' + json.dumps(ld).replace("</", "<\\/") + "</script>"

CSS = """th[data-k]{cursor:pointer}th[data-dir="desc"]::after{content:" ↓"}th[data-dir="asc"]::after{content:" ↑"}
.src{font-size:14px}.faq h3{font-size:16px;margin:16px 0 4px}.faq p{margin:0 0 8px}
@media (max-width:640px){.hero .trio{grid-template-columns:1fr}.hero .trio .num{font-size:18px}}
"""

TICK = """<script>(function(){const nf0=new Intl.NumberFormat('en-US',{maximumFractionDigits:0});
const H=document.getElementById('t-total'),B=+H.dataset.b,R=+H.dataset.r,T0=+H.dataset.t,hv=document.getElementById('hv'),hs=document.getElementById('hs'),OPENED=Date.now()/1000;
const tot=t=>B+R*(t-T0);(function f(){const t=Date.now()/1000,x=tot(t);hv.textContent=(x<0?'−':'')+'$'+nf0.format(Math.abs(x));
if(hs)hs.textContent=(R<0?'−':'+')+'$'+nf0.format(Math.abs(R*(t-OPENED)));requestAnimationFrame(f)})();
const table=document.getElementById('debt-table');if(!table)return;const tb=table.tBodies[0];
table.querySelectorAll('th[data-k]').forEach(function(th){th.addEventListener('click',function(){const dir=th.dataset.dir==='asc'?'desc':'asc',k=th.dataset.k;
table.querySelectorAll('th[data-k]').forEach(function(h){delete h.dataset.dir});th.dataset.dir=dir;
const rows=[].slice.call(tb.rows);rows.sort(function(a,b){const av=a.dataset[k],bv=b.dataset[k],an=+av,bn=+bv;
const c=(av!==''&&bv!==''&&!isNaN(an)&&!isNaN(bn))?an-bn:String(av).localeCompare(String(bv));return dir==='asc'?c:-c});
rows.forEach(function(r){tb.appendChild(r)})})})})()</script>"""

def _pool(places, economies):
    """Official places plus one record per new IMF clock, so related links can see both."""
    extra = [{"slug": e["slug"], "kind": "country", "name": e["name"], "weo": True, "region": e.get("region") or ""}
             for e in economies if e["clock"] == "weo"]
    return list(places) + extra

def _gdp(economies):
    out = {e["slug"]: e["gdp_2026_usd"] / 1e9 for e in economies}
    for slug, v in (pb.GDP_BY_SLUG or {}).items():
        out.setdefault(slug, v or 0)
    return out

def _related(pool, gdp, cur):
    items = ex.pick_related(pool, lambda p: {"total": 0}, cur=cur, gdp=gdp)
    urls = [u for _, u, _ in items]
    self = f'countries/{cur["slug"]}/'
    if len(items) != 3 or len(set(urls)) != 3 or self in urls:
        raise SystemExit(f"related clocks: {cur['slug']} -> {items}")
    return ex.related_html("../../", items)

def _country_faqs(name, now_s, d26_s, ratio, d25_s):
    return [
        (f"How much is {name}'s national debt?",
         f"The IMF estimate interpolated to this page's build is {now_s}. The end-2026 projection is {d26_s}, {ratio:.2f} percent of GDP. "
         f"The end-2025 projection was {d25_s}. This is general government gross debt, GGXWDG_NGDP times NGDPD, in current US dollars."),
        (f"Is the {name} debt clock a live official figure?",
         f"No. It is an estimate interpolated from IMF projections, not a live ledger. {name} does not publish a daily debt stock, and this page does not use a national statistical office series."),
        (f"Where does the {name} debt figure come from?",
         "IMF World Economic Outlook, October 2026. General government gross debt as a percent of GDP (GGXWDG_NGDP) times GDP in current US dollars (NGDPD)."),
        (f"Why does the {name} dollar figure move by more than new borrowing?",
         "The end-2025 and end-2026 stocks are both in current US dollars, so the change includes exchange-rate effects as well as borrowing."),
    ]

def _country_page(R, SITE, with_analytics, og, stamp, now, e, D, places, pool, gdp):
    t0 = _t0(D)
    name, slug = e["name"], e["slug"]
    rate = e["rate_usd_per_sec"]
    projected = _now(e["debt_2025_usd"], rate, now, t0)
    url = f"{SITE}/countries/{slug}/"
    title = f"{name} National Debt Clock"
    now_s, d26_s, d25_s = _money0(projected), _money0(e["debt_2026_usd"]), _money0(e["debt_2025_usd"])
    desc = (f"{name} national debt clock: IMF estimate of general government gross debt, {_money(e['debt_2026_usd'])} at end-2026 "
            f"({e['ratio_2026']:.2f}% of GDP). Interpolated from IMF projections, not a live ledger.")
    faqs = _country_faqs(name, now_s, d26_s, e["ratio_2026"], d25_s)
    img = f"og/places/{slug}.png"
    if og:
        og(f"{R}/{img}", f"{name} national debt · IMF estimate", _money0(projected),
           [("Debt / GDP, 2026", f"{e['ratio_2026']:.2f}%"), ("End-2026 stock", _money(e["debt_2026_usd"]))],
           _signed(rate * 86400) + "/day", "#ff4d5e", "IMF WEO October 2026\ninterpolated estimate, not a live ledger")
    up = rate >= 0
    header = (f'<header class="top"><div class="topin"><a class="brand" href="../../">EVERY <b>DEBT</b> CLOCK</a>{pb.nav_html(places, 2, "country", "plnav")}'
              f'<span class="live"><span class="dot"></span><span>IMF estimate</span></span></div></header>')
    crumb = ('<div class="crumb"><a href="../../">← US national debt clock</a><span>·</span><a href="../../countries/">All country debt clocks</a>'
             '<span>·</span><a href="../../world-government-debt/">World government debt clock</a><span>·</span><a href="../../world/">World debt clock</a></div>')
    hero = (f'<div class="hero lead" id="t-total" data-b="{e["debt_2025_usd"]}" data-r="{rate:.12g}" data-t="{t0:.0f}">'
            f'<div class="k">{E(name)} general government debt · US dollars · IMF estimate</div><div class="big num" id="hv">{_money0(projected)}</div>'
            f'<div class="sub"><span>{_signed(rate)}/sec · {_signed(rate * 86400)}/day</span>'
            f'<span class="note">interpolated from the IMF end-2025 and end-2026 projections; not a live ledger</span>'
            f'<span>Since you opened this page: <span class="num" id="hs">$0</span> {"more" if up else "less"} debt</span></div>'
            f'<div class="trio"><div><span class="l">End-2026 IMF projection</span><span class="num">{_money0(e["debt_2026_usd"])}</span></div>'
            f'<div><span class="l">Debt / GDP, 2026</span><span class="num">{e["ratio_2026"]:.2f}%</span></div>'
            f'<div><span class="l">End-2025 IMF projection</span><span class="num">{_money0(e["debt_2025_usd"])}</span></div></div>'
            f'<div class="meta" style="margin-top:10px"><span class="badge proj">IMF ESTIMATE · interpolated</span><span class="badge">not a live ledger</span></div></div>')
    intro = (f'<section class="intro" id="intro">{crumb}<h1>{E(title)}</h1>'
             f'<p><b>What this page counts.</b> {E(name)}\'s general government gross debt, from the IMF World Economic Outlook, October 2026: '
             f'the debt ratio (GGXWDG_NGDP) times GDP in current US dollars (NGDPD). '
             f'The end-2026 projection is <b>{_money0(e["debt_2026_usd"])}</b> ({_money(e["debt_2026_usd"])}), {e["ratio_2026"]:.2f}% of GDP. '
             f'The end-2025 projection was {_money0(e["debt_2025_usd"])} ({e["ratio_2025"]:.2f}% of GDP). '
             f'The live number above is that estimate interpolated from the end-2025 stock on 1 January 2026 to the end-2026 stock on 1 January 2027. '
             f'It is not a live ledger. The dollar change includes exchange-rate effects, not only new borrowing. '
             f'{E(name)} does not have a separate official-source clock on this site, so this page does not mix in another publisher\'s figure.</p>'
             f'<p>This estimate is one row of the <a href="../../world-government-debt/">World Government Debt Clock</a>. '
             f'The <a href="../../world/">World Debt Clock</a> is a different total: it adds only the official country clocks and does not include this IMF estimate.</p>'
             f'{_src_html()}</section>')
    day = e["debt_2026_usd"] - e["debt_2025_usd"]
    changed = (f'<section id="changed"><div class="sh"><span class="bar" style="background:var(--red)"></span><h2>What the IMF projects</h2>'
               f'<span class="h2n">Fixed year-end projections · these two cards do not tick</span></div><div class="wc">'
               f'<div class="wcc now"><div class="d">NOW · interpolated</div><div class="v num" id="wcn">{_money(projected)}</div>'
               f'<div class="x">between the IMF year-end projections</div></div>'
               f'<div class="wcc"><div class="d">End-2026 · IMF</div><div class="v num">{_money(e["debt_2026_usd"])}</div>'
               f'<div class="x">{e["ratio_2026"]:.2f}% of GDP</div></div>'
               f'<div class="wcc"><div class="d">End-2025 · IMF</div><div class="v num">{_money(e["debt_2025_usd"])}</div>'
               f'<div class="x">{e["ratio_2025"]:.2f}% of GDP</div><div class="x">change to end-2026 {_signed(day)}</div></div>'
               f'</div></section>')
    meth = (f'<section id="method"><div class="sh"><span class="bar" style="background:var(--mut)"></span><h2>How it works</h2>'
            f'<span class="h2n">IMF projections · interpolation labelled · source linked</span></div><div class="sk foot">'
            f'<p><b>The stock.</b> End-year general government gross debt in US dollars = GGXWDG_NGDP ÷ 100 × NGDPD. '
            f'End-2026 is {_money0(e["debt_2026_usd"])}. End-2025 is {_money0(e["debt_2025_usd"])}.</p>'
            f'<p><b>The live number</b> starts at the end-2025 stock on 1 January 2026, 00:00 UTC, and reaches the end-2026 stock on 1 January 2027, 00:00 UTC. '
            f'2026 has {D["seconds_2026"]:,} seconds. The rate is ({_money0(e["debt_2026_usd"])} − {_money0(e["debt_2025_usd"])}) ÷ {D["seconds_2026"]:,} = {_signed(rate)} per second.</p>'
            f'<p><code>projected = {e["debt_2025_usd"]:,} + {rate:.6f} × (seconds since 2026-01-01 00:00 UTC)</code></p>'
            f'<p>The dollar change includes exchange-rate effects, because both stocks are current US dollars. This is not a live ledger of auctions and repayments.</p>'
            f'{_src_html()}<p>Page built {E(stamp)}.</p></div></section>')
    faq_html = '<section class="faq" id="faq"><div class="sh"><h2>Questions</h2></div>' + "".join(f"<h3>{E(q)}</h3><p>{E(a)}</p>" for q, a in faqs) + "</section>"
    links = ('<section class="answers" id="answers"><div class="sh"><h2>More clocks</h2></div><ul>'
             '<li><a href="../../world-government-debt/">World government debt clock</a> (this estimate is included)</li>'
             '<li><a href="../../world/">World debt clock</a> (official clocks only)</li>'
             '<li><a href="../../">US national debt clock</a> (Treasury, a different measure)</li>'
             '<li><a href="../../countries/">All country debt clocks</a></li></ul></section>')
    cur = {"slug": slug, "kind": "country", "name": name, "weo": True, "region": e.get("region") or ""}
    page = (pb.meta_head(SITE, url, title, desc, img, 2, pb.PL_CSS + world_build.CSS + CSS, _faq_ld(faqs) + _dataset_ld(title, desc, url))
            + header + ex.search_box("../../") + '<main id="app">' + hero + intro + changed + meth + faq_html + '</main>'
            + _related(pool, gdp, cur) + links
            + '<footer class="site-foot">Every Debt Clock · IMF estimate, interpolation labelled · <a href="../../methodology/">Methodology</a> · <a href="../../privacy.html">Privacy</a> · Independent site, not affiliated with any government. Not financial advice.</footer>'
            + TICK + "</body></html>")
    os.makedirs(f"{R}/countries/{slug}", exist_ok=True)
    open(f"{R}/countries/{slug}/index.html", "w").write(with_analytics(page))
    return url

def _world_page(R, SITE, with_analytics, og, stamp, now, D, places, economies):
    t0 = _t0(D)
    n = len(economies)
    rate = D["rate_usd_per_sec"]
    projected = _now(D["panel_2025_usd"], rate, now, t0)
    url = f"{SITE}/world-government-debt/"
    title = "World Government Debt Clock"
    desc = (f"IMF estimate of general government gross debt for {n} economies: {_money(D['panel_2026_usd'])} at end-2026. "
            f"Interpolated from World Economic Outlook projections, not a live ledger. Includes exchange-rate effects.")
    img = "og/places/world-government-debt.png"
    if og:
        og(f"{R}/{img}", f"World government debt · {n} economies · IMF estimate", _money0(projected),
           [("Economies", str(n)), ("End-2026 stock", _money(D["panel_2026_usd"]))],
           _signed(rate * 86400) + "/day", "#ff4d5e", "IMF WEO October 2026\ninterpolated estimate, not a live ledger")
    rows = sorted(economies, key=lambda e: -e["ratio_2026"])
    body = ""
    for e in rows:
        if e["clock"] == "us":
            href, label = "../", "US debt clock"
            note = "IMF row, not Treasury"
        elif e["clock"] == "official":
            href, label = f"../countries/{e['slug']}/", "Official clock"
            note = "IMF row; clock is separate"
        else:
            href, label = f"../countries/{e['slug']}/", "IMF estimate"
            note = "IMF estimate clock"
        share = e["debt_2026_usd"] / D["panel_2026_usd"] * 100
        body += (f'<tr data-name="{E(e["name"])}" data-ratio="{e["ratio_2026"]}" data-debt="{e["debt_2026_usd"]}" data-gdp="{e["gdp_2026_usd"]}" data-share="{share:.6f}" data-iso="{e["iso3"]}">'
                 f'<td class="c"><b><a href="{href}">{E(e["name"])}</a></b><br><a href="{href}">{E(label)}</a></td>'
                 f'<td class="num" data-l="Debt / GDP">{e["ratio_2026"]:.2f}%</td>'
                 f'<td class="num" data-l="Debt, end-2026" title="{e["debt_2026_usd"]:,.0f}">{_money(e["debt_2026_usd"])}</td>'
                 f'<td class="num" data-l="GDP, 2026" title="{e["gdp_2026_usd"]:,.0f}">{_money(e["gdp_2026_usd"])}</td>'
                 f'<td class="num" data-l="Share of panel">{share:.1f}%</td>'
                 f'<td class="m" data-l="Clock">{E(note)}</td></tr>')
    only = D.get("year_2025_only") or []
    only_names = ", ".join(E(x["name"]) for x in only) if only else "none"
    skipped = D.get("skipped") or []
    skip_lis = "".join(f'<li>{E(x["name"])} ({E(x["iso3"])}): {E(x["reason"])}</li>' for x in skipped)
    header = (f'<header class="top"><div class="topin"><a class="brand" href="../">EVERY <b>DEBT</b> CLOCK</a>{pb.nav_html(places, 1, "weo", "plnav")}'
              f'<span class="live"><span class="dot"></span><span>IMF estimate</span></span></div>'
              f'<nav class="jump"><a href="#t-total">Total</a><a href="#table">By economy</a><a href="#method">Method</a></nav></header>')
    hero = (f'<div class="hero lead" id="t-total" data-b="{D["panel_2025_usd"]}" data-r="{rate:.6f}" data-t="{t0:.0f}">'
            f'<div class="k">General government gross debt · {n} economies · US dollars · IMF estimate</div>'
            f'<div class="big num" id="hv">{_money0(projected)}</div>'
            f'<div class="sub"><span>{_signed(rate)}/sec · {_signed(rate * 86400)}/day</span>'
            f'<span class="note">interpolated from IMF end-2025 and end-2026 projections; not a live ledger</span>'
            f'<span>Since you opened this page: <span class="num" id="hs">$0</span> {"more" if rate >= 0 else "less"} debt</span></div>'
            f'<div class="trio"><div><span class="l">End-2026 stock</span><span class="num">{_money(D["panel_2026_usd"])}</span></div>'
            f'<div><span class="l">Economies in the clock</span><span class="num">{n}</span></div>'
            f'<div><span class="l">Same economies, end-2025</span><span class="num">{_money(D["panel_2025_usd"])}</span></div></div>'
            f'<div class="meta" style="margin-top:10px"><span class="badge proj">IMF ESTIMATE · interpolated</span><span class="badge">includes exchange-rate effects</span></div></div>')
    intro = (f'<section class="intro" id="intro"><div class="crumb"><a href="../">← US national debt clock</a><span>·</span>'
             f'<a href="../world/">World debt clock</a> (official clocks only)<span>·</span><a href="../countries/">All country debt clocks</a></div>'
             f'<h1>World Government Debt Clock</h1>'
             f'<p><b>What this page counts.</b> General government gross debt for {n} economies that have both a 2026 debt-to-GDP ratio (GGXWDG_NGDP) and a 2026 GDP in current US dollars (NGDPD) in the IMF World Economic Outlook, October 2026. '
             f'The end-2026 stock is <b>{_money0(D["panel_2026_usd"])}</b> ({_money(D["panel_2026_usd"])}). '
             f'The same {n} economies were {_money0(D["panel_2025_usd"])} ({_money(D["panel_2025_usd"])}) at end-2025. '
             f'The live number above is that estimate interpolated from the end-2025 stock on 1 January 2026 to the end-2026 stock on 1 January 2027. '
             f'It is not a live ledger. The dollar change includes exchange-rate effects, not only new borrowing. '
             f'This page does not use the US Treasury Debt to the Penny figure. The United States row is the IMF estimate; the <a href="../">US national debt clock</a> is a different measure.</p>'
             f'<p>Economies with both 2025 series number {D["broader_2025_count"]} and sum to {_money(D["broader_2025_usd"])} at end-2025. '
             f'{len(only)} of them have no 2026 debt ratio, so they are not in this clock: {only_names}.</p>'
             f'<p>The <a href="../world/">World Debt Clock</a> is a different total. It adds the latest official figure from each country clock on this site, in US dollars, and it does not use this IMF panel.</p>'
             f'{_src_html()}</section>')
    table = (f'<section id="table" class="wsec"><div class="sh"><span class="bar" style="background:var(--red)"></span><h2>Debt to GDP</h2>'
             f'<span class="h2n">End-2026 IMF projections · click a column to sort · this table does not tick</span></div>'
             f'<div class="tw"><table class="wt wstk" id="debt-table"><thead><tr class="hd">'
             f'<th data-k="name">Economy</th><th class="num" data-k="ratio" data-dir="desc">Debt / GDP</th>'
             f'<th class="num" data-k="debt">Debt, end-2026</th><th class="num" data-k="gdp">GDP, 2026</th>'
             f'<th class="num" data-k="share">Share of panel</th><th>Clock</th></tr></thead><tbody>{body}</tbody></table></div>'
             f'<p class="dnote">Debt = GGXWDG_NGDP ÷ 100 × NGDPD. Share = that debt ÷ the {n}-economy panel. '
             f'Official clocks linked from this table keep their own sources; the number in the row is still the IMF estimate.</p></section>')
    method = (f'<section id="method" class="wsec"><div class="sh"><span class="bar" style="background:var(--mut)"></span><h2>How it works</h2>'
              f'<span class="h2n">One IMF measure · interpolation labelled · source linked</span></div><div class="sk foot">'
              f'<p><b>The panel.</b> An economy is included when both GGXWDG_NGDP and NGDPD are positive for 2025 and for 2026. '
              f'That is {n} economies. End-2026 total {_money0(D["panel_2026_usd"])}. End-2025 total of the same economies {_money0(D["panel_2025_usd"])}.</p>'
              f'<p><b>The live number</b> = end-2025 panel + (end-2026 panel − end-2025 panel) × seconds since 2026-01-01 00:00 UTC ÷ {D["seconds_2026"]:,}. '
              f'2026 is not a leap year, so the denominator is {D["seconds_2026"]:,} seconds. The rate is {_signed(rate)} per second. '
              f'The dollar change includes exchange-rate effects. This is not a live ledger.</p>'
              f'<p><code>projected = {D["panel_2025_usd"]:,} + {rate:.4f} × (seconds since 2026-01-01 00:00 UTC)</code></p>'
              f'<p><b>Not included</b> when a 2025 or 2026 series is missing, or the debt ratio is zero. Left out of the clock:</p><ul>{skip_lis}</ul>'
              f'{_src_html()}<p>Precision source for this build: {E(D.get("precision_source") or "")}. '
              f'Machine-readable: <a href="../api/world_government_debt.json">/api/world_government_debt.json</a>. Page built {E(stamp)}.</p></div></section>')
    explore_html = ex.explore("../", places, pb.calc, cur=None, gdp=pb.GDP_BY_SLUG, kind_hint="weo-world")
    links = ('<section class="answers" id="answers"><div class="sh"><h2>More clocks</h2></div><ul>'
             '<li><a href="../world/">World debt clock</a> (official clocks only)</li>'
             '<li><a href="../">US national debt clock</a> (Treasury, a different measure)</li>'
             '<li><a href="../countries/">All country debt clocks</a></li></ul></section>')
    page = (pb.meta_head(SITE, url, title, desc, img, 1, pb.PL_CSS + world_build.CSS + CSS, _dataset_ld(title, desc, url))
            + header + '<main id="app">' + hero + intro + table + ex.search_box("../") + method + '</main>' + explore_html + links
            + '<footer class="site-foot">Every Debt Clock · IMF estimate, interpolation labelled · <a href="../methodology/">Methodology</a> · <a href="../privacy.html">Privacy</a> · Independent site, not affiliated with any government. Not financial advice.</footer>'
            + TICK + "</body></html>")
    os.makedirs(f"{R}/world-government-debt", exist_ok=True)
    open(f"{R}/world-government-debt/index.html", "w").write(with_analytics(page))
    redir = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>World Government Debt Clock</title>
<link rel="canonical" href="{url}"><meta name="robots" content="noindex">
<meta http-equiv="refresh" content="0; url=../world-government-debt/">
<script>location.replace("../world-government-debt/")</script></head>
<body><p>This page is the <a href="../world-government-debt/">World Government Debt Clock</a>.</p></body></html>
"""
    os.makedirs(f"{R}/global-debt-clock", exist_ok=True)
    open(f"{R}/global-debt-clock/index.html", "w").write(redir)
    return url

def _patch_countries(R, economies):
    path = f"{R}/countries/index.html"
    if not os.path.exists(path): return
    text = open(path).read()
    items = sorted((e for e in economies if e["clock"] == "weo"), key=lambda e: e["name"])
    lis = "".join(f'<li><a href="{E(e["slug"])}/">{E(e["name"])} national debt clock</a> — {e["ratio_2026"]:.2f}% of GDP, end-2026 IMF estimate</li>' for e in items)
    block = (f'<section id="imf-estimates"><div class="sh"><span class="bar" style="background:var(--amber)"></span><h2>IMF estimates</h2>'
             f'<span class="h2n">{len(items)} economies</span></div>'
             f'<p class="dnote">What this section counts: IMF World Economic Outlook, October 2026, general government gross debt (GGXWDG_NGDP times NGDPD), in US dollars, for economies that do not have an official clock above. '
             f'The figure is an estimate interpolated from IMF projections, not a live ledger. The dollar change includes exchange-rate effects. '
             f'The <a href="../world-government-debt/">World Government Debt Clock</a> adds the whole IMF panel, including the official-clock countries, on this one measure.</p><ul>{lis}</ul></section>')
    if "<!--WEOCOUNTRIES-->" not in text:
        raise SystemExit("weo: countries index has no <!--WEOCOUNTRIES--> placeholder")
    open(path, "w").write(text.replace("<!--WEOCOUNTRIES-->", block))

def _patch_search(R, economies):
    path = f"{R}/api/search.json"
    if not os.path.exists(path): return
    idx = json.load(open(path))
    have = {p.get("u") for p in idx.get("places", [])}
    add = [{"n": "World Government Debt", "u": "world-government-debt/", "k": "worldgov",
            "a": "global debt clock imf general government gross debt world economic outlook"}]
    for e in economies:
        if e["clock"] != "weo": continue
        add.append({"n": e["name"], "u": f'countries/{e["slug"]}/', "k": "country",
                    "a": f'{e["iso3"].lower()} {e.get("aliases") or ""} imf estimate'.strip()})
    for row in add:
        if row["u"] not in have:
            idx["places"].append(row)
            have.add(row["u"])
    json.dump(idx, open(path, "w"), separators=(",", ":"), ensure_ascii=False)

def _api(R, SITE, D, economies, now, t0):
    os.makedirs(f"{R}/api", exist_ok=True)
    out = {
        "_doc": "IMF World Economic Outlook general government gross debt, GGXWDG_NGDP times NGDPD, current US dollars. "
                "projected_now interpolates from panel_2025 on the anchor to panel_2026 one year later. Not a live ledger. Not the Treasury US total.",
        "generated": dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat(timespec="seconds"),
        "url": f"{SITE}/world-government-debt/",
        "vintage": D.get("vintage"), "source": D.get("source"), "source_url": D.get("source_url"),
        "gdp_source_url": D.get("gdp_source_url"), "precision_source": D.get("precision_source"),
        "anchor": D.get("anchor"), "seconds_2026": D.get("seconds_2026"),
        "panel_count": D["panel_count"], "panel_2026_usd": D["panel_2026_usd"], "panel_2025_usd": D["panel_2025_usd"],
        "projected_now_usd": round(_now(D["panel_2025_usd"], D["rate_usd_per_sec"], now, t0)),
        "rate_usd_per_sec": D["rate_usd_per_sec"],
        "broader_2025_count": D["broader_2025_count"], "broader_2025_usd": D["broader_2025_usd"],
        "year_2025_only": D.get("year_2025_only"), "skipped": D.get("skipped"),
        "economies": [{"iso3": e["iso3"], "name": e["name"], "slug": e["slug"], "clock": e["clock"],
                       "ratio_2025": e["ratio_2025"], "ratio_2026": e["ratio_2026"],
                       "debt_2025_usd": e["debt_2025_usd"], "debt_2026_usd": e["debt_2026_usd"],
                       "gdp_2026_usd": e["gdp_2026_usd"], "rate_usd_per_sec": e["rate_usd_per_sec"],
                       "url": f"{SITE}/" if e["clock"] == "us" else f"{SITE}/countries/{e['slug']}/"} for e in economies],
    }
    json.dump(out, open(f"{R}/api/world_government_debt.json", "w"), indent=1, ensure_ascii=False)
    open(f"{R}/api/world_government_debt.json", "a").write("\n")

def _apply_official(economies, places):
    """A live country clock wins over the IMF page, even if the data file was fetched before that clock existed."""
    by_iso = {}
    for p in places:
        if p.get("kind") != "country": continue
        iso = p.get("iso3") or ISO2.get(p.get("country") or "")
        if iso: by_iso[iso] = p
    for e in economies:
        if e["iso3"] == "USA":
            e["clock"] = "us"
            e["name"] = "United States"
            continue
        p = by_iso.get(e["iso3"])
        if p:
            e["clock"] = "official"
            e["slug"] = p["slug"]
            e["name"] = p["name"]
        else:
            e["clock"] = "weo"
    return economies

def build(R, SITE, with_analytics, og, stamp, now, places):
    D = load(R)
    if not D or not D.get("economies"): return []
    economies = _apply_official(D["economies"], places)
    if any(not e.get("rate_usd_per_sec") for e in economies):
        raise SystemExit("weo: an economy has a zero ticker rate")
    pool, gdp = _pool(places, economies), _gdp(economies)
    urls = [_world_page(R, SITE, with_analytics, og, stamp, now, D, places, economies)]
    for e in economies:
        if e["clock"] == "weo":
            urls.append(_country_page(R, SITE, with_analytics, og, stamp, now, e, D, places, pool, gdp))
    _patch_countries(R, economies)
    _patch_search(R, economies)
    _api(R, SITE, D, economies, now, _t0(D))
    return urls
