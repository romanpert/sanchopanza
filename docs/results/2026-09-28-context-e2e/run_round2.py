"""Round 2: the autopilot (arm A) against native `/compact` (arm N, round-1 rows). See the
2026-09-28 amendment in `prereg.md`.

    python run_round2.py dry                                   # free: hook pipeline, no key
    TYPESAFE_API_KEY=... python run_round2.py run --tasks t01-orders   # the pilot
    TYPESAFE_API_KEY=... python run_round2.py run                      # t02-t06
    python run_round2.py collect                               # rows -> analysis-r2.json

Per task: a fresh copy of the repository; phase A with the autopilot installed (settings file
written by `sanchopanza install --autopilot` into the run's evidence folder and passed with
`--settings`, plugin through `--plugin-dir`; nothing under `~/.claude`), then `claude -p
"/compact" --resume <A>` (the plugin's `mask` arm), then phase B on the same session, then the
hidden tests. The key is read from this process's environment (or `--env-file`, run by the
owner), written to a file only the hook wrappers read, and deleted at the end.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import mean, median
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import costs  # noqa: E402
import run_e2e as r1  # noqa: E402
import tasks as gen  # noqa: E402
import transcripts  # noqa: E402

ROOT = r1.ROOT
TASKS = [f"t{i + 1:02d}-{gen.DOMAINS[i][0]}" for i in range(12)]  # R3: t07-t12 added
ROWS = HERE / "runs-r2.jsonl"
CLAUDE_STOP = 5.50  # round 2 only: ceiling 6.00
JEV_STOP = 0.45  # all Jev of the experiment: ceiling 0.50
HOOK = str(HERE / "hook_wrapper.py")
COMPACT = str(HERE / "compact_wrapper.py")
PLUGIN = ROOT / "plugin-autopilot"
ARRIVAL_MARK = "[sanchopanza cut this "
_lock = threading.Lock()


def rows() -> list[dict[str, Any]]:
    return r1._rows(ROWS)


def spent() -> float:
    return sum(r["a"]["cost_usd"] + r["compact"]["cost_usd"] + r["b"]["cost_usd"] for r in rows())


def jev_spent() -> float:
    return r1.jev_spent() + sum(r.get("jev_usd", 0.0) for r in rows())


def settings_for(ev: Path, keyfile: Path) -> Path:
    """What `install --autopilot` writes, then pointed at our wrappers; no marketplace entry
    (the plugin comes through `--plugin-dir`, so nothing is registered in `~/.claude`)."""
    path = ev / "settings.json"
    parts = [r1.PYTHON, HOOK, str(ev), str(keyfile)]
    hook = " ".join(parts)
    if any(" " in p for p in parts):
        raise SystemExit("a path has a space; the hook command would split")
    subprocess.run(
        [r1.SANCHO, "install", "--autopilot", "--plugin-dir", str(PLUGIN), "--path", str(path),
         "--provider", "jev", "--command-line", hook, "--write"],
        check=True, capture_output=True, text=True,
    )  # fmt: skip
    data = json.loads(path.read_text("utf-8"))
    data.pop("extraKnownMarketplaces", None)
    data.pop("enabledPlugins", None)
    data["env"] = {
        **data.get("env", {}),
        "SANCHOPANZA_COMPACT_COMMAND": f"{r1.PYTHON} {COMPACT} M {ev}",
        "SANCHOPANZA_COMPACT_MARKER": str(ev / "marker.txt"),
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def claude(prompt: str, settings: Path, resume: str | None = None) -> list[str]:
    cmd = r1.claude(prompt, resume=resume, plugin=PLUGIN)
    at = cmd.index("--allowedTools")
    return [*cmd[:at], "--settings", str(settings), *cmd[at:]]


class Gate(r1.Gate):
    def enter(self, jev: bool) -> bool:  # noqa: ARG002 - every session here can spend Jev
        with self.lock:
            import round3

            r3 = self.round3
            reserved = (round3.spent() if r3 else spent()) + (self.flight + 1) * r1.SESSION_CAP
            stop = round3.CLAUDE_STOP if r3 else CLAUDE_STOP
            if self.stopped or reserved > stop or jev_spent() > JEV_STOP:
                self.stopped = True
                return False
            self.flight += 1
            return True


def hook_stats(ev: Path) -> dict[str, Any]:
    lines = [json.loads(x) for x in transcripts._lines(ev / "hooks.jsonl")]
    post = [x for x in lines if x["event"] == "PostToolUse"]
    cuts = [x for x in post if x["updated"]]
    return {
        "events": len(lines),
        "post_tool_use": len(post),
        "over_6000": sum(x["response_chars"] > 6000 for x in post),
        "arrival_cuts": len(cuts),
        "arrival_cut_tools": sorted({x["tool"] for x in cuts}),
        "chars_saved": sum(x["response_chars"] - (x["updated_chars"] or 0) for x in cuts),
        "recall_on_tool": sum(x["context_chars"] > 0 for x in post),
        "recall_on_prompt": sum(
            x["context_chars"] > 0 for x in lines if x["event"] == "UserPromptSubmit"
        ),  # fmt: skip
        "recall_chars": sum(x["context_chars"] for x in lines),
        "denied": sum(x.get("permission") == "deny" or x.get("decision") == "block" for x in lines),
        "nonzero_exits": sum(x["exit"] != 0 for x in lines),
        "hook_seconds_median": median(x["seconds"] for x in lines) if lines else 0,
    }


def arrival_in_transcript(path: Path | None) -> dict[str, int]:
    """Did Claude Code apply updatedToolOutput? The cut header in a stored tool result says so."""
    by_tool: dict[str, int] = {}
    items = transcripts.entries(path)
    names = {u["id"]: u["name"] for u in transcripts.tool_uses(items)}
    for e in items:
        for b in transcripts._blocks(e):
            if b.get("type") == "tool_result" and ARRIVAL_MARK in json.dumps(b.get("content")):
                tool = names.get(b.get("tool_use_id"), "?")
                by_tool[tool] = by_tool.get(tool, 0) + 1
    return by_tool


def one(task: str, gate: Gate, keyfile: Path) -> dict[str, Any] | None:
    work, ev = ROOT / "work-A" / task, ROOT / "runs-r2" / task / "A"
    for path in (work, ev):
        if path.exists():
            shutil.rmtree(path)
    shutil.copytree(ROOT / "tasks" / "repos" / task, work)
    ev.mkdir(parents=True)
    settings = settings_for(ev, keyfile)
    env = r1.child_env(None, ev, None)
    a = r1.gated(gate, True, r1.session, claude(r1.PROMPT_A, settings), work, env, ev / "a.json")
    if a is None:
        return None
    consumed = {"token": not (work / "tools" / ".token_seed").exists(),
                "probe": not (work / "tools" / ".probe_state").exists()}  # fmt: skip
    valid = bool(a["session_id"]) and all(consumed.values()) and a["subtype"] == "success"
    compact = b = None
    if valid:
        compact = r1.gated(gate, True, r1.session, claude("/compact", settings, a["session_id"]),
                           work, env, ev / "compact.json")  # fmt: skip
        if compact is None:
            return None
        b = r1.gated(gate, True, r1.session, claude(r1.PROMPT_B, settings, a["session_id"]),
                     work, env, ev / "b.json")  # fmt: skip
        if b is None:
            return None
    empty = {"cost_usd": 0.0, "usage": {}, "subtype": "not_run", "seconds": 0}
    compact, b = compact or empty, b or empty
    tr = transcripts.find(a["session_id"])
    if tr:
        shutil.copy(tr, ev / "session.jsonl")
    tests = gen.run_tests(work, ROOT / "tasks" / "hidden" / task)
    fact = json.loads((ROOT / "tasks" / "facts.json").read_text("utf-8"))[int(task[1:3]) - 1]
    row = {
        "task": task, "arm": "A", "valid_a": valid, "consumed": consumed,
        "a": {k: v for k, v in a.items() if k != "result_text"},
        "compact": {k: v for k, v in compact.items() if k != "result_text"}, "b": b,
        "hooks": hook_stats(ev), "arrival_in_transcript": arrival_in_transcript(tr),
        "compaction_hook": transcripts.hook_outcome(ev),
        "compaction": transcripts.compaction(tr) if tr else None,
        "after": transcripts.summary_b(tr, tr) if tr else None,
        "summary_keeps": transcripts.summary_keeps(tr, fact) if tr else None,
        "window_constant": transcripts.constant_used(tr, fact) if tr else None,
        "tests": tests["tests"], "facts": gen.facts_passed(tests["tests"]),
        "success": tests["passed"] and valid,
        "jev_usd": transcripts.jev_cost(ev),
    }  # fmt: skip
    with _lock, ROWS.open("a", encoding="utf-8") as out:
        out.write(json.dumps(row) + "\n")
    print(json.dumps({"task": task, "success": row["success"], "facts": row["facts"],
                      "hooks": row["hooks"], "claude_r2": round(spent(), 4),
                      "jev": round(jev_spent(), 5)}), flush=True)  # fmt: skip
    return row


def key_from(env_file: str | None) -> str:
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key and env_file:
        for line in Path(env_file).read_text(encoding="utf-8").splitlines():
            if line.startswith("TYPESAFE_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        raise SystemExit("arm A needs TYPESAFE_API_KEY (environment or --env-file); not run")
    return key


def preflight(keyfile: Path) -> None:
    """One arrival decision through the real wrapper and key before any Claude session: the
    hook fails open in silence (README, round 2), so a bad key would otherwise measure mask
    compaction alone and call it the autopilot. Costs a few Jev decisions."""
    ev = ROOT / "preflight-r2"
    if ev.exists():
        shutil.rmtree(ev)
    ev.mkdir(parents=True)
    settings = settings_for(ev, keyfile)
    env = {**r1.child_env(None, ev, None), **json.loads(settings.read_text("utf-8"))["env"]}
    lines = [f"channel {i:03d} drift={i / 10000:.4f} ok" for i in range(400)]
    event = {
        "hook_event_name": "PostToolUse",
        "session_id": "preflight",
        "cwd": str(ev),
        "transcript_path": "",
        "tool_name": "Bash",
        "tool_input": {"command": "python tools/probe.py"},
        "tool_response": {"stdout": chr(10).join(lines), "stderr": "", "interrupted": False},
    }
    subprocess.run([r1.PYTHON, HOOK, str(ev), str(keyfile)], input=json.dumps(event), text=True,
                   capture_output=True, env=env, cwd=ev)  # fmt: skip
    events = [json.loads(x) for x in transcripts._lines(ev / "journal.jsonl")]
    decisions = [e["data"] for e in events if e.get("kind") == "decision"]
    good = [d for d in decisions if not d.get("error") and d.get("model") == "jev-1.13.0"]
    if not good:
        errors = sorted({str(d.get("error"))[:80] for d in decisions})
        raise SystemExit(
            f"preflight: no answered jev-1.13.0 decision ({len(decisions)} made, "
            f"errors {errors}); key or wiring broken, nothing launched"
        )
    print(json.dumps({"preflight_decisions": len(decisions), "jev_usd": transcripts.jev_cost(ev)}))


def run(chosen: list[str], env_file: str | None, workers: int) -> None:
    keyfile = ROOT / ".jev-key"
    keyfile.write_text(key_from(env_file), encoding="utf-8")
    os.chmod(keyfile, 0o600)
    try:
        preflight(keyfile)
    except SystemExit:
        keyfile.unlink(missing_ok=True)
        raise
    before = r1.marketplaces()
    import round3

    gate = Gate()
    gate.round3 = bool(chosen) and set(chosen) <= set(round3.TASKS)
    if not gate.round3 and set(chosen) & set(round3.TASKS):
        raise SystemExit("mix of round-3 and earlier tasks: run t07-t12 on their own")
    done = {r["task"] for r in rows()}
    try:
        with ThreadPoolExecutor(max_workers=max(1, min(workers, r1.WORKERS))) as pool:
            list(pool.map(lambda t: one(t, gate, keyfile), [t for t in chosen if t not in done]))
    finally:
        keyfile.unlink(missing_ok=True)
        added = sorted(set(r1.marketplaces()) - set(before))
        for name in added:
            subprocess.run(["claude", "plugin", "marketplace", "remove", name], capture_output=True)
        print(json.dumps({"marketplaces_added_and_removed": added}), flush=True)
    note = "STOPPED at a cap" if gate.stopped else "done"
    print(f"{note}: claude round 2 {spent():.4f} USD list, jev {jev_spent():.5f} USD", flush=True)


def dry() -> int:
    """Free: a PostToolUse and a UserPromptSubmit through the wrapper with no key (the hooks
    fail open), to check the settings, the wrapper and the log before anything is paid."""
    ev = ROOT / "dry-r2"
    if ev.exists():
        shutil.rmtree(ev)
    ev.mkdir(parents=True)
    settings = settings_for(ev, ev / "no-key")
    env = {**os.environ, **json.loads(settings.read_text("utf-8"))["env"]}
    env = {k: v for k, v in env.items() if k not in ("TYPESAFE_API_KEY", "ANTHROPIC_API_KEY")}
    big = "\n".join(f"line {i}: " + "x" * 60 for i in range(200))
    events = [
        {"hook_event_name": "PostToolUse", "session_id": "dry", "cwd": str(ev),
         "tool_name": "Bash", "tool_input": {"command": "python tools/x.py"},
         "tool_response": {"stdout": big, "stderr": "", "interrupted": False}},
        {"hook_event_name": "UserPromptSubmit", "session_id": "dry", "cwd": str(ev),
         "prompt": "set the token"},
    ]  # fmt: skip
    for event in events:
        subprocess.run([r1.PYTHON, HOOK, str(ev), str(ev / "no-key")], input=json.dumps(event),
                       text=True, capture_output=True, env=env, cwd=ev)  # fmt: skip
    print(json.dumps(hook_stats(ev)))
    print((ev / "settings.json").read_text("utf-8"))
    return 0


def b_input(part: dict[str, Any]) -> int:
    u = part.get("usage") or {}
    return sum(int(u.get(k) or 0) for k in (
        "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))  # fmt: skip


def fisher(a_yes: int, a_n: int, b_yes: int, b_n: int) -> dict[str, float]:
    """Fisher's exact test on a 2x2 table: two-sided (sum of tables no likelier than the one
    seen) and one-sided for A > N."""
    from math import comb

    total_yes, n = a_yes + b_yes, a_n + b_n

    def prob(k: int) -> float:
        return comb(a_n, k) * comb(b_n, total_yes - k) / comb(n, total_yes)

    ks = range(max(0, total_yes - b_n), min(a_n, total_yes) + 1)
    seen = prob(a_yes)
    two = sum(prob(k) for k in ks if prob(k) <= seen * (1 + 1e-9))
    one = sum(prob(k) for k in ks if k >= a_yes)
    return {"two_sided": round(min(1.0, two), 4), "one_sided_A_greater": round(one, 4)}


def per_task(t: str, a: dict[str, Any], n: dict[str, Any]) -> dict[str, Any]:
    ca, cn = costs.round2(t), costs.round1(t, "N")
    return {
        "task": t,
        "A_success": a["success"], "N_success": n["success"],
        "A_facts": a["facts"], "N_facts": n["facts"],
        "A_input": ca["total_input"], "N_input": cn["total_input"],
        "A_usd": ca["total_usd"], "N_usd": cn["total_usd"],
        "N_compact_usd": cn["compact_usd"], "N_compact_input": cn["compact_input"],
        "A_compaction": (a.get("compaction") or {}).get("kind"),
        "A_mask_fallback": a["compaction_hook"]["fallback"],
        "A_reduction": a["compaction_hook"]["reduction"],
        "hooks": a["hooks"], "arrival_in_transcript": a["arrival_in_transcript"],
        "A_re_reads": (a.get("after") or {}).get("re_reads"),
        "N_re_reads": (n.get("after") or {}).get("re_reads"),
        "A_summary_keeps": a.get("summary_keeps"), "N_summary_keeps": n.get("summary_keeps"),
        "jev_usd": a.get("jev_usd", 0.0),
    }  # fmt: skip


def summarise(per: list[dict[str, Any]]) -> dict[str, Any]:
    k = len(per)
    sa, sn = sum(p["A_success"] for p in per), sum(p["N_success"] for p in per)
    ia, inn = sum(p["A_input"] for p in per), sum(p["N_input"] for p in per)
    facts = {f: (sum(bool(p["A_facts"].get(f)) for p in per), sum(bool(p["N_facts"].get(f)) for p in per))  # noqa: E501
             for f in ("token", "probe", "window", "visible")}  # fmt: skip
    return {
        "tasks": k,
        "success": {"A": sa, "N": sn, "A_ci": r1_wilson(sa, k), "N_ci": r1_wilson(sn, k),
                    "fisher": fisher(sa, k, sn, k) if k else None},
        "facts_A_N": facts,
        "input_tokens_true": {"A": ia, "N": inn, "A_over_N": round(ia / inn - 1, 4) if inn else None},  # noqa: E501
        "usd_true": {"A": round(sum(p["A_usd"] for p in per), 4), "N": round(sum(p["N_usd"] for p in per), 4)},  # noqa: E501
        "HA1_success": sa >= sn - 1 if per else None,
        "HA2_tokens": ia < inn if per else None,
        "HA3_one_shot_facts": (facts["token"][0] >= facts["token"][1]
                               and facts["probe"][0] >= facts["probe"][1]) if per else None,
        "arrival_cuts": sum(p["hooks"]["arrival_cuts"] for p in per),
        "chars_saved": sum(p["hooks"]["chars_saved"] for p in per),
        "results_over_threshold": sum(p["hooks"]["over_6000"] for p in per),
        "recall_injections": {"prompt": sum(p["hooks"]["recall_on_prompt"] for p in per),
                              "tool": sum(p["hooks"]["recall_on_tool"] for p in per),
                              "chars": sum(p["hooks"]["recall_chars"] for p in per)},
        "mask": {"pruned": sum(not p["A_mask_fallback"] for p in per),
                 "reductions": [r for p in per for r in p["A_reduction"] if r is not None]},
        "re_reads_mean": {"A": round(mean(p["A_re_reads"] or 0 for p in per), 2) if per else None,
                          "N": round(mean(p["N_re_reads"] or 0 for p in per), 2) if per else None},
        "jev_usd": round(sum(p["jev_usd"] for p in per), 5),
    }  # fmt: skip


def collect() -> dict[str, Any]:
    """Pooled t01-t12 (amendment R3) and the two halves. Costs and HA2 tokens from `costs.py`."""
    import round3

    a_rows = {r["task"]: r for r in rows()}
    n_runs = {r["task"]: r for r in r1._rows(HERE / "runs.jsonl") if r["arm"] == "N"}
    both = [t for t in TASKS if t in a_rows and t in n_runs and a_rows[t]["valid_a"]]
    per = [per_task(t, a_rows[t], n_runs[t]) for t in both]
    first = [p for p in per if p["task"] not in round3.TASKS]
    second = [p for p in per if p["task"] in round3.TASKS]
    invalid = r1._rows(HERE / "runs-r2-invalid.jsonl")
    out = {
        "pooled": summarise(per),
        "t01_t06": summarise(first),
        "t07_t12": summarise(second),
        "invalid_attempts": [
            {
                "task": r["task"],
                "reason": r.get("invalid"),
                "usd_true": r["b"].get("cost_usd")
                or r["compact"].get("cost_usd")
                or r["a"].get("cost_usd"),
            }
            for r in invalid
        ],  # fmt: skip
        "round3_claude_usd_true": round(round3.spent(), 4),
        "per_task": per,
    }
    (HERE / "analysis-r2.json").write_text(json.dumps(out, indent=1) + chr(10), encoding="utf-8")
    return out


def r1_wilson(k: int, n: int) -> tuple[float, float]:
    import analyze

    return analyze.wilson(k, n)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("dry", "run", "collect"))
    parser.add_argument("--tasks", default="")
    parser.add_argument("--env-file", default=None)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args(argv)
    if args.action == "dry":
        return dry()
    if args.action == "collect":
        print(json.dumps({k: v for k, v in collect().items() if k != "per_task"}, indent=1))
        return 0
    chosen = [t for t in TASKS if not args.tasks or t in args.tasks.split(",")]
    run(chosen, args.env_file, args.workers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
