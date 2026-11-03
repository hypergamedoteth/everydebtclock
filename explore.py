"""Search box and 'Explore more clocks' links for every clock page (places, hubs, world, US homepage).
Static and light: the search is client-side over api/search.json (names, aliases, urls; ~10 KB); the explore links are plain
server-rendered anchors (neighbouring states, same region, largest by debt or GDP), so they are crawlable and need no JS.
Called from build.py / places_build.py / world_build.py."""
import json, os, html

E = html.escape

# Land borders between the 50 states (Four Corners points count: AZ-CO, NM-UT). Checked for symmetry at build time (check()).
NEIGHBORS = {
 "alabama": "florida georgia mississippi tennessee", "alaska": "", "arizona": "california colorado nevada new-mexico utah",
 "arkansas": "louisiana missouri mississippi oklahoma tennessee texas", "california": "arizona nevada oregon",
 "colorado": "arizona kansas nebraska new-mexico oklahoma utah wyoming", "connecticut": "massachusetts new-york rhode-island",
 "delaware": "maryland new-jersey pennsylvania", "florida": "alabama georgia", "georgia": "alabama florida north-carolina south-carolina tennessee",
 "hawaii": "", "idaho": "montana nevada oregon utah washington wyoming", "illinois": "indiana iowa kentucky missouri wisconsin",
 "indiana": "illinois kentucky michigan ohio", "iowa": "illinois minnesota missouri nebraska south-dakota wisconsin",
 "kansas": "colorado missouri nebraska oklahoma", "kentucky": "illinois indiana missouri ohio tennessee virginia west-virginia",
 "louisiana": "arkansas mississippi texas", "maine": "new-hampshire", "maryland": "delaware pennsylvania virginia west-virginia",
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
 "virginia": "kentucky maryland north-carolina tennessee west-virginia", "washington": "idaho oregon",
 "west-virginia": "kentucky maryland ohio pennsylvania virginia", "wisconsin": "illinois iowa michigan minnesota",
 "wyoming": "colorado idaho montana nebraska south-dakota utah"}
# US Census Bureau regions
STATE_REGION = {}
for _r, _s in {"Northeast": "connecticut maine massachusetts new-hampshire rhode-island vermont new-jersey new-york pennsylvania",
               "Midwest": "illinois indiana michigan ohio wisconsin iowa kansas minnesota missouri nebraska north-dakota south-dakota",
               "South": "delaware florida georgia maryland north-carolina south-carolina virginia west-virginia alabama kentucky mississippi tennessee arkansas louisiana oklahoma texas",
               "West": "arizona colorado idaho montana nevada new-mexico utah wyoming alaska california hawaii oregon washington"}.items():
    for _x in _s.split(): STATE_REGION[_x] = _r
# Country regions (hand-kept; a new country needs one line here, otherwise it falls back to "Other regions" and still gets the largest-economies links)
COUNTRY_REGION = {}
for _r, _s in {"Europe": "austria belgium france germany ireland italy netherlands poland russia spain sweden switzerland united-kingdom norway denmark finland portugal greece czechia romania hungary",
               "Asia-Pacific": "australia china india indonesia japan singapore south-korea taiwan new-zealand thailand malaysia philippines vietnam hong-kong",
               "Middle East": "qatar saudi-arabia turkey israel united-arab-emirates",
               "Africa": "egypt ghana kenya nigeria south-africa",
               "the Americas": "brazil canada mexico argentina colombia chile peru"}.items():
    for _x in _s.split(): COUNTRY_REGION[_x] = _r
# Other names people type
ALIASES = {"united-kingdom": "uk u.k. britain great britain england scotland", "south-korea": "korea republic of korea", "south-africa": "rsa",
           "united-arab-emirates": "uae emirates dubai", "czechia": "czech republic czech", "denmark": "danmark", "hungary": "magyarorszag", "finland": "suomi", "portugal": "portuguese", "romania": "romanian", "netherlands": "holland dutch", "russia": "russian federation",
           "taiwan": "chinese taipei roc", "turkey": "turkiye türkiye", "china": "prc", "hong-kong": "hk", "egypt": "arab republic of egypt",
           "new-york": "ny nyc", "district-of-columbia": "dc washington dc"}
POSTAL = {"alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL",
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

def search_index(places):
    out = [{"n": "United States", "u": "", "k": "country", "a": "usa us u.s. america national debt federal"},
           {"n": "World", "u": "world/", "k": "world", "a": "world debt global all countries"}]
    for p in sorted(places, key=lambda x: (x["kind"], x["name"])):
        a = ALIASES.get(p["slug"], "")
        if p["kind"] == "country":      # ISO codes: "pt", "dk", "deu" jump to the right country
            a = " ".join(x for x in (p.get("country", "").lower(), (p.get("iso3") or "").lower(), a) if x)
        if p["kind"] == "state": a = (POSTAL.get(p["slug"], "").lower() + " " + a).strip()
        out.append({"n": p["name"], "u": f'{SEC[p["kind"]]}/{p["slug"]}/', "k": p["kind"], "a": a})
    if WEALTH:
        out.append({"n": "Sovereign wealth funds", "u": "wealth/", "k": "wealth", "a": "wealth fund funds sovereign swf ranking assets per citizen"})
        for w in WEALTH:
            out.append({"n": w["name"], "u": f'wealth/{w["slug"]}/', "k": "wealth", "a": f'{w["name_long"]} {w["short"]} {w["country"]} wealth fund sovereign'.lower()})
    return {"_doc": "Client-side search index for the clock pages: n name, u url relative to the site root, k kind, a extra search words.", "places": out}

SEARCH_JS = """<script>(function(){var f=document.getElementById('qf'),q=document.getElementById('q'),ul=document.getElementById('qr'),up=f.dataset.up,ix=null,cur=-1,shown=[];
function load(c){if(ix)return c();fetch(up+'api/search.json').then(function(r){return r.json()}).then(function(j){ix=j.places;c()}).catch(function(){})}
function norm(s){return s.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').replace(/[^a-z0-9 ]+/g,' ').replace(/\\s+/g,' ').trim()}
function score(p,t){var n=norm(p.n),a=norm(p.a||'');if(n===t)return 0;if(n.indexOf(t)===0)return 1;if((' '+n).indexOf(' '+t)>=0)return 2;if((' '+a).indexOf(' '+t)>=0)return 3;if(n.indexOf(t)>=0)return 4;return 9}
function render(){var t=norm(q.value);ul.innerHTML='';shown=[];cur=-1;if(!t){ul.hidden=true;q.setAttribute('aria-expanded','false');return}
shown=ix.map(function(p){return[score(p,t),p]}).filter(function(x){return x[0]<9}).sort(function(a,b){return a[0]-b[0]||a[1].n.localeCompare(b[1].n)}).slice(0,8).map(function(x){return x[1]});
if(!shown.length){ul.innerHTML='<li class="none">No clock for that yet</li>'}else shown.forEach(function(p,i){var li=document.createElement('li'),a=document.createElement('a');a.href=up+p.u;a.setAttribute('role','option');a.id='qr'+i;
a.innerHTML='<span></span><em></em>';a.firstChild.textContent=p.n;a.lastChild.textContent=p.k==='state'?'US state':p.k==='world'?'All countries':p.k==='wealth'?'Wealth fund':'Country';li.appendChild(a);ul.appendChild(li)});
ul.hidden=false;q.setAttribute('aria-expanded','true')}
function mark(d){var as=ul.querySelectorAll('a');if(!as.length)return;cur=(cur+d+as.length)%as.length;as.forEach(function(a,i){a.classList.toggle('on',i===cur)});q.setAttribute('aria-activedescendant',as[cur].id)}
q.addEventListener('focus',function(){load(function(){if(q.value)render()})});q.addEventListener('input',function(){load(render)});
q.addEventListener('keydown',function(e){if(e.key==='ArrowDown'){e.preventDefault();mark(1)}else if(e.key==='ArrowUp'){e.preventDefault();mark(-1)}else if(e.key==='Escape'){ul.hidden=true}});
f.addEventListener('submit',function(e){e.preventDefault();load(function(){render();var a=ul.querySelectorAll('a')[Math.max(cur,0)];if(a)location.href=a.href})});
document.addEventListener('click',function(e){if(!f.contains(e.target))ul.hidden=true})})()</script>"""

def search_box(up):
    """The search form. up = path from this page to the site root ('' , '../', '../../')."""
    return (f'<div class="srchrow"><form class="srch" id="qf" data-up="{up}" role="search" action="{up or "./"}states/" autocomplete="off">'
            f'<label for="q">Find a clock</label><input id="q" type="search" placeholder="Type a country or state, e.g. Texas or Singapore" aria-expanded="false" aria-controls="qr" aria-autocomplete="list" enterkeyhint="go">'
            f'<button type="submit" aria-label="Go">Go</button><ul id="qr" role="listbox" hidden></ul></form></div>' + SEARCH_JS)

def _chips(items, up):
    return "".join(f'<a href="{up}{u}">{E(n)}</a>' for n, u in items)

def _group(title, items, up):
    items = [x for x in items if x]
    return f'<div class="xg"><h3>{E(title)}</h3><div class="xc">{_chips(items, up)}</div></div>' if items else ""

def explore(up, places, calc, cur=None, gdp=None, usd=None, kind_hint=None):
    """'Explore more clocks' section. cur = the page's own place dict (or None for US/world/hub pages). gdp = {slug: GDP bn} from data/world_gdp.json
    (ranks countries by economy size); usd = {slug: USD debt} for ranking countries by debt on the world page."""
    gdp = gdp or {}
    by = {p["slug"]: p for p in places}
    link = lambda p: (p["name"], f'{SEC[p["kind"]]}/{p["slug"]}/')
    states = [p for p in places if p["kind"] == "state"]
    countries = [p for p in places if p["kind"] == "country"]
    big_states = sorted(states, key=lambda p: -calc(p)["total"])
    def g(p): return gdp.get(p["slug"], 0) or 0
    big_c = sorted(countries, key=lambda p: -(usd or {}).get(p["slug"], 0) if usd else -g(p))
    groups, used = [], set()
    def take(ps, n):
        out = []
        for p in ps:
            if len(out) >= n: break
            if cur and p["slug"] == cur["slug"] or p["slug"] in used: continue
            used.add(p["slug"]); out.append(link(p))
        return out
    if cur and cur["kind"] == "state":
        nb = [by[s] for s in NEIGHBORS.get(cur["slug"], "").split() if s in by]
        reg = STATE_REGION.get(cur["slug"], "")
        groups.append(_group(f'Neighbouring states of {cur["name"]}', take(sorted(nb, key=lambda p: p["name"]), 10), up))
        peers = [p for p in states if STATE_REGION.get(p["slug"]) == reg]
        groups.append(_group(f"More {reg} states", take(sorted(peers, key=lambda p: -calc(p)["total"]), 6), up))
        groups.append(_group("Largest state debt clocks", take(big_states, 6), up))
        groups.append(_group("Largest economies", take(big_c, 6), up))
    elif cur and cur["kind"] == "country":
        reg = COUNTRY_REGION.get(cur["slug"], "")
        peers = [p for p in countries if COUNTRY_REGION.get(p["slug"]) == reg] if reg else []
        groups.append(_group(f"More in {reg}" if reg else "More countries", take(sorted(peers, key=lambda p: -g(p)), 8), up))
        groups.append(_group("Largest economies", take(big_c, 8), up))
        groups.append(_group("US state debt clocks", take(big_states, 5), up))
        groups.insert(0, _group(f'Sovereign wealth funds of {cur["name"]}', [(w["name"], f'wealth/{w["slug"]}/') for w in WEALTH if w["place_slug"] == cur["slug"]], up))
    else:
        groups.append(_group("Largest countries" if usd else "Largest economies", take(big_c, 10), up))
        groups.append(_group("Largest US states", take(big_states, 10), up))
    base = [("US national debt clock", ""), ("World debt clock", "world/"), ("All country debt clocks", "countries/"), ("All US state debt clocks", "states/")]
    skip = {"us": "", "world": "world/"}.get(kind_hint)
    if WEALTH: base.append(("Sovereign wealth funds ranked", "wealth/"))
    groups.append(_group("Browse", [b for b in base if b[1] != skip], up))
    return ('<section class="explore" id="explore"><div class="sh"><h2>Explore more clocks</h2></div>' + "".join(groups) + '</section>')

CSS = """.srchrow{max-width:1280px;margin:0 auto;padding:10px 14px 0}.srch{position:relative;display:flex;gap:8px;align-items:center;max-width:560px}
.srch label{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
.srch input{flex:1;min-width:0;background:var(--panel2);color:var(--txt);border:1px solid var(--line);border-radius:10px;padding:10px 12px;font:inherit;font-size:14px}
.srch input:focus{outline:2px solid var(--blue);outline-offset:1px}.srch button{background:var(--panel);color:var(--txt);border:1px solid var(--line);border-radius:10px;padding:10px 14px;font:inherit;font-size:14px;cursor:pointer}
.srch ul{position:absolute;top:100%;left:0;right:56px;z-index:30;list-style:none;margin:4px 0 0;padding:4px;background:var(--panel);border:1px solid var(--line);border-radius:10px;box-shadow:0 10px 30px #000a}
.srch ul[hidden]{display:none}.srch li a,.srch li.none{display:flex;justify-content:space-between;gap:12px;padding:9px 10px;border-radius:8px;color:var(--txt);font-size:14px}
.srch li.none{color:var(--mut)}.srch li a em{font-style:normal;color:var(--dim);font-size:12px}.srch li a:hover,.srch li a.on{background:var(--panel2)}
.explore{max-width:1280px;margin:0 auto;padding:0 14px 26px}.explore .xg{margin:0 0 14px}.explore h3{font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.05em;margin:0 0 7px;font-weight:600}
.explore .xc{display:flex;flex-wrap:wrap;gap:7px}.explore .xc a{border:1px solid var(--line);border-radius:999px;padding:6px 12px;font-size:13px;color:var(--txt);background:var(--panel)}.explore .xc a:hover{border-color:var(--blue);color:var(--blue)}
@media (max-width:640px){.srch ul{right:0}}"""
