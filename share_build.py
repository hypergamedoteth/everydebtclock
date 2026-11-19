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
    src = data
    c = data["clock"]
    share = data["debt"] / data["population"]
    robot = f'<meta name="robots" content="{robots}">' if robots else ""
    lead = f"Official: {usd2(share)} on {fdate(src['debtDate'])} (U.S. Treasury)."
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
<link rel="stylesheet" href="{root}style.css?v={v_css}"><link rel="stylesheet" href="share.css?v={v_share}">
<!--ANALYTICS--><!--/ANALYTICS-->
<link rel="icon" href="/favicon.ico" sizes="16x16 32x32 48x48"><link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png"><link rel="icon" type="image/svg+xml" href="/icon.svg">
</head><body class="share">
<main>
<a class="brand" href="{root}">EVERY <b>DEBT</b> CLOCK</a>
<section class="result" id="share-clock" data-b="{c['b']}" data-r="{c['r']}" data-t0="{c['t0']}" data-pop="{c['pop']}" data-pr="{c['pr']}" data-pt="{c['pt']}">
<p class="k">Your share · live</p>
<p class="big" id="share-num">{usd2(share)}</p>
</section>
<h1>{E(lead)}</h1>
<p>One equal share is the Treasury Debt to the Penny total divided by the Census resident population. The official figure is <b>{usd2(share)}</b> on <b>{fdate(src['debtDate'])}</b>: {money_exact(src['debt'])} ÷ {src['population']:,.0f} residents on {fdate(src['populationDate'])}. The number above is that national debt clock, projected forward, divided by the projected population.</p>
<p class="rel"><a href="{root}national-debt-per-person/">National debt per person</a> · <a href="{root}">Live debt clock</a></p>
{site_chrome.site_footer(root, lead=f"Treasury close {fdate(data['debtDate'])}. Page built {E(stamp)}.")}
</main>
<script src="share.js?v={v_js}"></script>
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
    td = json.load(open(os.path.join(root, "data", "data.json"), encoding="utf-8"))["tickers"]["debt_total"]
    data["clock"] = {
        "b": td["base"], "r": td["rate"], "t0": td["t0"],
        "pop": population_ticker["base"], "pr": population_ticker.get("rate") or 0,
        "pt": population_ticker.get("t0") or 0,
    }
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
        "Live clock ÷ projected population",
    ]
    render_card(os.path.join(og_dir, "default.png"), "Your share of the US debt", share_txt,
                [("TOTAL PUBLIC DEBT", money_exact(off_v)), ("US RESIDENTS", f"{pop:,.0f}")], base_notes, False)
    render_card(os.path.join(og_dir, "default-sq.png"), "Your share of the US debt", share_txt,
                [("TOTAL PUBLIC DEBT", money_exact(off_v)), ("US RESIDENTS", f"{pop:,.0f}")], base_notes, True)
    desc = (f"Your share of the US debt is {share_txt}: Treasury's {fdate(off_d)} total of {money_exact(off_v)} "
            f"divided by the Census Bureau's {pop:,.0f} residents on {fdate(pop_date)}.")
    title = f"Your Share of the US Debt: {share_txt}"
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
               robots="", sentence="", year=None)
    made = 0
    redir = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<link rel="canonical" href="{site}/your-share/">
<meta http-equiv="refresh" content="0; url=/your-share/">
<title>Your share of the national debt</title>
<script>location.replace("/your-share/")</script>
</head><body><p><a href="/your-share/">Your share of the national debt</a></p></body></html>
"""
    for y in range(OG_MIN, OG_MAX + 1):
        ydir = os.path.join(born_dir, str(y))
        os.makedirs(ydir, exist_ok=True)
        open(os.path.join(ydir, "index.html"), "w", encoding="utf-8").write(redir.format(site=site.rstrip("/")))
        made += 1
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    open(os.path.join(out, "data.json"), "w", encoding="utf-8").write(blob)
    _check(root, data, share_txt)
    print(f"your-share: {usd2(share)} as of {off_d}; {made} birth-year redirects; stamp {stamp}")
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
    page = open(os.path.join(root, "your-share", "index.html"), encoding="utf-8").read()
    if "<form" in page or 'id="born"' in page or 'name="hh"' in page or 'name="income"' in page:
        raise SystemExit("your-share: the calculator form is still on the page")
    if 'id="share-num"' not in page or not page.split("<h1>", 1)[-1].startswith("Official:"):
        raise SystemExit("your-share: missing the live share clock or the short official line")


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
