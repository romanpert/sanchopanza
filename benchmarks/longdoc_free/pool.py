"""∞Bench En.QA (`longbook_qa_eng`) for lot longdoc-free: the pinned file, its novels, the frozen
ids and the dev draw. Free: no model, no network beyond the one download.

Design: docs/results/2026-10-16-longdoc-free/design.md. The file is the Hugging Face dataset
`xinrongzhang2022/InfiniteBench` at commit 90f0394333616266d9fe85824ceaf505093cbaa5,
`longbook_qa_eng.jsonl`, sha256 below: 351 questions over 69 novels (5-7 each), 298,903 to
3,171,853 characters, short answers (a list of references). Questions on one novel are not
independent, so every draw and every bootstrap is by novel; a novel's key is the sha256 of its
text, which the file carries once per question.

    python benchmarks/longdoc_free/pool.py --download   # the pinned file into the cache
    python benchmarks/longdoc_free/pool.py --prepare    # each novel once, as <key>.txt
    python benchmarks/longdoc_free/pool.py --freeze     # ids.json: each item, its novel, its phase

The dev draw reads metadata only (ids and novel keys, never a question or an answer): the novels
in a seeded order, whole, until DEV_ITEMS questions are reached.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import urllib.request
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

CACHE = Path.home() / ".cache" / "sanchopanza" / "longdoc_free"
RAW = CACHE / "raw" / "longbook_qa_eng.jsonl"
NOVELS = CACHE / "novels"
REVISION = "90f0394333616266d9fe85824ceaf505093cbaa5"
URL = (
    "https://huggingface.co/datasets/xinrongzhang2022/InfiniteBench/resolve/"
    f"{REVISION}/longbook_qa_eng.jsonl"
)
SHA256 = "7f53a3aabd5445fa29f168914f13569c348406cfc88a3e495f3f2c13a0966ca4"
N_ITEMS = 351
N_NOVELS = 69
DEV_ITEMS = 40
SEED = 20261017
LOT_DIR = Path(__file__).resolve().parents[2] / "docs/results/2026-10-16-longdoc-free"
IDS_FILE = LOT_DIR / "ids.json"


@dataclass(frozen=True)
class Item:
    id: int
    novel: str  # sha256 of the novel's text, 16 hex characters
    question: str
    answers: tuple[str, ...]
    chars: int


def novel_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def require_pinned(path: Path = RAW) -> None:
    if not path.exists():
        raise SystemExit(f"{path} is missing: run --download")
    found = file_sha256(path)
    if found != SHA256:
        raise SystemExit(f"{path} has sha256 {found}, not the pinned {SHA256}")


def rows(path: Path = RAW) -> Iterator[dict]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def items(raw: Iterable[dict]) -> tuple[list[Item], dict[str, str]]:
    """The items, and each novel's text by key (once)."""
    out: list[Item] = []
    texts: dict[str, str] = {}
    for row in raw:
        text = row["context"]
        key = novel_key(text)
        texts.setdefault(key, text)
        answers = row["answer"] if isinstance(row["answer"], list) else [row["answer"]]
        out.append(Item(int(row["id"]), key, row["input"], tuple(map(str, answers)), len(text)))
    return out, texts


def draw_dev(novel_of: dict[int, str], target: int = DEV_ITEMS, seed: int = SEED) -> set[str]:
    """Whole novels in a seeded order until `target` questions: metadata only."""
    novels = sorted(set(novel_of.values()))
    random.Random(seed).shuffle(novels)
    count = {n: sum(1 for v in novel_of.values() if v == n) for n in novels}
    chosen: set[str] = set()
    total = 0
    for novel in novels:
        if total >= target:
            break
        chosen.add(novel)
        total += count[novel]
    return chosen


def frozen(all_items: list[Item]) -> dict:
    novel_of = {item.id: item.novel for item in all_items}
    dev = draw_dev(novel_of)
    return {
        "revision": REVISION,
        "sha256": SHA256,
        "seed": SEED,
        "dev_items": DEV_ITEMS,
        "items": [
            {
                "id": item.id,
                "novel": item.novel,
                "chars": item.chars,
                "phase": "dev" if item.novel in dev else "confirm",
            }
            for item in sorted(all_items, key=lambda i: i.id)
        ],  # fmt: skip
    }


def read_frozen(path: Path = IDS_FILE) -> dict:
    return json.loads(path.read_text("utf-8"))


def phase_ids(table: dict, phase: str) -> list[int]:
    return [row["id"] for row in table["items"] if row["phase"] == phase]


def novel_path(key: str, root: Path = NOVELS) -> Path:
    return root / f"{key}.txt"


def prepare(texts: dict[str, str], root: Path = NOVELS) -> int:
    """Each novel once, as `<key>.txt` (UTF-8, as in the file); returns how many were written."""
    root.mkdir(parents=True, exist_ok=True)
    written = 0
    for key, text in texts.items():
        path = novel_path(key, root)
        if path.exists() and novel_key(path.read_text("utf-8")) == key:
            continue
        path.write_bytes(text.encode("utf-8"))
        written += 1
    return written


def _download() -> None:
    RAW.parent.mkdir(parents=True, exist_ok=True)
    if RAW.exists() and file_sha256(RAW) == SHA256:
        print(f"{RAW} already pinned")
        return
    tmp = RAW.with_suffix(".part")
    urllib.request.urlretrieve(URL, tmp)  # noqa: S310 - a fixed https URL
    if file_sha256(tmp) != SHA256:
        tmp.unlink()
        raise SystemExit("the downloaded file does not match the pinned sha256")
    tmp.replace(RAW)
    print(f"{RAW} downloaded and pinned")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args(argv)
    if args.download:
        _download()
    if args.prepare or args.freeze:
        require_pinned()
        all_items, texts = items(rows())
        if len(all_items) != N_ITEMS or len(texts) != N_NOVELS:
            raise SystemExit(f"{len(all_items)} items over {len(texts)} novels, not the pinned set")
        if args.prepare:
            print(f"{prepare(texts)} novels written under {NOVELS}")
        if args.freeze:
            if IDS_FILE.exists():
                raise SystemExit(f"{IDS_FILE} exists: the ids are frozen once")
            IDS_FILE.parent.mkdir(parents=True, exist_ok=True)
            table = frozen(all_items)
            IDS_FILE.write_text(json.dumps(table, indent=1) + "\n", "utf-8")
            dev = phase_ids(table, "dev")
            print(f"{IDS_FILE}: {len(table['items'])} items, dev {len(dev)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
