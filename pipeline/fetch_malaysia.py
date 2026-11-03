#!/usr/bin/env python3
"""Re-base of places/malaysia.json from the quarterly federal government debt series (compiled by Bank Negara Malaysia, by remaining maturity) on the national open-data portal
(data.gov.my catalogue "federal_finance_qtr_debt_mat", RM million; each row's date is the first day of the quarter, the position is the quarter-end).
Total = domestic + external must hold, otherwise the file is left untouched (exit 0). Never invents a number."""
import json, sys, datetime as dt
from place_util import *

API = "https://api.data.gov.my/data-catalogue?id=federal_finance_qtr_debt_mat&limit=400&sort=-date"
M = 10**6

def qend(s):
    y, m = int(s[:4]), int(s[5:7]); return month_end(y, m + 2)

def build(p):
    rows = json.loads(get(API, ua=BROWSER_UA))
    g = lambda sector: {qend(r["date"]): float(r["value"]) * M for r in rows if r["type"] == "total" and r["maturity"] == "total" and r["sector"] == sector}
    tot, dom, ext = g("total"), g("domestic"), g("external")
    ok = {a: v for a, v in tot.items() if a in dom and a in ext and abs(dom[a] + ext[a] - v) <= 2 * M}
    if len(ok) < 6: raise RuntimeError("fewer than six complete quarters")
    p = rebase(p, ok, tol_days=20, keep_months=14)
    last = max(ok)
    p["components"][0]["breakdown"] = [{"label": "Domestic debt", "value": int(dom[last]), "group": "Domestic"}, {"label": "External debt", "value": int(ext[last]), "group": "External"}]
    p["next_update"] = "Bank Negara Malaysia adds each quarter-end position to the open-data portal some weeks after the quarter ends; this page re-bases to it automatically on the next daily build after it appears."
    return p

if __name__ == "__main__": sys.exit(run("malaysia", build))
