#!/usr/bin/env python3
"""Submit sitemap URLs to IndexNow (Bing, Yandex and other engines). No account required.

The verification key lives in pipeline/indexnow.key. build.py writes a file named
{key}.txt at the site root with the key as its body, which IndexNow fetches.
"""
import argparse, json, sys, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path

API = "https://api.indexnow.org/indexnow"
ROOT = Path(__file__).resolve().parents[1]
# Cloudflare (and some other edges) return 403 to Python's default urllib User-Agent.
UA = "EveryDebtClock-IndexNow/1.0 (+https://everydebtclock.com/)"

def open_url(url, timeout, data=None, headers=None, method=None):
    hdrs = {"User-Agent": UA}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    return urllib.request.urlopen(req, timeout=timeout)

def load_key(path):
    key = Path(path).read_text().strip()
    if not key:
        sys.exit("indexnow: empty key file")
    return key

def urls_from_sitemap(src):
    if src.startswith("http://") or src.startswith("https://"):
        with open_url(src, timeout=30) as r:
            data = r.read()
    else:
        data = Path(src).read_bytes()
    root = ET.fromstring(data)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = [el.text.strip() for el in root.findall("s:url/s:loc", ns) if el.text]
    if not locs:  # sitemap without a default xmlns prefix fallback
        locs = [el.text.strip() for el in root.iter() if el.tag.endswith("loc") and el.text]
    # unique, stable order
    seen, out = set(), []
    for u in locs:
        if u not in seen:
            seen.add(u); out.append(u)
    return out

def key_url(site, key, key_location):
    return key_location or f"{site.rstrip('/')}/{key}.txt"

def wait_for_key(url, key, tries=8, delay=15):
    for i in range(1, tries + 1):
        try:
            with open_url(url, timeout=20) as r:
                body = r.read().decode("utf-8", "replace").strip()
                if r.status == 200 and body == key:
                    return True, r.status
        except Exception as e:
            err = e
        else:
            err = f"status or body mismatch"
        print(f"indexnow: key file not live yet ({url}, try {i}/{tries}: {err})", file=sys.stderr)
        if i < tries:
            time.sleep(delay)
    return False, None

def submit(host, key, key_location, url_list):
    payload = {"host": host, "key": key, "keyLocation": key_location, "urlList": url_list}
    try:
        with open_url(API, timeout=60, data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json; charset=utf-8"}, method="POST") as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

def urls_from_file(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    seen, out = set(), []
    for line in lines:
        u = line.strip()
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sitemap", default="", help="sitemap.xml path or URL; used when --urls is omitted")
    ap.add_argument("--urls", default="", help="text file of URLs whose figures changed, one per line")
    ap.add_argument("--host", default="everydebtclock.com")
    ap.add_argument("--site", default="https://everydebtclock.com")
    ap.add_argument("--key-file", default=str(ROOT / "pipeline" / "indexnow.key"))
    ap.add_argument("--wait", action="store_true", help="wait until the key file is fetchable at the site")
    ap.add_argument("--tries", type=int, default=8)
    ap.add_argument("--delay", type=int, default=15)
    ap.add_argument("--soft", action="store_true", help="print the error and exit 0 if the ping fails")
    args = ap.parse_args()
    def fail(msg, code=1):
        print(msg, file=sys.stderr)
        sys.exit(0 if args.soft else code)
    try:
        key = load_key(args.key_file)
    except Exception as e:
        fail(f"indexnow: {e}")
        return
    key_location = key_url(args.site, key, None)
    try:
        urls = urls_from_file(args.urls) if args.urls else urls_from_sitemap(args.sitemap or str(ROOT / "sitemap.xml"))
    except Exception as e:
        fail(f"indexnow: could not read URLs: {e}")
        return
    if not urls:
        fail("indexnow: no URLs to submit")
        return
    if args.wait:
        ok, st = wait_for_key(key_location, key, tries=args.tries, delay=args.delay)
        if not ok:
            fail(f"indexnow: giving up; key file not live at {key_location}", 2)
            return
    try:
        code, body = submit(args.host, key, key_location, urls)
    except Exception as e:
        fail(f"indexnow: ping failed: {e}")
        return
    text = body.decode("utf-8", "replace") if body else ""
    print(f"indexnow: HTTP {code}; submitted {len(urls)} URLs; keyLocation={key_location}")
    if text:
        print(text[:500])
    if code not in (200, 202):
        fail(f"indexnow: HTTP {code}", 1)

if __name__ == "__main__":
    main()
