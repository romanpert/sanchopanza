"""Passages on arrival: a Claude Code hook on Bash, PowerShell and Read in coding sessions.
Bet A of `docs/PLAN-GANAR-H2H.md`; the cut itself is `context.passages`.

`PostToolUse`: a shell output or a `Read` past `SANCHOPANZA_PASSAGES_TOKENS` tokens (default
2,000, about 4,400 characters) is replaced, through `updatedToolOutput`, by about
`SANCHOPANZA_PASSAGES_FRACTION` of it (default 0.25; the second arm 0.10): the blocks that bear
on the agent's current step and every failure line of a test, lint, type-check or build log.
The whole text goes to the archive (`.sanchopanza/archive/<session>/passages-<id>.txt`, entries
older than 7 days pruned) and a header says where it is and how to get the rest back. Nothing
already in the context changes, so no cached prefix is touched. Built on `browse_hook`
(`_persisted`, `browse_goal`, reply shape, session ceiling) and `autopilot` (text field, archive
root, ledger), not beside them.

A cut `Read` keeps Read's own shape and every line where it was. Seen in the pinned Claude Code
2.1.287 (`grep -a` on its binary): a rewrite is checked with the tool's `outputSchema.safeParse`
(for a text Read: `file` with `filePath`, `content`, `numLines`, `startLine`, `totalLines` and an
optional `truncatedByTokenCap`) and then drawn by `mapToolResultToToolResultBlockParam`, which
numbers `content` from `startLine` straight through; `numLines` and `totalLines` are only read
when `content` is empty. So omitted lines become empty lines (`passages.render_in_place`), the
numbers beside kept lines stay the file's, `numLines` stays the count returned, and the header
goes on the last omitted line, never first. It says the view is partial: `passages_guard`
denies a `Write` from it until the rest has been read.

The goal: `browse_goal` over the transcript (the request, the latest one if it changed, the
agent's last words) and the call (a Bash `description` and command, a Read's path). A subagent's
call reads the subagent's own transcript (`<session>/subagents/agent-<id>.jsonl`).

What is never cut is in `passages_gates` (narrowed Reads, recovery, diffs, snapshots, files
edited or about to be), plus a whole re-request of a recent cut (`passages_state`), a cut that
saves under 20 %, and a decider that answered nothing or missed `DECIDE_TIMEOUT_S`. Each is
journaled as `acted: false` with the reason when the output is past the threshold.

Ranking: with a provider, the paragraph tournament (`Squire.triage_many`, the first stage of
`select_passages`); with none, or past `SANCHOPANZA_SESSION_MAX_USD` or with a ledger that cannot
be read, BM25 (free). A provider that answers nothing passes the output whole: falling back to
BM25 there would measure another arm.

A `Bash` output past 30,000 characters is one Claude Code saved to a file; it shows the model
2,000 characters of whatever the hook returns. There the whole output is ranked, the cut goes
to a file of its own, and the reply is a preview: header, failure lines first, ranked lines.

Journal: a `passages` event per decision (tool, kind, `chars_in`, `chars_out`, `injected_chars`,
`acted`, `reason`, `ranked_by`) and `passages_rerequest` for a later call that asks again.
Fail open everywhere. Not measured yet. Opt-in: `sanchopanza install --passages`.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .. import _env
from ..context import passages as ps
from . import autopilot, browse_hook
from . import passages_gates as gates
from . import passages_state as state_mod
from .passages_guard import pre_tool_use as pre_tool_use

SHELL_TOOLS = state_mod.SHELL_TOOLS
TOOLS = SHELL_TOOLS | {"Read"}
REREQUEST_WINDOW = state_mod.WINDOW
CALL_LIMIT = 160
QUERY_STEP = 1_000
DECIDE_TIMEOUT_S = 15.0
ARCHIVE_DAYS = 7
READ_HEADER = (
    "[sanchopanza cut this Read on arrival to what bears on the current step: {kept} of {total} "
    "chars; partial view: do not rewrite this file with Write from here; read the rest first. "
    "Every line is in its place: an empty line may be one left out, and each marker names the "
    "lines it stands for and the Read (offset and limit) that shows them (a plain Read of the "
    "file again answers that it is unchanged). The whole text: {archive}.]"
)
SHELL_HEADER = (
    "[sanchopanza cut this output on arrival to what bears on the current step: {kept} of "
    "{total} chars; failure lines and the summary are always kept, and markers give the "
    "output's own line numbers. The whole output: {archive} (Grep it, or Read it with offset "
    "and limit).]\n"
)
PREVIEW_HEADER = (
    "[sanchopanza: this output ({total} chars) is too large to show here. Below are its failure "
    "lines and the lines most likely needed. The cut ({kept} chars): Read {cut}. The whole "
    "output: {archive} (Grep it, or Read with offset and limit).]\n"
)


def settings_from_env() -> ps.Settings:
    """`PASSAGES_TOKENS`, `PASSAGES_FRACTION` (0 to 1, exclusive) and `PASSAGES_MIN_SAVING`;
    a bad value falls back to its default."""

    def number(name: str, default: float, low: float, high: float) -> float:
        try:
            value = float(_env.get(name, "") or default)
        except ValueError:
            return default
        return value if low < value < high else default

    return ps.Settings(
        tokens=int(number("PASSAGES_TOKENS", ps.DEFAULT_TOKENS, 0, 10**7)),
        fraction=number("PASSAGES_FRACTION", ps.DEFAULT_FRACTION, 0, 1),
        min_saving=number("PASSAGES_MIN_SAVING", ps.DEFAULT_MIN_SAVING, 0, 1),
    )


def say(text: str) -> None:
    try:
        sys.stderr.write(f"sanchopanza passages: {text}\n")
    except Exception:  # noqa: BLE001 - stderr gone: nothing left to tell
        return


def _input(event: Mapping[str, Any]) -> Mapping[str, Any]:
    value = event.get("tool_input")
    return value if isinstance(value, Mapping) else {}


def _text(tool: str, response: Any) -> tuple[tuple, str] | None:
    """The content field: a Read's `file.content` (text files only), a command's `stdout`."""
    found = autopilot.text_field(response)
    if found is None:
        return None
    path, text = found
    if tool == "Read":
        is_text = isinstance(response, Mapping) and response.get("type") == "text"
        return found if is_text and path == ("file", "content") else None
    return found if path and path[-1] == "stdout" else None


def subagent_transcript(event: Mapping[str, Any]) -> Path | None:
    """`<session>/subagents/agent-<id>.jsonl`, the id made a safe file name first."""
    from ..context.archive import safe_name

    agent, transcript = str(event.get("agent_id") or ""), str(event.get("transcript_path") or "")
    if not agent or not transcript:
        return None
    return Path(transcript).with_suffix("") / "subagents" / f"agent-{safe_name(agent)}.jsonl"


def _messages(event: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The conversation the call belongs to: a subagent's own transcript when it is one."""
    from ..context.transcript import messages_from_claude_code

    own = subagent_transcript(event)
    try:
        if own is not None and own.is_file():
            return messages_from_claude_code(own, sidechain=True)
    except (OSError, ValueError):
        pass
    return autopilot._messages(event)


def _call(tool: str, tool_input: Mapping[str, Any]) -> str:
    if tool == "Read":
        return f"Read {tool_input.get('file_path') or ''}"
    parts = [str(tool_input.get(k) or "") for k in ("description", "command")]
    return f"{tool}: " + " | ".join(p for p in parts if p)


def goal(messages: Sequence[Mapping[str, Any]], tool: str,
         tool_input: Mapping[str, Any]) -> tuple[str, str]:  # fmt: skip
    """(the purpose the decider reads, at most 400 characters; the wider BM25 query)."""
    from ..text import truncate

    call = truncate(_call(tool, tool_input), CALL_LIMIT)
    base = browse_hook.browse_goal(messages)
    room = browse_hook.GOAL_LIMIT - len(call) - len("\nThis call: ")
    purpose = "\n".join(p for p in (truncate(base, max(40, room)) if base else "",
                                    f"This call: {call}") if p)  # fmt: skip
    step = truncate(gates.last_words(messages), QUERY_STEP)
    pattern = str(tool_input.get("pattern") or "")
    return purpose, " ".join(p for p in (purpose, step, pattern) if p)


async def _order(text: str, lay: ps.Layout, purpose: str, query: str, squire: Any,
                 *, over: bool, label: str) -> tuple[list[int] | None, str, str]:  # fmt: skip
    """(units best first or None, who ranked them, why there is no order)."""
    import asyncio

    from ..redact import redact_secrets

    if squire.provider == "null":
        return ps.bm25_order(text, lay, query), "bm25", ""
    if over:
        return ps.bm25_order(text, lay, query), "bm25 (session ceiling)", ""
    pages = []
    for unit, (a, b) in enumerate(lay.units):
        lines = f"lines {lay.atoms[a].first_line}-{lay.atoms[b - 1].last_line}"
        pages.append((f"{label} {lines}", redact_secrets(ps.unit_text(text, lay, unit))))
    try:
        verdicts = await asyncio.wait_for(squire.triage_many(purpose=purpose, pages=pages),
                                          DECIDE_TIMEOUT_S)  # fmt: skip
    except TimeoutError:
        return None, squire.provider, f"the decider missed its {DECIDE_TIMEOUT_S:g} s deadline"
    probabilities = [p for _, p in verdicts]
    if all(p is None for p in probabilities):
        return None, squire.provider, "the decider gave no answer: passed whole"
    return ps.probability_order(probabilities), squire.provider, ""


def _record(squire: Any, tool: str, event: Mapping[str, Any], **data: Any) -> None:
    base = {"tool": tool, "tool_use_id": event.get("tool_use_id")}
    squire.journal.record("passages", {**base, "subagent": bool(event.get("agent_id")), **data})


def _passed(squire: Any, tool: str, event: Mapping[str, Any], text: str, reason: str,
            *, persisted: bool, kind: str = "") -> dict:  # fmt: skip
    shown = min(len(text), browse_hook.PREVIEW_CHARS) if persisted else len(text)
    _record(squire, tool, event, kind=kind, acted=False, reason=reason, chars_in=len(text),
            chars_out=len(text), injected_chars=shown, persisted=persisted)  # fmt: skip
    return {}


def _watch(squire: Any, root: Path, session: str, event: Mapping[str, Any],
           text: str) -> tuple[dict[str, Any], bool]:  # fmt: skip
    """Count this call toward the window of recent cuts, journal any re-request, and note what
    a `Read` showed of a file seen cut; (the state, whether this call asks again for a cut)."""
    tool, tool_input = str(event.get("tool_name", "")), _input(event)
    use_id = str(event.get("tool_use_id") or tool)
    before = state_mod.read(root, session)
    sha = state_mod.digest(text) if text else ""
    state, again, whole_again = state_mod.note_call(before, tool, tool_input, use_id, sha)
    for item in again:
        squire.journal.record("passages_rerequest", item)
    response = event.get("tool_response")
    file = response.get("file") if isinstance(response, Mapping) else None
    if tool == "Read" and isinstance(file, Mapping) and isinstance(file.get("startLine"), int):
        first = int(file["startLine"])
        shown = len(str(file.get("content") or "").splitlines())
        state = state_mod.see(state, str(tool_input.get("file_path") or ""), first,
                              first + shown - 1)  # fmt: skip
    if state != before:
        state_mod.write(root, session, state)
    return state, whole_again


async def post_tool_use(event: Mapping[str, Any], squire: Any) -> dict[str, Any]:
    """The hook body. `{}` means untouched."""
    tool = str(event.get("tool_name", ""))
    if tool not in TOOLS:
        return {}
    tool_input, response = _input(event), event.get("tool_response")
    config = autopilot.config_from_env()
    root, session = autopilot._root(event, config), autopilot._session(event)
    found = _text(tool, response)
    persisted, whole = browse_hook._persisted(response, event)
    text = whole if persisted and whole is not None else found[1] if found else ""
    state, whole_again = _watch(squire, root, session, event, text)
    if found is None or (persisted and whole is None):
        return {}  # nothing to cut, or only a prefix: never rank or archive a fragment
    settings = settings_from_env()
    if len(text) < settings.threshold_chars:
        return {}
    why = "a whole re-request of a recent cut" if whole_again else gates.why_not(
        event, tool, text, root)  # fmt: skip
    if why:
        return _passed(squire, tool, event, text, why, persisted=persisted)
    messages = _messages(event)
    why = gates.edits(messages, tool, tool_input, str(event.get("cwd") or ""))
    if why:
        return _passed(squire, tool, event, text, why, persisted=persisted)
    kind = ps.kind_of(tool, tool_input, text)
    lay = ps.layout(text, kind, ps.budget_for(text, settings))
    if len(lay.units) < 2:
        return _passed(squire, tool, event, text, "one block", persisted=persisted, kind=kind)
    ledger = autopilot.read_ledger(root, session)
    order, ranked_by, why = await _order(text, lay, *goal(messages, tool, tool_input), squire,
                                         over=autopilot._over_ceiling(ledger, config),
                                         label=_call(tool, tool_input)[:80])  # fmt: skip
    if squire.meter.decisions:
        try:
            autopilot.write_ledger(root, session, autopilot._charged(ledger, squire))
        except OSError:
            say("could not write the session ledger")
    if order is None:
        return _passed(squire, tool, event, text, why, persisted=persisted, kind=kind)
    cut = ps.cut_ordered(text, lay, order, settings, in_place=tool == "Read")
    if cut.text is None:
        return _passed(squire, tool, event, text, cut.reason, persisted=persisted, kind=kind)
    new_text, saved = _write(event, tool, root, session, text, cut, lay, order, persisted)
    _remember(root, session, state, event, text, cut, lay, saved)
    _record(squire, tool, event, kind=kind, acted=True, reason=cut.reason, ranked_by=ranked_by,
            fraction=settings.fraction, tokens=settings.tokens, persisted=persisted,
            chars_in=len(text), chars_out=len(cut.text), injected_chars=len(new_text),
            **{k: cut.report[k] for k in ("units", "kept_units", "must_lines", "rendered_in",
                                          "rendered_out")})  # fmt: skip
    updated = autopilot.replaced(response, found[0], new_text)
    if tool == "Read":  # numLines: the lines returned, the same count as the file's
        updated = autopilot.replaced(updated, ("file", "numLines"), len(new_text.splitlines()))
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedToolOutput": updated}}


def _remember(root: Path, session: str, state: Mapping[str, Any], event: Mapping[str, Any],
              text: str, cut: ps.Cut, lay: ps.Layout, saved: Path) -> None:  # fmt: skip
    """Record the cut for re-requests, and a file shown cut as a partial view."""
    tool, tool_input = str(event.get("tool_name", "")), _input(event)
    entry = {"id": str(event.get("tool_use_id") or tool), "tool": tool, "archive": str(saved),
             "key": state_mod.call_key(tool, tool_input), "sha": state_mod.digest(text)}
    state = state_mod.remember(state, entry)
    path = str(tool_input.get("file_path") or "") if tool == "Read" else gates.printed_file(
        str(tool_input.get("command") or ""), str(event.get("cwd") or ""))  # fmt: skip
    if path:
        total = len(text.splitlines())
        gaps = [(a + 1, b + 1) for a, b in ps.omitted_runs(text, lay, cut.kept)]
        seen, cursor = [], 1
        for a, b in gaps:
            seen += [(cursor, a - 1)] if a > cursor else []
            cursor = b + 1
        seen += [(cursor, total)] if cursor <= total else []
        state = state_mod.mark_partial(state, path, total, seen)
    state_mod.write(root, session, state)


def _prune(root: Path) -> None:
    """Our archive entries older than `ARCHIVE_DAYS`, in every session folder, removed."""
    limit = time.time() - ARCHIVE_DAYS * 86_400
    for path in root.glob("*/passages-*"):
        try:
            if path.stat().st_mtime < limit:
                path.unlink()
        except OSError:
            continue


def _write(event: Mapping[str, Any], tool: str, root: Path, session: str, text: str,
           cut: ps.Cut, lay: ps.Layout, order: Sequence[int],
           persisted: bool) -> tuple[str, Path]:  # fmt: skip
    """Archive the whole text (and, for a saved output, the cut); the text the agent gets."""
    from ..context import archive as archive_mod
    from ..redact import redact_secrets

    _prune(root)
    folder = archive_mod.session_dir(root, session)
    name = f"passages-{event.get('tool_use_id') or tool}"
    about = redact_secrets(_call(tool, _input(event)))[:160]
    meta = {"tool": tool, "about": about, "by": "passages"}
    saved = archive_mod.write_entry(folder, name, text, meta)
    body = cut.text or ""
    if tool == "Read":
        header = READ_HEADER.format(kept=len(body), total=len(text), archive=saved)
        return ps.render_in_place(text, lay, cut.kept, header=header), saved
    if not persisted:
        return SHELL_HEADER.format(kept=len(body), total=len(text), archive=saved) + body, saved
    cut_file = archive_mod.write_entry(folder, f"{name}-cut", body, {**meta, "about": "cut"})
    header = PREVIEW_HEADER.format(total=len(text), kept=len(body), cut=cut_file, archive=saved)
    return header + ps.fit(text, lay, order, browse_hook.PREVIEW_CHARS - len(header)), saved


def wants(event: Mapping[str, Any]) -> bool:
    """Pure and cheap, before asyncio or a squire: can this call be cut, count toward the
    re-request window of a recent cut, or show part of a file seen cut?"""
    tool = str(event.get("tool_name", ""))
    if tool not in TOOLS:
        return False
    response = event.get("tool_response")
    if isinstance(response, Mapping) and response.get("persistedOutputPath"):
        return True
    found = _text(tool, response)
    if found is not None and len(found[1]) >= settings_from_env().threshold_chars:
        return True
    root = autopilot._root(event, autopilot.config_from_env())
    state = state_mod.read(root, autopilot._session(event))
    if state_mod.watching(state):
        return True
    target = str(_input(event).get("file_path") or "")
    return tool == "Read" and bool(target) and bool(state_mod.unseen(state, target))


def main(argv: list[str] | None = None) -> int:
    # Bytes, decoded as UTF-8: on Windows `sys.stdin` decodes with the console's code page.
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return 0
    kind = event.get("hook_event_name") if isinstance(event, dict) else None
    output: dict[str, Any] = {}
    try:
        if kind == "PreToolUse":
            output = pre_tool_use(event)
        elif kind == "PostToolUse" and wants(event):
            import asyncio

            from .claude_code import squire_from_env

            output = asyncio.run(post_tool_use(event, squire_from_env(redact=True)))
    except Exception as error:  # noqa: BLE001 - fail open at the process boundary, never silently
        say(f"passed through unchanged ({error.__class__.__name__}: {error})")
        return 0
    if output:
        sys.stdout.buffer.write(json.dumps(output, ensure_ascii=False).encode("utf-8"))
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
