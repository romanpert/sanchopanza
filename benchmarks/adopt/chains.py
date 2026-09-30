"""Long-session tasks: chains of real bugs from one repository, asked one after another in one
Claude Code session. Selection is free and seeded; validation runs in Docker (`validate.py`).

The bugs are SWE-smith's `pr_mirror` instances (SWE-bench/SWE-smith on Hugging Face): a merged
pull request of the repository, undone on a snapshot of it, with the tests that the pull request
made pass (FAIL_TO_PASS) and a sample that must keep passing (PASS_TO_PASS). One Docker image per
repository holds the snapshot and its environment, with a single commit and no history. The
issue text is SWE-smith's, written before this study.

A chain is `CHAIN` bugs of one repository whose patches touch pairwise different files and whose
FAIL_TO_PASS sets do not overlap, drawn with a fixed seed. Which chains go to development and
which are held out is decided here, by the same seed, before any session runs.
"""

from __future__ import annotations

import ast
import json
import random
import re
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SOURCE = Path.home() / ".cache" / "sanchopanza" / "swe-eval" / "swesmith_pr.jsonl"
SEED = 20260930
CHAIN = 5
# Repositories: large code bases with many mirrored PRs, pytest suites, images under ~6 GB.
# (repo, chains in development, chains held out)
PLAN = (
    ("swesmith/pygments__pygments.27649ebb", 1, 1),
    ("swesmith/encode__starlette.db5063c2", 1, 1),
    ("swesmith/pydantic__pydantic.acb0f10f", 0, 2),
    ("swesmith/conan-io__conan.86f29e13", 0, 2),
    ("swesmith/iterative__dvc.1d6ea681", 0, 1),
    ("swesmith/pylint-dev__astroid.b114f6b5", 0, 1),
)
_FILES = re.compile(r"^diff --git a/(\S+) b/", re.M)


def files_of(patch: str) -> frozenset[str]:
    return frozenset(_FILES.findall(patch))


def listed(value: Any) -> list[str]:
    return list(value) if isinstance(value, list) else list(ast.literal_eval(value or "[]"))


def load() -> dict[str, list[dict[str, Any]]]:
    by_repo: dict[str, list[dict[str, Any]]] = {}
    for line in SOURCE.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        row["FAIL_TO_PASS"] = listed(row["FAIL_TO_PASS"])
        row["PASS_TO_PASS"] = listed(row["PASS_TO_PASS"])
        by_repo.setdefault(row["repo"], []).append(row)
    return by_repo


def usable(row: dict[str, Any]) -> bool:
    """One issue a person could file: a statement, 1-40 failing tests, code only in the patch."""
    files = files_of(row["patch"])
    return (
        bool(row["problem_statement"].strip())
        and 1 <= len(row["FAIL_TO_PASS"]) <= 40
        and bool(files)
        and not any(re.search(r"(^|/)tests?/", f) for f in files)
    )


def draw(rows: list[dict[str, Any]], count: int, rng: random.Random) -> list[list[dict[str, Any]]]:
    """`count` chains of CHAIN bugs, disjoint in files and in FAIL_TO_PASS, no bug used twice."""
    pool = [r for r in rows if usable(r)]
    rng.shuffle(pool)
    chains: list[list[dict[str, Any]]] = []
    used: set[str] = set()
    for _ in range(count):
        chain: list[dict[str, Any]] = []
        files: set[str] = set()
        tests: set[str] = set()
        for row in pool:
            if row["instance_id"] in used:
                continue
            mine = files_of(row["patch"])
            if mine & files or set(row["FAIL_TO_PASS"]) & tests:
                continue
            chain.append(row)
            files |= mine
            tests |= set(row["FAIL_TO_PASS"])
            used.add(row["instance_id"])
            if len(chain) == CHAIN:
                break
        if len(chain) == CHAIN:
            chains.append(chain)
    return chains


def select(spare: int = 3) -> list[dict[str, Any]]:
    """Every chain with its split. Each repository also gets `spare` extra bugs per chain, drawn
    after the chains, to replace a bug that fails validation (in their drawn order)."""
    by_repo = load()
    rng = random.Random(SEED)
    out = []
    for repo, dev, held in PLAN:
        chains = draw(by_repo[repo], dev + held, rng)
        taken = {r["instance_id"] for chain in chains for r in chain}
        rest = [r for r in by_repo[repo] if usable(r) and r["instance_id"] not in taken]
        rng.shuffle(rest)
        for i, chain in enumerate(chains):
            name = f"{repo.split('/')[1].split('.')[0]}-{i + 1}"
            spares = rest[i * spare : (i + 1) * spare]
            out.append({"chain": name, "repo": repo, "image": chain[0]["image_name"],
                        "split": "dev" if i < dev else "held", "bugs": chain,
                        "spares": spares})  # fmt: skip
    return out


CACHE = Path.home() / ".cache" / "sanchopanza" / "adopt"


def source_digest() -> str:
    import hashlib

    return hashlib.sha256(SOURCE.read_bytes()).hexdigest()


def full() -> list[dict[str, Any]]:
    """The selection with every row in full (patches, test lists): kept in the cache, since it
    is 14 MB and follows from the ids below and the source file."""
    path = CACHE / "chains-selected-full.json"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(select(), ensure_ascii=False), encoding="utf-8")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    chains = full()
    compact = {"source": "SWE-bench/SWE-smith, pr_mirror rows", "source_sha256": source_digest(),
               "seed": SEED, "chains": [{"chain": c["chain"], "repo": c["repo"],
               "image": c["image"],
               "split": c["split"], "bugs": [b["instance_id"] for b in c["bugs"]],
               "spares": [b["instance_id"] for b in c["spares"]]} for c in chains]}  # fmt: skip
    (HERE / "chains-selected.json").write_text(json.dumps(compact, indent=1), encoding="utf-8",
                                               newline="\n")  # fmt: skip
    for c in chains:
        print(c["split"], c["chain"], [b["instance_id"].rsplit(".", 1)[1] for b in c["bugs"]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
