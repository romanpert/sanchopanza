"""A recall gate for Claude Code's auto memory: put the memories a prompt needs in front of it.

Claude Code keeps auto memory in `~/.claude/projects/<project>/memory/`: one fact per `*.md`
file with a YAML front matter (`name`, `description`, `type`) and an index, `MEMORY.md`, of
which only the head loads at session start. Everything else waits for the model to decide, by
itself, to `Read` a memory file, and it often does not. The memory exists and goes unused.

This module is a `UserPromptSubmit` hook body. Per prompt:

1. `Squire.needs_recall` on the prompt, with the memory names as `topics`. A confident "this
   turn is self-contained" (p <= 1 - `act`) skips everything else: no memory call, nothing
   injected. Any other answer, including none, goes on.
2. Every memory file of the project judged in context against the prompt: `Squire.triage_pages`
   (one call, up to `chunks.PAGE_MAX` files) or `Squire.triage_many` (a tournament) with the
   prompt as `purpose` and `(file: name, description + body)` as the pages. This is the shape
   confirmed on HotpotQA (docs/results/2026-09-27-chunks/, -hierarchy/), reused unchanged.
3. The kept memories, most probable first, rendered under `cap` characters, each headed by its
   file name so the model can open the full file. What did not fit is listed by name.

Optional, off by default because it costs calls: `check_conflicts` runs `Squire.reconcile` on
at most `max_pairs` pairs of kept memories that share vocabulary. A pair the decider calls a
contradiction with the newer file known (mtime) drops the older one; an unresolved one is
injected with a warning naming both files.

Three rules that hold everywhere here:

- **Fail open means inject nothing.** A decider that answers nothing, a memory directory that
  cannot be read, a bug of ours: the prompt goes through exactly as it would without the hook,
  and the reason is written to stderr. A triage in which no page got an answer injects nothing
  (the null decider in a dry run does exactly that).
- **Secrets never leave.** The prompt and every memory are passed through
  `redact.redact_secrets` before any state is built, whatever the squire's own redactor is.
- **Measured before shipped.** Whether this helps is pre-registered in
  `docs/results/2026-09-28-memory-gate/prereg.md`. Until that runs, it is an opt-in.

**The hybrid store (autopilot).** `recall` treats the memory files and the autopilot's archive
(`context.archive`: tool output cut on arrival or stubbed at compaction) as one store. BM25
proposes the top `k` entries for the query, and one `Squire.triage_pages` over those `k`
(each read through `text.excerpt` against the query) keeps what contributes: the "hybrid" shape
registered in `docs/results/2026-09-28-memory-gate/prereg-longmemeval.md`, Amendment 2. It runs
at `UserPromptSubmit` (query: the prompt) and, in the autopilot, at `PostToolUse` (query: the
latest prompt plus what the agent is doing now), appending `additionalContext` only: nothing
already in the conversation is rewritten, so no cached prefix is invalidated. An archived entry
is shown as its passage that best matches the query, headed by its full path.

Hook output (https://code.claude.com/docs/en/hooks, UserPromptSubmit): exit 0 with
`{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "..."}}`.
The documentation states no size limit for `additionalContext`; `cap` is ours.
"""

from __future__ import annotations

import contextlib
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..points import chunks
from ..redact import redact_secrets
from ..text import BM25Index, excerpt

if TYPE_CHECKING:
    from ..squire import Squire

INDEX = "MEMORY.md"
CAP = 10_000  # characters of additionalContext; the auto-memory index itself loads 25 KB
BODY_LIMIT = 3_000  # one memory's share of the rendered context, before the cap
TOPICS_LIMIT = 500
PROMPT_MIN = 3
MAX_PAIRS = 3
HEADER = (
    "sanchopanza memory gate: saved memories of this project that look relevant to this "
    "request (directory {dir}). Each is headed by its file; Read the file for the full text."
)
EVENT = "UserPromptSubmit"
TAIL = "Also relevant, not shown for space (Read them if needed): "

_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.S)
_WORD = re.compile(r"[A-Za-z0-9_À-ɏ]{4,}")


@dataclass(frozen=True, slots=True)
class Memory:
    """One memory file. `text` is what a decision reads: description and body, redacted."""

    file: str
    name: str
    description: str
    body: str
    mtime: float = 0.0
    kind: str = ""
    # What BM25 scores when it differs from what a decision reads: an archived entry is
    # searched over its whole text and shown as its best passage. Empty: `name` + `text`.
    search: str = ""

    @property
    def text(self) -> str:
        return f"{self.description}\n{self.body}".strip()

    @property
    def title(self) -> str:
        return f"{self.file}: {self.name}" if self.name else self.file


@dataclass(frozen=True, slots=True)
class GateResult:
    """What the gate decided for one prompt. `context` is empty when nothing is injected."""

    context: str
    injected: tuple[str, ...]
    listed: tuple[str, ...]
    reason: str
    report: Mapping[str, Any] = field(default_factory=dict)


# --- loading ----------------------------------------------------------------------------


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """`key: value` lines of a leading `---` block, and the body after it. Never raises."""
    match = _FRONT.match(text.replace("\r\n", "\n"))
    if not match:
        return {}, text.strip()
    meta: dict[str, str] = {}
    nested: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if not (sep and key.strip()):
            continue
        entry = {key.strip().lower(): value.strip().strip("'\"")}
        if line.startswith((" ", "\t")):
            nested = {**entry, **nested}  # first nested value wins, e.g. metadata.type
        else:
            meta = {**meta, **entry}
    meta = {**{k: v for k, v in nested.items() if v}, **{k: v for k, v in meta.items() if v}}
    return meta, text.replace("\r\n", "\n")[match.end() :].strip()


def memory_from_text(file: str, text: str, *, mtime: float = 0.0) -> Memory:
    meta, body = parse_frontmatter(text)
    return Memory(
        file=file,
        name=redact_secrets(meta.get("name", "")),
        description=redact_secrets(meta.get("description", "")),
        kind=meta.get("type", ""),
        body=redact_secrets(body),
        mtime=mtime,
    )


def load_memories(directory: Path) -> tuple[Memory, ...]:
    """Every `*.md` memory file of a directory except the index, sorted by file name.

    Unreadable files are skipped, not fatal: one broken memory must not hide the others.
    """
    if not directory.is_dir():
        return ()
    out: list[Memory] = []
    for path in sorted(directory.glob("*.md")):
        if path.name == INDEX or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            mtime = path.stat().st_mtime
        except OSError:
            continue
        out = [*out, memory_from_text(path.name, text, mtime=mtime)]
    return tuple(out)


def project_key(cwd: str) -> str:
    """Claude Code's directory name for a project: every non-alphanumeric character -> '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", cwd)


def memory_dir_for(event: Mapping[str, Any], *, home: Path | None = None) -> Path | None:
    """The memory directory of the session that sent `event`.

    The transcript lives in the project directory, so its parent is the most reliable anchor
    (the cwd can move during a session). Falls back to the cwd, then to None.
    """
    transcript = str(event.get("transcript_path") or "")
    if transcript:
        return Path(transcript).parent / "memory"
    cwd = str(event.get("cwd") or "")
    if cwd:
        base = home if home is not None else Path.home()
        return base / ".claude" / "projects" / project_key(cwd) / "memory"
    return None


# --- pure pieces ------------------------------------------------------------------------


def pages_of(memories: Sequence[Memory], purpose: str = "") -> list[tuple[str, str]]:
    """(title, text) per memory. With `purpose`, a text longer than `chunks.PAGE_LIMIT` is
    sent as its head plus the window that best matches the purpose (`text.excerpt`), not as
    its head only: the part a prompt needs is often in the middle of a long memory."""
    if not purpose:
        return [(m.title, m.text) for m in memories]
    return [(m.title, excerpt(m.text, purpose, chunks.PAGE_LIMIT)) for m in memories]


def topics_of(memories: Sequence[Memory]) -> str:
    names = "; ".join(m.name or m.file for m in memories)
    return names[:TOPICS_LIMIT]


def order_kept(
    memories: Sequence[Memory], verdicts: Sequence[tuple[bool, float | None]]
) -> list[tuple[Memory, float | None]]:
    """Kept memories, most probable first; unanswered ones after every answered one."""
    kept = [(m, p) for m, (keep, p) in zip(memories, verdicts, strict=True) if keep]
    return sorted(kept, key=lambda mp: (mp[1] is None, -(mp[1] or 0.0)))


def _block(memory: Memory) -> str:
    body = memory.body
    if len(body) > BODY_LIMIT:
        body = body[:BODY_LIMIT] + " [...]"
    return f"## {memory.file} - {memory.name}\n{memory.description}\n{body}".strip()


def render(
    selected: Sequence[Memory],
    *,
    directory: str = "",
    cap: int = CAP,
    warnings: Iterable[str] = (),
    header: str = HEADER,
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """(context, files shown, files only listed by name). Never longer than `cap`.

    Memories are shown whole (up to `BODY_LIMIT`) in the given order while they fit, always
    leaving room to name every memory after them; what does not fit is listed by file name.
    """
    if not selected or cap <= 0:
        return "", (), ()
    parts = [header.format(dir=directory or "memory/"), *(f"Warning: {w}" for w in warnings)]
    used = sum(len(p) + 2 for p in parts) + len(TAIL)
    shown: list[str] = []
    listed: list[str] = []
    for index, memory in enumerate(selected):
        later = sum(len(m.file) + 2 for m in selected[index + 1 :])
        block = _block(memory)
        if used + len(block) + 2 + later <= cap:
            parts = [*parts, block]
            used += len(block) + 2
            shown = [*shown, memory.file]
        else:
            listed = [*listed, memory.file]
    if listed:
        parts = [*parts, TAIL + ", ".join(listed)]
    return "\n\n".join(parts)[:cap], tuple(shown), tuple(listed)


def hook_output(context: str, event: str = EVENT) -> dict[str, Any]:
    if not context:
        return {}
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}}


def _words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text)}


def conflict_candidates(
    memories: Sequence[Memory], *, max_pairs: int = MAX_PAIRS, min_overlap: float = 0.2
) -> list[tuple[int, int]]:
    """Pairs of the given memories most likely to speak about the same thing, by Jaccard
    overlap of their words, at most `max_pairs`. Code, not a decision: it only bounds calls."""
    bags = [_words(m.text) for m in memories]
    scored = []
    for i in range(len(memories)):
        for j in range(i + 1, len(memories)):
            union = bags[i] | bags[j]
            overlap = len(bags[i] & bags[j]) / len(union) if union else 0.0
            if overlap >= min_overlap:
                scored = [*scored, (overlap, i, j)]
    return [(i, j) for _, i, j in sorted(scored, reverse=True)[:max_pairs]]


# --- decisions --------------------------------------------------------------------------


async def triage_memories(
    squire: Squire, prompt: str, memories: Sequence[Memory]
) -> list[tuple[bool, float | None]]:
    # `triage_many` is one in-context call up to `chunks.PAGE_MAX` pages and a tournament past
    # it, so there is no second path to keep in step.
    return await squire.triage_many(purpose=prompt, pages=pages_of(memories, purpose=prompt))


async def _conflicts(
    squire: Squire, kept: Sequence[Memory], max_pairs: int
) -> tuple[set[str], list[str]]:
    """(files to drop, warnings). Only a contradiction with a known newer side drops."""
    drop: set[str] = set()
    warnings: list[str] = []
    for i, j in conflict_candidates(kept, max_pairs=max_pairs):
        a, b = kept[i], kept[j]
        if a.mtime == b.mtime:
            newer, old = a, b
            known: bool | None = None
        else:
            newer, old = (a, b) if a.mtime > b.mtime else (b, a)
            known = True
        verdict = await squire.reconcile(new=newer.text, stored=old.text, newer=known)
        if verdict.action == "replace":
            drop = {*drop, old.file}
        elif verdict.action == "flag":
            warnings = [*warnings, f"{a.file} and {b.file} may contradict each other"]
    return drop, warnings


async def gate(
    squire: Squire,
    prompt: str,
    memories: Sequence[Memory],
    *,
    directory: str = "",
    cap: int = CAP,
    check_conflicts: bool = False,
    max_pairs: int = MAX_PAIRS,
) -> GateResult:
    """Decide what to inject for one prompt. Raises only on a bug; `handle_user_prompt` wraps."""
    prompt = redact_secrets(prompt.strip())
    base = {"memories": len(memories), "prompt_chars": len(prompt)}
    if not memories:
        return GateResult("", (), (), "no memory files", base)
    if len(prompt) < PROMPT_MIN:
        return GateResult("", (), (), "prompt too short to judge", base)
    recall = await squire.needs_recall(prompt, topics=topics_of(memories))
    report = {**base, "recall_p": recall.probability, "recall": recall.reason}
    if not recall.look:
        return GateResult("", (), (), f"no recall needed: {recall.reason}", report)
    verdicts = await triage_memories(squire, prompt, memories)
    answered = sum(p is not None for _, p in verdicts)
    probabilities = {m.file: p for m, (_, p) in zip(memories, verdicts, strict=True)}
    report = {**report, "answered": answered, "probabilities": probabilities}
    if answered == 0:
        return GateResult("", (), (), "decider answered no memory: nothing injected", report)
    ordered = order_kept(memories, verdicts)
    kept = [m for m, _ in ordered]
    warnings: list[str] = []
    if check_conflicts and len(kept) > 1:
        drop, warnings = await _conflicts(squire, kept, max_pairs)
        kept = [m for m in kept if m.file not in drop]
        report = {**report, "superseded": sorted(drop)}
    context, shown, listed = render(kept, directory=directory, cap=cap, warnings=warnings)
    report = {**report, "kept": len(kept), "chars": len(context)}
    reason = f"{len(shown)} shown, {len(listed)} listed of {len(memories)}"
    return GateResult(context, shown, listed, reason, report)


async def handle_user_prompt(
    event: Mapping[str, Any],
    squire: Squire,
    *,
    memory_dir: Path | None = None,
    cap: int = CAP,
    check_conflicts: bool = False,
) -> dict[str, Any]:
    """The hook entry: a `UserPromptSubmit` event in, the hook's JSON out. Never raises.

    Returns `{}` (inject nothing) on any failure, with the reason on stderr.
    """
    try:
        prompt = str(event.get("prompt") or "")
        directory = memory_dir if memory_dir is not None else memory_dir_for(event)
        if directory is None:
            return _quiet("no memory directory for this session")
        memories = load_memories(directory)
        result = await gate(
            squire,
            prompt,
            memories,
            directory=str(directory),
            cap=cap,
            check_conflicts=check_conflicts,
        )
    except Exception as error:  # fail open at the hook boundary
        return _quiet(f"memory gate failed open: {error.__class__.__name__}: {error}")
    if not result.context:
        return _quiet(result.reason)
    return hook_output(result.context)


def _quiet(reason: str) -> dict[str, Any]:
    with contextlib.suppress(Exception):  # stderr gone is no reason to break a prompt
        sys.stderr.write(f"sanchopanza memory gate: {reason}\n")
    return {}


# --- the hybrid store: memory files and the archive ---------------------------------------

K = 5  # Amendment 2: BM25 candidates judged in one in-context call
STORE_HEADER = (
    "sanchopanza recall: saved memories and archived tool output of this project that look "
    "relevant to what you are doing now (memory directory {dir}). Each is headed by its file; "
    "Read the file for the full text."
)


def memory_from_entry(entry: Any, query: str) -> Memory:
    """An archived tool result as a store item: its passage that best matches the query."""
    body = redact_secrets(excerpt(entry.text, query, BODY_LIMIT))
    return Memory(
        file=str(entry.path),
        name=redact_secrets(entry.title),
        description="archived tool output",
        body=body,
        mtime=entry.mtime,
        kind="archive",
        search=f"{entry.title} {entry.text}",
    )


def store_of(memories: Sequence[Memory], entries: Sequence[Any], query: str) -> tuple[Memory, ...]:
    """Memory files first, then archive entries, as one list of `Memory`."""
    return (*memories, *(memory_from_entry(e, query) for e in entries))


def bm25_candidates(query: str, store: Sequence[Memory], k: int = K) -> list[int]:
    """Indexes of the top-`k` entries by BM25 over name, description and body, score > 0."""
    if not store or k <= 0:
        return []
    index = BM25Index([m.search or f"{m.name} {m.text}" for m in store])
    return [i for i, _ in index.top(query, k)]


async def recall(
    squire: Squire,
    query: str,
    store: Sequence[Memory],
    *,
    k: int = K,
    directory: str = "",
    cap: int = CAP,
    ask_recall: bool = True,
    exclude: Iterable[str] = (),
) -> GateResult:
    """BM25 top-`k` over the store, one in-context triage, render what contributes.

    `ask_recall` first asks `needs_recall` (skips on a confident "self-contained"). `exclude`
    names files already injected in this context, which are not proposed again. Raises only on
    a bug; the hook entries wrap it.
    """
    query = redact_secrets(query.strip())
    skip = set(exclude)
    pool = [m for m in store if m.file not in skip]
    base = {"store": len(store), "pool": len(pool), "query_chars": len(query)}
    if len(query) < PROMPT_MIN:
        return GateResult("", (), (), "query too short to judge", base)
    candidates = [pool[i] for i in bm25_candidates(query, pool, k)]
    report = {**base, "candidates": [m.file for m in candidates]}
    if not candidates:
        return GateResult("", (), (), "no candidate shares a word with the query", report)
    if ask_recall:
        verdict = await squire.needs_recall(query, topics=topics_of(candidates))
        report = {**report, "recall_p": verdict.probability}
        if not verdict.look:
            return GateResult("", (), (), f"no recall needed: {verdict.reason}", report)
    verdicts = await squire.triage_pages(purpose=query, pages=pages_of(candidates, query))
    answered = sum(p is not None for _, p in verdicts)
    probabilities = {m.file: p for m, (_, p) in zip(candidates, verdicts, strict=True)}
    report = {**report, "answered": answered, "probabilities": probabilities}
    if answered == 0:
        return GateResult("", (), (), "decider answered no candidate: nothing injected", report)
    kept = [m for m, _ in order_kept(candidates, verdicts)]
    context, shown, listed = render(kept, directory=directory, cap=cap, header=STORE_HEADER)
    reason = f"{len(shown)} shown, {len(listed)} listed of {len(candidates)} candidates"
    return GateResult(context, shown, listed, reason, {**report, "kept": len(kept)})
