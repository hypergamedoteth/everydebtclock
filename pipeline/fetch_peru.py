#!/usr/bin/env python3
"""Re-base of places/peru.json from the Banco Central de Reserva del Perú (BCRP) statistical database, series PN03371FQ "Saldo de la deuda del sector público
no financiero" (million soles, quarter-end, gross public debt), through the BCRP's open JSON API. Never invents a number: any error leaves the file untouched (exit 0)."""
import json, re, sys
from place_util import *

API = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api/PN03371FQ/json/2023-1/2099-4/ing"
M = 10**6

def build(p):
    d = json.loads(get(API, ua=BROWSER_UA))
    series = {}
    for r in d["periods"]:
        m = re.fullmatch(r"Q([1-4])\.(\d\d)", r["name"]); v = r["values"][0]
        if not m or v in (None, "", "n.d."): continue
        series[month_end(2000 + int(m.group(2)), 3 * int(m.group(1)))] = float(v) * M
    if len(series) < 6: raise RuntimeError("fewer than six quarters")
    p = rebase(p, series, tol_days=20, keep_months=14)
    p["next_update"] = "The BCRP adds each quarter-end position to its statistical database a few weeks after the quarter ends; this page re-bases to it automatically on the next daily build after it appears."
    return p

if __name__ == "__main__": sys.exit(run("peru", build))
