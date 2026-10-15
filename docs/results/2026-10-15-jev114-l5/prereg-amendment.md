# Lot L5: amendment after data (B2's picture band at least 300 px)

Written 2026-10-15, **after** B1 (142 steps, complete) and after B2 halted on its third step.
It does not replace any sealed rule: metrics, arms, steps, statistics, verdicts and the product
rule are those of `prereg.md` (sha256 `36973863...df119d0`).

## What happened

B2 halted by its own rule (more than 10 failed calls) after 3 of 48 steps. Every failure was an
HTTP 400 "Invalid image dimensions" on `i14` and `i13` (12 calls each). Probes through the
capped decider (13 tiny calls, a grey JPEG and one Truth, about 0.0004 USD in the lot's ledger)
found that jev-1.14.0 refuses an image with a side of 256 or 270 px (1280x256, 1280x270,
1200x256, 600x256, 256x1100, 256x1280) and takes 280 and up (1280x280, 1280x290, 1280x300,
1568x330). The documented floor is 256 px a side; the real one is between 271 and 280. The
sealed picture allowed a band of 256 px (`vision.window`'s minimum was the documented side).

The same floor explains B1's one failed call (step a9223421: a last tile of 269 page px, sent
as 1280x269, failed the presence call). B1 is not re-run: that step kept its Box and zoom, as
sealed.

## The change

`vision.MIN_BAND = 300`: a ranking call's band of the page is at least 300 px tall (it was at
least 256). Nothing else changes. A band that was 300 px or taller gives the same picture, so
every answer already recorded for it is replayed as it was; only the calls that failed are
asked again, with the band widened to 300 px around the same elements.

B2 is relaunched from where it stopped, on the same 48 steps, the same rotation and the same
caps. The three steps already run keep their recorded answers. What was seen of them before
this amendment: the target's position in each arm (t14 1, 1, 1; i14 3, 2, 1; i13 3, 1, 1;
steps 2 and 3 of the image arms were incomplete).
