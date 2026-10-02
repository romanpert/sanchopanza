"""v7: standing rules, the person's own sentences that later work must keep (`points.rules`).

Three moments, all in the memory hook:
- **Stop, after the record is saved:** each sentence of the request's prompt is asked whether it
  is a standing rule; the ones that are join the project's `rules.json`, verbatim, with when and
  where they were said. Only the prompt's text is read: never tool output or files.
- **SessionStart (a new session, a resume, a clear or after a compaction):** the newest rules are
  given as context, whatever file the session goes on to touch (the carry bench's cross-file gap:
  a rule said while changing one file and broken in another).
- **Stop, before the agent stops:** the request's diff since its start is held against each rule
  the request did not itself state; a confident "broken" sends the agent back once, quoting the
  rule (RepoComplianceBench 2026: one message naming the violation, 90-100 % compliance).

Fails open everywhere: no decider, no git or a decider error leave the request as it was.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .. import _env
from ..context import episodes as ep
from ..context.archive import safe_name

if TYPE_CHECKING:
    from ..squire import Squire

RULES = "rules.json"
AUDITED = "audited"
KEEP_MAX = 60  # rules kept per project, newest first
GIVE_MAX = 8  # rules given at a session's start
GIVE_CHARS = 1_800
CHECK_MAX = 8  # rules held against a request's diff
STANDING_AT = 0.5  # 16/16 rules, 3/36 others on the carry scenes; 3.8 % of real sentences
BROKEN_BELOW = 0.5  # 15/15 broken, 5 false of 49 kept on 64 carry diffs (AUC 0.959)
GIT_SECONDS = 3.0
HEADER = ("[sanchopanza memory, standing rules: what the person said in earlier sessions of this "
          "project that later work must keep, in their words, newest first]")  # fmt: skip
CLOSING = ("If the task in front of you would break one of these, keep the rule, or say so "
           "plainly before you change it.")  # fmt: skip


def rules_on() -> bool:
    return str(_env.get("MEMORY_RULES", "") or "on").strip().lower() not in ("off", "0")


def _path(store: Path) -> Path:
    return store / RULES


def load(store: Path) -> dict[str, Any]:
    try:
        data = json.loads(_path(store).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"rules": [], "asked": [], AUDITED: []}
    if not isinstance(data, dict):
        return {"rules": [], "asked": [], AUDITED: []}
    return {"rules": list(data.get("rules") or []), "asked": list(data.get("asked") or []),
            AUDITED: list(data.get(AUDITED) or [])}  # fmt: skip


def _save(store: Path, data: Mapping[str, Any]) -> None:
    ep.write_private(_path(store), json.dumps(data, ensure_ascii=False))


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


async def extract(squire: Squire, store: Path, episodes: Sequence[ep.Episode]) -> list[str]:
    """New standing rules from the requests not asked yet; the texts added."""
    import asyncio

    from ..points import rules as points

    data = load(store)
    asked = set(data["asked"])
    fresh = [e for e in episodes if e.key not in asked and e.request.strip()]
    if not fresh:
        return []
    pending = [(e, s) for e in fresh for s in points.sentences(e.request)]

    async def ask(sentence: str, request: str) -> float | None:
        state, qs = points.questions_for_sentence(sentence, request)
        decision = await squire.decide("memory_standing_rule", state, qs)
        answer = decision.answer("rule")
        return None if decision.failed or answer.empty else answer.truth

    found = await asyncio.gather(*(ask(s, e.request) for e, s in pending))
    known = {_norm(r["text"]) for r in data["rules"]}
    added: list[dict[str, Any]] = []
    for (episode, sentence), p in zip(pending, found, strict=True):
        if p is not None and p >= STANDING_AT and _norm(sentence) not in known:
            known.add(_norm(sentence))
            added.append({"text": sentence, "p": round(p, 3), "session": episode.session,
                          "index": episode.index, "at": episode.at or time.time(),
                          "files": list(episode.changed[:4])})  # fmt: skip
    rules = sorted([*data["rules"], *added], key=lambda r: -float(r.get("at") or 0))[:KEEP_MAX]
    _save(store, {**data, "rules": rules, "asked": [*data["asked"], *(e.key for e in fresh)]})
    return [r["text"] for r in added]


def _line(rule: Mapping[str, Any]) -> str:
    when = time.strftime("%Y-%m-%d", time.localtime(float(rule.get("at") or 0)))
    files = ", ".join(rule.get("files") or [])
    where = f", while changing {files}" if files else ""
    return f'- "{rule["text"]}" ({when}{where})'


def render(store: Path) -> str:
    """The newest rules as session context, or "" when there are none."""
    lines, room = [], GIVE_CHARS - len(HEADER) - len(CLOSING)
    for rule in load(store)["rules"][:GIVE_MAX]:
        line = _line(rule)
        if len(line) + 1 > room:
            break
        lines.append(line)
        room -= len(line) + 1
    return "\n".join([HEADER, *lines, CLOSING]) if lines else ""


def _diff(cwd: str, head: str) -> str:
    """The request's change since its start: the working tree against the commit it began at
    (commits made during the request included), tests left out."""
    if not cwd or not head:
        return ""
    try:
        done = subprocess.run(["git", "-C", cwd, "diff", "--no-color", head, "--", ".",
                               ":(exclude)tests", ":(exclude)test"], capture_output=True,
                              timeout=GIT_SECONDS, check=False)  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.decode("utf-8", errors="replace") if done.returncode == 0 else ""


async def audit(squire: Squire, store: Path, session: str, index: int, cwd: str,
                head: str) -> tuple[list[dict[str, Any]], dict[str, float | None]]:  # fmt: skip
    """(rules the request's diff confidently breaks, every probability). Once per request."""
    import asyncio

    from ..points import rules as points

    data = load(store)
    key = f"{safe_name(session)}-{index:03d}"
    if key in data[AUDITED]:
        return [], {}
    own = [r for r in data["rules"]
           if not (r.get("session") == session and r.get("index") == index)]
    held = own[:CHECK_MAX]
    change = _diff(cwd, head) if held else ""
    if not change.strip():
        return [], {}
    _save(store, {**data, AUDITED: [*data[AUDITED], key][-500:]})

    async def ask(rule: Mapping[str, Any]) -> float | None:
        state, qs = points.questions_for_change(str(rule["text"]), change)
        decision = await squire.decide("memory_rule_check", state, qs)
        answer = decision.answer("kept")
        return None if decision.failed or answer.empty else answer.truth

    found = await asyncio.gather(*(ask(r) for r in held))
    probabilities = {str(r["text"])[:80]: p for r, p in zip(held, found, strict=True)}
    broken = [r for r, p in zip(held, found, strict=True) if p is not None and p < BROKEN_BELOW]
    return broken, probabilities


def block_reason(broken: Sequence[Mapping[str, Any]]) -> str:
    quoted = "\n".join(_line(r) for r in broken[:3])
    return ("[sanchopanza memory] Before you stop: in an earlier session the person stated, in "
            f"their words:\n{quoted}\nYour change may go against this. Check it. If it does, make "
            "the change respect the rule. If the person asked for this change now, or it already "
            "respects the rule, say so in one line and stop.")  # fmt: skip
