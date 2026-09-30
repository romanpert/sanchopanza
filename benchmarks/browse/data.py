"""Mind2Web steps for the browse bench: download once, keep a compact copy outside the repo.

python benchmarks/browse/data.py            # fetch the registered sample (free, network)
python benchmarks/browse/data.py --confirm  # the confirmation sample: half a step further on

Source: osunlp/Multimodal-Mind2Web through the Hugging Face datasets server (rows API, no
screenshots kept). The sample is fixed before any model sees it: `PER_SPLIT` steps from each of
the three test splits, at evenly spaced offsets (`offsets`), so nobody picks the easy pages.

Each step becomes one record: the task, the previous actions, the target operation, every
candidate element (positive and negative) with the text code can read for it from the cleaned
HTML, and which candidates are positive. The raw HTML is not kept.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sanchopanza.browse import elements_from_html  # noqa: E402

DATASET = "osunlp/Multimodal-Mind2Web"
SPLITS = {"test_website": 1019, "test_domain": 4060, "test_task": 1339}
PER_SPLIT = 60
PAUSE_S = 2.0
ATTEMPTS = 6
CACHE = pathlib.Path(
    os.environ.get("SANCHOPANZA_CACHE", pathlib.Path.home() / ".cache" / "sanchopanza")
)
OUT = CACHE / "mind2web" / "steps.jsonl"
CONFIRM = CACHE / "mind2web" / "steps-confirm.jsonl"


def offsets(total: int, n: int, *, shift: float = 0.0) -> list[int]:
    """`n` evenly spaced row offsets in a split of `total` rows, moved `shift` of a step on.
    Deterministic, no seed. `shift=0.5` never meets a `shift=0` offset (steps are > 16 rows)."""
    step = total / n
    return [int((i + shift) * step) for i in range(n)]


def fetch(split: str, offset: int, length: int) -> list[dict[str, Any]]:
    url = (
        "https://datasets-server.huggingface.co/rows?"
        f"dataset={DATASET}&config=default&split={split}&offset={offset}&length={length}"
    )
    time.sleep(PAUSE_S)  # the rows API answers 429 past a few dozen quick requests
    for attempt in range(ATTEMPTS):
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                return [r["row"] for r in json.load(response)["rows"]]
        except urllib.error.HTTPError as error:
            if attempt == ATTEMPTS - 1:
                raise
            wait = error.headers.get("Retry-After") if error.code == 429 else None
            time.sleep(float(wait) if wait and wait.isdigit() else 15 * (attempt + 1))
        except Exception:  # noqa: BLE001 - network: bounded retries, then give up loudly
            if attempt == ATTEMPTS - 1:
                raise
            time.sleep(5 * (attempt + 1))
    return []


def node_id(candidate: str) -> str:
    return str(json.loads(candidate)["backend_node_id"])


def compact(row: dict[str, Any], split: str) -> dict[str, Any] | None:
    positives = {node_id(c) for c in row["pos_candidates"]}
    candidates = positives | {node_id(c) for c in row["neg_candidates"]}
    elements = [e for e in elements_from_html(row["cleaned_html"]) if e.key in candidates]
    found = {e.key for e in elements}
    if not positives & found:
        return None  # the positive is not in the cleaned HTML: nothing to rank
    index = int(row["target_action_index"])
    return {
        "id": row["action_uid"],
        "split": split,
        "website": row["website"],
        "task": row["confirmed_task"],
        "previous": row["action_reprs"][:index],
        "target": row["target_action_reprs"],
        "operation": json.loads(row["operation"]),
        "elements": [e.to_dict() for e in elements],
        "positives": sorted(positives & found),
        "html_chars": len(row["cleaned_html"]),
    }


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--confirm", action="store_true")
    args = ap.parse_args()
    out = CONFIRM if args.confirm else OUT
    shift = 0.5 if args.confirm else 0.0
    return fetch_all(out, shift)


def fetch_all(out_path: pathlib.Path, shift: float) -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out_path.exists():
        done = {
            json.loads(line)["id"] for line in out_path.read_text(encoding="utf-8").splitlines()
        }
    # The confirmation sample must not share a task with the development one: consecutive rows
    # are steps of the same task, and half a step on can land in one already seen.
    seen_tasks: set[str] = set()
    if out_path != OUT and OUT.exists():
        seen_tasks = {
            json.loads(line)["task"] for line in OUT.read_text(encoding="utf-8").splitlines()
        }
    kept = skipped = same_task = 0
    with out_path.open("a", encoding="utf-8") as sink:
        for split, total in SPLITS.items():
            for offset in offsets(total, PER_SPLIT, shift=shift):
                row = fetch(split, offset, 1)[0]
                if row["action_uid"] in done:
                    continue
                if row["confirmed_task"] in seen_tasks:
                    same_task += 1
                    continue
                record = compact(row, split)
                if record is None:
                    skipped += 1
                    continue
                sink.write(json.dumps(record, ensure_ascii=False) + "\n")
                sink.flush()
                kept += 1
    print(
        f"kept {kept}, skipped {skipped} (positive not in cleaned HTML), {same_task} sharing a "
        f"task with the development sample; file {out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
