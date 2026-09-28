"""`--lever pages` for the fixed-sequence A/B, and what it needs to be rerun cleanly.

## Why a new lever

The run of 2026-09-24 (`docs/results/2026-09-24-fixed-sequence/`) cut input tokens by 75 % with
page-by-page triage and lost four answers in ten, every one by dropping the answer document.
Two things were wrong with the question it asked: each document was judged alone, so on a
compound question ("the entry point of each of these four adapters") no single page satisfied
the purpose; and a long document (`paper-06`) was judged by what fit in the excerpt.

The points shipped since answer both. `Squire.triage_many` judges pages **with the others in
view** ("does this page hold a fact the answer needs"), and the unit here is the **passage**:
each document is split into paragraphs of at most `chunks.PAGE_LIMIT` characters, so a long
document is judged by all of its text, not by its head. A document keeps the passages that
survive, in order; a document with none left is withheld with the same one-line note as before.

## What is fixed here, and what is not

- `EveryQuestion`: a deterministic fake decider for the dry run. It answers every question
  with a probability drawn from a hash of the question and the state, so the tournament
  prunes and the number of calls is realistic. It says nothing about quality.
- `fake_answer`: the answering model replaced by a token estimate. No network.
- `git_reader`: the corpus is built from this repository's own documents, which change almost
  daily, so a rerun reads them at a pinned commit (`--corpus-ref`).
- `check_reusable`: a recorded bare arm is reused only if today's sequences are the recorded
  ones, document for document. On 2026-09-28 the 2026-09-24 bare arm matched no commit
  (best: 7 of 10 tasks at `6107f4f`); it was run on an uncommitted tree, so it cannot be
  reused and both arms have to be rerun.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from sanchopanza import Decision, truth
from sanchopanza.points.chunks import PAGE_LIMIT
from sanchopanza.text import split_sentences

PARAGRAPH_MIN = 200  # shorter paragraphs (headings, one-line bullets) fold into the previous


def _pack(sentences: Sequence[str], limit: int) -> list[str]:
    parts: list[str] = []
    current = ""
    for sentence in sentences:
        joined = f"{current} {sentence}".strip()
        if current and len(joined) > limit:
            parts.append(current)
            current = sentence
        else:
            current = joined
    return [*parts, current] if current else parts


def passages(text: str, *, limit: int = PAGE_LIMIT, minimum: int = PARAGRAPH_MIN) -> list[str]:
    """Paragraphs of a document, short ones folded forward, long ones packed by sentence."""
    folded: list[str] = []
    for block in (b.strip() for b in text.split("\n\n")):
        if not block:
            continue
        if folded and len(folded[-1]) < minimum:
            folded = [*folded[:-1], f"{folded[-1]}\n\n{block}"]
        else:
            folded = [*folded, block]
    out: list[str] = []
    for block in folded:
        out.extend([block] if len(block) <= limit else _pack(split_sentences(block), limit))
    return out


async def trim_by_pages(
    squire: Any, purpose: str, docs: Sequence[Any]
) -> tuple[dict[str, str], list[str], list[str]]:
    """Bodies of the documents after the tournament; withheld documents; dropped passages."""
    units = [(doc, i, part) for doc in docs for i, part in enumerate(passages(doc.text))]
    verdicts = await squire.triage_many(
        purpose=purpose, pages=[(doc.title, part) for doc, _i, part in units]
    )
    kept: dict[str, list[str]] = {doc.id: [] for doc in docs}
    dropped_passages: list[str] = []
    for (doc, i, part), (keep, _p) in zip(units, verdicts, strict=True):
        if keep:
            kept[doc.id] = [*kept[doc.id], part]
        else:
            dropped_passages.append(f"{doc.id}#{i}")
    withheld = [doc.id for doc in docs if not kept[doc.id]]
    bodies = {doc.id: "\n\n".join(kept[doc.id]) for doc in docs if kept[doc.id]}
    return bodies, withheld, dropped_passages


class EveryQuestion:
    """Fake decider: a hashed probability for every question. Free, deterministic, not a model."""

    name = "fake"
    model = "fake-hash"

    def __init__(self) -> None:
        self.calls = 0

    async def decide(self, point: str, state: Any, questions: Mapping[str, Any]) -> Decision:
        self.calls += 1
        seed = json.dumps(state, sort_keys=True, ensure_ascii=False, default=str)
        answers = {}
        for key in questions:
            digest = hashlib.sha256(f"{point}|{key}|{seed}".encode()).digest()
            answers[key] = truth(int.from_bytes(digest[:4], "big") / 2**32)
        return Decision(point, answers, self.name, self.model)


def fake_answer(content: str) -> tuple[str, int, int, float]:
    """(answer, input tokens, output tokens, cost): an estimate at four characters a token."""
    return "", len(content) // 4, 0, 0.0


def git_reader(ref: str, root: Path) -> Callable[[str], str]:
    """Read a repository file as it was at `ref`. Fails loudly on an unknown ref or path."""

    def read(path: str) -> str:
        done = subprocess.run(
            ["git", "-C", str(root), "show", f"{ref}:{path}"],
            capture_output=True,
            encoding="utf-8",
        )
        if done.returncode != 0:
            raise FileNotFoundError(f"{ref}:{path}: {done.stderr.strip()}")
        return done.stdout

    return read


def check_reusable(
    recorded: Sequence[Mapping[str, Any]], sequences: Mapping[str, Sequence[Any]], model: str
) -> list[str]:
    """Why a recorded bare arm cannot stand in for today's; empty when it can."""
    problems: list[str] = []
    bare = {row["task"]: row for row in recorded if row.get("arm") == "bare" and row["repeat"] == 0}
    for task, seq in sequences.items():
        row = bare.get(task)
        if row is None:
            problems.append(f"{task}: no recorded bare row")
        elif row.get("error"):
            problems.append(f"{task}: the recorded row failed ({row['error']})")
        elif row.get("model") != model:
            problems.append(f"{task}: recorded with {row.get('model')}, asked for {model}")
        elif list(row.get("fetched", [])) != [d.id for d in seq]:
            problems.append(f"{task}: the recorded sequence is not today's")
    return problems
