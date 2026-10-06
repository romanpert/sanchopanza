"""What stops a long chain, checked by `long_run.py` between calls and on every event: the
long-session pre-mortem's preventions that are pure decisions, kept apart from the runner so each
is tested on its own. Nothing here calls `claude`, an API or Jev.

- 1 a usage limit (`carry.limited`) or a rate-limit warning: LIMIT.flag, checked by every runner
  between calls; 18 a STOP file in the run root: the graceful stop.
- 4 a call cut mid-way (timeout, crash) is retried only when it used no tool and left the diff
  as it was; otherwise development goes on with a declared deviation and a confirmation chain
  is set aside.
- 6 a chain must not cross midnight (the date in the prompt changes and the cache misses).
- 9 the first request's prefix: N and N-early within 50 tokens, S above N by its install.
- 10, 11 every call's `init`: the pinned version, the model, the same permission mode, no API
  key, and an S arm's MCP servers connected (a failed server is a broken arm, not a run).
- 3, e every block's caps are summed against the ceiling before anything runs.
- 14 free disk; 15 Jev's decisions (the first ten all null: an outage); 18 a PID is killed only
  when its command line and creation date match the status file.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "memory_carry"))

import carry  # noqa: E402

LIMIT_FLAG = Path(r"C:\sp-runs\LIMIT.flag")
STOP_FILE = "STOP"
DISK_FLOOR_GB = 30.0
PREFIX_SAME = 50  # N against N-early: the same prefix, to this many tokens
S_PREFIX_EXTRA = (200, 6_000)  # S over N: its skill listing, server schemas, hook texts (~1k)
JEV_FIRST = 10
CONNECTED = "connected"


@dataclass(frozen=True)
class Expect:
    """What every call's `init` must say."""

    version: str
    model: str
    permission_mode: str
    mcp: tuple[str, ...] = ()  # servers that must be connected (S); none for N and N-early


# ---- stop files ----------------------------------------------------------------------------------


def stop_reason(root: Path, limit_flag: Path = LIMIT_FLAG) -> str:
    """Why no further call may start ("" when it may)."""
    if limit_flag.exists():
        return f"LIMIT.flag present ({limit_flag})"
    if (root / STOP_FILE).exists():
        return f"STOP file present ({root / STOP_FILE})"
    return ""


def raise_limit(limit_flag: Path, why: str) -> None:
    """Every runner on the machine stops before its next call."""
    limit_flag.parent.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().isoformat(timespec="seconds")
    with limit_flag.open("a", encoding="utf-8") as out:
        out.write(f"{stamp} {why}\n")


def limit_event(event: Mapping[str, Any]) -> str:
    """"limit" for the usage limit as `carry.limited` reads it, "warning" for a rate-limit event
    that is not `allowed` (2.1.287 says `allowed_warning` before it rejects), else ""."""
    if carry.limited(dict(event)):
        return "limit"
    info = event.get("rate_limit_info")
    if event.get("type") == "rate_limit_event" and isinstance(info, dict):
        return "" if info.get("status") == "allowed" else "warning"
    return ""


# ---- invariants ----------------------------------------------------------------------------------


def init_breaks(init: Mapping[str, Any], expect: Expect) -> tuple[str, ...]:
    """What a call's `init` (`carry.init_facts`) says that it must not. No init at all is one."""
    if not init:
        return ("no init event",)
    found = []
    pairs = (("version", expect.version), ("model", expect.model),
             ("permission_mode", expect.permission_mode), ("api_key_source", "none"))  # fmt: skip
    for key, wanted in pairs:
        if init.get(key) != wanted:
            found.append(f"{key} {init.get(key)!r}, expected {wanted!r}")
    servers = dict(init.get("mcp") or {})
    for name in expect.mcp:
        if servers.get(name) != CONNECTED:
            found.append(f"MCP server {name} {servers.get(name, 'absent')}")
    extra = sorted(set(servers) - set(expect.mcp))
    if extra:
        found.append(f"MCP servers nobody installed: {extra}")
    return tuple(found)


def permission_breaks(modes: Mapping[str, str]) -> tuple[str, ...]:
    """Pre-mortem 10: one permission mode for every arm and call (`modes`: "<arm>/<call>" ->
    the mode its init reported). Never `bypassPermissions`."""
    found = sorted(set(modes.values()))
    out = [f"permission modes differ: {found}"] if len(found) > 1 else []
    if "bypassPermissions" in found:
        out.append("a call ran with bypassPermissions")
    return tuple(out)


def prefix_breaks(prefix: Mapping[str, int]) -> tuple[str, ...]:
    """First-request prefix sizes (read + written + input) per arm, compared once all are in."""
    out = []
    n, early, s = prefix.get("N"), prefix.get("Ne"), prefix.get("S")
    if n is not None and early is not None and abs(n - early) > PREFIX_SAME:
        out.append(f"N-early's prefix {early} differs from N's {n} by more than {PREFIX_SAME}")
    low, high = S_PREFIX_EXTRA
    if n is not None and s is not None and not low <= s - n <= high:
        out.append(f"S's prefix {s} is not N's {n} plus {low}-{high}")
    return tuple(out)


# ---- plan time -----------------------------------------------------------------------------------


def plan_refusal(blocks: Iterable[tuple[str, str, float]], ceiling: float,
                 spent: float = 0.0) -> str:  # fmt: skip
    """Pre-mortem e: every (chain, model, chain cap) held at once against the ceiling, before
    the first call; "" when they fit. A fourth chain refused mid-run is a gate that never ends."""
    held = round(sum(cap for _c, _m, cap in blocks) + spent, 2)
    if held > ceiling:
        return f"the chain caps and the spend so far hold {held} USD, above the ceiling {ceiling}"
    return ""


def manifest_refusal(names: Iterable[str], known: Mapping[str, Any], folder: Path,
                     digest: Callable[[Mapping[str, Any]], str]) -> str:  # fmt: skip
    """No chain runs without the manifest its validation wrote (`long60/<chain>.json`): valid,
    and with the digest of the chain the runner is about to read ("" when every one holds)."""
    for name in names:
        path = folder / f"{name}.json"
        if not path.exists():
            return f"no manifest {path}: validate the chain and run `long.py manifests` first"
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return f"manifest {path} is not JSON"
        if manifest.get("valid") is not True:
            return f"manifest {path} does not say the chain is valid"
        if name in known and manifest.get("sha256") != digest(known[name]):
            return f"{name}: the chain in the cache is not the one its manifest describes"
    return ""


def window_breaks(early: int | None, installed: int | None) -> tuple[str, ...]:
    """N-early's window must be the one S's own install wrote for its budget, the same variable
    in the same settings block (`None`: that arm has not run yet)."""
    if early is None or installed is None or early == installed:
        return ()
    return (f"N-early's window {early} is not the {installed} S's install wrote",)


def crosses_midnight(start: dt.datetime, hours: float) -> bool:
    return (start + dt.timedelta(hours=hours)).date() != start.date()


def disk_refusal(path: Path, floor_gb: float = DISK_FLOOR_GB) -> str:
    free = shutil.disk_usage(path.anchor or str(path)).free / 1e9
    return f"{free:.1f} GB free on {path.anchor}, below {floor_gb}" if free < floor_gb else ""


# ---- a call cut mid-way --------------------------------------------------------------------------


def resume_decision(tool_uses: int, diff_before: str, diff_after: str, split: str) -> str:
    """Pre-mortem 4: "retry" (the call did nothing: no tool, the same diff), else "set-aside" for
    a confirmation chain and "continue" (a declared deviation) for development and the gate."""
    if tool_uses == 0 and diff_before == diff_after:
        return "retry"
    return "set-aside" if split == "held" else "continue"


def diff_vanished(previous: str, current: str) -> bool:
    """Pre-mortem 13: a diff that comes back empty after a non-empty one is the harness."""
    return bool(previous.strip()) and not current.strip()


# ---- Jev -----------------------------------------------------------------------------------------


def decisions(journal: Path, skip: int = 0) -> list[dict[str, Any]]:
    """The journal's decisions from line `skip` on (a call's own, given the count before it)."""
    if not journal.exists():
        return []
    out = []
    for line in journal.read_text(encoding="utf-8").splitlines()[skip:]:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and entry.get("kind") == "decision":
            out.append(entry.get("data") or {})
    return out


def failed(decision: Mapping[str, Any]) -> bool:
    return decision.get("provider") in (None, "null") or bool(decision.get("error"))


def jev_outage(found: list[Mapping[str, Any]], first: int = JEV_FIRST) -> bool:
    """Pre-mortem 15: the first `first` decisions of an S arm all failed or null."""
    return len(found) >= first and all(failed(d) for d in found[:first])


# ---- killing by PID ------------------------------------------------------------------------------

Query = Callable[[int], Mapping[str, str] | None]


def process_info(pid: int) -> dict[str, str] | None:
    """CommandLine and CreationDate of a live process, from WMI (None when it is gone)."""
    script = (f"$p = Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}'; "
              "if ($p) { @{c=$p.CommandLine; d=$p.CreationDate.ToString('o')} | ConvertTo-Json }")
    done = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True,
                          text=True, timeout=60)  # fmt: skip
    text = done.stdout.strip()
    if done.returncode != 0 or not text:
        return None
    data = json.loads(text)
    return {"command_line": str(data.get("c") or ""), "created": str(data.get("d") or "")}


def kill_tree(pid: int) -> int:
    """The process and everything it started (claude.exe, its MCP servers, runtests, docker)."""
    return subprocess.run(["taskkill", "/T", "/F", "/PID", str(int(pid))],
                          capture_output=True).returncode  # fmt: skip


def verified_kill(status: Mapping[str, Any], query: Query = process_info,
                  kill: Callable[[int], int] = kill_tree) -> str:  # fmt: skip
    """Pre-mortem 18: kill the runner's tree only when the live PID's command line and creation
    date are the ones its status file recorded; otherwise say why not."""
    pid = int(status.get("pid") or 0)
    live = query(pid) if pid else None
    if live is None:
        return f"no live process {pid}: nothing killed"
    for key in ("command_line", "created"):
        if live.get(key) != status.get(key):
            return f"PID {pid} is another process ({key} differs): nothing killed"
    code = kill(pid)
    return f"killed the tree of {pid} (taskkill exit {code})"
