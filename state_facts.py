"""Quotable figures for /states/<slug>/, computed only from Census and BEA inputs already on disk.

The clock stays the state-and-local total the page already ticks (or holds). This block,
under that clock, quotes state government debt on its own, debt per resident, debt divided
by BEA current-dollar GDP, rank, and the Census history. A missing input is left out.
"""
import datetime as dt
import html
import json
import os
from difflib import SequenceMatcher

import debt_by_year_build as dy

E = html.escape
CENSUS_RELEASE = "https://www.census.gov/data/datasets/2024/econ/local/public-use-datasets.html"
CITE = "Source: Every Debt Clock (everydebtclock.com), from the U.S. Census Bureau."

# Census Bureau divisions. Used only to name the peer group; the medians are computed from the debt figures.
DIVISION = {
    "connecticut": "New England", "maine": "New England", "massachusetts": "New England",
    "new-hampshire": "New England", "rhode-island": "New England", "vermont": "New England",
    "new-jersey": "Middle Atlantic", "new-york": "Middle Atlantic", "pennsylvania": "Middle Atlantic",
    "illinois": "East North Central", "indiana": "East North Central", "michigan": "East North Central",
    "ohio": "East North Central", "wisconsin": "East North Central",
    "iowa": "West North Central", "kansas": "West North Central", "minnesota": "West North Central",
    "missouri": "West North Central", "nebraska": "West North Central", "north-dakota": "West North Central",
    "south-dakota": "West North Central",
    "delaware": "South Atlantic", "district-of-columbia": "South Atlantic", "florida": "South Atlantic",
    "georgia": "South Atlantic", "maryland": "South Atlantic", "north-carolina": "South Atlantic",
    "south-carolina": "South Atlantic", "virginia": "South Atlantic", "west-virginia": "South Atlantic",
    "alabama": "East South Central", "kentucky": "East South Central", "mississippi": "East South Central",
    "tennessee": "East South Central",
    "arkansas": "West South Central", "louisiana": "West South Central", "oklahoma": "West South Central",
    "texas": "West South Central",
    "arizona": "Mountain", "colorado": "Mountain", "idaho": "Mountain", "montana": "Mountain",
    "nevada": "Mountain", "new-mexico": "Mountain", "utah": "Mountain", "wyoming": "Mountain",
    "alaska": "Pacific", "california": "Pacific", "hawaii": "Pacific", "oregon": "Pacific",
    "washington": "Pacific",
}

_CACHE = {}


def _date(s):
    return dt.date.fromisoformat(s).strftime("%B %-d, %Y")


def _usd(n):
    return ("−" if n < 0 else "") + f"${abs(n):,.0f}"


def _usd2(n):
    return ("−" if n < 0 else "") + f"${abs(n):,.2f}"


def _pct(n):
    return f"{n:.2f}%"


def _poss(name):
    return name + ("'" if name.endswith("s") else "'s")


def _ord(n):
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _median(vals):
    s = sorted(vals)
    n = len(s)
    if not n:
        return None
    if n % 2:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2


def _gdp_usd(millions):
    return int(round(float(millions) * 1_000_000))


def _load_gdp(R):
    path = os.path.join(R, "data", "state_gdp.json")
    if not os.path.exists(path):
        return None
    return json.load(open(path))


def _component(p, key):
    return next((c for c in p["components"] if c["key"] == key), None)


def _one(R, p, gdp_doc):
    slug = p["slug"]
    if slug not in DIVISION:
        raise SystemExit(f"state facts: {slug} has no Census division")
    rec = dy.load(R)["places"].get(slug)
    if not rec or rec.get("kind") != "state":
        raise SystemExit(f"state facts: {slug} has no Census debt-by-year series")
    rows, _place = dy.state_rows(R, slug, rec["rows"])
    dc = slug == "district-of-columbia"
    state = _component(p, "state")
    local = _component(p, "local")
    if dc:
        if state is not None or local is None:
            raise SystemExit("state facts: District of Columbia should have only the local component")
        total = int(local["value"])
        total_as_of = local["as_of"]
        state_debt = None
        state_as_of = None
        state_url = local["source_url"]
        state_name = local["source_name"]
    else:
        if state is None or local is None:
            raise SystemExit(f"state facts: {slug} is missing state or local debt")
        if state["as_of"] != local["as_of"]:
            raise SystemExit(f"state facts: {slug} state and local dates differ")
        total = int(state["value"]) + int(local["value"])
        total_as_of = state["as_of"]
        state_debt = int(state["value"])
        state_as_of = state["as_of"]
        state_url = state["source_url"]
        state_name = state["source_name"]
    pop = p.get("population") or {}
    pop_n = int(pop["value"]) if pop.get("value") else None
    per_total = (total / pop_n) if pop_n else None
    per_state = (state_debt / pop_n) if pop_n and state_debt is not None else None
    year = total_as_of[:4]
    gdp_usd = gdp_year = None
    ratio_state = ratio_total = None
    gdp_latest = gdp_latest_year = None
    if gdp_doc and slug in gdp_doc.get("states", {}):
        series = gdp_doc["states"][slug]["gdp_millions_current"]
        if year in series:
            gdp_year = int(year)
            gdp_usd = _gdp_usd(series[year])
            if gdp_usd:
                ratio_total = total / gdp_usd * 100
                if state_debt is not None:
                    ratio_state = state_debt / gdp_usd * 100
        if series:
            gdp_latest_year = max(int(y) for y in series)
            gdp_latest = _gdp_usd(series[str(gdp_latest_year)])
    else:
        series = {}
    hist = [{"year": r["year"], "date": r["date"], "state": int(r["state"]), "local": int(r["local"]),
             "total": int(r["amount"])} for r in rows]
    import places_build
    c = places_build.calc(p)
    return {
        "slug": slug, "name": p["name"], "dc": dc, "division": DIVISION[slug],
        "state_debt": state_debt, "state_as_of": state_as_of,
        "local_debt": int(local["value"]) if local else None,
        "local_as_of": local["as_of"] if local else None,
        "total": total, "total_as_of": total_as_of,
        "source_name": state_name, "source_url": state_url,
        "pop": pop_n, "pop_as_of": pop.get("as_of"),
        "pop_source_name": pop.get("source_name") or "U.S. Census Bureau",
        "pop_source_url": pop.get("source_url") or "",
        "per_total": per_total, "per_state": per_state,
        "gdp_year": gdp_year, "gdp_usd": gdp_usd,
        "gdp_latest": gdp_latest, "gdp_latest_year": gdp_latest_year,
        "ratio_state": ratio_state, "ratio_total": ratio_total,
        "gdp_series": series,
        "gdp_source": (gdp_doc or {}).get("source") or "",
        "gdp_url": (gdp_doc or {}).get("source_url") or "",
        "gdp_file_date": (gdp_doc or {}).get("file_date") or "",
        "rows": hist,
        "missing": dy.missing_years(rows),
        "hold": bool(p.get("hold_trend")),
        "hold_why": p.get("hold_why") or "",
        "rate": c["rate"],
        "prior_as_of": (state or local).get("prior_as_of"),
        "prior_total": (int(state["prior_value"]) + int(local["prior_value"])) if state and local and state.get("prior_value") is not None and local.get("prior_value") is not None else (int(local["prior_value"]) if dc and local.get("prior_value") is not None else None),
    }


def _ranks(group, key):
    ranked = [p for p in group if p.get(key) is not None]
    ranked.sort(key=lambda p: (-p[key], p["name"]))
    for i, p in enumerate(ranked, 1):
        p[key + "_rank"] = i
        p[key + "_n"] = len(ranked)
        p[key + "_above"] = ranked[i - 2] if i > 1 else None
        p[key + "_below"] = ranked[i] if i < len(ranked) else None
    return ranked


def all_profiles(R):
    if R in _CACHE:
        return _CACHE[R]
    gdp_doc = _load_gdp(R)
    import places_build
    profs = []
    for p in places_build.load(R):
        if p.get("kind") != "state" or p.get("status") != "live":
            continue
        profs.append(_one(R, p, gdp_doc))
    if len(profs) != 51:
        raise SystemExit(f"state facts: expected 51 states and DC, found {len(profs)}")
    states = [p for p in profs if not p["dc"]]
    _ranks(states, "state_debt")
    _ranks(profs, "total")
    _ranks(profs, "per_total")
    _ranks(states, "ratio_state")
    by_div = {}
    for p in states:
        by_div.setdefault(p["division"], []).append(p["state_debt"])
    med_all = _median([p["state_debt"] for p in states])
    for p in profs:
        peers = by_div.get(p["division"], [])
        # State-government median. The District has no state-government total, so it is not in this median.
        p["division_median"] = _median(peers)
        p["division_n"] = len(peers)
        p["states_median"] = med_all
    omitted = []
    for p in profs:
        if p["dc"]:
            omitted.append("District of Columbia: Census publishes no state-government debt total (the District is classified as local). The page quotes that District government total and leaves the state-government line off.")
        elif p["ratio_state"] is None:
            omitted.append(f"{p['name']}: debt-to-GDP omitted (no BEA current-dollar GDP for {p['total_as_of'][:4]}).")
        if p["per_total"] is None:
            omitted.append(f"{p['name']}: debt per resident omitted (no Census population).")
    ticking = sum(1 for p in profs if p["rate"])
    print(f"state facts: {len(profs)} pages, {ticking} ticking, {len(profs) - ticking} held at the Census figure", flush=True)
    for line in omitted:
        print("state facts omit:", line, flush=True)
    _CACHE[R] = profs
    return profs


def _by_slug(R):
    return {p["slug"]: p for p in all_profiles(R)}


# "the 50 states" is the state-government ranking. The other ranking is those 50 plus the District.
GROUP_50 = "the 50 states"
GROUP_51 = "the 50 states and the District of Columbia"


def _rank_sentence(p, key, label, group):
    rank = p.get(key + "_rank")
    n = p.get(key + "_n")
    if not rank:
        return ""
    above, below = p.get(key + "_above"), p.get(key + "_below")
    name = "The District of Columbia" if p["dc"] else p["name"]
    if rank == 1:
        where = f"{name} has the largest {label} of {group}"
    elif rank == n:
        where = f"{name} has the smallest {label} of {group}"
    else:
        where = f"{name} ranks {_ord(rank)} of {group} by {label}"
    extra = ""
    if above and below:
        extra = f" {_poss(above['name'])} debt is larger and {_poss(below['name'])} debt is smaller."
    elif below and rank == 1:
        extra = f" {_poss(below['name'])} debt is next."
    elif above and rank == n:
        extra = f" {_poss(above['name'])} debt is next."
    return where + "." + extra


def _history_bits(p):
    rows = p["rows"]
    if len(rows) < 2:
        return "", ""
    key = "total" if p["dc"] else "state"
    noun = "District government debt" if p["dc"] else "state government debt"
    first, last = rows[0], rows[-1]
    a, b = first[key], last[key]
    delta = b - a
    direction = "rose" if delta > 0 else "fell" if delta < 0 else "was unchanged"
    pct = (delta / a * 100) if a else 0
    hi = max(rows, key=lambda r: (r[key], r["year"]))
    lo = min(rows, key=lambda r: (r[key], -r["year"]))
    one_year = []
    for prev, cur in zip(rows, rows[1:]):
        if cur["year"] - prev["year"] != 1:
            continue
        one_year.append((cur[key] - prev[key], prev, cur))
    swing = ""
    if one_year:
        change, prev, cur = max(one_year, key=lambda item: abs(item[0]))
        way = "increase" if change > 0 else "decrease" if change < 0 else "change"
        swing = (f" The largest one-year {way} in {noun.lower()} was {_usd(abs(change))} "
                 f"from the {prev['year']} survey to {cur['year']}.")
    path = (f"From the {first['year']} survey ({_usd(a)} on {_date(first['date'])}) to the {last['year']} survey "
            f"({_usd(b)} on {_date(last['date'])}), {_poss(p['name'])} {noun.lower()} {direction} {_usd(abs(delta))}"
            f"{f' ({pct:+.1f}%)' if a else ''}. "
            f"The high in this Census file is {_usd(hi[key])} in {hi['year']}. "
            f"The low is {_usd(lo[key])} in {lo['year']}.{swing}")
    bits = []
    for r in rows:
        if p["dc"]:
            bits.append(f"{r['year']} {_usd(r['total'])}")
        else:
            bits.append(f"{r['year']} state {_usd(r['state'])}, local {_usd(r['local'])}")
    roll = "Census survey years in this file: " + "; ".join(bits) + "."
    if p["missing"]:
        listed = ", ".join(str(y) for y in p["missing"])
        roll += f" No row for {listed} in the summary tables this page uses."
    return path, roll


def _clock_sentence(p):
    as_of = _date(p["total_as_of"])
    if p["rate"] and p["prior_as_of"] and p["prior_total"] is not None:
        days = (dt.date.fromisoformat(p["total_as_of"]) - dt.date.fromisoformat(p["prior_as_of"])).days
        per_day = p["rate"] * 86400
        return (f"The clock starts at the Census total of {_usd(p['total'])} on {as_of} and moves "
                f"{_usd2(abs(p['rate']))} per second ({_usd(abs(per_day))} a day), which is the change from "
                f"{_date(p['prior_as_of'])} ({_usd(p['prior_total'])}) to {as_of} spread over {days} days. "
                f"Census publishes this once a year, so the ticking number is a projection, not a new Census figure.")
    why = p["hold_why"] or "Census did not publish a second year to measure a trend from"
    return (f"The clock shows the Census total of {_usd(p['total'])} on {as_of} and does not tick, because {why}.")


def _answer(p):
    """Two sentences an answer engine should quote, with the date and the source."""
    if p["dc"]:
        return (f"The District of Columbia's government debt was {_usd(p['total'])} as of {_date(p['total_as_of'])}. "
                f"Source: U.S. Census Bureau, which does not publish a separate state-government total for the District.")
    return (f"{_poss(p['name'])} state government debt was {_usd(p['state_debt'])} as of {_date(p['state_as_of'])}. "
            f"Source: U.S. Census Bureau.")


def faqs(p):
    out = [(f"How much {'government' if p['dc'] else 'state government'} debt does {p['name']} have?", _answer(p))]
    if p["per_state"] is not None:
        out.append((
            f"How much is {_poss(p['name'])} state government debt per resident?",
            (f"{_poss(p['name'])} state government debt was {_usd2(p['per_state'])} per resident as of {_date(p['state_as_of'])}, "
             f"{_usd(p['state_debt'])} divided by the Census estimate of {p['pop']:,} residents on {_date(p['pop_as_of'])}. "
             f"Source: U.S. Census Bureau."),
        ))
    elif p["dc"] and p["per_total"] is not None:
        out.append((
            "How much is District of Columbia government debt per resident?",
            (f"The District of Columbia's government debt was {_usd2(p['per_total'])} per resident: "
             f"{_usd(p['total'])} as of {_date(p['total_as_of'])}, divided by the Census estimate of "
             f"{p['pop']:,} residents on {_date(p['pop_as_of'])}."),
        ))
    if p["ratio_state"] is not None:
        out.append((
            f"What is {_poss(p['name'])} state government debt as a share of state GDP?",
            (f"{_poss(p['name'])} state government debt of {_usd(p['state_debt'])} as of {_date(p['state_as_of'])} "
             f"was {_pct(p['ratio_state'])} of BEA current-dollar GDP of {_usd(p['gdp_usd'])} for calendar year {p['gdp_year']}. "
             f"Source: U.S. Census Bureau and the Bureau of Economic Analysis; the debt date and the GDP year are not the same twelve months."),
        ))
    elif p["dc"] and p["ratio_total"] is not None:
        out.append((
            "What is District of Columbia government debt as a share of its GDP?",
            (f"The District of Columbia's government debt of {_usd(p['total'])} as of {_date(p['total_as_of'])} "
             f"was {_pct(p['ratio_total'])} of BEA current-dollar GDP of {_usd(p['gdp_usd'])} for calendar year {p['gdp_year']}. "
             f"Source: U.S. Census Bureau and the Bureau of Economic Analysis; the debt date and the GDP year are not the same twelve months."),
        ))
    rank_key = "total" if p["dc"] else "state_debt"
    label = "government debt" if p["dc"] else "state government debt"
    group = GROUP_51 if p["dc"] else GROUP_50
    rank = _rank_sentence(p, rank_key, label, group)
    if rank:
        out.append((f"Where does {p['name']} rank on government debt?", rank + f" Source: U.S. Census Bureau, as of {_date(p['total_as_of'])}."))
    out.append((f"How is the {p['name']} debt clock calculated?", _clock_sentence(p)))
    return out[:5]


def _mil(x):
    s = f"{float(x):.1f}"
    return s[:-2] if s.endswith(".0") else s


def _signed(n):
    return ("+" if n > 0 else "−" if n < 0 else "") + _usd(abs(n))


def series_paragraphs(p):
    """Year-by-year official series. The dollar amounts differ on every state page."""
    name = p["name"]
    rows = p["rows"]
    out = []
    if rows:
        totals = "; ".join(f"{r['year']} {_usd(r['total'])}" for r in rows)
        label = "District government debt" if p["dc"] else "state and local debt combined"
        out.append(f"{name} {label}, Census survey year by survey year: {totals}.")
        key = "total" if p["dc"] else "state"
        noun = "District government debt" if p["dc"] else "state government debt"
        changes = []
        for prev, cur in zip(rows, rows[1:]):
            if cur["year"] - prev["year"] != 1:
                continue
            changes.append(f"{cur['year']} {_signed(cur[key] - prev[key])}")
        if changes:
            out.append(f"{name} one-year change in {noun}, for survey years that follow the previous one directly: {'; '.join(changes)}.")
        if not p["dc"]:
            local_changes = []
            for prev, cur in zip(rows, rows[1:]):
                if cur["year"] - prev["year"] != 1:
                    continue
                local_changes.append(f"{cur['year']} {_signed(cur['local'] - prev['local'])}")
            if local_changes:
                out.append(f"{name} one-year change in local government debt: {'; '.join(local_changes)}.")
    series = p.get("gdp_series") or {}
    if series:
        bits = []
        for y in sorted(series, key=int):
            millions = series[y]
            bits.append(f"{y} {_mil(millions)} million ({_usd(_gdp_usd(millions))})")
        out.append(f"{name} BEA current-dollar GDP, all-industry total, by calendar year: {'; '.join(bits)}. "
                   f"Source: BEA table SAGDP2, file dated {p['gdp_file_date']}. Figures are millions of current dollars as published, not adjusted for inflation.")
        by_year = {r["year"]: r for r in rows}
        ratios = []
        for y in sorted(series, key=int):
            row = by_year.get(int(y))
            gdp = _gdp_usd(series[y])
            if not row or not gdp:
                continue
            debt = row["total"] if p["dc"] else row["state"]
            ratios.append(f"{y} {debt / gdp * 100:.2f}%")
        if ratios:
            which = "District government debt" if p["dc"] else "state government debt"
            out.append(f"{name} {which} divided by that calendar year's BEA GDP. "
                       f"The debt figure is the Census survey year ending June 30, and the GDP figure is the calendar year, so the two are not the same twelve months: {'; '.join(ratios)}.")
    return out


def _chart(p):
    rows = p["rows"]
    if len(rows) < 2:
        return ""
    key = "total" if p["dc"] else "state"
    vals = [r[key] for r in rows]
    w, h = 680, 160
    pl, pr, top, bot = 8, 672, 12, 132
    hi = max(vals) * 1.08 or 1
    def xy(i, v):
        x = pl + i * (pr - pl) / (len(rows) - 1)
        y = top + (1 - v / hi) * (bot - top)
        return x, y
    pts = " ".join(f"{xy(i, v)[0]:.1f},{xy(i, v)[1]:.1f}" for i, v in enumerate(vals))
    labels = []
    for i in (0, len(rows) // 2, len(rows) - 1):
        x, _ = xy(i, vals[i])
        anchor = "start" if i == 0 else "end" if i == len(rows) - 1 else "middle"
        labels.append(f'<text x="{x:.1f}" y="{h - 8}" fill="#8a97ab" font-size="11" text-anchor="{anchor}">{rows[i]["year"]}</text>')
    title = f"{p['name']} {'government' if p['dc'] else 'state government'} debt, Census survey years {rows[0]['year']}–{rows[-1]['year']}"
    return (f'<svg class="dchart" viewBox="0 0 {w} {h}" role="img" aria-label="{E(title)}">'
            f'<title>{E(title)}</title>'
            f'<polyline fill="none" stroke="#ff4d5e" stroke-width="2.5" points="{pts}"/>'
            f'{"".join(labels)}</svg>')


def for_page(R, place):
    """HTML for under the clock, plus FAQPage JSON-LD. Empty for a non-state."""
    if place.get("kind") != "state":
        return "", ""
    p = _by_slug(R)[place["slug"]]
    items = []
    if p["per_total"] is not None:
        items.append(
            f"<li><b>Debt per resident.</b> {_usd2(p['per_total'])}: the Census total of {_usd(p['total'])} "
            f"as of {_date(p['total_as_of'])}, divided by {p['pop']:,} residents on {_date(p['pop_as_of'])} "
            f"(<a href=\"{E(p['pop_source_url'])}\" rel=\"noopener\">{E(p['pop_source_name'])}</a>). "
            + (f"State government debt alone was {_usd2(p['per_state'])} per resident." if p["per_state"] is not None else "")
            + "</li>"
        )
    if p["ratio_state"] is not None or (p["dc"] and p["ratio_total"] is not None):
        ratio = p["ratio_state"] if p["ratio_state"] is not None else p["ratio_total"]
        debt = p["state_debt"] if p["state_debt"] is not None else p["total"]
        which = "State government debt" if not p["dc"] else "District government debt"
        newer = ""
        if p["gdp_latest_year"] and p["gdp_year"] and p["gdp_latest_year"] != p["gdp_year"] and p["gdp_latest"]:
            newer = (f" BEA's latest year in this file is {p['gdp_latest_year']} ({_usd(p['gdp_latest'])}). "
                     f"The ratio uses {p['gdp_year']}, the calendar year of the Census debt date.")
        items.append(
            f"<li><b>Debt to state GDP.</b> {which} of {_usd(debt)} as of {_date(p['total_as_of'])} "
            f"was {_pct(ratio)} of <a href=\"{E(p['gdp_url'])}\" rel=\"noopener\">BEA</a> current-dollar GDP "
            f"of {_usd(p['gdp_usd'])} for calendar year {p['gdp_year']} (table SAGDP2, all-industry total, "
            f"file dated {E(p['gdp_file_date'])}). The Census date is the survey year-end. "
            f"The BEA figure is the calendar year. They are not the same twelve months.{newer}"
            + (f" State and local debt together was {_pct(p['ratio_total'])} of that same GDP." if p["ratio_total"] is not None and not p["dc"] else "")
            + "</li>"
        )
    rank_bits = []
    if not p["dc"] and p.get("state_debt_rank"):
        rank_bits.append(_rank_sentence(p, "state_debt", "state government debt", GROUP_50))
    if p.get("total_rank"):
        rank_bits.append(_rank_sentence(p, "total", "state and local debt" if not p["dc"] else "government debt", GROUP_51))
    if p.get("per_total_rank"):
        rank_bits.append(_rank_sentence(p, "per_total", "debt per resident", GROUP_51))
    if p.get("ratio_state_rank"):
        rank_bits.append(_rank_sentence(p, "ratio_state", "state-government debt to GDP", GROUP_50))
    if rank_bits:
        med = ""
        if p["states_median"] is not None and not p["dc"]:
            side = "above" if p["state_debt"] >= p["states_median"] else "below"
            med = (f" The median state government debt among the 50 states is {_usd(p['states_median'])}. "
                   f"{p['name']} is {side} that median. In the {p['division']} division "
                   f"({p['division_n']} states), the median state government debt is {_usd(p['division_median'])}.")
        items.append(f"<li><b>Rank.</b> {' '.join(rank_bits)}{med}</li>")
    path, roll = _history_bits(p)
    local = ""
    if not p["dc"] and p["local_debt"] is not None and p["total"]:
        share = p["local_debt"] / p["total"] * 100
        local = (f"<p>Local governments in {p['name']} owed {_usd(p['local_debt'])} as of {_date(p['local_as_of'])}, "
                 f"{share:.1f}% of the combined {_usd(p['total'])}. The clock adds the state and local Census totals. "
                 f"It does not include unfunded pensions or a share of the federal debt.</p>")
    elif p["dc"]:
        local = ("<p>Census tables have no state-government level for the District of Columbia, so this page does not "
                 "quote a state-government figure. The clock is the District government total Census classifies as local. "
                 "It does not include a share of the federal debt.</p>")
    pairs = faqs(p)
    faq_html = "".join(f"<h3>{E(q)}</h3><p>{E(a)}</p>" for q, a in pairs)
    ld = {"@context": "https://schema.org", "@type": "FAQPage", "dateModified": p["total_as_of"],
          "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in pairs]}
    based = [p["source_url"], CENSUS_RELEASE]
    if p["pop_source_url"]:
        based.append(p["pop_source_url"])
    if p["gdp_url"] and (p["ratio_state"] is not None or p["ratio_total"] is not None):
        based.append(p["gdp_url"])
    dataset = {"@context": "https://schema.org", "@type": "Dataset",
               "name": f"{p['name']} government debt, U.S. Census Bureau",
               "description": _answer(p), "url": f"https://everydebtclock.com/states/{p['slug']}/",
               "dateModified": p["total_as_of"], "isAccessibleForFree": True,
               "creator": [{"@type": "Organization", "name": "U.S. Census Bureau", "url": "https://www.census.gov/"},
                           {"@type": "Organization", "name": "Every Debt Clock", "url": "https://everydebtclock.com/"}],
               "publisher": {"@type": "Organization", "name": "Every Debt Clock", "url": "https://everydebtclock.com/"},
               "spatialCoverage": {"@type": "Place", "name": p["name"]},
               "isBasedOn": based,
               "creditText": CITE}
    scripts = ("<script type=\"application/ld+json\">" + json.dumps(ld).replace("</", "<\\/") + "</script>"
               + "<script type=\"application/ld+json\">" + json.dumps(dataset).replace("</", "<\\/") + "</script>")
    html_s = (
        f'<section id="facts"><div class="sh"><span class="bar" style="background:var(--amber)"></span>'
        f'<h2>Official figures</h2><span class="h2n">U.S. Census Bureau · {_date(p["total_as_of"])}</span></div>'
        f'<p class="answer">{E(_answer(p))}</p>'
        f'<p>Suggested citation: {E(CITE)} '
        f'<a href="{E(p["source_url"])}" rel="noopener">{E(p["source_name"])}</a>.</p>'
        f'<ul class="facts">{"".join(items)}</ul>'
        f'{local}<p>{E(path)}</p>'
        f'{"".join(f"<p>{E(text)}</p>" for text in series_paragraphs(p))}'
        f'{_chart(p)}<p>{E(roll)}</p>'
        f'<p>{E(_clock_sentence(p))}</p>'
        f'</section>'
        f'<section class="faq" id="faq"><div class="sh"><h2>Questions</h2></div>{faq_html}</section>'
    )
    return html_s, scripts


def index_parts(R):
    """Intro sentence, FAQ HTML, and JSON-LD for /states/."""
    profs = all_profiles(R)
    states = [p for p in profs if not p["dc"]]
    top = max(states, key=lambda p: p["state_debt"])
    top_pp = max(profs, key=lambda p: p["per_total"])
    as_of = _date(top["total_as_of"])
    blurb = (f'<p>Each state page leads with a debt clock. Under it, the page quotes state government debt from the '
             f'<a href="{CENSUS_RELEASE}" rel="noopener">U.S. Census Bureau Annual Survey of State and Local Government Finances</a>, '
             f'debt per resident using the Census population estimate, and that debt as a share of '
             f'<a href="https://www.bea.gov/data/gdp/gdp-state" rel="noopener">BEA current-dollar GDP</a> '
             f'when both years exist. The District of Columbia has no state-government total in the Census tables, so its page quotes the District government total instead. '
             f'The same Census totals are in <a href="../data/us-state-debt.csv">us-state-debt.csv</a>.</p>')
    q1 = (f"{_poss(top['name'])} state government debt was {_usd(top['state_debt'])} as of {as_of}, "
          f"per the U.S. Census Bureau, the largest of the 50 states.")
    q2 = (f"{_poss(top_pp['name'])} {'government' if top_pp['dc'] else 'state and local'} debt was {_usd2(top_pp['per_total'])} per resident: "
          f"{_usd(top_pp['total'])} as of {_date(top_pp['total_as_of'])}, divided by the Census estimate of {top_pp['pop']:,} residents on {_date(top_pp['pop_as_of'])}.")
    q3 = ("The clocks use Census state and local debt outstanding. They do not include unfunded pensions or a share of the federal debt. "
          "A page ticks the latest one-year Census change forward only when that change is large enough to measure and no more than 5 percent of the prior level. Otherwise it shows the Census figure and does not tick.")
    pairs = [
        ("Which state has the most state government debt?", q1),
        ("Which state has the highest debt per resident?", q2),
        ("What do the state debt clocks leave out?", q3),
    ]
    faq_html = '<section class="faq" id="faq"><h2>Questions</h2>' + "".join(f"<h3>{E(q)}</h3><p>{E(a)}</p>" for q, a in pairs) + "</section>"
    ld = {
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "US state government debt",
        "description": q1,
        "url": "https://everydebtclock.com/states/",
        "dateModified": top["total_as_of"],
        "isAccessibleForFree": True,
        "creator": {"@type": "Organization", "name": "Every Debt Clock", "url": "https://everydebtclock.com/"},
        "isBasedOn": [CENSUS_RELEASE, "https://www.bea.gov/data/gdp/gdp-state",
                      "https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/state/totals/NST-EST2025-ALLDATA.csv"],
        "creditText": CITE,
        "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv",
                          "contentUrl": "https://everydebtclock.com/data/us-state-debt.csv"}],
    }
    faq_ld = {"@context": "https://schema.org", "@type": "FAQPage", "dateModified": top["total_as_of"],
              "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in pairs]}
    scripts = ("<script type=\"application/ld+json\">" + json.dumps(ld).replace("</", "<\\/") + "</script>"
               + "<script type=\"application/ld+json\">" + json.dumps(faq_ld).replace("</", "<\\/") + "</script>")
    return blurb, faq_html, scripts


def assert_state_pages_differ(root, limit=0.80):
    """Fail if two state articles share more than `limit` of their words. Same test as the country pages."""
    import country_profile
    base = os.path.join(root, "states")
    pages = []
    for slug in sorted(os.listdir(base)):
        path = os.path.join(base, slug, "index.html")
        place = os.path.join(root, "places", slug + ".json")
        if not os.path.isfile(path) or not os.path.isfile(place):
            continue
        pages.append((slug, country_profile._tokens(country_profile.visible_body(open(path, encoding="utf-8").read()))))
    if len(pages) < 51:
        raise SystemExit(f"state pages: expected 51 articles, found {len(pages)}")
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
                raise SystemExit(f"state pages {ai} and {bj} share {ratio:.1%} of their body text (limit {limit:.0%})")
    print(f"state pages distinct: {len(pages)} pages, closest {worst[1]} / {worst[2]} at {worst[0]:.1%}", flush=True)
    return worst
