# ruff: noqa: F811  (the imported `env` fixture is re-declared as a test argument)
"""Copy guard: every visible string on every page reads as one Greek product.

Drives each page of the real app through the AppTest harness from the UI gauntlet and checks
the text a user can see: no emoji or decorative symbols, no English words, no placeholders
like ``N/A`` / ``None``, Greek number formats and the right singular for ages.
"""

from __future__ import annotations

import re

import pytest

from .test_ui_gauntlet import PAGES, env, fresh  # noqa: F401, F811  (env is a pytest fixture)

# Latin-alphabet words of 4+ letters that may appear. Everything else must be Greek.
LATIN_ALLOWED = {
    "xe.gr",  # the portal we read
    "google",  # map links
    "mapbox",  # map tiles credit
    "cholargos",  # area names the source stores in Latin
    "green-acres",  # portal names (collectors.SOURCE_LABELS)
    "golden",
    "home",
    "re/max",
}
# Functional glyphs allowed inside button labels only (see _BUTTON_GLYPHS).
_BUTTON_GLYPHS = ""  # round-3 QA: buttons use words, no glyphs
# Pictographic or decorative: emoji, arrows, geometric shapes, "≈". Math signs (− × ÷ ≥ ≤)
# are allowed in formulas.
_DECOR = re.compile(
    "[\U0001f000-\U0001faff"  # emoji and pictographs
    "←-⇿"  # arrows
    "≈"  # ≈
    "■-◿"  # geometric shapes (▲ ▼ ■ …)
    "☀-➿"  # misc symbols and dingbats
    "⬀-⯿️‍]"
)
_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z.'-]{3,}")
_BAD_PERCENT = re.compile(r"\d%")
_URL = re.compile(r"https?://\S+|\]\([^)]*\)")
_HIDDEN = re.compile(r"<(style|script)\b.*?</\1>|<!--.*?-->", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_COLOR = re.compile(r":(?:green|orange|red|blue|gray|grey|violet|rainbow)\[")  # markdown colour


def _walk(node):
    yield node
    for child in getattr(node, "children", {}).values():
        yield from _walk(child)


def visible_strings(at) -> list[tuple[str, str]]:
    """(kind, text) for every string a user can read; buttons are returned as ``button``."""
    out: list[tuple[str, str]] = []
    for root in (at.main, at.sidebar):
        for el in _walk(root):
            kind = getattr(el, "type", "") or ""
            for attr in ("value", "label", "body", "help", "placeholder"):
                v = getattr(el, attr, None)
                if isinstance(v, str) and v.strip() and kind not in ("text_input",):
                    out.append(("button" if "button" in kind else kind, v))
            opts = getattr(el, "options", None)
            if isinstance(opts, (list, tuple)):
                out.extend((kind, str(o)) for o in opts if isinstance(o, str))
    return out


def _problems(page: str, strings: list[tuple[str, str]]) -> list[str]:
    bad: list[str] = []
    for kind, text in strings:
        shown = _URL.sub(" ", _TAG.sub(" ", _COLOR.sub("[", _HIDDEN.sub(" ", text))))
        scan = shown
        if kind == "button":  # functional glyphs are fine inside button labels
            scan = scan.translate({ord(c): None for c in _BUTTON_GLYPHS})
        for m in _DECOR.finditer(scan):
            bad.append(f"{page}: decoration {m.group()!r} in {text[:80]!r}")
        for m in _LATIN_WORD.finditer(shown):
            word = m.group().strip(".'-")
            if len(word) >= 4 and word.lower() not in LATIN_ALLOWED:
                bad.append(f"{page}: English/Latin {word!r} in {text[:80]!r}")
        if re.search(r"\bn=", shown):
            bad.append(f"{page}: «n=» notation in {text[:80]!r}")
        if re.search(r"\b(N/A|None|nan)\b", shown):
            bad.append(f"{page}: placeholder in {text[:80]!r}")
        if _BAD_PERCENT.search(shown):
            bad.append(f"{page}: percent without a space before % in {text[:80]!r}")
        if m := re.search(r"\b(AI|top|vs|and|the|for|new|best)\b", shown):
            bad.append(f"{page}: English {m.group()!r} in {text[:80]!r}")
        for wrong in ("1 ετών", "1 αγγελίες", "1 μέρες", "1 περιοχές", "1 παρόμοια"):
            if re.search(rf"(?<![\d.,]){wrong}\b", shown):
                bad.append(f"{page}: «{wrong}» in {text[:80]!r}")
    return bad


@pytest.mark.parametrize("page", PAGES)
def test_page_copy(env, page):  # noqa: F811
    at = fresh(page)
    assert not at.exception, [e.value for e in at.exception]
    strings = visible_strings(at)
    assert strings, page
    problems = _problems(page, strings)
    assert not problems, "\n".join(sorted(set(problems)))


def _click(at, prefix: str):
    next(b for b in at.button if (b.key or "").startswith(prefix)).click().run()


def _guide_step(n: int):
    """The guide page after answering its first ``n`` questions with the first option."""

    def run(env):
        at = fresh(PAGES[0])
        for prefix in ("guide-b", "guide-g-", "guide-w-", "guide-show")[:n]:
            _click(at, prefix)
        return at

    run.__name__ = f"_guide_after_{n}_answers"
    return run


def _search_example_with_advice(env):
    at = fresh("Αναζήτηση")
    at.button(key="ex0").click().run()
    at.button(key="advice_again").click().run()
    return at


def _favourite_and_details(env):
    at = fresh("Αναζήτηση")
    next(b for b in at.button if b.label == "Αγαπημένο").click().run()
    at.radio(key="page").set_value("Αγαπημένα").run()
    return at


def _saved_search(env):
    at = fresh("Αναζήτηση")
    at.button(key="ex0").click().run()
    at.button(key="save_mandate").click().run()
    at.radio(key="page").set_value("Αποθηκευμένες αναζητήσεις").run()
    return at


@pytest.mark.parametrize(
    "state",
    [_guide_step(n) for n in (1, 2, 3, 4)]
    + [_search_example_with_advice, _favourite_and_details, _saved_search],
)
def test_copy_in_interaction_states(env, state):  # noqa: F811
    at = state(env)
    assert not at.exception, [e.value for e in at.exception]
    problems = _problems(state.__name__, visible_strings(at))
    assert not problems, "\n".join(sorted(set(problems)))


def test_guard_catches_known_slop():
    """The guard itself: each of these slips must be reported, clean copy must pass."""
    slips = [
        ("markdown", "🔄 Ανανέωση"),
        ("markdown", "≈ 4,7 %"),
        ("markdown", "▲ ηλικία ▼"),
        ("markdown", "Μικτή απόδοση 4,7%"),
        ("markdown", "Πρόσοψη, 1 ετών"),
        ("markdown", "Οι top 20 αγγελίες"),
        ("caption", "Συχνά μόνο renders ή λογότυπο"),
        ("caption", "N/A"),
        ("markdown", "Δεύτερη γνώμη (AI)"),
        ("markdown", "Βρέθηκε 1 αγγελίες"),
        ("button", "↺ Αναίρεση"),
        ("markdown", "Ιουλ 2.589 (n=178)"),
    ]
    for kind, text in slips:
        assert _problems("x", [(kind, text)]), text
    clean = [
        ("button", "Αγαπημένο"),
        ("button", "Άνοιγμα στο XE.gr"),
        ("markdown", ":green[**Ελέγχθηκε η περιγραφή**]"),
        ("markdown", "Μικτή απόδοση 4,7 % · Ενοίκιο (εκτίμηση) ~1.070 €/μήνα · 12 − 1 μήνες"),
        ("markdown", '<div style="width:50%">Δεδομένα XE.gr, Cholargos</div>'),
        ("caption", "[Google](https://maps.google.com/?q=x) 3 μέρες στην αγορά"),
    ]
    assert not _problems("x", clean)
