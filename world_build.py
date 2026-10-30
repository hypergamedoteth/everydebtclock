"""World Debt Clock (/world/): the latest published government debt of every country with a live clock on this site
(the US national debt plus every places/*.json with kind "country" and status "live"), converted to US dollars at
an official daily reference rate. Called from build.py. Adding a country is a data file; it shows up here on the next build.

Inputs written by pipeline/fetch_world.py: data/world_fx.json (ECB reference rates, Bank of Russia USD/RUB) and
data/world_gdp.json (IMF WEO NGDPD, current year). It is a sum of different measures on different dates, never "total world debt".
Ticking: each country's own projected trend (the rate its own page uses), converted at the same fixed daily rate."""
import json, os, html, datetime as dt
import places_build as pb

E = html.escape
# Fallback ISO 3166 alpha-2 -> alpha-3 for places/*.json that do not carry "iso3" (needed to match the IMF GDP table).
ISO3 = {"US": "USA", "CA": "CAN", "MX": "MEX", "SG": "SGP", "GB": "GBR", "DE": "DEU", "JP": "JPN", "CN": "CHN", "IN": "IND", "FR": "FRA", "RU": "RUS",
        "IT": "ITA", "BR": "BRA", "KR": "KOR", "AU": "AUS", "ES": "ESP", "NL": "NLD", "CH": "CHE", "TR": "TUR", "ID": "IDN", "SA": "SAU", "AR": "ARG",
        "ZA": "ZAF", "PL": "POL", "SE": "SWE", "BE": "BEL", "NO": "NOR", "AT": "AUT", "IE": "IRL", "IL": "ISR", "PT": "PRT", "GR": "GRC", "DK": "DNK",
        "FI": "FIN", "NZ": "NZL", "CZ": "CZE", "HK": "HKG", "TH": "THA", "MY": "MYS", "PH": "PHL", "NG": "NGA", "EG": "EGY", "CL": "CHL", "CO": "COL", "TW": "TWN", "AE": "ARE", "QA": "QAT", "KW": "KWT", "OM": "OMN",
        "BH": "BHR", "MA": "MAR", "DZ": "DZA", "TN": "TUN", "LY": "LBY", "KE": "KEN", "ET": "ETH", "AO": "AGO", "GH": "GHA"}
# Currencies officially pegged to the US dollar: the central bank's fixed rate (no daily rate to fetch).
PEGS = {"SAR": (3.75, "Saudi Central Bank (SAMA), official peg of the riyal to the US dollar"),
        "QAR": (3.64, "Qatar Central Bank, official peg of the riyal to the US dollar")}
US_URL = "https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/debt-to-the-penny"

def _load(path):
    try: return json.load(open(path))
    except Exception: return {}

def usd_per_unit(code, fx):
    """(USD per one unit of currency, rate date, source name, quote as published) or None when no official daily rate is stored."""
    if code == "USD": return 1.0, None, "US dollar", "1"
    ecb, cbr = fx.get("ecb") or {}, fx.get("cbr") or {}
    if code == "RUB" and cbr.get("rub_per_usd"): return 1.0 / cbr["rub_per_usd"], cbr["date"], cbr["source"], f"{cbr['rub_per_usd']:g} RUB per USD"
    fed = fx.get("fed") or {}
    if code in (fed.get("per_usd") or {}): return 1.0 / fed["per_usd"][code], (fed.get("dates") or {}).get(code, fed["date"]), fed["source"], f"{fed['per_usd'][code]:g} {code} per USD"
    ust = fx.get("ust") or {}
    if code in (ust.get("per_usd") or {}): return 1.0 / ust["per_usd"][code], (ust.get("dates") or {}).get(code, ust["date"]), ust["source"], f"{ust['per_usd'][code]:g} {code} per USD"
    if code in PEGS: v, who = PEGS[code]; return 1.0 / v, None, who, f"pegged: {v:g} {code} per USD"
    pe = ecb.get("per_eur") or {}
    if code == "EUR" and pe.get("USD"): return pe["USD"], ecb["date"], ecb["source"], f"{pe['USD']:g} USD per EUR"
    if code in pe and pe.get("USD"): return pe["USD"] / pe[code], ecb["date"], ecb["source"], f"{pe['USD']:g} USD and {pe[code]:g} {code} per EUR"
    return None

def compute(R, places, us, now):
    """The world table, or None when there is nothing to show. us = dict(official, date, base, rate, t0, pop, pop_date)."""
    countries = [p for p in places if p["kind"] == "country"]
    if not countries: return None
    fx, gdp = _load(f"{R}/data/world_fx.json"), _load(f"{R}/data/world_gdp.json")
    rows, skipped = [], []
    rows.append({"slug": "united-states", "name": "United States", "url": "", "code": "USD", "iso3": "USA", "local": us["official"], "as_of": us["date"],
                 "measure": "Total public debt outstanding, gross (includes intragovernmental holdings)", "rate": 1.0, "rate_date": None, "rate_src": "US dollar", "quote": "1",
                 "pop": us["pop"], "pop_date": us["pop_date"], "trend_local": us["rate"], "trend_from": None, "trend_note": "Treasury's 90-day trend of Debt to the Penny", "now_local": us["base"], "source": "Treasury, Debt to the Penny", "source_url": US_URL})
    for p in sorted(countries, key=lambda x: x["name"]):
        c = pb.calc(p); code = (p.get("currency") or {}).get("code", "")
        r = usd_per_unit(code, fx)
        if not r: skipped.append((p["name"], code)); continue
        rate = c["rate"] or 0
        cs = p["components"]
        rows.append({"slug": p["slug"], "name": p["name"], "url": f"countries/{p['slug']}/", "code": code, "iso3": p.get("iso3") or ISO3.get(p.get("country", "")), "local": c["total"], "as_of": c["as_of"],
                     "measure": p.get("world_measure") or p["headline_long"].capitalize(), "rate": r[0], "rate_date": r[1], "rate_src": r[2], "quote": r[3],
                     "pop": p["population"]["value"], "pop_date": p["population"]["as_of"], "trend_local": rate,
                     "trend_from": (cs[0].get("prior_as_of") if rate else None), "trend_note": None, "now_local": c["total"] + rate * (now - c["t0"]),
                     "source": p.get("publisher", ""), "source_url": cs[0]["source_url"]})
    for x in rows:
        x["usd"] = x["local"] * x["rate"]; x["now_usd"] = x["now_local"] * x["rate"]; x["rate_usd_s"] = x["trend_local"] * x["rate"]
        x["per_person"] = x["usd"] / x["pop"]
    rows.sort(key=lambda x: -x["usd"])
    total = sum(x["usd"] for x in rows)
    for x in rows: x["share"] = x["usd"] / total * 100
    cov = None
    if gdp.get("world") and gdp.get("countries"):
        gs = {x["iso3"]: gdp["countries"].get(x["iso3"]) for x in rows}
        matched = [k for k, v in gs.items() if v]
        for x in rows: x["gdp_bn"] = gs.get(x["iso3"])
        num = sum(gs[k] for k in matched)
        cov = {"pct": num / gdp["world"] * 100, "gdp_bn": num, "world_bn": gdp["world"], "year": gdp["year"], "n": len(rows), "unmatched": [x["name"] for x in rows if not x.get("gdp_bn")],
               "source": gdp["source"], "source_url": gdp["source_url"], "fetched": gdp.get("fetched")}
    return {"rows": rows, "skipped": skipped, "total": total, "now_total": sum(x["now_usd"] for x in rows), "rate_s": sum(x["rate_usd_s"] for x in rows),
            "pop": sum(x["pop"] for x in rows), "cov": cov, "fx": fx, "gdp": gdp, "t0": now, "now": now}

# ------------------------------------------------------------------ formatting
def _tn(x): return f"${x/1e12:,.2f} trillion"
def _bn(x, code=None): return (f"{code} " if code else "") + f"{x/1e9:,.1f} bn"
def _usd0(x): return f"${x:,.0f}"
def _fd(s): return pb._fd(s)
def cov_line(W):
    cv = W["cov"]
    if not cv: return f"{len(W['rows'])} countries. IMF GDP weights are not available right now, so no GDP coverage is shown."
    return f"{cv['n']} countries covering {cv['pct']:.1f}% of world GDP"

def api_json(W, SITE, now):
    cv = W["cov"]; fx = W["fx"]
    return {"_doc": "World Debt Clock inputs and result. The sum of the latest published government debt of the countries listed (different measures, different dates), in US dollars at the stated official reference rates. Not the total debt of the world. projected_now = sum of each country's official figure + its own trend, at the fixed rate shown.",
            "generated": dt.datetime.fromtimestamp(now, pb.CT).isoformat(timespec="seconds"), "url": f"{SITE}/world/",
            "countries_count": len(W["rows"]), "total_official_usd": round(W["total"]), "total_projected_now_usd": round(W["now_total"]), "rate_usd_per_sec": round(W["rate_s"], 2),
            "population_sum": round(W["pop"]), "per_person_usd": round(W["total"] / W["pop"], 2),
            "gdp_coverage": ({"pct": round(cv["pct"], 2), "countries_gdp_usd_bn": round(cv["gdp_bn"], 3), "world_gdp_usd_bn": cv["world_bn"], "year": cv["year"], "source": cv["source"], "source_url": cv["source_url"], "unmatched": cv["unmatched"]} if cv else None),
            "fx": {"ecb_date": (fx.get("ecb") or {}).get("date"), "bank_of_russia_date": (fx.get("cbr") or {}).get("date")},
            "not_converted": [{"name": n, "currency": c} for n, c in W["skipped"]],
            "countries": [{"slug": x["slug"], "name": x["name"], "currency": x["code"], "debt_local_official": round(x["local"]), "as_of": x["as_of"], "measure": x["measure"],
                           "usd_per_unit": x["rate"], "fx_date": x["rate_date"], "fx_source": x["rate_src"], "debt_usd": round(x["usd"]), "share_pct": round(x["share"], 3),
                           "population": x["pop"], "population_as_of": x["pop_date"], "debt_per_person_usd": round(x["per_person"], 2), "trend_usd_per_sec": round(x["rate_usd_s"], 2),
                           "gdp_usd_bn": x.get("gdp_bn"), "url": f"{SITE}/{x['url']}"} for x in W["rows"]]}

CSS = """.wt{width:100%;border-collapse:collapse;font-size:13.5px;min-width:900px}.wt th,.wt td{border-bottom:1px solid var(--line);padding:8px 9px;text-align:left;vertical-align:top}
.wt th{color:var(--mut);font-weight:600;font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;white-space:nowrap}.wt td.num,.wt th.num{text-align:right;font-family:ui-monospace,Menlo,monospace;white-space:nowrap}
.wt td.m{color:var(--mut);font-size:12.5px;min-width:190px}.wt tr.tot td{font-weight:700;border-top:2px solid var(--line)}.wt a{color:var(--blue)}.wt td.c{min-width:130px}
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--line);border-radius:12px;padding:0 4px}.cvl{font-size:15px;margin:2px 0 14px}.cvl b{color:var(--txt)}
.wsec{margin:0 0 26px}.wnote{border:1px solid #5a3a12;background:#20170a;color:#ffb547;border-radius:10px;padding:10px 12px;font-size:13.5px;margin:0 0 18px}
@media (max-width:640px){.wt{font-size:13px}.wt td.m{min-width:170px}
.wt.wstk,.wt.wstk tbody{display:block;min-width:0!important;width:100%}.wt.wstk tr.hd{display:none}.wt.wstk tr{display:block;border-bottom:1px solid var(--line);padding:8px 2px}.wt.wstk tr:last-child{border-bottom:0}
.wt.wstk td{display:flex;justify-content:space-between;gap:14px;border:0;padding:3px 8px;text-align:right;white-space:normal;min-width:0!important}.wt.wstk td:before{content:attr(data-l);color:var(--mut);font-size:11.5px;text-transform:uppercase;letter-spacing:.04em;text-align:left;flex:none}
.wt.wstk td.c{display:block;text-align:left;font-size:15px;padding-bottom:5px}.wt.wstk td.c:before,.wt.wstk td.nm{display:none}.wt.wstk td.m{color:var(--mut)}}"""

def build(R, SITE, with_analytics, og, stamp, now, places, W):
    if not W: return []
    rows, cv = W["rows"], W["cov"]; n = len(rows)
    url = f"{SITE}/world/"
    title = f"World Debt Clock: Live Government Debt of {n} Countries"
    covtxt = f", covering {cv['pct']:.0f}% of world GDP" if cv else ""
    desc = f"Government debt of {n} countries in US dollars: {_tn(W['total'])} on the latest official figures{covtxt}. Measure, date and source for each."
    big_now = W["now_total"]
    os.makedirs(f"{R}/api", exist_ok=True)
    json.dump(api_json(W, SITE, now), open(f"{R}/api/world.json", "w"), indent=1)
    img = "og/places/world.png"
    if og:
        og(f"{R}/{img}", f"World debt clock · {n} countries · ticking live", _usd0(big_now),
           [("Countries", f"{n}" + (f" · {cv['pct']:.1f}% of world GDP" if cv else "")), ("Latest official sum", _usd0(W["total"]))],
           f"+${W['rate_s'] * 86400 / 1e9:,.1f}B/day",
           "#ff4d5e", "Sum of each country's latest published government debt\nin US dollars · measures and dates differ")
    names = [x["name"] for x in rows]
    ld = '<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "Dataset", "name": f"Government debt of {n} countries in US dollars", "description": desc, "url": url, "isAccessibleForFree": True,
        "creator": {"@type": "Organization", "name": "Every Debt Clock", "url": SITE + "/"}, "temporalCoverage": f"{min(x['as_of'] for x in rows)}/{max(x['as_of'] for x in rows)}",
        "isBasedOn": sorted({x["source_url"] for x in rows} | ({cv["source_url"]} if cv else set()) | {"https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html"})}).replace("</", "<\\/") + "</script>"

    # ---- header / intro / hero
    jump = [("total", "Total"), ("table", "By country"), ("measures", "Measures"), ("rates", "Exchange rates"), ("method", "Method")]
    header = (f'<header class="top"><div class="topin"><a class="brand" href="../">EVERY <b>DEBT</b> CLOCK</a>{pb.nav_html(places, 1, "world", "plnav")}'
              f'<span class="live"><span class="dot"></span><span>official data</span></span></div>'
              f'<nav class="jump">' + "".join(f'<a href="#{i}">{E(t)}</a>' for i, t in jump) + "</nav></header>")
    covsent = (f'<p class="cvl" id="coverage"><b>{cv["n"]} countries covering {cv["pct"]:.1f}% of world GDP.</b> Their {cv["year"]} GDP is {_tn(cv["gdp_bn"] * 1e9)} of an estimated {_tn(cv["world_bn"] * 1e9)} for the world '
               f'(<a href="{E(cv["source_url"])}" rel="noopener">IMF World Economic Outlook</a>, current US dollars, estimates). Not every country is included, so this is not the total debt of the world.</p>'
               if cv else '<p class="cvl" id="coverage"><b>GDP coverage is unavailable right now.</b> The IMF figures could not be read on the last refresh.</p>')
    crumb = '<div class="crumb"><a href="../">← US national debt clock</a><span>·</span><a href="../countries/">All country debt clocks</a><span>·</span><a href="../states/">All US state debt clocks</a></div>'
    intro = (f'<section class="intro" id="intro">{crumb}<h1>World Debt Clock</h1>'
             f'<p>This adds up the latest published government debt of {n} countries that have a clock on this site, in US dollars: <b>{_usd0(W["total"])}</b> ({_tn(W["total"])}). '
             f'It is the US national debt plus {n - 1} other countries. Each country reports a different measure on a different date, so the sum is a comparison of what is published, not one agreed worldwide figure. '
             f'Each figure is converted at an official reference rate (daily where the central banks publish one; see Exchange rates). The live number below projects each country\'s own debt forward at the trend its own page uses.</p></section>')
    hero_dlg = ""
    hero = (f'<div class="hero lead" id="total" data-b="{big_now:.2f}" data-r="{W["rate_s"]:.6f}" data-t="{now:.0f}" style="cursor:default">'
            f'<div class="k">Government debt of {n} countries · in US dollars · live</div><div class="big num" id="hv">{_usd0(big_now)}</div>'
            f'<div class="sub"><span>+${W["rate_s"]:,.0f}/sec · +${W["rate_s"] * 86400 / 1e9:,.1f} billion/day</span>'
            f'<span class="note">sum of each country\'s own projected trend; a projection, not an official figure</span>'
            f'<span>Since you opened this page: <span class="num" id="hs">$0</span> more debt</span></div>'
            f'<div class="trio"><div><span class="l">Latest official sum</span><span class="num">{_usd0(W["total"])}</span></div>'
            f'<div><span class="l">Countries</span><span class="num">{n}</span></div>'
            f'<div><span class="l">Per resident of these countries</span><span class="num" id="hpp" data-pp="{W["pop"]}">${big_now / W["pop"]:,.2f}</span></div></div>'
            f'<div class="meta" style="margin-top:10px"><span class="badge proj">PROJECTED · latest official figures</span><span class="badge">sources linked per country</span></div></div>')
    fxd = {x["rate_date"] for x in rows if x["rate_date"]}
    # ---- table
    body = ""
    for x in rows:
        loc = f'{E(x["code"])} {x["local"]/1e9:,.1f}bn' if x["code"] != "USD" else f'${x["local"]/1e9:,.1f}bn'
        link = f'<a href="../{x["url"]}">{E(x["name"])} debt clock</a>' if x["url"] else '<a href="../">United States debt clock</a>'
        body += (f'<tr><td class="c"><b>{E(x["name"])}</b><br>{link}</td><td class="num" data-l="Debt, local currency" title="{x["local"]:,.0f} {E(x["code"])}">{loc}</td><td class="num" data-l="USD equivalent" title="${x["usd"]:,.0f}">${x["usd"]/1e12:,.3f}tn</td>'
                 f'<td class="num" data-l="Share of sum">{x["share"]:.1f}%</td><td class="num" data-l="Per person (USD)">${x["per_person"]:,.0f}</td><td class="m" data-l="Measure">{E(x["measure"])}</td><td data-l="As of">{E(_fd(x["as_of"]))}</td></tr>')
    body += (f'<tr class="tot"><td class="c">Sum, {n} countries</td><td class="num nm">—</td><td class="num" data-l="USD equivalent" title="${W["total"]:,.0f}">${W["total"]/1e12:,.3f}tn</td><td class="num" data-l="Share of sum">100%</td>'
             f'<td class="num" data-l="Per person (USD)">${W["total"]/W["pop"]:,.0f}</td><td class="m" data-l="Measure">Mixed measures, see below</td><td data-l="As of">Mixed dates</td></tr>')
    table = (f'<section id="table" class="wsec"><div class="sh"><span class="bar" style="background:var(--red)"></span><h2>By country</h2><span class="h2n">Latest official figures, largest first · hover or tap a figure for the full number</span></div>'
             f'<div class="tw"><table class="wt wstk"><tr class="hd"><th>Country</th><th class="num">Debt, local currency</th><th class="num">USD equivalent</th><th class="num">Share of sum</th><th class="num">Per person (USD)</th><th>Measure</th><th>As of</th></tr>{body}</table></div>'
             f'<p class="dnote">USD equivalent = official local-currency figure × the exchange rate in the table below. Share = country ÷ sum. Per person = USD equivalent ÷ the population shown in the method section. The ticking number above projects these figures forward; this table does not tick.</p></section>')
    # ---- measures
    meas = (f'<section id="measures" class="wsec"><div class="sh"><span class="bar" style="background:var(--amber)"></span><h2>Measures and dates differ</h2></div>'
            f'<div class="wnote">These are not like-for-like. The Measure column says what each country counts: some are gross and some are net of assets, some are central government only and some cover the whole general government. ' + ("Russia\'s covers internal debt only, so it leaves out external debt. " if any(x["slug"] == "russia" for x in rows) else "") +
            f'The US figure is gross and includes debt the government owes to its own trust funds. Dates run from {E(_fd(min(x["as_of"] for x in rows)))} to {E(_fd(max(x["as_of"] for x in rows)))}, because each government publishes on its own schedule.</div>'
            '<p class="dnote">Each country\'s own page explains its measure, what it includes and leaves out, and links its source. Countries with a clock on this site are added here automatically.</p></section>')
    # ---- fx
    seen, fr = set(), ""
    for x in rows:
        if x["code"] in seen or x["code"] == "USD": continue
        seen.add(x["code"])
        fr += f'<tr><td class="c"><b>{E(x["code"])}</b></td><td class="num" data-l="Rate as published">{E(x["quote"])}</td><td class="num" data-l="USD per 1 unit">{x["rate"]:.6f}</td><td data-l="Rate date">{E(_fd(x["rate_date"]) if x["rate_date"] else "fixed peg")}</td><td class="m" data-l="Source">{E(x["rate_src"])}</td></tr>'
    rates = (f'<section id="rates" class="wsec"><div class="sh"><span class="bar" style="background:var(--teal)"></span><h2>Exchange rates used</h2><span class="h2n">Official reference rates, refreshed with the daily data update</span></div>'
             f'<div class="tw"><table class="wt wstk" style="min-width:640px"><tr class="hd"><th>Currency</th><th class="num">Rate as published</th><th class="num">USD per 1 unit</th><th>Rate date</th><th>Source</th></tr>{fr}</table></div>'
             '<p class="dnote">Euro reference rates come from the <a href="https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html" rel="noopener">European Central Bank</a>; other currencies are converted through the euro rate (USD per unit = USD per EUR ÷ units per EUR). '
             'The ECB does not publish a rouble rate, so Russia uses the <a href="https://www.cbr.ru/eng/currency_base/daily/" rel="noopener">Bank of Russia official rate</a>. Taiwan uses the Federal Reserve H.10 weekly rate. The Egyptian pound, Ghanaian cedi, Kenyan shilling and Nigerian naira have no ECB or Fed rate, so they use the US Treasury Reporting Rates of Exchange, which is published quarterly (the date of each rate is in the table; these currencies can move a lot between quarter-ends). Currencies pegged to the dollar use the central bank\'s fixed rate. The rate is held fixed between updates: the clock does not project exchange-rate moves.</p></section>')
    # ---- method
    mrows = ""
    for x in rows:
        tr = (f'{x["rate_usd_s"]:,.2f}' if x["rate_usd_s"] else "0 (fixed)")
        mrows += (f'<tr><td class="c"><b>{E(x["name"])}</b></td><td class="num" data-l="Population">{x["pop"]:,.0f}</td><td data-l="Population date">{E(_fd(x["pop_date"]))}</td><td class="num" data-l="Trend, USD per sec">${tr}</td>'
                  f'<td class="m" data-l="Trend basis">{E(("Official change " + _fd(x["trend_from"]) + " to " + _fd(x["as_of"])) if x["trend_from"] else (x["trend_note"] or "No trend: figure shown fixed"))}</td>'
                  f'<td class="m" data-l="Source"><a href="{E(x["source_url"])}" rel="noopener">{E(x["source"] or "Source")}</a></td></tr>')
    mt = (f'<table class="wt wstk" style="min-width:760px"><tr class="hd"><th>Country</th><th class="num">Population</th><th>Population date</th><th class="num">Trend, USD per sec</th><th>Trend basis</th><th>Source</th></tr>{mrows}</table>')
    skipped = (f'<p><b>Not converted.</b> No official daily rate is stored for: ' + ", ".join(f"{E(a)} ({E(b)})" for a, b in W["skipped"]) + '. They are left out of the sum until a rate is available.</p>' if W["skipped"] else "")
    unm = (f'<p><b>GDP.</b> No IMF GDP figure matched: ' + ", ".join(E(u) for u in cv["unmatched"]) + '. They are left out of the coverage percentage.</p>' if cv and cv["unmatched"] else "")
    method = (f'<section id="method" class="wsec"><div class="sh"><span class="bar" style="background:var(--mut)"></span><h2>How it works</h2><span class="h2n">Official figures · projection labelled · sources linked</span></div><div class="sk foot">'
              f'<p><b>The sum.</b> For each country, its latest official debt figure in local currency × the USD exchange rate on the rate date. The United States uses Treasury\'s Debt to the Penny, and every other country uses the figure on its own page. The sum is {_usd0(W["total"])}. '
              f'It is not the total debt of the world: only the {n} countries listed are included, they use different measures, and the dates differ.</p>'
              f'<p><b>The live number</b> = Σ (official figure + that country\'s trend × seconds since its figure) × exchange rate. Each trend is the one that country\'s own clock uses: the official change over its latest 12 months, spread evenly (the US uses Treasury\'s 90-day trend). '
              f'Governments report once a month, once a quarter or daily, so the live number is a projection, not an official figure, and it re-bases whenever a country publishes a new one. '
              f'The combined rate is ${W["rate_s"]:,.2f} per second. Exchange rates are held fixed.</p>'
              + (f'<p><b>GDP coverage.</b> The {cv["n"]} countries\' {cv["year"]} GDP in current US dollars ({_usd0(cv["gdp_bn"] * 1e9)}) ÷ the IMF\'s world aggregate ({_usd0(cv["world_bn"] * 1e9)}) = {cv["pct"]:.2f}%. '
                 f'Source: <a href="{E(cv["source_url"])}" rel="noopener">{E(cv["source"])}</a>, fetched with the daily data refresh{(", last read " + E(_fd(cv["fetched"]))) if cv.get("fetched") else ""}. These are IMF estimates for the current year, not final statistics.</p>' if cv else '')
              + f'<p><b>Per person</b> = USD equivalent ÷ each country\'s official population estimate on the date shown (not projected). The total row divides the sum by the sum of those populations.</p>'
              + skipped + unm + f'<div class="tw"><div style="min-width:0">{mt}</div></div>'
              f'<p>Machine-readable: <a href="../api/world.json">/api/world.json</a>. Page built {E(stamp)}.</p></div></section>')
    links = ('<section class="answers" id="answers"><div class="sh"><h2>More clocks</h2></div><ul><li><a href="../">US national debt clock</a></li><li><a href="../countries/">All country debt clocks</a></li>'
             '<li><a href="../states/">All US state debt clocks</a></li><li><a href="../api/world.json">World debt clock as JSON</a></li></ul><div class="sh"><h2>Countries in the sum</h2></div><ul>'
             + "".join(f'<li><a href="../{x["url"]}">{E(x["name"])} debt clock</a></li>' for x in sorted(rows, key=lambda r: r["name"])) + '</ul></section>')
    script = """<script>(function(){const nf0=new Intl.NumberFormat('en-US',{maximumFractionDigits:0}),nf2=new Intl.NumberFormat('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
const H=document.getElementById('total'),B=+H.dataset.b,R=+H.dataset.r,T0=+H.dataset.t,hv=document.getElementById('hv'),hs=document.getElementById('hs'),hpp=document.getElementById('hpp'),OPENED=Date.now()/1000;
const tot=t=>B+R*(t-T0);(function f(){const t=Date.now()/1000,x=tot(t);hv.textContent='$'+nf0.format(x);hs.textContent='$'+nf0.format(R*(t-OPENED));hpp.textContent='$'+nf2.format(x/+hpp.dataset.pp);requestAnimationFrame(f)})()})()</script>"""
    page = (pb.meta_head(SITE, url, title, desc, img, 1, pb.PL_CSS + CSS, ld) + header + intro + '<main id="app">' + hero + covsent + table + meas + rates + method + '</main>' + links
            + '<footer class="site-foot">Every Debt Clock · official data, projection labelled · <a href="../methodology/">Methodology</a> · <a href="../privacy.html">Privacy</a> · Independent site, not affiliated with any government. Not financial advice.</footer>' + script + "</body></html>")
    os.makedirs(f"{R}/world", exist_ok=True)
    open(f"{R}/world/index.html", "w").write(with_analytics(page))
    return [url]
