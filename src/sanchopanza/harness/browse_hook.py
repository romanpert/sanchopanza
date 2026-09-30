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
default 3000), SESSION_MAX_USD (the autopilot's per-session ceiling, shared), and the usual
provider settings. Without a provider the ranking is BM25 (free). Fail open everywhere.

Measured (`docs/results/2026-09-30-browse/`, Phase 3): in 36 real Claude Code sessions browsing
with `playwright-cli`, it answered as often and **saved nothing** (+0.0095 USD a session,
[-0.006, +0.027]): it acted in 8 of 18, because playwright-cli's snapshots are already moderate
and the agent used `find` and `eval`. It paid on the one large snapshot. Opt-in, no
recommendation: turn it on where agents read large snapshots (Playwright MCP's files).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from collections.abc import Mapping
from typing import Any

from .. import _env

DEFAULT_CHARS = 6000
DEFAULT_KEEP = 20
DEFAULT_TEXT = 3000


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


def say(text: str) -> None:
    with contextlib.suppress(Exception):
        sys.stderr.write(f"sanchopanza browse: {text}\n")


async def post_tool_use(event: Mapping[str, Any], squire: Any) -> dict[str, Any]:
    """The hook body. `{}` means untouched."""
    from ..browse import elements_from_snapshot, prune_snapshot, rank, snapshot_block
    from ..context import archive as archive_mod
    from ..context.arrival import purpose_of
    from . import autopilot

    response = event.get("tool_response")
    found = autopilot.text_field(response)
    if found is None:
        return {}
    path, text = found
    span = snapshot_block(text)
    if span is None or span[1] - span[0] < _int("BROWSE_CHARS", DEFAULT_CHARS):
        return {}
    config = autopilot.config_from_env()
    root, session = autopilot._root(event, config), autopilot._session(event)
    if _reads_the_archive(event, root):
        return {}  # the way back to a full snapshot: never pruned again
    ledger = autopilot.read_ledger(root, session)
    tool = str(event.get("tool_name", ""))
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), Mapping) else {}
    body = text[span[0] : span[1]]
    elements = elements_from_snapshot(body)
    if not elements:
        return {}
    over = autopilot._over_ceiling(ledger, config)
    purpose = purpose_of(autopilot._messages(event), tool, tool_input)
    ranked = await rank(
        purpose,
        elements,
        squire=None if over else squire,
        keep=_int("BROWSE_KEEP", DEFAULT_KEEP),
    )
    pruned, left_out = prune_snapshot(
        body,
        [r.element.key for r in ranked],
        purpose=purpose,
        text_budget=_int("BROWSE_TEXT", DEFAULT_TEXT),
    )
    if len(pruned) >= 0.8 * len(body):
        return {}
    meta = {"tool": tool, "about": f"{tool} snapshot", "by": "browse"}
    saved = archive_mod.write_entry(
        archive_mod.session_dir(root, session),
        f"browse-{event.get('tool_use_id') or tool}",
        text,
        meta,
    )
    note = (
        f"# sanchopanza kept {len(ranked)} of {len(elements)} elements and {left_out} snapshot "
        f"lines were left out. If what you need is not here, Read {saved} (never pruned).\n"
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
