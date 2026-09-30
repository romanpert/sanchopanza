"""Which bug of an invalid chain hides which, and which bugs to replace. Docker, free.

    python benchmarks/adopt/masking.py <chain>     # the full pairwise diagnosis, for the record

A chain is invalid when fixing one bug alone does not make its FAIL_TO_PASS pass. In conan and
dvc that happened to most bugs at once, and by hand the cause was another bug of the chain
breaking a path every test goes through (conan-rel-1: `'LocalAPI' object has no attribute
'editable_packages'`). Replacing the victims loses good bugs and keeps the one that breaks the
rest; `culprits` finds the ones to replace instead, and `validate.py` swaps those:

- a failing bug that still fails with every other bug fixed too is broken on its own: itself;
- otherwise the smallest group whose fix, with its own, makes it pass, found by bisection
  (log2(n) runs of its FAIL_TO_PASS only): those maskers.

`main` runs the pairwise version (fix `i` with each `j`) and writes `masking-<chain>.json`.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import docker_env  # noqa: E402


def short(bug: dict[str, Any]) -> str:
    return bug["instance_id"].rsplit(".", 1)[1]


def passes_with(tag: str, bugs: list[dict[str, Any]], i: int, fixed: list[int]) -> bool:
    """Bug `i`'s FAIL_TO_PASS all pass with `i` and `fixed` undone in the chain's image."""
    nodes = bugs[i]["FAIL_TO_PASS"]
    patch = "".join(p if p.endswith("\n") else p + "\n"
                    for p in (bugs[k]["patch"] for k in [i, *fixed]))  # fmt: skip
    result = docker_env.pytest(tag, patch, nodes, reverse=True)
    return all(result.get(n) == "PASSED" for n in nodes)


def maskers(i: int, others: list[int], passes: Callable[[int, list[int]], bool]) -> list[int]:
    """[i] when `i` fails even with all `others` fixed; else a small group of `others` whose fix
    lets it pass, by bisection (the whole group when both halves are needed)."""
    if not passes(i, others):
        return [i]
    group = list(others)
    while len(group) > 1:
        half = len(group) // 2
        left, right = group[:half], group[half:]
        if passes(i, left):
            group = left
        elif passes(i, right):
            group = right
        else:
            break
    return group


def culprits(tag: str, bugs: list[dict[str, Any]], bad: list[int]) -> list[int]:
    """The bugs to replace for the failing ones: their maskers, or themselves."""
    found: set[int] = set()
    for i in bad:
        others = [k for k in range(len(bugs)) if k != i]
        found |= set(maskers(i, others, lambda j, fixed: passes_with(tag, bugs, j, fixed)))
    return sorted(found)


def pairwise(tag: str, bugs: list[dict[str, Any]], failing: list[int]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for i in failing:
        found = [short(bugs[j]) for j in range(len(bugs))
                 if j != i and passes_with(tag, bugs, i, [j])]  # fmt: skip
        out[short(bugs[i])] = found or ["alone"]
        print(short(bugs[i]), "masked by", out[short(bugs[i])], flush=True)
    return out


def main(argv: list[str]) -> int:
    import validate

    name = argv[0]
    chain = validate.validated()[name]
    bugs = chain["bugs"]
    failing = [k for k, r in enumerate(chain["records"]) if not r["valid"]]
    docker_env.pull(chain["image"])
    tag = validate.tag_of(name)
    docker_env.bake(chain["image"], [b["patch"] for b in bugs], tag)
    result = {"chain": name, "bugs": [short(b) for b in bugs],
              "masked_by": pairwise(tag, bugs, failing)}  # fmt: skip
    (validate.CACHE / f"masking-{name}.json").write_text(json.dumps(result, indent=1),
                                                          encoding="utf-8")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
