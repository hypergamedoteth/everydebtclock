#!/usr/bin/env python3
"""Quarterly re-base of places/india.json from the Department of Economic Affairs (Ministry of Finance, India),
"Quarterly Report on Public Debt Management", Table 4.1 "Total Liabilities of Central Government" (₹ crore, quarter-end,
provisional): http://dea.gov.in/reports-public-debt-management

  H. Gross Liabilities as per FRBM Act   <- the ticking hero
  A. Public Debt (A1 + A2)               <- fact
  D. Total (net) Liabilities as in the Union Budget <- fact
Each report gives its own quarter-end and the previous one; the newest report wins for each quarter. The trend is the change over
the latest four quarters. Needs `pdftotext` (poppler-utils). dea.gov.in only works over plain http from some networks.
Rule: never invent a number. Any fetch error, missing tool, unreadable table, a gap in the quarters, or data older than the file
leaves places/india.json untouched (exit 0).
"""
import json, os, re, sys, calendar, subprocess, tempfile, urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "places", "india.json")
LIST = "http://dea.gov.in/reports-public-debt-management"
CRORE = 10_000_000
MONTH = {"March": 3, "June": 6, "September": 9, "December": 12}

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 everydebtclock.com"})
    with urllib.request.urlopen(req, timeout=90) as r: return r.read()

def qend(y, m): return f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"
def prev_q(y, m): return (y, m - 3) if m > 3 else (y - 1, 12)

def listing():
    h = get(LIST).decode("utf-8", "replace")
    out = {}
    for href in re.findall(r'href="([^"]*Quarterly[^"]*Report[^"]*Public[^"]*Debt[^"]*Management[^"]*\.pdf)"', h):
        name = urllib.parse.unquote(href)
        m = re.search(r"quarter\s+(January|April|July|October)\s*-\s*(March|June|September|December)\s+(\d{4})", name)
        if not m: continue
        key = (int(m.group(3)), MONTH[m.group(2)])
        url = urllib.parse.urljoin(LIST, href.replace(" ", "%20")).replace("https://", "http://")
        out.setdefault(key, url)
    return out

def parse_pdf(raw):
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(raw); f.flush()
        lines = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True, timeout=90, check=True).stdout.splitlines()
    idx = [i for i, l in enumerate(lines) if "Table 4.1: Total Liabilities" in l and "....." not in l]
    if not idx: raise RuntimeError("Table 4.1 not found")
    t = lines[idx[-1]:idx[-1] + 70]
    def row(pat):
        for i, l in enumerate(t):
            if re.match(pat, l.strip()):
                nums = []
                for ll in t[i:i + 3]:
                    nums += [int(n) for n in re.findall(r"(?<![\d.,])\d{6,9}(?![\d.,])", ll)]
                    if len(nums) >= 2: break
                if len(nums) >= 2: return nums[0], nums[1]
        raise RuntimeError("row not found: " + pat)
    return {"A": row(r"A\.\s+Public Debt"), "D": row(r"D\.\s+Total \(net\) Liabilities"), "H": row(r"H\.\s+Gross Liabilities as per FRBM")}

def rebase(p):
    files = listing()
    if not files: raise RuntimeError("no quarterly reports found")
    data = {}
    for key in sorted(files, reverse=True)[:6]:
        r = parse_pdf(get(files[key]))
        for lbl, (cur, prv) in r.items():
            data.setdefault(key, {})[lbl] = cur
            pk = prev_q(*key)
            data.setdefault(pk, {}).setdefault(lbl, prv)       # newest report wins: only fills if absent
    ks = sorted(data)
    run = [ks[-1]]
    for k in reversed(ks[:-1]):
        if k == prev_q(*run[0]): run.insert(0, k)
        else: break
    run = run[-9:]
    if len(run) < 5: raise RuntimeError("need at least 5 consecutive quarters")
    last, prior = run[-1], run[-5]
    for k in run:
        if len(data[k]) != 3: raise RuntimeError(f"incomplete rows for {k}")
    c = p["components"][0]; as_of = qend(*last)
    if as_of < c["as_of"]: raise RuntimeError(f"report quarter {as_of} older than file {c['as_of']}")
    v = lambda k, l: data[k][l] * CRORE
    c.update(value=v(last, "H"), as_of=as_of, prior_value=v(prior, "H"), prior_as_of=qend(*prior), history=[[qend(*k), v(k, "H")] for k in run])
    for f in c.get("facts", []):
        l = {"public_debt": "A", "net_liabilities": "D"}.get(f.get("key"))
        if l: f.update(value=v(last, l), as_of=as_of)
    nm = last[1] + 3
    ny, nm = (last[0], nm) if nm <= 12 else (last[0] + 1, 3)
    p["next_update"] = (f"The next quarterly report (quarter ending {calendar.month_name[nm]} {ny}) is usually published about three months after "
                        "the quarter ends; this page re-bases to it automatically on the next daily build after it appears. Figures are provisional and are revised in later reports.")
    return p

def main():
    p = json.load(open(PATH))
    try: new = rebase(json.loads(json.dumps(p)))
    except Exception as e:
        print("india: not updated:", e); return 0
    if new != p:
        json.dump(new, open(PATH, "w"), indent=1, ensure_ascii=False); open(PATH, "a").write("\n")
        c = new["components"][0]; print(f"india: {c['as_of']} ₹{c['value']:,} (prior {c['prior_as_of']} ₹{c['prior_value']:,})")
    else: print("india: unchanged")
    return 0

if __name__ == "__main__": sys.exit(main())
