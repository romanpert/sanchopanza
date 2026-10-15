"""A3: the MCP guard replayed over ATBench-Codex through the hook's real path.

    python benchmarks/a3_mcp/replay.py --dry               # free: calls counted, cost estimated
    python benchmarks/a3_mcp/replay.py --seal              # seal prereg.md + code + data
    python benchmarks/a3_mcp/replay.py --run --live        # spends: Jev, hard cap in code
    python benchmarks/a3_mcp/replay.py --run               # free: replay of answers.jsonl only
    python benchmarks/a3_mcp/replay.py                     # analysis, free

Pre-registered in docs/results/2026-10-16-a3-mcp/prereg.md. Every ATBench-Codex trajectory (500,
250 unsafe) becomes a Claude Code transcript, and every assistant action a PreToolUse event with
that transcript's path, as Claude Code hands it to `sanchopanza hook`: `shell_command` as `Bash`,
any other tool as `mcp__<server>__<operation>` (the broad run's `cases.py` naming). Each event goes
through `claude_code.needs_decision` and `claude_code.handle` in two arms that differ in one
variable: `today` (provider jev, guard profile coding) and `mcp` (the same plus
SANCHOPANZA_GUARD_MCP=1). A trajectory is flagged when any of its calls is denied. A control,
`offline`, asks the point again about the 500 whole records at the same cut (server drift).

Deciders are in deciders.py: answers.jsonl first, then jev-1.13.0 through `CappedDecider` on
this run's own ledger (LEDGER_PATH, CAP_USD), stopped dead at a cap refusal, an outage, another
model or MAX_FAILURES failed or empty answers in a row. A run that leaves a call without a usable
answer scores nothing and asks for a relaunch (exit 2; 3 at a cap); from the MAX_LAUNCHES-th
launch on, what is still unanswered is scored fail-open (not flagged), listed, and P3 fails. The
key comes from TYPESAFE_API_KEY or the file SANCHOPANZA_KEYS_ENV names, never printed. ATBench is
read from a local copy (SANCHOPANZA_ATBENCH_CODEX, else the cache folder), never written here.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import sys
import tempfile
from collections.abc import Mapping, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))

from sanchopanza import _env  # noqa: E402


def _module(path: pathlib.Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


dec = _module(HERE / "deciders.py", "a3_deciders")
Answers, Estimate, Gate, StopDead, Tap = dec.Answers, dec.Estimate, dec.Gate, dec.StopDead, dec.Tap
HALTED, TAPPED, CAP, MODEL = dec.HALTED, dec.TAPPED, dec.CAP, dec.MODEL

OUT = REPO / "docs" / "results" / "2026-10-16-a3-mcp"
ANSWERS = OUT / "answers.jsonl"
CALLS = OUT / "calls.jsonl"
CONTROL = OUT / "control.jsonl"
LAUNCHES = OUT / "launches.json"
LEDGER_PATH = pathlib.Path("C:/sp-runs/a3-mcp/ledger.json")
# The whole run and any relaunch, its control included. The dry run expects about 0.08 USD (0.12
# at the flat median) for about 1,690 requests: room for the flat estimate and an overshoot.
CAP_USD = 0.25
BATCH = "a3-replay"
MAX_LAUNCHES = 3  # the first and two relaunches; then what is unanswered is scored fail-open
FLAT_USD = 71e-6  # a real Jev request's median (CLAUDE.md), the estimate quoted before a run
CONCURRENCY = 4
SHELL = "shell_command"
# Codex's own tools, which ATBench records beside the MCP servers' and Claude Code would not
# route through an MCP server: the replay names them mcp__ like the rest (the primary metric
# counts them, as registered); a reported metric leaves them out.
CODEX_NATIVE = frozenset({"read_mcp_resource", "list_mcp_resources", "read_thread_terminal",
                          "apply_patch", "request_user_input", "spawn_agent"})  # fmt: skip
BASE_ENV = {"SANCHOPANZA_PROVIDER": "jev", "SANCHOPANZA_GUARD_PROFILE": "coding"}
ARMS = {"mcp": {**BASE_ENV, "SANCHOPANZA_GUARD_MCP": "1"}, "today": dict(BASE_ENV)}


# ---- ATBench-Codex as Claude Code transcripts ---------------------------------------------------


def codex_path(given: str = "") -> pathlib.Path:
    """`given`, else SANCHOPANZA_ATBENCH_CODEX, else the copy in either cache folder (the
    cascade runs left it in the old one)."""
    if given or _env.get("ATBENCH_CODEX"):
        return pathlib.Path(given or _env.get("ATBENCH_CODEX"))
    cache = pathlib.Path.home() / ".cache"
    found = [cache / d / "atbench-codex-test.json" for d in ("sanchopanza", "sancho")]
    return next((p for p in found if p.is_file()), found[0])


def parse_action(raw: Any) -> dict[str, Any]:
    """ATBench writes actions as Python reprs; JSON and a bare name are read too."""
    if isinstance(raw, Mapping):
        return dict(raw)
    for parse in (json.loads, ast.literal_eval):
        try:
            value = parse(str(raw))
        except (ValueError, SyntaxError):
            continue
        if isinstance(value, Mapping):
            return dict(value)
    return {"name": str(raw), "arguments": {}}


def tool_of(action: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    name = str(action.get("name") or "")
    arguments = action.get("arguments")
    if name == SHELL and isinstance(arguments, Mapping):
        return "Bash", {"command": str(arguments.get("command") or "")}
    args = dict(arguments) if isinstance(arguments, Mapping) else {"value": arguments}
    server = re.sub(r"_mcp$", "", name) or name
    server = re.sub(r"[^A-Za-z0-9_-]+", "_", server) or "tool"
    op = args.get("operation")
    op = re.sub(r"[^A-Za-z0-9_]+", "_", str(op)) if op else "call"
    return f"mcp__{server}__{op}", args


def _text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def trajectory(record: Mapping[str, Any]) -> dict[str, Any]:
    """Transcript entries, and per call the index of the entry holding its tool use."""
    entries: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    last = ""
    for message in record["conversation"]:
        role = message.get("role")
        if role == "user":
            content = _text(message.get("content"))
            entries.append({"type": "user", "message": {"role": "user", "content": content}})
        elif role == "assistant":
            blocks: list[dict[str, Any]] = []
            if message.get("thought"):
                blocks.append({"type": "text", "text": _text(message["thought"])})
            if message.get("action"):
                action = parse_action(message["action"])
                tool, args = tool_of(action)
                last = f"toolu_{len(calls):02d}"
                blocks.append({"type": "tool_use", "id": last, "name": tool, "input": args})
                native = action.get("name") in CODEX_NATIVE
                calls.append({"i": len(calls), "at": len(entries), "tool": tool, "input": args,
                              "id": last, "native": native})  # fmt: skip
            elif message.get("response") or message.get("content"):
                said = _text(message.get("response") or message.get("content"))
                blocks.append({"type": "text", "text": said})
            entries.append({"type": "assistant", "message": {"role": "assistant",
                                                             "content": blocks}})  # fmt: skip
        elif role == "environment":
            entries.append({"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": last,
                 "content": _text(message.get("content"))}]}})  # fmt: skip
    return {"id": str(record["id"]), "label": "safe" if record["is_safe"] else "unsafe",
            "entries": entries, "calls": calls}  # fmt: skip


def load(path: pathlib.Path) -> list[dict[str, Any]]:
    return [trajectory(r) for r in json.loads(path.read_text(encoding="utf-8"))]


def family(tool: str) -> str:
    return "shell" if tool == "Bash" else "mcp"


def control_cases(path: pathlib.Path) -> list[dict[str, Any]]:
    """The offline point's own states (`cascade/run.load_codex`): whole records, as measured."""
    cascade = _module(REPO / "benchmarks" / "cascade" / "run.py", "a3_cascade_run")
    return cascade.load_codex(path)


# ---- the hook's real path -----------------------------------------------------------------------


def event_for(case: Mapping[str, Any], call: Mapping[str, Any], transcript: pathlib.Path,
              cwd: pathlib.Path) -> dict[str, Any]:  # fmt: skip
    return {"hook_event_name": "PreToolUse", "session_id": f"atb-{case['id']}",
            "transcript_path": str(transcript), "cwd": str(cwd), "permission_mode": "default",
            "tool_name": call["tool"], "tool_input": dict(call["input"]),
            "tool_use_id": call["id"]}  # fmt: skip


async def verdict(event: Mapping[str, Any], env: Mapping[str, str], decider: Any) -> dict:
    """What `sanchopanza hook` answers to `event` under `env`: main's fast path, then handle."""
    from sanchopanza.harness import claude_code as hook

    env = dict(env)
    if not hook.needs_decision(event, hook.config_from_env(env)):
        return {"decided": False, "denied": False, "p": None, "model": None, "error": None}
    seen: list[dict[str, Any]] = []
    token = TAPPED.set(seen)
    try:
        out = await hook.handle(dict(event), hook.guardian_from_env(env, decider=Tap(decider)))
    finally:
        TAPPED.reset(token)
    specific = (out or {}).get("hookSpecificOutput") or {}
    last = seen[-1] if seen else {}
    return {"decided": bool(seen), "denied": specific.get("permissionDecision") == "deny",
            "p": last.get("p"), "model": last.get("model"), "error": last.get("error")}  # fmt: skip


async def judge_case(case: Mapping[str, Any], decider: Any, root: pathlib.Path,
                     gate: asyncio.Semaphore) -> list[dict[str, Any]]:  # fmt: skip
    async with gate:
        rows = []
        work = root / "work"
        work.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as folder:
            for call in case["calls"]:
                path = pathlib.Path(folder) / f"{call['i']}.jsonl"
                lines = (json.dumps(e) for e in case["entries"][: call["at"] + 1])
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                event = event_for(case, call, path, work)
                arms = {}
                for arm, env in ARMS.items():
                    env = {**env, "SANCHOPANZA_JOURNAL": str(root / f"journal-{arm}.jsonl")}
                    arms[arm] = await verdict(event, env, decider)
                rows.append({"id": case["id"], "label": case["label"], "i": call["i"],
                             "family": family(call["tool"]), "native": call["native"],
                             "arms": arms})  # fmt: skip
        return rows


async def run_all(cases: Sequence[Mapping[str, Any]], decider: Any,
                  root: pathlib.Path) -> list[dict[str, Any]]:  # fmt: skip
    root.mkdir(parents=True, exist_ok=True)
    gate = asyncio.Semaphore(CONCURRENCY)
    done = await asyncio.gather(*(judge_case(c, decider, root, gate) for c in cases))
    return [row for rows in done for row in rows]


def reference() -> Any:
    """The offline answers of 2026-09-27 (fixtures/cascade-jev.jsonl), replayed: free."""
    from sanchopanza.providers.recorded import RecordedDecider

    return RecordedDecider.from_file(REPO / "fixtures" / "cascade-jev.jsonl")


async def run_control(cases: Sequence[Mapping[str, Any]], decider: Any,
                      recorded: Any = None) -> list[dict[str, Any]]:  # fmt: skip
    """The offline point re-asked: one decision per whole record, p kept (cut in analysis),
    beside the reference's p for the same record (`recorded`, read only)."""
    gate = asyncio.Semaphore(CONCURRENCY)

    async def one(case: Mapping[str, Any]) -> dict[str, Any]:
        args = (case["point"], case["state"], case["questions"])
        ref = dec.usable_p(await recorded.decide(*args)) if recorded is not None else None
        row = {"id": case["id"], "label": case["label"], "ref_p": ref}
        async with gate:
            try:
                decision = await decider.decide(*args)
            except Exception as error:  # noqa: BLE001 - noted, never scored as an answer
                return {**row, "p": None, "error": type(error).__name__}
        p = dec.usable_p(decision)
        return {**row, "p": p, "error": None if p is not None else (decision.error or
                                                                     "empty answer")}  # fmt: skip

    return list(await asyncio.gather(*(one(c) for c in cases)))


def clean_environment() -> None:
    """The hook reads a few things from the process environment (autopilot, project folder): a
    runner started inside a Claude Code session must not inherit them."""
    keep = {"SANCHOPANZA_KEYS_ENV", "SANCHOPANZA_ATBENCH_CODEX", "SANCHOPANZA_FUNDS_DIR"}
    for name in list(os.environ):
        if name == "CLAUDE_PROJECT_DIR" or (
            name.startswith(("SANCHOPANZA_", "SANCHO_")) and name not in keep
        ):
            os.environ.pop(name)


# ---- completeness -------------------------------------------------------------------------------


def unanswered(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """`<id>:<i>/<arm>` of every call without a usable answer: an MCP call the `mcp` arm did not
    decide, or any decision with an error or no p."""
    out = []
    for r in rows:
        for arm, v in r["arms"].items():
            missing_mcp = arm == "mcp" and r["family"] == "mcp" and not v["decided"]
            failed = v["decided"] and (v["error"] is not None or v["p"] is None)
            if missing_mcp or failed:
                out.append(f"{r['id']}:{r['i']}/{arm}")
    return out


def complete(rows: Sequence[Mapping[str, Any]]) -> bool:
    return not unanswered(rows)


def launches() -> int:
    try:
        return int(json.loads(LAUNCHES.read_text(encoding="utf-8"))["live"])
    except (OSError, ValueError, KeyError, TypeError):
        return 0


def count_launch() -> int:
    n = launches() + 1
    OUT.mkdir(parents=True, exist_ok=True)
    LAUNCHES.write_text(json.dumps({"live": n}) + "\n", encoding="utf-8", newline="\n")
    return n


# ---- dry: counts and cost -----------------------------------------------------------------------


def token_fit() -> tuple[float, float]:
    """tokens = a + b * record characters, least squares over the offline ATBench answers
    (fixtures/cascade-jev.jsonl, jev-1.13.0, whole trajectories). Free."""
    recorded = reference()
    points = []
    for case in control_cases(codex_path()):
        decision = asyncio.run(recorded.decide(case["point"], case["state"], case["questions"]))
        if decision.input_tokens:
            points.append((len(case["state"]["record"]), decision.input_tokens))
    n = len(points)
    mx, my = sum(x for x, _ in points) / n, sum(y for _, y in points) / n
    b = sum((x - mx) * (y - my) for x, y in points) / sum((x - mx) ** 2 for x, _ in points)
    return my - b * mx, b


def dry(cases: Sequence[Mapping[str, Any]], root: pathlib.Path,
        control: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:  # fmt: skip
    fit = token_fit()
    estimate = Estimate(fit)
    recorded = Answers(ANSWERS)
    rows = asyncio.run(run_all(cases, Gate(recorded, estimate), root))
    hook_calls = len(estimate.calls)
    asyncio.run(run_control(control, Gate(recorded, estimate)))
    calls = estimate.calls
    n_mcp = sum(r["family"] == "mcp" for r in rows)
    decided = {arm: sum(r["arms"][arm]["decided"] for r in rows) for arm in ARMS}
    return {
        "trajectories": len(cases), "calls": len(rows), "mcp_calls": n_mcp,
        "mcp_calls_codex_native": sum(r["family"] == "mcp" and r["native"] for r in rows),
        "shell_calls": len(rows) - n_mcp, "decisions_by_arm": decided,
        "already_recorded": len(recorded), "to_ask": len(calls),
        "to_ask_hook": hook_calls, "to_ask_control": len(calls) - hook_calls,
        "by_point": {p: sum(c["point"] == p for c in calls) for p in sorted({c["point"]
                                                                             for c in calls})},
        "record_chars_hook": _quantiles([c["chars"] for c in calls[:hook_calls]]),
        "usd_flat_71u": round(len(calls) * FLAT_USD, 4),
        "usd_fit": round(sum(c["fit_usd"] for c in calls), 4),
        "usd_fit_control": round(sum(c["fit_usd"] for c in calls[hook_calls:]), 4),
        "usd_reserved": round(sum(c["reserve_usd"] for c in calls), 4),
        "token_fit": [round(fit[0], 1), round(fit[1], 4)],
        "cap_usd": CAP_USD,
        "fits_under_cap": max(len(calls) * FLAT_USD, sum(c["fit_usd"] for c in calls)) <= CAP_USD,
    }  # fmt: skip


def _quantiles(values: Sequence[int]) -> dict[str, int]:
    if not values:
        return {}
    ordered = sorted(values)
    pick = lambda q: ordered[min(len(ordered) - 1, int(q * len(ordered)))]  # noqa: E731
    return {"min": ordered[0], "median": pick(0.5), "p90": pick(0.9), "max": ordered[-1]}


# ---- seal ---------------------------------------------------------------------------------------

SEALED_FIXED = ("benchmarks/a3_mcp/replay.py", "benchmarks/a3_mcp/deciders.py",
                "benchmarks/a3_mcp/analysis.py", "tests/test_a3_mcp_replay.py",
                "benchmarks/cascade/run.py", "benchmarks/meter.py",
                "benchmarks/jev114/l4_stats.py", "benchmarks/agentdojo/score.py",
                "fixtures/cascade-jev.jsonl")  # fmt: skip


def manifest(data: pathlib.Path) -> dict[str, str]:
    """`<path> -> sha256` of prereg.md, the code (LF bytes), the package and the data. Sealed
    before any answer exists: `seal` refuses once answers.jsonl is there."""

    def digest(path: pathlib.Path, text: bool = True) -> str:
        raw = path.read_bytes()
        return hashlib.sha256(raw.replace(b"\r\n", b"\n") if text else raw).hexdigest()

    package = sorted(p.relative_to(REPO).as_posix() for p in (REPO / "src").rglob("*.py")
                     if "__pycache__" not in p.parts)  # fmt: skip
    found = {f"results/{OUT.name}/prereg.md": digest(OUT / "prereg.md")}
    found |= {p: digest(REPO / p) for p in (*SEALED_FIXED, *package)}
    return found | {f"data:{data.name}": digest(data, text=False)}


def combined(found: Mapping[str, str]) -> str:
    return hashlib.sha256("".join(f"{k} {v}\n" for k, v in found.items()).encode()).hexdigest()


def seal(data: pathlib.Path) -> str:
    if ANSWERS.exists():
        raise SystemExit("answers.jsonl exists: a seal comes before any answer, nothing written")
    found = manifest(data)
    value = combined(found)
    target = OUT / "prereg.sha256"
    if target.exists() and target.read_text().strip() not in ("", value):
        raise SystemExit("prereg.sha256 already holds another seal: nothing written")
    (OUT / "prereg.manifest.json").write_text(json.dumps(found, indent=1) + "\n",
                                              encoding="utf-8", newline="\n")  # fmt: skip
    target.write_text(value + "\n", encoding="utf-8", newline="\n")
    return value


def seal_state(data: pathlib.Path) -> dict[str, Any]:
    target = OUT / "prereg.sha256"
    now = combined(manifest(data))
    sealed = target.read_text().strip() if target.exists() else ""
    return {"combined_now": now, "sealed": sealed or None, "matches_seal": now == sealed}


def require_seal(data: pathlib.Path) -> None:
    if not seal_state(data)["matches_seal"]:
        raise SystemExit("prereg.md, the code or the data differ from the seal: nothing spent")


# ---- live ---------------------------------------------------------------------------------------


def ledger_spent() -> float:
    from sanchopanza.budget import SpendLedger

    if not LEDGER_PATH.exists():
        return 0.0
    return SpendLedger(LEDGER_PATH, cap_usd=CAP_USD).spent(BATCH)


def require_own_answers() -> None:
    """Answers on disk with nothing spent on this run's ledger came from somewhere else."""
    if ANSWERS.exists() and ledger_spent() <= 0:
        raise SystemExit("answers.jsonl exists but this run's ledger holds no spend: refused")


def go_live(data: pathlib.Path) -> Any:
    from sanchopanza.providers import jev
    from sanchopanza.providers.jev import apreflight

    require_seal(data)
    require_own_answers()
    dec.load_key()
    jev.RETRYABLE = frozenset(jev.RETRYABLE - {429})  # stop at the first 429, never retry it
    result = asyncio.run(apreflight(model=MODEL))  # one Truth, ~13 micro-dollars, off the ledger
    if not result.ok or result.model != MODEL:
        raise SystemExit(f"preflight {MODEL}: {result.reason}, served {result.model}")
    return dec.live_decider(LEDGER_PATH, CAP_USD, BATCH)


def _write_jsonl(path: pathlib.Path, rows: Sequence[Mapping[str, Any]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8", newline="\n")


def run(cases: Sequence[Mapping[str, Any]], control: Sequence[Mapping[str, Any]],
        root: pathlib.Path, live: Any, launch: int) -> int:  # fmt: skip
    """Exit 0 with calls.jsonl and control.jsonl written, or 2/3 with nothing scored."""
    answers = Answers(ANSWERS, live)
    rows = asyncio.run(run_all(cases, answers, root))
    checks = asyncio.run(run_control(control, answers, reference()))
    missing = unanswered(rows) + [f"{c['id']}/offline" for c in checks if c["p"] is None]
    print(json.dumps({"asked": answers.asked, "halted": HALTED[:1], "unanswered": len(missing),
                      "launch": launch}), file=sys.stderr)  # fmt: skip
    if missing and launch < MAX_LAUNCHES:
        return 3 if HALTED and HALTED[0].startswith(CAP) else 2
    _write_jsonl(CALLS, rows)
    _write_jsonl(CONTROL, checks)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--codex", default="", help="ATBench-Codex test.json")
    parser.add_argument("--root", default=str(LEDGER_PATH.parent), help="transcripts, journals")
    parser.add_argument("--dry", action="store_true", help="free: count and estimate")
    parser.add_argument("--seal", action="store_true", help="seal prereg.md, code and data")
    parser.add_argument("--run", action="store_true", help="replay; --live asks what is missing")
    parser.add_argument("--live", action="store_true", help="spend: jev-1.13.0, capped in code")
    args = parser.parse_args(argv)
    data, root = codex_path(args.codex), pathlib.Path(args.root)
    if not data.is_file():
        raise SystemExit(f"ATBench-Codex not found at {data}: set SANCHOPANZA_ATBENCH_CODEX")
    clean_environment()
    if args.seal:
        print(seal(data))
        return 0
    cases, control = load(data), control_cases(data)
    if args.dry:
        report = json.dumps(dry(cases, root, control), indent=1) + "\n"
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "dry.json").write_text(report, encoding="utf-8", newline="\n")
        print(report, end="")
        return 0
    if args.run:
        live = go_live(data) if args.live else None
        code = run(cases, control, root, live, count_launch() if args.live else launches())
        if code:
            return code
    analysis = _module(HERE / "analysis.py", "a3_analysis")
    extra = {"seal": seal_state(data), "ledger_usd": round(ledger_spent(), 6),
             "launches": launches()}  # fmt: skip
    print(json.dumps(analysis.write(extra), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
