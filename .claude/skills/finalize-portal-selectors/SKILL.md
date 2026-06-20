---
name: finalize-portal-selectors
description: Finalize the Spitogatos/Indomio (WAF-blocked portals) within-card CSS selectors against a live page captured via FlareSolverr. Use when adding/fixing coverage for those portals, when their scrapes return 0 cards or wrong fields, or when picking up backlog item "finalize portal selectors". Not for XE (that source is already live).
---

# Finalize Spitogatos / Indomio selectors

The FlareSolverr fetch + parse wiring is done (`base._collect_via_flaresolverr`,
`default_collectors` adds them when `FLARESOLVERR_URL` is set). What's NOT verified are
the **within-card selectors** in `src/scout/collectors/spitogatos.py` and `indomio.py`
(`CARD_SELECTOR`, `SEL_*`, `ATTR_ID`) — they're placeholders. This skill finalizes them
against a real captured page.

## Steps

1. **Bring up FlareSolverr** (free, Dockerized):
   ```bash
   cd /root/holargos && docker compose --profile flaresolverr up -d
   ```
   If Docker isn't available in this environment, you can't capture live markup — record
   that and stop; this task needs a reachable FlareSolverr.

2. **Capture a live search page** for one portal. Build a search URL with the collector's
   own `search_urls()` and fetch it through FlareSolverr, saving the HTML:
   ```bash
   . .venv/bin/activate && python -c "
   from scout.collectors.spitogatos import SpitogatosCollector
   from scout.config import load_strategy
   c = SpitogatosCollector(load_strategy())
   url = c.search_urls(load_strategy())[0]
   html = c._fetch_via_flaresolverr(url, 'http://localhost:8191/v1')
   open('tests/fixtures/spitogatos_page.html','w').write(html or '')
   print('captured', len(html or ''), 'bytes from', url)
   "
   ```

3. **Inspect the real card markup**. Find the repeating result-card element and the
   fields inside it (id, link, title, price, area, floor, neighborhood, description).
   Prefer **stable class names** over `data-testid` only if classes are more reliable;
   FlareSolverr returns hydrated DOM so `data-testid` is usually present.
   ```bash
   python -c "
   from selectolax.parser import HTMLParser
   t = HTMLParser(open('tests/fixtures/spitogatos_page.html').read())
   cards = t.css(\"[data-testid='property-card']\")  # adjust to the real card selector
   print('cards:', len(cards));  print((cards[0].html[:1200] if cards else 'NO CARDS'))
   "
   ```

4. **Update the selector constants** in the collector to match (`CARD_SELECTOR`, `SEL_LINK`,
   `SEL_TITLE`, `SEL_PRICE`, `SEL_AREA`, `SEL_FLOOR`, `SEL_NEIGHBORHOOD`, `SEL_DESC`,
   `ATTR_ID`). Keep them as class constants (a redesign stays a one-file fix).

5. **Save a single real card as a fixture** (`tests/fixtures/spitogatos_card.html`) and
   add a `parse_card` test mirroring `tests/test_normalize.py`'s XE card test: assert
   price/area/source_id/url parse correctly. Real captured card, not hand-written.

6. **Verify** `parse_card` yields the right fields on the real card; confirm
   `_collect_via_flaresolverr` returns multiple parsed raws on the page.

7. Repeat for Indomio.

8. Run the verification gate (see `holargos-verify`), commit, merge to `main`.

## Guardrails
- Don't hand-fabricate card HTML and call it "verified" — capture the real page.
- These portals are bot-guarded; if FlareSolverr returns 0 cards, retry (the path already
  retries with backoff) — a persistent 0 means the search URL or card selector is wrong.
- XE is unaffected; never route XE through FlareSolverr.
