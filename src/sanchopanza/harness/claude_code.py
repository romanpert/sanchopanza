"""Command-line hook for Claude Code (`sanchopanza hook`), and any harness with the same protocol.

Claude Code runs hooks as processes: JSON on stdin, JSON on stdout. In `settings.json`:

    {"hooks": {
      "PreToolUse": [{"matcher": "Agent|WebSearch|Bash",
                      "hooks": [{"type": "command", "command": "sanchopanza hook"}]}],
      "PostToolUse": [{"matcher": "Agent",
                       "hooks": [{"type": "command", "command": "sanchopanza hook"}]}]}}

Configuration is by environment, because a hook process has nothing else:

    SANCHO_PROVIDER   jev | recorded | null (default: jev if TYPESAFE_API_KEY is set, else null)
    TYPESAFE_API_KEY  for the Jev provider
    SANCHO_FIXTURE    path of a recording for the recorded provider
    SANCHO_JOURNAL    path of the JSONL journal (default: ~/.sancho/journal.jsonl)
    SANCHO_TIERS      "light=haiku-agent,default=general-purpose,deep=opus-agent" (optional)
    SANCHO_CHEAP_SEARCH  "1" when a cheap search tool is available to the agent
    SANCHO_SCAN_CONTENT  "1" to scan arriving tool results for instructions aimed at the
                      model. Off by default: it is a DETECTION control, not a barrier - by
                      PostToolUse the text is already in the transcript and no hook can
                      replace a tool result. It warns you, marks the passage as data in
                      front of the model, and journals the event. See `points.injection`.
    SANCHO_CONTENT_TOOLS  comma-separated tool names to scan (default: WebFetch,WebSearch)
    SANCHO_SCAN_SHELL_FETCHES  "0" to stop scanning the output of shell commands that fetch
                      from the network (curl, wget, Invoke-WebRequest, ...). On by default
                      whenever SANCHO_SCAN_CONTENT is; other shell output is scanned only
                      if Bash is named in SANCHO_CONTENT_TOOLS.
    SANCHO_PURPOSE    what the job is about, so the scan can judge "aimed at changing what?"
    SANCHO_CHECK_DONE "1" to check, at Stop, that the transcript shows the last request done,
                      and send Claude back once if it confidently does not (opt-in; never
                      twice in a row; any failure lets the stop through). Measured on
                      AgentDojo, not on coding sessions: see docs/results/2026-09-25-completion.
    SANCHO_T_*        any threshold by name, e.g. SANCHO_T_INJECTION=0.5

`sanchopanza install` writes the settings block for all of this.

Each hook process is a fresh squire, so the per-job budget and the repeated-query memory
do not persist across calls. That is the price of the process model; the SDK adapter keeps
them.

The process start-up is the hook's latency, so `main` decides in code, before loading the
squire, asyncio or any provider, whether the event can lead to a decision at all
(`needs_decision`). Most PostToolUse events for Bash, for instance, cannot: only the output of
a command that fetches from the network is scanned by default.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..points import completion
from ..points.routing import Tier
from .generic import Guardian, HarnessConfig, text_of

if TYPE_CHECKING:
    from ..contract import Decider


def decider_from_env(env: dict[str, str] | None = None) -> Decider:
    env = env if env is not None else dict(os.environ)
    from ..providers import create

    provider = env.get("SANCHO_PROVIDER")
    if not provider:
        provider = "jev" if env.get("TYPESAFE_API_KEY") else "null"
    if provider == "recorded":
        return create("recorded", path=env.get("SANCHO_FIXTURE", "fixtures/public-benches.jsonl"))
    if provider == "jev":
        return create("jev", api_key=env.get("TYPESAFE_API_KEY"))
    return create("null")


def config_from_env(env: dict[str, str] | None = None) -> HarnessConfig:
    env = env if env is not None else dict(os.environ)
    tiers: dict[Tier, str] = {}
    for part in filter(None, env.get("SANCHO_TIERS", "").split(",")):
        tier, _, name = part.partition("=")
        if tier.strip() in ("light", "default", "deep") and name.strip():
            tiers[tier.strip()] = name.strip()  # type: ignore[index]
    cheap = env.get("SANCHO_CHEAP_SEARCH", "") in ("1", "true", "yes")
    scan = env.get("SANCHO_SCAN_CONTENT", "") in ("1", "true", "yes")
    check_done = env.get("SANCHO_CHECK_DONE", "") in ("1", "true", "yes")
    shell_fetches = env.get("SANCHO_SCAN_SHELL_FETCHES", "1") not in ("0", "false", "no")
    named = {t.strip() for t in env.get("SANCHO_CONTENT_TOOLS", "").split(",") if t.strip()}
    purpose = env.get("SANCHO_PURPOSE", "").strip()
    defaults = HarnessConfig()
    return HarnessConfig(
        tiers=tiers,
        cheap_search_available=lambda: cheap,
        scan_content=scan,
        check_done=check_done,
        scan_shell_fetches=shell_fetches,
        content_tools=frozenset(named) if named else defaults.content_tools,
        content_purpose=(lambda: purpose) if purpose else defaults.content_purpose,
    )


def guardian_from_env(env: dict[str, str] | None = None) -> Guardian:
    from ..journal import JsonlJournal
    from ..policy import Thresholds
    from ..squire import Squire

    env = env if env is not None else dict(os.environ)
    journal_path = Path(env.get("SANCHO_JOURNAL") or Path.home() / ".sancho" / "journal.jsonl")
    thresholds = Thresholds.from_mapping(
        {k[len("SANCHO_T_") :].lower(): v for k, v in env.items() if k.startswith("SANCHO_T_")}
    )
    squire = Squire(
        decider_from_env(env), thresholds=thresholds, journal=JsonlJournal(journal_path)
    )
    return Guardian(squire, config_from_env(env))


TOOL_RESULT_LIMIT = 1_500


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            str(b.get("text") or b.get("content") or "")
            for b in content
            if isinstance(b, dict) and b.get("type") in ("text", None)
        )
    return ""


def transcript_task_and_record(path: Path) -> tuple[str, str]:
    """The last real prompt, and what the agent did after it, from a Claude Code transcript."""
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    task, lines = "", []
    for entry in entries:
        message = entry.get("message") or {}
        content = message.get("content")
        if entry.get("type") == "user":
            blocks = content if isinstance(content, list) else []
            results = [b for b in blocks if isinstance(b, dict) and b.get("type") == "tool_result"]
            if results:
                for b in results:
                    lines.append(f"TOOL RESULT: {_text_of(b.get('content'))[:TOOL_RESULT_LIMIT]}")
            elif _text_of(content).strip():
                task, lines = _text_of(content).strip(), []  # a new request starts the record
        elif entry.get("type") == "assistant" and isinstance(content, list):
            for b in content:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text" and b.get("text"):
                    lines.append(f"AGENT: {b['text']}")
                elif b.get("type") == "tool_use":
                    arguments = json.dumps(b.get("input"), ensure_ascii=False)
                    lines.append(f"AGENT ACTION: {b.get('name')}({arguments})")
    record = "\n".join(lines)
    return task, record[-completion.RECORD_LIMIT :]


async def stop(input_data: dict[str, Any], guardian: Guardian) -> dict[str, Any]:
    """Send Claude back once when the transcript confidently does not show the task done."""
    config = guardian.config
    if not config.check_done or input_data.get("stop_hook_active"):
        return {}
    try:
        task, record = transcript_task_and_record(Path(str(input_data.get("transcript_path"))))
    except OSError:
        return {}
    if not task:
        return {}
    verdict = await guardian.squire.check_done(task=task, record=record, cut=config.done_cut)
    if verdict.done is not False:
        return {}
    return {
        "decision": "block",
        "reason": (
            "sanchopanza: the transcript does not show this request done "
            f"(p={verdict.probability:.2f}). Before stopping, check every part of the request "
            "against what the tools actually returned, finish what is missing, or say plainly "
            "what could not be done and why."
        ),
    }


def needs_decision(input_data: Mapping[str, Any], config: HarnessConfig) -> bool:
    """False when `handle` would certainly answer `{}` without asking anything. Pure code.

    It mirrors the early returns of `Guardian.before_tool` / `after_tool` and `stop`; when in
    doubt it says True, and the full path decides as before.
    """
    event = str(input_data.get("hook_event_name", "PreToolUse"))
    if event == "Stop":
        return config.check_done and not input_data.get("stop_hook_active")
    name = str(input_data.get("tool_name", ""))
    arguments = input_data.get("tool_input")
    arguments = arguments if isinstance(arguments, Mapping) else {}
    if event == "PostToolUse":
        reviewed = name in config.delegate_tools and config.review_delegations
        scanned = config.scan_content and config.scans_after(name, arguments)
        return (reviewed or scanned) and bool(text_of(input_data.get("tool_response")).strip())
    return name in (config.delegate_tools | config.search_tools | config.shell_tools)


async def handle(input_data: dict[str, Any], guardian: Guardian) -> dict[str, Any]:
    from .claude_agent_sdk import post_tool_use, pre_tool_use

    event = str(input_data.get("hook_event_name", "PreToolUse"))
    if event == "Stop":
        return await stop(input_data, guardian)
    if event == "PostToolUse":
        return await post_tool_use(guardian)(input_data)
    return await pre_tool_use(guardian)(input_data)


def main(argv: list[str] | None = None) -> int:
    raw = sys.stdin.read()
    try:
        input_data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return 0  # malformed input: let the tool run; never block on our own bug
    try:
        if not isinstance(input_data, dict) or not needs_decision(input_data, config_from_env()):
            return 0
        import asyncio

        output = asyncio.run(handle(input_data, guardian_from_env()))
    except Exception:  # fail-open at the process boundary as well
        return 0
    if output:
        sys.stdout.write(json.dumps(output, ensure_ascii=False))
    return 0
