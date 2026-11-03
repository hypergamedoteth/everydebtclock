#!/usr/bin/env python3
"""Re-base of places/chile.json from the Dirección de Presupuestos (DIPRES) quarterly report "Reporte trimestral de deuda bruta del Gobierno Central"
(https://www.dipres.gob.cl/598/w3-propertyvalue-15500.html). Each report states "El stock de deuda bruta del Gobierno Central totalizó $X millones al
<day> de <month> de <year>" in Chilean pesos. The latest reports listed on the page are read (newest first) until a quarter about twelve months old is found.
Never invents a number: any error leaves the file untouched (exit 0)."""
import re, sys
from place_util import *

BASE = "https://www.dipres.gob.cl/598/"
PAGE = BASE + "w3-propertyvalue-15500.html"
ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
RX = re.compile(r"\$\s?(\d{1,3}(?:\.\d{3}){2,})\s+millones\s+al\s+(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(20\d\d)", re.I)
M = 10**6

def build(p):
    html = get(PAGE, ua=BROWSER_UA)
    links = []
    for l in re.findall(r'href="([^"]*articles-\d+_doc_pdf\.pdf[^"]*)"', html):
        if l not in links: links.append(l)
    if len(links) < 6: raise RuntimeError("few reports listed")
    series = {}
    for l in links[:5]:                                        # newest first: five quarters back
        m = RX.search(re.sub(r"\s+", " ", pdf_text(get(BASE + l, ua=BROWSER_UA, raw=True))))
        if not m or m.group(3).lower() not in ES: raise RuntimeError("no stock statement in " + l)
        series[month_end(int(m.group(4)), ES.index(m.group(3).lower()) + 1)] = float(m.group(1).replace(".", "")) * M
    if len(series) < 5: raise RuntimeError("fewer than five quarters read")
    p = rebase(p, series, tol_days=20, keep_months=14)
    p["next_update"] = "DIPRES publishes the quarterly debt report about three months after each quarter-end; this page re-bases to it automatically on the next daily build after it appears."
    return p

if __name__ == "__main__": sys.exit(run("chile", build))
