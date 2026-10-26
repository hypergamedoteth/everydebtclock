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
    if x.get("freeze_t") and t > x["freeze_t"]: t = x["freeze_t"]     # never project debt past the statutory limit
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
POP = val("population"); TAX = T["tax_returns"]["base"]
POP_OFF = T["population"]["base"]; POP_OFF_DATE = T["population"]["as_of"]   # official Census Vintage 2025, Jul 1, 2025
HH = T["households"]["base"]
DLS = M.get("debt_limit_status") or {}
HIST = {k for k, v in ALL.items() if v.get("historical")}      # fixed OMB ratios: folded into /national-debt-by-year/, no own pages
def official_close():
    """Latest official Debt to the Penny close (date, value), straight from Treasury rows."""
    td = T.get("debt_total") or {}
    cl = sorted((M.get("debt_closes") or []), key=lambda c: c[0], reverse=True)
    if td.get("status") == "ok" and cl and cl[0][0] == td.get("as_of"): return cl[0][0], float(cl[0][1])
    if td.get("status") == "ok": return td.get("as_of"), td.get("base")
    return None, None
OFF_D, OFF_V = official_close()
CLOSES = sorted(((c[0], float(c[1])) for c in (M.get("debt_closes") or [])), reverse=True)
def usd2(x): return "—" if x is None else ("−$" if x < 0 else "$") + f"{abs(x):,.2f}"
def usd0(x): return "—" if x is None else ("−$" if x < 0 else "$") + f"{abs(x):,.0f}"
def tril(x, d=2): return f"${x/1e12:,.{d}f} trillion"
def bil(x): return f"${x/1e12:,.2f} trillion" if abs(x) >= 1e12 else f"${x/1e9:,.1f} billion"
DTP_URL = "https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/debt-to-the-penny"
def dataset_ld(name, desc, url, based=None, temporal=None, kw=None):
    ld = {"@context": "https://schema.org", "@type": "Dataset", "name": name, "description": desc, "url": url, "isAccessibleForFree": True,
          "creator": {"@type": "Organization", "name": "Every Debt Clock", "url": SITE + "/"}, "dateModified": M["generated_iso"],
          "spatialCoverage": {"@type": "Place", "name": "United States"},
          "isBasedOn": based or [DTP_URL], "keywords": kw or ["US national debt", "national debt clock", "Treasury Debt to the Penny", "federal debt"],
          "distribution": [{"@type": "DataDownload", "name": "Daily official national debt feed", "encodingFormat": "application/json", "contentUrl": f"{SITE}/api/daily.json"},
                           {"@type": "DataDownload", "name": "All tickers with official bases and rates", "encodingFormat": "application/json", "contentUrl": f"{SITE}/data/data.json"}]}
    if temporal: ld["temporalCoverage"] = temporal
    return '<script type="application/ld+json">' + json.dumps(ld).replace("</", "<\\/") + "</script>"

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
    if i.get("held_at_limit"): return f"HELD AT DEBT LIMIT · official {fdate(i.get('as_of'))}"
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

for f in os.listdir(f"{R}/og"):   # drop share images for tickers that no longer exist (e.g. renamed slugs)
    if f.endswith(".png") and f[:-4] != "home" and (f[:-4] not in ALL or f[:-4] in HIST): os.remove(f"{R}/og/{f}")
home_debt = val("debt_total")
og(f"{R}/og/home.png", "US national debt · ticking live", fmt({"kind": "usd"}, home_debt),
   [("Per person (projected pop.)", ppf(home_debt / POP)), ("Per tax return filed", ppf(home_debt / TAX))],
   f"+{fmt({'kind':'usd'}, T['debt_total']['rate'] * 86400, True)}/day", "#ff4d5e",
   f"Treasury Debt to the Penny, {fdate(T['debt_total']['as_of'])} close\nprojected at the 90-day trend · checked daily")
for slug, i in ALL.items():
    x = get(slug)
    if x is None or slug in HIST: continue
    lines = [("Per person (projected pop.)", ppf(x / POP)), ("Per tax return filed", ppf(x / TAX))] if i.get("kind") == "usd" and slug != "debt_per_household" else \
            [("As of", fdate(i.get("as_of")) or "live"), ("Source", (i.get("source_name") or "Computed from official tickers")[:34])]
    mt = mode_txt(i).split(" · ")
    og(f"{R}/og/{slug}.png", label(slug, i), fmt(i, x), lines, mt[0], GROUP_COL.get(i.get("group"), "#5aa9ff"),
       (mt[1] if len(mt) > 1 else "") + "\n" + short_src(i.get("source_name") or "Official US data"))

# ---------------------------------------------------------------- index.html meta + build-time text (readable without JS)
idx = open(f"{R}/index.html").read()
PP_OFF = OFF_V / POP_OFF if OFF_V and POP_OFF else None
held = bool((T.get("debt_total") or {}).get("held_at_limit"))
desc = (f"US national debt: {tril(OFF_V)} at Treasury's {fdate(OFF_D)} close, {usd0(PP_OFF)} per person. "
        f"Live US debt clock projected from official Treasury data, with the deficit, interest, the debt limit and "
        f"{len(ALL) - len(HIST)} counters, checked daily against Treasury.")
HOME_TITLE = "US Debt Clock: Live National Debt, Checked Daily Against Treasury"
temporal = f"{CLOSES[-1][0]}/{CLOSES[0][0]}" if CLOSES else None
home_ld = dataset_ld("US national debt, daily official closes and live projection",
    f"Total public debt outstanding from Treasury's Debt to the Penny (latest close {fdate(OFF_D)}: {usd2(OFF_V)}), debt held by the public, "
    "intragovernmental holdings, debt subject to the statutory limit (Daily Treasury Statement Table III-C) and related federal fiscal figures, "
    "with per-person figures on the Census Vintage 2025 population. Re-based to Treasury every business day.",
    f"{SITE}/", based=["https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/debt-to-the-penny",
                       "https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/debt-subject-to-limit"], temporal=temporal)
meta = f"""<!--META--><title>{HOME_TITLE}</title>
<meta name="description" content="{html.escape(desc)}">
<link rel="canonical" href="{SITE}/">
<meta property="og:type" content="website"><meta property="og:site_name" content="Every Debt Clock"><meta property="og:url" content="{SITE}/">
<meta property="og:title" content="Every Debt Clock: US national debt, live and verified daily"><meta property="og:description" content="{html.escape(desc)}">
<meta property="og:image" content="{SITE}/og/home.png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta property="og:image:alt" content="US national debt counter with per-person and per-tax-return figures">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="Every Debt Clock: US national debt, live and verified daily">
<meta name="twitter:description" content="{html.escape(desc)}"><meta name="twitter:image" content="{SITE}/og/home.png">
{home_ld}
<!--/META-->"""
idx = re.sub(r"<!--META-->.*?<!--/META-->", lambda m: meta, idx, flags=re.S)
idx = re.sub(r'<meta property="og:title" content="US Debt Clock — live &amp; verified"><meta property="og:type" content="website">\n?', "", idx)
idx = idx.replace('<meta property="og:title" content="US Debt Clock — live & verified"><meta property="og:type" content="website">\n', "")
idx = re.sub(r'<script type="application/ld\+json">\{"@context":"https://schema.org","@type":"Dataset","name":"Every Debt Clock: US live tickers".*?</script>\n?', "", idx, flags=re.S)

ANSWERS = [("how-much-is-the-national-debt", "How much is the national debt?"), ("national-debt-per-person", "National debt per person"),
           ("national-debt-by-year", "US national debt by year"), ("when-will-debt-hit-41-trillion", "When will US debt hit $41 trillion?")]
KEY_TICKERS = ["debt_total", "debt_public", "debt_intragov", "debt_subject_limit", "debt_limit", "limit_headroom", "deficit", "interest_annual", "debt_per_household", "debt_gdp_now"]
sl_, lim_ = T.get("debt_subject_limit") or {}, T.get("debt_limit") or {}
rate_day = (T["debt_total"].get("rate_trend", T["debt_total"]["rate"])) * 86400
if held:
    proj_txt = (f"Debt subject to the limit is at the {tril(lim_.get('base', 0), 3)} statutory limit and Treasury is using extraordinary measures, "
                "so the clock below holds at Treasury's latest official figures instead of projecting growth.")
else:
    proj_txt = (f"The clock below starts from that official figure and projects forward at the 90-day trend (about {bil(rate_day)} a day). "
                "It is re-based to Treasury's new figure every business day and never projects past the debt limit.")
intro = (f"""<!--INTRO--><h1>US National Debt Clock</h1>
<p>The US national debt was <b>{usd2(OFF_V)}</b> ({tril(OFF_V)}) at the close of business on <b>{fdate(OFF_D)}</b>, according to Treasury's
<a href="{DTP_URL}" rel="noopener">Debt to the Penny</a>. That is <b>{usd2(PP_OFF)} per person</b>: the debt divided by the Census Bureau's estimate of
{POP_OFF:,.0f} US residents on {fdate(POP_OFF_DATE)}. {proj_txt}</p><!--/INTRO-->""")
def row(slug):
    i = ALL.get(slug)
    if not i: return ""
    if i.get("derived"):
        if slug == "limit_headroom" and lim_.get("base") and sl_.get("base"):
            v, asof = usd0(lim_["base"] - sl_["base"]), f"limit − debt subject to limit, official {fdate(sl_.get('as_of'))}"
        else: return ""
    else:
        v = usd0(i["base"]) if i.get("kind") == "usd" else fmt(i, i["base"])
        asof = (f"FY{i.get('fy')} to date through {fdate(i.get('as_of'))} (Daily Treasury Statement, converted to budget basis)" if i.get("mode") == "fytd"
                else f"official, {fdate(i.get('as_of'))}")
    return f'<tr><td><a href="t/{slug}.html">{html.escape(label(slug, i))}</a></td><td class="num">{v}</td><td>{html.escape(asof)}</td></tr>'
ssr = (f"""<!--SSR--><div class="ssr"><div class="hero lead"><div class="k">US national debt · official, {fdate(OFF_D)} close</div><div class="big num">{usd0(OFF_V)}</div>
<div class="trio"><div><span class="l">Per person (Census, {fdate(POP_OFF_DATE)})</span><span class="num">{usd2(PP_OFF)}</span></div>
<div><span class="l">Per tax return filed</span><span class="num">{usd2(OFF_V / TAX)}</span></div><div><span class="l">Per household</span><span class="num">{usd2(OFF_V / HH)}</span></div></div></div>
<section><div class="sh"><h2>Latest official figures</h2></div><table class="v"><tr><th>Figure</th><th>Amount</th><th>Basis</th></tr>
{''.join(row(s_) for s_ in ["debt_total", "debt_public", "debt_intragov", "debt_subject_limit", "debt_limit", "limit_headroom", "deficit", "spending", "revenue", "gdp"])}</table>
<noscript><p>Turn on JavaScript to watch these figures tick in real time.</p></noscript></section></div><!--/SSR-->""")
import places_build
PLACES_LIVE = places_build.load(R) if os.path.isdir(f"{R}/places") else []
links = (f"""<!--LINKS-->""" + ("" if not PLACES_LIVE else '<div class="sh"><h2>Debt by place</h2></div><ul>' + "".join(
         f'<li><a href="{d}/{p["slug"]}/">{html.escape(p["name"])} debt clock</a> (state + local)</li>' for k, d, _, _ in places_build.SECTIONS for p in PLACES_LIVE if p["kind"] == k)
         + "".join(f'<li><a href="{d}/">All {lab.lower()}</a></li>' for k, d, lab, _ in places_build.SECTIONS if any(p["kind"] == k for p in PLACES_LIVE)) + "</ul>") + f"""<div class="sh"><h2>Quick answers</h2></div><ul>{''.join(f'<li><a href="{a}/">{html.escape(t_)}</a></li>' for a, t_ in ANSWERS)}</ul>
<div class="sh"><h2>Popular counters</h2></div><ul>{''.join(f'<li><a href="t/{k}.html">{html.escape(label(k, ALL[k]))}</a></li>' for k in KEY_TICKERS if k in ALL)}</ul><!--/LINKS-->""")
if "<!--INTRO-->" in idx: idx = re.sub(r"<!--INTRO-->.*?<!--/INTRO-->", lambda m: intro, idx, flags=re.S)
else: idx = idx.replace('<main id="app">', f'<section class="intro" id="intro">{intro}</section>\n<main id="app">', 1)
if "<!--SSR-->" in idx: idx = re.sub(r"<!--SSR-->.*?<!--/SSR-->", lambda m: ssr, idx, flags=re.S)
else: idx = idx.replace('<main id="app"></main>', f'<main id="app">{ssr}</main>', 1)
if "<!--LINKS-->" in idx: idx = re.sub(r"<!--LINKS-->.*?<!--/LINKS-->", lambda m: links, idx, flags=re.S)
else: idx = idx.replace('<dialog id="dlg"></dialog>', f'<dialog id="dlg"></dialog>\n<section class="answers" id="answers">{links}</section>', 1)
PLNAV = ("<!--PLNAV-->" + ('<nav class="plnav"><a href="./" class="on">United States</a>' + "".join(f'<a href="{d}/">{lab}</a>' for k, d, lab, _ in places_build.SECTIONS
         if any(p["kind"] == k for p in PLACES_LIVE)) + "</nav>" if PLACES_LIVE else "") + "<!--/PLNAV-->")
if "<!--PLNAV-->" in idx: idx = re.sub(r"<!--PLNAV-->.*?<!--/PLNAV-->", lambda m: PLNAV, idx, flags=re.S)
else: idx = idx.replace('<span class="live">', PLNAV + '<span class="live">', 1)
# "Your state" card under the US hero: one compact card for the visitor's place (picked client-side in app.js from
# /api/geo, a saved choice, or the default), driven by the same index as api/places.json. Server-rendered with the
# default place so the card's height never changes when JS picks another place.
PIX = places_build.index(PLACES_LIVE, NOW)
def place_card(ix):
    if not ix["places"]: return "<!--PLACES--><!--/PLACES-->"
    p = next(x for x in ix["places"] if x["slug"] == ix["default"])
    v = p["base"] + p["rate"] * (NOW - p["t0"])
    opts = "".join(f'<option value="{x["slug"]}"{" selected" if x is p else ""}>{html.escape(x["name"])}</option>' for x in ix["places"])
    js_ix = json.dumps(ix, separators=(",", ":")).replace("</", "<\\/")
    return (f'<!--PLACES--><div class="placecard" id="placecard"><a class="pcmain" id="pcl" href="{p["url"]}">'
            f'<div class="k"><span id="pck">Featured state</span> · <b id="pcn">{html.escape(p["name"])}</b> <span id="pclab">{html.escape(p["label"])}</span></div>'
            f'<div class="pcv num" id="pcv">{usd0(v)}</div>'
            f'<div class="pcs"><span class="num" id="pcp">{usd2(v / p["population"])}</span> per <span id="pcd">{html.escape(p["demonym"])}</span> · '
            f'<span id="pcb">projected from official {fdate(p["base_date"])} figures</span> · <span class="go">See <span id="pcg">{html.escape(p["name"])}</span> →</span></div></a>'
            f'<label class="pcchg">Change <select id="pcsel" aria-label="Pick a place">{opts}</select></label>'
            f'<script type="application/json" id="placesix">{js_ix}</script></div>'
            f'<a class="pchub" href="{ix["hub"]}">See {html.escape(ix["hub_label"].lower().replace("all ", "all ", 1))} →</a><!--/PLACES-->')
PCARD = place_card(PIX)
if "<!--PLACES-->" in idx: idx = re.sub(r"<!--PLACES-->.*?<!--/PLACES-->", lambda m: PCARD, idx, flags=re.S)
else: idx = idx.replace("<!--/SSR--></main>", "<!--/SSR-->" + PCARD + "</main>", 1)
idx = with_analytics(idx)
open(f"{R}/index.html", "w").write(idx)
if os.path.exists(f"{R}/404.html"):
    p404 = with_analytics(open(f"{R}/404.html").read())
    open(f"{R}/404.html", "w").write(p404)

# ---------------------------------------------------------------- share pages
os.makedirs(f"{R}/t", exist_ok=True)
for f in os.listdir(f"{R}/t"): os.remove(f"{R}/t/{f}")
RELATED = {}
for slug, i in ALL.items():
    if slug not in HIST: RELATED.setdefault(i.get("group"), []).append(slug)
LIM = (T.get("debt_limit") or {}).get("base"); SUBJ = T.get("debt_subject_limit") or {}
# Query-matched titles/descriptions for the pages that map to real searches (others get a generated title).
KEY_PAGES = {
    "debt_total": ("US National Debt Clock: Live Total, Checked Daily Against Treasury",
                   f"US national debt: {usd2(OFF_V)} at Treasury's {fdate(OFF_D)} close ({usd2(OFF_V / POP_OFF)} per person). "
                   "Live national debt clock projected from Treasury's Debt to the Penny, re-based and checked every business day."),
    "debt_per_household": ("National Debt Per Household: Live, From Treasury and Census Data",
                           f"US national debt per household: {usd2(OFF_V / HH)} at Treasury's {fdate(OFF_D)} close, on Census's {HH:,.0f} households (CPS ASEC 2025). Ticks live between official updates."),
    "debt_limit": (f"US Debt Limit (Debt Ceiling): {tril(LIM or 0, 3)}, Per Treasury",
                   f"The statutory debt limit is {usd0(LIM)} ({tril(LIM or 0, 3)}), per Treasury's Daily Treasury Statement for {fdate(SUBJ.get('as_of'))}. "
                   f"Debt subject to the limit was {tril(SUBJ.get('base') or 0, 3)}, leaving {bil((LIM or 0) - (SUBJ.get('base') or 0))} of room."),
    "limit_headroom": ("How Close Is the US to the Debt Ceiling? Room Left, Live",
                       f"Room left under the {tril(LIM or 0, 3)} debt ceiling: {bil((LIM or 0) - (SUBJ.get('base') or 0))} at Treasury's {fdate(SUBJ.get('as_of'))} close "
                       "(Daily Treasury Statement Table III-C), counting down live at the 90-day trend."),
    "interest_annual": ("Interest on the National Debt: Annual Cost, Live",
                        None),
    "debt_public": ("Debt Held by the Public: Live US Total From Treasury", None),
    "deficit": (f"US Federal Deficit So Far in FY{M['fy']}: Live, From Treasury", None),
    "debt_gdp_now": ("US Debt-to-GDP Ratio Now: Live National Debt vs GDP", None),
}
need = {"population", "tax_returns", "households", "debt_total", "gdp", "spending", "revenue", "out_interest", "rate_all", "debt_limit",
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
    if x is None or slug in HIST: continue
    lab = label(slug, i); url = f"{SITE}/t/{slug}.html"
    usdpp = i.get("kind") == "usd" and slug != "debt_per_household"
    d1 = (f"{lab}: {fmt(i, x, True)} projected to {build_ct.strftime('%b %-d, %Y')}" + (f" ({ppf(x/POP)} per person on projected population, {ppf(x/TAX)} per tax return filed)" if usdpp else "") +
          (f". Official figure ({i.get('source_name')}), updated when the source publishes." if i.get("fixed") else
           f". Live counter from official data ({i.get('source_name') or 'computed from official Treasury tickers'}), recalibrated and checked daily."))
    kt, kd = KEY_PAGES.get(slug, (None, None))
    title = kt or f"{lab}: {'official figure' if i.get('fixed') else 'live calculation' if i.get('derived') else 'live counter'} | Every Debt Clock"
    d1 = kd or d1
    sub = {k: T[k] for k in need if k in T}
    if not i.get("derived"): sub[slug] = T[slug]
    data = json.dumps({"tickers": sub, "meta": {k: M[k] for k in ("fy_end_epoch", "fy")}, "derived": {slug: DV[slug]} if i.get("derived") else {}},
                      separators=(",", ":")).replace("</", "<\\/")
    rel = [s for s in RELATED.get(i.get("group"), []) if s != slug][:10]
    pp_off = (f" Official basis, no projection: {ppf(i['base'] / POP_OFF)} per person = Treasury's {fdate(i.get('as_of'))} close ÷ the {POP_OFF:,.0f} Census estimate for {fdate(POP_OFF_DATE)}."
              if slug == "debt_total" and i.get("base") and POP_OFF else "")
    v = i.get("validation") or {}
    check = (f"<p><b>Daily check.</b> Yesterday's projection vs {html.escape(v.get('against',''))}: {v['last_error_pct']:+.3f}% (threshold ±{v.get('threshold_pct')}%)"
             + (f"; average |error| over {v['n']} days {v['mean_abs_error_pct']:.3f}%" if v.get("mean_abs_error_pct") is not None else "") + ".</p>") if v.get("last_error_pct") is not None else ""
    ld = dataset_ld(lab, d1 if len(d1) >= 50 else d1 + " Every Debt Clock, from official US government data.", url,
                    based=[i.get("source") or "https://fiscaldata.treasury.gov/"], temporal=i.get("as_of") if re.match(r"^\d{4}-\d\d-\d\d$", i.get("as_of") or "") else None)
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(d1)}"><link rel="canonical" href="{url}">
<meta property="og:type" content="article"><meta property="og:site_name" content="Every Debt Clock"><meta property="og:url" content="{url}">
<meta property="og:title" content="{html.escape(lab)}: {html.escape(fmt(i, x, True))} and ticking"><meta property="og:description" content="{html.escape(d1)}">
<meta property="og:image" content="{SITE}/og/{slug}.png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{html.escape(lab)}: {html.escape(fmt(i, x, True))} and ticking">
<meta name="twitter:description" content="{html.escape(d1)}"><meta name="twitter:image" content="{SITE}/og/{slug}.png">
<meta name="theme-color" content="#07090d"><link rel="apple-touch-icon" href="../apple-touch-icon.png"><style>{PAGE_CSS}</style>
{ld}</head><body><main>
<a class="brand" href="../index.html">EVERY <b>DEBT</b> CLOCK</a>
<h1>{html.escape(lab)}</h1>
<div class="v" id="v">{html.escape(fmt(i, x))}</div>
{f'<div class="pp"><div><span class="l" title="Debt ÷ US population projected to now from Census Vintage 2025 (Jul 1, 2025 estimate) at the Census Bureau&#39;s stated growth rate">Per person (projected population)*</span><span class="n" id="p1">{ppf(x/POP)}</span></div><div><span class="l">Per tax return filed</span><span class="n" id="p2">{ppf(x/TAX)}</span></div></div>' if usdpp else ''}
<span class="b">{html.escape(mode_txt(i))}</span>{'<span class="b">official source cached (last run failed)</span>' if i.get('stale') else ''}
<p><b>How it's calculated.</b> {html.escape(i.get('method') or '')}</p>
{f'<p><b>Source.</b> <a href="{html.escape(i["source"])}" rel="noopener">{html.escape(i.get("source_name") or i["source"])}</a>, official as of {fdate(i.get("as_of"))}.</p>' if i.get('source') else ''}
{check}
<p><b>* Per person (projected population)</b> divides by the US population projected to now: the official Census Vintage 2025 estimate for July 1, 2025 ({POP_OFF:,.0f}), projected forward at Census's stated growth rate ({POP:,.0f} at build time).{pp_off} <b>Per tax return filed</b> divides by {TAX:,.0f} individual income tax returns filed in FY2025 (IRS Data Book, Table 1-2); a joint return counts once and returns with zero tax liability are included.</p>
<a class="cta" href="../index.html#t={slug}">Open the full live clock →</a>
<div class="rel"><b>Related:</b><br>{''.join(f'<a href="{s}.html">{html.escape(ALL[s].get("label", s))}</a>' for s in rel)}</div>
<footer>The value in this page's text is projected to {STAMP} from the official figure above (data fetched {gen_ct.strftime('%b %-d, %Y %-I:%M %p')} CT). The number above ticks live in your browser. · <a href="../privacy.html">Privacy</a></footer>
</main><script>window.DEBTCLOCK_DATA={data};</script><script src="../core.js"></script>
<script>(function(){{const C=DC(window.DEBTCLOCK_DATA),i=C.info({json.dumps(slug)}),v=document.getElementById('v'),p1=document.getElementById('p1'),p2=document.getElementById('p2');
(function f(){{const t=Date.now()/1000,x=C.get({json.dumps(slug)},t);v.textContent=C.fmt(i,x);if(p1){{p1.textContent=C.ppf(x/C.pop(t));p2.textContent=C.ppf(x/C.tax)}}requestAnimationFrame(f)}})()}})()</script>
</body></html>"""
    open(f"{R}/t/{slug}.html", "w").write(with_analytics(page))

# ---------------------------------------------------------------- redirects for renamed slugs (not in the sitemap)
# old slug -> (relative target from /t/, absolute canonical)
REDIRECTS = {"taxpayers": ("tax_returns.html", f"{SITE}/t/tax_returns.html")}
for h in HIST:      # the 14 fixed OMB ratio pages are folded into one by-year page
    y = ALL[h]["as_of"].replace("FY", "")
    REDIRECTS[h] = (f"../national-debt-by-year/#fy{y}", f"{SITE}/national-debt-by-year/")
for old, (rel, canon) in REDIRECTS.items():
    open(f"{R}/t/{old}.html", "w").write(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Moved | Every Debt Clock</title>
<link rel="canonical" href="{canon}"><meta name="robots" content="noindex"><meta http-equiv="refresh" content="0; url={rel}">
<script>location.replace("{rel}"{' + location.hash' if '#' not in rel else ''})</script></head><body><p>This page moved to <a href="{rel}">{rel}</a>.</p></body></html>
""")

# ---------------------------------------------------------------- /api/daily.json + /api/daily.txt
# Small, stable feed for the daily X post. Only real fetched Treasury rows; anything we can't compute is null.
def build_api():
    td = T.get("debt_total") or {}
    closes = M.get("debt_closes")
    if not closes and M.get("recent_closes"):          # older data.json: fall back to the What-changed rows (also official)
        closes = [[r["date"], r["total"]] for r in M["recent_closes"]]
    closes = sorted(((c[0], float(c[1])) for c in (closes or [])), key=lambda c: c[0], reverse=True)
    ok = td.get("status") == "ok" and closes and closes[0][0] == td.get("as_of")
    rec_date, official = (closes[0] if ok else (td.get("as_of"), None))
    if official is None and td.get("status") == "ok" and not td.get("stale"): official = td.get("base")
    def chg(days):
        if not ok: return None
        if days == 1:
            prev = closes[1] if len(closes) > 1 else None
        else:
            cut = (dt.date.fromisoformat(rec_date) - dt.timedelta(days=days)).isoformat()
            prev = next((c for c in closes if c[0] <= cut), None)
        if not prev: return None
        return {"amount": round(official - prev[1], 2), "from_date": prev[0], "from_value": round(prev[1], 2)}
    avg90 = None
    cf = (td.get("calc") or {})
    if cf.get("first") and cf.get("last"):
        d0, d1 = dt.date.fromisoformat(cf["first"][0]), dt.date.fromisoformat(cf["last"][0])
        if (d1 - d0).days > 0:
            avg90 = {"amount_per_day": round((cf["last"][1] - cf["first"][1]) / (d1 - d0).days, 2),
                     "from_date": cf["first"][0], "to_date": cf["last"][0], "method": "(last - first) / calendar days"}
    proj = val("debt_total")
    hh = (T.get("households") or {}).get("base")
    api = {
        "schema_version": 2,
        "as_of": build_ct.isoformat(timespec="seconds"),
        "treasury_record_date": rec_date if official is not None else None,
        "total_debt_official": round(official, 2) if official is not None else None,
        "total_debt_projected_now": round(proj) if proj is not None else None,
        "change_1d_official": chg(1),
        "change_7d_official": chg(7),
        "change_30d_official": chg(30),
        "avg_daily_change_90d": avg90,
        "per_second_rate": round(td["rate"], 2) if td.get("status") == "ok" else None,
        "held_at_debt_limit": bool(td.get("held_at_limit")),
        "per_second_rate_method": "90-day least-squares trend of Debt to the Penny" if td.get("status") == "ok" else None,
        "debt_per_person_official": round(official / POP_OFF, 2) if official is not None and POP_OFF else None,
        "census_population_official": int(POP_OFF) if POP_OFF else None,
        "census_population_vintage": "Census Vintage 2025 (NST-EST2025)" if POP_OFF else None,
        "census_population_date": POP_OFF_DATE if POP_OFF else None,
        "debt_per_person_projected_now": round(proj / POP, 2) if proj and POP else None,
        "population_projected_now": round(POP) if POP else None,
        "debt_per_household_official": round(official / hh, 2) if official is not None and hh else None,
        "debt_per_household_projected_now": round(proj / hh, 2) if proj and hh else None,
        "households_official": int(hh) if hh else None,
        "households_source": "Census CPS ASEC 2025" if hh else None,
        "per_person_basis": "_official = Treasury close / official Census estimate (no projection); _projected_now = projected debt / population projected at Census's stated rate",
        "stale": bool(td.get("stale") or M.get("debt_closes_stale")),
        "source_url": td.get("source") or "https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/debt-to-the-penny",
        "source_api": "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny",
        "site_url": SITE,
    }
    os.makedirs(f"{R}/api", exist_ok=True)
    json.dump(api, open(f"{R}/api/daily.json", "w"), indent=1)
    # one plain-English, nonpartisan line
    def big(x):
        a = abs(x)
        return f"${a/1e12:,.3f} trillion" if a >= 1e12 else f"${a/1e9:,.1f} billion" if a >= 1e9 else f"${a/1e6:,.1f} million" if a >= 1e6 else f"${a:,.0f}"
    if api["total_debt_official"] is None:
        line = ""
    else:
        line = f"US national debt: {big(api['total_debt_official'])} (Treasury, {fdate(rec_date)})."
        c = api["change_1d_official"]
        if c:
            word = "Up" if c["amount"] > 0 else "Down" if c["amount"] < 0 else "Unchanged"
            line += f" {word}{' ' + big(c['amount']) if c['amount'] else ''} since the prior record ({fdate(c['from_date'])})."
        line += f" {SITE.replace('https://', '')}"
    open(f"{R}/api/daily.txt", "w").write(line + "\n")
    return api
API = build_api()
# ---------------------------------------------------------------- answer pages (built from official data at build time)
ANS_CSS = """table{border-collapse:collapse;width:100%;font-size:13.5px;margin:8px 0 14px}th,td{border-bottom:1px solid #1c2533;padding:6px 8px;text-align:left;vertical-align:top}
th{color:#8a97ab;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.05em}td.num{font-family:ui-monospace,Menlo,monospace;text-align:right;white-space:nowrap}
h2{font-size:17px;margin:22px 0 6px}.k{color:#8a97ab;font-size:13px;margin:0}details summary{cursor:pointer;color:#5aa9ff;margin:8px 0}
.note{border:1px solid #5a3a12;background:#20170a;color:#ffb547;border-radius:10px;padding:10px 12px;font-size:13.5px}"""
def src_links(items):
    return "<p><b>Sources.</b> " + " · ".join(f'<a href="{html.escape(u)}" rel="noopener">{html.escape(n)}</a>' for n, u in items) + "</p>"
SRC_DTP = ("Treasury, Debt to the Penny", DTP_URL)
SRC_DSL = ("Treasury, Daily Treasury Statement Table III-C (debt subject to limit)", "https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/debt-subject-to-limit")
SRC_POP = ("Census Bureau, Vintage 2025 national population estimates", T["population"].get("source") or "https://www.census.gov/data/tables/time-series/demo/popest/2020s-national-total.html")
SRC_HH = ("Census Bureau, CPS ASEC 2025 Table HH-1", T["households"].get("source") or "https://www.census.gov/data/tables/time-series/demo/families/households.html")
SRC_IRS = ("IRS Data Book FY2025, Table 1-2", T["tax_returns"].get("source") or "https://www.irs.gov/statistics/soi-tax-stats-irs-data-book")
held_note = (f'<p class="note">At the debt limit: debt subject to the limit was {usd0(DLS.get("subject_to_limit"))} on {fdate(DLS.get("as_of"))}, '
             f'{bil(DLS.get("headroom") or 0)} under the {usd0(DLS.get("limit"))} limit. Treasury is using extraordinary measures, so the debt is not growing '
             'and our live clock holds at the official figure.</p>') if DLS.get("at_limit") else ""
def answer_page(slug, title, desc, h1, body, ld="", og_img="og/debt_total.png"):
    url = f"{SITE}/{slug}/"
    more = "".join(f'<a href="../{a}/">{html.escape(t_)}</a>' for a, t_ in ANSWERS if a != slug)
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}"><link rel="canonical" href="{url}">
<meta property="og:type" content="article"><meta property="og:site_name" content="Every Debt Clock"><meta property="og:url" content="{url}">
<meta property="og:title" content="{html.escape(title)}"><meta property="og:description" content="{html.escape(desc)}">
<meta property="og:image" content="{SITE}/{og_img}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{html.escape(title)}">
<meta name="twitter:description" content="{html.escape(desc)}"><meta name="twitter:image" content="{SITE}/{og_img}">
<meta name="theme-color" content="#07090d"><link rel="apple-touch-icon" href="../apple-touch-icon.png"><style>{PAGE_CSS}{ANS_CSS}</style>
{ld}</head><body><main>
<a class="brand" href="../">EVERY <b>DEBT</b> CLOCK</a>
<h1>{html.escape(h1)}</h1>
{held_note}{body}
<a class="cta" href="../">Open the live national debt clock →</a>
<div class="rel"><b>More answers:</b><br>{more}<a href="../t/debt_total.html">US national debt, live</a></div>
<footer>Every figure on this page is an official published number unless it is labelled "projected". Page built {STAMP} from data fetched {gen_ct.strftime('%b %-d, %Y %-I:%M %p')} CT; it is rebuilt after every Treasury update. · <a href="../privacy.html">Privacy</a></footer>
</main></body></html>"""
    os.makedirs(f"{R}/{slug}", exist_ok=True)
    open(f"{R}/{slug}/index.html", "w").write(with_analytics(page))

def closes_table(n, per_person=False):
    rows = CLOSES[:n + 1]
    out = ['<table><tr><th>Treasury close</th><th>Total debt</th><th>Change vs prior close</th>' + ('<th>Per person</th>' if per_person else '') + '</tr>']
    for k, (d, v) in enumerate(rows[:n]):
        ch = v - rows[k + 1][1] if k + 1 < len(rows) else None
        out.append(f'<tr><td>{fdate(d)}</td><td class="num">{usd0(v)}</td><td class="num">{"—" if ch is None else ("+" if ch >= 0 else "−") + bil(abs(ch))}</td>'
                   + (f'<td class="num">{usd2(v / POP_OFF)}</td>' if per_person else '') + '</tr>')
    return "".join(out) + "</table>"
def chg_txt(c, what):
    if not c: return ""
    a = c["amount"]; return f"<li>{what}: {'up' if a > 0 else 'down' if a < 0 else 'unchanged'} {bil(abs(a))} (from {usd0(c['from_value'])} on {fdate(c['from_date'])}).</li>"

if OFF_V:
    DP = T.get("debt_public") or {}; DI = T.get("debt_intragov") or {}
    proj_now = val("debt_total"); pop_now = POP
    not_subj = OFF_V - SUBJ["base"] if SUBJ.get("base") and SUBJ.get("as_of") == OFF_D else None

    # 1) How much is the national debt?
    body = f"""<p class="k">Treasury, Debt to the Penny · close of business {fdate(OFF_D)}</p><div class="v">{usd0(OFF_V)}</div>
<p><b>Answer.</b> The US national debt (total public debt outstanding) was <b>{usd2(OFF_V)}</b>, or about <b>{tril(OFF_V)}</b>, at the close of business on
{fdate(OFF_D)}, the latest figure Treasury has published. That is how much debt the US federal government is in: {usd2(OFF_V / POP_OFF)} for each of the
{POP_OFF:,.0f} people the Census Bureau counted on {fdate(POP_OFF_DATE)}.</p>
<h2>What the national debt is made of</h2>
<table><tr><th>Part</th><th>Amount</th><th>As of</th></tr>
<tr><td>Debt held by the public (Treasury securities owned by investors, the Fed, foreign governments)</td><td class="num">{usd0(DP.get('base'))}</td><td>{fdate(DP.get('as_of'))}</td></tr>
<tr><td>Intragovernmental holdings (securities held by federal trust funds such as Social Security)</td><td class="num">{usd0(DI.get('base'))}</td><td>{fdate(DI.get('as_of'))}</td></tr>
<tr><td><b>Total public debt outstanding</b></td><td class="num"><b>{usd0(OFF_V)}</b></td><td>{fdate(OFF_D)}</td></tr>
<tr><td>Debt subject to the statutory limit</td><td class="num">{usd0(SUBJ.get('base'))}</td><td>{fdate(SUBJ.get('as_of'))}</td></tr>
<tr><td>Statutory debt limit</td><td class="num">{usd0(LIM)}</td><td>{fdate(SUBJ.get('as_of'))}</td></tr></table>
<h2>How fast it is changing</h2><ul>
{chg_txt(API.get('change_1d_official'), 'Since the prior business day')}{chg_txt(API.get('change_7d_official'), 'Over about a week')}{chg_txt(API.get('change_30d_official'), 'Over about a month')}
<li>90-day trend: about {bil(rate_day)} a day (least-squares fit to Treasury's daily closes). Daily moves are lumpy: debt jumps on auction settlement days.</li>
<li>Projected to {STAMP} at that trend: {usd0(proj_now)} (projection, not an official figure).</li></ul>
<h2>Recent official closes</h2>{closes_table(10)}
<h2>When Treasury updates it</h2><p>Treasury publishes Debt to the Penny each business day, usually in the afternoon, for the previous business day's close. This page and the
<a href="../">live clock</a> are rebuilt after each release.</p>
{src_links([SRC_DTP, SRC_DSL, SRC_POP])}"""
    answer_page("how-much-is-the-national-debt",
                f"How Much Is the National Debt? {tril(OFF_V)} (Treasury, {fdate(OFF_D)})",
                f"The US national debt was {usd2(OFF_V)} ({tril(OFF_V)}) at Treasury's {fdate(OFF_D)} close: {usd0(DP.get('base'))} held by the public and "
                f"{usd0(DI.get('base'))} intragovernmental. Daily changes, the debt limit and recent official closes.",
                "How much is the national debt?", body,
                ld=dataset_ld("US national debt, latest official close", f"Total public debt outstanding, debt held by the public and intragovernmental holdings from Treasury's Debt to the Penny, latest close {fdate(OFF_D)}.",
                              f"{SITE}/how-much-is-the-national-debt/", temporal=f"{CLOSES[-1][0]}/{CLOSES[0][0]}" if CLOSES else None))

    # 2) National debt per person
    pp = OFF_V / POP_OFF
    body = f"""<p class="k">Treasury close {fdate(OFF_D)} ÷ Census population {fdate(POP_OFF_DATE)}</p><div class="v">{usd2(pp)}</div>
<p><b>Answer.</b> The national debt per person is <b>{usd2(pp)}</b>. That is Treasury's official total public debt outstanding of {usd2(OFF_V)}
at the close of business on {fdate(OFF_D)}, divided by the Census Bureau's official estimate of {POP_OFF:,.0f} US residents on {fdate(POP_OFF_DATE)}
(Vintage 2025, the latest official estimate).</p>
<h2>Other ways to divide it</h2>
<table><tr><th>Measure</th><th>Amount</th><th>Basis</th></tr>
<tr><td>Per person</td><td class="num">{usd2(pp)}</td><td>Total debt ({fdate(OFF_D)}) ÷ {POP_OFF:,.0f} residents ({fdate(POP_OFF_DATE)})</td></tr>
<tr><td>Per person, debt held by the public only</td><td class="num">{usd2((DP.get('base') or 0) / POP_OFF)}</td><td>{usd0(DP.get('base'))} ÷ the same population</td></tr>
<tr><td>Per household</td><td class="num">{usd2(OFF_V / HH)}</td><td>Total debt ÷ {HH:,.0f} households (Census CPS ASEC 2025)</td></tr>
<tr><td>Per individual income tax return filed</td><td class="num">{usd2(OFF_V / TAX)}</td><td>Total debt ÷ {TAX:,.0f} returns filed in FY2025 (IRS Data Book, Table 1-2)</td></tr>
<tr><td>Per person, projected to {STAMP}</td><td class="num">{usd2(proj_now / pop_now) if proj_now and pop_now else '—'}</td><td>Projection: debt at its 90-day trend ÷ population projected at Census's stated growth rate ({pop_now:,.0f})</td></tr></table>
<h2>Per person at recent official closes</h2><p>Same Census population for every row, so the change reflects the debt only.</p>{closes_table(10, per_person=True)}
<h2>What this number does and doesn't mean</h2>
<p>It is a way to scale a very large number, not a bill: no individual owes it. The population counts every resident, including children. The debt figure
and the population estimate have different dates because Census publishes its official estimate once a year (for July 1); we don't adjust either.
The total includes {usd0(DI.get('base'))} of intragovernmental debt that the government owes its own trust funds; the "held by the public" row leaves that out.</p>
{src_links([SRC_DTP, SRC_POP, SRC_HH, SRC_IRS])}"""
    answer_page("national-debt-per-person",
                f"National Debt Per Person: {usd0(pp)} (Treasury ÷ Census, {fdate(OFF_D)})",
                f"US national debt per person: {usd2(pp)}, Treasury's {fdate(OFF_D)} total of {tril(OFF_V)} divided by Census's {POP_OFF:,.0f} residents. "
                f"Also per household ({usd0(OFF_V / HH)}) and per tax return filed.",
                "National debt per person", body, og_img="og/home.png",
                ld=dataset_ld("US national debt per person", f"Total public debt outstanding (Treasury Debt to the Penny, {fdate(OFF_D)}) divided by the Census Vintage 2025 resident population estimate for {fdate(POP_OFF_DATE)}, plus per-household and per-tax-return figures.",
                              f"{SITE}/national-debt-per-person/", based=[DTP_URL, SRC_POP[1]]))

    # 3) National debt by year (also replaces the 14 fixed history pages)
    try: OMB = json.load(open(f"{R}/cache/omb_hist.json"))["data"]
    except Exception: OMB = {"t71": {}, "t12": {}}
    BY = {int(r[0]): (r[1], r[2]) for r in (M.get("debt_by_fy") or [])}
    t71, t12 = OMB.get("t71", {}), OMB.get("t12", {})
    def pc(v): return "—" if v is None else f"{v:.1f}%"
    def dpc(v): return "—" if v is None else ("surplus " + f"{v:.1f}%" if v > 0 else f"{-v:.1f}%")
    ys = sorted(set(BY) | {int(y) for y in t71}, reverse=True)
    modern = [y for y in ys if y >= 1940]; older = [y for y in ys if y < 1940 and y in BY]
    rows = []
    for y in modern:
        a = BY.get(y); r71 = t71.get(str(y)); r12 = t12.get(str(y))
        rows.append(f'<tr id="fy{y}"><td>FY{y}</td><td class="num">{usd0(a[1]) if a else "—"}</td><td>{fdate(a[0]) if a else "—"}</td>'
                    f'<td class="num">{pc(r71[6] if r71 else None)}</td><td class="num">{pc(r71[8] if r71 else None)}</td><td class="num">{dpc(r12[4] if r12 else None)}</td></tr>')
    orows = "".join(f'<tr id="fy{y}"><td>FY{y}</td><td class="num">{usd0(BY[y][1])}</td><td>{fdate(BY[y][0])}</td></tr>' for y in older)
    peak = max(((float(r[6]), int(y)) for y, r in t71.items() if r and r[6] is not None), default=None)
    ly = max(BY) if BY else None; lomb = max((int(y) for y in t71), default=None)
    summ = []
    if ly: summ.append(f"Total public debt outstanding was <b>{usd0(BY[ly][1])}</b> ({tril(BY[ly][1])}) at the end of FY{ly} ({fdate(BY[ly][0])})")
    if ly and ly - 1 in BY: summ.append(f"up {bil(BY[ly][1] - BY[ly - 1][1])} from FY{ly - 1}")
    if 2000 in BY: summ.append(f"and {BY[ly][1] / BY[2000][1]:.1f} times its FY2000 level of {tril(BY[2000][1])}")
    intro_y = ", ".join(summ) + "." if summ else ""
    if peak and lomb: intro_y += (f" Measured against the economy, gross federal debt was {t71[str(lomb)][6]:.1f}% of GDP in FY{lomb} (OMB); the peak in this table is "
                                  f"{peak[0]:.1f}% in FY{peak[1]}.")
    body = f"""<p><b>Answer.</b> {intro_y}</p>
<p>The dollar column is Treasury's Historical Debt Outstanding: total public debt at each fiscal year end (June 30 through FY1976, September 30 since FY1977).
The ratio columns are from OMB's Historical Tables (Table 7.1 for debt, Table 1.2 for the deficit). OMB's gross federal debt is measured a little differently
from Treasury's total (it includes some agency debt and nets out unamortized discount), so its ratio won't exactly match the dollar column divided by GDP.
"—" means the source has not published that year yet.</p>
<h2>By fiscal year, FY1940 to FY{modern[0] if modern else ''}</h2>
<table><tr><th>Fiscal year</th><th>Total debt (Treasury)</th><th>Record date</th><th>Gross debt % GDP (OMB)</th><th>Held by public % GDP (OMB)</th><th>Deficit % GDP (OMB)</th></tr>{''.join(rows)}</table>
<details><summary>Earlier years, FY{older[0] if older else ''} back to FY{older[-1] if older else ''} (Treasury totals only)</summary>
<table><tr><th>Fiscal year</th><th>Total debt</th><th>Record date</th></tr>{orows}</table></details>
<p>Today's figure: {usd0(OFF_V)} at Treasury's {fdate(OFF_D)} close (<a href="../how-much-is-the-national-debt/">details</a>).</p>
{src_links([("Treasury, Historical Debt Outstanding", M.get("debt_by_fy_source") or "https://fiscaldata.treasury.gov/datasets/historical-debt-outstanding/historical-debt-outstanding"),
            ("OMB Historical Tables (FY2027 Budget)", "https://www.govinfo.gov/app/collection/budget/2027/BUDGET-2027-TAB")])}"""
    if BY:
        answer_page("national-debt-by-year",
                    f"US National Debt by Year: Totals and Debt-to-GDP, FY{min(BY)} to FY{ly}",
                    f"US national debt by fiscal year from Treasury: {tril(BY[ly][1])} at the end of FY{ly}. Debt-to-GDP and deficit-to-GDP by year from OMB Historical Tables, FY1940 on.",
                    "US national debt by year", body,
                    ld=dataset_ld("US national debt by fiscal year", "Total public debt outstanding at each fiscal year end (Treasury Historical Debt Outstanding) with gross federal debt, debt held by the public and the deficit as a share of GDP (OMB Historical Tables 7.1 and 1.2).",
                                  f"{SITE}/national-debt-by-year/", based=[M.get("debt_by_fy_source") or DTP_URL, "https://www.govinfo.gov/app/collection/budget/2027/BUDGET-2027-TAB"],
                                  temporal=f"{min(BY)}/{ly}"))

    # 4) When will US debt hit $41 trillion?
    TARGET = 41e12
    first_hit = next((c for c in sorted(CLOSES) if c[1] >= TARGET), None)
    cf = T["debt_total"].get("calc") or {}
    t_off = dt.datetime.fromisoformat(OFF_D + "T23:59:59").replace(tzinfo=ET).timestamp()
    def when(rate_s):
        return dt.datetime.fromtimestamp(t_off + (TARGET - OFF_V) / rate_s, ZoneInfo("America/Chicago")) if rate_s and rate_s > 0 else None
    r_ols = T["debt_total"].get("rate_trend", T["debt_total"]["rate"])
    r_ft = None
    if cf.get("first") and cf.get("last"):
        dd = (dt.date.fromisoformat(cf["last"][0]) - dt.date.fromisoformat(cf["first"][0])).days
        if dd > 0: r_ft = (cf["last"][1] - cf["first"][1]) / dd / 86400
    e1, e2 = when(r_ols), when(r_ft)
    lim_t = dt.datetime.fromtimestamp(DLS["freeze_t"], ZoneInfo("America/Chicago")) if DLS.get("freeze_t") else None
    subj_at_target = TARGET - not_subj if not_subj is not None else None
    if first_hit:
        ans = f"It already has. Treasury's total public debt outstanding first closed above $41 trillion on <b>{fdate(first_hit[0])}</b> ({usd0(first_hit[1])})."
        ttl = f"When Did US Debt Hit $41 Trillion? {fdate(first_hit[0])} (Treasury)"
    elif DLS.get("at_limit"):
        ans = (f"Not while the debt limit binds. The debt was {usd0(OFF_V)} on {fdate(OFF_D)}, {bil(TARGET - OFF_V)} short of $41 trillion, and debt subject to the "
               f"limit is at the {tril(LIM, 3)} limit, so it can't grow much until Congress raises or suspends the limit.")
        ttl = "When Will US Debt Hit $41 Trillion? On Hold at the Debt Limit"
    else:
        ans = (f"At its recent pace, around <b>{e1.strftime('%b %-d, %Y')}</b>. The debt was {usd0(OFF_V)} at Treasury's {fdate(OFF_D)} close, "
               f"{bil(TARGET - OFF_V)} short of $41 trillion. That date is our projection from Treasury's daily figures, not a Treasury forecast.")
        ttl = f"When Will US Debt Hit $41 Trillion? Projected Around {e1.strftime('%b %-d, %Y')}"
    proj_rows = ""
    if not first_hit and not DLS.get("at_limit"):
        proj_rows = "<table><tr><th>Pace used</th><th>Per day</th><th>Projected $41T date (CT)</th></tr>"
        proj_rows += f"<tr><td>90-day least-squares trend ({cf.get('n', '—')} daily closes; the rate the live clock uses)</td><td class=\"num\">{bil(r_ols * 86400)}</td><td>{e1.strftime('%b %-d, %Y') if e1 else '—'}</td></tr>"
        if e2: proj_rows += f"<tr><td>Straight line from {fdate(cf['first'][0])} to {fdate(cf['last'][0])} (first and last close only)</td><td class=\"num\">{bil(r_ft * 86400)}</td><td>{e2.strftime('%b %-d, %Y')}</td></tr>"
        proj_rows += "</table><p>The two paces bracket a reasonable range. Daily moves are lumpy (big jumps on auction settlement days, dips when trust-fund securities mature), so the actual crossing can land days or weeks either side.</p>"
    lim_par = ""
    if LIM and SUBJ.get("base"):
        lim_par = (f"<h2>The debt limit</h2><p>The statutory debt limit is <b>{usd0(LIM)}</b> ({tril(LIM, 3)}), per Treasury's Daily Treasury Statement. It applies to "
                   f"<i>debt subject to the limit</i>, which was {usd0(SUBJ['base'])} on {fdate(SUBJ.get('as_of'))}, leaving {bil(LIM - SUBJ['base'])} of room.")
        if not_subj is not None:
            lim_par += (f" About {bil(not_subj)} of the total debt is not subject to the limit, so total debt reaches $41 trillion when debt subject to the limit is about "
                        f"{tril(subj_at_target, 3)}" + (", still under the limit" if subj_at_target < LIM else ", which is above the limit, so $41 trillion can't be reached unless Congress raises or suspends it")
                        + f"; the limit itself would bind with total debt near {tril(LIM + not_subj, 2)}.")
        if lim_t and not DLS.get("at_limit"):
            lim_par += f" At the 90-day pace of debt subject to the limit, the limit would be reached around {lim_t.strftime('%b %-d, %Y')} (our projection)."
            if e1 and lim_t < e1: lim_par += " That is before the projected $41 trillion date, so the crossing may wait until Congress acts."
        lim_par += (" Once the limit binds, Treasury uses extraordinary measures and the debt goes roughly flat; our clock then stops projecting growth and holds at the official figure.</p>")
    try: _rows = sorted(json.load(open(f"{R}/cache/debt_to_penny.json"))["data"]["rows"], key=lambda r: r["record_date"])
    except Exception: _rows = []
    _h40 = next((r for r in _rows if float(r["tot_pub_debt_out_amt"]) >= 40e12), None)
    m40 = (f"<p>For comparison, the previous trillion: total debt first closed above $40 trillion on {fdate(_h40['record_date'])} "
           f"({usd0(float(_h40['tot_pub_debt_out_amt']))}, Debt to the Penny).</p>") if _h40 and _h40 is not _rows[0] else ""
    body = f"""<p><b>Answer.</b> {ans}</p>{proj_rows}{lim_par}
<h2>Recent official closes</h2>{closes_table(5)}
{m40}<p>This page is rebuilt after each Treasury release.</p>
{src_links([SRC_DTP, SRC_DSL])}"""
    answer_page("when-will-debt-hit-41-trillion", ttl,
                (f"Projected date the US national debt passes $41 trillion, from Treasury's {fdate(OFF_D)} close of {tril(OFF_V)} and its 90-day trend, with the "
                 f"{tril(LIM or 0, 3)} debt limit explained." if not first_hit else f"US national debt first closed above $41 trillion on {fdate(first_hit[0])}, per Treasury's Debt to the Penny."),
                "When will US debt hit $41 trillion?", body)

# ---------------------------------------------------------------- place pages: /states/<slug>/, /countries/<slug>/ from places/*.json
import places_build
PLACE_URLS = places_build.build(R, SITE, with_analytics, PAGE_CSS, ANS_CSS, og, STAMP, NOW)

# ---------------------------------------------------------------- sitemap + robots
lm = gen_ct.date().isoformat()
urls = ([(f"{SITE}/", "1.0", "hourly")] + [(f"{SITE}/{a}/", "0.9", "daily") for a, _ in ANSWERS if os.path.exists(f"{R}/{a}/index.html")] +
        [(u, "0.8", "weekly") for u in PLACE_URLS] +
        [(f"{SITE}/t/{s}.html", "0.7", "daily") for s in ALL if s not in HIST and get(s) is not None] +
        ([(f"{SITE}/privacy.html", "0.2", "yearly")] if os.path.exists(f"{R}/privacy.html") else []))
open(f"{R}/sitemap.xml", "w").write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
    "".join(f"<url><loc>{u}</loc><lastmod>{lm}</lastmod><changefreq>{c}</changefreq><priority>{p}</priority></url>\n" for u, p, c in urls) + "</urlset>\n")
open(f"{R}/robots.txt", "w").write(f"User-agent: *\nAllow: /\nDisallow: /cache/\nDisallow: /pipeline/\nDisallow: /widget.html\nSitemap: {SITE}/sitemap.xml\n")

# ---------------------------------------------------------------- standalone
css, js = open(f"{R}/style.css").read(), open(f"{R}/app.js").read()
idx_ = re.sub(r'(href|src)="(style\.css|app\.js)\?v=[^"]*"', r'\1="\2"', idx)
single = (idx_.replace('<link rel="stylesheet" href="style.css">', f"<style>{css}</style>")
             .replace("<!--DATA-->", "<script>window.DEBTCLOCK_DATA=" + json.dumps(D, separators=(",", ":")).replace("</", "<\\/") + ";</script>")
             .replace('<script src="app.js"></script>', f"<script>{js}</script>"))
os.makedirs(f"{R}/dist", exist_ok=True)
open(f"{R}/dist/debtclock-standalone.html", "w").write(single)
print(f"standalone: {len(single)//1024} KB; share pages: {len(urls)-1}; og images: {len(os.listdir(R+'/og'))}; site={SITE}")

# ---------------------------------------------------------------- asset versions: ?v=<content hash> on every first-party CSS/JS reference
# so a deploy that changes style.css / app.js / core.js is picked up at once instead of after the 4-hour browser/CDN cache.
import hashlib, glob as _glob
AV = {a: hashlib.sha1(open(f"{R}/{a}", "rb").read()).hexdigest()[:10] for a in ("style.css", "app.js", "core.js") if os.path.exists(f"{R}/{a}")}
_vre = re.compile(r'((?:href|src)=")((?:\.\./)*)(' + "|".join(re.escape(a) for a in AV) + r')(?:\?v=[^"]*)?"')
_pages = ([f"{R}/{f}" for f in ("index.html", "404.html", "privacy.html", "widget.html")] + _glob.glob(f"{R}/t/*.html")
          + [f for d in ["states", "countries"] + [a for a, _ in ANSWERS] for f in _glob.glob(f"{R}/{d}/**/*.html", recursive=True)])
for f in _pages:
    if not os.path.exists(f): continue
    s_ = open(f).read(); n_ = _vre.sub(lambda m: f'{m.group(1)}{m.group(2)}{m.group(3)}?v={AV[m.group(3)]}"', s_)
    if n_ != s_: open(f, "w").write(n_)
print("asset versions:", AV)
