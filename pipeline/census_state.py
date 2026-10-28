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
    'alabama': ('Alabama', 'Alabamian', 'AL', '01', "Alabama's state fiscal year ends September 30, so Census's survey year 2024 holds the state government's fiscal year that ended September 30, 2023."),
    'alaska': ('Alaska', 'Alaskan', 'AK', '02', "Alaska's state fiscal year ends June 30."),
    'arizona': ('Arizona', 'Arizonan', 'AZ', '04', "Arizona's state fiscal year ends June 30."),
    'arkansas': ('Arkansas', 'Arkansan', 'AR', '05', "Arkansas's state fiscal year ends June 30."),
    'colorado': ('Colorado', 'Coloradan', 'CO', '08', "Colorado's state fiscal year ends June 30."),
    'connecticut': ('Connecticut', 'resident', 'CT', '09', "Connecticut's state fiscal year ends June 30."),
    'delaware': ('Delaware', 'Delawarean', 'DE', '10', "Delaware's state fiscal year ends June 30."),
    'hawaii': ('Hawaii', 'resident', 'HI', '15', "Hawaii's state fiscal year ends June 30."),
    'idaho': ('Idaho', 'Idahoan', 'ID', '16', "Idaho's state fiscal year ends June 30."),
    'indiana': ('Indiana', 'Hoosier', 'IN', '18', "Indiana's state fiscal year ends June 30."),
    'iowa': ('Iowa', 'Iowan', 'IA', '19', "Iowa's state fiscal year ends June 30."),
    'kansas': ('Kansas', 'Kansan', 'KS', '20', "Kansas's state fiscal year ends June 30."),
    'kentucky': ('Kentucky', 'Kentuckian', 'KY', '21', "Kentucky's state fiscal year ends June 30."),
    'louisiana': ('Louisiana', 'Louisianan', 'LA', '22', "Louisiana's state fiscal year ends June 30."),
    'maine': ('Maine', 'Mainer', 'ME', '23', "Maine's state fiscal year ends June 30."),
    'maryland': ('Maryland', 'Marylander', 'MD', '24', "Maryland's state fiscal year ends June 30."),
    'massachusetts': ('Massachusetts', 'resident', 'MA', '25', "Massachusetts's state fiscal year ends June 30."),
    'minnesota': ('Minnesota', 'Minnesotan', 'MN', '27', "Minnesota's state fiscal year ends June 30."),
    'mississippi': ('Mississippi', 'Mississippian', 'MS', '28', "Mississippi's state fiscal year ends June 30."),
    'missouri': ('Missouri', 'Missourian', 'MO', '29', "Missouri's state fiscal year ends June 30."),
    'montana': ('Montana', 'Montanan', 'MT', '30', "Montana's state fiscal year ends June 30."),
    'nebraska': ('Nebraska', 'Nebraskan', 'NE', '31', "Nebraska's state fiscal year ends June 30."),
    'nevada': ('Nevada', 'Nevadan', 'NV', '32', "Nevada's state fiscal year ends June 30."),
    'new-hampshire': ('New Hampshire', 'New Hampshirite', 'NH', '33', "New Hampshire's state fiscal year ends June 30."),
    'new-jersey': ('New Jersey', 'New Jerseyan', 'NJ', '34', "New Jersey's state fiscal year ends June 30."),
    'new-mexico': ('New Mexico', 'New Mexican', 'NM', '35', "New Mexico's state fiscal year ends June 30."),
    'north-dakota': ('North Dakota', 'North Dakotan', 'ND', '38', "North Dakota's state fiscal year ends June 30."),
    'oklahoma': ('Oklahoma', 'Oklahoman', 'OK', '40', "Oklahoma's state fiscal year ends June 30."),
    'oregon': ('Oregon', 'Oregonian', 'OR', '41', "Oregon's state fiscal year ends June 30."),
    'rhode-island': ('Rhode Island', 'Rhode Islander', 'RI', '44', "Rhode Island's state fiscal year ends June 30."),
    'south-carolina': ('South Carolina', 'South Carolinian', 'SC', '45', "South Carolina's state fiscal year ends June 30."),
    'south-dakota': ('South Dakota', 'South Dakotan', 'SD', '46', "South Dakota's state fiscal year ends June 30."),
    'tennessee': ('Tennessee', 'Tennessean', 'TN', '47', "Tennessee's state fiscal year ends June 30."),
    'utah': ('Utah', 'Utahn', 'UT', '49', "Utah's state fiscal year ends June 30."),
    'vermont': ('Vermont', 'Vermonter', 'VT', '50', "Vermont's state fiscal year ends June 30."),
    'virginia': ('Virginia', 'Virginian', 'VA', '51', "Virginia's state fiscal year ends June 30."),
    'washington': ('Washington', 'resident', 'WA', '53', "Washington's state fiscal year ends June 30."),
    'west-virginia': ('West Virginia', 'West Virginian', 'WV', '54', "West Virginia's state fiscal year ends June 30."),
    'wisconsin': ('Wisconsin', 'Wisconsinite', 'WI', '55', "Wisconsin's state fiscal year ends June 30."),
    'wyoming': ('Wyoming', 'Wyomingite', 'WY', '56', "Wyoming's state fiscal year ends June 30."),
}
def get(url): return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90).read()
def ye(y): return f"{y}-06-30"
def main(slugs):
    slugs = slugs or [k for k in STATES if not os.path.exists(os.path.join(ROOT, "places", k + ".json"))]  # default: only states without a file yet
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
            # Census publishes in $1,000, so parts can differ from the total by rounding. If Census omits the short-term row (no short-term debt reported), the long-term row must equal the total and the short-term tile is left out rather than assumed.
            assert abs(items.get((g, "LF0232", last), 0) + items[(g, "LF0233", last)] - out[g][last][0]) <= 5000, (slug, g, "LT+ST != total")
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
                          "breakdown": [{"label": "Long-term debt outstanding (Census item LF0233)", "value": items[(gt, "LF0233", last)], "tile_label": "Long-term debt"}]
                                        + ([{"label": "Short-term debt outstanding (Census item LF0232)", "value": items[(gt, "LF0232", last)], "tile_label": "Short-term debt"}] if (gt, "LF0232", last) in items else [])})
        sl = out["State and Local"]; ch = sl[last][0] - sl[prev][0]; se = sl[last][0] * float(sl[last][1]) / 100
        big = abs(ch) > 0.10 * sl[prev][0]  # a one-year move over 10% is more likely a sampling or reclassification event than a trend that should be extended for two more years
        hold = abs(ch) < 2 * se or big  # change is within Census's own sampling error: a straight-line projection would be noise, so the page shows the official figure fixed
        notes = [f"Census publishes {name}'s state + local total as ${sl[last][0]/1e9:,.2f} billion for {last} (coefficient of variation {sl[last][1]}%) and ${sl[prev][0]/1e9:,.2f} billion for {prev}. State + local here is exactly Census's state figure plus its local figure.",
                 f"Census's figures are the newest official state + local totals that use one definition for all 50 states, but they lag about two years, so the {"page shows the official figure as of" if hold else "live clock projects from"} June 30, {last}. {name}'s own audited report is fresher but is not used here: it covers a narrower scope and would not be comparable with the other states."]
        if hold:
            notes.append(f"The {prev}→{last} change (${ch/1e9:+,.2f} billion) is smaller than about two standard errors of the Census estimate (about ${2*se/1e9:,.1f} billion at a {sl[last][1]}% coefficient of variation), so Census's data does not show which way the debt is moving. This page therefore shows the official figure as published and does not tick it forward.")
        if big and not abs(ch) < 2 * se:
            notes.append(f"The {prev}→{last} change (${ch/1e9:+,.2f} billion, {ch / sl[prev][0]:+.0%}) is larger than 10% of the {prev} level in one year. A move that size is more likely a one-off (a large bond issue or payoff, a reclassification, or Census sampling) than a trend, so this page shows the official figure as published and does not extend it forward.")
        if float(out["Local"][last][1]) > 10:
            notes.append(f"Caution: Census's own sampling error on {name}'s local debt for {last} is large (coefficient of variation {out['Local'][last][1]}%), so the local figure, and therefore the total, can be far from the true amount. The figures are shown exactly as Census published them.")
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
             "hold_trend": hold, "legend": f"{name} state + local debt is reported once a year by the Census Bureau, about two years after the fact. Real borrowing happens in lumps when bonds are sold and is repaid on schedules, so " + ("the page shows the latest official figure without ticking it forward, because Census's own sampling error is larger than the change it measured." if hold else "the live number is a straight-line projection from the latest Census year, shown here next to the official totals.")}
        with open(os.path.join(ROOT, "places", f"{slug}.json"), "w") as f: json.dump(p, f, indent=1, ensure_ascii=False); f.write("\n")
        print(slug, last, sl[last][0], prev, sl[prev][0], "pop", p["population"]["value"], "per resident", round(sl[last][0] / p["population"]["value"], 2))
if __name__ == "__main__": main(sys.argv[1:])
