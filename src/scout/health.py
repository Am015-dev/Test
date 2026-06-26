"""Healthcheck — detect when scraping has silently broken.

A scraper that returns nothing doesn't crash; it just stops refreshing data, and the
dashboard quietly goes stale. This inspects the DB and the recent scrape-job outcomes
and reports problems so they can be alerted on (see ``scripts/healthcheck.py``):

- data staleness: the newest listing hasn't been refreshed in ``health_stale_hours``;
- total block: every scrape job in the last 24h returned 0 listings (all IPs blocked);
- partial trouble: some areas returned 0, or some jobs failed;
- empty database.

Results are also persisted to the ``health_report`` table via ``persist_health_report``
so the agent can read recent state across sessions via the postgres MCP.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select

from .config import get_settings, load_strategy
from .db import session_scope
from .models import HealthReportRow, ListingRow, ScrapeJobRow

logger = logging.getLogger(__name__)

# Severity ordering so we can escalate as checks find problems.
_RANK = {"ok": 0, "warn": 1, "error": 2}


@dataclass
class HealthReport:
    status: str = "ok"  # ok | warn | error
    issues: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def _escalate(self, level: str, issue: str) -> None:
        self.issues.append(issue)
        if _RANK[level] > _RANK[self.status]:
            self.status = level

    def as_text(self) -> str:
        head = f"{'✅' if self.ok else '🚨'} Holargos Scout health: {self.status.upper()}"
        body = "\n".join(f"  • {i}" for i in self.issues) or "  • all checks passed"
        metrics = "\n".join(f"  {k}: {v}" for k, v in self.metrics.items())
        return f"{head}\n{body}\n\nMetrics:\n{metrics}"


def check_health(now: datetime | None = None) -> HealthReport:
    """Inspect the DB + recent jobs and return a graded health report."""
    now = now or datetime.utcnow()
    settings = get_settings()
    report = HealthReport()

    with session_scope() as session:
        active = (
            session.scalar(
                select(func.count()).select_from(ListingRow).where(ListingRow.status == "active")
            )
            or 0
        )
        latest_seen = session.scalar(
            select(func.max(ListingRow.last_seen)).where(ListingRow.status == "active")
        )
        since = now - timedelta(hours=24)
        # Materialize plain tuples inside the session (rows detach once it closes).
        recent_jobs = session.execute(
            select(ScrapeJobRow.area, ScrapeJobRow.status, ScrapeJobRow.listings_found).where(
                ScrapeJobRow.updated_at >= since
            )
        ).all()

    done = [j for j in recent_jobs if j.status == "done"]
    failed = [j for j in recent_jobs if j.status == "failed"]
    with_data = {j.area for j in done if (j.listings_found or 0) > 0}
    # An area that returned data in *any* job this window is healthy, even if a later
    # transient run returned zero — so don't also list it as a zero/partial-trouble area.
    areas_with_data = sorted(with_data)
    areas_zero = sorted({j.area for j in done if not (j.listings_found or 0)} - with_data)
    hours_since = round((now - latest_seen).total_seconds() / 3600, 1) if latest_seen else None

    report.metrics = {
        "active_listings": active,
        "hours_since_refresh": hours_since,
        "recent_jobs_done": len(done),
        "recent_jobs_failed": len(failed),
        "areas_with_data": areas_with_data,
        "areas_returned_zero": areas_zero,
        "configured_areas": load_strategy().search.all_areas(),
    }

    # --- checks -------------------------------------------------------------
    if active == 0:
        report._escalate("error", "Database has no active listings.")
    if latest_seen is None:
        report._escalate("error", "No listing has ever been recorded.")
    elif hours_since is not None and hours_since > settings.health_stale_hours:
        report._escalate(
            "error",
            f"Data is stale: newest listing last refreshed {hours_since:.0f}h ago "
            f"(threshold {settings.health_stale_hours}h) — scraping is likely broken.",
        )

    if recent_jobs and not areas_with_data:
        report._escalate(
            "error",
            "Every scrape job in the last 24h returned 0 listings — likely IP-blocked "
            "on all areas. Add a worker on another Oracle instance / IP.",
        )
    elif areas_zero:
        report._escalate("warn", f"Some areas returned 0 listings: {areas_zero}.")

    if failed:
        report._escalate(
            "warn",
            f"{len(failed)} scrape job(s) failed in the last 24h: "
            f"{sorted({j.area for j in failed})}.",
        )

    logger.info("health: %s — %s", report.status, report.metrics)
    return report


def persist_health_report(
    report: HealthReport, checked_at: datetime | None = None
) -> None:
    """Write the report to health_report table for cross-session agent observability.

    Failures are logged but not re-raised — a DB write error must never suppress
    the alert that ``scripts/healthcheck.py`` is about to send.
    """
    now = checked_at or datetime.utcnow()
    try:
        with session_scope() as session:
            session.add(
                HealthReportRow(
                    checked_at=now,
                    status=report.status,
                    issues=json.dumps(report.issues),
                    metrics=json.dumps(report.metrics, default=str),
                )
            )
    except Exception:
        logger.exception("health: failed to persist report to DB")
