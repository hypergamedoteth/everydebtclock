#!/usr/bin/env python3
"""Build step (no bundler):
 1) index.html <head> meta refreshed with today's official numbers (title/description/OG/Twitter/canonical)
 2) og/<slug>.png + og/home.png share cards (1200x630, Pillow)
 3) t/<slug>.html noindex snapshot pages (one per ticker; not in the sitemap)
 4) sitemap.xml + robots.txt
 5) dist/debtclock-standalone.html (everything inlined, works offline)
 6) embed/ widgets (one noindex page per US, state, DC, country and world clock) and the indexable /embed/ directory
Site URL defaults to https://everydebtclock.com; override with DEBTCLOCK_SITE_URL for previews."""
import json, os, html, shutil, time, datetime as dt, re
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont
import site_chrome

R = os.path.dirname(os.path.abspath(__file__))
SITE = os.environ.get("DEBTCLOCK_SITE_URL", "https://everydebtclock.com").rstrip("/")
# Old iOS asks for this name even when apple-touch-icon.png is linked.
shutil.copyfile(f"{R}/apple-touch-icon.png", f"{R}/apple-touch-icon-precomposed.png")
import freshness
OLD_LASTMOD = freshness.read_lastmods(os.path.join(R, "sitemap.xml"))
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
    if not x or x.get("status") not in ("ok", "stale"): return None
    # A failed or cached source stays on its last official figure. It does not tick.
    if x.get("status") == "stale" or x.get("stale"): return x.get("base")
    if x.get("mode") == "fytd" and t >= M["fy_end_epoch"]: return x["rate"] * (t - M["fy_end_epoch"])
    if x.get("freeze_t") and t > x["freeze_t"]: t = x["freeze_t"]     # never project debt past the statutory limit
    return x["base"] + x["rate"] * (t - x["t0"]) + sum(a * min(1.0, max(0.0, (t - s0) / (s1 - s0))) for s0, s1, a, *_ in x.get("steps") or [])
def ia(t=NOW):
    a, r = val("debt_total", t), T.get("rate_all")
    return a * r["base"] / 100 if a and r else None
DER = {
    "debt_gdp_now": lambda: val("debt_total") / val("gdp") * 100,
    "deficit_gdp_now": lambda: (T["spending"]["ttm"] - T["revenue"]["ttm"]) / val("gdp") * 100,
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
ALL = {k: v for k, v in T.items() if v.get("status") in ("ok", "stale")}
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
def dataset_ld(name, desc, url, based=None, temporal=None, kw=None, source=None, modified=None):
    """Dataset JSON-LD. `source` is (organization, org url, credit text) for the figure's publisher."""
    org, org_url, credit = source or ("U.S. Department of the Treasury, Fiscal Data", "https://fiscaldata.treasury.gov/", "U.S. Treasury, Debt to the Penny")
    based = based or [DTP_URL]
    cite_url = based[0] if isinstance(based[0], str) else DTP_URL
    ld = {"@context": "https://schema.org", "@type": "Dataset", "name": name, "description": desc, "url": url, "isAccessibleForFree": True,
          "creator": [{"@type": "Organization", "name": org, "url": org_url},
                      {"@type": "Organization", "name": "Every Debt Clock", "url": SITE + "/"}],
          "publisher": {"@type": "Organization", "name": "Every Debt Clock", "url": SITE + "/"},
          "creditText": credit,
          "citation": {"@type": "CreativeWork", "name": credit, "url": cite_url,
                       "creator": {"@type": "Organization", "name": org, "url": org_url}},
          "dateModified": modified or OFF_D or M["generated_iso"],
          "spatialCoverage": {"@type": "Place", "name": "United States"},
          "isBasedOn": based, "keywords": kw or ["US national debt", "national debt clock", "Treasury Debt to the Penny", "federal debt"],
          "distribution": [{"@type": "DataDownload", "name": "Daily official national debt feed", "encodingFormat": "application/json", "contentUrl": f"{SITE}/api/daily.json"},
                           {"@type": "DataDownload", "name": "All tickers with official bases and rates", "encodingFormat": "application/json", "contentUrl": f"{SITE}/data/data.json"}]}
    if temporal: ld["temporalCoverage"] = temporal
    return '<script type="application/ld+json">' + json.dumps(ld).replace("</", "<\\/") + "</script>"

def faq_ld(pairs):
    """FAQPage JSON-LD. pairs = [(question, plain-text answer), ...]."""
    ld = {"@context": "https://schema.org", "@type": "FAQPage", "dateModified": M["generated_iso"],
          "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in pairs]}
    return '<script type="application/ld+json">' + json.dumps(ld).replace("</", "<\\/") + "</script>"

def faq_section(pairs, sources=None):
    """Visible FAQ. The paragraph text matches the FAQPage answers. sources = [(name, url), ...]."""
    body = "".join(f"<h3>{html.escape(q)}</h3><p>{html.escape(a)}</p>" for q, a in pairs)
    src = ""
    if sources:
        src = "<p><b>Sources.</b> " + " · ".join(f'<a href="{html.escape(u)}" rel="noopener">{html.escape(n)}</a>' for n, u in sources) + "</p>"
    return f'<section class="faq" id="faq"><h2>Questions</h2>{body}{src}</section>'

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
    return f"{s}{a:.6f}" if a < 0.01 else f"{s}{a:,.2f}"
def fdate(s):
    if not s: return ""
    if re.match(r"^\d{4}-\d\d-\d\d$", s): return dt.date.fromisoformat(s).strftime("%b %-d, %Y")
    if re.match(r"^\d{4}-\d\d$", s): return dt.date.fromisoformat(s + "-01").strftime("%b %Y")
    return s
def mode_txt(i):
    if i.get("historical"): return "HISTORICAL · fixed"
    if i.get("held_at_limit"): return f"HELD AT DEBT LIMIT · official {fdate(i.get('as_of'))}"
    if i.get("derived"): return "LIVE CALC · from official tickers"
    if i.get("badge"): return i["badge"]
    if i.get("fixed"): return f"FIXED · official {fdate(i.get('as_of'))}"
    if i.get("modeled"): return f"MODELED ESTIMATE · from {fdate(i.get('as_of'))}"
    if i.get("stale") or i.get("status") == "stale": return f"STALE · as of {fdate(i.get('as_of'))}"
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
# Crawlers still request URLs removed from git: taxpayers.png was renamed to tax_returns.png,
# and the 14 historical-ratio cards were folded into /national-debt-by-year/ (og/debt_total.png).
shutil.copyfile(f"{R}/og/tax_returns.png", f"{R}/og/taxpayers.png")
for _h in sorted(HIST):
    shutil.copyfile(f"{R}/og/debt_total.png", f"{R}/og/{_h}.png")

# ---------------------------------------------------------------- index.html meta + build-time text (readable without JS)
idx = open(f"{R}/index.html").read()
PP_OFF = OFF_V / POP_OFF if OFF_V and POP_OFF else None
held = bool((T.get("debt_total") or {}).get("held_at_limit"))
desc = (f"US national debt: {tril(OFF_V)} at Treasury's {fdate(OFF_D)} close, {usd2(PP_OFF)} per person. "
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
import topics_build
_HOME_HIST = topics_build._load(R)
MILE = topics_build.milestone_state(
    {"T": T, "NOW": NOW, "val": val, "fdate": fdate, "usd0": usd0, "usd2": usd2, "bil": bil, "OFF_D": OFF_D, "OFF_V": OFF_V},
    _HOME_HIST, topics_build.MILESTONE_PAGES[0])
INTEREST_DAY = topics_build.interest_day_answer(T, val, NOW, fdate, usd0, bil, STAMP)
_pub, _igov = T.get("debt_public") or {}, T.get("debt_intragov") or {}
_subj, _lim = T.get("debt_subject_limit") or {}, (T.get("debt_limit") or {}).get("base")
_rate_day = (T["debt_total"].get("rate_trend", T["debt_total"]["rate"])) * 86400
HOME_FAQS = [
    ("What is the US national debt right now?",
     f"As of {fdate(OFF_D)}, US federal debt is {tril(OFF_V)} ({usd2(OFF_V)}). "
     f"Source: U.S. Treasury, Debt to the Penny; the clock on this page projects forward from that close and is re-based every business day."),
    ("How much is the US debt per person?",
     f"US debt per person is {usd2(PP_OFF)} as of {fdate(OFF_D)}, the official total divided by the Census Bureau estimate of {POP_OFF:,.0f} residents on {fdate(POP_OFF_DATE)}. "
     f"Source: U.S. Treasury, Debt to the Penny, and the U.S. Census Bureau."),
]
if INTEREST_DAY:
    HOME_FAQS.append(("How much interest does the US pay per day?", INTEREST_DAY))
HOME_FAQS.append((f"When will the US debt hit ${MILE['n']} trillion?", MILE["quote"]))
if _pub.get("base") is not None and _igov.get("base") is not None:
    _limit_bit = (f", and debt subject to the statutory limit was {usd0(_subj['base'])} against a {usd0(_lim)} limit"
                  if _subj.get("base") is not None and _lim else "")
    HOME_FAQS.append((
        "How much of the national debt is held by the public?",
        f"As of {fdate(_pub.get('as_of'))}, {usd0(_pub['base'])} was held by the public and {usd0(_igov['base'])} was intragovernmental{_limit_bit}. "
        f"Source: U.S. Treasury, Debt to the Penny"
        + (" and the Daily Treasury Statement." if _limit_bit else "."),
    ))
if not held:
    HOME_FAQS.append((
        "How fast is the US national debt growing?",
        f"About {bil(_rate_day)} a day as of {fdate(OFF_D)}, the 90-day least-squares trend of U.S. Treasury Debt to the Penny closes. "
        f"Daily changes are lumpy, and the live clock uses this trend until the next Treasury close.",
    ))
if not 3 <= len(HOME_FAQS) <= 6:
    raise SystemExit(f"homepage FAQ has {len(HOME_FAQS)} questions")
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
{faq_ld(HOME_FAQS)}
<!--/META-->"""
idx = re.sub(r"<!--META-->.*?<!--/META-->", lambda m: meta, idx, flags=re.S)
idx = re.sub(r'<meta property="og:title" content="US Debt Clock — live &amp; verified"><meta property="og:type" content="website">\n?', "", idx)
idx = idx.replace('<meta property="og:title" content="US Debt Clock — live & verified"><meta property="og:type" content="website">\n', "")
idx = re.sub(r'<script type="application/ld\+json">\{"@context":"https://schema.org","@type":"Dataset","name":"Every Debt Clock: US live tickers".*?</script>\n?', "", idx, flags=re.S)

ANSWERS = [("how-much-is-the-national-debt", "How much is the national debt?"), ("debt-limit", "Debt limit and the X-date"),
           ("national-debt-per-person", "National debt per person"),
           ("facts", "Headline figures"),
           ("your-share", "Your share of the national debt"),
           ("national-debt-by-year", "US national debt by year"), ("41-trillion", "When will the US debt hit $41 trillion?"),
           ("press", "Press: the $41 trillion crossing"),
           ("national-debt-by-president", "National debt by president"), ("interest-on-the-national-debt", "Interest on the national debt"),
           ("methodology", "Methodology and accuracy")]
KEY_TICKERS = ["debt_total", "debt_public", "debt_intragov", "debt_subject_limit", "debt_limit", "limit_headroom", "deficit", "interest_annual", "debt_per_household", "debt_gdp_now"]
sl_, lim_ = T.get("debt_subject_limit") or {}, T.get("debt_limit") or {}
rate_day = (T["debt_total"].get("rate_trend", T["debt_total"]["rate"])) * 86400
if held:
    proj_txt = (f"Debt subject to the limit is at the {tril(lim_.get('base', 0), 3)} statutory limit and Treasury is using extraordinary measures, "
                "so the clock above holds at Treasury's latest official figures instead of projecting growth.")
else:
    proj_txt = (f"The clock above starts from that official figure and projects forward at the 90-day trend (about {bil(rate_day)} a day). "
                "It is re-based to Treasury's new figure every business day and never projects past the debt limit.")
import quotable
LEAD, LEAD_HTML = quotable.asof_pair(f"US federal debt is {tril(OFF_V)}", fdate(OFF_D), [("U.S. Treasury, Debt to the Penny", DTP_URL)])
answer_s = f"The official total is <b>{usd2(OFF_V)}</b> as of <b>{fdate(OFF_D)}</b>."
intro = (f"""<!--INTRO--><h1 class="quote asof" id="official">{LEAD_HTML}</h1>
<p class="answer">{answer_s} The figure is from <a href="{DTP_URL}" rel="noopener">U.S. Treasury, Debt to the Penny</a>.</p>
<p>That is <b>{usd2(PP_OFF)} per person</b>: the debt divided by the Census Bureau's estimate of
{POP_OFF:,.0f} US residents on {fdate(POP_OFF_DATE)}. {proj_txt}</p>
<!--/INTRO-->""")
# The World Debt Clock sentence is inserted after WORLD is computed, because the IMF general-government stock is not known yet.
def row(slug):
    i = ALL.get(slug)
    if not i: return ""
    if i.get("derived"):
        if slug == "limit_headroom" and lim_.get("base") and sl_.get("base"):
            v, asof = usd0(lim_["base"] - sl_["base"]), f"limit − debt subject to limit, official {fdate(sl_.get('as_of'))}"
        else: return ""
    else:
        if i.get("mode") == "fytd" and slug in ("deficit", "spending", "revenue"):   # budget-basis estimates: rounded, never to the dollar
            v = ("−$" if i["base"] < 0 else "$") + f"{abs(i['base'])/1e9:,.0f} billion (est.)"
            asof = (f"estimate: FY{i.get('fy')} to date through {fdate(i.get('as_of'))}, from the Daily Treasury Statement's cash flows converted to budget basis "
                    f"(revenue within about ±4%, the deficit less certain); Treasury's official monthly figure replaces it when published")
        else:
            v = usd0(i["base"]) if i.get("kind") == "usd" else fmt(i, i["base"])
            asof = (i["basis_txt"] if i.get("basis_txt") else f"official, {fdate(i.get('as_of'))}")
    return f'<tr><td><a href="t/{slug}.html">{html.escape(label(slug, i))}</a></td><td class="num">{v}</td><td>{html.escape(asof)}</td></tr>'
ssr = (f"""<!--SSR--><div class="ssr"><div class="hero lead"><div class="big num">{usd2(OFF_V)}</div></div>
<section class="intro" id="intro">{intro}</section>
<section><div class="sh"><h2>Latest figures</h2></div><table class="v"><tr><th>Figure</th><th>Amount</th><th>Basis</th></tr>
{''.join(row(s_) for s_ in ["debt_total", "debt_public", "debt_intragov", "debt_subject_limit", "debt_limit", "limit_headroom", "deficit", "spending", "revenue", "gdp"])}</table>
<noscript><p>Turn on JavaScript to watch these figures tick in real time.</p></noscript></section></div><!--/SSR-->""")
import places_build
PLACES_LIVE = places_build.load(R) if os.path.isdir(f"{R}/places") else []
# World Debt Clock: US national debt + every live country, in USD (world_build.py). None when there is no live country or no inputs.
import world_build
WORLD = world_build.compute(R, PLACES_LIVE, {"official": OFF_V, "date": OFF_D, "base": val("debt_total", NOW), "rate": (val("debt_total", NOW + 3600) - val("debt_total", NOW)) / 3600,
                                             "pop": POP_OFF, "pop_date": POP_OFF_DATE}, NOW) if PLACES_LIVE else None
places_build.WORLD = bool(WORLD)
places_build.WEO = os.path.exists(f"{R}/data/world_weo_debt.json")
places_build.HEADLINE_BY_SLUG = {x["slug"]: x for x in WORLD["rows"]} if WORLD else {}
if WORLD:
    _us = next(x for x in WORLD["rows"] if x["iso3"] == "USA")
    _us_note = (f'<p><b>World Debt Clock.</b> The United States row there starts at the IMF end-2025 general-government stock, '
                f'{usd0(_us["usd"])} as of {fdate(_us["as_of"]) if len(_us["as_of"]) == 10 else _us["as_of"]}, '
                f'and projects toward the IMF end-2026 estimate of {usd0(_us.get("imf_debt_2026") or 0)}. '
                f'This page\'s clock is narrower and is not in that total: federal debt, gross, Treasury Debt to the Penny, as of {fdate(OFF_D)}.</p>')
    intro = intro.replace("<!--/INTRO-->", _us_note + "<!--/INTRO-->")
    ssr = ssr.replace("<!--/INTRO-->", _us_note + "<!--/INTRO-->")
import explore
explore.check(PLACES_LIVE)
# Wealth tab (wealth_build.py): sets the flags/lists that nav, search and country-page links read, before any page is built
import wealth_build
WEALTH_D, WEALTH_FUNDS = wealth_build.prep(PLACES_LIVE)
# IMF GDP by place slug, used to pick peer-country related clocks (US included as "united-states")
_gdp = json.load(open(f"{R}/data/world_gdp.json")).get("countries", {}) if os.path.exists(f"{R}/data/world_gdp.json") else {}
places_build.GDP_BY_SLUG = {p["slug"]: _gdp.get(p.get("iso3") or world_build.ISO3.get(p.get("country", ""), ""), 0) for p in PLACES_LIVE if p["kind"] == "country"}
places_build.GDP_BY_SLUG["united-states"] = _gdp.get("USA", 0)
if PLACES_LIVE:
    explore.check_related(PLACES_LIVE, places_build.calc, gdp=places_build.GDP_BY_SLUG, funds=WEALTH_FUNDS)
HOME_EXPLORE = explore.explore("", PLACES_LIVE, places_build.calc, cur=None, gdp=places_build.GDP_BY_SLUG, kind_hint="us") if PLACES_LIVE else ""
HOME_FAQ_HTML = faq_section(HOME_FAQS, [
    ("Treasury, Debt to the Penny", DTP_URL),
    ("Treasury, Daily Treasury Statement Table III-C", "https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/debt-subject-to-limit"),
    ("Census Bureau, Vintage 2025 national population estimates", (T.get("population") or {}).get("source") or "https://www.census.gov/data/tables/time-series/demo/popest/2020s-national-total.html"),
    ("Treasury, Average Interest Rates on U.S. Treasury Securities", (T.get("rate_all") or {}).get("source") or "https://fiscaldata.treasury.gov/datasets/average-interest-rates-treasury-securities/average-interest-rates-on-u-s-treasury-securities"),
    ("Treasury, Interest Expense on the Public Debt Outstanding", (T.get("interest_gross") or {}).get("source") or "https://fiscaldata.treasury.gov/datasets/interest-expense-debt-outstanding/interest-expense"),
])
links = (f"""<!--LINKS-->""" + HOME_FAQ_HTML + HOME_EXPLORE + ("" if not PLACES_LIVE else '<div class="sh"><h2>Debt by place</h2></div><ul>' + "".join(
         f'<li><a href="{d}/{p["slug"]}/">{html.escape(p["name"])} debt clock</a> ({html.escape(p.get("link_label", "state + local"))})</li>' for k, d, _, _ in places_build.SECTIONS for p in PLACES_LIVE if p["kind"] == k)
         + "".join(f'<li><a href="{d}/">All {lab.lower()}</a></li>' for k, d, lab, _ in places_build.SECTIONS if any(p["kind"] == k for p in PLACES_LIVE)) + ('<li><a href="world/">World debt clock</a> (general government gross debt of every IMF economy)</li>' if WORLD else "") + "</ul>") + f"""<div class="sh"><h2>Quick answers</h2></div><ul>{''.join(f'<li><a href="{a}/">{html.escape(t_)}</a></li>' for a, t_ in ANSWERS)}</ul>
<div class="sh"><h2>Popular counters</h2></div><ul>{''.join(f'<li><a href="t/{k}.html">{html.escape(label(k, ALL[k]))}</a></li>' for k in KEY_TICKERS if k in ALL)}</ul><!--/LINKS-->""")
if "<!--INTRO-->" in idx: idx = re.sub(r"<!--INTRO-->.*?<!--/INTRO-->", lambda m: intro, idx, flags=re.S)
if "<!--SSR-->" in idx: idx = re.sub(r"<!--SSR-->.*?<!--/SSR-->", lambda m: ssr, idx, flags=re.S)
else: idx = idx.replace('<main id="app"></main>', f'<main id="app">{ssr}</main>', 1)
if "<!--LINKS-->" in idx: idx = re.sub(r"<!--LINKS-->.*?<!--/LINKS-->", lambda m: links, idx, flags=re.S)
else: idx = idx.replace('<dialog id="dlg"></dialog>', f'<dialog id="dlg"></dialog>\n<section class="answers" id="answers">{links}</section>', 1)
PLNAV = ("<!--PLNAV-->" + ('<nav class="plnav"><a href="./" class="on">United States</a>' + "".join(f'<a href="{d}/">{lab}</a>' for k, d, lab, _ in places_build.SECTIONS
         if any(p["kind"] == k for p in PLACES_LIVE)) + ('<a href="world/">World</a>' if WORLD else "") + ('<a href="wealth/">Wealth</a>' if WEALTH_FUNDS else "") + '<a href="debt-limit/">Debt limit</a><a href="reports/">Reports</a><a href="embed/">Embed</a></nav>' if PLACES_LIVE else "") + "<!--/PLNAV-->")
SEARCH = "<!--SEARCH-->" + (explore.search_box("") if PLACES_LIVE else "") + "<!--/SEARCH-->"
if "<!--SEARCH-->" in idx: idx = re.sub(r"<!--SEARCH-->.*?<!--/SEARCH-->", lambda m: SEARCH, idx, flags=re.S)
else: idx = idx.replace("</header>", "</header>" + SEARCH, 1)
if "<!--PLNAV-->" in idx: idx = re.sub(r"<!--PLNAV-->.*?<!--/PLNAV-->", lambda m: PLNAV, idx, flags=re.S)
else: idx = idx.replace('<span class="live">', PLNAV + '<span class="live">', 1)
# "Your state" card under the US hero: one compact card for the visitor's place (picked client-side in app.js from
# a saved choice, or the default), driven by the same index as api/places.json. Server-rendered with the
# default place so the card's height never changes when JS picks another place.
PIX = places_build.index(PLACES_LIVE, NOW)
def place_card(ix):
    if not ix["places"]: return "<!--PLACES--><!--/PLACES-->"
    p = next(x for x in ix["places"] if x["slug"] == ix["default"])
    coarse = p.get("frequency") not in ("daily", "weekly")
    v = p["base"] if coarse or not p["rate"] else p["base"] + p["rate"] * (NOW - p["t0"])
    if not p["rate"] or coarse:
        basis = f'as of {fdate(p["base_date"])}'
    else:
        basis = f'projection from {fdate(p["base_date"])}'
    cu = lambda s_: s_.replace("$", p.get("sym", "$"), 1)
    opts = "".join(f'<option value="{x["slug"]}"{" selected" if x is p else ""}>{html.escape(x["name"])}</option>' for x in ix["places"])
    js_ix = json.dumps(ix, separators=(",", ":")).replace("</", "<\\/")
    return (f'<!--PLACES--><div class="placecard" id="placecard"><a class="pcmain" id="pcl" href="{p["url"]}">'
            f'<div class="k"><span id="pck">Featured {"country" if p["kind"] == "country" else "state"}</span> · <b id="pcn">{html.escape(p["name"])}</b> <span id="pclab">{html.escape(p["label"])}</span></div>'
            f'<div class="pcv num" id="pcv">{cu(usd0(v))}</div>'
            f'<div class="pcs"><span class="num" id="pcp">{cu(usd2(v / p["population"]))}</span> per <span id="pcd">{html.escape(p["demonym"])}</span> · '
            f'<span id="pcb">{basis}</span> · <span class="go">See <span id="pcg">{html.escape(p["name"])}</span> →</span></div></a>'
            f'<label class="pcchg">Change <select id="pcsel" aria-label="Pick a place">{opts}</select></label>'
            f'<script type="application/json" id="placesix">{js_ix}</script></div>'
            f'<a class="pchub" href="{ix["hub"]}">See {html.escape(ix["hub_label"].lower().replace("all ", "all ", 1))} →</a><!--/PLACES-->')
PCARD = place_card(PIX)
if "<!--PLACES-->" in idx: idx = re.sub(r"<!--PLACES-->.*?<!--/PLACES-->", lambda m: PCARD, idx, flags=re.S)
else: idx = idx.replace("<!--/SSR--></main>", "<!--/SSR-->" + PCARD + "</main>", 1)
if 'href="#faq"' not in idx:
    idx = idx.replace('<a href="#method">Method</a>', '<a href="#method">Method</a><a href="#faq">Questions</a>', 1)
idx = with_analytics(idx)
open(f"{R}/index.html", "w").write(idx)
if os.path.exists(f"{R}/404.html"):
    p404 = with_analytics(open(f"{R}/404.html").read())
    open(f"{R}/404.html", "w").write(p404)

# ---------------------------------------------------------------- share pages
os.makedirs(f"{R}/t", exist_ok=True)
for f in os.listdir(f"{R}/t"):
    path = f"{R}/t/{f}"
    shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
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
    d1 = (f"{lab}: {fmt(i, x, True)}" + ("" if i.get("fixed") else f" projected to {build_ct.strftime('%b %-d, %Y')}") + (f" ({ppf(x/POP)} per person on projected population, {ppf(x/TAX)} per tax return filed)" if usdpp else "") +
          (f". Official figure ({i.get('source_name')}), updated when the source publishes." if i.get("fixed") else
           f". Modeled estimate, not an official published figure: {i.get('source_name')}. Recalibrated daily." if i.get("modeled") else
           f". Counter from official data ({i.get('source_name') or 'computed from official Treasury tickers'}), recalibrated and checked daily."))
    kt, kd = KEY_PAGES.get(slug, (None, None))
    title = kt or f"{lab}: {'official figure' if i.get('fixed') else 'live calculation' if i.get('derived') else 'modeled estimate' if i.get('modeled') else 'live counter'} | Every Debt Clock"
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
             + (f"; average |error| over {v['n']} days {v['mean_abs_error_pct']:.3f}%" if v.get("mean_abs_error_pct") is not None else "") + "." + (" " + html.escape(v["note"]) if v.get("note") else "") + "</p>") if v.get("last_error_pct") is not None else ""
    ld = dataset_ld(lab, d1 if len(d1) >= 50 else d1 + " Every Debt Clock, from official US government data.", url,
                    based=[i.get("source") or "https://fiscaldata.treasury.gov/"], temporal=i.get("as_of") if re.match(r"^\d{4}-\d\d-\d\d$", i.get("as_of") or "") else None)
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(d1)}"><link rel="canonical" href="{SITE}/"><meta name="robots" content="noindex">
<meta property="og:type" content="article"><meta property="og:site_name" content="Every Debt Clock"><meta property="og:url" content="{url}">
<meta property="og:title" content="{html.escape(lab)}: {html.escape(fmt(i, x, True))} and ticking"><meta property="og:description" content="{html.escape(d1)}">
<meta property="og:image" content="{SITE}/og/{slug}.png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{html.escape(lab)}: {html.escape(fmt(i, x, True))} and ticking">
<meta name="twitter:description" content="{html.escape(d1)}"><meta name="twitter:image" content="{SITE}/og/{slug}.png">
<meta name="theme-color" content="#07090d"><link rel="apple-touch-icon" href="../apple-touch-icon.png"><style>{PAGE_CSS}</style>
{ld}</head><body><main>
<a class="brand" href="../index.html">EVERY <b>DEBT</b> CLOCK</a><a class="navembed" href="../embed/" style="margin-left:12px;font-size:13px;font-weight:650">Embed</a>
<h1>{html.escape(lab)}</h1>
<div class="v" id="v">{html.escape(fmt(i, x))}</div>
{f'<div class="pp"><div><span class="l" title="Debt ÷ US population projected to now from Census Vintage 2025 (Jul 1, 2025 estimate) at the Census Bureau&#39;s stated growth rate">Per person (projected population)*</span><span class="n" id="p1">{ppf(x/POP)}</span></div><div><span class="l">Per tax return filed</span><span class="n" id="p2">{ppf(x/TAX)}</span></div></div>' if usdpp else ''}
<span class="b">{html.escape(mode_txt(i))}</span>{'<span class="b">official source cached (last run failed)</span>' if i.get('stale') else ''}
<p><b>How it's calculated.</b> {html.escape(i.get('method') or '')}</p>
{f'<p><b>Source.</b> <a href="{html.escape(i["source"])}" rel="noopener">{html.escape(i.get("source_name") or i["source"])}</a>, {"daily total as of" if i.get("modeled") else "official as of"} {fdate(i.get("as_of"))}.</p>' if i.get('source') else ''}
{check}
<p><b>* Per person (projected population)</b> divides by the US population projected to now: the official Census Vintage 2025 estimate for July 1, 2025 ({POP_OFF:,.0f}), projected forward at Census's stated growth rate ({POP:,.0f} at build time).{pp_off} <b>Per tax return filed</b> divides by {TAX:,.0f} individual income tax returns filed in FY2025 (IRS Data Book, Table 1-2); a joint return counts once and returns with zero tax liability are included.</p>
<a class="cta" href="../index.html#t={slug}">Open the full live clock →</a>
<div class="rel"><b>Related:</b><br>{''.join(f'<a href="{s}.html">{html.escape(ALL[s].get("label", s))}</a>' for s in rel)}</div>
<footer>The value in this page's text is projected to {STAMP} from the official figure above (data fetched {gen_ct.strftime('%b %-d, %Y %-I:%M %p')} CT). The number above ticks live in your browser. · <a href="../embed/">Embed a clock</a> · <a href="../data/">Data</a> · <a href="../methodology/">Methodology</a> · <a href="../privacy/">Privacy</a> · Independent site, not affiliated with the U.S. government. Not financial advice.</footer>
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
# Directory form of the same pages. GitHub Pages does not map /t/tax_returns/ onto tax_returns.html.
for folder, rel, canon in (
    ("tax_returns", "../tax_returns.html", f"{SITE}/t/tax_returns.html"),
    ("taxpayers", "../tax_returns.html", f"{SITE}/t/tax_returns.html"),
):
    os.makedirs(f"{R}/t/{folder}", exist_ok=True)
    open(f"{R}/t/{folder}/index.html", "w").write(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Moved | Every Debt Clock</title>
<link rel="canonical" href="{canon}"><meta name="robots" content="noindex"><meta http-equiv="refresh" content="0; url={rel}">
<script>location.replace("{rel}" + location.hash)</script></head><body><p>This page moved to <a href="{rel}">{rel}</a>.</p></body></html>
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
                     "from_date": cf["first"][0], "to_date": cf["last"][0],
                     "method": "straight line: (last close − first close) / calendar days in the 90-day window. Not the least-squares rate the clock uses."}
    proj = val("debt_total")
    fe = M.get("debt_fetched_epoch") if "debt_fetched_epoch" in M else M.get("generated_epoch")   # older data.json: fetch-run time
    fetched_ct = dt.datetime.fromtimestamp(fe, ZoneInfo("America/Chicago")) if fe else None
    hh = (T.get("households") or {}).get("base")
    api = {
        "schema_version": 2,
        "as_of": build_ct.isoformat(timespec="seconds"),
        "fetched_at": fetched_ct.isoformat(timespec="seconds") if fetched_ct else None,   # when Treasury data was pulled (as_of = page build time)
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
        # Same dollars-per-day figure as per_second_rate. avg_daily_change_90d stays the endpoint line.
        "clock_daily_change_90d": ({"amount_per_day": round(td["rate"] * 86400, 2),
                                     "per_second": round(td["rate"], 2),
                                     "from_date": (cf.get("first") or [None])[0],
                                     "to_date": (cf.get("last") or [None])[0],
                                     "method": "90-day least-squares slope of Debt to the Penny × 86,400. This is the live clock. per_second_rate is that slope rounded to the cent. avg_daily_change_90d is the straight line between the window's end points, not this slope."}
                                    if td.get("status") == "ok" and td.get("rate") is not None else None),
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
    # Additive debt-limit fields. Existing keys stay. See pipeline/debt_limit.py.
    import debt_limit_page
    _sum, _subj, _lim_t = debt_limit_page._summary(R, T)
    _slope = float(_subj.get("rate") or 0) if _subj else 0.0
    if _slope <= 0 and _subj and _subj.get("rate_trend"):
        _slope = float(_subj["rate_trend"])
    api.update(debt_limit_page.debt_limit.api_fields(_sum, _slope or None, (_subj or {}).get("t0")))
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
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch}code{overflow-wrap:anywhere}.note{border:1px solid #5a3a12;background:#20170a;color:#ffb547;border-radius:10px;padding:10px 12px;font-size:13.5px}
.faq h3{font-size:15.5px;margin:16px 0 4px}.faq p{margin:0 0 8px}
h1.quote,h1.asof,p.asof{font-size:15px;font-weight:650;line-height:1.45;margin:8px 0 10px;overflow-wrap:anywhere}
.hero.lead{border:1px solid #1c2533;background:#101828;border-radius:18px;padding:14px 12px;margin:8px 0 4px;max-width:100%}
.hero.lead .k{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#8a97ab}
.hero.lead .big{font:700 clamp(22px,6.2vw,46px)/1.1 ui-monospace,Menlo,monospace;color:#fff;margin:6px 0 0;overflow-wrap:anywhere}
.hero.lead .sub{color:#8a97ab;font-size:13px;margin-top:4px}"""
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
def answer_page(slug, title, desc, h1, body, ld="", og_img="og/debt_total.png", faqs=None, hero="", h1_html=None):
    url = f"{SITE}/{slug}/"
    body = body.replace("<table", '<div class="tw"><table').replace("</table>", "</table></div>")  # wide tables scroll inside the page on phones
    more = "".join(f'<a href="../{a}/">{html.escape(t_)}</a>' for a, t_ in ANSWERS if a != slug)
    heading = h1_html or f'<h1 class="quote">{html.escape(h1)}</h1>'
    brand = '<a class="brand" href="../">EVERY <b>DEBT</b> CLOCK</a><a class="navembed" href="../embed/" style="margin-left:12px;font-size:13px;font-weight:650">Embed</a>'
    # A hero clock stays first. Pages without one keep the dated heading as the lead.
    top = (brand + hero + heading) if hero else ((heading + brand) if slug == "national-debt-by-year" else (brand + heading))
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}"><link rel="canonical" href="{url}">
<meta property="og:type" content="article"><meta property="og:site_name" content="Every Debt Clock"><meta property="og:url" content="{url}">
<meta property="og:title" content="{html.escape(title)}"><meta property="og:description" content="{html.escape(desc)}">
<meta property="og:image" content="{SITE}/{og_img}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{html.escape(title)}">
<meta name="twitter:description" content="{html.escape(desc)}"><meta name="twitter:image" content="{SITE}/{og_img}">
<meta name="theme-color" content="#07090d"><link rel="apple-touch-icon" href="../apple-touch-icon.png"><style>{PAGE_CSS}{ANS_CSS}{explore.RELATED_CSS}</style>
{ld}</head><body><main>
{top}
{held_note}{body}
{faq_section(faqs) if faqs else ""}
<a class="cta" href="../">Open the live national debt clock →</a>
{explore.explore("../", PLACES_LIVE, places_build.calc, topic=slug, gdp=places_build.GDP_BY_SLUG) if PLACES_LIVE else ""}
<div class="rel"><b>More answers:</b><br>{more}<a href="../t/debt_total.html">US national debt, live</a></div>
<footer>Every figure on this page is an official published number unless it is labelled "projected". Page built {STAMP} from data fetched {gen_ct.strftime('%b %-d, %Y %-I:%M %p')} CT; it is rebuilt after every Treasury update. · <a href="../embed/">Embed a clock</a> · <a href="../data/">Data</a> · <a href="../methodology/">Methodology</a> · <a href="../privacy/">Privacy</a> · Independent site, not affiliated with the U.S. government. Not financial advice.</footer>
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
<p>Headroom, extraordinary measures, and X-date forecasts are on the <a href="../debt-limit/">debt limit page</a>.</p>
{src_links([SRC_DTP, SRC_DSL, SRC_POP])}"""
    answer_page("how-much-is-the-national-debt",
                f"How Much Is the National Debt? {tril(OFF_V)} (Treasury, {fdate(OFF_D)})",
                f"The US national debt was {usd2(OFF_V)} ({tril(OFF_V)}) at Treasury's {fdate(OFF_D)} close: {usd0(DP.get('base'))} held by the public and "
                f"{usd0(DI.get('base'))} intragovernmental. Daily changes, the debt limit and recent official closes.",
                "How much is the national debt?", body,
                ld=dataset_ld("US national debt, latest official close", f"Total public debt outstanding, debt held by the public and intragovernmental holdings from Treasury's Debt to the Penny, latest close {fdate(OFF_D)}.",
                              f"{SITE}/how-much-is-the-national-debt/", temporal=f"{CLOSES[-1][0]}/{CLOSES[0][0]}" if CLOSES else None)
                    + faq_ld([
                        ("How much is the US national debt?",
                         f"The US national debt was {usd2(OFF_V)} ({tril(OFF_V)}) at Treasury's {fdate(OFF_D)} close, according to Debt to the Penny."),
                        ("How much of that is held by the public?",
                         f"{usd0(DP.get('base'))} was held by the public and {usd0(DI.get('base'))} was intragovernmental as of {fdate(DP.get('as_of'))}."),
                    ]))

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
                f"National Debt Per Person: {usd2(pp)} (Treasury ÷ Census, {fdate(OFF_D)})",
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
    hdo_url = M.get("debt_by_fy_source") or "https://fiscaldata.treasury.gov/datasets/historical-debt-outstanding/historical-debt-outstanding"
    omb_url = "https://www.govinfo.gov/app/collection/budget/2027/BUDGET-2027-TAB"
    summ = []
    if ly and ly - 1 in BY: summ.append(f"up {bil(BY[ly][1] - BY[ly - 1][1])} from FY{ly - 1}")
    if ly and 2000 in BY and BY[2000][1]: summ.append(f"{BY[ly][1] / BY[2000][1]:.1f} times its FY2000 level of {tril(BY[2000][1])}")
    intro_y = ("It was " + " and ".join(summ) + ". ") if summ else ""
    if peak and lomb and t71.get(str(lomb)) and t71[str(lomb)][6] is not None:
        intro_y += (f"Measured against the economy, gross federal debt was {t71[str(lomb)][6]:.1f}% of GDP in FY{lomb} (OMB); the peak in this table is "
                    f"{peak[0]:.1f}% in FY{peak[1]}.")
    answer_y = (f"The year-end record is <b>{usd0(BY[ly][1])}</b> as of {fdate(BY[ly][0])}. "
                f"It is Treasury's Historical Debt Outstanding total for FY{ly}, not the live national debt clock."
                if ly else "")
    body = f"""<p class="answer">{answer_y}</p>
<p>{intro_y}</p>
<p>The dollar column is Treasury's Historical Debt Outstanding: total public debt at each fiscal year end (June 30 through FY1976, September 30 since FY1977).
The ratio columns are from OMB's Historical Tables (Table 7.1 for debt, Table 1.2 for the deficit). OMB's gross federal debt is measured a little differently
from Treasury's total (it includes some agency debt and nets out unamortized discount), so its ratio won't exactly match the dollar column divided by GDP.
"—" means the source has not published that year yet.</p>
<h2>By fiscal year, FY1940 to FY{modern[0] if modern else ''}</h2>
<table><tr><th>Fiscal year</th><th>Total debt (Treasury)</th><th>Record date</th><th>Gross debt % GDP (OMB)</th><th>Held by public % GDP (OMB)</th><th>Deficit % GDP (OMB)</th></tr>{''.join(rows)}</table>
<details><summary>Earlier years, FY{older[0] if older else ''} back to FY{older[-1] if older else ''} (Treasury totals only)</summary>
<table><tr><th>Fiscal year</th><th>Total debt</th><th>Record date</th></tr>{orows}</table></details>
<p>The same totals at the start and end of each term are on <a href="../national-debt-by-president/">national debt by president</a>.
Debt divided by Census population, including a by-year table, is on <a href="../national-debt-per-person/">national debt per person</a>.
The next trillion is the <a href="../41-trillion/">$41 trillion countdown</a>.</p>
<p>Today's figure: {usd0(OFF_V)} at Treasury's {fdate(OFF_D)} close (<a href="../how-much-is-the-national-debt/">details</a>).</p>
{src_links([("Treasury, Historical Debt Outstanding", hdo_url),
            ("OMB Historical Tables (FY2027 Budget)", omb_url)])}"""
    if BY and ly:
        year_faqs = [(
            f"How much was the US national debt at the end of FY{ly}?",
            f"Total public debt outstanding was {usd2(BY[ly][1])} as of {fdate(BY[ly][0])}. "
            f"Source: U.S. Treasury, Historical Debt Outstanding, the record for the end of FY{ly}.",
        )]
        if ly - 1 in BY:
            chg = BY[ly][1] - BY[ly - 1][1]
            verb = "rose" if chg > 0 else "fell" if chg < 0 else "was unchanged by"
            year_faqs.append((
                f"How much did the national debt change in FY{ly}?",
                f"It {verb} {bil(abs(chg))}, from {usd0(BY[ly - 1][1])} as of {fdate(BY[ly - 1][0])} to {usd0(BY[ly][1])} as of {fdate(BY[ly][0])}. "
                f"Source: U.S. Treasury, Historical Debt Outstanding.",
            ))
        if lomb and t71.get(str(lomb)) and t71[str(lomb)][6] is not None:
            missing = f", and has not published a gross-debt ratio for FY{ly} in this table" if lomb < ly else ""
            year_faqs.append((
                "What is the US debt-to-GDP ratio?",
                f"OMB Historical Table 7.1 puts gross federal debt at {t71[str(lomb)][6]:.1f}% of GDP in FY{lomb}{missing}. "
                f"Source: OMB Historical Tables; that gross-debt measure differs slightly from Treasury's total public debt outstanding.",
            ))
        if 2000 in BY and ly != 2000 and BY[2000][1]:
            year_faqs.append((
                "How does the national debt compare with FY2000?",
                f"The FY{ly} total of {usd0(BY[ly][1])} as of {fdate(BY[ly][0])} was {BY[ly][1] / BY[2000][1]:.1f} times the FY2000 total of {usd0(BY[2000][1])} as of {fdate(BY[2000][0])}. "
                f"Source: U.S. Treasury, Historical Debt Outstanding.",
            ))
        year_faqs.append((
            "How much is the national debt right now?",
            f"The latest Debt to the Penny close is {usd2(OFF_V)} as of {fdate(OFF_D)}. "
            f"Source: U.S. Treasury, Debt to the Penny; that close is after the FY{ly} year-end figure on this page.",
        ))
        if peak and len(year_faqs) < 6:
            year_faqs.append((
                "When was US debt-to-GDP highest in this table?",
                f"Gross federal debt peaked at {peak[0]:.1f}% of GDP in FY{peak[1]}. Source: OMB Historical Table 7.1.",
            ))
        _year_plain, _year_html = quotable.asof_pair(
            f"US federal debt at the end of FY{ly} is {tril(BY[ly][1])}", fdate(BY[ly][0]),
            [("U.S. Treasury, Historical Debt Outstanding", hdo_url)])
        _year_hero = (f'<div class="hero lead" id="lead"><div class="k">Official · {html.escape(fdate(BY[ly][0]))} · end of FY{ly}</div>'
                      f'<div class="big num">{usd2(BY[ly][1])}</div>'
                      f'<div class="sub">Treasury Historical Debt Outstanding. This figure does not tick.</div></div>')
        answer_page("national-debt-by-year",
                    f"US National Debt by Year: Totals and Debt-to-GDP, FY{min(BY)} to FY{ly}",
                    f"US national debt by fiscal year from Treasury: {tril(BY[ly][1])} as of {fdate(BY[ly][0])}, the end of FY{ly}. Debt-to-GDP and deficit-to-GDP by year from OMB Historical Tables, FY1940 on.",
                    _year_plain, body, faqs=year_faqs, hero=_year_hero,
                    h1_html=f'<h1 class="quote asof">{_year_html}</h1>',
                    ld=dataset_ld("US national debt by fiscal year", "Total public debt outstanding at each fiscal year end (Treasury Historical Debt Outstanding) with gross federal debt, debt held by the public and the deficit as a share of GDP (OMB Historical Tables 7.1 and 1.2).",
                                  f"{SITE}/national-debt-by-year/", based=[hdo_url, omb_url],
                                  temporal=f"{min(BY)}/{ly}",
                                  source=("U.S. Department of the Treasury, Fiscal Data", "https://fiscaldata.treasury.gov/", "U.S. Treasury, Historical Debt Outstanding")) + faq_ld(year_faqs))

    # 4) Old $41 trillion URL. The live page is /41-trillion/. GitHub Pages has no HTTP 301,
    # so this is the same refresh the world-clock redirects use: canonical, noindex, meta refresh.
    redir = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>When Will the US Debt Hit $41 Trillion?</title>
<link rel="canonical" href="{SITE}/41-trillion/"><meta name="robots" content="noindex">
<meta http-equiv="refresh" content="0; url=../41-trillion/">
<script>location.replace("../41-trillion/")</script></head>
<body><p>This page has moved to the <a href="../41-trillion/">$41 trillion countdown</a>.</p></body></html>
"""
    os.makedirs(f"{R}/when-will-debt-hit-41-trillion", exist_ok=True)
    open(f"{R}/when-will-debt-hit-41-trillion/index.html", "w").write(redir)

    import debt_limit_page
    debt_limit_page.build({
        "R": R, "SITE": SITE, "T": T, "M": M, "answer_page": answer_page, "faq_ld": faq_ld, "dataset_ld": dataset_ld,
        "fdate": fdate, "usd0": usd0, "usd2": usd2, "bil": bil, "OFF_V": OFF_V, "OFF_D": OFF_D,
        "quotable": quotable, "DTP": DTP_URL,
    })

# ---------------------------------------------------------------- 5) Methodology and accuracy (/methodology/)
# Dated snapshot of two other debt clocks, read in a browser on Oct 27, 2026 (values verified by hand that day; not updated automatically).
# Compared with Treasury's latest published record at that moment (Oct 26, 2026 close, $40,528,358,939,415.85).
SNAP = {"when": "Oct 27, 2026, 5:04 PM CT", "treasury_date": "2026-10-26", "treasury": 40528358939415.85,
        "rows": [("Every Debt Clock (this site), live projection", 40533338546720.16, "A projection from Treasury's Oct 26 close at the 90-day trend; calculated for 5:04:55 PM CT."),
                 ("us-debt-clock.com", 40372855520155, 'Read on the page at 5:04 PM CT. The page labels its latest Treasury record "August 20, 2026".'),
                 ("usdebtclock.org", 40455752046870, "Ticking counter read at 5:04 PM CT. The site does not say which Treasury date it starts from.")]}
if OFF_V:
    import csv as _csv
    bt_rows = []
    try:
        _all = [r for r in _csv.DictReader(open(f"{R}/data/validation_log.csv")) if r["ticker"] == "debt_total" and r["mode"] == "backtest" and r.get("error_pct") not in (None, "")]
        _last = max(r["run_iso"] for r in _all); bt_rows = sorted((r for r in _all if r["run_iso"] == _last), key=lambda r: r["to"], reverse=True)
    except Exception: bt_rows = []
    bt_html = ""
    if bt_rows:
        errs = [float(r["error_pct"]) for r in bt_rows]
        bt_html = (f"<p>Each row projects the debt from the previous business day's Treasury close with the 90-day trend, then compares it with the actual next close. "
                   f"Over the last {len(errs)} business days the average absolute error was <b>{sum(abs(e) for e in errs)/len(errs):.3f}%</b> and the largest was <b>{max(abs(e) for e in errs):.3f}%</b> "
                   f"(about {bil(max(abs(e) for e in errs) / 100 * OFF_V)} at today's level).</p>"
                   '<table><tr><th>Projected for</th><th>Projection from prior close</th><th>Treasury actual</th><th>Difference</th></tr>'
                   + "".join(f'<tr><td>{fdate(r["to"])}</td><td class="num">{usd0(float(r["projected"]))}</td><td class="num">{usd0(float(r["official"]))}</td><td class="num">{float(r["error_pct"]):+.3f}%</td></tr>' for r in bt_rows[:10]) + "</table>")
    td_ = T["debt_total"]; fd_ = M.get("debt_fetched_epoch")
    snap_rows = "".join(f'<tr><td>{html.escape(n)}</td><td class="num">{usd0(v)}</td><td class="num">{"+" if v - SNAP["treasury"] >= 0 else "−"}{bil(abs(v - SNAP["treasury"]))} ({(v - SNAP["treasury"]) / SNAP["treasury"] * 100:+.2f}%)</td><td>{html.escape(note)}</td></tr>' for n, v, note in SNAP["rows"])
    body = f"""<p class="k">Where every number comes from, how often it changes, and how close it is to Treasury</p>
<p><b>Short version.</b> The national debt figure on this site starts from Treasury's official <i>Debt to the Penny</i> number for the latest business day, then ticks forward at the recent official pace until Treasury publishes the next day. Every other figure follows the same pattern from its own official source. Official figures are read from the cited source, not typed in by hand (a few reference inputs such as the household and tax-return counts are entered from their cited publications), and anything projected or modeled is labelled as such.</p>
<h2>Where each number comes from</h2>
<table><tr><th>Figure</th><th>Official source</th><th>How it is used</th></tr>
<tr><td>National debt (total, public, intragovernmental)</td><td><a href="{DTP_URL}" rel="noopener">Treasury, Debt to the Penny</a></td><td>Latest close of business is the starting point; ticks at the 90-day trend until the next close.</td></tr>
<tr><td>Debt subject to the limit, statutory limit</td><td><a href="{SRC_DSL[1]}" rel="noopener">Treasury, Daily Treasury Statement, Table III-C</a></td><td>Same method; headroom is the limit minus debt subject to the limit.</td></tr>
<tr><td>Federal spending, revenue, deficit (fiscal year to date)</td><td>Treasury Monthly Treasury Statement (MTS) and Daily Treasury Statement (DTS)</td><td>Anchored to the latest MTS; days after it are added from DTS cash figures converted to budget basis with last year's MTS÷DTS ratio. Revenue is within roughly ±4% of the official total on that basis, which is why those tiles say so.</td></tr>
<tr><td>Interest on the debt</td><td>Treasury, Average Interest Rates on Treasury Securities, and the MTS/DTS interest lines</td><td>Annual interest = live debt × the average rate on interest-bearing debt. It is a calculation, labelled as such.</td></tr>
<tr><td>Per person</td><td><a href="{SRC_POP[1]}" rel="noopener">Census Bureau, Vintage 2025 population estimates</a></td><td>{POP_OFF:,.0f} residents on {fdate(POP_OFF_DATE)}, grown at the rate Census states for its population clock. Updated once a year when Census publishes a new vintage.</td></tr>
<tr><td>Per household</td><td><a href="{SRC_HH[1]}" rel="noopener">Census Bureau, CPS ASEC 2025, Table HH-1</a></td><td>{HH:,.0f} households, a fixed constant until the next release.</td></tr>
<tr><td>Per tax return filed</td><td><a href="{SRC_IRS[1]}" rel="noopener">IRS Data Book FY2025, Table 1-2</a></td><td>{TAX:,.0f} individual returns filed in FY2025, fixed. It includes zero-liability returns, and a joint return counts once.</td></tr>
<tr><td>GDP, debt-to-GDP</td><td>Bureau of Economic Analysis, NIPA Table 1.1.5 (read through the DBnomics mirror)</td><td>Latest quarter, ticking at the four-quarter trend.</td></tr>
<tr><td>Federal Reserve holdings, M2</td><td>New York Fed SOMA; Federal Reserve H.6</td><td>Latest published value, ticking at the recent trend.</td></tr>
<tr><td>State debt clocks</td><td>Census Bureau, Annual Survey of State and Local Government Finances</td><td>Annual and about two years old when published; see each <a href="../states/">state page</a> for its method.</td></tr>
<tr><td>World Debt Clock</td><td>National general-government releases, Eurostat Maastricht debt, World Bank/IMF QPSD general government, and the IMF World Economic Outlook (GGXWDG_NGDP times NGDPD)</td><td>One general-government gross stock per economy. A central or federal series is shown on the country page and is not added. See <a href="../world/">/world/</a>.</td></tr></table>
<h2>Record dates and when Treasury publishes</h2>
<p>Debt to the Penny gives the debt at the <i>close of business</i> on each business day. Each record is published on the next business day, usually in the afternoon (around 3 PM Central in recent weeks): Monday's record appears Tuesday, and Friday's appears Monday. Weekends and federal holidays have no record of their own. The latest record Treasury had published when this page was built is <b>{fdate(OFF_D)}: {usd2(OFF_V)}</b>. Daily changes are lumpy: the debt steps up on days when auctions settle and moves down when securities held by trust funds mature.</p>
<h2>How the live ticker works</h2>
<p>For every ticking figure: <code>value(now) = base + rate × (now − t0)</code>. The base is the latest official figure, t0 is the end of its record date (11:59:59 PM Eastern), and the rate is a least-squares fit to the last 90 days of Treasury's daily records (currently {bil(rate_day)} a day for the national debt). The browser recomputes this every animation frame, so the digits move smoothly between official releases. When Treasury publishes a new record the base and t0 reset to it, so a projection error never accumulates for more than about a day. If the debt reaches the statutory limit, the clock stops projecting growth and holds at the official figure. Every ticker has a "Show the math" panel with its base, t0, rate and sources.</p>
<h2>Update cadence</h2><ul>
<li>Every day at 6:30 AM Central (5:30 AM in winter): full recalibration from Census, BEA, the Monthly Treasury Statement, OMB and the other sources.</li>
<li>Weekdays, every 15 minutes from 2:00 to 4:00 PM Central, plus a backup check at 3:30 PM Central: the site fetches and republishes only when Treasury has posted a newer Debt to the Penny record, so the new figure reaches the site soon after Treasury publishes it.</li>
<li>Weekdays at 4:45 PM Central (3:45 PM in winter): a full end-of-day refresh.</li>
<li>The schedule runs on GitHub Actions, which can start scheduled jobs a few minutes late. This page and the other pages are rebuilt on every refresh. This one was built {STAMP} from data fetched {gen_ct.strftime('%b %-d, %Y %-I:%M %p')} CT.</li></ul>
<h2>Accuracy</h2>
<p><b>The official figure.</b> On the record date our starting figure is Treasury's number to the penny: the latest record is {fdate(OFF_D)}, {usd2(OFF_V)}, and the clock's base is {usd2(td_.get("base"))}. The live figure between records is a projection and is labelled one. It will differ slightly from the next Treasury figure; the table shows by how much.</p>
{bt_html}
<p>Each day's check against Treasury is in <a href="../data/validation_log.csv">data/validation_log.csv</a> (the same file is in the <a href="https://github.com/hypergamedoteth/everydebtclock" rel="noopener">repository</a>), with the threshold it was judged against. If a check exceeds its threshold, the clock shows a warning badge and the site's automated run is marked failed. Thresholds: 0.25% for the national debt, 0.5% for intragovernmental debt, 3% for revenue and spending, 10% for the fiscal-year-to-date deficit (a difference of two re-based figures, so it moves more day to day), 5% for most monthly figures.</p>
<h3>How other debt clocks compared on {SNAP["when"]}</h3>
<p>For context, this is what two other US debt clocks showed when we read them on {SNAP["when"]}, against the latest record Treasury had published at that moment ({fdate(SNAP["treasury_date"])}: {usd0(SNAP["treasury"])}). Treasury had not yet published October 27's close, so each figure is compared with the latest published record. This is a one-time dated snapshot of what those pages displayed, not a live comparison, and those sites may have changed since.</p>
<table><tr><th>Site</th><th>Figure shown</th><th>Versus Treasury's {fdate(SNAP["treasury_date"])} record</th><th>Note</th></tr>{snap_rows}</table>
<p>We are an independent site and are not affiliated with any of the sites listed or with the U.S. government.</p>
<h2>What this page does not claim</h2>
<ul><li>Projected figures are estimates between official releases. Fiscal-year-to-date revenue, spending and the deficit are estimates on a budget basis until the next MTS. On state pages and on world country rows, the headline is the official stock as of its date. A ticking number on an annual, quarterly, monthly, or IMF series is labelled a projection.</li>
<li>Per-person and per-household figures divide by population or household counts that Census publishes once a year, so they use different dates than the debt figure.</li>
<li>Nothing here is financial advice.</li></ul>
{src_links([SRC_DTP, SRC_DSL, SRC_POP, SRC_HH, SRC_IRS, ("Census, State and Local Government Finances", "https://www.census.gov/data/datasets/2024/econ/local/public-use-datasets.html")])}"""
    _ld = {"@context": "https://schema.org", "@type": "TechArticle", "headline": "Every Debt Clock methodology and accuracy", "url": f"{SITE}/methodology/",
           "description": "Where each number on Every Debt Clock comes from, how the live ticker is calculated, how often it updates, and how it compares with Treasury.",
           "dateModified": M["generated_iso"], "inLanguage": "en", "isAccessibleForFree": True,
           "author": {"@type": "Organization", "name": "Every Debt Clock", "url": SITE + "/"}, "publisher": {"@type": "Organization", "name": "Every Debt Clock", "url": SITE + "/"},
           "about": {"@type": "Thing", "name": "US national debt"}}
    answer_page("methodology", "Methodology and Accuracy: Where Every Number Comes From | Every Debt Clock",
                f"How Every Debt Clock calculates the US national debt: Treasury Debt to the Penny, record dates, the live ticker, update times, and a dated check against Treasury's {fdate(OFF_D)} figure.",
                "Methodology and accuracy", body, ld='<script type="application/ld+json">' + json.dumps(_ld).replace("</", "<\\/") + "</script>", og_img="og/home.png")

# ---------------------------------------------------------------- milestone, president, per-person, and interest pages
PRES_URLS = []
if OFF_V:
    import importlib.util
    _spec = importlib.util.spec_from_file_location("debtclock_series", f"{R}/pipeline/series.py")
    _series = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_series)
    topic_ctx = {
        "R": R, "SITE": SITE, "NOW": NOW, "STAMP": STAMP, "T": T, "M": M, "val": val,
        "fdate": fdate, "usd0": usd0, "usd2": usd2, "bil": bil, "tril": tril,
        "OFF_D": OFF_D, "OFF_V": OFF_V, "POP_OFF": POP_OFF, "POP_OFF_DATE": POP_OFF_DATE,
        "HH": HH, "TAX": TAX, "HH_URL": SRC_HH[1], "IRS_URL": SRC_IRS[1], "DTP": DTP_URL,
        "ANSWERS": ANSWERS, "places": PLACES_LIVE, "calc": places_build.calc, "gdp": places_build.GDP_BY_SLUG,
        "with_analytics": with_analytics, "dataset_ld": dataset_ld, "faq_ld": faq_ld, "src": src_links,
        "terms": _series.TERMS, "hdo": M.get("debt_by_fy") or [],
    }
    import press_build
    press_build.build(topic_ctx)
    import topics_build
    PRES_URLS = topics_build.build(topic_ctx) or []

# ---------------------------------------------------------------- place pages: /states/<slug>/, /countries/<slug>/ from places/*.json
import places_build
PLACE_URLS = places_build.build(R, SITE, with_analytics, PAGE_CSS, ANS_CSS, og, STAMP, NOW)
if WORLD:
    PLACE_URLS += world_build.build(R, SITE, with_analytics, og, STAMP, NOW, PLACES_LIVE, WORLD, M.get("generated_iso"))
else:
    world_build.write_us_redirect(R, SITE)
import weo_build
PLACE_URLS += weo_build.build(R, SITE, with_analytics, og, STAMP, NOW, PLACES_LIVE)
PLACE_URLS += wealth_build.build(R, SITE, with_analytics, og, PLACES_LIVE, WEALTH_D, WEALTH_FUNDS) if WEALTH_FUNDS else []

def write_api_index():
    """Directory index for /api/. GitHub Pages 404s a folder that has no index.html."""
    feeds = [
        ("daily.json", "Latest official US total and the one-day, 7-day and 30-day changes."),
        ("daily.txt", "The same US total as one plain-English line."),
        ("places.json", "State and country clocks."),
        ("search.json", "Place names for the on-site search box."),
        ("world.json", "World Debt Clock rows, with the source tier and as-of date."),
        ("world_government_debt.json", "IMF general-government estimate for the same economies."),
        ("wealth.json", "Sovereign wealth fund ranking."),
    ]
    items = "".join(
        f'<li><a href="{name}">{html.escape(name)}</a> — {html.escape(blurb)}</li>'
        for name, blurb in feeds if os.path.exists(f"{R}/api/{name}"))
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Data feeds | Every Debt Clock</title>
<meta name="description" content="JSON and text feeds from Every Debt Clock, plus a link to the CSV downloads.">
<link rel="canonical" href="{SITE}/api/"><meta name="robots" content="noindex">
<meta name="theme-color" content="#07090d"><link rel="apple-touch-icon" href="/apple-touch-icon.png">
<style>html{{overflow-x:clip}}body{{margin:0;background:#07090d;color:#e8edf5;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;line-height:1.5}}
main{{max-width:760px;margin:0 auto;padding:22px 16px 60px}}a{{color:#5aa9ff;overflow-wrap:anywhere}}h1{{font-size:22px}}li{{margin:6px 0}}</style>
</head><body><main>
<a href="/" style="font-weight:800;letter-spacing:.06em;color:#e8edf5;text-decoration:none">EVERY <b style="color:#ff4d5e">DEBT</b> CLOCK</a>
<h1>Data feeds</h1>
<ul>{items}</ul>
<p>CSV downloads and charts are on the <a href="/data/">data page</a>.</p>
</main></body></html>
"""
    os.makedirs(f"{R}/api", exist_ok=True)
    open(f"{R}/api/index.html", "w").write(page)

write_api_index()
import debt_by_year_build
DY_URLS = debt_by_year_build.build(R, SITE, with_analytics, STAMP, M.get("generated_iso") or "")
debt_by_year_build.patch_clocks(R)
import state_per_person_build
import presidents_build
SP_URLS = state_per_person_build.build(R, SITE, with_analytics, STAMP)

# ---------------------------------------------------------------- free data hub (/data/ CSVs, charts). New files only, plus the sitemap and footer links above.
import data_hub
data_hub.build(R, SITE, with_analytics, D, PLACES_LIVE, WORLD)
import monthly_report
REPORT_URLS = monthly_report.build(R, SITE, with_analytics, T["debt_total"])

# ---------------------------------------------------------------- legal pages (/privacy/, /about/, /contact/)
site_chrome.write_legal_pages(R, SITE, with_analytics)
site_chrome.write_advertise_page(R, SITE, with_analytics)

# ---------------------------------------------------------------- your share (/your-share/). Client-side; uses the per-person page's Treasury close ÷ Census population.
# share_build redraws every birth-year card from this run's close and date. The daily refresh runs this file, then deploys your-share/.
import share_build
if OFF_V and POP_OFF:
    share_build.build(R, SITE, with_analytics, STAMP, OFF_D, OFF_V, POP_OFF, POP_OFF_DATE,
                      T["households"], T["population"], M.get("debt_by_fy") or [], M.get("debt_by_fy_source"))

# ---------------------------------------------------------------- facts page (/facts/): headline figures, dates and sources, regenerated with the data
def write_facts():
    td = T.get("debt_total") or {}
    rate = td.get("rate") or 0
    t0 = td.get("t0") or 0
    ig = T.get("interest_gross") or {}
    intr_url = ig.get("source") or "https://fiscaldata.treasury.gov/datasets/interest-expense-debt-outstanding/interest-expense"
    pub, igov = T.get("debt_public") or {}, T.get("debt_intragov") or {}
    subj = T.get("debt_subject_limit") or {}
    rows = []
    def add(label, text):
        rows.append(f"<li><b>{html.escape(label)}.</b> {text}</li>")
    add("US federal debt", f"As of {fdate(OFF_D)}, US federal debt is {tril(OFF_V)} ({usd2(OFF_V)}). Source: <a href=\"{DTP_URL}\" rel=\"noopener\">U.S. Treasury, Debt to the Penny</a>.")
    add("Debt per person", f"US debt per person is {usd2(PP_OFF)} as of {fdate(OFF_D)}, the official total divided by the Census estimate of {POP_OFF:,.0f} residents on {fdate(POP_OFF_DATE)}. Sources: <a href=\"{DTP_URL}\" rel=\"noopener\">U.S. Treasury, Debt to the Penny</a> and <a href=\"{html.escape(SRC_POP[1])}\" rel=\"noopener\">the U.S. Census Bureau</a>.")
    if INTEREST_DAY and ig.get("ttm") and ig.get("as_of"):
        add("Interest per day", f"Treasury's interest-expense dataset totaled {usd0(ig['ttm'])} in the 12 months ending {fdate(ig['as_of'])}, about {bil((ig.get('rate') or 0) * 86400 if ig.get('rate') else ig['ttm'] / 365.25)} a day on an accrual basis. Source: <a href=\"{html.escape(intr_url)}\" rel=\"noopener\">U.S. Treasury, Interest Expense on the Public Debt Outstanding</a>.")
    if pub.get("base") is not None and igov.get("base") is not None:
        add("Held by the public", f"As of {fdate(pub.get('as_of'))}, {usd0(pub['base'])} was held by the public and {usd0(igov['base'])} was intragovernmental. Source: <a href=\"{DTP_URL}\" rel=\"noopener\">U.S. Treasury, Debt to the Penny</a>.")
    if subj.get("base") is not None and (T.get("debt_limit") or {}).get("base"):
        add("Debt limit", f"Debt subject to the statutory limit was {usd0(subj['base'])} as of {fdate(subj.get('as_of'))}, against a limit of {usd0(T['debt_limit']['base'])}. Source: <a href=\"{html.escape(SRC_DSL[1])}\" rel=\"noopener\">U.S. Treasury, Daily Treasury Statement</a>. See <a href=\"../debt-limit/\">the debt limit and X-date</a>.")
    if MILE and MILE.get("when"):
        add(f"${MILE['n']} trillion", html.escape(MILE["quote"]) + f" The pace is the homepage clock, not a Treasury forecast. See <a href=\"../41-trillion/\">the countdown</a>.")
    if WORLD:
        dmin = min(x["as_of"] for x in WORLD["rows"])
        dmax = max(x["as_of"] for x in WORLD["rows"])
        _world_line = html.escape(world_build.lead_claim(WORLD, dt.date.today()))
        add("World government debt", f"{_world_line} Source: national releases, Eurostat, and the <a href=\"https://www.imf.org/external/datamapper/GGXWDG_NGDP@WEO\" rel=\"noopener\">IMF World Economic Outlook</a>. See <a href=\"../world/\">the world debt clock</a>.")
    by = {int(r[0]): (r[1], r[2]) for r in (M.get("debt_by_fy") or [])}
    if by:
        ly = max(by)
        hdo = M.get("debt_by_fy_source") or "https://fiscaldata.treasury.gov/datasets/historical-debt-outstanding/historical-debt-outstanding"
        add(f"End of FY{ly}", f"US federal debt was {usd0(by[ly][1])} ({tril(by[ly][1])}) as of {fdate(by[ly][0])}. Source: <a href=\"{html.escape(hdo)}\" rel=\"noopener\">U.S. Treasury, Historical Debt Outstanding</a>. See <a href=\"../national-debt-by-year/\">national debt by year</a>.")
    facts_ld = dataset_ld(
        "Headline US debt figures",
        f"Official US federal debt and related figures cited by Every Debt Clock, dated to each source's record. Latest Debt to the Penny close {fdate(OFF_D)}: {usd2(OFF_V)}.",
        f"{SITE}/facts/", based=[DTP_URL], temporal=(f"{CLOSES[-1][0]}/{CLOSES[0][0]}" if CLOSES else None))
    tick = ""
    if td.get("status") == "ok" and not td.get("held_at_limit"):
        tick = f"""<script>(function(){{var H=document.getElementById('lead'),v=document.getElementById('hv');if(!H||!v)return;var b=+H.dataset.b,r=+H.dataset.r,t0=+H.dataset.t,nf=new Intl.NumberFormat('en-US',{{maximumFractionDigits:0}});
function usd(x){{return (x<0?'−$':'$')+nf.format(Math.abs(x))}}function f(){{v.textContent=usd(b+r*(Date.now()/1000-t0));requestAnimationFrame(f)}}f()}})();</script>"""
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Debt facts: official figures, dates and sources</title>
<meta name="description" content="As of {fdate(OFF_D)}, US federal debt is {tril(OFF_V)} ({usd2(OFF_V)}), from U.S. Treasury Debt to the Penny. Headline figures with record dates and sources.">
<link rel="canonical" href="{SITE}/facts/">
<meta property="og:title" content="Debt facts: official figures, dates and sources"><meta property="og:description" content="As of {fdate(OFF_D)}, US federal debt is {tril(OFF_V)}, U.S. Treasury Debt to the Penny.">
<meta property="og:url" content="{SITE}/facts/"><meta property="og:image" content="{SITE}/og/home.png">
<link rel="stylesheet" href="../style.css">
<style>
main{{max-width:760px;margin:0 auto;padding:8px 14px 48px}}
main .hero{{overflow:visible}}
main .hero .big{{font-size:clamp(18px,5.6vw,42px);overflow-wrap:anywhere}}
h1.asof{{font-size:15px;font-weight:650;line-height:1.45;margin:8px 2px 14px;color:var(--mut);overflow-wrap:anywhere}}
.facts{{margin:8px 0 18px;padding-left:18px}}.facts li{{margin:8px 0;overflow-wrap:anywhere}}
.faq h3{{font-size:15.5px;margin:14px 0 4px}}
</style>
{facts_ld}
{faq_ld(HOME_FAQS)}
</head><body class="srclead"><main>
<a class="brand" href="../">EVERY <b>DEBT</b> CLOCK</a>
<div class="hero lead" id="lead" data-b="{td.get('base') or OFF_V}" data-r="{rate}" data-t="{t0}">
<div class="k">Live estimate · US national debt</div>
<div class="big num" id="hv">{usd0(OFF_V)}</div>
<div class="sub"><span>Starts at the official {html.escape(fdate(OFF_D))} close. The line under the clock is that close, not the live tick.</span></div>
</div>
<h1 class="quote asof">{LEAD_HTML}</h1>
<p class="answer">Every figure below is the official published number, with its record date and source. The clock above is the only number that moves.</p>
<ul class="facts">{''.join(rows)}</ul>
<p>State clocks, country clocks and the world total name their own sources on those pages. The stable JSON feed is <a href="../api/daily.json">/api/daily.json</a>.</p>
{faq_section(HOME_FAQS, [
    ("Treasury, Debt to the Penny", DTP_URL),
    ("Census Bureau, Vintage 2025 national population estimates", SRC_POP[1]),
    ("Treasury, Interest Expense on the Public Debt Outstanding", intr_url),
])}
</main>
<footer class="site-foot">Every Debt Clock · <a href="../">US clock</a> · <a href="../national-debt-per-person/">Per person</a> · <a href="../national-debt-by-year/">By year</a> · <a href="../world/">World</a> · <a href="../methodology/">Methodology</a></footer>
{tick}</body></html>"""
    os.makedirs(f"{R}/facts", exist_ok=True)
    open(f"{R}/facts/index.html", "w").write(with_analytics(page))

if OFF_V:
    write_facts()

# Short aliases people already request. GitHub Pages cannot send a 301.
def write_alias(folder, canon, refresh, title, blurb):
    os.makedirs(f"{R}/{folder}", exist_ok=True)
    open(f"{R}/{folder}/index.html", "w").write(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="canonical" href="{canon}"><meta name="robots" content="noindex">
<meta http-equiv="refresh" content="0; url={refresh}">
<script>location.replace("{refresh}")</script></head>
<body><p>{blurb} <a href="{refresh}">{html.escape(refresh)}</a>.</p></body></html>
""")
write_alias("texas", f"{SITE}/states/texas/", "/states/texas/", "Texas debt clock", "This page moved to the Texas debt clock.")
write_alias("uk", f"{SITE}/countries/united-kingdom/", "/countries/united-kingdom/", "UK debt clock", "This page moved to the United Kingdom debt clock.")

# ---------------------------------------------------------------- sitemap + robots
# /embed/ is indexable. Per-clock pages under /embed/ are noindex and stay out of this list.
# lastmod is each page's data date, not the time this build ran.
DATES = freshness.collect(R, OFF_D, WORLD)
urls = ([(f"{SITE}/", "1.0", "hourly"), (f"{SITE}/embed/", "0.5", "weekly")] + data_hub.sitemap_entries(R, SITE) + [(f"{SITE}/{a}/", "0.9", "daily") for a, _ in ANSWERS if os.path.exists(f"{R}/{a}/index.html")] +
        [(u, "0.8", "weekly") for u in PLACE_URLS] +
        [(u, "0.8", "weekly") for u in DY_URLS] +
        [(u, "0.8", "weekly") for u in PRES_URLS] +
        [(u, "0.8", "weekly") for u in SP_URLS] +
        [(u, "0.8", "monthly") for u in REPORT_URLS] +
        site_chrome.sitemap_entries(SITE))
def _lastmod(url):
    path = url[len(SITE):] if url.startswith(SITE) else url
    found = freshness.lookup(DATES, path)
    if not found:
        raise SystemExit(f"no data date for {url}")
    return found
_sitemap_xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
    "".join(f"<url><loc>{u}</loc><lastmod>{_lastmod(u)}</lastmod><changefreq>{c}</changefreq><priority>{p}</priority></url>\n" for u, p, c in urls) + "</urlset>\n")
for _banned in ("/t/", "/texas/", "/uk/", "/world-government-debt/", "/global-debt-clock/", "/countries/united-states/"):
    if f"{SITE}{_banned}" in _sitemap_xml:
        raise SystemExit(f"sitemap lists {_banned}")
open(f"{R}/sitemap.xml", "w").write(_sitemap_xml)
AI_BOTS = ("GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-SearchBot", "Claude-User",
           "PerplexityBot", "Google-Extended", "Applebot", "Applebot-Extended", "Bingbot")
robots = "".join(f"User-agent: {b}\nAllow: /\n\n" for b in AI_BOTS)
robots += f"User-agent: *\nAllow: /\nDisallow: /cache/\nDisallow: /pipeline/\nDisallow: /widget.html\n\nSitemap: {SITE}/sitemap.xml\n"
open(f"{R}/robots.txt", "w").write(robots)
open(f"{R}/llms.txt", "w").write("\n".join([
    "# Every Debt Clock",
    f"{SITE}/",
    "",
    f"Live US, state, country and wealth-fund clocks built from official figures. The US national debt was {usd2(OFF_V)} ({tril(OFF_V)}) as of {fdate(OFF_D)} (Treasury, Debt to the Penny).",
    "",
    "US Debt to the Penny is re-based every business day after the U.S. Treasury posts a new record. State figures follow the Census annual survey. Country and world figures update when their sources publish. This file and /facts/ are regenerated on each refresh.",
    "",
    "## Answers",
    "These sentences are computed at build time from the same official figures as the pages. Projected figures say so.",
    f"- How much is the US national debt right now? {usd2(OFF_V)} ({tril(OFF_V)}) as of {fdate(OFF_D)}. Source: Treasury Debt to the Penny. https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/debt-to-the-penny",
    f"- How much is the national debt per person? {usd2(PP_OFF)} as of {fdate(OFF_D)}, the official total divided by the Census estimate of {POP_OFF:,.0f} residents on {fdate(POP_OFF_DATE)}.",
    ("- How much interest does the US pay per day? " + INTEREST_DAY if INTEREST_DAY else "- How much interest does the US pay per day? Not available from the current interest-expense and average-rate inputs."),
    f"- When will the US national debt hit ${MILE['n']} trillion? {MILE['quote']}",
    (f"- World government debt: {world_build.lead_claim(WORLD, dt.date.today())} "
     f"An IMF row's published figure is the end-2025 stock; the end-2026 estimate is the year-end target the clock runs toward, not a December 31 closing balance. See /world/." if WORLD else
     "- World government debt: the world page was not built on this run."),
    "",
    "## Key pages",
    f"- / : US national debt clock. Official total {usd2(OFF_V)} as of {fdate(OFF_D)} (Treasury, Debt to the Penny). The live projection is re-based every business day.",
    f"- /facts/ : Headline figures with the official record date and source for each number. Machine-readable feed: {SITE}/api/daily.json",
    "- /how-much-is-the-national-debt/ : Plain answer and a breakdown of the official total, public vs intragovernmental debt, and the statutory limit.",
    "- /debt-limit/ : X-date forecasts, extraordinary measures, and what a missed X-date would affect. The live limit, headroom, and the countdown to the ceiling are linked from here. They are not repeated.",
    f"- /national-debt-per-person/ : Official total divided by the Census Vintage 2025 population ({usd2(PP_OFF)} per person).",
    "- /your-share/ : One equal share of the official total, the live national debt clock divided by population. No calculator.",
    "- /national-debt-by-year/ : Treasury fiscal-year-end totals and OMB debt-to-GDP ratios, FY1940 to the latest year.",
    "- /41-trillion/ : Live countdown to the next trillion, using the homepage clock's Debt to the Penny base and per-second rate, plus each trillion crossing in that daily series.",
    "- /press/ : Press kit for the $41 trillion crossing. Exact projected time from the homepage 90-day pace, 12-month and 3-year comparisons, and the countdown embed.",
    "- /when-will-debt-hit-41-trillion/ : Redirects to /41-trillion/. GitHub Pages serves this as an HTML refresh with a canonical link, not an HTTP 301.",
    "- /national-debt-by-president/ : Debt at the start and end of each term. Debt to the Penny on or before the date from 1993; Historical Debt Outstanding annual records before that.",
    "- /interest-on-the-national-debt/ : Cash interest paid this fiscal year, MTS net interest by fiscal year, and Treasury's interest-expense dataset by fiscal year.",
    "- /world/ : World Debt Clock. General government gross debt for every IMF economy. A national or Eurostat or QPSD stock is used only when it is general government gross debt; otherwise the row is the IMF World Economic Outlook estimate. Narrower official series are labeled and not added.",
    "- /world-government-debt/ : Redirects to /world/. GitHub Pages serves this as an HTML refresh with a canonical link and noindex, not an HTTP 301.",
    "- /global-debt-clock/ : Redirects to /world/ the same way.",
    "- /countries/united-states/ : Redirects to /. Same canonical, noindex, and refresh. The US clock is the Treasury series, not the IMF row.",
    "- /texas/ : Redirects to /states/texas/ the same way.",
    "- /uk/ : Redirects to /countries/united-kingdom/ the same way.",
    "- /countries/ : National debt clocks by country. Economies with an official source keep that source; the rest are IMF World Economic Outlook estimates.",
    "- /states/ : State and local debt clocks for every US state and Washington, DC, from official Census figures.",
    "- /wealth/ : Sovereign wealth funds ranked by assets and assets per citizen.",
    "- /methodology/ : Sources, how the live ticker is calculated, and how it is checked against Treasury.",
    "- /about/ : Who runs the site (Hypergame LLC), the main data sources, and the update schedule.",
    "- /privacy/ : Privacy policy, including analytics, data downloads, and cookies if ads are shown.",
    "- /contact/ : Email hello@everydebtclock.com.",
    "- /advertise/ : Sponsorship on the US clock and the national-debt-by-year page.",
    "- /data/ : Free CSV and JSON of US debt. us-debt-daily is every Debt to the Penny close since 1993-04-01. us-debt-annual is Historical Debt Outstanding since 1790. Citation: Source: Every Debt Clock (everydebtclock.com), from U.S. Treasury Debt to the Penny.",
    "- /reports/ : Monthly U.S. debt reports from Debt to the Penny. Each completed month states the debt added, the average per calendar day, interest per day when Treasury's interest-expense series has that month, and a labelled projection for the next trillion.",
    "- /embed/ : Free debt clock widget. Paste-in clocks for the US, every state and Washington, DC, every country, and the world. Each one links back to its full page.",
    "",
] + debt_by_year_build.llms_lines(R) + presidents_build.llms_lines(R) + [
    "## Comparisons",
    "- /states/debt-per-person/ : Census state and local debt divided by Census Vintage 2025 population, for every state and the District of Columbia. The debt date and the population date are both named.",
    "",
] + [
    "## Data",
    "US figures come from Treasury Fiscal Data (Debt to the Penny; Daily Treasury Statement Table III-C for debt subject to the limit) and Census Bureau population estimates. State, country and wealth pages name their own official sources. Every projected figure is labelled as a projection.",
    "",
    "## Machine-readable",
    f"- {SITE}/data/us-debt-daily.csv — every Debt to the Penny close since 1993-04-01",
    f"- {SITE}/data/us-debt-daily.json — the same daily series",
    f"- {SITE}/data/us-debt-annual.csv — Historical Debt Outstanding, fiscal years from 1790",
    f"- {SITE}/data/us-debt-annual.json — the same annual series",
    f"- {SITE}/data/ — CSV downloads (debt by year, by president, per person, interest, states, countries) and chart images",
    f"- {SITE}/api/daily.json — latest official US total and daily changes",
    f"- {SITE}/data/data.json — all US tickers, official bases and rates",
    f"- {SITE}/api/places.json — state and country clocks",
    f"- {SITE}/api/world.json — best-source world total, with source tier and as-of date for each economy",
    f"- {SITE}/api/world_government_debt.json — IMF general-government estimate",
    f"- {SITE}/api/wealth.json — wealth-fund ranking",
    f"- {SITE}/sitemap.xml",
    f"- {SITE}/llms.txt",
    "",
]))
# IndexNow verification file: the key is both the filename and the file body.
_idx_key_path = f"{R}/pipeline/indexnow.key"
if os.path.exists(_idx_key_path):
    _idx_key = open(_idx_key_path).read().strip()
    if _idx_key:
        open(f"{R}/{_idx_key}.txt", "w").write(_idx_key + "\n")

# ---------------------------------------------------------------- embeddable clocks (after pages exist; patches the US, state, DC, country and world pages)
import embed_build
embed_build.apply(R, SITE, with_analytics, require_pages=True, now=NOW, world=WORLD)

# ---------------------------------------------------------------- asset versions: ?v=<content hash> on every first-party CSS/JS reference
# so a deploy that changes style.css / app.js / core.js is picked up at once instead of after the 4-hour browser/CDN cache.
import hashlib, glob as _glob
AV = {a: hashlib.sha1(open(f"{R}/{a}", "rb").read()).hexdigest()[:10] for a in ("style.css", "app.js", "core.js", "cross41.js") if os.path.exists(f"{R}/{a}")}
_vre = re.compile(r'((?:href|src)=")((?:\.\./)*)(' + "|".join(re.escape(a) for a in AV) + r')(?:\?v=[^"]*)?"')
# Per-clock files under embed/ are self-contained (no site CSS, no favicon request). Only the directory is versioned.
_pages = ([f"{R}/{f}" for f in ("index.html", "404.html", "privacy.html", "widget.html", "embed/index.html")] + _glob.glob(f"{R}/t/*.html")
          + [f for d in ["states", "countries", "world", "world-government-debt", "global-debt-clock", "wealth", "about", "contact", "privacy", "advertise", "facts"] + [a for a, _ in ANSWERS] for f in _glob.glob(f"{R}/{d}/**/*.html", recursive=True)])
# Every page gets real icon files (favicon.ico, a 32px PNG and the SVG), replacing the old inline data-URI icon. Made by pipeline/make_favicon.py.
ICON_LINKS = '<link rel="icon" href="/favicon.ico" sizes="16x16 32x32 48x48"><link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png"><link rel="icon" type="image/svg+xml" href="/icon.svg">'
_icon_re = re.compile(r'<link rel="icon"[^>]*>')
for f in _pages:
    if not os.path.exists(f): continue
    s_ = open(f).read(); n_ = _vre.sub(lambda m: f'{m.group(1)}{m.group(2)}{m.group(3)}?v={AV[m.group(3)]}"', s_)
    if "/favicon.ico" not in n_ and "</head>" in n_: n_ = _icon_re.sub("", n_).replace("</head>", ICON_LINKS + "</head>", 1)
    if n_ != s_: open(f, "w").write(n_)
print("asset versions:", AV)

site_chrome.finalize(R)
freshness.stamp_tree(R, SITE, DATES)
freshness.write_urls(os.path.join(R, "pipeline", "indexnow-urls.txt"), freshness.changed_urls(SITE, DATES, OLD_LASTMOD, urls))
freshness.check(R, SITE, DATES, urls, OFF_D)
import country_profile
country_profile.assert_country_pages_differ(R)
import state_facts
state_facts.assert_state_pages_differ(R)
debt_by_year_build.check(R, SITE)
presidents_build.check(R, SITE)
state_per_person_build.check(R, SITE)

# ---------------------------------------------------------------- standalone (read index.html back so the embed control is in the offline copy)
css, js = open(f"{R}/style.css").read(), open(f"{R}/app.js").read()
idx_ = re.sub(r'(href|src)="(style\.css|app\.js)\?v=[^"]*"', r'\1="\2"', open(f"{R}/index.html").read())
single = (idx_.replace('<link rel="stylesheet" href="style.css">', f"<style>{css}</style>")
             .replace("<!--DATA-->", "<script>window.DEBTCLOCK_DATA=" + json.dumps(D, separators=(",", ":")).replace("</", "<\\/") + ";</script>")
             .replace('<script src="app.js"></script>', f"<script>{js}</script>"))
os.makedirs(f"{R}/dist", exist_ok=True)
open(f"{R}/dist/debtclock-standalone.html", "w").write(single)
print(f"standalone: {len(single)//1024} KB; share pages: {len(urls)-1}; og images: {len(os.listdir(R+'/og'))}; site={SITE}")

def check_clock_first():
    """Pages with a live clock must lead with that clock, before the heading and the summary."""
    from html.parser import HTMLParser

    class First(HTMLParser):
        def __init__(self, share):
            super().__init__(convert_charrefs=True)
            self.share = share
            self.in_main = 0
            self.skip = 0
            self.first = None

        def handle_starttag(self, tag, attrs):
            if self.first:
                return
            a = {k: (v or "") for k, v in attrs}
            if tag == "main":
                self.in_main += 1
                return
            if not self.in_main:
                return
            if self.skip:
                self.skip += 1
                return
            cls = a.get("class", "")
            ident = a.get("id", "")
            classes = cls.split()
            if tag in ("script", "style", "noscript", "header", "nav", "dialog"):
                self.skip = 1
                return
            if ident == "cross41" or "hidden" in a:
                self.skip = 1
                return
            if tag == "a" and ("brand" in classes or "navembed" in classes):
                self.skip = 1
                return
            if tag == "div" and (ident == "app" or "ssr" in classes):
                return
            clock = ("hero" in classes and "lead" in classes) or ident == "share-num" or (self.share and tag == "section" and "result" in classes)
            if clock:
                self.first = "clock"
                return
            if tag in ("h1", "h2", "h3", "section", "form", "table", "p", "ul", "ol", "figure", "article") or (tag == "div" and classes):
                self.first = tag + ("." + cls if cls else "")

        def handle_endtag(self, tag):
            if self.skip:
                self.skip -= 1
                return
            if tag == "main" and self.in_main:
                self.in_main -= 1

    samples = [
        ('<main><div id="cross41" class="banner" hidden></div><div class="ssr"><div class="hero lead"></div><p class="official"></p><h1>As of</h1></div></main>', True),
        ('<main><a class="brand" href="/">x</a><a class="navembed" href="/e">Embed</a><div class="hero lead"></div><h1>Name</h1></main>', True),
        ('<main><a class="brand">x</a><section class="result" id="share-clock"><p class="big" id="share-num">$1</p></section><h1>Share</h1></main>', True),
        ('<main><h1>As of</h1><div class="hero lead"></div></main>', False),
        ('<main><section class="intro"><h1>As of</h1></section><div class="hero lead"></div></main>', False),
    ]
    for html, expect in samples:
        parser = First('id="share-num"' in html)
        parser.feed(html)
        if (parser.first == "clock") != expect:
            raise SystemExit(f"clock-order self-test failed: {html[:80]}")

    skip = {".git", "cache", "pipeline", "__pycache__", "embed"}
    bad = []
    for root, dirs, files in os.walk(R):
        dirs[:] = [d for d in dirs if d not in skip and not d.startswith(".")]
        for fn in files:
            if not fn.endswith(".html"):
                continue
            path = os.path.join(root, fn)
            text = open(path, encoding="utf-8", errors="replace").read()
            if 'class="hero lead"' not in text and 'id="share-num"' not in text:
                continue
            parser = First('id="share-num"' in text)
            parser.feed(text)
            if parser.first != "clock":
                bad.append(f"{os.path.relpath(path, R)}: first content is {parser.first or 'missing'}")
    if bad:
        raise SystemExit("live clock is not the first content element:\n" + "\n".join(bad[:20]))
    print(f"clock order ok")

def check_quotable():
    """The pages answer engines quote must be static HTML, with a dated answer and 3-6 FAQs."""
    bots = ("GPTBot", "OAI-SearchBot", "ChatGPT-User", "PerplexityBot", "Google-Extended", "ClaudeBot", "Applebot", "Bingbot")
    robots_txt = open(f"{R}/robots.txt").read()
    for b in bots:
        if f"User-agent: {b}\nAllow: /" not in robots_txt:
            raise SystemExit(f"robots.txt does not allow {b}")
    llms = open(f"{R}/llms.txt").read()
    for bit in ("## Answers", "/world/", "/national-debt-by-year/", "/41-trillion/", "/national-debt-by-president/",
                "/national-debt-per-person/", "/interest-on-the-national-debt/", "/data/", "Debt to the Penny"):
        if bit not in llms:
            raise SystemExit(f"llms.txt missing {bit}")
    pages = {
        f"{R}/index.html": "homepage",
        f"{R}/world/index.html": "world",
        f"{R}/national-debt-by-year/index.html": "national debt by year",
        f"{R}/41-trillion/index.html": "41 trillion",
        f"{R}/national-debt-by-president/index.html": "debt by president",
        f"{R}/national-debt-per-person/index.html": "per person",
        f"{R}/interest-on-the-national-debt/index.html": "interest",
        f"{R}/debt-limit/index.html": "debt limit",
    }
    for sample in ("states/california/debt-by-year/index.html", "countries/japan/debt-by-year/index.html"):
        if os.path.exists(f"{R}/{sample}"):
            pages[f"{R}/{sample}"] = sample
    for path, name in pages.items():
        if not os.path.exists(path):
            raise SystemExit(f"{name}: page was not built")
        text = open(path).read()
        if 'class="answer"' not in text:
            raise SystemExit(f"{name}: missing the answer line")
        if "as of" not in text.lower():
            raise SystemExit(f"{name}: no as-of date")
        if "FAQPage" not in text or "dateModified" not in text or 'id="faq"' not in text:
            raise SystemExit(f"{name}: missing FAQPage, dateModified, or a visible FAQ")
        nq = text.count('"@type": "Question"')
        visible = text.split('id="faq"', 1)[1].split("</section>", 1)[0]
        if not 3 <= nq <= 6 or visible.count("<h3>") != nq:
            raise SystemExit(f"{name}: {nq} JSON-LD questions, {visible.count('<h3>')} visible")
    home = open(f"{R}/index.html").read()
    if f'<div class="big num">{usd2(OFF_V)}</div>' not in home:
        raise SystemExit("homepage hero total changed")
    official_pp = usd2(PP_OFF)
    person = open(f"{R}/national-debt-per-person/index.html").read()
    facts = open(f"{R}/facts/index.html").read()
    for label, blob in (("homepage", home), ("per person", person), ("facts", facts), ("llms.txt", llms)):
        if official_pp not in blob:
            raise SystemExit(f"{label} is missing the official per-person figure {official_pp}")
    proj_pp = usd2(val("debt_total") / val("population")) if val("debt_total") and val("population") else None
    if proj_pp and proj_pp != official_pp:
        for label, blob in (("homepage FAQ", home.split('id="faq"', 1)[-1].split("</section>", 1)[0]),
                            ("per-person answer", person.split("<h1", 1)[-1].split("</h1>", 1)[0]),
                            ("facts", facts), ("llms.txt", llms)):
            if proj_pp in blob:
                raise SystemExit(f"{label} quotes the live per-person projection {proj_pp}")
    world_page = open(f"{R}/world/index.html").read()
    world_h1 = re.search(r"<h1\b[^>]*>(.*?)</h1>", world_page, re.S | re.I)
    world_lead = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", world_h1.group(1) if world_h1 else "")).strip()
    if ("add up to" not in world_lead or "IMF figures for end-2025" not in world_lead
            or "The live clock projects each country forward from its figure." not in world_lead
            or "projected toward" in world_lead
            or re.search(r"As of .*(December|Dec) 31, 2026", world_lead)):
        raise SystemExit("world answer line mixes the stock sum with the projection: " + world_lead[:300])
    imf_sample = f"{R}/countries/burkina-faso/index.html"
    if os.path.exists(imf_sample):
        sample = open(imf_sample).read()
        sample_h1 = re.search(r"<h1\b[^>]*>(.*?)</h1>", sample, re.S | re.I)
        sample_lead = re.sub(r"<[^>]+>", " ", sample_h1.group(1) if sample_h1 else "")
        if "IMF estimate for 2026" not in sample_lead or "Dec 31, 2026" in sample_lead:
            raise SystemExit("IMF country answer line still uses a future record date: " + sample_lead[:240])
    if " PM CT" in home.split('id="faq"', 1)[-1].split("</section>", 1)[0]:
        raise SystemExit("homepage FAQ bakes a build-time clock timestamp")
    api = json.load(open(f"{R}/api/daily.json"))
    expect = {"schema_version", "as_of", "fetched_at", "treasury_record_date", "total_debt_official",
              "total_debt_projected_now", "change_1d_official", "change_7d_official", "change_30d_official",
              "avg_daily_change_90d", "per_second_rate", "held_at_debt_limit", "per_second_rate_method",
              "clock_daily_change_90d",
              "debt_per_person_official", "census_population_official", "census_population_vintage",
              "census_population_date", "debt_per_person_projected_now", "population_projected_now",
              "debt_per_household_official", "debt_per_household_projected_now", "households_official",
              "households_source", "per_person_basis", "stale", "source_url", "source_api", "site_url"}
    added = {"debt_subject_to_limit", "statutory_limit", "dts_record_date", "debt_limit_headroom",
             "debt_limit_reported_status", "days_to_limit_estimate", "extraordinary_measures"}
    extra = set(api) - expect - added
    missing = expect - set(api)
    if missing or extra or api.get("schema_version") != 2:
        raise SystemExit("api/daily.json format changed: missing " + " ".join(sorted(missing)) + " extra " + " ".join(sorted(extra)))
    if "debt_subject_to_limit" not in api or "statutory_limit" not in api or "dts_record_date" not in api:
        raise SystemExit("api/daily.json is missing the debt-limit fields")
    if api.get("debt_limit_reported_status") == "in_force" and (api.get("statutory_limit") is None or api.get("debt_limit_headroom") is None):
        raise SystemExit("in-force debt limit is missing a ceiling or headroom")
    print("quotable pages ok")

def check_crossing():
    """A page must not contain the $41 trillion crossing claim until Treasury's close is there."""
    import crossing_banner
    if crossing_banner.crossed():
        print("crossing: official close is at the level; claim text is allowed")
        return
    bad = []
    for root, dirs, files in os.walk(R):
        dirs[:] = [d for d in dirs if d not in {".git", "cache", "pipeline", "__pycache__"}]
        for fn in files:
            if not fn.endswith(".html"):
                continue
            path = os.path.join(root, fn)
            text = open(path, encoding="utf-8", errors="replace").read()
            for claim in crossing_banner.CLAIMS:
                if claim in text:
                    bad.append(os.path.relpath(path, R) + ": " + claim)
                    break
    if bad:
        raise SystemExit("crossing-day text is in static HTML before Treasury posts that close:\n" + "\n".join(bad[:12]))
    print("crossing: static HTML does not say $41 trillion has been reached")

check_quotable()
check_crossing()
check_clock_first()
_quote_pages = [
    ("index.html", "home"),
    ("national-debt-by-year/index.html", "national debt by year"),
    ("world/index.html", "world"),
    ("states/index.html", "states"),
    ("states/california/index.html", "California"),
    ("states/texas/index.html", "Texas"),
    ("states/new-york/index.html", "New York"),
    ("countries/japan/index.html", "Japan"),
    ("countries/china/index.html", "China"),
    ("countries/germany/index.html", "Germany"),
    ("countries/india/index.html", "India"),
    ("countries/united-kingdom/index.html", "United Kingdom"),
    ("countries/france/index.html", "France"),
    ("data/index.html", "data"),
    ("reports/index.html", "reports"),
    ("reports/2026-10/index.html", "October 2026"),
]
for rel, name in _quote_pages:
    path = os.path.join(R, rel)
    if not os.path.exists(path):
        raise SystemExit(f"quotable lead missing page: {rel}")
    quotable.check_page(open(path, encoding="utf-8").read(), name)
print(f"quotable leads ok ({len(_quote_pages)} pages)")

