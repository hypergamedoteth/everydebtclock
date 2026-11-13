"""World Debt Clock (/world/): every IMF economy, each on the most precise stock available.

Order: a live national or Eurostat clock, then a World Bank / IMF QPSD quarterly stock within 25% of the IMF
figure, then the IMF World Economic Outlook interpolation. One row per economy. Called from build.py.

Ticking: each country's own trend where a year-ago official stock exists, otherwise that country's IMF interpolation.
"""
import json, os, html, datetime as dt
import places_build as pb
import explore as ex

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

def _imf_row(e, now, anchor_ts):
    projected = e["debt_2025_usd"] + e["rate_usd_per_sec"] * (now - anchor_ts)
    return {"slug": e["slug"], "name": e["name"], "url": f"countries/{e['slug']}/", "code": "USD", "iso3": e["iso3"],
            "local": e["debt_2026_usd"], "as_of": "2026-12-31", "measure": "General government, gross (IMF end-2026 projection)",
            "rate": 1.0, "rate_date": None, "rate_src": "US dollar", "quote": "1", "pop": None, "pop_date": None,
            "trend_local": e["rate_usd_per_sec"], "trend_from": "2025-12-31", "trend_note": "IMF interpolation from end-2025 to end-2026",
            "now_local": projected, "source": "IMF World Economic Outlook, October 2026", "source_url": "https://www.imf.org/external/datamapper/GGXWDG_NGDP@WEO",
            "tier": "imf", "trend_kind": "imf"}

def _qpsd_row(u, now):
    return {"slug": u["slug"], "name": u["name"], "url": f"countries/{u['slug']}/", "code": u["currency"], "iso3": u["iso3"],
            "local": u["local"], "as_of": u["as_of"], "measure": u["measure"], "rate": u["rate"], "rate_date": u["rate_date"],
            "rate_src": u["rate_src"], "quote": u["quote"], "pop": None, "pop_date": None, "trend_local": u["trend_local"],
            "trend_from": u["prior_as_of"], "trend_note": u["trend_note"], "now_local": u["local"] + u["trend_local"] * (now - u["t0"]),
            "source": u["source"], "source_url": u["source_url"], "tier": "harmonized", "trend_kind": u["trend_kind"]}

def _secondary(local, code, rate, as_of, measure, source, source_url):
    return {"local": local, "code": code, "usd": local * rate, "as_of": as_of, "measure": measure,
            "source": source, "source_url": source_url}

def _clock(p, fx, skipped):
    """FX and the place's own stock, or None when the currency cannot be converted."""
    c = pb.calc(p)
    code = (p.get("currency") or {}).get("code", "")
    r = usd_per_unit(code, fx)
    iso = p.get("iso3") or ISO3.get(p.get("country", ""))
    if not r:
        skipped.append((p["name"], code or "?", iso))
        return None
    return {"p": p, "c": c, "code": code, "fx": r, "iso": iso,
            "measure": p.get("world_measure") or (p.get("headline_long") or "").capitalize()}

def compute(R, places, us, now):
    """The world table, or None when there is nothing to show. us = dict(official, date, base, rate, t0, pop, pop_date).

    The headline stock for every economy is general government gross debt. A national or Eurostat figure is the
    headline only when it is that perimeter. A central, federal or otherwise narrower series is kept as official_line
    and the headline falls back to the IMF World Economic Outlook.
    """
    import world_sources
    countries = [p for p in places if p["kind"] == "country"]
    if not countries: return None
    fx, gdp = _load(f"{R}/data/world_fx.json"), _load(f"{R}/data/world_gdp.json")
    weo = _load(f"{R}/data/world_weo_debt.json")
    economies = weo.get("economies") or []
    by_iso = {e["iso3"]: e for e in economies}
    by_place = {}
    for p in countries:
        iso = p.get("iso3") or ISO3.get(p.get("country", ""))
        if iso:
            by_place[iso] = p
    rows, skipped = [], []
    upgrades, rejected = world_sources.qpsd_choice(R, places, fx, economies) if economies else ({}, [])
    anchor = dt.datetime.fromisoformat(weo["anchor"]).timestamp() if weo.get("anchor") else None
    seen = set()

    def add_imf(e, official_line=None):
        row = _imf_row(e, now, anchor)
        row["official_line"] = official_line
        rows.append(row)
        seen.add(e["iso3"])

    if anchor is None:
        return None
    for e in economies:
        iso = e["iso3"]
        p = by_place.get(iso)
        gg = world_sources.gg_from_place(p) if p else None
        bits = _clock(p, fx, skipped) if p else None
        q = upgrades.get(iso)
        if iso == "USA":
            add_imf(e, _secondary(us["official"], "USD", 1.0, us["date"],
                                  "Federal debt, gross (Treasury Debt to the Penny, includes intragovernmental holdings)",
                                  "Treasury, Debt to the Penny", US_URL))
            continue
        if gg and gg.get("use_clock") and bits:
            c, rate = bits["c"], bits["c"]["rate"] or 0
            cs = p["components"]
            rows.append({"slug": p["slug"], "name": p["name"], "url": f"countries/{p['slug']}/", "code": bits["code"], "iso3": iso,
                         "local": c["total"], "as_of": c["as_of"], "measure": gg["measure"], "rate": bits["fx"][0], "rate_date": bits["fx"][1],
                         "rate_src": bits["fx"][2], "quote": bits["fx"][3], "pop": p["population"]["value"], "pop_date": p["population"]["as_of"],
                         "trend_local": rate, "trend_from": (cs[0].get("prior_as_of") if rate else None),
                         "trend_note": "Official general-government change" if rate else "No trend: figure shown fixed",
                         "now_local": c["total"] + rate * (now - c["t0"]), "source": gg["source"], "source_url": gg["source_url"],
                         "tier": gg["tier"], "trend_kind": "official" if rate else "fixed", "official_line": None})
            seen.add(iso)
            continue
        if gg and not gg.get("use_clock") and bits:
            fxr = bits["fx"][0]
            local = gg["local"]
            if gg.get("prior_local") and gg.get("prior_as_of"):
                secs = pb._eod(gg["as_of"]) - pb._eod(gg["prior_as_of"])
                trend_local = (local - gg["prior_local"]) / secs if secs else 0
                trend_kind, trend_from = "official", gg["prior_as_of"]
                trend_note = f"General-government change {gg['prior_as_of']} to {gg['as_of']}"
            else:
                trend_local = e["rate_usd_per_sec"] / fxr
                trend_kind, trend_from = "imf", None
                trend_note = "IMF interpolation; a year-ago general-government stock is not stored"
            t0 = pb._eod(gg["as_of"])
            rows.append({"slug": p["slug"], "name": p["name"], "url": f"countries/{p['slug']}/", "code": bits["code"], "iso3": iso,
                         "local": local, "as_of": gg["as_of"], "measure": gg["measure"], "rate": fxr, "rate_date": bits["fx"][1],
                         "rate_src": bits["fx"][2], "quote": bits["fx"][3], "pop": p["population"]["value"], "pop_date": p["population"]["as_of"],
                         "trend_local": trend_local, "trend_from": trend_from, "trend_note": trend_note,
                         "now_local": local + trend_local * (now - t0), "source": gg["source"], "source_url": gg["source_url"],
                         "tier": gg["tier"], "trend_kind": trend_kind,
                         "official_line": _secondary(bits["c"]["total"], bits["code"], fxr, bits["c"]["as_of"], bits["measure"], p.get("publisher") or "", p["components"][0].get("source_url") or "")})
            seen.add(iso)
            continue
        if q and q.get("for_headline"):
            row = _qpsd_row(q, now)
            row["official_line"] = None
            row["pop"] = None
            rows.append(row)
            seen.add(iso)
            continue
        line = None
        if bits:
            line = _secondary(bits["c"]["total"], bits["code"], bits["fx"][0], bits["c"]["as_of"], bits["measure"], p.get("publisher") or "", p["components"][0].get("source_url") or "")
        elif q and not q.get("for_headline"):
            line = _secondary(q["local"], q["currency"], q["rate"], q["as_of"], q["measure"], q["source"], q["source_url"])
        add_imf(e, line)
    for x in rows:
        x["usd"] = x["local"] * x["rate"]; x["now_usd"] = x["now_local"] * x["rate"]; x["rate_usd_s"] = x["trend_local"] * x["rate"]
        x["per_person"] = (x["usd"] / x["pop"]) if x.get("pop") else None
        e = by_iso.get(x.get("iso3") or "")
        x["imf_debt_2026"] = e["debt_2026_usd"] if e else None
        x["imf_ratio_2026"] = e["ratio_2026"] if e else None
        if x.get("iso3") == "BRA":
            x["published_ratio"] = _pctgdp(by_place.get("BRA"))
        if x["tier"] == "imf":
            x["ratio"] = e["ratio_2026"] if e else None
        elif e and e.get("gdp_2026_usd"):
            x["ratio"] = x["usd"] / e["gdp_2026_usd"] * 100
        else:
            x["ratio"] = None
        x["imf_gap"] = (x["usd"] / e["debt_2026_usd"] - 1) if e and e.get("debt_2026_usd") else None
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
    counts = {k: sum(1 for x in rows if x["tier"] == k) for k in ("official", "harmonized", "imf")}
    review = [x for x in rows if x["tier"] != "imf" and x.get("imf_gap") is not None and abs(x["imf_gap"]) > 0.25]
    panel = weo.get("panel_2026_usd") or 0
    drivers = [x for x in rows if x.get("imf_debt_2026") and abs(x["usd"] - x["imf_debt_2026"]) >= 1e9]
    drivers.sort(key=lambda x: -abs(x["usd"] - x["imf_debt_2026"]))
    return {"rows": rows, "skipped": skipped, "total": total, "now_total": sum(x["now_usd"] for x in rows), "rate_s": sum(x["rate_usd_s"] for x in rows),
            "pop": sum(x["pop"] or 0 for x in rows), "cov": cov, "fx": fx, "gdp": gdp, "t0": now, "now": now,
            "counts": counts, "review": review, "rejected": rejected, "weo": weo, "upgrades": upgrades,
            "drivers": drivers, "gap_vs_imf": (total - panel) if panel else None}

# ------------------------------------------------------------------ formatting
def _tn(x): return f"${x/1e12:,.2f} trillion"
def _bn(x, code=None): return (f"{code} " if code else "") + f"{x/1e9:,.1f} bn"
def _usd0(x): return f"${x:,.0f}"
def _sgn(x, spec=",.0f", unit="", plus=True):
    """Signed dollar amount with the sign before the symbol: +$218.91, −$218.91 (never $-218.91)."""
    return ("+" if x >= 0 and plus else "" if x >= 0 else "−") + f"${abs(x):{spec}}{unit}"
def _fd(s): return pb._fd(s)
def cov_line(W):
    cv = W["cov"]
    if not cv: return f"{len(W['rows'])} countries. IMF GDP weights are not available right now, so no GDP coverage is shown."
    return f"{cv['n']} countries covering {cv['pct']:.1f}% of world GDP"

def api_json(W, SITE, now):
    cv = W["cov"]; fx = W["fx"]; counts = W["counts"]
    return {"_doc": "World Debt Clock. One row per IMF economy. debt_usd is the latest stock used on this page (official, QPSD, or the IMF end-2026 projection). "
            "projected_now sums each row's own trend: the official year-ago change where that stock exists, otherwise the IMF interpolation. "
            "Measures and dates differ. QPSD rows are kept only when they are within 25% of the IMF end-2026 stock.",
            "generated": dt.datetime.fromtimestamp(now, pb.CT).isoformat(timespec="seconds"), "url": f"{SITE}/world/",
            "countries_count": len(W["rows"]), "counts": counts,
            "total_latest_usd": round(W["total"]), "total_projected_now_usd": round(W["now_total"]), "rate_usd_per_sec": round(W["rate_s"], 2),
            "imf_panel_2026_usd": (W.get("weo") or {}).get("panel_2026_usd"),
            "gdp_coverage": ({"pct": round(cv["pct"], 2), "countries_gdp_usd_bn": round(cv["gdp_bn"], 3), "world_gdp_usd_bn": cv["world_bn"], "year": cv["year"], "source": cv["source"], "source_url": cv["source_url"], "unmatched": cv["unmatched"]} if cv else None),
            "fx": {"ecb_date": (fx.get("ecb") or {}).get("date"), "bank_of_russia_date": (fx.get("cbr") or {}).get("date"), "treasury_date": (fx.get("ust_broad") or fx.get("ust") or {}).get("date")},
            "not_converted": [{"name": n, "currency": c, "iso3": iso} for n, c, iso in W["skipped"]],
            "gap_vs_imf_usd": (round(W["gap_vs_imf"]) if W.get("gap_vs_imf") is not None else None),
            "review_over_25pct": [{"iso3": x["iso3"], "name": x["name"], "tier": x["tier"], "measure": x["measure"], "debt_usd": round(x["usd"]), "imf_debt_2026_usd": x["imf_debt_2026"], "gap": round(x["imf_gap"], 4), "source_url": x["source_url"]} for x in W["review"]],
            "gap_drivers": [{"iso3": x["iso3"], "name": x["name"], "tier": x["tier"], "measure": x["measure"], "debt_usd": round(x["usd"]), "imf_debt_2026_usd": x["imf_debt_2026"], "difference_usd": round(x["usd"] - x["imf_debt_2026"])} for x in W.get("drivers") or [] if x["tier"] != "imf"],
            "kept_on_imf": W["rejected"],
            "countries": [{"slug": x["slug"], "name": x["name"], "iso3": x["iso3"], "tier": x["tier"], "currency": x["code"], "debt_local": round(x["local"]), "as_of": x["as_of"], "measure": x["measure"],
                           "usd_per_unit": x["rate"], "fx_date": x["rate_date"], "fx_source": x["rate_src"], "debt_usd": round(x["usd"]), "debt_to_gdp": (round(x["ratio"], 2) if x.get("ratio") is not None else None),
                           "share_pct": round(x["share"], 3), "population": x["pop"], "trend_usd_per_sec": round(x["rate_usd_s"], 2), "trend": x.get("trend_kind"),
                           "source": x["source"], "source_url": x["source_url"], "imf_debt_2026_usd": x.get("imf_debt_2026"),
                           "url": f"{SITE}/{x['url']}" if x["url"] else f"{SITE}/"} for x in W["rows"]]}

TIER = {"official": "Official", "harmonized": "Harmonized", "imf": "IMF estimate"}
CSS = """.wt{width:100%;border-collapse:collapse;font-size:13.5px;min-width:900px}.wt th,.wt td{border-bottom:1px solid var(--line);padding:8px 9px;text-align:left;vertical-align:top}
.wt th{color:var(--mut);font-weight:600;font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;white-space:nowrap}.wt td.num,.wt th.num{text-align:right;font-family:ui-monospace,Menlo,monospace;white-space:nowrap}
.wt td.m{color:var(--mut);font-size:12.5px;min-width:190px}.wt tr.tot td{font-weight:700;border-top:2px solid var(--line)}.wt a{color:var(--blue)}.wt td.c{min-width:130px}
th[data-k]{cursor:pointer}th[data-dir="desc"]::after{content:" ↓"}th[data-dir="asc"]::after{content:" ↑"}
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--line);border-radius:12px;padding:0 4px}.cvl{font-size:15px;margin:2px 0 14px}.cvl b{color:var(--txt)}
.wsec{margin:0 0 26px}.wnote{border:1px solid #5a3a12;background:#20170a;color:#ffb547;border-radius:10px;padding:10px 12px;font-size:13.5px;margin:0 0 18px}
.faq h3{font-size:16px;margin:16px 0 4px}.faq p{margin:0 0 8px}.wt td.c .nat{display:block;color:var(--mut);font-size:12px;font-weight:400;margin-top:3px}
@media (max-width:640px){.wt{font-size:13px}.wt td.m{min-width:170px}
.wt.wstk,.wt.wstk tbody{display:block;min-width:0!important;width:100%}.wt.wstk tr.hd{display:none}.wt.wstk tr{display:block;border-bottom:1px solid var(--line);padding:8px 2px}.wt.wstk tr:last-child{border-bottom:0}
.wt.wstk td{display:flex;justify-content:space-between;gap:14px;border:0;padding:3px 8px;text-align:right;white-space:normal;min-width:0!important}.wt.wstk td:before{content:attr(data-l);color:var(--mut);font-size:11.5px;text-transform:uppercase;letter-spacing:.04em;text-align:left;flex:none}
.wt.wstk td.c{display:block;text-align:left;font-size:15px;padding-bottom:5px}.wt.wstk td.c:before,.wt.wstk td.nm{display:none}.wt.wstk td.m{color:var(--mut)}}"""

def _pctgdp(p):
    if not p:
        return None
    for c in p.get("components") or []:
        for f in c.get("facts") or []:
            if f.get("key") == "pctgdp" and isinstance(f.get("value"), (int, float)):
                return f["value"]
    return None

def _driver_why(x):
    """Why a non-IMF headline differs from the IMF stock. Date and FX only when that is the reason."""
    if x.get("iso3") == "NOR":
        gap = x.get("imf_gap")
        pct = f" ({gap * 100:+.1f}%)" if isinstance(gap, (int, float)) else ""
        return f"Eurostat gov_10q_ggdebt sector S13. The official stock differs from the IMF figure{pct}"
    if x.get("iso3") == "BRA":
        own = x.get("published_ratio")
        imf = x.get("imf_ratio_2026")
        own_s = f"{own:.2f}% of GDP" if isinstance(own, (int, float)) else "its published ratio"
        imf_s = f"{imf:.2f}%" if isinstance(imf, (int, float)) else "the IMF ratio"
        return (f"Banco Central do Brasil SGS 13761/13762 (DBGG) is {own_s}; the IMF ratio is {imf_s}. "
                "The official stock differs from the IMF figure")
    return ("General-government stock on a different date, converted at the exchange rate on this page, "
            "so the dollar figure differs from the IMF end-2026 stock")

def _named_differences(W):
    by = {x["iso3"]: x for x in W["rows"]}
    bits = []
    nor = by.get("NOR")
    if nor and isinstance(nor.get("imf_gap"), (int, float)):
        bits.append(f"Norway's headline is Eurostat gov_10q_ggdebt sector S13 and differs from the IMF figure by {nor['imf_gap'] * 100:+.1f}%.")
    bra = by.get("BRA")
    if bra:
        own, imf = bra.get("published_ratio"), bra.get("imf_ratio_2026")
        if isinstance(own, (int, float)) and isinstance(imf, (int, float)):
            bits.append(f"Brazil's headline is Banco Central do Brasil SGS 13761/13762 (DBGG), {own:.2f}% of GDP, against an IMF ratio of {imf:.2f}%. The official stock differs from the IMF figure.")
        else:
            bits.append("Brazil's headline is Banco Central do Brasil SGS 13761/13762 (DBGG). The official stock differs from the IMF figure.")
    return " ".join(bits)

def _faqs(W):
    n = len(W["rows"]); c = W["counts"]; panel = (W.get("weo") or {}).get("panel_2026_usd")
    panel_s = _usd0(panel) if panel else "the IMF panel"
    gap = W.get("gap_vs_imf")
    gap_s = (f" The headline sum differs from that IMF total by {_sgn(gap, ',.0f', plus=False)} ({gap / panel * 100:+.2f}%)." if panel and gap is not None else "")
    top = sorted(W["rows"], key=lambda x: -x["usd"])[:5]
    top_s = "; ".join(f"{x['name']}, {_usd0(x['usd'])}" for x in top)
    return [
        ("How much is world government debt?",
         f"General government gross debt for these {n} economies sums to {_usd0(W['total'])} ({_tn(W['total'])}). "
         f"{c['official']} rows use a national general-government stock, {c['harmonized']} use Eurostat or the Quarterly Public Sector Debt database, and {c['imf']} use the IMF World Economic Outlook. "
         f"The same economies are {panel_s} on the pure IMF end-2026 sum.{gap_s}"),
        ("Which countries owe the most?",
         f"By the headline dollar stock on this page, the five largest are: {top_s}."),
        ("What does general government mean?",
         "General government is central government plus state, local and social-security funds, gross of financial assets. "
         "A federal or central-government series is narrower, so it is shown on the country page and under the country name here, and it is not added into the total. "
         "The IMF estimate then supplies the general-government stock."),
        ("How is the IMF figure estimated?",
         "Each IMF stock is GGXWDG_NGDP divided by 100, times NGDPD, from the October 2026 World Economic Outlook. "
         "The live number draws a straight line from the end-2025 stock to the end-2026 stock. It includes exchange-rate effects and is not a live ledger."),
        ("Why does a headline differ from the IMF number?",
         "A general-government stock from Eurostat, a national statistics office or QPSD can use a different date and a different exchange rate from the IMF's end-2026 dollars. "
         "A QPSD general-government stock more than 25% from the IMF figure is not used, because that gap is large enough to be a unit or perimeter problem. "
         + _named_differences(W)),
    ]

def build(R, SITE, with_analytics, og, stamp, now, places, W):
    if not W: return []
    rows, cv = W["rows"], W["cov"]; n = len(rows); c = W["counts"]
    url = f"{SITE}/world/"
    title = f"World Debt Clock: Government Debt of {n} Countries"
    desc = (f"World Debt Clock: general government gross debt of {n} economies, {_tn(W['total'])}. "
            f"{c['official']} national general-government stocks, {c['harmonized']} Eurostat or QPSD stocks, and {c['imf']} IMF estimates.")
    big_now = W["now_total"]
    os.makedirs(f"{R}/api", exist_ok=True)
    json.dump(api_json(W, SITE, now), open(f"{R}/api/world.json", "w"), indent=1)
    open(f"{R}/api/world.json", "a").write("\n")
    img = "og/places/world.png"
    if og:
        og(f"{R}/{img}", f"World debt clock · {n} countries · ticking live", _usd0(big_now),
           [("Official / harmonized / IMF", f"{c['official']} / {c['harmonized']} / {c['imf']}"), ("Latest sum", _usd0(W["total"]))],
           f"{_sgn(W['rate_s'] * 86400 / 1e9, ',.1f', 'B')}/day",
           "#ff4d5e", "General government gross debt\nNational stocks only when they match that perimeter")
    faqs = _faqs(W)
    faq_ld = {"@context": "https://schema.org", "@type": "FAQPage",
              "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs]}
    ds_ld = {"@context": "https://schema.org", "@type": "Dataset", "name": f"Government debt of {n} countries in US dollars", "description": desc, "url": url, "isAccessibleForFree": True,
             "creator": {"@type": "Organization", "name": "Every Debt Clock", "url": SITE + "/"}, "temporalCoverage": f"{min(x['as_of'] for x in rows)}/{max(x['as_of'] for x in rows)}",
             "isBasedOn": sorted({x["source_url"] for x in rows})}
    ld = ('<script type="application/ld+json">' + json.dumps(faq_ld).replace("</", "<\\/") + "</script>"
          + '<script type="application/ld+json">' + json.dumps(ds_ld).replace("</", "<\\/") + "</script>")

    jump = [("total", "Total"), ("table", "By country"), ("imf", "IMF comparison"), ("measures", "Measures"), ("faq", "Questions"), ("method", "Method")]
    header = (f'<header class="top"><div class="topin"><a class="brand" href="../">EVERY <b>DEBT</b> CLOCK</a>{pb.nav_html(places, 1, "world", "plnav")}'
              f'<span class="live"><span class="dot"></span><span>mixed sources</span></span></div>'
              f'<nav class="jump">' + "".join(f'<a href="#{i}">{E(t)}</a>' for i, t in jump) + "</nav></header>")
    panel = (W.get("weo") or {}).get("panel_2026_usd")
    covsent = (f'<p class="cvl" id="coverage"><b>{c["official"]} official, {c["harmonized"]} harmonized, {c["imf"]} IMF.</b> '
               f'These {n} economies are the IMF panel'
               + (f', whose own end-2026 total is {_tn(panel)}' if panel else '')
               + (f'. Their {cv["year"]} GDP is {cv["pct"]:.1f}% of world GDP' if cv else '')
               + '.</p>' if True else '')
    crumb = '<div class="crumb"><a href="../">← US national debt clock</a><span>·</span><a href="../countries/">All country debt clocks</a><span>·</span><a href="#imf">IMF comparison</a></div>'
    gap = W.get("gap_vs_imf")
    gap_txt = (f' The pure IMF end-2026 sum for the same {n} economies is <b>{_usd0(panel)}</b> ({_tn(panel)}), a difference of {_sgn(gap, ",.0f", plus=False)} ({gap / panel * 100:+.2f}%).' if panel and gap is not None else "")
    intro = (f'<section class="intro" id="intro">{crumb}<h1>World Debt Clock</h1>'
             f'<p><b>What this page counts.</b> General government gross debt for each of {n} economies, in US dollars. '
             f'The latest sum is <b>{_usd0(W["total"])}</b> ({_tn(W["total"])}). '
             f'<b>{c["official"]}</b> rows are a national general-government stock, <b>{c["harmonized"]}</b> are Eurostat Maastricht debt or the World Bank/IMF Quarterly Public Sector Debt general-government stock, and <b>{c["imf"]}</b> are IMF World Economic Outlook estimates. '
             f'A central, federal or otherwise narrower official series is named under the country and is not added in. Each economy is counted once. '
             f'The live number moves at the general-government trend where that stock has a year-ago figure, and at the IMF interpolation otherwise. It is a projection.</p>'
             f'<p>{gap_txt} The comparison is in the section below the table. '
             f'/world-government-debt/ and /global-debt-clock/ redirect here.</p></section>')
    hero = (f'<div class="hero lead" id="total" data-b="{big_now:.2f}" data-r="{W["rate_s"]:.6f}" data-t="{now:.0f}" style="cursor:default">'
            f'<div class="k">General government gross debt · {n} countries · US dollars</div><div class="big num" id="hv">{_usd0(big_now)}</div>'
            f'<div class="sub"><span>{_sgn(W["rate_s"])}/sec · {_sgn(W["rate_s"] * 86400 / 1e9, ",.1f")} billion/day</span>'
            f'<span class="note">sum of each country\'s own trend; a projection, not one official figure</span>'
            f'<span>Since you opened this page: <span class="num" id="hs">$0</span> more debt</span></div>'
            f'<div class="trio"><div><span class="l">Sum of latest figures</span><span class="num">{_usd0(W["total"])}</span></div>'
            f'<div><span class="l">Economies</span><span class="num">{n}</span></div>'
            f'<div><span class="l">Official / harmonized / IMF</span><span class="num">{c["official"]} / {c["harmonized"]} / {c["imf"]}</span></div></div>'
            f'<div class="meta" style="margin-top:10px"><span class="badge proj">PROJECTED · mixed sources</span><span class="badge">{c["official"]} official · {c["harmonized"]} harmonized · {c["imf"]} IMF</span></div></div>')
    # ---- table
    body = ""
    for x in rows:
        ratio = f'{x["ratio"]:.1f}%' if x.get("ratio") is not None else "—"
        link = f'<a href="../{x["url"]}">{E(x["name"])} debt clock</a>' if x["url"] else '<a href="../">United States debt clock</a>'
        ol = x.get("official_line")
        nat = (f'<span class="nat">National series, not in the total: {E(ol["measure"])}, {E(_fd(ol["as_of"]))}, ${ol["usd"]/1e12:,.3f}tn</span>' if ol else "")
        body += (f'<tr data-name="{E(x["name"])}" data-debt="{x["usd"]:.0f}" data-ratio="{x["ratio"] if x.get("ratio") is not None else ""}" data-tier="{x["tier"]}" data-asof="{x["as_of"]}" data-iso="{E(x["iso3"] or "")}">'
                 f'<td class="c"><b>{E(x["name"])}</b><br>{link}{nat}</td>'
                 f'<td class="num" data-l="Debt, USD" title="${x["usd"]:,.0f}">${x["usd"]/1e12:,.3f}tn</td>'
                 f'<td class="num" data-l="Debt / GDP">{ratio}</td>'
                 f'<td data-l="Source tier">{TIER[x["tier"]]}</td>'
                 f'<td data-l="As of">{E(_fd(x["as_of"]))}</td>'
                 f'<td class="m" data-l="Measure">{E(x["measure"])}</td></tr>')
    table = (f'<section id="table" class="wsec"><div class="sh"><span class="bar" style="background:var(--red)"></span><h2>By country</h2><span class="h2n">Latest figure for each economy · click a column to sort · this table does not tick</span></div>'
             f'<div class="tw"><table class="wt wstk" id="debt-table"><thead><tr class="hd">'
             f'<th data-k="name">Country</th><th class="num" data-k="debt" data-dir="desc">Debt, USD</th><th class="num" data-k="ratio">Debt / GDP</th>'
             f'<th data-k="tier">Source tier</th><th data-k="asof">As of</th><th>Measure</th></tr></thead><tbody>{body}</tbody></table></div>'
             f'<p class="dnote">The debt column is general government gross debt. It does not tick. '
             f'A national series listed under the country is narrower (central, federal, or a different perimeter) and is not added. '
             f'Debt / GDP uses the IMF 2026 GDP for official and harmonized rows, and the IMF debt ratio for IMF rows. '
             f'As of is the stock date, or 31 December 2026 for an IMF end-2026 projection.</p></section>')
    # ---- measures
    drv = ""
    for x in W.get("drivers") or []:
        delta = x["usd"] - x["imf_debt_2026"]
        why = _driver_why(x)
        if x["tier"] == "imf":
            continue
        drv += (f'<tr><td class="c"><b>{E(x["name"])}</b></td><td data-l="Headline basis">{TIER[x["tier"]]}</td>'
                f'<td class="num" data-l="Headline">{_tn(x["usd"])}</td><td class="num" data-l="IMF end-2026">{_tn(x["imf_debt_2026"])}</td>'
                f'<td class="num" data-l="Difference">{("+" if delta >= 0 else "−") + "$" + f"{abs(delta)/1e9:,.1f}"} billion</td>'
                f'<td class="m" data-l="Why">{E(why)}. {E(x["measure"])}.</td></tr>')
    over = panel and gap is not None and abs(gap) / panel > 0.03
    imf_sec = (f'<section id="imf" class="wsec"><div class="sh"><span class="bar" style="background:var(--amber)"></span><h2>IMF comparison</h2>'
               f'<span class="h2n">One methodology · October 2026 World Economic Outlook</span></div>'
               f'<p><b>What the IMF total counts.</b> General government gross debt for the same {n} economies, GGXWDG_NGDP times NGDPD, in current US dollars. '
               f'The end-2026 sum is <b>{_usd0(panel)}</b> ({_tn(panel)}). '
               f'This page\'s headline sum is {_usd0(W["total"])} ({_tn(W["total"])}), {gap / panel * 100:+.2f}% from that IMF total. '
               + ("That is more than 3% away. Every country whose headline stock differs from its IMF stock by at least $1 billion is listed." if over else
                  "That is within 3%. Countries whose general-government stock is not the IMF figure, and differs by at least $1 billion, are listed.")
               + f'</p><div class="tw"><table class="wt wstk" style="min-width:760px"><tr class="hd"><th>Country</th><th>Headline basis</th><th class="num">Headline</th><th class="num">IMF end-2026</th><th class="num">Difference</th><th>Why</th></tr>{drv}</table></div>'
               f'<p class="src">Source: IMF World Economic Outlook, October 2026. <a href="https://www.imf.org/external/datamapper/GGXWDG_NGDP@WEO" rel="noopener">GGXWDG_NGDP</a> · '
               f'<a href="https://www.imf.org/external/datamapper/NGDPD@WEO" rel="noopener">NGDPD</a>. '
               f'The dollar change from end-2025 to end-2026 includes exchange-rate effects.</p></section>' if panel and gap is not None else "")
    meas = (f'<section id="measures" class="wsec"><div class="sh"><span class="bar" style="background:var(--amber)"></span><h2>One perimeter</h2></div>'
            f'<div class="wnote">Every headline row is general government gross debt. A central, federal or public-sector series is printed under the country name and is not in the sum. '
            + ("Russia's national series is internal debt only, so it leaves out external debt. " if any(x["slug"] == "russia" for x in rows) else "")
            + f'Dates run from {E(_fd(min(x["as_of"] for x in rows)))} to {E(_fd(max(x["as_of"] for x in rows)))}.</div>'
            f'<p class="dnote">{c["official"]} headlines are a national general-government stock. {c["harmonized"]} are Eurostat or QPSD general government. {c["imf"]} are the IMF estimate because the national series is narrower, missing, or a QPSD general-government stock more than 25% from the IMF figure.</p></section>')
    # ---- fx
    seen, fr = set(), ""
    for x in rows:
        if x["code"] in seen or x["code"] == "USD": continue
        seen.add(x["code"])
        fr += f'<tr><td class="c"><b>{E(x["code"])}</b></td><td class="num" data-l="Rate as published">{E(x["quote"])}</td><td class="num" data-l="USD per 1 unit">{x["rate"]:.6f}</td><td data-l="Rate date">{E(_fd(x["rate_date"]) if x["rate_date"] else "fixed peg")}</td><td class="m" data-l="Source">{E(x["rate_src"])}</td></tr>'
    rates = (f'<section id="rates" class="wsec"><div class="sh"><span class="bar" style="background:var(--teal)"></span><h2>Exchange rates used</h2><span class="h2n">Official reference rates, refreshed with the daily data update</span></div>'
             f'<div class="tw"><table class="wt wstk" style="min-width:640px"><tr class="hd"><th>Currency</th><th class="num">Rate as published</th><th class="num">USD per 1 unit</th><th>Rate date</th><th>Source</th></tr>{fr}</table></div>'
             '<p class="dnote">Euro reference rates come from the <a href="https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html" rel="noopener">European Central Bank</a>; other currencies on that feed are converted through the euro (USD per unit = USD per EUR ÷ units per EUR). '
             'The rouble uses the <a href="https://www.cbr.ru/eng/currency_base/daily/" rel="noopener">Bank of Russia</a> rate. Taiwan and the Sri Lanka rupee use the Federal Reserve H.10 weekly release. '
             'Currencies on neither feed use the <a href="https://fiscaldata.treasury.gov/datasets/treasury-reporting-rates-exchange/treasury-reporting-rates-of-exchange" rel="noopener">US Treasury Reporting Rates of Exchange</a>, which is a quarter-end rate. The Saudi riyal and the Qatari riyal use the central bank peg. IMF rows are already in US dollars. Rates are held fixed between updates.</p></section>')
    # ---- method
    review_rows = ""
    for x in sorted(W["review"], key=lambda r: -abs(r["imf_gap"])):
        review_rows += (f'<tr><td class="c"><b>{E(x["name"])}</b></td><td data-l="Source tier">{TIER[x["tier"]]}</td>'
                        f'<td class="num" data-l="Stock used">{_tn(x["usd"])}</td><td class="num" data-l="IMF end-2026">{_tn(x["imf_debt_2026"])}</td>'
                        f'<td class="num" data-l="Gap">{x["imf_gap"]:+.0%}</td>'
                        f'<td class="m" data-l="Source"><a href="{E(x["source_url"])}" rel="noopener">{E(x["source"] or "Source")}</a></td></tr>')
    review = (f'<p><b>More than 25% from the IMF stock.</b> {len(W["review"])} official or harmonized rows differ from the IMF end-2026 general-government stock by more than 25%. '
              f'The clock keeps the official stock. The usual reason is the perimeter: central government here, general government in the IMF series.</p>'
              f'<div class="tw"><table class="wt wstk" style="min-width:720px"><tr class="hd"><th>Country</th><th>Source tier</th><th class="num">Stock used</th><th class="num">IMF end-2026</th><th class="num">Gap</th><th>Source</th></tr>{review_rows}</table></div>'
              if W["review"] else '<p><b>More than 25% from the IMF stock.</b> No official or harmonized row is more than 25% from the IMF end-2026 stock.</p>')
    kept = "".join(f'<li>{E(r["name"])} ({E(r["iso3"])}): {E(r["reason"])}</li>' for r in W["rejected"])
    skipped = (f'<p><b>Not converted.</b> No official rate is stored for: ' + ", ".join(f"{E(a)} ({E(b)})" for a, b, _iso in W["skipped"]) + '. Those clocks are left out of the sum.</p>' if W["skipped"] else "")
    method = (f'<section id="method" class="wsec"><div class="sh"><span class="bar" style="background:var(--mut)"></span><h2>How it works</h2><span class="h2n">General government gross debt · projection labelled</span></div><div class="sk foot">'
              f'<p><b>The sum</b> is {_usd0(W["total"])}. The headline is a national or Eurostat or QPSD general-government gross stock when that stock exists and, for QPSD, converts to within 25% of the IMF end-2026 stock. Otherwise the headline is the IMF end-2026 projection. '
              f'{c["official"]} official, {c["harmonized"]} harmonized, {c["imf"]} IMF. One row per economy.</p>'
              f'<p><b>The live number</b> adds each headline\'s trend from its own as-of date. A general-government trend is the change from about a year earlier when that earlier stock is stored. Otherwise the pace is the IMF interpolation from end-2025 to end-2026. '
              f'The combined rate is {_sgn(W["rate_s"], ",.2f", plus=False)} per second. Exchange rates are held fixed. The live number is a projection. The US row uses the IMF pace, not Treasury\'s 90-day trend; Treasury Debt to the Penny is the national series under the United States.</p>'
              + (f'<p><b>GDP.</b> The economies in this table account for {cv["pct"]:.1f}% of IMF {cv["year"]} world GDP. Debt / GDP on an official or harmonized row is the USD stock divided by that economy\'s IMF 2026 GDP, not a national ratio.</p>' if cv else '')
              + review
              + (f'<p><b>Still on the IMF estimate.</b></p><ul>{kept}</ul>' if kept else '')
              + skipped
              + f'<p>Machine-readable: <a href="../api/world.json">/api/world.json</a>. Page built {E(stamp)}.</p></div></section>')
    faq_html = '<section class="faq" id="faq"><div class="sh"><h2>Questions</h2></div>' + "".join(f"<h3>{E(q)}</h3><p>{E(a)}</p>" for q, a in faqs) + "</section>"
    links = ('<section class="answers" id="answers"><div class="sh"><h2>More clocks</h2></div><ul><li><a href="../">US national debt clock</a></li>'
             + '<li><a href="#imf">IMF comparison on this page</a></li>'
             + '<li><a href="../countries/">All country debt clocks</a></li>'
             '<li><a href="../states/">All US state debt clocks</a></li><li><a href="../api/world.json">World debt clock as JSON</a></li></ul></section>')
    script = """<script>(function(){const nf0=new Intl.NumberFormat('en-US',{maximumFractionDigits:0});
const H=document.getElementById('total'),B=+H.dataset.b,R=+H.dataset.r,T0=+H.dataset.t,hv=document.getElementById('hv'),hs=document.getElementById('hs'),OPENED=Date.now()/1000;
const tot=t=>B+R*(t-T0);(function f(){const t=Date.now()/1000,x=tot(t);hv.textContent=(x<0?'−$':'$')+nf0.format(Math.abs(x));
hs.textContent=(R*(t-OPENED)<0?'−':'+')+'$'+nf0.format(Math.abs(R*(t-OPENED)));requestAnimationFrame(f)})();
const table=document.getElementById('debt-table');if(!table)return;const tb=table.tBodies[0];
table.querySelectorAll('th[data-k]').forEach(function(th){th.addEventListener('click',function(){const dir=th.dataset.dir==='asc'?'desc':'asc',k=th.dataset.k;
table.querySelectorAll('th[data-k]').forEach(function(h){delete h.dataset.dir});th.dataset.dir=dir;
const rows=[].slice.call(tb.rows);rows.sort(function(a,b){const av=a.dataset[k],bv=b.dataset[k],an=+av,bn=+bv;
const c=(av!==''&&bv!==''&&!isNaN(an)&&!isNaN(bn))?an-bn:String(av).localeCompare(String(bv));return dir==='asc'?c:-c});
rows.forEach(function(r){tb.appendChild(r)})})})})()</script>"""
    explore_html = ex.explore("../", places, pb.calc, cur=None, gdp=pb.GDP_BY_SLUG, usd={x["slug"]: x["usd"] for x in rows if x["slug"] != "united-states"}, kind_hint="world")
    page = (pb.meta_head(SITE, url, title, desc, img, 1, pb.PL_CSS + CSS, ld) + header + '<main id="app">' + hero + intro + covsent + table + imf_sec + meas + rates + faq_html + ex.search_box("../") + method + '</main>' + explore_html + links
            + '<footer class="site-foot">Every Debt Clock · mixed sources, projection labelled · <a href="../methodology/">Methodology</a> · <a href="../privacy.html">Privacy</a> · Independent site, not affiliated with any government. Not financial advice.</footer>' + script + "</body></html>")
    os.makedirs(f"{R}/world", exist_ok=True)
    open(f"{R}/world/index.html", "w").write(with_analytics(page))
    return [url]
