"""Which window should find_auto watch? R4 (the 4th search before any source Read or edit) closed
early in 6 of 10 sessions of the find_auto probe because the agent Read a wrong source file. This
replays alternative windows on the recorded sessions. Offline and free: no model, no Jev call (the
judged rate uses only the recorded answers in `answers.jsonl`), no Docker.

    .venv/Scripts/python.exe -m benchmarks.find_auto.windows fires      # rules per session
    .venv/Scripts/python.exe -m benchmarks.find_auto.windows retrieve   # BM25 at each new fire
    .venv/Scripts/python.exe -m benchmarks.find_auto.windows report     # -> windows-table.json

Windows, each fires once per session, all stepping the live hook's `harness.find_auto.step`:
  W1-N  the N-th search before the first edit of an existing source file (Reads do not close).
  W2-N  the N-th search since the last source Read followed by an edit of that file within K
        calls (a wrong Read does not reset the count); an edit closes. Live it needs a K-call wait.
  W3-N  the N-th search before the first Read of a source file the agent later edits, or that
        edit. NOT live-computable (it knows the future): an upper bound only.
  W4-M  R4 as today, or, once R4's window closed on a Read without firing, the M-th search of the
        session before any edit.
  W5-N  (added) the N-th search in a row with no source Read between them; an edit closes.

Sessions: the 179 Haiku singles `evaluate.py` uses, and the 20 sessions of the need and find_auto
probes (`adopt/dev-need`, `adopt/dev-auto`; phase D's `singles-d` is never read). The ranking at a
fire is evaluate.py's free source-only one (`+code`) on the issue plus the session's search words
(Q3); snapshots come from the same work copies (`evaluate.work_copy`). Real sessions with no gold
(evaluate's stage `real`) give the fires outside SWE-bench.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from benchmarks.find_need.need import gold_files
from benchmarks.find_need.replay import Call, Fire, reach, source_edits, stream_calls

from sanchopanza.harness.find_auto import NTH, relative
from sanchopanza.harness.find_auto import State as AutoState
from sanchopanza.harness.find_auto import step as auto_step

from .evaluate import (
    CACHE,
    RETRIEVAL,
    SCRATCH,
    SHORTLIST,
    SNAP,
    WIDE,
    call_turns,
    export,
    gold_lines,
    hits,
    is_source,
    qhash,
    queries,
    real_fires,
    repo_path,
    singles,
    value,
    verified,
    work_copy,
)

HERE = Path(__file__).resolve().parent
OUT = HERE / "windows-table.json"
WORK = SCRATCH / "windows"
FACTS = WORK / "facts.json"
RANKED = WORK / "retrieval"
PROBES = {"need": CACHE / "adopt" / "dev-need", "auto": CACHE / "adopt" / "dev-auto"}
K_EDIT = 3
HARD_SEARCHES = 5
SHOWN = 5
DETOUR = 0.5  # turns lost to a fire that shows no gold (evaluate.expected_value's detour)


# ---- pure: the windows ---------------------------------------------------------------------------


def _path(call: Call) -> str:
    raw = str(call.input.get("file_path") or call.input.get("notebook_path") or "")
    return repo_path(raw) if raw else ""


def _arguments(call: Call) -> Mapping[str, Any]:
    path = _path(call)
    return {**call.input, "file_path": path} if path else call.input


def _step(state: AutoState, call: Call, reads_close: bool) -> AutoState:
    """The live hook's step; with `reads_close=False` a source Read is remembered as read (for the
    Write rule) instead of closing the window."""
    after, _ = auto_step(state, call.name, _arguments(call), failed=call.error)
    if after.closed == "read" and not reads_close:
        return replace(state, read=state.read | {relative(_path(call), "")})
    return after


def _edited(calls: list[Call]) -> dict[int, str]:
    """Index -> normalised path of each edit of an existing non-test, non-doc file."""
    return {i: relative(_path(calls[i]), "") for i in source_edits(calls)}


def nth_before_edit(calls: list[Call], nth: int) -> Fire | None:
    """W1: the nth search while no existing source file has been edited; Reads do not close."""
    state = AutoState()
    for i, call in enumerate(calls):
        before = state.searches
        state = _step(state, call, reads_close=False)
        if state.closed:
            return None
        if state.searches == nth and before < nth:
            return Fire(i + 1, nth, "W1")
    return None


def nth_since_kept_read(calls: list[Call], nth: int, k: int = K_EDIT) -> Fire | None:
    """W2: the nth search since the last source Read that was followed by an edit of the same
    file within `k` calls; a Read the agent does not act on keeps the count."""
    edits = _edited(calls)
    state, since = AutoState(), 0
    for i, call in enumerate(calls):
        before = state.searches
        state = _step(state, call, reads_close=False)
        if state.closed:
            return None
        if call.name == "Read" and is_source(f"{_path(call)}:1-1"):
            target = relative(_path(call), "")
            if any(edits.get(j) == target for j in range(i + 1, i + 1 + k)):
                since = 0
        since += state.searches - before
        if state.searches > before and since == nth:
            return Fire(i + 1, state.searches, "W2")
    return None


def nth_before_edited_read(calls: list[Call], nth: int) -> Fire | None:
    """W3 (oracle, not live): the nth search before the first Read of a source file the session
    edits later, or that edit."""
    targets = set(_edited(calls).values())
    state = AutoState()
    for i, call in enumerate(calls):
        if call.name == "Read" and relative(_path(call), "") in targets:
            return None
        before = state.searches
        state = _step(state, call, reads_close=False)
        if state.closed:
            return None
        if state.searches == nth and before < nth:
            return Fire(i + 1, nth, "W3")
    return None


def r4_or_mth(calls: list[Call], mth: int, nth: int = NTH) -> Fire | None:
    """W4: R4; once R4's window closed on a source Read without firing, the mth search of the
    session while no existing source file has been edited."""
    state, reads_close = AutoState(), True
    for i, call in enumerate(calls):
        before = state.searches
        after = _step(state, call, reads_close=reads_close)
        if after.closed == "read":
            reads_close = False
            after = _step(state, call, reads_close=False)
        state = after
        if state.closed:
            return None
        goal = nth if reads_close else mth
        if state.searches == goal and before < goal:
            return Fire(i + 1, goal, "R4" if reads_close else "W4")
    return None


def nth_since_any_read(calls: list[Call], nth: int) -> Fire | None:
    """W5 (added): the nth search since the last source Read, i.e. nth searches in a row with no
    source file opened between them; an edit closes. R4 is its first stretch at nth=4."""
    state, since = AutoState(), 0
    for i, call in enumerate(calls):
        before = state.searches
        state = _step(state, call, reads_close=False)
        if state.closed:
            return None
        if call.name == "Read" and is_source(f"{_path(call)}:1-1"):
            since = 0
        since += state.searches - before
        if state.searches > before and since == nth:
            return Fire(i + 1, state.searches, "W5")
    return None


def r4(calls: list[Call]) -> Fire | None:
    """R4 as shipped: the nth search while no source file has been Read or edited."""
    state = AutoState()
    for i, call in enumerate(calls):
        before = state.searches
        state = _step(state, call, reads_close=True)
        if state.closed:
            return None
        if state.searches == NTH and before < NTH:
            return Fire(i + 1, NTH, "R4")
    return None


Rule = Callable[[list[Call]], "Fire | None"]
RULES: dict[str, Rule] = {
    "R4 (today)": r4,
    "W1-4": lambda c: nth_before_edit(c, 4),
    "W1-5": lambda c: nth_before_edit(c, 5),
    "W1-6": lambda c: nth_before_edit(c, 6),
    "W2-4": lambda c: nth_since_kept_read(c, 4),
    "W2-5": lambda c: nth_since_kept_read(c, 5),
    "W2-6": lambda c: nth_since_kept_read(c, 6),
    "W3-4 (oracle)": lambda c: nth_before_edited_read(c, 4),
    "W3-5 (oracle)": lambda c: nth_before_edited_read(c, 5),
    "W3-6 (oracle)": lambda c: nth_before_edited_read(c, 6),
    "W4-5": lambda c: r4_or_mth(c, 5),
    "W4-6": lambda c: r4_or_mth(c, 6),
    "W5-4": lambda c: nth_since_any_read(c, 4),
    "W5-5": lambda c: nth_since_any_read(c, 5),
    "W5-6": lambda c: nth_since_any_read(c, 6),
    "W4-8": lambda c: r4_or_mth(c, 8),
    "W4-10": lambda c: r4_or_mth(c, 10),
}


# ---- sessions ------------------------------------------------------------------------------------


def _session(key: str, stream: Path, instance: str, statement: str, patch: str, group: str,
             known: Mapping[str, Any] | None = None) -> dict[str, Any]:  # fmt: skip
    """One session's reach and fires; `known` is the need table's row (its hard/reach win)."""
    _, calls = stream_calls(stream)
    turns, result = call_turns(stream)
    got = reach(calls, gold_files(patch))
    searches = got["read_searches"] if got["read_searches"] is not None else got["view_searches"]
    if known is not None:
        searches = known["reach_searches"]
    fires = {}
    for name, rule in RULES.items():
        fire = rule(calls)
        if fire is not None:
            asked = queries(statement, calls, fire.call)
            fires[name] = {"call": fire.call, "search": fire.search,
                           "query": asked["Q3"] or statement}  # fmt: skip
    return {"key": key, "group": group, "instance": instance, "stream": str(stream),
            "calls": len(calls), "turns": result.get("turns"), "call_turns": turns,
            "read_at": got["read_at"],
            "reach_call": (known["read_at"] or known["view_at"]) if known else
            (got["read_at"] or got["view_at"]),
            "reach_searches": searches,
            "hard": searches is None or searches >= HARD_SEARCHES, "fires": fires,
            "reads": [[i + 1, relative(_path(c), "")] for i, c in enumerate(calls)
                      if c.name == "Read" and _path(c)]}  # fmt: skip


def run_fires() -> list[dict[str, Any]]:
    table = verified()
    out = []
    for r in singles():
        row = table[r["instance"]]
        out.append(_session(f"{r['source']}:{r['instance']}:{r['arm']}:{r['variant']}",
                            CACHE / r["stream"], r["instance"], row["problem_statement"],
                            row["patch"], "singles", r))  # fmt: skip
    for group, folder in PROBES.items():
        for stream in sorted(folder.glob("*/S/stream-1.jsonl")):
            instance = stream.parent.parent.name
            row = table[instance]
            out.append(_session(f"probe-{group}:{instance}", stream, instance,
                                row["problem_statement"], row["patch"], f"probe-{group}"))
    WORK.mkdir(parents=True, exist_ok=True)
    FACTS.write_text(json.dumps(out), encoding="utf-8")
    return out


# ---- retrieval -----------------------------------------------------------------------------------


def _known(instance: str) -> dict[str, list[str]]:
    """Source-only top-60 keys by query hash, from evaluate.py's retrieval and this one's."""
    out: dict[str, list[str]] = {}
    old = RETRIEVAL / f"{instance}.json"
    if old.exists():
        for name, got in json.loads(old.read_text(encoding="utf-8"))["queries"].items():
            if name.endswith("+code") and not name.startswith("Q1"):
                out[name.removesuffix("+code")] = got["keys"]
    mine = RANKED / f"{instance}.json"
    if mine.exists():
        out.update(json.loads(mine.read_text(encoding="utf-8")))
    return out


def run_retrieve() -> None:
    from sanchopanza.context.repo import chunks
    from sanchopanza.select import index_of

    os.environ["GIT_CEILING_DIRECTORIES"] = str(SNAP)
    facts = json.loads(FACTS.read_text(encoding="utf-8"))
    wanted: dict[str, dict[str, str]] = {}
    for f in facts:
        for fire in f["fires"].values():
            wanted.setdefault(f["instance"], {})[qhash(fire["query"])] = fire["query"]
    RANKED.mkdir(parents=True, exist_ok=True)
    for instance in sorted(wanted):
        known = _known(instance)
        missing = {h: t for h, t in wanted[instance].items() if h not in known}
        if not missing:
            continue
        source = work_copy(instance)
        if source is None:
            print(instance, "no work copy")
            continue
        root = SNAP / instance
        export(source, root)
        fragments = chunks(root)
        index = index_of(fragments)
        target = RANKED / f"{instance}.json"
        mine = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
        for h, text in missing.items():
            wide = index.top(text, WIDE)
            mine[h] = [fragments[i].key for i, _ in wide if is_source(fragments[i].key)][:SHORTLIST]
        target.write_text(json.dumps(mine), encoding="utf-8")
        shutil.rmtree(root, ignore_errors=True)
        print(instance, len(missing), "queries", flush=True)


# ---- judged, recorded answers only ---------------------------------------------------------------


async def _judged(instance: str, query: str, keys: list[str], decider: Any) -> list[str] | None:
    """Kept fragments by p, then the rest (judge.judge_one's ranking), when every answer is
    recorded; None otherwise. The decider never calls out (no live inner)."""
    from sanchopanza import Squire
    from sanchopanza.context.repo import PURPOSE
    from sanchopanza.policy import Thresholds

    from .judge import fragments

    work = work_copy(instance)
    if work is None:
        return None
    found = fragments(work, keys)
    shortlist = [found[k] for k in keys if k in found]
    squire = Squire(decider, thresholds=Thresholds(max_usd=0.05, max_decisions=50))
    refused = decider.refused
    verdicts = await squire.triage_many(purpose=PURPOSE.format(query=query),
                                        pages=[(c.title, c.text) for c in shortlist])  # fmt: skip
    if decider.refused != refused:
        return None
    kept = [(n, c.key, p) for n, (c, (keep, p)) in enumerate(zip(shortlist, verdicts, strict=False))
            if keep]  # fmt: skip
    kept.sort(key=lambda x: (-(x[2] if x[2] is not None else 0.5), x[0]))
    return [k for _, k, _ in kept]


# ---- gates: what is shown decides whether to show it --------------------------------------------

GATES = ("top1_unread", "two_unread", "any_unread")


def gates(keys: list[str], read: set[str]) -> dict[str, bool]:
    """Whether a fire still shows at the fire, by what the top 5 holds that the session already
    Read: `top1_unread` the first place is a file not Read yet; `two_unread` at least two of the
    five files are unread; `any_unread` at least one is (live: the hook sees the Reads)."""
    files = list(dict.fromkeys(k.rsplit(":", 1)[0].lower() for k in keys[:SHOWN]))
    unread = [f for f in files if f not in read]
    return {"top1_unread": bool(files) and files[0] not in read,
            "two_unread": len(unread) >= 2, "any_unread": bool(unread)}  # fmt: skip


# ---- report --------------------------------------------------------------------------------------


def _rate(n: int, d: int) -> str:
    return f"{n}/{d}" if d else "0/0"


def score_rule(rows: list[dict[str, Any]], name: str) -> dict[str, Any]:
    hard = [r for r in rows if r["hard"]]
    easy = [r for r in rows if not r["hard"]]
    fired = [r for r in rows if name in r["fires"]]
    early = [r for r in fired if r["value"][name]["before_reach"]]
    hard_early = [r for r in early if r["hard"]]
    hit = [r for r in hard_early if r["value"][name]["hit"]]
    judged = [r for r in hard_early if r["judged"].get(name) is not None]
    calls = [r["value"][name].get("saved_calls", 0) for r in hit]
    turns = [r["value"][name].get("saved_turns", 0) for r in hit]
    gated = {g: {"hard_before_gold": sum(r["value"][name]["gates"].get(g, False)
                                         for r in hard_early),
                 "hits_kept": sum(r["value"][name]["gates"].get(g, False) for r in hit),
                 "easy_before_gold": sum(r["value"][name]["gates"].get(g, False)
                                         for r in early if not r["hard"]),
                 "after_gold": sum(r["value"][name]["gates"].get(g, False)
                                   for r in fired if r not in early)} for g in GATES}
    def net(keep: Callable[[dict[str, Any]], bool]) -> float:
        """Saved turns if every shown gold is followed, minus DETOUR turns for each fire that
        shows no gold before it was reached and for each fire after it (an assumption)."""
        saved = sum(r["value"][name].get("saved_turns", 0) for r in hit if keep(r))
        misses = sum(1 for r in early if keep(r) and not r["value"][name]["hit"])
        late = sum(1 for r in fired if r not in early and keep(r))
        return round(saved - DETOUR * (misses + late), 1)

    for g in GATES:
        gated[g]["net_turns"] = net(lambda r, g=g: r["value"][name]["gates"].get(g, False))
    return {
        "net_turns": net(lambda r: True),
        "gated": gated,
        "fires_hard": _rate(sum(name in r["fires"] for r in hard), len(hard)),
        "fires_easy": _rate(sum(name in r["fires"] for r in easy), len(easy)),
        "hard_before_gold": len(hard_early),
        "easy_before_gold": len(early) - len(hard_early),
        "fires_after_gold": len(fired) - len(early),
        "free_gold_at5_hard_before_gold": _rate(len(hit), len(hard_early)),
        "judged_gold_at5_recorded": _rate(sum(r["judged"][name] for r in judged), len(judged)),
        "saved_calls_total": sum(calls),
        "saved_turns_total": sum(turns),
        "fire_search_median": sorted(r["fires"][name]["search"] for r in fired)[len(fired) // 2]
        if fired else None,
    }  # fmt: skip


def _evaluated(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from .judge import ANSWERS, CappedReplay

    decider = CappedReplay(None, 0.0)
    assert ANSWERS.exists()
    table = verified()
    rows = []
    for f in facts:
        lines = gold_lines(table[f["instance"]]["patch"])
        known = _known(f["instance"])
        v, judged = {}, {}
        for name, fire in f["fires"].items():
            keys = known.get(qhash(fire["query"]), [])
            h = hits(keys, lines) if keys else {}
            read = {p for n, p in f["reads"] if n <= fire["call"]}
            v[name] = {**value(fire["call"], f["reach_call"], f["call_turns"],
                               bool(h.get(f"any@{SHOWN}"))), "hunk": bool(h.get(f"hunk@{SHOWN}")),
                       "gates": gates(keys, read) if keys else {}}
            if f["hard"] and v[name]["before_reach"] and keys:
                got = asyncio.run(_judged(f["instance"], fire["query"], keys, decider))
                judged[name] = None if got is None else hits(got, lines)[f"any@{SHOWN}"]
        rows.append({**f, "value": v, "judged": judged})
    return rows


def run_real() -> dict[str, Any]:
    from benchmarks.find_need.real import SETS
    from benchmarks.find_need.replay import transcript_turns

    out: dict[str, Any] = {}
    for set_name, folder in SETS.items():
        counts = {k: {"fires": 0, "in_hard_turn": 0, "useful": 0} for k in RULES}
        sessions = 0
        for path in sorted(folder.glob("*.jsonl")):
            turns = transcript_turns(path)
            if not turns:
                continue
            sessions += 1
            for k, rule in RULES.items():
                got = real_fires(turns, rule)
                if got:
                    counts[k]["fires"] += 1
                    counts[k]["in_hard_turn"] += got["hard_turn"]
                    counts[k]["useful"] += got["useful"]
        out[set_name] = {"sessions": sessions, **counts}
    return out


def probe_detail(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per probe session: gold Read call, and each rule's fire call, before the gold, top-5 hit."""
    out = []
    for r in rows:
        if not r["group"].startswith("probe"):
            continue
        out.append({"session": r["key"], "hard": r["hard"], "read_at": r["read_at"],
                    "reach_searches": r["reach_searches"],
                    **{n: (f"call {r['fires'][n]['call']} (search {r['fires'][n]['search']})"
                           f"{' before' if r['value'][n]['before_reach'] else ' after'} gold"
                           f"{', top5 hit' if r['value'][n]['hit'] else ''}")
                       for n in RULES if n in r["fires"]}})  # fmt: skip
    return out


def run_report() -> dict[str, Any]:
    rows = _evaluated(json.loads(FACTS.read_text(encoding="utf-8")))
    groups = {"singles": [r for r in rows if r["group"] == "singles"],
              "probe-need": [r for r in rows if r["group"] == "probe-need"],
              "probe-auto": [r for r in rows if r["group"] == "probe-auto"]}  # fmt: skip
    report = {
        "rules": {name: (fn.__doc__ or "").strip() for name, fn in
                  (("R4", r4), ("W1", nth_before_edit), ("W2", nth_since_kept_read),
                   ("W3", nth_before_edited_read), ("W4", r4_or_mth),
                   ("W5", nth_since_any_read))},
        "sets": {g: {"sessions": len(rs), "hard": sum(r["hard"] for r in rs),
                     **{n: score_rule(rs, n) for n in RULES}} for g, rs in groups.items()},
        "probe_sessions": probe_detail(rows),
        "real": run_real(),
    }  # fmt: skip
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("what", choices=("fires", "retrieve", "report"))
    args = parser.parse_args(argv)
    if args.what == "fires":
        print(len(run_fires()), "sessions")
    elif args.what == "retrieve":
        run_retrieve()
    else:
        print(json.dumps(run_report()["sets"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
