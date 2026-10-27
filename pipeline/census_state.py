#!/usr/bin/env python3
"""Write places/<slug>.json for a US state from the Census Bureau's Annual Survey of State and Local Government Finances
(table GS00LOCALFIN, Debt - Total Debt Outstanding, item LF0231) and Census Vintage 2025 state population.
Usage: python3 pipeline/census_state.py illinois pennsylvania ...   (slugs in STATES below; needs network, no key)
Same definitions and wording as the California/Florida/New York/Texas pages, but without a state-report secondary line.
Headline = Census state + local debt outstanding; state + local is asserted equal to Census's State + Local rows."""
import csv, io, json, os, sys, urllib.request
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
TABLE = "https://data.census.gov/table/GOVSLOCALFINTIMESERIES.GS00LOCALFIN?q=GS00LOCALFIN&g=040XX00US{fips}"
API = "https://data.census.gov/api/access/data/table?id=GOVSLOCALFINTIMESERIES.GS00LOCALFIN&g=040XX00US{fips}"
POP_URL = "https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/state/totals/NST-EST2025-ALLDATA.csv"
REL = "https://www.census.gov/data/datasets/2024/econ/local/public-use-datasets.html"
METH = "https://www2.census.gov/programs-surveys/gov-finances/tables/2024/2024_methodology.pdf"
UA = {"User-Agent": "Mozilla/5.0"}
# slug: (name, demonym, USPS, FIPS, state fiscal-year-end note)
STATES = {
    "illinois": ("Illinois", "Illinoisan", "IL", "17", "Illinois's state fiscal year ends June 30."),
    "pennsylvania": ("Pennsylvania", "Pennsylvanian", "PA", "42", "Pennsylvania's state fiscal year ends June 30."),
    "ohio": ("Ohio", "Ohioan", "OH", "39", "Ohio's state fiscal year ends June 30."),
    "georgia": ("Georgia", "Georgian", "GA", "13", "Georgia's state fiscal year ends June 30."),
    "north-carolina": ("North Carolina", "North Carolinian", "NC", "37", "North Carolina's state fiscal year ends June 30."),
    "michigan": ("Michigan", "Michigander", "MI", "26", "Michigan's state fiscal year ends September 30, so Census's survey year 2024 holds the state government's fiscal year that ended September 30, 2023."),
}
def get(url): return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90).read()
def ye(y): return f"{y}-06-30"
def main(slugs):
    pops = {r["NAME"]: r for r in csv.DictReader(io.StringIO(get(POP_URL).decode("utf-8-sig")))}
    for slug in slugs:
        name, dem, usps, fips, fy = STATES[slug]
        d = json.loads(get(API.format(fips=fips)))["response"]["data"]; h = d[0]; ix = {k: h.index(k) for k in h}
        out, items = {}, {}
        for r in d[1:]:
            assert r[ix["NAME"]] == name, (slug, r[ix["NAME"]])
            g = r[ix["GOVTYPE_LABEL"]]
            if r[ix["AGG_DESC"]] == "LF0231" and g in ("State", "Local", "State and Local"):
                out.setdefault(g, {})[int(r[ix["YEAR"]])] = (int(r[ix["AMOUNT"]]) * 1000, r[ix["AMOUNT_CV"]])
            if r[ix["AGG_DESC"]] in ("LF0232", "LF0233") and g in ("State", "Local"):
                items[(g, r[ix["AGG_DESC"]], int(r[ix["YEAR"]]))] = int(r[ix["AMOUNT"]]) * 1000
        ys = sorted(out["State and Local"]); last, prev = ys[-1], ys[-2]
        for y in ys: assert out["State"][y][0] + out["Local"][y][0] == out["State and Local"][y][0], (slug, y)
        for g in ("State", "Local"):
            assert items[(g, "LF0232", last)] + items[(g, "LF0233", last)] == out[g][last][0], (slug, g, "LT+ST != total")
        pr = pops[name]
        src = (f"US Census Bureau, Annual Survey of State and Local Government Finances, table GS00LOCALFIN (State and Local Government Finances by Level of Government: "
               f"U.S. and States: 2017-{last}), Debt - Total Debt Outstanding (LF0231)")
        comps = []
        for key, lab, short, gt, inc in [
            ("state", "State government debt", "State debt", "State", f"All debt of the {name} state government as Census defines it: long-term and short-term debt of the state and its dependent agencies, whatever the source of repayment. Census uses the same definition for every state."),
            ("local", "Local government debt", "Local debt", "Local", f"All debt of {name}'s counties, cities, towns, school districts and special districts, on the same Census definition. Census estimates local totals from a sample of local governments in most years (2022 was a full count, the Census of Governments); coefficient of variation for {last}: {out['Local'][last][1]}%.")]:
            comps.append({"key": key, "label": lab, "short": short, "value": out[gt][last][0], "as_of": ye(last), "prior_value": out[gt][prev][0], "prior_as_of": ye(prev),
                          "source_name": src, "source_url": TABLE.format(fips=fips),
                          "source_locator": f"{name}, Government type '{gt}', items LF0231 Total, LF0233 Long-term and LF0232 Short-term Debt Outstanding, survey year {last}; amounts published in $1,000",
                          "includes": inc, "history": [[ye(y), out[gt][y][0]] for y in ys],
                          "breakdown": [{"label": "Long-term debt outstanding (Census item LF0233)", "value": items[(gt, "LF0233", last)], "tile_label": "Long-term debt"},
                                        {"label": "Short-term debt outstanding (Census item LF0232)", "value": items[(gt, "LF0232", last)], "tile_label": "Short-term debt"}]})
        sl = out["State and Local"]; ch = sl[last][0] - sl[prev][0]; se = sl[last][0] * float(sl[last][1]) / 100
        notes = [f"Census publishes {name}'s state + local total as ${sl[last][0]/1e9:,.2f} billion for {last} (coefficient of variation {sl[last][1]}%) and ${sl[prev][0]/1e9:,.2f} billion for {prev}. State + local here is exactly Census's state figure plus its local figure.",
                 f"Census's figures are the newest official state + local totals that use one definition for all 50 states, but they lag about two years, so the live clock projects from June 30, {last}. {name}'s own audited report is fresher but is not used here: it covers a narrower scope and would not be comparable with the other states."]
        if abs(ch) < 2 * se:
            notes.append(f"The {prev}→{last} change (${ch/1e9:+,.2f} billion) is smaller than about two standard errors of the Census local estimate (about ${2*se/1e9:,.1f} billion at a {sl[last][1]}% coefficient of variation), so the direction of the projected trend is uncertain.")
        notes.append("Not included: unfunded pension and retiree-health liabilities, and the state's share of the federal debt.")
        p = {"_doc": "One file per place. build.py renders /states/<slug>/ (kind=state) from this file. Every number must be an official published figure with its source. Amounts in US dollars. Headline is Census state + local debt (same source and definition for every state). Generated by pipeline/census_state.py.",
             "slug": slug, "kind": "state", "country": "US", "region_code": usps, "name": name, "demonym": dem, "status": "live",
             "publisher": "US Census Bureau", "reporter": "The Census Bureau", "reporter_its": f"{name}'s state + local",
             "title": f"{name} Debt Clock: Live State and Local Debt, From Official Data",
             "cadence": f"Annual. The Census Bureau's Annual Survey of State and Local Government Finances comes out about two years after the fiscal year (survey year {last}: July 2026; survey year {prev}: July 2025).",
             "next_update": f"The next Census figures, for survey year {last+1}, are expected around mid-{last+3}, based on the last two release dates.",
             "fiscal_year_end_note": f"{fy} Census survey year {last} covers each government's fiscal year that ended between July 1, {last-1} and June 30, {last}; the clock dates it June 30, {last}, the end of that window.",
             "population": {"value": int(pr["POPESTIMATE2025"]), "prior_value": int(pr["POPESTIMATE2024"]), "as_of": "2025-07-01", "prior_as_of": "2024-07-01",
                            "source_name": "Census Bureau, Vintage 2025 state population estimates (NST-EST2025)", "source_url": POP_URL},
             "components": comps,
             "extra_sources": [{"name": f"US Census Bureau, {last} State & Local Government Finance Datasets and Tables (release page)", "url": REL},
                               {"name": f"US Census Bureau, {last} Annual Survey of Local Government Finances methodology", "url": METH},
                               {"name": f"Census data API download used for these figures ({name})", "url": API.format(fips=fips)}],
             "notes": notes,
             "legend": f"{name} state + local debt is reported once a year by the Census Bureau, about two years after the fact. Real borrowing happens in lumps when bonds are sold and is repaid on schedules, so the live number is a straight-line projection from the latest Census year, shown here next to the official totals."}
        with open(os.path.join(ROOT, "places", f"{slug}.json"), "w") as f: json.dump(p, f, indent=1, ensure_ascii=False); f.write("\n")
        print(slug, last, sl[last][0], prev, sl[prev][0], "pop", p["population"]["value"], "per resident", round(sl[last][0] / p["population"]["value"], 2))
if __name__ == "__main__": main(sys.argv[1:] or list(STATES))
