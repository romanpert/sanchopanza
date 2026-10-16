"""v7: standing rules, the person's own sentences that later work must keep (`points.rules`).

Three moments, all in the memory hook:
- **Stop, after the record is saved:** each sentence of the request's prompt is asked whether it
  is a standing rule; the ones that are join the project's `rules.json`, verbatim, with when and
  where they were said. Only the prompt's text is read: never tool output or files. A plan or
  next-step sentence (`is_plan`, ROADMAP C8) is not asked about: it belongs to the record.
- **SessionStart (a new session, a resume, a clear or after a compaction):** the newest rules are
  given as context, whatever file the session goes on to touch (the carry bench's cross-file gap:
  a rule said while changing one file and broken in another).
- **Stop, before the agent stops (opt-in, `MEMORY_RULES_AUDIT=on`; `audit_on`):** the request's
  diff since its start is held against each rule the request did not itself state; a confident
  "broken" sends the agent back once, quoting the rule (RepoComplianceBench 2026: one message
  naming the violation, 90-100 % compliance), unless a newer stored rule or a sentence of the
  request's own prompt replaces it (F1, `superseded`). Off by default since 2026-10-14: no right
  send-back in the maintainer's real sessions (docs/results/2026-10-14-memory-stop).

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
from ..contract import Choice

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


# F1, supersession: a break confirmed by `kept` and `relation` is not sent back when the person
# replaced the rule since. On the maintainer's real sessions (v8 replay, 2026-10-03) 2 of the 8
# false send-backs quoted a rule the same request's prompt had just replaced. Measured on two
# sealed benches by two labellers (2026-10-05, branch memoria-v83): this Choice is the variant a
# second, blind labeller's rule picked (987ea5f, 1a60df9): at 0.55, 11/16 replaced rules caught,
# 0/32 correct send-backs suppressed, highest negative 0.45, every newer-stored-rule case caught;
# on the first bench (bc08d38, 0cbac8e) 7/10 held out, 0 false. A Truth on the request (0cbac8e's
# v8.3) caught more but suppressed tasks that would break the rule (0.81-0.90), so it is not used.
# The likeliest newer option must reach the cut and beat `stands`. It only runs on a confirmed
# break (under 1 % of audits). A failed, late or partial answer (no `stands` probability, an
# option it was not offered) sends back, as before.
SUPERSEDED_AT = 0.55
SUPERSEDE_SECONDS = 8.0  # its own deadline when the caller gives none
SUPERSEDE_RESERVE = 1.0  # seconds of the audit's deadline kept for writing its mark
NEWER_MAX = 8  # newer stored rules offered, newest first, after the request's own sentences
STANDS = "stands"
SUPERSEDE_INSTRUCTIONS = (
    "The person stated `rule` in an earlier session of this project. Each option below is "
    "something they said after it, with when. Does one of them replace `rule`, so that work going "
    "against `rule` now follows what the person asked later?"
)
SUPERSEDE_STANDS = (
    "None of them: `rule` still stands. They are about something else, add to it, refine it, "
    "repeat it or agree with it, or ask for work that only happens to touch what it protects; "
    "only an instruction that asks for the opposite, drops or renames what the rule protects, or "
    "says the rule no longer applies replaces it"
)

Note = Callable[[Mapping[str, Any]], None]


def _quiet(row: Mapping[str, Any]) -> None:
    return None


def rules_on() -> bool:
    return str(_env.get("MEMORY_RULES", "") or "on").strip().lower() not in ("off", "0")


AUDIT_ON = ("on", "1", "block")


def audit_on() -> bool:
    """Whether Stop holds the request's diff against the rules (`audit`) and sends a confident
    break back: `MEMORY_RULES_AUDIT` on, off by default since 2026-10-14
    (docs/results/2026-10-14-memory-stop). On the maintainer's real sessions it sent back 8 of 518
    audits with v8 and 1 of 349 with v8.1's cuts, none of them right; the memory cell's gain had
    no send-back (0 of 72 audits). Extraction and the rules given at session start stay on."""
    return str(_env.get("MEMORY_RULES_AUDIT", "") or "off").strip().lower() in AUDIT_ON


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


# ROADMAP C8: a plan or a decision about the next step ("For step 2, cap the discount at 20 %",
# "Step 2, in the next session: ...") is what comes next in one feature, not a rule later work
# must keep. In F2 the standing-rules question kept 40 such sentences in 72 S arms, beside each
# scene's constraint, in the 8-rule slot every session start gives. They belong to the record of
# the request that said them (`memory_recall.continued` gives it at a continuation), so they are
# neither asked about at Stop (no decision spent) nor given at a session start (stored before).
_PLAN = re.compile(
    r"\bsteps?\s*(?:\d+|one|two|three|four|five)\b|\bnext (?:session|time|step)\b|"
    r"\b(?:tomorrow|later today)\b|\b(?:phase|stage)\s*\d+\b|"
    r"\bpasos?\s*(?:\d+|uno|dos|tres)\b|\bpr[óo]xima sesi[óo]n\b|\bfase\s*\d+\b|"
    r"(?<!esta )\bmañana\b|\bsiguiente paso\b",
    re.IGNORECASE,
)


def is_plan(sentence: str) -> bool:
    """A sentence about a numbered step, the next session or tomorrow: a plan, not a rule."""
    return bool(_PLAN.search(sentence or ""))


def plan_in(request: str) -> bool:
    """A request that states a plan in one of the person's sentences."""
    from ..points.rules import sentences

    return any(is_plan(s) for s in sentences(request or ""))


async def extract(squire: Squire, store: Path, episodes: Sequence[ep.Episode]) -> list[str]:
    """New standing rules from the requests not asked yet; the texts added. A request is marked
    asked only when every one of its sentences got an answer (a decider error retries later)."""
    import asyncio

    from ..points import rules as points

    asked = set(load(store)["asked"])
    fresh = [e for e in episodes if e.key not in asked and e.request.strip()]
    if not fresh:
        return []
    pending = [(e, s) for e in fresh for s in points.sentences(e.request)
               if not is_plan(s)]  # fmt: skip

    async def ask(sentence: str, request: str) -> float | None:
        state, qs = points.questions_for_sentence(sentence, request)
        decision = await _decided(squire, "memory_standing_rule", state, qs)
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


async def _decided(squire: Squire, point: str, state: Any, questions: Any) -> Any:
    """`squire.decide` and its journal row: these points spent without a trace until 2026-10-06
    (the Jev audit could not meter them), and their failures, a 402 among them, went unseen."""
    decision = await squire.decide(point, state, questions)
    squire.record(decision)
    return decision


def _when(at: Any) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(float(at or 0)))


def _line(rule: Mapping[str, Any]) -> str:
    when = _when(rule.get("at"))
    files = ", ".join(rule.get("files") or [])
    where = f", while changing {files}" if files else ""
    return f'- "{rule["text"]}" ({when}{where})'


def render(store: Path) -> str:
    """The newest rules as session context, or "" when there are none. Newest first by the time
    they were said, whatever order the store keeps; header, lines and closing within GIVE_CHARS.
    A plan (`is_plan`) stored before C8 is not given: it would take a rule's place."""
    lines, room = [], GIVE_CHARS - len(HEADER) - len(CLOSING) - 1
    rules = sorted((r for r in load(store)["rules"] if not is_plan(str(r.get("text") or ""))),
                   key=lambda r: -float(r.get("at") or 0))  # fmt: skip
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
    own = [
        r for r in data["rules"] if not (r.get("session") == session and r.get("index") == index)
    ]
    held = own[:CHECK_MAX]
    change = _diff(cwd, head, paths) if held else ""
    if not change.strip():
        return [], {}

    from ..redact import redact_secrets

    order = _order(key, len(held))
    # The rules travel in the Choice's options, which the squire's redaction (of `state` only)
    # never reaches: masked here (review of v8, H1). A rule with no secret is sent as measured.
    state, questions = points.questions_for_rules(
        [
            (
                redact_secrets(str(held[i]["text"])),
                [redact_secrets(str(f)) for f in held[i].get("files") or []],
            )
            for i in order
        ],
        change,
    )
    seen = await _decided(squire, "memory_rule_all", state, questions)
    answer = seen.answer("broken")
    if seen.failed or answer.empty:  # nothing named: the request stays as it was, asked again
        return [], {"_failed": "memory_rule_all"}
    named = [0.0] * len(held)
    for k, i in enumerate(order, 1):
        named[i] = float(answer.probabilities.get(f"rule_{k}", 0.0))

    async def ask(rule: Mapping[str, Any]) -> float | None:
        """`kept` of a rule the side-by-side Choice named; None on a failure."""
        decision = await _decided(
            squire, "memory_rule_check", *points.questions_for_change(str(rule["text"]), change)
        )
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
        decision = await _decided(squire, "memory_rule_relation", *questions)
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
    """(text, source, when) said after `rule`: the request's own sentences first (the newest),
    then up to NEWER_MAX stored rules said after it, newest first; each text once."""
    from ..points import rules as points

    at = float(rule.get("at") or 0)
    seen = {_norm(str(rule.get("text") or ""))}
    out: list[tuple[str, str, str]] = []
    for sentence in points.sentences(request):
        if _norm(sentence) not in seen:
            seen.add(_norm(sentence))
            out.append((sentence, "request", "in the request being checked"))
    later = sorted((r for r in stored if float(r.get("at") or 0) > at),
                   key=lambda r: -float(r.get("at") or 0))  # fmt: skip
    stored_out: list[tuple[str, str, str]] = []
    for other in later:
        text = str(other.get("text") or "")
        if text.strip() and _norm(text) not in seen and len(stored_out) < NEWER_MAX:
            seen.add(_norm(text))
            stored_out.append((text, "stored", f"said {_when(other.get('at'))}, a stored rule"))
    return [*out, *stored_out]


def questions_for_superseded(rule: Mapping[str, Any], newer: Sequence[tuple[str, str, str]],
                             ) -> tuple[Mapping[str, Any], dict[str, Choice]]:  # fmt: skip
    """One Choice: `newer_<k>` is `newer[k - 1]`, and STANDS. Texts masked here: the options are
    not in `state`, which is all the squire's redaction reaches (review of v8, H1)."""
    from ..points.rules import SENTENCE_MAX
    from ..redact import redact_secrets
    from ..text import truncate

    options = {f"newer_{k}": f'"{redact_secrets(truncate(text, SENTENCE_MAX))}" ({when})'
               for k, (text, _, when) in enumerate(newer, 1)}  # fmt: skip
    state = {"rule": redact_secrets(truncate(str(rule.get("text") or ""), SENTENCE_MAX)),
             "rule_said": _when(rule.get("at"))}  # fmt: skip
    question = Choice(SUPERSEDE_INSTRUCTIONS, {**options, STANDS: SUPERSEDE_STANDS})
    return state, {"superseded": question}


Replaced = tuple[float | None, bool]  # (the likeliest newer option's probability, suppress)


async def _replaced(squire: Squire, store: Path, rules: Sequence[Mapping[str, Any]],
                    request: str, note: Note, budget: float = SUPERSEDE_SECONDS,
                    ) -> list[Replaced]:  # fmt: skip
    """Per confirmed break, whether something said since replaced the rule, within `budget`
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
        found = await asyncio.wait_for(
            asyncio.gather(*(_replaced_one(squire, r, stored, request, note) for r in rules)),
            budget,
        )
    except TimeoutError:
        for rule in rules:
            note({"event": "rules", "part": "superseded", "rule": str(rule["text"]),
                  "failed": f"timed out after {budget:.1f} s", "suppressed": False})  # fmt: skip
        return late
    return list(found)


async def _replaced_one(squire: Squire, rule: Mapping[str, Any],
                        stored: Sequence[Mapping[str, Any]], request: str, note: Note,
                        ) -> Replaced:  # fmt: skip
    newer = _newer(rule, stored, request)
    if not newer:
        return None, False
    offered = {f"newer_{k}": item for k, item in enumerate(newer, 1)}
    row: dict[str, Any] = {"event": "rules", "part": "superseded", "rule": str(rule["text"])}
    try:
        decision = await _decided(squire, "memory_rule_superseded",
                                       *questions_for_superseded(rule, newer))  # fmt: skip
        answer = decision.answer("superseded")
        probs = {str(k): float(v) for k, v in (answer.probabilities or {}).items()}
        failed = "decider failed" if decision.failed or answer.empty else ""
    except Exception as error:  # noqa: BLE001 - fail open: the send-back stands
        probs, failed = {}, f"error {error.__class__.__name__}"
    named = [k for k in probs if k != STANDS]
    if not failed and (STANDS not in probs or not named):
        failed = "no probability for stands" if STANDS not in probs else "no newer option"
    if not failed and any(k not in offered for k in named):
        failed = "an option it was not offered"
    if failed:
        note({**row, "failed": failed, "suppressed": False})
        return None, False
    top = max(named, key=lambda k: probs[k])
    p, stands = round(probs[top], 3), round(probs[STANDS], 3)
    suppressed = p >= SUPERSEDED_AT and p > stands
    text, source, _ = offered[top]
    note({**row, "by": text, "source": source, "p": p, "stands": stands,
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
