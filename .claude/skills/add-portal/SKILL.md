---
name: add-portal
description: Add a brand-new listing source (real-estate portal) to the scraper end-to-end — a new Collector subclass, search URLs, card parser, fixtures, and wiring into default_collectors. Use when expanding beyond XE/Spitogatos/Indomio to another site. For fixing an existing broken collector use repair-collector; for finalizing the already-wired Spitogatos/Indomio use finalize-portal-selectors.
---

# Add a new portal

Collectors emit raw dicts; `normalize.py` maps them to the canonical `Listing`, so a new
portal only needs a collector that yields the raw shape. Everything downstream (enrich,
dedup, score, store, digest) is portal-agnostic.

## Steps

1. **Create `src/scout/collectors/<portal>.py`** subclassing `Collector`
   (`collectors/base.py`). Implement:
   - `source` class attr (a short unique string).
   - `CARD_SELECTOR` + `SEL_*` class constants (selectors for the result card + fields).
   - `search_urls(strategy)` → pre-filtered search URLs from `strategy.search`
     (transaction=buy, price/area bounds, area/geo). Prefer server-side geo filtering.
   - `parse_card(html, base_url)` → the raw dict. Mirror an existing collector; reuse
     `parse_helpers` (`parse_int`, `parse_float`, `parse_floor`, `parse_rent`,
     `parse_private_seller`). Must FAIL SOFT — any missing field becomes None.
   - `collect()` → choose the fetch path:
     - server-rendered HTML reachable over plain HTTP → a `requests.Session` loop like
       `XeCollector` (preferred — no browser).
     - Cloudflare/WAF-guarded → `yield from self._collect_via_flaresolverr(endpoint)` when
       `get_settings().flaresolverr_url` is set, else `self._collect_with_playwright()`
       (copy the Spitogatos dispatch).

2. **Produce the raw dict keys** `normalize` expects: `source`, `source_id` (UNIQUE per
   listing — verify dedup doesn't collapse them), `url`, `title`, `price`, `area_m2`,
   `floor`, `bedrooms`, `year_built`, `neighborhood`, `address`, and the optional
   `is_currently_rented`/`listed_rent`/`is_private_seller`.

3. **Capture a real card** to `tests/fixtures/<portal>_card.html` and add a `parse_card`
   test asserting price/area/source_id/url (mirror the XE test in `tests/test_normalize.py`).

4. **Wire into `collectors/__init__.py: default_collectors`** — add it to the returned
   list (gated on `flaresolverr_url` if it's WAF-blocked, like Spitogatos/Indomio).

5. **Verify** the collector yields parsed raws on a live page; run a full pipeline pass and
   confirm the new source's listings are stored, scored, and appear in the digest coverage.

6. Run `holargos-verify`, commit, merge.

## Notes
- Keep crawl volume low and polite (the base provides delays + retry-on-empty).
- If the portal needs a detail-page visit for some fields, gate it behind a cheap
  pre-filter so you don't fetch every listing's detail page.
- Geo filtering server-side (like XE's `geo_place_id`) keeps results scoped; otherwise the
  metro-distance hard filter does the narrowing.
