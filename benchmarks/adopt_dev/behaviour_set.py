"""The development set of the find nudge probe: 7 "behaviour-only" SWE-bench Verified issues
and 3 controls, by a rule fixed before any session. Free: git and the dataset, no model.

    python -m benchmarks.adopt_dev.behaviour_set draw     # -> behaviour-set.json (once)
    python -m benchmarks.adopt_dev.behaviour_set check    # ids still outside every exclusion

Why: in the alwaysLoad probe 9 of 10 issues named the symbol or file to change, so find was never
needed. This set asks the question where it can be needed.

The rule (written before the draw, not changed after):

- Data: `verified.parquet` of the find line (`benchmarks/find/swebench.py`), the file phase D's
  `draw.py` read; rows with an image in `singles_run`'s cached Verified rows; difficulty
  "<15 min fix" or "15 min - 1 hour" (one probe session should cost about 0.5-0.7 USD).
- Excluded: every id of `benchmarks/adopt_d/used-ids.json` (300, which hold phase A's singles and
  the find line's samples), every id anywhere in `benchmarks/adopt_d/singles-d.json` (phase D,
  held out and spares), every id of `benchmarks/adopt/singles-selected.json`, and the alwaysLoad
  probe's 10.
- Order: the pool sorted by id, shuffled whole with `random.Random(SEED)`.
- Tokens of a problem statement, in order of appearance, at most `MAX_TOKENS`: backtick spans
  with no space (trailing `()` cut), CamelCase and camelCase words, words with an underscore,
  dotted names (and the last part of each), each at least 3 characters.
- A token *points at the gold* when `git grep -l -F -I` at the base commit lists 1 to `MAX_HITS`
  files and one of them is changed by the gold patch, or when a gold file's path ends with it.
- Behaviour-only: no token points at the gold. Control: some token does.
- Walk the order, classify each, take the first 7 behaviour-only and the first 3 controls; every
  instance classified is recorded with its evidence.

Checkouts: a worktree per repository under ~/.cache/sanchopanza/adopt/dev-nudge/trees (the shared
blob-less clones of `benchmarks/find` fetch the base commit's blobs; their own checkout is left
alone), removed at the end.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CACHE = Path.home() / ".cache" / "sanchopanza"
DATA = CACHE / "find" / "swebench" / "verified.parquet"
CLONES = CACHE / "find" / "repos"
ROWS = CACHE / "swe-eval" / "verified-rows.json"
TREES = CACHE / "adopt" / "dev-nudge" / "trees"
OUT = HERE / "behaviour-set.json"
USED = REPO / "benchmarks" / "adopt_d" / "used-ids.json"
PHASE_D = REPO / "benchmarks" / "adopt_d" / "singles-d.json"
PHASE_A = REPO / "benchmarks" / "adopt" / "singles-selected.json"
# The alwaysLoad probe's 10 (benchmarks/adopt_dev/common.py, DEV1 + NEW).
ALWAYSLOAD = ("django__django-15315", "django__django-14752", "matplotlib__matplotlib-23412",
              "django__django-11206", "django__django-12708", "django__django-16631",
              "django__django-15104", "sympy__sympy-18763", "django__django-15563",
              "django__django-12143")  # fmt: skip
SEED = "20261003-dev-nudge"
LEVELS = ("<15 min fix", "15 min - 1 hour")
WANT = {"behaviour": 7, "control": 3}
MAX_TOKENS = 40
MAX_HITS = 5
MIN_LEN = 3

INSTANCE_ID = re.compile(r"[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+-\d+")
BACKTICK = re.compile(r"`([^`\n]+)`")
CAMEL = re.compile(r"\b(?:[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+|[a-z][a-z0-9]*[A-Z][A-Za-z0-9]*)\b")
SNAKE = re.compile(r"\b\w*[A-Za-z]\w*\b")
DOTTED = re.compile(r"\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+\b")


# ---- the rule, pure ------------------------------------------------------------------------------


def tokens(statement: str) -> list[str]:
    """The greppable tokens of a statement, in order of appearance, at most MAX_TOKENS."""
    found: list[tuple[int, str]] = []
    for m in BACKTICK.finditer(statement):
        span = m.group(1).strip().removesuffix("()")
        if span and not any(c.isspace() for c in span):
            found.append((m.start(), span))
    found += [(m.start(), m.group(0)) for m in CAMEL.finditer(statement)]
    found += [(m.start(), m.group(0)) for m in SNAKE.finditer(statement) if "_" in m.group(0)]
    for m in DOTTED.finditer(statement):
        parts = m.group(0).split(".")
        if all(len(p) >= 2 for p in parts):
            found += [(m.start(), m.group(0)), (m.start(), parts[-1])]
    out: list[str] = []
    for _, token in sorted(found, key=lambda pair: pair[0]):
        if len(token) >= MIN_LEN and token not in out:
            out.append(token)
    return out[:MAX_TOKENS]


def names_gold(token: str, gold: Iterable[str]) -> bool:
    """A gold file's path ends with the token (a file named in the statement)."""
    tail = token.replace("\\", "/").lstrip("./")
    return ("/" in tail or "." in tail) and any(g == tail or g.endswith("/" + tail) for g in gold)


def classify(
    words: list[str], gold: list[str], grep: Callable[[str], list[str]]
) -> tuple[str, dict[str, Any]]:
    """("control", the first token that points at the gold) or ("behaviour", {})."""
    for token in words:
        if names_gold(token, gold):
            return "control", {"token": token, "by": "path"}
        hits = grep(token)
        if 1 <= len(hits) <= MAX_HITS and set(hits) & set(gold):
            return "control", {"token": token, "by": "git grep", "hits": hits}
    return "behaviour", {}


def walk(
    order: list[dict[str, Any]], judge: Callable[[dict[str, Any]], tuple[str, dict[str, Any]]]
) -> tuple[dict[str, list[str]], list[dict[str, Any]]]:
    """Classify in order until WANT is met; returns the picks and every classified row."""
    picked: dict[str, list[str]] = {label: [] for label in WANT}
    seen: list[dict[str, Any]] = []
    for row in order:
        if all(len(picked[k]) >= n for k, n in WANT.items()):
            break
        label, evidence = judge(row)
        seen.append({"instance_id": row["instance_id"], "class": label, **evidence})
        if len(picked[label]) < WANT[label]:
            picked[label].append(row["instance_id"])
    return picked, seen


# ---- data and exclusions -------------------------------------------------------------------------


def excluded() -> set[str]:
    used = set(json.loads(USED.read_text(encoding="utf-8"))["used"])
    phase_d = set(INSTANCE_ID.findall(PHASE_D.read_text(encoding="utf-8")))
    phase_a = {r["instance_id"] for r in json.loads(PHASE_A.read_text(encoding="utf-8"))}
    return used | phase_d | phase_a | set(ALWAYSLOAD)


def gold_files(patch: str) -> list[str]:
    return sorted(set(re.findall(r"^diff --git a/(\S+) b/", patch, re.M)))


def pool() -> list[dict[str, Any]]:
    import pyarrow.parquet as pq

    images = json.loads(ROWS.read_text(encoding="utf-8"))
    taken = excluded()
    rows = [r for r in pq.read_table(DATA).to_pylist()
            if r["difficulty"] in LEVELS and r["instance_id"] not in taken
            and r["instance_id"] in images]  # fmt: skip
    return sorted(rows, key=lambda r: r["instance_id"])


def ordered(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    shuffled = list(rows)
    random.Random(SEED).shuffle(shuffled)
    return shuffled


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---- git -----------------------------------------------------------------------------------------


def tree_at(repo: str, commit: str) -> Path:
    """A worktree of the repository at `commit` (blobs fetched by the checkout, in one go)."""
    clone, tree = CLONES / repo.replace("/", "__"), TREES / repo.replace("/", "__")
    if not (tree / ".git").exists():
        TREES.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "-C", str(clone), "worktree", "add", "-q", "--detach", "--force",
                        str(tree), commit], check=True, timeout=1800)  # fmt: skip
    else:
        subprocess.run(["git", "-C", str(tree), "checkout", "-q", "-f", "--detach", commit],
                       check=True, timeout=1800)  # fmt: skip
    return tree


def git_grep(tree: Path, token: str) -> list[str]:
    done = subprocess.run(["git", "-C", str(tree), "grep", "-l", "-F", "-I", "-e", token],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=300)  # fmt: skip
    return [line.strip() for line in done.stdout.splitlines() if line.strip()]


def remove_trees() -> None:
    for tree in sorted(TREES.glob("*")) if TREES.exists() else []:
        clone = CLONES / tree.name
        subprocess.run(["git", "-C", str(clone), "worktree", "remove", "--force", str(tree)],
                       capture_output=True)  # fmt: skip


def judge_row(row: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    gold = gold_files(row["patch"])
    tree = tree_at(row["repo"], row["base_commit"])
    words = tokens(row["problem_statement"])
    label, evidence = classify(words, gold, lambda t: git_grep(tree, t))
    print(f"{row['instance_id']}: {label} {evidence.get('token', '')}", flush=True)
    return label, {"gold": gold, "tokens": len(words), **evidence}


# ---- commands ------------------------------------------------------------------------------------


def draw() -> dict[str, Any]:
    if OUT.exists():
        raise SystemExit(f"{OUT.name} exists: the draw is done once")
    rows = pool()
    try:
        picked, seen = walk(ordered(rows), judge_row)
    finally:
        remove_trees()
    images = json.loads(ROWS.read_text(encoding="utf-8"))
    chosen = [*picked["behaviour"], *picked["control"]]
    result = {"dataset": {"file": "~/.cache/sanchopanza/find/swebench/verified.parquet",
                          "sha256": sha256(DATA)},
              "rule": __doc__.split("The rule", 1)[1].split("Checkouts:", 1)[0].strip(),
              "seed": SEED, "levels": list(LEVELS), "max_tokens": MAX_TOKENS,
              "max_hits": MAX_HITS, "pool": len(rows), "excluded": len(excluded()),
              "behaviour": picked["behaviour"], "control": picked["control"],
              "images": {i: images[i]["image"] for i in chosen},
              "classified": seen}  # fmt: skip
    OUT.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    return result


def check() -> list[str]:
    """Problems: an id now excluded, or a pick no longer in the pool."""
    data = json.loads(OUT.read_text(encoding="utf-8"))
    chosen = [*data["behaviour"], *data["control"]]
    taken, available = excluded(), {r["instance_id"] for r in pool()}
    bad = [i for i in chosen if i in taken or i not in available]
    return [f"no longer usable: {bad}"] if bad else []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("draw", "check"))
    args = parser.parse_args(argv)
    if args.action == "draw":
        result = draw()
        print(json.dumps({k: result[k] for k in ("behaviour", "control", "pool")}, indent=1))
        return 0
    problems = check()
    print("\n".join(problems) or "BEHAVIOUR SET OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
