"""F2's free preflight: every check before the night, no paid call, no key or .env read.

- the pinned Claude Code (`claude --version` from the pin folder, and the `claude` first on the
  launcher's PATH);
- clean-user isolation: the root outside the home folder, no memory file above it; the token is
  only looked for in this process's environment (the keys file is never read here: reported as
  skipped);
- arm S as it ships: `sanchopanza install --scope project --write` (the bare defaults) and the
  runner's own install (`carry_s.S_INSTALL`) write the same files; memory's hooks are in them;
- the decider: with a dummy key, `decider_from_env` builds Jev and `httpx` imports;
- the inputs: 12 scenes, the pilot's 4, every check compiles, decoys never `near`;
- the caps: each run's cap holds at least one triple's reserve, and the three fit NIGHT_CAP;
- the seal, LIMIT.flag and STOP.

    python benchmarks/memory_carry/handoff.py --preflight [--out ROOT]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import carry  # noqa: E402
import carry_s  # noqa: E402
import handoff  # noqa: E402
from scenes_handoff import CHECKS, HANDOFF, HANDOFF_PILOT, check_code  # noqa: E402

PIN_DIR = Path.home() / ".cache" / "sanchopanza" / "claude-pin" / carry.PIN
FILES = (".claude/settings.json", ".mcp.json", ".claude/skills/sanchopanza-code/SKILL.md")
MEMORY_EVENTS = ("UserPromptSubmit", "Stop", "SessionEnd", "SessionStart")


def pin_check(pin: Path = PIN_DIR) -> tuple[bool, str]:
    exe = next((p for p in (pin / "claude.exe", pin / "claude") if p.exists()), None)
    if exe is None:
        return False, f"no claude in {pin}"
    done = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=120,
                          env={**os.environ, "DISABLE_AUTOUPDATER": "1"}, check=False)  # fmt: skip
    version = (done.stdout or done.stderr).strip()
    return version.startswith(f"{carry.PIN} "), version


def installed(args: tuple[str, ...]) -> dict[str, str]:
    """The files `sanchopanza <args>` writes in an empty folder, with the folder's path made
    neutral."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        done = subprocess.run([sys.executable, "-m", "sanchopanza", *args], cwd=repo,
                              env={**carry.environment(), "PYTHONPATH": str(carry_s.SRC)},
                              capture_output=True, text=True, timeout=120, check=False)  # fmt: skip
        if done.returncode:
            return {"error": done.stderr[-300:]}
        out = {}
        for rel in FILES:
            path = repo / rel
            text = path.read_text(encoding="utf-8") if path.exists() else "<missing>"
            for form in (str(repo), repo.as_posix(), json.dumps(str(repo))[1:-1]):
                text = text.replace(form, "<repo>")
            out[rel] = text
        return out


def s_check() -> tuple[bool, str]:
    default = installed(("install", "--scope", "project", "--write"))
    runner = installed(carry_s.S_INSTALL)
    if "error" in default or "error" in runner:
        return False, f"install failed: {default.get('error') or runner.get('error')}"
    settings = json.loads(default[".claude/settings.json"])
    hooks = settings.get("hooks") or {}
    memory = [e for e in MEMORY_EVENTS
              if any("memory-hook" in h.get("command", "") for x in hooks.get(e, [])
                     for h in x.get("hooks", []))]  # fmt: skip
    same = default == runner
    audit = (settings.get("env") or {}).get("SANCHOPANZA_MEMORY_RULES_AUDIT", "unset")
    ok = same and len(memory) == len(MEMORY_EVENTS)
    return ok, (f"runner install == bare default install: {same}; memory hooks on "
                f"{','.join(memory)}; Stop audit env {audit}")  # fmt: skip


def decider_check() -> tuple[bool, str]:
    code = (
        "from sanchopanza.harness.claude_code import decider_from_env; import httpx; "
        "print(type(decider_from_env({'TYPESAFE_API_KEY': 'dummy'})).__name__)"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          env={**carry.environment(), "PYTHONPATH": str(carry_s.SRC)},
                          timeout=120, check=False)  # fmt: skip
    name = (done.stdout or done.stderr).strip().splitlines()[-1:] or ["?"]
    return name[0] == "JevDecider", name[0]


def inputs_check() -> tuple[bool, str]:
    bad = []
    for name, scene in HANDOFF.items():
        for check in CHECKS:
            try:
                compile(check_code(scene, check), f"{name}:{check}", "exec")
            except SyntaxError as error:
                bad.append(f"{name}:{check}: {error}")
        near = {carry.DECOY_POOL[k] for k in scene["near"] if k in carry.DECOY_POOL}
        if near & set(handoff.decoys(name)) or len(handoff.decoys(name)) != carry.DECOYS:
            bad.append(f"{name}: decoys")
    ok = len(HANDOFF) == 12 and set(HANDOFF_PILOT) <= set(HANDOFF) and not bad
    return ok, f"{len(HANDOFF)} scenes, pilot {HANDOFF_PILOT}; problems: {bad or 'none'}"


def caps_check() -> tuple[bool, str]:
    lines, ok = [], True
    for run, spec in handoff.RUNS.items():
        triple = sum(handoff.reserve_of(spec["model"], arm) for arm in handoff.ARMS)
        ok = ok and spec["cap"] >= triple
        lines.append(f"{run}: cap {spec['cap']}, one triple's reserve {triple:.2f}")
    total = sum(spec["cap"] for spec in handoff.RUNS.values())
    ok = ok and total <= handoff.NIGHT_CAP
    return ok, "; ".join(lines) + f"; caps sum {total} <= night {handoff.NIGHT_CAP}"


def isolation_check(root: Path) -> tuple[bool, str]:
    home = Path.home().resolve()
    inside = root.resolve().is_relative_to(home)
    found = carry.ancestors_memory(root.resolve())
    return not inside and not found, f"root {root}; under home: {inside}; memory above: {found}"


def token_check() -> tuple[bool | None, str]:
    if os.environ.get(carry.TOKEN):
        return True, "token present in this environment (not shown)"
    return None, ("skipped: no token in this shell; the keys file SANCHOPANZA_KEYS_ENV names is "
                  "not read by the preflight")  # fmt: skip


def report(root: Path) -> list[tuple[str, bool | None, str]]:
    out: list[tuple[str, bool | None, str]] = []
    for name, fn in (("pin", pin_check), ("arm S install", s_check),
                     ("decider", decider_check), ("inputs", inputs_check),
                     ("caps", caps_check)):  # fmt: skip
        ok, detail = fn()
        out.append((name, ok, detail))
    out.append(("clean user", *isolation_check(root)))
    out.append(("token", *token_check()))
    out.append(("seal", handoff.seal_ok(), "prereg.sha256 matches" if handoff.seal_ok()
                else "not sealed or changed since"))  # fmt: skip
    flags = [str(p) for p in root.rglob("*") if p.name in ("LIMIT.flag", "STOP")] \
        if root.exists() else []  # fmt: skip
    out.append(("flags", not flags, f"LIMIT.flag/STOP: {flags or 'none'}"))
    return out


def main(root: Path) -> int:
    rows: list[Any] = report(root)
    for name, ok, detail in rows:
        mark = "ok  " if ok else "skip" if ok is None else "FAIL"
        print(f"{mark} {name}: {detail}")
    return 0 if all(ok is not False for name, ok, _ in rows if name != "seal") else 1


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else handoff.OUT))
