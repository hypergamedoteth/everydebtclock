#!/usr/bin/env python3
"""Quarterly re-base of places/china.json from the Ministry of Finance of China, "Central Government Operations And Debt" (IMF SDDS
data category, 中央政府债务余额 季度数据), published on https://gks.mof.gov.cn/tongjishuju/ as a PDF (RMB billion, quarter-end).

  Debt (债务余额)            <- the ticking hero: central government debt balance
  Domestic / foreign debt   <- shown as facts; they must add up to the total (within rounding)
Each PDF holds the quarters of one calendar year so far; the fetcher reads the newest PDF of the latest years and joins them.
The trend is the official change over the latest four quarters.
Needs `pdftotext` (poppler-utils). Rule: never invent a number. Any fetch error, missing tool, unreadable table, a gap in the
quarters, parts that don't add up, or data older than what the file already has leaves places/china.json untouched (exit 0).
"""
import json, os, re, sys, calendar, subprocess, tempfile, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "places", "china.json")
LIST = "https://gks.mof.gov.cn/tongjishuju/"
BN = 1_000_000_000

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 everydebtclock.com"})
    with urllib.request.urlopen(req, timeout=60) as r: return r.read()

def listing():
    h = get(LIST).decode("utf-8", "replace")
    out = {}
    for href, title in re.findall(r'href="(\./\d{6}/P\d+\.pdf)"[^>]*title="([^"]+)"', h):
        if "债务余额" not in title or "Central_Government_Operations_And_Debt" not in title: continue
        m = re.match(r"(\d{4})年", title)
        if m and int(m.group(1)) not in out: out[int(m.group(1))] = LIST + href[2:]   # page lists newest first
    return out

def parse_pdf(raw):
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(raw); f.flush()
        txt = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True, timeout=60, check=True).stdout
    lines = txt.splitlines()
    start = next((i for i, l in enumerate(lines) if "中央政府债务余额" in l and "季度" in l), None)
    if start is None: raise RuntimeError("quarterly debt table not found")
    got, label = {}, ""
    for l in lines[start + 1:start + 60]:
        s = l.strip()
        if not s: continue
        nums = re.findall(r"\d[\d,]*\.\d", s)
        if nums and re.fullmatch(r"[\d,.\s]+", s): got.setdefault(label, [float(n.replace(",", "")) for n in nums])
        elif re.match(r"[\u4e00-\u9fff]", s):
            label = "total" if s.startswith("债务余额") else "domestic" if "国内债务" in s else "foreign" if "国外债务" in s else "x" + s
    for k in ("total", "domestic", "foreign"):
        if k not in got: raise RuntimeError(f"row {k} not found")
    if not (len(got["total"]) == len(got["domestic"]) == len(got["foreign"])): raise RuntimeError("rows have different numbers of quarters")
    for t, d, f in zip(got["total"], got["domestic"], got["foreign"]):
        if abs(d + f - t) > 0.25: raise RuntimeError("domestic + foreign does not add up to the total")
    return got

def qend(y, q): return f"{y:04d}-{q * 3:02d}-{calendar.monthrange(y, q * 3)[1]:02d}"

def rebase(p):
    files = listing()
    if not files: raise RuntimeError("no Central Government Operations And Debt PDFs found")
    data = {}
    for y in sorted(files)[-3:]:
        got = parse_pdf(get(files[y]))
        for q, (t, d, f) in enumerate(zip(got["total"], got["domestic"], got["foreign"]), 1): data[(y, q)] = (t, d, f)
    ks = sorted(data)
    for a, b in zip(ks, ks[1:]):
        if (b[0] * 4 + b[1]) - (a[0] * 4 + a[1]) != 1: raise RuntimeError(f"gap between {a} and {b}")
    ks = ks[-9:]
    if len(ks) < 5: raise RuntimeError("need at least 5 quarters")
    last, prior = ks[-1], ks[-5]
    c = p["components"][0]; as_of = qend(*last)
    if as_of < c["as_of"]: raise RuntimeError(f"MOF quarter {as_of} older than file {c['as_of']}")
    v = lambda k, i: int(round(data[k][i] * BN))
    c.update(value=v(last, 0), as_of=as_of, prior_value=v(prior, 0), prior_as_of=qend(*prior), history=[[qend(*k), v(k, 0)] for k in ks])
    for f in c.get("facts", []):
        i = {"domestic": 1, "foreign": 2}.get(f.get("key"))
        if i:
            f.update(value=v(last, i), as_of=as_of)
            f["note"] = f["note"].split(" A year earlier")[0].strip() + f" A year earlier ({qend(*prior)}) it was ¥{v(prior, i) / 1e12:,.2f} trillion."
    ny, nq = last[0] + (last[1] == 4), last[1] % 4 + 1
    p["next_update"] = (f"The Q{nq} {ny} quarter-end balance is expected from the Ministry of Finance roughly four weeks after the quarter ends; "
                        "this page re-bases to it automatically on the next daily build after it appears.")
    return p

def main():
    p = json.load(open(PATH))
    try: new = rebase(json.loads(json.dumps(p)))
    except Exception as e:
        print("china: not updated:", e); return 0
    if new != p:
        json.dump(new, open(PATH, "w"), indent=1, ensure_ascii=False); open(PATH, "a").write("\n")
        c = new["components"][0]; print(f"china: {c['as_of']} ¥{c['value']:,} (prior {c['prior_as_of']} ¥{c['prior_value']:,})")
    else: print("china: unchanged")
    return 0

if __name__ == "__main__": sys.exit(main())
