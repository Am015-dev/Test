"""Collector ABC + shared Playwright plumbing.

Collectors scrape search-results pages first (cheap), then visit detail pages only
for listings that pass a cheap pre-filter, keeping crawl volume low. Raw HTML is
persisted under ``data/raw/<source>/<id>-<date>.html`` so parsers can be re-run
offline and tests can use real fixtures.

Politeness is built in: networkidle waits, randomized 2-5 s delays between detail
pages, one portal at a time, a real User-Agent. Parsers fail soft — a missing
field becomes ``None`` and never crashes the run.
"""

from __future__ import annotations

import logging
import random
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import date
from pathlib import Path

from ..config import REPO_ROOT, Strategy

logger = logging.getLogger(__name__)

RAW_HTML_DIR = REPO_ROOT / "data" / "raw"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)
MIN_DELAY_S = 2.0
MAX_DELAY_S = 5.0
# Retry a search page that returns zero cards (transient anti-bot empties).
MAX_PAGE_ATTEMPTS = 3
RETRY_BACKOFF_S = 4.0


class Collector(ABC):
    """Base class for portal collectors."""

    source: str = "base"
    CARD_SELECTOR: str = ""

    def __init__(self, strategy: Strategy, save_raw: bool = True):
        self.strategy = strategy
        self.save_raw = save_raw

    @abstractmethod
    def search_urls(self, strategy: Strategy) -> list[str]:
        """Build pre-filtered search-results URLs from the strategy."""

    @abstractmethod
    def collect(self) -> Iterator[dict]:
        """Yield raw listing dicts (portal-shaped, pre-normalization)."""

    @abstractmethod
    def parse_card(self, html: str, base_url: str) -> dict:
        """Parse a single result-card's HTML into a raw dict. Must fail soft."""

    # ---- shared helpers ----------------------------------------------------

    def polite_delay(self) -> None:
        time.sleep(random.uniform(MIN_DELAY_S, MAX_DELAY_S))

    def save_raw_html(self, listing_id: str, html: str) -> Path | None:
        if not self.save_raw:
            return None
        out_dir = RAW_HTML_DIR / self.source
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{listing_id}-{date.today().isoformat()}.html"
        try:
            path.write_text(html, encoding="utf-8")
            return path
        except OSError as exc:  # never crash the run over a disk write
            logger.warning("could not save raw html for %s: %s", listing_id, exc)
            return None

    def _collect_with_playwright(self) -> Iterator[dict]:
        """Default Playwright crawl. Imported lazily so tests don't need Playwright."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning("playwright not installed; %s.collect() yields nothing", self.source)
            return

        from ..config import get_settings

        ignore_https = get_settings().scrape_ignore_https_errors
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                locale="el-GR", user_agent=USER_AGENT, ignore_https_errors=ignore_https
            )
            page = context.new_page()
            try:
                for url in self.search_urls(self.strategy):
                    # Anti-bot pages intermittently return zero results to datacenter
                    # IPs. Retry with backoff so a transient empty page doesn't become
                    # "0 listings today" — a real block stays empty after the retries.
                    cards = []
                    for attempt in range(1, MAX_PAGE_ATTEMPTS + 1):
                        try:
                            page.goto(url, wait_until="networkidle", timeout=30_000)
                            self._autoscroll(page)
                        except Exception as exc:
                            logger.warning("failed to load %s (attempt %d): %s", url, attempt, exc)
                            cards = []
                        else:
                            cards = page.query_selector_all(self.CARD_SELECTOR)
                        if cards:
                            break
                        if attempt < MAX_PAGE_ATTEMPTS:
                            time.sleep(RETRY_BACKOFF_S * attempt)
                    logger.info("%s: %d cards on %s", self.source, len(cards), url)
                    for card in cards:
                        try:
                            # outerHTML so the card's own attributes (data-id) are visible.
                            card_html = card.evaluate("el => el.outerHTML")
                            raw = self.parse_card(card_html, base_url=url)
                            if raw:
                                yield raw
                        except Exception as exc:  # fail soft per card
                            logger.warning("%s: card parse error: %s", self.source, exc)
                    self.polite_delay()
            finally:
                context.close()
                browser.close()

    @staticmethod
    def _autoscroll(page, steps: int = 8, pause_ms: int = 400) -> None:
        """Scroll to load lazy results."""
        for _ in range(steps):
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(pause_ms)
