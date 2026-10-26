"""Place pages (US states now, countries later), rendered from places/<slug>.json.
Called from build.py. Adding a place is a data file: places/<slug>.json with kind "state" or "country".
Each place page shows its official annual figures and, when two consecutive official figures exist,
a clearly labelled projection: latest official total + (latest - prior) / (seconds between them) x (seconds since latest)."""
import json, os, html, glob, datetime as dt
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
# Sections shown in the place nav. A section appears in the nav once it has at least one live place.
SECTIONS = [("state", "states", "States", "US state debt clocks"),
            ("country", "countries", "Countries", "Country debt clocks")]
# Shown on an index page as "coming soon" (names only, no numbers).
COMING = {"state": ["California", "Florida", "New York"], "country": ["Canada"]}

def load(R):
    out = []
    for f in sorted(glob.glob(f"{R}/places/*.json")):
        p = json.load(open(f))
        if p.get("status") == "live": out.append(p)
    return out

def _d(s): return dt.date.fromisoformat(s)
def _fd(s): return _d(s).strftime("%b %-d, %Y")
def _usd0(x): return ("−$" if x < 0 else "$") + f"{abs(x):,.0f}"
def _usd2(x): return ("−$" if x < 0 else "$") + f"{abs(x):,.2f}"
def _b(x): return f"${x/1e12:,.2f} trillion" if abs(x) >= 1e12 else f"${x/1e9:,.2f} billion"
def _eod(s): return dt.datetime.combine(_d(s), dt.time(23, 59, 59), CT).timestamp()

def calc(p):
    """Totals and the labelled trend. Returns None for the trend unless every component has a prior official figure."""
    cs = p["components"]
    total = sum(c["value"] for c in cs)
    dates = {c["as_of"] for c in cs}
    t0 = max(_eod(c["as_of"]) for c in cs)
    rate = None
    if all(c.get("prior_value") and c.get("prior_as_of") for c in cs):
        rate = sum((c["value"] - c["prior_value"]) / (_eod(c["as_of"]) - _eod(c["prior_as_of"])) for c in cs)
    return {"total": total, "t0": t0, "rate": rate, "same_date": len(dates) == 1, "as_of": max(dates)}

def nav_html(places, depth, current=None):
    """Top place nav: United States, then one link per section that has a live place."""
    up = "../" * depth
    kinds = {p["kind"] for p in places}
    items = [(f"{up}", "United States", current == "us")]
    items += [(f"{up}{d}/", lab, current == k) for k, d, lab, _ in SECTIONS if k in kinds]
    return '<nav class="pl">' + "".join(f'<a href="{h}"{" class=on" if on else ""}>{lab}</a>' for h, lab, on in items) + "</nav>"

PL_CSS = """nav.pl{display:flex;gap:6px;margin:12px 0 0;flex-wrap:wrap}nav.pl a{font-size:12px;color:#8a97ab;border:1px solid #1c2533;border-radius:999px;padding:4px 11px;background:#0e131b}
nav.pl a.on{color:#e8edf5;border-color:#3a4a63}.lab{font-size:11px;color:#8a97ab;text-transform:uppercase;letter-spacing:.08em;margin-top:14px}
.off{font:600 clamp(20px,5.5vw,30px) ui-monospace,Menlo,monospace;font-variant-numeric:tabular-nums;margin:2px 0}tr.sub td{color:#8a97ab;font-size:12.5px}
.pp3{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px}.pp3 div{background:#121925;border-radius:10px;padding:8px 10px}
.pp3 .l{display:block;font-size:10.5px;color:#5c687a;text-transform:uppercase;letter-spacing:.08em}.pp3 .n{font:600 15px ui-monospace,Menlo,monospace}
ul.places{padding-left:18px}ul.places li{margin:6px 0}.soon{color:#5c687a}@media(max-width:560px){.pp3{grid-template-columns:1fr}}"""

def build(R, SITE, with_analytics, PAGE_CSS, ANS_CSS, og, stamp, now):
    places = load(R)
    urls = []
    os.makedirs(f"{R}/og/places", exist_ok=True)
    for k, d, lab, desc_ in SECTIONS:
        live = [p for p in places if p["kind"] == k]
        if not live: continue
        for p in live: urls.append(place_page(R, SITE, with_analytics, PAGE_CSS, ANS_CSS, og, stamp, now, p, d, places))
        urls.append(index_page(R, SITE, with_analytics, PAGE_CSS, ANS_CSS, k, d, lab, desc_, live, places))
    return urls

def head(SITE, url, title, desc, img, css, ld=""):
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}"><link rel="canonical" href="{url}">
<meta property="og:type" content="article"><meta property="og:site_name" content="Every Debt Clock"><meta property="og:url" content="{url}">
<meta property="og:title" content="{html.escape(title)}"><meta property="og:description" content="{html.escape(desc)}">
<meta property="og:image" content="{SITE}/{img}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{html.escape(title)}">
<meta name="twitter:description" content="{html.escape(desc)}"><meta name="twitter:image" content="{SITE}/{img}">
<meta name="theme-color" content="#07090d"><style>{css}</style>
{ld}</head><body><main>"""

def place_page(R, SITE, with_analytics, PAGE_CSS, ANS_CSS, og, stamp, now, p, sec_dir, places):
    c = calc(p); pop = p["population"]; cs = p["components"]; name = p["name"]; dem = p.get("demonym", "resident")
    url = f"{SITE}/{sec_dir}/{p['slug']}/"
    proj = c["total"] + (c["rate"] * (now - c["t0"]) if c["rate"] else 0)
    pp_off = c["total"] / pop["value"]
    as_of = _fd(c["as_of"])
    title = f"{name} Debt Clock: State and Local Debt, {_b(c['total'])} (Official, {as_of})"
    desc = (f"{name} state and local government debt: {_b(c['total'])} at fiscal year-end {as_of} ("
            + " + ".join(f"{c_['short'].lower()} {_b(c_['value'])}" for c_ in cs)
            + f"), {_usd0(pp_off)} per {dem}. Official annual figures with sources, plus a clearly labelled projection.")
    img = f"og/places/{p['slug']}.png"
    if og:
        og(f"{R}/{img}", f"{name} state + local debt · projected", _usd0(proj),
           [(f"Official, {as_of}", _usd0(c["total"])), (f"Per {dem} (official)", _usd2(pp_off))],
           "PROJECTED" if c["rate"] else "OFFICIAL", "#ff4d5e",
           f"{p.get('publisher', 'official data')}, {as_of}\nat last year's pace · annual data" if c["rate"] else f"{p.get('publisher', 'official data')}, {as_of}")
    ld = '<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "Dataset", "name": f"{name} state and local government debt", "description": desc, "url": url,
        "isAccessibleForFree": True, "creator": {"@type": "Organization", "name": "Every Debt Clock", "url": SITE + "/"},
        "spatialCoverage": {"@type": "Place", "name": name}, "temporalCoverage": f"{min(h[0] for c_ in cs for h in c_.get('history', [[c_['as_of']]]))}/{c['as_of']}",
        "isBasedOn": sorted({c_["source_url"] for c_ in cs} | {pop["source_url"]})}).replace("</", "<\\/") + "</script>"
    def comp_table(c_):
        rows = "".join(f'<tr{" class=sub" if b.get("sub") else ""}><td>{html.escape(b["label"].strip())}</td><td class="num">{_usd0(b["value"])}</td></tr>' for b in c_.get("breakdown", []))
        return (f'<h2>{html.escape(c_["label"])}: {_usd0(c_["value"])}</h2><p class="k">Official, fiscal year-end {_fd(c_["as_of"])} · '
                f'<a href="{html.escape(c_["source_url"])}" rel="noopener">{html.escape(c_["source_name"])}</a> ({html.escape(c_.get("source_locator", ""))})</p>'
                f'<table><tr><th>Part</th><th>Amount</th></tr>{rows}<tr><td><b>Total</b></td><td class="num"><b>{_usd0(c_["value"])}</b></td></tr></table>'
                f'<p>{html.escape(c_.get("includes", ""))}</p>')
    # history: combined by year where every component has that date
    hist = None
    if all(c_.get("history") for c_ in cs):
        ds = sorted(set.intersection(*[{h[0] for h in c_["history"]} for c_ in cs]))
        hv = {d: sum(dict(map(tuple, c_["history"]))[d] for c_ in cs) for d in ds}
        hist = "<h2>By year (official)</h2><table><tr><th>Fiscal year-end</th>" + "".join(f'<th>{html.escape(c_["short"])}</th>' for c_ in cs) + "<th>Combined</th><th>Change</th></tr>"
        for k, d in enumerate(reversed(ds)):
            prev = ds[len(ds) - 2 - k] if len(ds) - 2 - k >= 0 else None
            ch = (hv[d] - hv[prev]) if prev else None
            hist += (f"<tr><td>{_fd(d)}</td>" + "".join(f'<td class="num">{_b(dict(map(tuple, c_["history"]))[d])}</td>' for c_ in cs)
                     + f'<td class="num">{_b(hv[d])}</td><td class="num">{"—" if ch is None else ("+" if ch >= 0 else "−") + _b(abs(ch))}</td></tr>')
        hist += "</table>"
    if c["rate"]:
        prior_total = sum(c_["prior_value"] for c_ in cs)
        method = (f"<p><b>How the clock ticks.</b> {name} debt is published once a year, not daily, so the ticking number is a projection, not an official figure. "
                  f"It starts at the latest official combined total, {_usd0(c['total'])} at the end of {as_of}, and adds each part's change over its latest official year "
                  f"(combined: {_usd0(c['total'])} − {_usd0(prior_total)} = {_usd0(c['total'] - prior_total)} over {(_d(c['as_of']) - _d(cs[0]['prior_as_of'])).days} days), "
                  f"which is about <b>{_usd2(c['rate'])} per second</b> or {_b(c['rate'] * 86400)} a day.</p>"
                  f"<p><code>projected = {c['total']:,.0f} + {c['rate']:,.4f} × (seconds since {as_of} 11:59:59 PM CT)</code></p>"
                  f"<p>It will drift from reality: governments borrow in lumps when bonds are sold and repay on schedules, so the actual path is not a straight line. "
                  f"When the next annual reports come out, the clock re-bases to the new official figures. Per {dem} figures use the Census estimate for {_fd(pop['as_of'])} and are not projected.</p>")
    else:
        method = f"<p><b>Why this number doesn't tick.</b> Only one official year is available, so there is no defensible trend to project. The figure shown is the official total.</p>"
    srcs = []
    for c_ in cs: srcs.append((c_["source_name"], c_["source_url"]))
    srcs.append((pop["source_name"], pop["source_url"]))
    src = "<h2>Sources</h2><ul>" + "".join(f'<li><a href="{html.escape(u)}" rel="noopener">{html.escape(n)}</a></li>' for n, u in srcs) + "</ul>"
    notes = "<h2>Notes</h2><ul>" + "".join(f"<li>{html.escape(n)}</li>" for n in p.get("notes", []) + [p.get("fiscal_year_end_note", "")] if n) + \
            "<li>Figures from source tables may not add exactly because of rounding in the source.</li></ul>"
    trio = "".join(f'<div><span class="l">{html.escape(c_["short"])} · {_fd(c_["as_of"])}</span><span class="n">{_b(c_["value"])}</span></div>' for c_ in cs)
    trio += f'<div><span class="l">Per {html.escape(dem)} (official)</span><span class="n">{_usd2(pp_off)}</span></div>'
    data = json.dumps({"base": c["total"], "t0": c["t0"], "rate": c["rate"] or 0, "pop": pop["value"]})
    body = f"""<a class="brand" href="../../">EVERY <b>DEBT</b> CLOCK</a>
{nav_html(places, 2, p['kind'])}
<h1>{html.escape(name)} Debt Clock</h1>
<p class="k">State + local government debt in {html.escape(name)}</p>
<div class="lab">{'Projected now at last year\'s pace (not an official figure)' if c['rate'] else 'Official total'}</div>
<div class="v" id="v">{_usd0(proj)}</div>
<span class="b">{'PROJECTED · from official ' + as_of if c['rate'] else 'OFFICIAL · ' + as_of}</span><span class="b">ANNUAL DATA · {html.escape(p.get('publisher', ''))}</span>
<div class="lab">Official combined total, fiscal year-end {as_of}</div>
<div class="off">{_usd0(c['total'])}</div>
<div class="pp3">{trio}</div>
<p><b>Answer.</b> {html.escape(name)} state and local governments owed <b>{_b(c['total'])}</b> at the end of fiscal year {_d(c['as_of']).year} ({as_of}): {' and '.join(_b(c_['value']) + ' of ' + html.escape(c_['label'].lower()) for c_ in cs)}. That is <b>{_usd2(pp_off)} per {html.escape(dem)}</b>: the combined total divided by
the Census Bureau's estimate of {pop['value']:,} {html.escape(name)} residents on {_fd(pop['as_of'])}. These are the latest official figures. {html.escape(p.get('next_update', ''))}</p>
<p><b>How often it's published.</b> {html.escape(p.get('cadence', ''))}</p>
{method}
{''.join(comp_table(c_) for c_ in cs)}
{hist or ''}
{notes}
{src}
<a class="cta" href="../../">See the live US national debt clock →</a>
<footer>Every figure on this page is an official published number unless it is labelled "projected". The projected number in this page's text is as of {stamp}; it ticks live in your browser.</footer>
</main><script>(function(){{const D={data},v=document.getElementById('v');if(!D.rate)return;
const f=n=>'$'+Math.round(n).toLocaleString('en-US');(function t(){{v.textContent=f(D.base+D.rate*(Date.now()/1000-D.t0));requestAnimationFrame(t)}})()}})()</script>
</body></html>"""
    page = head(SITE, url, title, desc, img, PAGE_CSS + ANS_CSS + PL_CSS, ld) + body
    os.makedirs(f"{R}/{sec_dir}/{p['slug']}", exist_ok=True)
    open(f"{R}/{sec_dir}/{p['slug']}/index.html", "w").write(with_analytics(page))
    return url

def index_page(R, SITE, with_analytics, PAGE_CSS, ANS_CSS, kind, sec_dir, lab, desc_, live, places):
    url = f"{SITE}/{sec_dir}/"
    items = ""
    for p in sorted(live, key=lambda x: x["name"]):
        c = calc(p)
        items += (f'<li><a href="{p["slug"]}/"><b>{html.escape(p["name"])}</b></a>: {_b(c["total"])} state + local debt, official {_fd(c["as_of"])} '
                  f'({_usd0(c["total"] / p["population"]["value"])} per {html.escape(p.get("demonym", "resident"))})</li>')
    soon = [n for n in COMING.get(kind, []) if n not in {p["name"] for p in live}]
    items += "".join(f'<li class="soon">{html.escape(n)}: coming soon</li>' for n in soon)
    if kind == "state": items += '<li class="soon">The other states: coming soon</li>'
    title = f"{lab} Debt Clocks | Every Debt Clock"
    desc = f"{desc_}: official government debt figures with sources, starting with " + ", ".join(p["name"] for p in live) + "."
    body = f"""<a class="brand" href="../">EVERY <b>DEBT</b> CLOCK</a>
{nav_html(places, 1, kind)}
<h1>{html.escape(desc_)}</h1>
<p>Each page shows the latest official debt figures for the place, who publishes them and how often, with every number linked to its source.
Most state and local debt is reported once a year, so these clocks say clearly which numbers are official and which are projected.</p>
<ul class="places">{items}</ul>
<a class="cta" href="../">See the live US national debt clock →</a>
<footer>Pages are rebuilt with the site; figures change when the official source publishes a new report.</footer></main></body></html>"""
    page = head(SITE, url, title, desc, "og/home.png", PAGE_CSS + ANS_CSS + PL_CSS) + body
    os.makedirs(f"{R}/{sec_dir}", exist_ok=True)
    open(f"{R}/{sec_dir}/index.html", "w").write(with_analytics(page))
    return url
