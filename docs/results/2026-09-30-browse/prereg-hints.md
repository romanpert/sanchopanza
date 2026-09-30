# Browse, Phase 1d: unnamed elements described by their classes and holder

Written 2026-09-30 before any confirmation call. Runner: `benchmarks/browse/hints_jev.py
--confirm`.

## Why

Of the 23 development targets Jev ranked below 20 (`misses.py`), five were unnamed SVG icons,
and their classes said what they do (`add-wishlist-new__icon`, `save-icon-favorite` inside a
"Save" button). Commit 8e84849 makes `elements_from_html` describe an element **with no name**
by the useful words of its classes and the name of the element holding it; named elements are
unchanged.

On Phase 1's 169 development steps (seen data; `hints-jev-dev.json`, 0.42 USD of Jev): R@10
77.5 -> 80.5 % (+3.0 [0.0, +5.9]), R@20 86.4 -> 87.0 % (+0.6 [-3.0, +4.1]). The target's own line
changed in 12 steps: two icons went from outside the top 50 to 1st and 2nd, one field fell from
6th to 18th. Most of the R@10 gain came from steps whose target did not change (21 up, 21 down),
which is the noise of asking Jev again about changed groups. So the claim to test is modest:
no harm, and the icon cases fixed.

## Steps and arms

Phase 1c's 142 confirmation steps, refetched and read by the current reader
(`steps-confirm-hints.jsonl`). BEFORE: JEV-BLEND on Phase 1c's steps, replayed from its
recording (R@10 82.4 %, R@20 89.4 %, as published). HINTS: JEV-BLEND on the new reading; a call
whose group did not change is served from Phase 1c's recording, the rest asked live and recorded
in `fixtures/browse-jev-hints-confirm.jsonl`.

## Decision rule, fixed now

The description ships as the reader's default if HINTS minus BEFORE has a paired-bootstrap lower
bound (5,000 resamples, seed 2030) above -3 points at both R@10 and R@20. Otherwise it becomes
opt-in and the result is published as it comes. Reported besides: every step whose target line
changed, with its rank before and after.

## Money

At most 1.00 USD of Jev (the runner stops before passing it); expected about 0.40.

## What would make this wrong

Only a few percent of targets change, so a real gain on them is small against the noise of
re-asking; the rule is non-inferiority for that reason. Jev is not deterministic.
