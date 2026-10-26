"""Place pages (US states now, countries later), rendered from places/<slug>.json.
Called from build.py. Adding a place is a data file: places/<slug>.json with kind "state" or "country".
The page mirrors the US homepage clock (same style.css, header, hero, What-changed cards, tile grids,
history tiles, How-it-works panel and tap-to-open share dialog), rendered at build time plus a small ticker.
Ticking numbers are a labelled projection: latest official figure + (latest - prior) / (seconds between them)
x (seconds since latest). Places without two consecutive official figures show the official figure, fixed."""
import json, os, html, glob, datetime as dt
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
# Sections shown in the place nav. A section appears in the nav once it has at least one live place.
SECTIONS = [("state", "states", "States", "US state debt clocks"),
            ("country", "countries", "Countries", "Country debt clocks")]
# Shown on the homepage "Your state" card when the visitor's location is unknown or has no page yet.
DEFAULT_PLACE = "texas"
ACC = ["var(--red)", "var(--blue)", "var(--violet)", "var(--amber)", "var(--teal)"]
E = html.escape

def load(R):
    out = []
    for f in sorted(glob.glob(f"{R}/places/*.json")):
        p = json.load(open(f))
        if p.get("status") == "live": out.append(p)
    return out

def _d(s): return dt.date.fromisoformat(s)
def _fd(s): return _d(s).strftime("%b %-d, %Y")
CUR = "$"  # currency symbol for the page being rendered ("$" for US places, "C$" for Canada); set by _cur(p)
def _cur(p): global CUR; CUR = (p.get("currency") or {}).get("symbol", "$"); return CUR
def _usd0(x): return ("−" if x < 0 else "") + CUR + f"{abs(x):,.0f}"
def _usd2(x): return ("−" if x < 0 else "") + CUR + f"{abs(x):,.2f}"
def _sg(x): return "+" if x >= 0 else "−"
def _b(x): return ("−" if x < 0 else "") + CUR + (f"{abs(x)/1e12:,.2f} trillion" if abs(x) >= 1e12 else f"{abs(x)/1e9:,.2f} billion")
def _short(x):
    a, s = abs(x), ("−" if x < 0 else "") + CUR
    return s + (f"{a/1e12:.2f}T" if a >= 1e12 else f"{a/1e9:.2f}B" if a >= 1e9 else f"{a/1e6:.1f}M" if a >= 1e6 else f"{a:,.0f}")
def _rate_txt(r):
    if not r: return "fixed"
    sg = "+" if r > 0 else "−"
    return f"{sg}{_short(abs(r))[len(CUR):]}/sec · {sg}{_short(abs(r) * 86400)[len(CUR):]}/day"
def _eod(s): return dt.datetime.combine(_d(s), dt.time(23, 59, 59), CT).timestamp()

def texts(p):
    """Wording that differs by place. Defaults are the Texas (state + local, annual, Census) wording."""
    name, freq = p["name"], p.get("frequency", "annual")
    t = {"head": p.get("headline", "state + local debt"), "head_long": p.get("headline_long", "state and local government debt"),
         "subject": p.get("subject", f"{name} state and local governments"),
         "sum_note": p.get("sum_note", "Sum of the official state and local totals below." if len(p["components"]) > 1 else p["components"][0].get("includes", "")),
         "freq": freq, "once": "once a month" if freq == "monthly" else "once a year",
         "period": p.get("trend_period", "12 months" if freq == "monthly" else "year"),
         "pace": p.get("trend_pace", "the past 12 months' pace" if freq == "monthly" else "last year's pace"),
         "pop_pub": p["population"].get("publisher_short", "Census Bureau"), "pop_tag": p["population"].get("tag", "Census"),
         "report": "monthly figures" if freq == "monthly" else "annual reports"}
    t["pop_pos"] = p["population"].get("possessive", f"the {t['pop_pub']}'s")
    t["Head"] = p.get("hist_label", "State + local" if "headline" not in p else t["head"][0].upper() + t["head"][1:])
    t["rate_phrase"] = "last year's official change per second" if freq != "monthly" else "the official change per second over the past 12 months"
    t["pop_tag2"] = p["population"].get("tag", "Census")
    t["after"] = ", after the fiscal year ends" if freq != "monthly" else ", a few business days after each month-end"
    return t

def _when(p, d_):
    """How a figure date is labelled: FY2025 (annual, fiscal year-end) or Sep 2026 (monthly, month-end)."""
    return _d(d_).strftime("%b %Y") if p.get("frequency") == "monthly" else f"FY{_d(d_).year}"

def comp_rate(c):
    if c.get("prior_value") and c.get("prior_as_of"):
        return (c["value"] - c["prior_value"]) / (_eod(c["as_of"]) - _eod(c["prior_as_of"]))
    return None

def calc(p):
    """Totals and the labelled trend. The trend is None unless every component has a prior official figure."""
    cs = p["components"]
    total = sum(c["value"] for c in cs)
    rates = [comp_rate(c) for c in cs]
    rate = sum(rates) if all(r is not None for r in rates) else None
    return {"total": total, "t0": max(_eod(c["as_of"]) for c in cs), "rate": rate, "rates": rates,
            "as_of": max(c["as_of"] for c in cs), "same_date": len({c["as_of"] for c in cs}) == 1}

def nav_html(places, depth, current=None, cls="pl"):
    """Place nav: United States, then one link per section that has a live place."""
    up = "../" * depth
    kinds = {p["kind"] for p in places}
    items = [(up or "./", "United States", current == "us")]
    items += [(f"{up}{d}/", lab, current == k) for k, d, lab, _ in SECTIONS if k in kinds]
    return f'<nav class="{cls}">' + "".join(f'<a href="{h}"{" class=on" if on else ""}>{lab}</a>' for h, lab, on in items) + "</nav>"

def hub_label(places, short=False):
    """Data-driven name for the hub, from the kinds that have a live place (never names places that aren't live)."""
    kinds = {p["kind"] for p in places}
    w = "state & country" if kinds >= {"state", "country"} else "country" if kinds == {"country"} else "state"
    return w if short else f"{w} debt clocks"

def index(places, now):
    """Machine-readable list of every live place (api/places.json and the homepage card).
    value(t) = base + rate * (t - t0); rate is 0 when the place has no official trend."""
    sec = {k: d for k, d, _, _ in SECTIONS}
    out = []
    for p in sorted(places, key=lambda x: (x["kind"], x["name"])):
        c = calc(p)
        out.append({"slug": p["slug"], "name": p["name"], "kind": p["kind"], "country": p.get("country"), "region_code": p.get("region_code"),
                    "demonym": p.get("demonym", "resident"), "label": p.get("headline", "state + local debt" if p["kind"] == "state" else "government debt"),
                    "currency": (p.get("currency") or {}).get("code", "USD"), "sym": (p.get("currency") or {}).get("symbol", "$"), "frequency": p.get("frequency", "annual"),
                    "base": c["total"], "base_date": c["as_of"], "t0": c["t0"], "rate": c["rate"] or 0,
                    "population": p["population"]["value"], "publisher": p.get("publisher"), "url": f'{sec[p["kind"]]}/{p["slug"]}/'})
    default = DEFAULT_PLACE if any(x["slug"] == DEFAULT_PLACE for x in out) else (out[0]["slug"] if out else None)
    return {"_doc": "Live place clocks on everydebtclock.com. value(t) = base + rate * (t - t0), t in Unix seconds; rate 0 = official figure, not projected. url is relative to https://everydebtclock.com/.",
            "generated": dt.datetime.fromtimestamp(now, CT).isoformat(timespec="seconds"), "default": default, "hub": "states/", "hub_label": "All " + hub_label(places), "places": out}

def build(R, SITE, with_analytics, PAGE_CSS, ANS_CSS, og, stamp, now):
    places = load(R)
    urls = []
    os.makedirs(f"{R}/api", exist_ok=True)
    with open(f"{R}/api/places.json", "w") as f: json.dump(index(places, now), f, indent=1)
    os.makedirs(f"{R}/og/places", exist_ok=True)
    for k, d, lab, desc_ in SECTIONS:
        live = [p for p in places if p["kind"] == k]
        if not live: continue
        for p in live: urls.append(place_page(R, SITE, with_analytics, og, stamp, now, p, d, places))
        urls.append(index_page(R, SITE, with_analytics, PAGE_CSS, ANS_CSS, k, d, lab, desc_, live, places, now))
    return urls

def meta_head(SITE, url, title, desc, img, depth, extra_css="", ld="", css_link=True):
    up = "../" * depth
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}"><link rel="canonical" href="{url}">
<meta property="og:type" content="website"><meta property="og:site_name" content="Every Debt Clock"><meta property="og:url" content="{url}">
<meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc)}">
<meta property="og:image" content="{SITE}/{img}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{E(title)}">
<meta name="twitter:description" content="{E(desc)}"><meta name="twitter:image" content="{SITE}/{img}">
<meta name="theme-color" content="#07090d"><link rel="apple-touch-icon" href="{up}apple-touch-icon.png">
{f'<link rel="stylesheet" href="{up}style.css">' if css_link else ''}<style>{extra_css}</style>
{ld}</head><body>"""

# small additions on top of style.css (kept here so the US homepage is untouched)
PL_CSS = """.brand a,.brand{color:inherit}.tile .pp{grid-template-columns:1fr 1fr}.wcc .x b{color:var(--txt);font-weight:600}
details.det{margin:8px 0}details.det summary{cursor:pointer;color:var(--blue);font-size:13px;margin:6px 0}
table.v tr.sub td{color:var(--mut);font-size:12px}table.v td.num{text-align:right}.dnote{color:var(--mut);font-size:12.5px}
.badge.ann{border-color:#5a3a12;color:var(--amber)}
#details table.v td{color:var(--txt)}#details table.v tr.sub td{color:var(--mut);padding-left:22px}#details h3{color:var(--txt);margin:18px 0 4px}"""

def tile_html(tid, label, value_txt, acc, badge, rate_txt="fixed", pp=None, tick=None, dlg=None, wide=False):
    """One tile in the US homepage style. tick = (base, rate, t0) makes the value tick; dlg = dict for the tap dialog."""
    data = ""
    if tick: data += f' data-b="{tick[0]}" data-r="{tick[1]}" data-t="{tick[2]}"'
    if dlg: data += f" data-d='{E(json.dumps(dlg), quote=True)}'"
    pph = ""
    if pp:
        pph = '<div class="pp">' + "".join(f'<div><span class="l">{E(l)}</span><span class="num"{f" data-pp={chr(34)}{dv}{chr(34)}" if dv else ""}>{E(v)}</span></div>' for l, v, dv in pp) + "</div>"
    return (f'<div class="tile{" fixed" if not tick else ""}{" wide" if wide else ""}" id="t-{tid}" style="--acc:{acc}"{data}>'
            f'<div class="lab"><span>{E(label)}</span></div><div class="val num">{E(value_txt)}</div>{pph}'
            f'<div class="meta"><span class="rate{" up" if tick and tick[1] > 0 else ""}">{E(rate_txt)}</span>{badge}</div></div>')

def place_page(R, SITE, with_analytics, og, stamp, now, p, sec_dir, places):
    _cur(p); T = texts(p)
    c = calc(p); pop = p["population"]; cs = p["components"]; name = p["name"]; dem = p.get("demonym", "resident")
    pub = p.get("publisher", "official data")
    url = f"{SITE}/{sec_dir}/{p['slug']}/"
    t0, rate = c["t0"], c["rate"]
    proj = c["total"] + (rate * (now - t0) if rate else 0)
    pp_off = c["total"] / pop["value"]
    as_of = _fd(c["as_of"]); fy = _d(c["as_of"]).year
    prior_total = sum(x["prior_value"] for x in cs) if rate else None
    yr_change = c["total"] - prior_total if rate else None
    days = (_d(c["as_of"]) - _d(cs[0]["prior_as_of"])).days if rate else None
    up_ = (rate or 0) >= 0
    title = p.get("title", f"{name} Debt Clock: Live State and Local Debt, From Official Data")
    desc = (f"{name} {T['head_long']}: {_b(c['total'])} {'at month-end' if T['freq'] == 'monthly' else 'at fiscal year-end'} {as_of}"
            + (" (" + " + ".join(f"{x['short'].lower()} {_b(x['value'])}" for x in cs) + ")" if len(cs) > 1 else "")
            + f", {_usd0(pp_off)} per {dem}. Live clock projected from the official {T['freq']} figures, with sources and the math.")
    img = f"og/places/{p['slug']}.png"
    if og:
        og(f"{R}/{img}", f"{name} {T['head']} · ticking live", _usd0(proj),
           [(f"Per {dem} ({T['pop_tag']} pop.)", _usd2(proj / pop["value"])), (f"Official, {as_of}", _usd0(c["total"]))],
           (f"{_sg(rate)}{_short(abs(rate) * 86400)}/day" if rate else "OFFICIAL"), "#ff4d5e",
           f"{pub}, {_when(p, c['as_of'])} official\nprojected at {T['pace']} · {T['freq']} data" if rate else f"{pub}, {_when(p, c['as_of'])} official")
    ld = '<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "Dataset", "name": f"{name} {T['head_long']}", "description": desc, "url": url,
        "isAccessibleForFree": True, "creator": {"@type": "Organization", "name": "Every Debt Clock", "url": SITE + "/"},
        "spatialCoverage": {"@type": "Place", "name": name},
        "temporalCoverage": f"{min(h[0] for x in cs for h in x.get('history', [[x['as_of']]]))}/{c['as_of']}",
        "isBasedOn": sorted({x["source_url"] for x in cs} | {pop["source_url"]})}).replace("</", "<\\/") + "</script>"

    proj_badge = f'<span class="badge proj" title="Projected every frame from the official figure of {E(as_of)}">PROJECTED · from {E(as_of)}</span>'
    fix_badge = lambda d_: f'<span class="badge fix" title="Official figure that does not change until the next official report">FIXED · {E(_fd(d_))}</span>'
    ann_badge = f'<span class="badge ann" title="{E(p.get("cadence", ""))}">{T["freq"].upper()} DATA · reported {T["once"]}</span>'
    src_list = [(x["source_name"], x["source_url"]) for x in cs] + [(pop["source_name"], pop["source_url"])] + [(s_["name"], s_["url"]) for s_ in p.get("extra_sources", [])]

    def dlg(label, method, src_name, src_url, locator="", base=None, r=None, official=None):
        return {"l": label, "m": method, "s": src_name, "u": src_url, "loc": locator, "b": base, "r": r, "t0": t0 if r else None,
                "o": official, "share": url, "img": f"{SITE}/{img}"}

    # ---- header (same as the US homepage), jump nav adapted to the place's sections
    jump = [("changed", "What changed"), ("debt", "Debt")] + [(x["key"], x["short"]) for x in cs] + [("people", f"Per {dem}"), ("history", "History"), ("details", "Details"), ("method", "Method")]
    header = (f'<header class="top"><div class="topin"><a class="brand" href="../../">EVERY <b>DEBT</b> CLOCK</a>{nav_html(places, 2, p["kind"], "plnav")}'
              f'<span class="live"><span class="dot"></span><span>Official data through {E(as_of)} · {T["freq"]}</span></span></div>'
              f'<nav class="jump">' + "".join(f'<a href="#{i}">{E(t)}</a>' for i, t in jump) + "</nav></header>")

    # ---- intro (mirrors the US intro paragraph: official figure first, then how the clock projects)
    parts = " and ".join(f"{_b(x['value'])} of {E(x['label'].lower())}" for x in cs)
    proj_txt = (f"The clock below starts from that official figure and projects forward at {T['pace']} (about {_short(abs(rate) * 86400)} a day{'' if up_ else ' less'}), "
                f"the official change from {_fd(cs[0]['prior_as_of'])} to {as_of}. {E(name)} reports its debt {T['once']}, not daily, so the ticking number is a projection, not an official figure; "
                f"it re-bases when the next {T['report']} come out.") if rate else \
               f"{E(name)} reports its debt {T['once']} and only one official figure is available, so the clock shows the official figure without projecting."
    others = [o for o in places if o["slug"] != p["slug"]]
    crumb = (f'<div class="crumb"><a href="../../">← US national debt clock</a><span>·</span><a href="../../states/">All {E(hub_label(places))}</a>'
             + "".join(f'<span>·</span><a href="../../{dict((k, d) for k, d, _, _ in SECTIONS)[o["kind"]]}/{o["slug"]}/">{E(o["name"])}</a>' for o in sorted(others, key=lambda x: x["name"])[:8]) + '</div>')
    intro = (f'<section class="intro" id="intro">{crumb}<h1>{E(name)} Debt Clock</h1>'
             f'<p>{E(T["subject"])} owed <b>{_usd0(c["total"])}</b> ({_b(c["total"])}) '
             + (f'on <b>{as_of}</b>' if T["freq"] == "monthly" else f'at the end of fiscal year {fy} (<b>{as_of}</b>)') + ', according to the '
             + " and the ".join(f'<a href="{E(u_)}" rel="noopener">{E(n_)}</a>' for u_, n_ in dict.fromkeys((x["source_url"], x["source_name"].split(" (")[0]) for x in cs))
             + (f': {parts}' if len(cs) > 1 else '') + f'. {E(p.get("scope_note", ""))}{" " if p.get("scope_note") else ""}That is <b>{_usd2(pp_off)} per {E(dem)}</b>: the debt divided by {E(T["pop_pos"])} estimate of {pop["value"]:,} {E(name)} residents on {_fd(pop["as_of"])}. {proj_txt}</p></section>')

    # ---- hero (same block and labels as the US hero)
    hero_d = dlg(f'{name} {T["head"]}', T["sum_note"], pub, cs[0]['source_url'], cs[0].get("source_locator", "") if len(cs) == 1 else "", base=c['total'], r=rate, official=f"{_usd0(c['total'])} official, {as_of}")
    hero = (f'<div class="hero lead" id="t-total" data-b="{c["total"]}" data-r="{rate or 0}" data-t="{t0}" data-d=\'{E(json.dumps(hero_d), quote=True)}\'>'
            f'<div class="k">{E(name)} {E(T["head"])} · {"live" if rate else "official"}</div><div class="big num" id="hv">{_usd0(proj)}</div>')
    if rate:
        hero += (f'<div class="sub"><span>{_rate_txt(rate)}</span><span class="note">rate: official change over the latest {T["period"]} ({_fd(cs[0]["prior_as_of"])} → {as_of}, {days} days); {E(name)} reports {T["once"]}, so this is a projection</span>'
                 f'<span>Since you opened this page: <span class="num" id="hs">{CUR}0</span> {"more" if up_ else "less"} debt</span></div>')
    else:
        hero += f'<div class="sub"><span>fixed</span><span class="note">{E(name)} reports {T["once"]}; one official figure available</span></div>'
    trio_x = [(x["short"] + " · official " + _fd(x["as_of"]), _usd0(x["value"])) for x in cs[:2]] if len(cs) > 1 else \
             [(f"Official · {_fd(c['as_of'])}", _usd0(c["total"]))]
    trio_x += [(h["label"], h["value"]) for h in p.get("hero_extra", [])]
    hero += ('<div class="trio">' + f'<div><span class="l">Per {E(dem)} ({E(T["pop_tag"])}, {_fd(pop["as_of"])})</span><span class="num" data-pp="{pop["value"]}">{_usd2(proj / pop["value"])}</span></div>'
             + "".join(f'<div><span class="l">{E(l)}</span><span class="num">{E(v)}</span></div>' for l, v in trio_x[:2]) + "</div>"
             f'<div class="meta" style="margin-top:10px">{proj_badge if rate else fix_badge(c["as_of"])}{ann_badge}<span class="badge">source: {E(pub)}</span></div></div>')

    # ---- What changed: official annual figures, newest first, with a NOW card (mirrors the US recent-closes strip)
    wc = ""
    if all(x.get("history") for x in cs):
        ds = sorted(set.intersection(*[{h[0] for h in x["history"]} for x in cs]), reverse=True)
        H = {d_: [dict(map(tuple, x["history"]))[d_] for x in cs] for d_ in ds}
        def dl(v): return f'<span class="{"up" if v > 0 else "dn" if v < 0 else ""}">{"+" if v >= 0 else "−"}{_short(abs(v))}</span>'
        cards = ""
        for i, d_ in enumerate(ds):
            tot = sum(H[d_]); prev = ds[i + 1] if i + 1 < len(ds) else None
            cards += (f'<div class="wcc"><div class="d">{_when(p, d_)} · {_fd(d_)}</div><div class="v num">{_short(tot)}</div>'
                      + (f'<div class="x">{"change" if T["freq"] == "monthly" else "year"} {dl(tot - sum(H[prev]))}</div>' + ("".join(f'<div class="x">{E(x["short"].split()[0].lower())} {dl(H[d_][k] - H[prev][k])}</div>' for k, x in enumerate(cs)) if len(cs) > 1 else "") if prev else f'<div class="x">earliest {"month" if T["freq"] == "monthly" else "year"} shown</div>')
                      + (f'<div class="x">per {E(dem)} <b>{_usd0(tot / pop["value"])}</b></div>' if d_ == pop.get("debt_match_date", c["as_of"]) else "") + "</div>")
        now_card = (f'<div class="wcc now"><div class="d">NOW · projected</div><div class="v num" id="wcn">{_short(proj)}</div>'
                    f'<div class="x">vs last official <span class="num" id="wcd">{_sg(proj - c["total"])}{_short(abs(proj - c["total"]))}</span></div>'
                    f'<div class="x">per {E(dem)} <span class="num" data-pp="{pop["value"]}">{_usd0(proj / pop["value"])}</span></div></div>') if rate else ""
        wc = (f'<section id="changed"><div class="sh"><span class="bar" style="background:var(--red)"></span><h2>What changed</h2>'
              f'<span class="h2n">Official {T["freq"]} totals, newest first · {E(pub)} · published {T["once"]}{T["after"]}</span></div>'
              f'<div class="wc">{now_card}{cards}</div>'
              f'<div class="legend">{E(p.get("legend", f"{name} debt is reported once a year, at fiscal year-end. Real borrowing happens in lumps when bonds are sold and is repaid on schedules, so the live number is a straight-line projection between official reports, shown here next to the official totals."))}</div></section>')

    # ---- Debt overview tiles (mirror the US "National debt" grid where Texas has an equivalent)
    tiles = [tile_html("combined", f"{name} {T['head']}", _usd0(proj), ACC[0], proj_badge if rate else fix_badge(c["as_of"]), _rate_txt(rate),
                       pp=[(f"Per {dem} ({T['pop_tag']} pop.)", _usd2(proj / pop["value"]), pop["value"]), ("Official total", _short(c["total"]), None)],
                       tick=(c["total"], rate, t0) if rate else None,
                       dlg=dlg(f"{name} {T['head']}", "Sum of the official state and local totals." if len(cs) > 1 else T["sum_note"], pub, cs[0]["source_url"], base=c["total"], r=rate, official=f"{_usd0(c['total'])} official, {as_of}"))]
    for i, x in enumerate(cs if len(cs) > 1 else []):
        r_ = c["rates"][i]
        tiles.append(tile_html(f"{x['key']}_total", x["label"], _usd0(x["value"] + (r_ * (now - t0) if r_ else 0)), ACC[i + 1],
                               proj_badge if r_ else fix_badge(x["as_of"]), _rate_txt(r_),
                               pp=[(f"Per {dem} ({T['pop_tag']} pop.)", _usd2((x["value"] + (r_ * (now - t0) if r_ else 0)) / pop["value"]), pop["value"]), ("Official", _short(x["value"]), None)],
                               tick=(x["value"], r_, t0) if r_ else None,
                               dlg=dlg(x["label"], x.get("includes", ""), x["source_name"], x["source_url"], x.get("source_locator", ""), base=x["value"], r=r_, official=f"{_usd0(x['value'])} official, {_fd(x['as_of'])}")))
    if rate:
        tiles.append(tile_html("yr_change", f"Change over the latest official {T['period']}", _sg(yr_change) + _usd0(abs(yr_change)), ACC[3], fix_badge(c["as_of"]),
                               f"{_fd(cs[0]['prior_as_of'])} → {as_of}",
                               pp=([(x["short"], _sg(x["value"] - x["prior_value"]) + _short(abs(x["value"] - x["prior_value"])), None) for x in cs[:2]] if len(cs) > 1 else
                                   [(f"Per {dem}", _sg(yr_change) + _usd2(abs(yr_change) / pop["value"]), None), ("Change", f"{yr_change / prior_total * 100:+.1f}%", None)]),
                               dlg=dlg(f"Change over the latest official {T['period']}", f"Official total {as_of} ({_usd0(c['total'])}) minus official total {_fd(cs[0]['prior_as_of'])} ({_usd0(prior_total)}).", pub, cs[0]["source_url"])))
        tiles.append(tile_html("per_day", "Projected " + ("growth" if up_ else "decline") + " per day", _sg(rate) + _usd0(abs(rate) * 86400), ACC[3], proj_badge, f"{_sg(rate)}{_usd2(abs(rate))}/sec",
                               pp=[(f"Per {T['period']} (official)", _sg(yr_change) + _short(abs(yr_change)), None), (f"Per {dem} per {T['period']}", _sg(yr_change) + _usd2(abs(yr_change) / pop["value"]), None)],
                               dlg=dlg("Projected " + ("growth" if up_ else "decline") + " per day", f"Latest official {T['period']}'s change ÷ {days} days. This is the rate the clock ticks at; it is not an official daily figure.", pub, cs[0]["source_url"])))
    debt_sec = (f'<section id="debt"><div class="sh"><span class="bar" style="background:var(--red)"></span><h2>{E(name)} government debt</h2>'
                f'<span class="h2n">{E(pub)} · official as of {as_of} · {("projected at " + T["pace"].replace("'", "&#39;") + " between " + T["report"]) if rate else "fixed until the next report"}</span></div>'
                f'<div class="grid">{"".join(tiles)}</div></section>')

    # ---- one section per component: its breakdown and facts as fixed tiles (dense grid, like the US detail grids)
    comp_secs = ""
    for i, x in enumerate(cs):
        tl = ""
        for j, b in enumerate(x.get("breakdown", [])):
            share = b["value"] / (b.get("of") or x["value"]) * 100
            tl += tile_html(f"{x['key']}_{j}", b.get("tile_label", b["label"].strip()), _usd0(b["value"]), ACC[i + 1], fix_badge(x["as_of"]), f"{share:.1f}% of {b.get('of_label', x['short'].lower())}",
                            pp=[(f"Per {dem}", _usd2(b["value"] / pop["value"]), None)],
                            dlg=dlg(b["label"].strip(), x.get("includes", ""), x["source_name"], x["source_url"], x.get("source_locator", ""), official=f"{_usd0(b['value'])} official, {_fd(x['as_of'])}"))
        for j, f in enumerate(x.get("facts", [])):
            v = _usd0(f["value"]) if f.get("kind") == "usd" else f"{f['value']:.2f}%" if f.get("kind") == "pct" else f"{f['value']:,}"
            tl += tile_html(f"{x['key']}_f{j}", f["label"], v, ACC[i + 1], fix_badge(f["as_of"]), f.get("sub", "fixed"),
                            dlg=dlg(f["label"], f.get("note", ""), f.get("source_name", x["source_name"]), f.get("source_url", x["source_url"]), f.get("source_locator", ""), official=f"{v} official, {_fd(f['as_of'])}"))
        comp_secs += (f'<section id="{x["key"]}"><div class="sh"><span class="bar" style="background:{ACC[i + 1]}"></span><h2>{E(x["label"])}</h2>'
                      f'<span class="h2n">{E(x["source_name"])} · official, {_fd(x["as_of"])} · fixed</span></div><div class="grid dense">{tl}</div></section>')

    # ---- per person & population (mirrors the US "Ratios & economy" grid)
    pt = [tile_html("pp_total", f"Debt per {dem}", _usd2(proj / pop["value"]), "var(--teal)", proj_badge if rate else fix_badge(c["as_of"]),
                    (f"{_sg(rate)}{_usd2(abs(rate) * 86400 / pop['value'])}/day" if rate else "fixed"), pp=[("Official basis", _usd2(pp_off), None), ("Population", f"{pop['value']:,}", None)],
                    tick=(c["total"] / pop["value"], rate / pop["value"], t0) if rate else None,
                    dlg=dlg(f"Debt per {dem}", f"Live total ÷ {pop['value']:,} residents ({T['pop_tag']} estimate for {_fd(pop['as_of'])}, not projected). Official basis: {as_of} total ÷ the same population.", pop["source_name"], pop["source_url"]))]
    pt += [tile_html(f"pp_{x['key']}", f"{x['short']} per {dem}", _usd2(x["value"] / pop["value"]), "var(--teal)", fix_badge(x["as_of"]), "official basis",
                     dlg=dlg(f"{x['short']} per {dem}", f"Official {x['short'].lower()} ({_usd0(x['value'])}) ÷ {pop['value']:,} residents.", x["source_name"], x["source_url"])) for x in (cs if len(cs) > 1 else [])]
    pt.append(tile_html("population", f"{name} population", f"{pop['value']:,}", "var(--teal)", fix_badge(pop["as_of"]),
                        (f"{_sg(pop['value'] - pop['prior_value'])}{abs(pop['value'] - pop['prior_value']):,} in the prior year" if pop.get("prior_value") else "fixed"),
                        dlg=dlg(f"{name} population", f"{pop.get('method_short', 'Census Bureau Vintage estimate')} for {_fd(pop['as_of'])}. Used as-is (not projected) for every per-{dem} figure.", pop["source_name"], pop["source_url"])))
    people = (f'<section id="people"><div class="sh"><span class="bar" style="background:var(--teal)"></span><h2>Per {E(dem)}</h2>'
              f'<span class="h2n">{E(pop["source_name"])} · {_fd(pop["as_of"])}</span></div><div class="grid dense">{"".join(pt)}</div></section>')

    # ---- History tiles (mirrors the US History grid)
    hist = ""; det_hist = ""
    if all(x.get("history") for x in cs):
        ds = sorted(set.intersection(*[{h[0] for h in x["history"]} for x in cs]))
        HV = {d_: [dict(map(tuple, x["history"]))[d_] for x in cs] for d_ in ds}
        hist = (f'<section id="history"><div class="sh"><span class="bar" style="background:var(--violet)"></span><h2>History</h2>'
                f'<span class="h2n">Fixed official figures · {E(pub)} · these do not tick</span></div><div class="histgrid">'
                + "".join(f'<div class="htile"><div class="y">{_when(p, d_)} · OFFICIAL</div><div class="t">{E(T["Head"])}</div><div class="num">{_short(sum(HV[d_]))}</div>'
                          + ("".join(f'<div class="t">{E(x["short"])}</div><div class="num" style="font-size:15px">{_short(HV[d_][k])}</div>' for k, x in enumerate(cs)) if len(cs) > 1 else "") + "</div>" for d_ in ds[-12:])
                + "</div></section>")
        rows = ""
        for k, d_ in enumerate(reversed(ds)):
            prev = ds[len(ds) - 2 - k] if len(ds) - 2 - k >= 0 else None
            ch = sum(HV[d_]) - sum(HV[prev]) if prev else None
            rows += (f"<tr><td>{_fd(d_)}</td>" + "".join(f'<td class="num">{_usd0(v)}</td>' for v in HV[d_]) + f'<td class="num">{_usd0(sum(HV[d_]))}</td>'
                     f'<td class="num">{"—" if ch is None else ("+" if ch >= 0 else "−") + _short(abs(ch))}</td></tr>')
        det_hist = (f'<h3>{"By month" if T["freq"] == "monthly" else "By year"} (official)</h3><table class="v"><tr><th>{"Month-end" if T["freq"] == "monthly" else "Fiscal year-end"}</th>' + "".join(f"<th>{E(x['short'])}</th>" for x in cs)
                    + f"<th>Combined</th><th>Change</th></tr>{rows}</table>")

    # ---- Details: the long tables, below the fold (like the US detail sections)
    def comp_table(x):
        rows, g = "", None
        for b in x.get("breakdown", []):
            if b.get("group") and b["group"] != g:
                g = b["group"]; rows += f'<tr><th colspan="2">{E(g)}</th></tr>'
            rows += f'<tr{" class=sub" if b.get("sub") else ""}><td>{E(b["label"].strip())}</td><td class="num">{_usd0(b["value"])}</td></tr>'
        return (f'<h3>{E(x["label"])}: {_usd0(x["value"])}</h3><p class="dnote">Official, {"month-end" if T["freq"] == "monthly" else "fiscal year-end"} {_fd(x["as_of"])} · <a href="{E(x["source_url"])}" rel="noopener">{E(x["source_name"])}</a>'
                f'{" (" + E(x.get("source_locator", "")) + ")" if x.get("source_locator") else ""}</p>'
                f'<table class="v"><tr><th>Part</th><th>Amount</th></tr>{rows}<tr><td><b>Total</b></td><td class="num"><b>{_usd0(x["value"])}</b></td></tr></table><p class="dnote">{E(x.get("includes", ""))}</p>')
    details = (f'<section id="details"><div class="sh"><span class="bar" style="background:var(--mut)"></span><h2>Details</h2><span class="h2n">Full official tables</span></div>'
               f'<div class="sk foot">{"".join(comp_table(x) for x in cs)}{det_hist}</div></section>')

    # ---- How it works (mirrors the US method panel)
    if rate:
        meth = (f'<p><b>The live number</b> = latest official total + ({T["rate_phrase"]} × seconds since that total). '
                f'{E(name)} publishes its debt {T["once"]}, not daily, so this is a projection between {T["report"]}, not an official figure.</p>'
                f'<p><code>projected = {c["total"]:,.0f} + {rate:,.4f} × (seconds since {as_of} 11:59:59 PM CT)</code></p>'
                + (f'<p>The rate is each part\'s official change over its latest {T["period"]}, added up: ' + "; ".join(f'{E(x["short"].lower())} {_usd0(x["value"])} − {_usd0(x["prior_value"])} = {_usd0(x["value"] - x["prior_value"])}' for x in cs) + '; combined '
                   if len(cs) > 1 else f'<p>The rate is the official change from {_fd(cs[0]["prior_as_of"])} to {as_of}: {_usd0(c["total"])} − {_usd0(prior_total)} = ')
                + f'{_usd0(yr_change)} over {days} days = {_usd2(rate)} per second. {E(p.get("trend_why", "")) + " " if p.get("trend_why") else ""}The actual path is lumpy (bonds are sold in batches and repaid on schedules), so the projection will drift; '
                f'when new {T["report"]} come out, the clock re-bases to the new official figures.</p>')
    else:
        meth = "<p><b>Why this number doesn't tick.</b> Only one official year is available, so there is no defensible trend to project. The figure shown is the official total.</p>"
    meth += (f'<p><b>How often it\'s published.</b> {E(p.get("cadence", ""))} {E(p.get("next_update", ""))}</p>'
             f'<p><b>Per {E(dem)}</b> divides by {E(T["pop_pos"])} estimate of {pop["value"]:,} residents on {_fd(pop["as_of"])}. It is not projected forward, so the live per-{E(dem)} figure {"rises" if (rate or 0) >= 0 else "falls"} only with the debt.</p>'
             + "".join(f"<p><b>Note.</b> {E(n)}</p>" for n in p.get("notes", []) + [p.get("fiscal_year_end_note", "")] if n)
             + "<p><b>Note.</b> Figures from source tables may not add exactly because of rounding in the source.</p>"
             + "<p><b>Sources:</b> " + " · ".join(f'<a href="{E(u)}" target="_blank" rel="noopener">{E(n)}</a>' for n, u in src_list) + "</p>"
             + f"<p>Page built {E(stamp)} from the official figures above.</p>")
    method = (f'<section id="method"><div class="sh"><span class="bar" style="background:var(--mut)"></span><h2>How it works</h2>'
              f'<span class="h2n">Official {T["freq"]} figures · projection labelled · sources linked</span></div><div class="sk foot">{meth}</div></section>')

    links = (f'<section class="answers" id="answers"><div class="sh"><h2>More clocks</h2></div><ul>'
             f'<li><a href="../../">US national debt clock (live, checked daily against Treasury)</a></li>'
             f'<li><a href="../../states/">All {E(hub_label(places))}</a></li><li><a href="../../national-debt-per-person/">US national debt per person</a></li></ul>'
             + ('<div class="sh"><h2>Other places</h2></div><ul>' + "".join(f'<li><a href="../../{dict((k, d) for k, d, _, _ in SECTIONS)[o["kind"]]}/{o["slug"]}/">{E(o["name"])} debt clock</a></li>' for o in sorted(others, key=lambda x: x["name"])) + '</ul>' if others else '')
             + '</section>')

    script = f"""<script>(function(){{const nf0=new Intl.NumberFormat('en-US',{{maximumFractionDigits:0}}),nf2=new Intl.NumberFormat('en-US',{{minimumFractionDigits:2,maximumFractionDigits:2}});
const C='{CUR}',usd=(v,d)=>(v<0?'−':'')+C+(d?nf2:nf0).format(Math.abs(v)),short=v=>{{const a=Math.abs(v);return (v<0?'−':'')+C+(a>=1e12?(a/1e12).toFixed(2)+'T':a>=1e9?(a/1e9).toFixed(2)+'B':(a/1e6).toFixed(1)+'M')}},sg=v=>v<0?'−':'+';
const now=()=>Date.now()/1000,OPENED=now(),H=document.getElementById('t-total'),B=+H.dataset.b,R=+H.dataset.r,T0=+H.dataset.t,tot=t=>B+R*(t-T0);
const ticks=[...document.querySelectorAll('.tile[data-r]')].map(e=>({{v:e.querySelector('.val'),b:+e.dataset.b,r:+e.dataset.r,t:+e.dataset.t,pp:e.id==='t-pp_total',ppx:[...e.querySelectorAll('[data-pp]')]}}));
const hv=document.getElementById('hv'),hs=document.getElementById('hs'),wcn=document.getElementById('wcn'),wcd=document.getElementById('wcd'),pps=[...document.querySelectorAll('.hero [data-pp],.wcc [data-pp]')];
const dlg=document.getElementById('dlg');let mt=null;
function open(e){{const d=JSON.parse(e.dataset.d);const x='https://x.com/intent/post?text='+encodeURIComponent(d.l+': '+(d.r?short(d.b+d.r*(now()-d.t0))+' and ticking (projected from official data)':d.o))+'&url='+encodeURIComponent(d.share);
dlg.innerHTML='<h3></h3><div class="big num" id="mv"></div><p class="mo"></p><p><b>Method.</b> <span class="mm"></span></p>'+(d.r?'<div class="math"><b>Show the math</b><table><tr><td>Base (official)</td><td class="num">'+usd(d.b)+'</td></tr><tr><td>Rate per second</td><td class="num">'+usd(d.r,2)+'</td></tr></table><p><b>Now</b> = base + rate × (now − t0) = <span class="num" id="mf">—</span></p></div>':'')+
'<p><b>Source.</b> <a target="_blank" rel="noopener"></a> <span class="ml"></span></p><p><b>Share:</b> <a class="sl"></a></p><p class="shr"><button id="cp">Copy link</button><a class="btn" target="_blank" rel="noopener" id="px">Post on X</a><a class="btn" target="_blank" id="pi">Share image</a></p><p><button id="cl">Close</button></p>';
dlg.querySelector('h3').textContent=d.l;dlg.querySelector('.mo').textContent=d.o||'';dlg.querySelector('.mm').textContent=d.m||'';const a=dlg.querySelector('p a');a.href=d.u;a.textContent=d.s;dlg.querySelector('.ml').textContent=d.loc?'('+d.loc+')':'';
const sl=dlg.querySelector('.sl');sl.href=d.share;sl.textContent=d.share;dlg.querySelector('#px').href=x;dlg.querySelector('#pi').href=d.img;
const mv=dlg.querySelector('#mv'),mf=dlg.querySelector('#mf');mt=t=>{{const v=d.r?d.b+d.r*(t-d.t0):null;mv.textContent=v==null?(d.o||'').split(' ')[0]:usd(v);if(mf)mf.textContent=usd(d.b)+' + '+usd(d.r,4)+' × '+nf0.format(Math.round(t-d.t0))+' s = '+usd(v)}};
dlg.querySelector('#cl').onclick=()=>dlg.close();dlg.querySelector('#cp').onclick=()=>navigator.clipboard&&navigator.clipboard.writeText(d.share);dlg.showModal()}}
dlg.addEventListener('close',()=>mt=null);document.querySelectorAll('[data-d]').forEach(e=>e.onclick=()=>open(e));
(function f(){{const t=now(),x=tot(t);if(R){{hv.textContent=usd(x);if(hs)hs.textContent=(R<0?'':'+')+usd(Math.abs(x-tot(OPENED)));if(wcn)wcn.textContent=short(x);if(wcd)wcd.textContent=sg(x-B)+short(Math.abs(x-B));pps.forEach(e=>e.textContent=usd(x/+e.dataset.pp,e.closest('.hero')?2:0));
ticks.forEach(k=>{{const v=k.b+k.r*(t-k.t);k.v.textContent=k.pp?usd(v,2):usd(v);k.ppx.forEach(e=>e.textContent=usd(v/+e.dataset.pp,2))}})}}if(mt)mt(t);requestAnimationFrame(f)}})()}})()</script>"""

    page = (meta_head(SITE, url, title, desc, img, 2, PL_CSS, ld) + header + intro + '<main id="app">' + hero + wc + debt_sec + comp_secs + people + hist + details + method
            + '</main><dialog id="dlg"></dialog>' + links + '<footer class="site-foot">Every Debt Clock · official data, projection labelled · <a href="../../privacy.html">Privacy</a></footer>' + script + "</body></html>")
    os.makedirs(f"{R}/{sec_dir}/{p['slug']}", exist_ok=True)
    open(f"{R}/{sec_dir}/{p['slug']}/index.html", "w").write(with_analytics(page))
    _cur({})
    return url

def index_page(R, SITE, with_analytics, PAGE_CSS, ANS_CSS, kind, sec_dir, lab, desc_, live, places, now):
    """Hub of every live place (all kinds), driven by the same index as api/places.json. /states/ is the main hub;
    /countries/ (once a country is live) gets the same hub with countries first. Tiles tick; a sort control reorders them client-side."""
    url = f"{SITE}/{sec_dir}/"
    ix = index(places, now)["places"]
    up = "../"
    order = sorted(SECTIONS, key=lambda s_: s_[0] != kind)
    secs = ""
    for k, d, lab_, desc2 in order:
        items = [x for x in ix if x["kind"] == k]
        tiles = ""
        for x in items:
            _cur({"currency": {"symbol": x["sym"]}})
            v = x["base"] + x["rate"] * (now - x["t0"])
            tiles += (f'<a class="tile hubt" href="{up}{x["url"]}" style="--acc:var(--red);display:block;color:inherit" data-name="{E(x["name"])}" data-b="{x["base"]}" data-r="{x["rate"]}" data-t="{x["t0"]}" data-pop="{x["population"]}" data-sym="{E(x["sym"])}">'
                      f'<div class="lab"><span>{E(x["name"])}</span><span>{E(x["label"])}</span></div>'
                      f'<div class="val num">{_usd0(v)}</div><div class="pp"><div><span class="l">Per {E(x["demonym"])}</span><span class="num hpp">{_usd2(v / x["population"])}</span></div>'
                      f'<div><span class="l">Official total</span><span class="num">{_short(x["base"])}</span></div></div>'
                      f'<div class="meta"><span class="rate{" up" if x["rate"] > 0 else ""}">{_rate_txt(x["rate"]) if x["rate"] else "official"}</span>'
                      f'<span class="badge {"proj" if x["rate"] else "fix"}">{"PROJECTED" if x["rate"] else "OFFICIAL"} · from {_fd(x["base_date"])}</span></div></a>')
        _cur({})
        if not items: continue
        secs += (f'<section id="{d}"><div class="sh"><span class="bar" style="background:var(--red)"></span><h2>{E(lab_)}</h2>'
                 f'<span class="h2n">{len(items)} live</span></div><div class="grid hub">{tiles}</div></section>')
    names = ", ".join(x["name"] for x in ix)
    title = f"{lab} Debt Clocks | Every Debt Clock"
    desc = f"{desc_}: live clocks projected from official government debt figures, with sources. Now live: {names}."
    header = (f'<header class="top"><div class="topin"><a class="brand" href="../">EVERY <b>DEBT</b> CLOCK</a>{nav_html(places, 1, kind, "plnav")}'
              f'<span class="live"><span class="dot"></span><span>official data</span></span></div></header>')
    sort = ('<div class="hubsort"><label>Sort <select id="hsort"><option value="name">A–Z</option><option value="total">Total debt</option>'
            '<option value="pp">Debt per resident</option></select></label></div>')
    script = """<script>(function(){const nf0=new Intl.NumberFormat('en-US',{maximumFractionDigits:0}),nf2=new Intl.NumberFormat('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
const usd=(v,d,c)=>(v<0?'−':'')+(c||'$')+(d?nf2:nf0).format(Math.abs(v)),T=[...document.querySelectorAll('.hubt')].map(e=>({e,v:e.querySelector('.val'),p:e.querySelector('.hpp'),b:+e.dataset.b,r:+e.dataset.r,t:+e.dataset.t,pop:+e.dataset.pop,c:e.dataset.sym}));
const val=k=>k.b+k.r*(Date.now()/1000-k.t);document.getElementById('hsort').onchange=ev=>{const m=ev.target.value;document.querySelectorAll('.grid.hub').forEach(g=>{const ts=T.filter(k=>k.e.parentNode===g);
ts.sort((a,b)=>m==='name'?a.e.dataset.name.localeCompare(b.e.dataset.name):m==='total'?val(b)-val(a):val(b)/b.pop-val(a)/a.pop);ts.forEach(k=>g.appendChild(k.e))})};
(function f(){T.forEach(k=>{if(!k.r)return;const v=val(k);k.v.textContent=usd(v,0,k.c);k.p.textContent=usd(v/k.pop,2,k.c)});requestAnimationFrame(f)})()})()</script>"""
    body = (f'{header}<section class="intro"><div class="crumb"><a href="../">← US national debt clock</a></div><h1>{E(hub_label(places)[0].upper() + hub_label(places)[1:])}</h1><p>Every place with a live clock, built from figures its own government publishes. Each clock shows who publishes the numbers and how often, '
            f'with every number linked to its source. Most of these governments report their debt once a year or once a month, so the ticking numbers are labelled projections from the latest official figures. Each tile says what it counts: some states publish state and local debt together, others only state debt, and countries are shown in their own currency.</p></section>'
            f'<main id="app">{sort}{secs}</main>'
            f'<section class="answers"><ul><li><a href="../">US national debt clock</a></li><li><a href="../api/places.json">All places as JSON</a></li></ul></section><footer class="site-foot">Every Debt Clock · <a href="../privacy.html">Privacy</a></footer>{script}</body></html>')
    hub_css = PL_CSS + ".hubsort{display:flex;justify-content:flex-end;margin:4px 2px -14px;font-size:12px;color:var(--mut)}.hubsort select{margin-left:6px;background:var(--panel2);color:var(--txt);border:1px solid var(--line);border-radius:8px;padding:4px 8px;font:inherit;font-size:12px}.tile.hubt .lab span:last-child{font-size:11px;color:var(--dim)}"
    page = meta_head(SITE, url, title, desc, "og/home.png", 1, hub_css) + body
    os.makedirs(f"{R}/{sec_dir}", exist_ok=True)
    open(f"{R}/{sec_dir}/index.html", "w").write(with_analytics(page))
    return url
