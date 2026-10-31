"""Single-file, self-contained HTML one-page report for a listing (backlog #27).

The deliverable a buyer's agent hands a client: header (neighborhood, price, €/m²,
area, score, grade), the key facts, the investment case (net/gross yield, cap rate,
GRM, DSCR), the total all-in acquisition cost, and the listing URL.

Pure function, no network, no DB, no external assets — all CSS is inlined so the
returned string renders standalone in any browser and prints cleanly. Never raises on
missing keys: every field uses ``.get`` with a sane fallback, and every interpolated
string is passed through ``html.escape``.
"""

from __future__ import annotations

import html

from . import picks
from .finance import acquisition_costs
from .metrics import investor_metrics
from .ui.format import euro, euro_per_m2, pct


def _esc(value: object) -> str:
    """Escape any value for safe HTML interpolation (None → em dash)."""
    if value is None:
        return "—"
    text = str(value).strip()
    return html.escape(text) if text else "—"


def _annual_rent(d: dict) -> float | None:
    rent = d.get("est_monthly_rent") or d.get("listed_rent")
    if not rent or rent <= 0:
        return None
    return float(rent) * 12


def _year(d: dict) -> str:
    """Build year built (+ renovated) label, failing soft to an em dash."""
    built = d.get("year_built")
    reno = d.get("renovated_year")
    if built and reno:
        return f"{int(built)} (renovated {int(reno)})"
    if built:
        return str(int(built))
    if reno:
        return f"renovated {int(reno)}"
    return "—"


def _metro(d: dict) -> str:
    text = picks.station_text(d)
    return _esc(text) if text else "—"


def _rows_html(pairs: list[tuple[str, str]]) -> str:
    """A definition-list body from (label, already-safe value) pairs."""
    cells = []
    for label, value in pairs:
        cells.append(f'<div class="fact"><dt>{html.escape(label)}</dt>' f"<dd>{value}</dd></div>")
    return "".join(cells)


def build_report_html(d: dict) -> str:
    """Return a self-contained HTML one-page report for the listing dict ``d``.

    ``d`` follows the shape produced by ``scout.ui.queries._row_to_dict``. Missing keys
    are tolerated: absent optional fields render as an em dash rather than raising.
    """
    d = d or {}

    price = d.get("price")
    area = d.get("area_m2")
    is_private = bool(d.get("is_private_seller"))
    annual_rent = _annual_rent(d)

    neighborhood = _esc(d.get("neighborhood") or d.get("search_area") or "Listing")
    title = _esc(d.get("title"))
    grade = _esc(d.get("deal_grade"))
    score = d.get("score")
    score_txt = f"{float(score):.0f}" if score is not None else "—"

    # Investment case — fail soft to em dashes when rent/price are unknown.
    metrics = {}
    if price and price > 0:
        try:
            metrics = investor_metrics(int(price), annual_rent, area, is_private_seller=is_private)
        except Exception:
            metrics = {}

    acq = acquisition_costs(int(price), is_private) if price and price > 0 else None
    total_cost = (price + acq) if (price and acq is not None) else None

    header_facts = _rows_html(
        [
            ("Price", _esc(euro(price))),
            ("€ / m²", _esc(euro_per_m2(d.get("price_per_m2")))),
            ("Area", f"{_esc(area)} m²" if area else "—"),
            ("Score", _esc(score_txt)),
            ("Grade", grade),
        ]
    )

    key_facts = _rows_html(
        [
            ("Bedrooms", _esc(d.get("bedrooms"))),
            ("Floor", _esc(d.get("floor"))),
            ("Year", _year(d)),
            ("Energy class", _esc(d.get("energy_class"))),
            ("Metro", _metro(d)),
        ]
    )

    investment_facts = _rows_html(
        [
            ("Net yield", _esc(pct(d.get("net_yield")))),
            ("Gross yield", _esc(pct(d.get("gross_yield")))),
            ("Cap rate", _esc(pct(metrics.get("cap_rate")))),
            (
                "GRM",
                f"{metrics['grm']:.1f}×" if metrics.get("grm") is not None else "—",
            ),
            (
                "DSCR",
                f"{metrics['dscr']:.2f}×" if metrics.get("dscr") is not None else "—",
            ),
        ]
    )

    cost_facts = _rows_html(
        [
            ("Asking price", _esc(euro(price))),
            ("Acquisition costs", _esc(euro(acq))),
            ("Total all-in cost", _esc(euro(total_cost))),
        ]
    )

    url = d.get("url")
    if url:
        safe_url = html.escape(str(url), quote=True)
        url_html = f'<a class="cta" href="{safe_url}">View original listing ↗</a>'
    else:
        url_html = '<span class="cta muted">No listing URL available</span>'

    grade_reason = _esc(d.get("deal_grade_reason"))
    thesis = _esc(d.get("deal_thesis"))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Listing report — {neighborhood}</title>
<style>
  :root {{
    --ink: #1a1f2b; --muted: #5b6472; --line: #e3e7ee;
    --brand: #14532d; --bg: #f6f7f9; --card: #ffffff;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--ink);
    font: 15px/1.5 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }}
  .page {{ max-width: 820px; margin: 24px auto; padding: 0 16px; }}
  header.hero {{
    background: var(--card); border: 1px solid var(--line); border-radius: 12px;
    padding: 24px; margin-bottom: 16px;
  }}
  .hood {{ font-size: 24px; font-weight: 700; margin: 0 0 4px; }}
  .subtitle {{ color: var(--muted); margin: 0 0 16px; }}
  .grade {{
    display: inline-block; background: var(--brand); color: #fff; font-weight: 700;
    border-radius: 8px; padding: 2px 12px; margin-left: 8px;
  }}
  section.card {{
    background: var(--card); border: 1px solid var(--line); border-radius: 12px;
    padding: 20px 24px; margin-bottom: 16px;
  }}
  h2 {{
    font-size: 13px; text-transform: uppercase; letter-spacing: .06em;
    color: var(--muted); margin: 0 0 14px; font-weight: 700;
  }}
  dl.facts {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 14px 20px; margin: 0;
  }}
  .fact dt {{ color: var(--muted); font-size: 12px; margin-bottom: 2px; }}
  .fact dd {{ margin: 0; font-size: 17px; font-weight: 600; }}
  .cta {{
    display: inline-block; margin-top: 4px; color: var(--brand);
    font-weight: 700; text-decoration: none;
  }}
  .cta.muted, .muted {{ color: var(--muted); font-weight: 400; }}
  .thesis {{ margin: 10px 0 0; color: var(--ink); }}
  footer {{ color: var(--muted); font-size: 12px; text-align: center; padding: 8px 0 24px; }}
  @media print {{
    body {{ background: #fff; }}
    .page {{ margin: 0; max-width: 100%; }}
    section.card, header.hero {{ border-color: #ccc; break-inside: avoid; }}
    .cta {{ text-decoration: underline; }}
  }}
</style>
</head>
<body>
<div class="page">
  <header class="hero">
    <h1 class="hood">{neighborhood}<span class="grade">Grade {grade}</span></h1>
    <p class="subtitle">{title}</p>
    <dl class="facts">{header_facts}</dl>
  </header>

  <section class="card">
    <h2>Key facts</h2>
    <dl class="facts">{key_facts}</dl>
  </section>

  <section class="card">
    <h2>Investment case</h2>
    <dl class="facts">{investment_facts}</dl>
    <p class="thesis">{thesis}</p>
    <p class="thesis muted">Grade rationale: {grade_reason}</p>
  </section>

  <section class="card">
    <h2>Total acquisition cost</h2>
    <dl class="facts">{cost_facts}</dl>
  </section>

  <section class="card">
    <h2>Listing</h2>
    {url_html}
  </section>

  <footer>Prepared by Holargos Scout · figures are estimates, not investment advice.</footer>
</div>
</body>
</html>"""
