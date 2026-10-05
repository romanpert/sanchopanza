"""The guard's structural keep: whole tool results chosen by where the work is, no model.

The default chooser of the compaction guard (`SANCHOPANZA_GUARD_CHOOSER=struct`). It replaced the
decider's ranking (`context.keep`) after an offline replay on 2026-10-05
(docs/results/2026-10-05-guard-struct/): Jev's block scores ranked later-needed results worse than
plain recency (AUC 0.56 against 0.60), and on the owner's real sessions the order below kept
.67 of the results the work needed next where the guard's rule-only path kept .12.

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

# The budget for whole results, in characters (about 2.2 per token in the replay's sessions).
# Measured offline on 2026-10-05 (docs/results/2026-10-05-guard-struct/README.md): on the owner's
# Claude Code sessions (135 sessions, 344 compaction points at 200k tokens, mostly Opus 5.5),
# counting a read superseded by a newer kept read of the same file as kept, the share of
# later-needed results kept was, at 20k tokens (~44,000 characters): this order without the
# at-risk step .67 (at-risk .59), this order .64 (.61), recency .56, oracle .91, and the guard's
# rule-only fallback .12 (.17) at its 3,000 characters. At today's 3,000 characters (~1,364
# tokens) the same order keeps .15 (.17), against .21 (.13) without the at-risk step, recency
# .15 (.12) and oracle .39 (.27); at 11,000 characters .28 (.30); at 22,000 .44 (.43). The
# default is sized like the guard's earlier facts budget, so the block does not grow by surprise;
# `SANCHOPANZA_GUARD_STRUCT_CHARS=44000` is the size the .64-.67 was measured at. Replay scripts:
# guard-replay/real.py, iterate.py, iterate_credit.py, budget.py (local; owner's sessions not
# published). The "needed" label is a proxy: a later tool input or assistant text naming the
# result's file or a distinctive token first seen in it.
STRUCT_CHARS = guard.FACTS_CHARS
POINTER_CHARS = 1_500  # pointers have their own room: a line each, newest first
FENCE = 12  # "\n<<<output\n" and "\n>>>" around each kept result, and its source line's newline
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


def cost(source: str, content: str) -> int:
    """Characters a kept result takes in the block."""
    return len(source) + len(content) + FENCE


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
    kept: list[int] = []
    pointers: list[str] = []
    used = pointer_used = 0
    for p in ranked:
        call = history[p]
        reachable = web or not (call.tool in guard.WEB or call.tool.startswith("mcp__"))
        size = cost(label_of(call), content_of(call)) if reachable else budget + 1
        if used + size <= budget:
            kept.append(p)
            used += size
            continue
        pointer = _pointer(call, web=web)
        if pointer and pointer not in pointers and pointer_used + len(pointer) + 3 <= pointer_chars:
            pointers.append(pointer)
            pointer_used += len(pointer) + 3
    return Choice(tuple(sorted(kept)), tuple(pointers), superseded, len(ranked) + len(superseded))


def build_from_calls(
    history: Sequence[Call],
    requests: Sequence[str],
    *,
    since: int = 0,
    budget: int = STRUCT_CHARS,
    pointer_chars: int = POINTER_CHARS,
    web: bool = False,
) -> Guard:
    """The guard for `history` with its results chosen by structure."""
    choice = choose(history, since=since, budget=budget, pointer_chars=pointer_chars, web=web)
    facts = tuple(
        Fact(source=label_of(history[p]), line=content_of(history[p]), call=p,
             error=failed(history[p]))
        for p in choice.kept
    )  # fmt: skip
    return Guard(
        facts=facts,
        requests=tuple(requests),
        trail=guard.trail_of(history),
        candidates=choice.considered,
        chooser="struct",
        clipped=guard.clipped_of(history, web=web),
        kind="results",
        pointers=choice.pointers,
    )


def build(
    messages: Sequence[Mapping[str, Any]],
    *,
    since: int = 0,
    facts_chars: int = STRUCT_CHARS,
    requests_chars: int = guard.REQUESTS_CHARS,
    pointer_chars: int = POINTER_CHARS,
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
        web=web,
    )
