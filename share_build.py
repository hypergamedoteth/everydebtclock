#!/usr/bin/env python3
"""Your share of the national debt (/your-share/).

Per person = latest official total public debt / Census resident population.
That is the official figure on the per-person page, not the live projection.

Birth year = Treasury Historical Debt Outstanding at that fiscal year end.
Growth = latest official total / that fiscal-year-end total.
A year missing from the series is left missing. Population is used for a
birth year only when the Census July 1 count is in cache/history_pages.json.

State per person = sum of the state's official component totals / its Census
population, the same official basis as the state page (not the projected clock).

Called from build.py. `python3 share_build.py` rebuilds this page only.
"""
import datetime as dt, hashlib, html, json, os, re, shutil, subprocess
from zoneinfo import ZoneInfo

from urllib.parse import quote
from PIL import Image, ImageDraw, ImageFont
import site_chrome

R = os.path.dirname(os.path.abspath(__file__))
OG_MIN, OG_MAX = 1930, 2026
DTP = "https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/debt-to-the-penny"
FD = "/usr/share/fonts/truetype/dejavu/"


def usd2(x):
    return "—" if x is None else ("−$" if x < 0 else "$") + f"{abs(x):,.2f}"


def usd0(x):
    return "—" if x is None else ("−$" if x < 0 else "$") + f"{abs(x):,.0f}"


def money_exact(n):
    """Whole dollars when the official figure has no cents, otherwise cents."""
    if n is None:
        return "—"
    cents = int(round(abs(n) * 100))
    sign = "−$" if n < 0 else "$"
    whole, frac = divmod(cents, 100)
    body = f"{whole:,}"
    if not frac:
        return sign + body
    return sign + body + f".{frac:02d}"


def times(m):
    if not m or m <= 0:
        return None
    if m >= 100:
        return f"{m:.0f}"
    if m >= 10:
        return f"{m:.1f}"
    return f"{m:.2f}"


def fdate(s):
    if not s or not re.match(r"^\d{4}-\d\d-\d\d$", s):
        return s or ""
    return dt.date.fromisoformat(s).strftime("%b %-d, %Y")


def font(name, size):
    return ImageFont.truetype(FD + name, size)


def fit(draw, text, font_name, max_w, start):
    s = start
    while s > 16:
        f = font(font_name, s)
        if draw.textlength(text, font=f) <= max_w:
            return f
        s -= 2
    return font(font_name, 16)


def _analytics_fn(root):
    raw = os.environ.get("ANALYTICS_HTML")
    if raw is None and os.path.exists(os.path.join(root, "analytics.html")):
        raw = open(os.path.join(root, "analytics.html"), encoding="utf-8").read()
    snippet = (raw or "").strip()

    def apply(page):
        block = f"<!--ANALYTICS-->{snippet}<!--/ANALYTICS-->"
        if "<!--ANALYTICS-->" in page:
            return re.sub(r"<!--ANALYTICS-->.*?<!--/ANALYTICS-->", lambda m: block, page, count=1, flags=re.S)
        return page.replace("</head>", block + "\n</head>", 1)
    return apply


def load_inputs(root, off_d, off_v, pop, pop_date, households, population_ticker, debt_by_fy, debt_by_fy_source):
    hist = json.load(open(os.path.join(root, "cache", "history_pages.json"), encoding="utf-8"))["data"]
    pops = {p["year"]: p for p in hist["population_by_year"]}
    pop_sources = {s["id"]: [s["name"], s["page"]] for s in hist["population_sources"]}
    years = {}
    for fy, date, amt in debt_by_fy:
        pop_row = pops.get(int(fy))
        years[str(int(fy))] = [amt, date, pop_row["population"] if pop_row else None, pop_row["series"] if pop_row else None]
    states = []
    for name in sorted(os.listdir(os.path.join(root, "places"))):
        if not name.endswith(".json"):
            continue
        p = json.load(open(os.path.join(root, "places", name), encoding="utf-8"))
        if p.get("kind") != "state" or p.get("status") != "live":
            continue
        comps = p.get("components") or []
        pop_b = p.get("population") or {}
        if not comps or not pop_b.get("value"):
            continue
        sources = []
        for c in comps:
            pair = [c.get("source_name") or "", c.get("source_url") or ""]
            if pair[0] and pair[1] and pair not in sources:
                sources.append(pair)
        states.append({
            "slug": p["slug"],
            "name": p["name"],
            "demonym": p.get("demonym") or "resident",
            "label": p.get("headline") or p.get("link_label") or "state + local debt",
            "debt": sum(c["value"] for c in comps),
            "debtDate": max(c["as_of"] for c in comps),
            "pop": pop_b["value"],
            "popDate": pop_b.get("as_of") or "",
            "debtSources": sources,
            "popSource": [pop_b.get("source_name") or "", pop_b.get("source_url") or ""],
        })
    states.sort(key=lambda s: s["name"])
    latest_pop = max(pops) if pops else None
    data = {
        "site": "",
        "debt": off_v,
        "debtDate": off_d,
        "population": pop,
        "populationDate": pop_date,
        "debtSource": ["Treasury, Debt to the Penny", DTP],
        "popSource": [population_ticker.get("source_name") or "Census Bureau, Vintage 2025 population estimates",
                      population_ticker.get("source") or "https://www.census.gov/data/tables/time-series/demo/popest/2020s-national-total.html"],
        "histSource": ["Treasury, Historical Debt Outstanding", debt_by_fy_source or "https://fiscaldata.treasury.gov/datasets/historical-debt-outstanding/historical-debt-outstanding"],
        "households": {
            "count": households["base"],
            "asOf": households.get("as_of") or "",
            "sourceName": households.get("source_name") or "Census CPS ASEC, Table HH-1",
            "sourceUrl": households.get("source") or "",
        },
        "years": years,
        "popSources": pop_sources,
        "popLatest": latest_pop,
        "ogMin": OG_MIN,
        "ogMax": OG_MAX,
        "states": states,
    }
    return data


def wordmark(d, y):
    d.text((60, y), "EVERY ", font=font("DejaVuSans-Bold.ttf", 30), fill="#e8edf5")
    x = 60 + d.textlength("EVERY ", font=font("DejaVuSans-Bold.ttf", 30))
    d.text((x, y), "DEBT ", font=font("DejaVuSans-Bold.ttf", 30), fill="#ff4d5e")
    x += d.textlength("DEBT ", font=font("DejaVuSans-Bold.ttf", 30))
    d.text((x, y), "CLOCK", font=font("DejaVuSans-Bold.ttf", 30), fill="#e8edf5")


def render_card(path, title, big, chips, notes, square=False):
    W, H = (1200, 1200) if square else (1200, 630)
    im = Image.new("RGB", (W, H), "#07090d")
    d = ImageDraw.Draw(im)
    for y in range(min(H, 380)):
        c = int(18 * max(0, 1 - y / 380))
        d.line([(0, y), (W, y)], fill=(7 + c // 2, 9 + int(c * 0.8), 13 + c * 2))
    d.rectangle([0, 0, W, 10], fill="#ff4d5e")
    wordmark(d, 48 if not square else 56)
    # A source credit, not a seal. The site is independent of the Treasury.
    badge = "Treasury data"
    bf = font("DejaVuSans-Bold.ttf", 22)
    d.text((W - 60 - d.textlength(badge, font=bf), 52 if not square else 60), badge, font=bf, fill="#9fd0ff")
    title_size = 44 if square else 36
    d.text((60, 130 if not square else 150), title, font=fit(d, title, "DejaVuSans-Bold.ttf", W - 140, title_size), fill="#c9d3e2")
    big_f = fit(d, big, "DejaVuSansMono-Bold.ttf", W - 140, 108 if square else 92)
    d.text((56, 200 if not square else 240), big, font=big_f, fill="#ffffff")
    chip_w = W - 120 if square else 540
    chip_h = 108 if square else 74
    top = 430 if square else 360
    for i, (label, value) in enumerate(chips):
        y = top + i * (chip_h + (16 if square else 12))
        d.rounded_rectangle([60, y, 60 + chip_w, y + chip_h], 12, fill="#121925")
        d.text((82, y + 12), label, font=font("DejaVuSans-Bold.ttf", 16), fill="#8a97ab")
        vf = fit(d, value, "DejaVuSansMono-Bold.ttf", chip_w - 48, 36 if square else 30)
        d.text((82, y + (52 if square else 40)), value, font=vf, fill="#ffffff")
    dfont = font("DejaVuSans.ttf", 26 if square else 22)
    nx = 60 if square else 640
    ny = top + len(chips) * (chip_h + 16) + 28 if square else 368
    for i, line in enumerate(notes):
        d.text((nx, ny + i * (40 if square else 34)), line, font=dfont, fill="#8a97ab")
    d.text((60, H - 56), "everydebtclock.com/your-share/", font=font("DejaVuSans-Bold.ttf", 24), fill="#5aa9ff")
    corner = "Not a bill"
    d.text((W - 60 - d.textlength(corner, font=font("DejaVuSans.ttf", 20)), H - 52), corner, font=font("DejaVuSans.ttf", 20), fill="#5c687a")
    im.save(path, optimize=True)


def growth_clause(multiple):
    t = times(multiple)
    if not t:
        return "a growth multiple is not available for that total."
    n = float(t)
    if n > 1:
        return f"it has grown {t}× since."
    if n < 1:
        return f"it is now {t}× that level."
    return "it is about the same size."


def growth_sentence(share_txt, year, year_debt, multiple):
    s = f"Your share of the US debt: {share_txt}."
    if not year:
        return s
    if year_debt is None:
        return s + f" Historical Debt Outstanding on this site does not include {year}, so the debt that year is not shown. We don't estimate it."
    return s + f" When you were born ({year}) the debt was {money_exact(year_debt)}; {growth_clause(multiple)}"


def page_html(site, root, asset, title, desc, canonical, og_image, og_alt, robots, sentence, year, data, v_css, v_share, v_js, stamp):
    E = html.escape
    options = "".join(
        f'<option value="{E(s["slug"])}">{E(s["name"])}</option>' for s in data["states"]
    )
    hh = data["households"]
    share = data["debt"] / data["population"]
    per_hh = data["debt"] / hh["count"]
    born_attr = f' data-born="{year}"' if year else ""
    robot = f'<meta name="robots" content="{robots}">' if robots else ""
    year_note = ""
    if year and str(year) in data["years"]:
        amt, date, pop, _series = data["years"][str(year)]
        pop_bit = (f" July 1, {year} population in the Census series used here: {pop:,}."
                   if pop else f" No July 1, {year} population is in the Census series used here, so there is no per-person figure for {year}.")
        year_note = (f"<p>Without JavaScript, the line above is the whole result. The {money_exact(amt)} is Treasury's total at the end of fiscal year {year} "
                     f"({fdate(date)}), from Historical Debt Outstanding, not the debt on a birthday. "
                     f"Growth is {money_exact(data['debt'])} ÷ {money_exact(amt)}. {pop_bit}</p>")
    elif year:
        year_note = f"<p>Historical Debt Outstanding on this site does not include {year}. That year is not estimated.</p>"
    src = data
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}">
<link rel="canonical" href="{E(canonical)}">{robot}
<meta property="og:type" content="website"><meta property="og:site_name" content="Every Debt Clock"><meta property="og:url" content="{E(canonical)}">
<meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc)}">
<meta property="og:image" content="{E(og_image)}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{E(og_alt)}">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{E(title)}">
<meta name="twitter:description" content="{E(desc)}"><meta name="twitter:image" content="{E(og_image)}">
<meta name="theme-color" content="#07090d"><link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="stylesheet" href="{root}style.css?v={v_css}"><link rel="stylesheet" href="{asset}share.css?v={v_share}">
<!--ANALYTICS--><!--/ANALYTICS-->
<link rel="icon" href="/favicon.ico" sizes="16x16 32x32 48x48"><link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png"><link rel="icon" type="image/svg+xml" href="/icon.svg">
</head><body class="share"{born_attr}>
<main>
<a class="brand" href="{root}">EVERY <b>DEBT</b> CLOCK</a>
<h1>Your share of the national debt</h1>
<p class="lede">One equal share of the official US total. Enter a birth year to see the debt that year and how many times it has grown. A state, a household size, and an income are optional. The math runs in your browser.</p>
<form id="f" class="panel" action="" method="get" autocomplete="off">
<div class="fields">
<div class="span2"><label for="born">Birth year</label><input id="born" name="born" inputmode="numeric" autocomplete="bday-year" maxlength="4" placeholder="1985" aria-describedby="born-hint"><span class="hint" id="born-hint">The year you were born. The debt that year is the fiscal-year-end total, not your birthday.</span></div>
<div><label for="state">State</label><select id="state" name="state"><option value="">No state</option>{options}</select></div>
<div><label for="hh">Household size</label><input id="hh" name="hh" inputmode="numeric" maxlength="2" placeholder="Optional" aria-describedby="hh-hint"><span class="hint" id="hh-hint">1 to 20. Each person is one share.</span></div>
<div class="span2"><label for="income">Annual income</label><input id="income" name="income" inputmode="decimal" placeholder="Optional" aria-describedby="inc-hint"><span class="hint" id="inc-hint">Compared with the share only. What you type is not a statistic, and it is not saved.</span></div>
</div>
<div class="actions"><button class="primary" type="submit">See your share</button></div>
</form>
<p id="status" class="status">Loading the official figures…</p>
<section class="result" aria-live="polite">
<p class="k">Your share of the US debt</p>
<p class="big" id="share-num">{usd2(share)}</p>
<p class="asof" id="asof">As of Treasury's {fdate(src['debtDate'])} close · Census population {fdate(src['populationDate'])}</p>
<p class="sentence" id="sentence">{E(sentence)}</p>
<noscript>{year_note}<p>Turn on JavaScript for a birth year, a state, or a household. The share above does not need it: it is already the official total divided by the official population.</p></noscript>
<div class="cardwrap"><img id="preview" width="1200" height="630" alt="{E(og_alt)}" src="{E(og_image)}"><canvas id="card" hidden></canvas></div>
<div class="actions">
<button type="button" class="primary" id="native">Share</button>
<button type="button" id="copy">Copy link</button>
<a class="btn" id="x" href="https://x.com/intent/post?text={quote(sentence)}&amp;url={quote(canonical)}">Post on X</a>
<a class="btn" id="dl-wide" download href="{E(og_image)}">Download 1200×630</a>
<a class="btn" id="dl-sq" download href="{E(og_image.replace('.png', '-sq.png') if og_image.endswith('.png') else og_image)}">Download square</a>
</div>
<div class="linkrow"><label for="link" class="hint">Share link</label><input id="link" readonly value="{E(canonical)}" aria-label="Share link"></div>
<div class="details" id="details"></div>
<p class="note">A shared link keeps what you entered in the address, for example /your-share/?born=1985. Birth years {OG_MIN}–{OG_MAX} are shared as /your-share/born/YEAR/ so the preview image is that year’s card. State, household size, and income stay in the query string. This page does not send those inputs anywhere and does not store them. Anyone with the link can read them.</p>
</section>
<section class="math" id="method">
<h2>How your share is calculated</h2>
<p><b>Your share</b> = total public debt outstanding ÷ US resident population = {money_exact(src['debt'])} ÷ {src['population']:,.0f} = <b>{usd2(share)}</b>. The debt is Treasury’s Debt to the Penny close on {fdate(src['debtDate'])}. The population is the Census Bureau’s {src['population']:,.0f} residents on {fdate(src['populationDate'])}. Neither figure is projected. This is the official per-person figure on the <a href="{root}national-debt-per-person/">national debt per person</a> page, not the ticking clock.</p>
<p><b>The year you were born.</b> The debt is Treasury’s <a href="{E(src['histSource'][1])}" rel="noopener">Historical Debt Outstanding</a> total at that fiscal year end (June 30 through FY1976, September 30 after that). Growth = the {fdate(src['debtDate'])} close ÷ that fiscal-year-end total. If the series has no row for the year, the page says so and does not fill one in.</p>
<p><b>Per person that year</b> = the same fiscal-year-end total ÷ the Census July 1 resident population for that calendar year, and only when that July 1 count is already in the series used on the per-person page. The fiscal year end and July 1 are not the same day. A missing population is left missing.</p>
<p><b>A state</b> = that state’s official debt total ÷ its Census resident population. The debt total is the sum of the official components on the state page (state and local, where the page has both), not the projected clock. It is that state’s own debt per resident. It is not a different share of the federal debt. The federal share is the same in every state.</p>
<p><b>Household size</b> = the size you type × your share. Census’s own per-household figure is different: {money_exact(src['debt'])} ÷ {hh['count']:,.0f} households = {usd2(per_hh)} ({E(hh['sourceName'])}, {E(str(hh['asOf']))}).</p>
<p><b>Income</b> = (the household total if you entered a size, otherwise your share) ÷ the annual income you typed. The income is not a published number.</p>
<p>It is a way to scale a very large number, not a bill. The population counts every resident, including children.</p>
<table id="worked"><tr><th>Figure</th><th>Amount</th><th>Division</th></tr>
<tr><td>Your share</td><td class="num">{usd2(share)}</td><td>{money_exact(src['debt'])} ÷ {src['population']:,.0f}</td></tr>
<tr><td>Per household, Census count</td><td class="num">{usd2(per_hh)}</td><td>{money_exact(src['debt'])} ÷ {hh['count']:,.0f} households</td></tr>
</table>
<h2>Sources</h2>
<ul>
<li><a href="{E(src['debtSource'][1])}" rel="noopener">{E(src['debtSource'][0])}</a>, close of {fdate(src['debtDate'])}: {money_exact(src['debt'])}.</li>
<li><a href="{E(src['popSource'][1])}" rel="noopener">{E(src['popSource'][0])}</a>, {src['population']:,.0f} residents on {fdate(src['populationDate'])}.</li>
<li><a href="{E(src['histSource'][1])}" rel="noopener">{E(src['histSource'][0])}</a>, fiscal-year-end totals.</li>
<li><a href="{E(hh['sourceUrl'])}" rel="noopener">{E(hh['sourceName'])}</a>, {hh['count']:,.0f} households ({E(str(hh['asOf']))}).</li>
</ul>
</section>
<p class="rel"><a href="{root}national-debt-per-person/">National debt per person</a> · <a href="{root}national-debt-by-year/">Debt by year</a> · <a href="{root}">Live debt clock</a></p>
{site_chrome.site_footer(root, lead=f"Treasury close {fdate(data['debtDate'])}. Page built {E(stamp)}.")}
</main>
<script src="{asset}share.js?v={v_js}"></script>
</body></html>"""


def build(root, site, with_analytics, stamp, off_d, off_v, pop, pop_date, households, population_ticker, debt_by_fy, debt_by_fy_source):
    """Redraw every card and year page from this run's Treasury close and date.

    build.py calls this on every site build. The daily refresh workflow runs
    build.py, then copies your-share/ into the deploy, so the dollar figure
    and the close date on the pre-rendered cards stay current.
    """
    if not off_v or not pop:
        raise SystemExit("your-share: official debt or Census population is missing")
    if not os.path.isdir(FD):
        raise SystemExit(f"your-share: DejaVu fonts not found at {FD}")
    data = load_inputs(root, off_d, off_v, pop, pop_date, households, population_ticker, debt_by_fy, debt_by_fy_source)
    data["site"] = site.rstrip("/")
    out = os.path.join(root, "your-share")
    os.makedirs(out, exist_ok=True)
    og_dir = os.path.join(out, "og")
    born_dir = os.path.join(out, "born")
    if os.path.isdir(og_dir):
        shutil.rmtree(og_dir)
    if os.path.isdir(born_dir):
        shutil.rmtree(born_dir)
    os.makedirs(og_dir)
    share = off_v / pop
    share_txt = usd2(share)
    base_notes = [
        f"Treasury Debt to the Penny, {fdate(off_d)}",
        f"÷ {pop:,.0f} Census residents, {fdate(pop_date)}",
        "Enter a birth year for the debt then",
    ]
    render_card(os.path.join(og_dir, "default.png"), "Your share of the US debt", share_txt,
                [("TOTAL PUBLIC DEBT", money_exact(off_v)), ("US RESIDENTS", f"{pop:,.0f}")], base_notes, False)
    render_card(os.path.join(og_dir, "default-sq.png"), "Your share of the US debt", share_txt,
                [("TOTAL PUBLIC DEBT", money_exact(off_v)), ("US RESIDENTS", f"{pop:,.0f}")], base_notes, True)
    desc = (f"Your share of the US debt is {share_txt}: Treasury's {fdate(off_d)} total of {money_exact(off_v)} "
            f"divided by the Census Bureau's {pop:,.0f} residents on {fdate(pop_date)}. Enter a birth year. Nothing is stored.")
    title = f"Your Share of the US Debt: {usd0(share)}"
    v_css = hashlib.sha1(open(os.path.join(root, "style.css"), "rb").read()).hexdigest()[:10]
    v_share = hashlib.sha1(open(os.path.join(out, "share.css"), "rb").read()).hexdigest()[:10]
    v_js = hashlib.sha1(open(os.path.join(out, "share.js"), "rb").read()).hexdigest()[:10]
    apply = with_analytics or _analytics_fn(root)

    def write_page(path, **kw):
        doc = page_html(site, v_css=v_css, v_share=v_share, v_js=v_js, data=data, stamp=stamp, **kw)
        doc = apply(doc)
        doc = site_chrome.with_notice(doc)
        open(path, "w", encoding="utf-8").write(doc)

    write_page(os.path.join(out, "index.html"), root="../", asset="", title=title, desc=desc,
               canonical=f"{site}/your-share/", og_image=f"{site}/your-share/og/default.png",
               og_alt=f"Your share of the US debt is {share_txt} as of {fdate(off_d)}",
               robots="", sentence=growth_sentence(share_txt, None, None, None), year=None)
    made = 0
    for y in range(OG_MIN, OG_MAX + 1):
        row = data["years"].get(str(y))
        if not row:
            continue
        amt, date, _pop_y, _series = row
        multiple = off_v / amt if amt else None
        sent = growth_sentence(share_txt, y, amt, multiple)
        notes = [
            f"Treasury Debt to the Penny, {fdate(off_d)}",
            f"÷ Census residents, {fdate(pop_date)}",
            f"FY{y} ended {fdate(date)}",
        ]
        chips = [(f"DEBT IN {y}", money_exact(amt)), ("SINCE THEN", (times(multiple) or "—") + "×")]
        card_title = f"Born in {y}"
        render_card(os.path.join(og_dir, f"{y}.png"), card_title, share_txt, chips, notes, False)
        render_card(os.path.join(og_dir, f"{y}-sq.png"), card_title, share_txt, chips, notes, True)
        y_title = f"Born in {y}: Your Share of the US Debt Is {usd0(share)}"
        ydir = os.path.join(born_dir, str(y))
        os.makedirs(ydir, exist_ok=True)
        write_page(os.path.join(ydir, "index.html"), root="../../../", asset="../../", title=y_title, desc=sent,
                   canonical=f"{site}/your-share/born/{y}/", og_image=f"{site}/your-share/og/{y}.png",
                   og_alt=sent, robots="noindex", sentence=sent, year=y)
        made += 1
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    open(os.path.join(out, "data.json"), "w", encoding="utf-8").write(blob)
    _check(root, data, share_txt)
    print(f"your-share: {usd2(share)} as of {off_d}; {made} birth-year cards; stamp {stamp}")
    return f"{site}/your-share/"


def _check(root, data, share_txt):
    """The page's math has to match this file, and a missing year must stay missing."""
    share = data["debt"] / data["population"]
    if usd2(share) != share_txt:
        raise SystemExit("your-share: share text drifted")
    y1985 = data["years"].get("1985")
    y2026 = data["years"].get("2026")
    if not y1985 or y1985[2] is None:
        raise SystemExit("your-share: FY1985 debt or July 1 population is missing from the source files")
    if not y2026 or y2026[2] is not None:
        raise SystemExit("your-share: FY2026 should have a debt total and no July 1 population")
    cal = next(s for s in data["states"] if s["slug"] == "california")
    if cal["debt"] <= 0 or cal["pop"] <= 0:
        raise SystemExit("your-share: California official total is missing")
    sent = growth_sentence(share_txt, 1985, y1985[0], data["debt"] / y1985[0])
    script = os.path.join(root, "pipeline", "check_share.js")
    subprocess.check_call(["node", script, share_txt, usd2(cal["debt"] / cal["pop"]),
                           usd2(data["debt"] / data["households"]["count"]), sent], cwd=root)


def _from_data_json(root):
    D = json.load(open(os.path.join(root, "data", "data.json"), encoding="utf-8"))
    T, M = D["tickers"], D["meta"]
    td = T["debt_total"]
    closes = sorted((M.get("debt_closes") or []), key=lambda c: c[0], reverse=True)
    if td.get("status") == "ok" and closes and closes[0][0] == td.get("as_of"):
        off_d, off_v = closes[0][0], float(closes[0][1])
    else:
        off_d, off_v = td.get("as_of"), td.get("base")
    pop = T["population"]
    gen = dt.datetime.fromtimestamp(M["generated_epoch"], ZoneInfo("America/Chicago"))
    stamp = gen.strftime("%b %-d, %Y %-I:%M %p") + " CT"
    site = os.environ.get("DEBTCLOCK_SITE_URL", "https://everydebtclock.com").rstrip("/")
    return dict(root=root, site=site, with_analytics=None, stamp=stamp, off_d=off_d, off_v=off_v,
                pop=pop["base"], pop_date=pop["as_of"], households=T["households"], population_ticker=pop,
                debt_by_fy=M.get("debt_by_fy") or [], debt_by_fy_source=M.get("debt_by_fy_source"))


if __name__ == "__main__":
    build(**_from_data_json(R))
