"""The guard's pointer block, the default chooser since 2026-10-16 (`GUARD_CHOOSER=pointers`).

After a compaction it attaches what the summary drops and nothing it can point to instead, in
this order (`guard.pointer_block`):

- **The person's requests**, verbatim and masked, latest last, within `guard.REQUESTS_CHARS`.
  First, so they stay in the 2,000 characters Claude Code previews of a hook's context should
  the block ever pass its inline limit.
- **The work so far**: the files changed and the last test run with its outcome line.
- **The outputs the harness cut** before the conversation saw them, within `CLIPPED_CHARS`.
- **Pointers** to the tool output since the previous compaction, in the structural keep's order
  (`structural.order`: results on files being edited first, then by recency, output that cannot
  be had again first in each, one per file). Output that can be had again is named so the agent
  can read, search, fetch or run it again (the file and line range, the search, the command).
  Output that cannot (`guard.at_risk`: a one-shot command, a subagent's report) is written
  whole to the archive beside the project and out of git, as the autopilot's
  (`.sanchopanza/archive/<session>/guard-<call id>.txt`), every one of them whatever the room:
  the room limits only the lines listed, and the rest are counted ("N more archived"). The
  session folder is named once, quoted, with an absolute path the agent can `Read` under.
  Archived text is masked with `redact.mask_strict` on the whole raw result before any trim
  (JSON and repr credentials, URL passwords, a private key cut before its end).

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

from ..redact import mask_strict
from . import guard, structural
from .archive import safe_name, write_entry
from .guard import Guard
from .transcript import Call, calls

# Room for the listed pointers, in characters, newest first. With 2,500 of requests, 20 changed
# files and the cut outputs' room, the whole block stays within one hook's inline limit
# (`structural.INLINE_CHARS`), so it needs no split.
POINTER_CHARS = 4_000
CLIPPED_CHARS = 1_000
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


def archived_text(call: Call) -> str:
    """A result as it is archived: masked strictly on the whole raw text first (a secret cut in
    two is no longer found), then trailing spaces trimmed."""
    masked = mask_strict(call.result)
    return "\n".join(line.rstrip() for line in masked.strip().splitlines())


def _archived(call: Call, directory: Path) -> Archived:
    name = call.id.removeprefix("toolu_")
    return Archived(directory, f"{ARCHIVE_PREFIX}{name}", archived_text(call),
                    {"tool": call.tool, "input": structural.label_of(call),
                     "origin": "guard"})  # fmt: skip


def _pointer(call: Call, entry: Archived | None) -> str:
    label = structural.label_of(call)
    if entry is None:
        return label
    return f"{label} -> {entry.path.name} ({len(entry.text):,} characters)"


def _clipped(history: Sequence[Call], web: bool, room: int = CLIPPED_CHARS) -> tuple[str, ...]:
    """The cut outputs, newest kept, within `room`."""
    kept: list[str] = []
    used = 0
    for line in reversed(guard.clipped_of(history, web=web)):
        if used + len(line) + 3 > room:
            break
        kept.append(line)
        used += len(line) + 3
    return tuple(reversed(kept))


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
    """The pointer guard for `history` and every output to archive under `archive` (one
    session's folder). Without `archive`, output that cannot be had again gets no pointer. The
    block stays within `inline_chars` (0: no cap)."""
    ranked, superseded = structural.order(history, since=since, web=web)
    lines: list[tuple[str, bool]] = []  # (pointer, archived)
    entries: list[Archived] = []
    used = 0
    for p in ranked:
        call = history[p]
        entry = None
        if guard.at_risk(call, web=web):
            if archive is None:
                continue
            entry = _archived(call, archive)
            entries.append(entry)  # archived whatever the room
        pointer = _pointer(call, entry)
        if any(pointer == known for known, _ in lines):
            continue
        if used + len(pointer) + 3 > pointer_chars:
            continue
        lines.append((pointer, entry is not None))
        used += len(pointer) + 3
    built = Guard(
        facts=(),
        requests=tuple(requests),
        trail=guard.trail_of(history),
        candidates=len(ranked) + len(superseded),
        chooser="pointers",
        clipped=_clipped(history, web),
        kind="pointers",
        archive=str(archive.absolute()) if archive is not None and entries else "",
    )
    return _within(built, lines, len(entries), inline_chars), tuple(entries)


def _with_lines(built: Guard, lines: Sequence[tuple[str, bool]], archived: int) -> Guard:
    listed = sum(1 for _, was in lines if was)
    return dataclasses.replace(built, pointers=tuple(p for p, _ in lines),
                               archived_more=archived - listed)  # fmt: skip


def _fits(built: Guard, inline_chars: int) -> bool:
    return inline_chars <= 0 or structural.width(guard.block(built)) <= inline_chars


def _within(built: Guard, lines: list[tuple[str, bool]], archived: int, inline_chars: int) -> Guard:
    """Drop the lowest listed pointers, then the cut outputs, then the oldest trail lines, until
    the block fits. The requests are bounded on their own and never dropped here."""
    kept = list(lines)
    current = _with_lines(built, kept, archived)
    while not _fits(current, inline_chars) and kept:
        kept.pop()
        current = _with_lines(built, kept, archived)
    if not _fits(current, inline_chars):
        current = dataclasses.replace(current, clipped=())
    trail = list(current.trail)
    while not _fits(current, inline_chars) and trail:
        trail.pop()
        current = dataclasses.replace(current, trail=tuple(trail))
    return current


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
