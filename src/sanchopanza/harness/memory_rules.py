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
# v8 audit, a cascade: every rule side by side in one Choice (`points.questions_for_rules`), and
# `kept` asked only of a rule it names at CANDIDATE_AT or more; broken when `kept` <
# BROKEN_BELOW. On 175 recorded carry sessions, each with its own rule and seven decoys
# (`audit_bench.py`, 2026-10-02): 43/43 breaks caught, 0 sessions sent back for a decoy (v7's
# per-rule audit: 31), 10 of 132 for an own rule it kept (v7: 11). Flat for CANDIDATE_AT 0.4-0.5.
# A generative second judge did not pay: Haiku 42/43 with 18 own, Sonnet 42/43 with 6, at about
# 130 and 250 times the price of a decision.
CANDIDATE_AT = 0.4
BROKEN_BELOW = 0.5
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
    """New standing rules from the requests not asked yet; the texts added. A request is marked
    asked only when every one of its sentences got an answer (a decider error retries later)."""
    import asyncio

    from ..points import rules as points

    asked = set(load(store)["asked"])
    fresh = [e for e in episodes if e.key not in asked and e.request.strip()]
    if not fresh:
        return []
    pending = [(e, s) for e in fresh for s in points.sentences(e.request)]

    async def ask(sentence: str, request: str) -> float | None:
        state, qs = points.questions_for_sentence(sentence, request)
        decision = await squire.decide("memory_standing_rule", state, qs)
        answer = decision.answer("rule")
        return None if decision.failed or answer.empty else answer.truth

    found = await asyncio.gather(*(ask(s, e.request) for e, s in pending),
                                 return_exceptions=True)  # fmt: skip
    answers = [p if isinstance(p, float) else None for p in found]
    unanswered = {e.key for (e, _), p in zip(pending, answers, strict=True) if p is None}
    with ep.locked(_path(store)):  # another session's Stop may have written meanwhile
        data = load(store)
        known = {_norm(r["text"]) for r in data["rules"]}
        added: list[dict[str, Any]] = []
        for (episode, sentence), p in zip(pending, answers, strict=True):
            if p is not None and p >= STANDING_AT and _norm(sentence) not in known:
                known.add(_norm(sentence))
                added.append({"text": sentence, "p": round(p, 3), "session": episode.session,
                              "index": episode.index, "at": episode.at or time.time(),
                              "files": list(episode.changed[:4])})  # fmt: skip
        rules = sorted([*data["rules"], *added], key=lambda r: -float(r.get("at") or 0))
        done = [e.key for e in fresh if e.key not in unanswered and e.key not in data["asked"]]
        _save(store, {**data, "rules": rules[:KEEP_MAX], "asked": [*data["asked"], *done][-2000:]})
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


NEW_FILE_BYTES = 40_000
_SKIP = (":(exclude)tests", ":(exclude)test")


def _git(cwd: str, *args: str) -> str | None:
    try:
        done = subprocess.run(["git", "-C", cwd, *args], capture_output=True,
                              timeout=GIT_SECONDS, check=False)  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.decode("utf-8", errors="replace") if done.returncode == 0 else None


def _new_files(cwd: str, paths: Sequence[str]) -> str:
    """Of the request's files, those git does not track yet, as added lines: `git diff` leaves
    them out, and a new module is where a rule is most often broken (the cross-file scenes).
    Read without touching the index (no `git add -N`); secrets-like names are skipped."""
    from ..context.worktree import _secret

    listed = _git(cwd, "ls-files", "--others", "--exclude-standard", "-z", "--", *paths)
    out, room = [], NEW_FILE_BYTES
    for rel in (listed or "").split("\0"):
        path = Path(cwd) / rel
        try:
            if not rel or _secret(rel) or not path.is_file() or path.stat().st_size > room:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        room -= len(text)
        added = "".join(f"+{line}\n" for line in text.splitlines())
        out.append(f"+++ b/{rel} (new file)\n{added}")
    return "".join(out)


def _tested(rel: str) -> bool:
    name = rel.replace("\\", "/")
    return bool(re.search(r"(^|/)tests?/|(^|/)test_[^/]*$|_test\.[^/]+$", name))


def _diff(cwd: str, head: str, paths: Sequence[str]) -> str:
    """The request's own change: the files it wrote (`paths`, relative to `cwd`), against the
    commit it began at (commits made during the request included), plus the ones it created.
    Never the rest of the tree: a person's uncommitted edit is not the request's (review, H1)."""
    mine = [p for p in dict.fromkeys(paths) if p and not _tested(p)]
    if not cwd or not head or not mine:
        return ""
    tracked = _git(cwd, "diff", "--no-color", head, "--", *mine)
    return (tracked or "") + _new_files(cwd, mine)


def _order(seed: str, n: int) -> list[int]:
    """A fixed shuffle per request, as measured: the side-by-side Choice must not see the newest
    rule always first."""
    import hashlib

    return sorted(range(n), key=lambda i: hashlib.sha256(f"{seed}{i}".encode()).hexdigest())


async def audit(squire: Squire, store: Path, session: str, index: int, cwd: str, head: str,
                paths: Sequence[str],
                ) -> tuple[list[dict[str, Any]], dict[str, Any]]:  # fmt: skip
    """(rules the request's diff confidently breaks, every probability). Once per request: the
    mark is written when the answers are in, so a timeout leaves the request to be asked."""
    import asyncio

    from ..points import rules as points

    data = load(store)
    key = f"{safe_name(session)}-{index:03d}"
    if key in data[AUDITED]:
        return [], {}
    own = [r for r in data["rules"]
           if not (r.get("session") == session and r.get("index") == index)]
    held = own[:CHECK_MAX]
    change = _diff(cwd, head, paths) if held else ""
    if not change.strip():
        return [], {}

    from ..redact import redact_secrets

    order = _order(key, len(held))
    # The rules travel in the Choice's options, which the squire's redaction (of `state` only)
    # never reaches: masked here (review of v8, H1). A rule with no secret is sent as measured.
    state, questions = points.questions_for_rules(
        [(redact_secrets(str(held[i]["text"])),
          [redact_secrets(str(f)) for f in held[i].get("files") or []]) for i in order], change)
    seen = await squire.decide("memory_rule_all", state, questions)
    answer = seen.answer("broken")
    if seen.failed or answer.empty:  # nothing named: the request stays as it was, asked again
        return [], {"_failed": "memory_rule_all"}
    named = [0.0] * len(held)
    for k, i in enumerate(order, 1):
        named[i] = float(answer.probabilities.get(f"rule_{k}", 0.0))

    async def ask(rule: Mapping[str, Any]) -> float | None:
        """`kept` of a rule the side-by-side Choice named; None on a failure."""
        decision = await squire.decide("memory_rule_check",
                                       *points.questions_for_change(str(rule["text"]), change))
        kept = decision.answer("kept")
        return None if decision.failed or kept.empty else kept.truth

    asked = [i for i in range(len(held)) if named[i] >= CANDIDATE_AT]
    found = await asyncio.gather(*(ask(held[i]) for i in asked), return_exceptions=True)
    kept: dict[int, float] = {i: p for i, p in zip(asked, found, strict=True)
                              if isinstance(p, float)}  # fmt: skip
    if len(kept) < len(asked):  # a named rule went unanswered: no mark, asked again (M1)
        return [], {"_failed": "memory_rule_check"}
    with ep.locked(_path(store)):
        latest = load(store)
        if key in latest[AUDITED]:  # another Stop of this request got here first
            return [], {}
        _save(store, {**latest, AUDITED: [*latest[AUDITED], key][-500:]})
    # Per rule, what the Choice named and what `kept` said (None: not asked), so CANDIDATE_AT
    # can be checked again on real sessions (L1).
    probabilities = {f"{i}:{str(r['text'])[:80]}": {"named": round(named[i], 3),
                                                    "kept": kept.get(i)}
                     for i, r in enumerate(held)}  # fmt: skip
    broken = [held[i] for i, p in kept.items() if p < BROKEN_BELOW]
    return broken, probabilities


def block_reason(broken: Sequence[Mapping[str, Any]]) -> str:
    quoted = "\n".join(_line(r) for r in broken[:3])
    return ("[sanchopanza memory] Before you stop: in an earlier session the person stated, in "
            f"their words:\n{quoted}\nYour change may go against this. Check it. If it does, make "
            "the change respect the rule. If the person asked for this change now, or it already "
            "respects the rule, say so in one line and stop.")  # fmt: skip
