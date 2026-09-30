# Amendment 2: memory v4 against v3 on a fresh held-out set

Written 2026-10-01, before any item of the fresh set was built or scored. Sealed with the code it
names (`amendment-2.sha256`); the fresh items are built and scored once.

## Why a fresh set

The held-out half of `selection.json` was scored for v3 (amendment 1), so it has been seen. v4
was designed on development groups only; it is confirmed on groups nobody has looked at:
`selection-2.json` (`select_v4.py`, seed 20261002), every eligible SWE-chat group not in
`selection.json`, 74 groups, 402 sessions, all held out.

## What v4 changes (designed on development data, declared)

- The touch gives, at a Read, the record whose written lines the returned content shows most
  (nothing when none), and at an edit the record whose lines it replaces, else the newest; one
  record per touch (v3: the two newest records that changed the file).
- v4.1, after an adversarial review of v4: prints kept per file, in the order written, without
  failed calls, lines the same request took out again, imports, decorators or secret-like
  lines; words only (formatters' quotes, commas and spacing do not count); a line belongs to
  the newest record that wrote it. Neutral or better on development data; the review's other
  proposals (a floor of two lines, the newest at a Read with nothing in view, at a partial Read,
  the edit fallback once per file) lowered precision or recall there and were left out.
- The decider's cut at a session's first request: 0.8 (v3: 0.7).
- Development, all requests, `lineage or file`, replayed through the hook's code: v3 shipped
  0.944 / 0.603 / 0.049 (recall / precision / noise), v4.1 shipped 0.944 / 0.734 / 0.037.

## Arms on the fresh set

Both run by `confirm_v4.py`, items built by `build_v4b.py`:

- **v4**: v4.1 through the hook's own code (`replay_v4b.touch_replay`), first-request recall at
  0.8.
- **v3**: its touch rule reimplemented (`variants_v4b.Rule(newest_k=2)`, which matched the v3
  hook replay on development to within 0.002) plus first-request recall at 0.7, from the same
  cached decider answers.

## Success (all requests, label `lineage or file`, all five)

1. v4 precision > v3 precision.
2. v4 recall >= v3 recall - 0.01.
3. v4 noise <= v3 noise.
4. v4 recall >= 0.80 and precision >= 0.50.
5. v4 noise <= 0.10.

Reported, not criteria: `lineage` only, first requests, touch alone, characters per request.
Decider spend capped at 0.50 USD in code.
