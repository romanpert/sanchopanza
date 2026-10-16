"""The guard's pointer block, the default chooser since 2026-10-16 (`GUARD_CHOOSER=pointers`).

After a compaction it attaches what the summary drops and nothing it can point to instead:

- **The person's requests**, verbatim and masked, latest last, within `guard.REQUESTS_CHARS`.
- **The work so far**: the files changed and the last test run with its outcome line.
- **Pointers** to the tool output since the previous compaction, in the structural keep's order
  (`structural.order`: results on files being edited first, then by recency, output that cannot
  be had again first in each, one per file). Output that can be had again is named so the agent
  can read, search, fetch or run it again (the file and line range, the search, the command).
  Output that cannot (`guard.at_risk`: a one-shot command, a subagent's report) is written whole,
  masked, to the archive (`.sanchopanza/archive/<session>/guard-<call id>.txt`, beside the
  project and out of git, as the autopilot's) and its pointer names the file to `Read`.

Why not the whole results (`context.structural`, the default from 2026-10-05): the block re-sent
a median 49,473 characters (about 15k tokens) after every compaction. Replayed on the long60
sessions of clean Claude Code (100 compactions), the agent fetched again an item that block
would have held in 13 of them, worth about 0.002 USD per compaction against the block's 0.16
(Sonnet 5.5 rates), and docs/results/2026-10-07-h2h-ne found its re-injection added nothing
measurable on BrowseComp-Plus. The whole-results block stays one setting away
(`GUARD_CHOOSER=struct`, `sanchopanza install --guard-full`).

Pure: `build_from_calls` returns the guard and the archive entries to write; the hook writes
them (`write`) before it attaches the block.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import guard, structural
from .archive import safe_name, write_entry
from .guard import Guard
from .transcript import Call, calls

# Room for pointers, in characters: a line each (an archived one carries its path), newest first.
# With 2,500 of requests and 20 changed files the whole block stays within one hook's inline
# limit (`structural.INLINE_CHARS`), so it needs no split.
POINTER_CHARS = 4_000
ARCHIVE_PREFIX = "guard-"


@dataclass(frozen=True, slots=True)
class Archived:
    """One output to write before the block is attached: its file, text and sidecar."""

    directory: Path
    name: str
    text: str
    meta: Mapping[str, Any]

    @property
    def path(self) -> Path:
        return (self.directory / f"{safe_name(self.name)}.txt").absolute()


def _archived(call: Call, directory: Path) -> Archived:
    label = structural.label_of(call)
    return Archived(directory, f"{ARCHIVE_PREFIX}{call.id}", structural.content_of(call),
                    {"tool": call.tool, "input": label, "origin": "guard"})  # fmt: skip


def _pointer(call: Call, entry: Archived | None) -> str:
    label = structural.label_of(call)
    if entry is None:
        return label
    return f"{label} -> Read {entry.path} ({len(entry.text):,} characters)"


def build_from_calls(
    history: Sequence[Call],
    requests: Sequence[str],
    *,
    since: int = 0,
    archive: Path | None = None,
    pointer_chars: int = POINTER_CHARS,
    inline_chars: int = structural.INLINE_CHARS,
    web: bool = False,
) -> tuple[Guard, tuple[Archived, ...]]:
    """The pointer guard for `history` and the outputs to archive under `archive` (one session's
    folder). Without `archive`, output that cannot be had again gets no pointer. The block stays
    within `inline_chars` (0: no cap): pointers past the room are dropped, newest kept."""
    ranked, superseded = structural.order(history, since=since, web=web)
    pointers: list[str] = []
    entries: list[Archived] = []
    used = 0
    for p in ranked:
        call = history[p]
        entry = None
        if guard.at_risk(call, web=web):
            if archive is None:
                continue
            entry = _archived(call, archive)
        pointer = _pointer(call, entry)
        if pointer in pointers or used + len(pointer) + 3 > pointer_chars:
            continue
        pointers.append(pointer)
        used += len(pointer) + 3
        if entry is not None:
            entries.append(entry)
    built = Guard(
        facts=(),
        requests=tuple(requests),
        trail=guard.trail_of(history),
        candidates=len(ranked) + len(superseded),
        chooser="pointers",
        clipped=guard.clipped_of(history, web=web),
        kind="pointers",
        pointers=tuple(pointers),
    )
    return _within(built, entries, inline_chars)


def _within(
    built: Guard, entries: list[Archived], inline_chars: int
) -> tuple[Guard, tuple[Archived, ...]]:
    """Drop the oldest pointers (and their archive entries) until the block fits."""
    kept = list(built.pointers)
    while inline_chars > 0 and kept:
        trial = dataclasses.replace(built, pointers=tuple(kept))
        if structural.width(guard.block(trial)) <= inline_chars:
            break
        kept.pop()
    final = dataclasses.replace(built, pointers=tuple(kept))
    named = "\n".join(kept)
    return final, tuple(e for e in entries if str(e.path) in named)


def build(
    messages: Sequence[Mapping[str, Any]],
    *,
    since: int = 0,
    archive: Path | None = None,
    requests_chars: int = guard.REQUESTS_CHARS,
    pointer_chars: int = POINTER_CHARS,
    inline_chars: int = structural.INLINE_CHARS,
    web: bool = False,
) -> tuple[Guard, tuple[Archived, ...]]:
    """The pointer guard for a transcript (`since` as in `structural.build`). Pure."""
    return build_from_calls(
        calls(messages),
        guard.requests_of(messages, requests_chars),
        since=since,
        archive=archive,
        pointer_chars=pointer_chars,
        inline_chars=inline_chars,
        web=web,
    )


def write(entries: Sequence[Archived]) -> None:
    """Write each archived output and its sidecar (raises OSError when it cannot)."""
    for entry in entries:
        write_entry(entry.directory, entry.name, entry.text, entry.meta)
