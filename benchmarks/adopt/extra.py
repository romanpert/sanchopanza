"""Extra spares for the held-out chains that ran out of theirs (conan, dvc). Free, seeded.

    python benchmarks/adopt/extra.py      # writes extra-spares.json, prints the draw

The amendment of 2026-10-01 (`prereg-confirm.md`), approved by the owner before sealing the
confirmation and before any held-out session: conan-1, conan-2, dvc-1, conan-rel-1, conan-rel-2 and dvc-rel-1
stayed invalid because their three spares hide each other too. Nothing drawn before changes:
this replays the sealed draws (`chains.select`, `related.select`) with their seeds, checks it
gets exactly the spares they drew, and takes the next ones after them:

- a chain of `tasks.md`: the next bugs of the same shuffled list its spares came from, after the
  last chain's spares, `EXTRA` per chain in chain order, skipping any bug used anywhere;
- a related chain: the next bugs of its repository's shuffled pool, in pool order, that `grow`
  would have taken (a code file shared with the chain so far, its spares included, no failing
  test in common, no overlapping hunk), skipping any bug used anywhere.

`validate.py` tries them after the drawn spares, in this order.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import chains  # noqa: E402
import long  # noqa: E402
import related  # noqa: E402

EXTRA = 9
AMENDED = ("conan-1", "conan-2", "dvc-1", "conan-rel-1", "conan-rel-2", "dvc-rel-1")
OUT = HERE / "extra-spares.json"


def _ids(rows: list[dict[str, Any]]) -> list[str]:
    return [r["instance_id"] for r in rows]


def _used() -> set[str]:
    return {b["instance_id"] for c in [*chains.full(), *related.full(), *long.full()]
            for b in [*c["bugs"], *c["spares"]]}  # fmt: skip


def independent(used: set[str]) -> dict[str, list[dict[str, Any]]]:
    """Replays `chains.select`: the shuffled rest per repository, after the drawn spares."""
    sealed = {c["chain"]: _ids(c["spares"]) for c in chains.full()}
    by_repo = chains.load()
    rng = random.Random(chains.SEED)
    out: dict[str, list[dict[str, Any]]] = {}
    for repo, dev, held in chains.PLAN:
        drawn = chains.draw(by_repo[repo], dev + held, rng)
        taken = {r["instance_id"] for chain in drawn for r in chain}
        rest = [r for r in by_repo[repo] if chains.usable(r) and r["instance_id"] not in taken]
        rng.shuffle(rest)
        name = repo.split("/")[1].split(".")[0]
        for i in range(len(drawn)):
            if _ids(rest[i * 3 : (i + 1) * 3]) != sealed[f"{name}-{i + 1}"]:
                raise SystemExit(f"{name}-{i + 1}: the replay does not give the sealed spares")
        after = [r for r in rest[len(drawn) * 3 :] if r["instance_id"] not in used]
        for i in range(len(drawn)):
            out[f"{name}-{i + 1}"] = after[i * EXTRA : (i + 1) * EXTRA]
    return out


def _extend(chain: list[dict[str, Any]], pool: list[dict[str, Any]], used: set[str]) -> list:
    """`grow`'s rule, continued from the chain and its spares."""
    files = set().union(*(related.code_files(r) for r in chain))
    tests = {t for r in chain for t in r["FAIL_TO_PASS"]}
    taken: dict[str, list[tuple[int, int]]] = {}
    for r in chain:
        for f, s in related.spans(r["patch"]).items():
            taken[f] = [*taken.get(f, []), *s]
    out: list[dict[str, Any]] = []
    for row in pool:
        if len(out) == EXTRA:
            break
        if row["instance_id"] in used:
            continue
        mine, theirs = related.code_files(row), related.spans(row["patch"])
        if not mine & files or set(row["FAIL_TO_PASS"]) & tests or related.overlaps(theirs, taken):
            continue
        out.append(row)
        used.add(row["instance_id"])
        files |= mine
        tests |= set(row["FAIL_TO_PASS"])
        for f, s in theirs.items():
            taken[f] = [*taken.get(f, []), *s]
    return out


def linked(used: set[str]) -> dict[str, list[dict[str, Any]]]:
    """Replays `related.select`, then continues each amended chain over its repository's pool."""
    sealed = {c["chain"]: c for c in related.full()}
    by_repo = chains.load()
    chain_taken = {b["instance_id"] for c in chains.full() for b in [*c["bugs"], *c["spares"]]}
    rng = random.Random(related.SEED)
    out: dict[str, list[dict[str, Any]]] = {}
    for repo, dev, held in related.PLAN:
        rows = [r for r in by_repo[repo] if r["instance_id"] not in chain_taken]
        state = rng.getstate()
        drawn = related.draw(rows, dev + held, rng, 3)
        replay = random.Random()
        replay.setstate(state)
        pool = [n for r in rows
                if chains.usable(r) and related.code_files(n := related.normalized(r))]  # fmt: skip
        replay.shuffle(pool)
        name = repo.split("/")[1].split(".")[0]
        for i, (bugs, spares) in enumerate(drawn):
            chain = f"{name}-rel-{i + 1}"
            if _ids(bugs) != _ids(sealed[chain]["bugs"]) or _ids(spares) != _ids(
                sealed[chain]["spares"]
            ):
                raise SystemExit(f"{chain}: the replay does not give the sealed chain")
            if chain.split("__")[-1] in AMENDED:
                out[chain] = _extend([*bugs, *spares], pool, used)
    return out


def select() -> dict[str, list[dict[str, Any]]]:
    used = _used()
    picked = independent(used)
    wanted = {k: v for k, v in picked.items() if k.split("__")[-1] in AMENDED}
    used |= {r["instance_id"] for rows in wanted.values() for r in rows}
    return {**wanted, **linked(used)}


def spares(chain: str) -> list[dict[str, Any]]:
    """The extra spares of `chain` in full, [] for a chain the amendment does not name."""
    path = chains.CACHE / "extra-spares-full.json"
    if not path.exists():
        path.write_text(json.dumps(select(), ensure_ascii=False), encoding="utf-8")
    return json.loads(path.read_text(encoding="utf-8")).get(chain, [])


def main() -> int:
    picked = select()
    compact = {"seeds": [chains.SEED, related.SEED], "extra": EXTRA,
               "chains": {k: _ids(v) for k, v in picked.items()}}  # fmt: skip
    OUT.write_text(json.dumps(compact, indent=1), encoding="utf-8", newline="\n")
    (chains.CACHE / "extra-spares-full.json").write_text(json.dumps(picked, ensure_ascii=False),
                                                         encoding="utf-8")  # fmt: skip
    for k, v in picked.items():
        print(k, len(v), [i.rsplit(".", 1)[1] for i in _ids(v)])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
