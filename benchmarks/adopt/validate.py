"""Validate each selected chain in Docker, before any session and before sealing. Free.

    python benchmarks/adopt/validate.py <chain-name|all>
    python benchmarks/adopt/validate.py --bake <chain> [...]   # rebuild images only, after the seal
    python benchmarks/adopt/validate.py --summary   # rewrite the summary from the cache

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
import os
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import docker_env  # noqa: E402
import extra  # noqa: E402
import long  # noqa: E402
import masking  # noqa: E402
import related  # noqa: E402
import run  # noqa: E402
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
    loose = chain.get("kind") == "long"  # long chains (long.py) may share files
    of = related.code_files if linked or loose else (lambda row: files_of(row["patch"]))
    files = set().union(*(of(b) for b in rest))
    tests = {t for b in rest for t in b["FAIL_TO_PASS"]}
    for spare in chain["spares"]:
        if spare["instance_id"] in tried:
            continue
        tried.add(spare["instance_id"])
        shares = bool(of(spare) & files)
        if (not loose and shares != linked) or set(spare["FAIL_TO_PASS"]) & tests:
            continue
        if (linked or loose) and any(related.overlaps(related.spans(spare["patch"]),
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
    for attempt in range(SWAPS + 1):
        records, bad = check(chain, bugs)
        history.append([r["instance_id"] + (" ok" if r["valid"] else " INVALID") for r in records])
        # No swap after the last check: one with no check after it was saved beside the records
        # of the bug it replaced (pydantic-long40-1).
        if not bad or attempt == SWAPS:
            break
        # Replace the culprits, not the victims: a bug that breaks a path every test goes
        # through failed its neighbours too (conan, dvc), and swapping those lost good bugs and
        # kept it. `masking.culprits` names it, or the failing bug itself when nothing does.
        out = masking.culprits(tag_of(chain["chain"]), bugs, bad, records)
        history.append([f"replace {masking.short(bugs[k])}" for k in out])
        # Swaps on a copy, kept only when every culprit found a spare: a partial swap left the
        # stored bugs out of step with the records of the bake they came from (conan-2, rel-1).
        trial = list(bugs)
        if not all(swap(chain, trial, i, tried) for i in out):
            break
        bugs = trial
    valid = not bad
    for bug, record in zip(bugs, records, strict=True):
        bug["PASS_TO_PASS_STAR"] = record.pop("PASS_TO_PASS_STAR")
    return {**{k: v for k, v in chain.items() if k not in ("bugs", "spares")},
            "tag": tag_of(chain["chain"]), "valid": valid, "bugs": bugs, "records": records,
            "history": history, "seconds": round(time.time() - started)}  # fmt: skip


def validated() -> dict[str, dict[str, Any]]:
    return json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}


def save(result: dict[str, Any]) -> None:
    """`result` into chains-validated.json and the summary kept in the repository. Read again
    under a lock (other chains stay as they are; two validations at once lose nothing) and
    written whole through a temporary file (a run reading it never sees half of it)."""
    with _locked(OUT.with_suffix(".lock")):
        done = {**validated(), result["chain"]: result}
        OUT.parent.mkdir(parents=True, exist_ok=True)
        _write(OUT, json.dumps(done, ensure_ascii=False))
        _write(SUMMARY, json.dumps(summarize(done), indent=1))


def summarize(done: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The summary kept in the repository. `sha256` hashes what sessions and grading read from
    the cache (`run.chain_digest`): sealed with it, a changed cache entry is refused."""
    return {name: {"valid": c["valid"], "bugs": [b["instance_id"] for b in c["bugs"]],
                   "sha256": run.chain_digest(c), "history": c["history"],
                   "seconds": c["seconds"], "records": c["records"]}
            for name, c in done.items()}  # fmt: skip


def _write(path: Path, text: str) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temp, path)


@contextmanager
def _locked(lock: Path, wait_s: float = 120.0) -> Iterator[None]:
    """An exclusive lock file: waits for another validation to finish, then says so."""
    started = time.time()
    while True:
        try:
            handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.time() - started > wait_s:
                raise SystemExit(f"{lock} held for {wait_s:.0f} s: another validation? "
                                 "remove it if none runs") from None  # fmt: skip
            time.sleep(1)
    try:
        yield
    finally:
        os.close(handle)
        lock.unlink(missing_ok=True)


def bake_only(name: str) -> None:
    """`name`'s image baked again from the bugs it validated with: no check, nothing saved. The
    validation summary is sealed with the confirmation, so after the seal images are only
    rebuilt (`validate.py --bake <chain>`), never validated again."""
    chain = validated().get(name)
    if not chain or not chain.get("valid"):
        raise SystemExit(f"{name}: not a valid chain in {OUT}")
    docker_env.pull(chain["image"])
    docker_env.bake(chain["image"], [b["patch"] for b in chain["bugs"]], chain["tag"])
    # The image is pulled by name, not digest: check the baked bugs still break their tests.
    nodes = [t for b in chain["bugs"] for t in b["FAIL_TO_PASS"]]
    passing = [t for t, status in docker_env.pytest(chain["tag"], "", nodes).items()
               if status == "PASSED"]  # fmt: skip
    if passing:
        raise SystemExit(f"{name}: baked again, FAIL_TO_PASS that pass: {passing[:5]}")


def with_extra(chains: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each chain with the amendment's extra spares (`extra.py`) after its drawn ones."""
    return [{**c, "spares": [*c["spares"], *extra.spares(c["chain"])]} for c in chains]


def main() -> int:
    if sys.argv[1] == "--bake":
        for name in sys.argv[2:]:
            bake_only(name)
            print(name, "baked", flush=True)
        return 0
    if run.sealed():
        # The summary is sealed with the confirmation: validating again would rewrite it.
        raise SystemExit("the confirmation is sealed: only `--bake` runs now")
    if sys.argv[1] == "--summary":
        _write(SUMMARY, json.dumps(summarize(validated()), indent=1))
        return 0
    wanted = sys.argv[1]
    chains = with_extra([*full(), *related.full(), *long.full()])
    for chain in chains:
        if wanted not in ("all", chain["chain"]):
            continue
        result = validate(chain)
        save(result)
        print(chain["chain"], "valid" if result["valid"] else "INVALID", result["history"],
              f"{result['seconds']} s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
