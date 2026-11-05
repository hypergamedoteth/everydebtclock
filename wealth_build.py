"""Wealth tab: the opposite of the debt clocks. /wealth/ ranks sovereign wealth funds by assets; /wealth/<slug>/ is one page per fund.
Source data is committed in wealth_src/funds.json (every figure carries its source, date and basis). Nothing here ticks: the figures are the funds' own
latest disclosures, or a labelled third-party estimate where the fund publishes no total. Built by build.py after the place pages."""
import json, os, html
import places_build as pb
import explore as ex

E = html.escape
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wealth_src", "funds.json")
QUALITY = {  # label, short label, sort rank
    "full": ("Full: official total and allocation", "Full", 0),
    "total": ("Total only: official total, no allocation", "Total only", 1),
    "partial": ("Partial: official allocation or ranges, total estimated", "Partial", 2),
    "estimate": ("Estimate only: nothing published by the fund", "Estimate only", 3)}
BASIS = {"official": "Official", "official_converted": "Official, converted to USD", "estimate": "Estimate"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

def _date(s):
    """'2026-09-30' -> 'Sep 30, 2026'; '2026-10' -> 'Oct 2026'; anything else is shown as written."""
    try:
        p = s.split("-")
        if len(p) == 3: return f"{MONTHS[int(p[1]) - 1]} {int(p[2])}, {p[0]}"
        if len(p) == 2: return f"{MONTHS[int(p[1]) - 1]} {p[0]}"
    except Exception: pass
    return s

def usd(bn):
    return f"${bn / 1000:,.2f} trillion" if bn >= 1000 else f"${bn:,.1f} billion"

def usd_short(bn):
    return f"${bn / 1000:,.2f}tn" if bn >= 1000 else f"${bn:,.0f}bn"

def load():
    d = json.load(open(SRC))
    funds = d["funds"]
    for f in funds:
        a = f["assets"]; f["usd"] = a["usd_bn"] * 1e9
        f["pp"] = f["usd"] / f["pop"]["value"]
        f["url"] = f"wealth/{f['slug']}/"
        f["qual"] = QUALITY[f["quality"]]
        if a.get("local") and a.get("fx"):  # a converted figure must equal local amount x rate, so the USD shown can never drift from its own working
            want = a["local"]["amount_bn"] * a["fx"]["rate"]
            if abs(want - a["usd_bn"]) > 0.0006 * want: raise SystemExit(f"wealth: {f['slug']} usd_bn {a['usd_bn']} != {a['local']['amount_bn']} x {a['fx']['rate']} = {want:.3f}")
    funds.sort(key=lambda f: -f["assets"]["usd_bn"])  # the order the table shows is the order of the dollar figures it shows
    for i, f in enumerate(funds, 1): f["rank"] = i
    return d, funds

def prep(places):
    """Called before the place pages are built, so country pages and the search index can link to the fund pages."""
    d, funds = load()
    live = {p["slug"] for p in places}
    ex.WEALTH = [dict(name=f["nick"], slug=f["slug"], place_slug=f.get("place_slug") if f.get("place_slug") in live else None, country=f["country"], short=f["short"], name_long=f["name"]) for f in funds]
    pb.WEALTH = bool(funds)
    return d, funds

CSS = """.wt{width:100%;border-collapse:collapse;font-size:13.5px;min-width:820px}.wt th,.wt td{border-bottom:1px solid var(--line);padding:8px 9px;text-align:left;vertical-align:top}
.wt th{color:var(--mut);font-weight:600;font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;white-space:nowrap}.wt td.num,.wt th.num{text-align:right;font-family:ui-monospace,Menlo,monospace;white-space:nowrap}
.wt td.m{color:var(--mut);font-size:12.5px}.wt a{color:var(--blue)}.wt td.c{min-width:170px}.tw{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--line);border-radius:12px;padding:0 4px}
.wt th.s{cursor:pointer}.wt th.s:hover{color:var(--txt)}.wt th.s[aria-sort=ascending]:after{content:" \\25B2"}.wt th.s[aria-sort=descending]:after{content:" \\25BC"}
.wsec{margin:0 0 26px}.wnote{border:1px solid #5a3a12;background:#20170a;color:#ffb547;border-radius:10px;padding:10px 12px;font-size:13.5px;margin:0 0 14px}
.wnote.ok{border-color:#1d4a3a;background:#0b1d17;color:#7fe0bd}.bd{display:inline-block;border:1px solid var(--line);border-radius:6px;padding:2px 7px;font-size:11.5px;color:var(--mut);white-space:nowrap}
.bd.off{border-color:#1d4a3a;color:#38d39f}.bd.est{border-color:#5a3a12;color:#ffb547}.bd.pa{border-color:#1e3a5c;color:#9fd0ff}
.bar2{display:block;height:6px;border-radius:3px;background:var(--blue);min-width:2px;margin-top:4px}.wt td.bw{min-width:140px}
.wt td.bw .bar2.est{background:var(--amber)}.src{font-size:12.5px;color:var(--mut)}.src a{color:var(--blue)}.eq{font-family:ui-monospace,Menlo,monospace;font-size:13.5px;color:var(--txt)}
.wfacts{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px;margin:0 0 18px}.wfacts div{border:1px solid var(--line);border-radius:10px;padding:9px 11px;background:var(--panel)}
.wfacts .l{display:block;color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.05em}.wfacts .v{display:block;font-size:15px;margin-top:2px;overflow-wrap:anywhere}
@media (max-width:640px){.wt{font-size:13px}.wt.wstk,.wt.wstk tbody{display:block;min-width:0!important;width:100%}.wt.wstk tr.hd{display:none}.wt.wstk tr{display:block;border-bottom:1px solid var(--line);padding:8px 2px}.wt.wstk tr:last-child{border-bottom:0}
.wt.wstk td{display:flex;justify-content:space-between;gap:14px;border:0;padding:3px 8px;text-align:right;white-space:normal;min-width:0!important}.wt.wstk td:before{content:attr(data-l);color:var(--mut);font-size:11.5px;text-transform:uppercase;letter-spacing:.04em;text-align:left;flex:none}
.wt.wstk td.c{display:block;text-align:left;font-size:15px;padding-bottom:5px}.wt.wstk td.c:before{display:none}.wt.wstk td.bw{display:block}.wt.wstk td.bw:before{display:none}}"""

def _src(s, label=None):
    """One source as 'Name, published ..., locator' with a link."""
    pub = f", published {E(_date(s['published']))}" if s.get("published") and s["published"][:2] in ("20",) and len(s["published"]) <= 10 and s["published"][4:5] == "-" else (f", {E(s['published'])}" if s.get("published") else "")
    loc = f" ({E(s['locator'])})" if s.get("locator") else ""
    return f'<a href="{E(s["url"])}" rel="noopener">{E(label or s["name"])}</a>{pub}{loc}'

HEAD_NAV = lambda places, depth, cur: pb.nav_html(places, depth, cur, "plnav")

def _header(places, depth, jump):
    up = "../" * depth
    return (f'<header class="top"><div class="topin"><a class="brand" href="{up}">EVERY <b>DEBT</b> CLOCK</a>{HEAD_NAV(places, depth, "wealth")}'
            f'<span class="live"><span class="dot"></span><span>official disclosures</span></span></div>'
            f'<nav class="jump">' + "".join(f'<a href="#{i}">{E(t)}</a>' for i, t in jump) + "</nav></header>")

def _foot(depth):
    up = "../" * depth
    return (f'<footer class="site-foot">Every Debt Clock · official data, estimates labelled · <a href="{up}methodology/">Methodology</a> · <a href="{up}privacy.html">Privacy</a> · '
            'Independent site, not affiliated with any government or fund. Not financial advice.</footer>')

def _alloc_table(blk, est=False):
    rows = ""
    unit = blk.get("unit")
    mx = max([r.get("pct", r.get("hi", 0)) for r in blk["rows"]] + [1])
    for r in blk["rows"]:
        if "lo" in r:
            val = f'{r["lo"]}–{r["hi"]}%'; w = r["hi"] / mx * 100
        else:
            val = (f'{r["pct"]:.{r["dp"]}f}%' if "dp" in r else f'{r["pct"]:g}%'); w = r["pct"] / mx * 100
        amt = f'<td class="num" data-l="{E(unit)}">{r["amount"]:,.0f}</td>' if unit and "amount" in r else ""
        rows += f'<tr><td class="c">{E(r["name"])}</td><td class="num" data-l="Share{" (target range)" if "lo" in r else ""}">{val}</td>{amt}<td class="bw"><span class="bar2{" est" if "lo" in r else ""}" style="width:{w:.1f}%"></span></td></tr>'
    has_amt = bool(unit and any("amount" in r for r in blk["rows"]))
    hd = f'<tr class="hd"><th>Category</th><th class="num">{"Target range" if "lo" in blk["rows"][0] else "Share"}</th>{f"<th class=num>{E(unit)}</th>" if has_amt else ""}<th></th></tr>'
    return f'<div class="tw"><table class="wt wstk" style="min-width:520px">{hd}{rows}</table></div>'

def _holdings_table(blk):
    rows = "".join(f'<tr><td class="c">{i}. {E(r["name"])}</td><td class="num" data-l="Value, {E(blk["unit"])}">{r["value"]:,.0f}</td></tr>' for i, r in enumerate(blk["rows"], 1))
    return f'<div class="tw"><table class="wt wstk" style="min-width:420px"><tr class="hd"><th>Holding</th><th class="num">Value, {E(blk["unit"])}</th></tr>{rows}</table></div>'

def _invest(f):
    out = ""
    a, rg, sc, hd = f.get("alloc"), f.get("regions"), f.get("sectors"), f.get("holdings")
    if not (a or rg or sc or hd):
        return ('<div class="wnote">Not disclosed. ' + E(f["short"]) + ' does not publish its asset-class mix, regional mix or holdings, so none is shown here. '
                'This page does not guess one.' + (' Stakes that filings and news have reported are listed above, under what it owns.' if f.get('detail') else '') + '</div>')
    def blk(title, b, tbl):
        return (f'<h3>{E(title)}</h3><p class="src">As of {E(_date(b["as_of"]))}. Source: {_src(b["source"])}.</p>' + tbl + (f'<p class="dnote">{E(b["note"])}</p>' if b.get("note") else ""))
    if a: out += blk(a.get("title", "By asset class"), a, _alloc_table(a))
    else: out += '<h3>By asset class</h3><div class="wnote">Not disclosed. The fund does not publish an asset-class mix.</div>'
    if sc: out += blk(sc["title"], sc, _alloc_table(sc))
    if rg: out += blk(rg["title"], rg, _alloc_table(rg))
    elif f["quality"] != "estimate": out += '<h3>By region</h3><p class="dnote">No regional mix is shown. We only show one when the fund publishes it in the report this page is built from.</p>'
    if hd: out += blk("Largest holdings", hd, _holdings_table(hd))
    else: out += '<h3>Notable holdings</h3><p class="dnote">No holdings table is shown. We only show one when every line can be checked against the fund\'s own report, and none has been for this fund. Any named investments are in its own report, linked under Sources.</p>'
    return out

def _detail(f):
    """Estimate / why / what it owns. Returns (html, [sources])."""
    d = f.get("detail")
    if not d: return "", []
    srcs = []
    def add(x):
        if x and x.get("url") and x["url"] not in [y["url"] for y in srcs]: srcs.append(dict(name=x["name"], url=x["url"]))
    h = d.get("h") or ["The estimate", "Why this estimate", "What it owns"]
    rr = "".join(f'<tr><td class="c">{E(r["label"])}</td><td class="num" data-l="Value">{E(r["value"])}</td><td class="m" data-l="Source">{E(r["when"])} · {_src(r["source"])}</td></tr>' for r in d["range"])
    for r in d["range"]: add(r["source"])
    out = (f'<section id="estimate" class="wsec"><div class="sh"><span class="bar" style="background:var(--amber)"></span><h2>{E(d.get("title", "Size and holdings, in detail"))}</h2><span class="h2n">Every line sourced</span></div>'
           f'<h3>{E(h[0])}</h3>' + (f'<p>{E(d["summary"])}</p>' if d.get("summary") else "")
           + f'<div class="tw"><table class="wt wstk" style="min-width:560px"><tr class="hd"><th>Figure</th><th class="num">Value</th><th>Date and source</th></tr>{rr}</table></div>'
           + f'<h3>{E(h[1])}</h3>')
    for w in d["why"]:
        for x in w.get("sources", []): add(x)
        ss = " ".join(f'<a href="{E(x["url"])}" rel="noopener">{E(x["name"])}</a>' for x in w.get("sources", []))
        out += f'<p>{E(w["text"])}' + (f' <span class="src">Sources: {ss}</span>' if ss else "") + '</p>'
    if d.get("cant"): out += f'<p class="dnote"><b>What we could not source:</b> {E(d["cant"])}</p>'
    o = d.get("owns")
    if o:
        orows = "".join(f'<tr><td class="c">{E(r["name"])}</td><td data-l="Stake">{E(r["stake"])}</td><td class="m" data-l="Date and source">{E(r["as_of"])} · {_src(r["source"])}</td></tr>' for r in o["rows"])
        for r in o["rows"]: add(r["source"])
        out += (f'<h3>{E(h[2])}</h3><div class="tw"><table class="wt wstk" style="min-width:560px"><tr class="hd"><th>Holding</th><th>Stake</th><th>Date and source</th></tr>{orows}</table></div>'
                + (f'<p class="dnote">{E(o["note"])}</p>' if o.get("note") else ""))
    return out + '</section>', srcs

def fund_page(R, SITE, with_analytics, og, places, f, funds, place_url):
    a, pop = f["assets"], f["pop"]
    url = f"{SITE}/wealth/{f['slug']}/"
    title = f"{f['nick']}: Assets, Per Citizen and Holdings"
    est = a["basis"] == "estimate"
    bn = a["usd_bn"]
    pp = f["pp"]
    qlabel = f["qual"][0]
    if est:
        desc = f"{f['nick']} assets: about {usd(bn)} (Global SWF estimate; the fund does not publish its total), or about ${pp:,.0f} per person in {f['country']}. What is and is not disclosed, with sources."
    else:
        desc = f"{f['nick']} assets: {usd(bn)} at {_date(a['as_of'])}" + (f" ({a['local']['label']})" if a.get("local") else "") + f", or ${pp:,.0f} per person in {f['country']}. Asset mix, regions and holdings, with sources."
    img = f"og/wealth/{f['slug']}.png"
    if og:
        os.makedirs(f"{R}/og/wealth", exist_ok=True)
        og(f"{R}/{img}", f"{f['nick']} · assets", ("≈" if est else "") + usd_short(bn),
           [("Per person in " + f["country"], f"${pp:,.0f}"), ("Estimate by Global SWF" if est else f"Official, {_date(a['as_of'])}", qlabel.split(":")[0])],
           "ESTIMATE" if est else "OFFICIAL", "#38d39f", "Fund disclosures and official population figures\nsources linked on the page")
    srcs = []
    def add(s):
        if s and s["url"] not in [x["url"] for x in srcs]: srcs.append(dict(name=s["name"], url=s["url"]))
    add(a["source"]); add(dict(name=pop["source"], url=pop["url"]))
    if a.get("fx"): add(dict(name="ECB euro reference rates" if "ECB" in a["fx"]["source"] else a["fx"]["source"], url=a["fx"]["url"]))
    for k in ("alloc", "regions", "sectors", "holdings"):
        if f.get(k): add(f[k]["source"])
    det_html, det_srcs = _detail(f)
    for x in det_srcs: add(x)
    ld = '<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "Dataset", "name": f"{f['name']}: assets, assets per citizen and holdings", "description": desc, "url": url,
        "isAccessibleForFree": True, "creator": {"@type": "Organization", "name": "Every Debt Clock", "url": SITE + "/"},
        "spatialCoverage": {"@type": "Place", "name": f["country"]}, "temporalCoverage": a["as_of"], "isBasedOn": [s["url"] for s in srcs]}).replace("</", "<\\/") + "</script>"
    # ---- hero
    badge = ('<span class="bd est">ESTIMATE · not published by the fund</span>' if est else
             '<span class="bd off">OFFICIAL · converted to USD</span>' if a["basis"] == "official_converted" else '<span class="bd off">OFFICIAL</span>')
    loc = (f'<div><span class="l">In local currency</span><span class="num">{E(a["local"]["label"])}</span></div>' if a.get("local") else
           f'<div><span class="l">In local currency</span><span class="num" style="font-size:14px">{E(a.get("local_note", "Not reported in a local currency"))}</span></div>')
    hero = (f'<div class="hero lead" id="assets" style="cursor:default"><div class="k">{E(f["name"])} · total assets · {"estimate" if est else "official"}</div>'
            f'<div class="big num">{"≈ " if est else ""}{usd(bn)}</div>'
            f'<div class="sub"><span>{"Global SWF estimate, " + E(_date(a["as_of"])) if est else "As of " + E(_date(a["as_of"]))}</span>{"" if est or a["basis"] != "official" or a.get("round") else f'<span class="note">${bn * 1e9:,.0f}</span>'}'
            f'<span>Per person in {E(f["country"])}: <b>{"≈ " if est else ""}${pp:,.0f}</b></span></div>'
            f'<div class="trio"><div><span class="l">Assets, USD</span><span class="num">{usd(bn)}</span></div>{loc}'
            f'<div><span class="l">Per person</span><span class="num">{"≈ " if est else ""}${pp:,.0f}</span></div></div>'
            f'<div class="meta" style="margin-top:10px">{badge}<span class="bd pa">{E(qlabel)}</span></div></div>')
    jump = [("assets", "Assets")] + ([("estimate", "Estimate and holdings")] if det_html else []) + [("percitizen", "Per citizen"), ("invested", "Where it is invested"), ("disclosure", "Disclosure"), ("sources", "Sources")]
    crumb = '<div class="crumb"><a href="../../">← US national debt clock</a><span>·</span><a href="../">All sovereign wealth funds</a>' + (f'<span>·</span><a href="../../{place_url}">{E(f["country"])} debt clock</a>' if place_url else "") + '</div>'
    intro_txt = f["blurb"]
    if est: intro_txt += f' Its total is not published, so the figure on this page is a third-party estimate (Global SWF) and is labelled as one.' + (' Below: the range of estimates, how they are reached, and what the fund is known to own.' if f.get('detail') else '')
    intro = f'<section class="intro" id="intro">{crumb}<h1>{E(f["nick"])}: Assets, Per Citizen and Holdings</h1><p>{E(intro_txt)} Managed by {E(f["manager"])}. Figures do not tick: they are the latest disclosure, with the date shown.</p></section>'
    # ---- assets table
    srow = lambda k, v, m="": f'<tr><td class="c">{k}</td><td class="num" data-l="Value">{v}</td><td class="m" data-l="Detail">{m}</td></tr>'
    ar = srow("Total assets, US dollars", ("≈ " if est else "") + usd(bn), (f"${bn * 1e9:,.0f}. " if a["basis"] == "official" and not a.get("round") else "") + ("Estimate; " + E(a["estimate_note"]) if est else ("Converted from the official local-currency figure below." if a["basis"] == "official_converted" else "As reported by the fund.")))
    if a.get("local"): ar += srow("Total assets, local currency", E(a["local"]["label"]), "Official figure as published.")
    ar += srow("As of", E(_date(a["as_of"])), "Estimate date: the month the ranking was published." if est else "Date of the fund's own figure.")
    ar += srow("Source", "", _src(a["source"]))
    if a.get("fx"):
        fx = a["fx"]
        ar += srow("Exchange rate used", f'{fx["rate"]:.6f} USD per unit', f'{E(fx["quote"])} · {E(fx["source"])} · {E(fx["date"] if fx["date"] == "fixed peg" else _date(fx["date"]))} · <a href="{E(fx["url"])}" rel="noopener">source</a>')
    sect_assets = (f'<section id="assets-detail" class="wsec"><div class="sh"><span class="bar" style="background:var(--teal)"></span><h2>Total assets</h2><span class="h2n">{"Estimate, labelled" if est else "Official figure"}{" · converted at the rate shown" if a["basis"] == "official_converted" else ""}</span></div>'
                   + (f'<div class="wnote">{E(a["estimate_note"])} Treat it as an estimate: it is not a disclosure by {E(f["short"])}.</div>' if est else "")
                   + f'<div class="tw"><table class="wt wstk" style="min-width:560px"><tr class="hd"><th>Item</th><th class="num">Value</th><th>Detail</th></tr>{ar}</table></div>'
                   + (f'<p class="dnote">{E(a["note"])}</p>' if a.get("note") else "") + '</section>')
    # ---- per citizen
    scope = pop["scope"]
    pc = (f'<section id="percitizen" class="wsec"><div class="sh"><span class="bar" style="background:var(--blue)"></span><h2>Assets per citizen</h2><span class="h2n">Total assets ÷ population</span></div>'
          f'<p class="eq">${bn:,.1f} billion ÷ {pop["value"]:,.0f} people = <b>{"about " if est else ""}${pp:,.0f}</b> per person</p>'
          f'<div class="wfacts"><div><span class="l">Population used</span><span class="v">{pop["value"]:,.0f}</span></div><div><span class="l">Population date</span><span class="v">{E(_date(pop["as_of"]) if pop["as_of"][:2] == "20" else pop["as_of"])}</span></div>'
          f'<div><span class="l">Population source</span><span class="v"><a href="{E(pop["url"])}" rel="noopener">{E(pop["source"])}</a></span></div>'
          f'<div><span class="l">Source type</span><span class="v">{"National statistics office" if pop["office"] else "IMF estimate (the national office figure could not be reached)"}</span></div></div>'
          f'<p class="dnote">Population counted: {E(scope)}. "Per citizen" here means per person in that population; ' + E(f.get("ownership_note", "the fund belongs to the state, and no individual owns a share of it")) + '. '
          + ("The assets are an estimate, so this figure is too. " if est else "")
          + ("The assets and the population are from different dates. " if a["as_of"][:4] != pop["as_of"][:4] else "")
          + (f"Other funds in {E(f['country'])} are not included in this per-person figure. " if f.get("other_funds") else "")
          + '</p>' + (f'<p class="dnote">{E(f["other_funds"])}</p>' if f.get("other_funds") else "") + '</section>')
    notes = ("<ul>" + "".join(f"<li>{E(n)}</li>" for n in f["notes"]) + "</ul>") if f.get("notes") else ""
    inv = (f'<section id="invested" class="wsec"><div class="sh"><span class="bar" style="background:var(--violet)"></span><h2>Where the money is invested</h2><span class="h2n">What the fund discloses, with date and source</span></div>'
           + _invest(f) + notes + '</section>')
    why = {"full": f"{f['short']} publishes its total value and an allocation. Every number on this page is from its own report, except any dollar conversion, percentage or per-person figure, which we calculate and say so where it appears.",
           "total": f"{f['short']} publishes audited total assets but no asset-class mix, so only the total and the per-person figure are shown.",
           "partial": f"{f['short']} publishes an allocation or ranges and returns, but not its total assets. The total here is a labelled third-party estimate.",
           "estimate": f"{f['short']} publishes neither its total assets nor an allocation. The only number here is a labelled third-party estimate, and no holdings table is shown. Stakes reported in filings and news are listed separately, each with its source."}[f["quality"]]
    disc = (f'<section id="disclosure" class="wsec"><div class="sh"><span class="bar" style="background:var(--amber)"></span><h2>How much it discloses</h2></div>'
            f'<p><span class="bd pa">{E(qlabel)}</span></p><p>{E(why)}</p>'
            f'<p class="dnote">Disclosure labels: Full = official total and allocation; Total only = official total, no allocation; Partial = official allocation or ranges, estimated total; Estimate only = nothing published by the fund. '
            f'Estimates are from <a href="https://globalswf.com/ranking" rel="noopener">Global SWF</a> and are never presented as official.</p></section>')
    sl = "".join(f'<li><a href="{E(s["url"])}" rel="noopener">{E(s["name"])}</a></li>' for s in srcs)
    srcsec = (f'<section id="sources" class="wsec"><div class="sh"><span class="bar" style="background:var(--mut)"></span><h2>Sources</h2></div><div class="sk foot"><ul>{sl}</ul>'
              f'<p>Ranking: <a href="https://globalswf.com/ranking" rel="noopener">Global SWF</a>, October 2026 (fund #{f["swf_rank"]} among sovereign wealth funds by assets under management). '
              f'Machine-readable: <a href="../../api/wealth.json">/api/wealth.json</a>.</p></div></section>')
    others = [g for g in funds if g["country"] == f["country"] and g["slug"] != f["slug"]]
    near = [g for g in funds if g["slug"] != f["slug"] and g not in others]
    chips = lambda items: "".join(f'<a href="../../{u}">{E(n)}</a>' for n, u in items)
    xg = ""
    if others: xg += f'<div class="xg"><h3>Other funds in {E(f["country"])}</h3><div class="xc">{chips([(g["nick"], g["url"]) for g in others])}</div></div>'
    xg += f'<div class="xg"><h3>Other sovereign wealth funds</h3><div class="xc">{chips([(g["nick"], g["url"]) for g in near[:8]])}</div></div>'
    br = [("All sovereign wealth funds ranked", "wealth/"), ("US national debt clock", ""), ("World debt clock", "world/"), ("All country debt clocks", "countries/")]
    if place_url: br.insert(1, (f'{f["country"]} debt clock', place_url))
    xg += f'<div class="xg"><h3>Debt clocks</h3><div class="xc">{chips(br)}</div></div>'
    explore_html = f'<section class="explore" id="explore"><div class="sh"><h2>Explore more</h2></div>{xg}</section>'
    links = ('<section class="answers" id="answers"><ul><li><a href="../">Sovereign wealth funds ranked</a></li>' + (f'<li><a href="../../{place_url}">{E(f["country"])} debt clock</a></li>' if place_url else "") +
             '<li><a href="../../">US national debt clock</a></li><li><a href="../../api/wealth.json">Wealth funds as JSON</a></li></ul></section>')
    page = (pb.meta_head(SITE, url, title, desc, img, 2, pb.PL_CSS + CSS, ld) + _header(places, 2, jump) + ex.search_box("../../") + '<main id="app">' + hero + intro + sect_assets + det_html + pc + inv + disc + srcsec + '</main>' + explore_html + links + _foot(2) + "</body></html>")
    os.makedirs(f"{R}/wealth/{f['slug']}", exist_ok=True)
    open(f"{R}/wealth/{f['slug']}/index.html", "w").write(with_analytics(page))
    return url

SORT_JS = """<script>(function(){var t=document.getElementById('wr');if(!t)return;var b=t.tBodies[0],hs=t.querySelectorAll('th.s');
function sort(h,dir){var i=+h.dataset.i,num=h.dataset.t==='n',rows=[].slice.call(b.rows);rows.sort(function(x,y){var a=x.cells[i].dataset.v,c=y.cells[i].dataset.v;if(num){a=+a;c=+c;return dir*(a-c)}return dir*a.localeCompare(c)});
rows.forEach(function(r){b.appendChild(r)});hs.forEach(function(k){k.removeAttribute('aria-sort')});h.setAttribute('aria-sort',dir>0?'ascending':'descending')}
hs.forEach(function(h){h.tabIndex=0;var go=function(){sort(h,h.getAttribute('aria-sort')==='descending'?1:-1)};h.addEventListener('click',go);h.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();go()}})})})()</script>"""

def hub_page(R, SITE, with_analytics, og, places, funds, d, place_urls):
    n = len(funds); url = f"{SITE}/wealth/"
    tot = sum(f["usd"] for f in funds) / 1e12
    title = f"Sovereign Wealth Funds Ranked: Assets and Per Citizen"
    desc = f"{n} sovereign wealth funds ranked by assets, from {funds[0]['country']}'s {usd_short(funds[0]['usd'] / 1e9)} fund down, with assets per citizen and where the money is invested. Official figures; estimates are labelled."
    img = "og/wealth/index.png"
    if og:
        os.makedirs(f"{R}/og/wealth", exist_ok=True)
        og(f"{R}/{img}", f"Sovereign wealth funds ranked · {n} funds", f"${tot:,.1f} trillion", [("Largest", f"{funds[0]['short']} · {usd_short(funds[0]['usd'] / 1e9)}"), ("Funds", f"{n} · official or labelled estimate")],
           "RANKING", "#38d39f", "The opposite of the debt clocks\nsources linked per fund")
    ld = '<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "Dataset", "name": f"{n} sovereign wealth funds ranked: assets and assets per citizen", "description": desc, "url": url,
        "isAccessibleForFree": True, "creator": {"@type": "Organization", "name": "Every Debt Clock", "url": SITE + "/"},
        "isBasedOn": [d["ranking"]["url"]] + [f"{SITE}/{f['url']}" for f in funds]}).replace("</", "<\\/") + "</script>"
    jump = [("table", "Ranking"), ("method", "How it works"), ("funds", "All funds")]
    rows = ""
    for i, f in enumerate(funds, 1):
        a = f["assets"]; est = a["basis"] == "estimate"
        q = f["qual"]; cls = {"full": "off", "total": "off", "partial": "pa", "estimate": "est"}[f["quality"]]
        rows += (f'<tr><td class="num" data-l="Rank" data-v="{i}">{i}</td><td class="c" data-v="{E(f["nick"])}"><a href="{f["slug"]}/"><b>{E(f["name"].split(" (")[0])}</b></a></td>'
                 f'<td data-l="Country" data-v="{E(f["country"])}">{E(f["country"])}</td>'
                 f'<td class="num" data-l="Assets (USD)" data-v="{f["usd"]:.0f}" title="${f["usd"]:,.0f}">{"≈ " if est else ""}{usd_short(a["usd_bn"])}</td>'
                 f'<td class="m" data-l="Basis" data-v="{E(BASIS[a["basis"]])}">{"Estimate" if est else "Official"}{"" if est else (", " + E(_date(a["as_of"])))}{"<br>group total, not AuM" if a.get("group_total") else ""}</td>'
                 f'<td class="num" data-l="Per citizen (USD)" data-v="{f["pp"]:.2f}">{"≈ " if est else ""}${f["pp"]:,.0f}</td>'
                 f'<td class="num" data-l="Global SWF rank" data-v="{f["swf_rank"]}">{f["swf_rank"]}</td>'
                 f'<td data-l="Disclosure" data-v="{q[2]}"><span class="bd {cls}">{E(q[1])}</span></td></tr>')
    hd = ('<tr class="hd"><th class="s num" data-i="0" data-t="n" aria-sort="ascending">#</th><th class="s" data-i="1" data-t="s">Fund</th><th class="s" data-i="2" data-t="s">Country</th>'
          '<th class="s num" data-i="3" data-t="n">Assets (USD)</th><th class="s" data-i="4" data-t="s">Basis, as of</th><th class="s num" data-i="5" data-t="n">Per citizen (USD)</th><th class="s num" data-i="6" data-t="n">Global SWF rank</th><th class="s" data-i="7" data-t="n">Disclosure</th></tr>')
    table = (f'<section id="table" class="wsec"><div class="sh"><span class="bar" style="background:var(--teal)"></span><h2>Ranking by assets</h2><span class="h2n">Click a column to sort · figures do not tick</span></div>'
             f'<div class="tw"><table class="wt wstk" id="wr">{hd}{rows}</table></div>'
             '<p class="dnote">Assets are in US dollars. "Official" is the fund\'s own latest figure (converted at an official rate where it reports in another currency); "Estimate" is a third-party number because the fund does not publish a total. '
             'Per citizen = assets ÷ the country\'s population from its statistics office (or the IMF where none is reachable). Rows are ordered by the dollar figure shown, largest first. The Global SWF rank column is that list\'s own order, which can differ because it measures some funds differently. Rows marked "group total, not AuM" are a consolidated company balance sheet (banks, operating companies), which is much larger than a pool of investable savings and is not like-for-like with the others. Danantara is shown at Global SWF\'s estimate of the fund itself, not the $1 trillion its own announcements give.</p></section>')
    nest = sum(1 for f in funds if f["assets"]["basis"] == "estimate")
    intro = (f'<section class="intro" id="intro"><div class="crumb"><a href="../">← US national debt clock</a><span>·</span><a href="../world/">World debt clock</a><span>·</span><a href="../countries/">All country debt clocks</a></div>'
             f'<h1>Sovereign Wealth Funds Ranked: Assets and Per Citizen</h1>'
             f'<p>The debt clocks show what governments owe. This is the other side: the money states have set aside in sovereign wealth funds. {n} funds are ranked by assets, each with its total, '
             f'the same total per person in its country, and where the money is invested. Funds do not tick: each figure is the fund\'s latest disclosure, with its date and a link. '
             f'{nest} of the {n} funds publish no total, so their size is a third-party estimate and is marked as one.</p></section>')
    method = ('<section id="method" class="wsec"><div class="sh"><span class="bar" style="background:var(--mut)"></span><h2>How it works</h2><span class="h2n">Official first, estimates labelled</span></div><div class="sk foot">'
              '<p><b>Ranking.</b> Funds are ordered by the US-dollar assets shown in the table, largest first. The list of funds comes from the <a href="https://globalswf.com/ranking" rel="noopener">Global SWF</a> ranking of sovereign wealth funds (October 2026), whose own rank is shown in the last column. A fund appears here once every figure on its page has been checked against its own report or disclosure; '
              'a fund whose figures could not be checked is left off, so Global SWF ranks skip.</p>'
              '<p><b>Assets.</b> The fund\'s own annual report or official statement where one exists, with the date it covers. Where a fund reports in local currency, the page shows both and converts at the official rate on the as-of date (ECB reference rate, or the fixed central-bank peg). '
              'Where the fund does not publish its total, the page uses the Global SWF estimate and says so. Totals are not like-for-like: some are gross assets under management, some are a group balance sheet, and some are estimates. Each page says which.</p>'
              '<p><b>Per citizen.</b> Assets in US dollars ÷ the country\'s population. We use the national statistics office where its latest figure is reachable, otherwise the IMF World Economic Outlook population estimate, and each page names which. The count includes non-citizens (large in the Gulf and Singapore), '
              'and where a country has several funds each fund is divided separately, so per-person figures for the same country should not be added without care.</p>'
              '<p><b>Where the money is invested.</b> Only what the fund publishes: asset-class mix, regions and holdings. Where a fund does not publish them, the page says "not disclosed". Nothing is inferred.</p>'
              f'<p>Machine-readable: <a href="../api/wealth.json">/api/wealth.json</a>.</p></div></section>')
    fl = '<section class="answers" id="funds"><div class="sh"><h2>All funds</h2></div><ul>' + "".join(f'<li><a href="{f["slug"]}/">{E(f["nick"])}</a></li>' for f in funds) + '</ul>' \
         '<div class="sh"><h2>Debt clocks</h2></div><ul><li><a href="../">US national debt clock</a></li><li><a href="../world/">World debt clock</a></li><li><a href="../countries/">All country debt clocks</a></li><li><a href="../states/">All US state debt clocks</a></li></ul></section>'
    xg = ("".join(f'<a href="../{pu}">{E(c)} debt clock</a>' for pu, c in {pu: f["country"] for f in funds for pu in [place_urls.get(f["slug"])] if pu}.items()))
    explore_html = f'<section class="explore" id="explore"><div class="sh"><h2>Explore more clocks</h2></div><div class="xg"><h3>Debt clocks of fund countries</h3><div class="xc">{xg}</div></div></section>' if xg else ""
    page = (pb.meta_head(SITE, url, title, desc, img, 1, pb.PL_CSS + CSS, ld) + _header(places, 1, jump) + ex.search_box("../") + intro + '<main id="app">' + table + method + '</main>' + explore_html + fl + _foot(1) + SORT_JS + "</body></html>")
    os.makedirs(f"{R}/wealth", exist_ok=True)
    open(f"{R}/wealth/index.html", "w").write(with_analytics(page))
    return url

def build(R, SITE, with_analytics, og, places, d, funds):
    live = {p["slug"]: p for p in places}
    place_urls = {f["slug"]: f"{ex.SEC[live[f['place_slug']]['kind']]}/{f['place_slug']}/" for f in funds if f.get("place_slug") in live}
    urls = [hub_page(R, SITE, with_analytics, og, places, funds, d, place_urls)]
    for f in funds: urls.append(fund_page(R, SITE, with_analytics, og, places, f, funds, place_urls.get(f["slug"])))
    os.makedirs(f"{R}/api", exist_ok=True)
    json.dump({"_doc": "Sovereign wealth funds ranked by the USD assets shown (rank_by_assets); rank_global_swf is Global SWF's own rank. basis: official | official_converted | estimate. Per-citizen = assets ÷ population (see population source). Figures do not tick.",
               "ranking_source": d["ranking"], "funds": [{"slug": f["slug"], "name": f["name"], "country": f["country"], "rank_by_assets": f["rank"], "rank_global_swf": f["swf_rank"], "assets_usd": round(f["usd"]), "assets_basis": f["assets"]["basis"],
                "assets_as_of": f["assets"]["as_of"], "assets_local": f["assets"].get("local"), "assets_source": f["assets"]["source"]["url"], "population": f["pop"]["value"], "population_as_of": f["pop"]["as_of"],
                "population_source": f["pop"]["url"], "assets_per_person_usd": round(f["pp"], 2), "disclosure": f["quality"], "url": f"{SITE}/{f['url']}", **({"detail": f["detail"]} if f.get("detail") else {})} for f in funds]}, open(f"{R}/api/wealth.json", "w"), indent=1, ensure_ascii=False)
    return urls
