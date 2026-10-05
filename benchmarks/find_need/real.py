"""Where else need for find could come from: real Claude Code sessions with no gold patch.

Two local sets: the owner's own transcripts (`memory-real/transcripts`) and SWE-chat's 300 public
Claude Code sessions (`candor-external/swe-chat/transcripts`). Nothing of their text leaves this
process: the result is counts, and per-session ids only in the scratch folder.

A turn is a typed request and the main-thread calls until the next one. Without a gold patch the
target of a turn is the first existing non-test file it edits (`replay.source_edits`); its need is
the searches before the first Read of that target in the same turn (turns whose target was read in
an earlier turn, or never read, are counted apart). A request is behaviour-described when it has
no file path and no code token (`adopt_dev.behaviour_set.tokens`: backticks, CamelCase,
snake_case, dotted names). The nudge rules replay over the whole session (the hook keeps its state
per session); a fire is useful when it lands in a hard turn before that turn's target Read.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from benchmarks.adopt_dev.behaviour_set import tokens

from .replay import Call, is_search, norm, replay_empty, replay_live, source_edits, transcript_turns

CACHE = Path.home() / ".cache" / "sanchopanza"
SETS = {
    "memory-real": CACHE / "memory-real" / "transcripts",
    "swe-chat": CACHE / "candor-external" / "swe-chat" / "transcripts",
}
SCRATCH = CACHE / "find-need"
HARD_SEARCHES = 5
FILE_PATH = re.compile(r"[\w./\\-]+\.(?:py|ts|tsx|js|jsx|go|rs|java|rb|php|cs|cpp|c|h|kt|swift|vue|"
                       r"svelte|sql|yaml|yml|toml|json|sh|md)\b", re.IGNORECASE)  # fmt: skip
RULES = {"live": replay_live, "new": lambda c: replay_empty(c, 2, "source"),
         "new8": lambda c: replay_empty(c, 2, "source", 8)}  # fmt: skip


def names_code(prompt: str) -> bool:
    return bool(FILE_PATH.search(prompt) or tokens(prompt))


def turn_need(calls: list[Call]) -> dict[str, Any]:
    """The turn's target (first existing non-test file edited) and the searches before its Read."""
    edits = source_edits(calls)
    if not edits:
        return {"edits": False}
    target = norm(str(calls[edits[0]].input.get("file_path", "")))
    searches = 0
    for n, call in enumerate(calls[: edits[0]]):
        if call.name == "Read" and norm(str(call.input.get("file_path", ""))) == target:
            return {"edits": True, "read_at": n + 1, "searches": searches}
        searches += is_search(call.name, call.input)
    return {"edits": True, "read_at": None, "searches": None}


def session(path: Path) -> dict[str, Any] | None:
    turns = transcript_turns(path)
    if not turns:
        return None
    rows, offset, flat = [], 0, []
    for t in turns:
        need = turn_need(t["calls"])
        hard = need.get("searches") is not None and need["searches"] >= HARD_SEARCHES
        total = sum(is_search(c.name, c.input) for c in t["calls"])
        rows.append({**need, "offset": offset, "n": len(t["calls"]), "hard": hard,
                     "behaviour": not names_code(t["prompt"]),
                     "searches_total": total})  # fmt: skip
        offset += len(t["calls"])
        flat += t["calls"]
    fires = {}
    for name, rule in RULES.items():
        fire = rule(flat)
        if fire is None:
            fires[name] = None
            continue
        turn = next(r for r in rows if r["offset"] < fire.call <= r["offset"] + r["n"])
        local = fire.call - turn["offset"]
        fires[name] = {"turn": rows.index(turn) + 1, "hard_turn": turn["hard"],
                       "useful": turn["hard"] and local < (turn.get("read_at") or 0)}  # fmt: skip
    return {"id": path.stem, "model": turns[0]["model"], "turns": rows, "fires": fires,
            "project": Path(str(turns[0].get("cwd") or "")).name}  # fmt: skip


def sessions(folder: Path) -> Iterator[dict[str, Any]]:
    for path in sorted(folder.glob("*.jsonl")):
        found = session(path)
        if found is not None:
            yield found


def summarise(found: list[dict[str, Any]]) -> dict[str, Any]:
    turns = [t for s in found for t in s["turns"]]
    edit = [t for t in turns if t["edits"]]
    measured = [t for t in edit if t["searches"] is not None]
    hard = [t for t in measured if t["hard"]]
    out: dict[str, Any] = {
        "sessions": len(found),
        "turns": len(turns),
        "turns_with_source_edit": len(edit),
        "turns_target_read_in_turn": len(measured),
        "hard_turns": len(hard),
        "hard_turns_behaviour_described": sum(t["behaviour"] for t in hard),
        "behaviour_described_turns_with_edit": sum(t["behaviour"] for t in edit),
        "sessions_with_a_hard_turn": sum(any(t["hard"] for t in s["turns"]) for s in found),
        "sessions_first_edit_turn_hard": sum(
            next((t["hard"] for t in s["turns"] if t["edits"]), False) for s in found
        ),
        "models": Counter(s["model"] for s in found).most_common(6),
    }
    for name in RULES:
        fired = [s["fires"][name] for s in found if s["fires"][name]]
        out[f"rule_{name}"] = {"fires": len(fired),
                               "in_hard_turn": sum(f["hard_turn"] for f in fired),
                               "useful": sum(f["useful"] for f in fired)}  # fmt: skip
    return out


def run_real() -> dict[str, Any]:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    report = {}
    for name, folder in SETS.items():
        found = list(sessions(folder))
        (SCRATCH / f"real-{name}.json").write_text(json.dumps(found), encoding="utf-8")
        report[name] = summarise(found)
        if name == "memory-real":
            hard = Counter(s["project"] for s in found for t in s["turns"] if t["hard"])
            report[name]["hard_turns_by_project_top"] = hard.most_common(8)
    return report
