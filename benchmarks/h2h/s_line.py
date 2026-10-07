"""The S arm's install line, read from `s_install.json`, run for real and checked flag by flag.

S is whatever `sanchopanza install --path <user>/settings.json --write <flags>` writes from a
frozen copy of `source` at `commit`, plus `env` in the claude process: nothing about it is
written by hand here. The file is sealed by the owner's session; an unsealed one is refused for
paid runs (`require_sealed`).

`verify` is the preflight's proof that everything on the line is installed, without a table of
what each flag should write (a new flag such as `--knowledge` needs no edit here):

- the full install exits 0 and its stderr carries none of the installer's "not wired" / "not
  registered" refusals (an option it dropped);
- leave one out: for every option on the line, the install without it must differ from the full
  one (settings, files beside them, MCP servers it prints or writes); an option that is on by
  default (`--guard`, `--skill`) must differ from the install with its `--no-` form instead,
  and an option the line writes at its default value (`--guard-profile coding`,
  `--context-budget 160000`) must differ with another value (`alternate`);
- every `sanchopanza <sub>` the settings or the MCP servers run is a subcommand of the frozen
  copy (`<sub> --help` exits 0);
- every variable in `env` is read somewhere in the frozen `src` (a misspelt name would be
  installed and ignored).

Each session's install is reduced to a digest (paths of that session replaced by placeholders)
and must equal the preflight's, so the arm cannot change in the middle of a phase.

MCP servers: a user-scope install cannot register one. It writes some into a `.mcp.json` in its
working folder (`--find`) and prints a `claude mcp add-json` line for others (`--fetch`). The
session's `--mcp-config` gets the written ones and the printed ones the line asked for, which
are those the install with no flag does not print (it prints find_in_repo's as a hint, which
the GAIA dev phase did not follow), rewritten to run the frozen copy's Python directly (Claude
Code on Windows cannot spawn the `.cmd` shim without a shell) with the same per-session home as
the hooks.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
S_INSTALL = HERE / "s_install.json"
# Options the runner owns: where the install goes, that it is applied, and the hook command.
OWNED = ("--path", "--write", "--scope", "--command-line", "--plugin-dir")
ENV_PREFIX = "SANCHOPANZA_"
# Measurement variables the runner sets; the line may not override them.
RESERVED_ENV = ("SANCHOPANZA_JOURNAL", "SANCHOPANZA_GUARD_LOG")
DROPPED = ("ANTHROPIC_", "AWS_BEARER_TOKEN_BEDROCK", "CLAUDE", "TYPESAFE_", "SANCHOPANZA_",
           "SANCHO_", "PYTHONPATH")  # fmt: skip
REFUSAL = re.compile(r"not wired|not registered|could not write", re.I)
MCP_LINE = re.compile(r"claude mcp add-json(?:\s+--scope\s+\S+)?\s+(\S+)\s+'(\{.*\})'")
INSTALL_TIMEOUT_S = 180
# A file another process holds for a moment (on this PC, a scanner reading the settings file the
# runner has just written): the install is tried again, a few times, never more.
BUSY = re.compile(r"WinError 32|being used by another process|utilizado por otro proceso", re.I)
INSTALL_TRIES = 4
BUSY_WAIT_S = 2.0


@dataclass(frozen=True)
class SLine:
    sealed: bool
    flags: tuple[str, ...]
    env: tuple[tuple[str, str], ...] = ()
    source: str | None = None  # a repository to freeze from; None: this worktree
    commit: str | None = None  # None: HEAD of `source`
    note: str = ""

    @property
    def env_map(self) -> dict[str, str]:
        return dict(self.env)


@dataclass(frozen=True)
class Installed:
    settings: dict[str, Any]
    files: dict[str, str]  # path under the user folder -> sha256 of its normalised text
    mcp_servers: dict[str, Any]
    stderr: str = ""
    raw_mcp: dict[str, Any] = field(default_factory=dict)  # before normalising, for the session
    hinted: dict[str, Any] = field(default_factory=dict)  # only printed as `add-json` lines

    @property
    def digest(self) -> str:
        blob = json.dumps([self.settings, self.files, self.mcp_servers, sorted(self.hinted)],
                          sort_keys=True)  # fmt: skip
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# --- the file -----------------------------------------------------------------------------------


def parse(raw: Mapping[str, Any]) -> SLine:
    flags = tuple(str(x) for x in raw.get("flags") or [])
    env = {str(k): str(v) for k, v in (raw.get("env") or {}).items()}
    if flags and not flags[0].startswith("--"):
        raise ValueError(f"the line must start with an option, not {flags[0]!r}")
    owned = [f for f in flags if f.split("=", 1)[0] in OWNED]
    if owned:
        raise ValueError(f"the runner owns {owned}: leave them out of the line")
    bad = sorted(k for k in env if not k.startswith(ENV_PREFIX) or k in RESERVED_ENV)
    if bad:
        raise ValueError(f"env may hold only {ENV_PREFIX}* variables the runner leaves: {bad}")
    return SLine(
        sealed=bool(raw.get("sealed")), flags=flags, env=tuple(sorted(env.items())),
        source=raw.get("source") or None, commit=raw.get("commit") or None,
        note=str(raw.get("note") or ""),
    )  # fmt: skip


def load(path: pathlib.Path = S_INSTALL) -> SLine:
    return parse(json.loads(path.read_text(encoding="utf-8")))


def require_sealed(line: SLine, allow_unsealed: bool = False) -> None:
    if not line.sealed and not allow_unsealed:
        raise SystemExit("the S install line is not sealed (s_install.json): no paid S session")
    if line.sealed and not (line.source and line.commit):
        # A null source or commit freezes this worktree's HEAD at each launch: suites started at
        # different times could run different S, and the h2h branch is not main (2026-10-06).
        raise SystemExit("a sealed S line names its source and commit; null freezes whatever "
                         "HEAD the worktree has at launch")


def options(flags: Sequence[str]) -> list[tuple[str, ...]]:
    """The line split into options: `--x`, `--x=v` or `--x v [v ...]`."""
    groups: list[tuple[str, ...]] = []
    for token in flags:
        if token.startswith("--") or not groups:
            groups = [*groups, (token,)]
        else:
            groups = [*groups[:-1], (*groups[-1], token)]
    return groups


def without(flags: Sequence[str], group: tuple[str, ...]) -> list[str]:
    return [t for g in options(flags) if g != group for t in g]


def alternate(group: tuple[str, ...], help_text: str) -> tuple[str, ...] | None:
    """Another value for a one-value option, to prove it is wired when the line writes its
    default (leaving it out then changes nothing): the first other choice `--help` lists for it,
    or the integer plus one; None for a flag or a free-text value."""
    if len(group) != 2:
        return None
    head, value = group
    listed = re.search(re.escape(head) + r"\s+\{([^}]*)\}", help_text)
    if listed:
        others = [c for c in listed.group(1).split(",") if c and c != value]
        return (head, others[0]) if others else None
    return (head, str(int(value) + 1)) if re.fullmatch(r"-?\d+", value) else None


def negation(group: tuple[str, ...]) -> tuple[str, ...] | None:
    head = group[0]
    if len(group) == 1 and "=" not in head and not head.startswith("--no-"):
        return (f"--no-{head[2:]}",)
    return None


# --- one install --------------------------------------------------------------------------------


def _normalise(text: str, places: Mapping[str, str]) -> str:
    for real, label in places.items():
        for spelling in {real, real.replace("\\", "/"), json.dumps(real)[1:-1]}:
            text = text.replace(spelling, label)
    return text


def mcp_from_output(stdout: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, blob in MCP_LINE.findall(stdout):
        out = {**out, name: json.loads(blob)}
    return out


def _clean_env(src: pathlib.Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(DROPPED)}
    return {**env, "PYTHONPATH": str(src)}


def run_install(
    config: pathlib.Path,
    src: pathlib.Path,
    flags: Sequence[str],
    cwd: pathlib.Path,
    python: str = sys.executable,
    strict: bool = True,
) -> Installed:
    """The real install into `config`, run from `cwd` (where a `.mcp.json` would land). Strict,
    an option the installer reports as dropped is an error (a leave-one-out install may drop
    one that needed the option left out: that still shows as a difference)."""
    config.mkdir(parents=True, exist_ok=True)
    cwd.mkdir(parents=True, exist_ok=True)
    argv = [python, "-m", "sanchopanza", "install", "--path", str(config / "settings.json"),
            "--write", *flags]  # fmt: skip
    for attempt in range(INSTALL_TRIES):
        done = subprocess.run(
            argv,
            cwd=cwd,
            env=_clean_env(src),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=INSTALL_TIMEOUT_S,
        )
        if done.returncode == 0 or not BUSY.search(done.stderr or ""):
            break
        if attempt + 1 < INSTALL_TRIES:
            time.sleep(BUSY_WAIT_S)
    if done.returncode != 0:
        raise RuntimeError(f"sanchopanza install failed ({done.returncode}): {done.stderr[-500:]}")
    refused = [x for x in done.stderr.splitlines() if REFUSAL.search(x)]
    if refused and strict:
        raise RuntimeError(f"sanchopanza install dropped part of the line: {refused}")
    # A try that a busy file stopped can leave its atomic write's temporary file behind (it
    # could not remove it either); the retry wrote the real one. Gone, so no digest reads it.
    for leftover in config.glob(".settings.json.*.tmp"):
        leftover.unlink()
    places = {str(config): "<config>", str(cwd): "<cwd>", str(src): "<src>"}
    settings_file = config / "settings.json"
    text = settings_file.read_text(encoding="utf-8") if settings_file.exists() else "{}"
    files = {
        p.relative_to(config).as_posix(): hashlib.sha256(
            _normalise(p.read_text(encoding="utf-8", errors="replace"), places).encode()
        ).hexdigest()[:16]
        for p in sorted(config.rglob("*"))
        if p.is_file() and p.name != "settings.json" and not p.name.startswith("settings.json")
    }  # fmt: skip
    # Registered: what the install wrote into its working folder's .mcp.json (an option asked
    # for on the line). Printed `claude mcp add-json` lines are hints a user may or may not
    # follow (the default install prints one for find_in_repo): kept apart, not registered.
    mcp: dict[str, Any] = {}
    project = cwd / ".mcp.json"
    if project.exists():
        mcp = dict(json.loads(project.read_text(encoding="utf-8")).get("mcpServers", {}))
    return Installed(
        settings=json.loads(_normalise(text, places)),
        files=files,
        mcp_servers=json.loads(_normalise(json.dumps(mcp), places)),
        stderr=done.stderr,
        raw_mcp=mcp,
        hinted=mcp_from_output(done.stdout),
    )


# --- the preflight's proof ----------------------------------------------------------------------


def subcommands(installed: Installed) -> set[str]:
    """`sanchopanza <sub>` words the settings' hooks and the MCP servers run."""
    found: set[str] = set()
    for command in re.findall(r'"command":\s*"([^"]*)"', json.dumps(installed.settings)):
        words = command.split()
        if len(words) >= 2 and words[0] == "sanchopanza":
            found.add(words[1])
    for entry in [*installed.mcp_servers.values(), *installed.hinted.values()]:
        if entry.get("command") == "sanchopanza" and entry.get("args"):
            found.add(str(entry["args"][0]))
    return found


def env_unread(line: SLine, src: pathlib.Path) -> list[str]:
    """Variables of the line that no file of the frozen `src` mentions, by full name or by the
    suffix `_env.get` takes."""
    text = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                     for p in src.rglob("*.py"))  # fmt: skip
    missing = []
    for name in line.env_map:
        suffix = name[len(ENV_PREFIX) :]
        if name not in text and f'"{suffix}"' not in text and f"'{suffix}'" not in text:
            missing.append(name)
    return missing


def _help(sub: str, src: pathlib.Path, python: str) -> subprocess.CompletedProcess:
    return subprocess.run([python, "-m", "sanchopanza", sub, "--help"], env=_clean_env(src),
                          capture_output=True, encoding="utf-8", errors="replace",
                          timeout=60)  # fmt: skip


def _help_ok(sub: str, src: pathlib.Path, python: str) -> bool:
    return _help(sub, src, python).returncode == 0


def asked_hints(full: Installed, bare: Installed) -> tuple[str, ...]:
    """The printed servers the line asked for: those the install with no flag does not print."""
    return tuple(sorted(set(full.hinted) - set(bare.hinted)))


def registered(installed: Installed, hints: Sequence[str]) -> dict[str, Any]:
    """The servers a session gets: the written ones and the asked-for printed ones."""
    return {**installed.raw_mcp, **{h: installed.hinted[h] for h in hints if h in installed.hinted}}


Proof = tuple[Installed, list[str], tuple[str, ...]]


def verify(line: SLine, src: pathlib.Path, scratch: pathlib.Path,
           python: str = sys.executable) -> Proof:  # fmt: skip
    """The full install, every problem found with the line (empty: all of it installed) and the
    printed servers it asked for."""
    full = run_install(scratch / "full" / "config", src, line.flags, scratch / "full" / "cwd",
                       python)  # fmt: skip
    bare = run_install(scratch / "bare" / "config", src, [], scratch / "bare" / "cwd", python,
                       strict=False)  # fmt: skip
    hints = asked_hints(full, bare)
    install_help = _help("install", src, python).stdout
    problems: list[str] = []
    for i, group in enumerate(options(line.flags)):
        rest = without(line.flags, group)
        other = run_install(scratch / f"loo{i}" / "config", src, rest, scratch / f"loo{i}" / "cwd",
                            python, strict=False)  # fmt: skip
        if other.digest != full.digest:
            continue
        neg = negation(group)
        if neg is not None:
            base = scratch / f"neg{i}"
            flipped = run_install(base / "config", src, [*rest, *neg], base / "cwd", python,
                                  strict=False)  # fmt: skip
            if flipped.digest != full.digest:
                continue
        other_value = alternate(group, install_help)
        if other_value is not None:  # the line writes the default: another value must show
            base = scratch / f"alt{i}"
            moved = run_install(base / "config", src, [*rest, *other_value], base / "cwd", python,
                                strict=False)  # fmt: skip
            if moved.digest != full.digest:
                continue
        problems.append(f"{shlex.join(group)} changes nothing in the install")
    for sub in sorted(subcommands(full)):
        if not _help_ok(sub, src, python):
            problems.append(f"the install runs `sanchopanza {sub}`, which the frozen copy lacks")
    problems.extend(f"{name} is not read by the frozen src" for name in env_unread(line, src))
    return full, problems, hints


# --- the session's MCP servers ------------------------------------------------------------------


def session_mcp(raw: Mapping[str, Any], src: pathlib.Path, home: pathlib.Path,
                python: str = sys.executable) -> dict[str, Any]:  # fmt: skip
    """The install's MCP servers for `--mcp-config`: `sanchopanza <args>` becomes the frozen
    copy's Python with PYTHONPATH, and HOME/USERPROFILE point at the session's own home."""
    out: dict[str, Any] = {}
    for name, entry in raw.items():
        command = str(entry.get("command") or "")
        args = list(entry.get("args") or [])
        if pathlib.Path(command).stem == "sanchopanza":
            command, args = python, ["-m", "sanchopanza", *args]
        env = {**dict(entry.get("env") or {}), "PYTHONPATH": str(src), "HOME": str(home),
               "USERPROFILE": str(home)}  # fmt: skip
        out = {**out, name: {**dict(entry), "command": command, "args": args, "env": env}}
    return out
