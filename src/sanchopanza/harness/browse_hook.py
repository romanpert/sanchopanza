"""Browse lean: a Claude Code `PostToolUse` hook that prunes browser snapshots on arrival.

An agent browsing reads the page's whole accessibility snapshot, and pays for it again on every
later turn. It arrives three ways (checked 2026-09-30 with Playwright MCP 0.0.83 and
`@playwright/cli` 0.1.18): inline in an MCP tool result, on `Bash` stdout from
`playwright-cli snapshot` (or agent-browser), or as a `.yml` file that `playwright-cli goto` and
Playwright MCP write by default and the agent then `Read`s. Wherever it is found
(`browse.snapshot_block`), this hook replaces a large one with the same YAML pruned
(`browse.prune_snapshot`): the elements `browse.rank` puts first for the task, every heading, the
text lines that bear on the task, and each kept line's ancestors, so the refs still work and
the tree still reads as the page. Everything outside the YAML block (the code Playwright ran,
the URL, the title, console messages) passes as it was. The full result goes to the archive and
the reply says where, so `search_archive`, `Read`, or a new snapshot recovers anything cut.

Opt-in. In `.claude/settings.json`:

    {"hooks": {"PostToolUse": [{"matcher": "Bash|Read|mcp__playwright__.*|mcp__plugin_playwright.*",
      "hooks": [{"type": "command", "command": "python -m sanchopanza.harness.browse_hook"}]}]}}

Environment (`SANCHOPANZA_<NAME>`): BROWSE_CHARS (snapshot size that triggers a cut, default
6000), BROWSE_KEEP (elements kept, default 20), BROWSE_TEXT (characters of text lines kept,
default 3000), BROWSE_MAX_ELEMENTS (past this many, BM25 shortlists what the decider ranks,
default 600), SESSION_MAX_USD (the autopilot's per-session ceiling, shared), and the usual
provider settings. Without a provider the ranking is BM25 (free). Fail open everywhere.

Measured (`docs/results/2026-09-30-browse/`, Phase 3): in 36 real Claude Code sessions browsing
with `playwright-cli`, it answered as often and **saved nothing** (+0.0095 USD a session,
[-0.006, +0.027]): it acted in 8 of 18, because playwright-cli's snapshots are already moderate
and the agent used `find` and `eval`. It paid on the one large snapshot. With Playwright MCP
(Phase 3b, 48 sessions) it saved nothing either, for three faults since fixed: Claude Code
replaces an MCP result past its token limit with a notice before any `PostToolUse` hook runs, so
the hook now reads the saved result behind the notice (only from its own session's
`tool-results` folder) and returns it pruned; the agent's own `find` results pass untouched; and
the goal is `browse_goal`, which keeps the question at the end of a request. Phase 3c found
two more (a `Read` with a limit and a targeted snapshot were cut; recovery read the whole
archive), fixed too. **Phase 3d, registered, six new tasks: 12.9 % cheaper with Playwright
MCP, -0.0144 USD a session [-0.0270, -0.0025], no answer lost.** Recommended with Playwright
MCP. With playwright-cli (Phase 3e, same tasks): -0.0094 USD a session [-0.0184, -0.0036],
rule met, though it cut on two of the six tasks and part of that saving is noise.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .. import _env

DEFAULT_CHARS = 6000
DEFAULT_KEEP = 20
DEFAULT_TEXT = 3000
DEFAULT_MAX_ELEMENTS = 600
SAVED_MAX_BYTES = 20_000_000
# What may replace Claude Code's notice. Its limit is 25,000 tokens by default, and the GitHub
# page it refused was 72,000 characters; past this the notice stays (review 2026-10-01).
OVERSIZE_RETURN_MAX = 60_000
# Claude Code's notice when an MCP result passes its token limit. The hook is handed this
# notice, never the result (probed 2026-09-30 with a recording hook and Playwright MCP 0.0.83).
_OVERSIZE = re.compile(
    r"^Error: result \([^)]*\) exceeds maximum allowed tokens\. "
    r"Output has been saved to (?P<path>.+?\.txt)\.\s*$",
    re.M,
)
# The CLI's `find` subcommand, after any flags; not the word inside a URL (`goto .../find-a-store`).
_CLI_FIND = re.compile(r"\b(?:playwright-cli|agent-browser)(?:\s+-\S+)*\s+find\b")


def _int(name: str, default: int) -> int:
    try:
        return max(0, int(_env.get(name, str(default))))
    except ValueError:
        return default


def _reads_the_archive(event: Mapping[str, Any], root: Any) -> bool:
    """A `Read` of a file under the archive root: the agent asking for what was cut."""
    from pathlib import Path

    if str(event.get("tool_name", "")) != "Read":
        return False
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), Mapping) else {}
    target = str(tool_input.get("file_path") or "")
    if not target:
        return False
    try:
        return Path(target).resolve().is_relative_to(Path(root).resolve())
    except (OSError, ValueError):
        return False


_NARROWING = frozenset({"target", "ref", "selector", "element", "depth"})


def _is_search(tool: str, tool_input: Mapping[str, Any]) -> bool:
    """What the agent narrowed itself: `browser_find` or a browser CLI's `find` (pruning its
    answer sent the agent to the whole archive in 3 of 4 cases, Phase 3b), a `Read` of part of a
    file, and a snapshot of one element or depth (both cut in Phase 3c's M4, and the agent went
    looking for what the cut removed)."""
    if tool.endswith("browser_find"):
        return True
    if tool == "Read":
        return any(tool_input.get(k) not in (None, "") for k in ("offset", "limit"))
    if tool.endswith("browser_snapshot"):
        return any(tool_input.get(k) not in (None, "") for k in _NARROWING)
    return tool == "Bash" and bool(_CLI_FIND.search(str(tool_input.get("command") or "")))


_URL = re.compile(r"https?://([^/\s?#]+)\S*")
GOAL_LIMIT = 400  # what `points.browse` shows of the goal
STEP_LIMIT = 90
FOLLOW_UP_LIMIT = 110


def browse_goal(messages: Any) -> str:
    """What the ranking is for: the request, the latest one if it changed, and the agent's last
    stated step. Not `purpose_of`, which the arrival cut shares and was measured with: it keeps
    the first 130 characters of the request, and a request that opens with a URL and
    instructions ends with its question (a 2026-09-30 probe lost "which license" that way).
    URLs are cut to their host; a long request keeps its start and its end. The follow-up and
    the step are sized first and the request takes what is left, so no part falls off the end
    (review 2026-10-01: a long request and a follow-up used to push the step out)."""
    from ..context.transcript import is_prompt, message_text
    from ..points.context import head_tail
    from ..text import truncate

    def clean(text: str) -> str:
        return " ".join(_URL.sub(r"\1", text).split())

    def fit(text: str, limit: int) -> str:
        # head_tail adds a marker of about 30 characters to what it keeps
        return text if len(text) <= limit else head_tail(text, max(40, limit - 32))

    prompts = [clean(message_text(m)) for m in messages if is_prompt(m)]
    intent = next(
        (message_text(m) for m in reversed(messages)
         if m.get("role") == "assistant" and message_text(m)),
        "",
    )  # fmt: skip
    if not prompts:
        return ""
    tail = []
    if len(prompts) > 1 and prompts[-1] != prompts[0]:
        tail.append(f"Now asked: {fit(prompts[-1], FOLLOW_UP_LIMIT)}")
    if intent:
        tail.append(f"Agent's step: {truncate(clean(intent), STEP_LIMIT)}")
    room = GOAL_LIMIT - len("Task: ") - sum(len(t) + 1 for t in tail)
    return "\n".join([f"Task: {fit(prompts[0], room)}", *tail])


def _oversized(text: str, event: Mapping[str, Any]) -> str | None:
    """The saved result behind Claude Code's too-large notice, or None.

    Read only from this session's own `tool-results` folder, next to its transcript: the notice
    is text, and a page can print one naming any file."""
    match = _OVERSIZE.match(text.strip())
    transcript = str(event.get("transcript_path") or "")
    if match is None or not transcript:
        return None
    allowed = Path(transcript).with_suffix("") / "tool-results"
    try:
        saved = Path(match["path"]).resolve()
        if not saved.is_relative_to(allowed.resolve()) or not saved.is_file():
            return None
        if saved.stat().st_size > SAVED_MAX_BYTES:
            return None
        return saved.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return None


def say(text: str) -> None:
    with contextlib.suppress(Exception):
        sys.stderr.write(f"sanchopanza browse: {text}\n")


async def post_tool_use(event: Mapping[str, Any], squire: Any) -> dict[str, Any]:
    """The hook body. `{}` means untouched."""
    from ..browse import elements_from_snapshot, prune_snapshot, rank, snapshot_block
    from ..context import archive as archive_mod
    from . import autopilot

    response = event.get("tool_response")
    found = autopilot.text_field(response)
    if found is None:
        return {}
    path, text = found
    tool = str(event.get("tool_name", ""))
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), Mapping) else {}
    if _is_search(tool, tool_input):
        return {}
    # Only an MCP result is ever replaced by Claude Code's notice; a `cat` or `curl` of a page
    # that prints one must not pull another file in (review 2026-10-01).
    saved_text = _oversized(text, event) if tool.startswith("mcp__") else None
    if saved_text is not None:  # the result itself replaces the notice, pruned, in its place
        text = saved_text
    span = snapshot_block(text)
    if span is None or span[1] - span[0] < _int("BROWSE_CHARS", DEFAULT_CHARS):
        return {}
    config = autopilot.config_from_env()
    root, session = autopilot._root(event, config), autopilot._session(event)
    if _reads_the_archive(event, root):
        return {}  # the way back to a full snapshot: never pruned again
    ledger = autopilot.read_ledger(root, session)
    body = text[span[0] : span[1]]
    elements = elements_from_snapshot(body)
    if not elements:
        return {}
    purpose = browse_goal(autopilot._messages(event))
    if not purpose:
        return {}  # nothing to rank for: cutting blind could drop what the agent needs
    over = autopilot._over_ceiling(ledger, config)
    # Phase 3f (W4, W7): ranking every one of 2,000-3,000 elements cost Jev more than the cut
    # saved; past this many, BM25 shortlists what the decider sees (about 21 calls at most).
    most = _int("BROWSE_MAX_ELEMENTS", DEFAULT_MAX_ELEMENTS)
    ranked = await rank(
        purpose,
        elements,
        squire=None if over else squire,
        keep=_int("BROWSE_KEEP", DEFAULT_KEEP),
        shortlist=most if most and len(elements) > most else None,
    )
    pruned, left_out = prune_snapshot(
        body,
        [r.element.key for r in ranked],
        purpose=purpose,
        text_budget=_int("BROWSE_TEXT", DEFAULT_TEXT),
    )
    if len(pruned) >= 0.8 * len(body):
        return {}
    new_text_chars = len(text) - len(body) + len(pruned)
    if saved_text is not None and new_text_chars > OVERSIZE_RETURN_MAX:
        return {}  # still past Claude Code's limit: its notice and saved file stay
    meta = {"tool": tool, "about": f"{tool} snapshot", "by": "browse"}
    saved = archive_mod.write_entry(
        archive_mod.session_dir(root, session),
        f"browse-{event.get('tool_use_id') or tool}",
        text,
        meta,
    )
    note = (
        f"# sanchopanza kept {len(ranked)} of {len(elements)} elements and {left_out} snapshot "
        f"lines were left out. If what you need is not here, Grep {saved} for it (never "
        "pruned; Read it whole only if a search will not do).\n"
    )
    squire.journal.record(
        "browse",
        {
            "tool": tool,
            "elements": len(elements),
            "kept": len(ranked),
            "chars": len(body),
            "kept_chars": len(pruned),
            "ranked_by": "bm25" if over else squire.provider,
        },
    )
    with contextlib.suppress(OSError):
        autopilot.write_ledger(root, session, autopilot._charged(ledger, squire))
    new_text = text[: span[0]] + note + pruned + text[span[1] :]
    updated = autopilot.replaced(response, path, new_text)
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedToolOutput": updated}}


def main(argv: list[str] | None = None) -> int:
    # Bytes, decoded as UTF-8: Claude Code writes UTF-8, and on Windows `sys.stdin` decodes with
    # the console's code page, which turned playwright-cli's box-drawing banner into surrogates
    # and made every write of the event fail (Phase 3 pilot, 2026-09-30).
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return 0
    if not isinstance(event, dict) or event.get("hook_event_name") != "PostToolUse":
        return 0
    try:
        from .claude_code import squire_from_env

        output = asyncio.run(post_tool_use(event, squire_from_env(redact=True)))
    except Exception as error:  # fail open at the process boundary, never silently
        say(f"passed through unchanged ({error.__class__.__name__}: {error})")
        return 0
    if output:
        sys.stdout.buffer.write(json.dumps(output, ensure_ascii=False).encode("utf-8"))
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
