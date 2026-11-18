"""Free embeddable debt clocks.

build.py calls apply() on every run, including a plain push (the deploy rebuilds pages from
repo data and does not commit them). One self-contained page per live clock:

  /embed/us/
  /embed/world/
  /embed/states/<slug>/          (50 states and Washington, DC)
  /embed/countries/<slug>/       (official clocks and IMF-estimate country pages)

Numbers use the same inputs as the full pages: debt_total in data/data.json for the US,
places_build.calc() for each places/<slug>.json, world_build.compute() for /world/, and the
IMF or QPSD series that weo_build.py puts on the remaining country pages. Clock pages are
noindex, carry no analytics, and do not set X-Frame-Options or a frame-ancestors policy.
GitHub Pages does not send X-Frame-Options, which is what lets another site iframe these URLs.

The /embed/ directory is a normal indexable page and is the only embed URL in the sitemap.
On a clock page the offer sits inside #intro, after the summary paragraphs. The US homepage's
app.js detaches #intro, drops the SSR block, and puts #intro back under the live ticker, so the
offer travels with the summary and the ticker stays first.
"""
import hashlib, html, json, os, re, shutil, time
import xml.etree.ElementTree as ET
import places_build

E = html.escape
BYLINE = "Live debt clock by EveryDebtClock.com"
GET = "Get this clock for your site"
LIMIT = 15 * 1024
DESC_LIMIT = 155
WIDGET_PHRASE = "Free widget for your site."
SKIP_DIRS = {".git", "cache", "pipeline", "og", "dist", "data", "__pycache__", "node_modules", ".venv", "venv"}
OLD_PANEL_RE = re.compile(r'<div class="embedbox">[\s\S]*?</script></div>\n?')
NEW_PANEL_RE = re.compile(r'<aside class="embedbox"[\s\S]*?</script></aside>\n?')
EXAMPLES = ("us", "texas", "world")
ICON = ('<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 32 32%22%3E'
        '%3Crect width=%2232%22 height=%2232%22 rx=%226%22 fill=%22%2307090d%22/%3E%3Ctext x=%2216%22 y=%2223%22 '
        'font-size=%2220%22 text-anchor=%22middle%22 fill=%22%23ff4d5e%22 font-family=%22Arial%22 font-weight=%22900%22%3E'
        '$%3C/text%3E%3C/svg%3E">')
PITCH = ("A free debt clock widget for a website. Paste one iframe. "
         "The clock shows the name, the live total, the per-second rate, and the source. "
         "Copy it into a blog post, a local news story, or a page from a political or civic group. "
         "The link under the frame points back to the full page. No account. "
         "The clock page sets no cookies and loads no analytics.")
OFFER_CSS = (
    ".embedbox{margin:12px 0 2px;padding:10px 12px;border:1px solid var(--line,#1c2533);border-radius:14px;background:var(--panel,#121925);color:var(--txt,#e8edf5)}"
    ".embedbox .embedhd{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:0 0 8px}"
    ".embedbox .embedhd b{font-size:14px;font-weight:650}"
    ".embedbox .embedrow{display:grid;grid-template-columns:minmax(0,280px) minmax(0,1fr);gap:10px}"
    ".embedbox iframe{display:block;width:100%;height:148px;border:0;border-radius:10px;background:#0e131b}"
    ".embedbox textarea{display:block;width:100%;height:148px;margin:0;resize:vertical;box-sizing:border-box;background:#0a0e15;color:#e8edf5;border:1px solid #1c2533;border-radius:8px;padding:8px;font:12px/1.45 ui-monospace,Menlo,Consolas,monospace}"
    ".embedcopy{flex:none;background:#121925;color:#e8edf5;border:1px solid #1c2533;border-radius:8px;padding:6px 12px;font:inherit;font-size:13px;cursor:pointer}"
    "a.navembed{margin-left:12px;font-size:13px;font-weight:650}"
    "@media (max-width:640px){.embedbox{padding:8px}.embedbox .embedhd b{font-size:13px}.embedbox .embedrow{grid-template-columns:1fr}.embedbox iframe{height:132px}.embedbox textarea{height:72px}}"
)
COPY_JS = ('<script>(function(){var box=document.currentScript.parentNode,t=box.querySelector("textarea"),c=box.querySelector(".embedcopy");'
           'if(!c||!t)return;c.addEventListener("click",function(){var s=t.value,done=function(){c.textContent="Copied";setTimeout(function(){c.textContent="Copy code"},1500)};'
           'if(navigator.clipboard&&navigator.clipboard.writeText)navigator.clipboard.writeText(s).then(done,function(){t.select();document.execCommand("copy");done()});'
           'else{t.select();document.execCommand("copy");done()}})})();</script>')

def project(base, rate, t0, t, freeze, steps):
    """Same recurrence as core.js val(): base + rate * (t - t0) + step ramps, frozen at the debt limit."""
    if freeze is not None and t > freeze:
        t = freeze
    v = base + (rate or 0) * (t - t0)
    for q in steps or []:
        s0, s1, a = q[0], q[1], q[2]
        if s1 != s0:
            v += a * min(1.0, max(0.0, (t - s0) / (s1 - s0)))
    return v

def _total(sym, v):
    return ("−" if v < 0 else "") + sym + f"{abs(v):,.0f}"

def _rate(sym, r):
    if not r:
        return sym + "0.00/sec"
    return ("−" if r < 0 else "+") + sym + f"{abs(r):,.2f}/sec"

def snippet(site, embed_path, page_url, title, anchor):
    """iframe plus a plain backlink. The backlink is outside the iframe so it counts when the frame is not crawled."""
    return (f'<iframe src="{site}/{embed_path}" width="100%" height="160" style="border:0" title="{E(title, quote=True)}"></iframe>\n'
            f'<a href="{page_url}">{E(anchor)}</a>')

def panel_html(code, preview, title):
    """Visible offer: live preview of this page's /embed/ URL, the snippet, and Copy code."""
    return ('<aside class="embedbox" aria-label="Add this clock to your site">'
            '<div class="embedhd"><b>Add this clock to your site</b>'
            '<button type="button" class="embedcopy">Copy code</button></div>'
            '<div class="embedrow">'
            f'<iframe src="{E(preview, quote=True)}" title="{E(title, quote=True)}" width="100%" height="148" style="border:0" loading="lazy"></iframe>'
            f'<textarea readonly rows="4" spellcheck="false" aria-label="Embed code">{E(code)}</textarea>'
            f'</div>{COPY_JS}</aside>\n')

def set_panel(page, panel):
    """Put the offer at the end of #intro, after the summary paragraphs. Strip any older control first."""
    page = OLD_PANEL_RE.sub("", page)
    page = NEW_PANEL_RE.sub("", page)
    marker = '<section class="intro" id="intro">'
    at = page.find(marker)
    if at < 0:
        raise RuntimeError("no intro section for the embed offer")
    end = page.find("</section>", at + len(marker))
    if end < 0:
        raise RuntimeError("intro section does not close")
    return page[:end] + panel + page[end:]

def fit_widget(desc):
    """Append the widget phrase only when the visible description stays within DESC_LIMIT."""
    raw = html.unescape(desc).strip()
    if "free widget for your site" in raw.lower():
        return raw
    base = raw if raw.endswith((".", "!", "?")) else raw + "."
    extra = " " + WIDGET_PHRASE
    if len(base) + len(extra) <= DESC_LIMIT:
        return base + extra
    return raw

def patch_desc(page):
    """Clock-page meta description only. Titles are left as written."""
    m = re.search(r'<meta name="description" content="([^"]*)"', page)
    if not m:
        return page
    old_esc = m.group(1)
    new = fit_widget(old_esc)
    new_esc = E(new)
    if new_esc == old_esc:
        return page
    page = page.replace(f'<meta name="description" content="{old_esc}"', f'<meta name="description" content="{new_esc}"', 1)
    for attr in ('property="og:description"', 'name="twitter:description"'):
        page = page.replace(f'<meta {attr} content="{old_esc}"', f'<meta {attr} content="{new_esc}"')
    return page

def ensure_offer_css(page):
    """Pages that do not load style.css (milestone pages) still get the compact offer."""
    if 'class="embedbox"' not in page or "style.css" in page or 'id="embed-offer"' in page:
        return page
    return page.replace("</head>", f'<style id="embed-offer">{OFFER_CSS}</style></head>', 1)

def _rel_prefix(chunk):
    m = re.search(r'href="([^"]*)"', chunk)
    if not m:
        return ""
    href = m.group(1)
    if href.startswith("/") and not href.startswith("//"):
        return "/"
    ups = re.match(r"(?:\.\./)*", href)
    return ups.group(0) if ups else ""

def add_header_embed(page):
    """'Embed' in the top nav. Pages with only a brand link get the same link beside it."""
    nav = re.search(r'<nav class="plnav">[\s\S]*?</nav>', page)
    if nav:
        if re.search(r'href="[^"]*embed/"', nav.group(0)):
            return page
        link = f'<a href="{_rel_prefix(nav.group(0))}embed/">Embed</a>'
        return page.replace(nav.group(0), nav.group(0).replace("</nav>", link + "</nav>", 1), 1)
    if 'class="navembed"' in page:
        return page
    brand = re.search(r'<a class="brand" href="([^"]*)">[\s\S]*?</a>', page)
    if brand:
        link = f'<a class="navembed" href="{_rel_prefix(brand.group(0))}embed/" style="margin-left:12px;font-size:13px;font-weight:650">Embed</a>'
        return page[:brand.end()] + link + page[brand.end():]
    divb = re.search(r'<div class="brand">[\s\S]*?</div>', page)
    if divb and '<a class="brand"' not in page:
        link = '<a class="navembed" href="/embed/" style="margin-left:12px;font-size:13px;font-weight:650">Embed</a>'
        return page[:divb.end()] + link + page[divb.end():]
    return page

def _has_header_embed(page):
    nav = re.search(r'<nav class="plnav">[\s\S]*?</nav>', page)
    if nav and re.search(r'href="[^"]*embed/"', nav.group(0)):
        return True
    return 'class="navembed"' in page and "embed/" in page

def add_footer(page):
    """Link /embed/ from the site footer. Depth is copied from the Methodology or Privacy link already there."""
    m = re.search(r'<footer class="site-foot">(?:(?!</footer>).)*?</footer>', page, re.S)
    if not m or re.search(r'href="(?:\.\./|/)*embed/"', m.group(0)):
        return page
    foot = m.group(0)
    for pat in (r'<a href="((?:\.\./)*)methodology/">', r'<a href="((?:\.\./)*)privacy(?:\.html|/)">', r'<a href="(/)(?:methodology/|privacy(?:\.html|/))">'):
        mm = re.search(pat, foot)
        if not mm:
            continue
        prefix = mm.group(1)
        link = f'<a href="{prefix}embed/">Embed a clock</a> · '
        return page.replace(foot, foot[:mm.start()] + link + foot[mm.start():], 1)
    return page.replace(foot, foot.replace("</footer>", ' · <a href="embed/">Embed a clock</a></footer>', 1), 1)

def _analytics(R):
    raw = os.environ.get("ANALYTICS_HTML")
    path = os.path.join(R, "analytics.html")
    if raw is None and os.path.exists(path):
        raw = open(path).read()
    raw = (raw or "").strip()
    block = f"<!--ANALYTICS-->{raw}<!--/ANALYTICS-->"
    def apply_html(page):
        if "<!--ANALYTICS-->" in page:
            return re.sub(r"<!--ANALYTICS-->.*?<!--/ANALYTICS-->", lambda m: block, page, flags=re.S)
        return page.replace("</head>", block + "\n</head>", 1)
    return apply_html

def _clock_html(c, now, embed_home):
    sym, rate = c["sym"], c["rate"] or 0
    frozen = c["freeze"] is not None and now > c["freeze"]
    shown_rate = 0 if frozen else rate
    cfg = {"b": c["base"], "r": rate, "t0": c["t0"], "sym": sym}
    if c["freeze"] is not None:
        cfg["fz"] = c["freeze"]
    if c["steps"]:
        cfg["steps"] = [[q[0], q[1], q[2]] for q in c["steps"]]
    blob = json.dumps(cfg, separators=(",", ":")).replace("<", "\\u003c")
    klass = "r dn" if shown_rate < 0 else "r" if shown_rate > 0 else "r z"
    label, source = c["label"], c["source"]
    page_url = c["page_url"]
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>{E(c["iframe_title"])}</title>
<script>if(new URLSearchParams(location.search).get("theme")==="light")document.documentElement.classList.add("light")</script>
<style>
:root{{color-scheme:dark;--bg:#0e131b;--fg:#e8edf5;--mut:#8a97ab;--dim:#6a778c;--link:#7cb6ff;--up:#3dca8e;--dn:#ff5d6c}}
html.light{{color-scheme:light;--bg:#f6f7fb;--fg:#161a22;--mut:#526074;--dim:#5c6b80;--link:#0b57d0;--up:#067647;--dn:#c42334}}
*{{box-sizing:border-box}}html{{-webkit-text-size-adjust:100%}}html,body{{height:100%;margin:0;background:var(--bg);color:var(--fg)}}
body{{font:13px/1.35 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;overflow:hidden}}
.w{{height:100%;display:flex;flex-direction:column;justify-content:center;gap:1px;padding:8px 12px 7px;border-left:3px solid #ff4d5e}}
.n,.v,.s{{min-width:0}}.n{{font-size:12px;color:var(--mut);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.v{{display:block;max-width:100%;font:700 clamp(15px,5.4vw,26px)/1.15 ui-monospace,Menlo,Consolas,monospace;font-variant-numeric:tabular-nums;letter-spacing:-.03em;white-space:nowrap;overflow:hidden}}
.r{{font:600 12.5px/1.3 ui-monospace,Menlo,Consolas,monospace;color:var(--up);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.r.dn{{color:var(--dn)}}.r.z{{color:var(--dim);font-weight:500}}
.s{{font-size:11px;color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.cr{{display:flex;flex-wrap:wrap;gap:2px 10px;align-items:baseline}}
a.by{{color:var(--link);font-size:12px;text-decoration:underline;text-underline-offset:2px}}
a.get{{color:var(--link);font-size:11px;text-decoration:underline;text-underline-offset:2px}}
</style>{ICON}</head><body><div class="w">
<div class="n" title="{E(label, quote=True)}">{E(label)}</div>
<div class="v" id="v">{E(_total(sym, project(c["base"], rate, c["t0"], now, c["freeze"], c["steps"])))}</div>
<div class="{klass}" id="r">{E(_rate(sym, shown_rate))}</div>
<div class="s" title="{E("Source: " + source, quote=True)}">Source: {E(source)}</div>
<div class="cr"><a class="by" href="{E(page_url, quote=True)}" target="_top">{BYLINE}</a><a class="get" href="{E(embed_home, quote=True)}" target="_blank" rel="noopener">{GET}</a></div>
</div><script type="application/json" id="c">{blob}</script>
<script>(function(){{var C=JSON.parse(document.getElementById("c").textContent);
var nf=new Intl.NumberFormat("en-US",{{maximumFractionDigits:0}}),nf2=new Intl.NumberFormat("en-US",{{minimumFractionDigits:2,maximumFractionDigits:2}});
var v=document.getElementById("v"),r=document.getElementById("r");
function val(t){{if(C.fz&&t>C.fz)t=C.fz;var s=C.b+C.r*(t-C.t0),i,q;for(i=0;i<(C.steps||[]).length;i++){{q=C.steps[i];if(q[1]!==q[0])s+=q[2]*Math.min(1,Math.max(0,(t-q[0])/(q[1]-q[0])))}}return s}}
function fit(){{if(!v.clientWidth)return;var s=26;v.style.fontSize=s+"px";while(v.scrollWidth>v.clientWidth+1&&s>11){{s--;v.style.fontSize=s+"px"}}}}
function paint(){{var t=Date.now()/1000,held=C.fz&&t>C.fz,x=val(t),rate=held?0:C.r;
v.textContent=(x<0?"−":"")+C.sym+nf.format(Math.abs(x));r.className="r"+(rate<0?" dn":rate?"":" z");
r.textContent=rate?(rate<0?"−":"+")+C.sym+nf2.format(Math.abs(rate))+"/sec":C.sym+"0.00/sec";fit()}}
(function loop(){{paint();requestAnimationFrame(loop)}})()}})();</script></body></html>"""

def _entry(**kw):
    kw.setdefault("freeze", None)
    kw.setdefault("steps", [])
    return kw

def _us_clock(R, site):
    D = json.load(open(os.path.join(R, "data", "data.json")))
    td = (D.get("tickers") or {}).get("debt_total") or {}
    if td.get("status") != "ok":
        raise RuntimeError("embed: US debt_total ticker is not ok")
    return _entry(file="index.html", group="United States", name="United States", headline="national debt",
                  label="US national debt", source=td.get("source_name") or "Treasury, Debt to the Penny", sym="$",
                  base=td["base"], rate=td.get("rate") or 0, t0=td["t0"], freeze=td.get("freeze_t"), steps=td.get("steps") or [],
                  page_url=site + "/", embed_path="embed/us/", preview="us/", iframe_title="US debt clock",
                  anchor="US debt clock by EveryDebtClock.com", slug="us")

def _place_clock(p, site):
    c = places_build.calc(p)
    kind = p["kind"]
    sec = "states" if kind == "state" else "countries"
    sym = (p.get("currency") or {}).get("symbol") or "$"
    name, head = p["name"], places_build.texts(p)["head"]
    return _entry(file=f"{sec}/{p['slug']}/index.html", group="States" if kind == "state" else "Countries",
                  name=name, headline=head, label=f"{name} {head}", source=p.get("publisher") or "official data",
                  sym=sym, base=c["total"], rate=c["rate"] or 0, t0=c["t0"],
                  page_url=f"{site}/{sec}/{p['slug']}/", embed_path=f"embed/{sec}/{p['slug']}/",
                  preview=f"{sec}/{p['slug']}/", iframe_title=f"{name} debt clock",
                  anchor=f"{name} debt clock by EveryDebtClock.com", slug=p["slug"])

def _world_clock(R, site, now, world):
    if world is None:
        places = places_build.load(R)
        if not places or not os.path.exists(os.path.join(R, "data", "world_weo_debt.json")):
            return None
        import world_build
        D = json.load(open(os.path.join(R, "data", "data.json")))
        td = (D.get("tickers") or {}).get("debt_total") or {}
        us = {"official": td.get("base"), "date": td.get("as_of"), "base": td.get("base"), "rate": td.get("rate") or 0,
              "pop": 0, "pop_date": None}
        world = world_build.compute(R, places, us, now)
    if not world:
        return None
    # Same rounding the world page bakes into data-b / data-r / data-t.
    return _entry(file="world/index.html", group="World", name="World", headline="general government gross debt",
                  label="World general government debt",
                  source="National releases, Eurostat, QPSD, and IMF WEO", sym="$",
                  base=float(f"{world['now_total']:.2f}"), rate=float(f"{world['rate_s']:.6f}"), t0=float(f"{now:.0f}"),
                  page_url=f"{site}/world/", embed_path="embed/world/", preview="world/",
                  iframe_title="World debt clock", anchor="World debt clock by EveryDebtClock.com", slug="world")

def _weo_clocks(R, site):
    """Country pages that are not a places/<slug>.json clock: IMF estimates, and QPSD stocks where those replace the IMF line.

    A country slug can match a US state slug (Georgia). Those stay separate: /embed/countries/ vs /embed/states/.
    """
    import weo_build
    import world_build
    import world_sources
    D = weo_build.load(R)
    if not D or not D.get("economies"):
        return []
    places = places_build.load(R)
    economies = weo_build._apply_official(list(D["economies"]), places)
    fx = world_build._load(os.path.join(R, "data", "world_fx.json"))
    upgrades, _rejected = world_sources.qpsd_choice(R, places, fx, economies)
    t0 = weo_build._t0(D)
    out = []
    for e in economies:
        if e.get("clock") != "weo":
            continue
        name, slug = e["name"], e["slug"]
        u = upgrades.get(e["iso3"])
        if u:
            sector = "general government" if u["sector"] == "general" else "central government"
            rate = float(f"{(u['trend_local'] * u['rate']):.12g}")
            out.append(_entry(file=f"countries/{slug}/index.html", group="Countries", name=name, headline=f"{sector} debt",
                               label=f"{name} {sector} debt", source=u["source"], sym="$",
                               base=u["usd"], rate=rate or 0, t0=float(f"{u['t0']:.0f}"),
                               page_url=f"{site}/countries/{slug}/", embed_path=f"embed/countries/{slug}/",
                               preview=f"countries/{slug}/", iframe_title=f"{name} debt clock",
                               anchor=f"{name} debt clock by EveryDebtClock.com", slug=slug))
        else:
            out.append(_entry(file=f"countries/{slug}/index.html", group="Countries", name=name,
                               headline="general government debt", label=f"{name} general government debt",
                               source="IMF World Economic Outlook, October 2026", sym="$",
                               base=e["debt_2025_usd"], rate=float(f"{(e['rate_usd_per_sec'] or 0):.12g}"), t0=float(f"{t0:.0f}"),
                               page_url=f"{site}/countries/{slug}/", embed_path=f"embed/countries/{slug}/",
                               preview=f"countries/{slug}/", iframe_title=f"{name} debt clock",
                               anchor=f"{name} debt clock by EveryDebtClock.com", slug=slug))
    return out

def _clocks(R, site, now, world):
    places = places_build.load(R)
    out = [_us_clock(R, site)]
    world_clock = _world_clock(R, site, now, world)
    if world_clock:
        out.append(world_clock)
    out += [_place_clock(p, site) for p in sorted(places, key=lambda p: (p["kind"] != "state", p["name"].lower()))]
    out += sorted(_weo_clocks(R, site), key=lambda c: c["name"].lower())
    slugs = [c["embed_path"] for c in out]
    if len(slugs) != len(set(slugs)):
        raise RuntimeError("embed: two clocks share a URL")
    return out

def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write(text)

def _prune(parent, keep):
    if not os.path.isdir(parent):
        return
    for name in os.listdir(parent):
        if name in keep:
            continue
        path = os.path.join(parent, name)
        shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)

def _card(site, c, button):
    code = snippet(site, c["embed_path"], c["page_url"], c["iframe_title"], c["anchor"])
    sub = f'{c["headline"]} · {c["source"]}'
    return (f'<article class="embcard"><h3>{E(c["name"])}</h3><p class="sub">{E(sub)}</p>'
            f'<iframe src="{E(c["preview"], quote=True)}" width="100%" height="160" style="border:0" loading="lazy" title="{E(c["iframe_title"], quote=True)}"></iframe>'
            f'<textarea readonly rows="5" spellcheck="false" aria-label="Embed code for {E(c["name"], quote=True)}">{E(code)}</textarea>'
            f'<button type="button" class="embedcopy" data-label="{button}">{button}</button></article>')

def _directory(R, site, clocks, analytics_fn):
    sm = os.path.join(R, "sitemap.xml")
    listed = open(sm).read() if os.path.exists(sm) else ""
    if os.path.exists(os.path.join(R, "world", "index.html")) or "/world/" in listed:
        places_build.WORLD = True
    if os.path.exists(os.path.join(R, "wealth", "index.html")) or "/wealth/" in listed:
        places_build.WEALTH = True
    places = places_build.load(R)
    ver = hashlib.sha1(open(os.path.join(R, "style.css"), "rb").read()).hexdigest()[:10]
    order = ("United States", "World", "States", "Countries")
    by_slug = {c["slug"]: c for c in clocks}
    featured = "".join(_card(site, by_slug[s], "Copy code") for s in EXAMPLES if s in by_slug)
    groups = []
    for name in order:
        items = [c for c in clocks if c["group"] == name]
        if not items:
            continue
        cards = "".join(_card(site, c, "Copy code") for c in items)
        groups.append(f'<section class="embsec" id="{E(name.lower().replace(" ", "-"))}"><h2>{E(name)}</h2><div class="embgrid">{cards}</div></section>')
    jumps = "".join(f'<a href="#{E(name.lower().replace(" ", "-"))}">{E(name)}</a>' for name in order if any(c["group"] == name for c in clocks))
    desc = "Free debt clock widget for any website. Embed a national debt clock, a state clock, or the world clock. Copy the code. No account."
    title = "Free Debt Clock Widget for Your Website | Every Debt Clock"
    nav = places_build.nav_html(places, 1, "embed", "plnav")
    body = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}"><link rel="canonical" href="{site}/embed/">
<meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc)}">
<meta property="og:url" content="{site}/embed/"><meta property="og:type" content="website">
<meta name="theme-color" content="#07090d"><link rel="apple-touch-icon" href="../apple-touch-icon.png">
<link rel="stylesheet" href="../style.css?v={ver}">{ICON}</head><body>
<header class="top"><div class="topin"><a class="brand" href="../">EVERY <b>DEBT</b> CLOCK</a>{nav}<span class="live"><span class="dot"></span><span>embed</span></span></div></header>
<section class="intro pitch"><h1>Free debt clock widget</h1>
<p>{E(PITCH)}</p>
<p>Add <code>?theme=light</code> to the iframe address for a light background. The snippet is the iframe plus a plain link under it.</p>
<h2>Add this clock to your site</h2>
<p>United States, Texas, and the world, live. Every other clock is listed below.</p>
<div class="embgrid">{featured}</div>
<p class="embjump">{jumps}</p></section>
<div class="embwrap">{''.join(groups)}</div>
<footer class="site-foot">Every Debt Clock · <a href="../embed/">Embed a clock</a> · <a href="../methodology/">Methodology</a> · <a href="../privacy/">Privacy</a> · Independent site, not affiliated with the U.S. government. Not financial advice.</footer>
<script>document.addEventListener("click",function(e){{var b=e.target.closest(".embedcopy");if(!b)return;var t=b.parentNode.querySelector("textarea");if(!t)return;
var label=b.getAttribute("data-label")||"Copy code",done=function(){{b.textContent="Copied";setTimeout(function(){{b.textContent=label}},1500)}};
if(navigator.clipboard&&navigator.clipboard.writeText)navigator.clipboard.writeText(t.value).then(done,function(){{t.select();document.execCommand("copy");done()}});
else{{t.select();document.execCommand("copy");done()}}}});</script>
</body></html>"""
    return analytics_fn(body) if analytics_fn else body

def _patch_sitemap(R, site):
    path = os.path.join(R, "sitemap.xml")
    if not os.path.exists(path):
        return
    text = open(path).read()
    if f"{site}/embed/</loc>" in text:
        return
    lm = (re.search(r"<lastmod>([^<]+)</lastmod>", text) or [None, time.strftime("%Y-%m-%d")])[1]
    row = f"<url><loc>{site}/embed/</loc><lastmod>{lm}</lastmod><changefreq>weekly</changefreq><priority>0.5</priority></url>\n"
    if "</url>\n" not in text:
        raise RuntimeError("sitemap.xml has no url to insert /embed/ after")
    open(path, "w").write(text.replace("</url>\n", "</url>\n" + row, 1))

def _walk_html(R):
    for dirpath, dirnames, filenames in os.walk(R):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not (os.path.basename(dirpath) == "embed" and d in ("us", "world", "states", "countries"))]
        # Clock pages are self-contained. Do not walk into them (no site footer, no analytics).
        if os.path.basename(dirpath) == "embed":
            dirnames[:] = []
        for fn in filenames:
            if fn.endswith(".html"):
                yield os.path.join(dirpath, fn)

def _subdirs(parent):
    if not os.path.isdir(parent):
        return set()
    return {n for n in os.listdir(parent) if os.path.isdir(os.path.join(parent, n))}

def _offer_pos(host, label, preview):
    if host.count('class="embedbox"') != 1:
        raise RuntimeError(f"{label} should have one embed offer")
    if "Embed this clock" in host:
        raise RuntimeError(f"{label} still has the old embed button")
    if ">Copy code</button>" not in host:
        raise RuntimeError(f"{label} is missing Copy code")
    if f'src="{preview}"' not in host:
        raise RuntimeError(f"{label} preview is not its embed URL")
    hero, intro = host.find('class="hero lead"'), host.find('id="intro"')
    box = host.find('class="embedbox"')
    close = host.find("</section>", intro) if intro >= 0 else -1
    if not (hero >= 0 and intro > hero and intro < box < close):
        raise RuntimeError(f"{label} embed offer is not directly after the summary, under the ticker")
    if "<p" not in host[intro:box] or "embedbox" in host[hero:intro]:
        raise RuntimeError(f"{label} moved the ticker or the summary")
    if not _has_header_embed(host):
        raise RuntimeError(f"{label} header is missing the Embed link")
    dm = re.search(r'<meta name="description" content="([^"]*)"', host)
    if not dm:
        raise RuntimeError(f"{label} is missing a meta description")
    desc = html.unescape(dm.group(1))
    if fit_widget(desc) != desc:
        raise RuntimeError(f"{label} meta description did not get the widget phrase")
    if "Free widget for your site." in desc and len(desc) > DESC_LIMIT:
        raise RuntimeError(f"{label} widget phrase made the description {len(desc)} characters")
    tm = re.search(r"<title>([^<]*)</title>", host)
    if not tm or "Free widget" in tm.group(1):
        raise RuntimeError(f"{label} title was changed")
    return "Free widget for your site." in desc

def _check(R, site, clocks, now, require_pages, milestones):
    assert project(100, 1, 0, 10, None, None) == 110
    assert project(100, 1, 0, 50, 20, None) == 120
    assert abs(project(0, 0, 0, 5, None, [[0, 10, 5]]) - 2.5) < 1e-9
    assert len(fit_widget("Short debt clock.")) <= DESC_LIMIT
    assert "Free widget" not in fit_widget("x" * 140)
    sizes, phrased = [], 0
    for c in clocks:
        path = os.path.join(R, c["embed_path"], "index.html")
        text = open(path).read()
        n = len(text.encode())
        sizes.append((n, c["embed_path"]))
        if n > LIMIT:
            raise RuntimeError(f"{c['embed_path']} is {n} bytes (limit {LIMIT})")
        for bad in ("goatcounter", "gc.zgo.at", "fetch(", "XMLHttpRequest", "localStorage", "document.cookie",
                    "nofollow", "stylesheet", "core.js", "app.js", "data.json", "X-Frame-Options", "frame-ancestors",
                    "googletagmanager", "google-analytics"):
            if bad in text:
                raise RuntimeError(f"{c['embed_path']} must not contain {bad}")
        if 'content="noindex"' not in text or BYLINE not in text or f'Source: {E(c["source"])}' not in text:
            raise RuntimeError(f"{c['embed_path']} missing noindex, byline, or source")
        if f'href="{c["page_url"]}" target="_top">{BYLINE}</a>' not in text:
            raise RuntimeError(f"{c['embed_path']} backlink is not a plain dofollow link to the full page")
        if f'href="{site}/embed/" target="_blank"' not in text or GET not in text:
            raise RuntimeError(f"{c['embed_path']} is missing the directory link")
        if 'get("theme")==="light"' not in text:
            raise RuntimeError(f"{c['embed_path']} missing the light theme")
        rate = 0 if c["freeze"] is not None and now > c["freeze"] else (c["rate"] or 0)
        if _rate(c["sym"], rate) not in text or E(c["label"]) not in text:
            raise RuntimeError(f"{c['embed_path']} missing label or per-second rate")
        host_path = os.path.join(R, c["file"])
        if not os.path.exists(host_path):
            if require_pages:
                raise RuntimeError(f"embed: no page for {c['file']}")
            continue
        host = open(host_path).read()
        preview = f"{site}/{c['embed_path']}"
        if _offer_pos(host, c["file"], preview):
            phrased += 1
        code = html.unescape(re.search(r'class="embedbox"[\s\S]*?<textarea[^>]*>([\s\S]*?)</textarea>', host).group(1))
        expect = snippet(site, c["embed_path"], c["page_url"], c["iframe_title"], c["anchor"])
        if code != expect:
            raise RuntimeError(f"{c['file']} snippet does not match the embed URL")
        fm = re.search(r'<footer class="site-foot">[\s\S]*?</footer>', host)
        if not fm or not re.search(r'href="(?:\.\./)*embed/"', fm.group(0)):
            raise RuntimeError(f"{c['file']} footer is missing the embed link")
    us = next(c for c in clocks if c["embed_path"] == "embed/us/")
    us_preview = f"{site}/embed/us/"
    us_code = snippet(site, us["embed_path"], us["page_url"], us["iframe_title"], us["anchor"])
    for path in milestones:
        host = open(path).read()
        rel = os.path.relpath(path, R)
        if _offer_pos(host, rel, us_preview):
            phrased += 1
        code = html.unescape(re.search(r'class="embedbox"[\s\S]*?<textarea[^>]*>([\s\S]*?)</textarea>', host).group(1))
        if code != us_code:
            raise RuntimeError(f"{rel} should offer the US clock")
        if 'class="hero lead"' not in host.split('id="intro"', 1)[0]:
            raise RuntimeError(f"{rel} ticker is not above the summary")
    directory = open(os.path.join(R, "embed", "index.html")).read()
    if 'content="noindex"' in directory or 'class="embedbox"' in directory:
        raise RuntimeError("/embed/ index must stay indexable and is not itself a clock panel")
    if "Add this clock to your site" not in directory or "coming soon" in directory.lower():
        raise RuntimeError("/embed/ index is missing the pitch")
    for bit in ("blog post", "local news", "civic group", "free debt clock widget", "national debt clock"):
        if bit not in directory.lower():
            raise RuntimeError(f"/embed/ pitch is missing {bit}")
    if "Free Debt Clock Widget" not in directory or "widget" not in re.search(r'<meta name="description" content="([^"]*)"', directory).group(1).lower():
        raise RuntimeError("/embed/ title or description does not mention the free widget")
    n_ex = sum(1 for s in EXAMPLES if any(c["slug"] == s for c in clocks))
    if directory.count("<iframe ") != len(clocks) + n_ex:
        raise RuntimeError("/embed/ index is missing a preview")
    if require_pages and n_ex != 3:
        raise RuntimeError("embed landing page needs live US, Texas, and World examples")
    for slug in EXAMPLES:
        c = next((x for x in clocks if x["slug"] == slug), None)
        if c and directory.count(f'src="{c["preview"]}"') < 2:
            raise RuntimeError(f"/embed/ is missing the {slug} example")
    if not _has_header_embed(directory):
        raise RuntimeError("/embed/ header is missing the Embed link")
    sm = open(os.path.join(R, "sitemap.xml")).read()
    ET.fromstring(sm)
    if sm.count("/embed/") != 1 or any(f"{site}/embed/{p}" in sm for p in ("us/", "world/", "states/", "countries/")):
        raise RuntimeError("sitemap must list /embed/ and no per-clock embed URL")
    robots = open(os.path.join(R, "robots.txt")).read()
    if "Disallow: /embed" in robots:
        raise RuntimeError("robots.txt must allow /embed/ so the directory can be indexed and clocks can be framed")
    for quiet in ("states/index.html", "countries/index.html", "methodology/index.html", "how-much-is-the-national-debt/index.html", "t/debt_total.html"):
        path = os.path.join(R, quiet)
        if not os.path.exists(path):
            continue
        text = open(path).read()
        if "Free widget for your site." in text or 'class="embedbox"' in text:
            raise RuntimeError(f"{quiet} is not a single clock page")
        if not _has_header_embed(text):
            raise RuntimeError(f"{quiet} header is missing the Embed link")
    for hub, href in (("states/index.html", "../embed/"), ("countries/index.html", "../embed/"), ("index.html", "embed/"),
                      ("world/index.html", "../embed/"), ("wealth/index.html", "../embed/")):
        path = os.path.join(R, hub)
        if not os.path.exists(path):
            if require_pages and hub in ("states/index.html", "countries/index.html", "index.html", "world/index.html"):
                raise RuntimeError(f"{hub} is missing")
            continue
        text = open(path).read()
        if f'href="{href}"' not in text:
            raise RuntimeError(f"{hub} footer is missing the embed link")
    for hub in ("states/index.html", "countries/index.html", "wealth/index.html"):
        path = os.path.join(R, hub)
        if os.path.exists(path) and 'class="embedbox"' in open(path).read():
            raise RuntimeError(f"{hub} is a list, not a single clock")
    if require_pages:
        state_dirs = _subdirs(os.path.join(R, "states")) - {"debt-per-person"}
        country_dirs = _subdirs(os.path.join(R, "countries"))
        got_states = {c["slug"] for c in clocks if c["group"] == "States"}
        got_countries = {c["slug"] for c in clocks if c["group"] == "Countries"}
        if state_dirs != got_states:
            raise RuntimeError(f"state embeds {sorted(got_states - state_dirs)[:5]} vs pages {sorted(state_dirs - got_states)[:5]}")
        if country_dirs != got_countries:
            raise RuntimeError(f"country embeds missing pages {sorted(got_countries - country_dirs)[:8]} or pages missing embeds {sorted(country_dirs - got_countries)[:8]}")
        if not any(c["group"] == "World" for c in clocks) or not os.path.exists(os.path.join(R, "world", "index.html")):
            raise RuntimeError("world clock embed is missing")
        if "district-of-columbia" not in got_states:
            raise RuntimeError("Washington, DC has no embed")
    sizes.sort()
    print(f"embeds: {len(clocks)} clocks, largest {sizes[-1][0]} bytes ({sizes[-1][1]}), index {site}/embed/, widget phrase on {phrased} descriptions")

def apply(R, site, analytics_fn=None, require_pages=False, now=None, world=None):
    site = site.rstrip("/")
    daily = os.path.join(R, "api", "daily.json")
    ticker = os.path.join(R, "t", "debt_total.html")
    daily_before = open(daily, "rb").read() if os.path.exists(daily) else None
    ticker_before = open(ticker, "rb").read() if os.path.exists(ticker) else None
    if now is None:
        now = time.time()
    clocks = _clocks(R, site, now, world)
    state_slugs, country_slugs = set(), set()
    embed_home = site + "/embed/"
    for c in clocks:
        _write(os.path.join(R, c["embed_path"], "index.html"), _clock_html(c, now, embed_home))
        if c["embed_path"].startswith("embed/states/"):
            state_slugs.add(c["slug"])
        elif c["embed_path"].startswith("embed/countries/"):
            country_slugs.add(c["slug"])
    _prune(os.path.join(R, "embed", "states"), state_slugs)
    _prune(os.path.join(R, "embed", "countries"), country_slugs)
    if not any(c["group"] == "World" for c in clocks):
        world_dir = os.path.join(R, "embed", "world")
        if os.path.isdir(world_dir):
            shutil.rmtree(world_dir)
    if analytics_fn is None:
        analytics_fn = _analytics(R)
    _write(os.path.join(R, "embed", "index.html"), _directory(R, site, clocks, analytics_fn))
    def finish(text, panel):
        return ensure_offer_css(patch_desc(add_header_embed(add_footer(set_panel(text, panel)))))
    hosts, missing = {}, []
    for c in clocks:
        path = os.path.join(R, c["file"])
        if not os.path.exists(path):
            missing.append(c["file"])
            continue
        code = snippet(site, c["embed_path"], c["page_url"], c["iframe_title"], c["anchor"])
        hosts[path] = finish(open(path).read(), panel_html(code, f"{site}/{c['embed_path']}", c["iframe_title"]))
    us = next(c for c in clocks if c["embed_path"] == "embed/us/")
    us_code = snippet(site, us["embed_path"], us["page_url"], us["iframe_title"], us["anchor"])
    us_panel = panel_html(us_code, f"{site}/embed/us/", us["iframe_title"])
    milestones = []
    for name in sorted(os.listdir(R)):
        if not re.fullmatch(r"\d+-trillion", name):
            continue
        path = os.path.join(R, name, "index.html")
        if not os.path.exists(path):
            continue
        raw = open(path).read()
        if 'class="hero lead"' not in raw or 'id="intro"' not in raw:
            continue
        hosts[path] = finish(raw, us_panel)
        milestones.append(path)
    if missing and require_pages:
        raise RuntimeError("embed: full pages missing after the page build: " + ", ".join(missing[:8]))
    elif missing:
        print(f"embed: {len(missing)} full pages are not in this tree; widgets were still written")
    for path, text in hosts.items():
        open(path, "w").write(text)
    for path in _walk_html(R):
        if path in hosts or os.path.join(R, "embed", "index.html") == path:
            continue
        text = open(path).read()
        new = add_header_embed(add_footer(text))
        if new != text:
            open(path, "w").write(new)
    _patch_sitemap(R, site)
    if daily_before is not None and open(daily, "rb").read() != daily_before:
        raise RuntimeError("embed build changed api/daily.json")
    if ticker_before is not None and open(ticker, "rb").read() != ticker_before:
        raise RuntimeError("embed build changed a ticker page")
    _check(R, site, clocks, now, require_pages, milestones)
    return f"{site}/embed/"

if __name__ == "__main__":
    root = os.path.dirname(os.path.abspath(__file__))
    apply(root, os.environ.get("DEBTCLOCK_SITE_URL", "https://everydebtclock.com"))
