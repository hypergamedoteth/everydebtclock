#!/usr/bin/env python3
"""Full Debt to the Penny history for the downloadable /data files.

Treasury's dataset starts on 1993-04-01. This pulls every published row (total,
held by the public, intragovernmental) and caches it. The live clock keeps its
own short window in cache/debt_to_penny.json; this file does not feed that window.

    python3 pipeline/fetch_us_debt_history.py
"""
import json
import os
import time
import urllib.parse
import urllib.request
from decimal import Decimal, ROUND_HALF_UP

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "cache", "debt_to_penny_full.json")
API = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny"
PAGE = "https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/debt-to-the-penny"
SOURCE = "U.S. Department of the Treasury, Debt to the Penny"
FIELDS = "record_date,tot_pub_debt_out_amt,debt_held_public_amt,intragov_hold_amt"
UA = {"User-Agent": "EveryDebtClock/1.0 (history; +https://everydebtclock.com/data/)", "Accept": "application/json"}
CENT = Decimal("0.01")
# The public file begins on this date. A later start means rows were dropped.
SERIES_START = "1993-04-01"


def _get(url):
    last = None
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def _cents(raw):
    if raw is None or str(raw).strip().lower() in {"", "null", "none"}:
        return None
    return Decimal(str(raw)).quantize(CENT, rounding=ROUND_HALF_UP)


def _money(d):
    return f"{d:.2f}"


def download():
    """Every Debt to the Penny row, oldest first. Raises if the extract is short or the parts do not add up."""
    q = urllib.parse.urlencode({"fields": FIELDS, "sort": "record_date", "page[size]": 10000})
    url = f"{API}?{q}"
    payload = _get(url)
    rows = list(payload["data"])
    pages = int(payload["meta"]["total-pages"])
    for pg in range(2, pages + 1):
        rows += _get(f"{url}&page%5Bnumber%5D={pg}")["data"]
    if len(rows) < 8000:
        raise RuntimeError(f"Debt to the Penny history has {len(rows)} rows; expected the full series")
    out = []
    seen = set()
    for r in rows:
        day = r["record_date"]
        if day in seen:
            raise RuntimeError(f"duplicate Debt to the Penny date {day}")
        seen.add(day)
        total = _cents(r["tot_pub_debt_out_amt"])
        if total is None:
            raise RuntimeError(f"{day}: total public debt is blank")
        public = _cents(r["debt_held_public_amt"])
        intra = _cents(r["intragov_hold_amt"])
        if public is None or intra is None:
            if public is not None or intra is not None:
                raise RuntimeError(f"{day}: only one of the two debt parts is published")
            public_s = intra_s = equal = gap_s = ""
        else:
            gap = public + intra - total
            public_s, intra_s = _money(public), _money(intra)
            equal = "yes" if gap == 0 else "no"
            gap_s = "" if gap == 0 else _money(gap)
        out.append({
            "record_date": day,
            "total_public_debt_outstanding_usd": _money(total),
            "debt_held_by_the_public_usd": public_s,
            "intragovernmental_holdings_usd": intra_s,
            "parts_equal_total": equal,
            "parts_gap_usd": gap_s,
        })
    out.sort(key=lambda r: r["record_date"])
    if out[0]["record_date"] > SERIES_START:
        raise RuntimeError(f"series starts {out[0]['record_date']}, after the published start {SERIES_START}")
    if SERIES_START not in seen:
        raise RuntimeError(f"series is missing the published start {SERIES_START}")
    split = next((r["record_date"] for r in out if r["debt_held_by_the_public_usd"]), "")
    gaps = [{"record_date": r["record_date"], "parts_gap_usd": r["parts_gap_usd"]}
            for r in out if r["parts_equal_total"] == "no"]
    return {
        "source_name": SOURCE,
        "source_url": PAGE,
        "api_url": API,
        "components_start": split,
        "parts_gap_rows": gaps,
        "rows": out,
    }


def main():
    data = download()
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump({"fetched": time.time(), "data": data}, open(CACHE, "w"))
    rows = data["rows"]
    print(f"debt to the penny history: {len(rows)} rows, {rows[0]['record_date']} to {rows[-1]['record_date']}")
    if data["parts_gap_rows"]:
        print("published parts do not sum to the total on:", ", ".join(
            f"{g['record_date']} ({g['parts_gap_usd']})" for g in data["parts_gap_rows"]))


if __name__ == "__main__":
    main()
