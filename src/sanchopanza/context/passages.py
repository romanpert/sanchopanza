"""Passages on arrival for coding sessions: a large shell output or Read cut to a fraction.

Bet A of `docs/PLAN-GANAR-H2H.md`. The replay of 141 real sessions put 32 % of the bill in
tool output that is read again on every later request (shell 76 %, Read 23 %). Cutting it before
it enters the context is free for the cache: nothing already in the prefix changes. The hook is
`harness.passages_hook`; this module is the pure half, no decider and no I/O.

What is cut, and how (decided here, measured nowhere yet):

- **Size.** A result past `Settings.tokens` tokens (default 2,000, at the 2.2 characters per
  token measured on real sessions: 4,400 characters) keeps about `Settings.fraction` of its
  characters (25 %; the second arm 10 %). A cut that saves less than `min_saving` passes whole.
- **Grain.** Code (a `Read` of a source file) is cut into blocks at definitions and blank lines
  (`blocks.split`, `code`); prose at paragraphs; shell output at blank lines, headers (`==> f <==`,
  `diff --git`, rules, `Title:` lines) and where `grep -n` hits move to another file (`shell`).
  Blocks are about a third of the budget (200 to 900 characters), so even the 10 % arm has
  several to choose from. What is kept is always whole lines, byte for byte: the agent edits by
  content, and `Edit` needs the literal text.
- **Line numbers.** Shell output: every omitted run becomes one marker naming its lines in the
  original numbering (`blocks.assemble`). A `Read` keeps every line in its place
  (`render_in_place`, review 2026-10-07): Claude Code numbers `content` from `startLine` straight
  through, so an omitted line becomes an empty one (2 or 3 tokens with its number) and the first
  line of each run holds a marker with its lines, the definitions it held and the `Read` that
  shows it. A kept fragment of a long function keeps the line that opens it (`_enclosing`), so a
  body never arrives without its signature.
- **Rules before ranking.** "Test" covers tests and the other commands that print diagnostics:
  type checkers, linters, compilers, build tools (`TEST_COMMAND`); a search (`grep`, `rg`,
  `findstr`, `Select-String`) is its own kind with no rule. In a test log every failure line is
  kept, with no model: `file:line: error`/`warning` diagnostics, FAILED and
  ERROR lines, pytest's `E` and `>` lines and section titles, a traceback (its first 4 and last 24
  lines), `file:line: Error` lines, panics, compiler errors, and the summary lines of pytest,
  jest, go, cargo and unittest, plus the last 3 lines. Plain shell output keeps only strong
  failures anchored at the line start (`Traceback`, `fatal:`, `error:`, `SomeError:`) and its
  last 2 lines: a `grep error` must not turn every hit into a rule.
- **Ranking.** The rest is ranked by the caller: `bm25_order` (free; identifiers split into
  their words, so `parse_config` meets "config parser") or `probability_order` over the
  decider's probabilities (the paragraph tournament, `Squire.triage_many`). Blocks are taken in
  that order while they fit the budget; the first always goes in.

`fit` is the same cut sized to a limit: Claude Code shows the model only the first 2,000
characters of a `Bash` output it saved to a file, so the hook previews within that.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import Any, Literal

from ..text import bm25_scores
from . import blocks

Kind = Literal["code", "prose", "shell", "test", "search"]

CHARS_PER_TOKEN = 2.2  # measured on 141 real sessions with their `usage` (PLAN-GANAR-H2H 4)
DEFAULT_TOKENS = 2_000
DEFAULT_FRACTION = 0.25
DEFAULT_MIN_SAVING = 0.2
UNIT_MIN, UNIT_MAX = 200, 900
TRACEBACK_HEAD, TRACEBACK_TAIL = 4, 24
TAIL_LINES = {"test": 3, "shell": 2}
OUTLINE_NAMES = 4
FIT_TRIES = 8
MARKER_CHARS = 60  # about what one omission marker costs: a shorter gap is kept instead
IN_PLACE_MARKER_CHARS = 100  # the in-place marker is longer: it names the Read that shows it


@dataclass(frozen=True, slots=True)
class Settings:
    tokens: int = DEFAULT_TOKENS
    fraction: float = DEFAULT_FRACTION
    min_saving: float = DEFAULT_MIN_SAVING

    @property
    def threshold_chars(self) -> int:
        return round(self.tokens * CHARS_PER_TOKEN)


@dataclass(frozen=True, slots=True)
class Layout:
    """`atoms` tile the text (one per line); `units` are the ranked blocks, as `[a, b)` ranges of
    atoms; `must` holds the atoms the rules keep."""

    kind: str
    atoms: tuple[blocks.Block, ...]
    units: tuple[tuple[int, int], ...]
    must: frozenset[int]


@dataclass(frozen=True, slots=True)
class Cut:
    """`text` is what the agent gets without the hook's header, or None: pass the original."""

    text: str | None
    reason: str
    report: Mapping[str, Any] = field(default_factory=dict)
    kept: frozenset[int] = frozenset()  # the atoms kept, before small gaps are filled


# --- what the output is ----------------------------------------------------------------------

# Tests, and the other commands whose output is a list of diagnostics: type checkers, linters,
# compilers and build tools (review 2026-10-07: their `error:` lines are kept by rule too).
TEST_COMMAND = re.compile(
    r"\b(?:py\.?test|unittest|nose2|tox|nox|jest|vitest|mocha|karma|rspec|phpunit|ctest|bats"
    r"|mypy|pyright|tsc|ruff|flake8|pylint|eslint|stylelint|biome|clippy|golangci-lint"
    r"|go\s+(?:test|build|vet)|cargo\s+(?:test|nextest|build|check|clippy)"
    r"|(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?(?:test|build|lint|typecheck|check)"
    r"|make|dotnet\s+(?:test|build)|gradlew?|mvn|msbuild)\b"
)
# Commands whose output is search hits: no rule keeps a line for saying "error".
SEARCH_COMMAND = re.compile(
    r"^\s*(?:grep|egrep|fgrep|rg|ag|ack|findstr|git\s+grep|Select-String|sls)\b", re.I
)
TEST_SHAPE = re.compile(
    r"(?m)^(?:=+ test session starts =+$|Tests?:\s+\d+|test result: |Ran \d+ tests? in "
    r"|(?:ok|FAIL)\s+\S+\s+[\d.]+s$|---- FAILURES ----)"
)


def kind_of(tool: str, tool_input: Mapping[str, Any] | None, text: str) -> Kind:
    """Code or prose for a `Read` (by suffix); test log or plain shell output for a command."""
    tool_input = tool_input or {}
    if tool in blocks.READ_TOOLS:
        raw = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
        suffix = PurePath(raw.replace("\\", "/")).suffix.lower()
        return "prose" if suffix in blocks.PROSE_SUFFIXES else "code"
    command = str(tool_input.get("command") or "")
    if SEARCH_COMMAND.search(command):
        return "search"
    if TEST_COMMAND.search(command) or TEST_SHAPE.search(text[:4000] + "\n" + text[-4000:]):
        return "test"
    return "shell"


# --- the rules: what is kept with no ranking -------------------------------------------------

TEST_FAILURE = re.compile(
    r"^(?:FAILED|FAIL|ERROR)\b|\s(?:FAILED|ERROR)(?:\s|$)|^E\s{2,}\S|^>\s|^_{3,} .+ _{3,}$"
    r"|Traceback \(most recent call last\)|^\s*File \"[^\"]+\", line \d+"
    r"|^[\w.]*(?:Error|Exception|Failure)\b:?|^\S+:\d+: (?:in \w+|\w*(?:Error|Exception))"
    r"|\bpanic(?:ked)?\b|^--- FAIL|^\s*(?:✕|✗|×|●)\s"
    r"|\berror(?:\[[A-Z]?\d+\])?:|^npm ERR!|^fatal:|\bSegmentation fault\b|\bassert\b.*=="
    r"|^\S+?[:(]\d+.*\b(?i:error|warning)\b|^(?i:error|warning)(?:\[\w+\])?:|^\s*--> \S+:\d+"
    r"|^[\w./\\-]+\.\w+:\d+:\d+:? |^\s+\d+:\d+\s+(?:error|warning)\b"
)
TEST_SUMMARY = re.compile(
    r"^=+ .*\b(?:passed|failed|errors?|skipped|deselected|xfailed|xpassed|warnings?)\b.* =+$"
    r"|^=+ (?:FAILURES|ERRORS|short test summary info) =+$|^(?:Tests|Test Suites|Snapshots):\s"
    r"|^test result:|^Ran \d+ tests? in|^(?:OK|FAILED)(?: \(.*\))?$|^(?:ok|FAIL)\s+\S+\s+[\d.]+s"
    r"|^\d+ (?:passing|failing|pending)\b|^Found \d+ errors?\b|^Success: no issues"
    r"|^\W*\d+ problems? \(|^error: could not compile|^BUILD (?:SUCCESSFUL|FAILED)"
    r"|^Build (?:succeeded|FAILED)|^\d+ errors? (?:generated|found)"
)
SHELL_FAILURE = re.compile(
    r"^(?:Traceback \(most recent call last\)|fatal:|error(?:\[[A-Z]?\d+\])?:|npm ERR!"
    r"|[\w.]*(?:Error|Exception):)|panicked at|^\S+?[:(]\d+[:,)].*\b(?i:error|warning)\b"
)


def _traceback_lines(lines: Sequence[str]) -> set[int]:
    """Python tracebacks: from `Traceback` to the exception line, head and tail of a long one."""
    out: set[int] = set()
    i = 0
    while i < len(lines):
        if "Traceback (most recent call last)" not in lines[i]:
            i += 1
            continue
        end = i + 1
        while end < len(lines) and (not lines[end].strip() or lines[end][:1].isspace()):
            end += 1
        last = min(end, len(lines) - 1)
        region = list(range(i, last + 1))
        if len(region) > TRACEBACK_HEAD + TRACEBACK_TAIL:
            region = region[:TRACEBACK_HEAD] + region[-TRACEBACK_TAIL:]
        out.update(region)
        i = last + 1
    return out


def must_lines(text: str, kind: str) -> frozenset[int]:
    """0-based line indexes the rules keep: failures, tracebacks, summaries and the tail."""
    if kind not in TAIL_LINES:
        return frozenset()
    lines = text.splitlines()
    rule = TEST_FAILURE if kind == "test" else SHELL_FAILURE
    keep = {i for i, line in enumerate(lines) if rule.search(line)}
    if kind == "test":
        keep |= {i for i, line in enumerate(lines) if TEST_SUMMARY.search(line)}
    keep |= _traceback_lines(lines)
    filled = [i for i, line in enumerate(lines) if line.strip()]
    keep |= set(filled[-TAIL_LINES[kind] :])
    return frozenset(keep)


# --- the layout ------------------------------------------------------------------------------

GRAIN: Mapping[str, blocks.Kind] = {"code": "code", "prose": "prose", "shell": "shell",
                                    "test": "shell", "search": "shell"}  # fmt: skip


def budget_for(text: str, settings: Settings) -> int:
    return max(1, int(len(text) * settings.fraction))


def layout(text: str, kind: str, budget: int) -> Layout:
    target = blocks.effective_target(text, max(UNIT_MIN, min(UNIT_MAX, budget // 3)))
    pieces = tuple(blocks.atoms(text, target))
    spans = blocks.split(text, GRAIN.get(kind, "log"), target=target)
    units: list[tuple[int, int]] = []
    cursor = 0
    for span in spans:
        start = cursor
        while cursor < len(pieces) and pieces[cursor].start < span.end:
            cursor += 1
        if cursor > start:
            units.append((start, cursor))
    rules = must_lines(text, kind)
    must = frozenset(i for i, atom in enumerate(pieces) if atom.first_line - 1 in rules)
    return Layout(kind, pieces, tuple(units), must)


def unit_text(text: str, lay: Layout, unit: int) -> str:
    a, b = lay.units[unit]
    return text[lay.atoms[a].start : lay.atoms[b - 1].end]


# --- ranking ---------------------------------------------------------------------------------

_IDENT = re.compile(
    r"[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+|[a-z]+(?:[A-Z][a-z0-9]*)+|[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+"
)
_HUMP = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")


def expand(text: str) -> str:
    """The text with its compound identifiers also spelt as words: `parseConfig` adds `parse
    config`, so BM25 meets a request in prose."""
    words = [w.lower() for ident in _IDENT.findall(text) for part in ident.split("_")
             for w in _HUMP.findall(part)]  # fmt: skip
    return f"{text} {' '.join(words)}" if words else text


def _fallback(count: int, kind: str) -> list[int]:
    """The order of blocks nothing scored: the start of a file, the end of a log first."""
    if kind in ("code", "prose"):
        return list(range(count))
    head, tail = 0, count - 1
    out: list[int] = []
    while head <= tail:
        out.append(tail)
        if head != tail:
            out.append(head)
        head, tail = head + 1, tail - 1
    return out


def bm25_order(text: str, lay: Layout, query: str) -> list[int]:
    """Units by BM25 against `query`, best first; those with no shared word in `_fallback` order."""
    docs = [expand(unit_text(text, lay, u)) for u in range(len(lay.units))]
    scores = bm25_scores(expand(query), docs) if query.strip() else [0.0] * len(docs)
    hits = sorted((u for u, s in enumerate(scores) if s > 0), key=lambda u: (-scores[u], u))
    rest = [u for u in _fallback(len(docs), lay.kind) if scores[u] <= 0]
    return [*hits, *rest]


def probability_order(probabilities: Sequence[float | None]) -> list[int]:
    """Units by the decider's probability, best first; unanswered ones at 0.5."""
    p = [0.5 if x is None else float(x) for x in probabilities]
    return sorted(range(len(p)), key=lambda u: (-p[u], u))


# --- selection and assembly ------------------------------------------------------------------

DEFINITION = re.compile(
    r"^\s*(?:(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:def|class|function|func|fn)\b"
    r"|(?:pub(?:\(\w+\))?\s+)?(?:fn|struct|enum|trait|impl)\b|(?:public|private|protected)\b.*\()"
)
_SCAN_BACK = 400


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _enclosing(text: str, lay: Layout, unit: int) -> int | None:
    """The atom of the definition a code unit sits in, when the unit does not open with one."""
    a, b = lay.units[unit]
    first = next((i for i in range(a, b) if lay.atoms[i].of(text).strip()), None)
    if first is None or DEFINITION.match(lay.atoms[first].of(text)):
        return None
    depth = _indent(lay.atoms[first].of(text))
    for i in range(first - 1, max(-1, first - _SCAN_BACK), -1):
        line = lay.atoms[i].of(text)
        if line.strip() and _indent(line) < depth and DEFINITION.match(line):
            return i
    return None


def select(text: str, lay: Layout, order: Sequence[int], budget: int,
           *, at_least_one: bool = True) -> frozenset[int]:  # fmt: skip
    """Atoms kept: the rules', then whole units in `order` while they fit `budget` characters."""
    kept = set(lay.must)
    used = sum(lay.atoms[i].end - lay.atoms[i].start for i in kept)
    taken = not at_least_one
    for unit in order:
        new = [i for i in range(*lay.units[unit]) if i not in kept]
        if lay.kind == "code" and new:
            opener = _enclosing(text, lay, unit)
            new += [opener] if opener is not None and opener not in kept else []
        cost = sum(lay.atoms[i].end - lay.atoms[i].start for i in new)
        if not new or (taken and used + cost > budget):
            continue
        kept.update(new)
        used, taken = used + cost, True
        if used >= budget:
            break
    return frozenset(kept)


_NAMED = re.compile(
    r"^(?:export\s+)?(?:async\s+)?(def|class|function|func|fn|struct|interface|type)\s+(\w+)", re.M
)


def outline(omitted: str) -> str:
    """The top-level definitions an omitted run of code held: `def a, class B, +3 more`."""
    names = [f"{kind} {name}" for kind, name in _NAMED.findall(omitted)]
    if not names:
        return ""
    shown = names[:OUTLINE_NAMES]
    more = len(names) - len(shown)
    return ", ".join(shown) + (f", +{more} more" if more else "")


def _small_gaps(lay: Layout, kept: frozenset[int]) -> frozenset[int]:
    """`kept` plus every omitted run shorter than its marker would be."""
    out, run = set(kept), []
    for i in [*range(len(lay.atoms)), None]:
        if i is not None and i not in kept:
            run.append(i)
            continue
        if run and sum(lay.atoms[j].end - lay.atoms[j].start for j in run) < MARKER_CHARS:
            out.update(run)
        run = []
    return frozenset(out)


def render(text: str, lay: Layout, kept: frozenset[int], *, line_offset: int = 0) -> str:
    kept = _small_gaps(lay, kept)
    flags = [i in kept for i in range(len(lay.atoms))]
    describe = outline if lay.kind == "code" else None
    return blocks.assemble(text, lay.atoms, flags, line_offset=line_offset, describe=describe)


def _ending(line: str) -> str:
    return "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""


def omitted_runs(text: str, lay: Layout, kept: frozenset[int]) -> list[tuple[int, int]]:
    """The runs of lines left out, 0-based and inclusive, once a run shorter than its marker
    (`IN_PLACE_MARKER_CHARS`) is kept instead."""
    lines = text.splitlines(keepends=True)
    shown: set[int] = set()
    for i in kept:
        shown.update(range(lay.atoms[i].first_line - 1, lay.atoms[i].last_line))
    runs: list[tuple[int, int]] = []
    start = None
    for n in [*range(len(lines)), None]:
        if n is not None and n not in shown:
            start = n if start is None else start
            continue
        if start is not None:
            end = (len(lines) if n is None else n) - 1
            if sum(len(x) for x in lines[start : end + 1]) >= IN_PLACE_MARKER_CHARS:
                runs.append((start, end))
        start = None
    return runs


def render_in_place(text: str, lay: Layout, kept: frozenset[int], *, line_offset: int = 0,
                    header: str = "") -> str:  # fmt: skip
    """A `Read` cut that keeps every line where it was: Claude Code numbers `content` from
    `startLine` straight through (seen in 2.1.287), so an omitted line becomes an empty one and
    the numbers beside the kept lines stay the file's. The first line of each omitted run holds
    one marker with its lines, the definitions it held and the `Read` that shows it; `header`
    (one line) goes on the last line of the last run, never first, never as an extra line."""
    lines = text.splitlines(keepends=True)
    out = list(lines)
    runs = omitted_runs(text, lay, kept)
    for a, b in runs:
        label = outline("".join(lines[a : b + 1])) if lay.kind == "code" else ""
        first, last = a + 1 + line_offset, b + 1 + line_offset
        held = f" ({label})" if label else ""
        marker = f"[sanchopanza: lines {first}-{last} omitted{held}; Read offset={first} " \
                 f"limit={last - first + 1}]"  # fmt: skip
        out[a : b + 1] = [_ending(line) for line in lines[a : b + 1]]
        out[a] = marker + _ending(lines[a])
    if header and runs:
        a, b = runs[-1]
        note = header.replace("\n", " ").strip()
        out[b] = (out[b].rstrip("\r\n") + " " if a == b else "") + note + _ending(lines[b])
    return "".join(out)


def rendered_size(text: str, line_offset: int = 0) -> int:
    """Characters the model reads of a `Read`: each line with its number and a separator."""
    return sum(len(str(n + 1 + line_offset)) + 1 + len(line)
               for n, line in enumerate(text.splitlines()))  # fmt: skip


def cut_ordered(text: str, lay: Layout, order: Sequence[int], settings: Settings,
                *, line_offset: int = 0, in_place: bool = False) -> Cut:  # fmt: skip
    """The cut for a ranking already made. Passes whole when it saves under `min_saving`.
    `in_place` renders a `Read` (`render_in_place`) and measures the saving with line numbers."""
    kept = select(text, lay, order, budget_for(text, settings))
    if in_place:
        out = render_in_place(text, lay, kept, line_offset=line_offset)
        before, after = rendered_size(text, line_offset), rendered_size(out, line_offset)
    else:
        out = render(text, lay, kept, line_offset=line_offset)
        before, after = len(text), len(out)
    saving = 1 - after / before
    report = {
        "kind": lay.kind,
        "units": len(lay.units),
        "kept_units": sum(all(i in kept for i in range(a, b)) for a, b in lay.units),
        "must_lines": len({lay.atoms[i].first_line for i in lay.must}),
        "chars_in": len(text),
        "chars_out": len(out),
        "rendered_in": before,
        "rendered_out": after,
        "saving": round(saving, 4),
    }
    if saving < settings.min_saving:
        why = f"saves {saving:.0%}, under {settings.min_saving:.0%}: passed whole"
        return Cut(None, why, report, kept)
    return Cut(out, f"kept {len(out)} of {len(text)} chars", report, kept)


def cut_free(text: str, kind: str, query: str, settings: Settings,
             *, line_offset: int = 0) -> Cut:  # fmt: skip
    """The whole cut with BM25 ranking: no decider. Pure; never raises on input."""
    if len(text) < settings.threshold_chars:
        return Cut(None, f"under {settings.threshold_chars} chars")
    lay = layout(text, kind, budget_for(text, settings))
    if len(lay.units) < 2:
        return Cut(None, "one block: nothing to choose between", {"kind": kind})
    return cut_ordered(text, lay, bm25_order(text, lay, query), settings, line_offset=line_offset)


def fit(text: str, lay: Layout, order: Sequence[int], limit: int, *, line_offset: int = 0) -> str:
    """The cut rendered within `limit` characters: the budget shrinks until it fits, then the
    ranked blocks go and only the rules' lines stay; past that, the rendering is cut short."""
    budget, out = limit, ""
    for attempt in range(FIT_TRIES):
        kept = select(text, lay, order, budget, at_least_one=attempt < FIT_TRIES // 2)
        out = render(text, lay, kept, line_offset=line_offset)
        if len(out) <= limit:
            return out
        budget = int(budget * 0.7)
    return out[: out.rfind("\n", 0, limit) + 1] if "\n" in out[:limit] else out[:limit]
