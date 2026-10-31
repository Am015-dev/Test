# C11 — the card photo at 390 px

`before-*` is `main` at 7caf9c1 (no photo on the buyer card). `after-*` is `ws/card-thumb`
with that main merged in. Both builds ran on the same copy of the published DB (2026-10-31).
Run with `NODE_PATH=$(npm root -g) node docs/qa/photo/shots.js <label> <baseUrl>`.

The published DB has no XE photos yet: phase 1 (#96) fills them on the next weekly run. In
the copy used here, the 24 active XE listings whose search cards I captured from xe.gr on
2026-10-31 carry their real card photo URLs (`blob.cdn.xe.gr`). The Golden Home, RE/MAX and
Green-Acres rows already had theirs. No image was made up, downloaded or stored: the browser
loads each photo from the portal's CDN.

| screen | scrollWidth | photo boxes | CLS while photos load | page-swap CLS before · after |
|---|---|---|---|---|
| guide result | 390 | 10 × 96×72, stable (none of the ten has a photo yet) | 0 | 0,03 · 0,03 |
| search | 390 | 12 × 96×72, stable (none of the first 12 has a photo yet) | 0 | 0,00 · 0,01 |
| search «διαμέρισμα στο Μαρούσι» | 390 | 12 × 96×72, stable (1 photo loaded) | 0 | 0,26 · 0,29 |
| listing page | 390 | 1 × 324×243, stable (photo loaded) | 0 | 0 · 0 |

"Stable" means every `.hg-thumb` box measured the same size before and after its image
loaded. The page-swap CLS is Streamlit replacing the page right after a tap. It varies from
run to run on both builds (one earlier run of the base build measured 0,48; the Μαρούσι search
swap is about 0,27 on both), so it is reported apart from the photo check. Raw numbers: `before.json`, `after.json`.
