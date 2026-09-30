"""Related chains: bugs of one repository where each later request touches code an earlier one
touched. Where memory between requests and sessions can pay; the chains of `chains.py` are
drawn the other way (pairwise different files) and measure that it does no harm. Free, seeded.

    python benchmarks/adopt/related.py        # writes related-selected.json

A related chain is `chains.CHAIN` SWE-smith `pr_mirror` bugs of one repository, none of them in
any chain of `chains.py`, drawn in order: a seed bug, then each next bug shares at least one code
file with a bug already in the chain (generated files such as pygments' `_mapping.py` do not
count), no two bugs share a FAIL_TO_PASS test, and no two bugs' hunks overlap in a file (all
five are undone together in one image). Each chain gets up to three spares, drawn the same way,
to replace a bug that fails validation. Which chains are development and which are held out is
fixed here, by the seed, before any session runs.

SWE-smith's `pr_mirror` patches also take the final newline off every file they touch (a hunk
that only adds the "No newline at end of file" marker). Two such patches on one file cannot both
apply, and the hunk is not part of the bug, so `normalize` drops it; the row keeps the original
as `patch_original`. Found by the first bake of starlette-rel-1, before any session ran.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any

import chains

HERE = Path(__file__).resolve().parent
SEED = 20261001
GENERATED = ("_mapping.py",)
NO_EOL = "\\ No newline at end of file"
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@")
_FILE = re.compile(r"^diff --git a/(\S+) b/")
# (repo, related chains in development, held out). Pygments has no related chain: its five
# carbon.py bugs, the only file with more than four, share FAIL_TO_PASS tests; astroid has none
# once hunks may not overlap, and conan takes its place.
PLAN = (
    ("swesmith/encode__starlette.db5063c2", 1, 1),
    ("swesmith/pydantic__pydantic.acb0f10f", 0, 1),
    ("swesmith/conan-io__conan.86f29e13", 0, 2),
    ("swesmith/iterative__dvc.1d6ea681", 0, 1),
)


def _sections(patch: str) -> list[list[str]]:
    """The patch cut at each `diff --git` line (anything before the first is dropped)."""
    out: list[list[str]] = []
    for line in patch.splitlines():
        if _FILE.match(line):
            out.append([line])
        elif out:
            out[-1].append(line)
    return out


def _hunks(section: list[str]) -> tuple[list[str], list[list[str]]]:
    """(the file header lines, each hunk with its `@@` line)."""
    head: list[str] = []
    hunks: list[list[str]] = []
    for line in section:
        if _HUNK.match(line):
            hunks.append([line])
        elif hunks:
            hunks[-1].append(line)
        else:
            head.append(line)
    return head, hunks


def _eol_only(hunk: list[str]) -> bool:
    """A hunk whose removed and added lines are the same text: it only moves the final newline."""
    body = [line for line in hunk[1:] if line != NO_EOL]
    removed = [line[1:] for line in body if line.startswith("-")]
    added = [line[1:] for line in body if line.startswith("+")]
    return bool(removed) and removed == added


def normalize(patch: str) -> str:
    """The patch without end-of-file-newline hunks, and without files left with no hunk."""
    kept: list[str] = []
    for section in _sections(patch):
        head, hunks = _hunks(section)
        real = [h for h in hunks if not _eol_only(h)]
        if real:
            kept.extend([*head, *(line for h in real for line in h)])
    return "\n".join(kept) + "\n" if kept else ""


def spans(patch: str) -> dict[str, list[tuple[int, int]]]:
    """Old-side line ranges of each hunk, per file."""
    out: dict[str, list[tuple[int, int]]] = {}
    for section in _sections(patch):
        name = _FILE.match(section[0]).group(1)  # type: ignore[union-attr]
        for hunk in _hunks(section)[1]:
            m = _HUNK.match(hunk[0])
            start, count = int(m.group(1)), int(m.group(2) or 1)  # type: ignore[union-attr]
            out.setdefault(name, []).append((start, start + max(count, 1) - 1))
    return out


def overlaps(a: dict[str, list[tuple[int, int]]], b: dict[str, list[tuple[int, int]]]) -> bool:
    return any(x0 <= y1 and y0 <= x1 for f in a.keys() & b.keys() for x0, x1 in a[f]
               for y0, y1 in b[f])  # fmt: skip


def normalized(row: dict[str, Any]) -> dict[str, Any]:
    return {**row, "patch": normalize(row["patch"]), "patch_original": row["patch"]}


def code_files(row: dict[str, Any]) -> frozenset[str]:
    return frozenset(f for f in chains.files_of(row["patch"]) if not f.endswith(GENERATED))


def grow(
    seed: dict[str, Any], pool: list[dict[str, Any]], used: set[str], size: int
) -> list[dict[str, Any]]:
    """The seed, then pool bugs (in pool order) sharing a code file with the chain so far."""
    chain = [seed]
    files = set(code_files(seed))
    tests = set(seed["FAIL_TO_PASS"])
    taken = spans(seed["patch"])
    for row in pool:
        if len(chain) == size:
            break
        if row["instance_id"] in used or row in chain:
            continue
        mine = code_files(row)
        theirs = spans(row["patch"])
        if not mine & files or set(row["FAIL_TO_PASS"]) & tests or overlaps(theirs, taken):
            continue
        chain.append(row)
        files |= mine
        tests |= set(row["FAIL_TO_PASS"])
        taken = {f: [*taken.get(f, []), *theirs.get(f, [])] for f in taken.keys() | theirs.keys()}
    return chain


def draw(
    rows: list[dict[str, Any]], count: int, rng: random.Random, spare: int
) -> list[tuple[list[dict[str, Any]], list[dict[str, Any]]]]:
    """`count` related chains of `chains.CHAIN` bugs with up to `spare` related spares each."""
    pool = [n for r in rows if chains.usable(r) and code_files(n := normalized(r))]
    rng.shuffle(pool)
    used: set[str] = set()
    out = []
    for seed in pool:
        if len(out) == count:
            break
        if seed["instance_id"] in used:
            continue
        chain = grow(seed, pool, used, chains.CHAIN + spare)
        if len(chain) < chains.CHAIN:
            continue  # spares are best effort; the chain itself is not
        used |= {r["instance_id"] for r in chain}
        out.append((chain[: chains.CHAIN], chain[chains.CHAIN :]))
    return out


def select(spare: int = 3) -> list[dict[str, Any]]:
    by_repo = chains.load()
    taken = {b["instance_id"] for c in chains.full() for b in [*c["bugs"], *c["spares"]]}
    rng = random.Random(SEED)
    out = []
    for repo, dev, held in PLAN:
        rows = [r for r in by_repo[repo] if r["instance_id"] not in taken]
        drawn = draw(rows, dev + held, rng, spare)
        if len(drawn) < dev + held:
            raise SystemExit(f"{repo}: only {len(drawn)} related chains of {dev + held}")
        for i, (bugs, spares) in enumerate(drawn):
            name = f"{repo.split('/')[1].split('.')[0]}-rel-{i + 1}"
            out.append({"chain": name, "repo": repo, "image": bugs[0]["image_name"],
                        "split": "dev" if i < dev else "held", "kind": "related",
                        "bugs": bugs, "spares": spares})  # fmt: skip
    return out


def full() -> list[dict[str, Any]]:
    """The selection with every row in full, kept in the cache like `chains.full`."""
    path = chains.CACHE / "related-selected-full.json"
    if not path.exists():
        path.write_text(json.dumps(select(), ensure_ascii=False), encoding="utf-8")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    selected = select()
    compact = {"source": "SWE-bench/SWE-smith, pr_mirror rows", "source_sha256":
               chains.source_digest(), "seed": SEED, "kind": "related",
               "chains": [{"chain": c["chain"], "repo": c["repo"], "image": c["image"],
                           "split": c["split"], "bugs": [b["instance_id"] for b in c["bugs"]],
                           "spares": [b["instance_id"] for b in c["spares"]],
                           "files": [sorted(code_files(b)) for b in c["bugs"]]}
                          for c in selected]}  # fmt: skip
    (HERE / "related-selected.json").write_text(json.dumps(compact, indent=1), encoding="utf-8",
                                                newline="\n")  # fmt: skip
    full = chains.CACHE / "related-selected-full.json"
    full.write_text(json.dumps(selected, ensure_ascii=False), encoding="utf-8")
    for c in selected:
        print(c["split"], c["chain"], [sorted(code_files(b)) for b in c["bugs"]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
