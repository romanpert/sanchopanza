"""Substitution instead of suggestion: if a hook ran find_in_repo itself at the struggle point and
put its top places in front of the agent, would they hold the gold, how early, and is it worth it?
Offline and free: recorded sessions, local work copies, BM25 only. No model, no Jev, no Docker.

    .venv/Scripts/python.exe -m benchmarks.find_auto.evaluate sessions   # triggers per session
    .venv/Scripts/python.exe -m benchmarks.find_auto.evaluate retrieve   # BM25 per instance
    .venv/Scripts/python.exe -m benchmarks.find_auto.evaluate report     # -> auto-table.json
    .venv/Scripts/python.exe -m benchmarks.find_auto.evaluate latency    # index, pickle, load
    .venv/Scripts/python.exe -m benchmarks.find_auto.evaluate real       # live rules, real sessions

Sessions: the 179 single sessions of `benchmarks/find_need` (its `sessions.json`: hard = 5+
searches before the first gold Read, or never). Turns and cost come from each stream's own
messages and `result` event (Haiku 4.5, list price).

Triggers, all computable live (no gold): A the 2nd empty search before an edit of an existing
non-test source file (`replay_empty`); B4/B5/B6 the N-th search before such an edit
(`replay_count`); R3/R4/R5 the N-th search while no source file has been Read or
edited (`replay_untouched`); C at session start when the request names no code
(`real.names_code`); C0 at session start always (the shipped `FIND_ON_PROMPT` hint, which
skips repositories over 3,000 files).

Retrieval: each instance's base snapshot is exported with `git archive HEAD` from an existing
work copy (read only; phase D's `-r<n>-` copies and the running need probe's `work-dnd` are never
read), checked with `git apply --check` of the gold patch, indexed by `context.repo.chunks` and
asked with `BM25Index.top`, exactly `find_in_repo` without a key. Queries: Q1 the issue text (what
the hook sees in the prompt), Q2 Q1 plus the words of the empty searches so far, Q3 Q1 plus the
words of every search so far, Q4 those search words alone. A hit is a gold file (any@k) or a
changed line of the gold patch (hunk@k) among the top k fragments; `short60` is a gold file in
the 60-fragment shortlist, the most a Jev judge could reach. The judged rate is not measured here
(no Jev): it is extrapolated from the retrieval run's judge/ceiling ratios, and said so.

Scratch: ~/.cache/sanchopanza/find-auto/ (snapshots are deleted after indexing). The committed
table holds ids, counts and rates only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import re
import shutil
import statistics
import subprocess
import tarfile
import time
from collections import defaultdict
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

from benchmarks.find_need.real import names_code
from benchmarks.find_need.replay import (
    SEARCH_TOOLS,
    SHELL_TOOLS,
    Call,
    Fire,
    is_empty,
    is_search,
    is_test,
    jsonl,
    replay_count,
    replay_empty,
    source_edits,
    stream_calls,
)

HERE = Path(__file__).resolve().parent
CACHE = Path.home() / ".cache" / "sanchopanza"
NEED_SESSIONS = CACHE / "find-need" / "sessions.json"
VERIFIED = CACHE / "find" / "swebench" / "verified.parquet"
SCRATCH = CACHE / "find-auto"
FACTS = SCRATCH / "sessions-auto.json"
RETRIEVAL = SCRATCH / "retrieval"
SNAP = SCRATCH / "snap"
OUT = HERE / "auto-table.json"
WORK_COPIES = (  # first existing wins; never adopt/work-dnd (running) nor `-r<n>-` (phase D)
    CACHE / "find-e2e" / "work" / "{id}-N",
    CACHE / "adopt" / "work" / "{id}-N",
    CACHE / "adopt" / "work-dal" / "{id}-N",
    CACHE / "adopt" / "work-dn" / "{id}-N",
    CACHE / "adopt" / "work" / "{id}-S",
    CACHE / "adopt" / "work-dal" / "{id}-S",
    CACHE / "adopt" / "work-dn" / "{id}-S",
)
KS = (1, 3, 5)
SHORTLIST = 60
WIDE = 1_000  # BM25 depth before the source-only filter
CODE = "+code"  # suffix of a query whose fragments are source files only
CONFIG_SUFFIXES = frozenset([".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".xml", ".gradle"])
NOT_SOURCE_DIRS = frozenset(["doc", "docs", "examples", "example", "benchmarks", "asv_bench"])
INJECT_K = (3, 5)
TOKEN_CHARS = 3.5  # characters per token for code and paths, a rough count
# Haiku 4.5 list, USD per token: the session caches with the 1 h TTL (2x input) and reads at 0.1x.
CACHE_WRITE, CACHE_READ = 2.0e-6, 0.10e-6
# The retrieval run (docs/results/2026-09-29-find, 117 issues): judged any@k over the 60-fragment
# ceiling (72.7 %). Used only to extrapolate a Jev-judged hook from the measured shortlist.
JUDGE_OVER_CEILING = {1: 51.3 / 72.7, 3: 59.8 / 72.7, 5: 65.0 / 72.7}
HEADER = "sanchopanza ran find_in_repo on the request; places that may bear on it (Read to check):"
_SHELL_WORDS = (
    "grep egrep rg ag ack find fd ls tree head tail xargs cat sed awk sort uniq wc echo cd type "
    "name iname include exclude path print null testbed dev usr lib python python3 site packages "
    "and the for not with from import def class self return none true false"
)
SHELL_WORDS = frozenset(_SHELL_WORDS.split())
WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@")


# ---- pure: patches, hits, triggers, queries ------------------------------------------------------


def gold_lines(patch: str) -> dict[str, set[int]]:
    """Per file, the lines of the old file that the patch changes: removed lines, and for a pure
    insertion the lines on both sides of it."""
    out: dict[str, set[int]] = defaultdict(set)
    path, old, previous = "", 0, ""
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            path, previous = line.split(" b/", 1)[-1].strip(), ""
            continue
        m = HUNK.match(line)
        if m:
            old, previous = int(m.group(1)), ""
            continue
        if not path or line.startswith(("---", "+++", "\\")):
            continue
        kind = line[:1]
        if kind == "-":
            out[path].add(old)
            old += 1
        elif kind == "+" and previous not in ("-", "+"):
            out[path].update({max(1, old - 1), old})
        elif kind == " ":
            old += 1
        previous = kind
    return dict(out)


def parse_key(key: str) -> tuple[str, int, int]:
    path, span = key.rsplit(":", 1)
    first, last = span.split("-")
    return path.replace("\\", "/"), int(first), int(last)


def hits(keys: list[str], lines: Mapping[str, set[int]]) -> dict[str, bool]:
    """Gold file (any@k) and changed gold line (hunk@k) among the first k keys; `short60` over
    all of them (the shortlist)."""
    parsed = [parse_key(k) for k in keys]
    out: dict[str, bool] = {}
    for k in KS:
        top = parsed[:k]
        out[f"any@{k}"] = any(p in lines for p, _, _ in top)
        out[f"hunk@{k}"] = any(p in lines and any(a <= n <= b for n in lines[p]) for p, a, b in top)
    out["short60"] = any(p in lines for p, _, _ in parsed[:SHORTLIST])
    return out


def search_words(call: Call) -> list[str]:
    """The words an agent searched for: Grep/Glob patterns, a shell search's arguments."""
    if call.name in SEARCH_TOOLS:
        text = " ".join(str(call.input.get(k) or "") for k in ("pattern", "glob"))
    elif call.name in SHELL_TOOLS:
        text = re.sub(r"(?:^|\s)--?[\w-]+(?:=\S+)?", " ", str(call.input.get("command") or ""))
    else:
        return []
    words = [w for w in WORD.findall(text) if w.lower() not in SHELL_WORDS]
    return list(dict.fromkeys(words))


def queries(statement: str, calls: list[Call], fire: int) -> dict[str, str]:
    """Q2-Q4 at a fire after call `fire` (1-based; 0 = before any call)."""
    before = [c for c in calls[:fire] if is_search(c.name, c.input)]
    empty = [w for c in before if is_empty(c) for w in search_words(c)]
    every = [w for c in before for w in search_words(c)]
    empty, every = list(dict.fromkeys(empty)), list(dict.fromkeys(every))
    return {"Q2": f"{statement}\n{' '.join(empty)}" if empty else "",
            "Q3": f"{statement}\n{' '.join(every)}" if every else "",
            "Q4": " ".join(every)}  # fmt: skip


def is_source(key: str) -> bool:
    """A fragment of a program file that is not a test, an example, documentation, configuration
    or a hidden folder (`.github`): what a fix edits, and the only kind `+code` shows."""
    from sanchopanza.context.blocks import CODE_SUFFIXES

    path = parse_key(key)[0]
    parts = path.lower().split("/")
    suffix = Path(path).suffix.lower()
    return (suffix in CODE_SUFFIXES and suffix not in CONFIG_SUFFIXES and not is_test(path)
            and not any(p in NOT_SOURCE_DIRS or p.startswith(".") for p in parts[:-1]))  # fmt: skip


def qhash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


WORK_PREFIX = re.compile(r"^.*?/(?:testbed|[^/]+-(?:N|S|F|Nf|Sf|Sm|Sfn|Sb))/")


def repo_path(path: str) -> str:
    """A recorded absolute path made relative to the repository (`/testbed/` in a container, the
    work copy's folder on the host); live, the hook would use the project directory."""
    return WORK_PREFIX.sub("", path.replace("\\", "/"))


def replay_untouched(calls: list[Call], nth: int) -> Fire | None:
    """The `nth` search while no source file has been Read or edited yet: searching without
    having opened any code (computable live, no gold)."""
    closes, count = set(source_edits(calls)), 0
    for i, call in enumerate(calls):
        path = str(call.input.get("file_path") or "")
        if i in closes or (call.name == "Read" and path and is_source(repo_path(path) + ":1-1")):
            return None
        if is_search(call.name, call.input):
            count += 1
            if count == nth:
                return Fire(i + 1, count, "untouched")
    return None


Rule = Callable[[list[Call]], "Fire | None"]
TRIGGERS: dict[str, Rule] = {
    "A": lambda c: replay_empty(c, 2, "source"),
    "B4": lambda c: replay_count(c, 4, "source"),
    "B5": lambda c: replay_count(c, 5, "source"),
    "B6": lambda c: replay_count(c, 6, "source"),
    "R3": lambda c: replay_untouched(c, 3),
    "R4": lambda c: replay_untouched(c, 4),
    "R5": lambda c: replay_untouched(c, 5),
}
TRIGGER_NAMES = {
    "A": "2nd empty search before a source edit",
    "B4": "4th search before a source edit",
    "B5": "5th search before a source edit",
    "B6": "6th search before a source edit",
    "R3": "3rd search before any source file is Read or edited",
    "R4": "4th search before any source file is Read or edited",
    "R5": "5th search before any source file is Read or edited",
    "C": "session start, request names no code",
    "C0": "session start, always (the FIND_ON_PROMPT hint)",
}


def fire_points(calls: list[Call], statement: str) -> dict[str, int | None]:
    """Per trigger, the call after which the hook would add its context (0 = with the prompt)."""
    out: dict[str, int | None] = {}
    for name, rule in TRIGGERS.items():
        fire = rule(calls)
        out[name] = None if fire is None else fire.call
    out["C"] = None if names_code(statement) else 0
    out["C0"] = 0
    return out


# ---- pure: turns and value -----------------------------------------------------------------------


def call_turns(path: Path) -> tuple[list[int], dict[str, Any]]:
    """The 1-based API turn of each main-thread call (in `stream_calls` order) and the result
    event's cost and turns."""
    seen: set[str] = set()
    messages: dict[str, int] = {}
    turns: list[int] = []
    result: dict[str, Any] = {}
    for e in jsonl(path):
        if e.get("type") == "result":
            result = {"cost": e.get("total_cost_usd"), "turns": e.get("num_turns")}
        if e.get("type") != "assistant" or e.get("parent_tool_use_id"):
            continue
        message = e.get("message") or {}
        mid = str(message.get("id"))
        messages.setdefault(mid, len(messages) + 1)
        for b in message.get("content") or []:
            if isinstance(b, Mapping) and b.get("type") == "tool_use" and b.get("id") not in seen:
                seen.add(str(b.get("id")))
                turns.append(messages[mid])
    result.setdefault("turns", len(messages))
    result["api_turns"] = len(messages)
    return turns, result


def turn_at(turns: list[int], call: int) -> int:
    """The turn of call `call` (1-based); 0 for the prompt."""
    return 0 if call <= 0 else turns[min(call, len(turns)) - 1]


def value(fire: int | None, reach_call: int | None, turns: list[int], hit: bool) -> dict[str, Any]:
    """Turns a fire saves if the agent Reads the gold place it was shown on its next turn."""
    if fire is None:
        return {"fired": False}
    before = reach_call is None or fire < reach_call
    out = {"fired": True, "before_reach": before, "hit": hit, "turn": turn_at(turns, fire)}
    if before and hit and reach_call is not None:
        out["saved_turns"] = max(0, turn_at(turns, reach_call) - out["turn"] - 1)
        out["saved_calls"] = max(0, reach_call - fire - 1)
    return out


def context_cost(tokens: float, remaining_turns: int) -> float:
    """Added context: written to the cache once, read on every later turn."""
    return tokens * (CACHE_WRITE + CACHE_READ * max(0, remaining_turns))


def expected_value(
    rows: list[dict[str, Any]], follow: float, detour: float, tokens: float
) -> dict[str, Any]:
    """Saved turns (followed with probability `follow`) against added context on every fire and
    one wrong-file turn (probability `detour`) on a miss before the gold was reached."""
    saved = cost = 0.0
    for r in rows:
        v = r["value"]
        if not v["fired"]:
            continue
        per_turn = r["cost_per_turn"]
        cost += context_cost(tokens, r["turns"] - v["turn"])
        if v.get("saved_turns"):
            saved += follow * v["saved_turns"] * per_turn
        elif v["before_reach"] and not v["hit"]:
            cost += detour * per_turn
    return {"saved_usd": round(saved, 4), "cost_usd": round(cost, 4),
            "net_usd": round(saved - cost, 4)}  # fmt: skip


def render(fragments: list[tuple[str, str]], query: str) -> str:
    """The hook's note: `path:lines` and the fragment's line with most query words."""
    words = {w.lower() for w in WORD.findall(query)}
    lines = [HEADER]
    for key, text in fragments:
        body = [x.strip() for x in text.splitlines() if x.strip()]
        best = max(body, key=lambda x: len(words & {w.lower() for w in WORD.findall(x)}),
                   default="")  # fmt: skip
        lines.append(f"- {key}  {best[:100]}")
    return "\n".join(lines)


# ---- sessions ------------------------------------------------------------------------------------


def verified() -> dict[str, dict[str, Any]]:
    import pyarrow.parquet as pq

    cols = ["instance_id", "repo", "patch", "problem_statement"]
    return {r["instance_id"]: r for r in pq.read_table(VERIFIED, columns=cols).to_pylist()}


def singles() -> list[dict[str, Any]]:
    rows = json.loads(NEED_SESSIONS.read_text(encoding="utf-8"))
    return [r for r in rows if r["source"] != "chains"]


def session_facts(row: Mapping[str, Any], statement: str) -> dict[str, Any]:
    path = CACHE / row["stream"]
    _, calls = stream_calls(path)
    turns, result = call_turns(path)
    if len(turns) != len(calls):
        raise ValueError(f"{path}: {len(turns)} turns for {len(calls)} calls")
    reach_call = row["read_at"] or row["view_at"]
    fires = fire_points(calls, statement)
    asked = {name: queries(statement, calls, fire) for name, fire in fires.items()
             if fire is not None and fire > 0}  # fmt: skip
    cost, n = result.get("cost"), result.get("turns") or len(set(turns)) or 1
    return {
        "key": f"{row['source']}:{row['instance']}:{row['arm']}:{row['variant']}",
        "instance": row["instance"], "repo": row["repo"], "source": row["source"],
        "arm": row["arm"], "hard": row["hard"], "reach_searches": row["reach_searches"],
        "reach_call": reach_call, "calls": len(calls), "turns": n, "cost": cost,
        "cost_per_turn": (cost / n) if cost else None, "call_turns": turns, "fires": fires,
        "queries": {t: {q: qhash(text) for q, text in qs.items() if text}
                    for t, qs in asked.items()},
        "query_text": {qhash(text): text for qs in asked.values() for text in qs.values() if text},
    }  # fmt: skip


def run_sessions() -> list[dict[str, Any]]:
    table = verified()
    out = [session_facts(r, table[r["instance"]]["problem_statement"]) for r in singles()]
    SCRATCH.mkdir(parents=True, exist_ok=True)
    FACTS.write_text(json.dumps(out), encoding="utf-8")
    return out


# ---- retrieval -----------------------------------------------------------------------------------


def work_copy(instance: str) -> Path | None:
    for pattern in WORK_COPIES:
        path = Path(str(pattern).format(id=instance))
        if path.is_dir() and not re.search(r"-r\d+-", path.name):
            return path
    return None


def export(source: Path, dest: Path) -> int:
    """`git archive HEAD` of a work copy into `dest` (regular files only); files written."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    archive = dest.parent / f"{dest.name}.tar"  # a file, not a pipe: no deadlock on the tail
    cmd = ["git", "-c", "core.autocrlf=false", "-C", str(source), "archive", "--format=tar",
           "-o", str(archive), "HEAD"]  # fmt: skip
    subprocess.run(cmd, check=True, timeout=600, stdin=subprocess.DEVNULL)
    written = 0
    with tarfile.open(archive) as tar:
        for member in tar:
            if member.isfile():
                tar.extract(member, dest, filter="data")
                written += 1
    archive.unlink()
    return written


def applies(root: Path, patch: str) -> bool:
    gold = root.parent / f"{root.name}.patch"
    gold.write_text(patch, encoding="utf-8", newline="\n")
    run = subprocess.run(["git", "apply", "--check", str(gold)], cwd=root, capture_output=True,
                         check=False)  # fmt: skip
    gold.unlink()
    return run.returncode == 0


def retrieve_one(instance: str, row: Mapping[str, Any], texts: dict[str, str]) -> dict[str, Any]:
    from sanchopanza.context.repo import chunks
    from sanchopanza.select import index_of

    source = work_copy(instance)
    if source is None:
        return {"instance": instance, "error": "no work copy"}
    root = SNAP / instance
    t0 = time.time()
    exported = export(source, root)
    ok = applies(root, row["patch"])
    t1 = time.time()
    fragments = chunks(root)
    index = index_of(fragments)
    t2 = time.time()
    out: dict[str, Any] = {"instance": instance, "work_copy": str(source.relative_to(CACHE)),
                           "files": exported, "gold_applies": ok, "fragments": len(fragments),
                           "export_s": round(t1 - t0, 2), "index_s": round(t2 - t1, 2),
                           "queries": {}}  # fmt: skip
    asked = {"Q1": row["problem_statement"], **texts}
    for name, text in asked.items():
        t = time.time()
        wide = index.top(text, WIDE)
        elapsed = round(time.time() - t, 3)
        source = [x for x in wide if is_source(fragments[x[0]].key)][:SHORTLIST]
        for suffix, top in (("", wide[:SHORTLIST]), (CODE, source)):
            shown = {k: render([(fragments[i].key, fragments[i].text) for i, _ in top[:k]], text)
                     for k in INJECT_K}  # fmt: skip
            out["queries"][name + suffix] = {
                "keys": [fragments[i].key for i, _ in top], "query_s": elapsed,
                "tokens": {k: round(len(v) / TOKEN_CHARS) for k, v in shown.items()}}  # fmt: skip
    shutil.rmtree(root, ignore_errors=True)
    return out


def _complete(target: Path, texts: Mapping[str, str]) -> bool:
    """Retrieved already, with every query asked now (else the instance is indexed again)."""
    if not target.exists():
        return False
    asked = json.loads(target.read_text(encoding="utf-8")).get("queries", {})
    return all(name in asked for name in texts)


def run_retrieve(only: list[str] | None = None) -> None:
    os.environ["GIT_CEILING_DIRECTORIES"] = str(SNAP)  # never climb to a repository above
    facts = json.loads(FACTS.read_text(encoding="utf-8"))
    table = verified()
    texts: dict[str, dict[str, str]] = defaultdict(dict)
    for f in facts:
        texts[f["instance"]].update(f["query_text"])
    RETRIEVAL.mkdir(parents=True, exist_ok=True)
    for instance in sorted(texts):
        target = RETRIEVAL / f"{instance}.json"
        if (only and instance not in only) or _complete(target, texts[instance]):
            continue
        found = retrieve_one(instance, table[instance], texts[instance])
        target.write_text(json.dumps(found), encoding="utf-8")
        print(instance, found.get("fragments"), found.get("index_s"), found.get("gold_applies"))


def run_latency(instance: str) -> dict[str, Any]:
    """Index build, pickle size and load time for one instance: can a fresh hook process afford
    the index, or must it reuse one built earlier?"""
    from sanchopanza.context.repo import chunks
    from sanchopanza.select import index_of

    os.environ["GIT_CEILING_DIRECTORIES"] = str(SNAP)
    source = work_copy(instance)
    assert source is not None
    root = SNAP / instance
    export(source, root)
    t0 = time.time()
    fragments = chunks(root)
    t1 = time.time()
    index = index_of(fragments)
    t2 = time.time()
    # Timing only: the bytes are made and loaded in this process, never read from disk.
    blob = pickle.dumps((fragments, index), protocol=pickle.HIGHEST_PROTOCOL)
    t3 = time.time()
    pickle.loads(blob)
    t4 = time.time()
    shutil.rmtree(root, ignore_errors=True)
    return {"instance": instance, "fragments": len(fragments), "chunks_s": round(t1 - t0, 2),
            "index_s": round(t2 - t1, 2), "pickle_mb": round(len(blob) / 1e6, 1),
            "dump_s": round(t3 - t2, 2), "load_s": round(t4 - t3, 2)}  # fmt: skip


# ---- report --------------------------------------------------------------------------------------


def rate(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.0f} %)" if d else "0/0"


def query_name(fact: Mapping[str, Any], trigger: str, query: str) -> str | None:
    """The retrieval key of `query` ("Q1", "Q3", "Q3+code"...) at `trigger`'s fire: Q1 is the
    same at every fire, and at the prompt every query is Q1."""
    base, suffix = (query[: -len(CODE)], CODE) if query.endswith(CODE) else (query, "")
    if base == "Q1" or fact["fires"][trigger] in (None, 0):
        return "Q1" + suffix
    asked = fact["queries"].get(trigger, {}).get(base)
    return asked + suffix if asked else None


def evaluated_rows(facts: list[dict[str, Any]], retrieved: dict[str, dict[str, Any]],
                   lines: dict[str, dict[str, set[int]]], trigger: str, query: str, k: int
                   ) -> Iterator[dict[str, Any]]:  # fmt: skip
    """Each session with its retrieval at `trigger` (Q1 is the same at every fire)."""
    for f in facts:
        got = retrieved.get(f["instance"])
        if not got or "queries" not in got or f["cost_per_turn"] is None:
            continue
        fire = f["fires"][trigger]
        found = got["queries"].get(query_name(f, trigger, query) or "")
        h = hits(found["keys"], lines[f["instance"]]) if found else {}
        yield {**f, "hits": h, "tokens": found["tokens"][str(k)] if found else 0,
               "value": value(fire, f["reach_call"], f["call_turns"],
                              bool(h.get(f"any@{k}")))}  # fmt: skip


def trigger_table(rows: list[dict[str, Any]], k: int) -> dict[str, Any]:
    hard = [r for r in rows if r["hard"]]
    easy = [r for r in rows if not r["hard"]]
    fired = [r for r in rows if r["value"]["fired"]]
    early = [r for r in fired if r["value"]["before_reach"]]
    hard_early = [r for r in early if r["hard"]]
    useful = [r for r in hard_early if r["value"]["hit"]]
    saved = [r["value"]["saved_turns"] for r in useful if "saved_turns" in r["value"]]
    calls = [r["value"]["saved_calls"] for r in useful if "saved_calls" in r["value"]]
    tokens = statistics.median([r["tokens"] for r in fired]) if fired else 0
    return {
        "fires_hard": rate(sum(r["value"]["fired"] for r in hard), len(hard)),
        "fires_easy": rate(sum(r["value"]["fired"] for r in easy), len(easy)),
        "fires_before_gold_hard": len(hard_early),
        "fires_before_gold_easy": sum(not r["hard"] for r in early),
        "precision_before_gold": rate(len(hard_early), len(early)),
        f"hard_before_gold_with_gold_file_in_top{k}": rate(len(useful), len(hard_early)),
        "hard_never_reached_shown_gold": sum(r["reach_call"] is None for r in useful),
        "saved_turns_median": statistics.median(saved) if saved else None,
        "saved_turns_total": sum(saved),
        "saved_calls_total": sum(calls),
        "easy_saved_turns_total": sum(
            r["value"].get("saved_turns", 0) for r in early if not r["hard"]
        ),  # fmt: skip
        "injected_tokens_median": tokens,
        "ev_follow1_detour05": expected_value(rows, 1.0, 0.5, tokens),
        "ev_follow05_detour05": expected_value(rows, 0.5, 0.5, tokens),
        "ev_follow1_detour05_hard_only": expected_value(hard, 1.0, 0.5, tokens),
    }


def retrieval_table(facts: list[dict[str, Any]], retrieved: dict[str, dict[str, Any]],
                    lines: dict[str, dict[str, set[int]]]) -> dict[str, Any]:  # fmt: skip
    """Q1 per session (hard / easy) and Q2-Q4 against Q1 at trigger A's and B5's fires in hard
    sessions; each also with source fragments only (`+code`)."""
    out: dict[str, Any] = {}
    metrics = [f"any@{k}" for k in KS] + [f"hunk@{k}" for k in KS] + ["short60"]

    def got(f: Mapping[str, Any], name: str) -> dict[str, bool]:
        return hits(retrieved[f["instance"]]["queries"][name]["keys"], lines[f["instance"]])

    for suffix in ("", CODE):
        for label, keep in (("hard", True), ("easy", False)):
            group = [f for f in facts if f["hard"] is keep and f["instance"] in retrieved]
            hs = [got(f, "Q1" + suffix) for f in group]
            row = {m: rate(sum(h[m] for h in hs), len(hs)) for m in metrics}
            for k in KS:  # not measured: the retrieval run's judge/ceiling ratio, applied
                share = sum(h["short60"] for h in hs) * JUDGE_OVER_CEILING[k] / max(1, len(hs))
                row[f"judged_any@{k}_extrapolated"] = round(share, 3)
            out[f"Q1{suffix}_{label}_sessions"] = row
        for trigger in ("A", "B5", "R4"):
            for query in ("Q2", "Q3", "Q4"):
                group = [f for f in facts if f["hard"] and f["fires"][trigger]
                         and f["queries"].get(trigger, {}).get(query)
                         and f["instance"] in retrieved]  # fmt: skip
                hs = [got(f, f["queries"][trigger][query] + suffix) for f in group]
                q1 = [got(f, "Q1" + suffix) for f in group]
                out[f"{query}{suffix}_at_{trigger}_hard"] = {
                    "n": len(hs), **{m: f"{sum(h[m] for h in hs)} vs Q1 {sum(h[m] for h in q1)}"
                                     for m in metrics}}  # fmt: skip
    return out


def recorded_finds() -> list[dict[str, Any]]:
    """Every find_in_repo call in the single sessions (the agent's own query, judged by Jev
    where a key was set): did its keys hold a gold file / a changed gold line?"""
    table = verified()
    out = []
    for r in singles():
        if not r["finds_total"]:
            continue
        _, calls = stream_calls(CACHE / r["stream"])
        lines = gold_lines(table[r["instance"]]["patch"])
        for n, c in enumerate(calls, 1):
            if c.name.endswith("find_in_repo"):
                text = c.result if isinstance(c.result, str) else json.dumps(c.result)
                keys = list(dict.fromkeys(re.findall(r"\[\d+\] (\S+:\d+-\d+)", text)))
                out.append({"session": f"{r['source']}:{r['instance']}:{r['arm']}",
                            "hard": r["hard"], "call": n, "reach_call": r["read_at"],
                            "judged": "judged in context" in text, "keys": len(keys),
                            **hits(keys, lines)})  # fmt: skip
    return out


def run_report() -> dict[str, Any]:
    facts = json.loads(FACTS.read_text(encoding="utf-8"))
    table = verified()
    retrieved = {}
    for path in RETRIEVAL.glob("*.json"):
        got = json.loads(path.read_text(encoding="utf-8"))
        if got.get("gold_applies"):
            retrieved[got["instance"]] = got
    lines = {i: gold_lines(table[i]["patch"]) for i in {f["instance"] for f in facts}}
    hard = [f for f in facts if f["hard"]]
    covered = [f for f in hard if f["instance"] in retrieved]
    triggers: dict[str, Any] = {}
    for trigger in TRIGGER_NAMES:
        asked = ("Q1", "Q3") if trigger in TRIGGERS else ("Q1",)
        for query in (q + suffix for q in asked for suffix in ("", CODE)):
            for k in INJECT_K:
                rows = list(evaluated_rows(facts, retrieved, lines, trigger, query, k))
                triggers[f"{trigger} {TRIGGER_NAMES[trigger]} | {query} | top{k}"] = (
                    trigger_table(rows, k))  # fmt: skip
    per_turn = [f["cost_per_turn"] for f in facts if f["cost_per_turn"]]
    retrievals = list(retrieved.values())
    report = {
        "rule": "see evaluate.py docstring",
        "coverage": {
            "single_sessions": len(facts), "hard_sessions": len(hard),
            "hard_sessions_evaluated": len(covered),
            "instances": len({f["instance"] for f in facts}),
            "instances_evaluated": len(retrieved),
            "not_evaluated": sorted({f["instance"] for f in facts} - set(retrieved)),
        },
        "cost_per_turn_usd": {"median": round(statistics.median(per_turn), 5),
                              "mean": round(statistics.mean(per_turn), 5)},
        "index": {"fragments_median": statistics.median(r["fragments"] for r in retrievals),
                  "index_s_median": statistics.median(r["index_s"] for r in retrievals),
                  "index_s_max": max(r["index_s"] for r in retrievals),
                  "query_s_max": max(q["query_s"] for r in retrievals
                                     for q in r["queries"].values())},
        "hint_skipped_over_3000_files": sum(r["files"] > 3000 for r in retrievals),
        "retrieval": retrieval_table(facts, retrieved, lines),
        "triggers": triggers,
        "recorded_finds": recorded_finds(),
    }  # fmt: skip
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


# ---- real sessions (no gold) ---------------------------------------------------------------------


def _relative(calls: list[Call], cwd: str) -> list[Call]:
    """Calls with file paths made relative to the session's directory, as the hook would see
    them against the project."""
    root = cwd.replace(chr(92), "/").rstrip("/").lower() + "/"
    out = []
    for c in calls:
        path = str(c.input.get("file_path") or "").replace(chr(92), "/")
        if path.lower().startswith(root):
            c = Call(c.name, {**c.input, "file_path": path[len(root) :]}, c.result, c.error)
        out.append(c)
    return out


def real_fires(turns: list[dict[str, Any]], rule: Rule) -> dict[str, Any] | None:
    """`real.session`'s reading for one rule: the turn it lands in, and whether that turn was
    hard (5+ searches before its edit target's Read) and the fire came before that Read."""
    from benchmarks.find_need.real import HARD_SEARCHES, turn_need

    flat, spans = [], []
    for t in turns:
        calls = _relative(t["calls"], str(t.get("cwd") or ""))
        spans.append((len(flat), len(calls), turn_need(calls)))
        flat += calls
    fire = rule(flat)
    if fire is None:
        return None
    for offset, n, need in spans:
        if offset < fire.call <= offset + n:
            hard = need.get("searches") is not None and need["searches"] >= HARD_SEARCHES
            return {"hard_turn": hard, "useful": hard and fire.call - offset < need["read_at"]}
    return None


def run_real() -> dict[str, Any]:
    """Trigger fires in real Claude Code sessions with no gold (the owner's and SWE-chat's):
    how often each live rule would inject, and how often into a hard turn before its target."""
    from benchmarks.find_need.real import SETS
    from benchmarks.find_need.replay import transcript_turns

    rules = {k: TRIGGERS[k] for k in ("A", "B4", "B5", "R3", "R4", "R5")}
    out: dict[str, Any] = {}
    for name, folder in SETS.items():
        counts = {k: {"fires": 0, "in_hard_turn": 0, "useful": 0} for k in rules}
        sessions = 0
        for path in sorted(folder.glob("*.jsonl")):
            turns = transcript_turns(path)
            if not turns:
                continue
            sessions += 1
            for k, rule in rules.items():
                got = real_fires(turns, rule)
                if got:
                    counts[k]["fires"] += 1
                    counts[k]["in_hard_turn"] += got["hard_turn"]
                    counts[k]["useful"] += got["useful"]
        out[name] = {"sessions": sessions, **counts}
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("what", choices=("sessions", "retrieve", "report", "latency", "real"))
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--instance", default="django__django-14007")
    args = parser.parse_args(argv)
    if args.what == "sessions":
        print(len(run_sessions()), "sessions")
    elif args.what == "retrieve":
        run_retrieve(args.only)
    elif args.what == "real":
        found = run_real()
        (SCRATCH / "real-fires.json").write_text(json.dumps(found, indent=1), encoding="utf-8")
        print(json.dumps(found, indent=1))
    elif args.what == "latency":
        print(json.dumps(run_latency(args.instance)))
    else:
        report = run_report()
        print(json.dumps({k: report[k] for k in ("coverage", "cost_per_turn_usd", "index")},
                         indent=1))  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
