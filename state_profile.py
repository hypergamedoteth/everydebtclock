"""Per-state facts for the debt clocks: per resident, debt-to-GDP, rank, and FAQs.

Every dollar amount is a Census or BEA figure already on disk. A ratio is that
debt divided by that GDP. When BEA did not publish the matching calendar year,
the ratio is left off the page. The District of Columbia has no separate
state-government total in the Census tables, so that sentence is not invented.
"""
import datetime as dt
import html
import json
import os
import re
from difflib import SequenceMatcher

E = html.escape
CENSUS_SURVEY = "https://www.census.gov/data/datasets/2024/econ/local/public-use-datasets.html"
POP_URL = "https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/state/totals/NST-EST2025-ALLDATA.csv"

_FACTS = {}
_GDP = None


_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = "zero ten twenty thirty forty fifty sixty seventy eighty ninety".split()


def _under1000(n):
    if n < 20:
        return _ONES[n]
    if n < 100:
        t, r = divmod(n, 10)
        return _TENS[t] if r == 0 else f"{_TENS[t]}-{_ONES[r]}"
    h, r = divmod(n, 100)
    head = f"{_ONES[h]} hundred"
    return head if r == 0 else f"{head} {_under1000(r)}"


def number_words(n):
    """Whole dollars in words, so a citable sentence is not only digits."""
    n = int(round(n))
    if n == 0:
        return "zero"
    neg = n < 0
    n = abs(n)
    parts = []
    for name, size in (("trillion", 10 ** 12), ("billion", 10 ** 9), ("million", 10 ** 6), ("thousand", 10 ** 3)):
        q, n = divmod(n, size)
        if q:
            parts.append(f"{_under1000(q)} {name}")
    if n:
        parts.append(_under1000(n))
    text = " ".join(parts)
    return ("minus " + text) if neg else text


def _words_sentence(r):
    bits = [f"{poss(r['name'])} Census {r['headline']} is {number_words(r['total'])} dollars."]
    if r["state"]:
        bits.append(f"State government debt is {number_words(r['state']['value'])} dollars.")
    if r["local"]:
        bits.append(f"Local government debt is {number_words(r['local']['value'])} dollars.")
    bits.append(f"Debt per resident is {number_words(round(r['pp']))} dollars.")
    if r["gdp"]:
        bits.append(f"{r['gdp_year']} state GDP is {number_words(r['gdp'])} dollars.")
    if r.get("prior_total") is not None:
        bits.append(f"The prior Census total was {number_words(r['prior_total'])} dollars.")
    return "In words: " + " ".join(bits)


def _series_digits(r):
    """The state's own Census series as figures. The dates are the same nationwide, so they are named once above."""
    def years(comp):
        if not comp:
            return "not published"
        if comp.get("history"):
            return " ".join(str(int(v)) for _, v in comp["history"])
        return str(int(comp["value"]))
    parts, priors = [], []
    for comp in (r["state"], r["local"]):
        if not comp:
            continue
        for b in comp.get("breakdown") or []:
            parts.append(str(int(b["value"])))
        if comp.get("prior_value") is not None:
            priors.append(str(int(comp["prior_value"])))
    combined = " ".join(str(int(v)) for _, v in r["hist"])
    gdp = str(int(r["gdp"])) if r["gdp"] else "not published"
    return (f"{r['name']} ({r['code']}). State debt by year: {years(r['state'])}. "
            f"Local debt by year: {years(r['local'])}. "
            f"Long-term then short-term parts: {' '.join(parts)}. "
            f"Prior year: {' '.join(priors)}. "
            f"Population {int(r['pop'])}. State GDP {gdp}. Debt per resident {int(round(r['pp']))}. "
            f"Combined total by year: {combined}.")


def _part_words(r):
    bits = []
    for comp, who in ((r["state"], "State"), (r["local"], "Local")):
        if not comp:
            continue
        for b in comp.get("breakdown") or []:
            label = (b.get("tile_label") or b.get("label") or "debt").strip()
            bits.append(f"{who} {label.lower()} is {number_words(b['value'])} dollars.")
    if not bits:
        return ""
    return "Census parts, in words: " + " ".join(bits)


def money0(x):
    return ("−" if x < 0 else "") + f"${abs(int(round(x))):,}"


def money2(x):
    return ("−" if x < 0 else "") + f"${abs(x):,.2f}"


def fdate(s):
    return dt.date.fromisoformat(s).strftime("%b %-d, %Y")


def ordinal(n):
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def poss(name):
    return name + "'s"


def _series(p):
    cs = p["components"]
    if not all(x.get("history") for x in cs):
        return []
    dates = set.intersection(*({h[0] for h in x["history"]} for x in cs))
    maps = [dict(x["history"]) for x in cs]
    return [(d, sum(m[d] for m in maps)) for d in sorted(dates)]


def _component(p, key):
    return next((c for c in p["components"] if c.get("key") == key), None)


def _rank(rows, key):
    """1 = highest. Ties break on the name so the rank is stable."""
    ordered = sorted(rows, key=lambda r: (-r[key], r["name"]))
    return {r["slug"]: i + 1 for i, r in enumerate(ordered)}


def prepare(R, places):
    """Rank the live states and attach BEA GDP where the survey year was published."""
    global _GDP, _FACTS
    path = os.path.join(R, "data", "state_gdp.json")
    _GDP = json.load(open(path)) if os.path.exists(path) else None
    states = [p for p in places if p.get("kind") == "state" and p.get("status") == "live"]
    rows = []
    for p in states:
        cs = p["components"]
        total = sum(c["value"] for c in cs)
        as_of = max(c["as_of"] for c in cs)
        pop = p["population"]
        state = _component(p, "state")
        local = _component(p, "local")
        year = str(dt.date.fromisoformat(as_of).year)
        gdp = millions = None
        if _GDP and p["slug"] in _GDP.get("states", {}):
            rec = _GDP["states"][p["slug"]]
            if year in rec.get("gdp_dollars", {}):
                gdp = rec["gdp_dollars"][year]
                millions = rec["gdp_millions_published"][year]
        hist = _series(p)
        priors = [c.get("prior_value") for c in cs]
        prior_dates = [c.get("prior_as_of") for c in cs]
        can_rate = all(v is not None for v in priors) and all(prior_dates) and not p.get("hold_trend")
        rows.append({
            "slug": p["slug"], "name": p["name"], "code": p.get("region_code") or "",
            "demonym": p.get("demonym", "resident"),
            "total": total, "as_of": as_of, "pop": pop["value"], "pop_as_of": pop["as_of"],
            "pop_source": pop.get("source_name"), "pop_url": pop.get("source_url"),
            "pp": total / pop["value"],
            "state": state, "local": local,
            "debt_url": (state or cs[0])["source_url"],
            "debt_source": (state or cs[0])["source_name"],
            "gdp": gdp, "gdp_millions": millions, "gdp_year": int(year) if gdp else None,
            "ratio": (total / gdp * 100) if gdp else None,
            "state_ratio": (state["value"] / gdp * 100) if gdp and state else None,
            "hist": hist, "hold": bool(p.get("hold_trend")), "hold_why": p.get("hold_why") or "",
            "prior_total": sum(priors) if can_rate else None,
            "prior_as_of": max(prior_dates) if can_rate else None,
            "headline": "government debt" if p["slug"] == "district-of-columbia" else "state and local debt",
        })
    by_slug = {r["slug"]: r for r in rows}
    for slug, rank in _rank(rows, "total").items():
        by_slug[slug]["rank_total"] = rank
    for slug, rank in _rank(rows, "pp").items():
        by_slug[slug]["rank_pp"] = rank
    with_gdp = [r for r in rows if r["ratio"] is not None]
    for slug, rank in _rank(with_gdp, "ratio").items():
        by_slug[slug]["rank_ratio"] = rank
    with_state = [r for r in rows if r["state"]]
    state_rows = [{**r, "state_value": r["state"]["value"]} for r in with_state]
    for slug, rank in _rank(state_rows, "state_value").items():
        by_slug[slug]["rank_state"] = rank
    med = sorted(r["total"] for r in rows)
    mid = len(med) // 2
    median = med[mid] if len(med) % 2 else (med[mid - 1] + med[mid]) / 2
    for r in rows:
        r["n"] = len(rows)
        r["n_ratio"] = len(with_gdp)
        r["n_state"] = len(with_state)
        r["median"] = median
    _FACTS = by_slug
    missing = [r["name"] for r in rows if r["ratio"] is None]
    if missing:
        print("state gdp omitted:", ", ".join(missing))
    else:
        print(f"state gdp: {len(with_gdp)} of {len(rows)} paired with BEA calendar-year GDP")
    return _FACTS


def _fact(slug):
    if slug not in _FACTS:
        raise SystemExit(f"state profile: {slug} was not prepared")
    return _FACTS[slug]


def _history_sentence(r):
    hist = r["hist"]
    if len(hist) < 2:
        return ""
    first_d, first_v = hist[0]
    last_d, last_v = hist[-1]
    changes = []
    up = down = 0
    for (d0, v0), (d1, v1) in zip(hist, hist[1:]):
        delta = v1 - v0
        changes.append((delta, d0, d1))
        if delta > 0:
            up += 1
        elif delta < 0:
            down += 1
    rise = max(changes, key=lambda x: x[0])
    fall = min(changes, key=lambda x: x[0])
    pct = (last_v - first_v) / first_v * 100
    direction = "higher" if last_v >= first_v else "lower"
    sent = (f"From {fdate(first_d)} to {fdate(last_d)}, {poss(r['name'])} Census {r['headline']} went from "
            f"{money0(first_v)} to {money0(last_v)}, {abs(pct):.1f}% {direction}. "
            f"In that series the total rose in {up} year{'' if up == 1 else 's'}"
            f" and fell in {down} year{'' if down == 1 else 's'}. "
            f"The largest rise was {money0(rise[0])}, from {fdate(rise[1])} to {fdate(rise[2])}.")
    if fall[0] < 0:
        sent += f" The largest fall was {money0(fall[0])}, from {fdate(fall[1])} to {fdate(fall[2])}."
    else:
        sent += " The total did not fall between any two published years in that series."
    return sent


def _neighbor_sentence(r):
    import explore
    names = {s: f["name"] for s, f in _FACTS.items()}
    totals = {s: f["total"] for s, f in _FACTS.items()}
    slugs = [s for s in explore.NEIGHBORS.get(r["slug"], "").split() if s in _FACTS]
    if not slugs:
        return f"{r['name']} has no land border with another state on this list."
    top = max(slugs, key=lambda s: (totals[s], names[s]))
    theirs = totals[top]
    if theirs == r["total"]:
        rel = f"the same official total as {names[top]}"
    elif r["total"] > theirs:
        rel = f"{money0(r['total'] - theirs)} above {names[top]}"
    else:
        rel = f"{money0(theirs - r['total'])} below {names[top]}"
    return (f"Among bordering states, {names[top]} has the largest Census total, {money0(theirs)} as of {fdate(_FACTS[top]['as_of'])}. "
            f"{r['name']} is {rel}.")


def _quote(r):
    if r["state"]:
        c = r["state"]
        return f"{poss(r['name'])} state government debt was {money0(c['value'])} as of {fdate(c['as_of'])}, per the U.S. Census Bureau."
    return (f"{poss(r['name'])} government debt was {money0(r['total'])} as of {fdate(r['as_of'])}, per the U.S. Census Bureau. "
            "Census does not publish a separate state-government total for the District.")


def _per_resident(r):
    return (f"{poss(r['name'])} {r['headline']} was {money0(r['total'])} as of {fdate(r['as_of'])}, "
            f"or {money2(r['pp'])} per resident. That divides the Census debt total by the Census population of "
            f"{r['pop']:,} on {fdate(r['pop_as_of'])}.")


def _gdp_sentence(r):
    if r["ratio"] is None:
        return (f"Debt as a share of {r['name']} GDP is not shown. The Bureau of Economic Analysis file on this site "
                f"has no current-dollar all-industry total for calendar {dt.date.fromisoformat(r['as_of']).year}.")
    sent = (f"{poss(r['name'])} {r['headline']} was {r['ratio']:.2f}% of {r['gdp_year']} state GDP. "
            f"The debt is the Census total of {money0(r['total'])} as of {fdate(r['as_of'])}. "
            f"State GDP is the Bureau of Economic Analysis figure of {money0(r['gdp'])} "
            f"({r['gdp_millions']} million current dollars) for calendar {r['gdp_year']}.")
    if r["state_ratio"] is not None:
        sent += f" State government debt alone was {r['state_ratio']:.2f}% of that same GDP."
    return sent


def _rank_sentence(r):
    sent = (f"{r['name']} ranks {ordinal(r['rank_total'])} of {r['n']} by official {r['headline']} as of {fdate(r['as_of'])}, "
            f"and {ordinal(r['rank_pp'])} of {r['n']} by debt per resident.")
    if r["ratio"] is not None:
        sent += f" It ranks {ordinal(r['rank_ratio'])} of {r['n_ratio']} by that debt as a share of state GDP."
    if r.get("rank_state"):
        sent += f" Its state government debt ranks {ordinal(r['rank_state'])} of {r['n_state']}."
    return sent


def _method_sentence(r):
    if r["hold"] or r.get("prior_total") is None:
        why = r["hold_why"] or "the latest change is not a rate this site will extend"
        return (f"The clock shows the official Census total of {money0(r['total'])} as of {fdate(r['as_of'])} "
                f"and does not add a daily rate, because {why}.")
    change = r["total"] - r["prior_total"]
    days = (dt.date.fromisoformat(r["as_of"]) - dt.date.fromisoformat(r["prior_as_of"])).days
    per_sec = change / (days * 86400) if days else 0
    sign = "adds" if change >= 0 else "subtracts"
    return (f"The clock starts at the Census total of {money0(r['total'])} on {fdate(r['as_of'])} and {sign} "
            f"the official change of {money0(abs(change))} since {fdate(r['prior_as_of'])}, "
            f"which is {days} days, or {money2(abs(per_sec))} per second. It is a projection, not a new Census figure.")


def faqs(slug):
    r = _fact(slug)
    q1 = "How much is the District of Columbia's government debt?" if slug == "district-of-columbia" else f"How much is {r['name']}'s state government debt?"
    return [
        (q1, _quote(r)),
        (f"How much is {r['name']}'s debt per resident?", _per_resident(r)),
        (f"What is {r['name']}'s debt-to-GDP?", _gdp_sentence(r)),
        (f"Where does {r['name']} rank among states?", _rank_sentence(r)),
        (f"Is the live {r['name']} debt clock an official figure?", _method_sentence(r)),
    ]


def _median_sentence(r):
    gap = r["total"] - r["median"]
    side = "above" if gap >= 0 else "below"
    return (f"The median official total among the {r['n']} clocks is {money0(r['median'])}. "
            f"{r['name']} is {money0(abs(gap))} {side} that median.")


def facts_html(slug):
    r = _fact(slug)
    gdp_url = (_GDP or {}).get("dataset_url") or "https://www.bea.gov/data/gdp/gdp-state"
    if r["ratio"] is None:
        gdp_num = "Not published"
        gdp_note = E(_gdp_sentence(r))
    else:
        gdp_num = f"{r['ratio']:.2f}%"
        extra = ""
        if r["state_ratio"] is not None:
            extra = f" State government debt alone is {r['state_ratio']:.2f}% of the same GDP."
        gdp_note = (f"Census {E(r['headline'])} as of {E(fdate(r['as_of']))} ÷ BEA current-dollar GDP for calendar {r['gdp_year']} "
                    f"({E(money0(r['gdp']))}, published as {E(r['gdp_millions'])} million).{E(extra)} "
                    f"<a href=\"{E(gdp_url)}\">Bureau of Economic Analysis</a>")
    rank_note = E(_rank_sentence(r))
    local = ""
    if r["local"] and r["state"]:
        share = r["local"]["value"] / r["total"] * 100
        local = (f" Local governments are {share:.1f}% of the latest Census total "
                 f"({money0(r['local']['value'])}); the state government is {100 - share:.1f}% "
                 f"({money0(r['state']['value'])}).")
    blurb = " ".join(s for s in (_words_sentence(r), _part_words(r), _series_digits(r), _history_sentence(r) + local, _median_sentence(r), _neighbor_sentence(r), _method_sentence(r)) if s)
    return f'''<section class="facts" id="facts">
<p class="answer">{E(_quote(r))}</p>
<div class="factgrid">
<div><span class="l">Debt per resident</span><span class="n">{E(money2(r['pp']))}</span><span class="s">{E(_per_resident(r))} <a href="{E(r['pop_url'])}">Census population</a></span></div>
<div><span class="l">Debt to state GDP</span><span class="n">{E(gdp_num)}</span><span class="s">{gdp_note}</span></div>
<div><span class="l">Rank among states</span><span class="n">{E(ordinal(r['rank_total']))} of {r['n']}</span><span class="s">{rank_note}</span></div>
</div>
<p>{E(blurb)}</p>
</section>'''


def faq_html(slug):
    parts = []
    for i, (q, a) in enumerate(faqs(slug)):
        cls = ' class="answer"' if i == 0 else ""
        parts.append(f"<h3>{E(q)}</h3><p{cls}>{E(a)}</p>")
    return f'<section class="faq" id="faq"><h2>Questions</h2>{"".join(parts)}</section>'


def faq_ld(slug):
    ld = {"@context": "https://schema.org", "@type": "FAQPage",
          "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs(slug)]}
    return '<script type="application/ld+json">' + json.dumps(ld).replace("</", "<\\/") + "</script>"


def extra_sources(slug):
    if not _GDP or _fact(slug)["ratio"] is None:
        return []
    return [(_GDP["source_name"], _GDP["dataset_url"])]


def index_parts(site):
    """FAQ and Dataset for /states/. Uses only the prepared official totals."""
    if not _FACTS:
        raise SystemExit("state profile: index requested before prepare()")
    rows = list(_FACTS.values())
    dates = sorted({r["as_of"] for r in rows})
    pop_dates = sorted({r["pop_as_of"] for r in rows})
    gdp_years = sorted({r["gdp_year"] for r in rows if r["gdp_year"]})
    when = fdate(dates[0]) if len(dates) == 1 else "the date named on each state page"
    pop_when = fdate(pop_dates[0]) if len(pop_dates) == 1 else "the date named on each state page"
    if len(gdp_years) == 1 and len(gdp_years) == len([r for r in rows if r["ratio"] is not None]) and len(rows) == sum(1 for r in rows if r["ratio"] is not None):
        gdp_when = f"calendar {gdp_years[0]}"
    elif gdp_years:
        gdp_when = "the BEA calendar year named on each state page"
    else:
        gdp_when = None
    n = len(rows)
    held = sum(1 for r in rows if r["hold"])
    ticking = n - held
    q1 = (f"Each clock counts Census Bureau debt outstanding for one state or the District of Columbia. "
          f"For the {n - 1} states that is state government debt plus local government debt. "
          f"The District is published as one government total, because Census has no separate state level for it. "
          f"The latest Census date on these pages is {when}.")
    q2 = (f"Debt per resident divides that Census total by the Census Bureau population estimate, {pop_when}. "
          + (f"Debt-to-GDP divides the same Census total by Bureau of Economic Analysis current-dollar GDP for {gdp_when}. "
             if gdp_when else "Debt-to-GDP is omitted where BEA did not publish the matching year. ")
          + "The two dates are both named, because the debt year and the population year are not the same release.")
    q3 = (f"All 50 states and the District of Columbia are listed. {ticking} clock{'s' if ticking != 1 else ''} "
          f"{'extend' if ticking != 1 else 'extends'} the latest official change forward by the second. "
          f"{held} {'hold' if held != 1 else 'holds'} the official total, because that change is not a rate this site will extend. "
          f"The reason is on the state page.")
    q4 = "Source: Every Debt Clock (everydebtclock.com), from the U.S. Census Bureau."
    pairs = [
        ("What do the US state debt clocks count?", q1),
        ("Where do the per-resident and debt-to-GDP figures come from?", q2),
        ("Which states have a debt clock?", q3),
        ("How should a state debt figure be cited?", q4),
    ]
    body = "".join(f"<h3>{E(q)}</h3><p>{E(a)}</p>" for q, a in pairs)
    html_block = f'<section class="faq" id="faq"><h2>Questions</h2>{body}</section>'
    based = [CENSUS_SURVEY, POP_URL]
    if _GDP:
        based.append(_GDP["dataset_url"])
    ld = {
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "US state and District of Columbia government debt",
        "description": q1, "url": site.rstrip("/") + "/states/",
        "isAccessibleForFree": True,
        "creator": {"@type": "Organization", "name": "Every Debt Clock", "url": site.rstrip("/") + "/"},
        "spatialCoverage": {"@type": "Place", "name": "United States"},
        "isBasedOn": based,
        "variableMeasured": ["Census debt outstanding", "debt per resident", "debt as a share of state GDP"],
    }
    faq = {"@context": "https://schema.org", "@type": "FAQPage",
           "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in pairs]}
    scripts = "".join('<script type="application/ld+json">' + json.dumps(x).replace("</", "<\\/") + "</script>" for x in (ld, faq))
    return html_block, scripts


def check(root, limit=0.80):
    """State clock pages must differ, and each one must carry the quotable Census sentence.

    Same comparison as the country pages: difflib on the words of <main>, after the shared
    "How it works" section is set aside. The Census line-item table (the same two labels on
    every state) is set aside for the same reason. The clock, the official total, per resident,
    debt-to-GDP, rank, history, and the FAQs stay in the comparison.
    """
    import country_profile
    pages = []
    missing = []
    for slug, r in sorted(_FACTS.items()):
        path = os.path.join(root, "states", slug, "index.html")
        if not os.path.isfile(path):
            missing.append(slug)
            continue
        text = open(path, encoding="utf-8").read()
        quote = _quote(r)
        if quote not in text and html.escape(quote) not in text:
            raise SystemExit(f"state page {slug}: missing the Census sentence")
        for bit in ('class="hero lead"', 'id="facts"', 'id="faq"', "FAQPage", "Dataset", "per the U.S. Census Bureau"):
            if bit not in text:
                raise SystemExit(f"state page {slug}: missing {bit}")
        if r["ratio"] is not None and "bea.gov" not in text:
            raise SystemExit(f"state page {slug}: debt-to-GDP is missing its BEA link")
        article = re.sub(r'<section[^>]*\bid="details"[\s\S]*?</section>', " ", text)
        pages.append((slug, country_profile._tokens(country_profile.visible_body(article))))
    if missing:
        raise SystemExit("state pages not built: " + ", ".join(missing))
    if len(pages) < 51:
        raise SystemExit(f"state pages: expected 51 clocks, found {len(pages)}")
    worst = (0.0, "", "")
    for i in range(len(pages)):
        ai, a = pages[i]
        for j in range(i + 1, len(pages)):
            bj, b = pages[j]
            bound = 2 * min(len(a), len(b)) / (len(a) + len(b) or 1)
            if bound <= limit:
                continue
            ratio = SequenceMatcher(None, a, b).ratio()
            if ratio > worst[0]:
                worst = (ratio, ai, bj)
            if ratio > limit:
                raise SystemExit(f"state pages {ai} and {bj} share {ratio:.1%} of their body text (limit {limit:.0%})")
    print(f"state pages distinct: {len(pages)} pages, closest {worst[1]} / {worst[2]} at {worst[0]:.1%}", flush=True)
    return worst
