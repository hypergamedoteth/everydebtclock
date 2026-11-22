#!/usr/bin/env python3
"""Refresh data/state_federal.json from official files.

Not part of the daily Treasury refresh. Run by hand when a new SSA table,
FedScope summary, DMDC location report, or USAspending fiscal year is published.

SSA's site blocks this environment (HTTP 403), so the beneficiary rows below
are Table 2 of OASDI Beneficiaries by State and County, 2025, copied from
https://www.ssa.gov/policy/docs/statcomps/oasdi_sc/2025/table02.html
Each row is checked: the eight benefit-type columns must add to the total,
and every area in the table must add to the published "All areas" total.
"""
import csv
import datetime as dt
import io
import json
import os
import sys
import urllib.request
import zipfile
from zoneinfo import ZoneInfo

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(R, "pipeline"))
import xlsx_min  # noqa: E402

UA = "everydebtclock-research (state pages; official figures only)"
CT = ZoneInfo("America/Chicago")
OUT = os.path.join(R, "data", "state_federal.json")

# name, total, and the eight Table 2 columns that must sum to total.
# Order: retired workers, spouses, children; widow(er)s and parents, children;
# disabled workers, spouses, children.
SSA_ROWS = """
Alabama,1207893,844517,24819,13086,71450,46076,179658,2084,26203
Alaska,123083,95859,3165,2072,5870,4989,9566,129,1433
Arizona,1576812,1255039,40560,16400,77709,42336,126749,1634,16385
Arkansas,736994,513912,12382,7697,41400,26866,116254,1277,17206
California,6813640,5341103,298390,86216,371353,163397,487142,8178,57861
Colorado,1035297,831752,32376,8245,51038,25978,76220,742,8946
Connecticut,765437,606612,18390,8074,34750,18405,69825,596,8785
Delaware,257024,206680,4052,1855,11113,6653,23762,179,2730
District of Columbia,88265,66920,1688,868,3843,3374,10514,30,1028
Florida,5294001,4191491,139400,52501,260003,122233,462756,5863,59754
Georgia,2081735,1559957,43943,22111,110316,74380,234325,2527,34176
Hawaii,310761,258046,7678,3795,13744,6314,18082,273,2829
Idaho,421169,330415,10422,4442,19478,11171,38890,488,5863
Illinois,2454005,1886306,74758,24897,137812,71287,227744,2517,28684
Indiana,1473765,1102704,28047,13935,78841,50758,174475,1817,23188
Iowa,717616,565146,11333,6957,34105,19826,70847,534,8868
Kansas,612962,476959,11307,6451,30170,19392,59707,531,8445
Kentucky,1059779,719046,30486,10586,70752,40712,163589,2903,21705
Louisiana,992482,661928,46087,10510,81561,43428,127416,2506,19046
Maine,388279,294438,9640,3758,18506,9920,45046,461,6510
Maryland,1133360,892917,25591,11028,53588,33995,102841,647,12753
Massachusetts,1409032,1076890,43542,15909,64737,35001,151027,1247,20679
Michigan,2381255,1786475,52935,24249,122832,71665,280455,3616,39028
Minnesota,1187480,954855,19222,11799,47304,29288,109011,676,15325
Mississippi,710023,493663,12724,9050,42060,32560,103115,1370,15481
Missouri,1415977,1049942,27409,13191,74393,48767,177564,1887,22824
Montana,270750,217470,5443,2654,12824,7161,22250,252,2696
Nebraska,388626,306643,6209,3861,17926,11587,36838,244,5318
Nevada,629413,497960,16759,5890,31045,15788,54871,638,6462
New Hampshire,353828,277320,5938,3016,13906,7737,39030,272,6609
New Jersey,1780433,1406793,45287,20310,84413,44205,156810,1797,20818
New Mexico,486067,366403,13079,4369,25384,17362,52376,638,6456
New York,3924458,3000986,117930,48804,186832,97205,411652,5096,55953
North Carolina,2385531,1827895,38612,21432,110681,72873,275659,2671,35708
North Dakota,153839,121375,2790,1341,7886,5007,13431,74,1935
Ohio,2611577,1900292,94674,22064,169406,85711,299284,3791,36355
Oklahoma,868591,626946,18253,8783,52128,32601,112710,1397,15773
Oregon,963726,768868,21465,9212,44610,21481,87378,875,9837
Pennsylvania,3035656,2319503,65412,27534,155824,83281,337653,3445,43004
Rhode Island,248674,190326,4385,2922,10053,5789,30621,222,4356
South Carolina,1333647,1021012,22594,11623,65730,41699,149711,1567,19711
South Dakota,206052,166111,3225,1783,9178,6248,17132,119,2256
Tennessee,1592535,1169095,31907,14905,88378,58159,201124,2214,26753
Texas,4996895,3710457,207044,53826,327139,164872,457400,7202,68955
Utah,487611,373883,18174,5899,24270,17489,40948,468,6480
Vermont,168263,131909,2640,1800,6811,3984,18241,120,2758
Virginia,1735496,1339580,39816,16629,87126,48009,178996,1868,23472
Washington,1526417,1216514,39773,15361,69367,35592,132137,1369,16304
West Virginia,482115,325414,16858,5826,36206,17808,69526,1498,8979
Wisconsin,1398745,1114607,20653,12931,59032,36050,136029,1024,18419
Wyoming,132693,105473,2692,1109,6454,3683,11725,109,1448
American Samoa,6527,3103,224,239,636,642,1312,34,337
Guam,22535,15630,1541,511,1977,1095,1406,63,312
Northern Mariana Islands,4775,3222,228,203,371,328,325,5,93
Puerto Rico,851795,537482,67957,8869,73053,21952,124379,5320,12783
U.S. Virgin Islands,22695,18419,775,381,1154,621,1137,28,180
Foreign countries,733078,480167,119053,11152,101822,11247,7177,316,2144
Unknown,321,234,10,1,32,8,32,0,4
"""
SSA_ALL_AREAS = 70451490

OPM_ZIP = "https://www.opm.gov/data/datasets/Files/753/bc88ce69-1bbe-406f-9441-3c5153014616.zip"
DMDC_FILE = "DMDC_Website_Location_Report_2609.xlsx"
DMDC_URL = "https://dwp.dmdc.osd.mil/dwp/api/download?fileName=" + DMDC_FILE + "&groupName=milRegionCountry"
USA_API = "https://api.usaspending.gov/api/v2/search/spending_by_geography/"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def slug(name):
    return name.lower().replace(" ", "-")


def ssa_states():
    out = {}
    total = 0
    for line in SSA_ROWS.strip().splitlines():
        parts = line.split(",")
        name, nums = parts[0], [int(x) for x in parts[1:]]
        n, cols = nums[0], nums[1:]
        if sum(cols) != n:
            raise SystemExit(f"SSA row does not add up: {name} {n} vs {sum(cols)}")
        total += n
        if name in ("American Samoa", "Guam", "Northern Mariana Islands", "Puerto Rico",
                    "U.S. Virgin Islands", "Foreign countries", "Unknown"):
            continue
        out[slug(name)] = n
    if total != SSA_ALL_AREAS:
        raise SystemExit(f"SSA areas sum to {total}, table says {SSA_ALL_AREAS}")
    if len(out) != 51:
        raise SystemExit(f"SSA states+DC: {len(out)}")
    return out, total


def opm_states():
    z = zipfile.ZipFile(io.BytesIO(get(OPM_ZIP)))
    name = "Status Employment by Duty Location_202503_and_202409.txt"
    raw = z.read(name).decode("utf-8", "replace")
    out = {}
    redacted = None
    for row in csv.DictReader(io.StringIO(raw), delimiter="\t"):
        if row["DATECODE"] != "202503":
            continue
        if row["STATE"] == "REDACTED":
            redacted = int(row["EMPCOUNT"])
            continue
        out[slug(row["STATET"])] = int(row["EMPCOUNT"])
    if len(out) != 51 or redacted is None:
        raise SystemExit(f"OPM states {len(out)} redacted {redacted}")
    return out, redacted


def dmdc_states():
    wb = xlsx_min.read_bytes(get(DMDC_URL))
    rows = wb["LOCATION COUNTRY REPORT"]
    # Column I is the active-duty total (Army through Coast Guard). Header is row 6.
    out = {}
    us_total = None
    for rn, row in rows:
        b = (row.get("B") or "").strip()
        if b == "" and (row.get("A") or "").strip() == "UNITED STATES TOTAL":
            us_total = int(row.get("I") or 0)
        if not b or b in ("DUTY STATE / COUNTRY",):
            continue
        key = slug(b)
        if key == "district-of-columbia" or key in (
            "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut",
            "delaware", "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa",
            "kansas", "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan",
            "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada",
            "new-hampshire", "new-jersey", "new-mexico", "new-york", "north-carolina",
            "north-dakota", "ohio", "oklahoma", "oregon", "pennsylvania", "rhode-island",
            "south-carolina", "south-dakota", "tennessee", "texas", "utah", "vermont",
            "virginia", "washington", "west-virginia", "wisconsin", "wyoming"):
            out[key] = int(float(row["I"]))
        if (row.get("A") or "").strip() == "UNITED STATES TOTAL":
            us_total = int(float(row["I"]))
    if len(out) != 51 or not us_total:
        raise SystemExit(f"DMDC states {len(out)} us_total {us_total} sample {list(out)[:5]}")
    return out, us_total


def usa_states():
    body = {
        "scope": "place_of_performance",
        "geo_layer": "state",
        "spending_level": "transactions",
        "filters": {"time_period": [{"start_date": "2025-10-01", "end_date": "2026-09-30"}]},
    }
    req = urllib.request.Request(USA_API, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.load(r)
    if data.get("spending_level") != "transactions":
        raise SystemExit("USAspending spending_level changed: " + str(data.get("spending_level")))
    by_code = {}
    for row in data["results"]:
        code = row.get("shape_code")
        if not code:
            continue
        by_code[code] = int(round(float(row["aggregated_amount"]) * 100))  # cents
    places = []
    for fn in os.listdir(os.path.join(R, "places")):
        p = json.load(open(os.path.join(R, "places", fn)))
        if p.get("kind") == "state" and p.get("status") == "live":
            places.append(p)
    out = {}
    for p in places:
        code = p["region_code"]
        if code not in by_code:
            raise SystemExit(f"USAspending has no row for {code}")
        out[p["slug"]] = by_code[code]
    if len(out) != 51:
        raise SystemExit(f"USAspending states {len(out)}")
    return out


def main():
    ssa, ssa_sum = ssa_states()
    print("SSA ok", len(ssa), "all areas", ssa_sum)
    opm, redacted = opm_states()
    print("OPM ok", len(opm), "redacted", redacted, "states sum", sum(opm.values()))
    dmdc, us_total = dmdc_states()
    print("DMDC ok", len(dmdc), "US total", us_total, "states+DC", sum(dmdc.values()))
    usa = usa_states()
    print("USAspending ok", len(usa), "states+DC cents", sum(usa.values()))
    doc = {
        "_doc": "Fixed official figures for the state-page federal section. The live federal-debt share and the interest share are computed at build time from data/data.json and data/us-interest.csv so they stay on the same Treasury figures as the rest of the site. Amounts from USAspending are integer cents.",
        "ssa": {
            "as_of": "2025-12-01",
            "label": "December 2025",
            "measure": "OASDI beneficiaries in current-payment status. Benefits withheld are excluded. State is the beneficiary ZIP code, or the representative payee's ZIP code when there is one.",
            "source_name": "Social Security Administration, OASDI Beneficiaries by State and County, 2025, Table 2",
            "source_url": "https://www.ssa.gov/policy/docs/statcomps/oasdi_sc/2025/table02.html",
            "all_areas": SSA_ALL_AREAS,
            "states": ssa,
        },
        "opm": {
            "as_of": "2025-03-31",
            "label": "March 2025",
            "preliminary": True,
            "redacted": redacted,
            "measure": "Federal civilian employees in active pay status, by duty station. Executive branch. Excludes the Postal Service and intelligence agencies. Headcount, not full-time equivalents. OPM counts some Maryland, Virginia, and West Virginia duty stations in the District of Columbia. The March 2025 snapshot is marked preliminary.",
            "source_name": "U.S. Office of Personnel Management, FedScope Employment Summary Data (March 2025), Status Employment by Duty Location",
            "source_url": "https://www.opm.gov/data/datasets/",
            "file_url": OPM_ZIP,
            "states": opm,
        },
        "dmdc": {
            "as_of": "2026-09-30",
            "label": "September 30, 2026",
            "prepared": "2026-11-17",
            "us_total_active_duty": us_total,
            "measure": "Active duty assigned to a unit in the state: Army, Navy, Marine Corps, Air Force, Space Force, and Coast Guard. Not the National Guard, the reserves, or civilians. Not everyone on temporary duty or deployed. The file's United States total also includes territories and armed-forces mail locations, so the 50 states and DC add to less than that total.",
            "source_name": "Defense Manpower Data Center, Military and Civilian Personnel by Assigned Duty Location, September 30, 2026",
            "source_url": "https://dwp.dmdc.osd.mil/dwp/app/dod-data-reports/workforce-reports/",
            "file_url": DMDC_URL,
            "states": dmdc,
        },
        "usaspending": {
            "fiscal_year": 2026,
            "start": "2025-10-01",
            "end": "2026-09-30",
            "pulled": dt.datetime.now(CT).date().isoformat(),
            "scope": "place_of_performance",
            "spending_level": "transactions",
            "measure": "Prime-award transaction amounts with a place of performance in the state during the fiscal year. Not most federal salaries. Not a full accounting of benefits paid to residents. Agencies can still file late records after the pull date.",
            "source_name": "USAspending.gov",
            "source_url": "https://www.usaspending.gov/state/{slug}/2026",
            "api": USA_API,
            "states_cents": usa,
        },
    }
    json.dump(doc, open(OUT, "w"), indent=1)
    open(OUT, "a").write("\n")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
