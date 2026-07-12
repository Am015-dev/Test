"""Settings (env) and strategy (YAML) loading.

Two distinct config sources:
- ``Settings``: operational/secret config from ``.env`` / environment.
- ``Strategy``: the investor's rules & weights from ``strategy.yaml``. Hot-editable.
"""

from __future__ import annotations

import functools
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = three parents up from this file (src/scout/config.py).
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STRATEGY_PATH = REPO_ROOT / "strategy.yaml"


class Settings(BaseSettings):
    """Operational config, sourced from environment / ``.env``."""

    # Anchor .env to the repo root (like DEFAULT_STRATEGY_PATH), NOT the process CWD:
    # a bare ".env" resolves relative to wherever the process was started, so a cron
    # entry or worker launched from another directory would silently miss DATABASE_URL
    # and fall back to a private local SQLite, breaking the shared worker queue.
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    geocoder_user_agent: str = "holargos-scout/1.0 (you@example.com)"
    db_path: str = "data/listings.db"
    # Full SQLAlchemy URL override. Set this to a Postgres DSN to scale beyond the
    # default single-file SQLite (e.g. postgresql+psycopg://user:pass@host/db).
    database_url: str = ""
    osrm_base_url: str = "https://router.project-osrm.org"

    # Set true only behind a TLS-intercepting proxy. Keeps TLS strict by default.
    scrape_ignore_https_errors: bool = False

    # Polite scraping controls (tuned so a low-frequency daily run stays under XE's
    # per-IP rate limit). Spacing is randomized between min/max; empty/blocked pages
    # are retried with growing backoff; fetched pages are cached for the TTL so
    # re-runs don't re-hit the portal.
    scrape_request_min_s: float = 2.0
    scrape_request_max_s: float = 6.0
    scrape_max_retries: int = 4
    scrape_retry_backoff_s: float = 8.0
    scrape_cache_ttl_minutes: int = 360
    # How many result PAGES to walk per area (XE returns ~36 per page; `&page=N`
    # advances). Deeper collection = more inventory; the crawl stops early when a page
    # returns no new listings, so a small area never wastes requests.
    scrape_max_pages: int = 4

    # Fetch each listing's detail page for the rich investment signals the search cards
    # lack (year built, energy class, bedrooms, full description → rent/rented/private).
    # This is the difference between "cheap old flats with a made-up yield" and real
    # analysis. It costs one extra request per listing (cached, throttled); cap it per
    # area to bound a single-node daily run (0 = no cap — best on the worker queue).
    scrape_detail_pages: bool = True
    scrape_detail_max_per_area: int = 0

    # Healthcheck: alert when the newest listing hasn't been refreshed in this many
    # hours (scraping has silently broken — e.g. every area is IP-blocked).
    health_stale_hours: int = 36

    # Self-hosted FlareSolverr endpoint (free Cloudflare/WAF bypass). When set, the
    # WAF-blocked portals (Spitogatos, Indomio) are scraped through it and added to
    # the default collectors. e.g. http://flaresolverr:8191/v1
    flaresolverr_url: str = ""

    # Optional alert sinks (disabled when blank).
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    alert_email_to: str = ""

    # Daily-digest "hot deal" thresholds. A new listing clearing EITHER bar is
    # highlighted at the top of the digest. Tunable per investor without code.
    digest_hot_min_score: float = 55.0
    digest_hot_min_net_yield: float = 0.04  # 4% net yield after costs

    @property
    def db_url(self) -> str:
        if self.database_url:
            # Normalize the bare postgresql:// scheme (as Railway provides it) to the
            # psycopg3 driver prefix SQLAlchemy 2.0 requires.
            url = self.database_url
            if url.startswith("postgres://") or url.startswith("postgresql://"):
                url = "postgresql+psycopg://" + url.split("://", 1)[1]
            return url
        path = Path(self.db_path)
        if not path.is_absolute():
            path = REPO_ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path}"


# ---- Strategy models (mirror strategy.yaml) -------------------------------


class SearchConfig(BaseModel):
    # Municipality/locality used for server-side geo filtering on portals that
    # support it (XE resolves it to a geo_place_id). The neighborhoods below are
    # sub-areas of this municipality, used for display and per-area scoring.
    municipality: str = "Cholargos"
    # Extra municipalities to also cover (each becomes its own scrape job for the
    # worker queue). Empty = just ``municipality``. All areas share the scoring
    # thesis below, so keep them within the same metro corridor.
    areas: list[str] = Field(default_factory=list)
    neighborhoods: list[str] = Field(default_factory=list)
    price_min: int = 0
    price_max: int = 10_000_000
    area_min_m2: float = 0.0
    # Fallback monthly rent estimate (€/m²/month) used to compute gross yield when a
    # listing has no scraped rent and the neighborhood has no rent comps. Without it
    # the yield signal (the largest score weight) is zero for every listing.
    est_rent_eur_per_m2: float = 11.0

    def all_areas(self) -> list[str]:
        """The municipality plus any extra areas, de-duplicated, order preserved."""
        seen: dict[str, None] = {}
        for a in [self.municipality, *self.areas]:
            if a:
                seen.setdefault(a, None)
        return list(seen)


class HardFilters(BaseModel):
    min_floor: int = 1
    max_metro_distance_m: int = 600


class Weights(BaseModel):
    # Quality-first: a buy-to-let investor wants a good ASSET at a fair price, not the
    # cheapest flat. Newness + energy (asset quality) together outweigh undervaluation, so
    # an efficient, well-built property near metro ranks above an old energy-H flat that
    # merely looks "cheap for its (poor) attributes". On top of these weights, the score
    # is further scaled down for energy-liability stock (see energy_liability_floor).
    newness: float = 20  # build/renovation year — new stock rents better, costs less to hold
    gross_yield: float = 22  # realistic rental income (from real rent comps)
    energy_class: float = 18  # A/B rent higher and are future-proof vs EU efficiency rules
    undervaluation: float = 16  # priced below hedonic fair value (secondary to quality now)
    price_drop: float = 8
    is_currently_rented: float = 8
    is_private_seller: float = 8

    def total(self) -> float:
        return (
            self.undervaluation
            + self.gross_yield
            + self.newness
            + self.energy_class
            + self.price_drop
            + self.is_currently_rented
            + self.is_private_seller
        )


class OpportunityFlag(BaseModel):
    price_per_m2_below_median_pct: float = 0.85


class ScoringReference(BaseModel):
    yield_floor: float = 0.02
    yield_ceiling: float = 0.08
    max_price_drop_pct: float = 0.20
    # Newness normalization: a build/renovation year at/below the floor scores 0, at/above
    # the ceiling scores 1 (linear between). Unknown year is treated as neutral-low.
    build_year_floor: int = 1980
    build_year_ceiling: int = 2015
    # Undervaluation normalization: a listing priced this fraction below its hedonic
    # fair value scores a full 1.0 on the undervaluation signal (linear from 0). 0.20 =
    # "20% under fair value is a top-tier bargain".
    target_undervaluation: float = 0.20
    # Energy-liability demotion: the multiplier applied to the WORST energy class (G/Η).
    # The best class keeps 1.0; classes scale linearly between. 0.55 means a bottom-class
    # energy-H flat loses ~45% of its score — reflecting the EU-EPBD renovation liability.
    energy_liability_floor: float = 0.55


class Strategy(BaseModel):
    search: SearchConfig = Field(default_factory=SearchConfig)
    hard_filters: HardFilters = Field(default_factory=HardFilters)
    weights: Weights = Field(default_factory=Weights)
    opportunity_flag: OpportunityFlag = Field(default_factory=OpportunityFlag)
    scoring_reference: ScoringReference = Field(default_factory=ScoringReference)


def load_strategy(path: str | Path | None = None) -> Strategy:
    """Load and validate ``strategy.yaml`` (or defaults if absent)."""
    p = Path(path) if path else DEFAULT_STRATEGY_PATH
    if not p.exists():
        return Strategy()
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return Strategy.model_validate(data)


def save_strategy(strategy: Strategy, path: str | Path | None = None) -> None:
    """Persist a Strategy back to YAML (used by the UI Strategy editor)."""
    p = Path(path) if path else DEFAULT_STRATEGY_PATH
    p.write_text(
        yaml.safe_dump(strategy.model_dump(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
