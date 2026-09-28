"""Free labels for the memory gate, from this machine's own Claude Code sessions.

For one project: its memory files (`memory/*.md`, the index excluded) and its top-level
transcripts (`*.jsonl`, sidechains skipped). Every first-level user prompt is a case. A memory
file is RELEVANT to a prompt when, in the window after it (the next `WINDOW` assistant blocks
before the next prompt), the assistant

- **read** it (`Read` whose path ends in `memory/<file>` of this project), or
- **quoted** it: used, in its own text or tool input, a distinctive token of that memory that
  appears in no other memory, the index, the project's CLAUDE.md, the prompt, the session
  before the prompt, or a tool result earlier in the window. A lexical proxy, like the context
  benchmark's; declared as a bound, not as ground truth.

A memory written or edited by the assistant in the window is not labelled for that prompt (it
is being stored, not recalled), and a memory not yet born at the prompt (first evidence: its
file creation time or its first `Write` in any transcript) is not a candidate.

Pure functions: a path in, dictionaries out. Nothing here writes a file.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

WINDOW = 12
MEMORY_TOOLS_WRITE = frozenset({"Write", "Edit", "MultiEdit"})
META_PREFIXES = (
    "<command-",
    "<local-command",
    "<task-notification",
    "<system-reminder",
    "<bash-",
    "<user-prompt-submit-hook",
    "[Request interrupted",
    "Caveat: The messages below",
)
_TOKEN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./\\:-]{4,}[A-Za-z0-9_]")


def distinctive_tokens(text: str) -> set[str]:
    """Identifier-like tokens of at least 6 characters: they carry a digit, `_`, `.`, `/`,
    `-` or an inner capital. Plain words are not distinctive enough to count as a quotation."""
    out: set[str] = set()
    for token in _TOKEN.findall(text):
        shaped = any(c.isdigit() or c in "_./-\\:" for c in token) or any(
            c.isupper() for c in token[1:]
        )
        if shaped and not token.replace(".", "").replace("-", "").isdigit():
            out = {*out, token}
    return out


def text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            text_of(b.get("text") or b.get("content") or "") for b in content if isinstance(b, dict)
        )
    return ""


def when(entry: Mapping[str, Any]) -> float:
    raw = str(entry.get("timestamp") or "")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def entries(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and not row.get("isSidechain"):
            out = [*out, row]
    return out


def prompt_text(entry: Mapping[str, Any]) -> str | None:
    """The text of a first-level user prompt, or None for anything else."""
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isCompactSummary"):
        return None
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content
    ):
        return None
    text = text_of(content).strip()
    if not text or text.startswith(META_PREFIXES):
        return None
    return text


@dataclass(frozen=True)
class Block:
    """One step of the window: an assistant text, an assistant tool call, or a tool result."""

    kind: str  # "text" | "tool_use" | "tool_result"
    text: str
    tool: str = ""
    path: str = ""


def blocks_of(entry: Mapping[str, Any]) -> list[Block]:
    content = (entry.get("message") or {}).get("content")
    if not isinstance(content, list):
        return []
    out: list[Block] = []
    for b in content:
        if not isinstance(b, dict):
            continue
        kind = b.get("type")
        if entry.get("type") == "assistant" and kind == "text":
            out = [*out, Block("text", str(b.get("text") or ""))]
        elif entry.get("type") == "assistant" and kind == "tool_use":
            args = b.get("input") if isinstance(b.get("input"), dict) else {}
            path = str(args.get("file_path") or args.get("path") or "")
            out = [
                *out,
                Block("tool_use", json.dumps(args, ensure_ascii=False), str(b.get("name")), path),
            ]
        elif kind == "tool_result":
            out = [*out, Block("tool_result", text_of(b.get("content")))]
    return out


def memory_file_of(path: str, project: str) -> str | None:
    """The file name if `path` is a memory file of `project` (case-insensitive, any slash)."""
    norm = path.replace("\\", "/").lower()
    marker = f"/.claude/projects/{project.lower()}/memory/"
    if marker not in norm:
        return None
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    return name if name.lower().endswith(".md") and name != "MEMORY.md" else None


@dataclass(frozen=True)
class Case:
    project: str
    session: str
    index: int
    prompt: str
    at: float
    available: tuple[str, ...]
    read: tuple[str, ...]
    quoted: tuple[str, ...]
    written: tuple[str, ...]
    blocks: int = 0
    evidence: Mapping[str, str] = field(default_factory=dict)

    @property
    def relevant(self) -> tuple[str, ...]:
        both = (set(self.read) | set(self.quoted)) - set(self.written)
        return tuple(sorted(f for f in both if f in self.available))


def first_touches(
    sessions: Iterable[Sequence[Mapping[str, Any]]], project: str
) -> dict[str, float]:
    """Earliest `Write`/`Edit`/`Read` of every memory file, across all sessions: a file
    touched at t existed at t."""
    out: dict[str, float] = {}
    for rows in sessions:
        for row in rows:
            if row.get("type") != "assistant":
                continue
            for block in blocks_of(row):
                name = memory_file_of(block.path, project) if block.tool else None
                if name and block.tool in {*MEMORY_TOOLS_WRITE, "Read"}:
                    t = when(row)
                    if t and (name not in out or t < out[name]):
                        out = {**out, name: t}
    return out


def assistant_tokens(rows: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    """Distinctive tokens the assistant itself wrote (text or tool input), earliest time each."""
    out: dict[str, float] = {}  # a local accumulator: copying it per token is quadratic
    for row in rows:
        if row.get("type") != "assistant":
            continue
        t = when(row)
        for block in blocks_of(row):
            if block.kind == "tool_result":
                continue
            for token in distinctive_tokens(block.text):
                if token not in out or (t and t < out[token]):
                    out[token] = t
    return out


def recallable_tokens(
    tokens: Mapping[str, set[str]],
    born: Mapping[str, float],
    used_here: Mapping[str, float],
    other_projects: Mapping[str, int],
    *,
    elsewhere: int = 2,
) -> dict[str, set[str]]:
    """Amendment 1 of the pre-registration: drop the tokens that cannot be evidence of recall.

    - general vocabulary: the assistant used it in `elsewhere` or more OTHER projects
      (`dev/null`, `node_modules`, `package.json`);
    - older than the memory: the assistant used it in this project before the memory's first
      evidence of existence, so it came from somewhere else (a branch name, a known path).
    """
    out: dict[str, set[str]] = {}
    for file, bag in tokens.items():
        birth = born.get(file) or 0.0
        keep = {
            t
            for t in bag
            if other_projects.get(t, 0) < elsewhere
            and not (t in used_here and used_here[t] and birth and used_here[t] < birth)
        }
        out = {**out, file: keep}
    return out


def unique_tokens(memories: Mapping[str, str], shared: str) -> dict[str, set[str]]:
    """Per memory, the distinctive tokens that no other memory and no `shared` text holds."""
    bags = {f: distinctive_tokens(t) for f, t in memories.items()}
    common = distinctive_tokens(shared)
    out: dict[str, set[str]] = {}
    for f, bag in bags.items():
        others = set().union(*(b for g, b in bags.items() if g != f)) if len(bags) > 1 else set()
        out = {**out, f: bag - others - common}
    return out


def cases_of_session(
    rows: Sequence[Mapping[str, Any]],
    *,
    project: str,
    session: str,
    born: Mapping[str, float],
    tokens: Mapping[str, set[str]],
    window: int = WINDOW,
) -> Iterator[Case]:
    """Every first-level prompt of one session, labelled."""
    prompts = [(i, t) for i, row in enumerate(rows) if (t := prompt_text(row)) is not None]
    environment = environment_text(rows)
    history: list[str] = [environment]
    cursor = 0
    for n, (start, prompt) in enumerate(prompts):
        end = prompts[n + 1][0] if n + 1 < len(prompts) else len(rows)
        history = [*history, *(_row_text(r) for r in rows[cursor:start])]
        cursor = start
        before = "\n".join(history) + "\n" + prompt
        at = when(rows[start])
        available = tuple(sorted(f for f, b in born.items() if b and at and b < at))
        read, quoted, written, evidence, used = _scan(
            rows[start + 1 : end], project, tokens, before, window
        )
        yield Case(
            project, session, n, prompt, at, available, read, quoted, written, used, evidence
        )


def environment_text(rows: Iterable[Mapping[str, Any]]) -> str:
    """The session's working directories and git branches, in both slash styles.

    Amendment 2: they reach the model through the system prompt (cwd, git status), which the
    transcript does not hold, so a token found in them is not evidence of a memory."""
    values = {str(row.get(key)) for row in rows for key in ("cwd", "gitBranch") if row.get(key)}
    both = {v for value in values for v in (value, value.replace("\\", "/"))}
    return "\n".join(sorted(both))


def _row_text(row: Mapping[str, Any]) -> str:
    text = text_of((row.get("message") or {}).get("content"))
    return text if text else ""


def _scan(
    rows: Sequence[Mapping[str, Any]],
    project: str,
    tokens: Mapping[str, set[str]],
    before: str,
    window: int,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], dict[str, str], int]:
    read: set[str] = set()
    quoted: set[str] = set()
    written: set[str] = set()
    evidence: dict[str, str] = {}
    seen = before
    used = 0
    for row in rows:
        for block in blocks_of(row):
            if block.kind == "tool_result":
                seen += "\n" + block.text
                continue
            if used >= window:
                break
            used += 1
            name = memory_file_of(block.path, project) if block.tool else None
            if name and block.tool == "Read":
                read = {*read, name}
                continue
            if name and block.tool in MEMORY_TOOLS_WRITE:
                written = {*written, name}
                continue
            for file, bag in tokens.items():
                hit = next((t for t in bag if t in block.text and t not in seen), None)
                if hit:
                    quoted = {*quoted, file}
                    evidence = {**evidence, file: hit}
    return tuple(sorted(read)), tuple(sorted(quoted)), tuple(sorted(written)), evidence, used
