#!/usr/bin/env python3
"""Build step (no bundler):
 1) index.html <head> meta refreshed with today's official numbers (title/description/OG/Twitter/canonical)
 2) og/<slug>.png + og/home.png share cards (1200x630, Pillow)
 3) t/<slug>.html real, indexable, live-ticking share pages (one per ticker)
 4) sitemap.xml + robots.txt
 5) dist/debtclock-standalone.html (everything inlined, works offline)
Site URL defaults to https://everydebtclock.com; override with DEBTCLOCK_SITE_URL for previews."""
import json, os, html, time, datetime as dt, re
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont

R = os.path.dirname(os.path.abspath(__file__))
SITE = os.environ.get("DEBTCLOCK_SITE_URL", "https://everydebtclock.com").rstrip("/")
# Analytics hook: empty by default. Set ANALYTICS_HTML (raw HTML snippet) or put it in analytics.html next to build.py.
# The env var wins if both exist. It is injected before </head> on index.html, every t/ page, 404.html and the standalone.
ANALYTICS_HTML = os.environ.get("ANALYTICS_HTML")
if ANALYTICS_HTML is None and os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "analytics.html")):
    ANALYTICS_HTML = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "analytics.html")).read()
ANALYTICS_HTML = (ANALYTICS_HTML or "").strip()
def with_analytics(page):
    """Replace the <!--ANALYTICS-->...<!--/ANALYTICS--> block (or insert one before </head>)."""
    block = f"<!--ANALYTICS-->{ANALYTICS_HTML}<!--/ANALYTICS-->"
    if "<!--ANALYTICS-->" in page:
        return re.sub(r"<!--ANALYTICS-->.*?<!--/ANALYTICS-->", lambda m: block, page, flags=re.S)
    return page.replace("</head>", block + "\n</head>", 1)
D = json.load(open(f"{R}/data/data.json"))
T, M, DV = D["tickers"], D["meta"], D["derived"]
NOW = time.time()
ET = ZoneInfo("America/New_York")

def val(s, t=NOW):
    x = T.get(s)
    if not x or x.get("status") != "ok": return None
    if x.get("mode") == "fytd" and t >= M["fy_end_epoch"]: return x["rate"] * (t - M["fy_end_epoch"])
    return x["base"] + x["rate"] * (t - x["t0"])
def ia(t=NOW):
    a, r = val("debt_total", t), T.get("rate_all")
    return a * r["base"] / 100 if a and r else None
DER = {
    "debt_gdp_now": lambda: val("debt_total") / val("gdp") * 100,
    "deficit_gdp_now": lambda: (T["spending"]["ttm"] - T["revenue"]["ttm"]) / val("gdp") * 100,
    "interest_share": lambda: val("out_interest") / val("revenue") * 100,
    "debt_per_household": lambda: val("debt_total") / T["households"]["base"],
    "interest_annual": ia, "interest_per_day": lambda: ia() / 365.25, "interest_per_sec": lambda: ia() / 31557600,
    "interest_since_open": lambda: ia() / 31557600 * 60,   # card shows "per minute"
    "limit_headroom": lambda: T["debt_limit"]["base"] - val("debt_subject_limit"),
    "fed_share_public": lambda: val("fed_treasuries") / val("debt_public") * 100,
    "m2_debt_ratio": lambda: val("debt_total") / val("m2") * 100,
}
def get(s):
    try: return DER[s]() if s in DER else val(s)
    except Exception: return None
ALL = {k: v for k, v in T.items() if v.get("status") == "ok"}
ALL.update({k: dict(v, derived=True, status="ok") for k, v in DV.items() if k in DER})
POP = val("population"); TAX = T["taxpayers"]["base"]

def fmt(i, x, short=False):
    if x is None: return "—"
    if i.get("kind") == "pct": return f"{x:.2f}%"
    if i.get("kind") == "count": return f"{x:,.0f}"
    a = abs(x); s = "−$" if x < 0 else "$"
    if short:
        for d, u in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
            if a >= d: return f"{s}{a/d:.2f}{u}"
    return f"{s}{a:,.2f}" if a < 1000 else f"{s}{a:,.0f}"
def ppf(v):
    a = abs(v); s = "−$" if v < 0 else "$"
    return f"{s}{a:.6f}" if a < 0.01 else f"{s}{a:.4f}" if a < 100 else f"{s}{a:,.2f}"
def fdate(s):
    if not s: return ""
    if re.match(r"^\d{4}-\d\d-\d\d$", s): return dt.date.fromisoformat(s).strftime("%b %-d, %Y")
    if re.match(r"^\d{4}-\d\d$", s): return dt.date.fromisoformat(s + "-01").strftime("%b %Y")
    return s
def mode_txt(i):
    if i.get("historical"): return "HISTORICAL · fixed"
    if i.get("derived"): return "LIVE CALC · from official tickers"
    if i.get("fixed"): return f"FIXED · official {fdate(i.get('as_of'))}"
    return f"PROJECTED · from official {fdate(i.get('as_of'))}"
GROUP_COL = {"debt": "#ff4d5e", "fytd": "#ffb547", "interest": "#ff8f5a", "spending": "#5aa9ff", "revenue": "#38d39f", "trust": "#a98bff",
             "money": "#2fd0d0", "economy": "#2fd0d0", "people": "#2fd0d0", "history": "#a98bff", "ratios": "#2fd0d0"}
def label(slug, i):
    l = i.get("label", slug)
    if i.get("mode") == "fytd": l += f" (FY{M['fy']} to date)"
    if slug == "interest_since_open": l = "Interest on the debt, per minute"
    return l

# ---------------------------------------------------------------- OG images
FD = "/usr/share/fonts/truetype/dejavu/"
F = lambda n, s: ImageFont.truetype(FD + n, s)
os.makedirs(f"{R}/og", exist_ok=True)
gen_ct = dt.datetime.fromtimestamp(M["generated_epoch"], ZoneInfo("America/Chicago"))   # when data.json was fetched
# Every static number (share images, page text, meta descriptions) is computed at NOW, so it is labelled with NOW too.
build_ct = dt.datetime.fromtimestamp(NOW, ZoneInfo("America/Chicago"))
STAMP = build_ct.strftime("%b %-d, %Y %-I:%M %p") + " CT"
def fit(draw, text, font_name, max_w, start):
    s = start
    while s > 20:
        f = F(font_name, s)
        if draw.textlength(text, font=f) <= max_w: return f
        s -= 4
    return F(font_name, s)
def short_src(n, k=44):
    n = n.split(" (")[0]
    return n if len(n) <= k else n[:k].rsplit(" ", 1)[0].rstrip(",:;") + "…"
def og(path, title, big, lines, badge, col, note="Official US data · recalibrated & checked daily"):
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), "#07090d"); d = ImageDraw.Draw(im)
    for y in range(H):  # subtle top glow
        c = int(20 * max(0, 1 - y / 380)); d.line([(0, y), (W, y)], fill=(7 + c // 2, 9 + c // 1.5 // 1 if False else 9 + int(c * .8), 13 + c * 2))
    d.rectangle([0, 0, W, 10], fill=col)
    d.text((60, 44), "EVERY ", font=F("DejaVuSans-Bold.ttf", 30), fill="#e8edf5")
    x = 60 + d.textlength("EVERY ", font=F("DejaVuSans-Bold.ttf", 30))
    d.text((x, 44), "DEBT", font=F("DejaVuSans-Bold.ttf", 30), fill="#ff4d5e"); x += d.textlength("DEBT ", font=F("DejaVuSans-Bold.ttf", 30))
    d.text((x, 44), "CLOCK", font=F("DejaVuSans-Bold.ttf", 30), fill="#e8edf5")
    d.ellipse([W - 160, 54, W - 146, 68], fill="#38d39f"); d.text((W - 136, 46), "LIVE", font=F("DejaVuSans-Bold.ttf", 24), fill="#38d39f")
    d.text((60, 130), title, font=fit(d, title, "DejaVuSans-Bold.ttf", W - 120, 44), fill="#c9d3e2")
    d.text((56, 190), big, font=fit(d, big, "DejaVuSansMono-Bold.ttf", W - 120, 118), fill="#ffffff")
    y = 350
    for k, v in lines:
        d.rounded_rectangle([60, y, 60 + 520, y + 70], 12, fill="#121925")
        d.text((80, y + 8), k.upper(), font=F("DejaVuSans-Bold.ttf", 17), fill="#5c687a")
        d.text((80, y + 30), v, font=fit(d, v, "DejaVuSansMono-Bold.ttf", 480, 32), fill="#dfe6f1")
        y += 82
    bw = d.textlength(badge, font=F("DejaVuSans-Bold.ttf", 20)) + 28
    d.rounded_rectangle([W - 60 - bw, 350, W - 60, 392], 8, outline="#1e3a5c", width=2)
    d.text((W - 60 - bw + 14, 359), badge, font=F("DejaVuSans-Bold.ttf", 20), fill="#9fd0ff")
    for k, ln in enumerate(note.split("\n")):
        d.text((W - 60 - d.textlength(ln, font=F("DejaVuSans.ttf", 21)), 412 + 32 * k), ln, font=F("DejaVuSans.ttf", 21), fill="#8a97ab")
    d.text((60, H - 56), SITE.replace("https://", ""), font=F("DejaVuSans-Bold.ttf", 24), fill="#5aa9ff")
    stamp = f"Projected to {STAMP}"
    d.text((W - 60 - d.textlength(stamp, font=F("DejaVuSans.ttf", 20)), H - 52), stamp, font=F("DejaVuSans.ttf", 20), fill="#5c687a")
    im.save(path, optimize=True)

home_debt = val("debt_total")
og(f"{R}/og/home.png", "US national debt · ticking live", fmt({"kind": "usd"}, home_debt),
   [("Per person", ppf(home_debt / POP)), ("Per tax return", ppf(home_debt / TAX))],
   f"+{fmt({'kind':'usd'}, T['debt_total']['rate'] * 86400, True)}/day", "#ff4d5e",
   f"Treasury Debt to the Penny, {fdate(T['debt_total']['as_of'])} close\nprojected at the 90-day trend · checked daily")
for slug, i in ALL.items():
    x = get(slug)
    if x is None: continue
    lines = [("Per person", ppf(x / POP)), ("Per tax return", ppf(x / TAX))] if i.get("kind") == "usd" and slug != "debt_per_household" else \
            [("As of", fdate(i.get("as_of")) or "live"), ("Source", (i.get("source_name") or "Computed from official tickers")[:34])]
    mt = mode_txt(i).split(" · ")
    og(f"{R}/og/{slug}.png", label(slug, i), fmt(i, x), lines, mt[0], GROUP_COL.get(i.get("group"), "#5aa9ff"),
       (mt[1] if len(mt) > 1 else "") + "\n" + short_src(i.get("source_name") or "Official US data"))

# ---------------------------------------------------------------- index.html meta
idx = open(f"{R}/index.html").read()
desc = (f"US national debt: {fmt({'kind':'usd'}, T['debt_total']['base'], True)} at Treasury's {fdate(T['debt_total']['as_of'])} close, "
        f"rising {fmt({'kind':'usd'}, T['debt_total']['rate']*86400, True)} a day. Live deficit, spending, interest, debt limit, trust funds and "
        f"{len(ALL)} more official counters, each per person and per tax return filed, checked daily against Treasury.")
meta = f"""<!--META--><title>Every Debt Clock: live US national debt, deficit and interest, verified daily</title>
<meta name="description" content="{html.escape(desc)}">
<link rel="canonical" href="{SITE}/">
<meta property="og:type" content="website"><meta property="og:site_name" content="Every Debt Clock"><meta property="og:url" content="{SITE}/">
<meta property="og:title" content="Every Debt Clock: US national debt, live and verified daily"><meta property="og:description" content="{html.escape(desc)}">
<meta property="og:image" content="{SITE}/og/home.png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta property="og:image:alt" content="US national debt counter with per-person and per-tax-return figures">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="Every Debt Clock: US national debt, live and verified daily">
<meta name="twitter:description" content="{html.escape(desc)}"><meta name="twitter:image" content="{SITE}/og/home.png">
<!--/META-->"""
idx = re.sub(r"<!--META-->.*?<!--/META-->", lambda m: meta, idx, flags=re.S)
idx = re.sub(r'<meta property="og:title" content="US Debt Clock — live &amp; verified"><meta property="og:type" content="website">\n?', "", idx)
idx = idx.replace('<meta property="og:title" content="US Debt Clock — live & verified"><meta property="og:type" content="website">\n', "")
idx = with_analytics(idx)
open(f"{R}/index.html", "w").write(idx)
if os.path.exists(f"{R}/404.html"):
    p404 = with_analytics(open(f"{R}/404.html").read())
    open(f"{R}/404.html", "w").write(p404)

# ---------------------------------------------------------------- share pages
os.makedirs(f"{R}/t", exist_ok=True)
for f in os.listdir(f"{R}/t"): os.remove(f"{R}/t/{f}")
RELATED = {}
for slug, i in ALL.items(): RELATED.setdefault(i.get("group"), []).append(slug)
need = {"population", "taxpayers", "households", "debt_total", "gdp", "spending", "revenue", "out_interest", "rate_all", "debt_limit",
        "debt_subject_limit", "fed_treasuries", "debt_public", "m2"}
PAGE_CSS = """body{margin:0;background:#07090d;color:#e8edf5;font-family:-apple-system,BlinkMacSystemFont,Inter,Segoe UI,Roboto,sans-serif;line-height:1.5}
main{max-width:760px;margin:0 auto;padding:22px 16px 60px}a{color:#5aa9ff;text-decoration:none}
.brand{font-weight:800;letter-spacing:.06em;font-size:14px}.brand b{color:#ff4d5e}h1{font-size:22px;margin:18px 0 4px}
.v{font:600 clamp(28px,8vw,46px) ui-monospace,Menlo,monospace;font-variant-numeric:tabular-nums;margin:6px 0;white-space:nowrap}
.pp{display:grid;grid-template-columns:1fr 1fr;gap:8px}.pp div{background:#121925;border-radius:10px;padding:8px 10px}
.pp .l{display:block;font-size:10.5px;color:#5c687a;text-transform:uppercase;letter-spacing:.08em}.pp .n{font:600 17px ui-monospace,Menlo,monospace}
.b{display:inline-block;border:1px solid #1e3a5c;color:#9fd0ff;border-radius:6px;padding:2px 7px;font-size:11.5px;margin:10px 6px 0 0}
p{color:#c2ccda;font-size:14.5px}.cta{display:inline-block;margin:14px 0;background:#ff4d5e;color:#fff;border-radius:10px;padding:10px 16px;font-weight:700}
.rel a{display:inline-block;margin:4px 8px 4px 0;font-size:13px}footer{color:#5c687a;font-size:12px;margin-top:30px}"""
for slug, i in ALL.items():
    x = get(slug)
    if x is None: continue
    lab = label(slug, i); url = f"{SITE}/t/{slug}.html"
    usdpp = i.get("kind") == "usd" and slug != "debt_per_household"
    d1 = (f"{lab}: {fmt(i, x, True)} projected to {build_ct.strftime('%b %-d, %Y')}" + (f" ({ppf(x/POP)} per person, {ppf(x/TAX)} per tax return filed)" if usdpp else "") +
          f". Live counter from official data ({i.get('source_name') or 'computed from official Treasury tickers'}), recalibrated and checked daily.")
    sub = {k: T[k] for k in need if k in T}
    if not i.get("derived"): sub[slug] = T[slug]
    data = json.dumps({"tickers": sub, "meta": {k: M[k] for k in ("fy_end_epoch", "fy")}, "derived": {slug: DV[slug]} if i.get("derived") else {}},
                      separators=(",", ":")).replace("</", "<\\/")
    rel = [s for s in RELATED.get(i.get("group"), []) if s != slug][:10]
    v = i.get("validation") or {}
    check = (f"<p><b>Daily check.</b> Yesterday's projection vs {html.escape(v.get('against',''))}: {v['last_error_pct']:+.3f}% (threshold ±{v.get('threshold_pct')}%)"
             + (f"; average |error| over {v['n']} days {v['mean_abs_error_pct']:.3f}%" if v.get("mean_abs_error_pct") is not None else "") + ".</p>") if v.get("last_error_pct") is not None else ""
    ld = {"@context": "https://schema.org", "@type": "Dataset", "name": lab, "description": d1, "url": url, "isAccessibleForFree": True,
          "creator": {"@type": "Organization", "name": "Every Debt Clock"}, "dateModified": M["generated_iso"],
          "isBasedOn": i.get("source") or "https://fiscaldata.treasury.gov/", "variableMeasured": lab}
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(lab)}: live counter | Every Debt Clock</title>
<meta name="description" content="{html.escape(d1)}"><link rel="canonical" href="{url}">
<meta property="og:type" content="article"><meta property="og:site_name" content="Every Debt Clock"><meta property="og:url" content="{url}">
<meta property="og:title" content="{html.escape(lab)}: {html.escape(fmt(i, x, True))} and ticking"><meta property="og:description" content="{html.escape(d1)}">
<meta property="og:image" content="{SITE}/og/{slug}.png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{html.escape(lab)}: {html.escape(fmt(i, x, True))} and ticking">
<meta name="twitter:description" content="{html.escape(d1)}"><meta name="twitter:image" content="{SITE}/og/{slug}.png">
<meta name="theme-color" content="#07090d"><link rel="apple-touch-icon" href="../apple-touch-icon.png"><style>{PAGE_CSS}</style>
<script type="application/ld+json">{json.dumps(ld)}</script></head><body><main>
<a class="brand" href="../index.html">EVERY <b>DEBT</b> CLOCK</a>
<h1>{html.escape(lab)}</h1>
<div class="v" id="v">{html.escape(fmt(i, x))}</div>
{f'<div class="pp"><div><span class="l">Per person</span><span class="n" id="p1">{ppf(x/POP)}</span></div><div><span class="l">Per tax return filed</span><span class="n" id="p2">{ppf(x/TAX)}</span></div></div>' if usdpp else ''}
<span class="b">{html.escape(mode_txt(i))}</span>{'<span class="b">official source cached (last run failed)</span>' if i.get('stale') else ''}
<p><b>How it's calculated.</b> {html.escape(i.get('method') or '')}</p>
{f'<p><b>Source.</b> <a href="{html.escape(i["source"])}" rel="noopener">{html.escape(i.get("source_name") or i["source"])}</a>, official as of {fdate(i.get("as_of"))}.</p>' if i.get('source') else ''}
{check}
<p><b>Per person</b> divides by the US population: Census Vintage 2025 estimate for July 1, 2025, projected forward at Census's stated growth rate ({POP:,.0f} at build time). <b>Per tax return filed</b> divides by {TAX:,.0f} individual income tax returns filed in FY2025 (IRS Data Book, Table 1-2); a joint return counts once and returns with zero tax liability are included.</p>
<a class="cta" href="../index.html#t={slug}">Open the full live clock →</a>
<div class="rel"><b>Related:</b><br>{''.join(f'<a href="{s}.html">{html.escape(ALL[s].get("label", s))}</a>' for s in rel)}</div>
<footer>The value in this page's text is projected to {STAMP} from the official figure above (data fetched {gen_ct.strftime('%b %-d, %Y %-I:%M %p')} CT). The number above ticks live in your browser.</footer>
</main><script>window.DEBTCLOCK_DATA={data};</script><script src="../core.js"></script>
<script>(function(){{const C=DC(window.DEBTCLOCK_DATA),i=C.info({json.dumps(slug)}),v=document.getElementById('v'),p1=document.getElementById('p1'),p2=document.getElementById('p2');
(function f(){{const t=Date.now()/1000,x=C.get({json.dumps(slug)},t);v.textContent=C.fmt(i,x);if(p1){{p1.textContent=C.ppf(x/C.pop(t));p2.textContent=C.ppf(x/C.tax)}}requestAnimationFrame(f)}})()}})()</script>
</body></html>"""
    open(f"{R}/t/{slug}.html", "w").write(with_analytics(page))

# ---------------------------------------------------------------- sitemap + robots
lm = gen_ct.date().isoformat()
urls = [(f"{SITE}/", "1.0", "hourly")] + [(f"{SITE}/t/{s}.html", "0.7", "daily") for s in ALL if get(s) is not None]
open(f"{R}/sitemap.xml", "w").write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
    "".join(f"<url><loc>{u}</loc><lastmod>{lm}</lastmod><changefreq>{c}</changefreq><priority>{p}</priority></url>\n" for u, p, c in urls) + "</urlset>\n")
open(f"{R}/robots.txt", "w").write(f"User-agent: *\nAllow: /\nDisallow: /cache/\nDisallow: /pipeline/\nDisallow: /widget.html\nSitemap: {SITE}/sitemap.xml\n")

# ---------------------------------------------------------------- standalone
css, js = open(f"{R}/style.css").read(), open(f"{R}/app.js").read()
single = (idx.replace('<link rel="stylesheet" href="style.css">', f"<style>{css}</style>")
             .replace("<!--DATA-->", "<script>window.DEBTCLOCK_DATA=" + json.dumps(D, separators=(",", ":")).replace("</", "<\\/") + ";</script>")
             .replace('<script src="app.js"></script>', f"<script>{js}</script>"))
os.makedirs(f"{R}/dist", exist_ok=True)
open(f"{R}/dist/debtclock-standalone.html", "w").write(single)
print(f"standalone: {len(single)//1024} KB; share pages: {len(urls)-1}; og images: {len(os.listdir(R+'/og'))}; site={SITE}")
