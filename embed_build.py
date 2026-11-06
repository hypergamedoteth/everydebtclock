"""Free embeddable debt clocks.

build.py calls apply() on every run, including a plain push (the deploy rebuilds pages from
repo data and does not commit them). One self-contained page per live clock:

  /embed/us/
  /embed/states/<slug>/
  /embed/countries/<slug>/

Numbers use the same inputs as the full pages: debt_total in data/data.json for the US,
and places_build.calc() for each places/<slug>.json. Clock pages are noindex, carry no
analytics, and do not set X-Frame-Options or a frame-ancestors policy. GitHub Pages does
not send X-Frame-Options, which is what lets a news site iframe these URLs.

The /embed/ directory is a normal indexable page and is the only embed URL in the sitemap.
"""
import hashlib, html, json, os, re, shutil, time
import places_build

E = html.escape
BYLINE = "Live debt clock by EveryDebtClock.com"
LIMIT = 15 * 1024
SKIP_DIRS = {".git", "cache", "pipeline", "og", "dist", "data", "__pycache__", "node_modules", ".venv", "venv"}
PANEL_RE = re.compile(r'<div class="embedbox"><button type="button" class="embedbtn"[\s\S]*?</script></div>\n?')
ICON = ('<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 32 32%22%3E'
        '%3Crect width=%2232%22 height=%2232%22 rx=%226%22 fill=%22%2307090d%22/%3E%3Ctext x=%2216%22 y=%2223%22 '
        'font-size=%2220%22 text-anchor=%22middle%22 fill=%22%23ff4d5e%22 font-family=%22Arial%22 font-weight=%22900%22%3E'
        '$%3C/text%3E%3C/svg%3E">')

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

def panel_html(code):
    # After </main>, never inside #app: the US page's app.js rebuilds #app and keeps the ticker first.
    return ('<div class="embedbox"><button type="button" class="embedbtn" aria-expanded="false">Embed this clock</button>'
            '<div class="embedpanel" hidden><p>Paste this where you want the clock.</p>'
            f'<textarea readonly rows="8" spellcheck="false" aria-label="Embed code">{E(code)}</textarea>'
            '<button type="button" class="embedcopy">Copy</button></div>'
            '<script>(function(){var box=document.currentScript.parentNode,b=box.querySelector(".embedbtn"),p=box.querySelector(".embedpanel"),t=box.querySelector("textarea"),c=box.querySelector(".embedcopy");'
            'b.addEventListener("click",function(){var o=p.hidden;p.hidden=!o;b.setAttribute("aria-expanded",o?"true":"false");if(o)t.focus()});'
            'c.addEventListener("click",function(){var s=t.value,done=function(){c.textContent="Copied";setTimeout(function(){c.textContent="Copy"},1500)};'
            'if(navigator.clipboard&&navigator.clipboard.writeText)navigator.clipboard.writeText(s).then(done,function(){t.select();document.execCommand("copy");done()});'
            'else{t.select();document.execCommand("copy");done()}})})();</script></div>\n')

def set_panel(page, panel):
    if 'class="embedbox"' in page:
        page2, n = PANEL_RE.subn(panel, page, count=1)
        if n != 1:
            raise RuntimeError("embed panel found but could not be replaced")
        return page2
    if "<footer class=\"site-foot\">" not in page:
        raise RuntimeError("no site footer to attach the embed panel")
    return page.replace("<footer class=\"site-foot\">", panel + "<footer class=\"site-foot\">", 1)

def add_footer(page):
    """Link /embed/ from the site footer. Depth is copied from the Methodology or Privacy link already there."""
    m = re.search(r'<footer class="site-foot">(?:(?!</footer>).)*?</footer>', page, re.S)
    if not m or re.search(r'href="(?:\.\./)*embed/"', m.group(0)):
        return page
    foot = m.group(0)
    for pat in (r'<a href="((?:\.\./)*)methodology/">', r'<a href="((?:\.\./)*)privacy\.html">'):
        mm = re.search(pat, foot)
        if not mm:
            continue
        link = f'<a href="{mm.group(1)}embed/">Embed a clock</a> · '
        return page.replace(foot, foot[:mm.start()] + link + foot[mm.start():], 1)
    return page.replace(foot, foot.replace("</footer>", '<a href="embed/">Embed a clock</a></footer>', 1), 1)

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

def _clock_html(c, now):
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
.r{{font:600 12.5px/1.3 ui-monospace,Menlo,Consolas,monospace;color:var(--up)}}.r.dn{{color:var(--dn)}}.r.z{{color:var(--dim);font-weight:500}}
.s{{font-size:11px;color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
a.by{{color:var(--link);font-size:12px;text-decoration:underline;text-underline-offset:2px}}
</style>{ICON}</head><body><div class="w">
<div class="n" title="{E(label, quote=True)}">{E(label)}</div>
<div class="v" id="v">{E(_total(sym, project(c["base"], rate, c["t0"], now, c["freeze"], c["steps"])))}</div>
<div class="{klass}" id="r">{E(_rate(sym, shown_rate))}</div>
<div class="s" title="{E("Source: " + source, quote=True)}">Source: {E(source)}</div>
<a class="by" href="{E(page_url, quote=True)}" target="_top">{BYLINE}</a>
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

def _us_clock(R, site):
    D = json.load(open(os.path.join(R, "data", "data.json")))
    td = (D.get("tickers") or {}).get("debt_total") or {}
    if td.get("status") != "ok":
        raise RuntimeError("embed: US debt_total ticker is not ok")
    return {"file": "index.html", "group": "United States", "name": "United States", "label": "US national debt",
            "source": td.get("source_name") or "Treasury, Debt to the Penny", "sym": "$", "base": td["base"],
            "rate": td.get("rate") or 0, "t0": td["t0"], "freeze": td.get("freeze_t"), "steps": td.get("steps") or [],
            "page_url": site + "/", "embed_path": "embed/us/", "preview": "us/", "iframe_title": "US debt clock",
            "anchor": "US debt clock by EveryDebtClock.com", "slug": "us", "headline": "national debt"}

def _place_clock(p, site):
    c = places_build.calc(p)
    kind = p["kind"]
    sec = "states" if kind == "state" else "countries"
    sym = (p.get("currency") or {}).get("symbol") or "$"
    name, head = p["name"], places_build.texts(p)["head"]
    return {"file": f"{sec}/{p['slug']}/index.html", "group": "States" if kind == "state" else "Countries",
            "name": name, "headline": head, "label": f"{name} {head}", "source": p.get("publisher") or "official data",
            "sym": sym, "base": c["total"], "rate": c["rate"] or 0, "t0": c["t0"], "freeze": None, "steps": [],
            "page_url": f"{site}/{sec}/{p['slug']}/", "embed_path": f"embed/{sec}/{p['slug']}/",
            "preview": f"{sec}/{p['slug']}/", "iframe_title": f"{name} debt clock",
            "anchor": f"{name} debt clock by EveryDebtClock.com", "slug": p["slug"]}

def _clocks(R, site):
    places = [p for p in places_build.load(R)]
    out = [_us_clock(R, site)]
    out += [_place_clock(p, site) for p in sorted(places, key=lambda p: (p["kind"] != "state", p["name"].lower()))]
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

def _directory(R, site, clocks, analytics_fn):
    sm = os.path.join(R, "sitemap.xml")
    listed = open(sm).read() if os.path.exists(sm) else ""
    # The directory is built after place pages on deploy. In a checkout that has not
    # generated world/ or wealth/ yet, the sitemap still names them.
    if os.path.exists(os.path.join(R, "world", "index.html")) or "/world/" in listed:
        places_build.WORLD = True
    if os.path.exists(os.path.join(R, "wealth", "index.html")) or "/wealth/" in listed:
        places_build.WEALTH = True
    places = places_build.load(R)
    ver = hashlib.sha1(open(os.path.join(R, "style.css"), "rb").read()).hexdigest()[:10]
    groups = []
    for name in ("United States", "States", "Countries"):
        items = [c for c in clocks if c["group"] == name]
        if not items:
            continue
        cards = []
        for c in items:
            code = snippet(site, c["embed_path"], c["page_url"], c["iframe_title"], c["anchor"])
            sub = f'{c["headline"]} · {c["source"]}'
            cards.append(
                f'<article class="embcard"><h3>{E(c["name"])}</h3><p class="sub">{E(sub)}</p>'
                f'<iframe src="{E(c["preview"], quote=True)}" width="100%" height="160" style="border:0" loading="lazy" title="{E(c["iframe_title"], quote=True)}"></iframe>'
                f'<textarea readonly rows="8" spellcheck="false" aria-label="Embed code for {E(c["name"], quote=True)}">{E(code)}</textarea>'
                f'<button type="button" class="embedcopy">Copy</button></article>')
        groups.append(f'<section class="embsec"><h2>{E(name)}</h2><div class="embgrid">{"".join(cards)}</div></section>')
    desc = "Free debt clock embeds for any site. Live US, state and country totals, with the source and a link back."
    title = "Embed a Debt Clock | Every Debt Clock"
    nav = places_build.nav_html(places, 1, None, "plnav")
    body = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}"><link rel="canonical" href="{site}/embed/">
<meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc)}">
<meta property="og:url" content="{site}/embed/"><meta property="og:type" content="website">
<meta name="theme-color" content="#07090d"><link rel="apple-touch-icon" href="../apple-touch-icon.png">
<link rel="stylesheet" href="../style.css?v={ver}">{ICON}</head><body>
<header class="top"><div class="topin"><a class="brand" href="../">EVERY <b>DEBT</b> CLOCK</a>{nav}<span class="live"><span class="dot"></span><span>embed</span></span></div></header>
<section class="intro"><h1>Embed a debt clock</h1>
<p>Paste a snippet into your page. The clock ticks on its own, names its source, and links to the full page. No account, and the clock page has no tracking. Add <code>?theme=light</code> to the iframe address for a light background.</p></section>
<div class="embwrap">{''.join(groups)}</div>
<footer class="site-foot">Every Debt Clock · <a href="../embed/">Embed a clock</a> · <a href="../methodology/">Methodology</a> · <a href="../privacy.html">Privacy</a> · Independent site, not affiliated with the U.S. government. Not financial advice.</footer>
<script>document.addEventListener("click",function(e){{var b=e.target.closest(".embedcopy");if(!b)return;var t=b.parentNode.querySelector("textarea");if(!t)return;
var done=function(){{b.textContent="Copied";setTimeout(function(){{b.textContent="Copy"}},1500)}};
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
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".html"):
                yield os.path.join(dirpath, fn)

def _check(R, site, clocks, now, require_pages):
    assert project(100, 1, 0, 10, None, None) == 110
    assert project(100, 1, 0, 50, 20, None) == 120
    assert abs(project(0, 0, 0, 5, None, [[0, 10, 5]]) - 2.5) < 1e-9
    sizes = []
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
        rate = 0 if c["freeze"] is not None and now > c["freeze"] else (c["rate"] or 0)
        if _rate(c["sym"], rate) not in text or E(c["label"]) not in text:
            raise RuntimeError(f"{c['embed_path']} missing label or per-second rate")
        host_path = os.path.join(R, c["file"])
        if not os.path.exists(host_path):
            if require_pages:
                raise RuntimeError(f"embed: no page for {c['file']}")
            continue
        host = open(host_path).read()
        if host.count('class="embedbox"') != 1:
            raise RuntimeError(f"{c['file']} should have one embed panel")
        code = html.unescape(re.search(r'class="embedbox"[\s\S]*?<textarea[^>]*>([\s\S]*?)</textarea>', host).group(1))
        expect = snippet(site, c["embed_path"], c["page_url"], c["iframe_title"], c["anchor"])
        if code != expect:
            raise RuntimeError(f"{c['file']} snippet does not match the embed URL")
        main_end = host.find("</main>")
        box = host.find('class="embedbox"')
        hero, intro = host.find('class="hero lead"'), host.find('id="intro"')
        if main_end < 0 or box < main_end or hero < 0 or intro < hero or "embedbox" in host[hero:intro]:
            raise RuntimeError(f"{c['file']} embed control is not below the ticker and summary")
        fm = re.search(r'<footer class="site-foot">[\s\S]*?</footer>', host)
        if not fm or not re.search(r'href="(?:\.\./)*embed/"', fm.group(0)):
            raise RuntimeError(f"{c['file']} footer is missing the embed link")
    directory = open(os.path.join(R, "embed", "index.html")).read()
    if 'content="noindex"' in directory or 'class="embedbox"' in directory:
        raise RuntimeError("/embed/ index must stay indexable and is not itself a clock panel")
    if directory.count("<iframe ") != len(clocks):
        raise RuntimeError("/embed/ index is missing a preview")
    sm = open(os.path.join(R, "sitemap.xml")).read()
    if sm.count("/embed/") != 1 or f"{site}/embed/us/" in sm or f"{site}/embed/states/" in sm or f"{site}/embed/countries/" in sm:
        raise RuntimeError("sitemap must list /embed/ and no per-clock embed URL")
    robots = open(os.path.join(R, "robots.txt")).read()
    if "Disallow: /embed" in robots:
        raise RuntimeError("robots.txt must allow /embed/ so the directory can be indexed and clocks can be framed")
    for hub, href in (("states/index.html", "../embed/"), ("countries/index.html", "../embed/"), ("index.html", "embed/")):
        text = open(os.path.join(R, hub)).read()
        if f'href="{href}"' not in text:
            raise RuntimeError(f"{hub} footer is missing the embed link")
    for hub in ("states/index.html", "countries/index.html"):
        if 'class="embedbox"' in open(os.path.join(R, hub)).read():
            raise RuntimeError(f"{hub} is a list, not a single clock")
    sizes.sort()
    print(f"embeds: {len(clocks)} clocks, largest {sizes[-1][0]} bytes ({sizes[-1][1]}), index {site}/embed/")

def apply(R, site, analytics_fn=None, require_pages=False):
    site = site.rstrip("/")
    daily = os.path.join(R, "api", "daily.json")
    ticker = os.path.join(R, "t", "debt_total.html")
    daily_before = open(daily, "rb").read() if os.path.exists(daily) else None
    ticker_before = open(ticker, "rb").read() if os.path.exists(ticker) else None
    now = time.time()
    clocks = _clocks(R, site)
    state_slugs, country_slugs = set(), set()
    for c in clocks:
        _write(os.path.join(R, c["embed_path"], "index.html"), _clock_html(c, now))
        if c["embed_path"].startswith("embed/states/"):
            state_slugs.add(c["slug"])
        elif c["embed_path"].startswith("embed/countries/"):
            country_slugs.add(c["slug"])
    _prune(os.path.join(R, "embed", "states"), state_slugs)
    _prune(os.path.join(R, "embed", "countries"), country_slugs)
    if analytics_fn is None:
        analytics_fn = _analytics(R)
    _write(os.path.join(R, "embed", "index.html"), _directory(R, site, clocks, analytics_fn))
    hosts, missing = {}, []
    for c in clocks:
        path = os.path.join(R, c["file"])
        if not os.path.exists(path):
            missing.append(c["file"])
            continue
        hosts[path] = set_panel(add_footer(open(path).read()), panel_html(snippet(site, c["embed_path"], c["page_url"], c["iframe_title"], c["anchor"])))
    if missing and require_pages:
        raise RuntimeError("embed: full pages missing after the page build: " + ", ".join(missing[:8]))
    elif missing:
        print(f"embed: {len(missing)} full pages are not in this tree; widgets were still written")
    for path, text in hosts.items():
        open(path, "w").write(text)
    for path in _walk_html(R):
        if path in hosts:
            continue
        text = open(path).read()
        new = add_footer(text)
        if new != text:
            open(path, "w").write(new)
    _patch_sitemap(R, site)
    if daily_before is not None and open(daily, "rb").read() != daily_before:
        raise RuntimeError("embed build changed api/daily.json")
    if ticker_before is not None and open(ticker, "rb").read() != ticker_before:
        raise RuntimeError("embed build changed a ticker page")
    _check(R, site, clocks, now, require_pages)
    return f"{site}/embed/"

if __name__ == "__main__":
    root = os.path.dirname(os.path.abspath(__file__))
    apply(root, os.environ.get("DEBTCLOCK_SITE_URL", "https://everydebtclock.com"))
