#!/usr/bin/env python3
"""Re-base of places/taiwan.json from the National Treasury Administration of Taiwan's open dataset D3-12F (central government debt outstanding,
weekly; NT$100 million): column 2 = debts with a maturity of one year or more, column 3 = short-term debts. The hero is their sum.
The same file carries the population (Ministry of the Interior), which refreshes the page's population.
The trend is the official change over the latest twelve months (month-end observations). Never invents a number; any error leaves the file untouched."""
import csv, io, sys, datetime as dt
from place_util import *

URL = "https://nss.nta.gov.tw/nss/files/opendata/D3-12F.csv"
YI = 10**8

def roc(s):
    s = s.strip(); return dt.date(int(s[:-4]) + 1911, int(s[-4:-2]), int(s[-2:])).isoformat()

def build(p):
    rows = list(csv.reader(io.StringIO(get(URL, ua=BROWSER_UA, raw=True).decode("utf-8-sig"))))[1:]
    series, pops = {}, {}
    for r in rows:
        if len(r) < 4 or not r[0].strip().isdigit(): continue
        a, b, s, n = roc(r[0]), float(r[1]), float(r[2]), int(float(r[3]))
        series[a] = (b + s) * YI; pops[a] = n
    last = max(series)
    if len(series) < 60: raise RuntimeError("series too short")
    p = rebase(p, series, tol_days=10, hist_monthly=True)
    r = [x for x in rows if x and x[0].strip().isdigit() and roc(x[0]) == last][0]
    c = p["components"][0]
    c["breakdown"] = [{"label": "Debts with a maturity of one year or more", "value": int(float(r[1]) * YI), "group": "Long-term"},
                      {"label": "Short-term debts", "value": int(float(r[2]) * YI), "group": "Short-term"}]
    if pops[last] > 20_000_000 and last >= p["population"]["as_of"]:
        p["population"]["value"] = pops[last]; p["population"]["as_of"] = last
    p["next_update"] = "The National Treasury Administration updates the figure about weekly; this page re-bases to each new row automatically on the next daily build after it appears."
    return p

if __name__ == "__main__": sys.exit(run("taiwan", build))
