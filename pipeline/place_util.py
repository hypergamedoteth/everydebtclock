"""Shared helpers for the single-series country fetchers (Turkey, Switzerland, Taiwan, Korea, Australia, Indonesia, Saudi Arabia, ...).

A fetcher parses an official source into a series {YYYY-MM-DD: amount in whole currency units} and calls rebase(). Rules (same as the other
fetchers): never invent a number; any error, an implausible jump, or data older than the file leaves the place's JSON untouched (exit 0).
"""
import json, os, ssl, time, urllib.request, datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "Mozilla/5.0 (compatible; everydebtclock.com data refresh)"
BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
_ctx = ssl.create_default_context()
_ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT      # some government certificates lack a Subject Key Identifier; the chain is still verified

def get(url, ua=UA, raw=False, referer=None, timeout=60):
    h = {"User-Agent": ua, "Accept": "*/*"}
    if referer: h["Referer"] = referer
    for attempt in range(3):                 # government sites drop connections now and then
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout, context=_ctx) as r:
                b = r.read()
            break
        except Exception:
            if attempt == 2: raise
            time.sleep(3)
    return b if raw else b.decode("utf-8", "replace")

def d(s): return dt.date.fromisoformat(s)

def month_end(y, m):
    return (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)).isoformat()

def rebase(p, series, tol_days=45, keep_months=14, max_jump=0.25, hist_monthly=False, next_update=None):
    """Set the hero component from `series`. Prior = the point closest to one year before the latest (within tol_days).
    History = stored history merged with the series, from the prior point onwards (month-end points only when hist_monthly)."""
    c = p["components"][0]
    new = dict(series)
    if not new: raise RuntimeError("empty series")
    last = max(new)
    if last < c["as_of"]: raise RuntimeError(f"source date {last} older than file {c['as_of']}")
    target = d(last) - dt.timedelta(days=365)
    merged = {a: v for a, v in c.get("history", [])}; merged.update(new)
    cands = sorted(merged, key=lambda x: abs((d(x) - target).days))
    prior = cands[0]
    if abs((d(prior) - target).days) > tol_days: raise RuntimeError(f"no point within {tol_days} days of {target}; closest {prior}")
    if d(prior) >= d(last): raise RuntimeError("prior is not before latest")
    if c["value"] and c["as_of"] != "1970-01-01":
        prev = c["value"]
        if abs(new[last] / prev - 1) > max_jump: raise RuntimeError(f"implausible change {prev} -> {new[last]}")
    hist = sorted(a for a in merged if a >= prior)
    if hist_monthly:
        mends = {}
        for a in hist: mends[a[:7]] = a            # last observation in each month
        hist = sorted(set(mends.values()) | {prior, last})
    c.update(value=int(round(new[last])), as_of=last, prior_value=int(round(merged[prior])), prior_as_of=prior,
             history=[[a, int(round(merged[a]))] for a in hist][-(keep_months + 2):])
    if next_update: p["next_update"] = next_update
    return p

def path(slug): return os.path.join(ROOT, "places", slug + ".json")

def _clean(o):
    """Remove float noise (e.g. 1060099999999 for 1,060.1bn): a figure within 1.5 units of a round thousand is that thousand."""
    if isinstance(o, dict):
        return {k: (_snap(v) if k in ("value", "prior_value") else _clean(v)) for k, v in o.items()}
    if isinstance(o, list): return [_clean(x) for x in o]
    return o

def _snap(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) >= 1e9:
        r = round(v, -3)
        if abs(v - r) <= 1.5: return int(r)
        return int(v) if float(v).is_integer() else v
    return _clean(v) if isinstance(v, (dict, list)) else v

def run(slug, build, label=None):
    """build(p) -> new p (deep-copied input). Writes only if changed; prints one line; always returns 0."""
    pth = path(slug)
    if not os.path.exists(pth): return 0
    p = json.load(open(pth))
    try: new = _clean(build(json.loads(json.dumps(p))))
    except Exception as e:
        print(f"{slug}: not updated: {e}"); return 0
    if new != p:
        json.dump(new, open(pth, "w"), indent=1, ensure_ascii=False); open(pth, "a").write("\n")
        c = new["components"][0]; s = new["currency"]["symbol"]
        print(f"{slug}: {c['as_of']} {s}{c['value']:,} (prior {c['prior_as_of']} {s}{c['prior_value']:,})")
    else: print(f"{slug}: unchanged")
    return 0

def pdf_text(data):
    """Text of a PDF (bytes): pypdf if installed (GitHub Actions), else the poppler `pdftotext` binary. Raises if neither works."""
    try:
        import pypdf, io
        r = pypdf.PdfReader(io.BytesIO(data))
        return "\n".join((pg.extract_text() or "") for pg in r.pages)
    except ImportError:
        import subprocess, tempfile
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(data); f.flush()
            return subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, check=True, timeout=60).stdout.decode("utf-8", "replace")
