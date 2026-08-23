"""Unit tests for the score-explanation module — pure, no DB, no network.

These pin the honesty contract: real undervaluation + a real-rent yield read as
positive rows; a missing energy/build year reads as an ``unknown`` (not-scored) row,
never a fabricated positive; and an imputed rent (``rent_estimated=True``) is never
counted as a positive yield signal — exactly the renormalize-over-known logic in
``scoring.py``.
"""

from __future__ import annotations

from scout.score_explain import explain_score, summarize_score


def _effect(rows: list[dict], label_substr: str) -> str:
    for r in rows:
        if label_substr.lower() in r["label"].lower():
            return r["effect"]
    raise AssertionError(f"no row matching {label_substr!r} in {[r['label'] for r in rows]}")


def _good_listing() -> dict:
    return {
        "score": 78.0,
        "value_gap_pct": 0.12,  # priced 12% below the hedonic model
        "net_yield": 0.048,  # 4.8% net
        "gross_yield": 0.061,
        "rent_estimated": False,  # a REAL rent comp
        "year_built": 2012,
        "renovated_year": None,
        "energy_class": "B",
        "metro_distance_m": 300,
        "location_precision": "exact",
    }


def test_empty_dict_returns_empty_list():
    assert explain_score({}) == []
    assert summarize_score({}) == "No signals available"


def test_row_shape_and_effect_domain():
    rows = explain_score(_good_listing())
    assert rows, "expected some rows"
    for r in rows:
        assert set(r) == {"label", "effect", "detail"}
        assert r["effect"] in {"positive", "negative", "unknown"}
        assert isinstance(r["label"], str) and r["label"]
        assert isinstance(r["detail"], str) and r["detail"]


def test_real_undervaluation_and_yield_are_positive():
    rows = explain_score(_good_listing())
    assert _effect(rows, "below area model") == "positive"
    assert _effect(rows, "net yield") == "positive"
    # And the numbers are rendered honestly.
    labels = " | ".join(r["label"] for r in rows)
    assert "12% below area model" in labels
    assert "4.8% net yield" in labels


def test_yield_row_prefers_area_percentile_over_flat_floor():
    # 4.8% clears the flat net_yield_floor (0.015) → positive under the old flat-only logic.
    # With yield_percentile present (annotate_relative_value ran on the pool) and below 0.5,
    # it's actually the WORST yield among comparable local listings — the explanation must
    # say so, or it would contradict what the area-relative score signal now computes on.
    d = _good_listing()
    d["yield_percentile"] = 0.2
    rows = explain_score(d)
    assert _effect(rows, "net yield") == "negative"
    details = " | ".join(r["detail"] for r in rows)
    assert "better than 20% of comparable listings" in details

    # And the reverse: below the flat floor but locally the best available → positive.
    d2 = _good_listing()
    d2["net_yield"] = 0.01  # below flat net_yield_floor (0.015)
    d2["yield_percentile"] = 0.9
    assert _effect(explain_score(d2), "net yield") == "positive"


def test_good_energy_and_modern_build_are_positive():
    rows = explain_score(_good_listing())
    assert _effect(rows, "Energy class B") == "positive"
    assert _effect(rows, "Modern stock") == "positive"
    assert _effect(rows, "to metro") == "positive"


def test_missing_energy_and_year_are_unknown_not_negative():
    d = _good_listing()
    d["energy_class"] = None
    d["year_built"] = None
    d["renovated_year"] = None
    rows = explain_score(d)
    assert _effect(rows, "Energy class not reported") == "unknown"
    assert _effect(rows, "Build year not reported") == "unknown"
    # An unknown signal must be flagged as not-scored, never dressed up as a positive.
    for label in ("Energy class not reported", "Build year not reported"):
        row = next(r for r in rows if r["label"] == label)
        assert "not scored" in row["detail"].lower()


def test_poor_energy_class_is_negative():
    d = _good_listing()
    d["energy_class"] = "E"
    assert _effect(explain_score(d), "Energy class E") == "negative"


def test_estimated_rent_is_not_a_positive_yield():
    d = _good_listing()
    d["rent_estimated"] = True  # imputed rent — not a real comp
    rows = explain_score(d)
    # The yield row must be unknown, and NO row may claim a yield as positive.
    assert _effect(rows, "estimated rent") == "unknown"
    for r in rows:
        if "yield" in r["label"].lower():
            assert r["effect"] != "positive"


def test_missing_rent_key_defaults_to_estimated():
    d = _good_listing()
    del d["rent_estimated"]
    d.pop("net_yield")
    d.pop("gross_yield")
    rows = explain_score(d)
    assert _effect(rows, "yield") == "unknown"


def test_centroid_location_metro_is_unknown():
    d = _good_listing()
    d["location_precision"] = "area"  # not a per-listing point
    rows = explain_score(d)
    assert _effect(rows, "Location approximate") == "unknown"


def test_above_model_price_is_negative():
    d = _good_listing()
    d["value_gap_pct"] = -0.05  # priced above fair value
    assert _effect(explain_score(d), "above area model") == "negative"


def test_summary_mentions_score_strengths_and_concerns():
    d = _good_listing()
    d["energy_class"] = "E"  # a concern
    summary = summarize_score(d)
    assert summary.startswith("Score 78")
    assert "strengths:" in summary
    assert "concerns:" in summary
    assert "Energy class E" in summary
