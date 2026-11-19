#!/usr/bin/env python3
"""Full US debt history for the public downloads.

Debt to the Penny, every record Treasury publishes (the series starts in 1993),
and Historical Debt Outstanding, the annual series. Amounts stay the strings
Treasury returned so cents are not rounded through a float.

Writes cache/debt_to_penny_history.json and cache/debt_outstanding_exact.json.
A failed fetch keeps the last good cache and exits 0 when that cache exists.
"""
import json, os, sys, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "cache")
FD = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
NOW = time.time()

DTP_FIELDS = "record_date,tot_pub_debt_out_amt,debt_held_public_amt,intragov_hold_amt"
HDO_FIELDS = "record_date,record_fiscal_year,debt_outstanding_amt"


def get(url, tries=4, timeout=60):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8")
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def fd_all(endpoint, **params):
    params["page[size]"] = "10000"
    q = urllib.parse.urlencode(params, safe=":,()")
    url = f"{FD}/{endpoint}?{q}"
    j = json.loads(get(url))
    data = list(j["data"])
    pages = int(j["meta"]["total-pages"])
    for pg in range(2, pages + 1):
        data += json.loads(get(f"{url}&page[number]={pg}"))["data"]
    if len(data) != int(j["meta"]["total-count"]):
        raise RuntimeError(f"{endpoint}: got {len(data)} rows, Treasury counts {j['meta']['total-count']}")
    return data


def _amount(raw):
    if raw is None:
        return None
    s = str(raw).strip()
    if s == "" or s.lower() == "null":
        return None
    # Treasury publishes a decimal. Keep it. Reject anything that is not a number.
    body = s[1:] if s.startswith("-") else s
    if not body or body.count(".") > 1 or not body.replace(".", "", 1).isdigit():
        raise RuntimeError(f"not a Treasury amount: {raw!r}")
    return s


def _write(name, payload):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name + ".json")
    tmp = path + ".tmp"
    json.dump(payload, open(tmp, "w"), indent=1)
    open(tmp).close()
    os.replace(tmp, path)
    return path


def fetch_daily():
    rows = fd_all("v2/accounting/od/debt_to_penny", sort="record_date", fields=DTP_FIELDS)
    out = []
    for r in rows:
        total = _amount(r.get("tot_pub_debt_out_amt"))
        if total is None:
            raise RuntimeError(f"Debt to the Penny row {r.get('record_date')} has no total")
        out.append({
            "record_date": r["record_date"],
            "total_public_debt_outstanding_usd": total,
            "debt_held_by_the_public_usd": _amount(r.get("debt_held_public_amt")),
            "intragovernmental_holdings_usd": _amount(r.get("intragov_hold_amt")),
        })
    out.sort(key=lambda r: r["record_date"])
    if not out or out[0]["record_date"] > "1993-04-01":
        raise RuntimeError(f"Debt to the Penny history does not start at the published beginning: {out[:1]}")
    return out


def fetch_annual():
    rows = fd_all("v2/accounting/od/debt_outstanding", sort="record_date", fields=HDO_FIELDS)
    out = []
    for r in rows:
        amt = _amount(r.get("debt_outstanding_amt"))
        if amt is None:
            raise RuntimeError(f"Historical Debt Outstanding row {r.get('record_date')} has no amount")
        out.append({
            "fiscal_year": int(r["record_fiscal_year"]),
            "record_date": r["record_date"],
            "debt_outstanding_usd": amt,
        })
    out.sort(key=lambda r: (r["fiscal_year"], r["record_date"]))
    if not out or out[0]["fiscal_year"] != 1790:
        raise RuntimeError(f"Historical Debt Outstanding does not start at 1790: {out[:1]}")
    years = {r["fiscal_year"] for r in out}
    missing = [y for y in range(min(years), max(years) + 1) if y not in years]
    if missing:
        raise RuntimeError(f"Historical Debt Outstanding is missing years: {missing[:12]}")
    # 1843 is published twice (January 1 and July 1). Both rows stay; nothing is averaged.
    return out


def _keep(name, err):
    path = os.path.join(CACHE, name + ".json")
    print(f"{name}: {err}", file=sys.stderr)
    if os.path.exists(path):
        print(f"{name}: kept the last good cache")
        return 0
    print(f"{name}: no cache to keep", file=sys.stderr)
    return 1


def main():
    code = 0
    try:
        rows = fetch_daily()
        _write("debt_to_penny_history", {"fetched": NOW, "data": rows})
        print(f"debt to the penny history: {len(rows)} rows, {rows[0]['record_date']} → {rows[-1]['record_date']}")
    except Exception as e:
        code = max(code, _keep("debt_to_penny_history", e))
    try:
        rows = fetch_annual()
        _write("debt_outstanding_exact", {"fetched": NOW, "data": rows})
        print(f"historical debt outstanding: {len(rows)} years, FY{rows[0]['fiscal_year']} → FY{rows[-1]['fiscal_year']}")
    except Exception as e:
        code = max(code, _keep("debt_outstanding_exact", e))
    return code


if __name__ == "__main__":
    sys.exit(main())
