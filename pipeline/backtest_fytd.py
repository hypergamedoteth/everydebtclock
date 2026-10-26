#!/usr/bin/env python3
"""Backtest the FYTD projections the daily check validates: project each DTS record from the previous one,
compare with the official FYTD value. Compares the old 90-day average pace with pipeline/seasonal.py.
Usage: python3 pipeline/backtest_fytd.py [history.json]   (default: cache/dts_daily.json)"""
import json, os, sys, datetime as dt, statistics as st
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seasonal as SEA
p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "cache", "dts_daily.json")
rows = json.load(open(p)); rows = rows.get("data", rows)
H = SEA.History(rows); D = H.dates
RA, RB = float(os.environ.get("RA", 0.8238)), float(os.environ.get("RB", 0.8972))   # budget/cash ratios (cancel for rev/out)
fy = lambda s: (lambda d: d.year + 1 if d.month >= 10 else d.year)(dt.date.fromisoformat(s))
def fytd(k, d):  # FYTD cash at record d
    y = fy(d); start = f"{y-1}-09-30"
    return H.flow(k, start, d)
def old(k, d, n):
    d0 = dt.date.fromisoformat(d); return H.flow(k, d0 - dt.timedelta(90), d0) / 90 * (dt.date.fromisoformat(n) - d0).days
def new(k, d, n):
    d0, n0 = dt.date.fromisoformat(d), dt.date.fromisoformat(n)
    return SEA.expected_interest(H, d0, n0) if k == "int" else SEA.expected_flow(H, k, d0, n0)
res = {"old": [], "new": []}
for i in range(1, len(D)):
    d, n = D[i - 1], D[i]
    if fy(d) != fy(n) or not SEA.has_year_history(H, dt.date.fromisoformat(d)): continue
    if n < "2023-10-01": continue
    a = {k: fytd(k, n) for k in ("rev", "out", "int")}
    for name, f in (("old", old), ("new", new)):
        p_ = {k: fytd(k, d) + f(k, d, n) for k in ("rev", "out", "int")}
        e = lambda k: (p_[k] - a[k]) / abs(a[k]) * 100 if a[k] else 0.0
        dp, da = RB * p_["out"] - RA * p_["rev"], RB * a["out"] - RA * a["rev"]
        res[name].append((n, e("rev"), e("out"), (dp - da) / abs(da) * 100 if da else 0.0, e("int")))
THR = (3.0, 3.0, 3.0, 10.0)
for lab, sel in (("all", lambda n: True), ("Oct", lambda n: n[5:7] == "10"), ("Oct-Dec", lambda n: n[5:7] in ("10", "11", "12")), ("Jan-Sep", lambda n: n[5:7] not in ("10", "11", "12"))):
    for name in ("old", "new"):
        S = [r for r in res[name] if sel(r[0])]
        if not S: continue
        cells = " ".join(f"{m}: mean|e| {st.mean(abs(r[j]) for r in S):5.2f}% over-thr {sum(abs(r[j]) > THR[j-1] for r in S) / len(S) * 100:5.1f}% |"
                         for j, m in ((1, "revenue"), (2, "spending"), (3, "deficit"), (4, "interest_cash")))
        print(f"{lab:8} {name:3} n={len(S):3} {cells}")
print("recent (new):", [(r[0], *[round(x, 2) for x in r[1:]]) for r in res["new"][-6:]])
print("recent (old):", [(r[0], *[round(x, 2) for x in r[1:]]) for r in res["old"][-6:]])
