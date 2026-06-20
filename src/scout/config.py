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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    geocoder_user_agent: str = "holargos-scout/1.0 (you@example.com)"
    db_path: str = "data/listings.db"
    # Full SQLAlchemy URL override. Set this to a Postgres DSN to scale beyond the
    # default single-file SQLite (e.g. postgresql+psycopg://user:pass@host/db).
    database_url: str = ""
    osrm_base_url: str = "https://router.project-osrm.org"

    # Set true only behind a TLS-intercepting proxy. Keeps TLS strict by default.
    scrape_ignore_https_errors: bool = False

    # Reliable, scalable data source (recommended for production). When apify_token is
    # set, the Apify-backed collector is used instead of the best-effort direct fetch:
    # Apify runs the maintained xe.gr actor on its cloud with GR residential proxies,
    # so it isn't IP-throttled and scales across areas. ~$3.50 / 1000 listings.
    apify_token: str = ""
    apify_xe_actor: str = "logiover/xe-gr-real-estate-scraper-greece-property-data"

    # Optional alert sinks (disabled when blank).
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    alert_email_to: str = ""

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
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
    neighborhoods: list[str] = Field(default_factory=list)
    price_min: int = 0
    price_max: int = 10_000_000
    area_min_m2: float = 0.0
    # Fallback monthly rent estimate (€/m²/month) used to compute gross yield when a
    # listing has no scraped rent and the neighborhood has no rent comps. Without it
    # the yield signal (the largest score weight) is zero for every listing.
    est_rent_eur_per_m2: float = 11.0


class HardFilters(BaseModel):
    min_floor: int = 1
    max_metro_distance_m: int = 600


class Weights(BaseModel):
    gross_yield: float = 35
    price_vs_area_median: float = 25
    price_drop: float = 20
    is_currently_rented: float = 10
    is_private_seller: float = 10

    def total(self) -> float:
        return (
            self.gross_yield
            + self.price_vs_area_median
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
