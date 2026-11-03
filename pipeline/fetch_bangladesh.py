#!/usr/bin/env python3
"""Re-base of places/bangladesh.json from the Finance Division's Quarterly Debt Bulletin (Ministry of Finance), listed on https://www.spfms.gov.bd/Home/DebtBulletin
(newest first). Table 6 "Government Debt Stock" gives total debt (domestic + external) in crore taka at each 30 June and at the latest quarter-end. The latest bulletin's
latest column and its 30 June figures are read; domestic + external must equal the total. Never invents a number: any error leaves the file untouched (exit 0)."""
import re, sys
from place_util import *

URL = "https://www.spfms.gov.bd/Home/DebtBulletin"
CR = 10**7
MON = {"March": 3, "June": 6, "September": 9, "December": 12}

def nums(t, label, n):
    m = re.search(label + r"((?:\s+[\d,]{5,}){%d})" % n, t)
    if not m: raise RuntimeError("row not found: " + label)
    return [float(x.replace(",", "")) * CR for x in m.group(1).split()]

def build(p):
    html = get(URL, ua=BROWSER_UA)
    first = re.search(r'href="(/uploads/publications/[^"]+\.pdf)"', html)
    if not first: raise RuntimeError("no bulletin listed")
    t = re.sub(r"\s+", " ", pdf_text(get("https://www.spfms.gov.bd" + first.group(1), ua=BROWSER_UA, raw=True)))
    i = t.find("Table 6: Government Debt Stock")
    if i < 0: raise RuntimeError("Table 6 not found")
    t = t[i:i + 2500]
    dom, ext, tot = nums(t, r"Domestic Debt \(1\+2\)", 5), nums(t, r"External Debt\*?", 5), nums(t, r"Total Debt \(A\+B\)", 5)
    if any(abs(a + b - c) > 25 * CR for a, b, c in zip(dom, ext, tot)): raise RuntimeError("domestic + external do not add up")   # the bulletin rounds its parts to the nearest 10 crore in places
    hdr = re.findall(r"As of (\d{1,2}) ([A-Za-z]+) (20\d\d)", t[:400])
    if len(hdr) != 5: raise RuntimeError("table header not read")
    series = {}
    for (dd, mo, yy), v in zip(hdr, tot):
        m = [k for k, n in MON.items() if k.lower().startswith(mo[:3].lower())]
        if not m: raise RuntimeError("unknown month " + mo)
        series[month_end(int(yy), MON[m[0]])] = v
    last = max(series)
    series = {a: v for a, v in series.items() if a >= month_end(int(last[:4]) - 1, 6)}      # latest quarter-end and the 30 June before it
    p = rebase(p, series, tol_days=100, keep_months=30)
    c = p["components"][0]
    c["breakdown"] = [{"label": "Domestic debt", "value": int(dom[4]), "group": "Domestic"}, {"label": "External debt", "value": int(ext[4]), "group": "External"}]
    p["next_update"] = "The Finance Division publishes the Quarterly Debt Bulletin some months after each quarter closes; this page re-bases to it automatically on the next daily build after it appears."
    return p

if __name__ == "__main__": sys.exit(run("bangladesh", build))
