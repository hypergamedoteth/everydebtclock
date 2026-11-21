"""Country-page facts from the IMF World Economic Outlook file already on the site.

data/world_weo_history.json is the October 2026 GGXWDG_NGDP path (percent of GDP) and LP population.
Dollar stocks for 2025 and 2026 come from data/world_weo_debt.json, the same products the clocks use.
Nothing here is estimated locally: ranks, medians and per-person figures are arithmetic on those inputs.
"""
import datetime as dt
import html
import json
import os
import re
from difflib import SequenceMatcher

E = html.escape
PUBLISHED = "October 13, 2026"
SOURCE = "IMF World Economic Outlook, October 2026"
RATIO_URL = "https://www.imf.org/external/datamapper/GGXWDG_NGDP@WEO"
POP_URL = "https://www.imf.org/external/datamapper/LP@WEO"
PUB_URL = "https://www.imf.org/en/publications/weo/issues/2026/10/13/world-economic-outlook-october-2026"


def load(R):
    path = os.path.join(R, "data", "world_weo_history.json")
    if not os.path.exists(path):
        raise SystemExit("country profile: data/world_weo_history.json is missing")
    return json.load(open(path))


def money(x):
    ax = abs(x)
    s = "−" if x < 0 else ""
    if ax >= 1e12:
        return s + f"${ax / 1e12:,.2f} trillion"
    if ax >= 1e9:
        return s + f"${ax / 1e9:,.2f} billion"
    if ax >= 1e6:
        return s + f"${ax / 1e6:,.2f} million"
    return s + f"${ax:,.0f}"


def money0(x):
    return ("−" if x < 0 else "") + f"${abs(x):,.0f}"


def pct(x):
    return f"{x:.2f}%"


def per_person(debt, pop):
    v = debt / pop
    if abs(v) >= 100:
        return f"${v:,.0f}"
    return f"${v:,.2f}"


def ordinal(n):
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def poss(name):
    return name + "'" if name.endswith("s") else name + "'s"


def _median(vals):
    s = sorted(vals)
    n = len(s)
    if n == 0:
        return None
    if n % 2:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2


def _status(year, meta):
    if year >= meta["projection_from"]:
        return "projection"
    if year == meta["estimate_year"]:
        return "estimate"
    return "history"


def build_profiles(economies, history):
    """One profile per IMF economy. Raises if the history file is a different vintage than the clock file."""
    meta = history
    rows = history["economies"]
    profiles = {}
    for e in economies:
        row = rows.get(e["iso3"])
        if not row:
            raise SystemExit(f"country profile: {e['iso3']} is in the clock file and missing from the history file")
        ratio = {int(y): float(v) for y, v in (row.get("ratio") or {}).items()}
        for year, key in ((2026, "ratio_2026"), (2025, "ratio_2025")):
            if year not in ratio or abs(ratio[year] - e[key]) > 0.02:
                raise SystemExit(f"country profile: {e['iso3']} {year} ratio does not match the clock file")
        pop = {int(y): int(v) for y, v in (row.get("population") or {}).items() if int(v) > 0}
        series = [{"year": y, "ratio": ratio[y], "status": _status(y, meta)} for y in sorted(ratio)]
        profiles[e["iso3"]] = {
            "iso3": e["iso3"], "name": e["name"], "slug": e["slug"], "region": e.get("region") or "",
            "debt_2026": e["debt_2026_usd"], "debt_2025": e["debt_2025_usd"],
            "gdp_2026": e["gdp_2026_usd"], "ratio_2026": e["ratio_2026"], "ratio_2025": e["ratio_2025"],
            "rank_debt": e["rank_debt"], "rank_ratio": e["rank_ratio"], "n": len(economies),
            "series": series, "pop": pop, "published": meta["published"],
            "history_through": meta["history_through"], "estimate_year": meta["estimate_year"],
            "projection_from": meta["projection_from"],
        }
    _region_stats(profiles)
    return profiles


def _region_stats(profiles):
    by_region = {}
    for p in profiles.values():
        by_region.setdefault(p["region"], []).append(p)
    for region, group in by_region.items():
        ratios = [p["ratio_2026"] for p in group]
        med = _median(ratios)
        by_ratio = sorted(group, key=lambda p: (-p["ratio_2026"], p["name"]))
        by_debt = sorted(group, key=lambda p: (-p["debt_2026"], p["name"]))
        for i, p in enumerate(by_ratio, 1):
            p["region_rank_ratio"] = i
        for i, p in enumerate(by_debt, 1):
            p["region_rank_debt"] = i
        for p in group:
            p["region_n"] = len(group)
            p["region_median"] = med


def usefulness(p):
    """Reasons the page cannot carry the history, the per-person figure and a projection. Empty means publish it."""
    if not p:
        return ["no IMF history row"]
    hist = [pt for pt in p["series"] if pt["status"] != "projection"]
    proj = [pt for pt in p["series"] if pt["status"] == "projection"]
    reasons = []
    if len(hist) < 8:
        reasons.append(f"only {len(hist)} published debt-to-GDP years before the projection window")
    if not proj:
        reasons.append("no IMF projection year after 2026")
    pop_year = _pop_year(p)
    if pop_year is None:
        reasons.append("no IMF population (LP) for 2024, 2025 or 2026")
    if not p["debt_2026"] or p["debt_2026"] <= 0:
        reasons.append("no positive 2026 debt stock")
    return reasons


def _pop_year(p):
    for year in (p["estimate_year"], p["history_through"], p["estimate_year"] - 2):
        if year in p["pop"]:
            return year
    years = [y for y in p["pop"] if y <= p["estimate_year"]]
    return max(years) if years else None


def _pop(p):
    year = _pop_year(p)
    if year is None:
        return None, None
    return p["pop"][year], year


def _points(p, statuses):
    return [pt for pt in p["series"] if pt["status"] in statuses]


def _swings(points, min_pp):
    """Pivot chain. A turn is kept only when the ratio reverses by at least min_pp."""
    if len(points) < 2:
        return list(points)
    pivots = [points[0]]
    direction = 0
    extreme = points[0]
    for pt in points[1:]:
        if direction == 0:
            if abs(pt["ratio"] - pivots[0]["ratio"]) >= min_pp:
                direction = 1 if pt["ratio"] > pivots[0]["ratio"] else -1
                extreme = pt
            continue
        if direction == 1:
            if pt["ratio"] >= extreme["ratio"]:
                extreme = pt
            elif extreme["ratio"] - pt["ratio"] >= min_pp:
                pivots.append(extreme)
                direction = -1
                extreme = pt
        else:
            if pt["ratio"] <= extreme["ratio"]:
                extreme = pt
            elif pt["ratio"] - extreme["ratio"] >= min_pp:
                pivots.append(extreme)
                direction = 1
                extreme = pt
    if extreme["year"] != pivots[-1]["year"]:
        pivots.append(extreme)
    last = points[-1]
    if pivots[-1]["year"] != last["year"] and abs(last["ratio"] - pivots[-1]["ratio"]) >= min_pp:
        pivots.append(last)
    elif pivots[-1]["year"] != last["year"]:
        pivots.append(last)
    return pivots


def _decade_moves(p):
    hist = {pt["year"]: pt["ratio"] for pt in p["series"] if pt["status"] == "history"}
    windows = ((1980, 1989, "the 1980s"), (1990, 1999, "the 1990s"), (2000, 2009, "the 2000s"),
               (2010, 2019, "the 2010s"), (2020, 2025, "2020 through 2025"))
    moves = []
    for a, b, label in windows:
        years = [y for y in range(a, b + 1) if y in hist]
        if len(years) < 2 or years[-1] - years[0] < 4:
            continue
        y0, y1 = years[0], years[-1]
        moves.append({"label": label, "y0": y0, "y1": y1, "r0": hist[y0], "r1": hist[y1], "delta": hist[y1] - hist[y0]})
    return moves


def _region_noun(region):
    return {"Europe": "European", "Africa": "African", "Asia-Pacific": "Asia-Pacific",
            "Middle East": "Middle Eastern", "the Americas": "Western Hemisphere"}.get(region, "panel")


def _in_region(region):
    if region == "the Americas":
        return "in the Americas"
    if region == "Middle East":
        return "in the Middle East"
    if not region:
        return "in the IMF panel"
    return "in " + region


def path_paragraph(p):
    hist = _points(p, {"history"})
    if len(hist) < 2:
        return ""
    lo = min(hist, key=lambda pt: (pt["ratio"], pt["year"]))
    hi = max(hist, key=lambda pt: (pt["ratio"], -pt["year"]))
    span = hi["ratio"] - lo["ratio"]
    y0, y1 = hist[0], hist[-1]
    name = p["name"]
    net = y1["ratio"] - y0["ratio"]
    if span < 8:
        return (f"Through {y1['year']} the published ratio stays in a narrow band. "
                f"The low is {pct(lo['ratio'])} in {lo['year']} and the high is {pct(hi['ratio'])} in {hi['year']}. "
                f"{y1['year']} is {pct(y1['ratio'])}, {abs(net):.2f} percentage points from {pct(y0['ratio'])} in {y0['year']}.")
    min_pp = 5 if span >= 20 else 3
    pivots = _swings(hist, min_pp)
    ends_are_extremes = abs(hi["ratio"] - max(y0["ratio"], y1["ratio"])) < 1 and abs(lo["ratio"] - min(y0["ratio"], y1["ratio"])) < 1
    if len(pivots) <= 2 and ends_are_extremes and abs(net) >= 8:
        way = "down" if net < 0 else "up"
        return (f"The net move in the published series, {y0['year']} to {y1['year']}, is {way} {abs(net):.2f} percentage points, "
                f"from {pct(y0['ratio'])} to {pct(y1['ratio'])}.")
    bits = []
    for a, b in zip(pivots, pivots[1:]):
        change = b["ratio"] - a["ratio"]
        if abs(change) < 1:
            continue
        if change >= 15:
            verb = "climbed"
        elif change > 0:
            verb = "rose"
        elif change <= -15:
            verb = "dropped"
        else:
            verb = "eased"
        bits.append(f"{verb} from {pct(a['ratio'])} in {a['year']} to {pct(b['ratio'])} in {b['year']}")
    if not bits:
        return (f"From {pct(y0['ratio'])} in {y0['year']} the published series ends {y1['year']} at {pct(y1['ratio'])}. "
                f"The high is {pct(hi['ratio'])} in {hi['year']} and the low is {pct(lo['ratio'])} in {lo['year']}.")
    turn = max(0, len(bits) - 1)
    turn_word = "no turn above" if turn == 0 else "one turn of at least" if turn == 1 else f"{turn} turns of at least"
    joined = bits[0]
    for bit in bits[1:]:
        joined += ", then " + bit
    return f"In the published years, {poss(name)} ratio has {turn_word} {min_pp:.0f} percentage points. It {joined}."


def decade_paragraph(p):
    moves = _decade_moves(p)
    if not moves:
        return ""
    moves.sort(key=lambda m: abs(m["delta"]), reverse=True)
    top = moves[0]
    if top["delta"] >= 0:
        lead = (f"Inside one decade window, the largest rise is {top['label']}: "
                f"{pct(top['r0'])} in {top['y0']} to {pct(top['r1'])} in {top['y1']}, "
                f"up {top['delta']:.2f} percentage points.")
    else:
        lead = (f"Inside one decade window, the largest fall is {top['label']}: "
                f"{pct(top['r0'])} in {top['y0']} to {pct(top['r1'])} in {top['y1']}, "
                f"down {abs(top['delta']):.2f} percentage points.")
    if len(moves) == 1:
        return lead
    nxt = moves[1]
    way = "up" if nxt["delta"] >= 0 else "down"
    return lead + (f" The next largest move is {nxt['label']}, {way} {abs(nxt['delta']):.2f} percentage points "
                   f"({pct(nxt['r0'])} in {nxt['y0']} to {pct(nxt['r1'])} in {nxt['y1']}).")


def threshold_paragraph(p):
    hist = _points(p, {"history"})
    if not hist:
        return ""
    r = p["ratio_2026"]
    name = p["name"]
    over100 = [pt for pt in hist if pt["ratio"] >= 100]
    over60 = [pt for pt in hist if pt["ratio"] >= 60]
    under60 = [pt for pt in hist if pt["ratio"] < 60]
    if r >= 100:
        if over100 and over100[0]["year"] == hist[0]["year"] and all(pt["ratio"] >= 100 for pt in hist):
            return (f"Every published year in this file, from {hist[0]['year']} through {hist[-1]['year']}, is above 100% of GDP. "
                    f"The 2026 estimate, {pct(r)}, is on that side of the line as well.")
        if over100 and over100[0]["year"] == hist[0]["year"]:
            under = [pt for pt in hist if pt["ratio"] < 100]
            extra = f" It is under 100% in {under[-1]['year']} ({pct(under[-1]['ratio'])})." if under else ""
            return (f"The published series opens above 100% of GDP, at {pct(hist[0]['ratio'])} in {hist[0]['year']}.{extra} "
                    f"The 2026 estimate is {pct(r)}.")
        if over100:
            first = over100[0]
            return (f"The first published year at or above 100% of GDP is {first['year']}, at {pct(first['ratio'])}. "
                    f"The 2026 estimate is {pct(r)}.")
        return (f"The 2026 estimate is {pct(r)}, above 100% of GDP. "
                f"No published year through {hist[-1]['year']} is that high.")
    below60 = [pt for pt in hist if pt["ratio"] < 60]
    if r >= 60:
        if over100:
            last = over100[-1]
            extra = f" The last published year under 60% is {below60[-1]['year']} ({pct(below60[-1]['ratio'])})." if below60 else ""
            return (f"The 2026 estimate is {pct(r)}, between 60% and 100% of GDP. "
                    f"The series was last at or above 100% in {last['year']} ({pct(last['ratio'])}).{extra}")
        if not below60:
            return (f"Every published year in this file is above 60% of GDP and below 100%, "
                    f"from {hist[0]['year']} through {hist[-1]['year']}. The 2026 estimate is {pct(r)}.")
        if over60 and over60[0]["year"] != hist[0]["year"] and below60[-1]["year"] < over60[0]["year"]:
            first = over60[0]
            return (f"The first published year above 60% of GDP is {first['year']} ({pct(first['ratio'])}), "
                    f"and the series stays above 60% after that. The 2026 estimate is {pct(r)}.")
        return (f"The 2026 estimate is {pct(r)}, above 60% of GDP and below 100%. "
                f"The last published year under 60% is {below60[-1]['year']} ({pct(below60[-1]['ratio'])}).")
    if over100:
        last = over100[-1]
        return (f"The 2026 estimate is {pct(r)}, under 60% of GDP. "
                f"The ratio was above 100% as recently as {last['year']} ({pct(last['ratio'])}).")
    if over60:
        last = over60[-1]
        return (f"The 2026 estimate is {pct(r)}, under both 60% and 100% of GDP. "
                f"The last published year above 60% is {last['year']} ({pct(last['ratio'])}).")
    if under60 and len(under60) == len(hist):
        return (f"{name} stays under 60% of GDP in every published year in this file, "
                f"from {pct(hist[0]['ratio'])} in {hist[0]['year']} to {pct(hist[-1]['ratio'])} in {hist[-1]['year']}. "
                f"The 2026 estimate is {pct(r)}.")
    return f"The 2026 estimate is {pct(r)}, under 60% of GDP."


def covid_paragraph(p):
    by = {pt["year"]: pt["ratio"] for pt in p["series"] if pt["status"] == "history"}
    if not all(y in by for y in (2019, 2020, 2021)):
        return ""
    jump = by[2020] - by[2019]
    if jump < 5:
        return ""
    name = p["name"]
    if by[2020] > by[2021]:
        return (f"2020 is a spike in {poss(name)} series: {pct(by[2020])}, up from {pct(by[2019])} in 2019, "
                f"then {pct(by[2021])} in 2021.")
    return (f"The ratio jumped in 2020, from {pct(by[2019])} in 2019 to {pct(by[2020])}, "
            f"and 2021 is higher still at {pct(by[2021])}.")


def projection_paragraph(p):
    proj = _points(p, {"projection"})
    est = next((pt for pt in p["series"] if pt["year"] == p["estimate_year"]), None)
    hist = _points(p, {"history"})
    if not proj or not est:
        return ""
    end = proj[-1]
    delta = end["ratio"] - est["ratio"]
    hist_high = max((pt["ratio"] for pt in hist), default=est["ratio"])
    proj_high = max(proj, key=lambda pt: pt["ratio"])
    name = p["name"]
    label = f"The dashed part of the chart, {proj[0]['year']}–{end['year']}, is an IMF projection, not an outcome."
    if proj_high["ratio"] > hist_high and proj_high["ratio"] > est["ratio"]:
        return (f"The IMF projection puts {name} at a new high of {pct(proj_high['ratio'])} in {proj_high['year']}, "
                f"above every published year in this file. The {end['year']} projection is {pct(end['ratio'])}. {label}")
    if delta >= 5:
        return (f"From the 2026 estimate of {pct(est['ratio'])} the IMF projection rises to {pct(end['ratio'])} in {end['year']}, "
                f"up {delta:.2f} percentage points. {label}")
    if delta <= -5:
        return (f"The IMF projection takes {name} from {pct(est['ratio'])} in 2026 to {pct(end['ratio'])} in {end['year']}, "
                f"down {abs(delta):.2f} percentage points. {label}")
    return (f"The IMF projection stays near the 2026 estimate: {pct(end['ratio'])} in {end['year']}, "
            f"{abs(delta):.2f} percentage points from {pct(est['ratio'])}. {label}")


def start_paragraph(p):
    hist = _points(p, {"history"})
    if not hist or hist[0]["year"] <= 2000:
        return ""
    return (f"The IMF series for {p['name']} in this vintage starts in {hist[0]['year']}, "
            f"so the table has no 2000 row. It runs through the 2026 estimate and the projections that follow.")


def rank_paragraph(p):
    return (f"{p['name']} ranks {p['rank_debt']} of {p['n']} by the 2026 dollar stock "
            f"({money(p['debt_2026'])}) and {p['rank_ratio']} of {p['n']} by debt to GDP ({pct(p['ratio_2026'])}).")


def compare_paragraph(p, us, peers, outside):
    gap = p["ratio_2026"] - us["ratio_2026"]
    if gap >= 1:
        us_bit = (f"{pct(p['ratio_2026'])} is {gap:.2f} percentage points above the IMF figure for the United States "
                  f"({pct(us['ratio_2026'])}, {money(us['debt_2026'])}).")
    elif gap <= -1:
        us_bit = (f"{pct(p['ratio_2026'])} is {abs(gap):.2f} percentage points below the IMF figure for the United States "
                  f"({pct(us['ratio_2026'])}, {money(us['debt_2026'])}).")
    else:
        us_bit = (f"{pct(p['ratio_2026'])} is within one percentage point of the IMF figure for the United States "
                  f"({pct(us['ratio_2026'])}).")
    med = p["region_median"]
    where = _in_region(p["region"])
    place = f"{ordinal(p['region_rank_ratio'])} of {p['region_n']} by the ratio and {ordinal(p['region_rank_debt'])} by the dollar stock"
    if med is None:
        reg_bit = ""
    elif p["ratio_2026"] > med + 0.5:
        reg_bit = (f" Among economies {where}, {pct(p['ratio_2026'])} is above the median of {pct(med)}. "
                   f"{p['name']} is {place}.")
    elif p["ratio_2026"] < med - 0.5:
        reg_bit = (f" Among economies {where}, {pct(p['ratio_2026'])} is below the median of {pct(med)}. "
                   f"{p['name']} is {place}.")
    else:
        reg_bit = (f" {pct(p['ratio_2026'])} is within half a point of the median {where} ({pct(med)}). "
                   f"{p['name']} is {place}.")
    bits = []
    for o in peers[:3]:
        if o["ratio_2026"] > p["ratio_2026"] + 0.05:
            rel = "a higher ratio"
        elif o["ratio_2026"] < p["ratio_2026"] - 0.05:
            rel = "a lower ratio"
        else:
            rel = "about the same ratio"
        bits.append(f"{o['name']} ({pct(o['ratio_2026'])}, {rel})")
    who = "Closest economies by 2026 GDP, including some outside the region," if outside else "Closest economies in the region by 2026 GDP:"
    if outside:
        peer = who + " " + "; ".join(bits) + "."
    else:
        peer = who + " " + "; ".join(bits) + "."
    return us_bit + reg_bit + " " + peer


def person_paragraph(p, us):
    pop, year = _pop(p)
    us_pop, us_year = _pop(us)
    if not pop or not us_pop:
        return ""
    mine = p["debt_2026"] / pop
    theirs = us["debt_2026"] / us_pop
    share = mine / theirs if theirs else None
    year_bit = "2026" if year == p["estimate_year"] else str(year)
    src = (f"Population is the IMF estimate of {pop:,} people in {year_bit} "
           f"(indicator LP, persons), from the October 2026 World Economic Outlook published {PUBLISHED}.")
    if share is None:
        return src
    if share >= 1.05:
        rel = f"higher than the same calculation for the United States ({per_person(us['debt_2026'], us_pop)} per person, population {us_pop:,} in {us_year})"
    elif share <= 0.5:
        rel = f"under half the same calculation for the United States ({per_person(us['debt_2026'], us_pop)} per person, population {us_pop:,} in {us_year})"
    else:
        rel = f"set against the same calculation for the United States ({per_person(us['debt_2026'], us_pop)} per person, population {us_pop:,} in {us_year})"
    return (f"Dividing the {money0(p['debt_2026'])} stock by that population gives {per_person(p['debt_2026'], pop)} per person, {rel}. {src}")


def h1_text(p):
    return (f"{p['name']}'s general government gross debt is {money(p['debt_2026'])} "
            f"in the IMF estimate for 2026 (IMF World Economic Outlook, published {PUBLISHED}).")


def distinct_reading(p):
    """A long reading of this country's own path. The years and the direction of each move are the content."""
    hist = _points(p, {"history"})
    if len(hist) < 4:
        return ""
    moves = []
    for a, b in zip(hist, hist[1:]):
        moves.append({"year": b["year"], "prev": a["year"], "delta": b["ratio"] - a["ratio"], "ratio": b["ratio"], "from": a["ratio"]})
    rises = [m for m in moves if m["delta"] > 1]
    falls = [m for m in moves if m["delta"] < -1]
    flat = [m for m in moves if abs(m["delta"]) <= 1]
    biggest = max(moves, key=lambda m: abs(m["delta"]))
    name = p["name"]
    if biggest["delta"] <= -10 and biggest["year"] < 2010:
        opener = (f"The sharpest one-year drop in {poss(name)} published series came before 2010: "
                  f"{pct(biggest['from'])} in {biggest['prev']} to {pct(biggest['ratio'])} in {biggest['year']}, "
                  f"down {abs(biggest['delta']):.2f} percentage points.")
    elif biggest["delta"] >= 10 and biggest["year"] >= 2020:
        opener = (f"The sharpest one-year jump in {poss(name)} published series is in the 2020s: "
                  f"{pct(biggest['from'])} in {biggest['prev']} to {pct(biggest['ratio'])} in {biggest['year']}, "
                  f"up {biggest['delta']:.2f} percentage points.")
    elif biggest["delta"] >= 10:
        opener = (f"The largest one-year rise for {name} is {biggest['delta']:.2f} percentage points, "
                  f"from {pct(biggest['from'])} in {biggest['prev']} to {pct(biggest['ratio'])} in {biggest['year']}.")
    elif biggest["delta"] <= -10:
        opener = (f"The largest one-year fall for {name} is {abs(biggest['delta']):.2f} percentage points, "
                  f"from {pct(biggest['from'])} in {biggest['prev']} to {pct(biggest['ratio'])} in {biggest['year']}.")
    else:
        opener = (f"No single year moves {poss(name)} ratio by 10 points. The largest change is "
                  f"{biggest['delta']:+.2f} points, from {pct(biggest['from'])} in {biggest['prev']} to {pct(biggest['ratio'])} in {biggest['year']}.")
    others = sorted((m for m in moves if m is not biggest), key=lambda m: abs(m["delta"]), reverse=True)[:4]
    bits = []
    for m in others:
        way = "up" if m["delta"] >= 0 else "down"
        bits.append(f"{way} {abs(m['delta']):.2f} points in {m['year']} (to {pct(m['ratio'])})")
    follow = "The next largest changes are " + ", ".join(bits) + "." if bits else ""
    count = (f"From {hist[0]['year']} to {hist[-1]['year']}, the ratio rose by more than one point in {len(rises)} years, "
             f"fell by more than one point in {len(falls)} years, and moved by a point or less in {len(flat)} years.")
    by = {pt["year"]: pt["ratio"] for pt in hist}
    anchors = []
    for y0, y1, label in ((2000, 2010, "From 2000 to 2010"), (2010, 2019, "From 2010 to 2019"), (2019, 2025, "From 2019 to 2025")):
        if y0 in by and y1 in by:
            d = by[y1] - by[y0]
            way = "higher" if d > 0 else "lower" if d < 0 else "unchanged"
            anchors.append(f"{label} it was {way} by {abs(d):.2f} points, {pct(by[y0])} then {pct(by[y1])}")
    anchor = (". ".join(anchors) + ".") if anchors else ""
    # Decade windows already covered elsewhere. Here, name the high and low inside each decade that exists.
    decades = []
    for start, end, label in ((1990, 1999, "the 1990s"), (2000, 2009, "the 2000s"), (2010, 2019, "the 2010s"), (2020, 2025, "2020–2025")):
        pts = [pt for pt in hist if start <= pt["year"] <= end]
        if len(pts) < 3:
            continue
        lo = min(pts, key=lambda pt: pt["ratio"])
        hi = max(pts, key=lambda pt: pt["ratio"])
        up = sum(1 for a, b in zip(pts, pts[1:]) if b["ratio"] > a["ratio"])
        if hi["year"] < lo["year"]:
            decades.append(f"In {label} the high comes first ({pct(hi['ratio'])} in {hi['year']}) and the low is {pct(lo['ratio'])} in {lo['year']}, with the ratio up in {up} of the {len(pts) - 1} steps")
        elif hi["year"] > lo["year"]:
            decades.append(f"In {label} the low comes first ({pct(lo['ratio'])} in {lo['year']}) and the high is {pct(hi['ratio'])} in {hi['year']}, with the ratio up in {up} of the {len(pts) - 1} steps")
        else:
            decades.append(f"In {label} the high and the low fall in {hi['year']}")
    decade = ". ".join(decades) + "." if decades else ""
    highs = []
    mark = -1
    for pt in hist:
        if pt["ratio"] > mark + 0.05:
            highs.append(f"{pt['year']} ({pct(pt['ratio'])})")
            mark = pt["ratio"]
    high_line = ""
    if highs:
        shown = ", ".join(highs[:8])
        extra = f", plus {len(highs) - 8} later highs" if len(highs) > 8 else ""
        high_line = f"A new high was reached in {len(highs)} published years: {shown}{extra}."
    return " ".join(x for x in (opener, follow, count, anchor, decade, high_line) if x)


def threshold_lists(p):
    """Which published years sit above each round threshold. The year lists differ by country."""
    hist = _points(p, {"history"})
    if not hist:
        return ""
    bits = []
    for level in (30, 60, 100, 150):
        years = [str(pt["year"]) for pt in hist if pt["ratio"] >= level]
        if not years:
            bits.append(f"No published year is at or above {level}% of GDP")
        elif len(years) == len(hist):
            bits.append(f"Every published year from {years[0]} through {years[-1]} is at or above {level}% of GDP")
        else:
            shown = ", ".join(years[:12])
            more = f", and {len(years) - 12} later years" if len(years) > 12 else ""
            bits.append(f"Published years at or above {level}% of GDP: {shown}{more}")
    return ". ".join(bits) + "."


def year_roll(p):
    hist = _points(p, {"history"})
    if len(hist) < 4:
        return ""
    bits = [f"{p['name']} {pt['year']}: {pct(pt['ratio'])}" for pt in hist]
    return "Published debt to GDP, one year at a time: " + "; ".join(bits) + "."


def paragraphs(p, us, peers, outside):
    parts = {
        "path": path_paragraph(p),
        "reading": distinct_reading(p),
        "lists": threshold_lists(p),
        "decade": decade_paragraph(p),
        "threshold": threshold_paragraph(p),
        "covid": covid_paragraph(p),
        "projection": projection_paragraph(p),
        "start": start_paragraph(p),
        "rank": rank_paragraph(p),
        "compare": compare_paragraph(p, us, peers, outside),
        "person": person_paragraph(p, us),
        "roll": year_roll(p),
    }
    hist = _points(p, {"history"})
    hist_high = max((pt["ratio"] for pt in hist), default=0)
    proj = _points(p, {"projection"})
    proj_high = max((pt["ratio"] for pt in proj), default=0)
    if p["ratio_2026"] >= 100:
        order = ("threshold", "reading", "lists", "path", "decade", "covid", "projection", "start", "rank", "compare", "person")
    elif proj_high > hist_high and proj_high > p["ratio_2026"]:
        order = ("projection", "reading", "lists", "path", "threshold", "decade", "covid", "start", "rank", "compare", "person")
    elif parts["covid"] and "spike" in parts["covid"]:
        order = ("covid", "reading", "lists", "path", "decade", "threshold", "projection", "start", "rank", "compare", "person")
    elif any(abs(m["delta"]) >= 25 for m in _decade_moves(p)):
        order = ("decade", "reading", "lists", "path", "threshold", "covid", "projection", "start", "rank", "compare", "person")
    else:
        order = ("reading", "lists", "path", "decade", "threshold", "covid", "projection", "start", "rank", "compare", "person")
    out = [parts[k] for k in order if parts.get(k)]
    if parts.get("roll"):
        out.append(parts["roll"])
    return out


def faqs(p, us, peers, outside):
    pop, year = _pop(p)
    hist = _points(p, {"history", "estimate"})
    hi = max(hist, key=lambda pt: (pt["ratio"], -pt["year"])) if hist else None
    r = p["ratio_2026"]
    name = p["name"]
    out = []
    if r >= 100:
        q1 = f"Is {poss(name)} general government debt larger than its GDP?"
        a1 = (f"Yes. The IMF's 2026 estimate is {pct(r)} of GDP, {money0(p['debt_2026'])}. "
              f"Source: {SOURCE}, GGXWDG_NGDP times NGDPD, published {PUBLISHED}.")
    elif r >= 60:
        q1 = f"Is {poss(name)} general government debt above 60% of GDP?"
        a1 = (f"Yes. The IMF's 2026 estimate is {pct(r)} of GDP, {money0(p['debt_2026'])}, which is above 60% and below 100%. "
              f"Source: {SOURCE}, published {PUBLISHED}.")
    else:
        q1 = f"Is {poss(name)} general government debt under 60% of GDP?"
        a1 = (f"Yes. The IMF's 2026 estimate is {pct(r)} of GDP, {money0(p['debt_2026'])}. "
              f"Source: {SOURCE}, GGXWDG_NGDP times NGDPD, published {PUBLISHED}.")
    out.append((q1, a1))
    if hi:
        kind = "a projection" if hi["status"] == "projection" else "the 2026 estimate" if hi["status"] == "estimate" else "a published year"
        if hi["status"] == "projection":
            q2 = f"Does the IMF project a new high for {poss(name)} debt ratio?"
        elif hi["year"] == 2020:
            q2 = f"Was 2020 the peak of {poss(name)} debt ratio?"
        else:
            q2 = f"When was {poss(name)} debt-to-GDP ratio at its high?"
        a2 = (f"The high in this file is {pct(hi['ratio'])} in {hi['year']}, which is {kind}. "
              f"The 2026 estimate is {pct(r)}.")
        out.append((q2, a2))
    moves = _decade_moves(p)
    if moves:
        top = max(moves, key=lambda m: abs(m["delta"]))
        way = "rise" if top["delta"] >= 0 else "fall"
        q3 = f"Which stretch shows the largest {way} in {poss(name)} debt ratio?"
        a3 = (f"{top['label'].capitalize() if top['label'][0].islower() else top['label']}: "
              f"from {pct(top['r0'])} in {top['y0']} to {pct(top['r1'])} in {top['y1']}, "
              f"{'up' if top['delta'] >= 0 else 'down'} {abs(top['delta']):.2f} percentage points. "
              f"That uses published years only, not the IMF projections.")
        out.append((q3, a3))
    if pop:
        q4 = f"How much of {poss(name)} general government debt is that per person?"
        a4 = person_paragraph(p, us)
        out.append((q4, a4))
    q5 = f"How does {name} compare with the United States and with its region?"
    a5 = compare_paragraph(p, us, peers, outside) + " " + rank_paragraph(p)
    out.append((q5, a5))
    return out[:5]


def chart_svg(p):
    series = p["series"]
    if len(series) < 2:
        return ""
    vals = [pt["ratio"] for pt in series]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    lo2, hi2 = lo - span * 0.08, hi + span * 0.12
    w, h = 680, 200
    pl, pr, top, bot = 44, 668, 16, 168

    def xy(i, v):
        x = pl if len(series) == 1 else pl + i * (pr - pl) / (len(series) - 1)
        y = top + (1 - (v - lo2) / (hi2 - lo2)) * (bot - top)
        return x, y

    def poly(indexes):
        return " ".join(f"{xy(i, series[i]['ratio'])[0]:.1f},{xy(i, series[i]['ratio'])[1]:.1f}" for i in indexes)

    hist_i = [i for i, pt in enumerate(series) if pt["status"] != "projection"]
    proj_i = [i for i, pt in enumerate(series) if pt["status"] == "projection"]
    if hist_i and proj_i:
        proj_i = [hist_i[-1]] + proj_i
    parts = [f'<svg class="dchart" viewBox="0 0 {w} {h}" role="img" aria-label="{E(p["name"])} general government debt to GDP, {series[0]["year"]} to {series[-1]["year"]}, IMF World Economic Outlook October 2026. Dashed segment is the projection.">',
             f'<title>{E(p["name"])} debt to GDP, {series[0]["year"]}–{series[-1]["year"]}</title>']
    for level, lab in ((60, "60%"), (100, "100% of GDP")):
        if lo2 < level < hi2:
            y = xy(0, level)[1]
            parts.append(f'<line x1="{pl}" y1="{y:.1f}" x2="{pr}" y2="{y:.1f}" stroke="#2a3548" stroke-dasharray="3 4"/>')
            parts.append(f'<text x="{pl + 4}" y="{y - 3:.1f}" fill="#8a97ab" font-size="11">{lab}</text>')
    if hist_i:
        parts.append(f'<polyline fill="none" stroke="#ffb547" stroke-width="2.5" points="{poly(hist_i)}"/>')
    if proj_i:
        parts.append(f'<polyline fill="none" stroke="#5aa9ff" stroke-width="2.5" stroke-dasharray="5 4" points="{poly(proj_i)}"/>')
    # year labels at ends and at 2000 when present
    labels = {0, len(series) - 1}
    for i, pt in enumerate(series):
        if pt["year"] in (2000, p["estimate_year"], p["projection_from"]):
            labels.add(i)
    for i in sorted(labels):
        x, _ = xy(i, series[i]["ratio"])
        anchor = "start" if i == 0 else "end" if i == len(series) - 1 else "middle"
        parts.append(f'<text x="{x:.1f}" y="{h - 8}" fill="#8a97ab" font-size="11" text-anchor="{anchor}">{series[i]["year"]}</text>')
    parts.append("</svg>")
    return "".join(parts)


def history_table(p):
    rows = []
    for pt in p["series"]:
        cls = ' class="proj"' if pt["status"] == "projection" else ' class="est"' if pt["status"] == "estimate" else ""
        label = {"history": "History", "estimate": "Estimate", "projection": "Projection"}[pt["status"]]
        rows.append(f"<tr{cls}><td>{pt['year']}</td><td class=\"num\">{pct(pt['ratio'])}</td><td>{label}</td></tr>")
    y0, y1 = p["series"][0]["year"], p["series"][-1]["year"]
    note = (f"{E(p['name'])} general government gross debt, percent of GDP, {y0}–{y1}. "
            f"History through {p['history_through']}, {p['estimate_year']} estimate, "
            f"{p['projection_from']}–{y1} IMF projections. "
            f"Source: {E(SOURCE)}, GGXWDG_NGDP, published {PUBLISHED}.")
    return (f'<table class="wt" id="path" style="min-width:0;max-width:420px">'
            f'<caption class="legend-line">{note}</caption>'
            f'<tr class="hd"><th>Year</th><th class="num">Debt / GDP</th><th>Status</th></tr>{"".join(rows)}</table>')


def peer_table(p, peers):
    rows = (f'<tr><td><b>{E(p["name"])}</b></td><td class="num">{pct(p["ratio_2026"])}</td>'
            f'<td class="num">{money(p["debt_2026"])}</td><td class="num">{money(p["gdp_2026"])}</td></tr>')
    for o in peers:
        href = "../../" if o.get("iso3") == "USA" or o.get("clock") == "us" else f"../{o['slug']}/"
        debt = o.get("debt_2026", o.get("debt_2026_usd"))
        gdp = o.get("gdp_2026", o.get("gdp_2026_usd"))
        rows += (f'<tr><td><a href="{href}">{E(o["name"])}</a></td><td class="num">{pct(o["ratio_2026"])}</td>'
                 f'<td class="num">{money(debt)}</td><td class="num">{money(gdp)}</td></tr>')
    return ('<table class="wt" id="peers" style="min-width:0"><tr class="hd"><th>Economy</th>'
            '<th class="num">Debt / GDP, 2026</th><th class="num">Debt, end-2026</th><th class="num">GDP, 2026</th></tr>'
            f'{rows}</table>')


def nav_links():
    return ('<p>More clocks: <a href="../../countries/">all country debt clocks</a>, '
            '<a href="../../world/">the world debt clock</a>, and '
            '<a href="../../">the US national debt clock</a> '
            '(Treasury Debt to the Penny, a different measure from this IMF series).</p>')


def history_section(p, section_id="history", table_id="path"):
    y0 = p["series"][0]["year"]
    y1 = p["series"][-1]["year"]
    table = history_table(p).replace('id="path"', f'id="{table_id}"', 1)
    return (f'<section id="{section_id}"><div class="sh"><span class="bar" style="background:var(--violet)"></span>'
            f'<h2>Debt to GDP, {y0}–{y1}</h2>'
            f'<span class="h2n">IMF GGXWDG_NGDP · projections dashed</span></div>'
            f'<p class="legend-line">Solid line: published series through {p["history_through"]}, plus the {p["estimate_year"]} estimate. '
            f'Dashed line: IMF projections from {p["projection_from"]}. Reference lines mark 60% and 100% of GDP when they fall inside the scale.</p>'
            f'{chart_svg(p)}<div class="tw">{table}</div></section>')


def compare_section(p, peers, outside):
    note = (" Fewer than three other economies in this region are in the panel, so the table reaches outside the region."
            if outside else " The other rows are the economies in the same region with the closest 2026 GDP.")
    return (f'<section id="compare"><div class="sh"><span class="bar" style="background:var(--teal)"></span>'
            f'<h2>Rank, debt per person, and peers</h2>'
            f'<span class="h2n">Same IMF measure · 2026 estimate</span></div>'
            f'<p>{E(rank_paragraph(p))}{E(note)}</p>'
            f'<div class="tw">{peer_table(p, peers)}</div></section>')


def lead_html(p, us, peers, outside):
    body = "".join(f"<p>{E(text)}</p>" for text in paragraphs(p, us, peers, outside))
    return body + nav_links()


def series_document(p):
    pop, year = _pop(p)
    return {
        "country": p["name"], "iso3": p["iso3"], "slug": p["slug"],
        "vintage": "October 2026", "published": p["published"],
        "source": SOURCE, "source_url": RATIO_URL, "publication_url": PUB_URL,
        "indicator": "GGXWDG_NGDP", "unit": "percent of GDP",
        "debt_2026_usd": p["debt_2026"], "debt_2025_usd": p["debt_2025"],
        "ratio_2026": p["ratio_2026"], "ratio_2025": p["ratio_2025"],
        "population": pop, "population_year": year, "population_indicator": "LP",
        "population_unit": "persons", "population_source_url": POP_URL,
        "history_through": p["history_through"], "estimate_year": p["estimate_year"],
        "projection_from": p["projection_from"],
        "series": [{"year": pt["year"], "debt_to_gdp_pct": pt["ratio"], "status": pt["status"]} for pt in p["series"]],
    }


def write_series(R, p):
    os.makedirs(os.path.join(R, "country-series"), exist_ok=True)
    path = os.path.join(R, "country-series", p["slug"] + ".json")
    json.dump(series_document(p), open(path, "w"), indent=1, ensure_ascii=False)
    open(path, "a").write("\n")


def faq_ld(pairs):
    ld = {"@context": "https://schema.org", "@type": "FAQPage", "dateModified": "2026-10-13",
          "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in pairs]}
    return '<script type="application/ld+json">' + json.dumps(ld).replace("</", "<\\/") + "</script>"


def dataset_ld(p, url, desc):
    pop, year = _pop(p)
    y0 = p["series"][0]["year"] if p["series"] else p["estimate_year"]
    y1 = p["series"][-1]["year"] if p["series"] else p["estimate_year"]
    ld = {"@context": "https://schema.org", "@type": "Dataset",
          "name": f"{p['name']} general government gross debt, IMF World Economic Outlook October 2026",
          "description": desc, "url": url, "dateModified": p["published"],
          "temporalCoverage": f"{y0}/{y1}", "isAccessibleForFree": True,
          "creator": [{"@type": "Organization", "name": "International Monetary Fund", "url": "https://www.imf.org/"},
                      {"@type": "Organization", "name": "Every Debt Clock", "url": "https://everydebtclock.com/"}],
          "publisher": {"@type": "Organization", "name": "Every Debt Clock", "url": "https://everydebtclock.com/"},
          "creditText": "IMF World Economic Outlook, October 2026, GGXWDG_NGDP",
          "isBasedOn": [RATIO_URL, POP_URL, PUB_URL],
          "distribution": [{"@type": "DataDownload", "encodingFormat": "application/json",
                            "contentUrl": f"https://everydebtclock.com/country-series/{p['slug']}.json"}]}
    if pop:
        ld["variableMeasured"] = ["GGXWDG_NGDP", "general government gross debt, US dollars", "LP population"]
    return '<script type="application/ld+json">' + json.dumps(ld).replace("</", "<\\/") + "</script>"


_CACHE = None


def _cached(R):
    """Profiles for every IMF economy, built once per process."""
    global _CACHE
    if _CACHE and _CACHE[0] == R:
        return _CACHE[1], _CACHE[2]
    import weo_build
    history = load(R)
    economies = json.load(open(os.path.join(R, "data", "world_weo_debt.json")))["economies"]
    weo_build._annotate(economies)
    profiles = build_profiles(economies, history)
    _CACHE = (R, profiles, economies)
    return profiles, economies


def official_section(R, place):
    """IMF debt-to-GDP profile for an official country clock. Empty when that economy is not in the WEO file."""
    import world_build
    iso = place.get("iso3") or world_build.ISO3.get(place.get("country") or "")
    if not iso:
        return ""
    profiles, economies = _cached(R)
    p = profiles.get(iso)
    if not p or iso == "USA":
        return ""
    import weo_build
    e = next(x for x in economies if x["iso3"] == iso)
    peers, outside = weo_build._peers(e, economies)
    us = profiles["USA"]
    paras = "".join(f"<p>{E(text)}</p>" for text in paragraphs(p, us, peers, outside))
    return (f'<section id="profile"><div class="sh"><span class="bar" style="background:var(--amber)"></span>'
            f'<h2>IMF debt to GDP, for comparison</h2>'
            f'<span class="h2n">{E(SOURCE)} · published {PUBLISHED}</span></div>'
            f'<p>{E(h1_text(p))} This is general government gross debt, a wider measure than the clock on this page when the clock is central or federal debt.</p>'
            f'{paras}{history_section(p, "imf-history", "imf-path")}'
            f'{compare_section(p, peers, outside)}</section>')


def visible_main(page):
    """Visible text of the page body. Scripts, styles and tags are not body text."""
    m = re.search(r"<main\b[^>]*>(.*)</main>", page, re.S | re.I)
    chunk = m.group(1) if m else page
    chunk = re.sub(r"<script\b[^>]*>.*?</script>", " ", chunk, flags=re.S | re.I)
    chunk = re.sub(r"<style\b[^>]*>.*?</style>", " ", chunk, flags=re.S | re.I)
    chunk = re.sub(r"<[^>]+>", " ", chunk)
    chunk = html.unescape(chunk)
    return re.sub(r"\s+", " ", chunk).strip()


def _tokens(text):
    return text.split()


def visible_body(page):
    """Article text. The shared clock-method boilerplate is not what makes two countries the same page."""
    page = re.sub(r'<section[^>]*\bid="method"[\s\S]*?</section>', " ", page)
    return visible_main(page)


def assert_country_pages_differ(root, limit=0.80):
    """Fail if any two /countries/<slug>/ pages share more than `limit` of their article text.

    The comparison is difflib's ratio on the words of <main>, after the shared "How it works" section
    is set aside. Scripts, styles and tags are not text. A ratio above the limit means the two articles
    are the same template with the names swapped.
    """
    base = os.path.join(root, "countries")
    pages = []
    if not os.path.isdir(base):
        raise SystemExit("country pages: countries/ was not built")
    for slug in sorted(os.listdir(base)):
        path = os.path.join(base, slug, "index.html")
        if os.path.isfile(path):
            pages.append((slug, _tokens(visible_body(open(path, encoding="utf-8").read()))))
    if len(pages) < 2:
        raise SystemExit("country pages: fewer than two country pages to compare")
    worst = (0.0, "", "")
    for i in range(len(pages)):
        ai, a = pages[i]
        for j in range(i + 1, len(pages)):
            bj, b = pages[j]
            bound = 2 * min(len(a), len(b)) / (len(a) + len(b) or 1)
            if bound <= limit:
                continue
            ratio = SequenceMatcher(None, a, b).ratio()
            if ratio > worst[0]:
                worst = (ratio, ai, bj)
            if ratio > limit:
                raise SystemExit(f"country pages {ai} and {bj} share {ratio:.1%} of their body text (limit {limit:.0%})")
    print(f"country pages distinct: {len(pages)} pages, closest {worst[1]} / {worst[2]} at {worst[0]:.1%}", flush=True)
    return worst
