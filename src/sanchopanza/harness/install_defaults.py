"""What `sanchopanza install` adds by default besides the hooks: a context budget, the
`find_in_repo` MCP server and the skill that says when to use each part.

- **Context budget** (`--context-budget`, default `DEFAULT_BUDGET` tokens, 0 turns it off). In the
  owner's 1,283 Claude Code sessions, 77 % of the list-price spend was cache reads, and 94 % of it
  sat in the 160 sessions of 100+ calls, whose median context was 308k-419k tokens: with a 1M
  window the native compaction almost never fired. Replaying those sessions with a compaction
  threshold (each compaction charged) put the context re-read cost at 42-44 % of what it was for
  thresholds of 140k-200k, flat around 160k; 100k thrashed (133 %), because their base context
  was 68k. That is a ceiling, not a result: it leaves out the work a compaction makes, which the
  compaction guard exists to cut. Claude Code compacts at `window - 20k - 13k` of the window it is
  told (`CLAUDE_CODE_AUTO_COMPACT_WINDOW`, read from the 2.1.282 binary,
  docs/results/2026-09-28-context-lean/), so the budget writes `budget + 33k` there. A window the
  owner set is theirs: it is kept, and the budget marker is not written.
- **find_in_repo** (`--no-find` to leave it out): the `sanchopanza` server in the project's
  `.mcp.json`, approved by name in the settings. BM25 fragments without a key; judged by the
  decision model when one is configured.
- **The skill** (`--no-skill`): `sanchopanza-code`, copied to `<scope>/.claude/skills/`.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

DEFAULT_BUDGET = 160_000
WINDOW = "CLAUDE_CODE_AUTO_COMPACT_WINDOW"
BUDGET = "SANCHOPANZA_CONTEXT_BUDGET"  # ours: marks the window as ours
COMPACT_MARGIN = 33_000  # 20k reserved for the summary + the 13k Claude Code keeps below it
MIN_BUDGET = 100_000 - COMPACT_MARGIN  # Claude Code floors the window at 100k

FIND_SERVER = "sanchopanza"
SKILL_NAME = "sanchopanza-code"


def window_for(budget: int) -> int:
    return budget + COMPACT_MARGIN


def merge_budget(
    merged: dict[str, Any], budget: int
) -> tuple[dict[str, Any], list[str], list[str]]:
    """The budget's two variables in `env`, or ours out of it when `budget` is 0."""
    env = merged.get("env", {})
    if not isinstance(env, dict):
        return merged, [], []
    ours = BUDGET in env
    if budget <= 0:
        if not ours:
            return merged, [], []
        rest = {k: v for k, v in env.items() if k not in (BUDGET, WINDOW)}
        return {**merged, "env": rest}, [], [f"env: {BUDGET}", f"env: {WINDOW}"]
    if budget < MIN_BUDGET:
        raise ValueError(f"--context-budget below {MIN_BUDGET} cannot be set: Claude Code "
                         "floors the compaction window at 100k")  # fmt: skip
    if WINDOW in env and not ours:
        return merged, [], []  # the owner's own window: theirs to keep
    wanted = {BUDGET: str(budget), WINDOW: str(window_for(budget))}
    changed = {k: v for k, v in wanted.items() if env.get(k) != v}
    if not changed:
        return merged, [], []
    return {**merged, "env": {**env, **changed}}, [f"env: {k}={v}" for k, v in changed.items()], []


def find_server_entry(command: str) -> dict[str, Any]:
    """The `.mcp.json` entry, from the hook command: `<x> hook` becomes `<x> find-mcp`."""
    words = command.split()
    if words and words[-1] == "hook":
        words = words[:-1]
    words = words or ["sanchopanza"]
    return {"command": words[0], "args": [*words[1:], "find-mcp"]}


def skill_text() -> str:
    return resources.files("sanchopanza.harness").joinpath("skill_code.md").read_text("utf-8")


def skill_path(settings_path: Path) -> Path:
    """Beside the settings file: `<project>/.claude/skills/...` or `~/.claude/skills/...`."""
    return settings_path.parent / "skills" / SKILL_NAME / "SKILL.md"


def skill_change(settings_path: Path, on: bool) -> tuple[Path, str | None] | None:
    """(path, new text) to write, (path, None) to remove ours, or None when nothing changes."""
    target = skill_path(settings_path)
    if on:
        text = skill_text()
        current = target.read_text(encoding="utf-8") if target.exists() else None
        return None if current == text else (target, text)
    if target.exists() and target.read_text(encoding="utf-8") == skill_text():
        return (target, None)  # only a copy we wrote is taken out; an edited one is theirs
    return None


def apply_skill(change: tuple[Path, str | None]) -> None:
    target, text = change
    if text is None:
        target.unlink()
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")
