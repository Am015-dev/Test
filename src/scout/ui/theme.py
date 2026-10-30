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
/* Apply the UI font to the app containers and let it inherit to text. Do NOT use a
 * broad [class*="st-"] selector — it also matches Streamlit's Material Symbols icon
 * <span>s and overrides their icon font, so ligatures like "keyboard_arrow_right" and
 * the sidebar-collapse chevron render as raw TEXT instead of glyphs. */
html, body,
[data-testid="stAppViewContainer"], [data-testid="stSidebar"],
[data-testid="stMarkdownContainer"], [data-testid="stHeading"],
button, input, select, textarea, p, label {{
    font-family: {_FONT_STACK};
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    text-rendering: optimizeLegibility;
}}
/* Belt-and-suspenders: never let the UI font touch Streamlit's Material Symbols icon
 * elements (expander chevrons, sidebar collapse), or their ligatures render as raw
 * text like "keyboard_arrow_right". */
[data-testid="stIconMaterial"], .material-symbols-rounded,
span[class*="material-symbols"] {{
    font-family: "Material Symbols Rounded", "Material Symbols Outlined" !important;
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
/* No text-transform: uppercase — on a lang="en" page Chrome keeps the Greek accents
 * ("ΑΓΑΠΗΜΈΝΑ"), which is wrong Greek typography. */
[data-testid="stMetricLabel"] {{
    font-size: .78rem !important;
    font-weight: 600;
    color: var(--hg-muted);
}}
[data-testid="stMetricLabel"] p {{ color: var(--hg-muted); }}
[data-testid="stMetricValue"] {{
    font-size: 1.35rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: var(--hg-ink);
    line-height: 1.15;
}}
[data-testid="stMetricDelta"] {{ font-size: .8rem; font-weight: 600; }}
/* Wrap long values ("cheaper than area") instead of truncating them to "chea…". */
[data-testid="stMetric"] {{ min-width: 0; }}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] * {{
    white-space: normal !important; text-overflow: clip !important; overflow-wrap: normal;
    min-width: 0; max-width: 100%;
}}
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

/* Hide the default Streamlit chrome for a clean, product-like frame — but KEEP the header
 * itself: it holds the "open sidebar" button, the only way to reach the menu on a phone
 * (the sidebar starts collapsed there) or after collapsing it on desktop. */
#MainMenu, [data-testid="stDecoration"], [data-testid="stStatusWidget"] {{ display: none !important; }}
[data-testid="stToolbarActions"], [data-testid="stMainMenu"] {{ display: none !important; }}
[data-testid="stAppDeployButton"], .stDeployButton {{ display: none !important; }}
header[data-testid="stHeader"] {{
    background: transparent; height: auto; min-height: 0; pointer-events: none;
}}
header[data-testid="stHeader"] [data-testid="stExpandSidebarButton"] {{
    pointer-events: auto; background: var(--hg-surface); border: 1px solid var(--hg-line);
    border-radius: 10px; box-shadow: var(--hg-shadow); margin: 8px 0 0 4px;
    color: var(--hg-ink);
}}
footer {{ visibility: hidden; height: 0; }}
[data-testid="stMainBlockContainer"] {{ padding-top: 2.2rem; }}
@media (max-width: 640px) {{
    [data-testid="stMainBlockContainer"] {{ padding: 3.1rem 1rem 2rem; }}
}}

/* ------------------------------------------------------------------ *
 * Listing card grid — the product view (replaces the raw dataframe).
 * ------------------------------------------------------------------ */
.ph-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 18px;
    margin: 8px 0 4px;
}}
/* On phones a 340px min column overflows the viewport and forces a horizontal scroll;
   drop to a single full-width column so cards stay readable and never clip. */
@media (max-width: 640px) {{
    .ph-grid {{ grid-template-columns: 1fr; gap: 12px; }}
}}
.ph-card {{
    background: var(--hg-surface);
    border: 1px solid var(--hg-line);
    border-radius: 16px;
    box-shadow: var(--hg-shadow);
    display: flex; flex-direction: column;
    overflow: hidden;
    transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease;
}}
.ph-body {{ padding: 15px 18px 14px; display: flex; flex-direction: column; gap: 12px; }}
.ph-card:hover {{ transform: translateY(-3px); box-shadow: var(--hg-shadow-h); border-color: #CBD5E1; }}

/* Photo header: gradient placeholder (always visible) + real image on top. */
.ph-photo {{
    display: block; position: relative; height: 96px; width: 100%;
    background: linear-gradient(135deg, #64748B, #94A3B8);
}}
.ph-photo-new {{ background: linear-gradient(135deg, #15803D, #4ADE80); }}
.ph-photo-reno {{ background: linear-gradient(135deg, #1D4ED8, #60A5FA); }}
.ph-photo-modern {{ background: linear-gradient(135deg, #0369A1, #38BDF8); }}
.ph-photo-liability {{ background: linear-gradient(135deg, #B91C1C, #F87171); }}
.ph-photo-dated, .ph-photo-std {{ background: linear-gradient(135deg, #64748B, #94A3B8); }}
.ph-photo img {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }}
/* No-photo header: a thin archetype-coloured accent bar so the card reads finished
   without a big empty image block (most card-only listings have no photo). */
.ph-accent {{ display: block; height: 6px; width: 100%; }}
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
.ph-grade {{ font-size: 1rem; font-weight: 800; color: #fff; border-radius: 8px;
    padding: 2px 9px; align-self: center; }}
.ph-grade-A {{ background: #15803D; }}
.ph-grade-B {{ background: #65A30D; }}
.ph-grade-C {{ background: #CA8A04; }}
.ph-grade-D {{ background: #9CA3AF; }}
.ph-conf {{ display: flex; flex-direction: column; align-items: center; font-size: .8rem;
    font-weight: 700; color: var(--hg-muted); align-self: center; line-height: 1; }}
.ph-conf small {{ font-size: .55rem; text-transform: uppercase; letter-spacing: .03em; }}
.ph-thesis {{ font-size: .8rem; line-height: 1.35; color: var(--hg-ink);
    background: #FFF7ED; border: 1px solid #FED7AA; border-radius: 9px;
    padding: 8px 10px; margin: 2px 0; }}
.ph-incomplete {{ font-size: .72rem; line-height: 1.3; color: #92400E;
    background: #FEFCE8; border: 1px solid #FEF08A; border-radius: 8px;
    padding: 6px 9px; margin: 2px 0; }}
/* The recommendation line — BUY/WATCH/PASS verdict + concrete action. */
.ph-rec {{ font-size: .8rem; line-height: 1.35; border-radius: 10px; padding: 8px 11px;
    margin: 2px 0; display: flex; gap: 8px; align-items: baseline; }}
.ph-rec-badge {{ font-size: .66rem; font-weight: 800; letter-spacing: .04em;
    padding: 2px 7px; border-radius: 999px; flex: 0 0 auto; color: #fff; }}
.ph-rec-BUY {{ background: #ECFDF5; color: #065F46; border: 1px solid #A7F3D0; }}
.ph-rec-BUY .ph-rec-badge {{ background: #059669; }}
.ph-rec-WATCH {{ background: #FEFCE8; color: #854D0E; border: 1px solid #FDE68A; }}
.ph-rec-WATCH .ph-rec-badge {{ background: #CA8A04; }}
.ph-rec-PASS {{ background: #FEF2F2; color: #991B1B; border: 1px solid #FECACA; }}
.ph-rec-PASS .ph-rec-badge {{ background: #DC2626; }}
/* Strategy-fit tags: small teal chips summarising the investment angle. */
.ph-strats {{ display: flex; flex-wrap: wrap; gap: 5px; margin: 2px 0; }}
.ph-strat {{ font-size: .68rem; font-weight: 600; color: #0F766E; background: #CCFBF1;
    border: 1px solid #99F6E4; border-radius: 999px; padding: 2px 9px; }}
/* Internal-consistency warning: stronger (rose) than the limited-data note — the numbers
   themselves look wrong, not merely absent. */
.ph-inconsistent {{ font-size: .72rem; line-height: 1.3; color: #9F1239;
    background: #FFF1F2; border: 1px solid #FECDD3; border-radius: 8px;
    padding: 6px 9px; margin: 2px 0; }}
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
/* hide the radio dot itself (label > [hidden input span] + div > [dot div, text div]) */
[data-testid="stSidebar"] [role="radiogroup"] label > div:first-child,
[data-testid="stSidebar"] [data-testid="stRadioOption"] > div > div:first-child:not(:has(p)) {{
    display: none;
}}
/* selected item — teal pill */
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {{
    background: var(--hg-accent); color: #fff;
}}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p {{ color: #fff; font-weight: 650; }}

/* ------------------------------------------------------------------ *
 * Metric rows on phones: two tiles per row instead of one tall stack.
 * ------------------------------------------------------------------ */
@media (max-width: 640px) {{
    [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] [data-testid="stMetric"]) {{
        flex-direction: row !important; flex-wrap: wrap !important; gap: .6rem !important;
    }}
    [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] [data-testid="stMetric"])
        > [data-testid="stColumn"] {{
        flex: 1 1 calc(50% - .6rem) !important; min-width: calc(50% - .6rem) !important;
        width: auto !important;
    }}
    [data-testid="stMetricValue"] {{ font-size: 1.2rem; }}
    [data-testid="stMetric"] {{ padding: .7rem .8rem; }}
}}

/* ------------------------------------------------------------------ *
 * Buyer pages (buyer.py): search hero, example chips, result cards.
 * ------------------------------------------------------------------ */
.st-key-hero {{
    background: linear-gradient(180deg, #FFFFFF 0%, #F2FBF9 100%);
    border: 1px solid var(--hg-line); border-radius: 18px; box-shadow: var(--hg-shadow);
    padding: 1.6rem 1.8rem 1.3rem; margin-bottom: .6rem; gap: .7rem;
}}
.st-key-hero [data-testid="stCaptionContainer"] {{ margin-top: -.55rem; }}
.st-key-hero h2 {{ font-size: 1.75rem; font-weight: 750; letter-spacing: -0.02em;
    margin: 0 0 .1rem; padding: 0; }}
.st-key-hero [data-baseweb="input"] {{ background: #fff; border: 1.5px solid #CBD5E1;
    border-radius: 12px; }}
.st-key-hero [data-baseweb="input"]:focus-within {{ border-color: var(--hg-accent); }}
.st-key-hero [data-baseweb="input"] input {{ font-size: 1rem; padding: .7rem .8rem;
    background: #fff; }}
.st-key-hero [data-testid="stFormSubmitButton"] button {{ min-height: 2.9rem;
    border-radius: 12px; font-size: 1rem; }}
.st-key-examples {{ align-items: center; row-gap: .45rem; }}
.hg-try {{ font-size: .8rem; color: var(--hg-muted); font-weight: 600; }}
.st-key-examples button {{
    border-radius: 999px !important; min-height: 0 !important; padding: .25rem .75rem !important;
    background: #fff; border: 1px solid #CCE7E2 !important; color: var(--hg-accent) !important;
}}
.st-key-examples button p {{ font-size: .82rem !important; font-weight: 600; }}
.st-key-examples button:hover {{ background: #ECFDF8; border-color: var(--hg-accent) !important; }}

/* "Κατάλαβα:" — the parsed filters as chips. */
.hg-understood {{ display: flex; flex-wrap: wrap; align-items: center; gap: 6px;
    font-size: .88rem; }}
.hg-understood b {{ color: var(--hg-ink); margin-right: 2px; }}
.hg-understood span {{ background: #E6F4F1; color: #115E59; border-radius: 999px;
    padding: 3px 10px; font-weight: 550; }}
.hg-count {{ font-size: .95rem; color: var(--hg-muted); }}
.hg-count b {{ color: var(--hg-ink); font-size: 1.05rem; }}

/* Result card: a keyed bordered container, so the styling stays scoped to it. */
[class*="st-key-card-"] {{ padding: 1rem 1.15rem .9rem !important; gap: .45rem !important;
    border-radius: 14px !important; }}
/* Streamlit gives markdown a -1rem bottom margin to cancel the last <p>'s margin; our blocks
   are divs/headings, so that would make the next row overlap them. */
[class*="st-key-card-"] [data-testid="stMarkdownContainer"],
.st-key-hero [data-testid="stMarkdownContainer"], .st-key-examples [data-testid="stMarkdownContainer"],
[data-testid="stMarkdownContainer"]:has(> .hg-understood, > .hg-count) {{ margin-bottom: 0; }}
[class*="st-key-card-"] [data-testid="stMarkdownContainer"] p:last-child,
.st-key-examples [data-testid="stMarkdownContainer"] p:last-child {{ margin-bottom: 0; }}
[class*="st-key-card-"] h3 {{ font-size: 1.55rem; font-weight: 750; letter-spacing: -0.02em;
    margin: 0; padding: 0; line-height: 1.15; }}
.hg-photo {{ display: block; width: 100%; height: 180px; object-fit: cover;
    border-radius: 10px; background: var(--hg-line-2); }}
.hg-head {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 10px;
    line-height: 1.35; }}
.hg-title {{ font-size: .98rem; font-weight: 600; color: var(--hg-ink); }}
.hg-loc {{ font-size: .86rem; color: var(--hg-muted); }}
.hg-facts {{ display: flex; flex-wrap: wrap; gap: 0; margin-top: 6px; font-size: .88rem;
    color: var(--hg-ink-soft); }}
.hg-facts span {{ white-space: nowrap; }}
.hg-facts span + span::before {{ content: "·"; color: var(--hg-faint); margin: 0 8px; }}
.hg-facts b {{ font-weight: 700; color: var(--hg-ink); }}
.hg-badges {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }}
.hg-b {{ font-size: .76rem; font-weight: 600; border-radius: 6px; padding: 3px 8px;
    line-height: 1.3; white-space: nowrap; }}
.hg-b-good {{ background: #DCFCE7; color: #166534; }}
.hg-b-drop {{ background: #FFEDD5; color: #9A3412; }}
.hg-b-priv {{ background: #EDE9FE; color: #5B21B6; }}
.hg-b-offer {{ background: #E0F2FE; color: #075985; }}
.hg-b-muted {{ background: #F1F5F9; color: #475569; }}
.hg-score {{ display: inline-flex; align-items: baseline; gap: 5px; border-radius: 10px;
    padding: 5px 10px; border: 1px solid; white-space: nowrap; cursor: help; }}
.hg-score small {{ font-size: .7rem; font-weight: 600; opacity: .85; }}
.hg-score b {{ font-size: 1.2rem; font-weight: 800; line-height: 1; }}
.hg-score i {{ font-style: normal; font-size: .72rem; font-weight: 700; opacity: .8;
    border-left: 1px solid currentColor; padding-left: 5px; }}
.hg-score-hi {{ background: #ECFDF5; color: #047857; border-color: #A7F3D0; }}
.hg-score-mid {{ background: #FFFBEB; color: #92400E; border-color: #FDE68A; }}
.hg-score-lo {{ background: #F8FAFC; color: #475569; border-color: var(--hg-line); }}
[class*="st-key-card-"] [data-testid="stCaptionContainer"] {{ font-size: .8rem; }}

/* Card actions: compact, equal buttons; the active "★" star is amber, not teal. */
[class*="st-key-act-"] {{ margin-top: .25rem; }}
[class*="st-key-act-"] button, [class*="st-key-act-"] a {{
    min-height: 2.25rem !important; padding: .25rem .6rem !important;
}}
[class*="st-key-act-"] button p, [class*="st-key-act-"] a p {{ font-size: .86rem !important; }}
[class*="st-key-act-"] [data-testid="stBaseButton-primary"] {{
    background: #FEF3C7; border-color: #FCD34D; color: #92400E;
}}
[class*="st-key-act-"] [data-testid="stBaseButton-primary"]:hover {{
    background: #FDE68A; border-color: #F59E0B; color: #78350F;
}}

@media (max-width: 640px) {{
    .st-key-hero {{ padding: 1.1rem 1rem 1rem; border-radius: 14px; }}
    .st-key-hero h2 {{ font-size: 1.4rem; }}
    [class*="st-key-card-"] {{ padding: .85rem .9rem .8rem !important; }}
    [class*="st-key-card-"] h3 {{ font-size: 1.35rem; }}
    .hg-photo {{ height: 150px; }}
    /* actions: a 2-up grid instead of a tall stack; a lone first button (3 total) spans. */
    [class*="st-key-act-"] [data-testid="stHorizontalBlock"] {{
        flex-direction: row !important; flex-wrap: wrap !important; gap: .45rem !important;
    }}
    [class*="st-key-act-"] [data-testid="stColumn"] {{
        flex: 1 1 calc(50% - .45rem) !important; min-width: calc(50% - .45rem) !important;
        width: auto !important;
    }}
    [class*="st-key-act-"] [data-testid="stColumn"]:first-child:nth-last-child(3) {{
        flex-basis: 100% !important; min-width: 100% !important;
    }}
}}
</style>
"""


def inject_css() -> None:
    """Inject the app's global CSS. Call once, early in ``main()`` (after
    ``st.set_page_config``). Idempotent and side-effect-only."""
    st.markdown(_CSS, unsafe_allow_html=True)
