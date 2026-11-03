"""One rule for whether a state page ticks its Census figure forward, and the wording that explains it.

Used by census_state.py (new files) and runnable on its own to re-apply the rule to every state file:
    python3 pipeline/state_trend.py            # rewrites places/<state>.json in place, no network

Rule: the clock extends the last one-year change only if that change (a) is at least about two standard errors
of Census's estimate (otherwise Census's data does not show which way debt is moving) and (b) is no more than
MAX_TICK of the prior year's level (otherwise a straight line carried two more years past a one-year jump
would drift far from any plausible figure). Otherwise the official figure is shown fixed.
Large year-over-year swings are flagged on the page whether or not the page ticks.
"""
import glob, json, os, re, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
MAX_TICK = 0.05    # largest one-year change (share of prior level) we are willing to carry forward
SWING = 0.20       # a year-over-year move larger than this is flagged as a swing
BASE = "{name} state + local debt is reported once a year by the Census Bureau, about two years after the fact. Real borrowing happens in lumps when bonds are sold and is repaid on schedules, so "

def _b(v): return f"${abs(v)/1e9:,.2f} billion"

def apply(p):
    name = p["name"]; cs = p["components"]
    tot = {}
    for c in cs:
        for d, v in c["history"]: tot[d] = tot.get(d, 0) + v
    ds = sorted(tot); a, b = ds[-2], ds[-1]; prev, last = a[:4], b[:4]
    L, P = tot[b], tot[a]; ch = L - P; pct = ch / P
    cv = float(p["total_cv"]); se = L * cv / 100
    noise = abs(ch) < 2 * se; large = abs(pct) > MAX_TICK
    p["hold_trend"] = bool(noise or large)
    swings = [(x[:4], y[:4], tot[y] - tot[x], tot[y] / tot[x] - 1) for x, y in zip(ds, ds[1:]) if abs(tot[y] / tot[x] - 1) > SWING]
    p["trend_pct"] = round(pct * 100, 1)
    n_noise = f"the {prev}→{last} change ({'+' if ch >= 0 else '−'}{_b(ch)}) is smaller than about two standard errors of the Census estimate (about {_b(2 * se)} at a {cv:g}% coefficient of variation), so Census's data does not show which way the debt is moving"
    n_large = f"the {prev}→{last} change ({'+' if ch >= 0 else '−'}{_b(ch)}, {pct:+.1%}) is more than {MAX_TICK:.0%} of the {prev} level in one year, and a straight line carried a further two years past a jump that size would drift far from any plausible figure; a move that big is more likely a one-off (a large bond issue or payoff, a reclassification, or Census sampling) than a trend"
    why = {"both": f"{n_noise}; and {n_large}", "noise": n_noise, "large": n_large}.get("both" if noise and large else "noise" if noise else "large" if large else "", "")
    if noise and large: why = f"the {prev}→{last} change is both within about two standard errors of the Census estimate and more than {MAX_TICK:.0%} of the {prev} level in one year"
    p["hold_why"] = ""  # set below to the short reason
    notes = [n for n in p["notes"] if not re.match(r"The \d{4}→\d{4} change", n) and not n.startswith(("Large swings", "This page therefore shows the official figure as published")) and n != p.get("reconcile_note")]
    notes[1] = re.sub(r"so the (page shows the official figure as of|live clock projects from) June 30", "so the " + ("page shows the official figure as of" if p["hold_trend"] else "live clock projects from") + " June 30", notes[1])
    new = []
    if noise: new.append(f"The {prev}→{last} change ({'+' if ch >= 0 else '−'}{_b(ch)}) is smaller than about two standard errors of the Census estimate (about {_b(2 * se)} at a {cv:g}% coefficient of variation), so Census's data does not show which way the debt is moving.")
    if large: new.append(f"The {prev}→{last} change ({'+' if ch >= 0 else '−'}{_b(ch)}, {pct:+.1%}) is more than {MAX_TICK:.0%} of the {prev} level in one year. A move that size is more likely a one-off (a large bond issue or payoff, a reclassification, or Census sampling) than a trend, and a straight line carried a further two years past it would drift far from any plausible figure.")
    new.append("This page therefore shows the official figure as published and does not tick it forward." if p["hold_trend"] else f"The {prev}→{last} change ({pct:+.1%}) is large enough to measure and small enough to extend, so the live number continues it as a straight line from June 30, {last}. Treat it as a projection, not a reported figure.")
    if swings:
        txt = "; ".join(f"{x}→{y}: {'+' if d >= 0 else '−'}{_b(d)} ({r:+.0%})" for x, y, d, r in swings)
        s = f"Large swings in Census's series for {name}: {txt}. Census's tables give no explanation for these moves and we have not found one, so read the history table with care: they may be real payoffs or issuance, or a change in how Census measured or classified debt."
        if any("2022" in (x, y) for x, y, *_ in swings): s += " Census's 2022 local-government figures come from the full Census of Governments rather than the sample used in other years, so a shift around 2022 may partly reflect that change of method."
        new.append(s)
    if p.get("reconcile_note"): new.append(p["reconcile_note"])  # hand-written note tying the page to a newer state-published figure
    notes[2:2] = new
    p["notes"] = notes
    lg = BASE.format(name=name)
    sw = f"{'+' if ch >= 0 else '−'}{abs(pct):.1%}"
    sh = ("the " + f"{prev}→{last} change ({sw}) is within about two standard errors of the Census estimate" if noise and not large else
          f"the {prev}→{last} change ({sw}) is too large to carry forward as a trend" if large and not noise else
          f"the {prev}→{last} change ({sw}) is both within about two standard errors of the Census estimate and too large to carry forward as a trend")
    p["hold_why"] = sh if p["hold_trend"] else ""
    if p["hold_trend"]: lg += f"the page shows the latest official figure without ticking it forward, because {sh}."
    else: lg += "the live number is a straight-line projection from the latest Census year, shown here next to the official totals."
    if swings: lg += " Large year-over-year swings are flagged in the notes below: " + ", ".join(f"{x}→{y} ({r:+.0%})" for x, y, d, r in swings) + "."
    p["legend"] = lg
    return p

def main():
    for f in sorted(glob.glob(os.path.join(ROOT, "places", "*.json"))):
        p = json.load(open(f))
        if p.get("kind") != "state": continue
        if "total_cv" not in p:
            p["total_cv"] = float(re.search(r"coefficient of variation ([\d.]+)%", p["notes"][0]).group(1))
        apply(p)
        with open(f, "w") as o: json.dump(p, o, indent=1, ensure_ascii=False); o.write("\n")
        print(p["slug"], "HOLD" if p["hold_trend"] else "tick", p["trend_pct"])
if __name__ == "__main__": main()
