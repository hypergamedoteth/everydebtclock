"""Official history series for the milestone, president, per-person, and interest pages.

Debt amounts come only from Treasury Fiscal Data. Population figures come only from
Census files. Nothing here fills a missing year with an estimate.

fetch.py calls build_history() on every refresh and validate_history() before the
numbers are allowed into the cache. `python3 pipeline/series.py` writes the cache
once, the same file fetch.py refreshes.
"""
import csv, datetime as dt, io, json, os, re, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "cache")
FD = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

DTP_URL = "https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/debt-to-the-penny"
DO_URL = "https://fiscaldata.treasury.gov/datasets/historical-debt-outstanding/historical-debt-outstanding"
INT_URL = "https://fiscaldata.treasury.gov/datasets/interest-expense-debt-outstanding/interest-expense"
MTS_URL = "https://fiscaldata.treasury.gov/datasets/monthly-treasury-statement/receipts-of-the-u-s-government"
DTS_URL = "https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/deposits-and-withdrawals-of-operating-cash"

# July 1 resident population. Each block is one Census publication. They are not one revised vintage,
# and the page says so. A year is taken from the newest block that publishes it.
POP_SOURCES = [
    {
        "id": "historical-1900-1999",
        "name": "Census Bureau, Historical National Population Estimates, July 1, 1900–1999",
        "url": "https://www2.census.gov/programs-surveys/popest/tables/1900-1980/national/totals/popclockest.txt",
        "page": "https://www.census.gov/data/tables/time-series/demo/popest/pre-1980-national.html",
        "years": (1900, 1999),
    },
    {
        "id": "intercensal-2000-2010",
        "name": "Census Bureau, 2000–2010 national intercensal estimates, July 1",
        "url": "https://www2.census.gov/programs-surveys/popest/datasets/2000-2010/intercensal/national/us-est00int-tot.csv",
        "page": "https://www.census.gov/data/tables/time-series/demo/popest/intercensal-2000-2010-national.html",
        "years": (2000, 2010),
    },
    {
        "id": "vintage-2020",
        "name": "Census Bureau, Vintage 2020 national population estimates, July 1",
        "url": "https://www2.census.gov/programs-surveys/popest/datasets/2010-2020/national/totals/nst-est2020-alldata.csv",
        "page": "https://www.census.gov/data/tables/time-series/demo/popest/2010s-national-total.html",
        "years": (2011, 2019),
    },
    {
        "id": "vintage-2025",
        "name": "Census Bureau, Vintage 2025 national population estimates, July 1",
        "url": "https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/state/totals/NST-EST2025-ALLDATA.csv",
        "page": "https://www.census.gov/data/tables/time-series/demo/popest/2020s-national-total.html",
        "years": (2020, 2025),
    },
]

# Constitutional term dates. March 4 through 1933; January 20 from 1937 (20th Amendment).
# A term that ended early uses that calendar date. The debt on the date is looked up, never typed in.
# n is the term count for that person, including a remainder term.
TERMS = [
    ("George Washington", 1, "1789-04-30", "1793-03-04"),
    ("George Washington", 2, "1793-03-04", "1797-03-04"),
    ("John Adams", 1, "1797-03-04", "1801-03-04"),
    ("Thomas Jefferson", 1, "1801-03-04", "1805-03-04"),
    ("Thomas Jefferson", 2, "1805-03-04", "1809-03-04"),
    ("James Madison", 1, "1809-03-04", "1813-03-04"),
    ("James Madison", 2, "1813-03-04", "1817-03-04"),
    ("James Monroe", 1, "1817-03-04", "1821-03-04"),
    ("James Monroe", 2, "1821-03-04", "1825-03-04"),
    ("John Quincy Adams", 1, "1825-03-04", "1829-03-04"),
    ("Andrew Jackson", 1, "1829-03-04", "1833-03-04"),
    ("Andrew Jackson", 2, "1833-03-04", "1837-03-04"),
    ("Martin Van Buren", 1, "1837-03-04", "1841-03-04"),
    ("William Henry Harrison", 1, "1841-03-04", "1841-04-04"),
    ("John Tyler", 1, "1841-04-04", "1845-03-04"),
    ("James K. Polk", 1, "1845-03-04", "1849-03-04"),
    ("Zachary Taylor", 1, "1849-03-04", "1850-07-09"),
    ("Millard Fillmore", 1, "1850-07-09", "1853-03-04"),
    ("Franklin Pierce", 1, "1853-03-04", "1857-03-04"),
    ("James Buchanan", 1, "1857-03-04", "1861-03-04"),
    ("Abraham Lincoln", 1, "1861-03-04", "1865-03-04"),
    ("Abraham Lincoln", 2, "1865-03-04", "1865-04-15"),
    ("Andrew Johnson", 1, "1865-04-15", "1869-03-04"),
    ("Ulysses S. Grant", 1, "1869-03-04", "1873-03-04"),
    ("Ulysses S. Grant", 2, "1873-03-04", "1877-03-04"),
    ("Rutherford B. Hayes", 1, "1877-03-04", "1881-03-04"),
    ("James A. Garfield", 1, "1881-03-04", "1881-09-19"),
    ("Chester A. Arthur", 1, "1881-09-19", "1885-03-04"),
    ("Grover Cleveland", 1, "1885-03-04", "1889-03-04"),
    ("Benjamin Harrison", 1, "1889-03-04", "1893-03-04"),
    ("Grover Cleveland", 2, "1893-03-04", "1897-03-04"),
    ("William McKinley", 1, "1897-03-04", "1901-03-04"),
    ("William McKinley", 2, "1901-03-04", "1901-09-14"),
    ("Theodore Roosevelt", 1, "1901-09-14", "1905-03-04"),
    ("Theodore Roosevelt", 2, "1905-03-04", "1909-03-04"),
    ("William Howard Taft", 1, "1909-03-04", "1913-03-04"),
    ("Woodrow Wilson", 1, "1913-03-04", "1917-03-04"),
    ("Woodrow Wilson", 2, "1917-03-04", "1921-03-04"),
    ("Warren G. Harding", 1, "1921-03-04", "1923-08-02"),
    ("Calvin Coolidge", 1, "1923-08-02", "1925-03-04"),
    ("Calvin Coolidge", 2, "1925-03-04", "1929-03-04"),
    ("Herbert Hoover", 1, "1929-03-04", "1933-03-04"),
    ("Franklin D. Roosevelt", 1, "1933-03-04", "1937-01-20"),
    ("Franklin D. Roosevelt", 2, "1937-01-20", "1941-01-20"),
    ("Franklin D. Roosevelt", 3, "1941-01-20", "1945-01-20"),
    ("Franklin D. Roosevelt", 4, "1945-01-20", "1945-04-12"),
    ("Harry S. Truman", 1, "1945-04-12", "1949-01-20"),
    ("Harry S. Truman", 2, "1949-01-20", "1953-01-20"),
    ("Dwight D. Eisenhower", 1, "1953-01-20", "1957-01-20"),
    ("Dwight D. Eisenhower", 2, "1957-01-20", "1961-01-20"),
    ("John F. Kennedy", 1, "1961-01-20", "1963-11-22"),
    ("Lyndon B. Johnson", 1, "1963-11-22", "1965-01-20"),
    ("Lyndon B. Johnson", 2, "1965-01-20", "1969-01-20"),
    ("Richard Nixon", 1, "1969-01-20", "1973-01-20"),
    ("Richard Nixon", 2, "1973-01-20", "1974-08-09"),
    ("Gerald Ford", 1, "1974-08-09", "1977-01-20"),
    ("Jimmy Carter", 1, "1977-01-20", "1981-01-20"),
    ("Ronald Reagan", 1, "1981-01-20", "1985-01-20"),
    ("Ronald Reagan", 2, "1985-01-20", "1989-01-20"),
    ("George H. W. Bush", 1, "1989-01-20", "1993-01-20"),
    ("Bill Clinton", 1, "1993-01-20", "1997-01-20"),
    ("Bill Clinton", 2, "1997-01-20", "2001-01-20"),
    ("George W. Bush", 1, "2001-01-20", "2005-01-20"),
    ("George W. Bush", 2, "2005-01-20", "2009-01-20"),
    ("Barack Obama", 1, "2009-01-20", "2013-01-20"),
    ("Barack Obama", 2, "2013-01-20", "2017-01-20"),
    ("Donald Trump", 1, "2017-01-20", "2021-01-20"),
    ("Joe Biden", 1, "2021-01-20", "2025-01-20"),
    ("Donald Trump", 2, "2025-01-20", None),
]


def term_boundary_dates():
    dates = []
    for name, n, start, end in TERMS:
        dates.append(start)
        if end:
            dates.append(end)
    # unique, stable
    return sorted(set(dates))


def _get(url, timeout=60):
    last = None
    for i in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json,text/plain,*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def _fd(endpoint, full=False, **params):
    q = urllib.parse.urlencode(params, safe=":,()")
    j = json.loads(_get(f"{FD}/{endpoint}?{q}").decode())
    data = j["data"]
    if full:
        pages = j["meta"]["total-pages"]
        for pg in range(2, pages + 1):
            data += json.loads(_get(f"{FD}/{endpoint}?{q}&page%5Bnumber%5D={pg}").decode())["data"]
    return data


def _on_or_before(series, day):
    """Last (date, amount) with date <= day. series is sorted ascending."""
    best = None
    for d, amt in series:
        if d <= day:
            best = (d, amt)
        else:
            break
    return best


def _crossings(series):
    """First close at or above each whole trillion, only when the previous close was below it."""
    if len(series) < 2:
        raise ValueError("Debt to the Penny series is too short")
    start_d, start_a = series[0]
    out = []
    # The series opens above $4 trillion. Thresholds the first row already clears are not crossings.
    n = int(start_a // 10**12) + 1
    idx = 0
    last = series[-1][1]
    while n * 10**12 <= last + 1:
        thr = n * 10**12
        while idx < len(series) and series[idx][1] < thr:
            idx += 1
        if idx >= len(series) or idx == 0:
            break
        d, amt = series[idx]
        pd, pamt = series[idx - 1]
        if not (pamt < thr <= amt) or not (pd < d):
            raise ValueError(f"${n}T crossing is not a step up: {pd} {pamt} -> {d} {amt}")
        if d == start_d:
            raise ValueError(f"${n}T uses the first row of Debt to the Penny, so it is not an observed crossing")
        out.append({
            "trillion": n,
            "date": d,
            "amount": amt,
            "prior_date": pd,
            "prior_amount": pamt,
        })
        n += 1
    return {"date": start_d, "amount": start_a}, out


def _interest_expense(rows):
    """Sum every line in the dataset, matching the interest_gross clock. September FYTD is a full year."""
    by = {}
    for r in rows:
        fy = int(r["record_fiscal_year"])
        d = r["record_date"]
        b = by.setdefault(fy, {}).setdefault(d, {"month": 0.0, "fytd": 0.0, "n": 0})
        b["month"] += float(r["month_expense_amt"] or 0)
        b["fytd"] += float(r["fytd_expense_amt"] or 0)
        b["n"] += 1
    out = []
    for fy in sorted(by):
        days = sorted(by[fy])
        month_sum = sum(by[fy][d]["month"] for d in days)
        last = days[-1]
        fytd = by[fy][last]["fytd"]
        complete = last[5:7] == "09"
        out.append({
            "fy": fy,
            "date": last,
            "amount": fytd if complete else fytd,
            "month_sum": month_sum,
            "complete": complete,
            "months": len(days),
        })
    return out


def _net_interest(rows):
    """MTS Table 9 line 320, Net Interest. September FYTD is the fiscal-year total; the newest month is the current pace."""
    parsed = []
    for r in rows:
        amt = r.get("current_fytd_rcpt_outly_amt")
        if amt in (None, "", "null"):
            continue
        parsed.append({"fy": int(r["record_fiscal_year"]), "date": r["record_date"], "amount": float(amt)})
    if not parsed:
        raise ValueError("MTS net interest returned no amounts")
    by = {}
    for row in parsed:
        if row["date"][5:7] != "09":
            continue
        by[row["fy"]] = row
    latest = max(parsed, key=lambda r: r["date"])
    return [by[y] for y in sorted(by)], latest


def _pop_historical(text):
    found = {}
    for m in re.finditer(r"July 1,\s+(\d{4})\s+([\d,]+)", text):
        found[int(m.group(1))] = int(m.group(2).replace(",", ""))
    return found


def _pop_intercensal(text):
    found = {}
    for row in csv.DictReader(io.StringIO(text)):
        if row.get("MONTH") == "7" and row.get("YEAR") and row.get("TOT_POP"):
            found[int(row["YEAR"])] = int(row["TOT_POP"])
    return found


def _pop_vintage(text, year_from, year_to):
    rows = list(csv.DictReader(io.StringIO(text)))
    us = next(r for r in rows if r.get("NAME") == "United States")
    found = {}
    for y in range(year_from, year_to + 1):
        key = f"POPESTIMATE{y}"
        if us.get(key):
            found[y] = int(us[key])
    return found


def _population(get_text):
    blocks = []
    by_year = {}
    for src in POP_SOURCES:
        raw = get_text(src["url"])
        text = raw.decode("latin-1") if isinstance(raw, (bytes, bytearray)) else raw
        a, b = src["years"]
        if src["id"] == "historical-1900-1999":
            found = _pop_historical(text)
        elif src["id"] == "intercensal-2000-2010":
            found = _pop_intercensal(text)
        else:
            found = _pop_vintage(text, a, b)
        years = {y: found[y] for y in range(a, b + 1) if y in found}
        missing = [y for y in range(a, b + 1) if y not in years]
        if missing:
            raise ValueError(f"{src['id']} missing July 1 population for {missing[:8]}")
        blocks.append({"id": src["id"], "name": src["name"], "url": src["url"], "page": src["page"], "from": a, "to": b})
        for y, pop in years.items():
            by_year[y] = {"year": y, "population": pop, "series": src["id"], "source_name": src["name"], "source_url": src["page"]}
    rows = [by_year[y] for y in sorted(by_year)]
    return blocks, rows


def build_history(fd=None, get_bytes=None):
    """Pull the four series. fd(endpoint, full=False, **params) and get_bytes(url)->bytes default to this file's client."""
    fd = fd or _fd
    get_bytes = get_bytes or _get
    debt = fd("v2/accounting/od/debt_to_penny", full=True, sort="record_date", **{"page[size]": 10000},
              fields="record_date,tot_pub_debt_out_amt")
    series = [(r["record_date"], float(r["tot_pub_debt_out_amt"])) for r in debt]
    series.sort()
    if len(series) < 8000:
        raise ValueError(f"Debt to the Penny returned {len(series)} rows; expected the full history")
    start, crossings = _crossings(series)
    # One lookup per term boundary on or after the daily series begins. Earlier dates use Historical Debt Outstanding.
    boundaries = [d for d in term_boundary_dates() if d >= start["date"]]
    on_or_before = {}
    for day in boundaries:
        hit = _on_or_before(series, day)
        if not hit:
            raise ValueError(f"no Debt to the Penny row on or before {day}")
        on_or_before[day] = {"date": hit[0], "amount": hit[1]}
    ie = fd("v2/accounting/od/interest_expense", full=True, sort="record_date", **{"page[size]": 5000},
            fields="record_date,record_fiscal_year,month_expense_amt,fytd_expense_amt")
    mts = fd("v1/accounting/mts/mts_table_9", full=True, sort="record_date",
             filter="line_code_nbr:eq:320", **{"page[size]": 500},
             fields="record_date,current_fytd_rcpt_outly_amt,record_fiscal_year,line_code_nbr,classification_desc")
    pop_sources, population = _population(get_bytes)
    net_by_fy, net_latest = _net_interest(mts)
    return {
        "series_start": start,
        "series_end": {"date": series[-1][0], "amount": series[-1][1]},
        "crossings": crossings,
        "on_or_before": on_or_before,
        "interest_expense_by_fy": _interest_expense(ie),
        "net_interest_by_fy": net_by_fy,
        "net_interest_latest": net_latest,
        "population_sources": pop_sources,
        "population_by_year": population,
        "sources": {"debt_to_penny": DTP_URL, "debt_outstanding": DO_URL, "interest_expense": INT_URL,
                    "mts_net_interest": MTS_URL, "dts_interest_paid": DTS_URL},
    }


def _chain_ok():
    for a, b in zip(TERMS, TERMS[1:]):
        if a[3] != b[2]:
            raise ValueError(f"term dates do not meet: {a[0]} ends {a[3]}, {b[0]} starts {b[2]}")
    if TERMS[-1][3] is not None:
        raise ValueError("the current term needs an open end date")


def validate_history(h, debt_base=None, debt_as_of=None, population_base=None):
    """Raise if a series contradicts itself or the clock's official debt and Census base."""
    _chain_ok()
    start, end = h["series_start"], h["series_end"]
    if start["date"] != "1993-04-01":
        raise ValueError(f"Debt to the Penny no longer starts on 1993-04-01 ({start['date']})")
    if not (4e12 < start["amount"] < 5e12):
        raise ValueError("Debt to the Penny no longer opens between $4T and $5T; milestone rules need another look")
    xs = h["crossings"]
    if not xs or xs[0]["trillion"] != 5:
        raise ValueError("first observed trillion crossing is not $5T")
    prev_n, prev_d = 4, start["date"]
    for c in xs:
        if c["trillion"] != prev_n + 1:
            raise ValueError(f"trillion sequence skipped at {c['trillion']}")
        if not (c["prior_date"] < c["date"] and c["prior_amount"] < c["trillion"] * 10**12 <= c["amount"]):
            raise ValueError(f"bad crossing {c}")
        if c["date"] <= prev_d:
            raise ValueError("crossing dates are not increasing")
        prev_n, prev_d = c["trillion"], c["date"]
    if xs[-1]["amount"] > end["amount"] + 0.01:
        raise ValueError("a crossing is after the latest Debt to the Penny row")
    top = int(end["amount"] // 10**12)
    if xs[-1]["trillion"] != top:
        raise ValueError(f"latest debt is in the ${top}T range but the last stored crossing is ${xs[-1]['trillion']}T")
    if any(c["trillion"] > top for c in xs):
        raise ValueError("stored a crossing above the latest debt")
    if debt_base is not None and abs(end["amount"] - float(debt_base)) > 0.02:
        raise ValueError(f"history end {end['amount']} != debt clock base {debt_base}")
    if debt_as_of is not None and end["date"] != debt_as_of:
        raise ValueError(f"history end date {end['date']} != debt clock {debt_as_of}")
    # Interest: a finished fiscal year, the sum of the months equals the September year-to-date.
    finished = [r for r in h["interest_expense_by_fy"] if r["complete"]]
    if len(finished) < 10:
        raise ValueError("interest expense is missing finished fiscal years")
    full_years = [r for r in finished if r["months"] == 12]
    if len(full_years) < 10:
        raise ValueError("interest expense is missing 12-month fiscal years")
    for r in full_years:
        # September's year-to-date is the fiscal-year total. It matches the sum of the months only when all 12 are in the file.
        if abs(r["month_sum"] - r["amount"]) > 1.0:
            raise ValueError(f"FY{r['fy']} interest expense months {r['month_sum']} != September FYTD {r['amount']}")
    # The file opens in the middle of a year, so that first September total has no 12 month rows. Later years must.
    for r in finished:
        if r["fy"] != finished[0]["fy"] and r["months"] != 12:
            raise ValueError(f"FY{r['fy']} interest expense has {r['months']} months")
    nets = h["net_interest_by_fy"]
    if not nets or nets[-1]["fy"] < 2024:
        raise ValueError("MTS net interest has no recent September total")
    latest = h.get("net_interest_latest") or {}
    if latest.get("date", "") < nets[-1]["date"]:
        raise ValueError("latest MTS net interest is older than the last full fiscal year")
    for a, b in zip(nets, nets[1:]):
        if b["fy"] != a["fy"] + 1:
            raise ValueError(f"MTS net interest skips FY{a['fy'] + 1}")
    pops = h["population_by_year"]
    years = [p["year"] for p in pops]
    if years != list(range(years[0], years[-1] + 1)):
        raise ValueError("population years have a gap")
    if years[0] != 1900:
        raise ValueError("population series does not start in 1900")
    for p, q in zip(pops, pops[1:]):
        if q["population"] < p["population"] * 0.98:
            raise ValueError(f"Census population fell more than 2% in {q['year']}")
    y2025 = next((p for p in pops if p["year"] == 2025), None)
    if not y2025:
        raise ValueError("no Census July 1, 2025 population")
    if population_base is not None and int(y2025["population"]) != int(population_base):
        raise ValueError(f"July 1, 2025 population {y2025['population']} != clock base {population_base}")
    return True


def validation_rows(h, debt_base, debt_as_of, population_base, net_interest_fy2026=None):
    """Rows for validation_log.csv. error_pct is 0 when the new extract matches the clock."""
    end = h["series_end"]
    err_debt = (end["amount"] - float(debt_base)) / float(debt_base) * 100 if debt_base else None
    y2025 = next(p["population"] for p in h["population_by_year"] if p["year"] == 2025)
    err_pop = (y2025 - float(population_base)) / float(population_base) * 100 if population_base else None
    worst = 0.0
    for r in h["interest_expense_by_fy"]:
        if r["complete"] and r["months"] == 12 and r["amount"]:
            worst = max(worst, abs(r["month_sum"] - r["amount"]) / abs(r["amount"]) * 100)
    rows = [
        {"ticker": "history_debt", "from": end["date"], "to": debt_as_of or end["date"],
         "projected": round(end["amount"], 2), "official": round(float(debt_base), 2) if debt_base is not None else None,
         "error_pct": round(err_debt, 6) if err_debt is not None else None, "mode": "history_vs_debt_total", "thr": 0.001},
        {"ticker": "history_population_2025", "from": "2025-07-01", "to": "2025-07-01",
         "projected": y2025, "official": int(population_base) if population_base is not None else None,
         "error_pct": round(err_pop, 6) if err_pop is not None else None, "mode": "census_vs_clock", "thr": 0.001},
        {"ticker": "interest_expense_fy", "from": str(h["interest_expense_by_fy"][0]["fy"]),
         "to": str(h["interest_expense_by_fy"][-1]["fy"]),
         "projected": round(worst, 6), "official": 0, "error_pct": round(worst, 6),
         "mode": "fytd_vs_sum_of_months", "thr": 0.001},
    ]
    if net_interest_fy2026 is not None:
        m = next((r for r in h["net_interest_by_fy"] if r["fy"] == 2026), None)
        if m:
            err = (m["amount"] - float(net_interest_fy2026)) / float(net_interest_fy2026) * 100
            rows.append({"ticker": "net_interest_fy2026", "from": "FY2026", "to": m["date"],
                         "projected": round(m["amount"], 2), "official": round(float(net_interest_fy2026), 2),
                         "error_pct": round(err, 6), "mode": "mts_vs_stored_fy", "thr": 0.001})
    return rows


def main():
    os.makedirs(CACHE, exist_ok=True)
    h = build_history()
    # Compare with the clock file when it is present, so a hand run fails on a mismatch too.
    debt_base = debt_as_of = pop_base = None
    data_p = os.path.join(ROOT, "data", "data.json")
    if os.path.exists(data_p):
        d = json.load(open(data_p))
        td = d.get("tickers", {}).get("debt_total") or {}
        pop = d.get("tickers", {}).get("population") or {}
        if td.get("status") == "ok":
            debt_base, debt_as_of = td.get("base"), td.get("as_of")
        if pop.get("status") == "ok":
            pop_base = pop.get("base")
    validate_history(h, debt_base, debt_as_of, pop_base)
    json.dump({"fetched": time.time(), "data": h}, open(os.path.join(CACHE, "history_pages.json"), "w"))
    end = h["series_end"]
    print(f"history: debt {end['date']} {end['amount']:.2f}; crossings {h['crossings'][0]['trillion']}–{h['crossings'][-1]['trillion']}; "
          f"population {h['population_by_year'][0]['year']}–{h['population_by_year'][-1]['year']}; "
          f"net interest FY{h['net_interest_by_fy'][0]['fy']}–FY{h['net_interest_by_fy'][-1]['fy']}")


if __name__ == "__main__":
    main()
