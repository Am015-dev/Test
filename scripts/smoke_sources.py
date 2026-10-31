"""Smoke-test collectors for ONE area into whatever DB ``DATABASE_URL`` names (use a throwaway
SQLite file), then print what was parsed, what was stored, field fill rates per source, and
how many listings have a twin on another portal. Diagnostic; run it from a GitHub runner:

    DATABASE_URL=sqlite:////tmp/smoke.db SOURCES=xe,goldenhome \\
        python scripts/smoke_sources.py --area Cholargos
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import select  # noqa: E402

from scout import market_intel as mi  # noqa: E402
from scout.collectors import default_collectors  # noqa: E402
from scout.config import load_strategy  # noqa: E402
from scout.db import init_db, session_scope  # noqa: E402
from scout.models import ListingRow  # noqa: E402
from scout.normalize import normalize  # noqa: E402
from scout.pipeline import run  # noqa: E402

FIELDS = ("price", "area_m2", "floor", "year_built", "bedrooms", "neighborhood", "photo_count")


class _Recorder:
    """Wraps a collector so the raw dicts it yields are counted before the pipeline runs."""

    def __init__(self, inner):
        self.inner, self.source, self.raws = inner, inner.source, []

    def collect(self):
        for raw in self.inner.collect():
            self.raws.append(raw)
            yield raw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", default="Cholargos")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    init_db()
    strategy = load_strategy().model_copy(deep=True)
    strategy.search.municipality = args.area
    recorders = [_Recorder(c) for c in default_collectors(strategy)]
    summary = run(strategy=strategy, collectors=recorders, use_network=False, area=args.area)
    print(f"\nRUN SUMMARY {summary}")

    for rec in recorders:
        ok = [r for r in rec.raws if normalize(r) is not None]
        print(f"SOURCE {rec.source}: raw={len(rec.raws)} normalized={len(ok)}")

    with session_scope() as s:
        rows = s.execute(select(ListingRow).where(ListingRow.search_area == args.area)).scalars()
        dicts = [
            {
                "id": r.id,
                "source": r.source,
                "title": r.title,
                "price": r.price,
                "area_m2": r.area_m2,
                "price_per_m2": r.price_per_m2,
                "floor": r.floor,
                "year_built": r.year_built,
                "bedrooms": r.bedrooms,
                "neighborhood": r.neighborhood,
                "photo_count": r.photo_count,
                "is_unfinished": r.is_unfinished,
            }
            for r in rows
        ]
    by_source = Counter(d["source"] for d in dicts)
    for src, n in sorted(by_source.items()):
        mine = [d for d in dicts if d["source"] == src]
        fill = " ".join(f"{f}={sum(d[f] is not None for d in mine)}" for f in FIELDS)
        unfinished = sum(bool(d["is_unfinished"]) for d in mine)
        print(f"STORED {src}: {n} listings · {fill} · unfinished={unfinished}")

    intel = mi.build(dicts)
    cross = [
        (d["source"], d["id"], [(t["source"], t["id"]) for t in intel.twins(d)])
        for d in dicts
        if any(t["source"] != d["source"] for t in intel.twins(d))
    ]
    print(f"CROSS-PORTAL TWINS: {len(cross)} listings have a twin on another portal")
    for src, i, twins in cross[:10]:
        print(f"  {src}:{i} ~ {twins}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
