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
    --hg-radius:   var(--hg-r-card);

    /* Round 5 (C6) tokens. Status: one tint + one ink per tone, ink ≥ 4.5:1 on its tint. */
    --hg-ok-bg:    #DCFCE7;  --hg-ok-fg:    #166534;  --hg-ok-line:   #86EFAC;
    --hg-warn-bg:  #FEF3C7;  --hg-warn-fg:  #92400E;  --hg-warn-line: #FCD34D;
    --hg-bad-bg:   #FEE2E2;  --hg-bad-fg:   #991B1B;  --hg-bad-line:  #FCA5A5;
    --hg-neu-bg:   #F1F5F9;  --hg-neu-fg:   #334155;
    --hg-accent-tint: #E6F4F1;            /* selected / pressed tint of the accent      */
    --hg-sep:      #7C8BA0;               /* «·» separators: ≥ 3:1 on canvas and card   */
    /* Type roles (rem, system stack). */
    --hg-fs-large:    1.75rem;   /* page title          */
    --hg-fs-title:    1.3rem;    /* section, price      */
    --hg-fs-headline: 1.0625rem; /* emphasised row, big choice buttons (600) */
    --hg-fs-body:     1rem;
    --hg-fs-subhead:  .9375rem;  /* card text, controls */
    --hg-fs-footnote: .8125rem;  /* captions, badges, basis */
    --hg-fs-caption:  .75rem;    /* map legend only     */
    /* Spacing: one 4-pt scale. */
    --hg-s1: 4px; --hg-s2: 8px; --hg-s3: 12px; --hg-s4: 16px; --hg-s5: 20px; --hg-s6: 24px;
    --hg-s8: 32px; --hg-s10: 40px;
    /* Shape: cards 14, controls 10, chips 6, pills round; touch target 44. */
    --hg-r-card: 14px; --hg-r-control: 10px; --hg-r-chip: 6px; --hg-r-pill: 999px;
    --hg-target: 44px;
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
h1 {{ font-size: var(--hg-fs-large); font-weight: 700; letter-spacing: -0.02em; margin-bottom: 4px; }}
h2 {{ font-size: var(--hg-fs-title); margin-top: 8px; }}
/* st.subheader */
h3 {{ font-size: var(--hg-fs-headline); }}
/* markdown "#### …" section heads */
h4 {{ font-size: var(--hg-fs-body); letter-spacing: .002em; margin: 4px 0 8px; }}

p, li, [data-testid="stMarkdownContainer"] {{ line-height: 1.6; }}

/* Captions & small print — quiet, not shouty. */
[data-testid="stCaptionContainer"], .stCaption, small {{
    color: var(--hg-muted);
    font-size: var(--hg-fs-footnote);
    line-height: 1.5;
}}

/* Comfortable main-column width & padding so content breathes. */
[data-testid="stMainBlockContainer"], .block-container {{
    padding-top: 40px;
    padding-bottom: 48px;
    max-width: 1280px;
}}

/* ------------------------------------------------------------------ *
 * Section dividers (st.divider) — a hairline, not a heavy rule.
 * ------------------------------------------------------------------ */
hr, [data-testid="stDivider"] {{
    border: none;
    border-top: 1px solid var(--hg-line);
    margin: 24px 0;
}}

/* ------------------------------------------------------------------ *
 * Bordered containers — the "Top picks" cards.
 * st.container(border=True) => stVerticalBlockBorderWrapper
 * ------------------------------------------------------------------ */
[data-testid="stVerticalBlockBorderWrapper"] {{
    background: var(--hg-surface);
    border: 1px solid var(--hg-line);
    border-radius: var(--hg-radius);
    padding: 20px 20px;
    transition: border-color .16s ease;
}}
/* Price headline inside a pick card sits tight to its meta caption. */
[data-testid="stVerticalBlockBorderWrapper"] h3 {{
    margin-bottom: 0;
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
    padding: 12px 16px 16px;
}}
/* No text-transform: uppercase — on a lang="en" page Chrome keeps the Greek accents
 * ("ΑΓΑΠΗΜΈΝΑ"), which is wrong Greek typography. */
[data-testid="stMetricLabel"] {{
    font-size: var(--hg-fs-footnote) !important;
    font-weight: 600;
    color: var(--hg-muted);
}}
[data-testid="stMetricLabel"] p {{ color: var(--hg-muted); }}
[data-testid="stMetricValue"] {{
    font-size: var(--hg-fs-title);
    font-weight: 700;
    letter-spacing: -0.02em;
    color: var(--hg-ink);
    line-height: 1.15;
}}
[data-testid="stMetricDelta"] {{ font-size: var(--hg-fs-footnote); font-weight: 600; }}
/* Wrap long values ("cheaper than area") instead of truncating them to "chea…". */
[data-testid="stMetric"] {{ min-width: 0; }}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] * {{
    white-space: normal !important; text-overflow: clip !important;
    overflow-wrap: normal !important; word-break: normal !important; hyphens: none;
    min-width: 0; max-width: 100%;
}}
/* Same for labels: Greek labels are long ("Μέρες στην αγορά"); wrap, never "Μέρες στην αγ…". */
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * {{
    white-space: normal !important; text-overflow: clip !important;
    overflow: visible !important; word-break: normal !important;
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
    border-radius: var(--hg-r-pill);
}}
[data-testid="stProgress"] > div > div > div {{ border-radius: var(--hg-r-pill); }}

/* ------------------------------------------------------------------ *
 * Sidebar — tighten, add a hairline separator, quiet the surface.
 * ------------------------------------------------------------------ */
[data-testid="stSidebar"] {{
    background: var(--hg-canvas);
    border-right: 1px solid var(--hg-line);
}}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{
    padding-top: 24px;
}}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {{ font-size: var(--hg-fs-body); letter-spacing: 0; }}
[data-testid="stSidebar"] .stRadio label {{ font-size: var(--hg-fs-subhead); }}

/* ------------------------------------------------------------------ *
 * Buttons & link-buttons — solid, calm, slightly rounded.
 * ------------------------------------------------------------------ */
.stButton > button, .stLinkButton > a, [data-testid="stBaseButton-secondary"] {{
    border-radius: var(--hg-r-control);
    border: 1px solid var(--hg-line);
    font-weight: 600;
    transition: background .14s ease, border-color .14s ease,
                box-shadow .14s ease, transform .05s ease;
}}
@media (hover: hover) and (pointer: fine) {{
    .stButton > button:hover, .stLinkButton > a:hover {{
        border-color: var(--hg-accent);
        color: var(--hg-accent);
    }}
    [data-testid="stVerticalBlockBorderWrapper"]:hover {{ border-color: #CBD5E1; }}
    [data-testid="stExpander"] summary:hover {{ color: var(--hg-accent); }}
}}
/* Primary buttons use the accent as a solid fill. */
[data-testid="stBaseButton-primary"] {{
    background: var(--hg-accent);
    border-color: var(--hg-accent);
    color: #fff;
}}
@media (hover: hover) and (pointer: fine) {{
    [data-testid="stBaseButton-primary"]:hover {{
        background: var(--hg-accent-2);
        border-color: var(--hg-accent-2);
    }}
}}

/* Links pick up the accent, not browser blue. */
a, [data-testid="stMarkdownContainer"] a {{ color: var(--hg-accent); }}
@media (hover: hover) {{ a:hover {{ color: var(--hg-accent-2); }} }}

/* ------------------------------------------------------------------ *
 * Dataframes & tables — crisp header, soft row separation, rounded frame.
 * (The grid body is a canvas widget; we style the frame + the classic
 *  st.table markup, which is all CSS can reliably reach.)
 * ------------------------------------------------------------------ */
[data-testid="stDataFrame"], [data-testid="stTable"] {{
    border: 1px solid var(--hg-line);
    border-radius: var(--hg-radius);
    overflow: hidden;
}}
[data-testid="stTable"] table {{ border-collapse: collapse; width: 100%; }}
[data-testid="stTable"] thead th {{
    background: var(--hg-canvas);
    color: var(--hg-muted);
    font-size: var(--hg-fs-footnote);
    font-weight: 600;
    letter-spacing: .04em;
   
    border-bottom: 1px solid var(--hg-line);
    padding: 8px 12px;
}}
[data-testid="stTable"] tbody td {{
    border-bottom: 1px solid var(--hg-line-2);
    padding: 8px 12px;
    color: var(--hg-ink-soft);
}}
[data-testid="stTable"] tbody tr:last-child td {{ border-bottom: none; }}

/* ------------------------------------------------------------------ *
 * Tabs, expanders & alerts — softened corners, quieter chrome.
 * ------------------------------------------------------------------ */
[data-testid="stExpander"] {{
    border: 1px solid var(--hg-line);
    border-radius: var(--hg-radius);
    background: var(--hg-surface);
}}

[data-testid="stAlert"] {{
    border-radius: var(--hg-r-control);
    border: 1px solid var(--hg-line);
}}

/* Inputs / select boxes — consistent radius with the rest of the system. */
[data-baseweb="input"], [data-baseweb="select"] > div {{
    border-radius: var(--hg-r-control);
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
    border-radius: var(--hg-r-control); box-shadow: var(--hg-shadow); margin: 8px 0 0 4px;
    color: var(--hg-ink);
}}
footer {{ visibility: hidden; height: 0; }}
[data-testid="stMainBlockContainer"] {{ padding-top: 36px; }}
@media (max-width: 640px) {{
    [data-testid="stMainBlockContainer"] {{ padding: 48px 16px 32px; }}
}}

/* ------------------------------------------------------------------ *
 * Listing card grid — the product view (replaces the raw dataframe).
 * ------------------------------------------------------------------ */
.ph-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 16px;
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
    border-radius: var(--hg-r-card);
    display: flex; flex-direction: column;
    overflow: hidden;
    transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease;
}}
.ph-body {{ padding: 16px 16px 16px; display: flex; flex-direction: column; gap: 12px; }}
@media (hover: hover) {{ .ph-card:hover {{ border-color: #CBD5E1; }} }}

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
.ph-card-head {{ display: flex; align-items: center; gap: 16px; }}
.ph-score {{
    flex: 0 0 auto; width: 52px; height: 52px; border-radius: var(--hg-r-card);
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    background: hsl(var(--hue), 62%, 94%); color: hsl(var(--hue), 70%, 28%);
    border: 1px solid hsl(var(--hue), 55%, 84%);
}}
.ph-score span {{ font-size: var(--hg-fs-title); font-weight: 750; line-height: 1; }}
.ph-score small {{ font-size: var(--hg-fs-footnote); letter-spacing: .06em; opacity: .8; }}
.ph-price-wrap {{ flex: 1 1 auto; min-width: 0; }}
.ph-price {{ font-size: var(--hg-fs-title); font-weight: 750; color: var(--hg-ink); line-height: 1.1; }}
.ph-ppm2 {{ font-size: var(--hg-fs-footnote); color: var(--hg-muted); margin-top: 4px; }}
.ph-arch {{
    flex: 0 0 auto; font-size: var(--hg-fs-footnote); font-weight: 650; padding: 4px 8px; border-radius: var(--hg-r-pill);
    letter-spacing: .03em; white-space: nowrap;
}}
.ph-arch-new {{ background: #DCFCE7; color: #15803D; }}
.ph-arch-reno {{ background: #DBEAFE; color: #1D4ED8; }}
.ph-arch-modern {{ background: #E0F2FE; color: #0369A1; }}
.ph-arch-dated {{ background: #F1F5F9; color: #64748B; }}
.ph-arch-liability {{ background: #FEE2E2; color: #B91C1C; }}
.ph-arch-std {{ background: #F1F5F9; color: #64748B; }}
.ph-hood {{ font-size: var(--hg-fs-subhead); color: var(--hg-ink-soft); font-weight: 550; margin-top: -4px; }}
.ph-specs {{ display: flex; flex-wrap: wrap; gap: 8px; }}
.ph-spec {{ font-size: var(--hg-fs-footnote); color: var(--hg-ink-soft); background: var(--hg-canvas);
    border: 1px solid var(--hg-line-2); border-radius: var(--hg-r-chip); padding: 4px 8px; }}
.ph-pill {{ font-size: var(--hg-fs-footnote); font-weight: 650; border-radius: var(--hg-r-chip); padding: 4px 8px; }}
.ph-en-good {{ background: #DCFCE7; color: #15803D; }}
.ph-en-mid {{ background: #FEF9C3; color: #A16207; }}
.ph-en-poor {{ background: #FFEDD5; color: #C2410C; }}
.ph-en-bad {{ background: #FEE2E2; color: #B91C1C; }}
.ph-en-unknown {{ background: #F1F5F9; color: #64748B; }}
.ph-signals {{ display: flex; gap: 8px; border-top: 1px solid var(--hg-line-2);
    border-bottom: 1px solid var(--hg-line-2); padding: 8px 0; }}
.ph-sig {{ flex: 1; display: flex; flex-direction: column; gap: 1px; }}
.ph-sig b {{ font-size: var(--hg-fs-body); font-weight: 700; color: var(--hg-ink); }}
.ph-sig span {{ font-size: var(--hg-fs-footnote); color: var(--hg-muted); letter-spacing: .03em; }}
.ph-sig-pos b {{ color: #15803D; }}
.ph-sig-neg b {{ color: #B91C1C; }}
.ph-grade {{ font-size: var(--hg-fs-body); font-weight: 800; color: #fff; border-radius: var(--hg-r-control);
    padding: 4px 8px; align-self: center; }}
.ph-grade-A {{ background: #15803D; }}
.ph-grade-B {{ background: #65A30D; }}
.ph-grade-C {{ background: #CA8A04; }}
.ph-grade-D {{ background: #9CA3AF; }}
.ph-conf {{ display: flex; flex-direction: column; align-items: center; font-size: var(--hg-fs-footnote);
    font-weight: 700; color: var(--hg-muted); align-self: center; line-height: 1; }}
.ph-conf small {{ font-size: var(--hg-fs-footnote); letter-spacing: .03em; }}
.ph-thesis {{ font-size: var(--hg-fs-footnote); line-height: 1.35; color: var(--hg-ink);
    background: #FFF7ED; border: 1px solid #FED7AA; border-radius: var(--hg-r-control);
    padding: 8px 8px; margin: 4px 0; }}
.ph-incomplete {{ font-size: var(--hg-fs-footnote); line-height: 1.3; color: #92400E;
    background: #FEFCE8; border: 1px solid #FEF08A; border-radius: var(--hg-r-control);
    padding: 8px 8px; margin: 4px 0; }}
/* The recommendation line — BUY/WATCH/PASS verdict + concrete action. */
.ph-rec {{ font-size: var(--hg-fs-footnote); line-height: 1.35; border-radius: var(--hg-r-control); padding: 8px 12px;
    margin: 4px 0; display: flex; gap: 8px; align-items: baseline; }}
.ph-rec-badge {{ font-size: var(--hg-fs-footnote); font-weight: 800; letter-spacing: .04em;
    padding: 4px 8px; border-radius: var(--hg-r-pill); flex: 0 0 auto; color: #fff; }}
.ph-rec-BUY {{ background: #ECFDF5; color: #065F46; border: 1px solid #A7F3D0; }}
.ph-rec-BUY .ph-rec-badge {{ background: #059669; }}
.ph-rec-WATCH {{ background: #FEFCE8; color: #854D0E; border: 1px solid #FDE68A; }}
.ph-rec-WATCH .ph-rec-badge {{ background: #CA8A04; }}
.ph-rec-PASS {{ background: #FEF2F2; color: #991B1B; border: 1px solid #FECACA; }}
.ph-rec-PASS .ph-rec-badge {{ background: #DC2626; }}
/* Strategy-fit tags: small teal chips summarising the investment angle. */
.ph-strats {{ display: flex; flex-wrap: wrap; gap: 4px; margin: 4px 0; }}
.ph-strat {{ font-size: var(--hg-fs-footnote); font-weight: 600; color: #0F766E; background: #CCFBF1;
    border: 1px solid #99F6E4; border-radius: var(--hg-r-pill); padding: 4px 8px; }}
/* Internal-consistency warning: stronger (rose) than the limited-data note — the numbers
   themselves look wrong, not merely absent. */
.ph-inconsistent {{ font-size: var(--hg-fs-footnote); line-height: 1.3; color: #9F1239;
    background: #FFF1F2; border: 1px solid #FECDD3; border-radius: var(--hg-r-control);
    padding: 8px 8px; margin: 4px 0; }}
.ph-card-foot {{ display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 4px; }}
.ph-badges {{ display: flex; flex-wrap: wrap; gap: 4px; }}
.ph-badge {{ font-size: var(--hg-fs-footnote); font-weight: 600; color: var(--hg-accent);
    background: #ECFDF5; border-radius: var(--hg-r-chip); padding: 4px 8px; }}
.ph-cta {{ flex: 0 0 auto; font-size: var(--hg-fs-footnote); font-weight: 650; color: #fff !important;
    background: var(--hg-accent); border-radius: var(--hg-r-control); padding: 8px 12px; text-decoration: none !important;
    white-space: nowrap; transition: background .15s ease; }}
@media (hover: hover) {{ .ph-cta:hover {{ background: var(--hg-accent-2); }} }}

/* ------------------------------------------------------------------ *
 * Sidebar navigation — turn the default radio into a clean nav menu.
 * ------------------------------------------------------------------ */
[data-testid="stSidebar"] [role="radiogroup"] {{ gap: 4px; }}
[data-testid="stSidebar"] [role="radiogroup"] label {{
    display: flex; align-items: center; width: 100%;
    padding: 8px 12px; border-radius: var(--hg-r-control); cursor: pointer;
    font-size: var(--hg-fs-subhead); font-weight: 550; color: var(--hg-ink-soft);
    transition: background .12s ease, color .12s ease;
}}
@media (hover: hover) {{
    [data-testid="stSidebar"] [role="radiogroup"] label:hover {{ background: #E7EDF4; }}
}}
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
        flex-direction: row !important; flex-wrap: wrap !important; gap: 8px !important;
    }}
    [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] [data-testid="stMetric"])
        > [data-testid="stColumn"] {{
        flex: 1 1 calc(50% - 8px) !important; min-width: calc(50% - 8px) !important;
        width: auto !important;
    }}
    [data-testid="stMetricValue"] {{ font-size: var(--hg-fs-title); }}
    [data-testid="stMetric"] {{ padding: 12px 12px; }}
}}

/* ------------------------------------------------------------------ *
 * Buyer pages (buyer.py): search hero, example chips, result cards.
 * ------------------------------------------------------------------ */
.st-key-hero {{
    background: var(--hg-surface);
    border: 1px solid var(--hg-line); border-radius: var(--hg-r-card);
    padding: 24px 28px 20px; margin-bottom: 8px; gap: 12px;
}}
.st-key-hero [data-testid="stCaptionContainer"] {{ margin-top: -8px; }}
.st-key-hero h2 {{ font-size: var(--hg-fs-large); font-weight: 750; letter-spacing: -0.02em;
    margin: 0; padding: 0; }}
.st-key-hero [data-baseweb="input"] {{ background: #fff; border: 1.5px solid #CBD5E1;
    border-radius: var(--hg-r-card); }}
.st-key-hero [data-baseweb="input"]:focus-within {{ border-color: var(--hg-accent); }}
.st-key-hero [data-baseweb="input"] input {{ font-size: var(--hg-fs-body); padding: 12px 12px;
    background: #fff; }}
.st-key-hero [data-testid="stFormSubmitButton"] button {{ min-height: 48px;
    border-radius: var(--hg-r-card); font-size: var(--hg-fs-body); }}
.st-key-examples {{ align-items: center; row-gap: 8px; }}
.hg-try {{ font-size: var(--hg-fs-footnote); color: var(--hg-muted); font-weight: 600; }}
.st-key-examples button {{
    border-radius: var(--hg-r-pill) !important; min-height: var(--hg-target) !important; padding: 4px 12px !important;
    background: #fff; border: 1px solid #CCE7E2 !important; color: var(--hg-accent) !important;
}}
.st-key-examples button p {{ font-size: var(--hg-fs-footnote) !important; font-weight: 600; }}
@media (hover: hover) {{
    .st-key-examples button:hover {{ background: #ECFDF8; border-color: var(--hg-accent) !important; }}
}}

/* The parsed search as chips. */
.hg-understood {{ display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
    font-size: var(--hg-fs-footnote); }}
.hg-understood b {{ color: var(--hg-ink); margin-right: 4px; }}
.hg-understood span {{ background: #E6F4F1; color: #115E59; border-radius: var(--hg-r-pill);
    padding: 4px 8px; font-weight: 550; }}
.hg-count {{ font-size: var(--hg-fs-subhead); color: var(--hg-muted); }}
.hg-count b {{ color: var(--hg-ink); font-size: var(--hg-fs-headline); }}

/* Result card: a keyed bordered container, so the styling stays scoped to it. */
[class*="st-key-card-"] {{ padding: 16px 20px 16px !important; gap: 8px !important;
    border-radius: var(--hg-r-card) !important; }}
/* Streamlit gives markdown a -1rem bottom margin to cancel the last <p>'s margin; our blocks
   are divs/headings, so that would make the next row overlap them. */
[class*="st-key-card-"] [data-testid="stMarkdownContainer"],
.st-key-hero [data-testid="stMarkdownContainer"], .st-key-examples [data-testid="stMarkdownContainer"],
[data-testid="stMarkdownContainer"]:has(> .hg-understood, > .hg-count) {{ margin-bottom: 0; }}
[class*="st-key-card-"] [data-testid="stMarkdownContainer"] p:last-child,
.st-key-examples [data-testid="stMarkdownContainer"] p:last-child {{ margin-bottom: 0; }}
[class*="st-key-card-"] h3 {{ font-size: var(--hg-fs-title); font-weight: 750; letter-spacing: -0.02em;
    margin: 0; padding: 0; line-height: 1.15; }}
.hg-photo {{ display: block; width: 100%; height: 180px; object-fit: cover;
    border-radius: var(--hg-r-control); background: var(--hg-line-2); }}
.hg-head {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 8px;
    line-height: 1.35; }}
.hg-title {{ font-size: var(--hg-fs-body); font-weight: 600; color: var(--hg-ink); }}
.hg-loc {{ font-size: var(--hg-fs-footnote); color: var(--hg-muted); }}
.hg-facts {{ display: flex; flex-wrap: wrap; gap: 0; margin-top: 8px; font-size: var(--hg-fs-footnote);
    color: var(--hg-ink-soft); }}
.hg-facts span {{ white-space: nowrap; }}
.hg-facts span + span::before {{ content: "·"; color: var(--hg-faint); margin: 0 8px; }}
.hg-facts b {{ font-weight: 700; color: var(--hg-ink); }}
.hg-badges {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }}
/* Badges wrap inside a narrow (phone) card instead of overflowing it. */
.hg-b {{ font-size: var(--hg-fs-footnote); font-weight: 600; border-radius: var(--hg-r-chip); padding: 4px 8px;
    line-height: 1.3; white-space: normal; overflow-wrap: anywhere; max-width: 100%; }}
.hg-rent {{ margin-top: 8px; font-size: var(--hg-fs-footnote); color: var(--hg-ink-soft); }}
.hg-rent b {{ color: var(--hg-ink); font-weight: 700; }}
.hg-rent span {{ color: var(--hg-muted); font-size: var(--hg-fs-footnote); }}
.hg-note-bad {{ margin-top: 8px; padding: 8px 8px; border-radius: var(--hg-r-control); font-size: var(--hg-fs-footnote);
    font-weight: 600; background: var(--hg-bad-bg); color: var(--hg-bad-fg);
    border: 1px solid var(--hg-bad-line); }}
/* Score breakdown under the price row: visible text (works on phones, unlike a tooltip). */
.hg-parts {{ display: flex; flex-wrap: wrap; gap: 4px 0; font-size: var(--hg-fs-footnote); margin-top: -4px;
    color: var(--hg-muted); }}
.hg-parts span {{ white-space: nowrap; }}
.hg-parts span + span::before {{ content: "·"; color: var(--hg-faint); margin: 0 8px; }}
.hg-p-up {{ color: #047857; }}
.hg-p-down {{ color: #B91C1C; }}
.hg-p-flat {{ color: var(--hg-muted); }}
/* Price position: this flat's €/m² vs the comparables' p25–median–p75. */
.hg-pos {{ margin: 4px 0 8px; }}
.hg-pos-track {{ position: relative; height: 14px; border-radius: var(--hg-r-chip); background: var(--hg-line-2); }}
.hg-pos-band {{ position: absolute; top: 0; bottom: 0; background: #CCE7E2; border-radius: var(--hg-r-chip); }}
.hg-pos-med {{ position: absolute; top: -3px; bottom: -3px; width: 2px; margin-left: -1px;
    background: var(--hg-accent); }}
.hg-pos-dot {{ position: absolute; top: 50%; width: 14px; height: 14px; margin: -8px 0 0 -8px;
    border-radius: 50%; background: var(--hg-ink); border: 2px solid #fff;
    box-shadow: 0 0 0 1px var(--hg-ink); }}
.hg-pos-legend {{ display: flex; flex-wrap: wrap; gap: 4px 16px; margin-top: 8px; font-size: var(--hg-fs-footnote);
    color: var(--hg-muted); }}
.hg-pos-legend i {{ display: inline-block; width: 10px; height: 10px; margin-right: 4px;
    vertical-align: middle; border-radius: var(--hg-r-chip); }}
.hg-pos-k-band {{ background: #CCE7E2; }}
.hg-pos-k-med {{ background: var(--hg-accent); width: 3px !important; }}
.hg-pos-k-dot {{ background: var(--hg-ink); border-radius: 50% !important; }}
.hg-b-good {{ background: #DCFCE7; color: #166534; }}
.hg-b-drop {{ background: #FFEDD5; color: #9A3412; }}
.hg-b-priv {{ background: #EDE9FE; color: #5B21B6; }}
.hg-b-offer {{ background: #E0F2FE; color: #075985; }}
.hg-b-muted {{ background: #F1F5F9; color: #475569; }}
.hg-b-warn {{ background: #FEF3C7; color: #92400E; }}
.hg-b-bad {{ background: #FEE2E2; color: #991B1B; }}
.hg-advice {{ margin: 4px 0 0; padding: 8px 12px; border-radius: var(--hg-r-control); font-size: var(--hg-fs-footnote);
    line-height: 1.35; border: 1px solid; }}
.hg-advice-good {{ background: #F0FDF4; border-color: #16A34A; color: #14532D; }}
.hg-advice-warn {{ background: #FFFBEB; border-color: #D97706; color: #78350F; }}
.hg-advice-bad {{ background: #FEF2F2; border-color: #DC2626; color: #7F1D1D; }}
.hg-score {{ display: inline-flex; align-items: baseline; gap: 4px; border-radius: var(--hg-r-control);
    padding: 4px 8px; border: 1px solid; white-space: nowrap; cursor: help; }}
.hg-score small {{ font-size: var(--hg-fs-footnote); font-weight: 600; opacity: .85; }}
.hg-score b {{ font-size: var(--hg-fs-title); font-weight: 800; line-height: 1; }}
.hg-score i {{ font-style: normal; font-size: var(--hg-fs-footnote); font-weight: 700; opacity: .8;
    border-left: 1px solid currentColor; padding-left: 4px; }}
.hg-score-hi {{ background: #ECFDF5; color: #047857; border-color: #A7F3D0; }}
.hg-score-mid {{ background: #FFFBEB; color: #92400E; border-color: #FDE68A; }}
.hg-score-lo {{ background: #F8FAFC; color: #475569; border-color: var(--hg-line); }}
[class*="st-key-card-"] [data-testid="stCaptionContainer"] {{ font-size: var(--hg-fs-footnote); }}

/* Card actions: compact, equal buttons; the active "★" star is amber, not teal. */
[class*="st-key-act-"] {{ margin-top: 4px; }}
[class*="st-key-act-"] button, [class*="st-key-act-"] a {{
    min-height: var(--hg-target) !important; padding: 4px 12px !important;
}}
[class*="st-key-act-"] button p, [class*="st-key-act-"] a p {{ font-size: var(--hg-fs-subhead) !important; }}
[class*="st-key-act-"] [data-testid="stBaseButton-primary"] {{
    background: #FEF3C7; border-color: #FCD34D; color: #92400E;
}}
@media (hover: hover) {{
    [class*="st-key-act-"] [data-testid="stBaseButton-primary"]:hover {{
        background: #FDE68A; border-color: #F59E0B; color: #78350F;
    }}
}}

@media (max-width: 640px) {{
    .st-key-hero {{ padding: 16px 16px 16px; border-radius: var(--hg-r-card); }}
    .st-key-hero h2 {{ font-size: var(--hg-fs-title); }}
    [class*="st-key-card-"] {{ padding: 12px 16px 12px !important; }}
    [class*="st-key-card-"] h3 {{ font-size: var(--hg-fs-title); }}
    .hg-photo {{ height: 150px; }}
    /* filters: a compact 2-up grid (the first, wide column spans) so results show sooner. */
    .st-key-filters {{ padding: 8px 12px !important; gap: 8px !important; }}
    .st-key-filters [data-testid="stHorizontalBlock"] {{
        flex-direction: row !important; flex-wrap: wrap !important; gap: 8px !important;
    }}
    .st-key-filters [data-testid="stColumn"] {{
        flex: 1 1 calc(50% - 8px) !important; min-width: calc(50% - 8px) !important;
        width: auto !important;
    }}
    .st-key-filters [data-testid="stColumn"]:first-child:nth-last-child(3) {{
        flex-basis: 100% !important; min-width: 100% !important;
    }}
    .st-key-filters label p {{ font-size: var(--hg-fs-footnote) !important; }}
    /* actions: a 2-up grid instead of a tall stack; a lone first button (3 total) spans. */
    [class*="st-key-act-"] [data-testid="stHorizontalBlock"] {{
        flex-direction: row !important; flex-wrap: wrap !important; gap: 8px !important;
    }}
    [class*="st-key-act-"] [data-testid="stColumn"] {{
        flex: 1 1 calc(50% - 8px) !important; min-width: calc(50% - 8px) !important;
        width: auto !important;
    }}
    [class*="st-key-act-"] [data-testid="stColumn"]:first-child:nth-last-child(3) {{
        flex-basis: 100% !important; min-width: 100% !important;
    }}
}}

/* ------------------------------------------------------------------ *
 * App shell: top page pills (one tap on a phone) + compare facts table.
 * ------------------------------------------------------------------ */
.st-key-nav_pill [data-testid="stButtonGroup"], .st-key-nav_pill > div > div {{ flex-wrap: wrap; gap: 8px; }}
.st-key-nav_pill button {{ min-height: var(--hg-target); padding: 4px 12px; font-size: var(--hg-fs-subhead); }}
/* Selected pill: filled AND bold with a check, so it never relies on colour alone. */
[data-testid="stMain"] .st-key-nav_pill button[aria-checked="true"],
[data-testid="stMain"] .st-key-nav_pill [data-testid="stButtonGroup"] button[aria-checked="true"][data-selected],
[data-testid="stMain"] .st-key-nav_pill button[aria-pressed="true"] {{
    font-weight: 700; background: var(--hg-accent); border-color: var(--hg-accent);
    color: #fff;
}}
[data-testid="stMain"] .st-key-nav_pill button[aria-checked="true"] p,
[data-testid="stMain"] .st-key-nav_pill button[aria-pressed="true"] p {{
    color: #fff;
}}
[data-testid="stMarkdownContainer"] table {{
    width: 100%; table-layout: fixed; border-collapse: collapse; font-size: var(--hg-fs-subhead);
}}
[data-testid="stMarkdownContainer"] th, [data-testid="stMarkdownContainer"] td {{
    padding: 8px 8px; vertical-align: top; overflow-wrap: anywhere;
    border-bottom: 1px solid var(--hg-line-2);
}}
[data-testid="stMarkdownContainer"] td:first-child {{ width: 32%; color: var(--hg-muted); }}
/* Nothing may push a page wider than the phone (the select's hidden input did on the map). */
[data-testid="stMain"] {{ overflow-x: clip; }}
[data-testid="stMain"] [data-baseweb="select"] input {{ max-width: 100%; }}

/* ------------------------------------------------------------------ *
 * Finish (round 4): one header line, one type scale for every page.
 * Header 1.05rem · page title 1.3rem (## and ### alike) · section 1rem · body .95rem ·
 * small print .875rem. Spacing: 1rem between blocks, .5rem inside a card.
 * ------------------------------------------------------------------ */
.hg-app-head {{ font-size: var(--hg-fs-headline); font-weight: 750; color: var(--hg-ink);
    letter-spacing: -0.01em; line-height: 1.3; margin: 0; }}
[data-testid="stMain"] h2, [data-testid="stMain"] h3 {{
    font-size: var(--hg-fs-title); font-weight: 700; margin: 4px 0 4px; padding: 0; }}
[data-testid="stMain"] h4 {{ font-size: var(--hg-fs-body); font-weight: 650; margin: 12px 0 4px; }}
[data-testid="stMain"] p, [data-testid="stMain"] li {{ font-size: var(--hg-fs-subhead); }}
[data-testid="stMain"] [data-testid="stCaptionContainer"] p {{ font-size: var(--hg-fs-footnote); }}
[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"] {{ padding: 12px 16px; }}
.hg-card[data-compact] > div + div {{ margin-top: 4px; }}
.hg-card[data-compact] details {{ margin-top: 4px; }}
/* ------------------------------------------------------------------ *
 * Round 5 (C6) — the design finish. Type roles, touch targets, focus,
 * states, status tones, grouped lists, browser surfaces. Rules that must
 * beat the page modules' own <style> blocks (buyer.CARD_CSS, guide.CSS,
 * injected after this sheet) carry [data-testid="stMain"] for specificity
 * instead of !important.
 * ------------------------------------------------------------------ */

/* Type roles: large title 1.75 · title 1.3 · headline 1.0625/600 · body 1 ·
 * subhead .9375 · footnote .8125 · caption .75 (rem). Tracking on titles only. */
[data-testid="stMain"] h1, [data-testid="stMain"] h2 {{
    font-size: var(--hg-fs-large); font-weight: 700; letter-spacing: -0.02em;
    line-height: 1.3; margin: var(--hg-s2) 0 var(--hg-s1); padding: 0;
}}
[data-testid="stMain"] h3 {{
    font-size: var(--hg-fs-title); font-weight: 700; letter-spacing: -0.01em;
    line-height: 1.3; margin: var(--hg-s6) 0 var(--hg-s2); padding: 0;
}}
[data-testid="stMain"] h4, [data-testid="stMain"] h5 {{
    font-size: var(--hg-fs-headline); font-weight: 600; letter-spacing: 0;
    line-height: 1.3; margin: var(--hg-s5) 0 var(--hg-s2); padding: 0;
}}
[data-testid="stMain"] p, [data-testid="stMain"] li {{
    font-size: var(--hg-fs-body); line-height: 1.5;
}}
[data-testid="stMain"] [data-testid="stCaptionContainer"],
[data-testid="stMain"] [data-testid="stCaptionContainer"] p,
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{
    font-size: var(--hg-fs-footnote); line-height: 1.5;
}}
/* Controls: one text size. */
:is([data-testid="stMain"], [data-testid="stSidebar"]) :is(button, a, summary) p,
:is([data-testid="stMain"], [data-testid="stSidebar"]) summary span,
:is([data-testid="stMain"], [data-testid="stSidebar"]) [data-testid="stWidgetLabel"] p,
:is([data-testid="stMain"], [data-testid="stSidebar"]) [data-testid="stMarkdownContainer"] label,
:is([data-testid="stMain"], [data-testid="stSidebar"]) :is(input, textarea),
:is([data-testid="stMain"], [data-testid="stSidebar"]) [data-baseweb="select"] *,
:is([data-testid="stMain"], [data-testid="stSidebar"]) [data-baseweb="tag"] span {{
    font-size: var(--hg-fs-subhead);
}}
[data-testid="stMain"] [class*="st-key-guide-"] button p {{
    font-size: var(--hg-fs-headline); font-weight: 600;
}}
[data-testid="stMain"] [data-testid="stAlert"] p {{ font-size: var(--hg-fs-subhead); }}
[data-testid="stMain"] [data-testid="stMetricValue"] {{ font-size: var(--hg-fs-title); }}
[data-testid="stMain"] [data-testid="stMetricLabel"] p {{ font-size: var(--hg-fs-footnote); }}
[data-testid="stMain"] table {{ font-size: var(--hg-fs-subhead); }}
[data-testid="stSidebar"] h3 {{ font-size: var(--hg-fs-headline); }}
/* Every number lines up. */
[data-testid="stAppViewContainer"] {{ font-variant-numeric: tabular-nums; }}

/* The header band: the data line sits close to the pills, the page title close to it. */
[data-testid="stMainBlockContainer"] {{ padding-top: var(--hg-s10); }}
@media (max-width: 640px) {{
    [data-testid="stMainBlockContainer"] {{ padding: 56px var(--hg-s4) var(--hg-s8); }}
}}
[data-testid="stMain"] [data-testid="stVerticalBlock"] {{ gap: var(--hg-s3); }}
/* A page module's <style> block renders as an empty element that still takes a gap: drop it
 * from the layout (the stylesheet keeps applying). */
[data-testid="stMain"] [data-testid="stElementContainer"]:has(style):not(:has(
    p, h1, h2, h3, h4, li, img, table, button, a, .hg-card
)) {{
    display: none;
}}

/* Touch targets: every control ≥ 44 px tall (Apple HIG 44 pt, WCAG 2.5.5). */
:is([data-testid="stMain"], [data-testid="stSidebar"]) :is(
    .stButton button, .stDownloadButton button, .stFormSubmitButton button, .stLinkButton a,
    [data-testid="stButtonGroup"] button, [data-testid="stExpander"] summary,
    [data-testid="stNumberInputStepDown"], [data-testid="stNumberInputStepUp"],
    [data-testid="stCheckbox"] label, [data-testid="stRadio"] label,
    [data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"]
) {{
    min-height: var(--hg-target);
}}
:is([data-testid="stMain"], [data-testid="stSidebar"]) :is([data-testid="stCheckbox"], [data-testid="stRadio"]) label {{
    align-items: center;
}}
:is([data-testid="stMain"], [data-testid="stSidebar"]) :is(
    [data-baseweb="input"] input, [data-baseweb="select"] input, [data-baseweb="textarea"] textarea
) {{
    min-height: calc(var(--hg-target) - 2px); box-sizing: border-box;
}}
[data-testid="stNumberInputStepDown"], [data-testid="stNumberInputStepUp"] {{
    min-width: var(--hg-target);
}}
[data-testid="stMain"] .st-key-nav_pill button {{ min-height: var(--hg-target); }}
/* Streamlit's small icon buttons: the box grows, the icon stays. */
[data-testid="stTooltipHoverTarget"] button {{
    min-width: var(--hg-target); min-height: var(--hg-target); margin: -12px -12px -12px 0;
}}
/* Selects (Streamlit 1.66 draws them with react-aria, not BaseWeb): field row 44 px. */
:is([data-testid="stMain"], [data-testid="stSidebar"]) .react-aria-ComboBox > div {{
    min-height: var(--hg-target);
}}
:is([data-testid="stMain"], [data-testid="stSidebar"]) .react-aria-ComboBox > div > :is(input, button) {{
    min-height: var(--hg-target);
}}
:is([data-testid="stMain"], [data-testid="stSidebar"]) .react-aria-ComboBox > div:focus-within {{
    border-color: var(--hg-accent); box-shadow: 0 0 0 1px var(--hg-accent);
}}
/* Number / text inputs: the field and its container. */
:is([data-testid="stMain"], [data-testid="stSidebar"]) :is(
    [data-testid="stNumberInputContainer"], [data-testid="stTextInputRootElement"]
) {{
    min-height: var(--hg-target);
}}
:is([data-testid="stMain"], [data-testid="stSidebar"]) input:is(
    [data-testid="stNumberInputField"], [data-testid="stTextInputField"]
) {{
    min-height: var(--hg-target);
}}
/* Multiselect: the typing field fills the 44 px row; a chip's remove control gets the
 * 24 px WCAG 2.5.8 minimum (44 px would make every chip a button-sized block). */
:is([data-testid="stMain"], [data-testid="stSidebar"]) [data-testid="stMultiSelectTagsContainer"] input {{
    min-height: var(--hg-target);
}}
:is([data-testid="stMain"], [data-testid="stSidebar"]) [data-testid="stMultiSelectTagsContainer"] button {{
    min-width: 24px; min-height: 24px;
}}
[data-testid="stBaseButton-headerNoPadding"] {{
    min-width: var(--hg-target); min-height: var(--hg-target);
}}
[data-testid="stElementToolbar"] button, [data-testid="stDeckGlJsonChartZoomButton"] button,
[data-testid="stDeckGlJsonChart"] button {{
    min-width: var(--hg-target); min-height: var(--hg-target);
}}
/* The card disclosure («Από πού βγαίνουν») is a full-width 44 px row with a drawn chevron. */
[data-testid="stMain"] .hg-card details {{
    margin-top: var(--hg-s2); border-top: 1px solid var(--hg-line-2);
    font-size: var(--hg-fs-footnote);
}}
[data-testid="stMain"] .hg-card summary {{
    display: flex; align-items: center; justify-content: space-between;
    min-height: var(--hg-target); list-style: none; cursor: pointer;
    font-size: var(--hg-fs-subhead); font-weight: 600; color: var(--hg-accent);
}}
[data-testid="stMain"] .hg-card summary::-webkit-details-marker {{ display: none; }}
[data-testid="stMain"] .hg-card summary::after {{
    content: ""; width: 8px; height: 8px; margin-right: var(--hg-s1);
    border-right: 2px solid currentColor; border-bottom: 2px solid currentColor;
    transform: rotate(45deg); transition: transform .2s cubic-bezier(.2, .8, .2, 1);
}}
[data-testid="stMain"] .hg-card details[open] > summary::after {{ transform: rotate(-135deg); }}

/* Focus: one visible ring from the accent on every control (keyboard only). */
:is([data-testid="stMain"], [data-testid="stSidebar"], header) :is(
    button, a, summary, [role="radio"], [role="option"], [role="checkbox"], [role="switch"],
    [role="tab"]
):is(:focus-visible, [data-focus-visible]) {{
    outline: 2px solid var(--hg-accent); outline-offset: 2px;
}}
:is([data-testid="stMain"], [data-testid="stSidebar"]) :is(
    [data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"]
):focus-within {{
    border-color: var(--hg-accent); box-shadow: 0 0 0 1px var(--hg-accent);
}}
:is([data-testid="stMain"], [data-testid="stSidebar"]) :is(
    [data-testid="stNumberInputContainer"], [data-testid="stTextInputRootElement"],
    [data-testid="stTextAreaRootElement"]
):focus-within {{
    border-color: var(--hg-accent); box-shadow: 0 0 0 1px var(--hg-accent);
}}
/* The page itself is a keyboard scroll region in Streamlit: give it the ring too. */
[data-testid="stMain"]:focus-visible {{ outline: 2px solid var(--hg-accent); outline-offset: -2px; }}
:is([data-testid="stMain"], [data-testid="stSidebar"]) label:has(input:focus-visible) {{
    outline: 2px solid var(--hg-accent); outline-offset: 2px; border-radius: var(--hg-r-chip);
}}

/* States: pressed and disabled on every button. */
:is([data-testid="stMain"], [data-testid="stSidebar"]) :is(button, .stLinkButton a):active {{
    transform: scale(.98);
}}
:is([data-testid="stMain"], [data-testid="stSidebar"]) button:disabled {{
    opacity: .5; cursor: not-allowed; transform: none;
}}
@media (prefers-reduced-motion: reduce) {{
    :is([data-testid="stMain"], [data-testid="stSidebar"]) :is(button, .stLinkButton a):active,
    [data-testid="stMain"] .hg-card summary::after {{ transform: none; transition: none; }}
}}

/* Controls: one radius family; pills round. */
:is([data-testid="stMain"], [data-testid="stSidebar"]) :is(
    .stButton button, .stLinkButton a, .stFormSubmitButton button
) {{
    border-radius: var(--hg-r-control);
}}
[data-testid="stMain"] [data-testid="stButtonGroup"] button {{ border-radius: var(--hg-r-pill); }}
/* Option chips and segmented controls wrap with an 8 px gap: never touching, never clipped. */
[data-testid="stMain"] [data-testid="stButtonGroup"] :has(> button) {{
    flex-wrap: wrap; gap: var(--hg-s2);
}}
[data-testid="stMain"] [data-testid="stButtonGroup"] button {{
    border-width: 1px; border-style: solid;  /* separate chips, not a joined segment */
}}
[data-testid="stMain"] [data-testid="stButtonGroup"] button:not([aria-checked="true"]):not([aria-pressed="true"]) {{
    border-color: #CBD5E1;
}}
/* Streamlit clears the left border of the chip after the chosen one (a joined segment). */
[data-testid="stMain"] [data-testid="stButtonGroup"] button[data-selected]
    + button[data-variant]:not([aria-checked="true"]):not([aria-pressed="true"]) {{
    border-left-color: #CBD5E1;
}}
[data-testid="stMain"] [data-testid="stButtonGroup"]
    button[data-variant]:not([aria-checked="true"]):not([aria-pressed="true"]):has(+ button[data-selected]) {{
    border-right-color: #CBD5E1;
}}

/* Cards: 14 px radius, hairline on the canvas, no shadow (elevation declared once). */
[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"] {{
    border-radius: var(--hg-r-card); box-shadow: none;
}}

/* The guide card's four buttons (C6 decision): «Εγκρίνω» primary; «Λεπτομέρειες» and
 * «Αγαπημένο» secondary; «Δεν μου κάνει» tertiary — text weight, same height. */
[data-testid="stMain"] :is([class*="st-key-pick-no-"], [class*="st-key-rent-no-"]) button {{
    background: transparent; border-color: transparent; color: var(--hg-muted);
}}
[data-testid="stMain"] :is([class*="st-key-pick-no-"], [class*="st-key-rent-no-"]) button p {{
    font-weight: 500;
}}
[data-testid="stMain"] :is([class*="st-key-pick-fav-"], [class*="st-key-rent-star-"])
    [data-testid="stBaseButton-primary"] {{
    background: var(--hg-warn-bg); border-color: var(--hg-warn-line); color: var(--hg-warn-fg);
}}
/* The result header: «Πίσω» small and secondary next to the title. */
[data-testid="stMain"] .st-key-guide-result-head [data-testid="stHorizontalBlock"] {{
    flex-wrap: nowrap; align-items: center; gap: var(--hg-s3);
}}
[data-testid="stMain"] .st-key-guide-result-head [data-testid="stColumn"] {{
    width: auto; min-width: 0; flex: 0 1 auto;
}}
[data-testid="stMain"] .st-key-guide-result-head [data-testid="stColumn"]:last-child {{
    flex: 1 1 auto;
}}
[data-testid="stMain"] .st-key-guide-result-head h3 {{ margin: 0; }}
[data-testid="stMain"] .st-key-guide-result-head button {{ min-height: var(--hg-target); }}
[data-testid="stMain"] .st-key-guide-result-head button p {{
    font-size: var(--hg-fs-subhead); font-weight: 600;
}}

/* Status tones: one token set for the card badge, the badges and the advice box. */
[data-testid="stMain"] .hg-st {{
    font-size: var(--hg-fs-footnote); border-radius: var(--hg-r-chip); padding: 2px 8px;
}}
[data-testid="stMain"] .hg-st-ok, .hg-b-good {{ background: var(--hg-ok-bg); color: var(--hg-ok-fg); }}
[data-testid="stMain"] .hg-st-unk, .hg-b-warn, .hg-b-drop {{
    background: var(--hg-warn-bg); color: var(--hg-warn-fg);
}}
[data-testid="stMain"] .hg-st-bad, .hg-b-bad {{ background: var(--hg-bad-bg); color: var(--hg-bad-fg); }}
[data-testid="stMain"] :is(.hg-st-neu, .hg-st-photo), .hg-b-muted {{
    background: var(--hg-neu-bg); color: var(--hg-neu-fg);
}}
.hg-advice-good {{ background: var(--hg-ok-bg); border-color: var(--hg-ok-line); color: var(--hg-ok-fg); }}
.hg-advice-warn {{ background: var(--hg-warn-bg); border-color: var(--hg-warn-line); color: var(--hg-warn-fg); }}
.hg-advice-bad {{ background: var(--hg-bad-bg); border-color: var(--hg-bad-line); color: var(--hg-bad-fg); }}
/* Verdict words of the six checks (areas.render_checks). */
.hg-v {{ font-weight: 700; }}
.hg-v-good {{ color: var(--hg-ok-fg); }}
.hg-v-mid {{ color: var(--hg-warn-fg); }}
.hg-v-warn {{ color: var(--hg-bad-fg); }}
.hg-v-unk {{ color: var(--hg-muted); }}

/* The compact card's text roles. */
[data-testid="stMain"] .hg-card {{ font-size: var(--hg-fs-subhead); line-height: 1.45; }}
[data-testid="stMain"] .hg-card > div + div {{ margin-top: var(--hg-s1); }}
[data-testid="stMain"] .hg-l1 .hg-price {{ font-size: var(--hg-fs-title); letter-spacing: -0.01em; }}
[data-testid="stMain"] .hg-rank {{ font-size: var(--hg-fs-headline); }}
[data-testid="stMain"] :is(.hg-more, .hg-hidden) {{ font-size: var(--hg-fs-footnote); }}
[data-testid="stMain"] .hg-desc {{ font-size: var(--hg-fs-subhead); }}
[data-testid="stMain"] .hg-sep {{ color: var(--hg-sep); }}
[data-testid="stMain"] [class*="st-key-card-"] h3 {{ font-size: var(--hg-fs-title); }}

/* Grouped lists: fact rows with inset separators, label muted, value ink, no bullets
 * (area cards, the six checks, the compare table). */
[data-testid="stMain"] [class*="st-key-area-card-"] ul {{ list-style: none; padding: 0; margin: 0; }}
[data-testid="stMain"] [class*="st-key-area-card-"] li {{
    padding: var(--hg-s2) 0; margin: 0; border-bottom: 1px solid var(--hg-line-2);
    color: var(--hg-ink);
}}
[data-testid="stMain"] [class*="st-key-area-card-"] li:last-child {{ border-bottom: none; }}
[data-testid="stMain"] [class*="st-key-area-card-"] li strong {{
    display: block; font-size: var(--hg-fs-footnote); font-weight: 500; color: var(--hg-muted);
}}
[data-testid="stMain"] [class*="st-key-area-card-"] code {{
    background: none; color: var(--hg-accent); padding: 0; font-size: var(--hg-fs-body);
}}
[data-testid="stMain"] .hg-check {{ padding: var(--hg-s2) 0; border-bottom: 1px solid var(--hg-line-2); }}
[data-testid="stMain"] [data-testid="stMarkdownContainer"] table {{ border: none; }}
[data-testid="stMain"] [data-testid="stMarkdownContainer"] :is(th, td) {{
    border: none; border-bottom: 1px solid var(--hg-line-2); padding: var(--hg-s2) var(--hg-s2);
}}
[data-testid="stMain"] [data-testid="stMarkdownContainer"] td:not(:first-child) {{ color: var(--hg-ink); }}

/* The listing page: a page title and the actions within reach at the bottom of the screen. */
[data-testid="stMain"] [class*="st-key-act-l-"] {{
    position: sticky; bottom: 0; z-index: 2; background: var(--hg-canvas);
    padding: var(--hg-s2) 0; border-top: 1px solid var(--hg-line);
}}

/* Identity: the wordmark set with intent, the data line as a quiet second line. */
[data-testid="stMain"] .st-key-app-head {{ gap: 2px; padding-bottom: var(--hg-s1); }}
[data-testid="stMain"] .st-key-app-head [data-testid="stMarkdownContainer"] {{ margin: 0; }}
[data-testid="stMain"] .hg-app-head {{
    font-size: var(--hg-fs-headline); font-weight: 750; letter-spacing: -0.01em;
    color: var(--hg-accent); line-height: 1.3;
}}
[data-testid="stMain"] .st-key-app-head [data-testid="stCaptionContainer"] p {{
    color: var(--hg-muted); margin: 0;
}}
/* Page pills: quiet until chosen. */
[data-testid="stMain"] .st-key-nav_pill button[aria-checked="false"] {{
    background: transparent; border-color: var(--hg-line); color: var(--hg-ink-soft);
}}
/* The sidebar opener: a hairline control, not a floating card. */
header[data-testid="stHeader"] [data-testid="stExpandSidebarButton"] {{
    box-shadow: none; border-radius: var(--hg-r-control);
    min-width: var(--hg-target); min-height: var(--hg-target);
}}

/* Notes: Streamlit's alerts as the product's own notes — a hairline box on the surface,
 * tinted only when the tone carries meaning. */
[data-testid="stMain"] [data-testid="stAlert"] {{
    border: 1px solid var(--hg-line); border-radius: var(--hg-r-control); overflow: hidden;
}}
[data-testid="stMain"] [data-testid="stAlertContainer"] {{
    border-radius: 0; background: var(--hg-surface); color: var(--hg-ink-soft);
    padding: var(--hg-s3) var(--hg-s4);
}}
[data-testid="stMain"] [data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]) {{
    border-color: var(--hg-warn-line);
}}
[data-testid="stMain"] [data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]) {{
    background: var(--hg-warn-bg); color: var(--hg-warn-fg);
}}
[data-testid="stMain"] [data-testid="stAlert"]:has([data-testid="stAlertContentError"]) {{
    border-color: var(--hg-bad-line);
}}
[data-testid="stMain"] [data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]) {{
    background: var(--hg-bad-bg); color: var(--hg-bad-fg);
}}
[data-testid="stMain"] [data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]) {{
    border-color: var(--hg-ok-line);
}}
[data-testid="stMain"] [data-testid="stAlertContainer"]:has([data-testid="stAlertContentSuccess"]) {{
    background: var(--hg-ok-bg); color: var(--hg-ok-fg);
}}
[data-testid="stMain"] [data-testid="stAlertContainer"] p {{ color: inherit; }}

/* Rhythm in the result list: the first pick leads (accent hairline, the large price);
 * the rest step down to the title size. */
[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"]:has(.hg-card[data-rank="1"]) {{
    border-color: var(--hg-accent);
}}
[data-testid="stMain"] .hg-card[data-rank="1"] .hg-price {{ font-size: var(--hg-fs-large); }}

/* Map legend (components.map legend): footnote role. */
[data-testid="stMain"] .hg-legend {{ font-size: var(--hg-fs-footnote); }}
/* Streamlit's hover-only «link to heading» anchors: no use on a phone, a 16 px target. */
[data-testid="stMain"] [data-testid="stHeadingWithActionElements"] [data-testid="stHeaderActionElements"],
[data-testid="stMain"] [data-testid="stHeaderActionElements"] a {{
    display: none;
}}
/* Sidebar navigation text on the control role. */
[data-testid="stSidebar"] [role="radiogroup"] label p {{ font-size: var(--hg-fs-subhead); }}
/* Focusable regions Streamlit adds (the map canvas, its attribution): the same ring. */
[data-testid="stMain"] [tabindex]:focus-visible {{
    outline: 2px solid var(--hg-accent); outline-offset: 2px;
}}
[data-testid="stMain"] [data-testid="stDeckGlJsonChart"] [tabindex]:focus-visible {{
    box-shadow: inset 0 0 0 2px var(--hg-accent);  /* the map draws outline: none inline */
}}

/* Browser surfaces. */
::selection {{ background: #CCE7E2; color: var(--hg-ink); }}
html {{ caret-color: var(--hg-accent); accent-color: var(--hg-accent); }}
* {{ scrollbar-width: thin; scrollbar-color: #CBD5E1 transparent; }}
::-webkit-scrollbar {{ width: 8px; height: 8px; }}
::-webkit-scrollbar-thumb {{ background: #CBD5E1; border-radius: var(--hg-r-pill); }}
[data-testid="stMain"] a {{ text-underline-offset: 3px; text-decoration-thickness: 1px; }}
</style>
"""


def inject_css() -> None:
    """Inject the app's global CSS. Call once, early in ``main()`` (after
    ``st.set_page_config``). Idempotent and side-effect-only."""
    st.markdown(_CSS, unsafe_allow_html=True)
