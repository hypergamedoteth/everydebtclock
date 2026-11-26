#!/usr/bin/env python3
"""Fail if the staged site (_site) has an internal link, src, or og:image that is not a file.

Also reads sitemap.xml, llms.txt, CSS url(), and JSON feeds for internal URLs.
Requires the public URLs crawlers already request, including /your-share.html,
/your-share/born/, /country-series/, /openapi.json, and /.well-known/ai-plugin.json.

External http(s) links are requested and printed, including 404s. They do not fail
the check, because many official sites block automated requests.

Run after the workflow copies public files into _site. Passing the repo root instead of
_site does not catch a path that build.py wrote but the deploy copy list left behind.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from html.parser import HTMLParser
from urllib.parse import unquote, urlparse

HOSTS = {"everydebtclock.com", "www.everydebtclock.com"}
SKIP_SCHEMES = {"mailto", "tel", "sms", "javascript", "data", "blob", "about"}
CSS_URL = re.compile(r"url\(\s*['\"]?([^)'\"]+)['\"]?\s*\)", re.I)
TEXT_URL = re.compile(r"https?://[^\s<>\"']+")
LLMS_PATH = re.compile(r"(?<![\w/])(/[a-z0-9][a-z0-9._/-]*/)")
# Offline snapshot of the homepage. Its relative URLs are written as if the file were
# index.html, and nothing on the site links to /dist/.
ROOT_SHAPED = {"dist/debtclock-standalone.html"}
SHARE_YEARS = range(1930, 2027)  # keep in step with share_build.OG_MIN / OG_MAX
HIST_YEARS = (1960, 1980, 1990, 2000, 2010, 2020, 2025)
PNG = b"\x89PNG\r\n\x1a\n"
EMAIL_PAGES = (
    "about/index.html",
    "contact/index.html",
    "advertise/index.html",
    "press/index.html",
    "privacy/index.html",
)


class Refs(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found = []

    def handle_starttag(self, tag, attrs):
        d = {}
        for key, value in attrs:
            if key and value is not None:
                d[key.lower()] = value
        for key in ("href", "src"):
            if d.get(key):
                self.found.append((f"{tag} {key}", d[key]))
        if d.get("srcset"):
            for part in d["srcset"].split(","):
                url = part.strip().split()[0] if part.strip() else ""
                if url:
                    self.found.append((f"{tag} srcset", url))
        prop = (d.get("property") or d.get("name") or "").lower()
        if prop in ("og:image", "og:image:url", "og:image:secure_url", "twitter:image", "twitter:image:src") and d.get("content"):
            self.found.append((prop, d["content"]))


def fail(msg):
    print("check_links: " + msg, file=sys.stderr)
    sys.exit(1)


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.digest()


def is_png(path):
    with open(path, "rb") as f:
        return f.read(8) == PNG and os.path.getsize(path) > 32


def resolve(root, html_path, raw):
    """Return a path relative to root, or None when the URL is not an internal file."""
    raw = (raw or "").strip()
    if not raw or raw.startswith("#"):
        return None
    parsed = urlparse(raw)
    if parsed.scheme in SKIP_SCHEMES:
        return None
    if parsed.scheme in ("http", "https"):
        if (parsed.hostname or "").lower() not in HOSTS:
            return None
        path = parsed.path or "/"
    elif parsed.scheme:
        return None
    elif raw.startswith("//"):
        host = urlparse("https:" + raw).hostname or ""
        if host.lower() not in HOSTS:
            return None
        path = urlparse("https:" + raw).path or "/"
    elif raw.startswith("/"):
        path = parsed.path or "/"
    else:
        base = root if os.path.relpath(html_path, root) in ROOT_SHAPED else os.path.dirname(html_path)
        path = os.path.relpath(os.path.normpath(os.path.join(base, unquote(parsed.path))), root)
        return path
    path = unquote(path).split("?", 1)[0]
    if path.startswith("/"):
        path = path[1:]
    return path


def target_file(root, rel):
    """File that serves this URL path, or None."""
    if rel in ("", "."):
        rel = "index.html"
    full = os.path.normpath(os.path.join(root, rel))
    if not full.startswith(os.path.normpath(root) + os.sep) and full != os.path.normpath(root):
        return None
    if rel.endswith("/") or os.path.isdir(full):
        index = os.path.join(full, "index.html")
        return index if os.path.isfile(index) else None
    if os.path.isfile(full):
        return full
    return None


def iter_html(root):
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in {".git", "cache", "pipeline", "__pycache__"}]
        for name in files:
            if name.endswith(".html"):
                yield os.path.join(dirpath, name)


def same(root, a, b):
    pa, pb = os.path.join(root, a), os.path.join(root, b)
    if not (os.path.isfile(pa) and os.path.isfile(pb)):
        fail(f"missing alias pair {a} or {b}")
    if not is_png(pa) or sha(pa) != sha(pb):
        fail(f"{a} is not a copy of {b}")


def require_redirect(root, rel, canonical, refresh):
    path = os.path.join(root, rel)
    if not os.path.isfile(path):
        fail(f"missing redirect {rel}")
    text = open(path, encoding="utf-8", errors="replace").read()
    if f'rel="canonical" href="{canonical}"' not in text:
        fail(f"{rel} canonical is not {canonical}")
    if "noindex" not in text:
        fail(f"{rel} is missing noindex")
    if f"url={refresh}" not in text:
        fail(f"{rel} does not refresh to {refresh}")


class WorldTable(HTMLParser):
    """Name links in #debt-table. The first link in the country cell is the row link."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_table = False
        self.in_row = False
        self.in_name = False
        self.in_link = False
        self.rows = []
        self._name = ""
        self._href = None
        self._text = ""
        self._seen_link = False

    def handle_starttag(self, tag, attrs):
        d = {}
        for key, value in attrs:
            if key and value is not None:
                d[key.lower()] = value
        if tag == "table" and d.get("id") == "debt-table":
            self.in_table = True
            return
        if not self.in_table:
            return
        if tag == "tr" and "data-name" in d:
            self.in_row = True
            self.in_name = False
            self.in_link = False
            self._seen_link = False
            self._name = d.get("data-name") or ""
            self._href = None
            self._text = ""
            return
        if self.in_row and tag == "td" and "c" in (d.get("class") or "").split():
            self.in_name = True
            return
        if self.in_name and tag == "a" and not self._seen_link:
            self._seen_link = True
            self.in_link = True
            self._href = d.get("href") or ""
            self._text = ""

    def handle_endtag(self, tag):
        if tag == "a" and self.in_link:
            self.in_link = False
        elif tag == "td" and self.in_name:
            self.in_name = False
        elif tag == "tr" and self.in_row:
            self.rows.append({"name": self._name, "href": self._href, "text": " ".join(self._text.split())})
            self.in_row = False
            self.in_name = False
            self.in_link = False
        elif tag == "table" and self.in_table:
            self.in_table = False

    def handle_data(self, data):
        if self.in_link:
            self._text += data


def check_world_table(root):
    """Every By-country row links its country name to a page that exists.

    The United States name links to the homepage. /countries/united-states/ is a redirect, not the clock.
    """
    import json
    world_path = os.path.join(root, "world", "index.html")
    if not os.path.isfile(world_path):
        fail(f"missing world/index.html under {root}")
    parser = WorldTable()
    parser.feed(open(world_path, encoding="utf-8").read())
    api_path = os.path.join(root, "api", "world.json")
    if not os.path.isfile(api_path):
        fail("missing api/world.json")
    countries = json.load(open(api_path, encoding="utf-8")).get("countries") or []
    by_name = {}
    for country in countries:
        name = country.get("name") or ""
        if name in by_name:
            fail(f"duplicate country name in api/world.json: {name}")
        by_name[name] = country
    if len(parser.rows) != len(countries):
        fail(f"world table has {len(parser.rows)} named rows, api/world.json has {len(countries)}")
    seen = set()
    for row in parser.rows:
        name = row["name"]
        if name in seen:
            fail(f"duplicate world table row {name}")
        seen.add(name)
        country = by_name.get(name)
        if country is None:
            fail(f"world table row {name!r} is not in api/world.json")
        if not row["href"] or row["text"] != name:
            fail(f"{name} name is not a link (href={row['href']!r}, text={row['text']!r})")
        slug = country.get("slug") or ""
        if country.get("iso3") == "USA" or slug == "united-states":
            if row["href"] != "../":
                fail(f"United States row links to {row['href']}, expected ../")
        else:
            expect = f"../countries/{slug}/"
            if row["href"] != expect:
                fail(f"{name} links to {row['href']}, expected {expect}")
        if "united-states" in (row["href"] or ""):
            fail(f"{name} links to /countries/united-states/")
        rel = resolve(root, world_path, row["href"])
        if rel is None or target_file(root, rel) is None:
            fail(f"{name} link {row['href']} does not exist under {root} ({rel})")
    missing = [c.get("name") for c in countries if c.get("name") not in seen]
    if missing:
        fail("world table is missing rows: " + ", ".join(missing[:12]))
    page = open(world_path, encoding="utf-8").read()
    if 'id="table"' not in page or '<h2>Debt clock by country</h2>' not in page:
        fail("world table section lost id=table or the Debt clock by country heading")


def check_legacy(root):
    require_redirect(root, "countries/united-states/index.html", "https://everydebtclock.com/", "/")
    require_redirect(root, "texas/index.html", "https://everydebtclock.com/states/texas/", "/states/texas/")
    require_redirect(root, "uk/index.html", "https://everydebtclock.com/countries/united-kingdom/", "/countries/united-kingdom/")
    require_redirect(root, "world-government-debt/index.html", "https://everydebtclock.com/world/", "../world/")
    require_redirect(root, "global-debt-clock/index.html", "https://everydebtclock.com/world/", "../world/")
    require_redirect(root, "t/tax_returns/index.html", "https://everydebtclock.com/t/tax_returns.html", "../tax_returns.html")
    require_redirect(root, "t/taxpayers/index.html", "https://everydebtclock.com/t/tax_returns.html", "../tax_returns.html")
    for rel in ("apple-touch-icon-precomposed.png", "api/index.html", "og/taxpayers.png", "og/tax_returns.png", "og/debt_total.png",
                "your-share/og/default.png", "your-share/og/default-sq.png"):
        if not os.path.isfile(os.path.join(root, rel)):
            fail(f"missing {rel}")
    same(root, "apple-touch-icon-precomposed.png", "apple-touch-icon.png")
    same(root, "og/taxpayers.png", "og/tax_returns.png")
    for year in HIST_YEARS:
        for kind in ("hist_debt_gdp", "hist_def_gdp"):
            same(root, f"og/{kind}_{year}.png", "og/debt_total.png")
    for year in SHARE_YEARS:
        same(root, f"your-share/og/{year}.png", "your-share/og/default.png")
        same(root, f"your-share/og/{year}-sq.png", "your-share/og/default-sq.png")
    api = open(os.path.join(root, "api", "index.html"), encoding="utf-8").read()
    for name in ("daily.json", "daily.txt", "world.json", "/data/", "/openapi.json"):
        if name not in api:
            fail(f"/api/ index does not point at {name}")
    for rel in ("your-share.html", "your-share/born/index.html", "country-series/index.html",
                "openapi.json", "swagger.json", ".well-known/ai-plugin.json"):
        if not os.path.isfile(os.path.join(root, rel)):
            fail(f"missing {rel}")
    spec_text = open(os.path.join(root, "openapi.json"), encoding="utf-8").read()
    if open(os.path.join(root, "swagger.json"), encoding="utf-8").read() != spec_text:
        fail("swagger.json is not a copy of openapi.json")
    home = open(os.path.join(root, "index.html"), encoding="utf-8").read()
    if 'rel="canonical" href="https://everydebtclock.com/"' not in home:
        fail("index.html canonical is not https://everydebtclock.com/")
    if "/index.html" in home.split('rel="canonical"', 1)[1][:80]:
        fail("index.html canonical still points at /index.html")
    if "index\\.html" not in home and "index.html" not in home.split("<title>", 1)[0]:
        fail("index.html does not redirect /index.html to /")
    require_redirect(root, "your-share.html", "https://everydebtclock.com/your-share/", "/your-share/")
    spec = json.load(open(os.path.join(root, "openapi.json"), encoding="utf-8"))
    if not str(spec.get("openapi", "")).startswith("3."):
        fail("openapi.json is not OpenAPI 3")
    if "everydebtclock.com" not in json.dumps(spec.get("info", {})):
        fail("openapi.json info does not name everydebtclock.com")
    check_world_table(root)
    world = open(os.path.join(root, "world", "index.html"), encoding="utf-8").read()
    if 'href="../countries/united-states/"' in world or 'href="/countries/united-states/"' in world:
        fail("world page still links to /countries/united-states/")
    if 'href="../">United States debt clock</a>' not in world:
        fail("world page does not link the United States row to /")
    rows = json.load(open(os.path.join(root, "api", "world.json")))["countries"]
    usa = next(r for r in rows if r.get("iso3") == "USA")
    if usa.get("url", "").rstrip("/") != "https://everydebtclock.com":
        fail(f"api/world.json USA url is {usa.get('url')}")
    for rel in EMAIL_PAGES:
        text = open(os.path.join(root, rel), encoding="utf-8").read()
        if "<!--email_off-->" not in text or "mailto:hello@everydebtclock.com" not in text:
            fail(f"{rel} does not serve a plain mailto inside email_off")
        if "/cdn-cgi/l/email-protection" in text:
            fail(f"{rel} still points at /cdn-cgi/l/email-protection")
    page404 = open(os.path.join(root, "404.html"), encoding="utf-8").read()
    if 'name="robots" content="noindex"' not in page404:
        fail("404.html lost its noindex")


def _walk_files(root):
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in {".git", "cache", "pipeline", "__pycache__"}]
        for name in files:
            yield os.path.join(dirpath, name)


def _json_strings(obj, out):
    if isinstance(obj, dict):
        for value in obj.values():
            _json_strings(value, out)
    elif isinstance(obj, list):
        for value in obj:
            _json_strings(value, out)
    elif isinstance(obj, str) and (obj.startswith("http://") or obj.startswith("https://") or (obj.startswith("/") and " " not in obj and len(obj) < 300)):
        out.append(obj)


def collect_refs(root):
    """Every internal reference the deploy should be able to serve, plus external URLs."""
    refs = []
    external = []
    pages = 0
    for path in _walk_files(root):
        relf = os.path.relpath(path, root).replace("\\", "/")
        name = os.path.basename(path)
        if name.endswith(".html"):
            pages += 1
            text = open(path, encoding="utf-8", errors="replace").read()
            parser = Refs()
            try:
                parser.feed(text)
            except Exception as exc:
                fail(f"could not read {relf}: {exc}")
            refs.extend((path, kind, raw) for kind, raw in parser.found)
            refs.extend((path, "css url", m.group(1)) for m in CSS_URL.finditer(text))
        elif name.endswith(".css"):
            text = open(path, encoding="utf-8", errors="replace").read()
            refs.extend((path, "css url", m.group(1)) for m in CSS_URL.finditer(text))
        elif name.endswith(".xml"):
            text = open(path, encoding="utf-8", errors="replace").read()
            refs.extend((path, "sitemap", loc.strip()) for loc in re.findall(r"<loc>\s*([^<]+)\s*</loc>", text))
        elif name == "llms.txt" or (name.endswith(".txt") and relf in {"llms.txt", "robots.txt", "api/daily.txt"}):
            text = open(path, encoding="utf-8", errors="replace").read()
            refs.extend((path, "text", m.rstrip(".,);")) for m in TEXT_URL.findall(text))
            if name == "llms.txt":
                refs.extend((path, "llms path", m) for m in LLMS_PATH.findall(text))
        elif name.endswith(".json") and (relf.startswith("api/") or relf.startswith("country-series/") or relf.startswith("data/") or relf in {"openapi.json", ".well-known/ai-plugin.json"}):
            try:
                doc = json.loads(open(path, encoding="utf-8").read())
            except Exception:
                continue
            found = []
            _json_strings(doc, found)
            refs.extend((path, "json", raw) for raw in found)
    kept = []
    for path, kind, raw in refs:
        host = ""
        if raw.startswith("http"):
            host = (urlparse(raw).hostname or "").lower()
        if host and host not in HOSTS:
            external.append(raw.split("#")[0].rstrip(".,);"))
            continue
        kept.append((path, kind, raw))
    return pages, kept, sorted(set(external))


def check_external(urls):
    """Print external failures, including 404s. They do not fail the check."""
    if os.environ.get("CHECK_LINKS_SKIP_EXTERNAL") == "1" or not urls:
        print(f"external links skipped ({len(urls)} urls)")
        return
    import ssl
    import urllib.error
    import urllib.request
    from concurrent.futures import ThreadPoolExecutor
    ctx = ssl.create_default_context()

    def one(url):
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "everydebtclock-linkcheck/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=8, context=ctx) as resp:
                resp.read(64)
                return url, getattr(resp, "status", 200), ""
        except urllib.error.HTTPError as exc:
            return url, exc.code, ""
        except Exception as exc:
            return url, 0, type(exc).__name__

    gone = []
    other = []
    with ThreadPoolExecutor(max_workers=16) as pool:
        for url, code, err in pool.map(one, urls):
            if code in (404, 410):
                gone.append(f"{code} {url}")
            elif not code or code >= 400:
                other.append(f"{code or err} {url}")
    print(f"external links: {len(urls)} checked, {len(gone)} not found, {len(other)} other failures")
    for line in gone:
        print("external 404: " + line)
    for line in other[:30]:
        print("external: " + line)
    if len(other) > 30:
        print(f"external: ... and {len(other) - 30} more non-404 failures")


def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "_site")
    if not os.path.isdir(root):
        fail(f"{root} is not a directory (stage the site before this check)")
    missing = []
    pages, refs, external = collect_refs(root)
    links = 0
    for html_path, kind, raw in refs:
        links += 1
        rel = resolve(root, html_path, raw)
        if rel is None:
            continue
        found = target_file(root, rel)
        if found is None:
            missing.append(f"{os.path.relpath(html_path, root)}: {kind}={raw} -> {rel}")
        elif found.endswith(".png") and not is_png(found):
            missing.append(f"{os.path.relpath(html_path, root)}: {raw} is not a PNG")
    if missing:
        preview = "\n".join(missing[:40])
        extra = f"\n... and {len(missing) - 40} more" if len(missing) > 40 else ""
        fail(f"{len(missing)} internal target(s) missing under {root}:\n{preview}{extra}")
    check_legacy(root)
    check_external(external)
    print(f"check_links ok: {pages} pages, {links} refs, legacy image and redirect URLs present")


if __name__ == "__main__":
    main()
