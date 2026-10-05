"""Browse, development: the `sources` Stop hook on free FRAMES tasks, Sonnet and Haiku.

python benchmarks/browse/free_frames.py --plan          # free: ids and arms in run order
python benchmarks/browse/free_frames.py --preflight     # free: version, hook, global settings
python benchmarks/browse/free_frames.py --probe-deny    # ~0.05 USD: the deny rules refuse
python benchmarks/browse/free_frames.py --smoke         # the first task, both -SRC arms
python benchmarks/browse/free_frames.py --live          # the pilot, under its ceiling
python benchmarks/browse/free_frames.py                 # free: the report so far

A development pilot of `sanchopanza install --sources` measured the way people use Claude Code:
the session gets the question, the calibration's ANSWER instruction and Claude Code's normal
tools (`free_e2e.one_session`: WebSearch, WebFetch, Playwright MCP, files, subagents; Bash and
the scheduling tools denied), nothing else. Four arms, interleaved so a ceiling stop cuts them
alike: SONNET (cap 1.50 USD), SONNET-SRC (1.05 + the hook), HAIKU (0.60), HAIKU-SRC (0.42 + the
hook). A -SRC cap is 70 % of its base: the calibration found a stop there costs no right answer,
so the hook's extra turn is paid out of money the base arm spends on wrong sessions.

Tasks: FRAMES (Krishna et al., 2024), test split, cached locally only. Twenty tasks with
"Multiple constraints" among their reasoning types, an answer of at most four words and two to
four Wikipedia links; half with that type alone, half with Numerical or Temporal reasoning as
well; seeded. Only the ids reach the repository (`frames-ids.txt`); the rows, which keep the
agents' answers, live beside the cached set.

Every arm denies WebFetch to the hosts that serve the set (Hugging Face, GitHub, Kaggle, Papers
with Code) through the session's own settings, and a session whose tool results mention the set
is marked `leak`. The hook is wired through `--settings` of each -SRC session alone, with its
marks in the session's own folder: never in `~/.claude/settings.json`, where another session
measures its own Stop hook.

Grading is automatic and provisional (normalised; the gold contained in the ANSWER line); the
real grade is by hand. The ANSWER is the last one in the main transcript, so a session the cap
stops in the hook's extra turn keeps the one it gave before; the one before the block is kept
too, for the before/after matrix. A 429 or "weekly limit" in a session stops the phase at once.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import pathlib
import random
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


calib = _load("browse_free_calib", HERE / "free_calib.py")
free = calib.free
phase = free.nav.phase
trace = free.trace

from sanchopanza.harness.sources_hook import REQUEST  # noqa: E402 (src is on the path now)
from sanchopanza.harness.sources_v2 import REQUEST_V2  # noqa: E402

FRAMES = free.CACHE / "frames-test.tsv"
RESULTS = free.nav.base.ROOT / "docs" / "results" / "2026-10-05-browse-frames"
IDS = RESULTS / "frames-ids.txt"
REPORT = RESULTS / "frames.json"
PRIVATE = free.CACHE / "frames-pilot"  # the rows keep the agents' answers: not in the repo
SESSIONS = PRIVATE / "sessions.jsonl"
SMOKE = PRIVATE / "smoke-sessions.jsonl"
PROBE = PRIVATE / "deny-probe.json"
SEED = 20261005
N_TASKS = 20
CEILING_USD = 32.0
SMOKE_CEILING_USD = 3.0
CAPS = {"SONNET": 1.50, "SONNET-SRC": 1.05, "HAIKU": 0.60, "HAIKU-SRC": 0.42}
ARMS = tuple(CAPS)
RESERVE_USD = max(CAPS.values())  # the ceiling keeps the largest cap free before each session
CLAUDE_VERSION = "2.1.287"
CONSTRAINTS = "Multiple constraints"
WITH = frozenset({"Numerical reasoning", "Temporal reasoning"})
STRATA = ("alone", "with")
DENIED_HOSTS = (
    "huggingface.co", "hf.co", "datasets-server.huggingface.co", "github.com",
    "raw.githubusercontent.com", "kaggle.com", "www.kaggle.com", "paperswithcode.com",
    "www.paperswithcode.com",
)  # fmt: skip
DENY = tuple(f"WebFetch(domain:{host})" for host in DENIED_HOSTS)
HOOK_TIMEOUT_S = 30
MARK = REQUEST[:48]  # the block's reason as it lands in the transcript
MARKS = (MARK, REQUEST_V2[:48])  # either version's
_YEAR_ADDED = re.compile(r"^(.*[a-z].*?)\s+(?:1\d{3}|20\d{2})$")
_PARENS_ADDED = re.compile(r"\s*\([^()]*\)\s*$")
_LEAK_ANY_CASE = re.compile(r"frames-benchmark|frames-test\.tsv|sanchopanza[\\/]+free", re.I)
_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?!\w)")  # a whole token: not 1990s
_LIMIT = re.compile(r"\b429\b|weekly limit", re.I)
ANSWER_KEPT = 200


# --- tasks --------------------------------------------------------------------------------------


def read_frames(path: pathlib.Path = FRAMES) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def types_of(row: Mapping[str, str]) -> frozenset[str]:
    return frozenset(
        t.strip() for t in str(row.get("reasoning_types") or "").split("|") if t.strip()
    )


def links_of(row: Mapping[str, str]) -> int:
    return sum(1 for k, v in row.items() if k.startswith("wikipedia_link_") and str(v).strip())


def eligible(row: Mapping[str, str]) -> bool:
    return (
        CONSTRAINTS in types_of(row)
        and 0 < len(str(row.get("Answer") or "").split()) <= 4
        and 2 <= links_of(row) <= 4
    )


def stratum(row: Mapping[str, str]) -> str | None:
    kinds = types_of(row)
    if kinds == {CONSTRAINTS}:
        return "alone"
    return "with" if kinds & WITH else None


def tid_of(row: Mapping[str, str]) -> str:
    return f"FR{row['']}"


def sample(rows: Sequence[Mapping[str, str]], n: int = N_TASKS, seed: int = SEED) -> list[dict]:
    """n eligible rows, half of each stratum, seeded and in file order before the draw; the two
    halves interleaved."""
    rng = random.Random(seed)
    halves = []
    for name in STRATA:
        pool = [dict(r) for r in rows if eligible(r) and stratum(r) == name]
        halves.append(rng.sample(pool, n // 2))
    return calib.interleave(halves)


def tasks(rows: Sequence[Mapping[str, str]], ids: Sequence[str]) -> list[tuple[str, str, str, str]]:
    by_id = {tid_of(r): r for r in rows}
    return [(tid, "", by_id[tid]["Prompt"], by_id[tid]["Answer"]) for tid in ids]


def chosen_ids(rows: Sequence[Mapping[str, str]]) -> list[str]:
    """The ids in the repository when they are there, else the sample, written down."""
    if IDS.exists():
        return [x.strip() for x in IDS.read_text(encoding="utf-8").splitlines() if x.strip()]
    ids = [tid_of(r) for r in sample(rows)]
    IDS.parent.mkdir(parents=True, exist_ok=True)
    IDS.write_text("\n".join(ids) + "\n", encoding="utf-8")
    return ids


def plan(items: Sequence[tuple]) -> list[tuple]:
    """(index, task, run, arm): every task in every arm, interleaved by task."""
    streams = [[(t, arm) for t in items] for arm in ARMS]
    return [(i, task, 1, arm) for i, (task, arm) in enumerate(calib.interleave(streams))]


# --- grading and transcript reading -------------------------------------------------------------


def normal(text: str) -> str:
    t = str(text or "").lower().replace(",", "").replace("$", "").replace("%", "")
    t = re.sub(r"['’]", "", t)  # John's -> johns
    t = re.sub(r"[^\w\s.]", " ", t)
    t = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", t)  # a dot stays only inside a number
    return " ".join(t.split())


def _symbols(answer: str, gold: str) -> bool:
    """A gold of symbols alone (the normaliser leaves nothing of it): the gold, spaces dropped,
    as one token of the answer, emphasis and a final full stop stripped."""
    want = "".join(str(gold or "").split())
    tokens = [t.strip("*`'\"") for t in str(answer or "").split()]
    return bool(want) and any(t in (want, want + ".") for t in tokens)


def golds(gold: str) -> list[str]:
    """The gold, and the gold without what a FRAMES gold sometimes appends to the answer: a
    trailing year after a name, or a trailing parenthesis."""
    want = normal(gold)
    out = [want]
    year = _YEAR_ADDED.match(want)
    if year:
        out.append(year.group(1))
    bare = normal(_PARENS_ADDED.sub("", str(gold or "")))
    if bare and bare != want:
        out.append(bare)
    return out


def graded(answer: str, gold: str) -> bool:
    """Provisional: the normalised gold inside the normalised ANSWER; a numeric gold must equal
    a number in it. A gold with a year or a parenthesis appended also passes without it; a gold
    of symbols alone is matched as symbols."""
    got, want = normal(answer), normal(gold)
    if not want:
        return _symbols(answer, gold)
    if not got:
        return False
    if re.fullmatch(r"-?\d+(?:\.\d+)?", want):
        return any(float(x) == float(want) for x in _NUMBER.findall(got))
    return any(f" {g} " in f" {got} " for g in golds(gold))


def leaked(text: str) -> bool:
    return "FRAMES" in text or bool(_LEAK_ANY_CASE.search(text))


def limit_hit(reply_or_stderr: str) -> bool:
    return bool(_LIMIT.search(reply_or_stderr or ""))


def main_entries(folder: pathlib.Path) -> list[tuple[str, dict[str, Any]]]:
    """(raw line, entry) of the main agent's transcript, in file order."""
    out = []
    for path in sorted(folder.glob("*.jsonl")) if folder.is_dir() else []:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip():
                entry = json.loads(line)
                if not entry.get("isSidechain"):
                    out.append((line, entry))
    return out


def _texts(entry: Mapping[str, Any]) -> list[str]:
    content = (entry.get("message") or {}).get("content")
    blocks = content if isinstance(content, list) else []
    return [
        str(b.get("text") or "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"
    ]


def answers(entries: Sequence[tuple[str, Mapping[str, Any]]]) -> dict[str, Any]:
    """The last ANSWER before the hook's block, the last overall, and when the block came."""
    block = next((i for i, (line, _e) in enumerate(entries) if any(m in line for m in MARKS)), None)
    before = after = ""
    for i, (_line, entry) in enumerate(entries):
        if entry.get("type") != "assistant":
            continue
        for text in _texts(entry):
            line = free.nav.answer_line(text)
            if line:
                after = line
                before = line if block is None or i < block else before
    block_ts = str(entries[block][1].get("timestamp") or "") if block is not None else None
    return {"hook_fired": block is not None, "block_ts": block_ts, "answer_before": before,
            "answer_after": after}  # fmt: skip


def usd_after(calls: Sequence[Mapping[str, Any]], path: Sequence[float], block_ts: str) -> float:
    """What the session spent after the block: the total less the cost of the calls before it."""
    spent_before = [usd for c, usd in zip(calls, path, strict=True) if c["ts"] <= block_ts]
    total = path[-1] if path else 0.0
    return round(total - (spent_before[-1] if spent_before else 0.0), 4)


def inspect(row: Mapping[str, Any], gold: str, cap: float, sources_dir: pathlib.Path) -> dict:
    """The pilot's fields, read from the session's own transcripts and folder."""
    folder = trace.folder_of(row["workdir"])
    seen = answers(main_entries(folder))
    calls = trace.load_calls(folder)
    path = trace.trajectory(calls, row["list_usd"], row.get("usd_by_model") or {})
    work = pathlib.Path(row["workdir"])
    stderr = (
        (work / "stderr.txt").read_text(encoding="utf-8") if (work / "stderr.txt").exists() else ""
    )
    return {
        "ok_auto": graded(seen["answer_after"], gold),
        "ok_before": graded(seen["answer_before"], gold),
        "provisional": True,
        "hook_fired": seen["hook_fired"],
        "hook_marked": sources_dir.is_dir() and any(sources_dir.glob("sources-*.json")),
        "usd_after_block": usd_after(calls, path, seen["block_ts"]) if seen["block_ts"] else None,
        "answer_before": seen["answer_before"][:ANSWER_KEPT],
        "answer_after": seen["answer_after"][:ANSWER_KEPT],
        "hit_cap": row.get("subtype") == "error_max_budget_usd" or row["list_usd"] >= cap * 0.999,
        "leak": any(leaked(c["results"]) for c in calls),
        "limit": limit_hit(stderr),
    }


# --- sessions -----------------------------------------------------------------------------------


def hook_command() -> str:
    return f'"{free.nav.HOOK_PYTHON.as_posix()}" -m sanchopanza.harness.sources_hook'


def is_src(arm: str) -> bool:
    """An arm with the sources hook, of either version (-SRC, -SRC2)."""
    return "-SRC" in arm


def hooks_for(arm: str) -> dict[str, Any] | None:
    if not is_src(arm):
        return None
    hook = {"type": "command", "command": hook_command(), "timeout": HOOK_TIMEOUT_S}
    return {"Stop": [{"matcher": "", "hooks": [hook]}]}


def session_for(log_to: pathlib.Path):
    def session(task: tuple, run: int, arm: str) -> dict[str, Any]:
        sources_dir = pathlib.Path(tempfile.mkdtemp(prefix=f"sp-frames-src-{task[0].lower()}-"))
        row = free.one_session(
            task, run, arm, session_max_usd=CAPS[arm], deny=DENY, hooks=hooks_for(arm),
            env_extra={"SANCHOPANZA_SOURCES_DIR": str(sources_dir)},
        )  # fmt: skip
        found = inspect(row, task[3], CAPS[arm], sources_dir)
        out = {**row, **found, "success_reply": row["success"], "success": found["ok_auto"]}
        if found["limit"] or phase.usage_limited(row):
            phase._log(log_to, f"STOP-LIMIT {task[0]} {arm}: 429 or weekly limit in the session")
            out = {**out, "answer": free.LIMIT_MARKER}  # run_phase marks it not run and stops
        return out

    return session


# --- checks -------------------------------------------------------------------------------------


def global_settings_clean() -> bool:
    path = pathlib.Path.home() / ".claude" / "settings.json"
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    return "sources-hook" not in text and "sources_hook" not in text


def preflight() -> list[str]:
    """Free checks before anything is spent: the pinned Claude Code, a hook that blocks once on
    a session that used the web, the set on disk, and no sources hook in the global settings."""
    problems: list[str] = []
    claude = shutil.which("claude") or "claude"
    try:
        version = subprocess.run([claude, "--version"], capture_output=True, timeout=60)
        if CLAUDE_VERSION not in version.stdout.decode("utf-8", errors="replace"):
            problems.append(f"claude on PATH ({claude}) is not {CLAUDE_VERSION}")
    except (OSError, subprocess.TimeoutExpired) as error:
        problems.append(f"claude did not run: {error.__class__.__name__}")
    if not FRAMES.exists():
        problems.append(f"no {FRAMES.name} in the cache")
    if not global_settings_clean():
        problems.append("a sources hook is in ~/.claude/settings.json: take it out first")
    outs = hook_twice()
    if json.loads(outs[0] or "{}").get("decision") != "block" or outs[1]:
        problems.append(f"the hook should block once, then stay silent: got {outs}")
    return problems


def web_transcript(path: pathlib.Path, final: str = "") -> pathlib.Path:
    """A one-search transcript in Claude Code's shape: the hook counts a call with its result;
    `final`, when given, is the agent's last reply."""
    use = {"type": "tool_use", "id": "t0", "name": "WebSearch", "input": {"query": "x"}}
    result = {"type": "tool_result", "tool_use_id": "t0", "content": "found"}
    entries = [
        {"type": "assistant", "message": {"role": "assistant", "content": [use]}},
        {"type": "user", "message": {"role": "user", "content": [result]}},
    ]
    if final:
        text = [{"type": "text", "text": final}]
        entries.append({"type": "assistant", "message": {"role": "assistant", "content": text}})
    path.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    return path


def hook_twice(env_extra: Mapping[str, str] | None = None, final: str = "") -> list[str]:
    """The hook's stdout on the same Stop event twice, run the way a -SRC session runs it."""
    with tempfile.TemporaryDirectory() as tmp:
        transcript = web_transcript(pathlib.Path(tmp) / "t.jsonl", final)
        event = {"hook_event_name": "Stop", "session_id": "preflight", "stop_hook_active": False,
                 "transcript_path": str(transcript)}  # fmt: skip
        env = {**free.nav.base.clean_env(dict(os.environ)), "PYTHONPATH": str(free.SRC),
               "SANCHOPANZA_SOURCES_DIR": str(pathlib.Path(tmp) / "m"),
               **(env_extra or {})}  # fmt: skip
        outs = []
        for _ in range(2):
            ran = subprocess.run(
                [str(free.nav.HOOK_PYTHON), "-m", "sanchopanza.harness.sources_hook"],
                input=json.dumps(event).encode(), env=env, capture_output=True, timeout=60,
            )  # fmt: skip
            outs.append(ran.stdout.decode("utf-8", errors="replace").strip())
    return outs


def deny_probe() -> dict[str, Any]:
    """One Haiku session asked to WebFetch two denied hosts: each result must be a refusal."""
    question = (
        "Use the WebFetch tool on https://huggingface.co/ and then on https://github.com/ - one "
        "call each, no other tool - and say whether each call was refused."
    )
    row = free.one_session(("PROBE", "", question, ""), 1, "HAIKU", session_max_usd=0.15, deny=DENY)
    folder = trace.folder_of(row["workdir"])
    fetched = []
    for _line, entry in main_entries(folder):
        content = (entry.get("message") or {}).get("content")
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                text = trace._result_text(block.get("content"))
                fetched.append({"is_error": bool(block.get("is_error")), "head": text[:160]})
    return {"list_usd": row["list_usd"], "version": row["version"], "results": fetched,
            "workdir": row["workdir"]}  # fmt: skip


# --- report -------------------------------------------------------------------------------------


def report(rows: Sequence[Mapping[str, Any]], arms: Sequence[str] = ARMS) -> dict[str, Any]:
    spent = round(sum(r["list_usd"] for r in rows), 2)
    out: dict[str, Any] = {"provisional_grades": True, "sessions": len(rows), "list_usd": spent}
    out["by_arm"] = {}
    for arm in arms:
        mine = [r for r in rows if r["arm"] == arm]
        if not mine:
            continue
        fired = [r for r in mine if r.get("hook_fired")]
        cell = {
            "sessions": len(mine),
            "ok_auto": sum(bool(r.get("ok_auto")) for r in mine),
            "mean_usd": round(statistics.mean(r["list_usd"] for r in mine), 4),
            "median_usd": round(statistics.median(r["list_usd"] for r in mine), 4),
            "hit_cap": sum(bool(r.get("hit_cap")) for r in mine),
            "leak": sum(bool(r.get("leak")) for r in mine),
            "hook_fired": len(fired),
        }
        if is_src(arm):
            pairs = [(bool(r.get("ok_before")), bool(r.get("ok_auto"))) for r in fired]
            cell["before_after"] = {
                f"{'right' if b else 'wrong'}->{'right' if a else 'wrong'}": pairs.count((b, a))
                for b in (True, False) for a in (True, False)
            }  # fmt: skip
            after = [r["usd_after_block"] for r in fired if r.get("usd_after_block") is not None]
            cell["mean_usd_after_block"] = round(statistics.mean(after), 4) if after else None
        out["by_arm"][arm] = cell
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group()
    for flag in ("--plan", "--preflight", "--probe-deny", "--smoke", "--live"):
        mode.add_argument(flag, action="store_true")
    args = ap.parse_args()
    PRIVATE.mkdir(parents=True, exist_ok=True)
    rows_all = read_frames()
    steps = plan(tasks(rows_all, chosen_ids(rows_all)))
    if args.plan:
        for i, task, _run, arm in steps:
            print(i, task[0], arm, CAPS[arm])
        return 0
    if args.preflight or args.smoke or args.live or args.probe_deny:
        problems = preflight()
        if problems:
            print("preflight: " + "; ".join(problems), file=sys.stderr)
            return 3
        if args.preflight:
            print("preflight: ok", file=sys.stderr)
            return 0
    if args.probe_deny:
        found = deny_probe()
        PROBE.write_text(json.dumps(found, indent=1), encoding="utf-8")
        print(json.dumps(found, indent=1))
        return 0
    sessions = SMOKE if args.smoke else SESSIONS
    rows = free.nav.done_sessions(sessions)
    code = 0
    if args.smoke:
        first = steps[0][1]
        smoke = [(0, first, 1, "SONNET-SRC"), (0, first, 1, "HAIKU-SRC")]
        limits = phase.Limits(session_max_usd=RESERVE_USD, ceiling_usd=SMOKE_CEILING_USD)
        code, rows = phase.run_phase(smoke, rows, limits, session_for(sessions), sessions)
    elif args.live:
        limits = phase.Limits(session_max_usd=RESERVE_USD, ceiling_usd=CEILING_USD)
        code, rows = phase.run_phase(steps, rows, limits, session_for(sessions), sessions)
    counted = phase.counted(rows)
    if counted:
        result = report(counted)
        if not args.smoke:
            REPORT.write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(json.dumps(result, indent=1))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
