#!/usr/bin/env python3
"""Fail if the staged site (_site) has an internal link, src, or og:image that is not a file.

Also requires the public URLs crawlers already request: the US country alias, the retired
share and OG images, the precomposed touch icon, /api/, and the /t/ trailing-slash aliases.
Those are not all linked from current pages, so a link scan alone would not keep them.

Run after the workflow copies public files into _site. Passing the repo root instead of
_site does not catch a path that build.py wrote but the deploy copy list left behind.
"""
from __future__ import annotations

import hashlib
import os
import sys
from html.parser import HTMLParser
from urllib.parse import unquote, urlparse

HOSTS = {"everydebtclock.com", "www.everydebtclock.com"}
SKIP_SCHEMES = {"mailto", "tel", "sms", "javascript", "data", "blob", "about"}
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


def check_legacy(root):
    require_redirect(root, "countries/united-states/index.html", "https://everydebtclock.com/", "/")
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
    for name in ("daily.json", "daily.txt", "world.json", "/data/"):
        if name not in api:
            fail(f"/api/ index does not point at {name}")
    world = open(os.path.join(root, "world", "index.html"), encoding="utf-8").read()
    if 'href="../countries/united-states/"' in world or 'href="/countries/united-states/"' in world:
        fail("world page still links to /countries/united-states/")
    if 'href="../">United States debt clock</a>' not in world:
        fail("world page does not link the United States row to /")
    import json
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


def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "_site")
    if not os.path.isdir(root):
        fail(f"{root} is not a directory (stage the site before this check)")
    missing = []
    pages = links = 0
    for html_path in iter_html(root):
        pages += 1
        parser = Refs()
        try:
            parser.feed(open(html_path, encoding="utf-8", errors="replace").read())
        except Exception as exc:
            fail(f"could not read {os.path.relpath(html_path, root)}: {exc}")
        for kind, raw in parser.found:
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
    print(f"check_links ok: {pages} pages, {links} refs, legacy image and redirect URLs present")


if __name__ == "__main__":
    main()
