"""F2's night: f2-pilot, its automatic gate, f2-sonnet, f2-opus, in one unattended sequence
(docs/results/2026-10-16-memory-f2/prereg.md). Started by `f2-night-run.cmd` (WMI, CreateFlags
512); run it again to resume: finished runs are skipped, recorded arms are kept, an arm cut by a
crash or reboot runs again whole (`handoff.run_plan`).

- SIGINT is ignored; one night at a time (a lock file with a live PID refuses a second).
- LIMIT.flag in the root (a usage limit) refuses to start: the owner removes it to resume.
- A STOP file in the root or in a run's folder stops before the next arm.
- Each run's cap is min(its own cap, NIGHT_CAP minus what the night's earlier runs spent).
- After f2-pilot the gate (`handoff_analyze.gate`) is written to `gate.json` and `gate.md`;
  if it fails, nothing larger runs (exit 5). Its result is final: a resume reads it back.
- Any other stop (cap, limit, harness, STOP, broken) ends the night with that run's exit code.
- After each run its analysis (free) goes to `<run>-table.json`.
- `--lot w17` runs W17's two memory lots instead (docs/results/2026-10-16-memory-w17/
  prereg.md): w17-sonnet then w17-opus, no gate, no arm in the quiet hours; `--only <run>` runs
  one of them. In a root that holds both runs, one cap of 45 USD binds both (`handoff.LOTS`).
  Its analysis is `handoff_pairs.analyse`. Amendment 1 (the Opus redo): the quiet hours lift
  while Windows Update is paused (`winupdate.quiet_lifted`); a night, dry or live, refuses the
  interrupted run's roots (`handoff.W17_INTERRUPTED`, exit 11), so the redo cannot mix with
  them; and the redo's root (`handoff.LOTS["w17"]["out"]`) runs only w17-opus, under its own
  33 USD: w17-sonnet is refused there (exit 11), since that root holds no ledger of it and the
  45 USD would not bind it.

    python benchmarks/memory_carry/handoff_night.py --root C:\\sp-runs\\memory-f2 [--dry]
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import carry  # noqa: E402
import handoff  # noqa: E402
import handoff_analyze  # noqa: E402
import handoff_pairs  # noqa: E402
import handoff_seal  # noqa: E402

SEQUENCE = ("f2-pilot", "f2-sonnet", "f2-opus")
GATE_FAIL = 5


def alive(pid: int) -> bool:
    """Whether a process is running, without signalling it (os.kill on Windows terminates)."""
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    kernel = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    code = ctypes.c_ulong()
    try:
        kernel.GetExitCodeProcess(handle, ctypes.byref(code))
    finally:
        kernel.CloseHandle(handle)
    return code.value == 259  # STILL_ACTIVE


def lock(root: Path) -> None:
    path = root / "night.lock"
    if path.exists():
        try:
            pid = int(path.read_text().split()[0])
        except (ValueError, IndexError):
            pid = 0
        if pid and pid != os.getpid() and alive(pid):
            raise SystemExit(f"another night runs (PID {pid}): refusing")
    path.write_text(f"{os.getpid()} {time.strftime('%Y-%m-%d %H:%M:%S')}\n", encoding="utf-8")


def spent_before(root: Path, run: str, lot: str = "f2") -> float:
    """What the lot's other runs spent before `run` (for W17, whose runs can run alone with
    `--only`, every other run of the lot)."""
    sequence = handoff.LOTS[lot]["sequence"]
    others = sequence[: sequence.index(run)] if lot == "f2" else [r for r in sequence if r != run]
    return sum(handoff.ledger(root / r) for r in others)


def interrupted_refusal(root: Path, lot: str) -> str:
    """W17's redo (Amendment 1): why `root` or the lot's work folder is, or lies under, the
    interrupted run's ("" when neither does; `handoff.interrupted_refusal`)."""
    if lot != "w17":
        return ""
    return handoff.interrupted_refusal(root, Path(handoff.LOTS[lot]["work"]))


def redo_refusal(root: Path, lot: str, sequence: tuple[str, ...]) -> str:
    """Amendment 1: why the redo's root, or a folder under it, may not run w17-sonnet ("" when
    it may run what is asked). w17-sonnet ran in the first root and is published from there; the
    redo's root holds no ledger of it, so the lot's 45 USD would not bind it."""
    if lot != "w17" or "w17-sonnet" not in sequence:
        return ""
    redo, here = Path(handoff.LOTS[lot]["out"]).resolve(), root.resolve()
    if here != redo and redo not in here.parents:
        return ""
    return f"{root} is the Opus redo's root (Amendment 1): only w17-opus runs here"


def table(root: Path, run: str) -> None:
    out = root / run
    rows = handoff.rows_of(out)
    plan = handoff.build_plan(run)
    planned = sorted({(s, m, r) for s, m, _, r in plan})
    model = handoff.RUNS[run]["model"]
    if handoff.lot_of(run) == "f2":
        result = handoff_analyze.analyse(rows, model, out, planned)
    else:
        result = handoff_pairs.analyse(rows, model, out, planned)
    (root / f"{run}-table.json").write_text(json.dumps(result, indent=1), encoding="utf-8")


def pilot_gate(root: Path) -> dict[str, Any]:
    path = root / "gate.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    rows = handoff.rows_of(root / "f2-pilot")
    result = handoff_analyze.gate(rows, handoff.build_plan("f2-pilot"))
    path.write_text(json.dumps(result, indent=1), encoding="utf-8")
    (root / "gate.md").write_text(handoff_analyze.gate_text(result), encoding="utf-8")
    return result


def status(root: Path, text: str) -> None:
    with (root / "night.status").open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text}\n")
    print(text, flush=True)


def night(root: Path, dry: bool = False, work: Path | None = None, lot: str = "f2",
          only: str | None = None) -> int:  # fmt: skip
    """`work`: where the agents work (the lot's own); a dry night builds under `root/dry`.
    `only`: one run of the lot (W17's two lots can run apart)."""
    spec = handoff.LOTS[lot]
    sequence = tuple(r for r in spec["sequence"] if only in (None, r))
    if not sequence:
        raise SystemExit(f"{only} is not a run of the lot {lot}")
    if why := interrupted_refusal(root, lot) or redo_refusal(root, lot, sequence):
        # dry or not, before anything is written there
        print(f"refused: {why}; nothing run", flush=True)
        return handoff_seal.SEALED_CHECKOUT_REFUSED
    root.mkdir(parents=True, exist_ok=True)
    if dry:
        for run in sequence:
            print(f"== {run} (dry: every arm built, nothing called)", flush=True)
            out = root / "dry" / run
            base = work or root / "dry" / Path(spec["work"]).name
            handoff.execute(run, out, handoff.RUNS[run]["cap"], dry=True,
                            work_root=base / handoff.RUNS[run]["dir"])  # fmt: skip
        return 0
    handoff_seal.require_sealed_checkout(*([] if lot == "f2" else [lot]))
    for run in sequence:  # a key a crash left behind is never reused
        (handoff.work_of(run) / "typesafe.key").unlink(missing_ok=True)
    if (root / "LIMIT.flag").exists():
        status(root, "refused: LIMIT.flag (a usage limit paused the night)")
        return handoff.EXIT["limit"]
    lock(root)
    try:
        for run in sequence:
            if spec["gate"] and run != spec["gate"]:
                result = pilot_gate(root)
                if not result["pass"]:
                    status(root, "gate failed: " + "; ".join(result["reasons"]))
                    return GATE_FAIL
            night_cap = handoff.NIGHT_CAP if lot == "f2" else float(spec["night_cap"])
            cap = min(handoff.RUNS[run]["cap"], night_cap - spent_before(root, run, lot))
            status(root, f"{run} starts, cap {cap:.2f} USD")
            stop = handoff.execute(run, root / run, cap, night=root)
            table(root, run)
            status(root, f"{run} ends: {stop or 'done'}, spent {handoff.ledger(root / run):.2f}")
            if stop:
                return handoff.EXIT[stop]
        status(root, "night done")
        return 0
    finally:
        (root / "night.lock").unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    carry.ignore_interrupts()
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    parser.add_argument("--dry", action="store_true")
    parser.add_argument("--lot", choices=sorted(handoff.LOTS), default="f2")
    parser.add_argument("--only", choices=sorted(handoff.RUNS))
    args = parser.parse_args(argv)
    root = Path(args.root) if args.root else Path(handoff.LOTS[args.lot]["out"])
    return night(root, args.dry, lot=args.lot, only=args.only)


if __name__ == "__main__":
    raise SystemExit(main())
