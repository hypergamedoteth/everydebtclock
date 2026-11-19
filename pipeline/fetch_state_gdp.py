#!/usr/bin/env python3
"""BEA current-dollar GDP by state, for the state debt-to-GDP lines.

Table SAGDP2, all-industry total, from the public regional zip (no API key).
Figures stay in the published millions and are also stored as whole dollars
(millions × 1,000,000). A blank or suppressed BEA cell is left out.

Writes data/state_gdp.json. A failed download keeps the last good file and
exits 0 when that file exists.
"""
import csv, io, json, os, sys, time, zipfile, urllib.request
from decimal import Decimal, InvalidOperation

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "state_gdp.json")
ZIP_URL = "https://apps.bea.gov/regional/zip/SAGDP.zip"
PAGE_URL = "https://www.bea.gov/data/gdp/gdp-state"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
SOURCE_NAME = "U.S. Bureau of Economic Analysis, GDP by State, Table SAGDP2 (all industry total, current dollars)"


def get(url):
    last = None
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def _places():
    by_name = {}
    folder = os.path.join(ROOT, "places")
    for fn in os.listdir(folder):
        if not fn.endswith(".json"):
            continue
        p = json.load(open(os.path.join(folder, fn)))
        if p.get("kind") == "state" and p.get("status") == "live":
            by_name[p["name"]] = p
    return by_name


def _money(raw):
    s = (raw or "").strip().replace(",", "")
    if not s or s.startswith("("):
        return None
    try:
        millions = Decimal(s)
    except InvalidOperation:
        return None
    dollars = int((millions * Decimal(1000000)).to_integral_value())
    return str(millions), dollars


def fetch():
    blob = get(ZIP_URL)
    z = zipfile.ZipFile(io.BytesIO(blob))
    name = next((n for n in z.namelist() if n.startswith("SAGDP2__ALL_AREAS") and n.endswith(".csv")), None)
    if not name:
        raise RuntimeError("SAGDP.zip has no SAGDP2 all-areas file: " + ", ".join(z.namelist()[:8]))
    text = z.read(name).decode("utf-8-sig")
    # BEA's export puts a space before the first quoted field, so the stock parser
    # keeps the quote on GeoFIPS. Strip quotes and spaces on every cell.
    raw_rows = list(csv.reader(io.StringIO(text)))
    if len(raw_rows) < 2:
        raise RuntimeError("SAGDP2 file is empty")
    header = [c.strip().strip('"').strip() for c in raw_rows[0]]
    rows = []
    for raw in raw_rows[1:]:
        if len(raw) < len(header):
            raw = raw + [""] * (len(header) - len(raw))
        rows.append({header[i]: raw[i].strip().strip('"').strip() for i in range(len(header))})
    years = [k for k in header if k.isdigit()]
    if not years:
        raise RuntimeError("SAGDP2 file has no year columns")
    places = _places()
    states = {}
    unmatched = []
    for r in rows:
        if (r.get("LineCode") or "").strip() != "1":
            continue
        if "All industry total" not in (r.get("Description") or ""):
            continue
        unit = (r.get("Unit") or "").strip().lower()
        if "current dollars" not in unit:
            continue
        try:
            fips = int((r.get("GeoFIPS") or "").strip() or "0")
        except ValueError:
            continue
        state_fips = fips // 1000
        if not 1 <= state_fips <= 56:
            continue
        geo = (r.get("GeoName") or "").replace("*", "").strip()
        place = places.get(geo)
        if not place:
            unmatched.append(geo)
            continue
        gdp = {}
        published = {}
        for y in years:
            parsed = _money(r.get(y))
            if not parsed:
                continue
            millions, dollars = parsed
            published[y] = millions
            gdp[y] = dollars
        if not gdp:
            unmatched.append(geo + " (no numeric year)")
            continue
        states[place["slug"]] = {
            "name": place["name"],
            "region_code": place.get("region_code"),
            "geofips": (r.get("GeoFIPS") or "").strip(),
            "gdp_dollars": gdp,
            "gdp_millions_published": published,
        }
    missing = sorted(p["slug"] for p in places.values() if p["slug"] not in states)
    if unmatched:
        raise RuntimeError("BEA names with no state page: " + ", ".join(unmatched))
    return {
        "source_name": SOURCE_NAME,
        "source_url": ZIP_URL,
        "dataset_url": PAGE_URL,
        "table": "SAGDP2",
        "file": name,
        "unit": "millions of current dollars",
        "line": "All industry total",
        "fetched": time.strftime("%Y-%m-%d", time.gmtime()),
        "years": years,
        "note": "Calendar-year current-dollar GDP, not adjusted for inflation. Dollars equal the published millions times 1,000,000. A year BEA suppressed or left blank is omitted.",
        "states": states,
        "missing_slugs": missing,
    }


def main():
    try:
        doc = fetch()
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        tmp = OUT + ".tmp"
        json.dump(doc, open(tmp, "w"), indent=1)
        open(tmp).close()
        os.replace(tmp, OUT)
        print(f"state gdp: {len(doc['states'])} areas, years {doc['years'][0]}–{doc['years'][-1]}, file {doc['file']}")
        if doc["missing_slugs"]:
            print("state gdp missing:", ", ".join(doc["missing_slugs"]))
        return 0
    except Exception as e:
        print(f"state gdp: {e}", file=sys.stderr)
        if os.path.exists(OUT):
            print("state gdp: kept the last good file")
            return 0
        return 1


if __name__ == "__main__":
    sys.exit(main())
