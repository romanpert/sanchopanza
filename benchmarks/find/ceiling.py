"""The shortlist ceiling of repository search, by strategy: free, code only, no model.

    python benchmarks/find/ceiling.py dev      # strategies on a dev sample (not the 117)
    python benchmarks/find/ceiling.py test     # the chosen strategies on the registered 117

The judge can only keep what the shortlist holds: with SHORTLIST fragments from BM25 over the
issue text, a gold file was in reach in 72.7 % of the 117 registered issues. Every strategy
here is code (it proposes; a judge would decide), and is compared on a dev sample of SWE-bench
Verified drawn with another seed and disjoint from the 117, so that choosing one does not
tune on the issues it is reported on.

Strategies (each yields SHORTLIST fragments):
- `base`: BM25 over fragments, the issue as the query (the registered arm).
- `ident`: the issue plus the identifiers it names (CamelCase, snake_case, dotted names, paths,
  traceback files), repeated so that they weigh more than prose words.
- `files`: two levels: BM25 over whole files picks files, each gives its best fragments.
- `paths`: files whose path or module name the issue names come first.
- `rrf`: reciprocal-rank fusion of the fragment ranking and the file ranking.
- `combo`: `ident` for the query, then `paths` and `rrf`.
"""

from __future__ import annotations

import json
import random
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import swebench  # noqa: E402

from sanchopanza.context.repo import _read, chunks, files  # noqa: E402
from sanchopanza.select import index_of  # noqa: E402
from sanchopanza.text import BM25Index  # noqa: E402

OUT = swebench.OUT / "ceiling"
SHORTLIST = swebench.SHORTLIST
DEV_SEED = 20260930
DEV_PER_REPO = 6

_CAMEL = re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+\b")
_SNAKE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
_DOTTED = re.compile(r"\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+\b")
_PATHS = re.compile(r"[\w./-]+\.(?:py|pyx|js|ts|rst|cfg|toml|txt)\b")
_TRACE = re.compile(r'File "([^"]+)", line \d+')
_BACKTICK = re.compile(r"`([^`\n]{2,80})`")


def identifiers(text: str) -> list[str]:
    """Names the issue gives code: what a person would grep for."""
    found: list[str] = []
    for pattern in (_TRACE, _PATHS, _DOTTED, _CAMEL, _SNAKE, _BACKTICK):
        for match in pattern.finditer(text):
            value = match.group(1) if pattern.groups else match.group(0)
            found += [value, *re.split(r"[./\s()]+", value)]
    return [w for w in dict.fromkeys(found) if len(w) >= 3]


def _split(name: str) -> str:
    return " ".join(re.sub(r"(?<=[a-z0-9])(?=[A-Z])|[_.]", " ", name).lower().split())


def dev_instances(exclude: set[str]) -> list[dict[str, Any]]:
    import pyarrow.parquet as pq

    rows = pq.read_table(swebench.DATA / "verified.parquet").to_pylist()
    rng = random.Random(DEV_SEED)
    by_repo: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sorted(rows, key=lambda r: r["instance_id"]):
        if row["instance_id"] not in exclude:
            by_repo[row["repo"]].append(row)
    out = []
    for repo in sorted(by_repo):
        out += rng.sample(by_repo[repo], min(DEV_PER_REPO, len(by_repo[repo])))
    return sorted(out, key=lambda r: r["instance_id"])


def _path_of(key: str) -> str:
    return key.rsplit(":", 1)[0]


def strategies(root: Path, issue: str) -> dict[str, list[str]]:
    """Each strategy's shortlist, as fragment keys."""
    fragments = chunks(root)
    index = index_of(fragments)
    keys = [c.key for c in fragments]
    by_file: dict[str, list[int]] = defaultdict(list)
    for i, key in enumerate(keys):
        by_file[_path_of(key)].append(i)
    names = identifiers(issue)
    boosted = issue + ("\n" + " ".join(names)) * 3

    def top(query: str, k: int = SHORTLIST) -> list[int]:
        return [i for i, _ in index.top(query, k)]

    listed = [rel for rel in files(root) if rel in by_file]
    docs = [f"{rel}\n{_read(root / rel) or ''}" for rel in listed]
    file_rank = [listed[i] for i, _ in BM25Index(docs).top(issue, 50)]

    def best_in(path: str, query: str, n: int) -> list[int]:
        scores = index.scores(query)
        return sorted(by_file[path], key=lambda i: -scores[i])[:n]

    def fill(first: list[int], rest: list[int]) -> list[int]:
        out = list(dict.fromkeys(first))
        out += [i for i in rest if i not in set(out)]
        return out[:SHORTLIST]

    named = [
        p
        for p in by_file
        if any(n == p or p.endswith("/" + n) or Path(p).stem == n.split(".")[-1] for n in names)
    ]
    fused: dict[int, float] = defaultdict(float)
    for rank, i in enumerate(top(issue, 200)):
        fused[i] += 1 / (60 + rank)
    for rank, path in enumerate(file_rank):
        for i in best_in(path, issue, 2):
            fused[i] += 1 / (60 + rank)
    rrf = [i for i, _ in sorted(fused.items(), key=lambda kv: -kv[1])]
    fused_b: dict[int, float] = defaultdict(float)
    for rank, i in enumerate(top(boosted, 200)):
        fused_b[i] += 1 / (60 + rank)
    for rank, path in enumerate(file_rank):
        for i in best_in(path, boosted, 2):
            fused_b[i] += 1 / (60 + rank)
    rrf_b = [i for i, _ in sorted(fused_b.items(), key=lambda kv: -kv[1])]
    # BM25 counts each query word once, so repeating identifiers weighs nothing: they get a
    # ranking of their own (with snake_case and CamelCase split into words), fused by rank.
    ident_query = " ".join([*names, *(_split(n) for n in names)])
    fused_i = dict(fused)
    for rank, i in enumerate(top(ident_query, 200) if ident_query else []):
        fused_i[i] = fused_i.get(i, 0.0) + 1 / (60 + rank)
    rrf_i = [i for i, _ in sorted(fused_i.items(), key=lambda kv: -kv[1])]
    out_idx = {
        "base": top(issue),
        "ident": top(boosted),
        "files": fill([i for p in file_rank[:20] for i in best_in(p, issue, 3)], top(issue)),
        "paths": fill([i for p in named[:15] for i in best_in(p, boosted, 2)], top(issue)),
        "rrf": rrf[:SHORTLIST],
        "combo": fill([i for p in named[:15] for i in best_in(p, boosted, 2)], rrf_b),
        "rrf_ident": rrf_i[:SHORTLIST],
    }
    return {name: [keys[i] for i in idx] for name, idx in out_idx.items()}


def run(sample: str) -> int:
    registered = swebench.instances()
    rows = registered if sample == "test" else dev_instances({r["instance_id"] for r in registered})
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{sample}{sys.argv[2] if len(sys.argv) > 2 else ''}.jsonl"
    done = (
        {json.loads(x)["id"] for x in path.read_text("utf-8").splitlines()}
        if path.exists()
        else set()
    )
    with path.open("a", encoding="utf-8") as out:
        for row in rows:
            if row["instance_id"] in done:
                continue
            started = time.time()
            try:
                root = swebench.checkout(row["repo"], row["base_commit"])
                lists = strategies(root, row["problem_statement"])
            except Exception as error:  # noqa: BLE001 - a checkout that fails is reported, not hidden
                out.write(
                    json.dumps({"id": row["instance_id"], "error": type(error).__name__}) + "\n"
                )
                continue
            gold = swebench.gold_files(row["patch"])
            hit = {k: any(g in {_path_of(x) for x in v} for g in gold) for k, v in lists.items()}
            out.write(
                json.dumps(
                    {
                        "id": row["instance_id"],
                        "repo": row["repo"],
                        "hit": hit,
                        "files": {k: len({_path_of(x) for x in v}) for k, v in lists.items()},
                        "s": round(time.time() - started, 1),
                    }
                )
                + "\n"
            )
            out.flush()
    rows_out = [json.loads(x) for x in path.read_text("utf-8").splitlines()]
    ok = [r for r in rows_out if "hit" in r]
    summary = {k: f"{sum(r['hit'][k] for r in ok)}/{len(ok)}" for k in ok[0]["hit"]} if ok else {}
    sys.stdout.write(
        json.dumps(
            {"sample": sample, "n": len(ok), "errors": len(rows_out) - len(ok), "ceiling": summary},
            indent=1,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1] if len(sys.argv) > 1 else "dev"))
