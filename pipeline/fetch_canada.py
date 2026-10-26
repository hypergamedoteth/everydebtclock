#!/usr/bin/env python3
"""Monthly re-base of places/canada.json from the Bank of Canada Valet API (official, keyless, machine-readable).

Series (Bank of Canada, "Government of Canada direct securities and loans: Distribution of holdings", month-end, C$ millions):
  V42141673  Total securities outstanding (inflation adjusted)   <- the ticking hero, closest to US Total Public Debt Outstanding
  V37340     Total securities outstanding (par value)             <- shown as a fact
  holders (inflation adjusted): V42141663 Bank of Canada, V37363 Government of Canada accounts,
  general public: V37377 treasury bills, V37323 Canada Bills (US$), V42141666 marketable bonds (inflation adjusted), V37295 retail debt
  FXUSDCAD   daily USD/CAD, for the "in US dollars" note.
A Valet date YYYY-MM-01 is that month's month-end figure. The trend is the official change over the latest 12 months
(same month a year earlier -> latest month): month-to-month changes swing with bond maturities and T-bill rollovers.

Rule: never invent a number. Any fetch error, a missing series, holders that don't add up to the total, or data older than
what the file already has leaves places/canada.json untouched (exit 0 so the rest of the daily run continues).
"""
import json, os, sys, calendar, datetime as dt, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "places", "canada.json")
VALET = "https://www.bankofcanada.ca/valet/observations"
TOTAL, PAR = "V42141673", "V37340"
HOLDERS = [("V42141663", "Bank of Canada (inflation adjusted)", "Holders"),
           ("V37363", "Government of Canada accounts", "Holders"),
           ("V37377", "General public: treasury bills", "Holders"),
           ("V37323", "General public: Canada Bills issued in US dollars", "Holders"),
           ("V42141666", "General public: marketable bonds and notes (inflation adjusted)", "Holders"),
           ("V37295", "General public: retail debt", "Holders")]
M = 1_000_000

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 everydebtclock.com", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read().decode("utf-8"))

def month_end(d):
    y, m = int(d[:4]), int(d[5:7]); return f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"

def rebase(p, obs, fx):
    ser = [TOTAL, PAR] + [s for s, _, _ in HOLDERS]
    rows = [o for o in obs if all(o.get(s, {}).get("v") not in (None, "") for s in ser)]
    rows.sort(key=lambda o: o["d"])
    if len(rows) < 13: raise RuntimeError(f"need 13 complete months, got {len(rows)}")
    last, prior = rows[-1], rows[-13]
    v = lambda o, s: int(round(float(o[s]["v"]))) * M
    if int(prior["d"][:4]) != int(last["d"][:4]) - 1 or prior["d"][5:7] != last["d"][5:7]: raise RuntimeError("prior month is not 12 months back")
    hs = sum(v(last, s) for s, _, _ in HOLDERS)
    if abs(hs - v(last, TOTAL)) > 5 * M: raise RuntimeError(f"holders {hs} != total {v(last, TOTAL)}")
    c = p["components"][0]
    as_of = month_end(last["d"])
    if as_of < c["as_of"]: raise RuntimeError(f"Valet month {as_of} older than file {c['as_of']}")
    c.update(value=v(last, TOTAL), as_of=as_of, prior_value=v(prior, TOTAL), prior_as_of=month_end(prior["d"]),
             history=[[month_end(o["d"]), v(o, TOTAL)] for o in rows[-13:]])
    c["breakdown"] = [{"label": lab, "value": v(last, s), "group": g} for s, lab, g in HOLDERS if v(last, s)]
    for f in c.get("facts", []):
        if f.get("key") == "par":
            f.update(value=v(last, PAR), as_of=as_of)
            f["note"] = (f"The same securities at face value, without the inflation adjustment on Real Return Bonds "
                         f"(Bank of Canada series {PAR}); {month_end(prior['d'])}: C${v(prior, PAR) / 1e9:,.1f} billion.")
    if fx:
        d_, r_ = fx
        p["hero_extra"] = [{"label": f"Official figure in US$ (BoC rate {d_}: {r_:.4f})", "value": f"US${v(last, TOTAL) / r_ / 1e12:,.3f} trillion"}]
        p["fx_note"] = {"date": d_, "usdcad": r_}
    y, m = int(as_of[:4]), int(as_of[5:7]); ny, nm = (y + (m == 12), m % 12 + 1); ay, am = (ny + (nm == 12), nm % 12 + 1)
    p["next_update"] = (f"The {calendar.month_name[nm]} {ny} month-end figure is expected in early {calendar.month_name[am]} {ay}; "
                        "this page re-bases to it automatically on the next daily build after it appears.")
    return p

def main():
    p = json.load(open(PATH))
    try:
        obs = get(f"{VALET}/{','.join([TOTAL, PAR] + [s for s, _, _ in HOLDERS])}/json?recent=24")["observations"]
        try:
            fo = get(f"{VALET}/FXUSDCAD/json?recent=5")["observations"][-1]; fx = (fo["d"], float(fo["FXUSDCAD"]["v"]))
        except Exception as e:
            print("canada: FX unavailable, keeping old note:", e); fx = None
        new = rebase(json.loads(json.dumps(p)), obs, fx)
    except Exception as e:
        print("canada: not updated:", e); return 0
    if new != p:
        json.dump(new, open(PATH, "w"), indent=1, ensure_ascii=False); open(PATH, "a").write("\n")
        c = new["components"][0]; print(f"canada: {c['as_of']} C${c['value']:,} (prior {c['prior_as_of']} C${c['prior_value']:,})")
    else: print("canada: unchanged")
    return 0

if __name__ == "__main__": sys.exit(main())
