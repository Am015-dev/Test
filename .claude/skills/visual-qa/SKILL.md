---
name: visual-qa
description: LOOK at the actual running product before claiming anything about its quality. Launches the Streamlit app, screenshots every page with real Chromium, and critiques what a user actually sees — broken rendering, blank/slow pages, ugly layout, empty states, leaking raw HTML. Use before any "the product is good / ready / worth €X" claim, at the start of any UI-improvement cycle, and whenever the user says the product is "bad", "half-finished", "ugly", or "doesn't work". Backend tests passing is NOT evidence the product looks right — only screenshots are.
---

# Visual QA — see the product before you judge it

The hard lesson this skill exists for: a full green test suite and a high self-assigned
"sellability score" hid a catastrophic bug for many cycles — every listing card rendered its
footer as **raw HTML text** because a blank line broke Streamlit's raw-HTML block. Nobody
caught it because nobody LOOKED. Never reason about UI quality from code alone. Screenshot it.

## Do this every UI cycle (and before any quality claim)

1. **Launch** the app (background), wait for health:
   ```bash
   streamlit run src/scout/ui/app.py --server.port=8510 --server.address=127.0.0.1 \
       --server.headless=true --server.fileWatcherType=none   # run_in_background
   # wait until: curl -s http://127.0.0.1:8510/_stcore/health  -> 200
   ```
2. **Screenshot every page** with Python Playwright (Chromium at `/opt/pw-browsers/chromium`).
   Wait ~20 s after networkidle — Streamlit reruns the whole script and cached fits (e.g.
   `load_valuation_summary`) take seconds; a short wait catches a spinner, not the page.
   Navigate the sidebar radio to hit Opportunities, Deals, Saved searches, Map, Listing detail.
3. **Read each PNG** and critique what a *user* sees, not what the code intends. Check for:
   - **Leaking raw HTML** (`<div ...>` shown as text) → a blank line inside a raw-HTML block.
     Fix: collapse inter-tag whitespace (`re.sub(r">\s+<", "><", html)`) before `st.markdown`.
   - **Blank / spinner-stuck pages** → a slow cached function; measure it, cache/precompute.
   - **Empty states** (no photos, "—" everywhere, 0 results) → fill or hide gracefully.
   - **Density & hierarchy** — oversized headers, cramped clusters, unreadable contrast.
   - **Broken flows** — a filter that empties the page, a button that does nothing.
4. **Fix the worst, re-screenshot, confirm.** A fix isn't done until the new screenshot proves it.
5. Only then update any score. If you didn't screenshot it, you don't get to call it good.

## Guardrails
- The sandbox blocks external image/map CDNs, so listing photos and map tiles may be blank
  here — judge layout/structure, and verify photo/map code separately; don't "fix" a blank
  that's only the sandbox.
- Keep the app launch in the background; never block the turn on it.
