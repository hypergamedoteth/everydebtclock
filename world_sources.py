"""Best debt stock for each IMF economy: a live clock, then a QPSD quarterly stock, then the IMF WEO fallback.

QPSD is kept only when the converted stock is within 25% of that economy's IMF end-2026 stock.
A wider gap is rejected rather than published: the QPSD unit is not cross-checked against a national release.
National and Eurostat clocks are kept either way; a gap above 25% is flagged for review, not dropped.
"""
import datetime as dt
import json
import os

MIN_ASOF = "2025-06-30"
MAX_GAP = 0.25
QPSD_SRC = "World Bank and IMF, Quarterly Public Sector Debt (QPSD)"
QPSD_URL = {
    "general": "https://data.worldbank.org/indicator/DP.DOD.DECT.CR.GG",
    "central": "https://data.worldbank.org/indicator/DP.DOD.DECT.CR.CG",
}
SECTOR = {"general": "General government, gross", "central": "Central government, gross"}

def load_json(path):
    try:
        return json.load(open(path))
    except Exception:
        return {}

def tier_of(p):
    if p.get("source_tier") in ("official", "harmonized"):
        return p["source_tier"]
    if "Eurostat" in (p.get("publisher") or ""):
        return "harmonized"
    return "official"

def _days(a, b):
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days

def _fx(code, label, fx):
    import world_build
    hit = world_build.usd_per_unit(code, fx)
    if hit:
        return hit
    broad = fx.get("ust_broad") or {}
    v = (broad.get("per_usd") or {}).get(label or "")
    if v and v > 0:
        return 1.0 / v, broad.get("date"), broad.get("source") or "US Treasury", f"{v:g} {code} per USD"
    return None

def _prior(history, as_of):
    cands = [(d, v) for d, v in history if d < as_of and v > 0 and 300 <= _days(d, as_of) <= 450]
    if not cands:
        return None
    return min(cands, key=lambda dv: abs(_days(dv[0], as_of) - 365))

def official_iso(places):
    import world_build
    out = {"USA"}
    for p in places:
        if p.get("kind") != "country" or p.get("status") not in (None, "live"):
            continue
        iso = p.get("iso3") or world_build.ISO3.get(p.get("country") or "")
        if iso:
            out.add(iso)
    return out

def qpsd_choice(R, places, fx, economies):
    """Return (used {iso3: record}, rejected [dict]). Economies with a live clock are not considered."""
    doc = load_json(f"{R}/data/world_qpsd.json")
    raw = doc.get("countries") or {}
    by = {e["iso3"]: e for e in economies}
    skip = official_iso(places)
    used, rejected = {}, []
    import places_build as pb
    for iso, e in by.items():
        if iso in skip:
            continue
        slot = raw.get(iso)
        if not slot:
            continue
        passes, fails = [], []
        for sector in ("general", "central"):
            hist = slot.get(sector) or []
            pts = [(d, v) for d, v in hist if d >= MIN_ASOF and v > 0]
            if not pts:
                continue
            as_of, local = pts[-1]
            hit = _fx(slot.get("currency") or "", slot.get("fx_label"), fx)
            if not hit:
                fails.append(f"{sector} stock has no official USD rate")
                continue
            rate, rate_date, rate_src, quote = hit
            usd = local * rate
            imf = e["debt_2026_usd"]
            gap = usd / imf - 1 if imf else None
            rec = {"sector": sector, "as_of": as_of, "local": local, "history": hist, "usd": usd,
                   "rate": rate, "rate_date": rate_date, "rate_src": rate_src, "quote": quote, "gap": gap,
                   "currency": slot.get("currency")}
            if gap is not None and abs(gap) <= MAX_GAP:
                passes.append(rec)
            else:
                fails.append(f"{sector} {as_of} converts to ${usd/1e9:,.1f} billion, {gap:+.0%} versus the IMF end-2026 stock" if gap is not None else f"{sector} has no IMF comparison")
        if not passes and not fails and slot:
            fails.append("no general or central government stock dated 2025-06-30 or later")
        if passes:
            # General government wins when both perimeters are inside the screen.
            rec = next((r for r in passes if r["sector"] == "general"), passes[0])
            prior = _prior(rec["history"], rec["as_of"])
            if prior:
                secs = pb._eod(rec["as_of"]) - pb._eod(prior[0])
                trend_local = (rec["local"] - prior[1]) / secs
                trend_kind, trend_note = "official", f"QPSD change {prior[0]} to {rec['as_of']}"
                prior_as_of, prior_local = prior[0], prior[1]
            else:
                trend_local = e["rate_usd_per_sec"] / rec["rate"]
                trend_kind = "imf"
                trend_note = "IMF 2025-to-2026 interpolation; the quarterly file has no stock about a year earlier"
                prior_as_of, prior_local = None, None
            used[iso] = {
                "iso3": iso, "name": e["name"], "slug": e["slug"], "sector": rec["sector"],
                "measure": SECTOR[rec["sector"]], "currency": rec["currency"], "local": rec["local"],
                "as_of": rec["as_of"], "prior_local": prior_local, "prior_as_of": prior_as_of,
                "history": [[d, v] for d, v in rec["history"] if d <= rec["as_of"]][-8:],
                "rate": rec["rate"], "rate_date": rec["rate_date"], "rate_src": rec["rate_src"], "quote": rec["quote"],
                "usd": rec["usd"], "trend_local": trend_local, "trend_kind": trend_kind, "trend_note": trend_note,
                "t0": pb._eod(rec["as_of"]), "source": QPSD_SRC, "source_url": QPSD_URL[rec["sector"]],
                "imf_gap": rec["gap"], "region": e.get("region") or "",
            }
        elif fails:
            rejected.append({"iso3": iso, "name": e["name"], "slug": e["slug"], "reason": "; ".join(fails)})
    seen = set(used) | {r["iso3"] for r in rejected}
    for iso, e in by.items():
        if iso in skip or iso in seen:
            continue
        rejected.append({"iso3": iso, "name": e["name"], "slug": e["slug"],
                         "reason": "no QPSD general or central government stock dated 2025-06-30 or later in the World Bank API, and no separate keyless national source was automated"})
    return used, rejected
