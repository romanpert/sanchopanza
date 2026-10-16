"""F2's S arms replayed through memory's C8 code, free (docs/results/2026-10-16-memory-c8-replay).

For each S arm of the F2 night (docs/results/2026-10-16-memory-f2), from the run root it left
on disk (`f2-sonnet/f2.json`, `f2-opus/f2.json`, and each arm's folder with its memory store and
hook logs):
- session 2's first prompt (the scene's continue line) goes through `memory_hook.recall` twice
  on a copy of the arm's store as it stood before session 2: once with the continuation off
  (`SANCHOPANZA_MEMORY_CONTINUE=off`, the hook before C8) and once as shipped. The decider is
  replaced by the probabilities the night logged for the same candidates (`Logged`): nothing is
  asked live, and a question the night did not ask is counted as unanswered, never answered;
- session 2's SessionStart rules are rendered from the same store with plans ranked (as
  shipped) and with every rule treated as a rule (as before C8);
- the standing rules the night stored (each S arm's `rules` log rows) and the sentences of the
  scenes' session-1 prompts (`benchmarks/memory_carry/scenes_handoff.py`) are counted by
  `memory_rules.is_plan`.

Nothing is written into the run root: each store is copied to a temporary folder. The rows hold
numbers, scene names and arm flags only: no prompt, record or rule text, no session id, no path.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import statistics as st
import sys
import tempfile
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for extra in (REPO / "src", REPO / "benchmarks" / "memory_carry"):
    sys.path.insert(0, str(extra))

from scenes_handoff import HANDOFF  # noqa: E402

from sanchopanza import Decision, truth  # noqa: E402
from sanchopanza.harness import memory_hook as mh  # noqa: E402
from sanchopanza.harness import memory_rules as mr  # noqa: E402
from sanchopanza.points.rules import sentences  # noqa: E402
from sanchopanza.squire import Squire  # noqa: E402

RUNS = ("f2-sonnet", "f2-opus")
ENV = ("MEMORY_STORE", "MEMORY_STORE_KEY", "MEMORY_SELECT", "MEMORY_PROMPT", "MEMORY_TREE",
       "MEMORY_STORE_LOG", "MEMORY_CONTINUE")  # fmt: skip


def lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


class Logged:
    """Answers candidate i with the probability the night logged for it; else nothing."""

    name = "logged"
    accepts_attachments = False

    def __init__(self, candidates: list[str], probabilities: Mapping[str, float]) -> None:
        self.candidates, self.probabilities = candidates, probabilities
        self.calls = self.unanswered = 0

    async def decide(self, point: str, state: Any, questions: Mapping[str, Any]) -> Decision:
        self.calls += 1
        answers = {}
        for key in questions:
            i = int(key[1:]) - 1
            p = self.probabilities.get(self.candidates[i]) if i < len(self.candidates) else None
            if p is None:
                self.unanswered += 1
            else:
                answers = {**answers, key: truth(p)}
        return Decision(point, answers, self.name, "logged")


@contextlib.contextmanager
def environment(values: Mapping[str, str]) -> Iterator[None]:
    """`SANCHOPANZA_<name>` set for the block, and put back after it."""
    names = [f"SANCHOPANZA_{k}" for k in ENV]
    before = {n: os.environ.get(n) for n in names}
    try:
        for name in names:
            os.environ.pop(name, None)
        os.environ.update({f"SANCHOPANZA_{k}": v for k, v in values.items()})
        yield
    finally:
        for name, value in before.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _before_session_2(folder: Path, store: Path) -> tuple[Path, str]:
    """The arm's store copied to `store`, with what session 2 wrote taken out."""
    hooks = lines(folder / "hooks.jsonl")
    started = [h["session"] for h in hooks if h.get("event") == "SessionStart"]
    second = list(dict.fromkeys(started))[1]
    shutil.copytree(folder / "store", store)
    project = next(p for p in store.iterdir() if p.is_dir() and not p.name.startswith("."))
    for path in [*project.glob(f"{second}-*.json"), *(project / "shown").glob(f"{second}*")]:
        path.unlink()
    index = json.loads((project / "index.json").read_text(encoding="utf-8"))
    kept = {k: v for k, v in index.items() if not k.startswith(second)}
    (project / "index.json").write_text(json.dumps(kept), encoding="utf-8")
    rules = json.loads((project / mr.RULES).read_text(encoding="utf-8"))
    rules = {**rules, "rules": [r for r in rules["rules"] if r.get("session") != second]}
    (project / mr.RULES).write_text(json.dumps(rules), encoding="utf-8")
    return project, second


def replay_arm(row: Mapping[str, Any], work: Path) -> dict[str, Any]:
    folder = Path(row["folder"])
    log = lines(folder / "hook-log.jsonl")
    starts = [i for i, r in enumerate(log) if r.get("event") == "SessionStart"]
    second_rows = log[starts[1] :]
    night = next(r for r in second_rows if r.get("event") == "UserPromptSubmit")
    touch = sum(r.get("chars") or 0 for r in second_rows if r.get("event") == "PostToolUse")
    project, session = _before_session_2(folder, work / "store")
    event = {"hook_event_name": "UserPromptSubmit", "session_id": session,
             "transcript_path": str(work / project.name / f"{session}.jsonl"),  # not written
             "cwd": str(folder / "repo"), "prompt": HANDOFF[row["scene"]]["continue"]}  # fmt: skip
    out: dict[str, Any] = {}
    for label, continuation in (("before", "off"), ("now", "on")):
        shutil.rmtree(project / "shown", ignore_errors=True)
        values = {"MEMORY_STORE": str(work / "store"), "MEMORY_STORE_KEY": "folder",
                  "MEMORY_SELECT": "decider", "MEMORY_PROMPT": "first", "MEMORY_TREE": "off",
                  "MEMORY_STORE_LOG": str(work / "log.jsonl"),
                  "MEMORY_CONTINUE": continuation}  # fmt: skip
        decider = Logged(night.get("candidates") or [], night.get("probabilities") or {})
        with environment(values):
            given = asyncio.run(mh.recall(event, Squire(decider)))
        text = (given.get("hookSpecificOutput") or {}).get("additionalContext", "")
        shown = lines(work / "log.jsonl")[-1].get("shown") or []
        out = {**out, f"{label}_prompt_chars": len(text), f"{label}_at_prompt": bool(shown),
               f"{label}_decider_calls": decider.calls,
               f"{label}_unanswered": decider.unanswered}  # fmt: skip
    with mock.patch.object(mr, "is_plan", lambda _: False):
        rules_before = len(mr.render(project))
    rules_now = len(mr.render(project))
    return {
        "scene": row["scene"], "model": row["model"], "repeat": row["repeat"],
        "night_at_prompt": bool(night.get("shown")), "night_prompt_chars": night.get("chars", 0),
        "night_touch_chars": touch, "night_rules_chars": second_rows[0].get("rules_chars"),
        "rules_chars_before": rules_before, "rules_chars_now": rules_now, **out,
    }  # fmt: skip


def stored_rules(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    """The standing rules the night's S arms stored, by `is_plan` now."""
    added = [t for r in rows for x in lines(Path(r["folder"]) / "hook-log.jsonl")
             if x.get("event") == "rules" for t in x.get("added") or []]  # fmt: skip
    plans = sum(1 for t in added if mr.is_plan(t))
    return {"stored": len(added), "plan_shaped": plans, "rules": len(added) - plans}


def session_1_sentences() -> dict[str, int]:
    """The sentences of the scenes' session-1 prompts that Stop no longer asks Jev about."""
    found = [s for scene in HANDOFF.values() for s in sentences(scene["first"])]
    skipped = sum(1 for s in found if mr.is_plan(s) or "[...]" in s)
    lengths = [len(scene["first"]) for scene in HANDOFF.values()]
    return {
        "sentences": len(found),
        "not_asked": skipped,
        "scenes": len(HANDOFF),
        "prompt_chars_min": min(lengths),
        "prompt_chars_max": max(lengths),
    }


def summary(arms: list[Mapping[str, Any]]) -> dict[str, Any]:
    def total(key: str) -> int:
        return sum(int(a[key]) for a in arms)

    injected_before = [a["night_rules_chars"] + a["night_prompt_chars"] + a["night_touch_chars"]
                       for a in arms]  # fmt: skip
    # now, a record given at the prompt is not given again at the touch
    injected_now = [a["rules_chars_now"] + a["now_prompt_chars"]
                    + (0 if a["now_at_prompt"] else a["night_touch_chars"])
                    for a in arms]  # fmt: skip
    return {
        "arms": len(arms),
        "before_matches_the_night": sum(
            1 for a in arms if a["before_at_prompt"] == a["night_at_prompt"]
            and a["before_prompt_chars"] == a["night_prompt_chars"]),
        "rules_before_match_the_night": sum(
            1 for a in arms if a["rules_chars_before"] == a["night_rules_chars"]),
        "record_at_prompt_night": total("night_at_prompt"),
        "record_at_prompt_now": total("now_at_prompt"),
        "decider_calls_before": total("before_decider_calls"),
        "decider_calls_now": total("now_decider_calls"),
        "unanswered": total("before_unanswered") + total("now_unanswered"),
        "rules_chars_median_night": st.median(a["night_rules_chars"] for a in arms),
        "rules_chars_median_now": st.median(a["rules_chars_now"] for a in arms),
        "injected_chars_median_night": st.median(injected_before),
        "injected_chars_median_now": st.median(injected_now),
    }  # fmt: skip


def run(root: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"runs": {}}
    every: list[Mapping[str, Any]] = []
    for name in RUNS:
        rows = [r for r in json.loads((root / name / "f2.json").read_text(encoding="utf-8"))
                if r["arm"] == "S"]  # fmt: skip
        every = [*every, *rows]
        arms = []
        for row in rows:
            with tempfile.TemporaryDirectory() as tmp:
                arms.append(replay_arm(row, Path(tmp)))
        out["runs"][name] = {"summary": summary(arms), "arms": arms}
    return {**out, "stored_rules": stored_rules(every), "session_1": session_1_sentences()}
