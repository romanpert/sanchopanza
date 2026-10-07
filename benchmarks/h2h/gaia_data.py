"""GAIA validation, cached outside the repository, read without printing a question or an answer.

python benchmarks/h2h/gaia_data.py --fetch    # needs huggingface_hub and pyarrow, and the gate
python benchmarks/h2h/gaia_data.py            # free: counts by level and attachment, ids only

GAIA (Mialon et al., 2023) is gated on Hugging Face; the validation split keeps its answers, the
test split does not. `--fetch` downloads `2023/validation` into ~/.cache/sanchopanza/gaia/hf with
the token in ~/.cache/huggingface/token and writes `tasks.jsonl` beside it: one row per task with
the attachment's absolute path. Any Python with huggingface_hub and pyarrow can run the fetch;
everything else here is stdlib, so the runner's venv needs neither.

Nothing from a task's text reaches the repository or the terminal: the summary prints task ids
and counts. The set's own canary asks that it never be published in plain text.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

CACHE = pathlib.Path.home() / ".cache" / "sanchopanza" / "gaia"
HF = CACHE / "hf"
TASKS = CACHE / "tasks.jsonl"
REPO = "gaia-benchmark/GAIA"
SPLIT_DIR = "2023/validation"
# Attachment kinds the counts group by; anything else is reported by its own extension.
KINDS = {
    "pdf": "pdf", "xlsx": "xlsx", "xls": "xlsx", "csv": "csv", "png": "image", "jpg": "image",
    "jpeg": "image", "gif": "image", "mp3": "audio", "wav": "audio", "m4a": "audio",
    "docx": "docx", "pptx": "pptx", "py": "py", "zip": "zip", "txt": "txt", "json": "json",
    "jsonld": "json", "xml": "xml", "pdb": "pdb", "mov": "video", "mp4": "video",
}  # fmt: skip
_VIDEO = re.compile(r"youtube\.com|youtu\.be|\bvideo\b", re.I)


@dataclass(frozen=True)
class Task:
    task_id: str
    level: int
    question: str
    gold: str
    file_name: str
    file_path: str  # absolute, or "" when the task has no attachment
    tools: str  # the annotator's tool list: used only to flag tasks that need video

    @property
    def kind(self) -> str:
        return attachment_kind(self.file_name)

    @property
    def video(self) -> bool:
        return needs_video(self.question, self.tools)


def attachment_kind(file_name: str) -> str:
    if not file_name:
        return "none"
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    return KINDS.get(ext, ext or "other")


def needs_video(question: str, tools: str = "") -> bool:
    """A YouTube link or a video in the question, or a video tool in the annotator's list."""
    return bool(_VIDEO.search(question or "")) or bool(re.search(r"video", tools or "", re.I))


def row_to_task(row: Mapping[str, Any], root: pathlib.Path = HF) -> Task:
    meta = row.get("Annotator Metadata") or {}
    rel = str(row.get("file_path") or "")
    name = str(row.get("file_name") or "")
    path = (root / rel) if rel else (root / SPLIT_DIR / name if name else None)
    return Task(
        task_id=str(row["task_id"]),
        level=int(str(row["Level"]).strip()),
        question=str(row["Question"]),
        gold=str(row["Final answer"]),
        file_name=name,
        file_path=str(path.resolve()) if path else "",
        tools=str(meta.get("Tools") or "") if isinstance(meta, Mapping) else "",
    )


def load(path: pathlib.Path = TASKS) -> list[Task]:
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing: run gaia_data.py --fetch first")
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [Task(**r) for r in rows]


def summary(tasks: Sequence[Task]) -> dict[str, Any]:
    """Counts and ids only: never a question, never an answer."""
    missing = [t.task_id for t in tasks if t.file_path and not pathlib.Path(t.file_path).exists()]
    return {
        "tasks": len(tasks),
        "by_level": dict(sorted(Counter(t.level for t in tasks).items())),
        "by_attachment": dict(Counter(t.kind for t in tasks).most_common()),
        "by_level_and_attachment": {
            str(level): dict(Counter(t.kind for t in tasks if t.level == level).most_common())
            for level in sorted({t.level for t in tasks})
        },
        "video": len([t for t in tasks if t.video]),
        "video_by_level": dict(sorted(Counter(t.level for t in tasks if t.video).items())),
        "video_ids": sorted(t.task_id for t in tasks if t.video),
        "attachments_missing": missing,
    }


def select(
    tasks: Iterable[Task],
    levels: Iterable[int] = (1, 2, 3),
    no_video: bool = False,
    ids: Iterable[str] | None = None,
) -> list[Task]:
    wanted = set(ids) if ids is not None else None
    keep = set(levels)
    return [
        t
        for t in tasks
        if t.level in keep
        and not (no_video and t.video)
        and (wanted is None or t.task_id in wanted)
    ]


def fetch() -> pathlib.Path:  # pragma: no cover - network, gated set
    import pyarrow.parquet as pq
    from huggingface_hub import snapshot_download

    snapshot_download(REPO, repo_type="dataset", allow_patterns=[f"{SPLIT_DIR}/*"], local_dir=HF)
    table = pq.read_table(HF / SPLIT_DIR / "metadata.parquet").to_pylist()
    tasks = [row_to_task(r) for r in table]
    TASKS.write_text(
        "".join(json.dumps(t.__dict__, ensure_ascii=False) + "\n" for t in tasks), encoding="utf-8"
    )
    return TASKS


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fetch", action="store_true")
    args = ap.parse_args()
    if args.fetch:
        fetch()
    print(json.dumps(summary(load()), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
