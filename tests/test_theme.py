"""The design system in ``ui/theme.py`` (round 5, C6): tokens, type roles, the 4-pt spacing
scale, one radius family, 44 px touch targets, a focus ring, and the craft-floor bans.

These read the CSS text; the rendered numbers (contrast, target boxes, font sizes in use) are
measured on the running app by ``docs/qa/design/measure.js``.
"""

from __future__ import annotations

import re

from scout.ui import theme

CSS = theme._CSS
ROOT = re.search(r":root \{(.*?)\n\}", CSS, re.S).group(1)


def _tokens() -> dict[str, str]:
    return {k: v.strip() for k, v in re.findall(r"(--hg-[\w-]+):\s*([^;]+);", ROOT)}


def _px(value: str) -> float:
    n = float(re.match(r"-?[\d.]+", value).group())
    return n * 16 if value.endswith("rem") else n


def test_token_set():
    t = _tokens()
    for name in (
        "--hg-ink",
        "--hg-muted",
        "--hg-accent",
        "--hg-surface",
        "--hg-canvas",
        "--hg-line",
        "--hg-sep",
        "--hg-target",
        *(f"--hg-{tone}-{part}" for tone in ("ok", "warn", "bad") for part in ("bg", "fg")),
        *(f"--hg-r-{r}" for r in ("card", "control", "chip", "pill")),
        *(f"--hg-s{n}" for n in (1, 2, 3, 4, 5, 6, 8, 10)),
    ):
        assert name in t, name
    assert [t[f"--hg-s{n}"] for n in (1, 2, 3, 4, 5, 6, 8, 10)] == [
        "4px",
        "8px",
        "12px",
        "16px",
        "20px",
        "24px",
        "32px",
        "40px",
    ]
    assert 12 <= _px(t["--hg-r-card"]) <= 16


def test_type_roles_and_every_font_size_is_a_role():
    t = _tokens()
    roles = {
        "large": "1.75rem",
        "title": "1.3rem",
        "headline": "1.0625rem",
        "body": "1rem",
        "subhead": ".9375rem",
        "footnote": ".8125rem",
        "caption": ".75rem",
    }
    for role, size in roles.items():
        assert t[f"--hg-fs-{role}"] == size, role
    sizes = re.findall(r"font-size:\s*([^;}]+)", CSS)
    loose = [s for s in sizes if not re.match(r"var\(--hg-fs-\w+\)", s.strip())]
    assert not loose, loose
    # tracking on titles only, never tighter than the floor
    assert all(float(v) >= -0.04 for v in re.findall(r"letter-spacing:\s*(-[\d.]+)em", CSS))


def test_spacing_is_on_the_4pt_scale():
    off = []
    for prop, value in re.findall(
        r"((?:margin|padding|gap|row-gap|column-gap)[\w-]*):\s*([^;}]+)", CSS
    ):
        for tok in value.replace("!important", "").split():
            # 1-2 px are hairline / optical offsets (badge padding, border overlap), not spacing
            if re.fullmatch(r"-?[\d.]+(px|rem)", tok) and abs(_px(tok)) > 2 and _px(tok) % 4:
                off.append(f"{prop}: {value.strip()}")
    assert not off, off


def test_one_radius_family():
    radii = re.findall(r"border-radius:\s*([^;}]+)", CSS)
    loose = [
        r
        for r in radii
        if not re.match(r"var\(--hg-(r-\w+|radius)\)", r.strip())
        and not r.startswith("50%")
        and r.strip() != "0"
    ]
    assert not loose, loose


def test_touch_targets_are_44px_on_every_control_family():
    assert _tokens()["--hg-target"] == "44px"
    block = re.search(
        r":is\(\s*\.stButton button(.*?)\)\s*\{\{?\s*min-height: var\(--hg-target\)", CSS, re.S
    )
    assert block, "the 44 px target rule is missing"
    rule = block.group(0)
    for hook in (
        ".stLinkButton a",
        '[data-testid="stButtonGroup"] button',
        '[data-testid="stExpander"] summary',
        '[data-testid="stCheckbox"] label',
        '[data-testid="stRadio"] label',
        '[data-baseweb="select"] > div',
        '[data-baseweb="input"]',
        '[data-testid="stNumberInputStepUp"]',
    ):
        assert hook in rule, hook
    # the card disclosure («Από πού βγαίνουν») is a full-width row, not an 18 px text link
    summary = re.search(r"\.hg-card summary \{\{?(.*?)\}", CSS, re.S).group(1)
    assert "min-height: var(--hg-target)" in summary


def test_focus_ring_and_browser_surfaces():
    assert re.search(
        r":focus-visible, \[data-focus-visible\]\) \{\{?\s*outline: 2px solid var\(--hg-accent\)",
        CSS,
    )
    for surface in (
        "::selection",
        "caret-color",
        "scrollbar-color",
        "tabular-nums",
        "text-underline-offset",
    ):
        assert surface in CSS, surface


def _rules() -> list[tuple[list[str], str]]:
    """(enclosing headers outermost first, declarations) for every CSS rule."""
    out, stack, buf = [], [], ""
    for ch in CSS:
        if ch == "{":
            stack.append(buf.strip().rsplit(";", 1)[-1].strip())
            buf = ""
        elif ch == "}":
            if stack:
                out.append((list(stack), buf))
                stack.pop()
            buf = ""
        else:
            buf += ch
    return out


def test_hover_is_for_fine_pointers_only():
    """On a phone a :hover sticks after a tap and makes the next question's button look
    chosen; every :hover sits inside a (hover: hover) media query."""
    loose = [
        heads[-1][:60]
        for heads, _ in _rules()
        if ":hover" in heads[-1] and not any("@media" in h and "hover" in h for h in heads[:-1])
    ]
    assert not loose, loose


def test_craft_floor_bans():
    stripes = [
        heads[-1]
        for heads, body in _rules()
        if re.search(r"border-(left|right):\s*([2-9]|\d\d)px", body)
        and not re.search(r"::(after|before)", heads[-1])  # a drawn chevron is not a stripe
    ]
    assert not stripes, stripes
    assert "background-clip: text" not in CSS, "gradient text"
    assert not re.search(r"box-shadow:\s*\d+px \d+px 0", CSS), "hard offset shadow"
    assert "text-decoration: underline" not in CSS.split("Shell: top page pills")[-1]
    # the selected nav pill is a solid accent fill with white text (≥ 4.5:1)
    pill = re.search(r'\.st-key-nav_pill button\[aria-checked="true"\][^{]*\{\{?(.*?)\}', CSS, re.S)
    assert "background: var(--hg-accent)" in pill.group(1) and "#fff" in pill.group(1)


def test_status_tokens_pass_contrast():
    def lum(hex_: str) -> float:
        c = [int(hex_[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

    def ratio(a: str, b: str) -> float:
        x, y = sorted((lum(a), lum(b)), reverse=True)
        return (x + 0.05) / (y + 0.05)

    t = _tokens()
    for tone in ("ok", "warn", "bad", "neu"):
        assert ratio(t[f"--hg-{tone}-fg"], t[f"--hg-{tone}-bg"]) >= 4.5, tone
    assert ratio(t["--hg-accent"], "#FFFFFF") >= 4.5  # selected pill, primary button
    assert ratio(t["--hg-muted"], t["--hg-canvas"]) >= 4.5
    assert ratio(t["--hg-sep"], t["--hg-canvas"]) >= 3  # decorative «·», aria-hidden
