#!/usr/bin/env python3
"""Quarterly re-base of places/nigeria.json from the Debt Management Office (DMO) "Nigeria's Total Public Debt as at <date>" PDF, which states the
total public debt (federal government, states and the FCT; domestic + external) in US$ million and N million, plus the federal-government-only rows.
Every quarter-end PDF listed on dmo.gov.ng within the last ~13 months is read; the trend is the change over the latest twelve months.
Never invents a number: the rows must add up (domestic + external = total), otherwise the file is left untouched (exit 0)."""
import re, sys, datetime as dt
from place_util import *

LIST = "https://www.dmo.gov.ng/debt-profile/total-public-debt?filter=&limit=50&limitstart=0&sort=title"
BASE = "https://www.dmo.gov.ng"
M = 10**6
LINK = re.compile(r'href="(/\d+-nigeria-s-total-public-debt(?:-stock)?-as-at-([a-z]+)-(\d{1,2})-(\d{4})/file)"', re.I)
NUM = r"([\d,]+\.\d+)"

def read(pdf):
    t = pdf_text(pdf)
    def row(label, nth=0):
        ms = re.findall(label + r"[^\n\d]*?" + NUM + r"\s+" + NUM, t)
        if len(ms) <= nth: raise RuntimeError(f"row {label!r} not found")
        return float(ms[nth][1].replace(",", "")) * M
    ext, dom, tot = row(r"Total External Debt"), row(r"Total Domestic Debt"), row(r"Total Public Debt\s*\(A\+B\)")
    if abs(ext + dom - tot) > 0.02 * M * 1000: raise RuntimeError("external + domestic != total")
    fgn_ext, fgn_dom = row(r"FGN Only", 0), row(r"FGN Only", 1)
    fx = re.search(r"Exchange Rate of US\$\s*1\s*/\s*N\s*([\d,.]+)", t)
    return tot, dom, ext, fgn_dom, fgn_ext, (float(fx.group(1).replace(",", "")) if fx else None)

def build(p):
    html_ = get(LIST, ua=BROWSER_UA)
    found = {}
    for href, mon, day, year in LINK.findall(html_):
        try: mi = [m.lower() for m in MONTHS].index(mon.lower()) + 1
        except ValueError: continue
        found[f"{int(year):04d}-{mi:02d}-{int(day):02d}"] = BASE + href
    if len(found) < 4: raise RuntimeError(f"only {len(found)} DMO releases found")
    last = max(found); cut = (d(last) - dt.timedelta(days=420)).isoformat()
    series, detail = {}, {}
    for a in sorted(x for x in found if x >= cut):
        try: detail[a] = read(get(found[a], ua=BROWSER_UA, raw=True))
        except Exception as e: print(f"nigeria: {a}: {e}"); continue
        series[a] = detail[a][0]
    if last not in series: raise RuntimeError("latest DMO release could not be read")
    p = rebase(p, series, tol_days=40)
    tot, dom, ext, fdom, fext, fx = detail[last]; c = p["components"][0]
    c["source_url"] = found[last]
    c["breakdown"] = [{"label": "Domestic debt (federal, states and FCT)", "value": int(dom), "group": "Domestic"},
                      {"label": "External debt (federal, states and FCT; converted at the CBN official rate)", "value": int(ext), "group": "External"}]
    for f in c.get("facts", []):
        if f.get("key") == "fgn": f.update(value=int(fdom + fext), as_of=last)
    y, mo = int(last[:4]), int(last[5:7]) + 3
    if mo > 12: y, mo = y + 1, mo - 12
    p["next_update"] = f"The next quarter-end position ({MONTHS[mo - 1]} {y}) is expected from the Debt Management Office roughly three months after the quarter ends; this page re-bases to it automatically on the next daily build after it appears."
    return p

if __name__ == "__main__": sys.exit(run("nigeria", build))
