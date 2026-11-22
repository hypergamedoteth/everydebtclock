#!/usr/bin/env python3
"""Quarterly re-base of places/egypt.json from the Ministry of Finance of Egypt "Budget Sector Statistical Debt Bulletin" (quarterly PDF, Debt Management Unit).
The bulletin page lists every bulletin; each states "Total Budget Sector Debt Outstanding" (EGP million) at the quarter-end (and at the prior reference date), with the domestic
and external parts. The newest bulletin and the one about a year earlier are read. Never invents a number: domestic + external must equal the total, otherwise the file is
left untouched (exit 0)."""
import re, sys
from place_util import *

# The bulletin index moved in 2026. The old citizens-budget URL 404s. Try the current page, then the old one.
PAGES = [
    "https://mof.gov.eg/en/financial-data/budget-agencies-debt-management/budget-sector-debt-bulletin/budget-sector-debt-bulletin",
    "https://mof.gov.eg/en/financial-data/citizens-budget/budget-sector-debt-bulletin/budget-sector-debt-bulletin",
]
M = 10**6

def bulletin_html():
    errors = []
    for url in PAGES:
        try:
            html = get(url, ua=BROWSER_UA, timeout=45)
        except Exception as e:
            errors.append(f"{url}: {e}")
            continue
        if "Budget_Sector_Statistical_Debt_Bulletin_" in html:
            return html
        errors.append(f"{url}: no bulletin links")
    raise RuntimeError("bulletin page not found; " + "; ".join(errors))

def _millions(text):
    """EGP billions as printed in the 2026 narrative bulletin, in the table's EGP-million unit."""
    return int(round(float(text.replace(",", "")) * 1000))

def read(url):
    t = pdf_text(get(url, ua=BROWSER_UA, raw=True))
    def row(label):
        r = re.search(r"^\s*" + label + r"[^\n\d]*([\d,]{7,}(?:\s+[\d,]{7,})*)", t, re.M)
        if not r: raise RuntimeError(f"row {label!r} missing in {url}")
        return [int(x.replace(",", "")) for x in re.findall(r"[\d,]{7,}", r.group(1))]
    try:
        tot, dom, ext = row("Total Budget Sector Debt Outstanding"), row("Total Domestic Budget Sector Debt"), row("Total External Budget Sector Debt")
        # the table gives the reference date (usually the previous June) first and the bulletin quarter-end last
        if abs(dom[-1] + ext[-1] - tot[-1]) > 5: raise RuntimeError("domestic + external != total")
        return tot[-1], dom[-1], ext[-1]
    except RuntimeError:
        pass
    # June 2026 onward states the stock in the narrative instead of the old table.
    tot_m = re.search(r"total budget sector debt stood at EGP ([\d,.]+) billion", t, re.I)
    dom_m = re.search(r"Domestic budget sector debt was EGP ([\d,.]+) billion", t, re.I)
    ext_m = re.search(r"External budget sector debt reached USD [\d,.]+ billion \(EGP ([\d,.]+) billion\)", t, re.I)
    if not (tot_m and dom_m and ext_m):
        raise RuntimeError(f"debt stock not found in {url}")
    tot, dom, ext = _millions(tot_m.group(1)), _millions(dom_m.group(1)), _millions(ext_m.group(1))
    if abs(dom + ext - tot) > 5: raise RuntimeError("domestic + external != total")
    return tot, dom, ext

def build(p):
    h = bulletin_html()
    found = {}
    for u, mon, yr in re.findall(r'(https://media\.mof\.gov\.eg/mof-prd/Budget_Sector_Statistical_Debt_Bulletin_([A-Za-z]+)_(\d{4})_[0-9a-f]+\.pdf)', h):
        try: found[month_end(int(yr), MONTHS.index(mon) + 1)] = u
        except ValueError: pass
    if len(found) < 3: raise RuntimeError("bulletins not found")
    last = max(found); cut = (d(last) - dt.timedelta(days=400)).isoformat()
    series, det = {}, {}
    for a in sorted(x for x in found if x >= cut):
        try: det[a] = read(found[a]); series[a] = det[a][0] * M
        except Exception as e: print(f"egypt: {a}: {e}")
    if last not in series: raise RuntimeError("latest bulletin unreadable")
    p = rebase(p, series, tol_days=45, keep_months=14)
    c = p["components"][0]; c["source_url"] = found[last]
    tot, dom, ext = det[last]
    c["breakdown"] = [{"label": "Domestic budget sector debt (includes foreign-currency debt owed to Egyptian residents)", "value": dom * M, "group": "Domestic"},
                      {"label": "External budget sector debt (foreign-currency debt held by non-residents)", "value": ext * M, "group": "External"}]
    p["next_update"] = "The Ministry of Finance publishes a Budget Sector Statistical Debt Bulletin each quarter, with a lag of several months; this page re-bases to it automatically on the next daily build after it appears."
    return p

if __name__ == "__main__": sys.exit(run("egypt", build))
