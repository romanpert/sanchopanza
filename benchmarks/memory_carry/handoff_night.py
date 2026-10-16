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


def spent_before(root: Path, run: str) -> float:
    earlier = SEQUENCE[: SEQUENCE.index(run)]
    return sum(handoff.ledger(root / r) for r in earlier)


def table(root: Path, run: str) -> None:
    out = root / run
    rows = handoff.rows_of(out)
    plan = handoff.build_plan(run)
    planned = sorted({(s, m, r) for s, m, _, r in plan})
    result = handoff_analyze.analyse(rows, handoff.RUNS[run]["model"], out, planned)
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


def night(root: Path, dry: bool = False, work: Path | None = None) -> int:
    """`work`: where the agents work (handoff.WORK); a dry night builds under `root/dry`."""
    root.mkdir(parents=True, exist_ok=True)
    if dry:
        for run in SEQUENCE:
            print(f"== {run} (dry: every arm built, nothing called)", flush=True)
            out = root / "dry" / run
            handoff.execute(
                run,
                out,
                handoff.RUNS[run]["cap"],
                dry=True,
                work_root=(work or root / "dry" / "w16") / handoff.RUNS[run]["dir"],
            )
        return 0
    handoff_seal.require_sealed_checkout()
    for run in SEQUENCE:  # a key a crash left behind is never reused
        (handoff.WORK / handoff.RUNS[run]["dir"] / "typesafe.key").unlink(missing_ok=True)
    if (root / "LIMIT.flag").exists():
        status(root, "refused: LIMIT.flag (a usage limit paused the night)")
        return handoff.EXIT["limit"]
    lock(root)
    try:
        for run in SEQUENCE:
            if run != "f2-pilot":
                result = pilot_gate(root)
                if not result["pass"]:
                    status(root, "gate failed: " + "; ".join(result["reasons"]))
                    return GATE_FAIL
            cap = min(handoff.RUNS[run]["cap"], handoff.NIGHT_CAP - spent_before(root, run))
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
    parser.add_argument("--root", default=str(handoff.OUT))
    parser.add_argument("--dry", action="store_true")
    args = parser.parse_args(argv)
    return night(Path(args.root), args.dry)


if __name__ == "__main__":
    raise SystemExit(main())
