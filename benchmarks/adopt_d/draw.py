"""Phase D of the adoption study: 26 new held-out SWE-bench Verified singles. Free, no session.

    python benchmarks/adopt_d/draw.py scan    # every Verified id used before -> used-ids.json
    python benchmarks/adopt_d/draw.py draw    # the seeded draw -> singles-d.json (once only)
    python benchmarks/adopt_d/draw.py check   # scan again: is any drawn id now used elsewhere?

Written before the draw (`docs/results/2026-10-03-adopt-d/prereg.md`, "Tasks").

Data: `verified.parquet` of the find line (`benchmarks/find/swebench.py`: princeton-nlp's
SWE-bench Verified at `REVISION`, 500 rows with SWE-bench's `difficulty`), the same file phase A's
`singles.py` drew from. Its sha256 is recorded in the output. The images and problem statements
the runner uses come from `singles_run.rows()` (SWE-bench/SWE-bench_Verified through `datasets`);
the draw checks that every drawn id is there and records its image.

Used before, and so excluded (`scan`), the union of:
- phase A's 32 singles (development and held out, `benchmarks/adopt/singles-selected.json`);
- the find line's retrieval sample, its development sample and find-e2e's sample, through
  phase A's own `singles.used_by_find()` (sealed code, imported, not changed);
- every Verified id that appears in a file or folder name, or in the text of a file, under
  `~/.cache/sanchopanza` (every benchmark's cache: runs, logs, work copies, harness reports) and
  under this repository's `benchmarks/` and `docs/` (other than this folder). A file naming 400
  or more distinct Verified ids is a copy of the dataset, not a use: it is listed and not counted.
  Folders that hold a checkout or a virtual environment are not read inside, only named.

The draw (`draw`): per stratum, the unused rows of its difficulties sorted by id and shuffled
whole with `random.Random(SEED)`, strata in `PLAN` order; the first `held` are drawn, and the
rest follow in that order as the stratum's spares. An instance whose image fails validation
(prereg, "Validation before sealing") is replaced by its stratum's next spare that passes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ADOPT = REPO / "benchmarks" / "adopt"
sys.path.insert(0, str(ADOPT))
sys.path.insert(0, str(REPO / "benchmarks" / "find"))

CACHE = Path.home() / ".cache" / "sanchopanza"
USED = HERE / "used-ids.json"
OUT = HERE / "singles-d.json"
SEED = 20261003
PLAN = {  # stratum -> (SWE-bench difficulties, drawn); the same strata as phase A's held out
    "general-easy": (("<15 min fix",), 10),
    "general-medium": (("15 min - 1 hour",), 10),
    "hard": (("1-4 hours", ">4 hours"), 6),
}
SPARES_KEPT = 12  # spares written per stratum; the order beyond is the same shuffle
DUMP_AT = 400  # distinct Verified ids in one file: a copy of the dataset, not a use
WHERE_KEPT = 5  # places written per id (with the count of all): enough to audit, not a listing
PRUNE = {".git", "node_modules", "__pycache__", "site-packages", "Lib", "Include", "Scripts",
         "repos", "work", "void"}  # fmt: skip
BINARY = {".parquet", ".arrow", ".pyc", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4",
          ".webm", ".zip", ".gz", ".tar", ".whl", ".db", ".sqlite", ".pdf", ".exe", ".dll",
          ".pyd", ".so", ".bin", ".safetensors", ".pt", ".onnx", ".npy", ".npz"}  # fmt: skip
MAX_BYTES = 400 * 1024 * 1024


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def verified() -> list[dict[str, Any]]:
    import pyarrow.parquet as pq
    import swebench

    return pq.read_table(swebench.DATA / "verified.parquet").to_pylist()


def id_pattern(ids: set[str]) -> re.Pattern[bytes]:
    """`owner__repo-<number>` for the dataset's twelve prefixes, not followed by a digit."""
    prefixes = sorted({i.rsplit("-", 1)[0] for i in ids}, key=len, reverse=True)
    alternatives = b"|".join(re.escape(p.encode()) for p in prefixes)
    return re.compile(b"(?:" + alternatives + rb")-\d+(?!\d)")


def found_in(data: bytes, pattern: re.Pattern[bytes], ids: set[str]) -> set[str]:
    return {m.decode() for m in pattern.findall(data)} & ids


def is_venv_or_checkout(path: Path) -> bool:
    return (path / "pyvenv.cfg").exists() or (path / ".git").exists()


def scan_tree(root: Path, ids: set[str], skip: set[Path]) -> dict[str, Any]:
    """Verified ids in names and text under `root`: {id: [where]}, dumps and skipped files."""
    pattern = id_pattern(ids)
    hits: dict[str, set[str]] = {}
    dumps: list[str] = []
    skipped: list[str] = []

    def note(found: set[str], where: str) -> None:
        for i in found:
            hits.setdefault(i, set()).add(where)

    for top, dirs, files in os.walk(root):
        here = Path(top)
        kept = []
        for d in sorted(dirs):
            path = here / d
            note(found_in(d.encode(), pattern, ids), f"name:{path.as_posix()}")
            if path in skip:
                continue
            if d in PRUNE or is_venv_or_checkout(path):
                # Not read inside; only what it holds one level down is named.
                try:
                    for child in os.listdir(path):
                        note(found_in(child.encode(), pattern, ids),
                             f"name:{(path / child).as_posix()}")  # fmt: skip
                except OSError:
                    pass
                continue
            kept.append(d)
        dirs[:] = kept
        for f in sorted(files):
            path = here / f
            if path in skip:
                continue
            note(found_in(f.encode(), pattern, ids), f"name:{path.as_posix()}")
            if path.suffix.lower() in BINARY:
                continue
            try:
                if path.stat().st_size > MAX_BYTES:
                    skipped.append(path.as_posix())
                    continue
                data = path.read_bytes()
            except OSError:
                skipped.append(path.as_posix())
                continue
            found = found_in(data, pattern, ids)
            if len(found) >= DUMP_AT:
                dumps.append(f"{path.as_posix()} ({len(found)} ids)")
                continue
            note(found, f"text:{path.as_posix()}")
    return {"hits": {i: sorted(w) for i, w in hits.items()}, "dumps": dumps, "skipped": skipped}


def by_code() -> dict[str, list[str]]:
    """What earlier selections drew, from their own (sealed) code and files."""
    import singles

    out: dict[str, set[str]] = {}
    for row in json.loads((ADOPT / "singles-selected.json").read_text(encoding="utf-8")):
        out.setdefault(row["instance_id"], set()).add(f"phase A singles ({row['split']})")
    for i in singles.used_by_find():
        out.setdefault(i, set()).add("find: retrieval, its development sample or find-e2e")
    return {i: sorted(w) for i, w in out.items()}


def scan() -> dict[str, Any]:
    rows = verified()
    ids = {r["instance_id"] for r in rows}
    skip = {HERE}
    cache = scan_tree(CACHE, ids, skip)
    repo: dict[str, Any] = {"hits": {}, "dumps": [], "skipped": []}
    for sub in ("benchmarks", "docs"):
        part = scan_tree(REPO / sub, ids, skip)
        for i, where in part["hits"].items():
            repo["hits"][i] = sorted(set(repo["hits"].get(i, [])) | set(where))
        repo["dumps"] += part["dumps"]
        repo["skipped"] += part["skipped"]
    code = by_code()
    used: dict[str, list[str]] = {}
    for source in (code, cache["hits"], repo["hits"]):
        for i, where in source.items():
            used[i] = sorted(set(used.get(i, [])) | set(where))
    return {"dataset": dataset_record(), "used_count": len(used),
            "by_code": sorted(code), "dumps": [short(p) for p in cache["dumps"] + repo["dumps"]],
            "skipped": [short(p) for p in cache["skipped"] + repo["skipped"]],
            "used": {i: places(used[i]) for i in sorted(used)}}  # fmt: skip


def short(where: str) -> str:
    """A place relative to the repository or the home folder: no local path is written."""
    for root, name in ((REPO.as_posix() + "/", ""), (Path.home().as_posix() + "/", "~/")):
        where = where.replace(root, name)
    return where


def places(where: list[str]) -> dict[str, Any]:
    kept = sorted({short(w) for w in where})
    return {"count": len(kept), "first": kept[:WHERE_KEPT]}


def dataset_record() -> dict[str, Any]:
    import swebench

    path = swebench.DATA / "verified.parquet"
    return {"name": "princeton-nlp/SWE-bench_Verified", "revision": swebench.REVISION,
            "file": path.as_posix().replace(Path.home().as_posix(), "~"),
            "sha256": sha256(path)}  # fmt: skip


def draw(used: set[str]) -> dict[str, Any]:
    import singles_run

    images = singles_run.rows()
    rows = sorted((r for r in verified() if r["instance_id"] not in used),
                  key=lambda r: r["instance_id"])  # fmt: skip
    rng = random.Random(SEED)
    held: list[dict[str, Any]] = []
    spares: dict[str, list[dict[str, Any]]] = {}
    pools: dict[str, int] = {}
    for stratum, (levels, k) in PLAN.items():
        pool = [r for r in rows if r["difficulty"] in levels]
        pools[stratum] = len(pool)
        order = rng.sample(pool, len(pool))

        def entry(r: dict[str, Any], s: str = stratum) -> dict[str, Any]:
            if r["instance_id"] not in images:
                raise SystemExit(f"{r['instance_id']} has no row in singles_run.rows()")
            return {"instance_id": r["instance_id"], "repo": r["repo"],
                    "difficulty": r["difficulty"], "stratum": s,
                    "image": images[r["instance_id"]]["image"]}  # fmt: skip

        held += [entry(r) for r in order[:k]]
        spares[stratum] = [entry(r) for r in order[k : k + SPARES_KEPT]]
    return {"seed": SEED, "plan": {s: {"difficulties": list(v[0]), "drawn": v[1]}
                                   for s, v in PLAN.items()},
            "pool_after_exclusion": pools, "excluded": len(used),
            "held": held, "spares": spares}  # fmt: skip


def write(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8",
                    newline="\n")  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("scan", "draw", "check"))
    args = parser.parse_args(argv)
    if args.action == "scan":
        if OUT.exists():
            raise SystemExit("the draw is made: scan again with `check`, not `scan`")
        found = scan()
        write(USED, found)
        print(f"{found['used_count']} Verified ids used before; dumps {len(found['dumps'])}, "
              f"skipped {len(found['skipped'])}")  # fmt: skip
        return 0
    if args.action == "draw":
        if OUT.exists():
            raise SystemExit(f"{OUT.name} exists: a draw is made once")
        recorded = json.loads(USED.read_text(encoding="utf-8"))
        if recorded["dataset"]["sha256"] != dataset_record()["sha256"]:
            raise SystemExit("the dataset file changed since the scan")
        result = {"dataset": recorded["dataset"], "used_ids_sha256": sha256(USED),
                  **draw(set(recorded["used"]))}  # fmt: skip
        write(OUT, result)
        for row in result["held"]:
            print(row["stratum"], row["difficulty"], row["instance_id"])
        return 0
    drawn = json.loads(OUT.read_text(encoding="utf-8"))
    names = {r["instance_id"] for r in drawn["held"]}
    names |= {r["instance_id"] for rows in drawn["spares"].values() for r in rows}
    now = scan()["used"]
    clash = {i: now[i] for i in sorted(names & set(now))}
    print(json.dumps({"drawn_or_spare_now_used_elsewhere": clash}, indent=1))
    return 1 if clash else 0


if __name__ == "__main__":
    raise SystemExit(main())
