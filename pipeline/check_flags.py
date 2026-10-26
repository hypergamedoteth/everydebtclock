#!/usr/bin/env python3
"""Exit non-zero if the latest data.json has validation flags or unavailable tickers (fails the CI run so GitHub emails you)."""
import json, sys, os
p = os.path.join(os.path.dirname(__file__), "..", "data", "data.json")
D = json.load(open(p))
flags = D.get("meta", {}).get("flags") or []
unavail = [k for k, t in D.get("tickers", {}).items() if t.get("status") == "unavailable"]
stale = [k for k, t in D.get("tickers", {}).items() if t.get("stale")]
print(f"flags={len(flags)} unavailable={len(unavail)} stale={len(stale)}")
if stale: print("stale (served from cache):", ", ".join(stale))
if flags or unavail:
    for f in flags: print("FLAG:", f)
    for u in unavail: print("UNAVAILABLE:", u)
    sys.exit(1)
