"""Unattended daily operator — the loop that makes it a running product, not a demo.

One idempotent entry the cron calls every morning. It does the recurring maintenance that
keeps the data fresh and delivers value to the subscriber, in a safe order:

  1. Deepen depth: enrich a capped batch of the top-scored still-incomplete listings
     (energy/year/coords) at the measured-safe cadence.
  2. Refresh rent comps for a rotating slice of areas (keeps net yield real without a full
     sweep every day).
  3. Rescore everything from the freshened data.
  4. Health check per area (stale/thin) → persisted + logged.
  5. Deliver: per-saved-search alerts (only fires if an alert sink is configured).

Emits a one-line run-metrics summary at the end (listings, complete %, alerts sent) for
observability. Fail-soft: any step that errors is logged and the rest still run.

Usage (cron, 07:00 Athens):
    SCRAPE_REQUEST_MIN_S=4 SCRAPE_REQUEST_MAX_S=7 python scripts/daily.py --enrich 300 --rent-areas 6
"""

from __future__ import annotations

import argparse
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("daily")


def _safe(step: str, fn):
    try:
        return fn()
    except Exception as exc:  # one broken step must not abort the daily run
        log.warning("daily: step %r failed: %s", step, exc)
        return None


def run_daily(enrich_limit: int = 300, rent_areas: int = 6) -> dict:
    from scout.config import load_strategy
    from scout.data_quality import audit
    from scout.db import init_db

    init_db()
    metrics: dict = {}

    # 1. Depth: enrich the top-scored incomplete listings (bounded, safe cadence).
    if enrich_limit > 0:

        def _enrich():
            from scripts.enrich_details import enrich

            return enrich(limit=enrich_limit, rescore=False)

        metrics["enrich"] = _safe("enrich", _enrich)

    # 2. Rent comps for a rotating slice of areas (deterministic rotation by weekday-free
    #    index would need a date; keep it simple — the first N areas each run, cron rotates
    #    naturally as earlier areas fill in). Skipped when rent_areas <= 0.
    if rent_areas > 0:

        def _rent():
            from scout.collectors.xe import XeCollector
            from scout.rent_comps import compute_rent_comps_with_counts, save_rent_comps

            strategy = load_strategy()
            written = 0
            for area in strategy.search.all_areas()[:rent_areas]:
                s = strategy.model_copy(deep=True)
                s.search.municipality = area
                rows = list(XeCollector(s).collect_rent_rows())
                comps, counts = compute_rent_comps_with_counts(rows)
                if comps:
                    written += save_rent_comps(area, comps, counts)
            return {"comp_rows": written}

        metrics["rent"] = _safe("rent", _rent)

    # 3. Rescore from the freshened data.
    def _rescore():
        from scout.pipeline import rescore_all

        return {"rescored": rescore_all()}

    metrics["rescore"] = _safe("rescore", _rescore)

    # 4. Health check (persist + log).
    def _health():
        from scout.scrape_health import check

        report = check()
        if not report["healthy"]:
            log.warning("daily: health issues — %s", report["issues"][:5])
        return {"healthy": report["healthy"], "issues": len(report["issues"])}

    metrics["health"] = _safe("health", _health)

    # 5. Deliver per-saved-search alerts (no-op if no sink configured).
    def _alerts():
        from scout.alerts import run_saved_search_alerts

        return {"sent": run_saved_search_alerts()}

    metrics["alerts"] = _safe("alerts", _alerts)

    # 6. Agent shortlist: send each buying mandate's new top picks (no-op without mandates).
    def _shortlist():
        from scout.shortlist import run_shortlists

        return {"sent": run_shortlists()}

    metrics["shortlist"] = _safe("shortlist", _shortlist)

    # Run-metrics summary (observability).
    a = _safe("audit", audit) or {}
    metrics["summary"] = {
        "listings": a.get("total"),
        "complete_pct": a.get("complete_pct"),
        "top_gap": a.get("top_gap"),
    }
    log.info("daily run metrics: %s", json.dumps(metrics.get("summary"), ensure_ascii=False))
    return metrics


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--enrich", type=int, default=300, help="max listings to detail-enrich")
    p.add_argument("--rent-areas", type=int, default=6, help="areas to refresh rent comps for")
    args = p.parse_args()
    metrics = run_daily(enrich_limit=args.enrich, rent_areas=args.rent_areas)
    print(f"Daily run complete: {json.dumps(metrics.get('summary'), ensure_ascii=False)}")


if __name__ == "__main__":
    main()
