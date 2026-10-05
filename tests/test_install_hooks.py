"""The split of `install` into `install_hooks`: `plan` keeps its signature and its output, the
browse sets keep their order, the names sealed benchmarks import from `install` are still there,
and `install_hooks` does not import `install` back."""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

from sanchopanza.harness import install, install_hooks
from sanchopanza.harness.generic import HarnessConfig

PLAN_PARAMETERS = (
    ("path", inspect.Parameter.empty),
    ("config", inspect.Parameter.empty),
    ("command", "sanchopanza hook"),
    ("provider", ""),
    ("compact_root", None),
    ("autopilot", False),
    ("lean", False),
    ("guard", False),
    ("candor", False),
    ("memory", False),
    ("budget", 0),
    ("find", False),
    ("find_nudge", False),
    ("find_auto", False),
    ("profile", "sandbox"),
    ("crawl", False),
    ("prune", False),
    ("sources", False),
    ("fetch", False),
)

MEMORY = "sanchopanza memory-hook"
HOOK = "sanchopanza hook"
PRE = "Agent|Bash|PowerShell|Task|WebSearch|bash|execute|run_command|shell"
# Memory v6 (894f650) added Bash and PowerShell to the touch; v7 (3f9d719) moved SessionStart
# from "compact" to every start (standing rules). Pinned again after memory v8.3 was merged.
FILES = "Read|Edit|MultiEdit|Write|NotebookEdit|Bash|PowerShell"


def _entry(matcher: str, command: str) -> dict:
    return {"matcher": matcher, "hooks": [{"type": "command", "command": command}]}


def test_plan_keeps_its_signature() -> None:
    parameters = inspect.signature(install.plan).parameters
    assert tuple((p.name, p.default) for p in parameters.values()) == PLAN_PARAMETERS
    assert parameters["profile"].annotation == "str | None"


def test_plan_output_is_unchanged_by_the_split(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    theirs = _entry("Read", "theirs")
    path.write_text(json.dumps({"hooks": {"PostToolUse": [theirs]}, "env": {"KEEP": "1"}}), "utf-8")
    settings = install.plan(
        path, HarnessConfig(), memory=True, budget=200000, find=True, profile=None
    )
    assert settings.added == (
        f"PreToolUse: {PRE}",
        "PostToolUse: Agent|Task",
        "UserPromptSubmit:  (memory)",
        "Stop:  (memory)",
        "SessionEnd:  (memory)",
        f"PostToolUse: {FILES} (memory)",
        "SessionStart:  (memory)",
        "env: SANCHOPANZA_CONTEXT_BUDGET=200000",
        "env: CLAUDE_CODE_AUTO_COMPACT_WINDOW=233000",
        "env: SANCHOPANZA_GUARD_PROFILE=coding",
        "enabledMcpjsonServers: sanchopanza",
    )
    assert settings.removed == ()
    assert settings.merged == {
        "enabledMcpjsonServers": ["sanchopanza"],
        "env": {
            "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "233000",
            "KEEP": "1",
            "SANCHOPANZA_CONTEXT_BUDGET": "200000",
            "SANCHOPANZA_GUARD_PROFILE": "coding",
        },
        "hooks": {
            "PostToolUse": [theirs, _entry("Agent|Task", HOOK), _entry(FILES, MEMORY)],
            "PreToolUse": [_entry(PRE, HOOK)],
            "UserPromptSubmit": [_entry("", MEMORY)],
            "Stop": [_entry("", MEMORY)],
            "SessionEnd": [_entry("", MEMORY)],
            "SessionStart": [_entry("", MEMORY)],
        },
    }


def test_browse_sets_are_wired_and_removed_in_order(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    on = install.plan(path, HarnessConfig(), crawl=True, prune=True, sources=True, fetch=True)
    browse = (
        "SessionStart:  (crawl)",
        # S seal: install --crawl wires every event crawl answers (CRAWL_INSTALL_HOOKS)
        "PreToolUse: mcp__.*__browser_(evaluate|take_screenshot) (crawl)",
        "PostToolUse: mcp__.*__browser_evaluate (crawl)",
        "UserPromptSubmit:  (crawl)",
        "PostToolUse: mcp__.*__browser_(?!evaluate$).* (prune)",
        "Stop:  (sources)",
        "PreToolUse: WebFetch (fetch)",
    )
    assert tuple(a for a in on.added if a.endswith(")")) == browse
    install.apply(on)
    assert install.plan(path, HarnessConfig()).removed == browse


def test_merge_browse_with_everything_off_changes_nothing() -> None:
    settings = {"hooks": {"Stop": [_entry("", "theirs")]}}
    merged, added, removed = install_hooks.merge_browse(
        settings, crawl=False, prune=False, sources=False, fetch=False
    )
    assert (merged, added, removed) == (settings, [], [])


def test_install_still_exports_what_sealed_benchmarks_import() -> None:
    for name in ("CRAWL_COMMAND", "CRAWL_HOOKS", "_merge_crawl", "_merge_owned", "PRUNE_COMMAND",
                 "PRUNE_HOOKS", "FETCH_COMMAND", "FETCH_HOOKS"):  # fmt: skip
        assert getattr(install, name) is getattr(install_hooks, name)


def test_install_hooks_does_not_import_install() -> None:
    tree = ast.parse(Path(install_hooks.__file__).read_text(encoding="utf-8"))
    modules = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    } | {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
         for alias in node.names}  # fmt: skip
    assert not any(m == "install" or m.endswith(".install") for m in modules)
