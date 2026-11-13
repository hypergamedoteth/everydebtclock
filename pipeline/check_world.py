#!/usr/bin/env python3
"""Check the best-source World Debt Clock after build.py.

Every economy row needs a positive USD stock, a source tier and an as-of date.
The latest sum has to sit in a sane range of the IMF end-2026 panel (0.60x to 1.45x).
Official or harmonized stocks more than 25% from the IMF stock are printed for review.
That gap does not fail the check: central government and general government are different perimeters.

Reads api/world.json, data/world_weo_debt.json and world/index.html. Never invents a figure.
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
LO, HI = 0.60, 1.45

def fail(msg):
    print("check_world:", msg, file=sys.stderr)
    sys.exit(1)

def main():
    api_path = os.path.join(ROOT, "api", "world.json")
    if not os.path.exists(api_path):
        fail("api/world.json is missing; run build.py")
    api = json.load(open(api_path))
    weo = json.load(open(os.path.join(ROOT, "data", "world_weo_debt.json")))
    rows = api.get("countries") or []
    panel = {e["iso3"] for e in weo["economies"]}
    got = [r.get("iso3") for r in rows]
    if len(got) != len(set(got)):
        fail("duplicate iso3 in the world table")
    missing = sorted(panel - set(got))
    if missing:
        fail("world table is missing IMF economies: " + " ".join(missing))
    for r in rows:
        if not isinstance(r.get("debt_usd"), (int, float)) or r["debt_usd"] <= 0:
            fail(f"{r.get('iso3')} has no positive USD stock")
        if r.get("tier") not in ("official", "harmonized", "imf"):
            fail(f"{r.get('iso3')} has no source tier")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", r.get("as_of") or ""):
            fail(f"{r.get('iso3')} has no as-of date")
        if r["tier"] != "imf" and not r.get("source_url"):
            fail(f"{r.get('iso3')} has no source URL")
    total = api["total_latest_usd"]
    summed = sum(r["debt_usd"] for r in rows)
    if abs(summed - total) > len(rows):
        fail(f"row sum {summed} does not match total_latest_usd {total}")
    ratio = total / weo["panel_2026_usd"]
    if not LO <= ratio <= HI:
        fail(f"world total ${total/1e12:.2f}T is {ratio:.2f}x the IMF panel ${weo['panel_2026_usd']/1e12:.2f}T")
    counts = api["counts"]
    if sum(counts.values()) != len(rows):
        fail(f"tier counts {counts} do not add up to {len(rows)} rows")
    page = open(os.path.join(ROOT, "world", "index.html")).read()
    if "coming soon" in page.lower():
        fail("world page contains coming soon")
    for phrase in ("What this page counts", "FAQPage", "Source tier", "As of", "id=\"total\"", "id=\"debt-table\""):
        if phrase not in page:
            fail(f"world page is missing {phrase}")
    if page.count('data-iso="') != len(rows):
        fail(f"world table has {page.count('data-iso=\"')} rows, api has {len(rows)}")
    m = re.search(r'id="total"[^>]*data-r="([^"]+)"', page)
    if not m or float(m.group(1)) == 0:
        fail("world ticker is missing or zero")
    review = api.get("review_over_25pct") or []
    print(f"world ok: {len(rows)} economies, ${total/1e12:.2f}T latest, "
          f"{ratio:.2%} of the IMF ${weo['panel_2026_usd']/1e12:.2f}T, "
          f"official {counts['official']}, harmonized {counts['harmonized']}, IMF {counts['imf']}")
    print(f"REVIEW rows more than 25% from the IMF end-2026 stock: {len(review)}")
    for r in sorted(review, key=lambda x: -abs(x["gap"])):
        print(f"  REVIEW {r['iso3']:3} {r['tier']:12} {r['gap']:+7.1%}  ${r['debt_usd']/1e12:.3f}T vs IMF ${r['imf_debt_2026_usd']/1e12:.3f}T  {r['name']}  {r['source_url']}")
    kept = api.get("kept_on_imf") or []
    print(f"kept on IMF: {len(kept)}")
    for r in kept:
        print(f"  IMF {r['iso3']:3} {r['name']}: {r['reason']}")

if __name__ == "__main__":
    main()
