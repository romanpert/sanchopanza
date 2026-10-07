"""The two arms of the GAIA head-to-head, as clean users: what each session's Claude Code loads.

Both arms (2026-10-05, `docs/PLAN-COMPARACION-FINAL.md`, section 1):

- **CC (N)**: Claude Code as it ships for a new user. Each session gets its own empty
  `CLAUDE_CONFIG_DIR` (no plugins, skills, MCP servers, hooks or user CLAUDE.md), signed in
  with the subscription's `CLAUDE_CODE_OAUTH_TOKEN`, and runs in a folder outside the home
  folder: under it, Claude Code's upward CLAUDE.md search loads the owner's `~/.claude/CLAUDE.md`
  and `~/.claude/rules/*.md` as project memory even with a fresh config folder (measured with
  `/context` on 2.1.287, free). `refuse_unclean` is `--clean-user`'s guard from
  `benchmarks/memory_carry/carry.py` (memoria-f1): no token, or a memory file above the run
  folder, and nothing starts.
- **SP (S)**: the same, plus what `sanchopanza install --path <CLAUDE_CONFIG_DIR>/settings.json
  --write <flags>` writes into that user folder, with `<flags>` and the extra `SANCHOPANZA_*`
  variables read from `s_install.json` (`s_line.py`): nothing about S is fixed by hand here. The
  install runs for real per session from a frozen copy of the line's `source` at its `commit`
  (this worktree's HEAD when the line names none), and its digest must equal the one the
  preflight proved flag by flag (`s_line.verify`), so a change stops the phase instead of
  changing the arm silently. The MCP servers a user-scope install prints or writes go into the
  session's `--mcp-config`. The hooks ask Jev when `TYPESAFE_API_KEY` is set: S gets the key, N
  never does. `sanchopanza` on the hooks' PATH is a shim that runs the frozen copy with HOME and
  USERPROFILE set to the session's own folder, so memory, guard, candor and caches of one
  session never reach another one or the owner's. `SP_USER_SETTINGS` is the record of the
  default install the GAIA dev phase of 2026-10-05 ran with (empty line), kept for its test.

Both arms load `--setting-sources user`: N's user folder is empty, S's holds the install. With
`""` Claude Code reads neither user settings nor user skills (measured), so S would lose its
hooks. Measurement-only variables in S: the journal and the guard log go to the session's side
folder (`SANCHOPANZA_JOURNAL`, `SANCHOPANZA_GUARD_LOG`), and the shim logs each call
(`H2H_SHIM_LOG`), so a session whose hooks ran some other `sanchopanza` on PATH shows up;
none changes what a hook decides.

Secrets: the OAuth token and the TypeSafe key go only into the claude process's environment,
never into a file the runner writes, and every file a session leaves is scrubbed of both.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import pathlib
import subprocess
import sys
import tarfile
from collections.abc import Mapping, Sequence
from typing import Any

from sanchopanza.harness.install_defaults import window_for

TOKEN = "CLAUDE_CODE_OAUTH_TOKEN"
JEV_KEY = "TYPESAFE_API_KEY"
INDAGIS_ENV = pathlib.Path(r"C:\Users\roman\Desktop\proyectos\apps\indagis\.env")
SETTING_SOURCES = "user"
# Set explicitly in both arms, by flag and in the --settings file: a clean Claude Code 2.1.287
# starts a user folder's first session in `auto` and the later ones in `default` (2026-10-05).
PERMISSION_MODE = "default"
SKILL = pathlib.Path("skills") / "sanchopanza-code" / "SKILL.md"
# N-early (2026-10-07, indagis-6c's Ne of the long bench): a clean N whose user settings hold only
# the auto-compact window S's install writes for the line's --context-budget (160000 + the
# install's margin), so NE and S differ by the rest of S alone.
NE_BUDGET = 160_000
NE_WINDOW = window_for(NE_BUDGET)
NE_USER_SETTINGS = {"env": {"CLAUDE_CODE_AUTO_COMPACT_WINDOW": str(NE_WINDOW)}}


def _sibling(name: str, file: str) -> Any:
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, pathlib.Path(__file__).parent / file)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


s_line = _sibling("h2h_s_line", "s_line.py")
# Every variable of the caller's environment that could change what Claude Code loads, who it
# bills or what a hook decides: dropped for both arms before each arm adds its own.
DROPPED = ("ANTHROPIC_", "AWS_BEARER_TOKEN_BEDROCK", "CLAUDE", "TYPESAFE_", "SANCHOPANZA_",
           "SANCHO_", "PYTHONPATH")  # fmt: skip

_SP_HOOK = [{"type": "command", "command": "sanchopanza hook"}]
_GUARD = [{"type": "command", "command": "sanchopanza guard-hook"}]
# What `sanchopanza install --path <user>/settings.json --write` writes with no flag, after the
# fusion of browse (main 76a75d0): the hooks, the guard, the context budget and the coding
# profile. Crawl, prune, sources, fetch, candor, memory, find and the autopilot are opt-in.
SP_USER_SETTINGS: dict[str, Any] = {
    "hooks": {
        "PreToolUse": [{
            "matcher": "Agent|Bash|PowerShell|Task|WebSearch|bash|execute|run_command|shell",
            "hooks": _SP_HOOK,
        }],
        "PostToolUse": [
            {"matcher": "Agent|Task", "hooks": _SP_HOOK},
            {"matcher": "Bash", "hooks": _GUARD},
        ],
        "Stop": [],
        "UserPromptSubmit": [],
        "PreCompact": [{"matcher": "manual|auto", "hooks": _GUARD}],
        "SessionStart": [{"matcher": "compact", "hooks": _GUARD}],
    },
    "env": {
        "SANCHOPANZA_CONTEXT_BUDGET": "160000",
        "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "193000",
        "SANCHOPANZA_GUARD_PROFILE": "coding",
    },
}  # fmt: skip


# --- secrets ------------------------------------------------------------------------------------


def secret(name: str, env_file: pathlib.Path = INDAGIS_ENV) -> str:
    """A secret from the environment, else from the owner's Indagis .env (a launcher started by
    WMI gets no window variables). Never printed; a refusal names the variable only."""
    value = os.environ.get(name, "").strip()
    if not value and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}="):
                value = line.split("=", 1)[1].strip().strip('"')
    if not value:
        raise SystemExit(f"no {name} in the environment or {env_file}; refusing to start")
    return value


def scrub(root: pathlib.Path, secrets: tuple[str, ...]) -> int:
    """Replace every secret in every file under `root`; the number of files changed."""
    changed = 0
    needles = [s.encode() for s in secrets if s]
    for path in root.rglob("*") if root.is_dir() else []:
        if not path.is_file():
            continue
        try:
            blob = path.read_bytes()
        except OSError:
            continue
        clean = blob
        for needle in needles:
            clean = clean.replace(needle, b"<redacted>")
        if clean != blob:
            path.write_bytes(clean)
            changed += 1
    return changed


# --- clean user ---------------------------------------------------------------------------------


def ancestors_memory(path: pathlib.Path) -> list[str]:
    """Memory files in `path` and the folders above it that the upward CLAUDE.md search reads
    (carry.py's check, memoria-f1)."""
    found: list[str] = []
    for folder in [path, *path.parents]:
        for rel in ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md"):
            if (folder / rel).is_file():
                found.append(str(folder / rel))
        rules = folder / ".claude" / "rules"
        if rules.is_dir() and any(rules.glob("*.md")):
            found.append(str(rules))
    return found


def refuse_unclean(runs: pathlib.Path) -> None:
    """No clean user without a token, or with a memory file above the run folder."""
    secret(TOKEN)
    found = ancestors_memory(runs.resolve())
    if found:
        raise SystemExit("clean user refused: memory files above the run folder: "
                         + ", ".join(found))  # fmt: skip


# --- the frozen sanchopanza ---------------------------------------------------------------------


def head_commit(root: pathlib.Path, ref: str = "HEAD") -> str:
    done = subprocess.run(["git", "-C", str(root), "rev-parse", ref], capture_output=True,
                          text=True, check=True)  # fmt: skip
    return done.stdout.strip()


def freeze(root: pathlib.Path, runs: pathlib.Path, commit: str | None = None) -> pathlib.Path:
    """`src` at `commit` of `root` (HEAD when None), exported once into `runs/frozen/<sha>`: the
    copy S runs, whatever happens to the repository during the phase. At HEAD, refuses a `src`
    with uncommitted changes."""
    if commit is None:
        argv = ["git", "-C", str(root), "status", "--porcelain", "--", "src"]
        dirty = subprocess.run(argv, capture_output=True, text=True, check=True).stdout.strip()
        if dirty:
            raise SystemExit("src has uncommitted changes: commit before freezing the SP arm")
    sha = head_commit(root, commit or "HEAD")
    target = runs / "frozen" / sha
    if not (target / "src" / "sanchopanza").is_dir():
        blob = subprocess.run(["git", "-C", str(root), "archive", "--format=tar", sha, "src"],
                              capture_output=True, check=True).stdout  # fmt: skip
        with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
            tar.extractall(target, filter="data")
    return target


def write_shim(frozen: pathlib.Path, python: str = sys.executable) -> pathlib.Path:
    """`bin/sanchopanza` (a POSIX shell script: Claude Code runs hooks through Git Bash on
    Windows) and `bin/sanchopanza.cmd`, both running the frozen `src` with `python`, and both
    moving HOME and USERPROFILE to `H2H_SP_HOME` when it is set (every sanchopanza store under
    the home folder becomes the session's own)."""
    src = (frozen / "src").resolve()
    folder = frozen / "bin"
    folder.mkdir(parents=True, exist_ok=True)
    py = pathlib.Path(python)
    log = '[ -n "$H2H_SHIM_LOG" ] && echo "$*" >> "$H2H_SHIM_LOG"\n'
    home = ('[ -n "$H2H_SP_HOME" ] && export HOME="$H2H_SP_HOME" '
            'USERPROFILE="$H2H_SP_HOME"\n')  # fmt: skip
    sh = (f'#!/bin/sh\n{log}{home}PYTHONPATH="{src.as_posix()}" exec "{py.as_posix()}" '
          '-m sanchopanza "$@"\n')  # fmt: skip
    (folder / "sanchopanza").write_text(sh, encoding="utf-8", newline="\n")
    cmd = ('@echo off\r\nif defined H2H_SHIM_LOG echo %*>> "%H2H_SHIM_LOG%"\r\n'
           'if defined H2H_SP_HOME set "USERPROFILE=%H2H_SP_HOME%"\r\n'
           'if defined H2H_SP_HOME set "HOME=%H2H_SP_HOME%"\r\n'
           f'set "PYTHONPATH={src}"\r\n"{py}" -m sanchopanza %*\r\n')  # fmt: skip
    (folder / "sanchopanza.cmd").write_text(cmd, encoding="utf-8", newline="")
    return folder


# --- per session --------------------------------------------------------------------------------


def install_sp(config: pathlib.Path, src: pathlib.Path, flags: Sequence[str] = (),
               cwd: pathlib.Path | None = None, python: str = sys.executable) -> Any:  # fmt: skip
    """The real `sanchopanza install <flags>` into this user's settings (`s_line.Installed`)."""
    return s_line.run_install(config, src, flags, cwd or config.parent / "install-cwd", python)


def check_sp(installed: Any, expected: str | None) -> None:
    """The session's install against the preflight's digest."""
    if expected is not None and installed.digest != expected:
        raise RuntimeError(f"sanchopanza install wrote another S ({installed.digest}) than the "
                           f"preflight proved ({expected})")  # fmt: skip


def prepare_config(brazo: str, config: pathlib.Path, src: pathlib.Path | None,
                   flags: Sequence[str] = (), expected: str | None = None) -> Any:  # fmt: skip
    """An empty user folder for CC (None); the line's install for SP (`s_line.Installed`)."""
    config.mkdir(parents=True, exist_ok=True)
    if brazo == "NE":
        (config / "settings.json").write_bytes(json.dumps(NE_USER_SETTINGS).encode("utf-8"))
        return None
    if brazo != "SP":
        return None
    if src is None:
        raise ValueError("the SP arm needs the frozen sanchopanza src")
    installed = install_sp(config, src, flags)
    check_sp(installed, expected)
    return installed


def session_env(
    brazo: str,
    config: pathlib.Path,
    side: pathlib.Path,
    shim: pathlib.Path | None,
    base: Mapping[str, str] | None = None,
    line_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """The claude process's environment. Both arms: nothing of the caller's Claude, Anthropic,
    TypeSafe or sanchopanza variables; this session's user folder and the subscription token;
    the deny hook's log; no auto-update. SP adds the line's variables, the Jev key, the shim,
    its own home and its two logs."""
    source = dict(os.environ if base is None else base)
    env = {k: v for k, v in source.items() if not k.upper().startswith(DROPPED)}
    env = {**env, "CLAUDE_CONFIG_DIR": str(config), TOKEN: secret(TOKEN),
           "H2H_DENY_LOG": str(side / "denied.jsonl"), "DISABLE_AUTOUPDATER": "1"}  # fmt: skip
    if brazo != "SP":
        return env
    if shim is None:
        raise ValueError("the SP arm needs the sanchopanza shim on PATH")
    path_key = next((k for k in env if k.upper() == "PATH"), "PATH")
    return {
        **env,
        **dict(line_env or {}),
        JEV_KEY: secret(JEV_KEY),
        "SANCHOPANZA_JOURNAL": str(side / "journal.jsonl"),
        "SANCHOPANZA_GUARD_LOG": str(side / "guard.jsonl"),
        "H2H_SHIM_LOG": str(side / "shim.log"),
        "H2H_SP_HOME": str(side / "home"),
        path_key: f"{shim}{os.pathsep}{env.get(path_key, '')}",
    }


def secrets_of(env: Mapping[str, str]) -> tuple[str, ...]:
    return tuple(v for k, v in env.items() if k in (TOKEN, JEV_KEY) and v)
