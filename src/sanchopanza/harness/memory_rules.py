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
  rule (RepoComplianceBench 2026: one message naming the violation, 90-100 % compliance), unless
  the person has since asked for or stated its opposite (F1, `superseded`, v8.3).

Rules are given with the minute they were said, newest first, under a header saying the newer of
two conflicting rules stands (F1): two rules of one day were not ordered before.

Fails open everywhere: no decider, no git or a decider error leave the request as it was.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .. import _env
from ..context import episodes as ep
from ..context.archive import safe_name
from ..contract import Truth

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
# 2026-10-03, the maintainer's real sessions (518 audits, 8 sent back, none right): 5 of the 8 had
# `kept` between 0.43 and 0.49. At 0.45 the carry bench still catches 43/43 (10 -> 8 own kept sent
# back); at 0.4 it drops to 41/43. And a rule `kept` judges broken is sent back only when the
# three-way `relation` (v7's question) also puts "breaks" first: 43/43 on carry (own kept 9 at
# 0.5); on the real sessions the two together leave 4 of the 8, all false all the same.
BROKEN_BELOW = 0.45
GIT_SECONDS = 3.0
HEADER = ("[sanchopanza memory, standing rules: what the person said in earlier sessions of this "
          "project that later work must keep, in their words, newest first, each with when it "
          "was said; where two of them conflict, the newer one stands]")  # fmt: skip
CLOSING = ("If the task in front of you would break one of these, keep the rule, or say so "
           "plainly before you change it.")  # fmt: skip


# F1, supersession (v8.3): a break confirmed by `kept` and `relation` is not sent back when the
# person has since asked for, or stated, the opposite of the rule. One Truth (SUPERSEDE) per text
# said since: the request's prompt, and each stored rule said after the rule (NEWER_MAX, newest
# first); suppressed when the highest reaches SUPERSEDED_AT. v8.2 asked one Choice, "does one of
# these replace the rule?", and suppressed none of 37 recorded send-backs, the 2 real ones
# included: in the real cases the person asks for what the rule forbids without saying the rule
# changed. Measured on `benchmarks/memory_carry/supersede_bench.py` (2026-10-05, 93 hand-labelled
# cases, a seeded held-out third, cut fixed on dev before the held-out run): dev 15 of 17
# suppressed (v8.2's Choice 10, a contradicts/refines/unrelated Choice 14), 0 of 44 negatives;
# held out 7 of 10, 0 of 22 negatives, but the highest negative, an own carry rule, at 0.74.
# THIN: the request half confuses "a task that would break the rule" with "asks for its
# opposite" (own carry rules up to 0.74); the stored half is clean (negatives <= 0.15, positives
# >= 0.89). Real request-path positives: 3 of 8 suppressed. Any failed, late or unreadable answer
# sends back, as before.
SUPERSEDED_AT = 0.75
SUPERSEDE_SECONDS = 8.0  # its own deadline when the caller gives none
SUPERSEDE_RESERVE = 1.0  # seconds of the audit's deadline kept for writing its mark
NEWER_MAX = 8  # stored rules said since that are asked, newest first, after the request
SUPERSEDE = Truth(
    "The person stated `rule` in an earlier session of this project (`rule_said`). Later "
    "(`said_when`) they said `said`. In `said`, does the person themselves ask for something "
    "`rule` forbids, or state the opposite of `rule`, so that their latest word replaces it?",
    criteria={
        "true": {
            "what": "`said` names what `rule` is about and asks for or states something else: "
            "another value, format, tool, order, language or permission than `rule` gives; drops "
            "or reverses what it protects; says it no longer holds; or asks, in so many words, "
            "for an exception to it now",
            "examples": [
                "rule: 'deploys happen only on Tuesdays'; said: 'from now on deploy whenever "
                "main is green'",
                "rule: 'thumbnails are 200 px wide'; said: 'the new gallery needs 320 px "
                "thumbnails, change them all'",
                "rule: 'nunca subas el modelo al bucket público'; said: 'sube esta versión al "
                "bucket público, ya es open source'",
                "rule: 'the nightly job never sends email'; said: 'have the nightly job email me "
                "a summary when it finishes'",
            ],
        },
        "false": {
            "what": "`said` repeats, agrees with, narrows or adds to `rule`, or sets a condition "
            "for later; is about something else; or asks for a piece of work that could go "
            "against `rule` only through how it is done, without saying anything against what "
            "`rule` protects (the person may have forgotten `rule`: it still stands)",
            "examples": [
                "rule: 'deploys happen only on Tuesdays'; said: 'remember, Tuesdays only'",
                "rule: 'thumbnails are 200 px wide'; said: 'make the gallery load faster'",
                "rule: 'report files start with the date, the archive sorts on it'; said: 'give "
                "the report files friendlier names for customers'",
                "rule: 'nunca subas el modelo al bucket público'; said: 'documenta cómo se "
                "entrena el modelo'",
            ],
        },
    },
)
NOW = "now, in the request being checked"

Note = Callable[[Mapping[str, Any]], None]


def _quiet(row: Mapping[str, Any]) -> None:
    return None


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


def _when(at: Any) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(float(at or 0)))


def _line(rule: Mapping[str, Any]) -> str:
    when = _when(rule.get("at"))
    files = ", ".join(rule.get("files") or [])
    where = f", while changing {files}" if files else ""
    return f'- "{rule["text"]}" ({when}{where})'


def render(store: Path) -> str:
    """The newest rules as session context, or "" when there are none. Newest first by the time
    they were said, whatever order the store keeps; header, lines and closing within GIVE_CHARS."""
    lines, room = [], GIVE_CHARS - len(HEADER) - len(CLOSING) - 1
    rules = sorted(load(store)["rules"], key=lambda r: -float(r.get("at") or 0))
    for rule in rules[:GIVE_MAX]:
        line = _line(rule)
        if len(line) + 1 > room:
            break
        lines.append(line)
        room -= len(line) + 1
    return "\n".join([HEADER, *lines, CLOSING]) if lines else ""


def merge(store: Path, other: Mapping[str, Any]) -> None:
    """Fold another store's rules and marks into `store` (`memory_store.adopt`): one copy per
    text, the newest; newest first, KEEP_MAX kept."""
    with ep.locked(_path(store)):
        data = load(store)
        best: dict[str, dict[str, Any]] = {}
        for rule in [*data["rules"], *(other.get("rules") or [])]:
            if not isinstance(rule, Mapping) or not str(rule.get("text") or "").strip():
                continue
            key = _norm(str(rule["text"]))
            if key not in best or float(rule.get("at") or 0) > float(best[key].get("at") or 0):
                best[key] = dict(rule)
        rules = sorted(best.values(), key=lambda r: -float(r.get("at") or 0))[:KEEP_MAX]
        asked = list(dict.fromkeys([*(other.get("asked") or []), *data["asked"]]))[-2000:]
        audited = list(dict.fromkeys([*(other.get(AUDITED) or []), *data[AUDITED]]))[-500:]
        _save(store, {**data, "rules": rules, "asked": asked, AUDITED: audited})


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
                paths: Sequence[str], request: str = "", note: Note = _quiet,
                deadline: float | None = None,
                ) -> tuple[list[dict[str, Any]], dict[str, Any]]:  # fmt: skip
    """(rules the request's diff confidently breaks, every probability). Once per request: the
    mark is written when the answers are in, so a timeout leaves the request to be asked.
    `request` is the request's prompt: a confirmed break it (or a newer stored rule) replaced is
    not sent back (`superseded`), and `note` gets one row per such question. `deadline` is the
    caller's (`time.monotonic()`): the supersession question gets what is left of it but
    SUPERSEDE_RESERVE, so running late there sends back instead of losing the audit."""
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

    async def relation(rule: Mapping[str, Any]) -> str | None:
        """The three-way relation's first answer for a rule `kept` judged broken."""
        questions = points.questions_for_relation(str(rule["text"]), change)
        decision = await squire.decide("memory_rule_relation", *questions)
        answer = decision.answer("relation")
        if decision.failed or answer.empty:
            return None
        if answer.choice:  # a provider may name the option and give no probabilities
            return answer.choice
        probs = answer.probabilities
        return max(probs, key=probs.get) if probs else None

    doubtful = [i for i, p in kept.items() if p < BROKEN_BELOW]
    first = await asyncio.gather(*(relation(held[i]) for i in doubtful), return_exceptions=True)
    if any(not isinstance(r, str) for r in first):  # unanswered: no mark, asked again (M1)
        return [], {"_failed": "memory_rule_relation"}
    confirmed = {i for i, r in zip(doubtful, first, strict=True) if r == "breaks"}
    budget = SUPERSEDE_SECONDS if deadline is None else \
        deadline - time.monotonic() - SUPERSEDE_RESERVE  # fmt: skip
    replaced = await _replaced(squire, store, [held[i] for i in sorted(confirmed)], request,
                               note, budget)  # fmt: skip
    by_rule = dict(zip(sorted(confirmed), replaced, strict=True))
    with ep.locked(_path(store)):
        latest = load(store)
        if key in latest[AUDITED]:  # another Stop of this request got here first
            return [], {}
        _save(store, {**latest, AUDITED: [*latest[AUDITED], key][-500:]})
    # Per rule, what the Choice named and what `kept` said (None: not asked), so CANDIDATE_AT
    # can be checked again on real sessions (L1).
    probabilities = {f"{i}:{str(r['text'])[:80]}": {"named": round(named[i], 3),
                                                    "kept": kept.get(i),
                                                    "breaks_first": i in confirmed,
                                                    **({"superseded": by_rule[i][0]}
                                                       if i in by_rule and by_rule[i][0]
                                                       is not None else {})}
                     for i, r in enumerate(held)}  # fmt: skip
    broken = [held[i] for i in sorted(confirmed) if not by_rule[i][1]]
    return broken, probabilities


def _newer(rule: Mapping[str, Any], stored: Sequence[Mapping[str, Any]], request: str,
           ) -> list[tuple[str, str, str]]:  # fmt: skip
    """(text, source, when) said after `rule`: the request's prompt first (the newest), then up
    to NEWER_MAX stored rules said after it, newest first; never the rule's own text."""
    at, own = float(rule.get("at") or 0), _norm(str(rule.get("text") or ""))
    out = [(request, "request", NOW)] if request.strip() else []
    later = sorted((r for r in stored if float(r.get("at") or 0) > at),
                   key=lambda r: -float(r.get("at") or 0))  # fmt: skip
    stored_out = [(str(r.get("text") or ""), "stored",
                   f"{_when(r.get('at'))}, as a rule for the project") for r in later
                  if str(r.get("text") or "").strip() and _norm(str(r["text"])) != own]  # fmt: skip
    return [*out, *stored_out[:NEWER_MAX]]


def questions_for_superseded(rule: Mapping[str, Any], said: str, when: str,
                             ) -> tuple[Mapping[str, Any], dict[str, Truth]]:  # fmt: skip
    """One Truth on `rule` and one text said since. Masked here too: a squire built without
    redaction must not carry a secret of the prompt (review of v8, H1)."""
    from ..points.rules import REQUEST_LIMIT, SENTENCE_MAX
    from ..redact import redact_secrets
    from ..text import truncate

    state = {"rule": redact_secrets(truncate(str(rule.get("text") or ""), SENTENCE_MAX)),
             "rule_said": _when(rule.get("at")),
             "said": redact_secrets(truncate(said, REQUEST_LIMIT)), "said_when": when}  # fmt: skip
    return state, {"against": SUPERSEDE}


Replaced = tuple[float | None, bool]  # (the highest probability, suppress)


async def _replaced(squire: Squire, store: Path, rules: Sequence[Mapping[str, Any]],
                    request: str, note: Note, budget: float = SUPERSEDE_SECONDS,
                    ) -> list[Replaced]:  # fmt: skip
    """Per confirmed break, whether the person has since asked for its opposite, within `budget`
    seconds. Late, failed or nothing newer: not suppressed (the send-back stands)."""
    import asyncio

    if not rules:
        return []
    # A newer rule another Stop wrote meanwhile counts too. This request's own sentences come
    # from `request`: its rules are extracted beside the audit, maybe into another store (K4).
    stored = load(store)["rules"]
    late = [(None, False) for _ in rules]
    if budget <= 0:
        for rule in rules:
            note({"event": "rules", "part": "superseded", "rule": str(rule["text"]),
                  "failed": "no time left", "suppressed": False})  # fmt: skip
        return late
    try:
        found = await asyncio.wait_for(asyncio.gather(
            *(_replaced_one(squire, r, stored, request, note) for r in rules)), budget)
    except TimeoutError:
        for rule in rules:
            note({"event": "rules", "part": "superseded", "rule": str(rule["text"]),
                  "failed": f"timed out after {budget:.1f} s", "suppressed": False})  # fmt: skip
        return late
    return list(found)


async def _against(squire: Squire, rule: Mapping[str, Any], said: str, when: str,
                   ) -> float | None:  # fmt: skip
    """SUPERSEDE's probability for one text, or None on any failure."""
    try:
        decision = await squire.decide("memory_rule_superseded",
                                       *questions_for_superseded(rule, said, when))  # fmt: skip
    except Exception:  # noqa: BLE001 - fail open: the send-back stands
        return None
    answer = decision.answer("against")
    if decision.failed or answer.empty or answer.truth is None:
        return None
    return float(answer.truth)


async def _replaced_one(squire: Squire, rule: Mapping[str, Any],
                        stored: Sequence[Mapping[str, Any]], request: str, note: Note,
                        ) -> Replaced:  # fmt: skip
    import asyncio

    newer = _newer(rule, stored, request)
    if not newer:
        return None, False
    row: dict[str, Any] = {"event": "rules", "part": "superseded", "rule": str(rule["text"])}
    found = await asyncio.gather(*(_against(squire, rule, text, when) for text, _, when in newer))
    answered = [p for p in found if p is not None]
    if len(answered) < len(found):  # one unanswered text is a doubt: send back
        note({**row, "failed": "decider failed", "asked": len(newer), "suppressed": False})
        return None, False
    top = max(range(len(newer)), key=lambda k: answered[k])
    p = round(answered[top], 3)
    suppressed = p >= SUPERSEDED_AT
    text, source, _ = newer[top]
    note({**row, "by": text[:400], "source": source, "p": p, "asked": len(newer),
          "suppressed": suppressed})  # fmt: skip
    return p, suppressed


async def extract_landed(squire: Squire, store: Path, session: str, cwd: str,
                         episodes: Sequence[ep.Episode], note: Note = _quiet,
                         ) -> list[str]:  # fmt: skip
    """`extract` for each request into the store of the repository its changes landed in (K4,
    `memory_store.landing`, which may call git: run off the event loop). The texts added."""
    import asyncio

    from . import memory_store

    targets = await asyncio.to_thread(memory_store.landing, store, session, cwd, episodes)
    elsewhere = {t.name: [e.key for e in v] for t, v in targets.items() if t != store}
    if elsewhere:
        note({"event": "rules", "part": "landing", "stores": elsewhere})
    found = await asyncio.gather(*(extract(squire, target, eps)
                                   for target, eps in targets.items()))  # fmt: skip
    return [text for texts in found for text in texts]


def block_reason(broken: Sequence[Mapping[str, Any]]) -> str:
    quoted = "\n".join(_line(r) for r in broken[:3])
    return ("[sanchopanza memory] Before you stop: in an earlier session the person stated, in "
            f"their words:\n{quoted}\nYour change may go against this. Check it. If it does, make "
            "the change respect the rule. If the person asked for this change now, or it already "
            "respects the rule, say so in one line and stop.")  # fmt: skip
