"""Validate each selected chain in Docker, before any session and before sealing. Free.

    python benchmarks/adopt/validate.py <chain-name|all>

A chain is valid when, with its five bugs baked into the image:
- every bug's FAIL_TO_PASS fails (none of them PASSED);
- fixing that bug alone (its patch reversed, the other four still in) makes all of its
  FAIL_TO_PASS pass.
A bug that fails either check is swapped for the chain's next spare that shares no file and no
failing test with the rest, in the drawn order, and the chain is baked again (at most `SWAPS`).
Related chains (`related.py`, `kind: related`) take a spare that shares a code file with the rest
instead, no failing test, and no overlapping hunk.

What grades a bug later: its FAIL_TO_PASS, and PASS_TO_PASS* = the PASS_TO_PASS tests that pass
when only that bug is fixed (tests another open bug breaks are not held against this one).
Writes chains-validated.json; the Docker tags stay for the sessions (`docker_env.drop` after).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import docker_env  # noqa: E402
import related  # noqa: E402
from chains import CACHE, files_of, full  # noqa: E402

SWAPS = 4
OUT = CACHE / "chains-validated.json"  # full rows: 4 MB, kept out of the repository
SUMMARY = HERE / "chains-validated-summary.json"


def tag_of(chain: str) -> str:
    return f"adopt-{chain.lower().replace('_', '-')}:bugs"


def nodes_of(bugs: list[dict[str, Any]]) -> list[str]:
    seen: dict[str, None] = {}
    for bug in bugs:
        for node in (*bug["FAIL_TO_PASS"], *bug["PASS_TO_PASS"]):
            seen.setdefault(node, None)
    return list(seen)


def check(chain: dict[str, Any], bugs: list[dict[str, Any]]) -> tuple[list[dict], list[int]]:
    """Per bug: its validation record; and the indexes of the bugs that failed it."""
    tag = tag_of(chain["chain"])
    docker_env.bake(chain["image"], [b["patch"] for b in bugs], tag)
    nodes = nodes_of(bugs)
    broken = docker_env.pytest(tag, "", nodes)
    records, bad = [], []
    for i, bug in enumerate(bugs):
        failing = [t for t in bug["FAIL_TO_PASS"] if broken.get(t) != "PASSED"]
        fixed = docker_env.pytest(tag, bug["patch"], nodes, reverse=True)
        passing = [t for t in bug["FAIL_TO_PASS"] if fixed.get(t) == "PASSED"]
        kept_p2p = [t for t in bug["PASS_TO_PASS"] if fixed.get(t) == "PASSED"]
        valid = len(failing) == len(bug["FAIL_TO_PASS"]) and len(passing) == len(failing)
        records.append({"instance_id": bug["instance_id"], "valid": valid,
                        "f2p_failing_with_bugs": len(failing),
                        "f2p_passing_when_fixed": len(passing),
                        "f2p": len(bug["FAIL_TO_PASS"]), "p2p_star": len(kept_p2p),
                        "PASS_TO_PASS_STAR": kept_p2p})  # fmt: skip
        if not valid:
            bad.append(i)
    return records, bad


def swap(chain: dict[str, Any], bugs: list[dict], index: int, tried: set[str]) -> bool:
    rest = [b for j, b in enumerate(bugs) if j != index]
    linked = chain.get("kind") == "related"
    of = related.code_files if linked else (lambda row: files_of(row["patch"]))
    files = set().union(*(of(b) for b in rest))
    tests = {t for b in rest for t in b["FAIL_TO_PASS"]}
    for spare in chain["spares"]:
        if spare["instance_id"] in tried:
            continue
        tried.add(spare["instance_id"])
        shares = bool(of(spare) & files)
        if shares != linked or set(spare["FAIL_TO_PASS"]) & tests:
            continue
        if linked and any(related.overlaps(related.spans(spare["patch"]),
                                           related.spans(b["patch"])) for b in rest):  # fmt: skip
            continue
        bugs[index] = spare
        return True
    return False


def validate(chain: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    docker_env.pull(chain["image"])
    bugs = list(chain["bugs"])
    tried = {b["instance_id"] for b in bugs}
    history = []
    for _ in range(SWAPS + 1):
        records, bad = check(chain, bugs)
        history.append([r["instance_id"] + (" ok" if r["valid"] else " INVALID") for r in records])
        if not bad:
            break
        if not all(swap(chain, bugs, i, tried) for i in bad):
            break
    valid = not bad
    for bug, record in zip(bugs, records, strict=True):
        bug["PASS_TO_PASS_STAR"] = record.pop("PASS_TO_PASS_STAR")
    return {**{k: v for k, v in chain.items() if k not in ("bugs", "spares")},
            "tag": tag_of(chain["chain"]), "valid": valid, "bugs": bugs, "records": records,
            "history": history, "seconds": round(time.time() - started)}  # fmt: skip


def main() -> int:
    wanted = sys.argv[1]
    chains = [*full(), *related.full()]
    done = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    for chain in chains:
        if wanted not in ("all", chain["chain"]):
            continue
        result = validate(chain)
        done[chain["chain"]] = result
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
        summary = {name: {"valid": c["valid"], "bugs": [b["instance_id"] for b in c["bugs"]],
                          "history": c["history"], "seconds": c["seconds"],
                          "records": c["records"]} for name, c in done.items()}  # fmt: skip
        SUMMARY.write_text(json.dumps(summary, indent=1), encoding="utf-8", newline="\n")
        print(chain["chain"], "valid" if result["valid"] else "INVALID", result["history"],
              f"{result['seconds']} s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
