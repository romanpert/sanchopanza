# Jev 1.14 and images on the browse ranking (lot L5: B1 Box, B2 the ranking with a screenshot)

Run of 2026-10-15 on Multimodal-Mind2Web, on the confirmation steps of
[2026-09-30-browse](../2026-09-30-browse/README.md). Jev only: 0 calls to Claude. Pre-registered in
`prereg.md` (sha256 `36973863...df119d0`, sealed at commit 011ec13 after an independent review),
with one amendment written after B2's first halt (`prereg-amendment.md`, commit 286939e: a
ranking picture's band is at least 300 px tall, because Jev refuses a side under about 280 px).
Every number below is in `report.json`, rebuilt for free from the rows and the labels by
`python -I benchmarks/jev114/l5.py`; `tests/test_jev114_l5.py` covers the helpers and the rule.

## Verdict

**Neither Box nor the screenshot beats the text ranking. By the sealed product rule a "vision"
mode in `sanchopanza browse` is not recommended.** The three tests of the rule, with Holm
across them, all came out "no concluyente". The model change holds up: in the ranking with
images, 1.14 is **no peor** than 1.13.

| Test (sealed) | Steps | New | Reference | Difference [95 % CI] | McNemar (new / ref only, p) | Verdict |
|---|---|---|---|---|---|---|
| B1 primary: BOX top 1 against TEXT13 top 1 | 142 | 35.9 % | 42.3 % | −6.3 [−16.2, +2.8] | 19 / 28, p 0.24 (Holm 0.73) | no concluyente |
| FUSE10 top 1 against TEXT13 top 1 | 142 | 42.3 % | 42.3 % | 0 [−9.2, +9.2] | 21 / 21, p 1 (Holm 1) | no concluyente |
| B2 image effect, R@10: `i14` against `t14` | 48 | 93.8 % | 93.8 % | 0 [−6.3, +6.3] | 1 / 1, p 1 (Holm 1) | no concluyente |
| B2 model effect, R@10: `i14` against `i13` | 48 | 93.8 % | 89.6 % | +4.2 [0, +10.4] | 2 / 0, p 0.5 (Holm 1) | **no peor** |

- **BOX** is 1.14's Box over the screenshot. It asks a presence question per 1280 px tile, then
  Box on the best tile, and picks the candidate whose box overlaps Box's answer most.
- **TEXT13** is the first element of 1.13's text ranking, recorded on 2026-09-30 and replayed
  free. The replay gives the published positions on all 142 steps.
- **FUSE10** keeps the text ranking's first 10 and picks among them the one Box's answer
  overlaps most.
- **`t14`, `i14` and `i13`** are the browse ranking as confirmed:
  - `t14` is 1.14 on text;
  - `i14` is 1.14 with each call's band of the page in the state, elements outlined and labelled
    E01...;
  - `i13` is `i14` with 1.13.

  All three ran live today on the first 16 steps of each split (48), in rotating order.

**Scale and power.** On 142 steps a top-1 difference has an interval of about ±9 points, and on
48 steps an R@10 difference has one of about ±6 to 10. Neither the image nor Box shows an effect
that size. The image effect at R@10 cannot clear the −2 point bound, because both arms are at
93.8 % with one step won and one lost.

## B1: Box over the screenshot (jev-1.14.0 only; Box answers HTTP 400 on 1.13)

| Pick (142 steps) | Top 1 | Against TEXT13 [95 % CI] |
|---|---|---|
| TEXT13: 1.13 text ranking, recorded | 42.3 % | |
| BOX: presence, then Box on the best tile | 35.9 % | −6.3 [−16.2, +2.8] |
| ZOOM: Box again on 640 px around the first box | 43.0 % | +0.7 [−8.5, +10.6] |
| FUSE10: the best overlap among the text's first 10 | 42.3 % | 0 [−9.2, +9.2] |

Secondary readings, descriptive:

- **BOX against 1.14's own text ranking, on the 48 B2 steps:** 35.4 % against 54.2 %, −18.8
  [−35.4, −2.1], p 0.064. FUSE10 on that ranking: 43.8 %, −10.4 [−25.0, +4.2].
- **The zoom** is better than one Box: +7.0 [+1.4, +13.4], p 0.041, 15 steps won against 5.
  The cause is that Box answers in steps of 2 % of the image. On a 1280 px tile that is 26 px,
  the height of a link.
- **Box as a ranking** (candidates by overlap): R@5 62.0 %, R@10 64.8 %, R@20 70.4 %, against
  82.4 % and 89.4 % at 10 and 20 for the text ranking.
- **Where the box lands:** its centre falls inside a target's box on 50.0 % of the steps.
- **Box's `shown` Truth** separates a right top 1 from a wrong one with an AUC of 0.70.
- **Failures:** one call failed. A last tile of 269 px was refused (see the image floor below),
  and that step kept its Box and zoom.
- **Cost:** 0.00075 USD a step, three calls of about 17,800 input tokens in all.

Box finds the region of the page more often than not, but not the element. A step's target
sits among nested candidates (a `div` around a `span` around a link) and among look-alike rows,
and a box placed 26 px off picks a neighbour. Even zoomed it only matches the text ranking's top
1, so the text ranking stays the better primitive here. Box does not lift the text's top 10
either: FUSE10 wins 21 steps and loses 21.

## B2: the ranking with the page in the state (48 steps)

| Arm | R@1 | R@5 | R@10 | R@20 | R@30 | USD a step |
|---|---|---|---|---|---|---|
| `t13rec`: 1.13 text, recorded 2026-09-30 | 45.8 % | 79.2 % | 89.6 % | 95.8 % | 95.8 % | |
| `t14`: 1.14 text | 54.2 % | 87.5 % | 93.8 % | 95.8 % | 100 % | 0.0062 |
| `i14`: 1.14 with the screenshot | **62.5 %** | 89.6 % | 93.8 % | 95.8 % | 100 % | 0.0078 |
| `i13`: 1.13 with the screenshot | 56.3 % | 79.2 % | 89.6 % | 93.8 % | 93.8 % | 0.0078 |

Every arm made all 18.4 calls a step on average, and no step was excluded. The 48 steps are
easier than the 142: 1.13's recording has R@10 89.6 % here against 82.4 % on all of them.

**The image does not move the ranking's recall** (R@10 and R@20 identical). It may move the
first place: R@1 is +8.3 points [−6.3, +22.9] for `i14` over `t14` (8 steps won, 4 lost,
p 0.39), not significant at this n. It costs 27 % more a step (about 2,200 image tokens on top
of 8,000 of text per call).

**The model, with the image** (`i14` against `i13`): R@10 +4.2 [0, +10.4], no peor, no step
lost; R@1 +6.3 [−4.2, +16.7]; R@30 100 % against 93.8 % (3 steps won).

**The model, on text** (`t14` against the recording `t13rec`, secondary, recording noise not
measured): R@10 +4.2 [−4.2, +12.5]; R@1 +8.3 [−2.1, +18.8].

**The image on 1.13** (`i13` against `t13rec`): R@10 0; R@1 +10.4 [−2.1, +22.9].

Phase 1 lost the elements without words, so they were to be reported apart. Only 3 of the 48
steps have such a target, and every arm has all 3 in its top 10. That is too few to say
anything.

## A floor the documentation does not state

Jev 1.14 answers HTTP 400 "Invalid image dimensions" to an image with a side of 256 or 270 px:

- refused: 1280x256, 1280x270, 1200x256, 600x256, 256x1100 and 256x1280;
- accepted: 1280x280, 1280x290, 1280x300 and 1568x330.

The vendor's page gives 256 px as the floor, and `providers.jev_assets` (`MIN_SIDE = 256`)
follows it. The real floor lies between 271 and 280 px. This is what halted B2's first launch
at its third step, and what failed B1's one call. The lot's own pictures now keep 300 px
(`vision.MIN_BAND`). `jev_assets` was not changed in this lot.

## Spend

**1.1988 USD** in the ledger for batch `jev114-l5`, against a cap of 1.50:

| Part | USD |
|---|---|
| Smoke on 11 + 2 development steps | 0.0415 |
| B1 | 0.1059 |
| B2, first launch (halted) | 0.0648 |
| Size probes | 0.0004 |
| B2 | 0.9860 |

On top of that come two preflights of about 13 micro-dollars each, outside the ledger. The
shared ledger stood at 3.654 USD of 4.50 when this lot closed. Claude: 0 USD.

## What this does not measure

- No navigation. Each step asks which element comes next on a recorded page, not whether an
  agent reaches its goal.
- 1.13's text ranking is not re-run today. TEXT13 and `t13rec` are the 2026-09-30 recording,
  and its noise against a re-run is not measured here (lot L1 measured about 1.5 decisions in
  100 changing on component benches).
- B2 covers 48 steps, not the plan's 71. With three live arms, 71 steps did not fit in the
  lot's 1.50 USD.
- The picture's design (band, red outlines, labels, 1 Mpx) and the tiling were fixed before the
  data and not tuned. A different design (set-of-mark on the whole viewport, a tighter crop
  for each element) is not measured.
- Box and the zoom were chosen on 11 development steps, where Box had 2 and the zoom 1. On the
  confirmation steps the zoom came out better.
