"""Deployment readiness self-check ("doctor").

Answers, in one place, "is this deployment wired correctly?" — DB connectivity and
schema, whether it's on shared Postgres or a local SQLite fallback, whether alert
sinks and geocoding are configured, and how many areas the collectors will cover.

Runtime *data* health (has scraping silently broken?) lives in ``health.py``; this
module is the complementary *config/deploy* pre-flight, meant to be run by hand
(``python scripts/doctor.py``) when diagnosing a misbehaving deploy.

Pure and side-effect-free apart from read-only DB access. It NEVER prints secrets —
tokens, passwords, and DSNs are reported only as "configured / not configured".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import func, inspect, select, text

from .config import Settings, Strategy, get_settings, load_strategy
from .db import get_engine, session_scope
from .models import ListingRow

logger = logging.getLogger(__name__)

# Severity ordering so an overall status can be derived from the worst check.
_RANK = {"ok": 0, "warn": 1, "fail": 2}

# Core tables the app cannot function without.
_REQUIRED_TABLES = {
    "listing",
    "price_history",
    "status_history",
    "scrape_job",
    "geocode_cache",
}


@dataclass
class Check:
    name: str
    status: str  # "ok" | "warn" | "fail"
    detail: str


def worst_status(checks: list[Check]) -> str:
    """The most severe status across ``checks`` ("ok" when the list is empty)."""
    return max((c.status for c in checks), key=lambda s: _RANK[s], default="ok")


def _db_backend(settings: Settings) -> str:
    return "postgres" if settings.database_url else "sqlite"


def diagnose(settings: Settings | None = None, strategy: Strategy | None = None) -> list[Check]:
    """Run every readiness check and return the results. Never raises."""
    settings = settings or get_settings()
    strategy = strategy or load_strategy()
    checks: list[Check] = []

    # --- Database connectivity (a hard prerequisite for everything below) ---
    engine = None
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks.append(Check("database", "ok", f"connected ({_db_backend(settings)})"))
    except Exception as exc:
        checks.append(Check("database", "fail", f"cannot connect ({_db_backend(settings)}): {exc}"))
        return checks  # nothing else is meaningful without a DB connection

    # --- Schema present ---
    try:
        tables = set(inspect(engine).get_table_names())
        missing = sorted(_REQUIRED_TABLES - tables)
        if missing:
            checks.append(Check("schema", "fail", f"missing tables {missing} — run init_db()"))
        else:
            checks.append(Check("schema", "ok", "all core tables present"))
    except Exception as exc:
        checks.append(Check("schema", "warn", f"could not inspect schema: {exc}"))

    # --- Backend suitability ---
    if settings.database_url:
        checks.append(Check("db_backend", "ok", "Postgres via DATABASE_URL (multi-worker safe)"))
    else:
        checks.append(
            Check(
                "db_backend",
                "warn",
                "SQLite fallback — fine for a single node; set DATABASE_URL to run "
                "multiple workers against one shared DB",
            )
        )

    # --- Data presence ---
    try:
        with session_scope() as session:
            active = (
                session.scalar(
                    select(func.count())
                    .select_from(ListingRow)
                    .where(ListingRow.status == "active")
                )
                or 0
            )
        if active:
            checks.append(Check("data", "ok", f"{active} active listings"))
        else:
            checks.append(
                Check("data", "warn", "no active listings yet — run the pipeline or wait for cron")
            )
    except Exception as exc:
        checks.append(Check("data", "warn", f"could not count listings: {exc}"))

    # --- Geocoder user agent (Nominatim policy wants a real contact) ---
    if "you@example.com" in settings.geocoder_user_agent:
        checks.append(
            Check("geocoder_ua", "warn", "GEOCODER_USER_AGENT is still the placeholder default")
        )
    else:
        checks.append(Check("geocoder_ua", "ok", "custom user agent set"))

    # --- Alert sinks (secrets reported only as configured / not) ---
    telegram = bool(settings.telegram_bot_token and settings.telegram_chat_id)
    email = bool(settings.smtp_host and settings.alert_email_to)
    if telegram or email:
        active_sinks = [n for n, on in (("telegram", telegram), ("email", email)) if on]
        checks.append(Check("alerts", "ok", f"configured: {', '.join(active_sinks)}"))
    else:
        checks.append(
            Check("alerts", "warn", "no alert sink — daily digest & health alerts won't be sent")
        )

    # --- Collector coverage ---
    areas = strategy.search.all_areas()
    if areas:
        checks.append(Check("areas", "ok", f"{len(areas)} area(s): {', '.join(areas)}"))
    else:
        checks.append(Check("areas", "fail", "no areas configured in strategy.yaml"))

    # --- FlareSolverr (unlocks the WAF-guarded portals) ---
    if settings.flaresolverr_url:
        checks.append(Check("flaresolverr", "ok", "set — Spitogatos/Indomio enabled"))
    else:
        checks.append(
            Check("flaresolverr", "warn", "not set — only XE is collected (WAF portals disabled)")
        )

    return checks


def as_text(checks: list[Check]) -> str:
    """Human-readable report with a leading overall line."""
    icon = {"ok": "✅", "warn": "⚠️ ", "fail": "🚨"}
    overall = worst_status(checks)
    head = f"{icon[overall]} Holargos Scout readiness: {overall.upper()}"
    body = "\n".join(f"  {icon[c.status]} {c.name}: {c.detail}" for c in checks)
    return f"{head}\n{body}"
