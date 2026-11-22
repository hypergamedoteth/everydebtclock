#!/usr/bin/env python3
"""Shared footer links, legal pages, and the cookie/ads notice.

The notice is a slim bar fixed to the bottom of the viewport so it cannot
cover the lead ticker at the top of a clock page. Embed clock widgets and
widget.html are left alone: they set no site cookies and load no analytics.
"""
from __future__ import annotations

import html as htmlmod
import os
import re

NOTICE_MARK_START = "<!--NOTICE-->"
NOTICE_MARK_END = "<!--/NOTICE-->"

# Ordered footer links after any page-specific lead-in. Advertise is optional
# so the sponsor pull request can add it without rewriting this list by hand.
FOOTER_LINKS = (
    ("embed/", "Embed a clock"),
    ("facts/", "Facts"),
    ("data/", "Data"),
    ("reports/", "Reports"),
    ("press/", "Press"),
    ("about/", "About"),
    ("advertise/", "Advertise"),
    ("methodology/", "Methodology"),
    ("privacy/", "Privacy"),
    ("contact/", "Contact"),
)

_FOOTER_RE = re.compile(r"<footer\b[^>]*>.*?</footer>", re.S | re.I)
_PRIVACY_HREF_RE = re.compile(
    r'(href="(?:(?:\.\./)+|/|))privacy\.html"',
    re.I,
)
_PREFIX_RE = re.compile(
    r'href="((?:\.\./)*)(?:embed/|data/|press/|about/|methodology/|privacy(?:\.html|/)|contact/|advertise/)"'
)
_ABS_PREFIX_RE = re.compile(
    r'href="/(?:embed/|data/|press/|about/|methodology/|privacy(?:\.html|/)|contact/|advertise/)"'
)


def _prefix_from(chunk: str) -> tuple[str, bool]:
    """Return (prefix, is_absolute). Absolute links use a leading slash."""
    if _ABS_PREFIX_RE.search(chunk):
        return "/", True
    m = _PREFIX_RE.search(chunk)
    if m:
        return m.group(1), False
    return "", False


def footer_anchor(prefix: str, slug: str, label: str, absolute: bool = False) -> str:
    if absolute or prefix == "/":
        href = f"/{slug}"
    else:
        href = f"{prefix}{slug}"
    return f'<a href="{href}">{htmlmod.escape(label)}</a>'


def link_list(prefix: str, absolute: bool = False, extra: tuple[tuple[str, str], ...] = ()) -> str:
    items = list(FOOTER_LINKS)
    # Keep Advertise after About when the caller asks for it.
    if extra:
        about_at = next((i for i, (s, _) in enumerate(items) if s == "about/"), len(items))
        for slug, label in extra:
            if any(s == slug for s, _ in items):
                continue
            items.insert(about_at + 1, (slug, label))
            about_at += 1
    return " · ".join(footer_anchor(prefix, slug, label, absolute) for slug, label in items)


def site_footer(
    prefix: str,
    lead: str = "Every Debt Clock",
    note: str = "Independent site, not affiliated with the U.S. government. Not financial advice.",
    cls: str = "site-foot",
    absolute: bool = False,
    extra: tuple[tuple[str, str], ...] = (),
) -> str:
    attr = f' class="{cls}"' if cls else ""
    parts = [lead, link_list(prefix, absolute, extra)]
    if note:
        parts.append(note)
    body = " · ".join(p for p in parts if p)
    return f"<footer{attr}>{body}</footer>"


def upgrade_footer(foot: str, extra: tuple[tuple[str, str], ...] = ()) -> str:
    """Keep the page's lead-in and disclaimer; refresh the standard legal links."""
    prefix, absolute = _prefix_from(foot)
    new_links = link_list(prefix, absolute, extra)
    # Replace the existing standard-link run (from the first known link to the
    # last), leaving the sentence before it and the disclaimer after it.
    known = (
        r"(?:(?:\.\./)+|/)?(?:embed/|data/|press/|about/|advertise/|methodology/|"
        r"privacy(?:\.html|/)|contact/|reports/|Home)"
    )
    run = re.search(
        rf'<a href="{known}"[^>]*>.*?(?:</a>(?:\s*·\s*<a href="{known}"[^>]*>.*?</a>)+)',
        foot,
        re.S | re.I,
    )
    if run:
        return foot[: run.start()] + new_links + foot[run.end() :]
    # No recognizable run: append the links before </footer>.
    foot = _PRIVACY_HREF_RE.sub(r'\1privacy/"', foot)
    if re.search(r"href=\"[^\"]*about/\"", foot) and re.search(r"href=\"[^\"]*contact/\"", foot):
        return foot
    return re.sub(r"</footer>", f" · {new_links}</footer>", foot, count=1, flags=re.I)


NOTICE_INNER = """\
<aside id="edc-notice" hidden role="region" aria-label="Cookies and ads">
<p>This site uses privacy-focused analytics. If ads are shown, Google and its partners may use cookies. <a href="/privacy/">Privacy</a></p>
<button type="button" id="edc-notice-ok">OK</button>
</aside>
<style>
#edc-notice{position:fixed;left:0;right:0;bottom:0;top:auto;z-index:40;display:flex;gap:8px;align-items:center;justify-content:space-between;flex-wrap:nowrap;box-sizing:border-box;margin:0;padding:6px 10px;background:#121925;color:#c2ccda;border-top:1px solid #1c2533;font:12px/1.3 -apple-system,BlinkMacSystemFont,Inter,Segoe UI,Roboto,sans-serif}
#edc-notice[hidden]{display:none!important}
#edc-notice p{margin:0;flex:1 1 auto;min-width:0}
#edc-notice a{color:#5aa9ff;text-decoration:none}
#edc-notice-ok{appearance:none;flex:none;border:1px solid #1c2533;background:#0e131b;color:#e8edf5;border-radius:8px;padding:4px 10px;font:inherit;font-weight:650;cursor:pointer}
</style>
<script>
(function(){
  var n=document.getElementById("edc-notice");
  if(!n)return;
  function pad(){if(document.body)document.body.style.paddingBottom=n.hidden?"":(n.offsetHeight+"px");}
  function close(){n.hidden=true;pad();document.dispatchEvent(new Event("edc-notice-closed"));}
  try{if(localStorage.getItem("edc.notice")==="1")return;}catch(e){}
  n.hidden=false;pad();
  var b=document.getElementById("edc-notice-ok");
  if(b)b.addEventListener("click",function(){
    try{localStorage.setItem("edc.notice","1")}catch(e){}
    close();
  });
})();
</script>
"""

NOTICE_BLOCK = NOTICE_MARK_START + NOTICE_INNER + NOTICE_MARK_END

A2HS_MARK_START = "<!--A2HS-->"
A2HS_MARK_END = "<!--/A2HS-->"
A2HS_INNER = """\
<aside id="edc-a2hs" hidden>
<p id="edc-a2hs-text">Add this live clock to your home screen.</p>
<button type="button" id="edc-a2hs-go" hidden>Add to home screen</button>
<button type="button" id="edc-a2hs-x">Not now</button>
</aside>
<style>
#edc-a2hs{display:flex;gap:8px;align-items:center;flex-wrap:nowrap;margin:6px 0 0;padding:6px 8px;background:#101828;color:#c2ccda;border:1px solid #1c2533;border-radius:8px;font:12px/1.3 -apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif}
#edc-a2hs[hidden]{display:none!important}
#edc-a2hs p{margin:0;flex:1 1 auto;min-width:0}
#edc-a2hs button{appearance:none;flex:none;white-space:nowrap;border:1px solid #1c2533;background:#0e131b;color:#e8edf5;border-radius:8px;padding:4px 8px;font:inherit;cursor:pointer}
#edc-a2hs-go{color:#9fd0ff}
</style>
<script>
(function(){
  if(!("serviceWorker" in navigator)){}
  else if(location.protocol==="https:"||location.hostname==="localhost"){
    navigator.serviceWorker.register("/sw.js").catch(function(){});
  }
  var n=document.getElementById("edc-a2hs"),go=document.getElementById("edc-a2hs-go"),x=document.getElementById("edc-a2hs-x"),text=document.getElementById("edc-a2hs-text");
  if(!n)return;
  var key="edc.a2hs";
  try{if(localStorage.getItem(key))return;}catch(e){return;}
  if(window.matchMedia&&window.matchMedia("(display-mode: standalone)").matches||navigator.standalone){
    try{localStorage.setItem(key,"1");}catch(e){}
    return;
  }
  var deferred=null,shown=false,waiting=false;
  function noticePending(){
    try{if(localStorage.getItem("edc.notice")==="1")return false;}catch(e){}
    var notice=document.getElementById("edc-notice");
    return !!(notice&&!notice.hidden);
  }
  window.addEventListener("beforeinstallprompt",function(e){e.preventDefault();deferred=e;if(!shown&&!noticePending()&&!waiting)show(true);});
  function show(install){
    if(shown||noticePending())return;shown=true;
    try{localStorage.setItem(key,"1");}catch(e){}
    if(install&&deferred){text.textContent="Add this live clock to your home screen.";go.hidden=false;}
    else if(/iphone|ipad|ipod/i.test(navigator.userAgent)||(navigator.platform==="MacIntel"&&navigator.maxTouchPoints>1)){
      text.textContent="Bookmark this clock: tap Share, then Add to Home Screen.";go.hidden=true;
    }else{text.textContent="Bookmark this clock to keep the live numbers one tap away.";go.hidden=true;}
    n.hidden=false;
  }
  if(go)go.addEventListener("click",function(){if(!deferred)return;deferred.prompt();deferred=null;n.hidden=true;});
  if(x)x.addEventListener("click",function(){try{localStorage.setItem(key,"1");}catch(e){}n.hidden=true;});
  function arm(){
    if(shown)return;
    if(noticePending()){
      if(waiting)return;waiting=true;
      document.addEventListener("edc-notice-closed",function(){waiting=false;show(!!deferred);},{once:true});
      return;
    }
    show(!!deferred);
  }
  setTimeout(arm,1500);
})();
</script>
"""
A2HS_BLOCK = A2HS_MARK_START + A2HS_INNER + A2HS_MARK_END


def with_a2hs(page: str) -> str:
    """Place the install prompt after the H1 so it is not the text a crawler quotes."""
    if A2HS_MARK_START in page:
        page = re.sub(
            re.escape(A2HS_MARK_START) + r".*?" + re.escape(A2HS_MARK_END),
            "",
            page,
            count=1,
            flags=re.S,
        )
    h1 = re.search(r"</h1>", page, re.I)
    if h1:
        at = h1.end()
        return page[:at] + A2HS_BLOCK + page[at:]
    header = re.search(r"</header>", page, re.I)
    if header:
        at = header.end()
        return page[:at] + "\n" + A2HS_BLOCK + page[at:]
    return re.sub(r"<body[^>]*>", lambda m: m.group(0) + A2HS_BLOCK, page, count=1, flags=re.I)


def _redirect(page: str) -> bool:
    head = page[:1800]
    return 'http-equiv="refresh"' in head or "location.replace" in head


def with_notice(page: str) -> str:
    if NOTICE_MARK_START in page:
        return re.sub(
            re.escape(NOTICE_MARK_START) + r".*?" + re.escape(NOTICE_MARK_END),
            lambda _m: NOTICE_BLOCK,
            page,
            count=1,
            flags=re.S,
        )
    if re.search(r"</body>", page, re.I):
        return re.sub(r"</body>", NOTICE_BLOCK + "\n</body>", page, count=1, flags=re.I)
    return page + NOTICE_BLOCK


def skip_notice(path: str) -> bool:
    rel = path.replace("\\", "/")
    if rel.endswith("/widget.html") or rel.endswith("widget.html"):
        return True
    if rel.endswith("analytics.html") or rel == "analytics.html":
        return True
    if "/embed/" in "/" + rel or rel.startswith("embed/"):
        # The /embed/ directory page is a normal site page; clock widgets are not.
        if rel.endswith("embed/index.html") or rel.endswith("/embed/index.html"):
            return False
        return True
    return False


LEGAL_CSS = """\
body{margin:0;background:#07090d;color:#e8edf5;font-family:-apple-system,BlinkMacSystemFont,Inter,Segoe UI,Roboto,sans-serif;line-height:1.5}
main{max-width:760px;margin:0 auto;padding:22px 16px 60px}a{color:#5aa9ff;text-decoration:none}
.brand{font-weight:800;letter-spacing:.06em;font-size:14px;color:#e8edf5}.brand b{color:#ff4d5e}
h1{font-size:22px;margin:18px 0 4px}h2{font-size:16px;margin:26px 0 6px}
p,li{color:#c2ccda;font-size:14.5px}ul{padding-left:20px}
.eff{color:#8a97ab;font-size:13px;margin-top:0}
footer{color:#5c687a;font-size:12px;margin-top:30px}
"""

ICON_LINKS = (
    '<link rel="icon" href="/favicon.ico" sizes="16x16 32x32 48x48">'
    '<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png">'
    '<link rel="icon" type="image/svg+xml" href="/icon.svg">'
)


def _meta_email(tag: str, text: str) -> str:
    """Cloudflare Email Obfuscation rewrites an address inside a meta tag too. The comments sit outside the tag so the content string stays the address."""
    if "@" not in text:
        return tag
    return f"<!--email_off-->{tag}<!--/email_off-->"


def _legal_shell(site: str, slug: str, title: str, desc: str, body: str, robots: str = "") -> str:
    url = f"{site}/{slug}/"
    robots_tag = f'<meta name="robots" content="{robots}">' if robots else ""
    foot = site_footer("../", absolute=False)
    desc_tag = _meta_email(f'<meta name="description" content="{htmlmod.escape(desc)}">', desc)
    og_desc = _meta_email(f'<meta property="og:description" content="{htmlmod.escape(desc)}">', desc)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{htmlmod.escape(title)}</title>
{desc_tag}
<link rel="canonical" href="{url}">{robots_tag}
<meta property="og:type" content="website"><meta property="og:site_name" content="Every Debt Clock">
<meta property="og:url" content="{url}"><meta property="og:title" content="{htmlmod.escape(title)}">
{og_desc}
<meta name="theme-color" content="#07090d"><link rel="apple-touch-icon" href="/apple-touch-icon.png">
<style>{LEGAL_CSS}</style>
<!--ANALYTICS--><!--/ANALYTICS-->
{ICON_LINKS}</head>
<body><main>
<a class="brand" href="/">EVERY <b>DEBT</b> CLOCK</a>
{body}
{foot}
</main></body></html>
"""


def privacy_body() -> str:
    return """
<h1>Privacy Policy</h1>
<p class="eff">Effective October 26, 2026. Updated November 18, 2026.</p>

<p>This website, <a href="https://everydebtclock.com/">everydebtclock.com</a>, is operated by Hypergame LLC, a Texas limited liability company ("we", "us"). This page explains what happens to information about you when you visit. There are no accounts and no sign-ups, and we don't ask for your name or email to use the site.</p>

<h2>What we collect</h2>
<p>The site has a search box ("Find a clock") on the home page and the /states/ and /countries/ pages, and a place picker on the home page. What you type in the search box stays in your browser: it filters a list of places (a static file, <code>/api/search.json</code>) that your browser downloads, and the text is not sent to us or anyone else. We don't collect your name, email or anything else you type. The only information we or our services receive is the technical information your browser sends whenever it loads a page, handled by the services below.</p>

<h2>Analytics: GoatCounter</h2>
<p>The site's pages include a script from <a href="https://www.goatcounter.com/" rel="noopener">GoatCounter</a>, a privacy-focused analytics service. It does not use cookies and does not track you across other websites. It records the page you viewed, the site that referred you, your browser and operating system type, screen size, your browser's language setting, and an approximate country. Your IP address is used only to work out the country and to avoid counting the same visit twice; GoatCounter does not store it. We see only totals, such as how many people viewed a page today. See <a href="https://www.goatcounter.com/help/privacy" rel="noopener">GoatCounter's privacy policy</a>.</p>

<h2>Hosting and security: GitHub Pages and Cloudflare</h2>
<p>The site's files are hosted on <a href="https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement" rel="noopener">GitHub Pages</a> and delivered through <a href="https://www.cloudflare.com/privacypolicy/" rel="noopener">Cloudflare</a>, which provides the HTTPS connection and protects the site from attacks. Like any web server, they process your IP address and browser details to deliver pages, and may keep these in logs for security and troubleshooting. If Cloudflare needs to check for automated traffic, it may set a strictly necessary security cookie (such as <code>__cf_bm</code> or <code>cf_clearance</code>); these are not used for advertising.</p>

<h2>Analytics: Cloudflare Web Analytics</h2>
<p>Because the site is delivered through Cloudflare, Cloudflare Web Analytics may also be on. It can be enabled at Cloudflare's network without a script in our pages. It is privacy-focused, does not use cookies and does not track you across other websites. It counts page views, referrers, browser and device type, an approximate country, and page-load performance. We see only totals. See <a href="https://www.cloudflare.com/privacypolicy/" rel="noopener">Cloudflare's privacy policy</a>.</p>

<h2>Cookies and local storage</h2>
<p>The site does not set its own first-party cookies today. It uses your browser's local storage in three places, all only on your device:</p>
<ul>
<li>When you pick a place in the home page's place picker, the site saves that choice (a place name such as "texas", under the key <code>edc.place</code>) so the same place can show next time.</li>
<li>When you dismiss the cookie and ads notice, the site saves that choice under the key <code>edc.notice</code> so the notice stays hidden.</li>
<li>When the add-to-home-screen prompt is shown, the site saves that under the key <code>edc.a2hs</code> so the prompt is not shown again. Nothing about that choice is sent to us.</li>
</ul>
<p>If the page registers its service worker, the browser keeps a copy of the stylesheet, scripts, and icons so a home-screen icon can open. Debt figures are requested again each visit and are not stored in that cache. The service worker does not set a cookie and does not record your visit.</p>
<p>You can remove both by clearing this site's data in your browser. The live counters are calculated in your browser from data files on our own site. The site does not look up your location: the featured place is a fixed default until you choose another.</p>

<h2>Advertising (if and when ads are shown)</h2>
<p>We may show ads, for example through Google AdSense. If and when ads are shown, these rules apply:</p>
<ul>
<li>Third-party vendors, including Google, use cookies to serve ads based on your prior visits to this website or other websites.</li>
<li>Google's use of advertising cookies enables it and its partners to serve ads to you based on your visits to this site and/or other sites on the Internet.</li>
<li>You can opt out of personalized advertising by visiting <a href="https://adssettings.google.com/" rel="noopener">Google Ads Settings</a>. You can also opt out of some third-party vendors' use of cookies for personalized advertising at <a href="https://youradchoices.com/" rel="noopener">youradchoices.com</a>.</li>
</ul>
<p>A short notice about cookies and ads appears at the bottom of site pages (not on the live ticker, and not on the embeddable clock widgets). We will keep this policy current if ads go live or if the vendors change.</p>

<h2>Data downloads</h2>
<p>The site publishes free <a href="/data/">CSV files and charts</a> of official public figures (and projections labelled as such): US debt by year, by president, per person, interest, state debt, and country debt. These files do not include information about visitors. Anyone may download them. They are public data, not personal data.</p>

<h2>Links and sharing</h2>
<p>The site links to official sources (such as the US Treasury, Census Bureau, IRS, Federal Reserve, BEA and the IMF) and offers a "share on X" link. Those sites have their own privacy policies; nothing is sent to them unless you click through. Other websites may embed our counter widget; when they do, your browser loads it from our site under this same policy. The embeddable clock widgets themselves set no cookies and load no analytics.</p>

<h2>Children</h2>
<p>The site is a general-audience information site. It is not directed at children under 13, and we don't knowingly collect personal information from anyone.</p>

<h2>Changes</h2>
<p>If this policy changes, we'll update this page and the date above.</p>

<h2>Contact</h2>
<p>Questions about this policy: <!--email_off--><a href="mailto:hello@everydebtclock.com">hello@everydebtclock.com</a><!--/email_off-->. If you email us, we use your message and address only to reply. More ways to reach us are on the <a href="/contact/">contact page</a>.</p>
"""


def about_body() -> str:
    return """
<h1>About Every Debt Clock</h1>
<p class="eff">Run by Hypergame LLC, a Texas limited liability company.</p>

<p>Every Debt Clock is an independent site with live clocks for US federal debt, US state and local debt, and government debt in other countries. The US clock starts from Treasury's official close and ticks forward at the recent official pace. Official figures are labelled as official; anything projected is labelled as a projection.</p>

<h2>Where the numbers come from</h2>
<ul>
<li><b>US federal debt.</b> Treasury's <a href="https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/debt-to-the-penny" rel="noopener">Debt to the Penny</a>. The live ticker starts from the latest official close and projects forward at the 90-day trend. It is re-based every business day and does not project past the statutory debt limit.</li>
<li><b>Interest, spending, revenue and the deficit.</b> Treasury's Monthly Treasury Statement and Daily Treasury Statement, as labelled on each page.</li>
<li><b>Population.</b> US Census Bureau estimates.</li>
<li><b>Other countries.</b> Official national sources where we have them; otherwise IMF World Economic Outlook general government gross debt. Each country page names its source.</li>
<li><b>US states and Washington, DC.</b> Official Census figures for state and local debt. Each state page names its source.</li>
</ul>
<p>The full method, including how the ticker is checked against the next Treasury close, is on the <a href="/methodology/">methodology</a> page. Downloadable copies of the series are on the <a href="/data/">data</a> page.</p>

<h2>How often it updates</h2>
<p>US federal figures are rebuilt after Treasury publishes a new Debt to the Penny close, on business days. State, country and IMF pages are updated when those sources publish.</p>

<h2>Independence</h2>
<p>We are not affiliated with the US government or any other government. Nothing on this site is financial, investment or legal advice.</p>

<p>Questions, corrections, the free embed, or advertising: <!--email_off--><a href="mailto:hello@everydebtclock.com">hello@everydebtclock.com</a><!--/email_off-->.</p>
"""


def contact_body() -> str:
    return """
<h1>Contact</h1>
<p>Email <!--email_off--><a href="mailto:hello@everydebtclock.com">hello@everydebtclock.com</a><!--/email_off-->.</p>
<p>Use this address for questions about the figures, corrections, the free <a href="/embed/">embed</a>, or advertising. We use your message and address only to reply.</p>
<p>If you are writing about a number on the site, include the page URL and the figure you want checked.</p>
<p>The site is operated by Hypergame LLC, a Texas limited liability company. How we handle visitor information is in the <a href="/privacy/">privacy policy</a>. How the numbers are built is on the <a href="/methodology/">methodology</a> page.</p>
"""


def privacy_redirect() -> str:
    return """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Privacy | Every Debt Clock</title>
<meta name="robots" content="noindex"><link rel="canonical" href="https://everydebtclock.com/privacy/">
<meta http-equiv="refresh" content="0; url=/privacy/"><meta name="theme-color" content="#07090d">
<link rel="icon" href="/favicon.ico" sizes="16x16 32x32 48x48"><link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png"><link rel="icon" type="image/svg+xml" href="/icon.svg">
<script>location.replace("/privacy/"+location.search+location.hash)</script>
<style>body{background:#07090d;color:#b8c3d4;font:16px system-ui,sans-serif;padding:40px}a{color:#5aa9ff}</style></head>
<body><p>Moved to <a href="/privacy/">the privacy page</a>.</p></body></html>
"""




def sponsor_slot(prefix: str, absolute: bool = False) -> str:
    """No placeholder sponsor line. A real sponsor would be added here on purpose."""
    return ""


def advertise_body() -> str:
    return """
<h1>Advertise</h1>
<p>Every Debt Clock is an independent site that publishes a live US national debt clock, checked daily against Treasury, plus state, country and history pages.</p>
<p>Email <!--email_off--><a href="mailto:hello@everydebtclock.com">hello@everydebtclock.com</a><!--/email_off--> to ask about a sponsorship. There is no empty sponsor slot on the pages.</p>
<h2>Audience</h2>
<p>About 1,380 visits in the 30 days ending November 16, 2026, mostly from the United States. The figures are from Cloudflare Web Analytics, which excludes bots. This is a small site. We will update these numbers as traffic changes.</p>
<p>We do not publish prices here. If you want to sponsor the clock, email <!--email_off--><a href="mailto:hello@everydebtclock.com">hello@everydebtclock.com</a><!--/email_off-->.</p>
"""


def write_advertise_page(R: str, site: str, with_analytics=None) -> None:
    wrap = with_analytics or (lambda p: p)
    title = "Advertise | Every Debt Clock"
    desc = "Sponsor Every Debt Clock. About 1,380 visits in the 30 days ending November 16, 2026, mostly from the United States. Email hello@everydebtclock.com."
    os.makedirs(os.path.join(R, "advertise"), exist_ok=True)
    page = wrap(_legal_shell(site, "advertise", title, desc, advertise_body()))
    open(os.path.join(R, "advertise", "index.html"), "w").write(page)


def write_legal_pages(R: str, site: str, with_analytics=None) -> None:
    pages = {
        "privacy": (
            "Privacy Policy | Every Debt Clock",
            "How Every Debt Clock handles visitor data: Cloudflare and GoatCounter analytics, GitHub Pages hosting, data downloads, and cookies if ads are shown.",
            privacy_body(),
        ),
        "about": (
            "About Every Debt Clock",
            "Every Debt Clock is an independent site run by Hypergame LLC. US figures come from Treasury's Debt to the Penny; countries use official sources or the IMF; states use Census figures.",
            about_body(),
        ),
        "contact": (
            "Contact | Every Debt Clock",
            "Contact Every Debt Clock at hello@everydebtclock.com for questions, corrections, the free embed, or advertising.",
            contact_body(),
        ),
    }
    wrap = with_analytics or (lambda p: p)
    for slug, (title, desc, body) in pages.items():
        os.makedirs(os.path.join(R, slug), exist_ok=True)
        page = wrap(_legal_shell(site, slug, title, desc, body))
        open(os.path.join(R, slug, "index.html"), "w").write(page)
    open(os.path.join(R, "privacy.html"), "w").write(privacy_redirect())


def sitemap_entries(site: str) -> list[tuple[str, str, str]]:
    return [
        (f"{site}/about/", "0.4", "yearly"),
        (f"{site}/advertise/", "0.3", "yearly"),
        (f"{site}/contact/", "0.3", "yearly"),
        (f"{site}/privacy/", "0.2", "yearly"),
    ]


def llms_lines() -> list[str]:
    return [
        "- /about/ : Who runs the site (Hypergame LLC), the main data sources, and the update schedule.",
        "- /privacy/ : Privacy policy, including analytics, data downloads, and cookies if ads are shown.",
        "- /contact/ : Email hello@everydebtclock.com.",
        "- /advertise/ : Sponsorship on the US clock and the national-debt-by-year page.",
    ]


def _upgrade_404_links(page: str) -> str:
    page = _PRIVACY_HREF_RE.sub(r'\1privacy/"', page)
    # The 404 page uses a small link row, not a <footer>.
    m = re.search(
        r'<p[^>]*>((?:<a href="/[^"]+"[^>]*>[^<]+</a>\s*·\s*)+<a href="/[^"]+"[^>]*>[^<]+</a>)</p>',
        page,
    )
    if not m:
        return page
    links = link_list("/", absolute=True)
    return page[: m.start(1)] + links + page[m.end(1) :]


def _iter_html(R: str):
    for root, dirs, files in os.walk(R):
        dirs[:] = [d for d in dirs if d not in {".git", "cache", "pipeline", "__pycache__"}]
        for name in files:
            if name.endswith(".html"):
                yield os.path.join(root, name)


_MAILTO_RE = re.compile(r'<a href="mailto:[^"]*">.*?</a>', re.I | re.S)
_META_RE = re.compile(r"<meta\b[^>]*>", re.I)


def _inside_email_off(page: str, index: int) -> bool:
    return page.rfind("<!--email_off-->", 0, index) > page.rfind("<!--/email_off-->", 0, index)


def protect_emails(page: str) -> str:
    """Keep mailto links as plain HTML.

    Cloudflare Email Obfuscation rewrites an address to /cdn-cgi/l/email-protection, which is a 404
    for clients that do not run Cloudflare's script. The email_off comments are Cloudflare's opt-out.
    """
    def wrap_mailto(m):
        if _inside_email_off(page, m.start()):
            return m.group(0)
        return "<!--email_off-->" + m.group(0) + "<!--/email_off-->"

    page = _MAILTO_RE.sub(wrap_mailto, page)

    def wrap_meta(m):
        tag = m.group(0)
        if "@" not in tag or _inside_email_off(page, m.start()):
            return tag
        return "<!--email_off-->" + tag + "<!--/email_off-->"

    return _META_RE.sub(wrap_meta, page)


def finalize(R: str, extra: tuple[tuple[str, str], ...] = ()) -> None:
    """Refresh footers and inject the cookie notice on ordinary site pages."""
    for path in _iter_html(R):
        rel = os.path.relpath(path, R)
        raw = open(path, encoding="utf-8").read()
        page = raw
        if os.path.basename(path) == "analytics.html":
            continue
        if os.path.basename(path) == "privacy.html" and "location.replace(\"/privacy/\"" in page:
            # Keep the redirect file as-is (already points at /privacy/).
            continue
        if os.path.basename(path) == "404.html":
            page = _upgrade_404_links(page)
        else:
            page = _PRIVACY_HREF_RE.sub(r'\1privacy/"', page)
            page = _FOOTER_RE.sub(lambda m: upgrade_footer(m.group(0), extra), page)
        if not skip_notice(rel):
            page = with_notice(page)
            if not _redirect(page):
                page = with_a2hs(page)
        page = protect_emails(page)
        if page != raw:
            open(path, "w", encoding="utf-8").write(page)
