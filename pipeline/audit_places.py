#!/usr/bin/env python3
"""Self-audit of every US state page against the official sources it cites. Read-only: never writes places/*.json.
Usage: python3 pipeline/audit_places.py [--offline] [--site DIR] [--report FILE]
  1. Internal checks on each places/<slug>.json (kind=state): state + local = state-and-local total, long + short term = component,
     history ends at the headline value, prior value matches history, population present, every figure has a source URL.
  2. Live check (skipped with --offline): re-download Census table GS00LOCALFIN for the state and Census Vintage 2025 population,
     and compare every stored figure (headline, prior, full history, breakdown, population). Any difference is DRIFT.
     A newer Census survey year than the one stored is reported as UPDATE AVAILABLE.
  3. Site check (with --site DIR, e.g. the built _site): states/<slug>/index.html exists for each live state and is listed in sitemap.xml.
Exit code 0 = clean; 1 = drift, a failed check or an update is available (so a scheduled run goes red and GitHub emails the owner).
Headline figures are Census numbers published in $1,000; parts may differ from totals by rounding, so equality checks allow $5,000."""
import argparse, csv, glob, io, json, os, re, sys, urllib.request
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
API = "https://data.census.gov/api/access/data/table?id=GOVSLOCALFINTIMESERIES.GS00LOCALFIN&g=040XX00US{fips}"
POP_URL = "https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/state/totals/NST-EST2025-ALLDATA.csv"
TOL = 5000  # dollars; Census publishes in $1,000
UA = {"User-Agent": "Mozilla/5.0"}

def get(url, tries=3):
    for i in range(tries):
        try: return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90).read()
        except Exception:
            if i == tries - 1: raise

def census(fips, tries=6):
    # data.census.gov sometimes answers a burst of requests with an HTML/empty page instead of JSON: back off and retry before calling it unverifiable
    import time
    for i in range(tries):
        try: d = json.loads(get(API.format(fips=fips)))["response"]["data"]; break
        except (ValueError, KeyError):
            if i == tries - 1: raise
            time.sleep(4 * (i + 1))
    h = d[0]; ix = {k: h.index(k) for k in h}
    out = {}
    for r in d[1:]:
        if r[ix["AGG_DESC"]] in ("LF0231", "LF0232", "LF0233") and r[ix["GOVTYPE_LABEL"]] in ("State", "Local", "State and Local"):
            out[(r[ix["GOVTYPE_LABEL"]], r[ix["AGG_DESC"]], int(r[ix["YEAR"]]))] = int(r[ix["AMOUNT"]]) * 1000
    return out

def audit_place(p, live, pops, issues, notes):
    slug = p["slug"]; E = lambda m: issues.append(f"{slug}: {m}")
    cs = {c["key"]: c for c in p["components"]}
    if set(cs) != {"state", "local"}: return E(f"expected components state+local, got {sorted(cs)}")
    fips = re.search(r"US(\d\d)", cs["state"]["source_url"]); fips = fips and fips.group(1)
    if not fips: return E("no FIPS in source_url")
    for k, c in cs.items():
        if not c.get("source_url", "").startswith("https://"): E(f"{k}: missing source_url")
        if c["history"][-1][1] != c["value"]: E(f"{k}: history does not end at headline value")
        if len(c["history"]) < 2 or c["history"][-2][1] != c["prior_value"]: E(f"{k}: prior_value does not match history")
        parts = sum(b["value"] for b in c.get("breakdown", []))
        if abs(parts - c["value"]) > TOL: E(f"{k}: breakdown parts {parts} != value {c['value']}")
    pop = p["population"]
    if not (pop["value"] > 0 and pop["source_url"].startswith("https://")): E("population missing or unsourced")
    if not live: return
    try: cen = census(fips)
    except Exception as ex: return E(f"could not fetch Census data ({ex.__class__.__name__}); not verified")
    years = sorted(y for (g, a, y) in cen if g == "State and Local" and a == "LF0231")
    last = int(cs["state"]["as_of"][:4])
    if years and years[-1] > last: issues.append(f"{slug}: UPDATE AVAILABLE, Census now has survey year {years[-1]} (page uses {last})")
    for k, g in (("state", "State"), ("local", "Local")):
        c = cs[k]
        for d, v in c["history"]:
            y = int(d[:4]); cv = cen.get((g, "LF0231", y))
            if cv is None: E(f"{k} {y}: not in Census data now")
            elif cv != v: E(f"DRIFT {k} {y}: page {v} vs Census {cv}")
        for b in c.get("breakdown", []):
            a = "LF0233" if "LF0233" in b["label"] else "LF0232"; cv = cen.get((g, a, last))
            if cv != b["value"]: E(f"DRIFT {k} {a} {last}: page {b['value']} vs Census {cv}")
    tot = cen.get(("State and Local", "LF0231", last))
    if tot is not None and abs(cs["state"]["value"] + cs["local"]["value"] - tot) > TOL: E(f"DRIFT state+local {last}: page sum vs Census total {tot}")
    pr = pops.get(p["name"])
    if not pr: E("not in Census population file")
    elif int(pr["POPESTIMATE2025"]) != pop["value"] or int(pr["POPESTIMATE2024"]) != pop["prior_value"]: E("DRIFT population vs Census Vintage 2025")
    notes.append(f"{slug}: {last} state+local ${(cs['state']['value'] + cs['local']['value'])/1e9:,.2f}B checked against Census" )

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--offline", action="store_true"); ap.add_argument("--site"); ap.add_argument("--report")
    a = ap.parse_args(); issues, notes = [], []
    places = [p for f in sorted(glob.glob(os.path.join(ROOT, "places", "*.json"))) for p in [json.load(open(f))] if p.get("kind") == "state" and p.get("status") == "live"]
    pops = {} if a.offline else {r["NAME"]: r for r in csv.DictReader(io.StringIO(get(POP_URL).decode("utf-8-sig")))}
    for p in places: audit_place(p, not a.offline, pops, issues, notes)
    if len(places) != 50: issues.append(f"expected 50 live state files, found {len(places)}")
    if a.site:
        sm = open(os.path.join(a.site, "sitemap.xml")).read() if os.path.exists(os.path.join(a.site, "sitemap.xml")) else ""
        for p in places:
            if not os.path.exists(os.path.join(a.site, "states", p["slug"], "index.html")): issues.append(f"{p['slug']}: page missing in built site")
            if f"/states/{p['slug']}/" not in sm: issues.append(f"{p['slug']}: not in sitemap.xml")
    lines = [f"# Places audit: {len(places)} state files, {'offline (internal checks only)' if a.offline else 'live Census comparison'}", ""]
    lines += ([f"## {len(issues)} issue(s)"] + [f"- {i}" for i in issues]) if issues else [("## Clean: internal checks passed (live Census comparison not run)." if a.offline else "## Clean: no drift, no failed checks, no newer Census year.")]
    lines += ["", f"Checked against the official source: {len(notes)} states."]
    out = "\n".join(lines); print(out)
    if a.report: open(a.report, "w").write(out + "\n")
    sys.exit(1 if issues else 0)
if __name__ == "__main__": main()
