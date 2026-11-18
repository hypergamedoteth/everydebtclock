#!/usr/bin/env python3
"""Re-check the long-tail pages against the sources they cite.

Read-only. Never writes places, debt_by_year.json, or HTML.

  python3 pipeline/audit_longtail.py [--offline] [--report FILE]

Offline checks the built pages against the committed data files. Without --offline
it also re-downloads Census (the time series and the summary workbooks cited on the
state pages), the World Bank mirror of the IMF World Economic Outlook, and Treasury
Historical Debt Outstanding plus Debt to the Penny for the president dates.

Exit 1 on drift, a page that does not match its data file, or a source that cannot be read.
"""
import argparse, json, os, sys, urllib.parse, urllib.request
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, ROOT)
import audit_places
import fetch_debt_by_year as fy

FD = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
UA = {"User-Agent": "Mozilla/5.0 (compatible; everydebtclock.com data refresh)"}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def issues_or(issues, msg):
    issues.append(msg)


def audit_states(doc, live, issues):
    """2017–2024 must match the state clock file and, live, the Census API. Earlier years are re-parsed from the cited file."""
    import debt_by_year_build as b
    pages = {slug: rec for slug, rec in doc["places"].items() if rec.get("kind") == "state"}
    cited = {}
    for slug, rec in pages.items():
        try:
            rows, _p = b.state_rows(ROOT, slug, rec["rows"])
        except Exception as e:
            issues_or(issues, f"{slug}: debt-by-year table does not match the state clock ({e})")
            continue
        text_path = os.path.join(ROOT, "states", slug, "debt-by-year", "index.html")
        text = open(text_path).read() if os.path.exists(text_path) else ""
        if not text:
            issues_or(issues, f"{slug}: debt-by-year page is missing")
            continue
        last = rows[-1]
        if f"${last['amount']:,.0f}" not in text and f"${last['amount']:,}" not in text:
            # money() uses the same thousands separators
            shown = f"${last['amount']:,.0f}"
            if shown not in text:
                issues_or(issues, f"{slug}: latest total {shown} is not on the page")
        if live:
            try:
                cen = audit_places.census(fy.STATE_FIPS[slug])
            except Exception as e:
                issues_or(issues, f"{slug}: Census API could not be read ({e})")
                cen = None
            if cen is not None:
                dc = slug == "district-of-columbia"
                for r in rows:
                    if r["year"] < 2017:
                        continue
                    if dc:
                        cv = cen.get(("Local", "LF0231", r["year"]))
                        if cv != r["amount"]:
                            issues_or(issues, f"DRIFT {slug} {r['year']}: page {r['amount']} vs Census local {cv}")
                    else:
                        cv = cen.get(("State and Local", "LF0231", r["year"]))
                        if cv is None or abs(cv - r["amount"]) > audit_places.TOL:
                            issues_or(issues, f"DRIFT {slug} {r['year']}: page {r['amount']} vs Census state-and-local {cv}")
        for src in rec.get("sources") or []:
            cited.setdefault(src["url"], []).append((slug, src["year"]))
    if not live:
        return
    parsed_cache = {}
    for url, uses in cited.items():
        try:
            data = get(url)
        except Exception as e:
            issues_or(issues, f"could not re-download {url} ({e})")
            continue
        name = url.rsplit("/", 1)[-1]
        if "slsstab1" in name or name.startswith("04slsstab1") or "stl001" in name:
            try:
                found = fy.parse_census_workbook(data)
            except Exception as e:
                issues_or(issues, f"could not parse {url} ({e})")
                continue
            parsed_cache[url] = found
        else:
            try:
                one = fy.parse_state_file(data, name)
            except Exception as e:
                issues_or(issues, f"could not parse {url} ({e})")
                continue
            parsed_cache[url] = one
        for slug, year in uses:
            got = parsed_cache[url]
            if isinstance(got, dict):
                hit = got.get(slug)
            else:
                hit = got
            stored = next((r for r in pages[slug]["rows"] if r["year"] == year), None)
            if stored is None or hit is None:
                issues_or(issues, f"{slug} {year}: cited file {url} did not yield a debt row")
                continue
            total, state, local = hit
            if abs(total - stored["total"]) > audit_places.TOL or abs(state - stored["state"]) > audit_places.TOL or abs(local - stored["local"]) > audit_places.TOL:
                issues_or(issues, f"DRIFT {slug} {year}: stored {stored['total']} vs re-parse {total} from {url}")


def audit_imf(doc, live, issues):
    weo = json.load(open(os.path.join(ROOT, "data", "world_weo_debt.json")))
    by = {e["slug"]: e for e in weo["economies"]}
    hist = None
    if live:
        try:
            hist = fy._weo_history()
        except Exception as e:
            issues_or(issues, f"IMF World Economic Outlook mirror could not be read ({e})")
    for slug, rec in doc["places"].items():
        if rec.get("kind") != "imf":
            continue
        e = by.get(slug)
        if e is None:
            issues_or(issues, f"{slug}: IMF page has no World Debt Clock row")
            continue
        points = {p["date"][:4]: p for p in rec["points"]}
        for y in ("2025", "2026"):
            p = points.get(y)
            if p is None or p["amount"] != e[f"debt_{y}_usd"] or p["gdp_usd"] != e[f"gdp_{y}_usd"]:
                issues_or(issues, f"DRIFT {slug} {y}: page does not match the stored WEO stock")
        if any(int(y) > 2026 for y in points):
            issues_or(issues, f"{slug}: IMF page includes a year after 2026")
        text_path = os.path.join(ROOT, "countries", slug, "debt-by-year", "index.html")
        if not os.path.exists(text_path):
            issues_or(issues, f"{slug}: IMF debt-by-year page is missing")
        elif f"${points[max(points)]['amount']:,.0f}" not in open(text_path).read():
            issues_or(issues, f"{slug}: latest IMF total is not on the page")
        if hist is None:
            continue
        years = hist.get(e["iso3"]) or {}
        if not years:
            issues_or(issues, f"{slug}: IMF mirror has no history")
            continue
        for y, p in points.items():
            if y not in years:
                issues_or(issues, f"DRIFT {slug} {y}: not in the IMF mirror")
                continue
            ratio, gdp = years[y]
            amount = fy._debt_usd(ratio, gdp)
            if amount != p["amount"] or gdp != p["gdp_usd"]:
                issues_or(issues, f"DRIFT {slug} {y}: stored {p['amount']} vs IMF mirror {amount}")


def _fd(endpoint, **params):
    q = urllib.parse.urlencode(params, safe=":,()")
    return json.loads(get(f"{FD}/{endpoint}?{q}").decode())["data"]


def audit_presidents(live, issues):
    import presidents_build
    try:
        published, skipped, _H = presidents_build.records(ROOT)
    except Exception as e:
        issues_or(issues, f"president records could not be built ({e})")
        return
    flags = {}
    flag_path = os.path.join(ROOT, "data", "longtail_flags.json")
    if os.path.exists(flag_path):
        flags = json.load(open(flag_path))
    flagged = {s["slug"] for s in flags.get("presidents_not_published") or []}
    for s in skipped:
        if s["slug"] not in flagged:
            issues_or(issues, f"{s['name']}: skipped on the page build but not listed in longtail_flags.json")
        if os.path.exists(os.path.join(ROOT, "national-debt-by-president", s["slug"], "index.html")):
            issues_or(issues, f"{s['name']}: flagged as unpublished but a page exists")
    if not live:
        for p in published:
            path = os.path.join(ROOT, "national-debt-by-president", p["slug"], "index.html")
            if not os.path.exists(path):
                issues_or(issues, f"{p['slug']}: president page is missing")
                continue
            text = open(path).read()
            if presidents_build._usd0(p["last"]["amount"]) not in text:
                issues_or(issues, f"DRIFT {p['slug']}: end amount is not the Treasury figure on the page")
        return
    try:
        hdo_rows = _fd("v2/accounting/od/debt_outstanding", sort="record_date", **{"page[size]": 400},
                       fields="record_date,debt_outstanding_amt")
    except Exception as e:
        issues_or(issues, f"Historical Debt Outstanding could not be read ({e})")
        hdo_rows = []
    hdo = sorted((r["record_date"], float(r["debt_outstanding_amt"])) for r in hdo_rows)
    seen = set()
    for p in published:
        for t in p["terms"]:
            for point in (t["a"], t["b"]):
                if not point or point["date"] in seen:
                    continue
                seen.add(point["date"])
                if point["basis"] == "hdo":
                    hit = next((a for d, a in hdo if d == point["date"]), None)
                    if hit is None or abs(hit - point["amount"]) > 0.01:
                        issues_or(issues, f"DRIFT president record {point['date']}: page {point['amount']} vs Historical Debt Outstanding {hit}")
                elif point["basis"] == "dtp":
                    try:
                        rows = _fd("v2/accounting/od/debt_to_penny", sort="-record_date", **{"page[size]": 1},
                                   filter=f"record_date:lte:{point['requested']}",
                                   fields="record_date,tot_pub_debt_out_amt")
                    except Exception as e:
                        issues_or(issues, f"Debt to the Penny could not be read for {point['requested']} ({e})")
                        continue
                    if not rows or rows[0]["record_date"] != point["date"] or abs(float(rows[0]["tot_pub_debt_out_amt"]) - point["amount"]) > 0.01:
                        issues_or(issues, f"DRIFT Debt to the Penny {point['requested']}: page {point['date']} {point['amount']} vs {rows[:1]}")


def audit_per_person(issues):
    import state_per_person_build as sp
    data, skipped = sp.rows(ROOT)
    if skipped or len(data) != 51:
        issues_or(issues, f"debt per person by state is short: {len(data)} rows, skipped {skipped}")
        return
    path = os.path.join(ROOT, "states", "debt-per-person", "index.html")
    if not os.path.exists(path):
        issues_or(issues, "states/debt-per-person/ is missing")
        return
    text = open(path).read()
    for r in data:
        if sp._usd0(r["per"]) not in text:
            issues_or(issues, f"DRIFT debt per person {r['slug']}: {_usd(r)} not on the page")
        # The figure is the clock total divided by the clock population. Recompute and compare.
        again = r["total"] / r["pop"]
        if abs(again - r["per"]) > 1e-6:
            issues_or(issues, f"DRIFT {r['slug']}: per person does not equal total divided by population")


def _usd(r):
    return r["per"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--report")
    a = ap.parse_args()
    doc = json.load(open(os.path.join(ROOT, "data", "debt_by_year.json")))
    issues = []
    audit_states(doc, not a.offline, issues)
    audit_imf(doc, not a.offline, issues)
    audit_presidents(not a.offline, issues)
    audit_per_person(issues)
    n_state = sum(1 for r in doc["places"].values() if r.get("kind") == "state")
    n_imf = sum(1 for r in doc["places"].values() if r.get("kind") == "imf")
    n_nat = sum(1 for r in doc["places"].values() if r.get("kind") == "country")
    lines = [f"# Long-tail audit: {n_state} state series, {n_nat} national country series, {n_imf} IMF country series", ""]
    if issues:
        lines += [f"## {len(issues)} issue(s)"] + [f"- {i}" for i in issues]
    else:
        lines.append("## Clean." if not a.offline else "## Clean: internal checks passed (live source comparison not run).")
    out = "\n".join(lines)
    print(out)
    if a.report:
        open(a.report, "w").write(out + "\n")
    sys.exit(1 if issues else 0)


if __name__ == "__main__":
    main()
