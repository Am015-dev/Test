"""Diagnostic: fetch XE listing pages and print what they really say (description + facts)."""

import re
import sys
from pathlib import Path

sys.path.insert(0, "src")
from selectolax.lexbor import LexborHTMLParser as HTMLParser  # noqa: E402

from scout.collectors.xe import XeCollector, parse_detail_jsonld  # noqa: E402
from scout.config import get_settings  # noqa: E402

c = XeCollector()
s = c._new_session()
for url in Path("diag/urls.txt").read_text().split():
    html = c._fetch_detail(s, url)
    print("\n" + "=" * 100 + "\n" + url)
    if not html:
        print("!! NO PAGE (blocked or removed)")
        continue
    d = parse_detail_jsonld(html) or {}
    print("JSONLD:", {k: v for k, v in d.items() if k != "description"})
    print("DESCRIPTION:", re.sub(r"\s+", " ", d.get("description") or "")[:1500])
    t = HTMLParser(html)
    for sel in ("[data-testid='characteristics']", ".characteristics", "[class*='characteristic']",
                "[data-testid*='feature']", "[class*='features']"):
        n = t.css_first(sel)
        if n:
            print("FACTS", sel, ":", re.sub(r"\s+", " ", n.text(separator=" | "))[:1200])
            break
    c._paced_sleep(get_settings())
