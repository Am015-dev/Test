"""Survey which Greek portals a GitHub runner can read with plain `requests`.

Run from a runner (the dev sandbox is blocked):  python diag/sources_probe.py
For each portal it fetches robots.txt, then a few candidate search-results URLs for
Χολαργός (sale, flats) and prints: status, final URL, HTML length, price-like strings,
detail-page links, JSON-LD / __NEXT_DATA__ / API markers, and the robots.txt Disallow
lines. With --links it also lists the homepage links that look like search pages, to
find the right search URL. Polite: real UA, 4–7 s between every request.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import random
import re
import sys
import time
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "el-GR,el;q=0.9,en;q=0.8",
}

# name -> (base, [candidate search URLs])
PORTALS: dict[str, tuple[str, list[str]]] = {
    "spiti24": ("https://www.spiti24.gr", []),
    "plot": ("https://www.plot.gr", []),
    "tospitimou": ("https://www.tospitimou.gr", []),
    "remax": ("https://www.remax.gr", []),
    "era": ("https://www.era.gr", []),
    "xrysi-eukairia": ("https://www.xrysi-eukairia.gr", []),
    "goldenhome": ("https://www.goldenhome.gr", []),
    "spitogatos": (
        "https://www.spitogatos.gr",
        ["https://www.spitogatos.gr/pwliseis-katoikies/cholargos"],
    ),
    "indomio": (
        "https://www.indomio.gr",
        ["https://www.indomio.gr/pwliseis-katoikies/cholargos/"],
    ),
    "noikaki": ("https://www.noikaki.gr", []),
}

PRICE_RE = re.compile(r"\d{1,3}(?:[.,]\d{3})+\s*(?:€|&euro;|EUR)|€\s*\d{1,3}(?:[.,]\d{3})+")
SEARCHY = re.compile(
    r"pwl|polis|πωλ|sale|buy|agor|αγορ|search|anazit|αναζητ|cholarg|χολαργ|katoik|κατοικ|"
    r"diamer|διαμερ|aggel|αγγελ|property|akinit|ακινητ",
    re.I,
)
HREF_RE = re.compile(r'href=["\']([^"\'#]+)["\']', re.I)
API_RE = re.compile(r"[\"'](/?(?:api|_next/data|wp-json|graphql|ajax)[^\"'\s]{0,120})[\"']", re.I)


def pause() -> None:
    time.sleep(random.uniform(4, 7))


def get(session: requests.Session, url: str) -> requests.Response | None:
    try:
        r = session.get(url, timeout=30, allow_redirects=True)
    except requests.RequestException as exc:
        print(f"    ERR {url}: {type(exc).__name__}: {str(exc)[:160]}")
        r = None
    pause()
    return r


def robots(session: requests.Session, base: str) -> RobotFileParser:
    rp = RobotFileParser()
    r = get(session, base + "/robots.txt")
    if r is None or not r.ok:
        print(f"  robots.txt: {getattr(r, 'status_code', 'ERR')} (treated as allow-all)")
        rp.parse([])
        return rp
    lines = r.text.splitlines()
    rp.parse(lines)
    agent = None
    for ln in lines:
        s = ln.strip()
        if s.lower().startswith("user-agent:"):
            agent = s.split(":", 1)[1].strip()
        elif s.lower().startswith(("disallow:", "sitemap:")) and agent in ("*", None):
            print(f"  robots[{agent}] {s}")
    return rp


def analyse(
    name: str, url: str, r: requests.Response, rp: RobotFileParser, dump: bool, grep: str = ""
) -> None:
    html = r.text or ""
    host = urlparse(r.url).netloc
    links = {urljoin(r.url, h) for h in HREF_RE.findall(html)}
    own = [x for x in links if urlparse(x).netloc == host]
    detailish = [x for x in own if re.search(r"/\d{5,}|[-/]\d{6,}|/property/|/aggelia|/ad/", x)]
    print(
        f"  GET {url}\n    status={r.status_code} final={r.url} len={len(html)} "
        f"allowed_by_robots={rp.can_fetch(UA, r.url)}\n"
        f"    prices={len(PRICE_RE.findall(html))} detail_links={len(detailish)} "
        f"jsonld={html.count('application/ld+json')} next_data={'__NEXT_DATA__' in html} "
        f"nuxt={'__NUXT__' in html} cf={'cf-chl' in html or 'Just a moment' in html} "
        f"px={'px-captcha' in html or '_pxAppId' in html}"
    )
    for ex in sorted(detailish)[:5]:
        print(f"    detail e.g. {ex}")
    apis = sorted(set(API_RE.findall(html)))[:10]
    for a in apis:
        print(f"    api? {a}")
    if grep:
        hits = sorted({x for x in links if re.search(grep, x, re.I)})
        for x in hits[:60]:
            print(f"    grep {x}")
    if dump and html:
        blob = base64.b64encode(gzip.compress(html.encode("utf-8"))).decode()
        print(f"    DUMP-BEGIN {name} {len(blob)}")
        for i in range(0, len(blob), 4000):
            print("    D " + blob[i : i + 4000])
        print(f"    DUMP-END {name}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated portal names")
    ap.add_argument("--links", action="store_true", help="list search-like homepage links")
    ap.add_argument("--dump", default="", help="portal names whose search HTML to dump b64")
    ap.add_argument("--url", action="append", default=[], help="name=url extra candidates")
    ap.add_argument("--grep", default="", help="print page links matching this regex")
    ap.add_argument("--no-home", action="store_true", help="skip the homepage fetch")
    args = ap.parse_args()
    only = {x for x in args.only.split(",") if x}
    dump = {x for x in args.dump.split(",") if x}
    extra: dict[str, list[str]] = {}
    for spec in args.url:
        n, u = spec.split("=", 1)
        extra.setdefault(n, []).append(u)

    for name, (base, cands) in PORTALS.items():
        if only and name not in only:
            continue
        print(f"\n=== {name} ({base})")
        session = requests.Session()
        session.headers.update(HEADERS)
        rp = robots(session, base)
        home = None if args.no_home else get(session, base + "/")
        if home is not None:
            analyse(name + "-home", base + "/", home, rp, False)
        if home is not None and args.links:
            host = urlparse(home.url).netloc
            seen = set()
            for h in HREF_RE.findall(home.text or ""):
                full = urljoin(home.url, h)
                if urlparse(full).netloc == host and SEARCHY.search(full) and full not in seen:
                    seen.add(full)
            for full in sorted(seen)[:40]:
                print(f"    link {full}")
        for url in cands + extra.get(name, []):
            if not rp.can_fetch(UA, url):
                print(f"  SKIP {url}: disallowed by robots.txt")
                continue
            r = get(session, url)
            if r is not None:
                analyse(name, url, r, rp, name in dump, args.grep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
