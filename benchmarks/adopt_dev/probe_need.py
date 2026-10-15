"""Does Haiku call find_in_repo where find is needed? A development probe of phase D's treatment
(the frozen copy of 7a39a1f: the default install, find alwaysLoad, no nudge, the delegation fix)
on the need-ranked development set (`benchmarks/find_need/need-table.json`: ten Verified singles
where a recorded control session took 5 or more searches to the gold file, or never got there).
Arm S only, one session each; the reference is the need table's recorded sessions. Paid
(subscription, list price).

    python -m benchmarks.adopt_dev.probe_need check     # free: see check_need.py
    python -m benchmarks.adopt_dev.probe_need run       # the probe (resumable)
    python -m benchmarks.adopt_dev.probe_need grade     # grade what ran, no session
    python -m benchmarks.adopt_dev.probe_need summary   # tables from the rows, free

The session is the alwaysLoad probe's (`probe_alwaysload.session`, reused as is): arm S is
`sanchopanza install --scope project --write` from the frozen copy, wired through `hook_env.py` as
the sealed runner does, with the per-arm key path of amendment 5; Claude Code 2.1.285 (private
copy first on PATH, DISABLE_AUTOUPDATER=1), Haiku 4.5, phase A's singles prompt, tools and test
command (`singles_run.PROMPT`, `run.command`), 1.50 USD per call. A session starts only if the
rows' cost so far (Jev's included) plus its cap fits under 12.00 USD. No retries: the batch stops
at the first API or usage-limit error result (the row is kept as NOT RUN and runs again on a later
`run`), at the cap, when find is not visible in a session that ran, and under 15 GB free.
Grading is the official SWE-bench harness; an empty diff is not resolved without it (phase D's
rule).

Per session, `need-facts.json` beside `row.json` (`need_facts.py`): find visible (init tools, no
deferred_tools_delta naming it, mcp.json alwaysLoad), find and ToolSearch calls with their tool
call and API call, searches before the first Read of a gold file, Agent calls and failures, and
the treatment's evidence (decider, server at init, Jev's decisions).

Writes only under ~/.cache/sanchopanza/adopt/dev-need/ and work-dnd/. Log lines that end a run:
`PROBE DONE`, `PROBE STOP: <why>` or `PROBE FAILED: <why>`; the launcher adds `exit <n>`.
"""

from __future__ import annotations

import os

os.environ.setdefault("ADOPT_DEV_PROFILE", "need")

import argparse  # noqa: E402
import json  # noqa: E402
import signal  # noqa: E402
import statistics  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402
from functools import cache  # noqa: E402
from typing import Any  # noqa: E402

from . import common  # noqa: E402

if common.PROFILE != "need":
    raise RuntimeError(f"common.py was pinned to {common.PROFILE!r} first: run this on its own")

from . import probe_alwaysload as base  # noqa: E402
from .need_facts import describe  # noqa: E402

OUT, PLAN, ARM = common.OUT, common.PLAN, "S"
EMPTY_DIFF = "empty diff"


@cache
def gold_of(name: str) -> tuple[str, ...]:
    from benchmarks.find_need.need import gold_files, verified

    return tuple(gold_files(verified()[name]["patch"]))


def session_facts(name: str) -> dict[str, Any] | None:
    evidence = OUT / name / ARM
    if not (evidence / "row.json").exists():
        return None
    facts = describe(evidence, list(gold_of(name)), common.read_json(evidence / "row.json"))
    (evidence / "need-facts.json").write_text(json.dumps(facts, indent=1), encoding="utf-8")
    return facts


def after_session(record: dict[str, Any]) -> None:
    """Log the need facts; stop when find was not visible in a session that ran (an error
    result is left to the driver, which stops on it as a usage limit)."""
    facts = session_facts(record["instance"]) or {}
    base.log(f"{record['instance']} S: find visible {facts.get('find_visible')} "
             f"({facts.get('find_hidden') or 'ok'}) find calls "
             f"{[(c['call'], c['api_call']) for c in facts.get('find_calls', [])]} "
             f"ToolSearch {len(facts.get('toolsearch_calls', []))} searches before gold read "
             f"{facts.get('searches_before_gold_read')} Agent "
             f"{len(facts.get('agent_calls', []))} failed {facts.get('agent_failures')} "
             f"decisions {facts.get('treatment', {}).get('decisions_by_provider')}")  # fmt: skip
    if not record["calls"][0].get("status") and facts.get("find_hidden"):
        raise base.Stop(f"{record['instance']} S: find_in_repo not visible "
                        f"({facts['find_hidden']})")  # fmt: skip


# ---- grading -------------------------------------------------------------------------------------


def grade_arm(name: str) -> bool | None:
    """The official harness on the session's diff, as `probe_alwaysload.grade_arm`; an empty diff
    is not resolved without the harness (swebench drops an empty prediction and writes no report).
    None: no report, and no grade.json."""
    evidence = OUT / name / ARM
    if (evidence / "grade.json").exists():
        return bool(common.read_json(evidence / "grade.json")["resolved"])
    patch = (evidence / "final.patch").read_text(encoding="utf-8")
    if patch == "":
        (evidence / "grade.json").write_text(json.dumps({"resolved": False, "reason": EMPTY_DIFF}),
                                             encoding="utf-8")  # fmt: skip
        return False
    model = "adopt-dneed-S"
    preds = evidence / "preds.jsonl"
    preds.write_text(json.dumps({"instance_id": name, "model_name_or_path": model,
                                 "model_patch": patch}) + "\n",
                     encoding="utf-8", newline="\n")  # fmt: skip
    run_id = f"{model}-{int(time.time())}"
    swe = common.singles_run.SWE
    subprocess.run([str(common.singles_run.SWE_PYTHON), str(swe / "run_swe.py"), "-d",
                    "SWE-bench/SWE-bench_Verified", "-p", str(preds), "-i", name,
                    "--max_workers", "1", "-id", run_id], cwd=swe, capture_output=True,
                   env={**os.environ, "PYTHONUTF8": "1"}, timeout=3600)  # fmt: skip
    report = swe / "logs" / "run_evaluation" / run_id / model / name / "report.json"
    if not report.exists():
        base.log(f"{name} S: no report from the harness, not graded")
        return None
    resolved = bool(common.read_json(report).get(name, {}).get("resolved"))
    (evidence / "grade.json").write_text(json.dumps({"resolved": resolved, "report": str(report)}),
                                         encoding="utf-8")  # fmt: skip
    return resolved


def needs_harness(name: str) -> bool:
    evidence = OUT / name / ARM
    return base.gradable(name, ARM) and (evidence / "final.patch").exists() and \
        (evidence / "final.patch").read_text(encoding="utf-8") != ""  # fmt: skip


def grade_done(name: str) -> None:
    if not base.gradable(name, ARM):
        return
    try:
        base.log(f"{name} S: resolved {grade_arm(name)}")
    except (OSError, subprocess.SubprocessError) as exc:
        base.log(f"{name} S: grading failed ({exc}); `grade` or `run` again grades it")


# ---- the probe -----------------------------------------------------------------------------------


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
    """Grade every ungraded session that ran; no session starts."""
    known = common.singles_run.rows()
    for name, _arms in PLAN:
        if not base.gradable(name, ARM):
            continue
        pulled = needs_harness(name)  # an empty diff is graded without the image
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


def summary() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for name, _arms in PLAN:
        evidence = OUT / name / ARM
        if not (evidence / "row.json").exists():
            continue
        record = common.read_json(evidence / "row.json")
        call = record["calls"][0]
        grade = evidence / "grade.json"
        facts = session_facts(name) or {}
        treated = facts.get("treatment", {})
        rows.append({"instance": name, "status": call.get("status") or call.get("subtype"),
                     "turns": call.get("turns"),
                     "cost_usd": round(call.get("cost_usd", 0.0) + record.get("jev_usd", 0.0), 4),
                     "jev_usd": round(record.get("jev_usd", 0.0), 6),
                     "resolved": common.read_json(grade)["resolved"] if grade.exists() else None,
                     "find_visible": facts.get("find_visible"),
                     "find_calls": [c["call"] for c in facts.get("find_calls", [])],
                     "toolsearch_calls": len(facts.get("toolsearch_calls", [])),
                     "searches_before_gold_read": facts.get("searches_before_gold_read"),
                     "agent_calls": len(facts.get("agent_calls", [])),
                     "agent_failures": facts.get("agent_failures"),
                     "decider": treated.get("decider"),
                     "server_at_init": treated.get("server_at_init")})  # fmt: skip
    ran = [r for r in rows if r["status"] and not str(r["status"]).startswith("NOT RUN")]
    reads = [r["searches_before_gold_read"] for r in ran
             if r["searches_before_gold_read"] is not None]  # fmt: skip
    table = {"sessions": len(ran), "find_called": sum(bool(r["find_calls"]) for r in ran),
             "resolved": sum(bool(r["resolved"]) for r in ran),
             "graded": sum(r["resolved"] is not None for r in ran),
             "hard": sum(1 for r in ran if r["searches_before_gold_read"] is None
                         or r["searches_before_gold_read"] >= 5),
             "gold_never_read": len(ran) - len(reads),
             "median_searches_before_gold_read": _median(reads),
             "median_cost_usd": _median([r["cost_usd"] for r in ran]),
             "agent_failures": sum(r["agent_failures"] or 0 for r in ran)}  # fmt: skip
    out = {"spent_usd": base.spent(), "cap_usd": common.TOTAL_CAP_USD, "table": table,
           "rows": rows}  # fmt: skip
    (OUT / "summary.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("check", "run", "grade", "summary"))
    args = parser.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    if args.action == "check":
        from .check_need import check

        return check()
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
    base.log(f"PROBE START need plan {[n for n, _ in PLAN]} spent {base.spent():.2f} USD "
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
