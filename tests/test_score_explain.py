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
    assert summarize_score({}) == "Δεν υπάρχουν διαθέσιμα σήματα"


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
    assert _effect(rows, "κάτω από το μοντέλο περιοχής") == "positive"
    assert _effect(rows, "Καθαρή απόδοση") == "positive"
    # And the numbers are rendered honestly.
    labels = " | ".join(r["label"] for r in rows)
    assert "Τιμή 12% κάτω από το μοντέλο περιοχής" in labels
    assert "Καθαρή απόδοση 4.8%" in labels


def test_yield_row_prefers_area_percentile_over_flat_floor():
    # 4.8% clears the flat net_yield_floor (0.015) → positive under the old flat-only logic.
    # With yield_percentile present (annotate_relative_value ran on the pool) and below 0.5,
    # it's actually the WORST yield among comparable local listings — the explanation must
    # say so, or it would contradict what the area-relative score signal now computes on.
    d = _good_listing()
    d["yield_percentile"] = 0.2
    rows = explain_score(d)
    assert _effect(rows, "Καθαρή απόδοση") == "negative"
    details = " | ".join(r["detail"] for r in rows)
    assert "καλύτερη από το 20% των συγκρίσιμων αγγελιών" in details

    # And the reverse: below the flat floor but locally the best available → positive.
    d2 = _good_listing()
    d2["net_yield"] = 0.01  # below flat net_yield_floor (0.015)
    d2["yield_percentile"] = 0.9
    assert _effect(explain_score(d2), "Καθαρή απόδοση") == "positive"


def test_good_energy_and_modern_build_are_positive():
    rows = explain_score(_good_listing())
    assert _effect(rows, "Ενεργειακή κλάση B") == "positive"
    assert _effect(rows, "Σύγχρονο ακίνητο") == "positive"
    assert _effect(rows, "ως το μετρό") == "positive"


def test_missing_energy_and_year_are_unknown_not_negative():
    d = _good_listing()
    d["energy_class"] = None
    d["year_built"] = None
    d["renovated_year"] = None
    rows = explain_score(d)
    assert _effect(rows, "Δεν δηλώνεται ενεργειακή κλάση") == "unknown"
    assert _effect(rows, "Δεν δηλώνεται έτος κατασκευής") == "unknown"
    # An unknown signal must be flagged as not-scored, never dressed up as a positive.
    for label in ("Δεν δηλώνεται ενεργειακή κλάση", "Δεν δηλώνεται έτος κατασκευής"):
        row = next(r for r in rows if r["label"] == label)
        assert "δεν βαθμολογείται" in row["detail"].lower()


def test_poor_energy_class_is_negative():
    d = _good_listing()
    d["energy_class"] = "E"
    assert _effect(explain_score(d), "Ενεργειακή κλάση E") == "negative"


def test_estimated_rent_is_not_a_positive_yield():
    d = _good_listing()
    d["rent_estimated"] = True  # imputed rent — not a real comp
    rows = explain_score(d)
    # The yield row must be unknown, and NO row may claim a yield as positive.
    assert _effect(rows, "εκτιμώμενο ενοίκιο") == "unknown"
    for r in rows:
        if "απόδοση" in r["label"].lower():
            assert r["effect"] != "positive"


def test_missing_rent_key_defaults_to_estimated():
    d = _good_listing()
    del d["rent_estimated"]
    d.pop("net_yield")
    d.pop("gross_yield")
    rows = explain_score(d)
    assert _effect(rows, "απόδοση") == "unknown"


def test_centroid_location_metro_is_unknown():
    d = _good_listing()
    d["location_precision"] = "area"  # not a per-listing point
    rows = explain_score(d)
    assert _effect(rows, "Κατά προσέγγιση τοποθεσία") == "unknown"


def test_above_model_price_is_negative():
    d = _good_listing()
    d["value_gap_pct"] = -0.05  # priced above fair value
    assert _effect(explain_score(d), "πάνω από το μοντέλο περιοχής") == "negative"


def test_summary_mentions_score_strengths_and_concerns():
    d = _good_listing()
    d["energy_class"] = "E"  # a concern
    summary = summarize_score(d)
    assert summary.startswith("Σκορ 78")
    assert "δυνατά σημεία:" in summary
    assert "αδυναμίες:" in summary
    assert "Ενεργειακή κλάση E" in summary
