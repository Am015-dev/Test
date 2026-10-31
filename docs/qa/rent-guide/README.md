# Rent guide (W17, contract C2): phone screenshots, 390×844

The rentals in 02–10 are the **test fixture** (`tests/test_rent_guide.py::RENTALS`, 36 rental
dicts with the C1 keys), loaded through `queries.load_rent_listings` by a QA launcher, because
W16's real loader has not merged yet. The sale data is the live `data` branch DB. 11 is the
real app without the loader: the page says «Τα ενοίκια έρχονται σε λίγο».
Not shown: the note and «Ρώτα με» (they need ANTHROPIC_API_KEY; the AppTest covers them with
a fake client).

| file | screen |
|---|---|
| 01-step0-mode | step 0 «Τι ψάχνεις;» |
| 02-step1-budget | 1 «Πόσο τον μήνα;» |
| 03-step2-bedrooms | 2 «Πόσα υπνοδωμάτια;» |
| 04-step3-where / 05-step3-areas | 3 «Πού;» (and area chips) |
| 06-step4-kind | 4 «Τι σπίτι;» (Επιπλωμένο, ηλικία) |
| 07-results-top / 08-results-full | 5 «Η πρότασή μου» |
| 09-card-details | a card with «Λεπτομέρειες» open |
| 10-results-relaxations | nothing matches |
| 11-no-rent-data-yet | before C1 merges |
