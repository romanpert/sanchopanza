"""Command-line hook for Claude Code (`sanchopanza hook`), and any harness with the same protocol.

Claude Code runs hooks as processes: JSON on stdin, JSON on stdout. In `settings.json`:

    {"hooks": {
      "PreToolUse": [{"matcher": "Agent|WebSearch|Bash",
                      "hooks": [{"type": "command", "command": "sanchopanza hook"}]}],
      "PostToolUse": [{"matcher": "Agent",
                       "hooks": [{"type": "command", "command": "sanchopanza hook"}]}]}}

Configuration is by environment, because a hook process has nothing else. Every variable
below is `SANCHOPANZA_<NAME>`; the old `SANCHO_<NAME>` spelling is still read, and the new one
wins when both are set (`sanchopanza._env`):

    PROVIDER          jev | recorded | null (default: jev if TYPESAFE_API_KEY is set, else null)
    TYPESAFE_API_KEY  for the Jev provider (this one keeps its own name)
    FIXTURE           path of a recording for the recorded provider
    JOURNAL           path of the JSONL journal (default: ~/.sanchopanza/journal.jsonl, or
                      ~/.sancho/journal.jsonl when only that directory exists)
    TIERS             "light=haiku-agent,default=general-purpose,deep=opus-agent" (optional)
    CHEAP_SEARCH      "1" when a cheap search tool is available to the agent
    SCAN_CONTENT      "1" to scan arriving tool results for instructions aimed at the
                      model. Off by default: it is a DETECTION control, not a barrier - by
                      PostToolUse the text is already in the transcript and no hook can
                      replace a tool result. It warns you, marks the passage as data in
                      front of the model, and journals the event. See `points.injection`.
    CONTENT_TOOLS     comma-separated tool names to scan (default: WebFetch,WebSearch)
    SCAN_SHELL_FETCHES  "0" to stop scanning the output of shell commands that fetch
                      from the network (curl, wget, Invoke-WebRequest, ...). On by default
                      whenever SCAN_CONTENT is; other shell output is scanned only
                      if Bash is named in CONTENT_TOOLS.
    PURPOSE           what the job is about, so the scan can judge "aimed at changing what?"
    CHECK_DONE        "1" to check, at Stop, that the transcript shows the last request done,
                      and send Claude back once if it confidently does not (opt-in; never
                      twice in a row; any failure lets the stop through). Measured on
                      AgentDojo, not on coding sessions: see docs/results/2026-09-25-completion.
    T_*               any threshold by name, e.g. SANCHOPANZA_T_INJECTION=0.5
    AUTOPILOT         "1" to cut long tool results on arrival and recall archived output and
                      memories (`harness.autopilot`, which lists its own knobs)

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

from .. import _env
from ..points import completion
from ..points.routing import Tier
from .generic import Guardian, HarnessConfig, text_of

if TYPE_CHECKING:
    from ..contract import Decider


def decider_from_env(env: dict[str, str] | None = None) -> Decider:
    env = env if env is not None else dict(os.environ)
    from ..providers import create

    provider = _env.get("PROVIDER", env=env)
    if not provider:
        provider = "jev" if env.get("TYPESAFE_API_KEY") else "null"
    try:
        if provider == "recorded":
            return create(
                "recorded", path=_env.get("FIXTURE", "fixtures/public-benches.jsonl", env=env)
            )
        if provider == "jev":
            url = _env.get("JEV_URL", "", env=env)
            extra = {"base_url": url} if url else {}
            return create("jev", api_key=env.get("TYPESAFE_API_KEY"), **extra)
        if provider == "clm":  # a self-hosted CLM (`clm-serve`): the Jev wire format
            return create("clm", base_url=_env.get("CLM_URL", "", env=env) or None)
        if provider == "llm":
            return _llm_from_env(env)
        if provider != "null":
            # Any other name is an installed provider plugin taking no required arguments.
            return create(provider)
    except Exception as error:  # noqa: BLE001 - fail open, but never in silence
        sys.stderr.write(f"sanchopanza: provider {provider!r} unavailable ({error}); no decider\n")
    return create("null")


def _llm_from_env(env: dict[str, str]) -> Decider:
    """A general model answering the typed questions (`providers.llm`), by Anthropic's API:
    `SANCHOPANZA_LLM_MODEL` (default Claude Haiku 4.5) and `ANTHROPIC_API_KEY`."""
    from ..providers.llm import LLMDecider, anthropic_completer

    model = _env.get("LLM_MODEL", "claude-haiku-4-5-20251001", env=env)
    key = env.get("ANTHROPIC_API_KEY") or ""
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    completer = anthropic_completer(key, model, timeout_s=60)
    return LLMDecider(completer, model=model, price_in_per_mtok=1.0, price_out_per_mtok=5.0)


def config_from_env(env: dict[str, str] | None = None) -> HarnessConfig:
    env = env if env is not None else dict(os.environ)
    tiers: dict[Tier, str] = {}
    for part in filter(None, _env.get("TIERS", "", env=env).split(",")):
        tier, _, name = part.partition("=")
        if tier.strip() in ("light", "default", "deep") and name.strip():
            tiers[tier.strip()] = name.strip()  # type: ignore[index]
    cheap = _env.get("CHEAP_SEARCH", "", env=env) in ("1", "true", "yes")
    scan = _env.get("SCAN_CONTENT", "", env=env) in ("1", "true", "yes")
    check_done = _env.get("CHECK_DONE", "", env=env) in ("1", "true", "yes")
    shell_fetches = _env.get("SCAN_SHELL_FETCHES", "1", env=env) not in ("0", "false", "no")
    named = {t.strip() for t in _env.get("CONTENT_TOOLS", "", env=env).split(",") if t.strip()}
    purpose = _env.get("PURPOSE", "", env=env).strip()
    chosen = _env.get("GUARD_PROFILE", "", env=env).strip().lower()
    profile = "coding" if chosen == "coding" else "sandbox"
    defaults = HarnessConfig()
    return HarnessConfig(
        tiers=tiers,
        cheap_search_available=lambda: cheap,
        scan_content=scan,
        check_done=check_done,
        scan_shell_fetches=shell_fetches,
        content_tools=frozenset(named) if named else defaults.content_tools,
        content_purpose=(lambda: purpose) if purpose else defaults.content_purpose,
        guard_profile=profile,
    )


def squire_from_env(env: dict[str, str] | None = None, *, redact: bool = False) -> Any:
    from ..journal import JsonlJournal
    from ..policy import Thresholds
    from ..redact import redact_secrets
    from ..squire import Squire

    env = env if env is not None else dict(os.environ)
    journal_path = Path(_env.get("JOURNAL", env=env) or _env.home_dir() / "journal.jsonl")
    thresholds = Thresholds.from_mapping(
        {k.lower(): v for k, v in _env.with_prefix("T_", env).items()}
    )
    return Squire(
        decider_from_env(env),
        thresholds=thresholds,
        journal=JsonlJournal(journal_path),
        redact=redact_secrets if redact else None,
    )


def guardian_from_env(env: dict[str, str] | None = None) -> Guardian:
    env = env if env is not None else dict(os.environ)
    return Guardian(squire_from_env(env), config_from_env(env))


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


def needs_decision(
    input_data: Mapping[str, Any], config: HarnessConfig, autopilot: Any = None
) -> bool:
    """False when `handle` would certainly answer `{}` without asking anything. Pure code.

    It mirrors the early returns of `Guardian.before_tool` / `after_tool` and `stop`; when in
    doubt it says True, and the full path decides as before.
    """
    if autopilot is not None and autopilot.any:
        from .autopilot import wants

        if wants(input_data, autopilot):
            return True
    event = str(input_data.get("hook_event_name", "PreToolUse"))
    if event == "Stop":
        return config.check_done and not input_data.get("stop_hook_active")
    if event == "UserPromptSubmit":
        return find_on_prompt()
    name = str(input_data.get("tool_name", ""))
    arguments = input_data.get("tool_input")
    arguments = arguments if isinstance(arguments, Mapping) else {}
    if event == "PostToolUse":
        reviewed = name in config.delegate_tools and config.review_delegations
        scanned = config.scan_content and config.scans_after(name, arguments)
        return (reviewed or scanned) and bool(text_of(input_data.get("tool_response")).strip())
    return name in (config.delegate_tools | config.search_tools | config.shell_tools)


def find_on_prompt() -> bool:
    return _env.get("FIND_ON_PROMPT", "") in ("1", "true", "yes")


def repo_hint(input_data: Mapping[str, Any]) -> dict[str, Any]:
    """`SANCHOPANZA_FIND_ON_PROMPT=1`: the likely files for the prompt, appended as context.
    Free (BM25), bounded (`context.repo.hint`), and never fatal."""
    if not find_on_prompt():
        return {}
    from ..context.repo import hint

    try:
        root = Path(str(input_data.get("cwd") or os.getcwd()))
        note = hint(str(input_data.get("prompt") or ""), root)
    except Exception as error:  # noqa: BLE001 - a hint is never worth a failed prompt
        name = error.__class__.__name__
        sys.stderr.write(f"sanchopanza: repository hint skipped ({name})\n")
        return {}
    if not note:
        return {}
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": note}}


def merge_outputs(first: Mapping[str, Any], second: Mapping[str, Any]) -> dict[str, Any]:
    """Two hook outputs as one: contexts joined, the second's other fields win."""
    if not first:
        return dict(second)
    if not second:
        return dict(first)
    a = dict(first.get("hookSpecificOutput") or {})
    b = dict(second.get("hookSpecificOutput") or {})
    contexts = (a.get("additionalContext"), b.get("additionalContext"))
    joined = "\n\n".join(x for x in contexts if x)
    specific = {**a, **b}
    if joined:
        specific["additionalContext"] = joined
    out = {**dict(first), **dict(second), "hookSpecificOutput": specific}
    return out


def project_dir(input_data: Mapping[str, Any]) -> str:
    """The project the session was started in, not the live `cwd`: a `cd ~` earlier in the
    session would otherwise tell the decider the whole home is writable."""
    fixed = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if fixed:
        return fixed
    start = Path(str(input_data.get("cwd") or os.getcwd()))
    for folder in (start, *start.parents):
        if (folder / ".git").exists():
            return str(folder)
    return str(start)


def with_workspace(guardian: Guardian, input_data: Mapping[str, Any]) -> Guardian:
    """The coding profile's guard asks with the session's own working directory as the place it
    may write; the sandbox profile keeps its configured environment."""
    config = guardian.config
    if config.guard_profile != "coding" or config.guard_environment is not None:
        return guardian
    from dataclasses import replace

    from ..points.guard import coding_environment

    workspace = project_dir(input_data)
    coding = replace(config, guard_environment=coding_environment(workspace))
    return Guardian(guardian.squire, coding)


async def handle(
    input_data: dict[str, Any], guardian: Guardian, autopilot_squire: Any = None
) -> dict[str, Any]:
    from .autopilot import config_from_env as autopilot_config
    from .autopilot import post_tool_use as autopilot_post
    from .autopilot import user_prompt, wants
    from .claude_agent_sdk import post_tool_use, pre_tool_use

    event = str(input_data.get("hook_event_name", "PreToolUse"))
    pilot = autopilot_config()
    squire = autopilot_squire if autopilot_squire is not None else guardian.squire
    guardian = with_workspace(guardian, input_data)
    if event == "Stop":
        return await stop(input_data, guardian)
    if event == "UserPromptSubmit":
        recalled = await user_prompt(input_data, squire, pilot) if pilot.recall else {}
        return merge_outputs(recalled, repo_hint(input_data))
    if event == "PostToolUse":
        base = {}
        if needs_decision(input_data, guardian.config):
            base = await post_tool_use(guardian)(input_data)
        extra = {}
        if pilot.any and wants(input_data, pilot):
            extra = await autopilot_post(input_data, squire, pilot)
        return merge_outputs(base, extra)
    return await pre_tool_use(guardian)(input_data)


def main(argv: list[str] | None = None) -> int:
    from .hookio import stdin_text, stdout_json

    raw = stdin_text()
    try:
        input_data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return 0  # malformed input: let the tool run; never block on our own bug
    try:
        from .autopilot import config_from_env as autopilot_config

        pilot = autopilot_config()
        if not isinstance(input_data, dict) or not needs_decision(
            input_data, config_from_env(), pilot
        ):
            return 0
        import asyncio

        squire = squire_from_env(redact=True) if pilot.any else None
        output = asyncio.run(handle(input_data, guardian_from_env(), squire))
    except Exception as error:  # fail-open at the process boundary, but never silently
        sys.stderr.write(
            f"sanchopanza hook: passed through unchanged ({error.__class__.__name__}: {error})\n"
        )
        return 0
    if output:
        stdout_json(output)
    return 0
