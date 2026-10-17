"""What `long-smoke-run.cmd`, `long-gate-run.cmd` and `long-pilot-a-run.cmd` run, once the window
has set the PATH (the pinned Claude Code first) and checked its version: the checks before any
spending, the expected cost and the caps, the Jev preflight for installed arms (S, A, A10), the
runner per model, the grade and the windows.

    python benchmarks/adopt/long_launch.py smoke --seal <commit> [--root C:\\sp-runs\\L-smoke]
    python benchmarks/adopt/long_launch.py gate [--root C:\\sp-runs\\L]
    python benchmarks/adopt/long_launch.py pilot-a --commit <commit> [--arm A|A10]
    python benchmarks/adopt/long_launch.py plan smoke|gate|pilot-a [--arm A10]  # the plan only
    python benchmarks/adopt/long_launch.py guardptr --seal <commit>   # also guardptr-30, -smoke

In order, and nothing paid before the last:
1. SIGINT ignored; the run folder gets `launch.json` with this process's PID, its parent's (the
   launcher window's `cmd.exe`) and each runner's PID as it starts (kill only by PID, verified:
   `long_run.py kill --root <root>`).
2. Refused (exit 1) when a runner of this root is alive, a chain has no valid manifest with the
   digest of the chain in the cache (`long60/<chain>.json`), or the caps do not fit the ceiling.
3. The expected cost (`costmodel.expected`) and every cap, printed and written to `plan.txt`.
4. Arms S (the seal) and A/A10 (`--commit`, `pilot_sancho`: the 402 breaker in its history and
   `passages-hook --help` answering in the frozen copy, the pilot of bet A, `long_pilot`) only:
   the frozen sanchopanza of the seal commit (built by `freeze.py`, with gate A and
   the 402 breaker in its history) and `python -m sanchopanza jev-preflight` with it, which
   exits 0 ok, 10 no_funds, 11 auth, 12 no_key, 13 unreachable, 14 other; any other code than 0
   ends the launch with that code before a model is asked anything. A keyless profile (the
   guard-pointers lot: P and F, `--seal` its own commit, `GUARDPTR_NEEDS` in its history) runs
   the frozen copy too, and no preflight: no key is read and no decision is asked.
5. The runner (`long_run.py run`), per model: the gate runs Opus only when Sonnet exits 0.
   A second launch resumes: finished arms are skipped and a stopped one goes on at its next
   request (`long_resume`).
6. The grade (free, pytest in Docker), the gate table and `windows.json` (each model's window as
   its sessions reported it).

`--dry-config <json>` (tests and the dry run only): a stand-in runner and `claude`, chains,
manifests, limit flag, the sanchopanza and preflight to use, and extra environment.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "memory_carry"))

import carry  # noqa: E402
import costmodel  # noqa: E402
import freeze  # noqa: E402
import guardptr_seal  # noqa: E402
import long_guard  # noqa: E402
import long_money  # noqa: E402
import long_pilot  # noqa: E402
import long_pointers  # noqa: E402
import long_run  # noqa: E402
import meter  # noqa: E402
import run  # noqa: E402
from sanchopanza import durable  # noqa: E402  (src/: long_run)

ROOTS = {"smoke": Path(r"C:\sp-runs\L-smoke"), "gate": Path(r"C:\sp-runs\L"),
         "pilot-a": long_pilot.ROOTS["A"],  # A10: long_pilot.ROOTS["A10"] (`root_for`)
         "noise-ne": Path(r"C:\sp-runs\L-ne"), "noise-n": Path(r"C:\sp-runs\L-n2"),
         "conan-n2": Path(r"C:\sp-runs\L-n2c"), "conan-ne2": Path(r"C:\sp-runs\L-ne2c"),
         "conan-a2": Path(r"C:\sp-runs\L-a2c"),
         # the context close-out (2026-10-13); its conditional sixth chain under the same root
         "compact": Path(r"C:\sp-runs\L-compact"),
         "compact-fifth": Path(r"C:\sp-runs\L-compact"),
         "compact-extra": Path(r"C:\sp-runs\L-compact"),
         # the conan-2 repeat (owner 2026-10-14, 45 USD hard): its own root, its own ceiling
         "compact-conan2": Path(r"C:\sp-runs\L-compact-conan2"),
         # the guard-pointers lot (2026-10-16): its own roots, ceilings and the smoke apart
         "guardptr": Path(r"C:\sp-runs\L-guardptr"),
         "guardptr-30": Path(r"C:\sp-runs\L-guardptr30"),
         "guardptr-smoke": Path(r"C:\sp-runs\L-guardptr-smoke")}
# Profiles that run only from their sealing commit (`guardptr_seal.require_seal`); a dry run
# checks it too when its config names a sealed repository (`seal_repo`).
SEALED_LOTS = long_pointers.SEALED_LOTS
# Profiles the launcher does not grade: `long_pointers_read.py grade` does, every chain with the
# per-test timeout its prereg registers (the close-out's moto grade hung 16 minutes without one).
GRADED_APART = {"guardptr": 300, "guardptr-30": 300, "guardptr-smoke": 300}
# What the guard-pointers lot's frozen copy must carry: the pointer guard as the default, its
# review fixes (archive every one-shot output, masked) and --guard-full's marked chooser.
GUARDPTR_NEEDS = {"bc2a0ac": "the pointer guard as the default chooser",
                  "4998684": "the pointer guard's review fixes (archive all, mask_strict)",
                  "6e2a1a1": "--guard-full's marked chooser"}  # fmt: skip
# The seal must carry these (main): gate A for check-done and candor, and the 402 breaker with
# `jev-preflight`. An older frozen copy would run S without them.
SEAL_NEEDS = {"f2a0fe2": "gate A (check-done and candor on change or action)",
              "674806b": "the 402 breaker and jev-preflight"}  # fmt: skip
SEAL_COMMIT = "cb0062e"  # S sealed by the owner, 2026-10-06 (guard struct over 6 parts)
PREFLIGHT = ("-m", "sanchopanza", "jev-preflight")
PREFLIGHT_CODES = {0: "ok", 10: "no_funds", 11: "auth", 12: "no_key", 13: "unreachable",
                   14: "other"}  # fmt: skip


def log(message: str) -> None:
    print(f"{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {message}", flush=True)


# ---- the run folder and its PIDs -----------------------------------------------------------------


def note_pids(root: Path, **pids: Any) -> dict[str, Any]:
    """`launch.json`: this launch's PIDs (with command line and creation date, for a verified
    kill), appended to the earlier launches' so a resume keeps the history."""
    path = root / "launch.json"
    history = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    if pids.get("new"):
        mine = {"started": dt.datetime.now().isoformat(timespec="seconds"),
                "launcher": _process(os.getpid()), "window": _process(os.getppid())}  # fmt: skip
        history = [*history, mine]
    else:
        history = [*history[:-1], {**history[-1], **{k: v for k, v in pids.items()}}]
    durable.replace_text(path, json.dumps(history, indent=1), newline="\n")
    return history[-1]


def _process(pid: int) -> dict[str, Any]:
    return {"pid": pid, **(long_guard.process_info(pid) or {})}


def busy(root: Path) -> str:
    """Why another launch of this root may still be running ("" when none is): the launcher
    before this one, or the runner its status file names, alive with the same command line and
    creation date."""
    launches = root / "launch.json"
    history = json.loads(launches.read_text(encoding="utf-8")) if launches.exists() else []
    if len(history) > 1:
        before = history[-2].get("launcher") or {}
        live = long_guard.process_info(int(before.get("pid") or 0)) if before.get("pid") else None
        if live and live.get("command_line") == before.get("command_line") and \
                live.get("created") == before.get("created"):  # fmt: skip
            return f"the launcher {before['pid']} of this root is still running"
    status = root / "long-run.status.json"
    if status.exists():
        found = json.loads(status.read_text(encoding="utf-8"))
        live = long_guard.process_info(int(found.get("pid") or 0)) if found.get("pid") else None
        if live and live.get("command_line") == found.get("command_line") and \
                live.get("created") == found.get("created"):  # fmt: skip
            return f"the runner {found['pid']} of this root is still running"
    return ""


# ---- what is expected and what is held -----------------------------------------------------------


def low_window() -> int:
    """N-early-low's window: what `install --context-budget 67000` writes (100,000)."""
    return long_run.window_for(long_run.COMPACT_LOW_BUDGET)


def turn_lines(profile: Any, model: str) -> list[str]:
    """Per arm, the worst turn past a cap (`long_money`: the context at the window, written to
    the cache at the 1-hour rate, plus a maximal answer) and where the arm stops at the latest."""
    mid, cap, chain = run.MODELS[model], profile.call_cap[model], profile.chain_cap[model]
    out = []
    for arm in profile.arms:  # N and the passages arms: the server's window
        window = long_money.DEFAULT_WINDOW[mid] if arm in ("N", *long_pilot.ARMS) else \
            low_window() if arm == "Nl" else profile.window  # fmt: skip
        worst = long_money.turn_cost(mid, window)
        out.append(f"  {arm}: one turn past a cap costs up to {worst:.2f} USD (context at the "
                   f"window {window}); at that context the arm starts no call past "
                   f"{chain - cap - worst:.2f} spent of its {chain:.2f}")  # fmt: skip
    return out


def modelled(arm: str) -> str:
    """The arm whose cost model an arm borrows: a passages arm N's (its effect is what the pilot
    asks), N-early-low N-early's (its saving is what the close-out asks: an upper side), and the
    guard lot's P and F N-early's too (the default install compacts at N-early's window)."""
    return "N" if arm in long_pilot.ARMS else "Ne" if arm in ("Nl", "P", "F") else arm


def expected(model: str, bugs: int, calls: int, profile: Any) -> dict[str, tuple[float, float]]:
    """`costmodel.expected` per arm, each at the model `modelled` names."""
    model_arms = tuple(dict.fromkeys(modelled(a) for a in profile.arms))
    found = costmodel.expected(model, bugs, calls, model_arms, profile.budget)
    return {a: found[modelled(a)] for a in profile.arms}


def plan_lines(name: str, chains: Mapping[str, Any], names: list[str], root: Path,
               ceiling: float, arms: tuple[str, ...] = ()) -> list[str]:  # fmt: skip
    """The expected cost per chain and arm, and every cap, as printed before anything runs."""
    import long

    profile = long_run.PROFILES[name].with_arms(arms)
    layout = long_run.Layout(root)
    spent = long_run.spent(layout)
    lines, low, high = [], 0.0, 0.0
    for model in profile.models:
        cap = profile.call_cap[model]
        cc = meter.claude_code_cap(cap, run.MODELS[model])
        lines.append(f"{model} ({run.MODELS[model]}): {cap:.2f} USD per call (--max-budget-usd "
                     f"at most {cc:.2f} in Claude Code's prices, less one turn), "
                     f"{profile.chain_cap[model]:.2f} per chain and arm, arms "
                     f"{', '.join(profile.arms)}")  # fmt: skip
        lines += turn_lines(profile, model)
        for chain in names:
            found = chains.get(chain)
            bugs = profile.bugs or (len(found["bugs"]) if found else long.SIZE60)
            calls = len(long.callbacks(bugs))
            exp = expected(model, bugs, calls, profile)
            low += sum(v[0] for v in exp.values())
            high += sum(v[1] for v in exp.values())
            each = ", ".join(f"{a} {v[0]:.2f}-{v[1]:.2f}" for a, v in exp.items())
            state = "" if found else " (not in the validated cache yet)"
            note = ("; passages arms at N's cost model (not modelled)"
                    if set(profile.arms) & set(long_pilot.ARMS) else "")  # fmt: skip
            lines.append(f"  {chain}{state}: {bugs} bugs + {calls} callbacks; expected {each} USD"
                         f"{note}")  # fmt: skip
    blocks, outside = long_run.held(layout, profile, names, list(profile.models))
    holding = sum(c for *_x, c in blocks) + outside
    pre, peak = long_pointers.bounds(profile.budget)
    lines += [f"expected total {low:.2f}-{high:.2f} USD (cost model, check-done 'mid'; "
              "uncapped, list prices)",
              f"caps held {holding:.2f} USD (each chain at the larger of its caps and its "
              f"spend); spent under the root so far {spent:.2f}; ceiling "
              f"{ceiling:.2f}{' (hard, in code)' if profile.hard_cap else ''}; a call starts "
              "only with room for its cap and one more turn under each cap and the ceiling",
              *([f"N-early window {profile.window} (S's install for --context-budget "
                 f"{profile.budget}); N's window: the server's, recorded in windows.json"]
                if {"Ne", "S"} & set(profile.arms) else
                [f"P and F: the install's window {profile.window} (--context-budget "
                 f"{profile.budget}); a compaction outside {pre}, a context past {peak} or a "
                 "compaction without its arm's guard stops the run"]
                if {"P", "F"} & set(profile.arms) else
                ["window: the server's (no arm sets one), recorded in windows.json"]),
              *([f"N-early-low window {low_window()} (the install's for --context-budget "
                 f"{long_run.COMPACT_LOW_BUDGET}), compacting near "
                 f"{long_run.COMPACT_LOW_BUDGET}: a compaction outside {long_run.LOW_PRE} or "
                 f"a call past {long_run.LOW_PEAK} of context stops the run"]
                if "Nl" in profile.arms else [])]
    return [*lines, *(long_pilot.plan_lines(profile.arms)
                      if set(profile.arms) & set(long_pilot.ARMS) else [])]


# ---- S: the sealed sanchopanza and the preflight -------------------------------------------------


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)


def frozen_sancho(seal: str, sealed_at: str | None = SEAL_COMMIT,
                  needs: Mapping[str, str] = SEAL_NEEDS) -> Path:  # fmt: skip
    """The frozen copy of the seal commit, refused when it is missing or lacks what S needs
    (`sealed_at`: the one commit allowed; None for the pilot's, checked by `pilot_sancho`)."""
    done = git("rev-parse", "--verify", f"{seal}^{{commit}}")
    if done.returncode != 0 or not seal:
        raise SystemExit(f"refused: {seal!r} is not a commit")
    full = done.stdout.strip()
    for commit, what in needs.items():
        if git("merge-base", "--is-ancestor", commit, full).returncode != 0:
            raise SystemExit(f"refused: the seal {full[:12]} does not carry {commit} ({what})")
    if sealed_at and full != git("rev-parse", f"{sealed_at}^{{commit}}").stdout.strip():
        raise SystemExit(f"refused: S is sealed at {sealed_at}, not {full[:12]}")
    target = freeze.ROOT / f"{full[:12]}-{'-'.join(freeze.EXTRAS)}"
    exe = target / "Scripts" / "sanchopanza.exe"
    stamp = target / "stamp.json"
    if not exe.exists() or not stamp.exists():
        raise SystemExit(f"refused: no frozen sanchopanza for {full[:12]}; build it with "
                         f"`python benchmarks/adopt/freeze.py {full}` (free)")  # fmt: skip
    found = json.loads(stamp.read_text(encoding="utf-8"))
    if found.get("commit") != full or set(freeze.EXTRAS) - set(found.get("extras") or []):
        raise SystemExit(f"refused: {stamp} is not the {full[:12]} copy with {freeze.EXTRAS}")
    return exe


def pilot_sancho(commit: str) -> Path:
    """The frozen copy of the pilot's own commit (any, not the seal), refused unless it carries
    the 402 breaker and its `passages-hook --help` answers."""
    exe = frozen_sancho(commit, None, long_pilot.NEEDS)
    if why := long_pilot.passages_refusal(exe):
        raise SystemExit(f"refused: {why}")
    return exe


def installed_sancho(profile: Any, cfg: Mapping[str, Any], args: argparse.Namespace) -> Path:
    """The frozen sanchopanza the installed arms run (dry: the configured one, still checked for
    `passages-hook` when a passages arm runs). A keyless profile: the copy of its own seal."""
    pilot = bool(set(profile.arms) & set(long_pilot.ARMS))
    if not cfg.get("sancho") and profile.keyless:
        return frozen_sancho(args.seal or "", None, GUARDPTR_NEEDS)
    if not cfg.get("sancho"):
        return pilot_sancho(args.commit) if pilot else frozen_sancho(args.seal or "")
    exe = Path(cfg["sancho"])
    if pilot and (why := long_pilot.passages_refusal(exe)):
        raise SystemExit(f"refused: {why}")
    return exe


def preflight(python: Path, root: Path, pythonpath: str = "") -> int:
    """`python -m sanchopanza jev-preflight` with the sanchopanza S runs (its own Python, no
    PYTHONPATH of ours), the key only in its environment. One real decision, ~13 micro-USD."""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    key = carry.from_harness_env("TYPESAFE_API_KEY")
    env = {**env, **({"TYPESAFE_API_KEY": key} if key else {}),
           **({"PYTHONPATH": pythonpath} if pythonpath else {})}  # fmt: skip
    done = subprocess.run([str(python), *PREFLIGHT], env=env, capture_output=True, text=True,
                          timeout=120)  # fmt: skip
    text = (done.stdout + done.stderr).strip()
    with (root / "preflight.txt").open("a", encoding="utf-8") as out:
        out.write(f"{dt.datetime.now().isoformat(timespec='seconds')} exit {done.returncode} "
                  f"({PREFLIGHT_CODES.get(done.returncode, 'unknown')}) {text}\n")  # fmt: skip
    log(f"jev preflight: exit {done.returncode} "
        f"({PREFLIGHT_CODES.get(done.returncode, 'unknown')}): {text[-300:]}")
    return done.returncode


# ---- the runs ------------------------------------------------------------------------------------


def runner_cmd(cfg: Mapping[str, Any], action: str, profile: str, root: Path,
               model: str | None, arms: tuple[str, ...] = ()) -> list[str]:  # fmt: skip
    script = cfg.get("runner") or str(HERE / "long_run.py")
    cmd = [sys.executable, "-u", script, action, "--profile", profile, "--root", str(root),
           "--manifests", str(cfg.get("manifests") or long_run.MANIFESTS),
           *(["--arms", ",".join(arms)] if arms else [])]  # fmt: skip
    cmd += ["--model", model] if model else []
    if action != "run":
        return [*cmd, *(["--chains-file", cfg["chains_file"]] if cfg.get("chains_file") else [])]
    extra = {"--limit-flag": cfg.get("limit_flag"), "--chains-file": cfg.get("chains_file"),
             "--claude": json.dumps(cfg["claude"]) if cfg.get("claude") else None}  # fmt: skip
    cmd += [x for k, v in extra.items() if v for x in (k, str(v))]
    return [*cmd, *(["--allow-midnight"] if cfg.get("allow_midnight") else [])]


def run_step(cmd: list[str], env: Mapping[str, str], log_file: Path, label: str,
             root: Path) -> int:  # fmt: skip
    with log_file.open("ab") as out:
        child = subprocess.Popen(cmd, cwd=REPO, env=dict(env), stdout=out, stderr=subprocess.STDOUT)
        note_pids(root, **{label: _process(child.pid)})
        log(f"{label}: PID {child.pid}, log {log_file}")
        code = child.wait()
    note_pids(root, **{f"{label}_exit": code})
    log(f"{label}: exit {code}")
    return code


def runs(name: str, cfg: Mapping[str, Any], root: Path, env: Mapping[str, str],
         arms: tuple[str, ...] = ()) -> int:  # fmt: skip
    """The runner per model in order; the gate's Opus only after Sonnet exits 0."""
    for model in long_run.PROFILES[name].models:
        code = run_step(runner_cmd(cfg, "run", name, root, model, arms), env,
                        root / f"runner-{model}.log", f"runner_{model}", root)  # fmt: skip
        if code != 0:
            return code
    return 0


def windows(root: Path) -> None:
    path = root / "windows.json"
    found = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for model, arms in found.items():
        for arm, w in arms.items():
            log(f"window {model} {arm}: {w.get('value')} (effective {w.get('effective_reported')}"
                f", source {w.get('source')})")
    if not found:
        log("window: no session reported one yet")


# ---- entry ---------------------------------------------------------------------------------------


def root_for(name: str, args: argparse.Namespace, cfg: Mapping[str, Any]) -> Path:
    default = long_pilot.ROOTS[args.arm or "A"] if name == "pilot-a" else ROOTS[name]
    return Path(args.root or cfg.get("root") or default)


def launch(name: str, args: argparse.Namespace) -> int:
    carry.ignore_interrupts()
    cfg = json.loads(Path(args.dry_config).read_text(encoding="utf-8")) if args.dry_config else {}
    root = root_for(name, args, cfg)
    arms = (args.arm,) if args.arm else ()
    root.mkdir(parents=True, exist_ok=True)
    note_pids(root, new=True)
    if why := busy(root):
        log(f"refused: {why}")
        return 1
    profile = long_run.PROFILES[name].with_arms(arms)
    if name in SEALED_LOTS and (not cfg or cfg.get("seal_repo")):
        try:  # before anything else: HEAD the sealing commit, clean, the seal, the launcher
            head = guardptr_seal.require_seal(os.environ.get(guardptr_seal.LAUNCHER_VAR, ""),
                                              args.seal, Path(cfg.get("seal_repo") or REPO))
        except SystemExit as refused:
            log(f"refused: {refused}")
            return 1
        log(f"HEAD {head} (the sealing commit); frozen copy {args.seal} (its parent)")
        with (root / "launch.status").open("a", encoding="utf-8") as status:
            status.write(f"seal HEAD {head}\n")
    known = (json.loads(Path(cfg["chains_file"]).read_text(encoding="utf-8"))
             if cfg.get("chains_file") else run.chains())  # fmt: skip
    names = list(profile.chains)
    manifests = Path(cfg.get("manifests") or long_run.MANIFESTS)
    if missing := [n for n in names if n not in known]:
        log(f"refused: chains not in the cache {missing}")
        return 1
    if why := long_guard.manifest_refusal(names, known, manifests, run.chain_digest):
        log(f"refused: {why}")
        return 1
    ceiling = profile.ceiling
    lines = plan_lines(name, known, names, root, ceiling, arms)
    (root / "plan.txt").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    for line in lines:
        log(line)
    blocks, outside = long_run.held(long_run.Layout(root), profile, names, list(profile.models))
    if why := long_guard.plan_refusal(blocks, ceiling, outside):
        log(f"refused: {why}")
        return 1
    env = {**os.environ, **(cfg.get("env") or {}), "PYTHONUNBUFFERED": "1",
           "ADOPT_PYTHON": os.environ.get("ADOPT_PYTHON") or sys.executable}  # fmt: skip
    if name in SEALED_LOTS:  # the runner checks the seal again itself (`long_run.seal_refusal`)
        env = {**env, guardptr_seal.INSTRUMENT_VAR: args.seal,
               **({guardptr_seal.REPO_VAR: str(cfg["seal_repo"])} if cfg.get("seal_repo")
                  else {})}  # fmt: skip
    if installing := [a for a in profile.arms if long_run.installed(a, profile)]:
        try:
            exe = installed_sancho(profile, cfg, args)
        except SystemExit as refused:
            log(str(refused))
            return 1
        env = {**env, "ADOPT_SANCHO": str(exe)}
        log(f"{' and '.join(installing)} runs {exe}")
        if name in SEALED_LOTS and not cfg.get("sancho"):  # the real path: the frozen copy
            if why := guardptr_seal.frozen_refusal(exe, guardptr_seal.manifest(REPO)):
                log(f"refused: {why}")
                return 1
            log(f"frozen copy matches the sealed package; {guardptr_seal.frozen_versions(exe)}")
        python = Path(cfg.get("preflight_python") or exe.parent / "python.exe")
        if profile.keyless:
            log("keyless: no TypeSafe key is read and no preflight is asked (the null decider)")
        elif code := preflight(python, root, cfg.get("preflight_pythonpath", "")):
            log(f"refused: jev-preflight exit {code}; nothing was run")
            return code
    code = runs(name, cfg, root, env, arms)
    windows(root)
    if code == 0 and name in GRADED_APART:
        log(f"{name}: graded apart, `long_pointers_read.py grade --profile {name} --final` "
            f"(per-test timeout {GRADED_APART[name]} s; the launcher's grade hung on moto)")
    elif code == 0 and cfg.get("grade", True):
        code = run_step(runner_cmd(cfg, "grade", name, root, None, arms), env,
                        root / "grade.log", "grade", root)  # fmt: skip
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("smoke", "gate", "pilot-a", "noise-ne", "noise-n",
                                           "conan-n2", "conan-ne2", "conan-a2", "compact",
                                           "compact-fifth", "compact-extra",
                                           "compact-conan2", "guardptr", "guardptr-30",
                                           "guardptr-smoke", "plan"))  # fmt: skip
    parser.add_argument("profile", nargs="?", default="",
                        help="plan: smoke, gate, pilot-a, noise-ne, noise-n, conan-n2, "
                        "conan-ne2, conan-a2, compact, compact-fifth, compact-extra or "
                        "compact-conan2")
    parser.add_argument("--seal", default="",
                        help="smoke: the sealed S commit; guardptr*: the lot's sealed commit "
                        "(frozen copy)")  # fmt: skip
    parser.add_argument("--commit", default="",
                        help="pilot-a, conan-a2: A's own commit (frozen copy)")
    parser.add_argument("--arm", default="", choices=("", *long_pilot.ARMS),
                        help="pilot-a: A (default) or A10")  # fmt: skip
    parser.add_argument("--root", default="")
    parser.add_argument("--dry-config", default="")
    args = parser.parse_args(argv)
    if args.action == "plan":
        cfg = json.loads(Path(args.dry_config).read_text("utf-8")) if args.dry_config else {}
        known = (json.loads(Path(cfg["chains_file"]).read_text(encoding="utf-8"))
                 if cfg.get("chains_file") else run.chains())  # fmt: skip
        profile = long_run.PROFILES[args.profile]
        root = root_for(args.profile, args, cfg)
        arms = (args.arm,) if args.arm else ()
        for line in plan_lines(args.profile, known, list(profile.chains), root, profile.ceiling,
                               arms):  # fmt: skip
            print(line)
        return 0
    return launch(args.action, args)


if __name__ == "__main__":
    raise SystemExit(main())
