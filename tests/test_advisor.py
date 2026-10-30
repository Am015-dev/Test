from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pytest

from scout.advisor import AdvisorError, red_flags, review

YEAR = date.today().year


def _row(sid: str, **kw) -> dict:
    d = {
        "source": "xe",
        "source_id": sid,
        "price": 180_000,
        "area_m2": 60.0,
        "price_per_m2": 3000.0,
        "floor": 2.0,
        "year_built": 2005,
        "renovated_year": None,
        "energy_class": None,
        "title": "Διαμέρισμα 60 τ.μ.",
    }
    return {**d, **kw}


def _client(content=None, boom=None):
    calls = []

    def create(**kw):
        calls.append(kw)
        if boom:
            raise boom
        return SimpleNamespace(content=content)

    return SimpleNamespace(messages=SimpleNamespace(create=create)), calls


def _out(verdicts, summary="Σύνοψη."):
    text = json.dumps({"summary": summary, "verdicts": verdicts}, ensure_ascii=False)
    return [SimpleNamespace(type="text", text=text)]


def _text(s):
    return [SimpleNamespace(type="text", text=s)]


def test_payload_has_only_sent_rows_and_skips_none():
    rows = [_row(str(i)) for i in range(5)]
    client, calls = _client(
        _out([{"key": f"xe:{i}", "label": "Αξίζει", "reason": "ok"} for i in range(3)])
    )
    review("δυάρι", rows, client=client, max_rows=3)
    payload = json.loads(calls[0]["messages"][0]["content"])
    keys = [x["key"] for x in payload["listings"]]
    assert keys == ["xe:0", "xe:1", "xe:2"]
    first = payload["listings"][0]
    assert "renovated_year" not in first and "energy_class" not in first
    assert first["year_built"] == 2005 and payload["context"]["query"] == "δυάρι"
    fmt = calls[0]["output_config"]["format"]
    assert fmt["type"] == "json_schema" and fmt["schema"]["additionalProperties"] is False


def test_unknown_keys_dropped_and_long_reason_trimmed():
    verdicts = [
        {"key": "xe:1", "label": "Απόφυγε", "reason": "α" * 300},
        {"key": "xe:999", "label": "Αξίζει", "reason": "invented"},
    ]
    client, _ = _client(_out(verdicts))
    out = review("q", [_row("1")], client=client)
    assert [v.key for v in out.verdicts] == ["xe:1"]
    assert len(out.verdicts[0].reason) <= 160


def test_missing_key_raises(monkeypatch):
    monkeypatch.setattr("scout.advisor.get_settings", lambda: SimpleNamespace(anthropic_api_key=""))
    with pytest.raises(AdvisorError):
        review("q", [_row("1")])


@pytest.mark.parametrize(
    "content,boom",
    [
        (None, RuntimeError("api down")),
        ([SimpleNamespace(type="tool_use", input={})], None),
        (_text("not json"), None),
        (_text('{"summary": "x", "verdicts": ['), None),
        (_text('{"verdicts": []}'), None),
        (_out([{"key": "xe:1", "label": "Τέλειο", "reason": "x"}]), None),
        (_out([{"key": "xe:2", "label": "Αξίζει", "reason": "wrong key only"}]), None),
    ],
)
def test_failures_raise_advisor_error(content, boom):
    client, calls = _client(content, boom)
    with pytest.raises(AdvisorError):
        review("q", [_row("1")], client=client)
    assert len(calls) == (1 if boom else 2)  # bad output is retried once, API errors are not


def test_unusable_output_is_retried_once():
    replies = iter(
        [
            _text('{"summary": "x"}'),
            _out([{"key": "xe:1", "label": "Με επιφύλαξη", "reason": "έτος δεν δηλώνεται"}]),
        ]
    )
    client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kw: SimpleNamespace(content=next(replies)))
    )
    out = review("q", [_row("1")], client=client)
    assert out.verdicts[0].label == "Με επιφύλαξη" and out.summary == "Σύνοψη."


def test_no_rows_raises():
    with pytest.raises(AdvisorError):
        review("q", [], client=object())


def test_red_flags_old_building():
    assert f"Κτίριο {YEAR - 1965} ετών" in red_flags(_row("1", year_built=1965))
    assert red_flags(_row("1", year_built=1965, renovated_year=2019)) == []
    assert "Κτίριο 50 ετών" in red_flags(_row("1", year_built=None, building_age=50))
    assert red_flags(_row("1", year_built=None)) == ["Χωρίς έτος κατασκευής"]


def test_red_flags_status_floor_energy_price():
    assert "Ημιτελές" in red_flags(_row("1", is_unfinished=True))
    assert "Ισόγειο" in red_flags(_row("1", floor=0.0))
    assert "Υπόγειο" in red_flags(_row("1", floor=-1.0))
    assert "Ενεργειακή Η" in red_flags(_row("1", energy_class="Η"))
    cheap = _row("1", price_per_m2=1500.0, area_median_ppm2=3000.0)
    assert "Πολύ φθηνό για την περιοχή — έλεγξε γιατί" in red_flags(cheap)
    assert red_flags(_row("1", price_per_m2=2500.0, area_median_ppm2=3000.0)) == []
    assert red_flags(_row("1", floor=0.5)) == []  # mezzanine is not ground
