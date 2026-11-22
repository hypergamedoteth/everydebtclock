#!/usr/bin/env python3
"""Fetch year-by-year debt for the state and country pages.

Writes data/debt_by_year.json. Every amount is parsed from an official file or API.
A place is omitted (listed under "skipped") when its source cannot be read or does not
match the figure already on its debt clock.

States: Census Bureau summary tables for survey years before 2017 (total debt outstanding,
state and local), the same item the clocks use. Survey years 2017–2024 are not stored here;
debt_by_year_build.py reads them from places/<state>.json, which pipeline/census_state.py
fills from the Census time-series table GS00LOCALFIN.

Countries: the same series the country clock already uses, taken back as far as that
source publishes a machine-readable history. .xls workbooks need xlrd (not used by the
daily site build).

Run: python3 pipeline/fetch_debt_by_year.py
"""
import calendar, json, os, re, sys, urllib.request
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import census_state
import xlsx_min

OUT = os.path.join(ROOT, "data", "debt_by_year.json")
FLAGS = os.path.join(ROOT, "data", "longtail_flags.json")
UA = {"User-Agent": "Mozilla/5.0 (compatible; everydebtclock.com data refresh)"}
# The four original clocks predate census_state.STATES. Same Census definitions.
_EXTRA_STATES = {
    "california": ("California", "Californian", "CA", "06", ""),
    "texas": ("Texas", "Texan", "TX", "48", ""),
    "florida": ("Florida", "Floridian", "FL", "12", ""),
    "new-york": ("New York", "New Yorker", "NY", "36", ""),
}
_CATALOG = {}
for _slug, (_name, _dem, _usps, _fips, _note) in {**census_state.STATES, **_EXTRA_STATES}.items():
    _CATALOG[_slug] = {"name": _name, "postal": _usps.lower(), "fips": _fips}
STATE_SLUGS = sorted(_CATALOG)
STATE_NAME = {k: v["name"] for k, v in _CATALOG.items()}
STATE_FIPS = {k: v["fips"] for k, v in _CATALOG.items()}
NAME_TO_SLUG = {v: k for k, v in STATE_NAME.items()}
POSTAL = {k: v["postal"] for k, v in _CATALOG.items()}
# States whose pre-2017 rows were checked in the first debt-by-year release. A re-parse that
# disagrees with those rows stops the run instead of rewriting them.
ANCHOR_STATES = [
    "california", "texas", "new-york", "florida", "illinois", "new-jersey",
    "massachusetts", "pennsylvania", "washington", "ohio",
]
CENSUS_API = "https://data.census.gov/api/access/data/table?id=GOVSLOCALFINTIMESERIES.GS00LOCALFIN&g=040XX00US{fips}"
CENSUS_TABLE = "https://data.census.gov/table/GOVSLOCALFINTIMESERIES.GS00LOCALFIN?q=GS00LOCALFIN&g=040XX00US{fips}"
CENSUS_REL = "https://www.census.gov/programs-surveys/gov-finances/data/tables.html"


def get(url, timeout=90):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def norm(v):
    return re.sub(r"\s+", " ", str(v or "")).strip()


def num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "").replace("−", "-").replace("–", "-")
    if not re.fullmatch(r"-?\d+(\.\d+)?", s):
        return None
    return float(s)


def dollars(v):
    """Census publishes debt in thousands of dollars."""
    return int(round(v * 1000))


def sheet_grids(data):
    if data[:2] == b"PK":
        wb = xlsx_min.read_bytes(data)
        out = []
        for rows in wb.values():
            grid = []
            for _, row in rows:
                if not row:
                    continue
                m = max(_col(k) for k in row)
                arr = [None] * (m + 1)
                for k, v in row.items():
                    arr[_col(k)] = v
                grid.append(arr)
            out.append(grid)
        return out
    import xlrd
    book = xlrd.open_workbook(file_contents=data)
    return [[[sh.cell_value(r, c) for c in range(sh.ncols)] for r in range(sh.nrows)] for sh in book.sheets()]


def _col(letters):
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch.upper()) - 64
    return n - 1


def _at(row, i):
    return row[i] if i < len(row) else None


def parse_census_workbook(data):
    """{slug: (total, state, local)} in dollars, from a summary workbook (one or two sheets)."""
    found = {}
    for grid in sheet_grids(data):
        state_cols, desc_col, header_r = {}, None, None
        for r, row in enumerate(grid):
            names, desc_here = {}, None
            for c, val in enumerate(row):
                s = norm(val)
                if s == "Description":
                    desc_here = c
                if s in NAME_TO_SLUG:
                    names[s] = c
            # Sheet 1a holds only some of the ten states, so one recognized state next to
            # the Description header is enough. Description has to be on this row.
            if desc_here is not None and names:
                state_cols, desc_col, header_r = names, desc_here, r
                break
        if not state_cols or desc_col is None:
            continue
        labels = None
        for r in range(header_r + 1, min(header_r + 8, len(grid))):
            row = grid[r]
            c0 = next(iter(state_cols.values()))
            lab = norm(_at(row, c0)).lower()
            if lab.startswith("amount"):
                labels = row
                break
        debt = None
        for row in grid:
            if norm(_at(row, desc_col)).lower() == "debt outstanding":
                debt = row
                break
        if labels is None or debt is None:
            continue
        for name, c in state_cols.items():
            later = [cc for cc in state_cols.values() if cc > c]
            end = min(later) if later else c + 6
            amounts = []
            for i in range(c, end):
                lab = norm(_at(labels, i)).lower()
                if lab.startswith("amount"):
                    amounts.append(i)
            if len(amounts) < 3:
                continue
            total, state, local = (num(_at(debt, i)) for i in amounts[:3])
            if None in (total, state, local):
                continue
            if abs((state + local) - total) > 5:
                raise RuntimeError(f"{name}: state {state} + local {local} != total {total}")
            if total < 1000:
                raise RuntimeError(f"{name}: implausible total {total}")
            found[NAME_TO_SLUG[name]] = (dollars(total), dollars(state), dollars(local))
    return found


def census_workbooks():
    """Survey year -> (url_a, url_b or None)."""
    files = {}
    # Single combined workbooks (every state in one file). Used only when the parser
    # actually finds all ten states; a different layout is skipped, not guessed.
    files[2001] = ("https://www2.census.gov/govs/estimate/01stl001.xls", None)
    files[2003] = ("https://www2.census.gov/govs/estimate/03stl001.xls", None)
    files[2002] = (
        "https://www2.census.gov/programs-surveys/gov-finances/tables/2002/summary-tables/02slsstab1a.xls",
        "https://www2.census.gov/programs-surveys/gov-finances/tables/2002/summary-tables/02slsstab1b.xls",
    )
    files[2004] = (
        "https://www2.census.gov/govs/estimate/04slsstab1a.xls",
        "https://www2.census.gov/govs/estimate/04slsstab1b.xls",
    )
    for y in range(2005, 2012):
        yy = f"{y % 100:02d}"
        base = f"https://www2.census.gov/programs-surveys/gov-finances/tables/{y}/summary-tables/{yy}slsstab1"
        files[y] = (base + "a.xls", base + "b.xls")
    for y in range(2012, 2017):
        yy = f"{y % 100:02d}"
        base = f"https://www2.census.gov/programs-surveys/gov-finances/tables/{y}/summary-tables/{yy}slsstab1"
        files[y] = (base + "a.xlsx", base + "b.xlsx")
    return files


def interpret_amounts(nums):
    """Pick (total, state, local) in thousands from the numbers on one debt line."""
    def ok(total, state, local):
        return total > 1000 and state > 0 and local > 0 and abs((state + local) - total) <= 5

    cands = []
    if len(nums) >= 5 and nums[1] < 100 and nums[4] < 100 and ok(nums[0], nums[2], nums[3]):
        cands.append((nums[0], nums[2], nums[3]))
    if len(nums) >= 3 and ok(nums[0], nums[1], nums[2]):
        cands.append((nums[0], nums[1], nums[2]))
    uniq = set(cands)
    if len(uniq) == 1:
        return uniq.pop()
    return None


def line_amounts(text):
    nums = []
    for tok in re.findall(r"-?[\d,]+(?:\.\d+)?", text):
        if not re.search(r"\d", tok):
            continue
        nums.append(float(tok.replace(",", "")))
    hit = interpret_amounts(nums)
    if hit:
        return hit
    if nums and nums[0] < 500 and nums[0] == int(nums[0]):
        return interpret_amounts(nums[1:])
    return None


def parse_state_file(data, filename):
    name = filename.lower()
    if name.endswith(".csv") or (b"," in data[:200] and not data[:2] == b"PK" and not data[:4] == b"\xd0\xcf\x11\xe0"):
        text = data.decode("latin1", "replace")
        for line in text.splitlines():
            if re.search(r"debt outstanding", line, re.I) and "interest" not in line.lower() and "purpose" not in line.lower():
                hit = line_amounts(line)
                if hit:
                    return tuple(dollars(x) for x in hit)
        return None
    try:
        found = parse_census_workbook(data)
    except Exception:
        return None
    # a one-state file should contain exactly one of our states
    ours = [s for s in found if s in STATE_NAME]
    if len(ours) == 1:
        return found[ours[0]]
    return None


def is_state_filename(name, postal):
    n = name.lower()
    if re.search(rf"sl\d{{2}}{postal}\.(csv|xlsx|xls)$", n):
        return True
    if re.search(rf"(?:^|[^a-z]){postal}sl[-_.0-9]", n):
        return True
    if re.search(rf"(?:^|[^a-z]){postal}\.(csv|xlsx|xls)$", n):
        return True
    return False


def census_early_years():
    """Per-state summary files for survey years that predate the combined workbook."""
    out = {}  # year -> {slug: (total, state, local)}
    urls = {}
    for y in list(range(1992, 2002)) + [2003]:
        yy = f"{y % 100:02d}"
        index = f"https://www2.census.gov/programs-surveys/gov-finances/tables/{y}/summary-tables/"
        try:
            html = get(index).decode("latin1", "replace")
        except Exception as e:
            print(f"census {y}: no directory ({e})")
            continue
        hrefs = re.findall(r'href="([^"?][^"]*)"', html)
        year_rows, year_urls = {}, {}
        for slug, postal in POSTAL.items():
            matches = [h for h in hrefs if is_state_filename(h, postal)]
            if len(matches) != 1:
                continue
            url = index + matches[0]
            try:
                parsed = parse_state_file(get(url), matches[0])
            except Exception as e:
                print(f"census {y} {slug}: {e}")
                continue
            if not parsed:
                print(f"census {y} {slug}: debt line not read ({matches[0]})")
                continue
            year_rows[slug] = parsed
            year_urls[slug] = url
        if year_rows:
            out[y] = year_rows
            urls[y] = year_urls
            ca = year_rows.get("california", (None,))[0]
            print(f"census {y}: per-state files, {len(year_rows)} states" + (f", CA total ${ca:,}" if ca else ""))
        else:
            print(f"census {y}: no per-state debt files")
    return out, urls


def fetch_states_clean():
    """Survey years before 2017, each state pointing at the file that held it."""
    series = {s: {} for s in STATE_SLUGS}
    file_of = {s: {} for s in STATE_SLUGS}
    early, early_urls = census_early_years()
    for y, rows in early.items():
        for slug, (total, state, local) in rows.items():
            series[slug][y] = row(y, total, state, local)
            file_of[slug][y] = early_urls[y][slug]
    for y, (ua, ub) in census_workbooks().items():
        try:
            a = parse_census_workbook(get(ua))
            b = parse_census_workbook(get(ub)) if ub else {}
        except Exception as e:
            print(f"census {y}: workbook skipped ({e})")
            continue
        found = dict(a)
        found.update(b)
        if not found:
            print(f"census {y}: workbook had no state debt rows, year skipped")
            continue
        for slug, (total, state, local) in found.items():
            if slug not in series:
                continue
            if slug == "district-of-columbia":
                if state != 0 or local != total:
                    print(f"census {y} DC: state {state} local {local} total {total}, year left out")
                    continue
            elif state <= 0 or local <= 0:
                print(f"census {y} {slug}: non-positive part, year left out")
                continue
            series[slug][y] = row(y, total, state, local)
            file_of[slug][y] = ua if slug in a else ub
        missing = [s for s in STATE_SLUGS if s not in found]
        ca = found.get("california", (None,))[0]
        print(f"census {y}: workbook, {len(found)} states" + (f", CA ${ca:,}" if ca else "") + (f", missing {len(missing)}" if missing else ""))
    ca = series["california"]
    if ca.get(2002, {}).get("total") != 209_671_522_000:
        raise SystemExit(f"census anchor failed: CA 2002 is {ca.get(2002)}")
    if ca.get(2016, {}).get("total") != 437_899_643_000:
        raise SystemExit(f"census anchor failed: CA 2016 is {ca.get(2016)}")
    # Confirm the current time series still matches the clock files, so pre-2017 can sit beside it.
    # One state that fails is left out. The ten already published must still match, or the file is not rewritten.
    api_bad = []
    for slug in STATE_SLUGS:
        try:
            api_rows = census_api(slug)
        except Exception as e:
            print(f"census API {slug}: {e}")
            api_bad.append(slug)
            continue
        place = json.load(open(os.path.join(ROOT, "places", slug + ".json")))
        comps = {c["key"]: {d: v for d, v in c["history"]} for c in place["components"]}
        dc = slug == "district-of-columbia"
        for d, total, state, local in api_rows:
            if dc:
                ok = comps.get("local", {}).get(d) == local and state == 0 and total == local
            else:
                ok = comps.get("state", {}).get(d) == state and comps.get("local", {}).get(d) == local
            if not ok:
                print(f"census API {slug} {d} does not match places/{slug}.json")
                api_bad.append(slug)
                break
    anchor_bad = [s for s in api_bad if s in ANCHOR_STATES]
    if anchor_bad:
        raise SystemExit(f"Census time series does not match the published state clocks: {anchor_bad}")
    for slug in api_bad:
        series[slug].clear()
        file_of[slug].clear()
    places = {}
    for slug in STATE_SLUGS:
        if slug in api_bad:
            continue
        rows = [series[slug][y] for y in sorted(series[slug])]
        # one source entry per file, years ascending
        srcs = []
        for y in sorted(file_of[slug]):
            srcs.append({"year": y, "name": f"US Census Bureau, State and Local Government Finances, survey year {y}, total debt outstanding", "url": file_of[slug][y]})
        places[slug] = {
            "kind": "state",
            "year_end_month": 6,
            "rows": rows,
            "sources": srcs,
            "api_source": {"name": "US Census Bureau, Annual Survey of State and Local Government Finances, table GS00LOCALFIN, total debt outstanding (LF0231), survey years 2017–2024", "url": CENSUS_TABLE.format(fips=STATE_FIPS[slug])},
            "api_download": CENSUS_API.format(fips=STATE_FIPS[slug]),
            "release_page": CENSUS_REL,
            "note": "Survey years before 2017 are the summary table Census published for that year (total debt outstanding; state government plus local government). Survey years 2017–2024 are Census's current time-series table, the same figures as the state debt clock. Census rebuilt that time series from 2017, so those years are the revised figures and the earlier years are the originally published tables. A survey year that is not in the table was not in a by-state file this fetch could read, and it is left out rather than estimated.",
        }
    skipped = [{"slug": s, "reason": "Census time series GS00LOCALFIN did not match places/" + s + ".json, or the API could not be read. No debt-by-year page was written for this state."} for s in api_bad]
    return places, skipped


def row(y, total, state, local):
    return {"year": y, "date": f"{y}-06-30", "total": total, "state": state, "local": local}


def census_api(slug):
    import time
    last = None
    for i in range(6):
        try:
            d = json.loads(get(CENSUS_API.format(fips=STATE_FIPS[slug])))
            data = d["response"]["data"]
            break
        except Exception as e:
            last = e
            time.sleep(4 * (i + 1))
    else:
        raise RuntimeError(last)
    h = data[0]
    ix = {k: h.index(k) for k in h}
    out = {"State": {}, "Local": {}}
    for r in data[1:]:
        if r[ix["AGG_DESC"]] != "LF0231":
            continue
        g = r[ix["GOVTYPE_LABEL"]]
        if g in out:
            out[g][int(r[ix["YEAR"]])] = int(r[ix["AMOUNT"]]) * 1000
    rows = []
    if slug == "district-of-columbia":
        # Census has no state-government level for the District. Local is the total.
        for y in sorted(out["Local"]):
            local = out["Local"][y]
            rows.append((f"{y}-06-30", local, 0, local))
    else:
        for y in sorted(set(out["State"]) & set(out["Local"])):
            rows.append((f"{y}-06-30", out["State"][y] + out["Local"][y], out["State"][y], out["Local"][y]))
    if not rows:
        raise RuntimeError("no LF0231 rows")
    return rows


# ---------------------------------------------------------------- countries

def place(slug):
    return json.load(open(os.path.join(ROOT, "places", slug + ".json")))


def month_end(y, m):
    return f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"


def check_overlap(slug, series, tol=0):
    """series: {date: int}. Must agree with the clock file on every shared date, and share at least one date."""
    p = place(slug)
    c = p["components"][0]
    hist = {d: int(v) for d, v in c["history"]}
    hist[c["as_of"]] = int(c["value"])
    shared = [d for d in hist if d in series]
    if len(shared) < 1:
        raise RuntimeError(f"{slug}: fetched series does not overlap the clock ({c['as_of']})")
    for d in shared:
        if abs(series[d] - hist[d]) > tol:
            raise RuntimeError(f"{slug}: {d} fetched {series[d]} != clock {hist[d]}")
    return series


def ons_uk():
    raw = json.loads(get("https://www.ons.gov.uk/economy/governmentpublicsectorandtaxes/publicsectorfinance/timeseries/bkpx/pusf/data"))
    mon = {m.upper(): i for i, m in enumerate(calendar.month_abbr) if m}
    series = {}
    for r in raw["months"]:
        if r.get("value") in (None, ""):
            continue
        y, m = r["date"].split()
        series[month_end(int(y), mon[m])] = int(round(float(r["value"]) * 1_000_000))
    check_overlap("united-kingdom", series)
    return series


def boc_canada():
    raw = json.loads(get("https://www.bankofcanada.ca/valet/observations/V42141673/json?start_date=1990-01-01"))
    series = {}
    for o in raw["observations"]:
        v = o.get("V42141673", {}).get("v")
        if v in (None, ""):
            continue
        y, m = int(o["d"][:4]), int(o["d"][5:7])
        series[month_end(y, m)] = int(round(float(v))) * 1_000_000
    check_overlap("canada", series)
    return series


def bcb_brazil():
    raw = json.loads(get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.13761/dados?formato=json"))
    series = {}
    for r in raw:
        dd, mm, yy = r["data"].split("/")
        y, m = int(yy), int(mm)
        series[month_end(y, m)] = int(round(float(r["valor"]) * 1_000_000))
    check_overlap("brazil", series)
    return series


def eurostat():
    import fetch_eurostat as fe
    url = ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/gov_10q_ggdebt"
           "?format=JSON&lang=EN&geo=DE&geo=FR&geo=IT&sector=S1311&na_item=GD&unit=MIO_EUR&sinceTimePeriod=1995-Q1")
    data = fe.get(url)
    series = {"germany": {}, "france": {}, "italy": {}}
    geo = {"DE": "germany", "FR": "france", "IT": "italy"}
    for c, v in fe.cells(data):
        if c.get("sector") != "S1311" or c.get("na_item") != "GD" or c["geo"] not in geo:
            continue
        series[geo[c["geo"]]][fe.qend(c["time"])] = int(round(float(v) * 1_000_000))
    for slug, s in series.items():
        check_overlap(slug, s)
    return series


def australia():
    html = get("https://www.aofm.gov.au/data-hub").decode("utf-8", "replace")
    m = re.search(r'href="(/sites/default/files/[^"]*portfolio_aggregate_-_dealt[^"]*\.xlsx)"', html)
    if not m:
        raise RuntimeError("AOFM workbook link not found")
    url = "https://www.aofm.gov.au" + m.group(1)
    wb = xlsx_min.read_bytes(get(url))
    rows = wb["FaceValue"]
    hdr = next(r for _, r in rows if (r.get("A") or "").strip() == "Instrument")
    cols = {str(v).strip(): k for k, v in hdr.items() if v}
    total_name = "Total AUD Main Funding Instruments"
    if total_name not in cols:
        raise RuntimeError("AOFM total column missing")
    series = {}
    for _, r in rows:
        a = r.get("A") or ""
        if not re.fullmatch(r"\d{5}", str(a).strip()):
            continue
        d = (date(1899, 12, 30) + __import__("datetime").timedelta(days=int(float(a)))).isoformat()
        series[d] = int(round(-float(r.get(cols[total_name]) or 0)))
    # The clock keeps whole dollars. Allow 1 dollar of rounding against the stored history.
    check_overlap("australia", series, tol=1)
    return series, url


def japan():
    url = "https://www.mof.go.jp/english/policy/jgbs/reference/gbb/suii.xls"
    grids = sheet_grids(get(url))
    grid = grids[0]
    header = None
    date_re = re.compile(r"20\d{2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)")
    for row in grid:
        if any(date_re.search(norm(c)) for c in row):
            header = row
            break
    if header is None:
        raise RuntimeError("Japan workbook: date header not found")
    total = None
    for row in grid:
        if any(norm(c).endswith("Total") or norm(c).startswith("Total") or "合計" in norm(c) for c in row[:3]):
            total = row
            break
    if total is None:
        raise RuntimeError("Japan workbook: total row not found")
    mon = {m: i for i, m in enumerate(calendar.month_name) if m}
    series = {}
    for i, cell in enumerate(header):
        s = norm(cell)
        m = re.search(r"(20\d{2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)", s)
        if not m:
            continue
        v = num(_at(total, i))
        if v is None:
            continue
        series[month_end(int(m.group(1)), mon[m.group(2)])] = int(round(v * 100_000_000))
    check_overlap("japan", series)
    return series, url


def china():
    import fetch_china as fc
    files = fc.listing()
    if not files:
        raise RuntimeError("no MOF debt PDFs")
    series = {}
    for y, url in sorted(files.items()):
        got = fc.parse_pdf(fc.get(url))
        for q, total in enumerate(got["total"], 1):
            series[fc.qend(y, q)] = int(round(total * fc.BN))
    check_overlap("china", series)
    return series, "https://gks.mof.gov.cn/tongjishuju/"


def india():
    import fetch_india as fi
    files = fi.listing()
    if not files:
        raise RuntimeError("no DEA quarterly reports")
    data = {}
    used = []
    for key in sorted(files):
        try:
            parsed = fi.parse_pdf(fi.get(files[key]))
        except Exception as e:
            print(f"india: {key} not used ({e})")
            continue
        for lbl, (cur, prv) in parsed.items():
            if lbl != "H":
                continue
            data[key] = cur
            pk = fi.prev_q(*key)
            data.setdefault(pk, prv)
        used.append(files[key])
    series = {fi.qend(*k): int(v) * fi.CRORE for k, v in data.items()}
    # Drop a quarter that jumps by more than 40% versus both neighbours: that is a mis-read, not a debt stock.
    ks = sorted(series)
    bad = set()
    for i in range(1, len(ks) - 1):
        a, b, c = series[ks[i - 1]], series[ks[i]], series[ks[i + 1]]
        if a and c and (b / a > 1.4 or b / a < 0.6) and (b / c > 1.4 or b / c < 0.6):
            bad.add(ks[i])
    for d in bad:
        print(f"india: dropping {d} as an implausible quarter")
        del series[d]
    check_overlap("india", series)
    return series, "http://dea.gov.in/reports-public-debt-management"


COUNTRY_SPEC = {
    "united-kingdom": {"year_end_month": 12, "fetch": ons_uk},
    "canada": {"year_end_month": 12, "fetch": boc_canada},
    "germany": {"year_end_month": 12},
    "france": {"year_end_month": 12},
    "italy": {"year_end_month": 12},
    "brazil": {"year_end_month": 12, "fetch": bcb_brazil},
    "australia": {"year_end_month": 6, "fetch": australia},
    "japan": {"year_end_month": 3, "fetch": japan},
    "china": {"year_end_month": 12, "fetch": china},
    "india": {"year_end_month": 3, "fetch": india},
}


def pack_country(slug, series, source, year_end_month):
    pts = [{"date": d, "amount": series[d]} for d in sorted(series)]
    return {
        "kind": "country",
        "year_end_month": year_end_month,
        "points": pts,
        "sources": [source],
    }


# G20 members that are countries in the IMF panel. The European Union is not a country clock.
G20_ISO = {
    "ARG", "AUS", "BRA", "CAN", "CHN", "FRA", "DEU", "IND", "IDN", "ITA", "JPN",
    "MEX", "RUS", "SAU", "ZAF", "KOR", "TUR", "GBR", "USA",
}
IMF_RATIO_URL = "https://www.imf.org/external/datamapper/GGXWDG_NGDP@WEO"
IMF_GDP_URL = "https://www.imf.org/external/datamapper/NGDPD@WEO"
WB_WEO = "https://data360files.worldbank.org/data360-data/data/IMF_WEO/IMF_WEO.csv"
IMF_LAST_YEAR = 2026  # later years in this vintage are forecasts and are not published


def _debt_usd(ratio, gdp):
    return int(round(ratio / 100.0 * gdp))


def _weo_history():
    """iso3 -> {year: (ratio_percent, gdp_usd)} from the World Bank mirror of the WEO.

    NGDPD in that file is current US dollars. GGXWDG_NGDP is the unrounded ratio. This is the
    same file pipeline/fetch_world.py uses when precision_source is worldbank.
    """
    import csv, io
    text = io.TextIOWrapper(urllib.request.urlopen(urllib.request.Request(WB_WEO, headers=UA), timeout=180), encoding="utf-8", newline="")
    ratio, gdp = {}, {}
    for row in csv.DictReader(text):
        ind = row.get("INDICATOR")
        if ind not in ("IMF_WEO_GGXWDG_NGDP", "IMF_WEO_NGDPD"):
            continue
        if row.get("COMP_BREAKDOWN_1") not in (None, "", "V_LST"):
            continue
        year = row.get("TIME_PERIOD")
        if not year or not year.isdigit() or int(year) > IMF_LAST_YEAR:
            continue
        code = row.get("REF_AREA") or ""
        if len(code) != 3:
            continue
        val = num(row.get("OBS_VALUE"))
        if val is None:
            continue
        (ratio if ind == "IMF_WEO_GGXWDG_NGDP" else gdp).setdefault(code, {})[year] = val
    # The mirror reports NGDPD in dollars. A billions file would put the US near 3e4.
    usa = gdp.get("USA", {}).get(str(IMF_LAST_YEAR))
    scale = 1e9 if usa is not None and usa < 1e9 else 1.0
    out = {}
    for code in set(ratio) & set(gdp):
        years = {}
        for y in set(ratio[code]) & set(gdp[code]):
            r, g = ratio[code][y], gdp[code][y] * scale
            if r > 0 and g > 0:
                years[y] = (r, int(round(g)))
        if years:
            out[code] = years
    return out


def fetch_imf_countries(national_slugs):
    """IMF general-government debt by year for G20 and the 40 largest economies by 2026 GDP.

    A country that already has a debt-by-year page from its own source is left on that source.
    The United States stays on Treasury Debt to the Penny. A series is kept only when its
    end-2025 and end-2026 stocks match data/world_weo_debt.json exactly.
    """
    weo = json.load(open(os.path.join(ROOT, "data", "world_weo_debt.json")))
    ecos = weo["economies"]
    top = {e["iso3"] for e in sorted(ecos, key=lambda e: e["gdp_2026_usd"], reverse=True)[:40]}
    want = top | G20_ISO
    by = {e["iso3"]: e for e in ecos}
    print("imf history…")
    hist = _weo_history()
    places, skipped = {}, []
    src = [
        {"name": "IMF World Economic Outlook, October 2026, GGXWDG_NGDP, general government gross debt, percent of GDP", "url": IMF_RATIO_URL},
        {"name": "IMF World Economic Outlook, October 2026, NGDPD, GDP, current US dollars", "url": IMF_GDP_URL},
        {"name": "World Bank Data360 mirror of the IMF World Economic Outlook (unrounded GGXWDG_NGDP and NGDPD)", "url": WB_WEO},
    ]
    for code in sorted(want, key=lambda c: by.get(c, {}).get("name") or c):
        e = by.get(code)
        if e is None:
            skipped.append({"slug": code.lower(), "reason": f"{code} is not in data/world_weo_debt.json"})
            continue
        slug, name = e["slug"], e["name"]
        if code == "USA":
            skipped.append({"slug": slug, "reason": "The US page uses Treasury Debt to the Penny, not the IMF estimate. No second US debt-by-year page."})
            continue
        if slug in national_slugs:
            continue
        years = hist.get(code) or {}
        points = []
        for y in sorted(years):
            ratio, gdp = years[y]
            points.append({"date": f"{y}-12-31", "amount": _debt_usd(ratio, gdp), "ratio": round(ratio, 6), "gdp_usd": gdp})
        reason = None
        if len(points) < 5:
            reason = f"fewer than five year-end IMF observations through {IMF_LAST_YEAR}"
        else:
            got = {p["date"][:4]: p for p in points}
            for y in ("2025", "2026"):
                p = got.get(y)
                if p is None:
                    reason = f"no IMF end-{y} stock"
                    break
                if p["amount"] != e[f"debt_{y}_usd"] or p["gdp_usd"] != e[f"gdp_{y}_usd"]:
                    reason = (f"end-{y} stock {p['amount']} or GDP {p['gdp_usd']} does not match "
                              f"the World Debt Clock's stored WEO figure {e[f'debt_{y}_usd']} / {e[f'gdp_{y}_usd']}")
                    break
        if reason:
            print("imf", slug, "SKIP", reason)
            skipped.append({"slug": slug, "reason": "IMF general government debt not published: " + reason})
            continue
        place_path = os.path.join(ROOT, "places", slug + ".json")
        if os.path.exists(place_path):
            p = json.load(open(place_path))
            clock_note = (f"The {name} debt clock on this site is {p.get('headline') or 'a national series'}, from {p.get('publisher') or 'its publisher'}. "
                          f"That is a different series from this IMF general-government total, so the two amounts are not the same and are not added together.")
        else:
            clock_note = (f"The {name} debt clock uses this same IMF series. It moves between the end-2025 and end-2026 stocks. "
                          f"This table shows those year-end estimates, not the live interpolation.")
        places[slug] = {
            "kind": "imf",
            "name": name,
            "year_end_month": 12,
            "points": points,
            "sources": src,
            "clock_note": clock_note,
            "vintage": weo.get("vintage") or "October 2026",
            "iso3": code,
        }
        print("imf", slug, points[0]["date"], points[-1]["date"], len(points), points[-1]["amount"])
    return places, skipped


def _load_existing():
    if os.path.exists(OUT):
        return json.load(open(OUT))
    return {"places": {}, "skipped": []}


def _overlap_matches(old_rows, new_rows):
    old = {r["year"]: r for r in old_rows}
    new = {r["year"]: r for r in new_rows}
    if not set(old) <= set(new):
        return False
    for y, r in old.items():
        n = new[y]
        for k in ("total", "state", "local"):
            if abs(int(r[k]) - int(n[k])) > 5000:
                return False
    return True


def main():
    existing = _load_existing()
    skipped = []
    places_out = {}
    for slug, rec in existing.get("places", {}).items():
        if rec.get("kind") == "country":
            places_out[slug] = rec
    print("states…")
    try:
        new_states, state_skipped = fetch_states_clean()
        skipped.extend(state_skipped)
        for slug, rec in new_states.items():
            old = (existing.get("places") or {}).get(slug)
            if old and old.get("kind") == "state" and slug in ANCHOR_STATES:
                if not _overlap_matches(old["rows"], rec["rows"]):
                    raise SystemExit(f"{slug}: re-parsed Census history does not match the published debt-by-year file")
                extra = sorted(set(r["year"] for r in rec["rows"]) - set(r["year"] for r in old["rows"]))
                places_out[slug] = old if not extra else rec
                if extra:
                    print(slug, "added survey years", extra)
            else:
                places_out[slug] = rec
    except Exception as e:
        print("STATES FAILED:", e)
        for slug, rec in existing.get("places", {}).items():
            if rec.get("kind") == "state":
                places_out[slug] = rec
        skipped.append({"slug": "states", "reason": f"Census history could not be fetched or checked: {e}"})
    print("countries…")
    euro = {}
    try:
        euro = eurostat()
        print("eurostat", {k: (min(v), max(v), len(v)) for k, v in euro.items()})
    except Exception as e:
        print("eurostat failed:", e)
        for s in ("germany", "france", "italy"):
            if s not in places_out:
                skipped.append({"slug": s, "reason": f"Eurostat gov_10q_ggdebt could not be fetched or did not match the clock: {e}"})
            else:
                print(s, "kept the previously checked series")
    euro_src = {"name": "Eurostat, Quarterly government debt (gov_10q_ggdebt), central government (S1311), Maastricht debt, million euro",
                "url": "https://ec.europa.eu/eurostat/databrowser/view/gov_10q_ggdebt/default/table"}
    for slug, ser in euro.items():
        places_out[slug] = pack_country(slug, ser, euro_src, 12)
    singles = {
        "united-kingdom": (ons_uk, {"name": "Office for National Statistics, Public sector finances, series BKPX, general government consolidated gross debt (Maastricht), £ million",
                                    "url": "https://www.ons.gov.uk/economy/governmentpublicsectorandtaxes/publicsectorfinance/timeseries/bkpx/pusf"}),
        "canada": (boc_canada, {"name": "Bank of Canada Valet, series V42141673, Government of Canada total securities outstanding (inflation adjusted), C$ millions",
                                "url": "https://www.bankofcanada.ca/valet/observations/V42141673/json"}),
        "brazil": (bcb_brazil, {"name": "Banco Central do Brasil, SGS series 13761, Dívida bruta do governo geral (DBGG), R$ million",
                                "url": "https://api.bcb.gov.br/dados/serie/bcdata.sgs.13761/dados?formato=json"}),
    }
    for slug, (fn, src) in singles.items():
        try:
            ser = fn()
            places_out[slug] = pack_country(slug, ser, src, 3 if slug == "united-kingdom" else 12)
            print(slug, min(ser), max(ser), len(ser))
        except Exception as e:
            print(slug, "FAILED", e)
            if slug not in places_out:
                skipped.append({"slug": slug, "reason": f"The national series for {slug} could not be read ({e}). No debt-by-year page was published from that series."})
            else:
                print(slug, "kept the previously checked series")
    for slug, month, fn, src_name in (
        ("australia", 6, australia, None),
        ("japan", 3, japan, None),
        ("china", 12, china, None),
        ("india", 3, india, None),
    ):
        try:
            got = fn()
            ser, url = got if isinstance(got, tuple) else (got, None)
            p = place(slug)
            src = {"name": p["components"][0]["source_name"], "url": url or p["components"][0]["source_url"]}
            places_out[slug] = pack_country(slug, ser, src, month)
            print(slug, min(ser), max(ser), len(ser))
        except Exception as e:
            print(slug, "FAILED", e)
            if slug not in places_out:
                skipped.append({"slug": slug, "reason": f"The national series for {slug} could not be read ({e}). No debt-by-year page was published from that series."})
            else:
                print(slug, "kept the previously checked series")
    national = {s for s, rec in places_out.items() if rec.get("kind") == "country"}
    try:
        imf_places, imf_skipped = fetch_imf_countries(national)
        places_out.update(imf_places)
        skipped.extend(imf_skipped)
    except Exception as e:
        print("IMF FAILED:", e)
        skipped.append({"slug": "imf", "reason": f"IMF World Economic Outlook history could not be fetched or checked: {e}"})
    doc = {
        "_doc": "Year-by-year debt fetched by pipeline/fetch_debt_by_year.py. Amounts are whole currency units. State rows before 2017 are Census summary tables; the page builder adds 2017–2024 from places/<state>.json (Census time series GS00LOCALFIN), the same figures as the state clocks. Country points with kind country are that clock's own official series. kind imf is IMF general government gross debt (GGXWDG_NGDP times NGDPD) and is not the country clock when that clock uses a different measure.",
        "fetched": __import__("clocktime").chicago_today().isoformat(),
        "places": places_out,
        "skipped": skipped,
    }
    json.dump(doc, open(OUT, "w"), indent=1)
    open(OUT, "a").write("\n")
    flags = json.load(open(FLAGS)) if os.path.exists(FLAGS) else {}
    flags["debt_by_year_not_published"] = skipped
    json.dump(flags, open(FLAGS, "w"), indent=1)
    open(FLAGS, "a").write("\n")
    print("wrote", OUT, "places", len(places_out), "skipped", [s["slug"] for s in skipped])


if __name__ == "__main__":
    main()
