#!/usr/bin/env python3
"""Quarterly re-base of places/singapore.json from SingStat Table Builder, table M130181
"Government Debt, (End Of Period), Quarterly" (source: Accountant-General's Department and Monetary Authority of Singapore).
Official, keyless, machine-readable: https://tablebuilder.singstat.gov.sg/api/table/tabledata/M130181

Series used (S$ million, quarter-end):
  1      Total Government Debt          <- the ticking hero, the closest Singapore measure to US Total Public Debt Outstanding
  1.1.4  Issued For Non-Spending Purposes   (shown as a fact)
  1.1.5  Issued For Spending Purposes       (shown as a fact)
  seven leaf instruments (the breakdown); they must add up to the total.
The trend is the official change over the latest four quarters (same quarter a year earlier -> latest quarter).

Rule: never invent a number. Any fetch error, a missing series, a breakdown that doesn't add up to the total, or data older than
what the file already has leaves places/singapore.json untouched (exit 0 so the rest of the daily run continues).
"""
import json, os, re, sys, calendar, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "places", "singapore.json")
URL = "https://tablebuilder.singstat.gov.sg/api/table/tabledata/M130181"
TOTAL, NONSPEND, SPEND = "1", "1.1.4", "1.1.5"
LEAVES = [("1.1.4.1.1", "Singapore Government Securities (Market Development)", "Not spent: publicly held"),
          ("1.1.4.1.2", "Treasury Bills and Cash Management Treasury Bills", "Not spent: publicly held"),
          ("1.1.4.1.3", "Singapore Savings Bonds", "Not spent: publicly held"),
          ("1.1.4.2.1", "Special Singapore Government Securities (mainly CPF) and advance deposits", "Not spent: held by CPF Board and MAS"),
          ("1.1.4.2.2", "Reserves Management Government Securities (MAS)", "Not spent: held by CPF Board and MAS"),
          ("1.1.5.1.1", "Singapore Government Securities (Infrastructure)", "Issued to fund infrastructure spending"),
          ("1.1.5.1.2", "Green Singapore Government Securities (Infrastructure)", "Issued to fund infrastructure spending")]
M = 1_000_000

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 everydebtclock.com", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as r: return json.loads(r.read().decode("utf-8"))

def qend(k):  # "2026 2Q" -> 2026-06-30
    m = re.fullmatch(r"(\d{4}) ([1-4])Q", k)
    if not m: raise RuntimeError(f"bad quarter key {k!r}")
    y, q = int(m.group(1)), int(m.group(2)); mo = q * 3
    return f"{y:04d}-{mo:02d}-{calendar.monthrange(y, mo)[1]:02d}"

def rebase(p, data):
    rows = {r["seriesNo"]: r for r in data["row"]}
    need = [TOTAL, NONSPEND, SPEND] + [s for s, _, _ in LEAVES]
    for s in need:
        if s not in rows: raise RuntimeError(f"series {s} missing")
    if "Million" not in rows[TOTAL].get("uoM", ""): raise RuntimeError("unit is not millions: " + rows[TOTAL].get("uoM", ""))
    ser = {s: {c["key"]: c["value"] for c in rows[s]["columns"]} for s in need}
    keys = sorted((k for k in ser[TOTAL] if re.fullmatch(r"\d{4} [1-4]Q", k) and all(ser[s].get(k) not in (None, "", "-") for s in need)), key=lambda k: (k[:4], k[5]))
    if len(keys) < 9: raise RuntimeError(f"need 9 complete quarters, got {len(keys)}")
    last, prior = keys[-1], keys[-5]
    if qend(prior)[5:7] != qend(last)[5:7] or int(qend(prior)[:4]) != int(qend(last)[:4]) - 1: raise RuntimeError("prior quarter is not 4 quarters back")
    v = lambda k, s: int(round(float(ser[s][k]) * M / 1000)) * 1000  # S$ million with one decimal -> whole S$ (exact to S$100k)
    tot = v(last, TOTAL)
    if abs(sum(v(last, s) for s, _, _ in LEAVES) - tot) > 1 * M: raise RuntimeError("instruments do not add up to the total")
    if abs(v(last, NONSPEND) + v(last, SPEND) - tot) > 1 * M: raise RuntimeError("spending + non-spending does not add up to the total")
    c = p["components"][0]
    as_of = qend(last)
    if as_of < c["as_of"]: raise RuntimeError(f"SingStat quarter {as_of} older than file {c['as_of']}")
    c.update(value=tot, as_of=as_of, prior_value=v(prior, TOTAL), prior_as_of=qend(prior),
             history=[[qend(k), v(k, TOTAL)] for k in keys[-9:]])
    c["breakdown"] = [{"label": lab, "value": v(last, s), "group": g} for s, lab, g in LEAVES if v(last, s)]
    for f in c.get("facts", []):
        if f.get("key") in ("nonspend", "spend"):
            s = NONSPEND if f["key"] == "nonspend" else SPEND
            f.update(value=v(last, s), as_of=as_of)
            f["note"] = f["note"].split(" A year earlier")[0].strip() + f" A year earlier ({qend(prior)}) it was S${v(prior, s) / 1e9:,.1f} billion; it is now {100 * v(last, s) / tot:.1f}% of the total."
    y, q = int(last[:4]), int(last[5]); ny, nq = (y + (q == 4), q % 4 + 1)
    p["next_update"] = (f"The Q{nq} {ny} quarter-end figure is expected roughly six weeks after the quarter ends; "
                        "this page re-bases to it automatically on the next daily build after it appears.")
    return p

def main():
    p = json.load(open(PATH))
    try:
        new = rebase(json.loads(json.dumps(p)), get(URL)["Data"])
    except Exception as e:
        print("singapore: not updated:", e); return 0
    if new != p:
        json.dump(new, open(PATH, "w"), indent=1, ensure_ascii=False); open(PATH, "a").write("\n")
        c = new["components"][0]; print(f"singapore: {c['as_of']} S${c['value']:,} (prior {c['prior_as_of']} S${c['prior_value']:,})")
    else: print("singapore: unchanged")
    return 0

if __name__ == "__main__": sys.exit(main())
