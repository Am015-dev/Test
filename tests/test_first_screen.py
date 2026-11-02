# ruff: noqa: F811  (the imported `env` fixture is re-declared as a test argument)
"""C18 — no machine prose, no clutter: the first screen of the guide result, the search, the
map and the areas page.

«First screen» here is every string the page renders outside an expander (what is behind one
tap may hold counts, method and formulas). The listing cards are left out: their lines are a
separate contract and the glossary itself prescribes «Παρόμοια (N)».

Asserts: no «#1»-style ranks, no «σύστημα», no «μοντέλο», no bracketed count, no sentence over
20 words; the sources/counts line is the page's last line, not its second.
"""

from __future__ import annotations

import re

import pytest

from .test_ui_gauntlet import AREAS, PAGES, SEARCH, env, fresh  # noqa: F401  (env is a fixture)

MAP = "Χάρτης"
MAX_WORDS = 20
_TAG = re.compile(r"<[^>]+>")
_HIDDEN = re.compile(r"<(style|script)\b.*?</\1>|<!--.*?-->", re.S | re.I)
_MD = re.compile(r"\*\*|__|^#+\s*|\[([^\]]*)\]\([^)]*\)", re.M)
_BRACKETED_COUNT = re.compile(r"\(\s*\+?[\d.,]+\b")  # «(8)», «(+31)», «(149 και 461 αγγελίες)»
_MACHINE = re.compile(r"#\d|σύστημ|μοντέλ", re.I)


def _click(at, prefix: str):
    next(b for b in at.button if (b.key or "").startswith(prefix)).click().run()


def guide_result(env):
    at = fresh(PAGES[0])
    _click(at, "guide-mode-buy")
    for prefix in ("guide-b2", "guide-g-", "guide-w-", "guide-show"):
        _click(at, prefix)
    assert not at.exception, [e.value for e in at.exception]
    return at


def first_screen(at) -> list[str]:
    """Every string the page shows before any tap: expanders, chat and the cards are skipped."""
    out: list[str] = []

    def walk(node):
        name = type(node).__name__
        if name in ("Expander", "ChatMessage"):
            return
        if "card" in str(getattr(getattr(node, "proto", None), "id", "")):  # keyed card boxes
            return
        kind = getattr(node, "type", "") or ""
        for attr in ("value", "label", "body"):
            v = getattr(node, attr, None)
            if isinstance(v, str) and v.strip() and kind not in ("text_input", "chat_input"):
                if 'class="hg-card"' not in v:
                    out.append(v)
        opts = getattr(node, "options", None)
        if isinstance(opts, (list, tuple)):
            out.extend(str(o) for o in opts if isinstance(o, str))
        for child in getattr(node, "children", {}).values():
            walk(child)

    walk(at.main)
    return out


def plain(text: str) -> str:
    return _MD.sub(r"\1", _TAG.sub(" ", _HIDDEN.sub(" ", text))).strip()


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!;])\s+|\n+", plain(text)) if s.strip()]


def words(sentence: str) -> int:
    return sum(1 for tok in sentence.split() if re.search(r"[^\W_]", tok))


def problems(strings: list[str]) -> list[str]:
    bad = []
    for raw in strings:
        text = plain(raw)
        if m := _MACHINE.search(text):
            bad.append(f"machine word {m.group()!r} in {text[:80]!r}")
        if m := _BRACKETED_COUNT.search(text):
            bad.append(f"bracketed count {m.group()!r} in {text[:80]!r}")
        for s in sentences(raw):
            if words(s) > MAX_WORDS:
                bad.append(f"{words(s)} words: {s[:100]!r}")
    return bad


GUIDE_HEAD_PENDING = pytest.mark.xfail(
    strict=False,
    reason="C17 (W31) rewrites the guide's result head: the «Πρόταση» paragraph carries "
    "«(222.000 €, …)», the counts line runs over 20 words, and the relaxation buttons say "
    "«(+5, 0 με ελεγμένη περιγραφή)». Drop this mark once that lands.",
)


@pytest.mark.parametrize(
    "page", [pytest.param(PAGES[0], marks=GUIDE_HEAD_PENDING), SEARCH, MAP, AREAS]
)
def test_first_screen_is_short_and_human(env, page):
    at = guide_result(env) if page == PAGES[0] else fresh(page)
    strings = first_screen(at)
    assert strings, page
    assert not problems(strings), "\n".join(problems(strings))


def test_guide_result_has_no_machine_prose(env):
    """The model-written «Σημείωμα επενδυτή» is gone from the result; nothing on the first
    screen says «#1», «σύστημα» or «μοντέλο» (strict, whatever the result head says)."""
    at = guide_result(env)
    strings = first_screen(at)
    assert not any("Σημείωμα επενδυτή" in s for s in strings)
    bad = [p for p in problems(strings) if p.startswith("machine word")]
    assert not bad, "\n".join(bad)


def test_sources_line_is_the_footer_not_the_header(env):
    at = fresh(SEARCH)
    caps = [c.value for c in at.main.caption]
    assert caps and caps[-1].startswith("XE.gr"), caps[-1:]  # the last line of every page
    head = [m.value for m in at.main.markdown if 'class="hg-app-head"' in m.value]
    assert len(head) == 1
    assert sum(c.startswith("XE.gr") for c in caps) == 1  # nowhere else


def test_search_counts_are_one_line_with_the_breakdown_behind_a_tap(env):
    at = fresh(SEARCH)
    count = next(m.value for m in at.markdown if 'class="hg-count"' in m.value)
    line = plain(count).split("\n")[-1] if "\n" in plain(count) else plain(count)
    assert words(line) <= MAX_WORDS, line
    hidden = [m for m in re.findall(r"Κρύβω [\d.]+: [^.]+\.", plain(count))]
    assert len(hidden) <= 1 and "Κρύβονται" not in count, count
    if hidden:
        exp = next(e for e in at.expander if e.label == "Τι κρύβω και γιατί")
        assert any(m.value.startswith("Κρύβ") for m in exp.markdown)


def test_map_first_screen_has_one_fact_line(env):
    at = fresh(MAP)
    line = next(m.value for m in at.markdown if "στον χάρτη**" in m.value)
    assert re.search(r"· (μόνο [\d.]+ με ακριβή θέση|καμία με ακριβή θέση)\.$", line), line
    exp = next(e for e in at.expander if e.label == "Τι δεν φαίνεται στον χάρτη")
    assert any("ακριβή θέση" in c.value for c in exp.caption)


def test_areas_box_is_four_verdicts_with_the_sentences_behind(env):
    from scout import area_insights as ai
    from scout.ui import areas

    at = fresh(AREAS)
    exp = next(e for e in at.expander if e.label == "Από πού βγαίνουν")
    full = [m.value for m in exp.markdown]
    assert full and full[0].startswith("Αν θες απόδοση:")
    verdict = re.compile(r"^\*\*[^*\n]+\*\* · [^\n]+$")  # one line: «**Περιοχή** · …»
    box = [m.value for m in at.markdown if verdict.match(m.value)]
    assert 1 <= len(box) <= 4, box
    for line in box:
        assert len(re.findall(r"\d+(?:[.,]\d+)?", line)) == 1, line  # one number each
    # the verdicts name the same areas, in the same order, as the sentences they summarise
    named = [re.match(r"\*\*([^*]+)\*\*", b).group(1) for b in box]
    in_full = [
        m.group(1) for s in full if (m := re.match(r"Αν θες [^:]+: ([^.,(]+?)(?:[.,]| \()", s))
    ]
    assert named == [a for a in in_full if a in named], (named, in_full)
    assert callable(areas.verdicts) and ai.decision  # the two read the same AreaInsight fields
