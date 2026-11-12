#!/usr/bin/env python3
"""Submit sitemap URLs to IndexNow (Bing, Yandex and other engines). No account required.

The verification key lives in pipeline/indexnow.key. build.py writes a file named
{key}.txt at the site root with the key as its body, which IndexNow fetches.
"""
import argparse, json, sys, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path

API = "https://api.indexnow.org/indexnow"
ROOT = Path(__file__).resolve().parents[1]

def load_key(path):
    key = Path(path).read_text().strip()
    if not key:
        sys.exit("indexnow: empty key file")
    return key

def urls_from_sitemap(src):
    if src.startswith("http://") or src.startswith("https://"):
        with urllib.request.urlopen(src, timeout=30) as r:
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
            with urllib.request.urlopen(url, timeout=20) as r:
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
    req = urllib.request.Request(
        API, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sitemap", default=str(ROOT / "sitemap.xml"), help="sitemap.xml path or URL")
    ap.add_argument("--host", default="everydebtclock.com")
    ap.add_argument("--site", default="https://everydebtclock.com")
    ap.add_argument("--key-file", default=str(ROOT / "pipeline" / "indexnow.key"))
    ap.add_argument("--wait", action="store_true", help="wait until the key file is fetchable at the site")
    ap.add_argument("--tries", type=int, default=8)
    ap.add_argument("--delay", type=int, default=15)
    args = ap.parse_args()
    key = load_key(args.key_file)
    key_location = key_url(args.site, key, None)
    urls = urls_from_sitemap(args.sitemap)
    if not urls:
        sys.exit(f"indexnow: no URLs in {args.sitemap}")
    if args.wait:
        ok, st = wait_for_key(key_location, key, tries=args.tries, delay=args.delay)
        if not ok:
            print(f"indexnow: giving up; key file not live at {key_location}", file=sys.stderr)
            sys.exit(2)
    code, body = submit(args.host, key, key_location, urls)
    text = body.decode("utf-8", "replace") if body else ""
    print(f"indexnow: HTTP {code}; submitted {len(urls)} URLs; keyLocation={key_location}")
    if text:
        print(text[:500])
    if code not in (200, 202):
        sys.exit(1)

if __name__ == "__main__":
    main()
