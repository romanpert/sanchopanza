# Jev 1.14 and images on the browse ranking (lot L5: B1 Box, B2 the ranking with a screenshot): pre-registration

Written 2026-10-15, before any Jev answer (1.13 or 1.14) on a screenshot of the confirmation
steps below. Instrument: `benchmarks/jev114/l5.py`, `benchmarks/jev114/l5_report.py`,
`benchmarks/browse/vision.py`, `benchmarks/browse/data.py --shots`, and the optional `picture`
of `sanchopanza.browse.rank` / `screenshot` of `points.browse.questions` (absent, the state is
byte for byte the recorded text one). `prereg.sha256` holds this file's hash; the live runner
refuses to spend when it differs or when anything under `src/`, `benchmarks/` or
`pyproject.toml` has uncommitted changes, and writes the commit, the Pillow version (the JPEG
bytes, and so the recording keys, depend on it) and the ledger path into `summary-<run>.json`.
Reviewed before sealing by an independent `revisor-prereg` agent; its findings are fixed here
(see the end).

## The question

Docs/results/2026-09-30-browse confirmed a text ranking of Mind2Web's next element: on 142 new
steps `jev-1.13.0` keeps the target in its top 20 in 89.4 %, top 10 in 82.4 %, top 1 in 42.3 %.
Phase 1 lost elements without words (icons, SVG, unnamed fields). Two questions:

- **B1.** Jev 1.14's new Box primitive, with a presence Truth, on the page's screenshot: does the
  candidate whose box best matches Jev's box pick the target (top 1) more often than the text
  ranking's first?
- **B2.** With each ranking call's part of the page in the state (elements outlined and
  labelled), does the ranking find the target more often (R@10) than from text alone? Is any
  change the image's or the model's?

Box exists only on 1.14 (1.13 answers it with HTTP 400), so B1 has no 1.13 arm. Images work on
both, so B2 separates the **image effect** (`i14` against `t14`, same model) from the **model
effect** (`i14` against `i13`, same image).

## What was seen before writing this

- The confirmation steps' text recording of 2026-09-30 (published), and their screenshots'
  sizes and candidate boxes while checking the download (no label was looked at with them).
- **A smoke on the development steps** (Phase 1's sample, `steps.jsonl`, no task shared with the
  confirmation), live, to measure cost and check the wire: B1 on 11 steps, B2 on 2 steps.
  0.0415 USD (ledger, batch `jev114-l5`). What it showed:
  - B1: 17,000 input tokens a step (presence over 2-4 tiles about 2,900 tokens each, Box about
    4,700, zoom about 1,500), **0.0006 USD a step**. Box answers come in steps of 0.02 of the image
    (about 26 px on a 1280 px tile). Top 1 on the 11 steps: Box 2, Box after the zoom 1, the text
    ranking (1.13, recorded) 4, the fusion below 3. The primary arm (Box without the zoom) was
    chosen on this, which is noise on 11 steps; the zoom was added because the vendor advises
    narrowing for small objects.
  - B2: a ranking call reads about 7,900 tokens of text, and about 2,100 more with the picture:
    per step of 559 elements about 0.0070 USD text only and 0.0089 with the picture (each
    image arm about 1.27 times the text arm). Positions on the 2 steps: t14 49 and none, i14 38
    and none, i13 18 and none.
  - No call failed; both models were served as asked.
- **The free replay of `t13rec`** with this runner (`--run t13`, before sealing): all 142
  steps rebuild the recorded calls and give the published positions on every step (top 1
  42.3 %, R@10 82.4 %, R@20 89.4 %), so the text state is unchanged by the `picture` hook.
  `rows-t13rec.jsonl` holds them.

## Data

- **Steps:** the 142 confirmation steps of 2026-09-30 (`~/.cache/sanchopanza/mind2web/steps-confirm.jsonl`,
  the same elements and positives). A step without a screenshot is left out and counted.
- **Screenshots and boxes:** `python -I benchmarks/browse/data.py --confirm --shots DIR`, the
  same rows of osunlp/Multimodal-Mind2Web through the Hugging Face rows API: the full-page
  screenshot (JPEG, 1280 px wide as served) and each candidate's `bounding_box_rect`. Stored in
  `C:\sp-runs\jev114\l5\data`, never in the repository. A candidate with no box or no area has
  no rect: Box can never pick it, and B2 does not outline it.
- **B2 steps:** the first 16 steps of each split in file order (website, domain, task), 48.
  The plan said 71 (half); it does not fit this lot's 1.50 USD: three live ranking arms cost
  about 0.024 USD a step (text alone is 0.0065 a step an arm, the 2026-09-30 figure), so 71
  steps are about 1.75 USD before B1. 48 steps are about 1.05 USD.

## B1: Box (`box14`, jev-1.14.0, images on)

Per step, three requests:

1. **Presence.** The screenshot cut top to bottom into tiles of 1280 page px (`vision.tiles`: a
   last piece under 256 px joins the tile above; at most 8 tiles, so nothing past 10,240 px is
   shown), each sent within 1,048,576 px (`PRESENCE_PIXELS`: 1024 x 1024 for a full tile). State: `goal` and `done` exactly
   as the ranking shows them, `tiles_note`, `tile_1`...`tile_n`. One Truth per tile
   (`l5.PRESENT`, `PRESENT_CRITERIA`): does this tile show the element to act on next.
2. **Box.** The tile with the highest presence (ties: the topmost) at full size (1280 x 1280
   at most), state `goal`, `done`, `screenshot`; questions `where` = Box (`l5.WHERE`) and
   `shown` = Truth (`l5.SHOWN`), in the same call as the vendor advises.
3. **Zoom.** A 640 x 640 page px square centred on that box (moved inside the page), the same
   two questions.

The box (fractions of the image) is mapped back to page pixels; every candidate with a rect is
ordered by IoU with it, then by the distance between centres, then by key (`vision.by_box`).

- **BOX** (primary): the first of that order after step 2.
- **ZOOM**: the same after step 3.
- **FUSE10**: among the first 10 of a text ranking, the candidate with the highest IoU with the
  BOX box (ties: the better text rank); the text's first when none overlaps it.
- **TEXT13**: the first of `jev-1.13.0`'s text ranking recorded on 2026-09-30, replayed free with
  today's code (`l5.py --run t13`), the reference. **TEXT14**: the first of B2's `t14`, on the
  48 B2 steps.

**Primary: top-1 accuracy of BOX minus TEXT13 on every step with a screenshot**, paired (exact
McNemar, item bootstrap). A step with no box (the call failed or answered none) counts as wrong
for BOX and is counted (`no_box`); a step any of whose three calls was not fully answered is
counted as `failed_steps` and kept. BOX is 1.14 reading an image and TEXT13 is 1.13 reading
text: Box exists only on 1.14, so this difference is the primitive's and the model's together;
BOX against TEXT14 on the 48 B2 steps is the same-model reading.

FUSE10 against TEXT13 is also tested and enters the product rule below (with Holm there).
Secondary, no multiplicity correction, descriptive: ZOOM against TEXT13; BOX and
FUSE10 (on `t14`'s ranking) against TEXT14 on the 48 B2 steps; ZOOM against BOX; BOX recall at
1, 5, 10, 20, 30 of its IoU order; the share of steps whose box centre falls inside a positive's
rect; AUC of `shown` for "BOX top 1 is right".

## B2: the ranking with a screenshot (`t14`, `i14`, `i13`)

`browse.rank` exactly as confirmed (every element, groups of 30 in page order, the best 30
re-judged, `blend` 0.5, the registered question `points.browse.NEXT`, `Thresholds(max_usd=0.05,
max_decisions=80)` a step, the first 50 kept):

- **`t14`:** jev-1.14.0, text only (the state of 2026-09-30).
- **`i14`:** jev-1.14.0, images on; each call's state also holds `screenshot` and
  `screenshot_note` (`points.browse.SCREENSHOT_NOTE`). The picture (`vision.marked_region`): the
  band of the page, at most 2,560 px tall and full width, that holds the most of that call's
  elements whole (24 px around them); each of the call's elements inside it outlined in red and
  labelled with its id (E01...); scaled to at most 1,048,576 px, JPEG. The questions do not
  change.
- **`i13`:** the same as `i14` with jev-1.13.0.
- **`t13rec`:** the 2026-09-30 recording of jev-1.13.0, text, replayed: a reference, not a live
  arm (today's 1.13 text ranking is not re-run: it would cost another 0.31 USD).

Each step runs the three live arms one after the other, the order rotating with the step's index
(t14-i14-i13, i14-i13-t14, i13-t14-i14), so each arm goes first on a third of the steps.

Metric: Recall@k, the target among the first k. **Primary: R@10**, two comparisons with Holm:

- **image effect:** `i14` minus `t14`;
- **model effect:** `i14` minus `i13`.

Secondary: R@1, R@20, R@30 for both; `i13` minus `t13rec` and `t14` minus `t13rec` at 1, 10 and
20 (the image on 1.13, and 1.14's text, against the recording, whose noise against a re-run is
not measured here); the steps whose positive has no name (the "wordless" ones), per arm,
descriptive; USD and calls a step per arm. A step counts only when no call of any of its three
arms failed; excluded steps are reported. A call fails when it raises, comes back without an
answer to every question, or comes from another model; a step also fails when its arm made
fewer calls than the tournament needs (`l5.calls_expected`: the Squire's own cap stopped it).

## Statistics and verdicts

`benchmarks/jev114/l5_report.py`, with lot L4's functions (`l4_stats`): exact McNemar on the
discordant pairs, a 95 % paired item bootstrap (10,000 replicas, seed 20261015; the website
cluster bootstrap reported beside it), Holm within B2's two primary comparisons (B1 has one).

- **mejora:** difference > 0 and (Holm) p < 0.05;
- **peor:** difference < 0 and (Holm) p < 0.05;
- **no peor:** the 95 % interval's lower bound above -2 points;
- otherwise **no concluyente**;
- **no medido** when fewer than 20 paired steps exist (a run halted early).

Power, said now: with 48 steps the interval on a difference in R@10 is about ±12 points, so
only a large image or model effect can be told from none; with 142 steps the top-1 interval is
about ±8 points.

## The product question, decided by this rule

A "vision" mode in `sanchopanza browse` is **recommended to build** if, with Holm across these
three, one of them is "mejora": BOX minus TEXT13 at top 1, FUSE10 minus TEXT13 at top 1, and
B2's image effect at R@10. Otherwise it is **not recommended** on this evidence, whatever a
secondary shows. `l5_report.product` computes it. The cost per step of each arm is reported
beside it.

## Running

- **Order:** B1 on all steps (four steps at a time), then `--run t13` (free), then B2 step by
  step. The live run does a `jev-preflight` for both models first (two calls of about 13
  micro-dollars each, outside the ledger). Expected duration 30-60 minutes, in the afternoon.
  Lot L6 spends on the same ledger today and may run at the same time; the caps are shared
  through the ledger, and a rate limit that fails calls is caught by the failure halts.
- **Requests:** at most 4 in flight. Every live call goes through `CappedDecider` on the
  shared ledger `C:\sp-runs\jev114\ledger.json` (4.50 USD in all) with batch `jev114-l5` capped
  at **1.50 USD** (the smoke's 0.0415 included). Answers are recorded per arm in
  `fixtures/jev114/browse-l5-<arm>.jsonl` (hashed keys and numbers, no text, no image), so a
  relaunch asks only what is missing. Claude: zero calls.
- **Halts** (the runner stops scheduling and exits 2; the steps already done are kept and
  analysed as they are; checked after each group of four B1 steps and after each B2 step): a cap
  refusal; an answer from a model other than the arm's (never used); more than
  5 failed calls in B1 or 10 in B2; a `STOP` file in `C:\sp-runs\jev114\l5`; live spend past 1.5
  times its estimate so far plus a margin (B1: 0.0008 USD a step + 0.01; B2: 0.0070 / 0.0089 /
  0.0089 USD per 559 elements a step for t14 / i14 / i13, + 0.02).
- **Expected spend:** B1 about 0.09 USD (142 x 0.0006); B2 about 1.05 USD (the recorded text
  cost of these 48 steps, 0.296, times 1 + 2 x 1.27); about 1.18 with the smoke.

## What will not be done

No change to `DEFAULT_MODEL`, to a threshold of `policy.py`, to the registered question, the
tournament or `blend`. No metric is swapped after the data. The picture's design (band, labels,
size) and the tiling are fixed here and not tuned on the confirmation steps.

## Review before sealing

The `revisor-prereg` review found, and this version fixes: a wrong-model answer inside the
ranking was swallowed by the Squire and counted as a complete step (now flagged, not used, and a
halt); partial answers and calls the Squire's cap prevented were not failures (now they are);
B1's per-step failure flag read a counter shared by concurrent steps (now from the step's own
calls); FUSE10 was in the product rule without a correction (now Holm across the three, computed
in code); the instrument list missed the statistics and the request path (now all of `src/` and
`benchmarks/`); rows were lost on a crash (now written in `finally`); too few steps could read
"no peor" (now "no medido" under 20). Not changed: the B2 overspend estimate still counts a step
replayed for free on a relaunch (it only loosens that halt; the caps do not move).
