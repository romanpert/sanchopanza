"""Passages on arrival: a Claude Code `PostToolUse` hook on Bash, PowerShell and Read in coding
sessions. Bet A of `docs/PLAN-GANAR-H2H.md`; the cut itself is `context.passages`.

A shell output or a `Read` past `SANCHOPANZA_PASSAGES_TOKENS` tokens (default 2,000, about 4,400
characters) is replaced, through `updatedToolOutput`, by about `SANCHOPANZA_PASSAGES_FRACTION`
of it (default 0.25; the second arm 0.10): the blocks that bear on the agent's current step, every
failure line of a test log, original line numbers in the markers. The whole text goes to the
archive (`.sanchopanza/archive/<session>/passages-<tool_use_id>.txt`) and a one-line header says
where it is and how to get the rest back. Nothing already in the context changes, so no cached
prefix is touched. Built on `browse_hook` (its `_persisted`, `browse_goal`, reply shape and
session ceiling) and `autopilot` (text field, archive root, ledger), not beside them.

What it is for (the goal): `browse_goal` over the transcript (the request, the latest one if it
changed, the agent's last words before the call) and the call itself (a Bash `description` and
its command, a Read's path). A subagent's call reads the subagent's own transcript
(`<session>/subagents/agent-<id>.jsonl`), so its goal is its task, not the parent's.

What is never cut, journaled as `acted: false` with the reason when it is past the threshold:

- a `Read` the agent narrowed (offset or limit): it already chose;
- a `Read` or command on the archive or on Claude Code's own `tool-results` folder: recovery;
- `git diff`, `git show`, `git log -p`, `diff -u`: a patch is applied or reviewed whole;
- a file the agent edited in this context, or one its last words say it will edit (an edit verb
  and the file's name): it will need the literal text around its change;
- a whole re-request of a recent cut (`passages_state`): cutting it again is the loop that made
  rtk-style compression cost 7.6 % more;
- a browser snapshot printed on stdout: that is `browse_hook`'s;
- a cut that saves under 20 %, and a decider that gave no answer at all.

Ranking: with a provider, the paragraph tournament (`Squire.triage_many`, the first stage of
`select_passages`: 96.5 % of evidence at 3.1 % of the text); its sentence stage is not used,
since a sentence splitter means nothing in code or a log. With no provider, or past
`SANCHOPANZA_SESSION_MAX_USD` (shared with the other hooks), BM25 (free). A provider that
answers nothing passes the output whole: falling back to BM25 there would measure another arm.

A `Bash` output past 30,000 characters is one Claude Code saved to a file; it shows the model
2,000 characters of whatever the hook returns. There the whole output is ranked, the cut goes
to a file of its own, and the reply is a preview: header, failure lines first, ranked lines.

Each decision is a `passages` journal event: tool, kind, `chars_in`, `chars_out` (the cut),
`injected_chars` (what reached the model, header included), `acted`, `reason`, `ranked_by`.
A later call that asks again is `passages_rerequest` (`passages_state`). Fail open everywhere.

Not measured yet. Opt-in: `sanchopanza install --passages [--passages-fraction 0.10]`.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .. import _env
from ..context import passages as ps
from . import autopilot, browse_hook
from . import passages_state as state_mod

SHELL_TOOLS = state_mod.SHELL_TOOLS
TOOLS = SHELL_TOOLS | {"Read"}
REREQUEST_WINDOW = state_mod.WINDOW
CALL_LIMIT = 160
QUERY_STEP = 1_000
DIFF = re.compile(
    r"\bgit\s+(?:-\S+\s+)*(?:diff|show|format-patch|stash\s+show)\b|\bgit\b.*\blog\b.*\s-p\b"
    r"|\bdiff\s+-\w*u|\binterdiff\b"
)
EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
WILL_EDIT = re.compile(
    r"\b(?:edit|fix|chang|modif|updat|patch|rewrit|refactor|replac|implement|editar|cambi"
    r"|arregl|corrig|toc)\w*",
    re.I,
)
READ_HEADER = (
    "[sanchopanza cut this Read on arrival to what bears on the current step: {kept} of {total} "
    "chars. Each marker gives the file's own line numbers for what it left out (the numbers "
    "beside the kept lines count only the lines shown). For omitted lines, Read {path} with "
    "offset and limit (a plain Read of it again answers that it is unchanged); the whole text "
    "is also in {archive}.]\n"
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


def _under(target: str, folder: Path) -> bool:
    try:
        return Path(target).resolve().is_relative_to(folder.resolve())
    except (OSError, ValueError):
        return False


def _recovery_folders(event: Mapping[str, Any], root: Path) -> list[Path]:
    transcript = str(event.get("transcript_path") or "")
    saved = [Path(transcript).with_suffix("") / "tool-results"] if transcript else []
    return [root, *saved]


def _why_not(event: Mapping[str, Any], tool: str, text: str, root: Path) -> str | None:
    """Why a large result passes whole, before the transcript is read; None to go on."""
    tool_input = _input(event)
    folders = _recovery_folders(event, root)
    if tool == "Read":
        if any(tool_input.get(k) not in (None, "") for k in ("offset", "limit")):
            return "a Read the agent narrowed (offset or limit)"
        if any(_under(str(tool_input.get("file_path") or ""), f) for f in folders):
            return "a Read of archived output: recovery"
        return None
    command = str(tool_input.get("command") or "")
    if any(str(f) in command or str(f).replace("\\", "/") in command for f in folders):
        return "a command on archived output: recovery"
    if DIFF.search(command):
        return "a diff: applied or reviewed whole"
    from ..browse import snapshot_block

    if snapshot_block(text) is not None:
        return "a browser snapshot: the browse hook's"
    return None


def _messages(event: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The conversation the call belongs to: a subagent's own transcript when it is one."""
    from ..context.transcript import messages_from_claude_code

    agent, transcript = str(event.get("agent_id") or ""), str(event.get("transcript_path") or "")
    if agent and transcript:
        own = Path(transcript).with_suffix("") / "subagents" / f"agent-{agent}.jsonl"
        try:
            if own.is_file():
                return messages_from_claude_code(own, sidechain=True)
        except (OSError, ValueError):
            pass
    return autopilot._messages(event)


def _last_words(messages: Sequence[Mapping[str, Any]]) -> str:
    from ..context.transcript import message_text

    return next((message_text(m) for m in reversed(messages)
                 if m.get("role") == "assistant" and message_text(m)), "")  # fmt: skip


def _edits(messages: Sequence[Mapping[str, Any]], tool: str, tool_input: Mapping[str, Any]) -> str:
    """Why a Read passes because the agent edited, or says it will edit, the file; else ""."""
    from ..context.transcript import calls

    if tool != "Read":
        return ""
    target = state_mod.path_key(str(tool_input.get("file_path") or ""))
    for call in calls(messages):
        raw = call.input.get("file_path") or call.input.get("notebook_path")
        if call.tool in EDIT_TOOLS and raw and state_mod.path_key(str(raw)) == target:
            return "a file the agent edited in this context"
    name = Path(str(tool_input.get("file_path") or "")).name.lower()
    words = _last_words(messages)
    if name and name in words.lower() and WILL_EDIT.search(words):
        return "a file the agent says it will edit"
    return ""


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
    step = truncate(_last_words(messages), QUERY_STEP)
    pattern = str(tool_input.get("pattern") or "")
    return purpose, " ".join(p for p in (purpose, step, pattern) if p)


async def _order(text: str, lay: ps.Layout, purpose: str, query: str, squire: Any,
                 *, over: bool, label: str) -> tuple[list[int] | None, str]:  # fmt: skip
    """Units best first and who ranked them; None when the decider answered nothing."""
    if squire.provider == "null":
        return ps.bm25_order(text, lay, query), "bm25"
    if over:
        return ps.bm25_order(text, lay, query), "bm25 (session ceiling)"
    from ..redact import redact_secrets

    pages = []
    for unit, (a, b) in enumerate(lay.units):
        lines = f"lines {lay.atoms[a].first_line}-{lay.atoms[b - 1].last_line}"
        pages.append((f"{label} {lines}", redact_secrets(ps.unit_text(text, lay, unit))))
    verdicts = await squire.triage_many(purpose=purpose, pages=pages)
    probabilities = [p for _, p in verdicts]
    if all(p is None for p in probabilities):
        return None, squire.provider
    return ps.probability_order(probabilities), squire.provider


def _record(squire: Any, tool: str, event: Mapping[str, Any], **data: Any) -> None:
    base = {"tool": tool, "tool_use_id": event.get("tool_use_id")}
    squire.journal.record("passages", {**base, "subagent": bool(event.get("agent_id")), **data})


def _passed(squire: Any, tool: str, event: Mapping[str, Any], text: str, reason: str,
            *, persisted: bool, kind: str = "") -> dict:  # fmt: skip
    shown = min(len(text), browse_hook.PREVIEW_CHARS) if persisted else len(text)
    _record(squire, tool, event, kind=kind, acted=False, reason=reason, chars_in=len(text),
            chars_out=len(text), injected_chars=shown, persisted=persisted)  # fmt: skip
    return {}


def _watch(squire: Any, root: Path, session: str, tool: str, tool_input: Mapping[str, Any],
           use_id: str) -> tuple[dict[str, Any], bool]:  # fmt: skip
    """Count this call toward the window of recent cuts and journal any re-request; (the state,
    whether this call asks again for a whole cut)."""
    before = state_mod.read(root, session)
    state, again, whole_again = state_mod.note_call(before, tool, tool_input, use_id)
    for item in again:
        squire.journal.record("passages_rerequest", item)
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
    use_id = str(event.get("tool_use_id") or tool)
    state, whole_again = _watch(squire, root, session, tool, tool_input, use_id)
    found = _text(tool, response)
    if found is None:
        return {}
    path, text = found
    persisted, whole = browse_hook._persisted(response, event)
    if persisted:
        if whole is None:
            return {}  # only a prefix: never rank or archive a fragment
        text = whole
    settings = settings_from_env()
    if len(text) < settings.threshold_chars:
        return {}
    why = "a whole re-request of a recent cut" if whole_again else _why_not(event, tool, text, root)
    if why:
        return _passed(squire, tool, event, text, why, persisted=persisted)
    messages = _messages(event)
    why = _edits(messages, tool, tool_input)
    if why:
        return _passed(squire, tool, event, text, why, persisted=persisted)
    kind = ps.kind_of(tool, tool_input, text)
    purpose, query = goal(messages, tool, tool_input)
    lay = ps.layout(text, kind, ps.budget_for(text, settings))
    if len(lay.units) < 2:
        return _passed(squire, tool, event, text, "one block", persisted=persisted, kind=kind)
    ledger = autopilot.read_ledger(root, session)
    order, ranked_by = await _order(text, lay, purpose, query, squire,
                                    over=autopilot._over_ceiling(ledger, config),
                                    label=_call(tool, tool_input)[:80])  # fmt: skip
    if squire.meter.decisions:
        try:
            autopilot.write_ledger(root, session, autopilot._charged(ledger, squire))
        except OSError:
            say("could not write the session ledger")
    if order is None:
        return _passed(squire, tool, event, text, "the decider gave no answer: passed whole",
                       persisted=persisted, kind=kind)  # fmt: skip
    cut = ps.cut_ordered(text, lay, order, settings)
    if cut.text is None:
        return _passed(squire, tool, event, text, cut.reason, persisted=persisted, kind=kind)
    new_text, saved = _write(event, tool, root, session, text, cut.text, lay, order, persisted)
    state_mod.write(root, session, state_mod.remember(state, {
        "id": use_id, "tool": tool, "key": state_mod.call_key(tool, tool_input),
        "archive": str(saved)}))  # fmt: skip
    _record(squire, tool, event, kind=kind, acted=True, reason=cut.reason, ranked_by=ranked_by,
            fraction=settings.fraction, tokens=settings.tokens, persisted=persisted,
            chars_in=len(text), chars_out=len(cut.text), injected_chars=len(new_text),
            **{k: cut.report[k] for k in ("units", "kept_units", "must_lines")})  # fmt: skip
    updated = autopilot.replaced(response, path, new_text)
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedToolOutput": updated}}


def _write(event: Mapping[str, Any], tool: str, root: Path, session: str, text: str, cut: str,
           lay: ps.Layout, order: Sequence[int], persisted: bool) -> tuple[str, Path]:  # fmt: skip
    """Archive the whole text (and, for a saved output, the cut); the text the agent gets."""
    from ..context import archive as archive_mod

    folder = archive_mod.session_dir(root, session)
    name = f"passages-{event.get('tool_use_id') or tool}"
    meta = {"tool": tool, "about": _call(tool, _input(event))[:160], "by": "passages"}
    saved = archive_mod.write_entry(folder, name, text, meta)
    if not persisted:
        if tool == "Read":
            header = READ_HEADER.format(kept=len(cut), total=len(text), archive=saved,
                                        path=_input(event).get("file_path") or "")  # fmt: skip
        else:
            header = SHELL_HEADER.format(kept=len(cut), total=len(text), archive=saved)
        return header + cut, saved
    cut_file = archive_mod.write_entry(folder, f"{name}-cut", cut, {**meta, "about": "cut"})
    header = PREVIEW_HEADER.format(total=len(text), kept=len(cut), cut=cut_file, archive=saved)
    return header + ps.fit(text, lay, order, browse_hook.PREVIEW_CHARS - len(header)), saved


def wants(event: Mapping[str, Any]) -> bool:
    """Pure and cheap, before asyncio or a squire: can this call be cut, or count toward the
    re-request window of a cut made earlier in the session?"""
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
    return bool(state_mod.read(root, autopilot._session(event)).get("cuts"))


def main(argv: list[str] | None = None) -> int:
    # Bytes, decoded as UTF-8: on Windows `sys.stdin` decodes with the console's code page.
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return 0
    if not isinstance(event, dict) or event.get("hook_event_name") != "PostToolUse":
        return 0
    try:
        if not wants(event):
            return 0
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
