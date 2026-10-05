"""Browse, development: fetch by passages in free FRAMES sessions (the fetch pilot).

python benchmarks/browse/free_fetch_pilot.py --plan         # free: ids and arms in run order
python benchmarks/browse/free_fetch_pilot.py --preflight    # free: version, hook, settings
python benchmarks/browse/free_fetch_pilot.py --check-load   # free: the tool is not deferred
python benchmarks/browse/free_fetch_pilot.py --smoke        # one SONNET-FETCH session: alwaysLoad
python benchmarks/browse/free_fetch_pilot.py --live         # the Sonnet arms, under 15 USD
python benchmarks/browse/free_fetch_pilot.py --live-haiku   # the Haiku arms, if the ceiling allows
python benchmarks/browse/free_fetch_pilot.py                # free: the report so far

Measured the way people use Claude Code, as the FRAMES pilots: the session gets the question and
the ANSWER instruction, Claude Code's normal tools (`free_e2e.one_session`; Bash and the scheduling
tools denied), WebFetch denied to the hosts that serve the set. A -FETCH arm adds the
`sanchopanza-fetch` server (`fetch_passages`, registered with `alwaysLoad` so tool search does not
defer it) and `fetch_hook` on `PreToolUse` WebFetch, both through the session's own MCP config and
`--settings`, never `~/.claude/settings.json`. Same cap in both arms of a model (Sonnet 1.50, Haiku
0.60): the question is whether the tool costs less for the same answers, not under a tighter cap.

Tasks: twenty FRAMES test rows chosen by metadata alone, none of either earlier pilot's: an answer
of at most four words and three or more Wikipedia links (questions that open more pages); seeded.
Only ids reach the repository (`fetch-pilot-ids.txt`); the rows, which keep the agents' answers,
live beside the cached set.

Ceilings: 15 USD for the smoke and the Sonnet arms; the Haiku arms run only when the smoke and
Sonnet left `HAIKU_NEEDS_USD` under 20 USD (the pilots' Haiku spend for 40 sessions and a cap), and
stop at 20. A 429 or "weekly limit" stops the phase at once. Each row keeps, beside the pilots'
fields, the web calls read from its transcripts (`web_calls`): no page text, no answer text in the
repository.
"""

from __future__ import annotations

import argparse
import http.server
import importlib.util
import json
import pathlib
import random
import shutil
import statistics
import sys
import tempfile
import threading
from collections.abc import Mapping, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


frames = _load("browse_free_frames", HERE / "free_frames.py")
free, phase, calib, trace = frames.free, frames.phase, frames.calib, frames.trace

from sanchopanza.harness.fetch_hook import REASON, TOOL_NAME  # noqa: E402

IDS = frames.RESULTS / "fetch-pilot-ids.txt"
REPORT = frames.RESULTS / "fetch-pilot.json"
PRIVATE = free.CACHE / "frames-fetch-pilot"  # the rows keep the agents' answers: not in the repo
SESSIONS = PRIVATE / "sessions.jsonl"
SMOKE = PRIVATE / "smoke-sessions.jsonl"
SEED = 20261008
N_TASKS = 20
MIN_LINKS = 3
MAX_WORDS = 4
CAPS = {"SONNET": 1.50, "SONNET-FETCH": 1.50, "HAIKU": 0.60, "HAIKU-FETCH": 0.60}
SONNET_ARMS = ("SONNET", "SONNET-FETCH")
HAIKU_ARMS = ("HAIKU", "HAIKU-FETCH")
ARMS = SONNET_ARMS + HAIKU_ARMS
SONNET_CEILING_USD = 15.0
CEILING_USD = 20.0
HAIKU_NEEDS_USD = 9.8  # 40 Haiku sessions at the pilots' 0.20-0.23 mean, plus one cap
SERVER = "sanchopanza-fetch"
DENIED_MARK = REASON[:40]  # the hook's deny as it lands in the tool result
FAILED = ("Refused:", "Could not fetch")
NOT_READ = ("not read here", "No text on the page")
PRIOR_IDS = ("frames-ids.txt", "frames2-ids.txt")


# --- tasks --------------------------------------------------------------------------------------


def eligible(row: Mapping[str, str]) -> bool:
    """A short answer and three or more linked articles."""
    words = len(str(row.get("Answer") or "").split())
    return 0 < words <= MAX_WORDS and frames.links_of(row) >= MIN_LINKS


def sample(
    rows: Sequence[Mapping[str, str]], taken: set[str], n: int = N_TASKS, seed: int = SEED
) -> list[str]:
    """n eligible ids not in `taken`, seeded, drawn from the pool in file order."""
    pool = [frames.tid_of(r) for r in rows if eligible(r) and frames.tid_of(r) not in taken]
    return random.Random(seed).sample(pool, n)


def taken_ids() -> set[str]:
    return {t for name in PRIOR_IDS for t in (frames.RESULTS / name).read_text().split()}


def chosen_ids(rows: Sequence[Mapping[str, str]]) -> list[str]:
    if IDS.exists():
        return [x.strip() for x in IDS.read_text(encoding="utf-8").splitlines() if x.strip()]
    ids = sample(rows, taken_ids())
    IDS.write_text("\n".join(ids) + "\n", encoding="utf-8")
    return ids


def plan(items: Sequence[tuple], arms: Sequence[str]) -> list[tuple]:
    streams = [[(t, arm) for t in items] for arm in arms]
    return [(i, task, 1, arm) for i, (task, arm) in enumerate(calib.interleave(streams))]


# --- sessions -----------------------------------------------------------------------------------


def is_fetch(arm: str) -> bool:
    return arm.endswith("-FETCH")


def server_entry() -> dict[str, Any]:
    """The fetch server as `sanchopanza install --fetch` registers it, loaded up front."""
    return {
        "command": str(free.nav.HOOK_PYTHON),
        "args": ["-m", "sanchopanza", "fetch-mcp"],
        "env": {
            "PYTHONPATH": str(free.SRC),
            "SANCHOPANZA_FETCH_DENY_HOSTS": ",".join(frames.DENIED_HOSTS),
        },
        "alwaysLoad": True,
    }


def hooks() -> dict[str, Any]:
    command = f'"{free.nav.HOOK_PYTHON.as_posix()}" -m sanchopanza.harness.fetch_hook'
    hook = {"type": "command", "command": command, "timeout": frames.HOOK_TIMEOUT_S}
    return {"PreToolUse": [{"matcher": "WebFetch", "hooks": [hook]}]}


def arm_options(arm: str, marks: pathlib.Path) -> dict[str, Any]:
    """What `free_e2e.one_session` gets beyond the base: nothing for a base arm."""
    if not is_fetch(arm):
        return {"hooks": None, "env_extra": None, "mcp_servers": None}
    env = {"SANCHOPANZA_FETCH_DIR": str(marks),
           "SANCHOPANZA_FETCH_DENY_HOSTS": ",".join(frames.DENIED_HOSTS)}  # fmt: skip
    return {"hooks": hooks(), "env_extra": env, "mcp_servers": {SERVER: server_entry()}}


def _tool_events(folder: pathlib.Path) -> list[dict[str, Any]]:
    """Every tool use of the session (main agent and subagents), with its result, file order."""
    out: list[dict[str, Any]] = []
    for path in sorted(folder.rglob("*.jsonl")) if folder.is_dir() else []:
        uses: list[tuple[str, dict[str, Any]]] = []
        results: dict[str, tuple[str, bool]] = {}
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            entry = json.loads(line) if line.strip() else {}
            content = (entry.get("message") or {}).get("content")
            for block in content if isinstance(content, list) else []:
                kind = block.get("type") if isinstance(block, dict) else None
                if kind == "tool_use":
                    use = {"name": str(block.get("name") or ""), "input": block.get("input") or {}}
                    uses.append((str(block.get("id")), use))
                elif kind == "tool_result":
                    text = trace._result_text(block.get("content"))
                    results[str(block.get("tool_use_id"))] = (text, bool(block.get("is_error")))
        for use_id, use in uses:
            text, error = results.get(use_id, (None, False))
            out.append({**use, "result": text, "is_error": error})
    return out


def unwrap(text: str) -> str:
    """An MCP tool's text as the agent reads it: Claude Code may keep `{"result": "..."}`."""
    if text.startswith('{"result"'):
        try:
            return str(json.loads(text).get("result") or "")
        except ValueError:
            return text
    return text


def web_calls(folder: pathlib.Path) -> dict[str, Any]:
    """Counts only: searches, WebFetch by outcome, fetch_passages by outcome and the passages'
    tokens (characters / 4), ToolSearch."""
    events = _tool_events(folder)
    fetches = [e for e in events if e["name"] == "WebFetch"]
    denied = [e for e in fetches if DENIED_MARK in str(e["result"] or "")]
    denied_urls = {str(e["input"].get("url") or "") for e in denied}
    ran = [e for e in fetches if e not in denied]
    passages = [e for e in events if e["name"] == TOOL_NAME]
    text = [unwrap(str(e["result"] or "")) for e in passages]
    failed = [t for t in text if t.startswith(FAILED) or any(m in t for m in NOT_READ)]
    read = [t for t in text if t not in failed]
    return {
        "web_search": sum(e["name"] == "WebSearch" for e in events),
        "web_fetch": len(fetches),
        "web_fetch_denied_by_hook": len(denied),
        "web_fetch_ran": len(ran),
        "web_fetch_error": sum(bool(e["is_error"]) for e in ran),
        "web_fetch_back": sum(str(e["input"].get("url") or "") in denied_urls for e in ran),
        "fetch_passages": len(passages),
        "fetch_passages_unread": len(failed),
        "passage_tokens": sum(len(t) // 4 for t in read),
        "tool_search": sum(e["name"] == "ToolSearch" for e in events),
        "subagents": sum(e["name"] in ("Task", "Agent") for e in events),
    }


def reader_usd(folder: pathlib.Path, by_model: Mapping[str, float]) -> float:
    """What the session paid that its own transcripts do not show: the readers inside WebSearch
    and WebFetch (modelUsage less the transcript's calls priced at list rates)."""
    seen: dict[str, float] = {}
    for call in trace.load_calls(folder):
        family = trace.family(call["model"])
        seen[family] = seen.get(family, 0.0) + trace.call_usd(call["model"], call["usage"])
    reported: dict[str, float] = {}
    for model, usd in by_model.items():
        reported[trace.family(model)] = reported.get(trace.family(model), 0.0) + float(usd)
    return round(sum(max(0.0, usd - seen.get(f, 0.0)) for f, usd in reported.items()), 5)


def haiku_usd(by_model: Mapping[str, float]) -> float:
    return round(sum(float(u) for m, u in by_model.items() if trace.family(m) == "haiku"), 5)


def session_for(log_to: pathlib.Path):
    def session(task: tuple, run: int, arm: str) -> dict[str, Any]:
        marks = pathlib.Path(tempfile.mkdtemp(prefix=f"sp-fetchp-{task[0].lower()}-"))
        row = free.one_session(task, run, arm, session_max_usd=CAPS[arm], deny=frames.DENY,
                               **arm_options(arm, marks))  # fmt: skip
        found = frames.inspect(row, task[3], CAPS[arm], marks)
        folder = trace.folder_of(row["workdir"])
        by_model = row.get("usd_by_model") or {}
        out = {**row, **found, "success_reply": row["success"], "success": found["ok_auto"],
               "calls": web_calls(folder), "reader_usd": reader_usd(folder, by_model),
               "haiku_usd": haiku_usd(by_model)}  # fmt: skip
        if found["limit"] or phase.usage_limited(row):
            phase._log(log_to, f"STOP-LIMIT {task[0]} {arm}: 429 or weekly limit in the session")
            out = {**out, "answer": free.LIMIT_MARKER}
        return out

    return session


# --- checks -------------------------------------------------------------------------------------


def global_settings_clean() -> bool:
    path = pathlib.Path.home() / ".claude" / "settings.json"
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    return frames.global_settings_clean() and "fetch-hook" not in text and "fetch_hook" not in text


def preflight() -> list[str]:
    problems = [p for p in frames.preflight() if "sources hook" not in p]
    if not global_settings_clean():
        problems.append("a sanchopanza hook is in ~/.claude/settings.json: take it out first")
    if not shutil.which("claude"):
        problems.append("no claude on PATH")
    return problems


def capture_server(sink: list[dict[str, Any]]) -> http.server.HTTPServer:
    """A local endpoint that keeps each request's tools (name, defer_loading) and answers 400."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or "{}")
            tools = [
                {"name": t.get("name"), "defer_loading": t.get("defer_loading"),
                 "has_schema": "input_schema" in t}
                for t in body.get("tools", [])
            ]  # fmt: skip
            sink.append({"model": body.get("model"), "tools": tools})
            error = {"type": "invalid_request_error", "message": "capture"}
            answer = json.dumps({"type": "error", "error": error}).encode()
            self.send_response(400)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(answer)))
            self.end_headers()
            self.wfile.write(answer)

        def log_message(self, *_args: Any) -> None:
            return

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def check_load() -> dict[str, Any]:
    """Free: a -FETCH session's first request, sent to a local endpoint that answers 400 (a dummy
    key, tool search on as with the real API): is fetch_passages offered with its schema, not
    deferred behind ToolSearch?"""
    sink: list[dict[str, Any]] = []
    server = capture_server(sink)
    marks = pathlib.Path(tempfile.mkdtemp(prefix="sp-fetchp-check-"))
    options = arm_options("SONNET-FETCH", marks)
    env = {**options["env_extra"], "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{server.server_port}",
           "ANTHROPIC_API_KEY": "dummy", "ENABLE_TOOL_SEARCH": "true"}  # fmt: skip
    try:
        free.one_session(("CHECK", "", "Say hi.", ""), 1, "SONNET-FETCH", session_max_usd=0.01,
                         deny=frames.DENY, **{**options, "env_extra": env})  # fmt: skip
    finally:
        server.shutdown()
    first = next((r for r in sink if any(t["name"] == "ToolSearch" for t in r["tools"])), None)
    if first is None:
        return {"requests": len(sink), "always_loaded": False}
    tools = {t["name"]: t for t in first["tools"]}
    mine = tools.get(TOOL_NAME) or {}
    loaded = bool(mine.get("has_schema")) and not mine.get("defer_loading")
    return {"requests": len(sink), "fetch_tool": mine, "offered": sorted(tools),
            "always_loaded": loaded}  # fmt: skip


def smoke_check(row: Mapping[str, Any]) -> dict[str, Any]:
    """alwaysLoad works when the agent called the tool with no ToolSearch before it."""
    calls = row.get("calls") or {}
    used = calls.get("fetch_passages", 0)
    searched = calls.get("tool_search", 0)
    return {"fetch_passages": used, "tool_search": searched,
            "always_loaded": used > 0 and not searched}  # fmt: skip


# --- report -------------------------------------------------------------------------------------


def _mean(values: Sequence[float]) -> float | None:
    return round(statistics.mean(values), 4) if values else None


def cell(rows: Sequence[Mapping[str, Any]], right: str = "ok_auto") -> dict[str, Any]:
    costs = [float(r["list_usd"]) for r in rows]
    calls = [r.get("calls") or {} for r in rows]
    total = {k: sum(c.get(k, 0) for c in calls) for k in calls[0]} if calls else {}
    return {
        "sessions": len(rows),
        "right": sum(bool(r.get(right)) for r in rows),
        "mean_usd": _mean(costs),
        "median_usd": round(statistics.median(costs), 4) if costs else None,
        "total_usd": round(sum(costs), 3),
        "mean_reader_usd": _mean([float(r.get("reader_usd") or 0) for r in rows]),
        "mean_haiku_usd": _mean([float(r.get("haiku_usd") or 0) for r in rows]),
        "hit_cap": sum(bool(r.get("hit_cap")) for r in rows),
        "leak": sum(bool(r.get("leak")) for r in rows),
        "calls": total,
        "passage_tokens_per_read": round(
            total.get("passage_tokens", 0)
            / max(1, total.get("fetch_passages", 0) - total.get("fetch_passages_unread", 0))
        ) if total else None,
    }  # fmt: skip


def report(rows: Sequence[Mapping[str, Any]], right: str = "ok_auto") -> dict[str, Any]:
    spend = round(sum(r["list_usd"] for r in rows), 2)
    out: dict[str, Any] = {"sessions": len(rows), "list_usd": spend, "grades": right, "by_arm": {}}
    for arm in ARMS:
        mine = [r for r in rows if r["arm"] == arm]
        if mine:
            out["by_arm"][arm] = cell(mine, right)
    return out


def spent(path: pathlib.Path) -> float:
    return sum(float(r["list_usd"]) for r in free.nav.done_sessions(path))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group()
    for flag in ("--plan", "--preflight", "--check-load", "--smoke", "--live", "--live-haiku"):
        mode.add_argument(flag, action="store_true")
    ap.add_argument("--task", help="--smoke: this FRAMES id instead of the pilot's first task")
    args = ap.parse_args()
    PRIVATE.mkdir(parents=True, exist_ok=True)
    rows_all = frames.read_frames()
    items = frames.tasks(rows_all, chosen_ids(rows_all))
    if args.plan:
        for i, task, _run, arm in plan(items, ARMS):
            print(i, task[0], arm, CAPS[arm])
        return 0
    if args.check_load:
        found = check_load()
        print(json.dumps(found, indent=1))
        return 0 if found["always_loaded"] else 1
    if args.preflight or args.smoke or args.live or args.live_haiku:
        problems = preflight()
        if problems:
            print("preflight: " + "; ".join(problems), file=sys.stderr)
            return 3
        if args.preflight:
            print("preflight: ok", file=sys.stderr)
            return 0
    code = 0
    if args.smoke:
        limits = phase.Limits(session_max_usd=CAPS["SONNET-FETCH"], ceiling_usd=3.0)
        task = frames.tasks(rows_all, [args.task])[0] if args.task else items[0]
        step = [(0, task, 1, "SONNET-FETCH")]
        code, rows = phase.run_phase(step, free.nav.done_sessions(SMOKE), limits,
                                     session_for(SMOKE), SMOKE)  # fmt: skip
        print(json.dumps([smoke_check(r) for r in rows], indent=1))
        return code
    rows = free.nav.done_sessions(SESSIONS)
    if args.live:
        limits = phase.Limits(session_max_usd=max(CAPS.values()),
                              ceiling_usd=SONNET_CEILING_USD - spent(SMOKE))  # fmt: skip
        code, rows = phase.run_phase(plan(items, SONNET_ARMS), rows, limits,
                                     session_for(SESSIONS), SESSIONS)  # fmt: skip
    elif args.live_haiku:
        left = CEILING_USD - spent(SMOKE) - spent(SESSIONS)
        done_haiku = sum(float(r["list_usd"]) for r in rows if r["arm"] in HAIKU_ARMS)
        if left + done_haiku < HAIKU_NEEDS_USD:
            phase._log(SESSIONS, f"HAIKU-SKIPPED {left:.2f} USD left under {CEILING_USD}")
            return 0
        limits = phase.Limits(session_max_usd=CAPS["HAIKU"],
                              ceiling_usd=CEILING_USD - spent(SMOKE))  # fmt: skip
        code, rows = phase.run_phase(plan(items, HAIKU_ARMS), rows, limits,
                                     session_for(SESSIONS), SESSIONS)  # fmt: skip
    counted = phase.counted(rows)
    if counted:
        result = report(counted)
        REPORT.write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(json.dumps(result, indent=1))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
