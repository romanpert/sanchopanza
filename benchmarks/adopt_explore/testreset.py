"""Phase A's held-out chains graded again with the agent's test edits dropped. Docker, free.

    python -m benchmarks.adopt_explore.testreset plan               # which arms can change
    python -m benchmarks.adopt_explore.testreset grade [--chains a,b] [--no-repro]
    python -m benchmarks.adopt_explore.testreset report             # tables to report.md

The sealed grader (`run.grade_chain`) applies the agent's whole final.patch, its edits to the
project's tests included, and then runs the chain's FAIL_TO_PASS and PASS_TO_PASS* there. SWE-bench
runs the reference tests instead. This grades each arm's patch with every test file left out
(`is_test_path`), so the reference tests at base decide, with the sealed command byte for byte
(`docker_env.pytest`, held-out: no `--continue-on-collection-errors`).

Only an arm that touches an existing test file (or any conftest.py) can change: a new test file
is never among the graded node ids. The others are copied as they were, marked so. Each arm that
can change is also graded again with its original patch (`repro`), so a difference is put down to
the reset and not to a rebuilt image or a flaky test.

Images are baked under this module's own tags (`TAG`), the sealed bake's steps replicated
(`validate.bake_only`), so nothing another session uses is rebuilt or dropped. Nothing under
`runs/` is written: results go to `explore-testreset/<chain>/<arm>/grade.json`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ADOPT = Path(__file__).resolve().parents[1] / "adopt"
sys.path.insert(0, str(ADOPT))

import docker_env  # noqa: E402
import run  # noqa: E402

OUT = run.ROOT / "explore-testreset"
HELD = (
    "pygments__pygments-2", "encode__starlette-2", "pydantic__pydantic-1",
    "pydantic__pydantic-2", "conan-io__conan-1", "conan-io__conan-2", "pylint-dev__astroid-1",
    "encode__starlette-rel-2", "pydantic__pydantic-rel-1", "iterative__dvc-rel-1",
)  # fmt: skip
REL_ARMS = ("Nf", "Sf", "Sf-nojev1")
BASE_ARMS = ("N", "Sm", "Sm-nojev1")
TEST_DIRS = ("tests/", "testing/", "test/")  # conan keeps its suite in test/
TEST_NAME = re.compile(r"(^|/)(test_[^/]*\.py|[^/]*_test\.py|conftest\.py)$")
DIFF_HEAD = re.compile(r"^diff --git a/(\S+) b/(\S+)$", re.M)


def is_test_path(path: str) -> bool:
    return path.startswith(TEST_DIRS) or bool(TEST_NAME.search(path))


def arms_of(chain: str) -> tuple[str, ...]:
    return BASE_ARMS + (REL_ARMS if "-rel-" in chain else ())


def evidence(chain: str, arm: str) -> Path:
    """`Sm-nojev1` is the first reading's Sm, under `<chain>-nojev1/Sm`."""
    name, _, reading = arm.partition("-")
    return run.RUNS / (f"{chain}-{reading}" if reading else chain) / name


def file_diffs(patch: str) -> list[tuple[str, str]]:
    """(path, its whole `diff --git` block) per file, in order."""
    starts = [m.start() for m in DIFF_HEAD.finditer(patch)]
    blocks = [patch[a:b] for a, b in zip(starts, [*starts[1:], len(patch)], strict=True)]
    return [(DIFF_HEAD.match(block).group(2), block) for block in blocks]  # type: ignore[union-attr]


def status_of(block: str) -> str:
    if "\nnew file mode" in block:
        return "new"
    if "\ndeleted file mode" in block:
        return "deleted"
    return "renamed" if "\nrename from" in block else "modified"


def split(patch: str) -> tuple[str, list[dict[str, str]]]:
    """The patch without its test files, and what was dropped (path and status)."""
    kept = [block for path, block in file_diffs(patch) if not is_test_path(path)]
    dropped = [{"path": path, "status": status_of(block)}
               for path, block in file_diffs(patch) if is_test_path(path)]  # fmt: skip
    return "".join(kept), dropped


def can_change(dropped: list[dict[str, str]]) -> bool:
    """A new test file is not among the graded nodes; an existing one, or a conftest, may be."""
    return any(d["status"] != "new" or d["path"].endswith("conftest.py") for d in dropped)


def nodes_of(chain: dict[str, Any]) -> list[str]:
    bugs = chain["bugs"]
    return list(dict.fromkeys(n for b in bugs for n in (*b["FAIL_TO_PASS"], *b["PASS_TO_PASS_STAR"])))


def score(chain: dict[str, Any], outcome: dict[str, str]) -> dict[str, Any]:
    """`run.grade_chain`'s scoring, unchanged."""
    bugs = []
    for bug in chain["bugs"]:
        f2p = [outcome.get(t) == "PASSED" for t in bug["FAIL_TO_PASS"]]
        p2p = [outcome.get(t) == "PASSED" for t in bug["PASS_TO_PASS_STAR"]]
        broken = [t for t, ok in zip(bug["PASS_TO_PASS_STAR"], p2p, strict=True) if not ok]
        bugs.append({"instance_id": bug["instance_id"], "resolved": all(f2p) and all(p2p),
                     "f2p_passed": sum(f2p), "f2p": len(f2p), "p2p_broken": len(broken),
                     "p2p_broken_ids": broken[:20], "patch_applied": "<patch>" not in outcome})  # fmt: skip
    return {"resolved": sum(b["resolved"] for b in bugs), "bugs": bugs}


def tag(chain: str) -> str:
    return f"adopt-explore-{chain.lower().replace('_', '-')}:bugs"


def bake(chain: dict[str, Any]) -> str:
    """`validate.bake_only`'s steps under this module's tag: pull, bake, and check the baked
    bugs still break their FAIL_TO_PASS with the sealed command. The check runs the grader's
    node set, not FAIL_TO_PASS alone: a docstring example's id names its line range, a baked bug
    shifts it, and with only such ids selected pytest reports nothing (pydantic-rel-1)."""
    image = tag(chain["chain"])
    docker_env.pull(chain["image"])
    docker_env.bake(chain["image"], [b["patch"] for b in chain["bugs"]], image)
    f2p = {t for b in chain["bugs"] for t in b["FAIL_TO_PASS"]}
    outcome = docker_env.pytest(image, "", nodes_of(chain))
    passing = [t for t, s in outcome.items() if s == "PASSED" and t in f2p]
    if passing:
        raise SystemExit(f"{chain['chain']}: baked, FAIL_TO_PASS that pass: {passing[:5]}")
    return image


def graded(chain: dict[str, Any], image: str, patch: str) -> dict[str, Any]:
    # keep_collecting=False: held-out chains keep the sealed command (amendment 5).
    return score(chain, docker_env.pytest(image, patch, nodes_of(chain), keep_collecting=False))


def original(chain: str, arm: str) -> dict[str, Any]:
    return json.loads((evidence(chain, arm) / "grade.json").read_text(encoding="utf-8"))


def write(chain: str, arm: str, result: dict[str, Any]) -> None:
    folder = OUT / chain / arm
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "grade.json").write_text(json.dumps(result, indent=1), encoding="utf-8")


def unchanged(chain: str, arm: str, dropped: list[dict[str, str]]) -> dict[str, Any]:
    first = original(chain, arm)
    return {"chain": chain, "arm": arm, "source": str(evidence(chain, arm)),
            "mode": "unchanged-by-inspection", "dropped": dropped,
            "resolved": first["resolved"], "bugs": first["bugs"],
            "original": {"resolved": first["resolved"], "bugs": first["bugs"]}}  # fmt: skip


def regrade(chain: dict[str, Any], arm: str, image: str, repro: bool) -> dict[str, Any]:
    name = chain["chain"]
    patch = (evidence(name, arm) / "final.patch").read_text(encoding="utf-8")
    reset, dropped = split(patch)
    first = original(name, arm)
    result = {"chain": name, "arm": arm, "source": str(evidence(name, arm)), "mode": "tests-reset",
              "dropped": dropped, "collection": "stop", "seal": seal(),
              "original": {"resolved": first["resolved"], "bugs": first["bugs"]},
              **graded(chain, image, reset)}  # fmt: skip
    return {**result, "repro": graded(chain, image, patch)} if repro else result


def seal() -> str | None:
    path = run.REPO / "docs" / "results" / "2026-09-30-adopt" / "prereg-confirm.sha256"
    return path.read_text(encoding="utf-8").strip() if path.exists() else None


def classify(chain: str) -> list[tuple[str, list[dict[str, str]], bool]]:
    rows = []
    for arm in arms_of(chain):
        patch = (evidence(chain, arm) / "final.patch").read_text(encoding="utf-8")
        _, dropped = split(patch)
        rows.append((arm, dropped, can_change(dropped)))
    return rows


def grade_chain(name: str, repro: bool) -> None:
    rows = classify(name)
    for arm, dropped, _ in (r for r in rows if not r[2]):
        write(name, arm, unchanged(name, arm, dropped))
    changing = [arm for arm, _, change in rows if change]
    if not changing:
        print(name, "nothing can change", flush=True)
        return
    chain = run.chains()[name]
    image = tag(name)
    try:
        bake(chain)
        for arm in changing:
            result = regrade(chain, arm, image, repro)
            write(name, arm, result)
            print(name, arm, first_to_reset(result), flush=True)
    finally:
        docker_env.drop(image)


def first_to_reset(result: dict[str, Any]) -> str:
    again = f" (repro {result['repro']['resolved']})" if "repro" in result else ""
    return f"{result['original']['resolved']} -> {result['resolved']}{again}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("plan", "grade", "report"))
    parser.add_argument("--chains", default=",".join(HELD))
    parser.add_argument("--no-repro", action="store_true")
    args = parser.parse_args(argv)
    names = [c for c in args.chains.split(",") if c]
    if args.action == "plan":
        for name in names:
            for arm, dropped, change in classify(name):
                print(name, arm, "CAN CHANGE" if change else "unchanged", dropped)
    elif args.action == "grade":
        for name in names:
            grade_chain(name, not args.no_repro)
    else:
        from . import report

        report.write(names)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
