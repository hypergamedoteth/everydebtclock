#!/usr/bin/env python3
"""Re-base of places/saudi-arabia.json from the National Debt Management Center (NDMC, Ministry of Finance) "Reports & Statistics" page, which states
"As at end of <month> <year>, Saudi Arabia's total outstanding direct indebtedness amounted to SAR X billion ... SAR D billion of domestic ... SAR E billion of external".
Every period stated there is read, plus the latest quarter-end table (loaded through the page year facet: domestic and external SAR billion). The page lists year-end and the latest quarter-ends only, so the trend is the change from the closest listed point to twelve months earlier (within 200 days) and the page says which dates it compares. Never invents a number; any error leaves the file untouched."""
import re, sys, html
from place_util import *

URL = "https://www.ndmc.gov.sa/en/reports-and-statistics"
B = 10**9
RX = re.compile(r"As at end of ([A-Za-z]+) (\d{4}),? Saudi Arabia[’']s total outstanding direct indebtedness amounted to SAR ([\d,.]+) billion", re.I)

def text(url):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", get(url, ua=BROWSER_UA)))).replace("\u200b", "")

def build(p):
    raw = get(URL, ua=BROWSER_UA)
    t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).replace("\u200b", "")
    series = {}
    for m in RX.finditer(t):
        series[month_end(int(m.group(2)), MONTHS.index(m.group(1).capitalize()) + 1)] = float(m.group(3).replace(",", "")) * B
    if len(series) < 6: raise RuntimeError(f"NDMC: only {len(series)} statements found")
    # the page's period table (latest quarter-end) is loaded through its year facet; domestic + external = total
    terms = sorted({x for ids in re.findall(r'data-term-ids="([^"]*)"', raw) for x in ids.split(",") if re.fullmatch(r"20\d{12}", x)})
    dom = ext = None
    if terms:
        term = terms[-1]; a = month_end(int(term[:4]), int(term[4:6]))
        tt = text(URL + "?totalDebt=" + term)
        g = lambda lab: re.search(r"([\d,.]+) " + re.escape(lab), tt)
        d, e, tot = g("Government's total domestic indebtedness (SAR)"), g("Government's total external indebtedness (SAR)"), g("Indebtedness Outstanding at End of Period")
        if d and e and tot:
            dom, ext, total = (float(x.group(1).replace(",", "")) * B for x in (d, e, tot))
            if abs(dom + ext - total) > 1.0 * B: raise RuntimeError("NDMC: domestic + external do not add up to the total")
            series[a] = dom + ext
    last = max(series)
    import datetime as dt
    cut = (dt.date.fromisoformat(last) - dt.timedelta(days=250)).isoformat()      # compare with the most recent listed year-end, not an older one
    p = rebase(p, {a: v for a, v in series.items() if a >= cut}, tol_days=200, keep_months=30)
    c = p["components"][0]
    if dom and ext and last == a:
        c["breakdown"] = [{"label": "Domestic debt", "value": int(dom), "group": "Domestic"}, {"label": "External debt", "value": int(ext), "group": "External"}]
    p["next_update"] = "The National Debt Management Center adds each quarter-end position to its Reports & Statistics page after the quarter ends; this page re-bases to it automatically on the next daily build after it appears."
    return p

if __name__ == "__main__": sys.exit(run("saudi-arabia", build))
