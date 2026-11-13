"""Search box and a 'Related clocks' block of exactly 3 links for every clock page (places, hubs, world, US homepage, wealth, topics).
Static and light: the search is client-side over api/search.json (names, aliases, urls; ~10 KB); the related links are plain
server-rendered anchors (neighbouring or similar-size states, regional or GDP peers, high-traffic pages), so they are crawlable and need no JS.
Called from build.py / places_build.py / world_build.py / wealth_build.py."""
import json, os, html

E = html.escape

# Land borders between the 50 states and the District of Columbia (Four Corners points count: AZ-CO, NM-UT). Checked for symmetry at build time (check()).
NEIGHBORS = {
 "alabama": "florida georgia mississippi tennessee", "alaska": "", "arizona": "california colorado nevada new-mexico utah",
 "arkansas": "louisiana missouri mississippi oklahoma tennessee texas", "california": "arizona nevada oregon",
 "colorado": "arizona kansas nebraska new-mexico oklahoma utah wyoming", "connecticut": "massachusetts new-york rhode-island",
 "delaware": "maryland new-jersey pennsylvania", "district-of-columbia": "maryland virginia", "florida": "alabama georgia", "georgia": "alabama florida north-carolina south-carolina tennessee",
 "hawaii": "", "idaho": "montana nevada oregon utah washington wyoming", "illinois": "indiana iowa kentucky missouri wisconsin",
 "indiana": "illinois kentucky michigan ohio", "iowa": "illinois minnesota missouri nebraska south-dakota wisconsin",
 "kansas": "colorado missouri nebraska oklahoma", "kentucky": "illinois indiana missouri ohio tennessee virginia west-virginia",
 "louisiana": "arkansas mississippi texas", "maine": "new-hampshire", "maryland": "delaware district-of-columbia pennsylvania virginia west-virginia",
 "massachusetts": "connecticut new-hampshire new-york rhode-island vermont", "michigan": "indiana ohio wisconsin",
 "minnesota": "iowa north-dakota south-dakota wisconsin", "mississippi": "alabama arkansas louisiana tennessee",
 "missouri": "arkansas illinois iowa kansas kentucky nebraska oklahoma tennessee", "montana": "idaho north-dakota south-dakota wyoming",
 "nebraska": "colorado iowa kansas missouri south-dakota wyoming", "nevada": "arizona california idaho oregon utah",
 "new-hampshire": "maine massachusetts vermont", "new-jersey": "delaware new-york pennsylvania",
 "new-mexico": "arizona colorado oklahoma texas utah", "new-york": "connecticut massachusetts new-jersey pennsylvania vermont",
 "north-carolina": "georgia south-carolina tennessee virginia", "north-dakota": "minnesota montana south-dakota",
 "ohio": "indiana kentucky michigan pennsylvania west-virginia", "oklahoma": "arkansas colorado kansas missouri new-mexico texas",
 "oregon": "california idaho nevada washington", "pennsylvania": "delaware maryland new-jersey new-york ohio west-virginia",
 "rhode-island": "connecticut massachusetts", "south-carolina": "georgia north-carolina",
 "south-dakota": "iowa minnesota montana nebraska north-dakota wyoming",
 "tennessee": "alabama arkansas georgia kentucky mississippi missouri north-carolina virginia", "texas": "arkansas louisiana new-mexico oklahoma",
 "utah": "arizona colorado idaho nevada new-mexico wyoming", "vermont": "massachusetts new-hampshire new-york",
 "virginia": "district-of-columbia kentucky maryland north-carolina tennessee west-virginia", "washington": "idaho oregon",
 "west-virginia": "kentucky maryland ohio pennsylvania virginia", "wisconsin": "illinois iowa michigan minnesota",
 "wyoming": "colorado idaho montana nebraska south-dakota utah"}
# US Census Bureau regions
STATE_REGION = {}
for _r, _s in {"Northeast": "connecticut maine massachusetts new-hampshire rhode-island vermont new-jersey new-york pennsylvania",
               "Midwest": "illinois indiana michigan ohio wisconsin iowa kansas minnesota missouri nebraska north-dakota south-dakota",
               "South": "delaware district-of-columbia florida georgia maryland north-carolina south-carolina virginia west-virginia alabama kentucky mississippi tennessee arkansas louisiana oklahoma texas",
               "West": "arizona colorado idaho montana nevada new-mexico utah wyoming alaska california hawaii oregon washington"}.items():
    for _x in _s.split(): STATE_REGION[_x] = _r
# Country regions (hand-kept; a new country needs one line here, otherwise it falls back to "Other regions" and still gets the largest-economies links)
COUNTRY_REGION = {}
for _r, _s in {"Europe": "austria belgium france germany ireland italy netherlands poland russia spain sweden switzerland united-kingdom norway denmark finland portugal greece czechia romania hungary slovakia slovenia croatia lithuania bulgaria estonia latvia luxembourg malta cyprus iceland albania bosnia-and-herzegovina north-macedonia moldova kosovo",
               "Asia-Pacific": "australia china india indonesia japan singapore south-korea taiwan new-zealand thailand malaysia philippines vietnam hong-kong bangladesh sri-lanka kazakhstan mongolia armenia georgia kyrgyzstan tajikistan papua-new-guinea solomon-islands tonga",
               "Middle East": "qatar saudi-arabia turkey israel united-arab-emirates",
               "Africa": "egypt ghana kenya nigeria south-africa morocco uganda zambia cote-divoire rwanda mauritius madagascar",
               "the Americas": "brazil canada mexico argentina colombia chile peru dominican-republic costa-rica uruguay el-salvador paraguay guatemala honduras nicaragua barbados suriname saint-lucia"}.items():
    for _x in _s.split(): COUNTRY_REGION[_x] = _r
# Other names people type
ALIASES = {"united-kingdom": "uk u.k. britain great britain england scotland", "south-korea": "korea republic of korea", "south-africa": "rsa",
           "united-arab-emirates": "uae emirates dubai", "czechia": "czech republic czech", "denmark": "danmark", "hungary": "magyarorszag", "finland": "suomi", "portugal": "portuguese", "romania": "romanian", "netherlands": "holland dutch", "russia": "russian federation",
           "taiwan": "chinese taipei roc", "turkey": "turkiye türkiye", "china": "prc", "hong-kong": "hk", "egypt": "arab republic of egypt",
           "new-york": "ny nyc", "district-of-columbia": "dc washington dc"}
POSTAL = {"alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE", "district-of-columbia": "DC", "florida": "FL",
          "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME",
          "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
          "new-hampshire": "NH", "new-jersey": "NJ", "new-mexico": "NM", "new-york": "NY", "north-carolina": "NC", "north-dakota": "ND", "ohio": "OH", "oklahoma": "OK",
          "oregon": "OR", "pennsylvania": "PA", "rhode-island": "RI", "south-carolina": "SC", "south-dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
          "vermont": "VT", "virginia": "VA", "washington": "WA", "west-virginia": "WV", "wisconsin": "WI", "wyoming": "WY"}

def check(places):
    """Build-time sanity: borders are symmetric and every live state is covered. Raises so a typo never ships."""
    for a, ns in NEIGHBORS.items():
        for b in ns.split():
            if a not in NEIGHBORS[b].split(): raise SystemExit(f"explore.NEIGHBORS not symmetric: {a} lists {b}")
    live = {p["slug"] for p in places if p["kind"] == "state"}
    miss = live - set(NEIGHBORS)
    if miss: raise SystemExit(f"explore.NEIGHBORS missing states: {sorted(miss)}")

SEC = {"state": "states", "country": "countries"}

WEALTH = []  # set by wealth_build.prep(): [{name, slug, place_slug, country, short, name_long}]

def _unapos(name, a):
    """The page script turns an apostrophe into a space ("l'imad" -> "l imad"), so "limad" would miss it. Add the apostrophe-free spelling as an alias."""
    s = name.replace("'", "").replace("\u2019", "")
    return f"{a} {s.lower()}".strip() if s != name else a

def search_index(places):
    out = [{"n": "United States", "u": "", "k": "country", "a": "usa us u.s. america national debt federal"},
           {"n": "World", "u": "world/", "k": "world", "a": "world debt global all countries"}]
    for p in sorted(places, key=lambda x: (x["kind"], x["name"])):
        a = ALIASES.get(p["slug"], "")
        if p["kind"] == "country":      # ISO codes: "pt", "dk", "deu" jump to the right country
            a = " ".join(x for x in (p.get("country", "").lower(), (p.get("iso3") or "").lower(), a) if x)
        if p["kind"] == "state": a = (POSTAL.get(p["slug"], "").lower() + " " + a).strip()
        out.append({"n": p["name"], "u": f'{SEC[p["kind"]]}/{p["slug"]}/', "k": p["kind"], "a": _unapos(p["name"], a)})
    if WEALTH:
        out.append({"n": "Sovereign wealth funds", "u": "wealth/", "k": "wealth", "a": "wealth fund funds sovereign swf ranking assets per citizen"})
        for w in WEALTH:
            out.append({"n": w["name"], "u": f'wealth/{w["slug"]}/', "k": "wealth", "a": _unapos(w["name"], f'{w["name_long"]} {w["short"]} {w["country"]} wealth fund sovereign'.lower())})
    return {"_doc": "Client-side search index for the clock pages: n name, u url relative to the site root, k kind, a extra search words.", "places": out}

SEARCH_JS = """<script>(function(){var f=document.getElementById('qf'),q=document.getElementById('q'),ul=document.getElementById('qr'),up=f.dataset.up,ix=null,cur=-1,shown=[];
function load(c){if(ix)return c();fetch(up+'api/search.json').then(function(r){return r.json()}).then(function(j){ix=j.places;c()}).catch(function(){})}
function norm(s){return s.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').replace(/[^a-z0-9 ]+/g,' ').replace(/\\s+/g,' ').trim()}
function score(p,t){var n=norm(p.n),a=norm(p.a||'');if(n===t)return 0;if(n.indexOf(t)===0)return 1;if((' '+n).indexOf(' '+t)>=0)return 2;if((' '+a).indexOf(' '+t)>=0)return 3;if(n.indexOf(t)>=0)return 4;return 9}
function render(){var t=norm(q.value);ul.innerHTML='';shown=[];cur=-1;if(!t){ul.hidden=true;q.setAttribute('aria-expanded','false');return}
shown=ix.map(function(p){return[score(p,t),p]}).filter(function(x){return x[0]<9}).sort(function(a,b){return a[0]-b[0]||a[1].n.localeCompare(b[1].n)}).slice(0,8).map(function(x){return x[1]});
if(!shown.length){ul.innerHTML='<li class="none">No clock for that yet</li>'}else shown.forEach(function(p,i){var li=document.createElement('li'),a=document.createElement('a');a.href=up+p.u;a.setAttribute('role','option');a.id='qr'+i;
a.innerHTML='<span></span><em></em>';a.firstChild.textContent=p.n;a.lastChild.textContent=p.k==='state'?'US state':p.k==='world'?'Best-source world total':p.k==='worldgov'?'IMF world total':p.k==='wealth'?'Wealth fund':'Country';li.appendChild(a);ul.appendChild(li)});
ul.hidden=false;q.setAttribute('aria-expanded','true')}
function mark(d){var as=ul.querySelectorAll('a');if(!as.length)return;cur=(cur+d+as.length)%as.length;as.forEach(function(a,i){a.classList.toggle('on',i===cur)});q.setAttribute('aria-activedescendant',as[cur].id)}
q.addEventListener('focus',function(){load(function(){if(q.value)render()})});q.addEventListener('input',function(){load(render)});
q.addEventListener('keydown',function(e){if(e.key==='ArrowDown'){e.preventDefault();mark(1)}else if(e.key==='ArrowUp'){e.preventDefault();mark(-1)}else if(e.key==='Escape'){ul.hidden=true}});
f.addEventListener('submit',function(e){e.preventDefault();load(function(){render();var a=ul.querySelectorAll('a')[Math.max(cur,0)];if(a)location.href=a.href})});
document.addEventListener('click',function(e){if(!f.contains(e.target))ul.hidden=true})})()</script>"""

def search_box(up):
    """The search form. up = path from this page to the site root ('' , '../', '../../')."""
    return (f'<div class="srchrow"><form class="srch" id="qf" data-up="{up}" role="search" action="{up or "./"}states/" autocomplete="off">'
            f'<label for="q">Find a clock</label><input id="q" type="search" placeholder="Type a country, state or wealth fund, e.g. Texas, Singapore or Norway" aria-expanded="false" aria-controls="qr" aria-autocomplete="list" enterkeyhint="go">'
            f'<button type="submit" aria-label="Go">Go</button><ul id="qr" role="listbox" hidden></ul></form></div>' + SEARCH_JS)




def _used_urls(items):
    return {u for _, u, _ in items}

def _fill(items, skip, n=3):
    """Pad to exactly n links from a short default list, never linking to the current page."""
    for name, url, why in (
        ("US national debt clock", "", "Federal debt, live"),
        ("World debt clock", "world/", "Best source for every economy, in dollars"),
        ("Country debt clocks", "countries/", "National debt by country"),
        ("US state debt clocks", "states/", "Every state and DC"),
        ("US national debt by year", "national-debt-by-year/", "Official totals by fiscal year"),
        ("How much is the national debt?", "how-much-is-the-national-debt/", "The official Treasury total"),
    ):
        if len(items) >= n: break
        if url in skip or url in _used_urls(items): continue
        items.append((name, url, why))
    if len(items) != n:
        raise SystemExit(f"related clocks: could not pick {n} links (got {items!r}, skip={skip!r})")
    return items[:n]

def pick_related(places, calc, cur=None, gdp=None, usd=None, kind_hint=None, topic=None, funds=None, fund=None):
    """Exactly 3 related links (name, site-root-relative url, one-line reason) for a clock page."""
    gdp, usd, funds = gdp or {}, usd or {}, funds or []
    by = {p["slug"]: p for p in places}
    states = [p for p in places if p["kind"] == "state"]
    countries = [p for p in places if p["kind"] == "country"]
    def debt(p): return calc(p)["total"]
    def g(p): return gdp.get(p["slug"], 0) or 0
    items, skip = [], set()

    if cur:
        skip.add(f'{SEC[cur["kind"]]}/{cur["slug"]}/')
    if topic:
        skip.add(f"{topic}/" if not topic.endswith("/") else topic)
    if fund:
        skip.add(f'wealth/{fund["slug"]}/')
    if kind_hint == "us":
        skip.add("")
    elif kind_hint == "world":
        skip.add("world/")
    elif kind_hint == "weo-world":
        skip.add("world/")
    elif kind_hint == "states":
        skip.add("states/")
    elif kind_hint == "countries":
        skip.add("countries/")
    elif kind_hint == "wealth":
        skip.add("wealth/")

    if topic:
        by_topic = {
            "how-much-is-the-national-debt": [
                ("US national debt clock", "", "Live official total"),
                ("National debt per person", "national-debt-per-person/", "The same total, per resident"),
                ("US national debt by year", "national-debt-by-year/", "Official totals by fiscal year"),
            ],
            "national-debt-per-person": [
                ("US national debt clock", "", "Live official total"),
                ("How much is the national debt?", "how-much-is-the-national-debt/", "The official Treasury total"),
                ("US national debt by year", "national-debt-by-year/", "Official totals by fiscal year"),
            ],
            "national-debt-by-year": [
                ("US national debt clock", "", "Live official total"),
                ("How much is the national debt?", "how-much-is-the-national-debt/", "The official Treasury total"),
                ("When will US debt hit $41 trillion?", "when-will-debt-hit-41-trillion/", "A projection from the official trend"),
            ],
            "when-will-debt-hit-41-trillion": [
                ("US national debt clock", "", "Live official total"),
                ("US national debt by year", "national-debt-by-year/", "Official totals by fiscal year"),
                ("How much is the national debt?", "how-much-is-the-national-debt/", "The official Treasury total"),
            ],
            "methodology": [
                ("US national debt clock", "", "Live official total"),
                ("How much is the national debt?", "how-much-is-the-national-debt/", "The official Treasury total"),
                ("US national debt by year", "national-debt-by-year/", "Official totals by fiscal year"),
            ],
        }
        items = list(by_topic.get(topic, []))
        return _fill(items, skip)

    if fund:
        others_same = [x for x in funds if x["country"] == fund["country"] and x["slug"] != fund["slug"]]
        others_all = [x for x in funds if x["slug"] != fund["slug"]]
        # Closest in assets after same-country peers
        def near(xs):
            return sorted(xs, key=lambda x: abs((x.get("usd") or 0) - (fund.get("usd") or 0)))
        picked = []
        for x in others_same + near(others_all):
            if x["slug"] in {p["slug"] for p in picked}: continue
            picked.append(x)
            if len(picked) == 2: break
        for x in picked:
            why = f'Also in {x["country"]}' if x["country"] == fund["country"] else "A similar-size fund"
            items.append((x.get("nick") or x["name"], f'wealth/{x["slug"]}/', why))
        place = fund.get("place_slug")
        if place and place in by:
            p = by[place]
            items.append((f'{p["name"]} debt clock', f'{SEC[p["kind"]]}/{p["slug"]}/', f'{p["name"]} government debt'))
        elif place == "united-states":
            items.append(("US national debt clock", "", "Federal debt, live"))
        return _fill(items, skip)

    if cur and cur["kind"] == "state":
        nb = [by[s] for s in NEIGHBORS.get(cur["slug"], "").split() if s in by]
        # Prefer neighbours closest in total debt; fill with similar-size states if fewer than 2 neighbours (Alaska, Hawaii, Maine).
        nb_sorted = sorted(nb, key=lambda p: abs(debt(p) - debt(cur)))
        similar = sorted((p for p in states if p["slug"] != cur["slug"] and p not in nb), key=lambda p: abs(debt(p) - debt(cur)))
        for p in (nb_sorted + similar)[:2]:
            why = f'Borders {"DC" if cur["slug"]=="district-of-columbia" else cur["name"]}' if p in nb else "Similar total debt"
            items.append((f'{p["name"]} debt clock', f'states/{p["slug"]}/', why))
        items.append(("US national debt clock", "", "Federal debt, live"))
        return _fill(items, skip)

    if cur and cur.get("weo"):
        def region_of(p): return p.get("region") or COUNTRY_REGION.get(p["slug"], "")
        reg = region_of(cur)
        pool = [p for p in countries if p["slug"] != cur["slug"]]
        peers = [p for p in pool if reg and region_of(p) == reg]
        peers = sorted(peers, key=lambda p: abs(g(p) - g(cur)))
        global_peers = sorted(pool, key=lambda p: abs(g(p) - g(cur)))
        seen = set()
        for p in peers + global_peers:
            if p["slug"] in seen: continue
            seen.add(p["slug"])
            why = f"Also in {reg}" if p in peers and reg else "Similar-size economy"
            items.append((f'{p["name"]} debt clock', f'countries/{p["slug"]}/', why))
            if len(items) == 2: break
        items.append(("World debt clock", "world/", "General-government total, with the IMF comparison"))
        return _fill(items, skip)

    if cur and cur["kind"] == "country":
        reg = COUNTRY_REGION.get(cur["slug"], "")
        peers = [p for p in countries if p["slug"] != cur["slug"] and COUNTRY_REGION.get(p["slug"]) == reg] if reg else []
        peers = sorted(peers, key=lambda p: abs(g(p) - g(cur)))
        global_peers = sorted((p for p in countries if p["slug"] != cur["slug"]), key=lambda p: abs(g(p) - g(cur)))
        for p in (peers + global_peers)[:2]:
            why = f"Also in {reg}" if p in peers and reg else "Similar-size economy"
            items.append((f'{p["name"]} debt clock', f'countries/{p["slug"]}/', why))
        items.append(("World debt clock", "world/", "Best source for every economy, in dollars"))
        return _fill(items, skip)

    if kind_hint == "us":
        items = [
            ("World debt clock", "world/", "Best source for every economy, in dollars"),
            ("US national debt by year", "national-debt-by-year/", "Official totals, FY1940 to now"),
            ("Country debt clocks", "countries/", "National debt by country"),
        ]
        return _fill(items, skip)

    if kind_hint == "weo-world":
        items = [
            ("World debt clock", "world/", "Best source for every economy, in dollars"),
            ("US national debt clock", "", "Treasury total, a different measure"),
            ("Country debt clocks", "countries/", "Official clocks and IMF estimate clocks"),
        ]
        return _fill(items, skip)

    if kind_hint == "world":
        ranked = sorted(countries, key=lambda p: -((usd or {}).get(p["slug"], 0) or g(p)))
        items.append(("US national debt clock", "", "Federal debt, live"))
        for p in ranked[:2]:
            items.append((f'{p["name"]} debt clock', f'countries/{p["slug"]}/', "One of the largest in the sum"))
        return _fill(items, skip)

    if kind_hint == "states":
        big = sorted(states, key=lambda p: -debt(p))
        items.append(("US national debt clock", "", "Federal debt, live"))
        for p in big[:2]:
            items.append((f'{p["name"]} debt clock', f'states/{p["slug"]}/', "One of the largest state clocks"))
        return _fill(items, skip)

    if kind_hint == "countries":
        ranked = sorted(countries, key=lambda p: -g(p))
        items = [("World debt clock", "world/", "Best source for every economy, in dollars"), ("US national debt clock", "", "Federal debt, live")]
        if ranked:
            p = ranked[0]
            items.append((f'{p["name"]} debt clock', f'countries/{p["slug"]}/', "Largest economy with a clock"))
        return _fill(items, skip)

    if kind_hint == "wealth":
        items.append(("US national debt clock", "", "Federal debt, live"))
        for x in funds[:2]:
            items.append((x.get("nick") or x["name"], f'wealth/{x["slug"]}/', "Largest funds on this list"))
        return _fill(items, skip)

    return _fill(items, skip)

def related_html(up, items):
    cards = "".join(f'<a href="{up}{u}"><span class="rn">{E(n)}</span><span class="rw">{E(w)}</span></a>' for n, u, w in items)
    return f'<section class="related" id="related"><div class="sh"><h2>Related clocks</h2></div><div class="rg">{cards}</div></section>'

def explore(up, places, calc, cur=None, gdp=None, usd=None, kind_hint=None, topic=None, funds=None, fund=None):
    """'Related clocks' block: exactly 3 relevant, crawlable links. Replaces the older chip groups from PR #9."""
    items = pick_related(places, calc, cur=cur, gdp=gdp, usd=usd, kind_hint=kind_hint, topic=topic, funds=funds, fund=fund)
    return related_html(up, items)

def check_related(places, calc, gdp=None, funds=None):
    """Build-time: every live state and country page gets exactly 3 links, none pointing at itself, none repeated."""
    gdp = gdp or {}
    for p in places:
        items = pick_related(places, calc, cur=p, gdp=gdp)
        urls = [u for _, u, _ in items]
        self = f'{SEC[p["kind"]]}/{p["slug"]}/'
        if len(items) != 3: raise SystemExit(f"related clocks: {p['slug']} has {len(items)}")
        if self in urls: raise SystemExit(f"related clocks: {p['slug']} links to itself")
        if len(set(urls)) != 3: raise SystemExit(f"related clocks: {p['slug']} has a repeated link: {urls}")

CSS = """.srchrow{max-width:1280px;margin:0 auto;padding:10px 14px 0}.srch{position:relative;display:flex;gap:8px;align-items:center;max-width:560px}
.srch label{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
.srch input{flex:1;min-width:0;background:var(--panel2);color:var(--txt);border:1px solid var(--line);border-radius:10px;padding:10px 12px;font:inherit;font-size:14px}
.srch input:focus{outline:2px solid var(--blue);outline-offset:1px}.srch button{background:var(--panel);color:var(--txt);border:1px solid var(--line);border-radius:10px;padding:10px 14px;font:inherit;font-size:14px;cursor:pointer}
.srch ul{position:absolute;top:100%;left:0;right:56px;z-index:30;list-style:none;margin:4px 0 0;padding:4px;background:var(--panel);border:1px solid var(--line);border-radius:10px;box-shadow:0 10px 30px #000a}
.srch ul[hidden]{display:none}.srch li a,.srch li.none{display:flex;justify-content:space-between;gap:12px;padding:9px 10px;border-radius:8px;color:var(--txt);font-size:14px}
.srch li.none{color:var(--mut)}.srch li a em{font-style:normal;color:var(--dim);font-size:12px}.srch li a:hover,.srch li a.on{background:var(--panel2)}
.related{max-width:1280px;margin:0 auto;padding:8px 14px 28px}.related .sh{margin:0 0 10px}.related h2{font-size:17px;margin:0}
.related .rg{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
.related .rg a{display:flex;flex-direction:column;gap:4px;padding:14px 16px;border:1px solid var(--line,#1c2533);border-radius:12px;background:var(--panel,#121925);color:var(--txt,#e8edf5);text-decoration:none}
.related .rg a:hover{border-color:var(--blue,#5aa9ff)}.related .rn{font-size:15px;font-weight:600}.related .rw{font-size:13px;color:var(--mut,#8a97ab)}
@media (max-width:700px){.related .rg{grid-template-columns:1fr}}
@media (max-width:640px){.srch ul{right:0}}"""

RELATED_CSS = CSS[CSS.index(".related"):CSS.index("@media (max-width:640px){.srch")]
