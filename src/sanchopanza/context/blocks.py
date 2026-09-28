"""A long tool result as blocks the tournament can judge, and the kept blocks as one text again.

The confirmed shape (`Squire.triage_many`, `docs/results/2026-09-27-hierarchy/`) judges pages
of up to `chunks.PAGE_LIMIT` characters with their siblings in view. A tool result is not a set
of pages, so it is cut into blocks of about that size, by the grain of what it is:

- `prose` (a fetched page, a Markdown file): paragraphs, blank-line separated, merged up to the
  target size;
- `code` (a source file read): blank-line blocks, and a new block at every top-level
  definition, merged up to the target size;
- `log` (command output, search hits): groups of consecutive lines up to the target size.

Every block is a character span of the original, `text[start:end]`, and the spans tile the text
without gaps or overlaps. That is what makes assembly literal: the agent gets the original
bytes of every kept span, in the original order, and one marker per run of omitted ones.
A single line longer than the target (minified code, a page without newlines) is split at
whitespace, so no block is unboundedly long.

Pure code: no decision is taken here.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any, Literal

Kind = Literal["prose", "code", "log"]

TARGET = 900  # chunks.PAGE_LIMIT: what one page of the in-context question shows
MAX_BLOCKS = 300  # past this the target grows, so the tournament stays at ~12 calls
CODE_SUFFIXES = frozenset(
    f".{s}"
    for s in [
        "py",
        "pyi",
        "js",
        "jsx",
        "ts",
        "tsx",
        "mjs",
        "cjs",
        "java",
        "kt",
        "go",
        "rs",
        "rb",
        "php",
        "c",
        "h",
        "cc",
        "cpp",
        "hpp",
        "cs",
        "swift",
        "scala",
        "sh",
        "bash",
        "ps1",
        "sql",
        "lua",
        "r",
        "m",
        "vue",
        "svelte",
        "json",
        "yaml",
        "yml",
        "toml",
        "ini",
        "cfg",
        "xml",
        "gradle",
        "tf",
        "dockerfile",
        "mk",
    ]
)
PROSE_SUFFIXES = frozenset(
    f".{s}" for s in ["md", "markdown", "txt", "rst", "adoc", "html", "htm", "tex", "org"]
)
LOG_TOOLS = frozenset({"Bash", "BashOutput", "Grep", "Glob", "LS", "TaskOutput", "KillShell"})
PROSE_TOOLS = frozenset({"WebFetch", "WebSearch"})
READ_TOOLS = frozenset({"Read", "NotebookRead"})
TOP_LEVEL = re.compile(
    r"^(?:async\s+def|def|class|function|export|const|let|var|fn|pub|impl|struct|enum|trait|"
    r"interface|type|func|module|package|public|private|protected|static|@)\b"
)


@dataclass(frozen=True, slots=True)
class Block:
    """`text[start:end]` of the original; lines are 1-based and inclusive."""

    start: int
    end: int
    first_line: int
    last_line: int

    def of(self, text: str) -> str:
        return text[self.start : self.end]


def kind_of(tool: str, tool_input: Mapping[str, Any] | None, text: str) -> Kind:
    """How to split a result: by the tool, then the file's suffix, then the text's shape."""
    tool_input = tool_input or {}
    if tool in LOG_TOOLS:
        return "log"
    if tool in PROSE_TOOLS:
        return "prose"
    if tool in READ_TOOLS:
        raw = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
        suffix = PurePath(raw.replace("\\", "/")).suffix.lower()
        if suffix in PROSE_SUFFIXES:
            return "prose"
        return "code"
    lines = text.splitlines() or [""]
    average = sum(len(line) for line in lines) / len(lines)
    return "log" if len(lines) > 30 and average < 60 else "prose"


def _units(text: str, target: int) -> list[tuple[int, int]]:
    """Lines as spans (newline included); a line longer than `target` split at whitespace."""
    out: list[tuple[int, int]] = []
    position = 0
    for line in text.splitlines(keepends=True):
        end = position + len(line)
        start = position
        while end - start > target:
            cut = text.rfind(" ", start + target // 2, start + target)
            cut = cut + 1 if cut > start else start + target
            out.append((start, cut))
            start = cut
        out.append((start, end))
        position = end
    return out


def _blank(text: str, span: tuple[int, int]) -> bool:
    return not text[span[0] : span[1]].strip()


def _boundary(text: str, units: Sequence[tuple[int, int]], i: int, kind: Kind) -> bool:
    """Whether a new block may start at unit `i`: after a blank line, or at a definition."""
    if i == 0 or kind == "log":
        return False
    if _blank(text, units[i - 1]) and not _blank(text, units[i]):
        return True
    return kind == "code" and bool(TOP_LEVEL.match(text[units[i][0] : units[i][1]]))


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def split(text: str, kind: Kind, *, target: int = TARGET, max_blocks: int = MAX_BLOCKS) -> list:
    """Blocks tiling `text`, in order. Never empty for a non-empty text."""
    if not text:
        return []
    if max_blocks > 0 and len(text) / target > max_blocks:
        target = -(-len(text) // max_blocks)
    units = _units(text, target)
    spans: list[tuple[int, int]] = []
    start = units[0][0]
    for i, (u_start, u_end) in enumerate(units):
        size = u_start - start
        soft = _boundary(text, units, i, kind) and size >= target // 3
        if size > 0 and (soft or size + (u_end - u_start) > target):
            spans.append((start, u_start))
            start = u_start
    spans.append((start, units[-1][1]))
    return [Block(s, e, _line_of(text, s), _line_of(text, max(s, e - 1))) for s, e in spans]


# --- sentences inside a block -------------------------------------------------------------

SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])")


def sentence_spans(text: str, block: Block) -> list[tuple[int, int]]:
    """The sentences of a block as spans of the original, in order, tiling the block."""
    body = block.of(text)
    cuts = [m.end() for m in SENTENCE_END.finditer(body)]
    bounds = [0, *cuts, len(body)]
    spans = [
        (block.start + a, block.start + b)
        for a, b in zip(bounds, bounds[1:], strict=False)
        if body[a:b].strip()
    ]
    return spans or [(block.start, block.end)]


# --- assembly -----------------------------------------------------------------------------

OMITTED = "[... sanchopanza omitted {what} ({chars} chars) ...]"
SENTENCE_GAP = " [...] "


def _lines(a: int, b: int, offset: int) -> str:
    a, b = a + offset, b + offset
    return f"line {a}" if a == b else f"lines {a}-{b}"


def assemble(
    text: str,
    blocks: Sequence[Block],
    kept: Sequence[bool | Sequence[tuple[int, int]]],
    *,
    line_offset: int = 0,
) -> str:
    """The kept parts of `text` in their original order, one marker per omitted run.

    `kept[i]` is True (the whole block), False (omitted), or the spans of the block to keep
    (sentences). Omitted sentences inside a kept block become `SENTENCE_GAP`; a run of omitted
    blocks becomes one line naming its lines, in the numbering of the original result plus
    `line_offset` (a `Read` that started at line 41 passes 40).
    """
    parts: list[str] = []
    run: list[Block] = []

    def flush() -> None:
        if not run:
            return
        what = _lines(run[0].first_line, run[-1].last_line, line_offset)
        chars = sum(b.end - b.start for b in run)
        marker = OMITTED.format(what=what, chars=chars)
        needs_break = parts and not parts[-1].endswith("\n")
        parts.append(("\n" if needs_break else "") + marker + "\n")
        run.clear()

    for block, keep in zip(blocks, kept, strict=True):
        if keep is True:
            flush()
            parts.append(block.of(text))
        elif keep is False or not keep:
            run.append(block)
        else:
            flush()
            parts.append(_partial(text, block, keep))
    flush()
    return "".join(parts)


def _partial(text: str, block: Block, spans: Sequence[tuple[int, int]]) -> str:
    out: list[str] = []
    cursor = block.start
    for start, end in sorted(spans):
        if start > cursor and text[cursor:start].strip():
            out.append(SENTENCE_GAP)
        elif start > cursor:
            out.append(text[cursor:start])
        out.append(text[start:end])
        cursor = end
    if cursor < block.end and text[cursor : block.end].strip():
        out.append(SENTENCE_GAP.rstrip() + ("\n" if text[block.end - 1] == "\n" else ""))
    elif cursor < block.end:
        out.append(text[cursor : block.end])
    return "".join(out)
