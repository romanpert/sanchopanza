"""Pilot of bet A, passages on arrival: arm N plus the `passages-hook` of a frozen sanchopanza and
nothing else, on the gate's chains, model and caps (`long_run.PROFILES["pilot-a"]`), against the
gate's own N rows (`pilot_a_compare.py`).

    A    sanchopanza install --scope project --write --passages --provider jev ...
    A10  sanchopanza install --scope project --write --passages --passages-fraction 0.10 ...

Both add `--no-guard --no-find --no-skill --context-budget 0` (the parts the default install turns
on) and the runner then keeps the passages hook alone: the install always wires `sanchopanza hook`
too (Task routing and the shell guard, which asks Jev about Bash commands), which N does not have.
The passages hook itself is wired twice (lean edd37bb): the cut after Bash, PowerShell and Read, and
before Write, Edit, MultiEdit and NotebookEdit the guard that denies rewriting a file from a cut
view. Checked after every install (`install_breaks`), or the arm does not start. The hooks' archive
lives under the arm's evidence (`hook_env`), outside the working copy, so its folder is added to
`permissions.additionalDirectories`: the hook's header tells the agent to Read or Grep it there, as
a user's `<repo>/.sanchopanza/archive` could be. `SANCHOPANZA_PROVIDER=jev` is set explicitly.

Each call's row carries the hook's journal (`passages` and `passages_rerequest` events, written by
`harness.passages_hook`): for the call and for the arm so far, the cuts, characters in and out,
re-requests whole (and of those, `identical`: the same output again) and targeted, and the share of
cuts asked again (`r`; `r_whole` for whole ones, identical or not). **Abort, in code**: after a
call, once the arm has at least `MIN_CUTS` cuts and more than `MAX_WHOLE` of them were asked again
whole, the arm stops (`stopped: "rerequest"`, exit 5) and the report says so. It is checked between
calls: a call that loops runs on to its own cap.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run  # noqa: E402

ARMS = ("A", "A10")
FLAGS = {"A": ("--passages",), "A10": ("--passages", "--passages-fraction", "0.10")}
PROVIDER = ("--provider", "jev")
OFF = ("--no-guard", "--no-find", "--no-skill", "--context-budget", "0")
ENV = (("SANCHOPANZA_PROVIDER", "jev"),)
HOOK = "passages-hook"
MATCHER = "Bash|PowerShell|Read"  # the cut, after the tool
GUARD_MATCHER = "Write|Edit|MultiEdit|NotebookEdit"  # no rewrite from a cut view (lean edd37bb)
WIRED = sorted([("PostToolUse", MATCHER), ("PreToolUse", GUARD_MATCHER)])
DEFAULT_FRACTION = "0.25"  # the install's default (`--passages-fraction`)
WINDOW = "CLAUDE_CODE_AUTO_COMPACT_WINDOW"
# The frozen commit must carry jev-preflight and the 402 breaker (the launch's preflight).
NEEDS = {"674806b": "the 402 breaker and jev-preflight"}
ROOTS = {"A": Path(r"C:\sp-runs\L-pilot-a"), "A10": Path(r"C:\sp-runs\L-pilot-a10")}
MIN_CUTS = 10
MAX_WHOLE = 0.5
EXIT_REREQUEST = 5


def arm_spec(arm: str) -> run.Arm:
    return run.Arm((*FLAGS[arm], *PROVIDER, *OFF), env=ENV)


def fraction_of(flags: Sequence[str]) -> str:
    """The fraction the install writes (`f"{fraction:g}"`), from the arm's flags."""
    found = flags[flags.index("--passages-fraction") + 1] if "--passages-fraction" in flags else \
        DEFAULT_FRACTION  # fmt: skip
    return f"{float(found):g}"


def install_line(arm: str) -> str:
    return ("sanchopanza install --scope project --write " + " ".join(arm_spec(arm).install) +
            ", then only the passages hook (the cut and the Write guard), "
            f"env {dict(ENV)}")  # fmt: skip


# ---- the install, kept to the passages hook ------------------------------------------------------


def _commands(entry: Mapping[str, Any]) -> list[str]:
    return [str(h.get("command", "")) for h in entry.get("hooks", []) if isinstance(h, Mapping)]


def _ours(command: str) -> bool:
    words = command.split()
    return bool(words) and ("hook_env.py" in command or words[0] == "sanchopanza")


def _is_passages(command: str) -> bool:
    return command.split()[-1:] == [HOOK]


def only_passages(settings: Mapping[str, Any]) -> dict[str, Any]:
    """The settings with every sanchopanza hook but the passages one taken out (others' kept)."""
    hooks = {}
    for event, entries in (settings.get("hooks") or {}).items():
        kept = [e for e in entries if not any(_ours(c) and not _is_passages(c)
                                              for c in _commands(e))]  # fmt: skip
        hooks = {**hooks, **({event: kept} if kept else {})}
    return {**settings, "hooks": hooks}


def install_breaks(settings: Mapping[str, Any], servers: Mapping[str, Any],
                   fraction: str) -> list[str]:  # fmt: skip
    """Why the installed arm is not N plus the passages hook with Jev (empty when it is)."""
    out = []
    entries = [(event, e) for event, es in (settings.get("hooks") or {}).items() for e in es]
    ours = [(event, e.get("matcher"), c) for event, e in entries for c in _commands(e) if _ours(c)]
    if others := [c for _e, _m, c in ours if not _is_passages(c)]:
        out.append(f"sanchopanza hooks other than {HOOK}: {others}")
    wired = sorted((event, m) for event, m, c in ours if _is_passages(c))
    if wired != WIRED:
        out.append(f"{HOOK} wired as {wired}, not once on each of {WIRED}")
    env = settings.get("env") or {}
    if env.get("SANCHOPANZA_PROVIDER") != "jev":
        out.append(f"provider {env.get('SANCHOPANZA_PROVIDER')!r}, not jev")
    if env.get("SANCHOPANZA_PASSAGES_FRACTION") != fraction:
        out.append(f"fraction {env.get('SANCHOPANZA_PASSAGES_FRACTION')!r}, not {fraction}")
    if WINDOW in env:
        out.append(f"{WINDOW} set ({env[WINDOW]}): N's window is the server's")
    if servers:
        out.append(f"MCP servers {sorted(servers)}: N has none")
    return out


def install(work: Path, evidence: Path, keyfile: Path, flags: tuple[str, ...]) -> Path:
    """`run.install_sancho` with the arm's flags, then the passages hook alone, the archive's
    folder readable, and the result checked; raises (the arm does not start) on any break."""
    mcp = work / ".mcp.json"
    mcp.write_text('{"mcpServers": {}}\n', encoding="utf-8", newline="\n")  # --no-find: untouched
    run.install_sancho(work, evidence, keyfile, flags)
    path = work / ".claude" / "settings.json"
    pruned = only_passages(json.loads(path.read_text(encoding="utf-8")))
    permissions = {**(pruned.get("permissions") or {}),
                   "additionalDirectories": [(evidence / "archive").as_posix()]}  # fmt: skip
    settings = {**pruned, "permissions": permissions}
    path.write_text(json.dumps(settings, indent=2), encoding="utf-8", newline="\n")
    servers = json.loads(mcp.read_text(encoding="utf-8")).get("mcpServers") or {}
    if breaks := install_breaks(settings, servers, fraction_of(flags)):
        raise RuntimeError(f"the passages arm's install is not N + {HOOK}: {breaks}")
    (evidence / "settings.json").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    run.snapshot_install(work, evidence)
    return mcp


def passages_refusal(exe: Path) -> str:
    """Why this sanchopanza cannot run the arm ("" when `passages-hook --help` answers)."""
    try:
        done = subprocess.run([str(exe), HOOK, "--help"], capture_output=True, text=True,
                              timeout=120, env=run.child_env("", ""))  # fmt: skip
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"{exe} {HOOK} --help did not run ({error})"
    if done.returncode != 0:
        return f"{exe} has no {HOOK} (exit {done.returncode}: {(done.stderr or '')[-200:]})"
    return ""


# ---- the journal: cuts and re-requests -----------------------------------------------------------


def journal_events(journal: Path, skip: int = 0) -> list[dict[str, Any]]:
    if not journal.exists():
        return []
    out = []
    for line in journal.read_text(encoding="utf-8").splitlines()[skip:]:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and entry.get("kind") in ("passages", "passages_rerequest"):
            out.append(entry)
    return out


def _share(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def summary(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Cuts and characters of the `passages` events; re-requests of `passages_rerequest`; `r`
    and `r_whole`, the share of these cuts asked again (at all, and whole)."""
    data = [(e["kind"], e.get("data") or {}) for e in events]
    cuts = [d for k, d in data if k == "passages" and d.get("acted")]
    again = [d for k, d in data if k == "passages_rerequest"]
    ids = {d.get("tool_use_id") for d in cuts}
    asked = {d.get("cut") for d in again if d.get("cut") in ids}
    whole = {d.get("cut") for d in again if d.get("cut") in ids and d.get("kind") == "whole"}
    return {"cuts": len(cuts), "passed": sum(1 for k, d in data if k == "passages" and
                                             not d.get("acted")),  # fmt: skip
            **{k: sum(int(d.get(k) or 0) for d in cuts)
               for k in ("chars_in", "chars_out", "injected_chars")},
            "rerequests_whole": sum(1 for d in again if d.get("kind") == "whole"),
            "rerequests_whole_identical": sum(1 for d in again if d.get("kind") == "whole"
                                              and d.get("identical")),  # fmt: skip
            "rerequests_targeted": sum(1 for d in again if d.get("kind") == "targeted"),
            "cuts_rerequested": len(asked), "cuts_whole": len(whole),
            "r": _share(len(asked), len(cuts)), "r_whole": _share(len(whole), len(cuts))}


def call_facts(journal: Path, skip: int) -> dict[str, Any]:
    """The call's own events (from line `skip`) and the arm's so far."""
    return {"passages": {"call": summary(journal_events(journal, skip)),
                         "arm": summary(journal_events(journal))}}  # fmt: skip


def row_facts(evidence: Path) -> dict[str, Any]:
    """The arm's row: its whole journal, summed."""
    return {"passages": summary(journal_events(evidence / "journal.jsonl"))}


def rerequest_stop(arm: Mapping[str, Any]) -> str:
    """Why the arm stops ("" to go on): enough cuts, and too many asked again whole."""
    cuts, whole = int(arm.get("cuts") or 0), int(arm.get("cuts_whole") or 0)
    if cuts >= MIN_CUTS and whole / cuts > MAX_WHOLE:
        return (f"re-requests: {whole} of {cuts} cuts asked again whole "
                f"({whole / cuts:.2f} > {MAX_WHOLE} after >= {MIN_CUTS} cuts)")
    return ""


def plan_lines(arms: Sequence[str]) -> list[str]:
    return [*(f"  {a}: {install_line(a)}" for a in arms if a in ARMS),
            f"abort: an arm stops (stopped 'rerequest', exit {EXIT_REREQUEST}) once it has "
            f">= {MIN_CUTS} cuts and more than {MAX_WHOLE} of them were asked again whole; "
            "checked between calls"]
