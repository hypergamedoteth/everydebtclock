#!/usr/bin/env python3
"""Cheap gate for the frequent afternoon checks: is there a Debt to the Penny record newer than the committed data?

Compares Treasury's latest record_date with data/data.json (debt_total as_of). Writes
changed=true|false, latest=, committed= to $GITHUB_OUTPUT (or stdout) and always exits 0,
so a no-change run ends green without fetching, committing or deploying. If Treasury can't
be reached it reports changed=false; the next check (or the full 21:45 UTC run) retries.
"""
import json, os, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny"
       "?sort=-record_date&page%5Bsize%5D=1&fields=record_date")

def committed():
    try:
        d = json.load(open(os.path.join(ROOT, "data", "data.json")))
        return (d.get("tickers", {}).get("debt_total") or {}).get("as_of")
    except Exception:
        return None

def latest():
    req = urllib.request.Request(URL, headers={"User-Agent": "everydebtclock-check/1.0", "Accept": "application/json"})
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)["data"][0]["record_date"]
        except Exception as e:
            err = e
    print(f"::warning::Treasury check failed: {err}", file=sys.stderr)
    return None

c, l = committed(), latest()
changed = bool(l) and l != c
out = f"changed={'true' if changed else 'false'}\nlatest={l or ''}\ncommitted={c or ''}\n"
print(f"Treasury latest record_date={l} committed={c} -> {'new data, refreshing' if changed else 'no change, skipping fetch/commit/deploy'}")
if os.environ.get("GITHUB_OUTPUT"):
    open(os.environ["GITHUB_OUTPUT"], "a").write(out)
