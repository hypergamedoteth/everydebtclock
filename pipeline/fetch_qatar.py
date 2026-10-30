#!/usr/bin/env python3
"""Annual re-base of places/qatar.json from the Qatar Ministry of Finance "Public Debt" dataset on the national open-data portal (data.gov.qa, CC BY):
year-end total public debt with its domestic and external parts, in QAR million. Never invents a number: domestic + external must equal the stated total, otherwise
the file is left untouched (exit 0). Year-end figures are dated 31 December."""
import sys, json
from place_util import *

API = "https://www.data.gov.qa/api/explore/v2.1/catalog/datasets/public-debt/records?limit=100"
M = 10**6

def build(p):
    rows = json.loads(get(API, ua=BROWSER_UA))["results"]
    by = {}
    for r in rows: by.setdefault(str(r["year"]), {})[r["item"]] = float(r["amount"]) * M
    tot, det = {}, {}
    for y, it in by.items():
        if "Total Public Debt" in it and "Domestic Debt" in it and "External Debt" in it:
            if abs(it["Domestic Debt"] + it["External Debt"] - it["Total Public Debt"]) > 1.5 * M: print(f"qatar: {y}: parts do not add up; skipped"); continue
            tot[f"{y}-12-31"] = it["Total Public Debt"]; det[y] = it
    if len(tot) < 3: raise RuntimeError("fewer than three complete years")
    p = rebase(p, tot, tol_days=30, keep_months=40)
    last = max(det); it = det[last]; c = p["components"][0]
    c["breakdown"] = [{"label": "Domestic debt", "value": int(it["Domestic Debt"]), "group": "Domestic"},
                      {"label": "External debt", "value": int(it["External Debt"]), "group": "External"}]
    p["next_update"] = f"The Ministry of Finance adds each year-end position to its open-data portal after the year closes; the {int(last) + 1} figure is expected during {int(last) + 2}. This page re-bases to it automatically on the next daily build after it appears."
    return p

if __name__ == "__main__": sys.exit(run("qatar", build))
