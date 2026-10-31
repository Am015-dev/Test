"""Diagnostic: fetch XE listing pages and print what they really say (description + facts)."""

import re
import sys
from pathlib import Path

sys.path.insert(0, "src")
from selectolax.lexbor import LexborHTMLParser as HTMLParser  # noqa: E402

from scout.collectors.xe import XeCollector, parse_detail_jsonld  # noqa: E402
from scout.config import get_settings, load_strategy  # noqa: E402

c = XeCollector(load_strategy())
s = c._new_session()
for url in Path("diag/urls.txt").read_text().split():
    html = c._fetch_detail(s, url)
    print("\n" + "=" * 100 + "\n" + url)
    if not html:
        print("!! NO PAGE (blocked or removed)")
        continue
    d = parse_detail_jsonld(html) or {}
    print("JSONLD:", {k: v for k, v in d.items() if k != "description"})
    print("DESCRIPTION:", re.sub(r"\s+", " ", d.get("description") or "")[:3000])
    imgs = list(dict.fromkeys(re.findall(r"https://blob\.cdn\.xe\.gr/[^\"' ]+?-source\.jpg", html)))
    print("IMAGES:", " ".join(imgs[:12]))
    import json as _json
    print("IMAGE_COUNTS:", re.findall(r"image_count(?:&quot;|\"):(\d+)", html)[:12])
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            j = _json.loads(m.group(1))
        except Exception:
            continue
        items = j if isinstance(j, list) else [j]
        for it in items:
            ph = it.get("photo") or it.get("image") or []
            if isinstance(ph, (list, str)):
                print("JSONLD", it.get("@type"), "photos:", len(ph) if isinstance(ph, list) else 1)
    t = HTMLParser(html)
    for sel in ("[data-testid='characteristics']", ".characteristics", "[class*='characteristic']",
                "[data-testid*='feature']", "[class*='features']"):
        n = t.css_first(sel)
        if n:
            print("FACTS", sel, ":", re.sub(r"\s+", " ", n.text(separator=" | "))[:1200])
            break
    c._paced_sleep(get_settings())
