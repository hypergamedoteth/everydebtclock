#!/usr/bin/env python3
"""Quarterly re-base of places/switzerland.json from the Swiss Federal Finance Administration (EFV) GFS quarterly data (SDDS Plus):
  cgd_q-d.xlsx  "Schulden Bund", row "Bruttoschulden" = gross debt of the Confederation (central government), 1,000 CHF, quarter-end  <- hero
  ggd_q-d.xlsx  "Bruttoschulden Staat" = gross debt of general government (Confederation, cantons, municipalities, social security) <- fact
The trend is the official change over the latest four quarters. Never invents a number; any error leaves the file untouched (exit 0)."""
import re, sys, calendar
from place_util import *
import xlsx_min

BASE = "https://www.data.finance.admin.ch/static/assets/datasets/gfs_dashboard/"
REF = "https://www.efv.admin.ch/de/fs-daten"
PARTS = [("Bargeld und Einlagen", "Currency and deposits", "Deposits"), ("Schuldtitel", "Debt securities", "Debt securities"), ("Kredite", "Loans", "Loans"),
         ("Versicherungs-, Alterssicherungs", "Insurance and pension liabilities", "Other liabilities"), ("Sonstige Verbindlichkeiten", "Other liabilities (accounts payable and other)", "Other liabilities")]

def qend(k):
    m = re.fullmatch(r"(\d{4})-Q([1-4])", k.strip())
    if not m: return None
    y, q = int(m.group(1)), int(m.group(2)); return month_end(y, q * 3)

def sheet(name):
    wb = xlsx_min.read_bytes(get(BASE + name, ua=BROWSER_UA, raw=True, referer=REF))
    rows = next(iter(wb.values()))
    hdr = next(r for i, r in rows if (r.get("A") or "").endswith("CHF") and any(qend(v or "") for v in r.values()))
    cols = {c: qend(v) for c, v in hdr.items() if v and qend(v)}
    out = {}
    for i, r in rows:
        lab = (r.get("A") or "").strip()
        if lab and r is not hdr:
            out[lab] = {cols[c]: float(v) * 1000 for c, v in r.items() if c in cols and re.fullmatch(r"-?[\d.]+(?:[eE][-+]?\d+)?", v or "")}
    return out

def build(p):
    cg = sheet("cgd_q-d.xlsx"); gg = sheet("ggd_q-d.xlsx")
    tot = cg["Bruttoschulden"]
    last = max(tot)
    parts = []
    for key, label, group in PARTS:
        row = next((v for k, v in cg.items() if k.startswith(key)), None)
        if row is None or last not in row: raise RuntimeError(f"missing row {key}")
        parts.append((label, group, row[last]))
    if abs(sum(v for _, _, v in parts) - tot[last]) > 5e6: raise RuntimeError("components do not add up to gross debt")
    ggt = gg["Bruttoschulden"]
    if last not in ggt or ggt[last] < tot[last] * 0.9: raise RuntimeError("general government debt missing or implausible")
    p = rebase(p, tot, tol_days=15)
    c = p["components"][0]
    c["breakdown"] = [{"label": l, "value": int(round(v)), "group": g} for l, g, v in parts if v]
    debt_only = sum(v for l, g, v in parts if g in ("Deposits", "Debt securities", "Loans"))
    for f in c.get("facts", []):
        if f["key"] == "gg":
            prior = c["prior_as_of"]
            f.update(value=int(round(ggt[last])), as_of=last, kind="usd")
            f["note"] = f["note"].split(" A year earlier")[0].strip() + (f" A year earlier ({prior}) it was CHF {ggt[prior] / 1e9:,.1f} billion." if prior in ggt else "")
        if f["key"] == "borrowed": f.update(value=int(round(debt_only)), as_of=last, kind="usd")
    y, q = int(last[:4]), int(last[5:7]) // 3; ny, nq = (y + (q == 4), q % 4 + 1)
    p["next_update"] = (f"The Q{nq} {ny} quarter-end figure is expected from the Federal Finance Administration roughly three months after the quarter ends; "
                        "this page re-bases to it automatically on the next daily build after it appears.")
    return p

if __name__ == "__main__": sys.exit(run("switzerland", build))
