---
name: tune-scoring
description: Adjust the investment thesis — scoring weights, hard filters, opportunity threshold, yield reference, or rent assumptions — in strategy.yaml, then rescore and verify the impact. Use when the user wants different ranking behavior (e.g. weight yield more, change the metro-distance cap, the min floor, or the price/area bounds), or when listings are being unexpectedly excluded.
---

# Tune the scoring / investment thesis

The thesis lives in `strategy.yaml` (modeled by `config.py`) and is hot-editable in the UI
Strategy page. Scoring logic is in `scoring.py`; filters/exclusions are applied in the
pipeline + scoring.

## What each knob does

- `search`: `municipality` + `areas` (coverage), `price_min/max`, `area_min_m2`,
  `est_rent_eur_per_m2` (fallback rent when no comps — drives the yield signal).
- `hard_filters`: `min_floor` (ground/low floors excluded), `max_metro_distance_m`
  (listings farther than this are excluded). Exclusion sets `excluded=True` + a reason; it
  doesn't delete.
- `weights` (quality-first): relative importance of `newness`, `gross_yield`,
  `energy_class`, `undervaluation` (asking price vs the hedonic fair-value model — falls
  back to raw €/m² vs area median when too few comps to fit), `price_drop`,
  `is_currently_rented`, `is_private_seller`. Newness + energy (asset quality) outweigh
  undervaluation so efficient/new stock ranks above old flats that merely look cheap.
  They don't need to sum to 100 (`total()` normalizes).
- `scoring_reference.energy_liability_floor`: the final score is multiplied down for
  energy-inefficient stock (E/F/G — Greek Ε/Ζ/Η) to reflect EU-EPBD renovation mandates;
  the worst class keeps this fraction of its score (default 0.55), the best keeps 1.0.
  Energy-liability flats are also never flagged as `is_opportunity`.
- `opportunity_flag.price_per_m2_below_median_pct`: the €/m² threshold (vs area median) to
  flag a listing as an opportunity (drives the digest's TOP OPPORTUNITIES).
- `scoring_reference`: `yield_floor`/`yield_ceiling` (the yield range mapped to 0..1),
  `max_price_drop_pct` (drop size that earns full price-drop points).

## Steps

1. Edit `strategy.yaml`. Keep weights sensible relative to each other.

2. **Rescore the existing DB** without re-scraping (this is what the UI Strategy editor
   calls):
   ```bash
   cd /root/holargos && . .venv/bin/activate && python -c "
   from scout.pipeline import rescore_all
   print('rescored', rescore_all(), 'listings')
   "
   ```

3. **Verify the impact**: load listings and inspect the new score distribution and what's
   now excluded vs included:
   ```bash
   python -c "
   from scout.ui.queries import load_listings
   ls = load_listings(include_excluded=True, only_active=True)
   elig = [d for d in ls if not d['excluded']]
   import statistics as st
   print('eligible:', len(elig), 'excluded:', len(ls)-len(elig))
   if elig:
       sc=[d['score'] for d in elig]; print('score min/med/max:', round(min(sc),1), round(st.median(sc),1), round(max(sc),1))
   from collections import Counter
   print('exclusion reasons:', Counter(d['exclusion_reason'] for d in ls if d['excluded']))
   "
   ```

4. **Sanity-check** a few top and bottom listings make intuitive sense for the thesis. If
   too much is excluded, the hard filters are likely too tight (common: `max_metro_distance_m`
   when an area isn't near a configured metro POI).

5. If you changed scoring CODE (not just yaml), run `holargos-verify` and update
   `tests/test_scoring.py`. Commit (yaml-only changes also commit + merge to deploy).

## Notes
- Scoring runs per-area during the pipeline (medians computed within the run's listings)
  and globally in `rescore_all`. Keep areas on one metro corridor so a shared thesis fits.
- Changing the thesis never deletes data — only `excluded`/`score`/`is_opportunity` flip.
