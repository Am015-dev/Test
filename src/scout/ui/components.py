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

from ..recommendation import MISSING_MARKER, verdict_label
from ..strategy_fit import strategy_label
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
# Greek display labels for the archetype pill (the English value stays the data/CSS key).
_ARCHETYPE_LABEL = {
    "New build": "Νεόδμητο",
    "Renovated": "Ανακαινισμένο",
    "Modern": "Σύγχρονο",
    "Dated": "Παλαιό",
    "Energy liability": "Ενεργοβόρο",
    "Standard": "Τυπικό",
}


def archetype_label(archetype: str | None) -> str:
    """Greek label for an archetype value ("" when unknown/empty)."""
    return _ARCHETYPE_LABEL.get(archetype or "", archetype or "")


def _score_hue(score: float) -> int:
    """0 (red) → 120 (green) hue for the score chip, clamped."""
    return int(max(0.0, min(1.0, score / 70.0)) * 130)


def _esc(v) -> str:
    return _html.escape(str(v)) if v is not None else ""


def _card_html(d: dict, metric: str = "score") -> str:
    # Which value fills the big chip. Default is the investment-quality score; the Deals
    # page leads with the motivation score instead (a red "1" investment score on a
    # genuine motivated-seller lead reads as broken — the page is ranked by motivation,
    # so show motivation). The A–D grade chip still carries the quality verdict.
    if metric == "negotiation_score":
        score = round(d.get("negotiation_score") or 0)
        hue = int(max(0.0, min(1.0, score / 100.0)) * 130)
        score_label = "κίνητρο"
    else:
        score = round(d.get("score") or 0)
        hue = _score_hue(score)
        score_label = "σκορ"
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
        specs.append(f'<span class="ph-spec">{_esc(d["bedrooms"])} υ/δ</span>')
    fl = d.get("floor")
    if fl is not None:
        specs.append(f'<span class="ph-spec">Όρ. {fl:.0f}</span>')
    built = d.get("renovated_year") or d.get("year_built")
    if built:
        specs.append(f'<span class="ph-spec">{_esc(built)}</span>')
    if en_pill:
        specs.append(en_pill)

    # Signal row: honest market-position rank (cheaper than X% of comparable active
    # listings — covers ~all listings, no pseudo-precise sold-price claim), net yield,
    # DOM, metro. The hedonic model gap is demoted to the detail page as a secondary estimate.
    signals = []
    vp = d.get("value_percentile")
    if vp is not None:
        vcls = "pos" if vp > 0.55 else ("neg" if vp < 0.45 else "neutral")
        signals.append(
            f'<div class="ph-sig ph-sig-{vcls}"><b>{vp * 100:.0f}%</b>'
            f"<span>φθηνότερο από παρόμοια</span></div>"
        )
    # Prefer NET yield (the honest after-cost return); fall back to gross. Rent is imputed
    # for most card-only listings, so mark those "est." rather than implying a real comp.
    est = " (εκτ.)" if d.get("rent_estimated") else ""
    ny = d.get("net_yield")
    if ny is not None:
        signals.append(
            f'<div class="ph-sig"><b>{ny * 100:.1f}%</b><span>καθαρή απόδοση{est}</span></div>'
        )
    else:
        gy = d.get("gross_yield")
        if gy:
            signals.append(
                f'<div class="ph-sig"><b>{gy * 100:.1f}%</b><span>μικτή απόδοση{est}</span></div>'
            )
    # A raw yield % means nothing without area context — 5.5% is exceptional in a prime
    # low-yield neighborhood, mediocre in a peripheral high-yield one. This ranks it
    # against comparable ACTIVE listings in the SAME area, same treatment as "cheaper
    # than peers" above, instead of a flat national threshold.
    yp = d.get("yield_percentile")
    if yp is not None:
        ycls = "pos" if yp > 0.55 else ("neg" if yp < 0.45 else "neutral")
        signals.append(
            f'<div class="ph-sig ph-sig-{ycls}"><b>{yp * 100:.0f}%</b>'
            f"<span>υψηλότερη απόδοση από παρόμοια</span></div>"
        )
    dom = d.get("days_on_market")
    if dom is not None:
        signals.append(f'<div class="ph-sig"><b>{dom} ημ.</b><span>στην αγορά</span></div>')
    metro = d.get("metro_distance_m")
    if metro is not None:
        # A centroid-only location gives an area-level distance, not a per-listing one —
        # label it "~" and "area" so a buyer never treats it as an exact walk time.
        approx = d.get("location_precision") != "exact"
        pfx = "~" if approx else ""
        lbl = "ως το μετρό (περιοχή)" if approx else "ως το μετρό"
        signals.append(f'<div class="ph-sig"><b>{pfx}{metro} m</b><span>{lbl}</span></div>')

    # Keep only temporal/status badges (NEW, PRICE ↓, RELISTED, RENTED, PRIVATE). Archetype
    # has its own pill, and OPPORTUNITY / NEGOTIABLE now duplicate the Underpriced / Motivated
    # strategy tags above — drop them so the card isn't double-signalling the same thing.
    badges = "".join(
        f'<span class="ph-badge">{_esc(b)}</span>'
        for b in fmt.badges(d)
        if b not in fmt.CARD_HIDDEN_BADGES
    )
    url = _esc(d.get("url") or "#")

    # Strategy-fit tags (Cashflow / Value-add / Underpriced / Motivated seller / Prime
    # location) — the one-glance "what kind of play is this?" a buyer filters on.
    strat = d.get("strategy_tags") or []
    strat_html = (
        '<div class="ph-strats">'
        + "".join(f'<span class="ph-strat">{_esc(strategy_label(t))}</span>' for t in strat)
        + "</div>"
        if strat
        else ""
    )

    # Deal grade (A-D) + data-confidence chip — a glanceable verdict and how much to trust it.
    grade = d.get("deal_grade")
    conf = d.get("data_confidence")
    grade_html = (
        f'<span class="ph-grade ph-grade-{_esc(grade)}">{_esc(grade)}</span>' if grade else ""
    )
    conf_html = (
        f'<span class="ph-conf" title="αξιοπιστία δεδομένων">{conf}%<small>δεδ.</small></span>'
        if conf is not None
        else ""
    )

    # The recommendation — the BUY/WATCH/PASS verdict + concrete action. This is the
    # decision a subscriber pays for; it replaces the old bare "offer" thesis.
    rec_v = d.get("rec_verdict")
    rec_h = d.get("rec_headline") or d.get("deal_thesis")
    if rec_v and rec_h:
        thesis_html = (
            f'<div class="ph-rec ph-rec-{_esc(rec_v)}">'
            f'<span class="ph-rec-badge">{_esc(verdict_label(rec_v))}</span> {_esc(rec_h)}</div>'
        )
    elif d.get("deal_thesis"):
        thesis_html = f'<div class="ph-thesis">💡 {_esc(d["deal_thesis"])}</div>'
    else:
        thesis_html = ""

    # Honest data-completeness note: say plainly what we DON'T know for this listing rather
    # than dressing gaps up as confident numbers (the single biggest trust fix from review).
    # Skip it when the recommendation headline is a "Έλεγξε πρώτα — … λείπουν: …" cap: that
    # headline already carries the exact same list, and saying it twice reads as clutter.
    rec_says_missing = bool(rec_h) and MISSING_MARKER in rec_h
    missing = d.get("data_missing") or []
    completeness_html = (
        f'<div class="ph-incomplete">⚠ Ελλιπή στοιχεία — λείπουν: {_esc(", ".join(missing))}. '
        f"Επιβεβαίωσε στην αγγελία.</div>"
        if missing and not rec_says_missing
        else ""
    )

    # Internal-consistency notes: the listing's own numbers contradict each other (e.g. a
    # €424/m² "flat" or A+ energy on a 1960 build). Warn to verify — never hide the listing.
    # Same de-dup: a consistency-capped headline already quotes the first flag verbatim.
    cflags = d.get("consistency_flags") or []
    if rec_h and cflags and cflags[0] in rec_h:
        cflags = cflags[1:]
    consistency_html = (
        f'<div class="ph-inconsistent">⚠ Έλεγχος: {_esc("; ".join(cflags))}.</div>'
        if cflags
        else ""
    )

    # Data-quality guard: the listing's numbers look like a DATA ERROR (a whole building
    # priced as a flat, a future year, an off-by-10x €/m²). This is WHY the ranking demoted
    # it — badge it loudly, never hide it. Reuses the ph-inconsistent warning style.
    dqflags = d.get("data_quality_flags") or []
    data_quality_html = (
        f'<div class="ph-inconsistent">⚠️ Ύποπτα στοιχεία: {_esc("; ".join(dqflags))}.</div>'
        if dqflags
        else ""
    )

    # Header strip. When we have a real listing photo we show it full-bleed (96px).
    # When we DON'T (most card-only listings), a big empty gradient block just makes
    # every card look unfinished — so we collapse to a thin archetype-coloured accent
    # bar instead. Same colour language, a fraction of the visual weight.
    img = d.get("image_url")
    if img:
        photo = (
            f'<a class="ph-photo ph-photo-{arch_cls}" href="{url}" target="_blank" rel="noopener">'
            f'<img src="{_esc(img)}" loading="lazy" alt="" '
            f'onerror="this.style.display=&quot;none&quot;"></a>'
        )
    else:
        photo = f'<a class="ph-accent ph-photo-{arch_cls}" href="{url}" target="_blank" rel="noopener"></a>'

    return f"""
<div class="ph-card">
  {photo}
  <div class="ph-body">
    <div class="ph-card-head">
      <div class="ph-score" style="--hue:{hue}"><span>{score}</span><small>{score_label}</small></div>
      {grade_html}{conf_html}
      <div class="ph-price-wrap">
        <div class="ph-price">{price}</div>
        <div class="ph-ppm2">{ppm2}</div>
      </div>
      <span class="ph-arch ph-arch-{arch_cls}">{_esc(archetype_label(archetype))}</span>
    </div>
    <div class="ph-hood">📍 {hood_full}</div>
    <div class="ph-specs">{"".join(specs)}</div>
    <div class="ph-signals">{"".join(signals)}</div>
    {strat_html}
    {thesis_html}
    {completeness_html}
    {consistency_html}
    {data_quality_html}
    <div class="ph-card-foot">
      <div class="ph-badges">{badges}</div>
      <a class="ph-cta" href="{url}" target="_blank" rel="noopener">Δες την αγγελία ↗</a>
    </div>
  </div>
</div>"""


def listing_grid(rows: list[dict], metric: str = "score") -> None:
    """Render listings as a responsive card grid (the product view, not a dataframe).

    ``metric`` selects the big chip: "score" (investment quality, default) or
    "negotiation_score" (seller motivation, used by the Deals page)."""
    if not rows:
        return
    cards = "".join(_card_html(d, metric=metric) for d in rows)
    # CRITICAL: collapse all whitespace BETWEEN tags to a single stream. Streamlit renders
    # this via a CommonMark parser, which treats a blank line inside a raw-HTML block as the
    # end of that block — so an empty optional section (no thesis / no completeness note)
    # left a blank line that made the browser render the rest of every card as literal text.
    # Removing inter-tag whitespace makes that impossible.
    cards = _re.sub(r">\s+<", "><", cards)
    st.markdown(f'<div class="ph-grid">{cards}</div>', unsafe_allow_html=True)
