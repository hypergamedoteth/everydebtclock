#!/usr/bin/env python3
"""Monthly re-base of places/brazil.json from the Banco Central do Brasil open-data API (SGS):
  series 13761  Gross general government debt (DBGG), balance, R$ million, month-end     <- the ticking hero
  series 13762  Gross general government debt (DBGG), % of GDP                           <- shown as a fact
Official, keyless: https://api.bcb.gov.br/dados/serie/bcdata.sgs.13761/dados/ultimos/14?formato=json
The trend is the official change over the latest twelve months.

Rule: never invent a number. Any fetch error, an unreadable or non-consecutive series, or data older than what the file already
has leaves places/brazil.json untouched (exit 0 so the rest of the daily run continues).
"""
import json, os, sys, calendar, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "places", "brazil.json")
URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.%d/dados/ultimos/%d?formato=json"
MI = 1_000_000

def get(code, n):
    req = urllib.request.Request(URL % (code, n), headers={"User-Agent": "Mozilla/5.0 everydebtclock.com", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as r: rows = json.loads(r.read().decode("utf-8"))
    out = {}
    for r in rows:
        d, mth, y = r["data"].split("/")                      # dd/mm/yyyy, the first of the reference month
        y, mth = int(y), int(mth)
        out[f"{y:04d}-{mth:02d}-{calendar.monthrange(y, mth)[1]:02d}"] = float(r["valor"])
    return out

def rebase(p, debt, pct):
    ds = sorted(debt)
    if len(ds) < 13: raise RuntimeError(f"need 13 months, got {len(ds)}")
    ds = ds[-13:]
    for a, b in zip(ds, ds[1:]):                                 # consecutive months only
        if (int(b[:4]) * 12 + int(b[5:7])) - (int(a[:4]) * 12 + int(a[5:7])) != 1: raise RuntimeError(f"gap between {a} and {b}")
    last, prior = ds[-1], ds[0]
    c = p["components"][0]
    if last < c["as_of"]: raise RuntimeError(f"BCB month {last} older than file {c['as_of']}")
    r = lambda x: int(round(x * MI))                              # R$ million with two decimals -> whole reais
    c.update(value=r(debt[last]), as_of=last, prior_value=r(debt[prior]), prior_as_of=prior, history=[[d, r(debt[d])] for d in ds])
    for f in c.get("facts", []):
        if f.get("key") == "pctgdp":
            if last not in pct or prior not in pct: raise RuntimeError("DBGG % of GDP missing for the latest or prior month")
            f.update(value=pct[last], as_of=last, kind="pct")
            f["note"] = f["note"].split(" A year earlier")[0].strip() + f" A year earlier ({prior}) it was {pct[prior]:.2f}% of GDP."
    y, m = int(last[:4]), int(last[5:7]); ny, nm = (y + (m == 12), m % 12 + 1)
    names = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    p["next_update"] = (f"The {names[nm - 1]} {ny} month-end figure is expected from the Banco Central do Brasil about a month after the month ends; "
                        "this page re-bases to it automatically on the next daily build after it appears.")
    return p

def main():
    p = json.load(open(PATH))
    try: new = rebase(json.loads(json.dumps(p)), get(13761, 14), get(13762, 14))
    except Exception as e:
        print("brazil: not updated:", e); return 0
    if new != p:
        json.dump(new, open(PATH, "w"), indent=1, ensure_ascii=False); open(PATH, "a").write("\n")
        c = new["components"][0]; print(f"brazil: {c['as_of']} R${c['value']:,} (prior {c['prior_as_of']} R${c['prior_value']:,})")
    else: print("brazil: unchanged")
    return 0

if __name__ == "__main__": sys.exit(main())
