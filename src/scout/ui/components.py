"""Custom HTML components — the product surface.

Streamlit's default dataframe reads as a spreadsheet; a property tool needs designed
*listing cards*. These render each listing as a card in a responsive grid via a single
``st.markdown(unsafe_allow_html=True)`` blob, so the page looks like a real proptech
product rather than an internal dashboard. Styling lives in ``theme.py`` (the ``ph-*``
classes); this module only builds the markup from listing dicts.
"""

from __future__ import annotations

import html as _html
import re as _re

import streamlit as st

from . import format as fmt

# Energy class -> pill colour bucket (good / mid / poor / liability).
_ENERGY_BUCKET = {
    "A+": "good",
    "Α+": "good",
    "A": "good",
    "Α": "good",
    "B+": "good",
    "Β+": "good",
    "B": "good",
    "Β": "good",
    "C": "mid",
    "Γ": "mid",
    "D": "mid",
    "Δ": "mid",
    "E": "poor",
    "Ε": "poor",
    "F": "poor",
    "Ζ": "poor",
    "G": "bad",
    "Η": "bad",
    "H": "bad",
}
_ARCHETYPE_CLASS = {
    "New build": "new",
    "Renovated": "reno",
    "Modern": "modern",
    "Dated": "dated",
    "Energy liability": "liability",
    "Standard": "std",
}


def _score_hue(score: float) -> int:
    """0 (red) → 120 (green) hue for the score chip, clamped."""
    return int(max(0.0, min(1.0, score / 70.0)) * 130)


def _esc(v) -> str:
    return _html.escape(str(v)) if v is not None else ""


def _card_html(d: dict) -> str:
    score = round(d.get("score") or 0)
    hue = _score_hue(score)
    price = fmt.euro(d.get("price"))
    ppm2 = fmt.euro_per_m2(d.get("price_per_m2"))
    hood = _esc(d.get("neighborhood") or d.get("search_area") or "—")
    region = d.get("region")
    hood_full = f"{hood} · {_esc(region)}" if region else hood

    archetype = d.get("archetype") or "Standard"
    arch_cls = _ARCHETYPE_CLASS.get(archetype, "std")

    energy = d.get("energy_class")
    en_cls = _ENERGY_BUCKET.get((energy or "").strip().upper(), "unknown")
    en_pill = f'<span class="ph-pill ph-en-{en_cls}">⚡ {_esc(energy)}</span>' if energy else ""

    # Spec chips
    specs = []
    if d.get("area_m2"):
        specs.append(f'<span class="ph-spec">{d["area_m2"]:.0f} m²</span>')
    if d.get("bedrooms"):
        specs.append(f'<span class="ph-spec">{_esc(d["bedrooms"])} bd</span>')
    fl = d.get("floor")
    if fl is not None:
        specs.append(f'<span class="ph-spec">Fl {fl:.0f}</span>')
    built = d.get("renovated_year") or d.get("year_built")
    if built:
        specs.append(f'<span class="ph-spec">{_esc(built)}</span>')
    if en_pill:
        specs.append(en_pill)

    # Signal row: value gap (only when the model actually priced it), net yield, DOM, metro.
    signals = []
    gap = d.get("value_gap_pct")
    if gap is not None:
        gcls = "pos" if gap > 0.02 else ("neg" if gap < -0.02 else "neutral")
        signals.append(
            f'<div class="ph-sig ph-sig-{gcls}"><b>{gap * 100:+.0f}%</b><span>vs model value</span></div>'
        )
    # Prefer NET yield (the honest after-cost return); fall back to gross. Rent is imputed
    # for most card-only listings, so mark those "est." rather than implying a real comp.
    est = " (est.)" if d.get("rent_estimated") else ""
    ny = d.get("net_yield")
    if ny is not None:
        signals.append(
            f'<div class="ph-sig"><b>{ny * 100:.1f}%</b><span>net yield{est}</span></div>'
        )
    else:
        gy = d.get("gross_yield")
        if gy:
            signals.append(
                f'<div class="ph-sig"><b>{gy * 100:.1f}%</b><span>gross yield{est}</span></div>'
            )
    dom = d.get("days_on_market")
    if dom is not None:
        signals.append(f'<div class="ph-sig"><b>{dom}d</b><span>on market</span></div>')
    metro = d.get("metro_distance_m")
    if metro is not None:
        # A centroid-only location gives an area-level distance, not a per-listing one —
        # label it "~" and "area" so a buyer never treats it as an exact walk time.
        approx = d.get("location_precision") != "exact"
        pfx = "~" if approx else ""
        lbl = "to metro (area)" if approx else "to metro"
        signals.append(f'<div class="ph-sig"><b>{pfx}{metro} m</b><span>{lbl}</span></div>')

    badges = "".join(
        f'<span class="ph-badge">{_esc(b)}</span>'
        for b in fmt.badges(d)
        if "NEW BUILD" not in b
        and "RENOVATED" not in b
        and "MODERN" not in b
        and "DATED" not in b
        and "LIABILITY" not in b  # archetype shown as its own pill
    )
    url = _esc(d.get("url") or "#")

    # Deal grade (A-D) + data-confidence chip — a glanceable verdict and how much to trust it.
    grade = d.get("deal_grade")
    conf = d.get("data_confidence")
    grade_html = (
        f'<span class="ph-grade ph-grade-{_esc(grade)}">{_esc(grade)}</span>' if grade else ""
    )
    conf_html = (
        f'<span class="ph-conf" title="data confidence">{conf}%<small>data</small></span>'
        if conf is not None
        else ""
    )

    # Deal thesis: the actionable recommended-offer line — the decision worth paying for.
    thesis = d.get("deal_thesis")
    thesis_html = f'<div class="ph-thesis">💡 {_esc(thesis)}</div>' if thesis else ""

    # Honest data-completeness note: say plainly what we DON'T know for this listing rather
    # than dressing gaps up as confident numbers (the single biggest trust fix from review).
    missing = d.get("data_missing") or []
    completeness_html = (
        f'<div class="ph-incomplete">⚠ Limited data — missing: {_esc(", ".join(missing))}. '
        f"Verify on the listing.</div>"
        if missing
        else ""
    )

    # Photo header: a coloured gradient placeholder always shows (so the card never
    # looks empty), with the real listing photo layered on top when it loads.
    img = d.get("image_url")
    img_layer = (
        f'<img src="{_esc(img)}" loading="lazy" alt="" '
        f'onerror="this.style.display=&quot;none&quot;">'
        if img
        else ""
    )
    photo = (
        f'<a class="ph-photo ph-photo-{arch_cls}" href="{url}" target="_blank" rel="noopener">'
        f"{img_layer}</a>"
    )

    return f"""
<div class="ph-card">
  {photo}
  <div class="ph-body">
    <div class="ph-card-head">
      <div class="ph-score" style="--hue:{hue}"><span>{score}</span><small>score</small></div>
      {grade_html}{conf_html}
      <div class="ph-price-wrap">
        <div class="ph-price">{price}</div>
        <div class="ph-ppm2">{ppm2}</div>
      </div>
      <span class="ph-arch ph-arch-{arch_cls}">{_esc(archetype)}</span>
    </div>
    <div class="ph-hood">📍 {hood_full}</div>
    <div class="ph-specs">{"".join(specs)}</div>
    <div class="ph-signals">{"".join(signals)}</div>
    {thesis_html}
    {completeness_html}
    <div class="ph-card-foot">
      <div class="ph-badges">{badges}</div>
      <a class="ph-cta" href="{url}" target="_blank" rel="noopener">View listing ↗</a>
    </div>
  </div>
</div>"""


def listing_grid(rows: list[dict]) -> None:
    """Render listings as a responsive card grid (the product view, not a dataframe)."""
    if not rows:
        return
    cards = "".join(_card_html(d) for d in rows)
    # CRITICAL: collapse all whitespace BETWEEN tags to a single stream. Streamlit renders
    # this via a CommonMark parser, which treats a blank line inside a raw-HTML block as the
    # end of that block — so an empty optional section (no thesis / no completeness note)
    # left a blank line that made the browser render the rest of every card as literal text.
    # Removing inter-tag whitespace makes that impossible.
    cards = _re.sub(r">\s+<", "><", cards)
    st.markdown(f'<div class="ph-grid">{cards}</div>', unsafe_allow_html=True)
