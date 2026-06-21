---
name: repair-collector
description: Diagnose and fix a portal collector that has stopped working — returns 0 cards, or parses wrong/empty fields — after the site changed its markup or started rate-limiting. Use when a scrape's stored/deduped count drops to 0 unexpectedly, the healthcheck flags an area as zero, or fields like price/area come back None. For XE this is the #1 maintenance task. For first-time WAF-portal setup use finalize-portal-selectors instead.
---

# Repair a broken collector

Portals redesign their markup periodically; the parser then silently returns nothing or
garbage (the pipeline is fail-soft, so it won't crash — it just goes empty). This skill
distinguishes the two root causes and fixes a markup change.

## Step 1 — Is it a block or a markup change?

Fetch one search page raw and count cards vs. check the bytes:

```bash
cd /root/holargos && . .venv/bin/activate && SCRAPE_IGNORE_HTTPS_ERRORS=true python -c "
from scout.collectors.xe import XeCollector, BROWSER_HEADERS
import requests, urllib3; urllib3.disable_warnings()
from selectolax.parser import HTMLParser
c = XeCollector.__new__(XeCollector)
from scout.config import load_strategy
c.strategy = load_strategy(); c.save_raw=False
s = requests.Session(); s.headers.update(BROWSER_HEADERS); s.verify=False
s.get('https://www.xe.gr/property/', timeout=20)
url = c.search_urls(load_strategy())[0]
html = s.get(url, timeout=20).text
print('bytes:', len(html), '| cards:', len(HTMLParser(html).css(XeCollector.CARD_SELECTOR)))
open('/tmp/page.html','w').write(html)
"
```

- **Small body / 403 / 0 cards repeatedly** → it's an IP **block**, not markup. The retry
  path already handles transient ones; a persistent block needs a different IP → see
  `triage-scraper-health` (add a worker on another Oracle instance). Do NOT churn selectors.
- **Large body but 0 cards**, or cards found but fields None → it's a **markup change**.
  Continue.

## Step 2 — Re-derive the selectors from the live page

Inspect the real card and locate each field. Prefer **class-based** selectors that exist
in the server-rendered HTML (XE) — `data-testid` only appears after JS hydration and is
absent from `requests` output (this is the trap that the class-based switch fixed).

```bash
python -c "
from selectolax.parser import HTMLParser
t = HTMLParser(open('/tmp/page.html').read())
card = t.css('div.common-ad-body')[0]   # adjust to the real card container
print(card.html[:1500])
"
```

Update the `CARD_SELECTOR` and `SEL_*` / `ATTR_ID` class constants in the collector
(`src/scout/collectors/<portal>.py`). Keep them as constants so the fix stays one-file.

## Step 3 — Refresh the fixture and test

Save one real card to `tests/fixtures/<portal>_card.html`, update the corresponding
`parse_card` test in `tests/test_normalize.py` to assert price/area/source_id/url, and run
it. The fixture must be a real captured card, never hand-written.

## Step 4 — Verify live + ship

Run `XeCollector(load_strategy()).collect()` and confirm cards parse with price+area and
clean canonical URLs. Then run the `holargos-verify` gate, commit, merge.

## Notes
- The id regex (`_ID_RE_D`/`_ID_RE_U`) must keep producing a UNIQUE id per listing — a
  non-unique slug collapses listings under dedup. Verify distinct `source_id`s.
- Don't widen `SEL_LINK` so far it grabs a non-canonical anchor (agent/image link).
