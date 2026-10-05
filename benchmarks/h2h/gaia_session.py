"""What one headless Claude Code session left behind, read without a model and without money.

Shared by the GAIA head-to-head runner (`h2h_gaia.py`) and its tests: the `--output-format json`
result (cost, `modelUsage`, permission denials), the session's own transcripts under
~/.claude/projects (tool calls, tool results, the last FINAL ANSWER), and the deny hook's log.

Cost is kept twice. `list_usd` is Claude Code's own `total_cost_usd`, the number the caps act on.
`list_usd_ours` reprices `modelUsage` with the list prices below, so a Claude Code build that
does not know a model's price shows up as a difference instead of passing silently. Cache writes
are priced at the 1-hour rate: a probe on 2.1.287 (Haiku, 2026-10-05) billed its 6,796 written
tokens at exactly 2x input. Web searches add 0.01 USD each.
"""

from __future__ import annotations

import json
import pathlib
import re
from collections.abc import Iterator, Mapping
from typing import Any

from sanchopanza.candor.claims import without_block

PROJECTS = pathlib.Path.home() / ".claude" / "projects"
# USD per million tokens: input, cache write (1 h), cache read, output. Source: the claude-api
# skill's model table (cached 2026-09-25) for Fable 5.1, Opus 5.5, Sonnet 5.5 and Haiku 4.5.
PRICES = {
    "claude-fable-5-1": (10.0, 20.0, 0.25, 50.0),
    "claude-opus-5-5": (4.0, 8.0, 0.20, 20.0),
    "claude-sonnet-5-5": (2.0, 4.0, 0.20, 10.0),
    "claude-haiku-4-5": (1.0, 2.0, 0.10, 5.0),
}
WEB_SEARCH_USD = 0.01
LEAK_WORD = "GAIA"  # case-sensitive: "Gaia" the spacecraft is not a leak


def folder_of(workdir: str | pathlib.Path, projects: pathlib.Path | None = None) -> pathlib.Path:
    """Where Claude Code keeps a working folder's transcripts: under the session's own user
    folder (`CLAUDE_CONFIG_DIR/projects`) for a clean user, else the home one."""
    return (projects or PROJECTS) / re.sub(r"[^A-Za-z0-9]", "-", str(workdir))


def price_key(model: str) -> str | None:
    for key in PRICES:
        if model.startswith(key):
            return key
    return None


def tokens_of(usage: Mapping[str, Any]) -> dict[str, int]:
    return {
        "input": int(usage.get("inputTokens") or 0),
        "cache_read": int(usage.get("cacheReadInputTokens") or 0),
        "cache_write": int(usage.get("cacheCreationInputTokens") or 0),
        "output": int(usage.get("outputTokens") or 0),
        "web_searches": int(usage.get("webSearchRequests") or 0),
    }


def our_usd(model: str, usage: Mapping[str, Any]) -> float | None:
    """`modelUsage` priced at list; None for a model the table does not know."""
    key = price_key(model) or price_key(str(usage.get("canonicalModel") or ""))
    if key is None:
        return None
    p_in, p_write, p_read, p_out = PRICES[key]
    t = tokens_of(usage)
    tokens = (
        t["input"] * p_in + t["cache_write"] * p_write + t["cache_read"] * p_read
        + t["output"] * p_out
    )  # fmt: skip
    return tokens / 1_000_000 + t["web_searches"] * WEB_SEARCH_USD


def usage_summary(model_usage: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    by_model = {m: round(float(u.get("costUSD") or 0.0), 6) for m, u in model_usage.items()}
    tokens_by_model = {m: tokens_of(u) for m, u in model_usage.items()}
    totals = {k: sum(t[k] for t in tokens_by_model.values()) for k in tokens_of({})}
    priced = {m: our_usd(m, u) for m, u in model_usage.items()}
    unknown = sorted(m for m, v in priced.items() if v is None)
    ours = round(sum(v for v in priced.values() if v is not None), 6)
    return {
        "usd_by_model": by_model,
        "tokens_by_model": tokens_by_model,
        "tokens": totals,
        "list_usd_ours": ours,
        "unpriced_models": unknown,
    }


# --- transcripts --------------------------------------------------------------------------------


def entries(folder: pathlib.Path) -> Iterator[dict[str, Any]]:
    """Every transcript entry of the session, subagents included."""
    for path in sorted(folder.rglob("*.jsonl")) if folder.is_dir() else []:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip():
                try:
                    yield json.loads(line)
                except ValueError:
                    continue


def _blocks(entry: Mapping[str, Any]) -> list[dict[str, Any]]:
    content = (entry.get("message") or {}).get("content")
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for block in content if isinstance(content, list) else []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    return "\n".join(parts)


def tool_calls(folder: pathlib.Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries(folder):
        for block in _blocks(entry):
            if block.get("type") == "tool_use":
                name = str(block.get("name"))
                counts = {**counts, name: counts.get(name, 0) + 1}
    return counts


def leaks(folder: pathlib.Path, task_id: str, word: str = LEAK_WORD) -> list[str]:
    """The tools whose results name the benchmark (`word`, case-sensitive) or carry the task id:
    each one is read by hand before the session counts."""
    names: dict[str, str] = {}
    found: list[str] = []
    for entry in entries(folder):
        for block in _blocks(entry):
            if block.get("type") == "tool_use":
                names = {**names, str(block.get("id")): str(block.get("name"))}
            elif block.get("type") == "tool_result":
                text = result_text(block.get("content"))
                if word in text or (task_id and task_id in text):
                    found.append(names.get(str(block.get("tool_use_id")), "?"))
    return found


FINAL_MARKER = re.compile(r"FINAL ANSWER[ \t]*:", re.I)


def is_status_line(line: str) -> bool:
    """A line of candor's status block (`candor.claims.BLOCK_REQUEST`: STATUS, TESTS,
    TEST_FILES_CHANGED, FILES_READ), read as candor reads it (`without_block`)."""
    return bool(line.strip()) and not without_block(line)


def marker_line(text: str | None, marker: re.Pattern[str] = FINAL_MARKER) -> str | None:
    """The text after the LAST `marker` in `text`, up to the end of that line (CR dropped), or
    None without a marker. The rule every h2h extractor follows in both arms: in S, candor appends
    a status block of a few lines after the answer, and none of it belongs to the answer.

    When the marker's own line is empty (`FINAL ANSWER:` and the answer below it), the answer is
    the next non-empty line, unless that line is candor's status block: then it is empty."""
    found = None
    for match in marker.finditer(text or ""):
        found = match
    if found is None:
        return None
    first, _, below = (text or "")[found.end() :].partition("\n")
    own = first.rstrip("\r").strip()
    if own:
        return own
    following = (line.rstrip("\r").strip() for line in below.split("\n"))
    nxt = next((line for line in following if line), "")
    return "" if is_status_line(nxt) else nxt


def last_assistant_texts(folder: pathlib.Path) -> list[str]:
    """The main agent's assistant texts, in file order (subagents left out)."""
    out = []
    for entry in entries(folder):
        if entry.get("isSidechain") or entry.get("type") != "assistant":
            continue
        out.extend(str(b.get("text") or "") for b in _blocks(entry) if b.get("type") == "text")
    return out


def version_of(folder: pathlib.Path) -> str:
    for entry in entries(folder):
        if entry.get("version"):
            return str(entry["version"])
    return ""


def hook_runs(folder: pathlib.Path) -> dict[str, int]:
    """Hooks whose output reached the transcript (Claude Code 2.1.287 writes an attachment only
    for a hook that printed something): `<event> <whose>`, where whose is `deny` (the runner's
    deny hook), `sanchopanza` (an installed `sanchopanza ...` command) or `other`. Every call of
    an SP hook, silent ones included, is in the shim's log (`shim_runs`)."""
    counts: dict[str, int] = {}
    for entry in entries(folder):
        hook = entry.get("attachment") if entry.get("type") == "attachment" else None
        if not isinstance(hook, dict) or not str(hook.get("type", "")).startswith("hook_"):
            continue
        command = str(hook.get("command") or "")
        # The deny hook's path runs through the sanchopanza checkout: test it first.
        whose = "deny" if "deny_hook" in command or "local_hook" in command else (
            "sanchopanza" if command.startswith("sanchopanza ") else "other")  # fmt: skip
        key = f"{hook.get('hookName') or hook.get('hookEvent')} {whose}"
        counts = {**counts, key: counts.get(key, 0) + 1}
    return counts


def shim_runs(path: pathlib.Path) -> dict[str, int]:
    """The SP shim's log: one line per `sanchopanza` call, by subcommand (`hook`, `guard-hook`)."""
    counts: dict[str, int] = {}
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    for line in lines:
        name = line.split()[0] if line.split() else "?"
        counts = {**counts, name: counts.get(name, 0) + 1}
    return counts


def journal(path: pathlib.Path) -> dict[str, Any]:
    """sanchopanza's journal for one session: decisions by point and provider, and their cost."""
    by_point: dict[str, int] = {}
    providers: dict[str, int] = {}
    usd = 0.0
    errors = 0
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("kind") != "decision":
            continue
        data = event.get("data") or {}
        point = str(data.get("point"))
        provider = str(data.get("provider"))
        by_point = {**by_point, point: by_point.get(point, 0) + 1}
        providers = {**providers, provider: providers.get(provider, 0) + 1}
        usd += float(data.get("cost_usd") or 0.0)
        errors += bool(data.get("error"))
    return {"jev_calls": sum(by_point.values()), "jev_by_point": by_point,
            "jev_providers": providers, "jev_usd": round(usd, 6), "jev_errors": errors}  # fmt: skip


def denials(out: Mapping[str, Any], deny_log: pathlib.Path) -> dict[str, Any]:
    """Claude Code's own `permission_denials` and the deny hook's log, tool names only."""
    listed = [str(d.get("tool_name")) for d in out.get("permission_denials") or []]
    hooked = []
    if deny_log.exists():
        for line in deny_log.read_text(encoding="utf-8").splitlines():
            try:
                hooked.append(str(json.loads(line).get("tool")))
            except ValueError:
                continue
    return {"denied": len(listed), "denied_tools": listed, "hook_denied": hooked}
