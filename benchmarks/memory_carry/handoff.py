"""F2 runner: memory against the handoff ritual (docs/results/2026-10-16-memory-f2/prereg.md).

A triple is one scene (`scenes_handoff.py`) at one repetition, run in three arms, one after the
other, each in its own fresh repository and clean Claude Code user (`carry.clean_config`, the
pair's own CLAUDE_CONFIG_DIR, the subscription's OAuth token only):

- `N0`: session 1 (the scene's `first`), then session 2, a new session, with the `continue` line;
- `H`: session 1; then the same session resumed once (`claude -p --resume <session id>`) with
  HANDOFF_REQUEST, its stream kept as `handoff.jsonl` and its result text as `handoff.txt`; then
  session 2, a new session, whose prompt is exactly that text;
- `S`: sanchopanza as `sanchopanza install` leaves it in a project today (`carry_s.install`,
  the memory cell's S: memory on by default, project scope, Jev with the key in the hooks only,
  7 decoy rules in its store), session 2 with the same `continue` line as N0.

Every session and the handoff turn: the same model, `--max-budget-usd` CALL_CAPS[model],
`--settings "{}"`, `--allowedTools` carry.TOOLS, `stream-json`. After session 1 (and H's handoff)
the work is committed. After session 2: the repository's tests and the scene's checks `task`,
`fact`, `decision`, `intact`.

NOT RUN (a row with `cut`, never retried): a session that timed out, ended without a result, or
ran another model or Claude Code; H's handoff with no session id to resume, a non-zero exit, no
result text, no reported cost, a resumed context smaller than session 1's (`context_carried`),
or text too long for a command line; S that did not run as S (`carry_s`, which also stops the
run). A usage limit leaves the arm without a row, writes LIMIT.flag and stops the run: it is a
pause, never a result. An arm cut by a crash or a reboot (a folder without a row) is counted
(its spend from its streams) and runs again whole, at most INTERRUPTS times.

Before each arm: a STOP file stops the run; the run's cap (spent plus the arm's calls at their
cap plus one worst turn, plus S's Jev reserve) stops it; the midnight rule waits (an arm, and a
triple from its first arm, never starts within its expected time of midnight).

    python benchmarks/memory_carry/handoff.py --run f2-pilot --out DIR [--dry] [--cap USD]
    python benchmarks/memory_carry/handoff.py --preflight [--out DIR]
    python benchmarks/memory_carry/handoff.py --seal          # writes the seal; never run live
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "src"))

import carry  # noqa: E402
import carry_s  # noqa: E402
from scenes_handoff import CHECKS, HANDOFF, HANDOFF_PILOT, check_code, names_c_d  # noqa: E402

ARMS = ("N0", "H", "S")
HANDOFF_REQUEST = "Give me a prompt to continue this work in a clean session."
CALL_CAPS = {"sonnet": 0.80, "opus": 1.50}
WORST_TURN = {"sonnet": 0.40, "opus": 0.75}  # one turn past --max-budget-usd (it cuts between)
NIGHT_CAP = 230.0  # USD at list price over every run of the night (handoff_night.py)
RUNS: dict[str, dict[str, Any]] = {
    "f2-pilot": {"model": "sonnet", "scenes": HANDOFF_PILOT, "repeats": [0], "cap": 11.5},
    "f2-sonnet": {"model": "sonnet", "scenes": list(HANDOFF), "repeats": [1, 2, 3, 4],
                  "cap": 109.0},
    "f2-opus": {"model": "opus", "scenes": list(HANDOFF), "repeats": [1, 2], "cap": 106.0},
}  # fmt: skip
SESSION_TIMEOUT = 900
HANDOFF_TIMEOUT = 600
MAX_PROMPT = 30_000  # characters: a handoff longer than this is not passed on a command line
INTERRUPTS = 2  # an arm cut by a crash or reboot runs again whole at most this many times
EXPECTED_ARM_S = {"sonnet": 300, "opus": 420}  # one arm, for the midnight rule
WALL_FACTOR = 1.5
MIDNIGHT_MARGIN_S = 120
OUT = Path(r"C:\sp-runs\memory-f2")
RESULTS = REPO / "docs" / "results" / "2026-10-16-memory-f2"
BROKEN_AFTER = 3  # arms in a row with a session that ended without a result stop the run
EXIT = {"": 0, "cap": 2, "limit": 3, "harness": 4, "manual": 6, "broken": 7}


# ---- plan ----------------------------------------------------------------------------------------


def build_plan(run: str) -> list[tuple[str, str, str, int]]:
    """(scene, model, arm, repetition) for every arm of every triple, the arms of a triple one
    after the other, their order rotated from triple to triple (and from repetition to
    repetition) so each arm runs first, second and third about equally often."""
    spec = RUNS[run]
    out = []
    for rep in spec["repeats"]:
        for i, name in enumerate(spec["scenes"]):
            k = (i + rep) % len(ARMS)
            out += [(name, spec["model"], arm, rep) for arm in (*ARMS[k:], *ARMS[:k])]
    return out


def calls_of(arm: str) -> int:
    return 3 if arm == "H" else 2


def reserve_of(model: str, arm: str) -> float:
    """What the next arm may spend at most: its calls at their cap, one worst turn past it, and
    S's Jev reserve per session."""
    jev = 2 * carry_s.JEV_RESERVE if arm == "S" else 0.0
    return calls_of(arm) * CALL_CAPS[model] + WORST_TURN[model] + jev


# ---- a claude call -------------------------------------------------------------------------------


def command(prompt: str, model: str, resume: str | None = None) -> list[str]:
    """The memory cell's command shape; a prompt that begins with "-" (a handoff can start with a
    list item) goes last, after "--", so it is never read as an option."""
    if prompt.startswith("-"):
        return [*command("x", model, resume)[:2], *command("x", model, resume)[3:], "--", prompt]
    head = ["claude", "-p", prompt, *(["--resume", resume] if resume else [])]
    return [*head, "--model", carry.MODELS[model], "--output-format", "stream-json", "--verbose",
            "--max-budget-usd", f"{CALL_CAPS[model]:.2f}", "--settings", "{}",
            "--allowedTools", *carry.TOOLS]  # fmt: skip


def stream_extra(path: Path) -> dict[str, Any]:
    """What carry.read_stream leaves out: the full result text, whether the result reported a
    cost, its usage, the prompt size of the first and last requests, and subagent calls."""
    text, reported, usage, prompts, agents = "", False, {}, [], 0
    raw = path.read_text(encoding="utf-8") if path.exists() else ""
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "result":
            text = str(event.get("result") or "")
            reported = isinstance(event.get("total_cost_usd"), (int, float))
            usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
        message = event.get("message")
        if event.get("type") == "assistant" and isinstance(message, dict):
            used = message.get("usage") or {}
            prompts.append(
                sum(
                    int(used.get(k) or 0)
                    for k in (
                        "input_tokens",
                        "cache_read_input_tokens",
                        "cache_creation_input_tokens",
                    )
                )
            )
            content = message.get("content") or []
            agents += sum(1 for b in content if isinstance(b, dict) and b.get("type") ==
                          "tool_use" and b.get("name") in ("Task", "Agent"))  # fmt: skip
    return {"text": text, "cost_reported": reported, "tokens": tokens_of(usage),
            "first_prompt": prompts[0] if prompts else None,
            "last_prompt": prompts[-1] if prompts else None, "subagents": agents}  # fmt: skip


def tokens_of(usage: dict[str, Any]) -> dict[str, int]:
    return {"input": int(usage.get("input_tokens") or 0),
            "output": int(usage.get("output_tokens") or 0),
            "cache_read": int(usage.get("cache_read_input_tokens") or 0),
            "cache_write": int(usage.get("cache_creation_input_tokens") or 0)}  # fmt: skip


def call(run: Path, cwd: Path, cmd: list[str], tag: str, config: Path | None,
         timeout: int) -> dict[str, Any]:  # fmt: skip
    """One `claude -p` process, its stream in `<tag>.jsonl`."""
    started = time.time()
    env = carry.environment(config)
    stream = run / f"{tag}.jsonl"
    try:
        with stream.open("w", encoding="utf-8") as out:
            done = subprocess.run(cmd, cwd=cwd, env=env, stdout=out, stderr=subprocess.PIPE,
                                  text=True, timeout=timeout, check=False)  # fmt: skip
        code, err, late = done.returncode, (done.stderr or "")[-300:], False
    except subprocess.TimeoutExpired:
        code, err, late = None, "", True
    seen = {**carry.read_stream(stream), **stream_extra(stream)}
    return {"returncode": code, "stderr": err, "timeout": late, "tag": tag,
            "started": started, "seconds": round(time.time() - started, 1), **seen}  # fmt: skip


def pinned(result: dict[str, Any], model: str) -> bool:
    init = result.get("init") or {}
    return init.get("version") == carry.PIN and init.get("model") == carry.MODELS[model]


def session_cut(result: dict[str, Any], model: str) -> str:
    """Why a session is NOT RUN ("" when it ran)."""
    if result.get("timeout"):
        return "timeout"
    if not carry.session_ran(result):
        return f"{result['tag']} ended without a result (exit {result.get('returncode')})"
    if not pinned(result, model):
        init = result.get("init") or {}
        return f"{result['tag']} ran {init.get('model')} on {init.get('version')}"
    return ""


def handoff_cut(first: dict[str, Any], turn: dict[str, Any]) -> str:
    """Why H's handoff turn is NOT RUN ("" when its text can be pasted)."""
    if turn.get("timeout"):
        return "handoff: timeout"
    if turn.get("returncode") != 0 or turn.get("subtype") != "success":
        return f"handoff: exit {turn.get('returncode')}, {turn.get('subtype') or 'no result'}"
    if not str(turn.get("text") or "").strip():
        return "handoff: no text"
    if not turn.get("cost_reported") or float(turn.get("cost") or 0.0) <= 0.0:
        return "handoff: no cost reported"
    if turn.get("context_carried") is False:
        return "handoff: the resumed turn did not carry session 1's context"
    if len(str(turn["text"])) > MAX_PROMPT:
        return f"handoff: text over {MAX_PROMPT} characters"
    return ""


def carried(first: dict[str, Any], turn: dict[str, Any]) -> bool | None:
    """The resumed turn's first request holds at least 90 % of session 1's last request's
    context (a fresh session would hold only the system prompt and the request)."""
    before, after = first.get("last_prompt"), turn.get("first_prompt")
    if not before or not after:
        return None
    return after >= 0.9 * before


# ---- one arm -------------------------------------------------------------------------------------


def decoys(name: str) -> list[str]:
    """carry.DECOYS rules of other scenes for S's store, never one the scene names `near`."""
    near = set(HANDOFF[name]["near"])
    pool = sorted(k for k in carry.DECOY_POOL if k not in near)
    start = sum(map(ord, name)) % len(pool)
    return [carry.DECOY_POOL[k] for k in (pool[start:] + pool[:start])[: carry.DECOYS]]


def seed(run: Path, repo: Path, name: str) -> None:
    """The decoys in S's store, as earlier sessions of this project left them (carry.seed)."""
    rules = [{"text": text, "p": 0.9, "session": f"earlier-{i}", "index": 1,
              "at": 1_790_000_000.0 + i * 3600, "files": carry.said_while(text)}
             for i, text in enumerate(decoys(name))]  # fmt: skip
    payload = json.dumps({"rules": rules[::-1], "asked": [], "audited": []})
    key = carry.project_name(repo)
    for folder in {key, key[:1].lower() + key[1:], key[:1].upper() + key[1:]}:
        (run / "store" / folder).mkdir(parents=True, exist_ok=True)
        (run / "store" / folder / "rules.json").write_text(payload, encoding="utf-8")


def steps_of(arm: str) -> list[str]:
    resume = f"handoff: claude -p --resume <session 1 id> {HANDOFF_REQUEST!r}"
    return ["session 1: first", *([resume] if arm == "H" else []),
            "session 2: " + ("handoff.txt" if arm == "H" else "continue")]  # fmt: skip


def arm_run(out: Path, name: str, model: str, arm: str, rep: int, keyfile: Path, dry: bool,
            clean: bool = True) -> dict[str, Any]:  # fmt: skip
    run = out / f"{name}-{model}-{arm}-{rep}"
    scene = HANDOFF[name]
    run.mkdir(parents=True, exist_ok=True)
    prepare = (lambda repo: carry_s.install(run, repo, keyfile, carry.environment())) \
        if arm == "S" else None  # fmt: skip
    repo = carry.build(run, {"files": scene["files"]}, prepare)
    config = carry.clean_config(run) if clean else None
    if arm == "S":
        seed(run, repo, name)
    row: dict[str, Any] = {"scene": name, "model": model, "arm": arm, "repeat": rep,
                           "planned": steps_of(arm)}  # fmt: skip
    if dry:
        return {**row, "dry": True, "repo": str(repo)}
    token = carry.clean_token() if clean else ""
    try:
        done = sessions_of(run, repo, scene, model, arm, config)
    finally:
        found = carry.scrub(run, token) if clean else ([], [])
    flags = {**({"token_scrubbed": found[0]} if found[0] else {}),
             **({"token_in_git": found[1]} if found[1] else {})}  # fmt: skip
    full = {**row, **done, **flags}
    return carry.redact(full, token) if clean else full


def sessions_of(run: Path, repo: Path, scene: dict[str, Any], model: str, arm: str,
                config: Path | None) -> dict[str, Any]:  # fmt: skip
    projects = config / "projects" if config else carry.PROJECTS
    ran: list[dict[str, Any]] = []
    turn: dict[str, Any] = {}
    cut = ""
    first = one(run, repo, scene["first"], model, arm, "session-1", config, projects)
    ran.append(first)
    cut = session_cut(first, model) or first.get("harness_cut", "")
    if not cut and not first.get("limit_hit") and arm == "H":
        turn = handoff_step(run, repo, first, model, config)
        cut = "" if turn.get("limit_hit") else handoff_cut(first, turn)
    limit = first.get("limit_hit") or turn.get("limit_hit")
    if not cut and not limit:
        carry.commit_wip(repo)
        prompt = turn["text"] if arm == "H" else scene["continue"]
        second = one(run, repo, prompt, model, arm, "session-2", config, projects)
        ran.append(second)
        limit = second.get("limit_hit")
        cut = session_cut(second, model) or second.get("harness_cut", "")
    jev = carry_s.jev(run) if arm == "S" else {}
    if arm == "S" and not cut and not limit:
        broken = carry_s.pair_breaks(jev)
        cut = f"harness: {'; '.join(broken)}" if broken else ""
    calls = [*ran, *([turn] if turn else [])]
    row = {"sessions": [brief(s) for s in ran], "handoff": handoff_facts(turn, scene),
           "given": carry.given(run), "native_after_1": first.get("native", []), **jev,
           "cost": round(sum(float(s.get("cost") or 0.0) for s in calls), 6),
           "tokens": {k: sum(s["tokens"][k] for s in calls if s.get("tokens"))
                      for k in ("input", "output", "cache_read", "cache_write")},
           "subagents": sum(int(s.get("subagents") or 0) for s in calls),
           "crossed_midnight": crossed(ran), "limit_hit": bool(limit)}  # fmt: skip
    if cut or limit:
        return {**row, "cut": cut or "usage limit"}
    return {**row, **checks(repo, scene)}


def one(run: Path, repo: Path, prompt: str, model: str, arm: str, tag: str,
        config: Path | None, projects: Path) -> dict[str, Any]:  # fmt: skip
    since = carry_s.hook_rows(run)
    result = call(run, repo, command(prompt, model), tag, config, SESSION_TIMEOUT)
    auto = (result.get("init") or {}).get("memory_auto")
    broken = carry_s.session_breaks(run, result, since) \
        if arm == "S" and carry.session_ran(result) else []  # fmt: skip
    return {
        **result,
        "native": carry.native_memory(repo, projects, auto),
        **({"harness_cut": f"harness: {tag}: {'; '.join(broken)}"} if broken else {}),
    }


def handoff_step(run: Path, repo: Path, first: dict[str, Any], model: str,
                 config: Path | None) -> dict[str, Any]:  # fmt: skip
    """H's ritual: session 1 resumed once with HANDOFF_REQUEST; its text kept in handoff.txt."""
    sid = (first.get("init") or {}).get("session_id")
    if not sid:
        return {"returncode": None, "subtype": "", "text": "", "tag": "handoff",
                "error": "session 1 reported no session id"}  # fmt: skip
    turn = call(run, repo, command(HANDOFF_REQUEST, model, resume=str(sid)), "handoff", config,
                HANDOFF_TIMEOUT)  # fmt: skip
    turn = {**turn, "resumed": str(sid), "context_carried": carried(first, turn),
            "same_session": (turn.get("init") or {}).get("session_id") == sid}  # fmt: skip
    (run / "handoff.txt").write_text(str(turn.get("text") or ""), encoding="utf-8")
    return turn


def handoff_facts(turn: dict[str, Any], scene: dict[str, Any]) -> dict[str, Any]:
    if not turn:
        return {}
    text = str(turn.get("text") or "")
    keys = (
        "returncode",
        "subtype",
        "cost",
        "cost_reported",
        "context_carried",
        "same_session",
        "first_prompt",
        "tokens",
        "seconds",
        "tools",
        "error",
    )
    return {**{k: turn.get(k) for k in keys if k in turn}, "chars": len(text),
            "names": names_c_d(text, scene)}  # fmt: skip


def brief(s: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "tag",
        "returncode",
        "subtype",
        "timeout",
        "cost",
        "turns",
        "tools",
        "seconds",
        "started",
        "init",
        "tokens",
        "subagents",
        "limit_hit",
        "native",
        "harness_cut",
        "first_prompt",
        "last_prompt",
        "is_error",
        "api_error_status",
    )
    return {k: s.get(k) for k in keys if k in s}


def crossed(ran: list[dict[str, Any]]) -> bool:
    if len(ran) < 2:
        return False
    start = dt.datetime.fromtimestamp(ran[0]["started"]).date()
    end = dt.datetime.fromtimestamp(ran[-1]["started"] + ran[-1]["seconds"]).date()
    return start != end


def checks(repo: Path, scene: dict[str, Any]) -> dict[str, Any]:
    try:
        tests = subprocess.run(
            [carry.PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=300,
        ).returncode
    except subprocess.TimeoutExpired:
        tests = -1
    found = {name: carry.passes(repo, check_code(scene, name)) for name in CHECKS}
    return {"tests_pass": tests == 0, **{f"{k}_pass": v for k, v in found.items()},
            "kept_all": bool(found["task"] and found["fact"] and found["decision"])}  # fmt: skip


# ---- a run ---------------------------------------------------------------------------------------


def rows_of(out: Path) -> list[dict[str, Any]]:
    path = out / "f2.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def ledger(out: Path) -> float:
    path = out / "ledger.jsonl"
    if not path.exists():
        return 0.0
    return sum(float(json.loads(x).get("usd") or 0.0)
               for x in path.read_text(encoding="utf-8").splitlines() if x.strip())  # fmt: skip


def book(out: Path, kind: str, usd: float, what: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "ledger.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"kind": kind, "usd": round(usd, 6), "what": what,
                            "at": time.strftime("%Y-%m-%d %H:%M:%S")}) + "\n")  # fmt: skip


def lost_cost(folder: Path) -> float:
    """What an interrupted arm had spent: its streams' own results and its decisions."""
    claude = sum(carry.read_stream(f)["cost"] for f in sorted(folder.glob("*.jsonl"))
                 if f.name.startswith(("session-", "handoff")))  # fmt: skip
    return claude + carry_s.jev(folder)["jev_usd"]


def interrupts(out: Path) -> dict[str, int]:
    path = out / "interrupts.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def stop_file(out: Path, extra: Path | None) -> bool:
    return any((d / "STOP").exists() for d in (out, extra) if d is not None)


def wait_for_day(seconds: float, clock: Callable[[], dt.datetime], sleep: Callable[[float], Any],
                 stopped: Callable[[], bool]) -> bool:  # fmt: skip
    """Waits while `seconds` from now would reach the next day; False if a STOP came first."""
    while True:
        now = clock()
        end = now + dt.timedelta(seconds=seconds * WALL_FACTOR + MIDNIGHT_MARGIN_S)
        if end.date() == now.date():
            return True
        if stopped():
            return False
        print(f"midnight rule: waiting at {now:%H:%M:%S}", flush=True)
        sleep(60)


def run_plan(out: Path, run: str, keyfile: Path, dry: bool, cap: float, night: Path | None,
             clock: Callable[[], dt.datetime] = dt.datetime.now,
             sleep: Callable[[float], Any] = time.sleep,
             arm_fn: Callable[..., dict[str, Any]] = arm_run) -> str:  # fmt: skip
    """Runs what is left of `run`; returns why it stopped ("cap", "limit", "harness", "manual")
    or "" at its end."""
    plan = build_plan(run)
    rows = [] if dry else rows_of(out)
    done = {(r["scene"], r["model"], r["arm"], r["repeat"]) for r in rows}
    seen = interrupts(out)
    failed = 0
    for index, (name, model, arm, rep) in enumerate(plan):
        if (name, model, arm, rep) in done:
            continue
        folder = out / f"{name}-{model}-{arm}-{rep}"
        if not dry and stop_file(out, night):
            print("stop: a STOP file", flush=True)
            return "manual"
        if folder.exists() and not dry:
            lost = lost_cost(folder)
            book(out, "interrupted", lost, folder.name)
            seen = {**seen, folder.name: seen.get(folder.name, 0) + 1}
            (out / "interrupts.json").write_text(json.dumps(seen), encoding="utf-8")
            shutil.rmtree(folder, onexc=carry._writable)
            if seen[folder.name] > INTERRUPTS:
                rows.append(
                    {
                        "scene": name,
                        "model": model,
                        "arm": arm,
                        "repeat": rep,
                        "cut": f"interrupted {seen[folder.name]} times",
                        "cost": 0.0,
                    }
                )
                (out / "f2.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
                continue
            print(f"interrupted arm {folder.name}: its {lost:.3f} USD counted, it runs again",
                  flush=True)  # fmt: skip
        spent = 0.0 if dry else ledger(out)
        if spent + reserve_of(model, arm) > cap:
            print(f"stop: {spent:.2f} USD spent, the next arm could pass {cap}", flush=True)
            return "cap"
        first_of_triple = index % len(ARMS) == 0
        expected = EXPECTED_ARM_S[model] * (len(ARMS) if first_of_triple else 1)
        if not dry and not wait_for_day(expected, clock, sleep, lambda: stop_file(out, night)):
            return "manual"
        row = arm_fn(out, name, model, arm, rep, keyfile, dry)
        if dry:
            print(json.dumps({k: row[k] for k in ("scene", "model", "arm", "repeat", "planned")}))
            continue
        usd = float(row.get("cost") or 0.0) + float(row.get("jev_usd") or 0.0)
        book(out, "arm", usd, folder.name)
        if row.get("limit_hit"):  # a pause: no row; the folder is kept aside, the arm runs again
            stamp = time.strftime("%Y%m%dT%H%M%S")
            shutil.move(str(folder), str(folder.with_name(f"{folder.name}.limit-{stamp}")))
            (out / "LIMIT.flag").write_text(f"{stamp} {folder.name}\n", encoding="utf-8")
            print("stop: the subscription's usage limit (LIMIT.flag)", flush=True)
            return "limit"
        failed = failed + 1 if str(row.get("cut") or "").find("without a result") >= 0 else 0
        if failed >= BROKEN_AFTER:
            rows.append(row)
            (out / "f2.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
            print(f"stop: {failed} arms in a row ended without a result", flush=True)
            return "broken"
        rows.append(row)
        (out / "f2.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
        brief_row = {k: row.get(k) for k in ("scene", "arm", "repeat", "kept_all", "task_pass",
                                             "fact_pass", "decision_pass", "intact_pass", "cut",
                                             "cost")}  # fmt: skip
        print(json.dumps(brief_row), f"spent {ledger(out):.2f}", flush=True)
        if str(row.get("cut") or "").startswith("harness"):
            print(f"stop: {row['cut']}", flush=True)
            return "harness"
    return ""


def complete(out: Path, run: str) -> bool:
    have = {(r["scene"], r["model"], r["arm"], r["repeat"]) for r in rows_of(out)}
    return all(p in have for p in build_plan(run))


def execute(run: str, out: Path, cap: float, dry: bool = False,
            night: Path | None = None) -> str:  # fmt: skip
    """A whole run: refusals, the key and Jev's preflight, then the plan."""
    if not dry:
        require_seal()
        carry.refuse_unclean(out)
        carry.record_claude(out, False, True)
        if (out / "LIMIT.flag").exists():
            raise SystemExit("LIMIT.flag in the run folder: a usage limit paused it")
    if not dry and complete(out, run):
        return ""
    plan = build_plan(run)
    keyfile = out / "typesafe.key" if dry else carry.keyfile_from_harness_env(out)
    try:
        if not dry:
            book(out, "preflight", carry.jev_first(out, plan, keyfile), "jev-preflight")
        return run_plan(out, run, keyfile, dry, cap, night)
    finally:
        keyfile.unlink(missing_ok=True)


# ---- seal ----------------------------------------------------------------------------------------

SEALED_FIXED = (
    "f2-night-run.cmd",
    "benchmarks/memory_carry/handoff.py", "benchmarks/memory_carry/handoff_analyze.py",
    "benchmarks/memory_carry/handoff_night.py", "benchmarks/memory_carry/handoff_preflight.py",
    "benchmarks/memory_carry/scenes_handoff.py",
    "tests/test_memory_carry_handoff.py", "tests/test_memory_carry_handoff_run.py",
)  # fmt: skip
SEALED_GLOBS = ("src/sanchopanza/**/*.py", "benchmarks/memory_carry/*.py")


def sealed_paths(repo: Path = REPO) -> tuple[str, ...]:
    found = {p.relative_to(repo).as_posix() for g in SEALED_GLOBS for p in repo.glob(g)
             if "__pycache__" not in p.parts}  # fmt: skip
    return (*SEALED_FIXED, *sorted(found - set(SEALED_FIXED)))


def manifest(repo: Path = REPO, results: Path = RESULTS) -> dict[str, str]:
    """`<path> -> sha256` of prereg.md and every sealed file (LF bytes)."""

    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()

    doc = (results / "prereg.md").relative_to(repo).as_posix()
    return {p: digest(repo / p) for p in (doc, *sealed_paths(repo))}


def combined(found: dict[str, str]) -> str:
    return hashlib.sha256("".join(f"{k} {v}\n" for k, v in found.items()).encode()).hexdigest()


def seal(repo: Path = REPO, results: Path = RESULTS) -> str:
    """prereg.manifest.json and prereg.sha256; a different seal already there is refused."""
    found = manifest(repo, results)
    value = combined(found)
    target = results / "prereg.sha256"
    if target.exists() and target.read_text().strip() not in ("", value):
        raise SystemExit("prereg.sha256 already holds another seal: nothing written")
    (results / "prereg.manifest.json").write_text(json.dumps(found, indent=1) + "\n",
                                                  encoding="utf-8", newline="\n")  # fmt: skip
    target.write_text(value + "\n", encoding="utf-8", newline="\n")
    return value


def seal_ok(repo: Path = REPO, results: Path = RESULTS) -> bool:
    target = results / "prereg.sha256"
    return target.exists() and target.read_text().strip() == combined(manifest(repo, results))


def require_seal() -> None:
    if not seal_ok():
        raise SystemExit("prereg.md or the code differ from the seal (or no seal): nothing run")


def main(argv: list[str] | None = None) -> int:
    carry.ignore_interrupts()
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", choices=sorted(RUNS))
    parser.add_argument("--out")
    parser.add_argument("--cap", type=float)
    parser.add_argument("--dry", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--seal", action="store_true")
    args = parser.parse_args(argv)
    if args.seal:
        print(seal())
        return 0
    if args.preflight:
        import handoff_preflight

        return handoff_preflight.main(Path(args.out) if args.out else OUT)
    if not args.run:
        parser.error("--run, --preflight or --seal")
    out = Path(args.out) if args.out else OUT / args.run
    cap = min(args.cap if args.cap is not None else RUNS[args.run]["cap"], RUNS[args.run]["cap"])
    return EXIT[execute(args.run, out, cap, args.dry)]


if __name__ == "__main__":
    raise SystemExit(main())
