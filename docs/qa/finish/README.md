# W18 / C3 — short cards, compare, finish: before / after at 390×844

Shots: `NODE_PATH=$(npm root -g) node docs/qa/finish/shots.js docs/qa/finish/<dir> http://127.0.0.1:8501 a,d,h`
(app on the published DB, no `GITHUB_TOKEN` / `ANTHROPIC_API_KEY`). `shots.js` is a copy of
`docs/qa/shots.js` with the step-4 button label fixed («Η πρότασή μου»).

| screen | before | after |
|---|---|---|
| guide result (10 cards) | `before/a5-guide-result.png` — 7.184 px tall; ~12 lines and 5 buttons per card | `after/a5-guide-result.png` — 4.554 px; 5 lines, 2 buttons + approve row |
| guide, 20 cards | `before/a6-guide-ten-more.png` | `after/a6-guide-ten-more.png` — approve row only on the first ten |
| search | `before/d0-search.png` | `after/d0-search.png` — compact card, «Λεπτομέρειες» · «Αγαπημένο» |
| compare | `before/h2-compare.png` — 12-row table | `after/h2-compare.png` — 8 rows, then the two compact cards |
| listing page | `before/d1-listing-page.png` | `after/d1-listing-page.png` — full card (unchanged) |

`overflow.json` in each folder: `scrollWidth` = 390 on every shot (no horizontal scroll).
