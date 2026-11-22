"""Federal block on /states/<slug>/. The Census state-and-local clock above it is unchanged.

Four additions, each with a source and a date:
- the state's population share of the live federal debt, per resident and in dollars, ticking
- that same share of Treasury's finished-year interest expense, not ticking
- USAspending award transactions performed in the state, not ticking
- Social Security beneficiaries, federal civilian employees, and active-duty military,
  as who is affected if the debt-limit X-date hits

Per resident, the federal debt and the interest share are the national figures.
They match in every state because the split is by population.
"""
import csv
import datetime as dt
import html
import json
import os

E = html.escape
CENSUS_POP = "https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/state/totals/NST-EST2025-ALLDATA.csv"
DEBT_URL = "https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/debt-to-the-penny"
INTEREST_URL = "https://fiscaldata.treasury.gov/datasets/interest-expense-debt-outstanding/interest-expense"

_CACHE = {}


def _date(iso):
    return dt.date.fromisoformat(iso[:10]).strftime("%b %-d, %Y")


def _long(iso):
    return dt.date.fromisoformat(iso[:10]).strftime("%B %-d, %Y")


def _usd0(n):
    n = round(n)
    return ("−" if n < 0 else "") + f"${abs(n):,}"


def _usd2(n):
    return ("−" if n < 0 else "") + f"${abs(n):,.2f}"


def _short(n):
    a = abs(n)
    s = "−" if n < 0 else ""
    if a >= 1e12:
        body = f"{a / 1e12:.2f}T"
    elif a >= 1e9:
        body = f"{a / 1e9:.2f}B"
    elif a >= 1e6:
        body = f"{a / 1e6:.1f}M"
    else:
        body = f"{a:,.0f}"
    return s + body


def _ord(n):
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _doc(R):
    path = os.path.join(R, "data", "state_federal.json")
    if not os.path.exists(path):
        raise SystemExit("state federal: data/state_federal.json is missing")
    return json.load(open(path))


def _interest(R):
    path = os.path.join(R, "data", "us-interest.csv")
    best = None
    for row in csv.DictReader(open(path)):
        if row["series"] != "interest_expense" or row["complete"] != "yes":
            continue
        if best is None or int(row["fiscal_year"]) > int(best["fiscal_year"]):
            best = row
    if not best:
        raise SystemExit("state federal: no complete interest-expense year")
    return best


def runtime(R):
    if R in _CACHE:
        return _CACHE[R]
    data = json.load(open(os.path.join(R, "data", "data.json")))
    debt = data["tickers"]["debt_total"]
    pop = data["tickers"]["population"]
    if debt.get("status") != "ok":
        raise SystemExit("state federal: debt_total is not ok")
    us_pop = int(pop["base"])
    if pop.get("as_of") != "2025-07-01":
        raise SystemExit("state federal: expected Census Vintage 2025 population dated 2025-07-01")
    interest = _interest(R)
    doc = _doc(R)
    import places_build
    states = [p for p in places_build.load(R) if p.get("kind") == "state"]
    if len(states) != 51:
        raise SystemExit(f"state federal: expected 51 states and DC, found {len(states)}")
    if sum(int(p["population"]["value"]) for p in states) != us_pop:
        raise SystemExit("state federal: state populations do not add up to the national Census estimate")
    ranked = sorted((p for p in states if p["slug"] != "district-of-columbia"),
                    key=lambda p: (-int(p["population"]["value"]), p["name"]))
    rank = {p["slug"]: i for i, p in enumerate(ranked, 1)}
    by = {}
    for p in states:
        slug = p["slug"]
        for key in ("ssa", "opm", "dmdc"):
            if slug not in doc[key]["states"]:
                raise SystemExit(f"state federal: {key} missing {slug}")
        if slug not in doc["usaspending"]["states_cents"]:
            raise SystemExit(f"state federal: USAspending missing {slug}")
        by[slug] = p
    ctx = {"debt": debt, "us_pop": us_pop, "pop_as_of": pop["as_of"],
           "pop_source": pop.get("source_name") or "U.S. Census Bureau, Vintage 2025",
           "interest": interest, "doc": doc, "rank": rank, "by": by}
    _CACHE[R] = ctx
    return ctx


def record_date(R):
    return runtime(R)["debt"]["as_of"]


def source_urls(R):
    doc = runtime(R)["doc"]
    return [DEBT_URL, CENSUS_POP, INTEREST_URL, doc["usaspending"]["api"],
            doc["ssa"]["source_url"], doc["opm"]["source_url"], doc["dmdc"]["source_url"]]


def _debt_at(debt, now):
    base = float(debt["base"])
    rate = 0.0 if debt.get("held_at_limit") else float(debt.get("rate") or 0)
    t0 = float(debt["t0"])
    freeze = debt.get("freeze_t")
    if rate and freeze and now > float(freeze):
        base = base + rate * (float(freeze) - t0)
        return base, 0.0, float(freeze)
    return base, rate, t0


def faq(R, profile):
    """One FAQ. The answer quotes the Treasury close, not the ticking projection."""
    ctx = runtime(R)
    slug = profile["slug"]
    place = ctx["by"][slug]
    debt = ctx["debt"]
    us_pop = ctx["us_pop"]
    state_pop = int(place["population"]["value"])
    base = float(debt["base"])
    pp = round(base / us_pop, 2)
    share = base * state_pop / us_pop
    name = place["name"]
    if slug == "district-of-columbia":
        q = "What is the District of Columbia's share of the federal debt?"
        who = "The District of Columbia's"
    else:
        q = f"What is {name}'s share of the federal debt?"
        who = f"{name}'s"
    a = (f"As of {_long(debt['as_of'])}, each resident's share of the federal debt was {_usd2(pp)}: "
         f"Treasury's {_usd2(base)} divided by {us_pop:,} U.S. residents on {_long(ctx['pop_as_of'])} (Census). "
         f"{who} share was {_usd0(share)} ({state_pop:,} residents). "
         f"Source: U.S. Treasury, Debt to the Penny, and the U.S. Census Bureau. "
         f"The page ticks that share forward. The tick is a projection.")
    return q, a


def section(R, place, now, tile_html, page_url, img):
    ctx = runtime(R)
    doc = ctx["doc"]
    debt = ctx["debt"]
    us_pop = ctx["us_pop"]
    slug = place["slug"]
    name = place["name"]
    state_pop = int(place["population"]["value"])
    frac = state_pop / us_pop
    base, rate, t0 = _debt_at(debt, now)
    pp_off = round(float(debt["base"]) / us_pop, 2)
    share_off = float(debt["base"]) * frac
    live_pp = (base + rate * (now - t0)) / us_pop
    live_share = (base + rate * (now - t0)) * frac
    interest = ctx["interest"]
    interest_amt = float(interest["amount_usd"])
    interest_fy = interest["fiscal_year"]
    interest_asof = interest["as_of"]
    share_i = interest_amt * frac
    pp_i = interest_amt / us_pop
    awards = doc["usaspending"]["states_cents"][slug] / 100
    awards_pp = awards / state_pop
    ssa_n = doc["ssa"]["states"][slug]
    opm_n = doc["opm"]["states"][slug]
    mil_n = doc["dmdc"]["states"][slug]
    as_of = _date(debt["as_of"])
    tick = rate != 0
    proj = (f'<span class="badge proj" title="Projected from the Treasury close of {E(as_of)} at the same 90-day trend as the U.S. clock">PROJECTED · from {E(as_of)}</span>'
            if tick else f'<span class="badge fix">FIXED · {E(as_of)}</span>')
    fix = lambda label: f'<span class="badge fix">FIXED · {E(label)}</span>'

    def dlg(label, method, src_name, src_url, official, base_=None, r=None, cents=False):
        return {"l": label, "m": method, "s": src_name, "u": src_url, "loc": "",
                "b": base_, "r": r, "t0": t0 if r else None, "o": official,
                "share": page_url, "img": img, "cents": cents}

    pp_method = (f"Treasury total public debt outstanding at the {as_of} close, divided by the Census estimate of "
                 f"{us_pop:,} U.S. residents on {_date(ctx['pop_as_of'])}. The same per resident in every state. "
                 f"The population is not projected. The debt ticks at the 90-day Treasury trend, about "
                 f"${rate * 86400 / us_pop:,.2f} per resident per day. This is not {name} government debt.")
    share_method = (f"{name} population {state_pop:,} on {_date(place['population']['as_of'])} divided by "
                    f"{us_pop:,} U.S. residents, times the Treasury total. "
                    f"That population share is {frac * 100:.2f}%. The ticking number is a projection from the {as_of} close.")
    tiles = []
    tiles.append(tile_html(
        "fed_pp", "Federal debt per resident", _usd2(live_pp), "var(--red)", proj,
        f"+${rate * 86400 / us_pop:,.2f}/day" if tick else f"as of {as_of}",
        pp=[("Official close", _usd2(pp_off), None), ("U.S. population", f"{us_pop:,}", None)],
        tick=(float(debt["base"]) / us_pop, rate / us_pop, t0) if tick else None,
        dlg=dlg("Federal debt per resident", pp_method, "Treasury, Debt to the Penny", DEBT_URL,
                f"{_usd2(pp_off)} at the {as_of} close", float(debt["base"]) / us_pop, rate / us_pop if tick else None, True)))
    share_rate = f"+${_short(rate * frac)}/sec · +${_short(rate * frac * 86400)}/day" if tick else f"as of {as_of}"
    tiles.append(tile_html(
        "fed_share", f"{name}'s share of the federal debt", _usd0(live_share), "var(--red)", proj, share_rate,
        pp=[("Official close", _usd0(share_off), None), ("Population share", f"{frac * 100:.2f}%", None)],
        tick=(share_off, rate * frac, t0) if tick else None,
        dlg=dlg(f"{name}'s share of the federal debt", share_method, "Treasury, Debt to the Penny", DEBT_URL,
                f"{_usd0(share_off)} at the {as_of} close", share_off, rate * frac if tick else None)))
    i_method = (f"Treasury interest expense on the public debt outstanding for fiscal year {interest_fy}, "
                f"the year ended {_date(interest_asof)}: {_usd0(interest_amt)}. "
                f"{name}'s figure is that total times its Census population share ({frac * 100:.2f}%). "
                f"A finished year. It does not tick.")
    tiles.append(tile_html(
        "fed_interest", f"Share of FY{interest_fy} interest", _usd0(share_i), "var(--orange)", fix(f"FY{interest_fy}"),
        "does not tick",
        pp=[("Per resident", _usd2(pp_i), None), ("U.S. total", "$" + _short(interest_amt), None)],
        dlg=dlg(f"{name}'s share of federal interest", i_method,
                "Treasury, Interest Expense on the Public Debt Outstanding", INTEREST_URL,
                f"{_usd0(share_i)} for FY{interest_fy}")))
    usa = doc["usaspending"]
    usa_url = f"https://www.usaspending.gov/state/{slug}/2026"
    a_method = (f"Prime-award transaction amounts with a place of performance in {name}, "
                f"FY{usa['fiscal_year']} ({_date(usa['start'])}–{_date(usa['end'])}), "
                f"as reported by USAspending on {_date(usa['pulled'])}. "
                f"Per resident uses the July 1, 2025 Census estimate, not USAspending's population. "
                f"Not most federal salaries, and not a resident's benefit check. Late reports can still change it.")
    tiles.append(tile_html(
        "fed_awards", f"Federal awards in {name}, FY{usa['fiscal_year']}", _usd0(awards), "var(--blue)",
        fix(f"FY{usa['fiscal_year']}"), "does not tick",
        pp=[("Per resident", _usd0(awards_pp), None), ("Place of performance", "FY2026", None)],
        dlg=dlg(f"Federal awards in {name}", a_method, "USAspending.gov", usa_url, f"{_usd0(awards)} in FY{usa['fiscal_year']}")))

    if slug == "district-of-columbia":
        rank = "The District is not in the 50-state ranking. Its share uses the same population math."
    else:
        n = ctx["rank"][slug]
        if n == 1:
            rank = f"{name} has the largest share of the 50 states, because it has the largest population."
        elif n == 50:
            rank = f"{name} has the smallest share of the 50 states, because it has the smallest population."
        else:
            rank = f"{name}'s share ranks {_ord(n)} of the 50 states, the same rank as its population."

    plain = name if slug != "district-of-columbia" else "the District"
    ssa, opm, mil = doc["ssa"], doc["opm"], doc["dmdc"]
    opm_note = ""
    if slug in ("maryland", "virginia", "west-virginia", "district-of-columbia"):
        opm_note = " Some Maryland, Virginia, and West Virginia duty stations are counted in the District of Columbia."
    parts = [
        f'<section id="federal"><div class="sh"><span class="bar" style="background:var(--red)"></span>'
        f'<h2>Federal debt in {E(name)}</h2><span class="h2n">Updated {_date(debt["as_of"])}</span></div>'
        f'<p>{E(name)}\'s share is its Census population times U.S. debt per resident. '
        f'Per resident, states match. Not {E(plain)} government debt. Debt figures tick. The rest do not. {E(rank)}</p>'
        '<div class="grid dense">',
        "".join(tiles),
        '</div>'
        f'<p class="src"><a href="{DEBT_URL}" rel="noopener">Debt to the Penny</a>, {E(as_of)}. '
        f'<a href="{E(place["population"]["source_url"])}" rel="noopener">Census Vintage 2025</a>, {_date(ctx["pop_as_of"])}. '
        f'<a href="{INTEREST_URL}" rel="noopener">Interest expense</a>, FY{E(interest_fy)} ended {_date(interest_asof)}, U.S. total {_usd0(interest_amt)}. '
        f'<a href="{E(usa_url)}" rel="noopener">USAspending</a> FY{usa["fiscal_year"]} awards performed in {E(name)}, pulled {_date(usa["pulled"])}. '
        f'Not most salaries or benefit checks.</p>'
        f'<h3>If the debt-limit X-date hits</h3>'
        f'<p>The X-date is when Treasury expects to run short of cash. <a href="../../debt-limit/">Debt limit and the X-date</a>.</p><ul>'
        f'<li><b>{ssa_n:,}</b> Social Security beneficiaries, {E(ssa["label"])}. '
        f'<a href="{E(ssa["source_url"])}" rel="noopener" title="{E(ssa["source_name"])}">SSA Table 2</a>.</li>'
        f'<li><b>{opm_n:,}</b> federal civilian employees, {E(opm["label"])}'
        f'{" (preliminary)" if opm.get("preliminary") else ""}. No Postal Service or intelligence agencies.{opm_note} '
        f'{opm["redacted"]:,} redacted, in no state. '
        f'<a href="{E(opm["source_url"])}" rel="noopener" title="{E(opm["source_name"])}">OPM FedScope</a>.</li>'
        f'<li><b>{mil_n:,}</b> active duty, {E(mil["label"])}. Not Guard or reserve. Not all who are deployed. '
        f'<a href="{E(mil["file_url"])}" rel="noopener" title="{E(mil["source_name"])}">DMDC</a>.</li></ul>'
        f'<p class="src">Cite: Every Debt Clock, from the links in this section.</p></section>',
    ]
    return "".join(parts)


def check(R):
    """Fail if a state page dropped the federal block, and print the accuracy spot checks."""
    ctx = runtime(R)
    debt = ctx["debt"]
    us_pop = ctx["us_pop"]
    base = float(debt["base"])
    pp = round(base / us_pop, 2)
    interest = float(ctx["interest"]["amount_usd"])
    doc = ctx["doc"]
    print("state federal accuracy review")
    print(f"  debt close {debt['as_of']} {base:,.2f}  per resident {pp:,.2f}  U.S. pop {us_pop:,}")
    print(f"  interest FY{ctx['interest']['fiscal_year']} ended {ctx['interest']['as_of']} {interest:,.2f}  per resident {interest / us_pop:,.2f}")
    print(f"  SSA all areas {doc['ssa']['all_areas']:,}  OPM redacted {doc['opm']['redacted']:,}  "
          f"DMDC U.S. active duty {doc['dmdc']['us_total_active_duty']:,} (states+DC {sum(doc['dmdc']['states'].values()):,})")
    print(f"  USAspending FY{doc['usaspending']['fiscal_year']} pulled {doc['usaspending']['pulled']}  "
          f"states+DC ${sum(doc['usaspending']['states_cents'].values()) / 100:,.0f}")
    spots = ("texas", "california", "new-york", "florida", "wyoming")
    missing = []
    for slug, place in sorted(ctx["by"].items()):
        path = os.path.join(R, "states", slug, "index.html")
        text = open(path, encoding="utf-8").read()
        state_pop = int(place["population"]["value"])
        share = base * state_pop / us_pop
        need = [
            'id="federal"', 'id="t-fed_pp"', 'id="t-fed_share"', 'id="t-fed_interest"', 'id="t-fed_awards"',
            'href="../../debt-limit/"', DEBT_URL, INTEREST_URL,
            doc["ssa"]["source_url"], "usaspending.gov", "opm.gov", "dmdc.osd.mil",
            f"{doc['ssa']['states'][slug]:,}", f"{doc['opm']['states'][slug]:,}", f"{doc['dmdc']['states'][slug]:,}",
            _usd2(pp), _usd0(share),
        ]
        for bit in need:
            if bit not in text:
                missing.append(f"{slug}: missing {bit[:80]}")
        # Yearly figures must not tick. The two debt figures must.
        for tid, should_tick in (("t-fed_pp", True), ("t-fed_share", True), ("t-fed_interest", False), ("t-fed_awards", False)):
            start = text.find(f'id="{tid}"')
            chunk = text[start:start + 400]
            has_rate = "data-r=" in chunk
            if has_rate != should_tick:
                missing.append(f"{slug}: {tid} tick={has_rate}, expected {should_tick}")
        if text.find('id="t-total"') > text.find('id="federal"'):
            missing.append(f"{slug}: federal block is above the state clock")
        if slug in spots:
            frac = state_pop / us_pop
            print(f"  {place['name']}: pop {state_pop:,} ({frac * 100:.4f}%) rank {ctx['rank'].get(slug, 'DC')}  "
                  f"share {_usd0(share)}  interest {_usd0(interest * frac)}  "
                  f"awards {_usd0(doc['usaspending']['states_cents'][slug] / 100)}  "
                  f"SSA {doc['ssa']['states'][slug]:,}  OPM {doc['opm']['states'][slug]:,}  "
                  f"active duty {doc['dmdc']['states'][slug]:,}")
    if missing:
        raise SystemExit("state federal check failed:\n" + "\n".join(missing[:20]))
    print(f"state federal: {len(ctx['by'])} pages, spot checks {', '.join(spots)}")
