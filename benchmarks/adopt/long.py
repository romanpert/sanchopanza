"""Long chains: many bugs of one repository asked in one session, long enough to reach the context
where a budget or memory can act. Free and seeded; validation runs in Docker (`validate.py`).

    python benchmarks/adopt/long.py        # writes long-selected.json

Why: in phase B, Sonnet 5.5 took about 5k tokens of context per SWE-smith bug and ended ten bugs
at 80k, below the default 160k budget, so nothing acted (dev log, "Phase B"). A session of 40
bugs should pass 200k. The bugs are drawn like the related chains (`related.py`): SWE-smith
`pr_mirror` rows of one repository, patches normalised, no two with overlapping hunks or a
FAIL_TO_PASS test in common, none in any chain or spare of `chains.py` or `related.py`; files may
be shared. Up to SPARES more are drawn the same way, to replace bugs that fail validation.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import chains
import related

HERE = Path(__file__).resolve().parent
SEED = 20261003
SIZE = 40
SPARES = 12
# (repo, name, split): development only for now; the owner decides on a held-out one.
PLAN = (("swesmith/pydantic__pydantic.acb0f10f", "pydantic__pydantic-long40-1", "dev"),)


def fits(row: dict[str, Any], taken: list[dict[str, Any]]) -> bool:
    mine, tests = related.spans(row["patch"]), set(row["FAIL_TO_PASS"])
    return not any(tests & set(b["FAIL_TO_PASS"])
                   or related.overlaps(mine, related.spans(b["patch"])) for b in taken)  # fmt: skip


def draw(
    rows: list[dict[str, Any]], size: int, spares: int, rng: random.Random
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pool = [n for r in rows if chains.usable(r) and related.code_files(n := related.normalized(r))]
    rng.shuffle(pool)
    picked: list[dict[str, Any]] = []
    for row in pool:
        if len(picked) == size + spares:
            break
        if fits(row, picked):
            picked.append(row)
    return picked[:size], picked[size:]


def select() -> list[dict[str, Any]]:
    by_repo = chains.load()
    sealed = {b["instance_id"] for c in [*chains.full(), *related.full()]
              for b in [*c["bugs"], *c["spares"]]}  # fmt: skip
    rng = random.Random(SEED)
    out = []
    for repo, name, split in PLAN:
        rows = [r for r in by_repo[repo] if r["instance_id"] not in sealed]
        bugs, spares = draw(rows, SIZE, SPARES, rng)
        if len(bugs) < SIZE:
            raise SystemExit(f"{repo}: only {len(bugs)} compatible bugs of {SIZE}")
        out.append({"chain": name, "repo": repo, "image": bugs[0]["image_name"], "split": split,
                    "kind": "long", "bugs": bugs, "spares": spares})  # fmt: skip
    return out


def full() -> list[dict[str, Any]]:
    path = chains.CACHE / "long-selected-full.json"
    if not path.exists():
        path.write_text(json.dumps(select(), ensure_ascii=False), encoding="utf-8")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    selected = select()
    (chains.CACHE / "long-selected-full.json").write_text(json.dumps(selected, ensure_ascii=False),
                                                           encoding="utf-8")  # fmt: skip
    compact = {"source": "SWE-bench/SWE-smith, pr_mirror rows", "source_sha256":
               chains.source_digest(), "seed": SEED, "kind": "long",
               "chains": [{"chain": c["chain"], "repo": c["repo"], "image": c["image"],
                           "split": c["split"], "bugs": [b["instance_id"] for b in c["bugs"]],
                           "spares": [b["instance_id"] for b in c["spares"]]}
                          for c in selected]}  # fmt: skip
    (HERE / "long-selected.json").write_text(json.dumps(compact, indent=1), encoding="utf-8",
                                             newline="\n")  # fmt: skip
    for c in selected:
        files = {f for b in c["bugs"] for f in related.code_files(b)}
        print(c["chain"], len(c["bugs"]), "bugs,", len(c["spares"]), "spares,", len(files), "files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
