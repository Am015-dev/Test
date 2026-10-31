"""One-round RE/MAX probe: find a server-rendered sale search for Χολαργός.

Runner-only. Polite (real UA, 4–7 s apart), robots.txt checked before every URL. Tries:
the sale-path analogue of the rental pages (RE/MAX transliterates η→h, ω→w), the
``/search/`` links, and the ``xml_sitemaps/el`` index. Prints status, card/price counts and
Χολαργός links; dumps (gzip+base64) the first page that has listing cards.
"""

from __future__ import annotations

import base64
import gzip
import random
import re
import time
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import requests

from scout.collectors.base import USER_AGENT

BASE = "https://www.remax.gr"
PRICE_RE = re.compile(r"\d{1,3}(?:\.\d{3})+\s*(?:€|&euro;)|€\s*\d{1,3}(?:\.\d{3})+")
DETAIL_RE = re.compile(r"/property/\d{4,}-[a-z0-9-]+")
CHOL_RE = re.compile(r'href="([^"]*(?:xolarg|cholarg|holarg)[^"]*)"', re.I)
# Round 1 (run 41221767513) found the sale scheme in the sitemap:
# /pwliseis-agora-katoikies/<id>-<slug>; round 2 checks the page itself.
CANDIDATES = ["/pwliseis-agora-katoikies/1031-xolargos"]
WEEKLY = re.compile(
    r"/\d+-(xolargos|papagoy|agia-paraskeyh|xalandri|brilhssia|maroysi|zwgrafoy|"
    r"palaio-ycyxiko|neo-ycyxiko|ycyxiko|filo8eh|hrakleio|nea-filadelfeia|peykh|galatsi|"
    r"ampelokhpoi|metamorfwsh)$"
)

s = requests.Session()
s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "el-GR,el;q=0.9"})
rp = RobotFileParser()
rp.parse(s.get(BASE + "/robots.txt", timeout=30).text.splitlines())
dumped = False


def get(path: str) -> requests.Response | None:
    url = urljoin(BASE, path)
    if not rp.can_fetch(USER_AGENT, url):
        print(f"SKIP robots {url}")
        return None
    time.sleep(random.uniform(4, 7))
    try:
        return s.get(url, timeout=30)
    except requests.RequestException as exc:
        print(f"ERR {url} {exc}")
        return None


def report(path: str, r: requests.Response) -> None:
    global dumped
    html = r.text
    details = sorted(set(DETAIL_RE.findall(html)))
    chol = sorted(set(CHOL_RE.findall(html)))
    print(
        f"GET {path} -> {r.status_code} final={r.url} len={len(html)} "
        f"prices={len(PRICE_RE.findall(html))} details={len(details)} chol_links={len(chol)}"
    )
    for d in details[:5]:
        print(f"   detail {d}")
    for c in chol[:20]:
        print(f"   chol {c}")
    nxt = re.findall(r'href="([^"]*[?&]page=\d+[^"]*)"', html)[:3]
    for n in nxt:
        print(f"   page-link {n}")
    if r.ok and len(details) >= 5 and not dumped:
        blob = base64.b64encode(gzip.compress(html.encode())).decode()
        print(f"DUMP-BEGIN remax {len(blob)}")
        for i in range(0, len(blob), 4000):
            print("D " + blob[i : i + 4000])
        print("DUMP-END remax")
        dumped = True


for path in CANDIDATES:
    r = get(path)
    if r is not None:
        report(path, r)

# Area ids for the weekly areas, from the sale-homes sitemap.
r = get("/xml_sitemaps/el/pwliseis-agora/katoikies.xml")
if r is not None:
    for u in re.findall(r"<loc>([^<]+)</loc>", r.text):
        if u.startswith(BASE + "/pwliseis-agora-katoikies/") and WEEKLY.search(u):
            print(f"AREA {u}")
