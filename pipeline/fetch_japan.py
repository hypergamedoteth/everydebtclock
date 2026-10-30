#!/usr/bin/env python3
"""Quarterly re-base of places/japan.json from the Ministry of Finance Japan, "Central Government Debt" quarterly tables
(https://www.mof.go.jp/english/policy/jgbs/reference/gbb/e{YYYYMM}.html, amounts in 100 million yen, quarter-end).

Table 1 "Outstanding Government Bonds and Borrowings": Government Bonds + Borrowings + Financing Bills = Total.
  Total             <- the ticking hero (the MOF's national government debt figure: the closest Japanese measure to US Total Public Debt Outstanding)
  Government Bonds, Borrowings, Financing Bills <- the breakdown; they must add up to the total (the MOF notes figures may not add because of rounding)
  Government-guaranteed debts (table 2) <- shown as a fact, not added to the total
The trend is the official change over the latest four quarters.

Rule: never invent a number. Any fetch error, an unreadable table, a breakdown that doesn't add up, a gap in the quarters or data older
than what the file already has leaves places/japan.json untouched (exit 0 so the rest of the daily run continues).
"""
import json, os, re, sys, calendar, datetime, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "places", "japan.json")
BASE = "https://www.mof.go.jp/english/policy/jgbs/reference/gbb/e%s.html"
OKU = 100_000_000
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

def page(ym):
    req = urllib.request.Request(BASE % ym, headers={"User-Agent": "Mozilla/5.0 everydebtclock.com"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r: return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 404: return None
        raise

def qend_of(y, m): return f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"

def parse(html, y, m):
    want = f"As of {MONTHS[m - 1]} {calendar.monthrange(y, m)[1]}, {y}"
    if want not in html: raise RuntimeError(f"{y}-{m:02d}: page does not say '{want}'")
    row = lambda lab: re.search(r'<th[^>]*>\s*' + lab + r'\s*</th>\s*<td[^>]*>\s*([\d,]+)\s*</td>', html)
    out = {}
    for k, lab in (("bonds", "Government Bonds"), ("loans", "Borrowings"), ("bills", "Financing Bills"), ("total", "Total")):
        mm = row(lab)
        if not mm: raise RuntimeError(f"{y}-{m:02d}: row {lab} not found")
        out[k] = int(mm.group(1).replace(",", ""))
    g = re.search(r'Government - Guaranteed Debts\s*</th>\s*<td[^>]*>\s*([\d,]+)\s*</td>', html)
    out["guar"] = int(g.group(1).replace(",", "")) if g else None
    if abs(out["bonds"] + out["loans"] + out["bills"] - out["total"]) > 3: raise RuntimeError(f"{y}-{m:02d}: parts do not add up to the total")
    return out

def quarters_back(y, m, n):
    out = []
    for _ in range(n):
        out.append((y, m)); m -= 3
        if m < 1: m += 12; y -= 1
    return out

def rebase(p):
    today = datetime.date.today()
    y, m = today.year, (today.month - 1) // 3 * 3 + 3
    data, tries = {}, 0
    for (yy, mm) in quarters_back(y, m, 4):       # newest published quarter-end (a new page appears about six weeks after quarter-end)
        h = page(f"{yy}{mm:02d}")
        if h is not None: newest = (yy, mm); data[newest] = parse(h, yy, mm); break
    else: raise RuntimeError("no quarterly page found")
    for (yy, mm) in quarters_back(*newest, 9)[1:]:
        h = page(f"{yy}{mm:02d}")
        if h is None: raise RuntimeError(f"gap: no page for {yy}-{mm:02d}")
        data[(yy, mm)] = parse(h, yy, mm)
    qs = sorted(data)
    last, prior = qs[-1], qs[-5]
    c = p["components"][0]; as_of = qend_of(*last)
    if as_of < c["as_of"]: raise RuntimeError(f"MOF quarter {as_of} older than file {c['as_of']}")
    yen = lambda k, f: data[k][f] * OKU
    c.update(value=yen(last, "total"), as_of=as_of, prior_value=yen(prior, "total"), prior_as_of=qend_of(*prior),
             history=[[qend_of(*k), yen(k, "total")] for k in qs])
    c["breakdown"] = [{"label": lab, "value": yen(last, k), "group": g} for k, lab, g in
                      (("bonds", "Government bonds", "Bonds, loans and bills"), ("loans", "Borrowings", "Bonds, loans and bills"), ("bills", "Financing bills", "Bonds, loans and bills")) if data[last][k]]
    for f in c.get("facts", []):
        if f.get("key") == "guar" and data[last]["guar"] is not None and data[prior]["guar"] is not None:
            f.update(value=yen(last, "guar"), as_of=as_of)
            f["note"] = f["note"].split(" A year earlier")[0].strip() + f" A year earlier ({qend_of(*prior)}) it was ¥{yen(prior, 'guar') / 1e12:,.1f} trillion."
    ny, nm = (last[0] + (last[1] == 12), last[1] % 12 + 3)
    p["next_update"] = (f"The {MONTHS[nm - 1]} {ny} quarter-end figure is expected from the Ministry of Finance roughly six weeks after the quarter ends; "
                        "this page re-bases to it automatically on the next daily build after it appears.")
    return p

def main():
    p = json.load(open(PATH))
    try: new = rebase(json.loads(json.dumps(p)))
    except Exception as e:
        print("japan: not updated:", e); return 0
    if new != p:
        json.dump(new, open(PATH, "w"), indent=1, ensure_ascii=False); open(PATH, "a").write("\n")
        c = new["components"][0]; print(f"japan: {c['as_of']} ¥{c['value']:,} (prior {c['prior_as_of']} ¥{c['prior_value']:,})")
    else: print("japan: unchanged")
    return 0

if __name__ == "__main__": sys.exit(main())
