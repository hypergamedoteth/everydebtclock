#!/usr/bin/env python3
"""Re-base of places/argentina.json from the Secretaría de Finanzas' monthly debt bulletins (Boletín mensual de deuda, Ministerio de Economía),
listed on https://www.argentina.gob.ar/economia/finanzas/datos-mensuales-de-la-deuda/informes-mensuales. Each bulletin's executive summary states
"el stock de deuda bruta ascendió a un monto total equivalente a USD<x> millones" (all figures in US dollars, converted at the last business day's rate).
The latest bulletin and the one about twelve months earlier are read. Never invents a number: any parse problem leaves the file untouched (exit 0)."""
import re, sys
from place_util import *

BASE = "https://www.argentina.gob.ar"
LIST = BASE + "/economia/finanzas/datos-mensuales-de-la-deuda/informes-mensuales"
ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
RX = re.compile(r"stock\s+de\s+deuda\s+bruta\s+ascendi[óo]\s+a\s+un\s+monto\s+total\s+equivalente\s+a\s+USD\s?([\d.]+)\s+millones", re.I)
M = 10**6

def value(url):
    t = re.sub(r"\s+", " ", pdf_text(get(url, ua=BROWSER_UA, raw=True)))
    m = RX.search(t)
    if not m: raise RuntimeError("no total in " + url)
    return float(m.group(1).replace(".", "")) * M

def build(p):
    html = get(LIST, ua=BROWSER_UA)
    links = {}
    for m in re.finditer(r'href="(/sites/default/files/informe_mensual_([a-z]+)-(20\d\d)[^"]*\.pdf)"', html):
        if m.group(2) in ES: links.setdefault((int(m.group(3)), ES.index(m.group(2)) + 1), m.group(1))
    if len(links) < 24: raise RuntimeError(f"only {len(links)} bulletins listed")
    latest = max(links); prior = (latest[0] - 1, latest[1])
    if prior not in links: raise RuntimeError(f"no bulletin for {prior}")
    series = {}
    for k in (prior, latest): series[month_end(*k)] = value(BASE + links[k])
    p = rebase(p, series, tol_days=20, keep_months=14)
    m = latest[1]
    p["next_update"] = "The Secretaría de Finanzas publishes the monthly debt bulletin in the weeks after each month ends; this page re-bases to it automatically on the next daily build after it appears."
    return p

if __name__ == "__main__": sys.exit(run("argentina", build))
