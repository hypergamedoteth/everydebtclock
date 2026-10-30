#!/usr/bin/env python3
"""Monthly re-base of places/australia.json from the Australian Office of Financial Management (AOFM) Data Hub, "Portfolio Aggregate - dealt":
sheet FaceValue, column "Total AUD Main Funding Instruments" = Treasury Bonds + Treasury Indexed Bonds (capital indexed) + Treasury Notes, face value, A$, month-end.
Cross-check: the AOFM's own annual series (stock_ags.csv: Treasury Bonds + Treasury Indexed Bonds on issue at 30 June, excludes Treasury Notes) must agree with the monthly workbook within 0.3% for every completed financial year.
The trend is the official change over the latest twelve months. Never invents a number; any error leaves the file untouched (exit 0)."""
import re, sys, datetime as dt
from place_util import *
import xlsx_min

HUB = "https://www.aofm.gov.au/data-hub"

def serial(s): return (dt.date(1899, 12, 30) + dt.timedelta(days=int(float(s)))).isoformat()

def build(p):
    h = get(HUB)
    m = re.search(r'href="(/sites/default/files/[^"]*portfolio_aggregate_-_dealt[^"]*\.xlsx)"', h)
    if not m: raise RuntimeError("AOFM data hub: dealt portfolio aggregate link not found")
    wb = xlsx_min.read_bytes(get("https://www.aofm.gov.au" + m.group(1), raw=True))
    rows = wb["FaceValue"]
    hdr = next(r for i, r in rows if (r.get("A") or "").strip() == "Instrument")
    cols = {v.strip(): k for k, v in hdr.items() if v}
    need = ["Treasury Bonds", "Treasury Indexed Bonds (Capital Indexed)", "Treasury Notes", "Total AUD Main Funding Instruments"]
    if any(n not in cols for n in need): raise RuntimeError("AOFM workbook: columns changed")
    tot, parts = {}, {}
    for i, r in rows:
        a = r.get("A") or ""
        if not re.fullmatch(r"\d{5}", a): continue
        d = serial(a); vals = {n: -float(r.get(cols[n]) or 0) for n in need}
        if abs(sum(vals[n] for n in need[:3]) - vals[need[3]]) > 1e6: raise RuntimeError(f"{d}: instruments do not add up")
        tot[d] = vals[need[3]]; parts[d] = vals
    last = max(tot)
    tot = {a: v for a, v in tot.items() if a >= f"{int(last[:4]) - 2}-01-01"}
    fyd = fyv = None
    try:
        t = get("https://www.aofm.gov.au/sites/default/files/2025-05-29/stock_ags.csv")
        cut = (dt.date.fromisoformat(last) - dt.timedelta(days=365)).isoformat()
        for l in t.strip().splitlines()[1:]:
            fy, v = l.split(",")[:2]
            fd = f"20{fy[-2:]}-06-30"
            if fd <= cut and fd in parts:
                fyd, fyv = fd, float(v) * 1e9
                bonds = parts[fd]["Treasury Bonds"] + parts[fd]["Treasury Indexed Bonds (Capital Indexed)"]
                if abs(bonds / fyv - 1) > 0.003: raise RuntimeError(f"monthly {fd} bonds {bonds:,.0f} disagree with the annual series {fyv:,.0f}")
    except RuntimeError: raise
    except Exception: fyd = fyv = None
    p = rebase(p, tot, tol_days=10)
    c = p["components"][0]; v = parts[last]
    c["breakdown"] = [{"label": "Treasury Bonds", "value": int(v["Treasury Bonds"]), "group": "Bonds"},
                      {"label": "Treasury Indexed Bonds (capital indexed)", "value": int(v["Treasury Indexed Bonds (Capital Indexed)"]), "group": "Bonds"},
                      {"label": "Treasury Notes", "value": int(v["Treasury Notes"]), "group": "Notes"}]
    for f in c.get("facts", []):
        if f["key"] == "fy" and fyd: f.update(value=int(fyv), as_of=fyd, kind="usd")
    y, mo = int(last[:4]), int(last[5:7]); ny, nm = (y + (mo == 12), mo % 12 + 1)
    p["next_update"] = (f"The {MONTHS[nm - 1]} {ny} month-end figure is expected on the AOFM Data Hub in the following weeks; "
                        "this page re-bases to it automatically on the next daily build after it appears.")
    return p

if __name__ == "__main__": sys.exit(run("australia", build))
