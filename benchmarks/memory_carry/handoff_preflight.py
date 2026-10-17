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


def user_check(tmp: Path | None = None) -> tuple[bool, str]:
    """W17's S' as it ships at user scope: the runner's install into an arm's configuration
    folder (`carry_s.install_user`, before its commands are rewired) writes the same settings and
    skill as a bare `sanchopanza install --write` writes into `~/.claude` (the home pointed at an
    empty folder); memory's hooks are in them; no `.mcp.json` and no MCP approval anywhere."""
    with tempfile.TemporaryDirectory() as scratch:
        base = Path(tmp or scratch)
        run, home, cwd = base / "arm", base / "home", base / "cwd"
        for folder in (run / "claude-config", home, cwd):
            folder.mkdir(parents=True, exist_ok=True)
        try:
            carry_s.install_user(run, run / "claude-config", base / "k", carry.environment())
        except RuntimeError as error:
            return False, f"runner's user install failed: {error}"
        env = {**carry.environment(), "PYTHONPATH": str(carry_s.SRC), "HOME": str(home),
               "USERPROFILE": str(home)}  # fmt: skip
        done = subprocess.run([sys.executable, "-m", "sanchopanza", "install", "--write"],
                              cwd=cwd, env=env, capture_output=True, text=True, timeout=120,
                              check=False)  # fmt: skip
        if done.returncode:
            return False, f"bare install failed: {done.stderr[-300:]}"
        written = run / "install" / "as-written"
        same = all((written / rel).is_file() and (home / ".claude" / rel).is_file()
                   and (written / rel).read_text(encoding="utf-8")
                   == (home / ".claude" / rel).read_text(encoding="utf-8")
                   for rel in carry_s.U_INSTALLED)  # fmt: skip
        settings = json.loads((written / "settings.json").read_text(encoding="utf-8"))
        hooks = settings.get("hooks") or {}
        memory = [e for e in MEMORY_EVENTS
                  if any("memory-hook" in h.get("command", "") for x in hooks.get(e, [])
                         for h in x.get("hooks", []))]  # fmt: skip
        mcp = [str(p) for p in base.rglob(".mcp.json")]
        approved = "enabledMcpjsonServers" in settings
        ok = same and len(memory) == len(MEMORY_EVENTS) and not mcp and not approved
        return ok, (f"runner user install == bare `install --write` in ~/.claude: {same}; memory "
                    f"hooks on {','.join(memory)}; .mcp.json: {mcp or 'none'}; MCP approval: "
                    f"{approved}")  # fmt: skip


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


def caps_check(lot: str = "f2") -> tuple[bool, str]:
    lines, ok = [], True
    runs = handoff.LOTS[lot]["sequence"]
    night_cap = handoff.NIGHT_CAP if lot == "f2" else float(handoff.LOTS[lot]["night_cap"])
    for run in runs:
        spec = handoff.RUNS[run]
        triple = sum(handoff.reserve_of(spec["model"], arm, run) for arm in handoff.arms_of(run))
        ok = ok and spec["cap"] >= triple
        lines.append(f"{run}: cap {spec['cap']}, one triple's (pair's) reserve {triple:.2f}")
    total = sum(handoff.RUNS[r]["cap"] for r in runs)
    if lot == "f2":
        ok = ok and total <= night_cap
        return ok, "; ".join(lines) + f"; caps sum {total} <= night {night_cap}"
    # W17: each run's cap is min(its cap, night cap - the other run's spend in the same root)
    # in code, so the night cap binds the two together where both run. The redo's root
    # (Amendment 1) refuses w17-sonnet, so there w17-opus runs under its own cap alone.
    ok = ok and all(handoff.RUNS[r]["cap"] <= night_cap for r in runs)
    return ok, "; ".join(lines) + (f"; each <= night {night_cap}, which binds both where both run;"
                                   " the redo's root runs only w17-opus")  # fmt: skip


def isolation_check(root: Path, work: Path | None = None) -> tuple[bool, str]:
    """The lot's root and the agents' work root: outside the home folder, no memory file above
    them; the work root's path names nothing of the lot (handoff.WORK)."""
    work = work or handoff.WORK
    home = Path.home().resolve()
    inside = [str(p) for p in (root, work) if p.resolve().is_relative_to(home)]
    found = carry.ancestors_memory(root.resolve()) + carry.ancestors_memory(work.resolve())
    words = ("memory", "f2", "handoff", "sonnet", "opus", "w17", "lot", "bare")
    named = [w for w in words if w in str(work).lower()]
    ok = not inside and not found and not named
    return ok, (f"root {root}, work {work}; under home: {inside or 'none'}; memory above: "
                f"{found or 'none'}; names in the work path: {named or 'none'}")  # fmt: skip


def token_check() -> tuple[bool | None, str]:
    if os.environ.get(carry.TOKEN):
        return True, "token present in this environment (not shown)"
    return None, ("skipped: no token in this shell; the keys file SANCHOPANZA_KEYS_ENV names is "
                  "not read by the preflight")  # fmt: skip


def report(root: Path, lot: str = "f2") -> list[tuple[str, bool | None, str]]:
    out: list[tuple[str, bool | None, str]] = []
    install = ("arm S install", s_check) if lot == "f2" else ("arm S' user install", user_check)
    for name, fn in (("pin", pin_check), install, ("decider", decider_check),
                     ("inputs", inputs_check), ("caps", lambda: caps_check(lot))):  # fmt: skip
        ok, detail = fn()
        out.append((name, ok, detail))
    out.append(("clean user", *isolation_check(root, Path(handoff.LOTS[lot]["work"]))))
    out.append(("token", *token_check()))
    results, fixed = handoff.handoff_seal.LOTS[lot]
    sealed = handoff.seal_ok(handoff.handoff_seal.REPO, results, fixed)
    out.append(("seal", sealed, "prereg.sha256 matches" if sealed
                else "not sealed or changed since"))  # fmt: skip
    flags = [str(p) for p in root.rglob("*") if p.name in ("LIMIT.flag", "STOP")] \
        if root.exists() else []  # fmt: skip
    out.append(("flags", not flags, f"LIMIT.flag/STOP: {flags or 'none'}"))
    return out


def main(root: Path, lot: str = "f2") -> int:
    rows: list[Any] = report(root, lot)
    for name, ok, detail in rows:
        mark = "ok  " if ok else "skip" if ok is None else "FAIL"
        print(f"{mark} {name}: {detail}")
    return 0 if all(ok is not False for name, ok, _ in rows if name != "seal") else 1


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else handoff.OUT))
