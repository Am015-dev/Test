"""Runner-only: capture a real XE rental search page for the rental-card fixture.

Uses the project's own polite XeCollector session (same pacing as the weekly run). Prints
gzip+base64 of the first rental cards of page 1 between BEGIN/END markers (the fixture is
copied from the job log), then runs ``collect_rentals`` for the area and prints field
coverage, so the PR can quote real numbers.
"""

from __future__ import annotations

import base64
import gzip
import sys
from collections import Counter

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from scout.collectors.xe import XeCollector
from scout.config import load_strategy

area = sys.argv[1] if len(sys.argv) > 1 else "Cholargos"
strategy = load_strategy().model_copy(deep=True)
strategy.search.municipality = area
xe = XeCollector(strategy)
session = xe._new_session()
url = xe.search_urls(strategy, transaction="rent")[0]
print("URL", url)
html = xe._fetch_html(session, url) or ""
cards = HTMLParser(html).css(xe.CARD_SELECTOR)
print("CARDS_PAGE1", len(cards))
for word in ("πιπλωμ", "Διαθέσιμο", "έπιπλ"):
    print("CARDS_WITH", word, sum(word in c.html for c in cards))
picked = [c.html for c in cards if "πιπλωμ" in c.html or "Διαθέσιμο" in c.html][:3]
picked += [c.html for c in cards if c.html not in picked][: 6 - len(picked)]
doc = "<html><body>\n" + "\n".join(picked) + "\n</body></html>\n"
blob = base64.b64encode(gzip.compress(doc.encode("utf-8"))).decode("ascii")
print("BEGIN_FIXTURE")
for i in range(0, len(blob), 4000):
    print(blob[i : i + 4000])
print("END_FIXTURE")

rows = list(xe.collect_rentals())
have = Counter()
for r in rows:
    for k in ("price", "area_m2", "floor", "year_built", "bedrooms", "neighborhood", "url"):
        have[k] += r.get(k) is not None
    have["furnished"] += r.get("furnished") is not None
    have["available_from"] += r.get("available_from") is not None
print("RENTALS", len(rows), dict(have))
