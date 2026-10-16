"""The guard's structural keep: whole tool results chosen by where the work is, no model.

The compaction guard's whole-results chooser (`SANCHOPANZA_GUARD_CHOOSER=struct`, `sanchopanza
install --guard-full`), its default from 2026-10-05 until the pointer block (`context.pointers`)
took that place on 2026-10-16. It replaced the
decider's ranking (`context.keep`) after an offline replay on 2026-10-05
(docs/results/2026-10-05-guard-struct/): Jev's block scores ranked later-needed results worse than
plain recency (AUC 0.56 against 0.60), and on the owner's real sessions the order below kept
.64-.67 of the results the work needed next at 44,000 characters, where the guard's rule-only
path kept .12. What one hook can attach inline in Claude Code is smaller (`INLINE_CHARS`).

The order (policy f of that replay), over every tool result since the previous compaction,
re-readable ones included:

1. **Results on files edited since the previous compaction**: the edits themselves, and reads,
   searches and commands naming one of those files.
2. **The rest, by recency.**
3. **One result per file**: of the reads and edits of one file only the latest counts; an older
   one is covered by it and takes no room.

Inside each tier, output that cannot be had again (`guard.at_risk`: a one-shot command, a
subagent's report) goes before output that can, newest first. Results are kept whole while they
fit the budget. A result that can be had again and does not fit leaves a pointer instead (the
file and line range, the search, the command to run again), so the agent knows where to look;
one that cannot be had again and does not fit is lost, as it would be without the guard. Web and
MCP output is only ever pointed to unless `web` is on: a page can be fetched again, and its text
could carry instructions aimed at the model.

Pure and fast: one pass over the calls, regexes on tool inputs only, masking on kept text only.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..redact import mask
from . import guard
from .guard import POINTERS_HEADING as POINTERS_HEADING  # the block's wording, for callers
from .guard import Fact, Guard
from .rules import WRITE_TOOLS, failed
from .transcript import Call, calls

# The budget for whole results, in characters (about 2.2 per token in the replay's sessions):
# 44,000, about 20k tokens. Measured offline on 2026-10-05
# (docs/results/2026-10-05-guard-struct/README.md) on the owner's Claude Code sessions (135
# sessions, 344 compaction points at 200k tokens, mostly Opus 5.5), counting a read superseded by
# a newer kept read of the same file as kept. Share of later-needed results kept (at-risk ones in
# brackets), by budget:
#
#   characters (tokens)   this order   without the at-risk step   recency     oracle
#    3,000 ( 1,364)       .15 (.17)    .21 (.13)                  .15 (.12)   .39 (.27)
#   11,000 ( 5,000)       .28 (.30)    .36 (.26)                  .25 (.21)   .65 (.55)
#   22,000 (10,000)       .44 (.43)    .52 (.40)                  .38 (.33)   .79 (.74)
#   44,000 (20,000)       .64 (.61)    .67 (.59)                  .56 (.51)   .91 (.89)
#
# The guard's rule-only fallback keeps .12 (.17) at its 3,000 characters. The "needed" label is a
# proxy: a later tool input or assistant text naming the result's file or a distinctive token
# first seen in it. Replay scripts: guard-replay/real.py, iterate.py, iterate_credit.py,
# budget.py (local; the owner's sessions are not published). `SANCHOPANZA_GUARD_STRUCT_CHARS`.
#
# What reaches the model is also bounded by `INLINE_CHARS`, the whole block's size; see there.
STRUCT_CHARS = 44_000
POINTER_CHARS = 1_500  # pointers have their own room: a line each, newest first
# The whole block, in characters. Claude Code keeps a hook's `additionalContext` inline only up
# to 10,000 characters; past that it writes the text to a file and the model sees a
# `<persisted-output>` notice with the first 2,000 characters and the path (read in the 2.1.282
# and 2.1.287 binaries on 2026-10-06: hook-output threshold 1e4, preview 2,000). A block over the
# limit would reach the model as less than the old 3,000-character one, so results get the room
# the rest of the block leaves under this cap, whatever `STRUCT_CHARS` allows; 0 turns the cap off
# for a host that takes more. With the requests, the trail and the pointers' share, that room is
# about 3,900 characters (2,500 of requests, 20 changed files) to 7,000 (a short request, three
# files). Each SessionStart hook's context is capped on its own and then concatenated, so the
# measured 44,000 arrives split across several hook commands, each part within this cap
# (`context.parts`, `sanchopanza guard-hook --part i`). `SANCHOPANZA_GUARD_INLINE_CHARS`.
INLINE_CHARS = 9_500
FENCE = 16  # "\n<<<output\n" and "\n>>>" around each kept result, and the newline after its source
FILE_TOOLS = frozenset({"Read", *WRITE_TOOLS})
SHELL = frozenset({"Bash", "PowerShell"})
_PATH_KEYS = ("file_path", "notebook_path", "path")
_PATH = re.compile(
    r"[\w.\-~:]*[/\\][\w.\-/\\]+|\b[\w\-]+\.(?:py|pyi|rst|md|txt|cfg|toml|ini|json|ya?ml|js|jsx|ts|"
    r"tsx|html|css|c|h|cpp|go|rs|java|rb|sh|sql)\b"
)
_NUMBERED = re.compile(r"^\s*(\d+)(?:\t|→)")


def path_key(value: str) -> str:
    """A path as compared across tools: its last two parts, lower case, forward slashes; "" for
    something that is not a file path (no extension in its last part)."""
    parts = [
        p for p in value.strip("'\"`,;()[]{}<>").lower().replace("\\", "/").split("/")
        if p and p not in (".", "..")
    ]  # fmt: skip
    if not parts or "." not in parts[-1].strip("."):
        return ""
    return "/".join(parts[-2:])


def paths_of(call: Call) -> frozenset[str]:
    """The files a call names: its path arguments, and paths inside a shell command."""
    found = [call.input.get(k) for k in _PATH_KEYS]
    command = call.input.get("command")
    if call.tool in SHELL and isinstance(command, str):
        found.extend(_PATH.findall(command))
    keys = {path_key(v) for v in found if isinstance(v, str)}
    return frozenset(k for k in keys if k)


def _considered(history: Sequence[Call], since: int) -> list[int]:
    """Positions of results worth a place, since the previous compaction when there are any."""

    def usable(call: Call) -> bool:
        text = call.result.strip()
        return bool(text) and not text.startswith(guard._HARNESS)

    after = [p for p, c in enumerate(history) if c.use_msg >= since and usable(c)]
    return after or [p for p, c in enumerate(history) if usable(c)]


def order(
    history: Sequence[Call], *, since: int = 0, web: bool = False
) -> tuple[list[int], frozenset[int]]:
    """(positions in the order they are fitted, positions superseded by a newer result on the
    same file). See the module docstring for the order."""
    newest = sorted(_considered(history, since), reverse=True)
    paths = {p: paths_of(history[p]) for p in newest}
    edited = frozenset().union(*(paths[p] for p in newest if history[p].tool in WRITE_TOOLS))
    seen: set[str] = set()
    superseded: set[int] = set()
    for p in newest:
        if history[p].tool in FILE_TOOLS and len(paths[p]) == 1:
            (key,) = paths[p]
            if key in seen:
                superseded.add(p)
            seen.add(key)

    def rank(p: int) -> tuple[bool, bool, int]:
        return (not (paths[p] & edited), not guard.at_risk(history[p], web=web), -p)

    return sorted((p for p in newest if p not in superseded), key=rank), frozenset(superseded)


def _range(call: Call) -> str:
    offset, limit = call.input.get("offset"), call.input.get("limit")
    if isinstance(offset, int) and isinstance(limit, int) and limit > 0:
        return f" lines {offset}-{offset + limit - 1}"
    numbers = [m.group(1) for line in call.result.splitlines() if (m := _NUMBERED.match(line))]
    if numbers:
        return f" lines {numbers[0]}-{numbers[-1]}"
    return f" from line {offset}" if isinstance(offset, int) else ""


def label_of(call: Call) -> str:
    """How a result is named in the block and in a pointer: enough to get it again."""
    path = next((v for k in _PATH_KEYS if isinstance(v := call.input.get(k), str) and v), "")
    pattern = call.input.get("pattern")
    if call.tool == "Read" and path:
        text = f"Read {path}{_range(call)}"
    elif call.tool in WRITE_TOOLS and path:
        text = f"{call.tool} {path}"
    elif call.tool in ("Grep", "Glob") and isinstance(pattern, str):
        text = f"{call.tool} {pattern!r} in {path or '.'}"
    else:
        return guard.source_of(call)
    return mask(text[: guard.COMMAND_MAX + 40])


def content_of(call: Call) -> str:
    """A result as it is attached: whole, trailing spaces trimmed, secrets masked."""
    return mask("\n".join(line.rstrip() for line in call.result.strip().splitlines()))


def width(text: str) -> int:
    """Characters as Claude Code counts them (JavaScript string length: UTF-16 code units), so a
    character outside the Basic Multilingual Plane counts twice."""
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def cost(source: str, content: str) -> int:
    """Characters a kept result takes in the block."""
    return width(source) + width(content) + FENCE


def _pointer(call: Call, *, web: bool) -> str | None:
    """The pointer for a result left out, or None when it cannot be had again."""
    if guard.at_risk(call, web=web):
        return None
    return label_of(call)


@dataclass(frozen=True, slots=True)
class Choice:
    """What the structural keep chose: positions in the history, oldest first."""

    kept: tuple[int, ...]
    pointers: tuple[str, ...]
    superseded: frozenset[int]
    considered: int


def pack(
    history: Sequence[Call],
    ranked: Sequence[int],
    rooms: Sequence[int],
    *,
    budget: int,
    pointer_chars: int = POINTER_CHARS,
    web: bool = False,
) -> tuple[tuple[tuple[int, ...], ...], tuple[str, ...]]:
    """(positions kept in each room, oldest first; pointers). Results go in `ranked` order, each
    whole into the first room it fits while all of them stay within `budget`; one that fits no
    room leaves a pointer when it can be had again. One room of `budget` is `choose`."""
    bins: list[list[int]] = [[] for _ in rooms]
    free = list(rooms)
    pointers: list[str] = []
    used = pointer_used = 0
    for p in ranked:
        call = history[p]
        reachable = web or not (call.tool in guard.WEB or call.tool.startswith("mcp__"))
        size = cost(label_of(call), content_of(call)) if reachable else budget + 1
        room = next((i for i, left in enumerate(free) if size <= left), None)
        if used + size <= budget and room is not None:
            bins[room].append(p)
            free[room] -= size
            used += size
            continue
        pointer = _pointer(call, web=web)
        if pointer and pointer not in pointers and pointer_used + len(pointer) + 3 <= pointer_chars:
            pointers.append(pointer)
            pointer_used += len(pointer) + 3
    return tuple(tuple(sorted(b)) for b in bins), tuple(pointers)


def choose(
    history: Sequence[Call],
    *,
    since: int = 0,
    budget: int = STRUCT_CHARS,
    pointer_chars: int = POINTER_CHARS,
    web: bool = False,
) -> Choice:
    """Results in `order` while they fit `budget`; pointers for re-readable ones left out."""
    ranked, superseded = order(history, since=since, web=web)
    (kept,), pointers = pack(history, ranked, (budget,), budget=budget,
                             pointer_chars=pointer_chars, web=web)  # fmt: skip
    return Choice(kept, pointers, superseded, len(ranked) + len(superseded))


def facts_of(history: Sequence[Call], positions: Sequence[int]) -> tuple[Fact, ...]:
    """Kept results as the block's facts, whole, in the order of `positions`."""
    return tuple(
        Fact(source=label_of(history[p]), line=content_of(history[p]), call=p,
             error=failed(history[p]))
        for p in positions
    )  # fmt: skip


def _with(history: Sequence[Call], base: Guard, choice: Choice) -> Guard:
    return dataclasses.replace(base, facts=facts_of(history, choice.kept),
                               pointers=choice.pointers, candidates=choice.considered)  # fmt: skip


def room_for_results(base: Guard, pointer_chars: int, inline_chars: int) -> int:
    """Characters left for whole results when the block must stay within `inline_chars`, with
    `pointer_chars` set aside for pointers (`base` holds everything but results and pointers)."""
    rest = width(guard.block(base)) or len(guard.HEADER) + len(guard.CLOSING) + 1
    headings = len(guard.RESULTS_HEADING) + len(guard.POINTERS_HEADING) + 2
    return max(0, inline_chars - rest - headings - pointer_chars)


def build_from_calls(
    history: Sequence[Call],
    requests: Sequence[str],
    *,
    since: int = 0,
    budget: int = STRUCT_CHARS,
    pointer_chars: int = POINTER_CHARS,
    inline_chars: int = INLINE_CHARS,
    web: bool = False,
) -> Guard:
    """The guard for `history` with its results chosen by structure, its block within
    `inline_chars` (0: no cap)."""
    base = Guard(
        facts=(),
        requests=tuple(requests),
        trail=guard.trail_of(history),
        candidates=0,
        chooser="struct",
        clipped=guard.clipped_of(history, web=web),
        kind="results",
    )
    if inline_chars > 0:
        budget = min(budget, room_for_results(base, pointer_chars, inline_chars))
    while True:
        choice = choose(history, since=since, budget=budget, pointer_chars=pointer_chars, web=web)
        built = _with(history, base, choice)
        over = width(guard.block(built)) - inline_chars
        if inline_chars <= 0 or over <= 0 or budget == 0:
            break
        budget = max(0, budget - over)  # a safety net: the room above is already exact or over
    if inline_chars > 0 and width(guard.block(built)) > inline_chars:
        built = dataclasses.replace(built, pointers=())  # requests and trail alone overflow
    return built


def build(
    messages: Sequence[Mapping[str, Any]],
    *,
    since: int = 0,
    facts_chars: int = STRUCT_CHARS,
    requests_chars: int = guard.REQUESTS_CHARS,
    pointer_chars: int = POINTER_CHARS,
    inline_chars: int = INLINE_CHARS,
    web: bool = False,
) -> Guard:
    """The guard for a transcript, by structure. `since` is the index of the first message after
    the previous compaction (`history_from_claude_code`'s second value). Pure."""
    return build_from_calls(
        calls(messages),
        guard.requests_of(messages, requests_chars),
        since=since,
        budget=facts_chars,
        pointer_chars=pointer_chars,
        inline_chars=inline_chars,
        web=web,
    )
