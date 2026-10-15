"""Does running find for the agent at the struggle point help where asking it to call find did not?
A development probe of the find-auto hook (`harness.find_auto`, `install --find-auto`) on the
need-ranked development set, the need probe's ten instances. Arm S only, one session each; the
reference is the need probe's rows on the same instances (dev-need/, phase D's copy, no hook).
Paid (subscription, list price; the hook's Jev tournament on top, cents).

    python -m benchmarks.adopt_dev.probe_auto check [--dev]  # free: see check_auto.py
    python -m benchmarks.adopt_dev.probe_auto run            # the probe (resumable)
    python -m benchmarks.adopt_dev.probe_auto grade          # grade what ran, no session
    python -m benchmarks.adopt_dev.probe_auto summary        # tables from the rows, free

The session is the alwaysLoad probe's (`probe_alwaysload.session`, reused as is) with one change
made here, in this process: `run.install_sancho` adds `--find-auto` to the install. So arm S is
`sanchopanza install --scope project --write --find-auto` from the frozen copy of `AUTO_COMMIT`
(common.py), wired through `hook_env.py` as the sealed runner does, with the per-arm key path;
Claude Code 2.1.285 (private copy first on PATH, DISABLE_AUTOUPDATER=1), Haiku 4.5, phase A's
singles prompt, tools and test command, 1.50 USD per call. A session starts only if the rows' cost
so far (Jev's included) plus its cap fits under 12.00 USD. No retries: the batch stops at the
first API or usage-limit error result (the row is kept as NOT RUN and runs again on a later `run`),
at the cap, under 15 GB free, when find is not visible, when the install lacks the hook, and when
the live rule should have fired (`expected_fire_call`) but the hook journalled nothing. Grading is
the official SWE-bench harness; an empty diff is not resolved without it.

Per session, `auto-facts.json` beside `row.json` (`auto_facts.py`): the need probe's facts, plus
whether the hook fired and at which call and search, the keys shown, whether one is a gold file or
holds a changed gold line, whether the next Read was of a shown place and how many calls later
one was Read, whether the header reached the transcript, and the hook's Jev cost (also in the
row's jev_usd, which sums the journal's decisions).

Writes only under ~/.cache/sanchopanza/adopt/dev-auto/ and work-dau/. Phase D's ledger
(`run_d.DEV_ROOTS`) does not count dev-auto: this probe's 12.00 USD sit outside D's ceiling.
Log lines that end a run: `PROBE DONE`, `PROBE STOP: <why>` or `PROBE FAILED: <why>`; the
launcher adds `exit <n>`.
"""

from __future__ import annotations

import os

os.environ.setdefault("ADOPT_DEV_PROFILE", "auto")

import argparse  # noqa: E402
import json  # noqa: E402
import signal  # noqa: E402
import statistics  # noqa: E402
import traceback  # noqa: E402
from functools import cache  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

from . import common  # noqa: E402

if common.PROFILE != "auto":
    raise RuntimeError(f"common.py was pinned to {common.PROFILE!r} first: run this on its own")

from . import probe_alwaysload as base  # noqa: E402
from .auto_facts import describe, need_reference  # noqa: E402

OUT, PLAN, ARM = common.OUT, common.PLAN, "S"
NEED_OUT = common.ROOT / "dev-need"  # the reference rows, read only
EMPTY_DIFF = "empty diff"
FLAG = "--find-auto"
_install_sancho = common.run.install_sancho


def install_with_auto(work: Path, evidence: Path, keyfile: Path,
                      extra: tuple[str, ...] = ()) -> Path:  # fmt: skip
    """The sealed runner's install, with the find-auto hook."""
    return _install_sancho(work, evidence, keyfile, (*extra, FLAG))


common.run.install_sancho = install_with_auto  # this process only; the sealed file is unchanged


@cache
def gold_of(name: str) -> tuple[tuple[str, ...], str]:
    from benchmarks.find_need.need import gold_files, verified

    patch = verified()[name]["patch"]
    return tuple(gold_files(patch)), patch


def wiring_problem(evidence: Path) -> str:
    """Why the install as copied into the evidence lacks the hook, or ""."""
    from sanchopanza.harness.find_auto import EVENTS, TOOL

    settings = json.loads((evidence / "settings.json").read_text(encoding="utf-8"))
    hooks = settings.get("hooks", {})
    for event in EVENTS:
        if not any(h.get("type") == "mcp_tool" and h.get("tool") == TOOL
                   for e in hooks.get(event, []) for h in e.get("hooks", [])):  # fmt: skip
            return f"no find_auto mcp_tool hook on {event}"
    server = json.loads((evidence / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    if server.get("sanchopanza", {}).get("args", [])[-2:] != ["find-mcp", "--auto"]:
        return f"the find server does not run find-mcp --auto: {server.get('sanchopanza')}"
    return ""


def session_facts(name: str) -> dict[str, Any] | None:
    evidence = OUT / name / ARM
    if not (evidence / "row.json").exists():
        return None
    gold, patch = gold_of(name)
    work = str(common.WORK / f"{name}-{ARM}")
    facts = describe(evidence, list(gold), patch, common.read_json(evidence / "row.json"), work)
    (evidence / "auto-facts.json").write_text(json.dumps(facts, indent=1), encoding="utf-8")
    return facts


def after_session(record: dict[str, Any]) -> None:
    """Log the facts; stop when the treatment did not run as installed."""
    name = record["instance"]
    facts = session_facts(name) or {}
    auto = facts.get("auto", {})
    base.log(f"{name} S: auto fired {auto.get('fired')} at call {auto.get('fire_call')} "
             f"(expected {auto.get('expected_fire_call')}) outcome {auto.get('outcome')} shown "
             f"{len(auto.get('shown', []))} gold file {auto.get('shown_gold_file')} hunk "
             f"{auto.get('shown_gold_hunk')} next read shown {auto.get('next_read_is_shown')} "
             f"searches before gold read {facts.get('searches_before_gold_read')} find calls "
             f"{len(facts.get('find_calls', []))} jev {auto.get('jev_usd')}")  # fmt: skip
    ran = not record["calls"][0].get("status")
    if not ran:
        return
    if facts.get("find_hidden"):
        raise base.Stop(f"{name} S: find_in_repo not visible ({facts['find_hidden']})")
    if why := wiring_problem(OUT / name / ARM):
        raise base.Stop(f"{name} S: {why}")
    outcomes = {row.get("outcome") for row in auto.get("journal") or []}
    if auto.get("expected_fire_call") and outcomes == {"not_ready"}:
        raise base.Stop(f"{name} S: the rule was due and the index was never ready in time "
                        f"(waited {[r.get('waited_s') for r in auto['journal']]} s): the probe "
                        "would pay to measure build time")  # fmt: skip
    if auto.get("expected_fire_call") and not auto.get("journal"):
        raise base.Stop(
            f"{name} S: the rule should have fired after call "
            f"{auto['expected_fire_call']} and the hook journalled nothing"
        )


# ---- grading -------------------------------------------------------------------------------------


def grade_arm(name: str) -> bool | None:
    """An empty diff is not resolved without the harness (swebench drops an empty prediction);
    any other diff goes to the official harness as `probe_alwaysload.grade_arm`."""
    evidence = OUT / name / ARM
    if (evidence / "grade.json").exists():
        return bool(common.read_json(evidence / "grade.json")["resolved"])
    if (evidence / "final.patch").read_text(encoding="utf-8") == "":
        (evidence / "grade.json").write_text(json.dumps({"resolved": False, "reason": EMPTY_DIFF}),
                                             encoding="utf-8")  # fmt: skip
        return False
    return base.grade_arm(name, ARM)


def grade_done(name: str) -> None:
    if not base.gradable(name, ARM):
        return
    try:
        base.log(f"{name} S: resolved {grade_arm(name)}")
    except OSError as exc:
        base.log(f"{name} S: grading failed ({exc}); `grade` or `run` again grades it")


def one_instance(row: dict[str, Any], keyfile: Any) -> None:
    name = row["instance_id"]
    todo = base.todo_arms(name, (ARM,))
    if not todo and not base.gradable(name, ARM):
        return
    base.docker_env.pull(row["image"])
    try:
        for arm in todo:
            base.run_arm(row, arm, keyfile)
    finally:
        try:
            grade_done(name)
        finally:
            base.docker_env.drop(row["image"])


def probe() -> int:
    base.preflight()
    known = common.singles_run.rows()
    keyfile = common.run.keyfile_from_harness_env()
    try:
        for name, _arms in PLAN:
            one_instance(known[name], keyfile)
    finally:
        keyfile.unlink(missing_ok=True)
        common.run.drop_arm_keys()
    return 0


def grade_only() -> int:
    known = common.singles_run.rows()
    for name, _arms in PLAN:
        if not base.gradable(name, ARM):
            continue
        evidence = OUT / name / ARM
        pulled = (evidence / "final.patch").read_text(encoding="utf-8") != ""
        if pulled:
            base.docker_env.pull(known[name]["image"])
        try:
            grade_done(name)
        finally:
            if pulled:
                base.docker_env.drop(known[name]["image"])
    return 0


# ---- summary -------------------------------------------------------------------------------------


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 4) if values else None


def row_of(name: str) -> dict[str, Any] | None:
    evidence = OUT / name / ARM
    if not (evidence / "row.json").exists():
        return None
    record = common.read_json(evidence / "row.json")
    call = record["calls"][0]
    grade = evidence / "grade.json"
    facts = session_facts(name) or {}
    auto = facts.get("auto", {})
    keep = (
        "fired",
        "fire_call",
        "expected_fire_call",
        "fire_search",
        "outcome",
        "shown",
        "shown_gold_file",
        "shown_gold_hunk",
        "shown_gold_first",
        "next_call",
        "next_read_is_shown",
        "next_call_follows",
        "calls_to_shown_read",
        "calls_to_shown_shell",
        "injected_in_transcript",
        "jev_usd",
    )
    return {"instance": name, "status": call.get("status") or call.get("subtype"),
            "turns": call.get("turns"),
            "cost_usd": round(call.get("cost_usd", 0.0) + record.get("jev_usd", 0.0), 4),
            "resolved": common.read_json(grade)["resolved"] if grade.exists() else None,
            "searches_before_gold_read": facts.get("searches_before_gold_read"),
            "find_calls": [c["call"] for c in facts.get("find_calls", [])],
            **{k: auto.get(k) for k in keep},
            "need": need_reference(NEED_OUT / name / ARM)}  # fmt: skip


def _hard(searches: int | None) -> bool:
    return searches is None or searches >= 5


def summary() -> dict[str, Any]:
    rows = [r for r in (row_of(name) for name, _arms in PLAN) if r]
    ran = [r for r in rows if r["status"] and not str(r["status"]).startswith("NOT RUN")]
    paired = [r for r in ran if r["need"]]
    reads = [r["searches_before_gold_read"] for r in ran
             if r["searches_before_gold_read"] is not None]  # fmt: skip
    table = {
        "sessions": len(ran),
        "fired": sum(bool(r["fired"]) for r in ran),
        "expected_to_fire": sum(bool(r["expected_fire_call"]) for r in ran),
        "shown_gold_file": sum(bool(r["shown_gold_file"]) for r in ran),
        "shown_gold_hunk": sum(bool(r["shown_gold_hunk"]) for r in ran),
        "next_read_shown": sum(bool(r["next_read_is_shown"]) for r in ran),
        "next_call_follows": sum(bool(r["next_call_follows"]) for r in ran),
        "shown_read_later": sum(r["calls_to_shown_read"] is not None for r in ran),
        "shown_named_in_shell_later": sum(r["calls_to_shown_shell"] is not None for r in ran),
        "resolved": sum(bool(r["resolved"]) for r in ran),
        "graded": sum(r["resolved"] is not None for r in ran),
        "hard": sum(_hard(r["searches_before_gold_read"]) for r in ran),
        "median_searches_before_gold_read": _median(reads),
        "median_cost_usd": _median([r["cost_usd"] for r in ran]),
        "jev_usd": round(sum(r["jev_usd"] or 0.0 for r in ran), 6),
        "need_probe_on_the_same_instances": {
            "sessions": len(paired),
            "resolved": f"auto {sum(bool(r['resolved']) for r in paired)} vs need "
                        f"{sum(bool(r['need']['resolved']) for r in paired)}",
            "hard": f"auto {sum(_hard(r['searches_before_gold_read']) for r in paired)} vs need "
                    f"{sum(_hard(r['need']['searches_before_gold_read']) for r in paired)}",
            "median_cost_usd": f"auto {_median([r['cost_usd'] for r in paired])} vs need "
                               f"{_median([r['need']['cost_usd'] for r in paired])}",
        },
    }  # fmt: skip
    out = {"spent_usd": base.spent(), "cap_usd": common.TOTAL_CAP_USD, "table": table,
           "rows": rows}  # fmt: skip
    (OUT / "summary.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("check", "run", "grade", "summary"))
    parser.add_argument(
        "--dev",
        action="store_true",
        help="check only: before the freeze, run the hook from this checkout",
    )
    args = parser.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    if args.action == "check":
        from .check_auto import check

        return check(dev=args.dev)
    if args.action == "summary":
        print(json.dumps(summary(), indent=1))
        return 0
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # a stray Ctrl+C killed phase A mid-grade
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal.SIG_IGN)
    if args.action == "grade":
        grade_only()
        summary()
        base.log(f"GRADE DONE (spent {base.spent():.2f} USD)")
        return 0
    base.AFTER_SESSION.append(after_session)
    stamp = common.run.frozen_stamp() or {}
    base.log(f"PROBE START auto plan {[n for n, _ in PLAN]} spent {base.spent():.2f} USD "
             f"cap {common.TOTAL_CAP_USD:.2f} frozen {stamp.get('commit')} "
             f"extras {stamp.get('extras')}")  # fmt: skip
    try:
        probe()
    except base.Stop as why:
        summary()
        base.log(f"PROBE STOP: {why} (spent {base.spent():.2f} USD)")
        return 0
    except Exception as exc:  # noqa: BLE001  (logged with its trace; the monitor greps for it)
        traceback.print_exc()
        base.log(f"PROBE FAILED: {type(exc).__name__}: {exc} (spent {base.spent():.2f} USD)")
        return 1
    done = summary()
    base.log(f"PROBE DONE: {len(done['rows'])} rows, spent {done['spent_usd']:.2f} USD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
