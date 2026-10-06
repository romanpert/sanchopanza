"""The compaction window each call ran under, as the session itself reports it. Free: it reads
files the call leaves behind, and asks no model.

Claude Code 2.1.287 resolves the auto-compaction window in this order (read from the pinned
binary, `resolveAutoCompactWindow`): env `CLAUDE_CODE_AUTO_COMPACT_WINDOW` > settings
`autoCompactWindow` > `clientdata` (server-sent per account, cached in the configuration's
`.claude.json` as `autoCompactWindowsCache` and `clientDataCache`) > `experiment` >
`model-default`. Before every API call it writes a debug line

    autocompact: tokens=<n> level=<ok|warn|compact> effectiveWindow=<w>

with `effectiveWindow = window - min(maxOutputTokens, 20k)`. The runner passes
`--debug=autocompact --debug-file=<evidence>/debug-<k>.log` in every arm (the same command
line), so N's server-set default is measured, not assumed (pre-mortem 8). The source is named
from what the arm set (N-early and S: the settings `env`) and from the server cache the clean
configuration received; a window nobody set and the cache does not name is "server or model
default".
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

LINE = re.compile(r"autocompact: tokens=(\d+) level=(\w+) effectiveWindow=(\d+)")
OUTPUT_RESERVE = 20_000  # window - effective: min(maxOutputTokens, 20k); 20k on every model here
CACHE_KEYS = ("autoCompactWindowsCache",)
CLIENT_DATA = "clientDataCache"
KEEP = 400  # lines of a debug file kept after the call (it only grows otherwise)


def debug_path(evidence: Path, k: int, retry: bool = False) -> Path:
    return evidence / f"debug-{k}{'-retry' if retry else ''}.log"


def flags(path: Path) -> list[str]:
    """The command-line flags that make Claude Code write the autocompact lines, and only them."""
    return ["--debug=autocompact", f"--debug-file={path}"]


def read_debug(path: Path) -> dict[str, Any]:
    """What the call's debug file says: the effective windows it saw and the largest token count
    measured against them. Empty when the file is absent (a call that never started)."""
    if not path.exists():
        return {}
    found = [m for m in (LINE.search(x) for x in path.read_text("utf-8", "replace").splitlines())
             if m]  # fmt: skip
    if not found:
        return {"lines": 0}
    windows = sorted({int(m.group(3)) for m in found})
    return {"lines": len(found), "effective": windows[-1], "effective_seen": windows,
            "max_tokens": max(int(m.group(1)) for m in found),
            "levels": sorted({m.group(2) for m in found})}  # fmt: skip


def trim_debug(path: Path, keep: int = KEEP) -> None:
    """Keep only the autocompact lines (the last `keep`): a long call's debug file stays small."""
    if not path.exists():
        return
    lines = [x for x in path.read_text("utf-8", "replace").splitlines() if LINE.search(x)]
    path.write_text("".join(f"{x}\n" for x in lines[-keep:]), encoding="utf-8", newline="\n")


def server_cache(config: Path) -> dict[str, Any]:
    """The window the server sent this clean configuration, as Claude Code cached it: the
    `autoCompactWindowsCache` entry and any `clientDataCache` key about compaction."""
    path = config / ".claude.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except ValueError:
        return {"error": f"{path.name} is not JSON"}
    out = {k: data[k] for k in CACHE_KEYS if data.get(k) is not None}
    client = data.get(CLIENT_DATA)
    if isinstance(client, dict):
        about = {k: v for k, v in client.items() if "compact" in k.lower() or k == "rowan_thicket"}
        out = {**out, **({CLIENT_DATA: about} if about else {})}
    return out


def source_of(configured: str | None, cache: Mapping[str, Any]) -> str:
    """Which input decided the window, as far as the files show it."""
    if configured:
        return "env"
    if cache.get("autoCompactWindowsCache") or cache.get(CLIENT_DATA):
        return "clientdata (server cache)"
    return "server or model default (no server cache entry)"


def call_window(debug: Path, config: Path, configured: str | None) -> dict[str, Any]:
    """The row's `window_reported` for one call: what the session said and where it came from."""
    seen = read_debug(debug)
    cache = server_cache(config)
    effective = seen.get("effective")
    return {**seen, "window": effective + OUTPUT_RESERVE if effective else None,
            "configured": int(configured) if configured else None,
            "source": source_of(configured, cache), "server_cache": cache}  # fmt: skip


def arm_window(calls: list[Mapping[str, Any]], configured: str | None) -> dict[str, Any]:
    """The arm's window: the first call that reported one (they never change within an arm unless
    the server changes its mind, which `changed` then says)."""
    reported = [c["window_reported"] for c in calls if (c.get("window_reported") or {}).get(
        "effective")]  # fmt: skip
    first = reported[0] if reported else {}
    values = sorted({r["effective"] for r in reported})
    return {"value": int(configured) if configured else first.get("window"),
            "configured": int(configured) if configured else None,
            "effective_reported": first.get("effective"), "changed": len(values) > 1,
            "source": first.get("source") or ("env" if configured else "not reported"),
            "server_cache": first.get("server_cache", {})}  # fmt: skip


def record(root: Path, model: str, arm: str, window: Mapping[str, Any]) -> Path:
    """`<root>/windows.json`: per model and arm, the window its session reported (the gate's
    record of N's server-set default per model)."""
    path = root / "windows.json"
    try:
        current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except ValueError:
        current = {}
    merged = {**current, model: {**(current.get(model) or {}), arm: dict(window)}}
    path.write_text(json.dumps(merged, indent=1), encoding="utf-8", newline="\n")
    return path
