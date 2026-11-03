#!/usr/bin/env python3
"""Re-base of places/thailand.json from the Public Debt Management Office (PDMO), Ministry of Finance: the monthly "Public Debt Status Summary" PDFs listed on
https://www.pdmo.go.th/en/monthly-public-debt-report. Each states "At the end of <month> <year>, Thailand's public debt amounted to X million Baht" (government debt,
state-owned enterprise debt, government-guaranteed financial SOE debt and government agency debt). The PDMO page lists only the latest few months; the place file keeps
the history it has already read, so the trend window grows from the first read. Never invents a number: any error leaves the file untouched (exit 0)."""
import re, sys
from place_util import *

URL = "https://www.pdmo.go.th/en/monthly-public-debt-report"
RX = re.compile(r"At the end of ([A-Za-z]+) (\d{4}),? Thailand.s public debt amounted to ([\d,]+(?:\.\d+)?) million Baht", re.I)
M = 10**6

def build(p):
    html = get(URL, ua=BROWSER_UA)
    links = sorted(set(re.findall(r'https://[^"\\ ]+\.pdf', html)))
    series = {}
    for l in links:
        try: t = re.sub(r"\s+", " ", pdf_text(get(l, ua=BROWSER_UA, raw=True)))
        except Exception: continue
        m = RX.search(t)
        if m and m.group(1).capitalize() in MONTHS:
            series[month_end(int(m.group(2)), MONTHS.index(m.group(1).capitalize()) + 1)] = float(m.group(3).replace(",", "")) * M
    if len(series) < 3: raise RuntimeError(f"only {len(series)} monthly summaries read")
    p = rebase(p, series, tol_days=300, keep_months=30, hist_monthly=True)
    p["next_update"] = "The PDMO publishes the Public Debt Status Summary at the end of the following month; this page re-bases to it automatically on the next daily build after it appears."
    return p

if __name__ == "__main__": sys.exit(run("thailand", build))
