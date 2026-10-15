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
variable: `today` (what `install` writes: provider jev, guard profile coding) and `mcp` (the same
plus SANCHOPANZA_GUARD_MCP=1). A trajectory is flagged when any of its calls is denied.

Answers are recorded first, asked second: `answers.jsonl` (hashed keys and numbers, no text) is
read before any call, so a relaunch pays only for what is missing. Live calls go to jev-1.13.0
through `CappedDecider` on this run's own ledger (LEDGER_PATH, LEDGER_CAP_USD) and are stopped
dead at a cap refusal, an outage (HTTP 401/402/403/429/5xx, no connection), another model, or
MAX_FAILURES failed calls in a row: every later call is refused unasked, nothing is scored, and
the exit code says why (3 cap, 2 pause). The key comes from TYPESAFE_API_KEY or the file
SANCHOPANZA_KEYS_ENV names, inside the process, never printed. ATBench is read from a local copy
(SANCHOPANZA_ATBENCH_CODEX, else the cache folder) and never written here.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import contextvars
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))

from sanchopanza import _env  # noqa: E402
from sanchopanza.contract import DeciderUnavailable, Decision  # noqa: E402
from sanchopanza.providers.recorded import key_of, order_of  # noqa: E402

OUT = REPO / "docs" / "results" / "2026-10-16-a3-mcp"
ANSWERS = OUT / "answers.jsonl"
CALLS = OUT / "calls.jsonl"
LEDGER_PATH = pathlib.Path("C:/sp-runs/a3-mcp/ledger.json")
# The whole run and any relaunch. The dry run expects 0.051 USD (0.084 at the flat median) for
# 1,189 requests: the cap leaves room for the flat estimate and its worst-case overshoot.
LEDGER_CAP_USD = 0.15
BATCH, BATCH_CAP_USD = "a3-replay", 0.15
MODEL = "jev-1.13.0"
PRICE_PER_MTOK = 0.042
FLAT_USD = 71e-6  # a real Jev request's median (CLAUDE.md), the estimate quoted before a run
CONCURRENCY = 4
TIMEOUT_S = 20.0
MAX_FAILURES = 3
STOP_STATUSES = frozenset({401, 402, 403, 429})
SHELL = "shell_command"
BASE_ENV = {"SANCHOPANZA_PROVIDER": "jev", "SANCHOPANZA_GUARD_PROFILE": "coding"}
ARMS = {"mcp": {**BASE_ENV, "SANCHOPANZA_GUARD_MCP": "1"}, "today": dict(BASE_ENV)}
CAP, PAUSE = "cap", "pause"
HALTED: list[str] = []
TAPPED: contextvars.ContextVar[list[dict[str, Any]] | None] = contextvars.ContextVar(
    "a3_tapped", default=None
)


def _module(path: pathlib.Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


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
                tool, args = tool_of(parse_action(message["action"]))
                last = f"toolu_{len(calls):02d}"
                blocks.append({"type": "tool_use", "id": last, "name": tool, "input": args})
                calls.append({"i": len(calls), "at": len(entries), "tool": tool, "input": args,
                              "id": last})  # fmt: skip
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


# ---- deciders -----------------------------------------------------------------------------------


class Answers:
    """Recorded first (answers.jsonl, then this run's), `live` second; a live answer is written
    down. Without `live` a miss is an empty decision: the hook fails open and the row says so."""

    def __init__(self, path: pathlib.Path, live: Any = None) -> None:
        self.name, self.model, self._path, self._live = "jev", MODEL, path, live
        self._known: dict[tuple[str, str], Decision] = {}
        self.asked = 0
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        for line in filter(None, lines):
            row = json.loads(line)
            if row.get("model") == MODEL:
                self._known[(row["key"], row["order"])] = _decision_of(row)

    def __len__(self) -> int:
        return len(self._known)

    async def decide(self, point: str, state: Any, questions: Mapping[str, Any]) -> Decision:
        slot = (key_of(point, state, questions, MODEL), order_of(questions))
        if slot in self._known:
            return replace(self._known[slot], provider="recorded", cost_usd=0.0, latency_ms=0)
        if self._live is None:
            return Decision(point, {}, "recorded", "-", error="not recorded")
        self.asked += 1
        decision = await self._live.decide(point, state, questions)
        if decision.answers and not decision.failed:
            self._known[slot] = decision
            self._write(slot, point, decision)
        return decision

    def _write(self, slot: tuple[str, str], point: str, decision: Decision) -> None:
        row = {"key": slot[0], "order": slot[1], "point": point, "model": decision.model,
               "default": False, "input_tokens": decision.input_tokens,
               "cost_usd": decision.cost_usd, "latency_ms": decision.latency_ms,
               "answers": {k: a.to_dict() for k, a in decision.answers.items()}}  # fmt: skip
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row) + "\n")


def _decision_of(row: Mapping[str, Any]) -> Decision:
    from sanchopanza.contract import Answer

    answers = {k: Answer.from_dict(v) for k, v in (row.get("answers") or {}).items()}
    return Decision(str(row.get("point")), answers, "recorded", str(row["model"]),
                    input_tokens=int(row.get("input_tokens") or 0),
                    cost_usd=float(row.get("cost_usd") or 0.0))  # fmt: skip


class Estimate:
    """Dry: asks nothing; notes what each distinct call would send and its price three ways
    (a question both arms ask is paid once: `Answers` keeps the first answer)."""

    def __init__(self, fit: tuple[float, float]) -> None:
        self.name, self.model, self.calls, self._fit = "dry", MODEL, [], fit
        self._seen: set[tuple[str, str]] = set()

    async def decide(self, point: str, state: Any, questions: Mapping[str, Any]) -> Decision:
        from sanchopanza.providers.capped import estimate_usd

        slot = (key_of(point, state, questions, MODEL), order_of(questions))
        if slot in self._seen:
            return Decision(point, {}, "dry", "-", error="dry run: asked already")
        self._seen.add(slot)
        chars = len(str(state.get("record") or state.get("command") or ""))
        tokens = self._fit[0] + self._fit[1] * chars
        self.calls.append({"point": point, "chars": chars,
                           "reserve_usd": estimate_usd(state, questions,
                                                       price_per_mtok=PRICE_PER_MTOK),
                           "fit_usd": tokens * PRICE_PER_MTOK / 1e6})  # fmt: skip
        return Decision(point, {}, "dry", "-", error="dry run: not asked")


class Tap:
    """Notes every decision of the event being judged (TAPPED), and passes it on."""

    def __init__(self, inner: Any) -> None:
        self._inner, self.name, self.model = inner, inner.name, MODEL

    async def decide(self, point: str, state: Any, questions: Mapping[str, Any]) -> Decision:
        seen = TAPPED.get()
        try:
            decision = await self._inner.decide(point, state, questions)
        except DeciderUnavailable as error:
            if seen is not None:
                seen.append({"point": point, "p": None, "model": "-", "error": str(error)[:200]})
            raise
        if seen is not None:
            answer = next(iter(decision.answers.values()), None)
            p = answer.truth if answer is not None else None
            error = decision.error or (None if decision.answers else "no answer")
            seen.append({"point": point, "p": p, "model": decision.model, "error": error,
                         "provider": decision.provider})  # fmt: skip
        return decision


class StopDead:
    """A live decider that stops the run dead (HALTED) at a cap refusal, an outage, another
    model, or MAX_FAILURES failed calls in a row; every later call is refused unasked."""

    def __init__(self, inner: Any) -> None:
        self._inner, self.name, self._fails = inner, inner.name, 0

    async def decide(self, point: str, state: Any, questions: Mapping[str, Any]) -> Decision:
        from sanchopanza.providers.capped import SpendCapReached

        if HALTED:
            raise DeciderUnavailable(f"halted, not called: {HALTED[0]}")
        try:
            decision = await self._inner.decide(point, state, questions)
        except SpendCapReached as error:
            HALTED.append(f"{CAP}: {error}")
            raise
        except Exception as error:
            self._failed(error)
            raise
        if decision.model != MODEL:
            HALTED.append(f"{PAUSE}: asked {MODEL}, served {decision.model}: not recorded")
            raise DeciderUnavailable(HALTED[-1])
        if decision.failed or not decision.answers:
            self._failed(RuntimeError(decision.error or "no answers"))
        else:
            self._fails = 0
        return decision

    def _failed(self, error: Exception) -> None:
        self._fails += 1
        found = re.search(r"HTTP (\d{3})", str(error))
        outage = found and (int(found.group(1)) in STOP_STATUSES or int(found.group(1)) >= 500)
        if (outage or "unreachable" in str(error) or self._fails >= MAX_FAILURES) and not HALTED:
            HALTED.append(f"{PAUSE}: {type(error).__name__}: {str(error)[:200]}")


def live_decider() -> Any:
    from sanchopanza.budget import SpendLedger
    from sanchopanza.providers import CappedDecider
    from sanchopanza.providers.jev import JevDecider

    ledger = SpendLedger(LEDGER_PATH, cap_usd=LEDGER_CAP_USD)
    jev = JevDecider(model=MODEL, timeout_s=TIMEOUT_S, long_context=False, images=False)
    return StopDead(CappedDecider(jev, ledger=ledger, batch=BATCH, max_usd=BATCH_CAP_USD,
                                  price_per_mtok=PRICE_PER_MTOK))  # fmt: skip


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
                             "family": family(call["tool"]), "arms": arms})  # fmt: skip
        return rows


async def run_all(cases: Sequence[Mapping[str, Any]], decider: Any,
                  root: pathlib.Path) -> list[dict[str, Any]]:  # fmt: skip
    root.mkdir(parents=True, exist_ok=True)
    gate = asyncio.Semaphore(CONCURRENCY)
    done = await asyncio.gather(*(judge_case(c, decider, root, gate) for c in cases))
    return [row for rows in done for row in rows]


def clean_environment() -> None:
    """The hook reads a few things from the process environment (autopilot, project folder): a
    runner started inside a Claude Code session must not inherit them."""
    keep = {"SANCHOPANZA_KEYS_ENV", "SANCHOPANZA_ATBENCH_CODEX", "SANCHOPANZA_FUNDS_DIR"}
    for name in list(os.environ):
        if name == "CLAUDE_PROJECT_DIR" or (
            name.startswith(("SANCHOPANZA_", "SANCHO_")) and name not in keep
        ):
            os.environ.pop(name)


# ---- dry: counts and cost -----------------------------------------------------------------------


def token_fit(cases: Sequence[Mapping[str, Any]] | None = None) -> tuple[float, float]:
    """tokens = a + b * record characters, least squares over the offline ATBench answers
    (fixtures/cascade-jev.jsonl, jev-1.13.0, whole trajectories). Free."""
    cascade = _module(REPO / "benchmarks" / "cascade" / "run.py", "a3_cascade_run")
    from sanchopanza.providers.recorded import RecordedDecider

    recorded = RecordedDecider.from_file(REPO / "fixtures" / "cascade-jev.jsonl")
    points = []
    for case in cascade.load_codex(codex_path()):
        decision = asyncio.run(recorded.decide(case["point"], case["state"], case["questions"]))
        if decision.input_tokens:
            points.append((len(case["state"]["record"]), decision.input_tokens))
    n = len(points)
    mx, my = sum(x for x, _ in points) / n, sum(y for _, y in points) / n
    b = sum((x - mx) * (y - my) for x, y in points) / sum((x - mx) ** 2 for x, _ in points)
    return my - b * mx, b


def dry(cases: Sequence[Mapping[str, Any]], root: pathlib.Path) -> dict[str, Any]:
    fit = token_fit()
    estimate = Estimate(fit)
    recorded = Answers(ANSWERS)
    rows = asyncio.run(run_all(cases, Gate(recorded, estimate), root))
    calls = estimate.calls
    n_mcp = sum(r["family"] == "mcp" for r in rows)
    decided = {arm: sum(r["arms"][arm]["decided"] for r in rows) for arm in ARMS}
    return {
        "trajectories": len(cases), "calls": len(rows), "mcp_calls": n_mcp,
        "shell_calls": len(rows) - n_mcp, "decisions_by_arm": decided,
        "already_recorded": len(recorded), "to_ask": len(calls),
        "by_point": {p: sum(c["point"] == p for c in calls) for p in {c["point"] for c in calls}},
        "record_chars": _quantiles([c["chars"] for c in calls]),
        "usd_flat_71u": round(len(calls) * FLAT_USD, 4),
        "usd_fit": round(sum(c["fit_usd"] for c in calls), 4),
        "usd_reserved": round(sum(c["reserve_usd"] for c in calls), 4),
        "token_fit": [round(fit[0], 1), round(fit[1], 4)],
        "cap_usd": BATCH_CAP_USD,
        "fits_under_cap": sum(c["reserve_usd"] for c in calls) <= BATCH_CAP_USD,
    }  # fmt: skip


class Gate:
    """Recorded answers first; the rest to `fallback` (the estimator, in a dry run)."""

    def __init__(self, recorded: Answers, fallback: Any) -> None:
        self._recorded, self._fallback, self.name, self.model = recorded, fallback, "jev", MODEL

    async def decide(self, point: str, state: Any, questions: Mapping[str, Any]) -> Decision:
        decision = await self._recorded.decide(point, state, questions)
        if decision.answers:
            return decision
        return await self._fallback.decide(point, state, questions)


def _quantiles(values: Sequence[int]) -> dict[str, int]:
    if not values:
        return {}
    ordered = sorted(values)
    pick = lambda q: ordered[min(len(ordered) - 1, int(q * len(ordered)))]  # noqa: E731
    return {"min": ordered[0], "median": pick(0.5), "p90": pick(0.9), "max": ordered[-1]}


# ---- seal ---------------------------------------------------------------------------------------

SEALED_FIXED = ("benchmarks/a3_mcp/replay.py", "benchmarks/a3_mcp/analysis.py",
                "tests/test_a3_mcp_replay.py", "benchmarks/cascade/run.py",
                "benchmarks/jev114/l4_stats.py", "benchmarks/agentdojo/score.py",
                "fixtures/cascade-jev.jsonl")  # fmt: skip


def manifest(data: pathlib.Path) -> dict[str, str]:
    """`<path> -> sha256` of prereg.md, the code (LF bytes), the package and the data."""

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
    found = manifest(data)
    value = combined(found)
    target = OUT / "prereg.sha256"
    if target.exists() and target.read_text().strip() not in ("", value):
        raise SystemExit("prereg.sha256 already holds another seal: nothing written")
    (OUT / "prereg.manifest.json").write_text(json.dumps(found, indent=1) + "\n",
                                              encoding="utf-8", newline="\n")  # fmt: skip
    target.write_text(value + "\n", encoding="utf-8", newline="\n")
    return value


def require_seal(data: pathlib.Path) -> None:
    target = OUT / "prereg.sha256"
    if not target.exists() or target.read_text().strip() != combined(manifest(data)):
        raise SystemExit("prereg.md, the code or the data differ from the seal: nothing spent")


# ---- live ---------------------------------------------------------------------------------------


def load_key() -> None:
    """TYPESAFE_API_KEY into this process from SANCHOPANZA_KEYS_ENV's file when unset."""
    lot = _module(REPO / "benchmarks" / "jev114" / "l4.py", "a3_l4")
    lot.load_key()


def go_live(data: pathlib.Path) -> Any:
    from sanchopanza.providers import jev
    from sanchopanza.providers.jev import apreflight

    require_seal(data)
    load_key()
    jev.RETRYABLE = frozenset(jev.RETRYABLE - {429})  # stop at the first 429, never retry it
    result = asyncio.run(apreflight(model=MODEL))
    if not result.ok or result.model != MODEL:
        raise SystemExit(f"preflight {MODEL}: {result.reason}, served {result.model}")
    return live_decider()


def complete(rows: Sequence[Mapping[str, Any]]) -> bool:
    """Every call the MCP arm decided has an answer from jev-1.13.0."""
    return all(r["arms"][a]["error"] is None for r in rows for a in ARMS
               if r["arms"][a]["decided"])  # fmt: skip


def write_calls(rows: Sequence[Mapping[str, Any]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    CALLS.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8", newline="\n")


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
    cases = load(data)
    if args.dry:
        report = json.dumps(dry(cases, root), indent=1) + "\n"
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "dry.json").write_text(report, encoding="utf-8", newline="\n")
        print(report, end="")
        return 0
    if args.run:
        live = go_live(data) if args.live else None
        answers = Answers(ANSWERS, live)
        rows = asyncio.run(run_all(cases, answers, root))
        print(json.dumps({"asked": answers.asked, "halted": HALTED[:1]}), file=sys.stderr)
        if HALTED:
            return 3 if HALTED[0].startswith(CAP) else 2
        if not complete(rows):
            print("not every decision has an answer: nothing scored", file=sys.stderr)
            return 2
        write_calls(rows)
    analysis = _module(HERE / "analysis.py", "a3_analysis")
    print(json.dumps(analysis.write(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
