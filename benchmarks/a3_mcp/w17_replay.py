"""W17: the MCP guard after the call, replayed over ATBench-Codex through the hook's real path.

    python benchmarks/a3_mcp/w17_replay.py --dry          # free: counts, cost, scorer rehearsed
    python benchmarks/a3_mcp/w17_replay.py --seal         # seal w17_prereg.md + code + data
    w17-mcp-post-run.cmd (filled copy, started by WMI)   # spends: --run --live, hard cap
    python benchmarks/a3_mcp/w17_replay.py --run          # free: replay of the run's answers

Registration: w17_prereg.md, a DEVELOPMENT lot on A3's own trajectories. A3's replay turns every
ATBench-Codex trajectory into a Claude Code transcript; this reuses it. Per MCP call, two events
go through `claude_code.needs_decision` and `claude_code.handle`:

- `pre`: the PreToolUse event with SANCHOPANZA_GUARD_MCP=1, answered from A3's answers.jsonl
  only (free, never asked again) and checked against A3's calls.jsonl;
- `post`: the PostToolUse event, the call's result as `tool_response`, with
  SANCHOPANZA_GUARD_MCP_POST=1: the `actions` point with the result last.

Cuts are applied in w17_analysis.py from each call's p. The live run starts only from the sealed
launcher (`w17-mcp-post-run.cmd`, its filled copy equal but for PY, SANCHOPANZA_KEYS_ENV and WT),
at the sealing commit (HEAD, one parent, changing only the seal files), on a clean tree. What a
run writes (answers, rows, analysis, launches, status) goes to the run folder RUN, outside the
repository, so a relaunch still finds the tree clean. Live answers go to RUN/w17_answers.jsonl
through `CappedDecider` on this run's own ledger (LEDGER_PATH, CAP_USD, BATCH, batch cap
CAP_USD) and A3's `StopDead` (a cap refusal, an outage, another model, three failures in a row).

- A launch stopped at the cap: the lot is NOT RUN (w17_status.json, exit 3), with no outcome;
  raising the cap is a labelled amendment and a new seal, and until then no live launch starts.
- A launch stopped dead otherwise (an outage, another model): a pause, not counted (exit 2).
- A launch that ends with a post call unanswered counts towards MAX_LAUNCHES (exit 2); at the
  last one the lot is NOT RUN (exit 4). Nothing is ever scored fail-open.

A relaunch replays what is recorded for free. Shell calls are left out (7, none denied in A3).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE))

import replay  # noqa: E402  (A3's transcripts, events, deciders and verdict)

dec = replay.dec
analysis = replay._module(HERE / "w17_analysis.py", "w17_analysis")

LEDGER_PATH = pathlib.Path("C:/sp-runs/w17-mcp-post/ledger.json")
RUN = LEDGER_PATH.parent  # untracked: what a run writes
ANSWERS = RUN / "w17_answers.jsonl"
CALLS = RUN / "w17_calls.jsonl"
ANALYSIS = RUN / "w17_analysis.json"
STATUS = RUN / "w17_status.json"
LAUNCHES = RUN / "w17_launches.json"
DRY = HERE / "w17_dry.json"
CEILING = HERE / "w17_ceiling.json"
LAUNCHER = "benchmarks/a3_mcp/w17-mcp-post-run.cmd"
# The launcher's local values are read as placeholders by the seal: the tracked file holds
# placeholders, the filled copy lives in RUN, and both hash the same (lot.py's rule).
LOCAL_VALUES = re.compile(r'^(set "(?:PY|SANCHOPANZA_KEYS_ENV|WT)=)[^"\n]*(")', re.MULTILINE)
MAX_LAUNCHES = 3  # the first and two relaunches, as A3
# The registered set, asserted before anything is scored.
N_TRAJECTORIES, N_PER_CLASS, N_MCP_CALLS = 500, 250, 1188
PREREG, SHA, MANIFEST = HERE / "w17_prereg.md", HERE / "w17_prereg.sha256", HERE / "w17.manifest"
# Ledger dollars: `CappedDecider` prices input tokens only (PRICE_PER_MTOK). The dry run's token
# fit gives about 52 of them an answer here (0.062 for 1,188); at the flat 71 µ$ median a run
# stopped at this cap would bill about 0.20 x 71 / 52 = 0.27 USD (0.34 at A3's 42 µ$ an answer).
CAP_USD = 0.20
BATCH = "w17-mcp-post"
PRE_ENV = dict(replay.ARMS["mcp"])
POST_ENV = {**replay.BASE_ENV, "SANCHOPANZA_GUARD_MCP_POST": "1"}
SEALED = ("benchmarks/a3_mcp/w17_replay.py", "benchmarks/a3_mcp/w17_analysis.py",
          "benchmarks/a3_mcp/replay.py", "benchmarks/a3_mcp/deciders.py",
          "benchmarks/cascade/run.py", "benchmarks/meter.py", "benchmarks/jev114/l4_stats.py",
          "benchmarks/agentdojo/score.py", "benchmarks/a3_mcp/diagnose.py",
          "benchmarks/a3_mcp/analysis.py", "benchmarks/a3_mcp/w17_ceiling.py",
          "benchmarks/a3_mcp/w17_ceiling.json", "benchmarks/a3_mcp/w17_dry.json",
          "tests/test_mcp_post.py", "tests/test_w17_mcp_post_replay.py",
          "fixtures/cascade-jev.jsonl", LAUNCHER,
          "docs/results/2026-10-16-a3-mcp/answers.jsonl",
          "docs/results/2026-10-16-a3-mcp/calls.jsonl")  # fmt: skip


def result_of(case: Mapping[str, Any], call: Mapping[str, Any]) -> str:
    """The tool result that follows the call in the transcript (every ATBench call has one)."""
    entry = case["entries"][call["at"] + 1]
    return str(entry["message"]["content"][0]["content"])


def post_event(case: Mapping[str, Any], call: Mapping[str, Any], transcript: pathlib.Path,
               cwd: pathlib.Path) -> dict[str, Any]:  # fmt: skip
    event = replay.event_for(case, call, transcript, cwd)
    return {**event, "hook_event_name": "PostToolUse", "tool_response": result_of(case, call)}


async def post_verdict(event: Mapping[str, Any], env: Mapping[str, str], decider: Any) -> dict:
    """What `sanchopanza hook` answers to a PostToolUse `event`: main's fast path, then handle."""
    from sanchopanza.harness import claude_code as hook

    if not hook.needs_decision(event, hook.config_from_env(dict(env))):
        return {"decided": False, "blocked": False, "p": None, "model": None, "error": None}
    seen: list[dict[str, Any]] = []
    token = dec.TAPPED.set(seen)
    try:
        out = await hook.handle(
            dict(event), hook.guardian_from_env(dict(env), decider=dec.Tap(decider))
        )
    finally:
        dec.TAPPED.reset(token)
    last = seen[-1] if seen else {}
    return {"decided": bool(seen), "blocked": (out or {}).get("decision") == "block",
            "p": last.get("p"), "model": last.get("model"), "error": last.get("error")}  # fmt: skip


async def judge_case(case: Mapping[str, Any], pre: Any, post: Any, root: pathlib.Path,
                     gate: asyncio.Semaphore) -> list[dict[str, Any]]:  # fmt: skip
    mcp = [c for c in case["calls"] if replay.family(c["tool"]) == "mcp"]
    rows = []
    async with gate:
        work = root / "work"
        work.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as folder:
            for call in mcp:
                path = pathlib.Path(folder) / f"{call['i']}.jsonl"
                lines = (json.dumps(e) for e in case["entries"][: call["at"] + 1])
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                journal = {"SANCHOPANZA_JOURNAL": str(root / "journal-w17.jsonl")}
                event = replay.event_for(case, call, path, work)
                before = await replay.verdict(event, {**PRE_ENV, **journal}, pre)
                after = await post_verdict(post_event(case, call, path, work),
                                           {**POST_ENV, **journal}, post)  # fmt: skip
                rows.append({"id": case["id"], "label": case["label"], "i": call["i"],
                             "native": call["native"], "last": call is mcp[-1],
                             "pre": before, "post": after})  # fmt: skip
    return rows


async def run_all(cases: Sequence[Mapping[str, Any]], pre: Any, post: Any,
                  root: pathlib.Path) -> list[dict[str, Any]]:  # fmt: skip
    root.mkdir(parents=True, exist_ok=True)
    gate = asyncio.Semaphore(replay.CONCURRENCY)
    done = await asyncio.gather(*(judge_case(c, pre, post, root, gate) for c in cases))
    return [row for rows in done for row in rows]


def pre_matches_a3(rows: Sequence[Mapping[str, Any]]) -> bool:
    """Every pre p equals A3's sealed `mcp` arm p for the same call (the record did not move)."""
    sealed = {(r["id"], r["i"]): r["arms"]["mcp"]["p"] for r in replay._sealed_rows()
              if r["family"] == "mcp"}  # fmt: skip
    return len(sealed) == len(rows) and all(sealed.get((r["id"], r["i"])) == r["pre"]["p"]
                                            for r in rows)  # fmt: skip


def labels(data: pathlib.Path) -> dict[str, dict[str, Any]]:
    return {str(r["id"]): r for r in json.loads(data.read_text(encoding="utf-8"))}


def gained() -> list[str]:
    """The 33 the free ceiling says the last result adds (w17_ceiling.json)."""
    return list(json.loads(CEILING.read_text(encoding="utf-8"))["gained_ids"])


def check_set(cases: Sequence[Mapping[str, Any]],
              rows: Sequence[Mapping[str, Any]] | None = None) -> None:  # fmt: skip
    """The registered set or nothing: 500 trajectories, 250 per class, and (with `rows`) 1,188
    MCP calls that group back into 500 trajectories, 250 per class."""
    unsafe = sum(c["label"] == "unsafe" for c in cases)
    found = (len(cases), unsafe, len(cases) - unsafe)
    if found != (N_TRAJECTORIES, N_PER_CLASS, N_PER_CLASS):
        raise SystemExit(f"not the registered set: {found}, nothing spent or scored")
    if rows is None:
        return
    labels_of = {r["id"]: r["label"] for r in rows}
    grouped = (len(rows), len(labels_of), sum(v == "unsafe" for v in labels_of.values()))
    if grouped != (N_MCP_CALLS, N_TRAJECTORIES, N_PER_CLASS):
        raise SystemExit(f"not the registered rows: {grouped}, nothing scored")


# ---- dry ----------------------------------------------------------------------------------------


def rehearsal(rows: Sequence[Mapping[str, Any]], data: pathlib.Path) -> list[dict[str, Any]]:
    """The scorer exercised end to end without a post answer: each trajectory's last post p is
    the offline reference's p (its record ends on the last result, w17_ceiling.py), the others
    0.0. A free proxy, labelled as one; never scored as the result."""
    import diagnose

    ref = diagnose.reference_p(data)
    return [{**r, "post": {**r["post"], "decided": True, "error": None, "model": dec.MODEL,
                           "p": ref[r["id"]] if r["last"] else 0.0}} for r in rows]  # fmt: skip


def dry(cases: Sequence[Mapping[str, Any]], root: pathlib.Path, data: pathlib.Path) -> dict:
    estimate = dec.Estimate(replay.token_fit())
    pre = dec.Answers(replay.ANSWERS)
    rows = asyncio.run(run_all(cases, pre, dec.Gate(dec.Answers(ANSWERS), estimate), root))
    calls = estimate.calls
    flat = len(calls) * replay.FLAT_USD
    fit = sum(c["fit_usd"] for c in calls)
    check_set(cases, rows)
    proxy = analysis.analyse(rehearsal(rows, data), labels(data), pre_matches_a3(rows), gained())
    return {
        "trajectories": len(cases), "mcp_calls": len(rows),
        "pre_replayed_free": len(pre.seen), "pre_asked": pre.asked,
        "pre_unanswered": sum(r["pre"]["p"] is None for r in rows),
        "pre_matches_a3": pre_matches_a3(rows),
        "post_decided_by_the_hook": sum(r["post"]["decided"] for r in rows),
        "post_to_ask": len(calls),
        "record_chars_post": replay._quantiles([c["chars"] for c in calls]),
        "usd_flat_71u": round(flat, 4), "usd_fit": round(fit, 4),
        "usd_reserved_each_at_most": round(max((c["reserve_usd"] for c in calls),
                                               default=0.0), 6),
        "cap_usd": CAP_USD, "fits_under_cap": max(flat, fit) <= CAP_USD,
        "rehearsal_proxy_not_a_result": {"arms": proxy["arms"], "paired": proxy["paired"],
                                         "ceiling_33": proxy["ceiling_33"],
                                         "proxy_outcome": proxy["development_rule"]},
    }  # fmt: skip


# ---- seal and live ------------------------------------------------------------------------------


def manifest(data: pathlib.Path) -> dict[str, str]:
    def digest(path: pathlib.Path, text: bool = True) -> str:
        raw = path.read_bytes()
        return hashlib.sha256(raw.replace(b"\r\n", b"\n") if text else raw).hexdigest()

    package = sorted(p.relative_to(REPO).as_posix() for p in (REPO / "src").rglob("*.py")
                     if "__pycache__" not in p.parts)  # fmt: skip
    found = {"benchmarks/a3_mcp/w17_prereg.md": digest(PREREG)}
    found |= {p: digest(REPO / p) for p in (*SEALED, *package) if p != LAUNCHER}
    found[LAUNCHER] = hashlib.sha256(launcher_text(REPO / LAUNCHER)).hexdigest()
    return found | {f"data:{data.name}": digest(data, text=False)}


def launcher_text(path: pathlib.Path) -> bytes:
    """A launcher with LF ends and its local values as placeholders."""
    text = path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
    return LOCAL_VALUES.sub(r"\1<LOCAL>\2", text).encode("utf-8")


def require_launcher(env: Mapping[str, str] | None = None) -> None:
    """Started by the sealed launcher: the copy that ran (SANCHOPANZA_LAUNCHER, which it sets)
    equals the tracked one but for its local values."""
    ran = (os.environ if env is None else env).get("SANCHOPANZA_LAUNCHER", "")
    if not ran or not pathlib.Path(ran).is_file():
        raise SystemExit("not started by the lot's launcher: nothing spent")
    if launcher_text(pathlib.Path(ran)) != launcher_text(REPO / LAUNCHER):
        raise SystemExit(f"{ran} differs from the sealed {LAUNCHER}: nothing spent")


def _git(*args: str) -> str:
    done = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)
    if done.returncode:
        raise SystemExit(f"git {' '.join(args)} failed: {done.stderr.strip()[:200]}")
    return done.stdout.strip()


def require_seal_commit() -> str:
    """HEAD is the sealing commit (the last that touched w17_prereg.sha256), with one parent,
    changing only the seal files, and the tree is clean. Returns HEAD."""
    rel = [x.relative_to(REPO).as_posix() for x in (SHA, MANIFEST)]
    head, sealed = _git("rev-parse", "HEAD"), _git("log", "-1", "--format=%H", "--", rel[0])
    if not sealed or head != sealed:
        raise SystemExit(f"HEAD {head[:9]} is not the sealing commit {sealed[:9]}: nothing spent")
    if len(_git("rev-list", "--parents", "-n", "1", "HEAD").split()) != 2:
        raise SystemExit("the sealing commit has not exactly one parent: nothing spent")
    changed = set(_git("diff", "--name-only", "HEAD^", "HEAD").split())
    if not changed <= set(rel):
        raise SystemExit(f"the sealing commit changes {sorted(changed)}: nothing spent")
    if _git("status", "--porcelain"):
        raise SystemExit("the worktree is not clean: nothing spent")
    return head


def seal(data: pathlib.Path) -> str:
    if ANSWERS.exists():
        raise SystemExit("w17_answers.jsonl exists: a seal comes before any answer")
    found = manifest(data)
    value = replay.combined(found)
    if SHA.exists() and SHA.read_text().strip() not in ("", value):
        raise SystemExit("w17_prereg.sha256 already holds another seal: nothing written")
    MANIFEST.write_text(json.dumps(found, indent=1) + "\n", encoding="utf-8", newline="\n")
    SHA.write_text(value + "\n", encoding="utf-8", newline="\n")
    return value


def seal_state(data: pathlib.Path) -> dict[str, Any]:
    sealed = SHA.read_text().strip() if SHA.exists() else ""
    if not sealed:
        return {"combined_now": None, "sealed": None, "matches_seal": False}
    now = replay.combined(manifest(data))
    return {"combined_now": now, "sealed": sealed or None, "matches_seal": now == sealed}


def ledger_spent() -> float:
    from sanchopanza.budget import SpendLedger

    if not LEDGER_PATH.exists():
        return 0.0
    return SpendLedger(LEDGER_PATH, cap_usd=CAP_USD).spent(BATCH)


def launches() -> int:
    try:
        return int(json.loads(LAUNCHES.read_text(encoding="utf-8"))["live"])
    except (OSError, ValueError, KeyError, TypeError):
        return 0


def _write(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8", newline="\n")


def go_live(data: pathlib.Path, cases: Sequence[Mapping[str, Any]],
            launcher: Mapping[str, str] | None = None) -> Any:  # fmt: skip
    check_set(cases)  # the registered set, before anything else and before any spend
    if STATUS.exists():
        raise SystemExit(f"{STATUS.name} says the lot is not run: an amendment comes first")
    if launches() >= MAX_LAUNCHES:
        raise SystemExit("every allowed launch is used: nothing spent")
    head = require_seal_commit()
    if not seal_state(data)["matches_seal"]:
        raise SystemExit("w17_prereg.md, the code or the data differ from the seal: nothing spent")
    require_launcher(launcher)
    print(f"HEAD {head} (seal)", flush=True)
    if ANSWERS.exists() and ledger_spent() <= 0:
        raise SystemExit("w17_answers.jsonl exists but this run's ledger holds no spend: refused")
    replay.preflight()
    return dec.live_decider(LEDGER_PATH, CAP_USD, BATCH, CAP_USD)


def run(cases: Sequence[Mapping[str, Any]], root: pathlib.Path, data: pathlib.Path,
        live: Any) -> int:  # fmt: skip
    post = dec.Answers(ANSWERS, live)
    rows = asyncio.run(run_all(cases, dec.Answers(replay.ANSWERS), post, root))
    check_set(cases, rows)
    cover = analysis.coverage(rows)
    state = {
        "asked": post.asked,
        "halted": dec.HALTED[:1],
        "post_unanswered": len(cover["post_unanswered"]),
    }
    print(json.dumps(state), file=sys.stderr)
    if cover["post_unanswered"] or cover["pre_unanswered"]:
        return stopped(live is not None)
    RUN.mkdir(parents=True, exist_ok=True)
    CALLS.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8", newline="\n")
    extra = {"seal": seal_state(data), "ledger_usd": round(ledger_spent(), 6),
             "launches": launches()}  # fmt: skip
    result = analysis.write(rows, labels(data), pre_matches_a3(rows), ANALYSIS, gained(), extra)
    print(json.dumps(result["development_rule"], indent=1))
    return 0


def stopped(live: bool) -> int:
    """A run with a call unanswered: the cap makes the lot NOT RUN (3); a pause is not counted
    (2); otherwise the launch counts, and the last allowed one makes the lot NOT RUN (4)."""
    if dec.HALTED and dec.HALTED[0].startswith(dec.CAP):
        _write(STATUS, {"status": "not run", "why": "stopped at the cap", "cap_usd": CAP_USD})
        return 3
    if dec.HALTED or not live:
        return 2
    n = launches() + 1
    _write(LAUNCHES, {"live": n})
    if n >= MAX_LAUNCHES:
        _write(STATUS, {"status": "not run", "why": f"unanswered after {n} launches"})
        return 4
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--codex", default="", help="ATBench-Codex test.json")
    parser.add_argument("--root", default=str(LEDGER_PATH.parent), help="transcripts, journals")
    parser.add_argument("--dry", action="store_true", help="free: count, estimate, rehearse")
    parser.add_argument("--dry-out", default=str(DRY), help="where --dry writes its report")
    parser.add_argument("--seal", action="store_true", help="seal w17_prereg.md, code and data")
    parser.add_argument("--run", action="store_true", help="replay; --live asks what is missing")
    parser.add_argument("--live", action="store_true", help="spend: jev-1.13.0, capped in code")
    args = parser.parse_args(argv)
    data, root = replay.codex_path(args.codex), pathlib.Path(args.root)
    if not data.is_file():
        raise SystemExit(f"ATBench-Codex not found at {data}: set SANCHOPANZA_ATBENCH_CODEX")
    # Read before A3's scrub, which drops every SANCHOPANZA_* it does not keep: the first sealed
    # launch (09ef1b9) was refused because the launcher's own variable was gone by then.
    launcher = {"SANCHOPANZA_LAUNCHER": os.environ.get("SANCHOPANZA_LAUNCHER", "")}
    replay.clean_environment()
    cases = replay.load(data)
    if args.seal:
        print(seal(data))
        return 0
    if args.dry:
        report = json.dumps(dry(cases, root, data), indent=1) + "\n"
        pathlib.Path(args.dry_out).write_text(report, encoding="utf-8", newline="\n")
        print(report, end="")
        return 0
    if args.run:
        return run(cases, root, data, go_live(data, cases, launcher) if args.live else None)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
