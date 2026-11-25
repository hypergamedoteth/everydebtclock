#!/usr/bin/env python3
"""BEA current-dollar GDP by state, for the state debt-to-GDP lines.

Table SAGDP2, line 1 (all-industry total), from the BEA regional zip. Figures
are millions of current dollars, not adjusted for inflation. A state BEA does
not publish is left out of the file rather than filled in.

    python3 pipeline/fetch_state_gdp.py
"""
import csv
import io
import json
import os
import sys
import time
import zipfile
import urllib.request
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "state_gdp.json")
ZIP_URL = "https://apps.bea.gov/regional/zip/SAGDP.zip"
PAGE_URL = "https://www.bea.gov/data/gdp/gdp-state"
UA = {"User-Agent": "EveryDebtClock/1.0 (state-gdp; +https://everydebtclock.com/)", "Accept": "*/*"}

# State FIPS (the first two digits of BEA's 5-digit GeoFIPS) to the page slug.
FIPS = {
    "01": "alabama", "02": "alaska", "04": "arizona", "05": "arkansas", "06": "california",
    "08": "colorado", "09": "connecticut", "10": "delaware", "11": "district-of-columbia",
    "12": "florida", "13": "georgia", "15": "hawaii", "16": "idaho", "17": "illinois",
    "18": "indiana", "19": "iowa", "20": "kansas", "21": "kentucky", "22": "louisiana",
    "23": "maine", "24": "maryland", "25": "massachusetts", "26": "michigan", "27": "minnesota",
    "28": "mississippi", "29": "missouri", "30": "montana", "31": "nebraska", "32": "nevada",
    "33": "new-hampshire", "34": "new-jersey", "35": "new-mexico", "36": "new-york",
    "37": "north-carolina", "38": "north-dakota", "39": "ohio", "40": "oklahoma", "41": "oregon",
    "42": "pennsylvania", "44": "rhode-island", "45": "south-carolina", "46": "south-dakota",
    "47": "tennessee", "48": "texas", "49": "utah", "50": "vermont", "51": "virginia",
    "53": "washington", "54": "west-virginia", "55": "wisconsin", "56": "wyoming",
}


def _download():
    last = None
    for i in range(3):
        try:
            req = urllib.request.Request(ZIP_URL, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"BEA GDP zip: {last}")


def _num(raw):
    s = (raw or "").strip().replace(",", "")
    if not s or s in {"(NA)", "NA", "(D)", "(L)"} or s.startswith("("):
        return None
    return float(s)


def parse(blob):
    zf = zipfile.ZipFile(io.BytesIO(blob))
    name = next(n for n in zf.namelist() if n.startswith("SAGDP2__ALL_AREAS_") and n.endswith(".csv"))
    info = zf.getinfo(name)
    file_date = f"{info.date_time[0]:04d}-{info.date_time[1]:02d}-{info.date_time[2]:02d}"
    text = io.TextIOWrapper(zf.open(name), encoding="utf-8-sig", newline="")
    states = {}
    for row in csv.DictReader(text):
        if str(row.get("LineCode", "")).strip() != "1":
            continue
        if "SAGDP2" not in (row.get("TableName") or ""):
            continue
        unit = (row.get("Unit") or "").strip()
        if unit != "Millions of current dollars":
            raise RuntimeError(f"SAGDP2 line 1 unit is {unit!r}, not millions of current dollars")
        fips = (row.get("GeoFIPS") or "").strip().strip('"')
        if len(fips) < 2 or fips[:2] not in FIPS:
            continue
        # State rows are SS000. Region composites use other codes and are not states.
        if not fips.endswith("000"):
            continue
        slug = FIPS[fips[:2]]
        series = {}
        for key, val in row.items():
            if key and key.isdigit():
                n = _num(val)
                if n is not None:
                    series[key] = n
        if not series:
            continue
        states[slug] = {
            "name": (row.get("GeoName") or "").strip(),
            "geofips": fips,
            "gdp_millions_current": series,
        }
    missing = sorted(set(FIPS.values()) - set(states))
    if missing:
        raise RuntimeError("BEA SAGDP2 has no all-industry total for: " + ", ".join(missing))
    no_2024 = sorted(s for s, rec in states.items() if "2024" not in rec["gdp_millions_current"])
    return {
        "source": "U.S. Bureau of Economic Analysis, GDP by state",
        "table": "SAGDP2",
        "line": "1 All industry total",
        "unit": "Millions of current dollars",
        "price_basis": "current dollars, not adjusted for inflation",
        "source_url": PAGE_URL,
        "download_url": ZIP_URL,
        "file_name": name,
        "file_date": file_date,
        "fetched": __import__("clocktime").chicago_today().isoformat(),
        "states_without_2024": no_2024,
        "states": states,
    }


def main():
    doc = parse(_download())
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(doc, open(OUT, "w"), indent=1)
    open(OUT, "a").write("\n")
    years = set()
    for rec in doc["states"].values():
        years.update(rec["gdp_millions_current"])
    print(f"state GDP: {len(doc['states'])} areas, years {min(years)}-{max(years)}, file {doc['file_date']}")
    if doc["states_without_2024"]:
        print("no 2024 GDP:", ", ".join(doc["states_without_2024"]))


if __name__ == "__main__":
    main()
