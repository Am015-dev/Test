"""The search page honours the floor / building-age / price / area filters, provably.

The owner's complaint was "I told you building age and floor and I still see the same". These
tests set the filters the way the buyer does (a parsed search the filter editor pre-fills, and
the filter widgets themselves) and check, against predicates written out here, that

* every card on screen satisfies every filter (read from the card itself),
* the result count is exactly the number of listings that satisfy them,
* "Κρύβονται N" + "N χωρίς δηλωμένο όροφο/έτος" account for every other listing, and the
  floor/year groups are exactly what «Δείξε όλες» brings back,
* listings that do not state their floor or build year never pass a floor/year filter
  silently: they are counted apart and come back only on «Δείξε και αυτές».

They run on the seeded gauntlet DB always, and on the real published DB when it has been
downloaded to ``data/listings.db`` (or ``LIVE_DB``) — see docs/COORDINATION.md.
"""

from __future__ import annotations

import os
import re
from collections import Counter
from datetime import date
from pathlib import Path

import pytest

from scout.config import get_settings
from scout.nl_search import NOT_A_HOME, SearchFilters, _norm

from .test_ui_gauntlet import APP, SEARCH, env, goto  # noqa: F401  (env is a fixture)

FLAT_WORDS = ("διαμερισμα", "apartment", "studio", "γκαρσονιερα", "loft", "flat")
AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
LIVE = Path(os.environ.get("LIVE_DB", Path(__file__).resolve().parents[1] / "data/listings.db"))
YEAR, FLOOR = 2015, 2
ALL = 1_000_000  # render every card


# ---- what the filters mean, written out independently of the app ---------------------------


def _is_home(d: dict) -> bool:
    if d.get("is_suspect") or d.get("is_unfinished"):
        return False
    title = _norm(d.get("title") or "")
    if title.startswith(NOT_A_HOME):
        return False
    if title and not title.startswith(FLAT_WORDS):  # houses only when asked for
        return False
    low = d.get("floor") is not None and d["floor"] < 1
    return not d.get("excluded") or low  # only the thesis' ground-floor rule is left to filters


def _other_filters(d: dict, areas: set[str], price_max: int) -> bool:
    from scout.ui import buyer

    return _is_home(d) and d["price"] <= price_max and buyer._area_hit(d, sorted(areas))


def _floor_year_ok(d: dict, year_min: int = YEAR) -> bool:
    return (
        d.get("floor") is not None
        and d["floor"] >= FLOOR
        and d.get("year_built") is not None
        and d["year_built"] >= year_min
    )


def _undeclared_only(d: dict, year_min: int) -> bool:
    """Fails the floor/year filter only because it does not state floor or year."""
    floor, year = d.get("floor"), d.get("year_built")
    return (
        (floor is None or year is None)
        and (floor is None or floor >= FLOOR)
        and (year is None or year >= year_min)
    )


# ---- reading the page ----------------------------------------------------------------------


def _cards(at) -> list[str]:
    return [m.value for m in at.markdown if 'class="hg-card"' in m.value]


def _count(at) -> int:
    m = next(m.value for m in at.markdown if 'class="hg-count"' in m.value)
    return int(re.search(r"<b>([\d.]+)</b>", m).group(1).replace(".", ""))


def _n(s: str) -> int:
    return int(s.replace(".", ""))


def _hidden(at) -> tuple[int, dict[str, int], int]:
    """(N in "Κρύβονται N", {label: n}, n without declared floor/year) — the one result line."""
    line = next(m.value for m in at.markdown if 'class="hg-count"' in m.value)
    m = re.search(r"Κρύβ(?:ονται|εται) ([\d.]+): (.*)</small>", line)
    if not m:
        return 0, {}, 0
    groups = {}
    for part in m.group(2).split(" · "):
        num, label = part.split(" ", 1)
        groups[label] = _n(num)
    undeclared = groups.pop("χωρίς όροφο/έτος", 0)
    return _n(m.group(1)) - undeclared, groups, undeclared


def _check_card(card: str, price_max: int, year_min: int) -> None:
    price = _n(re.search(r'class="hg-price">([\d.]+) €<', card).group(1))
    floor = re.search(r"(\d+)ος όροφος", card)
    year = re.search(r"κτίριο (\d{4})", card)
    assert price <= price_max, card
    assert floor and int(floor.group(1)) >= FLOOR, card
    assert year and int(year.group(1)) >= year_min, card
    assert "hg-st-bad" not in card, card  # never an under-construction flat


def _ver(at) -> int:
    return at.session_state["f_ver"] if "f_ver" in at.session_state else 0


def _run(at, f: SearchFilters | None = None):
    if f is not None:
        at.session_state["nl_filters"] = f
        at.session_state["f_ver"] = 7
    at.session_state["limit"] = ALL
    at.run()
    assert not at.exception, [e.value[:300] for e in at.exception]
    return at


def _open_search(timeout: int):
    at = AppTest.from_file(APP, default_timeout=timeout).run()
    goto(at, SEARCH)
    return at


def _prove(
    at, listings: list[dict], areas: list[str], price_max: int, year_min: int, report: dict
) -> None:
    """All the assertions, for one filter state already on screen."""
    from scout.ui import buyer

    pool = [d for d in listings if d.get("is_fresh", True)]
    rest = [d for d in pool if _other_filters(d, set(areas), price_max)]
    want = [d for d in rest if _floor_year_ok(d, year_min)]
    back = [d for d in rest if not _floor_year_ok(d, year_min)]
    undeclared = [d for d in back if _undeclared_only(d, year_min)]

    # 1. the result count is exactly the listings that satisfy every filter
    shown = _count(at)
    assert shown == len(want) > 0
    # 2. every card on screen satisfies every filter, read from the card itself
    cards = _cards(at)
    assert len(cards) == shown
    ids = {int(re.search(r'data-lid="(\d+)"', c).group(1)) for c in cards}
    assert ids == {d["id"] for d in want}
    for c in cards:
        _check_card(c, price_max, year_min)
    # 3. the hidden line accounts for every other listing, by reason
    total, groups, n_undeclared = _hidden(at)
    assert total == sum(groups.values())
    assert total + n_undeclared + shown == len(pool)
    assert n_undeclared == len(undeclared)
    labels = buyer.hide_labels(SearchFilters(floor_min=FLOOR, year_min=year_min))
    floor_year = groups.get(labels["floor"], 0) + groups.get(labels["year"], 0)
    assert floor_year + n_undeclared == len(back)
    report.update(
        year_min=year_min,
        pool=len(pool),
        shown=shown,
        hidden=total,
        undeclared=n_undeclared,
        groups=groups,
    )

    # 4. «Και αγγελίες χωρίς δηλωμένο όροφο/έτος» brings back exactly the undeclared ones,
    #    each saying so on its card
    if n_undeclared:
        at.checkbox(key=f"fe_undecl_{_ver(at)}").check()
        _run(at)
        assert _count(at) == shown + n_undeclared
        extra = [
            c for c in _cards(at) if int(re.search(r'data-lid="(\d+)"', c).group(1)) not in ids
        ]
        assert len(extra) == n_undeclared
        assert all("όροφος: δεν δηλώνεται" in c or "έτος: δεν δηλώνεται" in c for c in extra)
        at.checkbox(key=f"fe_undecl_{_ver(at)}").uncheck()
        _run(at)
        assert _count(at) == shown

    # 5. «Δείξε όλες» brings back exactly the floor/year groups (and the undeclared)
    btn = at.button(key="show_all_btn")
    assert _n(re.search(r"\(\+([\d.]+)\)", btn.label).group(1)) == len(back)
    btn.click()
    _run(at)
    assert _count(at) == shown + len(back)


def _setup_filters(listings: list[dict]) -> tuple[list[str], int]:
    """Two areas with the most flats satisfying floor/year, and a price cap that hides some."""
    from scout.ui import buyer

    good = [
        d
        for d in listings
        if d.get("is_fresh", True) and _is_home(d) and _floor_year_ok(d) and d.get("price")
    ]
    top = [a for a, _ in Counter(buyer.area_name(d) for d in good).most_common(2)]
    prices = sorted(d["price"] for d in good if buyer.area_name(d) in top)
    return top, prices[len(prices) * 3 // 4]


def _both_ways(at_factory, listings, report_prefix: str, reports: dict) -> None:
    areas, price_max = _setup_filters(listings)
    # a) the filters come from a search (the editor pre-fills them; 2015 is not a preset age)
    at = _run(
        at_factory(),
        SearchFilters(areas=areas, price_max=price_max, year_min=YEAR, floor_min=FLOOR),
    )
    ver = at.session_state["f_ver"]
    assert at.number_input(key=f"fe_year_{ver}").value == YEAR
    assert at.number_input(key=f"fe_floor_{ver}").value == FLOOR
    assert f"χτισμένο από το {YEAR}" in at.expander[0].label  # the filter panel says what applies
    reports[f"{report_prefix}/search"] = rep = {"areas": areas, "price_max": price_max}
    _prove(at, listings, areas, price_max, YEAR, rep)

    # b) the same filters set on the widgets by hand
    at = at_factory()
    ver = _ver(at)
    at.multiselect(key=f"fe_areas_{ver}").set_value(areas)
    at.number_input(key=f"fe_pmax_{ver}").set_value(price_max)
    at.number_input(key=f"fe_floor_{ver}").set_value(FLOOR)
    year_min = date.today().year - 10  # a different year than (a), typed in by hand
    at.number_input(key=f"fe_year_{ver}").set_value(year_min)
    _run(at)
    reports[f"{report_prefix}/widgets"] = rep = {"areas": areas, "price_max": price_max}
    _prove(at, listings, areas, price_max, year_min, rep)


# ---- the tests -----------------------------------------------------------------------------

REPORTS: dict[str, dict] = {}


def test_filters_honoured_on_seeded_db(env):  # noqa: F811
    from scout.ui import queries

    listings = queries.load_listings(include_excluded=True, only_active=True)
    _both_ways(lambda: _open_search(60), listings, "seeded", REPORTS)


@pytest.fixture
def live(monkeypatch, tmp_path):
    if not LIVE.exists():
        pytest.skip(f"no live DB at {LIVE} (download it per docs/COORDINATION.md)")
    import streamlit as st

    import scout.db as dbmod
    import scout.remote_db as rdb

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{LIVE.resolve()}")
    for k in ("GITHUB_TOKEN", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    get_settings.cache_clear()
    st.cache_data.clear()
    st.cache_resource.clear()
    dbmod._engine = None
    dbmod._SessionFactory = None
    dbmod.init_db()  # forward-migrate a downloaded DB that predates newer columns, as the app does
    monkeypatch.setattr(rdb.requests, "get", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    yield
    dbmod._engine = None
    dbmod._SessionFactory = None
    get_settings.cache_clear()


def test_filters_honoured_on_live_db(live):
    from scout.ui import queries

    listings = queries.load_listings(include_excluded=True, only_active=True)
    _both_ways(lambda: _open_search(600), listings, "live", REPORTS)
    for k, v in REPORTS.items():
        print(k, v)
