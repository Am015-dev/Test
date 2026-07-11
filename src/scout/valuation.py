"""Hedonic valuation model — the core of identifying a genuinely good case.

The naive "€/m² below the neighbourhood median" signal can't tell a *mispriced*
property from an *inferior* one: a cheap 1970s ground-floor flat is below median
because it deserves to be, not because it's a bargain. This fits a small hedonic
regression — ``log(price) ~ log(area) + floor + age + energy + bedrooms + metro +
area`` — over the current batch, predicts each property's **fair price given its own
attributes**, and reports the gap. A property priced well *below* its predicted fair
value (after accounting for how old/small/low/inefficient it is) is the real
opportunity; one *above* it is overpriced.

Pure NumPy (ordinary least squares via ``lstsq``); no DB, no network, no sklearn.
Fails soft: too few samples → ``None`` → callers fall back to the naive signal.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from .models import Listing
from .scoring import energy_class_score

# Below this many usable comps a fitted model is noise; fall back to the naive signal.
_MIN_SAMPLES = 25
# Clamp the reported gap so one wild prediction can't dominate the score.
_MAX_ABS_GAP = 0.6


def _usable(lst: Listing) -> bool:
    return bool(lst.price and lst.price > 0 and lst.area_m2 and lst.area_m2 > 0)


@dataclass
class ValuationModel:
    beta: np.ndarray | None
    medians: dict
    areas: list[str]
    ref_year: int
    r2: float = field(default=0.0)

    def _features(self, lst: Listing) -> np.ndarray | None:
        if not _usable(lst):
            return None
        m = self.medians
        floor = lst.floor if lst.floor is not None else m["floor"]
        age = (self.ref_year - lst.year_built) if lst.year_built else m["age"]
        energy = energy_class_score(lst.energy_class) if lst.energy_class else m["energy"]
        beds = lst.bedrooms if lst.bedrooms else m["beds"]
        metro = lst.metro_distance_m if lst.metro_distance_m is not None else m["metro"]
        row = [1.0, math.log(lst.area_m2), floor, age, energy, beds, metro / 1000.0]
        # Area fixed effects (one-hot, first area is the reference level).
        row.extend(1.0 if lst.search_area == a else 0.0 for a in self.areas[1:])
        return np.array(row, dtype=float)

    def predict_price(self, lst: Listing) -> float | None:
        row = self._features(lst)
        if row is None or self.beta is None:
            return None
        return float(math.exp(float(row @ self.beta)))

    def value_gap(self, lst: Listing) -> float | None:
        """(fair − actual) / fair, clamped. Positive = undervalued (a good case)."""
        predicted = self.predict_price(lst)
        if not predicted or not lst.price:
            return None
        gap = (predicted - lst.price) / predicted
        return max(-_MAX_ABS_GAP, min(_MAX_ABS_GAP, gap))


def apply_valuations(listings: list[Listing], model: ValuationModel | None) -> None:
    """Annotate each listing in place with ``predicted_price`` and ``value_gap_pct``.

    No-op when the model is ``None`` (too few comps to fit) — listings keep their default
    ``None`` valuation fields and scoring falls back to the naive €/m² signal."""
    if model is None:
        return
    for lst in listings:
        predicted = model.predict_price(lst)
        lst.predicted_price = int(round(predicted)) if predicted else None
        lst.value_gap_pct = model.value_gap(lst)


def fit_valuation_model(listings: list[Listing]) -> ValuationModel | None:
    rows = [lst for lst in listings if _usable(lst)]
    if len(rows) < _MIN_SAMPLES:
        return None
    ref_year = datetime.utcnow().year

    def _med(values: list[float], default: float) -> float:
        return statistics.median(values) if values else default

    medians = {
        "floor": _med([r.floor for r in rows if r.floor is not None], 2.0),
        "age": _med([ref_year - r.year_built for r in rows if r.year_built], 40.0),
        "energy": _med([energy_class_score(r.energy_class) for r in rows if r.energy_class], 0.3),
        "beds": _med([r.bedrooms for r in rows if r.bedrooms], 2.0),
        "metro": _med([r.metro_distance_m for r in rows if r.metro_distance_m is not None], 600.0),
    }
    areas = sorted({r.search_area for r in rows if r.search_area})
    model = ValuationModel(beta=None, medians=medians, areas=areas, ref_year=ref_year)

    feats, targets = [], []
    for r in rows:
        row = model._features(r)
        if row is not None:
            feats.append(row)
            targets.append(math.log(r.price))
    x = np.array(feats)
    y = np.array(targets)
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    model.beta = beta

    # In-sample R² — a rough confidence read (surfaced, not gated on).
    pred = x @ beta
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    model.r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return model
