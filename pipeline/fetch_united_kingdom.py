#!/usr/bin/env python3
"""Monthly re-base of places/united-kingdom.json from the Office for National Statistics public sector finances time series
(official, keyless JSON: https://www.ons.gov.uk/<series page>/data).

Series (ONS dataset PUSF, public sector finances, month-end):
  BKPX  GG: General government consolidated gross debt (Maastricht), £ million  <- the ticking hero: gross, like the US Total Public Debt Outstanding
  HF6W  PS: Net debt (excluding public sector banks), £ billion                 <- shown as a fact (the headline "PSND")
  CPPH  Public sector: PSND (ex PS banks ex BoE), £ billion                     <- shown as a fact
The trend is the official change over the latest 12 months (same month a year earlier -> latest month).

Rule: never invent a number. Any fetch error, a missing series, series that end in different months, or data older than what the
file already has leaves places/united-kingdom.json untouched (exit 0 so the rest of the daily run continues).
"""
import json, os, sys, calendar, datetime as dt, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "places", "united-kingdom.json")
BASE = "https://www.ons.gov.uk/economy/governmentpublicsectorandtaxes/publicsectorfinance/timeseries"
TOTAL, PSND, PSND_EXBOE = "bkpx", "hf6w", "cpph"
MON = {m.upper(): i for i, m in enumerate(calendar.month_abbr) if m}

def get(s):
    req = urllib.request.Request(f"{BASE}/{s}/pusf/data", headers={"User-Agent": "Mozilla/5.0 everydebtclock.com", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as r: return json.loads(r.read().decode("utf-8"))

def month_end(label):  # "2026 SEP" -> 2026-09-30
    y, m = label.split(); y, mo = int(y), MON[m]
    return f"{y:04d}-{mo:02d}-{calendar.monthrange(y, mo)[1]:02d}"

def series(d, unit_mult):
    out = {}
    for r in d["months"]:
        if r.get("value") not in (None, ""): out[month_end(r["date"])] = int(round(float(r["value"]) * unit_mult))
    return out

def rebase(p, tot, psnd, exboe):
    ds = sorted(tot)
    if len(ds) < 13: raise RuntimeError("need 13 months")
    last = ds[-1]; prior = ds[-13]
    if int(prior[:4]) != int(last[:4]) - 1 or prior[5:7] != last[5:7]: raise RuntimeError("prior month is not 12 months back or a month is missing")
    for name, s in (("PSND", psnd), ("PSND ex BoE", exboe)):
        if last not in s: raise RuntimeError(f"{name} has no figure for {last}")
    c = p["components"][0]
    if last < c["as_of"]: raise RuntimeError(f"ONS month {last} older than file {c['as_of']}")
    hist = [d for d in ds[-13:]]
    if any(not (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days in range(28, 32) for a, b in zip(hist, hist[1:])): raise RuntimeError("gap in the 13 months")
    c.update(value=tot[last], as_of=last, prior_value=tot[prior], prior_as_of=prior, history=[[d, tot[d]] for d in hist])
    for f in c.get("facts", []):
        s = {"psnd": psnd, "psnd_exboe": exboe}.get(f.get("key"))
        if s is not None:
            f.update(value=s[last], as_of=last)
            if prior in s: f["note"] = f["note"].split(" A year earlier")[0].strip() + f" A year earlier ({prior}) it was £{s[prior] / 1e9:,.1f} billion."
    y, m = int(last[:4]), int(last[5:7]); ny, nm = (y + (m == 12), m % 12 + 1)
    p["next_update"] = (f"The {calendar.month_name[nm]} {ny} month-end figure is expected in the ONS public sector finances release about three weeks after the month ends; "
                        "this page re-bases to it automatically on the next daily build after it appears.")
    return p

def main():
    p = json.load(open(PATH))
    try:
        new = rebase(json.loads(json.dumps(p)), series(get(TOTAL), 10**6), series(get(PSND), 10**9), series(get(PSND_EXBOE), 10**9))
    except Exception as e:
        print("united-kingdom: not updated:", e); return 0
    if new != p:
        json.dump(new, open(PATH, "w"), indent=1, ensure_ascii=False); open(PATH, "a").write("\n")
        c = new["components"][0]; print(f"united-kingdom: {c['as_of']} £{c['value']:,} (prior {c['prior_as_of']} £{c['prior_value']:,})")
    else: print("united-kingdom: unchanged")
    return 0

if __name__ == "__main__": sys.exit(main())
