"""Browse, development: fetch v2 in free FRAMES sessions, Haiku only (the fetch v2 pilot).

python benchmarks/browse/free_fetch2_pilot.py --replay-budget  # free: N from the fetch pilot
python benchmarks/browse/free_fetch2_pilot.py --plan           # free: ids and arms in run order
python benchmarks/browse/free_fetch2_pilot.py --preflight      # free: version, settings
python benchmarks/browse/free_fetch2_pilot.py --check-load     # free: the tool is not deferred
python benchmarks/browse/free_fetch2_pilot.py --check-note     # free: the note reaches the model
python benchmarks/browse/free_fetch2_pilot.py --live           # the two Haiku arms, under 10 USD
python benchmarks/browse/free_fetch2_pilot.py                  # free: the report so far

The fetch pilot's runner (`free_fetch_pilot.py`) with two arms: HAIKU, Claude Code alone, and
HAIKU-FETCH2, which adds the `sanchopanza-fetch` server at version 2 (`SANCHOPANZA_FETCH_VERSION=2`:
passages by sections, chrome stripped, a short line on a 404 or a disambiguation page) and
`fetch_hook` with the page budget (`SANCHOPANZA_FETCH_MAX_PAGES`): the WebFetch deny as before,
the count reset on WebSearch, and a short line after each page past `MAX_PAGES` pages in a row
with no search. Server and hooks go through the session's own MCP config and `--settings`, never
`~/.claude/settings.json`; the server is registered with `alwaysLoad`.

`MAX_PAGES` was chosen with `--replay-budget`, free: the hook's own `handle` run over the web
calls of the fetch pilot's recorded sessions, for each N, counting the sessions it would have
noted, right and wrong (`fetch2-budget-replay.json`).

Tasks: twenty FRAMES test rows chosen by metadata alone as in the fetch pilot (an answer of at
most four words, three or more Wikipedia links), none of any earlier pilot's, with a new seed.
Only ids reach the repository (`fetch2-pilot-ids.txt`). Cap 0.60 USD a session in both arms; a
hard ceiling of 10 USD in code; a 429 or "weekly limit" stops the run (`phase.run_phase`), and a
resume runs only what is missing.
"""

from __future__ import annotations

import http.server
import importlib.util
import json
import pathlib
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


pilot = _load("browse_free_fetch_pilot", HERE / "free_fetch_pilot.py")
frames, free, phase, calib, trace = pilot.frames, pilot.free, pilot.phase, pilot.calib, pilot.trace

from sanchopanza.harness import fetch_hook  # noqa: E402
from sanchopanza.harness.fetch_hook import TOOL_NAME, page_note  # noqa: E402
from sanchopanza.harness.fetch_tool import DISAMBIGUATION, GUESSED  # noqa: E402

IDS = frames.RESULTS / "fetch2-pilot-ids.txt"
REPORT = frames.RESULTS / "fetch2-pilot.json"
REPLAY = frames.RESULTS / "fetch2-budget-replay.json"
PRIVATE = free.CACHE / "frames-fetch2-pilot"  # the rows keep the agents' answers: not in the repo
SESSIONS = PRIVATE / "sessions.jsonl"
SEED = 20261010
ARMS = ("HAIKU", "HAIKU-FETCH2")
CAPS = {"HAIKU": 0.60, "HAIKU-FETCH2": 0.60}
CEILING_USD = 10.0
MAX_PAGES = 8  # from --replay-budget: the smallest N that notes no right session but the loop
REPLAY_NS = tuple(range(2, 13))
PRIOR_IDS = ("frames-ids.txt", "frames2-ids.txt", "fetch-pilot-ids.txt")
NOTE_MARK = page_note(0).split(" ", 1)[1][:30]  # the note's words after its number


# --- tasks --------------------------------------------------------------------------------------


def taken_ids() -> set[str]:
    return {t for name in PRIOR_IDS for t in (frames.RESULTS / name).read_text().split()}


def chosen_ids(rows: Sequence[Mapping[str, str]]) -> list[str]:
    if IDS.exists():
        return [x.strip() for x in IDS.read_text(encoding="utf-8").splitlines() if x.strip()]
    ids = pilot.sample(rows, taken_ids(), seed=SEED)
    IDS.write_text("\n".join(ids) + "\n", encoding="utf-8")
    return ids


def plan(items: Sequence[tuple]) -> list[tuple]:
    return pilot.plan(items, ARMS)


# --- sessions -----------------------------------------------------------------------------------


def is_fetch(arm: str) -> bool:
    return arm.endswith("-FETCH2")


def fetch_env(marks: pathlib.Path, max_pages: int = MAX_PAGES) -> dict[str, str]:
    return {
        "SANCHOPANZA_FETCH_DIR": str(marks),
        "SANCHOPANZA_FETCH_DENY_HOSTS": ",".join(frames.DENIED_HOSTS),
        "SANCHOPANZA_FETCH_VERSION": "2",
        "SANCHOPANZA_FETCH_MAX_PAGES": str(max_pages),
    }


def server_entry() -> dict[str, Any]:
    entry = pilot.server_entry()
    return {**entry, "env": {**entry["env"], "SANCHOPANZA_FETCH_VERSION": "2"}}


def hooks() -> dict[str, Any]:
    """The WebFetch deny and the count reset before a tool runs; the count after a page."""
    command = f'"{free.nav.HOOK_PYTHON.as_posix()}" -m sanchopanza.harness.fetch_hook'
    hook = {"type": "command", "command": command, "timeout": frames.HOOK_TIMEOUT_S}
    return {
        "PreToolUse": [{"matcher": "WebFetch|WebSearch", "hooks": [hook]}],
        "PostToolUse": [{"matcher": f"{TOOL_NAME}|WebFetch", "hooks": [hook]}],
    }


def arm_options(arm: str, marks: pathlib.Path, max_pages: int = MAX_PAGES) -> dict[str, Any]:
    if not is_fetch(arm):
        return {"hooks": None, "env_extra": None, "mcp_servers": None}
    return {"hooks": hooks(), "env_extra": fetch_env(marks, max_pages),
            "mcp_servers": {pilot.SERVER: server_entry()}}  # fmt: skip


def page_runs(events: Sequence[Mapping[str, Any]], max_pages: int = MAX_PAGES) -> dict[str, int]:
    """The hook's own count replayed on a session's web calls: the longest run of pages with no
    search, and how many pages came past `max_pages` (each got the note)."""
    longest = run = noted = 0
    for e in events:
        if e["name"] == "WebSearch":
            run = 0
        elif e["name"] == TOOL_NAME or (e["name"] == "WebFetch" and not _denied(e)):
            run += 1
            longest = max(longest, run)
            noted += run > max_pages
    return {"longest_page_run": longest, "page_notes": noted}


def _denied(event: Mapping[str, Any]) -> bool:
    return pilot.DENIED_MARK in str(event.get("result") or "")


def v2_calls(folder: pathlib.Path) -> dict[str, Any]:
    """The fetch pilot's counts plus what version 2 adds: guessed-404 and disambiguation lines,
    the longest page run and the page-budget notes."""
    events = pilot._tool_events(folder)
    texts = [pilot.unwrap(str(e["result"] or "")) for e in events if e["name"] == TOOL_NAME]
    return {**pilot.web_calls(folder), **page_runs(events),
            "guessed_404": sum(GUESSED in t for t in texts),
            "disambiguation": sum(DISAMBIGUATION[:30] in t for t in texts)}  # fmt: skip


def session_for(log_to: pathlib.Path):
    def session(task: tuple, run: int, arm: str) -> dict[str, Any]:
        marks = pathlib.Path(tempfile.mkdtemp(prefix=f"sp-fetch2-{task[0].lower()}-"))
        row = free.one_session(task, run, arm, session_max_usd=CAPS[arm], deny=frames.DENY,
                               **arm_options(arm, marks))  # fmt: skip
        found = frames.inspect(row, task[3], CAPS[arm], marks)
        folder = trace.folder_of(row["workdir"])
        by_model = row.get("usd_by_model") or {}
        out = {**row, **found, "success_reply": row["success"], "success": found["ok_auto"],
               "calls": v2_calls(folder), "reader_usd": pilot.reader_usd(folder, by_model),
               "haiku_usd": pilot.haiku_usd(by_model),
               "budget_marks": len(list(marks.glob("pages-*.json")))}  # fmt: skip
        if found["limit"] or phase.usage_limited(row):
            phase._log(log_to, f"STOP-LIMIT {task[0]} {arm}: 429 or weekly limit in the session")
            out = {**out, "answer": free.LIMIT_MARKER}
        return out

    return session


# --- the page budget, replayed for free ---------------------------------------------------------


def hook_events(events: Sequence[Mapping[str, Any]], session: str) -> list[dict[str, Any]]:
    """A session's web calls as the hook would have seen them."""
    out = []
    for e in events:
        if e["name"] == "WebSearch":
            out.append({"hook_event_name": "PreToolUse", "tool_name": "WebSearch"})
        elif e["name"] == TOOL_NAME or (e["name"] == "WebFetch" and not _denied(e)):
            out.append({"hook_event_name": "PostToolUse", "tool_name": e["name"]})
    return [{**x, "session_id": session, "tool_input": {}} for x in out]


def replay_budget(rows: Sequence[Mapping[str, Any]], ns: Sequence[int] = REPLAY_NS) -> dict:
    """For each N, the sessions `fetch_hook.handle` would have noted, and how many pages."""
    hand = _load("browse_free_fetch_pilot_hand", HERE / "free_fetch_pilot_hand.py")
    sessions = []
    for r in rows:
        if not r["arm"].endswith("-FETCH"):
            continue
        events = pilot._tool_events(trace.folder_of(r["workdir"]))
        sessions.append((r, hand.graded(r)["ok_hand"], hook_events(events, r["task"])))
    out: dict[str, Any] = {"sessions": len(sessions), "by_n": {}}
    for n in ns:
        noted = []
        with tempfile.TemporaryDirectory() as folder:
            env = {"SANCHOPANZA_FETCH_DIR": folder, "SANCHOPANZA_FETCH_MAX_PAGES": str(n)}
            for row, right, events in sessions:
                notes = [fetch_hook.handle({**e, "session_id": f"{row['arm']}-{row['task']}"}, env)
                         for e in events]  # fmt: skip
                count = sum(x is not None for x in notes)
                if count:
                    noted.append({"task": row["task"], "arm": row["arm"], "right": right,
                                  "pages_noted": count})  # fmt: skip
        out["by_n"][str(n)] = {
            "sessions_noted": len(noted),
            "right_noted": sum(x["right"] for x in noted),
            "wrong_noted": sum(not x["right"] for x in noted),
            "pages_noted": sum(x["pages_noted"] for x in noted),
            "noted": noted,
        }
    return out


# --- free checks --------------------------------------------------------------------------------


def check_load() -> dict[str, Any]:
    """Free: the -FETCH2 session's first request offers fetch_passages up front (as the pilot's
    `--check-load`, on this arm's options)."""
    sink: list[dict[str, Any]] = []
    server = pilot.capture_server(sink)
    marks = pathlib.Path(tempfile.mkdtemp(prefix="sp-fetch2-check-"))
    options = arm_options("HAIKU-FETCH2", marks)
    env = {**options["env_extra"], "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{server.server_port}",
           "ANTHROPIC_API_KEY": "dummy", "ENABLE_TOOL_SEARCH": "true"}  # fmt: skip
    try:
        free.one_session(("CHECK", "", "Say hi.", ""), 1, "HAIKU-FETCH2", session_max_usd=0.01,
                         deny=frames.DENY, **{**options, "env_extra": env})  # fmt: skip
    finally:
        server.shutdown()
    first = next((r for r in sink if any(t["name"] == "ToolSearch" for t in r["tools"])), None)
    if first is None:
        return {"requests": len(sink), "always_loaded": False}
    mine = {t["name"]: t for t in first["tools"]}.get(TOOL_NAME) or {}
    loaded = bool(mine.get("has_schema")) and not mine.get("defer_loading")
    return {"requests": len(sink), "fetch_tool": mine, "always_loaded": loaded}


def _sse(events: Sequence[Mapping[str, Any]]) -> bytes:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


def scripted_reply(body: Mapping[str, Any], url: str) -> list[dict[str, Any]]:
    """A streamed Messages reply: a call to fetch_passages while the request offers the tool and
    holds no tool result yet, else a short text answer."""
    tools = {t.get("name") for t in body.get("tools") or []}
    blocks = [b for m in body.get("messages") or [] if isinstance(m.get("content"), list)
              for b in m["content"] if isinstance(b, dict)]  # fmt: skip
    answered = any(b.get("type") == "tool_result" for b in blocks)
    usage = {"input_tokens": 10, "output_tokens": 1}
    start = {"type": "message_start", "message": {"id": "msg_check", "type": "message",
             "role": "assistant", "model": body.get("model"), "content": [], "stop_reason": None,
             "stop_sequence": None, "usage": usage}}  # fmt: skip
    if TOOL_NAME in tools and not answered:
        call = json.dumps({"url": url, "purpose": "what the page is for"})
        block = {"type": "tool_use", "id": "toolu_check", "name": TOOL_NAME, "input": {}}
        delta = {"type": "input_json_delta", "partial_json": call}
        stop = "tool_use"
    else:
        block = {"type": "text", "text": ""}
        delta = {"type": "text_delta", "text": "ANSWER: done"}
        stop = "end_turn"
    return [start, {"type": "content_block_start", "index": 0, "content_block": block},
            {"type": "content_block_delta", "index": 0, "delta": delta},
            {"type": "content_block_stop", "index": 0},
            {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None},
             "usage": {"output_tokens": 5}},
            {"type": "message_stop"}]  # fmt: skip


def script_server(sink: list[dict[str, Any]], url: str) -> http.server.HTTPServer:
    """A local Messages endpoint that plays `scripted_reply` and keeps every request body."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or "{}")
            sink.append({"path": self.path, "body": body})
            if "count_tokens" in self.path:
                answer, ctype = json.dumps({"input_tokens": 10}).encode(), "application/json"
            else:
                answer, ctype = _sse(scripted_reply(body, url)), "text/event-stream"
            self.send_response(200)
            self.send_header("content-type", ctype)
            self.send_header("content-length", str(len(answer)))
            self.end_headers()
            self.wfile.write(answer)

        def log_message(self, *_args: Any) -> None:
            return

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def check_note(url: str = "https://example.com/") -> dict[str, Any]:
    """Free: a -FETCH2 session against a scripted local endpoint, with the budget at 0 so the
    first page is past it. Does the request after the tool's result carry the passages and the
    hook's note? One real download of `url`, no model."""
    sink: list[dict[str, Any]] = []
    server = script_server(sink, url)
    marks = pathlib.Path(tempfile.mkdtemp(prefix="sp-fetch2-note-"))
    options = arm_options("HAIKU-FETCH2", marks, max_pages=0)
    env = {**options["env_extra"], "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{server.server_port}",
           "ANTHROPIC_API_KEY": "dummy", "ENABLE_TOOL_SEARCH": "true"}  # fmt: skip
    try:
        row = free.one_session(("CHECK", "", "Read the page.", ""), 1, "HAIKU-FETCH2",
                               session_max_usd=0.05, deny=frames.DENY,
                               **{**options, "env_extra": env})  # fmt: skip
    finally:
        server.shutdown()
    after = [json.dumps(r["body"]) for r in sink if '"tool_result"' in json.dumps(r["body"])]
    return {
        "requests": len(sink),
        "after_tool": len(after),
        "passages_back": any("Example Domain" in a for a in after),
        "note_back": any(NOTE_MARK in a for a in after),
        "budget_marks": len(list(marks.glob("pages-*.json"))),
        "subtype": row.get("subtype"),
    }


# --- report -------------------------------------------------------------------------------------


def report(rows: Sequence[Mapping[str, Any]], right: str = "ok_auto") -> dict[str, Any]:
    out: dict[str, Any] = {
        "sessions": len(rows),
        "list_usd": round(sum(r["list_usd"] for r in rows), 2),
        "grades": right,
        "max_pages": MAX_PAGES,
        "by_arm": {},
    }
    for arm in ARMS:
        mine = [r for r in rows if r["arm"] == arm]
        if mine:
            out["by_arm"][arm] = pilot.cell(mine, right)
    return out


def spent(path: pathlib.Path) -> float:
    return sum(float(r["list_usd"]) for r in free.nav.done_sessions(path))


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group()
    for flag in ("--replay-budget", "--plan", "--preflight", "--check-load", "--check-note",
                 "--live"):  # fmt: skip
        mode.add_argument(flag, action="store_true")
    args = ap.parse_args()
    PRIVATE.mkdir(parents=True, exist_ok=True)
    if args.replay_budget:
        found = replay_budget(free.nav.done_sessions(pilot.SESSIONS))
        REPLAY.write_text(json.dumps(found, indent=1), encoding="utf-8")
        print(json.dumps({n: {k: v for k, v in x.items() if k != "noted"}
                          for n, x in found["by_n"].items()}, indent=1))  # fmt: skip
        return 0
    rows_all = frames.read_frames()
    items = frames.tasks(rows_all, chosen_ids(rows_all))
    if args.plan:
        for i, task, _run, arm in plan(items):
            print(i, task[0], arm, CAPS[arm])
        return 0
    if args.check_load or args.check_note:
        found = check_load() if args.check_load else check_note()
        print(json.dumps(found, indent=1))
        ok = found["always_loaded"] if args.check_load else found["note_back"]
        return 0 if ok else 1
    if args.preflight or args.live:
        problems = pilot.preflight()
        if problems:
            print("preflight: " + "; ".join(problems), file=sys.stderr)
            return 3
        if args.preflight:
            print("preflight: ok", file=sys.stderr)
            return 0
    code = 0
    rows = free.nav.done_sessions(SESSIONS)
    if args.live:
        limits = phase.Limits(session_max_usd=max(CAPS.values()), ceiling_usd=CEILING_USD)
        code, rows = phase.run_phase(plan(items), rows, limits, session_for(SESSIONS), SESSIONS)
    counted = phase.counted(rows)
    if counted:
        result = report(counted)
        REPORT.write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(json.dumps(result, indent=1))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
