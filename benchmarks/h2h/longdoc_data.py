"""LongBench v2 (Bai et al., 2024): the long-document suite of the head-to-head, cached outside
the repository and summarised with ids and counts only.

  <bcp venv>/python benchmarks/h2h/longdoc_data.py --fetch   # network: data.json (465 MB)
  python benchmarks/h2h/longdoc_data.py --draw                # free: the 60 tasks and their files
  python benchmarks/h2h/longdoc_data.py                       # free: counts

Why LongBench v2 (`THUDM/LongBench-v2`, MIT, no gate): 503 four-way multiple-choice questions
over contexts from 8k to 2M words, graded automatically by the letter (the official
`extract_answer` regex), with the context as one string that can be written to a file. Of the
other candidates, QASPER's papers are mostly under 100K characters, Loong and DocFinQA need a
model or a tolerance to grade free answers, and NovelQA asks for a licence.

The draw: the "Single-Document QA" and "Multi-Document QA" domains, contexts above
`MIN_CHARS` characters, `SIZE` tasks by `random.Random(SEED).sample` of the sorted ids. Each
drawn context is written once to `DOCS/<id>.txt`; a session gets a copy named `document.txt`.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass

CACHE = pathlib.Path.home() / ".cache" / "sanchopanza" / "longdoc"
RAW = CACHE / "hf" / "data.json"
TASKS = CACHE / "tasks.jsonl"
DOCS = CACHE / "docs"
REPO = "THUDM/LongBench-v2"
DOMAINS = ("Single-Document QA", "Multi-Document QA")
MIN_CHARS = 100_000
SEED = 20261006
SIZE = 60
LETTERS = ("A", "B", "C", "D")


@dataclass(frozen=True)
class Task:
    task_id: str
    domain: str
    sub_domain: str
    difficulty: str  # easy | hard
    length: str  # short | medium | long (the set's own bands, in words)
    question: str
    choices: tuple[str, str, str, str]
    gold: str  # A-D
    chars: int
    doc_path: str


# --- the official grade (LongBench pred.py) -----------------------------------------------------


def extract_answer(response: str | None) -> str | None:
    """LongBench v2's `extract_answer`, verbatim in behaviour."""
    text = (response or "").replace("*", "")
    match = re.search(r"The correct answer is \(([A-D])\)", text)
    if match:
        return match.group(1)
    match = re.search(r"The correct answer is ([A-D])", text)
    return match.group(1) if match else None


def last_answer(response: str | None) -> str | None:
    """The official extraction applied to the last line that has one: an agent may restate the
    format while working. Falls back to the official one on the whole reply."""
    lines = [x for x in (response or "").splitlines() if extract_answer(x)]
    return extract_answer(lines[-1]) if lines else extract_answer(response)


# --- the draw -----------------------------------------------------------------------------------


def eligible(rows: Sequence[Mapping]) -> list[Mapping]:
    return [r for r in rows if r["domain"] in DOMAINS and len(r["context"]) > MIN_CHARS]


def draw_ids(rows: Sequence[Mapping], size: int = SIZE, seed: int = SEED) -> list[str]:
    pool = sorted(str(r["_id"]) for r in eligible(rows))
    return random.Random(seed).sample(pool, min(size, len(pool)))


def to_task(row: Mapping, docs: pathlib.Path = DOCS) -> Task:
    return Task(
        task_id=str(row["_id"]), domain=row["domain"], sub_domain=row["sub_domain"],
        difficulty=row["difficulty"], length=row["length"], question=row["question"],
        choices=tuple(row[f"choice_{x}"] for x in LETTERS), gold=row["answer"],
        chars=len(row["context"]), doc_path=str((docs / f"{row['_id']}.txt").resolve()),
    )  # fmt: skip


def write_draw(rows: Sequence[Mapping], docs: pathlib.Path = DOCS,
               tasks: pathlib.Path = TASKS) -> list[Task]:  # fmt: skip
    by_id = {str(r["_id"]): r for r in rows}
    docs.mkdir(parents=True, exist_ok=True)
    chosen = [to_task(by_id[i], docs) for i in draw_ids(rows)]
    for task in chosen:
        path = pathlib.Path(task.doc_path)
        if not path.exists():
            path.write_text(by_id[task.task_id]["context"], encoding="utf-8")
    tasks.write_text("".join(json.dumps(asdict(t), ensure_ascii=False) + "\n" for t in chosen),
                     encoding="utf-8")  # fmt: skip
    return chosen


def load(path: pathlib.Path = TASKS) -> list[Task]:
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing: run longdoc_data.py --draw first")
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [Task(**{**r, "choices": tuple(r["choices"])}) for r in rows]


def summary(tasks: Sequence[Task]) -> dict:
    """Counts and sizes only."""
    chars = sorted(t.chars for t in tasks)
    return {
        "tasks": len(tasks),
        "by_domain": dict(Counter(t.domain for t in tasks).most_common()),
        "by_difficulty": dict(Counter(t.difficulty for t in tasks).most_common()),
        "by_length": dict(Counter(t.length for t in tasks).most_common()),
        "gold_letters": dict(sorted(Counter(t.gold for t in tasks).items())),
        "chars_min": chars[0] if chars else 0,
        "chars_median": chars[len(chars) // 2] if chars else 0,
        "chars_max": chars[-1] if chars else 0,
        "docs_missing": [t.task_id for t in tasks if not pathlib.Path(t.doc_path).exists()],
    }


def fetch() -> pathlib.Path:  # pragma: no cover - network
    from huggingface_hub import hf_hub_download

    got = hf_hub_download(REPO, "data.json", repo_type="dataset", local_dir=RAW.parent)
    return pathlib.Path(got)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--draw", action="store_true")
    args = ap.parse_args(argv)
    if args.fetch:
        fetch()
    if args.draw:
        rows = json.loads(RAW.read_text(encoding="utf-8"))
        print(json.dumps({"rows": len(rows), "eligible": len(eligible(rows))}))
        write_draw(rows)
    print(json.dumps(summary(load()), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
