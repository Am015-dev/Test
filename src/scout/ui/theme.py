"""Visual theme for the Streamlit app — one call, ``inject_css()``, that turns the
default Streamlit look into a calm, premium proptech UI.

Design intent: Linear / Stripe / Notion-level restraint. Deep slate/navy text on a
clean off-white canvas, a single restrained teal accent, a clear type scale, and
soft-elevation "stat card" tiles. Nothing flashy.

Everything here is self-contained: a **system font stack only** (no web fonts /
CDNs — the app runs offline behind a strict CSP) and inline CSS. Selectors prefer
stable ``[data-testid=...]`` hooks and semantic tags so the styling survives
Streamlit's frequent CSS class-name churn.

Usage (wired by app.py — this module only exposes the function):

    from scout.ui.theme import inject_css
    inject_css()
"""

from __future__ import annotations

import streamlit as st

# System font stack — resolves to the platform's native UI face everywhere,
# so it renders crisply with zero network access.
_FONT_STACK = (
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, "
    "'Apple Color Emoji', 'Segoe UI Emoji', sans-serif"
)

# Palette — kept in one place so the whole sheet stays coherent.
#   ink      : primary text / headings (deep slate-navy)
#   muted    : secondary text, captions, metric labels
#   accent   : the single restrained teal used for emphasis
#   surface  : card / panel background (crisp white on the off-white canvas)
#   line     : hairline borders
#   canvas   : app background (matches config.toml backgroundColor)
_CSS = f"""
<style>
:root {{
    --hg-ink:      #0F172A;   /* slate-900  — headings & body text            */
    --hg-ink-soft: #1E293B;   /* slate-800  — body on cards                   */
    --hg-muted:    #64748B;   /* slate-500  — captions, labels                */
    --hg-faint:    #94A3B8;   /* slate-400  — least-important text            */
    --hg-accent:   #0F766E;   /* teal-700   — the one accent                  */
    --hg-accent-2: #0D9488;   /* teal-600   — hover / lighter accent          */
    --hg-surface:  #FFFFFF;   /* card surface                                 */
    --hg-canvas:   #F7F9FC;   /* app background                               */
    --hg-line:     #E2E8F0;   /* slate-200  — hairline borders                */
    --hg-line-2:   #EDF1F6;   /* even softer separators                       */
    --hg-shadow:   0 1px 2px rgba(15,23,42,.04), 0 6px 20px rgba(15,23,42,.06);
    --hg-shadow-h: 0 2px 4px rgba(15,23,42,.06), 0 16px 34px rgba(15,23,42,.10);
    --hg-radius:   12px;
}}

/* ------------------------------------------------------------------ *
 * Typography — one clear type scale, comfortable rhythm.
 * ------------------------------------------------------------------ */
html, body, [class*="css"], [class*="st-"],
[data-testid="stAppViewContainer"], [data-testid="stSidebar"] {{
    font-family: {_FONT_STACK};
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    text-rendering: optimizeLegibility;
}}
[data-testid="stAppViewContainer"] {{ color: var(--hg-ink-soft); }}

h1, h2, h3, h4, h5, h6 {{
    color: var(--hg-ink);
    font-weight: 650;
    letter-spacing: -0.01em;
    line-height: 1.2;
}}
/* App title (st.title) — the brand line. */
h1 {{ font-size: 1.85rem; font-weight: 700; letter-spacing: -0.02em; margin-bottom: .35rem; }}
h2 {{ font-size: 1.35rem; margin-top: .4rem; }}
/* st.subheader */
h3 {{ font-size: 1.12rem; }}
/* markdown "#### …" section heads */
h4 {{ font-size: 0.98rem; letter-spacing: .002em; margin: .2rem 0 .4rem; }}

p, li, [data-testid="stMarkdownContainer"] {{ line-height: 1.6; }}

/* Captions & small print — quiet, not shouty. */
[data-testid="stCaptionContainer"], .stCaption, small {{
    color: var(--hg-muted);
    font-size: 0.82rem;
    line-height: 1.5;
}}

/* Comfortable main-column width & padding so content breathes. */
[data-testid="stMainBlockContainer"], .block-container {{
    padding-top: 2.4rem;
    padding-bottom: 3rem;
    max-width: 1280px;
}}

/* ------------------------------------------------------------------ *
 * Section dividers (st.divider) — a hairline, not a heavy rule.
 * ------------------------------------------------------------------ */
hr, [data-testid="stDivider"] {{
    border: none;
    border-top: 1px solid var(--hg-line);
    margin: 1.4rem 0;
}}

/* ------------------------------------------------------------------ *
 * Bordered containers — the "Top picks" cards.
 * st.container(border=True) => stVerticalBlockBorderWrapper
 * ------------------------------------------------------------------ */
[data-testid="stVerticalBlockBorderWrapper"] {{
    background: var(--hg-surface);
    border: 1px solid var(--hg-line);
    border-radius: var(--hg-radius);
    padding: 1.15rem 1.25rem;
    box-shadow: var(--hg-shadow);
    transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease;
}}
[data-testid="stVerticalBlockBorderWrapper"]:hover {{
    transform: translateY(-3px);
    box-shadow: var(--hg-shadow-h);
    border-color: #CBD5E1;
}}
/* Price headline inside a pick card sits tight to its meta caption. */
[data-testid="stVerticalBlockBorderWrapper"] h3 {{
    margin-bottom: .1rem;
    color: var(--hg-ink);
}}

/* ------------------------------------------------------------------ *
 * Metric tiles (st.metric) — turned into clean stat cards.
 * label: small / uppercase / muted   value: large / bold / ink
 * ------------------------------------------------------------------ */
[data-testid="stMetric"] {{
    background: var(--hg-surface);
    border: 1px solid var(--hg-line);
    border-radius: var(--hg-radius);
    padding: .85rem 1.05rem .95rem;
    box-shadow: var(--hg-shadow);
    transition: box-shadow .16s ease, transform .16s ease;
}}
[data-testid="stMetric"]:hover {{
    box-shadow: var(--hg-shadow-h);
    transform: translateY(-1px);
}}
[data-testid="stMetricLabel"] {{
    font-size: .70rem !important;
    font-weight: 600;
    letter-spacing: .06em;
    text-transform: uppercase;
    color: var(--hg-muted);
}}
[data-testid="stMetricLabel"] p {{ color: var(--hg-muted); }}
[data-testid="stMetricValue"] {{
    font-size: 1.7rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: var(--hg-ink);
    line-height: 1.15;
}}
[data-testid="stMetricDelta"] {{ font-size: .8rem; font-weight: 600; }}
/* Metrics that live inside a card shouldn't double up borders/shadows. */
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMetric"] {{
    border: none;
    box-shadow: none;
    background: transparent;
    padding: 0;
}}

/* ------------------------------------------------------------------ *
 * Progress bars (score gauges) — slimmer track, rounded, teal fill
 * (fill colour comes from primaryColor in config.toml).
 * ------------------------------------------------------------------ */
[data-testid="stProgress"] > div > div {{
    background-color: var(--hg-line);
    border-radius: 999px;
}}
[data-testid="stProgress"] > div > div > div {{ border-radius: 999px; }}

/* ------------------------------------------------------------------ *
 * Sidebar — tighten, add a hairline separator, quiet the surface.
 * ------------------------------------------------------------------ */
[data-testid="stSidebar"] {{
    background: var(--hg-canvas);
    border-right: 1px solid var(--hg-line);
}}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{
    padding-top: 1.4rem;
}}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {{ font-size: 1rem; letter-spacing: 0; }}
[data-testid="stSidebar"] .stRadio label {{ font-size: .92rem; }}

/* ------------------------------------------------------------------ *
 * Buttons & link-buttons — solid, calm, slightly rounded.
 * ------------------------------------------------------------------ */
.stButton > button, .stLinkButton > a, [data-testid="stBaseButton-secondary"] {{
    border-radius: 9px;
    border: 1px solid var(--hg-line);
    font-weight: 600;
    transition: background .14s ease, border-color .14s ease,
                box-shadow .14s ease, transform .05s ease;
}}
.stButton > button:hover, .stLinkButton > a:hover {{
    border-color: var(--hg-accent);
    color: var(--hg-accent);
}}
.stButton > button:active {{ transform: translateY(1px); }}
/* Primary buttons use the accent as a solid fill. */
[data-testid="stBaseButton-primary"] {{
    background: var(--hg-accent);
    border-color: var(--hg-accent);
    color: #fff;
}}
[data-testid="stBaseButton-primary"]:hover {{
    background: var(--hg-accent-2);
    border-color: var(--hg-accent-2);
}}

/* Links pick up the accent, not browser blue. */
a, [data-testid="stMarkdownContainer"] a {{ color: var(--hg-accent); }}
a:hover {{ color: var(--hg-accent-2); }}

/* ------------------------------------------------------------------ *
 * Dataframes & tables — crisp header, soft row separation, rounded frame.
 * (The grid body is a canvas widget; we style the frame + the classic
 *  st.table markup, which is all CSS can reliably reach.)
 * ------------------------------------------------------------------ */
[data-testid="stDataFrame"], [data-testid="stTable"] {{
    border: 1px solid var(--hg-line);
    border-radius: var(--hg-radius);
    overflow: hidden;
    box-shadow: var(--hg-shadow);
}}
[data-testid="stTable"] table {{ border-collapse: collapse; width: 100%; }}
[data-testid="stTable"] thead th {{
    background: var(--hg-canvas);
    color: var(--hg-muted);
    font-size: .74rem;
    font-weight: 600;
    letter-spacing: .04em;
    text-transform: uppercase;
    border-bottom: 1px solid var(--hg-line);
    padding: .55rem .75rem;
}}
[data-testid="stTable"] tbody td {{
    border-bottom: 1px solid var(--hg-line-2);
    padding: .5rem .75rem;
    color: var(--hg-ink-soft);
}}
[data-testid="stTable"] tbody tr:last-child td {{ border-bottom: none; }}

/* ------------------------------------------------------------------ *
 * Tabs, expanders & alerts — softened corners, quieter chrome.
 * ------------------------------------------------------------------ */
[data-testid="stExpander"] {{
    border: 1px solid var(--hg-line);
    border-radius: var(--hg-radius);
    box-shadow: var(--hg-shadow);
    background: var(--hg-surface);
}}
[data-testid="stExpander"] summary:hover {{ color: var(--hg-accent); }}

[data-testid="stAlert"] {{
    border-radius: 10px;
    border: 1px solid var(--hg-line);
}}

/* Inputs / select boxes — consistent radius with the rest of the system. */
[data-baseweb="input"], [data-baseweb="select"] > div {{
    border-radius: 9px;
}}

/* Hide ALL default Streamlit chrome for a clean, product-like frame. */
#MainMenu, [data-testid="stDecoration"], [data-testid="stStatusWidget"] {{ display: none !important; }}
[data-testid="stToolbar"], [data-testid="stToolbarActions"] {{ display: none !important; }}
[data-testid="stAppDeployButton"], .stDeployButton, [data-testid="stHeader"] {{ display: none !important; }}
header[data-testid="stHeader"] {{ display: none !important; }}
footer {{ visibility: hidden; height: 0; }}
[data-testid="stMainBlockContainer"] {{ padding-top: 2.2rem; }}

/* ------------------------------------------------------------------ *
 * Listing card grid — the product view (replaces the raw dataframe).
 * ------------------------------------------------------------------ */
.ph-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 18px;
    margin: 8px 0 4px;
}}
.ph-card {{
    background: var(--hg-surface);
    border: 1px solid var(--hg-line);
    border-radius: 16px;
    padding: 18px 18px 14px;
    box-shadow: var(--hg-shadow);
    display: flex; flex-direction: column; gap: 12px;
    transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease;
}}
.ph-card:hover {{ transform: translateY(-3px); box-shadow: var(--hg-shadow-h); border-color: #CBD5E1; }}
.ph-card-head {{ display: flex; align-items: center; gap: 14px; }}
.ph-score {{
    flex: 0 0 auto; width: 52px; height: 52px; border-radius: 14px;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    background: hsl(var(--hue), 62%, 94%); color: hsl(var(--hue), 70%, 28%);
    border: 1px solid hsl(var(--hue), 55%, 84%);
}}
.ph-score span {{ font-size: 1.25rem; font-weight: 750; line-height: 1; }}
.ph-score small {{ font-size: .56rem; text-transform: uppercase; letter-spacing: .06em; opacity: .8; }}
.ph-price-wrap {{ flex: 1 1 auto; min-width: 0; }}
.ph-price {{ font-size: 1.5rem; font-weight: 750; color: var(--hg-ink); line-height: 1.1; }}
.ph-ppm2 {{ font-size: .82rem; color: var(--hg-muted); margin-top: 2px; }}
.ph-arch {{
    flex: 0 0 auto; font-size: .68rem; font-weight: 650; padding: 4px 9px; border-radius: 999px;
    text-transform: uppercase; letter-spacing: .03em; white-space: nowrap;
}}
.ph-arch-new {{ background: #DCFCE7; color: #15803D; }}
.ph-arch-reno {{ background: #DBEAFE; color: #1D4ED8; }}
.ph-arch-modern {{ background: #E0F2FE; color: #0369A1; }}
.ph-arch-dated {{ background: #F1F5F9; color: #64748B; }}
.ph-arch-liability {{ background: #FEE2E2; color: #B91C1C; }}
.ph-arch-std {{ background: #F1F5F9; color: #64748B; }}
.ph-hood {{ font-size: .9rem; color: var(--hg-ink-soft); font-weight: 550; margin-top: -2px; }}
.ph-specs {{ display: flex; flex-wrap: wrap; gap: 6px; }}
.ph-spec {{ font-size: .76rem; color: var(--hg-ink-soft); background: var(--hg-canvas);
    border: 1px solid var(--hg-line-2); border-radius: 7px; padding: 3px 8px; }}
.ph-pill {{ font-size: .72rem; font-weight: 650; border-radius: 7px; padding: 3px 8px; }}
.ph-en-good {{ background: #DCFCE7; color: #15803D; }}
.ph-en-mid {{ background: #FEF9C3; color: #A16207; }}
.ph-en-poor {{ background: #FFEDD5; color: #C2410C; }}
.ph-en-bad {{ background: #FEE2E2; color: #B91C1C; }}
.ph-en-unknown {{ background: #F1F5F9; color: #64748B; }}
.ph-signals {{ display: flex; gap: 8px; border-top: 1px solid var(--hg-line-2);
    border-bottom: 1px solid var(--hg-line-2); padding: 10px 0; }}
.ph-sig {{ flex: 1; display: flex; flex-direction: column; gap: 1px; }}
.ph-sig b {{ font-size: 1rem; font-weight: 700; color: var(--hg-ink); }}
.ph-sig span {{ font-size: .66rem; color: var(--hg-muted); text-transform: uppercase; letter-spacing: .03em; }}
.ph-sig-pos b {{ color: #15803D; }}
.ph-sig-neg b {{ color: #B91C1C; }}
.ph-card-foot {{ display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 2px; }}
.ph-badges {{ display: flex; flex-wrap: wrap; gap: 5px; }}
.ph-badge {{ font-size: .66rem; font-weight: 600; color: var(--hg-accent);
    background: #ECFDF5; border-radius: 6px; padding: 3px 7px; }}
.ph-cta {{ flex: 0 0 auto; font-size: .8rem; font-weight: 650; color: #fff !important;
    background: var(--hg-accent); border-radius: 9px; padding: 7px 13px; text-decoration: none !important;
    white-space: nowrap; transition: background .15s ease; }}
.ph-cta:hover {{ background: var(--hg-accent-2); }}

/* ------------------------------------------------------------------ *
 * Sidebar navigation — turn the default radio into a clean nav menu.
 * ------------------------------------------------------------------ */
[data-testid="stSidebar"] [role="radiogroup"] {{ gap: 2px; }}
[data-testid="stSidebar"] [role="radiogroup"] label {{
    display: flex; align-items: center; width: 100%;
    padding: 9px 12px; border-radius: 9px; cursor: pointer;
    font-size: .92rem; font-weight: 550; color: var(--hg-ink-soft);
    transition: background .12s ease, color .12s ease;
}}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {{ background: #E7EDF4; }}
/* hide the radio dot itself */
[data-testid="stSidebar"] [role="radiogroup"] label > div:first-child {{ display: none; }}
/* selected item — teal pill */
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {{
    background: var(--hg-accent); color: #fff;
}}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p {{ color: #fff; font-weight: 650; }}
</style>
"""


def inject_css() -> None:
    """Inject the app's global CSS. Call once, early in ``main()`` (after
    ``st.set_page_config``). Idempotent and side-effect-only."""
    st.markdown(_CSS, unsafe_allow_html=True)
