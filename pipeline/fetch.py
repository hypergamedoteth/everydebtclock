#!/usr/bin/env python3
"""Daily data pipeline for the debt clock prototype.

Pulls official figures (no API keys), computes base + per-second rate for every
ticker, validates yesterday's projections against new official numbers, and
writes data/data.json + data/validation_log.csv.

Rule: never invent a number. If a source fails and there is no cached official
value, the ticker is written with status "unavailable".
"""
import json, os, sys, time, csv, math, datetime as dt, urllib.request, urllib.parse, io
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(ROOT, "cache")
os.makedirs(DATA, exist_ok=True); os.makedirs(CACHE, exist_ok=True)
ET = ZoneInfo("America/New_York")
FD = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
YEAR_S = 365.25 * 86400
NOW = time.time()
errors = {}

def get(url, tries=3, timeout=25, headers=None, binary=False):
    last = None
    for i in range(tries):
        try:
            h = {"User-Agent": UA, "Accept": "application/json,*/*"}
            h.update(headers or {})
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
                b = r.read()
                return b if binary else b.decode("utf-8")
        except Exception as e:
            last = e; time.sleep(2 * (i + 1))
    raise RuntimeError(f"{url}: {last}")

def fd(endpoint, full=False, **params):
    """Fiscal Data query. full=True pages through everything (never silently truncate a set we sum)."""
    q = urllib.parse.urlencode(params, safe=":,()")
    j = json.loads(get(f"{FD}/{endpoint}?{q}"))
    data = j["data"]
    if full:
        pages = j["meta"]["total-pages"]
        for pg in range(2, pages + 1):
            data += json.loads(get(f"{FD}/{endpoint}?{q}&page%5Bnumber%5D={pg}"))["data"]
    return data

def cached(name, fn):
    """Run fn(); on success cache result, on failure fall back to cache (flagged stale)."""
    p = os.path.join(CACHE, name + ".json")
    try:
        v = fn()
        json.dump({"fetched": NOW, "data": v}, open(p, "w"))
        return v, False
    except Exception as e:
        errors[name] = str(e)[:300]
        if os.path.exists(p):
            return json.load(open(p))["data"], True
        return None, True

def eod_et(datestr):
    """End of an ET calendar day (official 'as of close of business')."""
    d = dt.date.fromisoformat(datestr)
    return dt.datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=ET).timestamp()

def fy_bounds(ts):
    d = dt.datetime.fromtimestamp(ts, ET)
    fy = d.year + 1 if d.month >= 10 else d.year
    start = dt.datetime(fy - 1, 10, 1, tzinfo=ET).timestamp()
    end = dt.datetime(fy, 10, 1, tzinfo=ET).timestamp()
    return fy, start, end

def ols_slope(xs, ys):
    n = len(xs); mx = sum(xs) / n; my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx

def ols_calc(labels, xs, ys, window):
    """Record exactly which official points a regression rate came from (shown in the 'show the math' modal)."""
    c = {"type": "ols", "window": window, "n": len(xs), "slope": ols_slope(xs, ys),
         "first": [labels[0], ys[0]], "last": [labels[-1], ys[-1]]}
    if len(xs) <= 16: c["points"] = [[l, y] for l, y in zip(labels, ys)]
    return c

# ---------------------------------------------------------------- sources
def src_debt():
    rows = fd("v2/accounting/od/debt_to_penny", sort="-record_date", **{"page[size]": 160},
              fields="record_date,tot_pub_debt_out_amt,debt_held_public_amt,intragov_hold_amt")
    y1 = (dt.date.fromisoformat(rows[0]["record_date"]) - dt.timedelta(days=365)).isoformat()
    old = fd("v2/accounting/od/debt_to_penny", filter=f"record_date:lte:{y1}", sort="-record_date", **{"page[size]": 1},
             fields="record_date,tot_pub_debt_out_amt,debt_held_public_amt,intragov_hold_amt")
    return {"rows": rows, "year_ago": old[0]}

def src_mts9():
    # last 13 months of MTS Table 9 (receipts by source, outlays by function)
    dates = fd("v1/accounting/mts/mts_table_9", sort="-record_date", fields="record_date",
               **{"page[size]": 600})
    uniq = sorted({r["record_date"] for r in dates}, reverse=True)[:13]
    out = {}
    for d in uniq:
        out[d] = fd("v1/accounting/mts/mts_table_9", full=True, filter=f"record_date:eq:{d}", **{"page[size]": 100},
                    fields="record_date,classification_desc,line_code_nbr,current_month_rcpt_outly_amt,current_fytd_rcpt_outly_amt,prior_fytd_rcpt_outly_amt,record_fiscal_year")
    return out

def src_interest():
    since = (dt.date.fromtimestamp(NOW) - dt.timedelta(days=430)).isoformat()
    rows = fd("v2/accounting/od/interest_expense", full=True, filter=f"record_date:gte:{since}", sort="-record_date", **{"page[size]": 2000},
              fields="record_date,expense_catg_desc,expense_group_desc,expense_type_desc,src_line_nbr,month_expense_amt,fytd_expense_amt,record_fiscal_year")
    return rows

def src_avg_rate():
    return fd("v2/accounting/od/avg_interest_rates", sort="-record_date", **{"page[size]": 30},
              fields="record_date,security_type_desc,security_desc,avg_interest_rate_amt")

def src_dts():
    return fd("v1/accounting/dts/deposits_withdrawals_operating_cash", sort="-record_date", **{"page[size]": 400},
              fields="record_date,transaction_type,transaction_catg,transaction_fytd_amt")

def src_gdp():
    u = ("https://api.db.nomics.world/v22/series/BEA/NIPA-T10105/A191RC-Q?observations=1")
    s = json.loads(get(u))["series"]["docs"][0]
    return {"period": s["period"][-6:], "value": s["value"][-6:]}

def src_pop():
    url = "https://www.census.gov/popclock/data/population.php/us"
    try:
        j = json.loads(get(url, headers={"Referer": "https://www.census.gov/popclock/"}, tries=2, timeout=20))
    except Exception:
        import subprocess  # census.gov's CDN is picky about clients; curl usually gets through
        j = None
        for _ in range(4):
            r = subprocess.run(["curl", "-s", "-m", "20", "-H", "Accept: application/json", "-H", "Referer: https://www.census.gov/popclock/",
                                "-A", UA, url], capture_output=True, text=True)
            if r.stdout.strip().startswith("{"):
                j = json.loads(r.stdout); break
            time.sleep(3)
        if j is None: raise RuntimeError("census popclock unreachable")
    return j["us"] if "us" in j else j

def src_omb():
    import openpyxl
    out = {}
    for key, tab in (("t12", "2-2"), ("t71", "8-1")):
        b = get(f"https://www.govinfo.gov/content/pkg/BUDGET-2027-TAB/xls/BUDGET-2027-TAB-{tab}.xlsx", binary=True, timeout=40)
        ws = openpyxl.load_workbook(io.BytesIO(b), data_only=True).active
        rows = {}
        for r in ws.iter_rows(values_only=True):
            y = str(r[0]).strip() if r[0] is not None else ""
            if y.isdigit():
                rows[y] = [c if isinstance(c, (int, float)) else None for c in r]
        out[key] = rows
    return out

# ---------------------------------------------------------------- build
T = {}          # tickers
validation_rows = []
META = {"generated_epoch": NOW, "generated_iso": dt.datetime.fromtimestamp(NOW, ET).isoformat()}

def add(slug, **kw):
    kw.setdefault("status", "ok"); kw["slug"] = slug
    if "calc" not in kw and kw.get("fixed"):
        kw["calc"] = {"type": "fixed", "base_src": [kw.get("as_of"), kw.get("base"), kw.get("source")]}
    T[slug] = kw

def unavailable(slug, label, group, source, why):
    add(slug, label=label, group=group, status="unavailable", source=source, note=why, kind="usd")

DTP_URL = "https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/debt-to-the-penny"
MTS_URL = "https://fiscaldata.treasury.gov/datasets/monthly-treasury-statement/receipts-of-the-u-s-government"
INT_URL = "https://fiscaldata.treasury.gov/datasets/interest-expense-debt-outstanding/interest-expense"
AIR_URL = "https://fiscaldata.treasury.gov/datasets/average-interest-rates-treasury-securities/average-interest-rates-on-u-s-treasury-securities"
DTS_URL = "https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/"
BEA_URL = "https://apps.bea.gov/iTable/?reqid=19&step=2&isuri=1&categories=survey#eyJhcHBpZCI6MTksInN0ZXBzIjpbMSwyLDNdLCJkYXRhIjpbWyJjYXRlZ29yaWVzIiwiU3VydmV5Il0sWyJOSVBBX1RhYmxlX0xpc3QiLCI1Il1dfQ=="
POP_URL = "https://www.census.gov/popclock/"
HH_URL = "https://www2.census.gov/programs-surveys/demo/tables/families/time-series/households/hh1.xls"
IRS_URL = "https://www.irs.gov/statistics/soi-tax-stats-numbers-of-returns-filed-by-type-of-return-irs-data-book-table-1-2"
OMB_URL = "https://www.govinfo.gov/app/collection/budget/2027/BUDGET-2027-TAB"

# ---- people (denominators)
# Base: Census Vintage 2025 national estimate (July 1, 2025). Rate: Census's own stated current growth (population clock
# per-second rate); if the clock has never been reachable, fall back to V2025's latest official annual change.
NST_URL = "https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/state/totals/NST-EST2025-ALLDATA.csv"
NST_PAGE = "https://www.census.gov/data/tables/time-series/demo/popest/2020s-national-total.html"
def src_v2025():
    rows = list(csv.DictReader(io.StringIO(get(NST_URL, binary=True).decode("latin-1"))))
    us = next(r for r in rows if r["NAME"] == "United States")
    return {k: int(us[k]) for k in ("POPESTIMATE2024", "POPESTIMATE2025", "NPOPCHG_2025", "BIRTHS2025", "DEATHS2025", "INTERNATIONALMIG2025")}
v25, v25_stale = cached("census_v2025", src_v2025)
pop, pop_stale = cached("census_pop", src_pop)
if v25:
    t0p = dt.datetime(2025, 7, 1, tzinfo=ET).timestamp()
    annual = v25["NPOPCHG_2025"] / YEAR_S
    if pop:
        prate, rsrc = float(pop["population_rate"]), f"Census population clock's stated rate ({float(pop['population_rate']):.6f}/s ≈ {float(pop['population_rate'])*YEAR_S:,.0f}/yr{', cached' if pop_stale else ''})"
    else:
        prate, rsrc = annual, f"V2025 Jul 2024→Jul 2025 change ({v25['NPOPCHG_2025']:,}/yr)"
    add("population", label="US population", group="people", kind="count", base=float(v25["POPESTIMATE2025"]), t0=t0p, rate=prate,
        as_of="2025-07-01", source=NST_PAGE, source_name="U.S. Census Bureau, Vintage 2025 population estimates (NST-EST2025)",
        method=(f"Official resident population on July 1, 2025 (Vintage 2025): {v25['POPESTIMATE2025']:,}. Projected forward at {rsrc}. "
                f"For reference, V2025's own Jul 2024→Jul 2025 change was {v25['NPOPCHG_2025']:,} (net international migration {v25['INTERNATIONALMIG2025']:,}); "
                f"Census's current clock assumes slower growth, mainly lower net migration. The live clock level is used only as a cross-check."),
        stale=v25_stale, calc={"type": "anchor_rate", "base_src": ["2025-07-01", v25["POPESTIMATE2025"], NST_URL], "rate_src": rsrc,
                               "alt_rate_v2025_annual": v25["NPOPCHG_2025"]})
    if pop and not pop_stale:   # cross-check vs the live Census clock
        tc = float(pop.get("last_updated") or NOW); ours = v25["POPESTIMATE2025"] + prate * (tc - t0p)
        err = (ours - float(pop["population"])) / float(pop["population"]) * 100
        T["population"]["validation"] = {"last_error_pct": round(err, 4), "threshold_pct": 0.5, "flag": abs(err) > 0.5, "against": "Census population clock (cross-check)"}
        validation_rows.append({"ticker": "population", "from": "2025-07-01", "to": dt.datetime.fromtimestamp(tc, ET).date().isoformat(),
                                "projected": round(ours), "official": float(pop["population"]), "error_pct": round(err, 4), "mode": "popclock_crosscheck"})
elif pop:
    t0 = float(pop.get("last_updated") or NOW)
    add("population", label="US population", group="people", kind="count", base=float(pop["population"]), t0=t0, rate=float(pop["population_rate"]),
        as_of=dt.datetime.fromtimestamp(t0, ET).date().isoformat(), source=POP_URL, source_name="U.S. Census Bureau population clock",
        method="Vintage file unreachable; using the Census population clock directly.", stale=True, calc={"type": "anchor_rate", "base_src": ["clock", float(pop["population"]), POP_URL]})
else:
    unavailable("population", "US population", "people", NST_PAGE, "Census estimates and population clock unreachable, no cache")

HOUSEHOLDS = 134_790_000   # CPS ASEC 2025, Table HH-1 (FRED TTLHH = 134,790 thousand)
TAX_RETURNS = 162_754_810    # IRS Data Book FY2025, Table 1-2: individual income tax returns filed
add("households", label="US households", group="people", kind="count", base=HOUSEHOLDS, rate=0, t0=NOW, as_of="2025",
    source=HH_URL, source_name="Census CPS ASEC 2025, Table HH-1", method="Annual survey figure (134.79M). Updated each December.", fixed=True,
    calc={"type": "fixed", "base_src": ["2025", HOUSEHOLDS, HH_URL]})
add("tax_returns", label="Individual income tax returns filed", group="people", kind="count", base=TAX_RETURNS, rate=0, t0=NOW, as_of="FY2025",
    source=IRS_URL, source_name="IRS Data Book FY2025, Table 1-2",
    method=("162,754,810 individual income tax returns filed in FY2025 (IRS Data Book, Table 1-2). Used as the 'per tax return filed' denominator. "
            "It counts returns, not people: a joint return counts once, and returns with zero tax liability are included."), fixed=True,
    calc={"type": "fixed", "base_src": ["FY2025", TAX_RETURNS, IRS_URL]})

# ---- debt (daily)
THR0 = {"debt_intragov": 0.5}
debt, debt_stale = cached("debt_to_penny", src_debt)
if isinstance(debt, list): debt = {"rows": debt, "year_ago": None}     # pre-Phase-3 cache format
# When the Debt to the Penny rows were actually pulled from Treasury (cache time if this run fell back to cache).
try: META["debt_fetched_epoch"] = NOW if not debt_stale else json.load(open(os.path.join(CACHE, "debt_to_penny.json")))["fetched"]
except Exception: META["debt_fetched_epoch"] = None
if debt:
    year_ago = debt["year_ago"]; rows = sorted(debt["rows"], key=lambda r: r["record_date"])
    latest = rows[-1]; t_latest = eod_et(latest["record_date"])
    for slug, field, label in (("debt_total", "tot_pub_debt_out_amt", "US national debt"),
                               ("debt_public", "debt_held_public_amt", "Debt held by the public"),
                               ("debt_intragov", "intragov_hold_amt", "Intragovernmental debt")):
        win = [r for r in rows if t_latest - eod_et(r["record_date"]) <= 90 * 86400]
        xs = [eod_et(r["record_date"]) for r in win]; ys = [float(r[field]) for r in win]
        rate = ols_slope(xs, ys)
        c = ols_calc([r["record_date"] for r in win], xs, ys, f"trailing 90 days ({win[0]['record_date']} to {win[-1]['record_date']})")
        if year_ago:
          y1v = float(year_ago[field]); c["context_1y"] = {"from": [year_ago["record_date"], y1v], "to": [latest["record_date"], float(latest[field])],
                                                        "rate": (float(latest[field]) - y1v) / (t_latest - eod_et(year_ago["record_date"]))}
        add(slug, label=label, group="debt", kind="usd", base=float(latest[field]), t0=t_latest, rate=rate,
            as_of=latest["record_date"], source=DTP_URL, source_name="Treasury, Debt to the Penny",
            method=f"Starts at Treasury's official figure for {latest['record_date']} (close of business). Rate: 90-day least-squares trend ({len(win)} daily records), the same window for total, public and intragovernmental debt so the parts add up to the total. Re-based every business day.",
            stale=debt_stale, calc=c)
        # backtest: project each of the last 20 records from the previous one using the then-trailing 90d slope
        bt = []
        for i in range(len(rows) - 20, len(rows)):
            prev = rows[i - 1]; tp = eod_et(prev["record_date"])
            w = [r for r in rows[:i] if tp - eod_et(r["record_date"]) <= 90 * 86400]
            if len(w) < 20: continue
            s = ols_slope([eod_et(r["record_date"]) for r in w], [float(r[field]) for r in w])
            tn = eod_et(rows[i]["record_date"])
            proj = float(prev[field]) + s * (tn - tp); off = float(rows[i][field])
            err = (proj - off) / off * 100
            bt.append(err)
            validation_rows.append({"ticker": slug, "from": prev["record_date"], "to": rows[i]["record_date"],
                                    "projected": round(proj, 2), "official": off, "error_pct": round(err, 4), "mode": "backtest"})
        T[slug]["validation"] = {"last_error_pct": round(bt[-1], 4), "mean_abs_error_pct": round(sum(map(abs, bt)) / len(bt), 4),
                                 "n": len(bt), "against": "Debt to the Penny (next business day)",
                                 "threshold_pct": THR0.get(slug, 0.25), "flag": abs(bt[-1]) > THR0.get(slug, 0.25)}
    # identical window → slopes are additive; pin total = public + intragov exactly
    T["debt_total"]["rate"] = T["debt_public"]["rate"] + T["debt_intragov"]["rate"]
    v = T["debt_total"]["validation"]
    T["debt_total"]["method"] += f" Backtested against the next Treasury close over the last {v['n']} business days: average error {v['mean_abs_error_pct']:.3f}%."
else:
    for s, l in (("debt_total", "US national debt"), ("debt_public", "Debt held by the public"), ("debt_intragov", "Intragovernmental debt")):
        unavailable(s, l, "debt", DTP_URL, "Debt to the Penny API unreachable and no cache")

# ---- GDP (quarterly, SAAR)
gdp, gdp_stale = cached("bea_gdp", src_gdp)
if gdp:
    per, val = gdp["period"], [v * 1e6 for v in gdp["value"]]
    def qmid(p):
        y, q = int(p[:4]), int(p[-1]); m = 3 * (q - 1) + 2
        return dt.datetime(y, m, 15, tzinfo=ET).timestamp()
    xs = [qmid(p) for p in per[-4:]]; ys = val[-4:]
    gcalc = ols_calc(per[-4:], xs, ys, "last 4 quarters (mid-quarter anchors)")
    add("gdp", calc=gcalc, label="GDP (annual rate)", group="economy", kind="usd", base=val[-1], t0=qmid(per[-1]), rate=ols_slope(xs, ys),
        as_of=per[-1], source=BEA_URL, source_name="BEA NIPA Table 1.1.5 (via DBnomics mirror)",
        method=f"Nominal GDP, seasonally adjusted annual rate, {per[-1]} = ${val[-1]/1e12:.3f}T. Ticks at the trend of the last 4 quarters, anchored at mid-quarter.",
        stale=gdp_stale)
else:
    unavailable("gdp", "GDP (annual rate)", "economy", BEA_URL, "BEA/DBnomics unreachable and no cache")

# ---- MTS + DTS: FYTD receipts/outlays (budget basis), re-based every business day from the Daily Treasury Statement
mts, mts_stale = cached("mts_table9", src_mts9)
FY, FY_START, FY_END = fy_bounds(NOW)
META.update({"fy": FY, "fy_start_epoch": FY_START, "fy_end_epoch": FY_END})
REV = {  # slug: (label, [line codes])
    "rev_individual": ("Individual income taxes", ["20"]),
    "rev_payroll": ("Payroll / social insurance taxes", ["50", "60", "70"]),
    "rev_corporate": ("Corporate income taxes", ["30"]),
    "rev_customs": ("Customs duties (tariffs)", ["100"]),
    "rev_excise": ("Excise taxes", ["80"]),
    "rev_estate": ("Estate and gift taxes", ["90"]),
    "rev_misc": ("Miscellaneous receipts (incl. Fed earnings)", ["110"]),
}
OUT = {
    "out_socsec": ("Social Security", ["270"]), "out_medicare": ("Medicare", ["250"]),
    "out_health": ("Health (incl. Medicaid)", ["240"]), "out_defense": ("National defense", ["140"]),
    "out_interest": ("Net interest", ["320"]), "out_income": ("Income security", ["260"]),
    "out_veterans": ("Veterans benefits", ["280"]), "out_education": ("Education, training, employment", ["230"]),
    "out_transport": ("Transportation", ["210"]), "out_agri": ("Agriculture", ["190"]),
    "out_intl": ("International affairs", ["150"]), "out_justice": ("Administration of justice", ["290"]),
    "out_science": ("Science, space and technology", ["160"]), "out_nature": ("Natural resources and environment", ["180"]),
    "out_community": ("Community and regional development", ["220"]), "out_govt": ("General government", ["300"]),
    "out_energy": ("Energy", ["170"]), "out_commerce": ("Commerce and housing credit (net)", ["200"]),
    "out_offsets": ("Undistributed offsetting receipts", ["330"]),
}
TOTALS = {"revenue": ("Federal revenue", ["120"]), "spending": ("Federal spending", ["340"])}

def dts_snapshot(on_or_before):
    """DTS FYTD cash totals (dollars) for the last business day <= date."""
    rows = fd("v1/accounting/dts/deposits_withdrawals_operating_cash", filter=f"record_date:lte:{on_or_before}",
              sort="-record_date", **{"page[size]": 250}, fields="record_date,transaction_type,transaction_catg,transaction_fytd_amt")
    d0 = rows[0]["record_date"]; s = {"date": d0}
    for r in rows:
        if r["record_date"] != d0: continue
        c = r["transaction_catg"]; t = r["transaction_type"]; v = float(r["transaction_fytd_amt"] or 0) * 1e6
        if c in (None, "null"): s["dep_total" if t.startswith("Dep") else "wd_total"] = v
        elif "Public Debt Cash Issues" in c and t.startswith("Dep"): s["dep_debt"] = v
        elif "Public Debt Cash Redemp" in c: s["wd_debt"] = v
        elif "Interest on Treasury Securities" in c: s["interest"] = v
    s["receipts"] = s["dep_total"] - s.get("dep_debt", 0)
    s["outlays"] = s["wd_total"] - s.get("wd_debt", 0)
    s["fy"] = fy_bounds(eod_et(d0))[0]
    return s

def src_dts_set():
    today = dt.datetime.fromtimestamp(NOW, ET).date()
    latest = dts_snapshot(today.isoformat())
    tl = dt.date.fromisoformat(latest["date"])
    out = {"latest": latest,
           "d90": dts_snapshot((tl - dt.timedelta(days=90)).isoformat()),
           "fyend_prev": dts_snapshot(f"{latest['fy'] - 1}-09-30"),
           "fyend_prev2": dts_snapshot(f"{latest['fy'] - 2}-09-30")}
    return out

dtsset, dts_stale = cached("dts_set", src_dts_set)
DTS_TABLE_URL = "https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/deposits-and-withdrawals-of-operating-cash"

if mts:
    dates = sorted(mts.keys())
    latest_d = dates[-1]; latest_fy = int(mts[latest_d][0]["record_fiscal_year"])
    def val(d, codes, col):
        return sum(float(r[col]) for r in mts[d] if r["line_code_nbr"] in codes and r[col] not in (None, "null"))
    last12 = dates[-12:]
    cur_fy_months = [d for d in dates if int(mts[d][0]["record_fiscal_year"]) == FY]
    prev_fy_end_d = max([d for d in dates if int(mts[d][0]["record_fiscal_year"]) == FY - 1], default=None)
    base_d = latest_d if latest_fy == FY else None
    # shares used to split the daily totals into sources/functions
    use_cur = base_d and len(cur_fy_months) >= 3
    def amount(codes):  # current FYTD if >=3 months, else trailing 12 months
        return val(base_d, codes, "current_fytd_rcpt_outly_amt") if use_cur else sum(val(d, codes, "current_month_rcpt_outly_amt") for d in last12)
    share_basis = f"FY{FY} to date (MTS through {base_d})" if use_cur else f"trailing 12 months of MTS ({last12[0][:7]} to {last12[-1][:7]})"
    totals = {}
    if dtsset and dtsset["latest"]["fy"] == FY:
        L, P, P2, D90 = dtsset["latest"], dtsset["fyend_prev"], dtsset["fyend_prev2"], dtsset["d90"]
        t_l = eod_et(L["date"]); days90 = (t_l - eod_et(D90["date"]))
        for slug, codes, cash in (("revenue", ["120"], "receipts"), ("spending", ["340"], "outlays")):
            mts_prev_fy = val(prev_fy_end_d, codes, "current_fytd_rcpt_outly_amt") if prev_fy_end_d else None
            ratio = mts_prev_fy / P[cash]                      # budget dollars per cash dollar, last full FY
            flow90 = L[cash] - D90[cash] if D90["fy"] == L["fy"] else L[cash] + (P[cash] - D90[cash])
            if base_d:
                mts_m = val(base_d, codes, "current_fytd_rcpt_outly_amt")
                dm = dts_snapshot(base_d) if not dts_stale else None
                est = mts_m + ratio * (L[cash] - (dm[cash] if dm else 0)); how = f"official MTS FYTD through {base_d} + DTS cash since then × {ratio:.4f}"
            else:
                est = ratio * L[cash]; how = f"DTS FYTD cash through {L['date']} (${L[cash]/1e9:,.1f}B) × {ratio:.4f} budget-to-cash ratio from FY{FY-1}"
            calc = {"type": "dts_ratio", "ratio": ratio, "ratio_src": [f"FY{FY-1} MTS total", mts_prev_fy, f"FY{FY-1} DTS cash", P[cash]],
                    "cash_from": [D90["date"], D90[cash]], "cash_to": [L["date"], L[cash]], "cash_flow_90d": flow90, "seconds": days90,
                    "base_parts": ({"mts_month": base_d, "mts_fytd": mts_m, "dts_cash_at_month_end": (dm[cash] if dm else 0), "dts_cash_latest": L[cash]} if base_d else {"dts_cash_latest": L[cash]})}
            totals[slug] = dict(base=est, t0=t_l, rate=ratio * flow90 / days90, as_of=L["date"], how=how, ratio=ratio, calc=calc,
                                prev=mts_prev_fy, ttm=sum(val(d, codes, "current_month_rcpt_outly_amt") for d in last12))
            # ratio stability backtest: FY-2 ratio applied to FY-1 cash vs the official FY-1 total
            mts_prev2 = sum(float(r["prior_fytd_rcpt_outly_amt"]) for r in mts[prev_fy_end_d] if r["line_code_nbr"] in codes and r.get("prior_fytd_rcpt_outly_amt") not in (None, "null"))
            if mts_prev2 and P2.get(cash):
                proj = mts_prev2 / P2[cash] * P[cash]; err = (proj - mts_prev_fy) / mts_prev_fy * 100
                validation_rows.append({"ticker": slug, "from": f"FY{FY-2} ratio", "to": f"FY{FY-1} total", "projected": round(proj, 2),
                                        "official": mts_prev_fy, "error_pct": round(err, 4), "mode": "dts_ratio_backtest"})
                totals[slug]["ratio_bt"] = round(err, 3)
            META.setdefault("dts_ratio", {})[slug] = {"ratio_prev_fy": ratio, "cash_prev_fy": P[cash], "cash_prev2_fy": P2[cash], "mts_prev_fy": mts_prev_fy, "backtest_err_pct": totals[slug].get("ratio_bt")}
        META["dts_latest"] = L["date"]
    for slug, (label, codes) in TOTALS.items():
        if slug in totals:
            x = totals[slug]
            add(slug, label=label, group="fytd", kind="usd", mode="fytd", base=x["base"], t0=x["t0"], rate=x["rate"], as_of=x["as_of"],
                fy=FY, prev_fy_total=x["prev"], ttm=x["ttm"], source=DTS_TABLE_URL, source_name="Treasury Daily Treasury Statement, calibrated to the Monthly Treasury Statement",
                method=f"FY{FY} to date, budget basis, re-based every business day: {x['how']}. Ticks at the last 90 days' cash pace × the same ratio. FY{FY-1} final (MTS): ${(x['prev'] or 0)/1e9:,.1f}B. Resets to $0 every Oct 1.",
                stale=dts_stale or mts_stale, basis="dts", calc=x["calc"])
        else:   # fallback: MTS only
            fytd = val(base_d, codes, "current_fytd_rcpt_outly_amt") if base_d else 0.0
            ttm = sum(val(d, codes, "current_month_rcpt_outly_amt") for d in last12)
            add(slug, label=label, group="fytd", kind="usd", mode="fytd", base=fytd, t0=eod_et(base_d) if base_d else FY_START, rate=ttm / YEAR_S,
                as_of=base_d or dt.datetime.fromtimestamp(FY_START, ET).date().isoformat(), fy=FY, ttm=ttm,
                prev_fy_total=val(prev_fy_end_d, codes, "current_fytd_rcpt_outly_amt") if prev_fy_end_d else None,
                source=MTS_URL, source_name="Treasury, Monthly Treasury Statement", method="DTS unavailable; MTS-only projection at the trailing 12-month pace.", stale=True, basis="mts")
    def split(group, items, parent):
        P = T[parent]; tot = amount(TOTALS[parent][1])
        for slug, (label, codes) in items.items():
            sh = amount(codes) / tot
            prev = val(prev_fy_end_d, codes, "current_fytd_rcpt_outly_amt") if prev_fy_end_d else None
            add(slug, label=label, group=group, kind="usd", mode="fytd", base=P["base"] * sh, t0=P["t0"], rate=P["rate"] * sh, as_of=P["as_of"],
                fy=FY, prev_fy_total=prev, share=sh, source=MTS_URL, source_name="Treasury MTS Table 9 (share) × daily total",
                method=f"{sh*100:.2f}% of {P['label'].lower()} (its share over {share_basis}), applied to the daily re-based FY{FY} total. FY{FY-1} final: ${(prev or 0)/1e9:,.1f}B.",
                stale=P.get("stale"), lines=codes, calc={"type": "share", "parent": parent, "share": sh, "basis": share_basis, "mts_lines": codes})
    split("revenue", REV, "revenue"); split("spending", OUT, "spending")
    sp, rv = T["spending"], T["revenue"]
    add("deficit", label="Federal deficit", group="fytd", kind="usd", mode="fytd", base=sp["base"] - rv["base"], t0=sp["t0"],
        rate=sp["rate"] - rv["rate"], as_of=sp["as_of"], fy=FY, prev_fy_total=(sp["prev_fy_total"] or 0) - (rv["prev_fy_total"] or 0),
        source=sp["source"], source_name=sp["source_name"], method="Spending minus revenue, both re-based daily and ticking.", stale=sp.get("stale"), basis=sp.get("basis"),
        calc={"type": "difference", "of": ["spending", "revenue"]})
    META["mts_latest"] = latest_d
    if dtsset:
        L, D90 = dtsset["latest"], dtsset["d90"]; P = dtsset["fyend_prev"]
        if "interest" in L and L["fy"] == FY:
            flow = L["interest"] - D90.get("interest", 0) if D90["fy"] == L["fy"] else L["interest"] + P.get("interest", 0) - D90.get("interest", 0)
            add("interest_cash", label="Interest paid to bondholders (cash)", group="fytd", kind="usd", mode="fytd", base=L["interest"], t0=eod_et(L["date"]),
                rate=flow / (eod_et(L["date"]) - eod_et(D90["date"])), as_of=L["date"], fy=FY, prev_fy_total=P.get("interest"),
                source=DTS_TABLE_URL, source_name="Treasury Daily Treasury Statement (Interest on Treasury Securities)",
                method=f"Cash interest paid on Treasury securities FY{FY} to date, re-based every business day; ticks at the last 90 days' average. Payments are lumpy (big on the 15th and month-end).", stale=dts_stale,
                calc={"type": "two_point", "from": [D90["date"], D90.get("interest", 0)], "to": [L["date"], L["interest"]], "flow": flow,
                      "note": "FYTD cash; across Oct 1 the flow adds the prior FY's Sep 30 total"})
else:
    for s, (l, c) in list(TOTALS.items()) + list(REV.items()) + list(OUT.items()):
        unavailable(s, l, "fytd", MTS_URL, "MTS API unreachable and no cache")
    unavailable("deficit", "Federal deficit", "fytd", MTS_URL, "MTS API unreachable")

# ---- gross interest expense on Treasury securities (accrual)
ie, ie_stale = cached("interest_expense", src_interest)
if ie:
    by = {}
    for r in ie:
        d = r["record_date"]; by.setdefault(d, {"m": 0.0, "f": 0.0, "n": 0, "fy": int(r["record_fiscal_year"])})
        by[d]["m"] += float(r["month_expense_amt"] or 0); by[d]["f"] += float(r["fytd_expense_amt"] or 0); by[d]["n"] += 1
    ds = sorted(by)[-12:]; last = ds[-1]
    ttm = sum(by[d]["m"] for d in ds)
    # integrity: 12 consecutive month-ends, each with the same row count as the latest month
    months = {d[:7] for d in ds}
    complete = len(months) == 12 and all(by[d]["n"] >= by[last]["n"] - 2 for d in ds)
    if not complete: errors["interest_expense_integrity"] = f"only {len(months)} months / row counts {[by[d]['n'] for d in ds]}"
    if by[last]["fy"] == FY:
        base, t0 = by[last]["f"], eod_et(last)
    else:
        base, t0 = 0.0, FY_START
    prev = by[last]["f"] if by[last]["fy"] == FY - 1 else None
    if prev is not None:   # when the latest month is September, TTM must equal the FY total
        e = (ttm - prev) / prev * 100
        validation_rows.append({"ticker": "interest_gross", "from": ds[0], "to": last, "projected": round(ttm, 2), "official": prev, "error_pct": round(e, 4), "mode": "ttm_vs_fy_total"})
    add("interest_gross", label="Gross interest expense on Treasury debt", group="fytd", kind="usd", mode="fytd", base=base, t0=t0,
        rate=ttm / YEAR_S, as_of=last if base else dt.datetime.fromtimestamp(FY_START, ET).date().isoformat(), fy=FY, prev_fy_total=prev, ttm=ttm,
        source=INT_URL, source_name="Treasury, Interest Expense on the Public Debt Outstanding",
        method=(f"One measure throughout: Treasury's monthly interest expense on all Treasury securities (accrual basis, including interest credited to trust funds and amortized discounts). "
                f"FY{FY} to date starts at $0 on Oct 1 and ticks at the last 12 reported months' total (${ttm/1e9:,.1f}B/yr, {ds[0][:7]} to {last[:7]})"
                + (f", which is also the official FY{FY-1} total (${prev/1e9:,.1f}B)" if prev is not None and abs(ttm - prev) / prev < 0.001 else "")
                + ". Larger than 'Net interest' (budget function 900) because interest paid to trust funds nets out there, and different from cash interest paid on the DTS."),
        stale=ie_stale, calc={"type": "ttm", "months": [[d, by[d]["m"]] for d in ds], "ttm": ttm})
else:
    unavailable("interest_gross", "Gross interest expense on Treasury debt", "fytd", INT_URL, "Interest expense API unreachable")

ar, ar_stale = cached("avg_rates", src_avg_rate)
if ar:
    d0 = ar[0]["record_date"]
    tot = [r for r in ar if r["record_date"] == d0 and r["security_desc"] in ("Total Marketable", "Total Interest-bearing Debt")]
    for r in tot:
        slug = "rate_marketable" if "Marketable" in r["security_desc"] else "rate_all"
        add(slug, label=f"Avg interest rate, {r['security_desc'].lower()}", group="economy", kind="pct", base=float(r["avg_interest_rate_amt"]),
            rate=0, t0=NOW, as_of=d0, fixed=True, source=AIR_URL, source_name="Treasury, Average Interest Rates on U.S. Treasury Securities",
            method="Monthly official average; changes once a month.", stale=ar_stale)

# ---- recent official closes ("What changed" strip)
if debt:
    rows = sorted(debt["rows"], key=lambda r: r["record_date"])[-11:]
    META["recent_closes"] = [{"date": b["record_date"], "total": float(b["tot_pub_debt_out_amt"]), "public": float(b["debt_held_public_amt"]),
                              "intragov": float(b["intragov_hold_amt"]), "d_total": float(b["tot_pub_debt_out_amt"]) - float(a["tot_pub_debt_out_amt"]),
                              "d_public": float(b["debt_held_public_amt"]) - float(a["debt_held_public_amt"]),
                              "d_intragov": float(b["intragov_hold_amt"]) - float(a["intragov_hold_amt"])} for a, b in zip(rows, rows[1:])][::-1]

# ---- official daily closes for /api/daily.json (last 45 records, newest first; real Treasury rows only)
if debt:
    rows = sorted(debt["rows"], key=lambda r: r["record_date"])[-45:]
    META["debt_closes"] = [[r["record_date"], float(r["tot_pub_debt_out_amt"])] for r in rows][::-1]
    META["debt_closes_stale"] = bool(debt_stale)

# ---- debt subject to the statutory limit (DTS Table III-C, daily)
DSL_URL = "https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/debt-subject-to-limit"
def src_dsl():
    rows = fd("v1/accounting/dts/debt_subject_to_limit", sort="-record_date", **{"page[size]": 700},
              fields="record_date,debt_catg,debt_catg_desc,close_today_bal")
    oldest = min(r["record_date"] for r in rows)        # page cut may split the oldest day: drop it
    return [r for r in rows if r["record_date"] != oldest]
dsl, dsl_stale = cached("dts_dsl", src_dsl)
if dsl:
    by = {}
    for r in dsl:
        d = by.setdefault(r["record_date"], {"subj": 0.0, "limit": None}); v = float(r["close_today_bal"] or 0) * 1e6
        c = r["debt_catg"]
        if c in ("Debt Held by the Public", "Intragovernmental Holdings", "Other Debt Subject to Limit"): d["subj"] += v
        elif c == "Debt Not Subject to Limit": d["subj"] -= v
        elif c == "Statutory Debt Limit": d["limit"] = v
    ds = sorted(by); last = ds[-1]; tl = eod_et(last)
    win = [d for d in ds if tl - eod_et(d) <= 90 * 86400]
    rate = ols_slope([eod_et(d) for d in win], [by[d]["subj"] for d in win])
    dcalc = ols_calc(win, [eod_et(d) for d in win], [by[d]["subj"] for d in win], f"trailing 90 days ({win[0]} to {win[-1]})")
    add("debt_subject_limit", calc=dcalc, label="Debt subject to the limit", group="debt", kind="usd", base=by[last]["subj"], t0=tl, rate=rate, as_of=last,
        source=DSL_URL, source_name="Treasury Daily Treasury Statement, Table III-C",
        method=f"Total debt minus debt not subject to limit (unamortized discount, FFB, other). Official close {last}; ticks at the 90-day trend ({len(win)} records).", stale=dsl_stale)
    if by[last]["limit"]:
        add("debt_limit", label="Statutory debt limit", group="debt", kind="usd", base=by[last]["limit"], rate=0, t0=tl, as_of=last, fixed=True,
            source=DSL_URL, source_name="Treasury Daily Treasury Statement, Table III-C", method="Set by Congress. Changes only when the law changes.", stale=dsl_stale)

# ---- debt-limit rule: never project the debt past the statutory limit
# When debt subject to the limit sits at (or within AT_LIMIT_MARGIN of) the limit, or has gone flat near it,
# Treasury is using extraordinary measures: debt stops growing, so the clock must stop projecting growth.
# Otherwise each debt ticker gets freeze_t = the moment its projected debt subject to limit would reach the limit,
# so a long gap between refreshes can never carry the clock past what the law allows.
AT_LIMIT_MARGIN = 25e9          # $25B: under extraordinary measures Treasury keeps the gap far smaller than this
FLAT_RANGE = 5e9                # last 5 closes within $5B of each other ...
FLAT_NEAR = 150e9               # ... while within $150B of the limit = held at the limit
if dsl and T.get("debt_subject_limit", {}).get("status") == "ok" and T.get("debt_limit", {}).get("status") == "ok":
    sl, lim = T["debt_subject_limit"], T["debt_limit"]["base"]
    last5 = [by[d]["subj"] for d in ds[-5:]]
    rng = max(last5) - min(last5); head = lim - sl["base"]
    at_limit = head <= AT_LIMIT_MARGIN or (len(last5) >= 5 and rng <= FLAT_RANGE and head <= FLAT_NEAR)
    held = ("debt_total", "debt_public", "debt_intragov", "debt_subject_limit")
    st = {"at_limit": at_limit, "limit": lim, "subject_to_limit": sl["base"], "headroom": head, "as_of": sl["as_of"],
          "last5_range": rng, "margin": AT_LIMIT_MARGIN, "source": DSL_URL, "freeze_t": None}
    if at_limit:
        note = (f" At the debt limit: debt subject to the limit was ${sl['base']/1e12:,.3f}T on {sl['as_of']}, "
                f"${head/1e9:,.1f}B under the ${lim/1e12:,.3f}T limit. Treasury is using extraordinary measures, so this ticker "
                "holds at the latest official figure instead of projecting growth.")
        for k in held:
            if T.get(k, {}).get("status") == "ok":
                T[k]["rate_trend"] = T[k]["rate"]; T[k]["rate"] = 0.0; T[k]["held_at_limit"] = True; T[k]["method"] += note
    elif sl["rate"] > 0:
        ft = sl["t0"] + head / sl["rate"]
        st["freeze_t"] = ft
        for k in held:
            if T.get(k, {}).get("status") == "ok": T[k]["freeze_t"] = ft
    META["debt_limit_status"] = st

# ---- Treasury Historical Debt Outstanding (fiscal-year end totals, 1790 to latest), for the by-year page
DO_URL = "https://fiscaldata.treasury.gov/datasets/historical-debt-outstanding/historical-debt-outstanding"
def src_debt_outstanding():
    rows = fd("v2/accounting/od/debt_outstanding", sort="record_date", **{"page[size]": 400},
              fields="record_date,debt_outstanding_amt,record_fiscal_year")
    if len(rows) < 200: raise ValueError(f"only {len(rows)} rows")
    return [[int(r["record_fiscal_year"]), r["record_date"], float(r["debt_outstanding_amt"])] for r in rows]
dout, dout_stale = cached("debt_outstanding", src_debt_outstanding)
if dout:
    META["debt_by_fy"] = dout; META["debt_by_fy_stale"] = bool(dout_stale); META["debt_by_fy_source"] = DO_URL

# ---- Federal Reserve holdings of Treasuries (NY Fed SOMA, weekly)
SOMA_URL = "https://www.newyorkfed.org/markets/soma-holdings"
def src_soma():
    return json.loads(get("https://markets.newyorkfed.org/api/soma/summary.json"))["soma"]["summary"][-20:]
soma, soma_stale = cached("nyfed_soma", src_soma)
if soma:
    tsy = lambda r: sum(float(r.get(k) or 0) for k in ("bills", "notesbonds", "frn", "tips", "tipsInflationCompensation"))
    pts = soma[-13:]; xs = [eod_et(r["asOfDate"]) for r in pts]; ys = [tsy(r) for r in pts]
    add("fed_treasuries", calc=ols_calc([r["asOfDate"] for r in pts], xs, ys, "last 13 weekly reports"), label="Fed holdings of Treasuries", group="money", kind="usd", base=ys[-1], t0=xs[-1], rate=ols_slope(xs, ys), as_of=pts[-1]["asOfDate"],
        source=SOMA_URL, source_name="Federal Reserve Bank of New York, SOMA holdings (H.4.1 basis)",
        method="Bills + notes/bonds + FRNs + TIPS incl. inflation compensation, par value, weekly (Wednesday). Ticks at the 13-week trend.", stale=soma_stale)

# ---- M2 money supply (Federal Reserve H.6, monthly, seasonally adjusted)
H6_URL = "https://www.federalreserve.gov/releases/h6/current/default.htm"
def src_m2():
    txt = get("https://www.federalreserve.gov/datadownload/Output.aspx?rel=H6&series=798e2796917702a5f8423426ba7e6b42&lastobs=8&from=&to=&filetype=csv&label=include&layout=seriescolumn")
    r = list(csv.reader(io.StringIO(txt))); i = r[0].index("M2; Seasonally adjusted")
    return [[row[0], float(row[i]) * 1e9] for row in r if re.match(r"^\d{4}-\d\d$", row[0] or "") and row[i] not in ("", "ND", "NA")]
import re
m2, m2_stale = cached("fed_h6_m2", src_m2)
if m2:
    def mm(p): y, m = map(int, p.split("-")); return dt.datetime(y, m, 15, tzinfo=ET).timestamp()
    pts = m2[-6:]
    add("m2", calc=ols_calc([p for p, _ in pts], [mm(p) for p, _ in pts], [v for _, v in pts], "last 6 monthly averages (mid-month anchors)"), label="M2 money supply", group="money", kind="usd", base=pts[-1][1], t0=mm(pts[-1][0]), rate=ols_slope([mm(p) for p, _ in pts], [v for _, v in pts]),
        as_of=pts[-1][0], source=H6_URL, source_name="Federal Reserve H.6 Money Stock (M2, seasonally adjusted)",
        method=f"Monthly average for {pts[-1][0]} = ${pts[-1][1]/1e12:.3f}T; ticks at the 6-month trend, anchored mid-month.", stale=m2_stale)

# ---- Social Security and Medicare trust funds (Treasury Federal Investments Program, monthly)
FIP_URL = "https://fiscaldata.treasury.gov/datasets/federal-investments-program-principal-outstanding/"
TF = {"tf_oasi": ("028X8006", "Social Security retirement (OASI) trust fund"), "tf_di": ("028X8007", "Social Security disability (DI) trust fund"),
      "tf_hi": ("075X8005", "Medicare hospital (HI) trust fund"), "tf_smi": ("075X8004", "Medicare SMI trust fund")}
def src_tf():
    since = (dt.date.fromtimestamp(NOW) - dt.timedelta(days=420)).isoformat()
    rows = []
    for acct, _ in TF.values():
        page = 1
        while True:
            j = json.loads(get(f"{FD}/v1/accounting/od/fip_principal_outstanding_table1?" + urllib.parse.urlencode({
                "filter": f"record_date:gte:{since},account_nbr:eq:{acct}", "fields": "record_date,account_nbr,src_line_nbr,security_desc,shares_per_par",
                "page[size]": 5000, "page[number]": page}, safe=":,")))
            rows += j["data"]
            if page >= j["meta"]["total-pages"]: break
            page += 1
    agg = {}
    for r in rows:
        agg.setdefault(r["record_date"], {}).setdefault(r["account_nbr"], 0.0)
        agg[r["record_date"]][r["account_nbr"]] += float(r["shares_per_par"] or 0)
    return agg
tf, tf_stale = cached("fip_trust_funds", src_tf)
if tf:
    ds = sorted(tf); last = ds[-1]
    def series(accts): return [(eod_et(d), sum(tf[d].get(a, 0) for a in accts)) for d in ds]
    combos = {"tf_socsec": (["028X8006", "028X8007"], "Social Security trust funds (OASI + DI)"),
              "tf_medicare": (["075X8005", "075X8004"], "Medicare trust funds (HI + SMI)")}
    for slug, (accts, label) in list(combos.items()) + [(k, ([a], l)) for k, (a, l) in TF.items()]:
        s = series(accts)[-13:]
        add(slug, calc=ols_calc([d for d in ds][-13:], [x for x, _ in s], [y for _, y in s], "last 13 month-ends"), label=label, group="trust", kind="usd", base=s[-1][1], t0=s[-1][0], rate=ols_slope([x for x, _ in s], [y for _, y in s]), as_of=last,
            source=FIP_URL, source_name="Treasury, Federal Investments Program: Principal Outstanding",
            method=f"Par value of Treasury securities held by the fund(s) at month-end {last}. Ticks at the 12-month trend; a falling number means the fund is being drawn down.", stale=tf_stale)

# ---- "Why the debt grew more than the deficit" (FY explainer, computed from official data)
def src_explain():
    fyp = FY - 1
    a = fd("v2/accounting/od/debt_to_penny", filter=f"record_date:in:({fyp-1}-09-30,{fyp}-09-30)", fields="record_date,tot_pub_debt_out_amt,debt_held_public_amt,intragov_hold_amt")
    o = fd("v1/accounting/dts/operating_cash_balance", filter=f"record_date:in:({fyp-1}-09-30,{fyp}-09-30)", fields="record_date,account_type,open_today_bal")
    return {"dttp": a, "ocb": o}
ex, ex_stale = cached("explainer", src_explain)
if ex and mts and len(ex["dttp"]) == 2:
    fyp = FY - 1
    d0, d1 = sorted(ex["dttp"], key=lambda r: r["record_date"])
    g = lambda r, k: float(r[k])
    tga = {r["record_date"]: float(r["open_today_bal"]) * 1e6 for r in ex["ocb"] if "Closing Balance" in r["account_type"]}
    deficit = T["deficit"]["prev_fy_total"]
    E = {"fy": fyp, "from": d0["record_date"], "to": d1["record_date"],
         "debt_growth": g(d1, "tot_pub_debt_out_amt") - g(d0, "tot_pub_debt_out_amt"),
         "public_growth": g(d1, "debt_held_public_amt") - g(d0, "debt_held_public_amt"),
         "intragov_growth": g(d1, "intragov_hold_amt") - g(d0, "intragov_hold_amt"),
         "deficit": deficit,
         "tga_change": (tga.get(d1["record_date"]) - tga.get(d0["record_date"])) if len(tga) == 2 else None,
         "sources": {"Debt to the Penny": DTP_URL, "Monthly Treasury Statement": MTS_URL, "Daily Treasury Statement (operating cash balance)": "https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/operating-cash-balance"}}
    E["other_financing"] = E["public_growth"] - E["deficit"] - (E["tga_change"] or 0)
    META["explainer"] = E

# ---- OMB historical (fixed)
omb, omb_stale = cached("omb_hist", src_omb)
if omb:
    for y in ("1960", "1980", "1990", "2000", "2010", "2020", "2025"):
        r71 = omb["t71"].get(y); r12 = omb["t12"].get(y)
        if r71: add(f"hist_debt_gdp_{y}", label=f"Debt-to-GDP, FY{y}", group="history", kind="pct", base=r71[6], rate=0, t0=NOW, as_of=f"FY{y}",
                    fixed=True, historical=True, source=OMB_URL, source_name="OMB Historical Tables, Table 7.1 (FY2027 Budget)",
                    method="Gross federal debt at end of fiscal year as % of GDP. Historical, does not tick.")
        if r12: add(f"hist_def_gdp_{y}", label=f"Deficit-to-GDP, FY{y}", group="history", kind="pct", base=-r12[4], rate=0, t0=NOW, as_of=f"FY{y}",
                    fixed=True, historical=True, source=OMB_URL, source_name="OMB Historical Tables, Table 1.2 (FY2027 Budget)",
                    method="Deficit as % of GDP (negative = surplus). Historical, does not tick.")

# ---- derived ratio metadata (computed live in the browser from ticking parts)
DERIVED = {
    "debt_gdp_now": {"label": "Debt-to-GDP, now", "num": "debt_total", "den": "gdp", "kind": "pct", "group": "ratios",
                     "method": "Live national debt ÷ live GDP (annual rate). Both tick."},
    "deficit_gdp_now": {"label": "Deficit-to-GDP, trailing 12 months", "num_ttm": ["spending", "revenue"], "den": "gdp", "kind": "pct", "group": "ratios",
                        "method": "Last 12 months of official MTS outlays minus receipts ÷ live GDP."},
    "interest_share": {"label": "Net interest as share of revenue", "num": "out_interest", "den": "revenue", "kind": "pct", "group": "ratios",
                       "method": "FY-to-date net interest ÷ FY-to-date revenue (both ticking)."},
    "interest_annual": {"label": "Annual interest on today's debt", "kind": "usd", "group": "interest",
                        "method": "Live national debt × Treasury's average interest rate on all interest-bearing debt. What a year of interest costs at today's debt and rates."},
    "interest_per_day": {"label": "Interest cost per day", "kind": "usd", "group": "interest",
                         "method": "Annual interest on today's debt ÷ 365.25."},
    "interest_per_sec": {"label": "Interest cost per second", "kind": "usd", "group": "interest", "method": "Annual interest on today's debt ÷ seconds in a year."},
    "limit_headroom": {"label": "Room left under the debt limit", "kind": "usd", "group": "debt",
                       "method": "Statutory debt limit minus live debt subject to limit. Goes negative only on paper; Treasury would use extraordinary measures first."},
    "interest_since_open": {"label": "Interest accrued since you opened this page", "kind": "usd", "group": "interest",
                            "method": "Annual interest on today's debt × seconds since page load ÷ seconds per year."},
    "fed_share_public": {"label": "Share of public debt held by the Fed", "kind": "pct", "group": "money",
                         "method": "Fed Treasury holdings (NY Fed SOMA) ÷ live debt held by the public."},
    "m2_debt_ratio": {"label": "National debt as % of M2", "kind": "pct", "group": "money", "method": "Live national debt ÷ live M2 money supply."},
    "debt_per_household": {"label": "Debt per household", "num": "debt_total", "den": "households", "kind": "usd", "group": "ratios",
                           "method": "Live national debt ÷ 134.79M households (Census CPS ASEC 2025)."},
}

# ---------------------------------------------------------------- validation (daily)
THR = {"debt_intragov": 0.5, "revenue": 3.0, "spending": 3.0, "interest_cash": 10.0}
prev_path = os.path.join(DATA, "data.json")
if os.path.exists(prev_path):
    try:
        prev = json.load(open(prev_path))
        for slug, p in prev.get("tickers", {}).items():
            n = T.get(slug)
            if not n or n.get("status") != "ok" or p.get("status") != "ok" or n.get("fixed"): continue
            if n["as_of"] == p["as_of"]: continue          # no new official value yet
            if slug == "population": continue              # own cross-check vs the Census clock (above)
            if n.get("share") is not None: continue         # split tickers follow their parent total
            if p.get("mode") == "fytd" and n.get("fy") != p.get("fy"): continue
            proj = p["base"] + p["rate"] * (n["t0"] - p["t0"])
            if n["base"] == 0: continue
            err = (proj - n["base"]) / abs(n["base"]) * 100
            switched = p.get("basis") != n.get("basis") or p.get("source") != n.get("source")
            validation_rows.append({"ticker": slug, "from": p["as_of"], "to": n["as_of"], "projected": round(proj, 2),
                                    "official": n["base"], "error_pct": round(err, 4),
                                    "mode": ("method_switch_" + str(p.get("basis") or "mts") + "_to_" + str(n.get("basis"))) if switched else ("daily_vs_dts" if n.get("basis") == "dts" else "daily")})
            if switched: continue
            thr = THR.get(slug, 0.25 if n["group"] == "debt" else 3.0 if n.get("basis") == "dts" else 5.0)
            n.setdefault("validation", {}).update({"last_error_pct": round(err, 4), "threshold_pct": thr, "flag": abs(err) > thr,
                                                   "against": n["source_name"]})
    except Exception as e:
        errors["validation"] = str(e)

# write log (append)
logp = os.path.join(DATA, "validation_log.csv")
new = not os.path.exists(logp)
with open(logp, "a", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["run_iso", "ticker", "mode", "from", "to", "projected", "official", "error_pct", "flag"])
    if new: w.writeheader()
    for r in validation_rows:
        thr = 5.0 if r["mode"] == "dts_ratio_backtest" else THR.get(r["ticker"], 0.25 if r["ticker"].startswith("debt") else 5.0)
        w.writerow({"run_iso": META["generated_iso"], **r, "flag": (not r["mode"].startswith("method_switch")) and r["error_pct"] is not None and abs(r["error_pct"]) > thr})

flags = [s for s, t in T.items() if t.get("validation", {}).get("flag")]
META.update({"errors": errors, "flags": flags, "denominators": {"population": "population", "tax_returns": "tax_returns"}})
out = {"meta": META, "tickers": T, "derived": DERIVED}
json.dump(out, open(prev_path, "w"), indent=1)
json.dump(out, open(os.path.join(DATA, f"data-{dt.datetime.fromtimestamp(NOW, ET).date()}.json"), "w"))
print(f"wrote {len(T)} tickers; flags={flags}; errors={list(errors)}")
for s in ("debt_total", "debt_public", "debt_intragov", "spending", "revenue", "deficit", "population", "gdp"):
    t = T.get(s, {})
    if t.get("status") == "ok":
        v = t["base"] + t["rate"] * (NOW - t["t0"])
        print(f"{s:16} now={v:,.0f} rate/s={t['rate']:,.2f} as_of={t['as_of']} val={t.get('validation')}")
    else: print(s, t.get("status"), t.get("note"))
