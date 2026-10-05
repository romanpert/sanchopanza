"""F1 supersession check, iterated on a labelled bench (2026-10-05). Before a confirmed send-back,
memory v8.2 asks one Choice whether something said since replaced the rule; on 37 recorded
send-backs it suppressed none, the two real ones included. This bench tests other questions.

    python supersede_bench.py build                      # free: JSONL + held-out draw
    python supersede_bench.py plan --variants a,b,c,d --split dev   # free: counts the calls
    python supersede_bench.py run  --variants a,b,c,d --split dev --paid
    python supersede_bench.py select                     # free: cuts and winner from dev
    python supersede_bench.py run  --variants <winner> --split held --paid
    python supersede_bench.py report

Variants, all asked through the squire (Jev, `SANCHOPANZA_PROVIDER=jev`):
- a: v8.2 as shipped then (frozen here as `V82`), one Choice. Score: the likeliest
  newer option's probability.
- b: one Truth on the rule and the request's prompt: does the person, in what they said, ask for
  what the rule forbids or state its opposite? Score: its probability.
- d: the same Truth on the rule and each stored rule said since (at most NEWER_MAX). Score: the
  highest. `b+d` (scored, never asked apart) is the higher of b and d.
- c: one Choice contradicts / refines / unrelated on the rule, the request and the single stored
  rule since that shares the most words with it. Score: p(contradicts).

Selection, fixed before any call (2026-10-05):
- For each of a, b, b+d and c, on the dev split (labels 0 and 1; ambiguous never scored), the cut
  is the first multiple of 0.05 at least 0.01 above the highest score of any dev negative, and
  never under 0.5. So every variant has 0 false suppressions on dev by construction.
- The winner suppresses the most dev positives at its cut; ties go to the higher dev AUC, then to
  fewer calls per case. No winner if the best suppresses none.
- The winner's cut is frozen and run once on the held-out third. It ships only if that run has no
  false suppression; whatever it gives is the reported result.
- A failed answer scores as not suppressed (fail open), and is reported.

Budget: Jev only, at most CAP calls for the whole iteration, counted in a ledger outside the
repository; `run` refuses to start when the planned calls would pass what is left.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import random
import re
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from rules import RULES  # noqa: E402
from scenes import SCENES  # noqa: E402
from scenes_cross import CROSS, CROSS_RULES  # noqa: E402
from scenes_held import HELD  # noqa: E402
from scenes_stale import STALE, STALE_RULES  # noqa: E402
from supersede_cases import CARRY_NOTES, REAL_PAIRS, REAL_SENDBACKS, WRITTEN  # noqa: E402

from sanchopanza.contract import Choice, Truth  # noqa: E402
from sanchopanza.harness import memory_rules as mr  # noqa: E402
from sanchopanza.points import rules as points  # noqa: E402
from sanchopanza.text import truncate  # noqa: E402

SEED = 20261005
CAP = 400
BENCH = HERE / "supersede_bench.jsonl"
CACHE = Path.home() / ".cache" / "sanchopanza" / "memory-supersede"
PRIVATE = CACHE / "real-cases.jsonl"
LEDGER = CACHE / "ledger.json"
DETAIL = Path.home() / ".cache" / "sanchopanza" / "memory-real" / "local-rules-v8-detail.json"
OUT = HERE.parent.parent / "docs" / "results" / "2026-10-05-memory-supersede"
BASE_AT = 1_788_253_200.0  # 2026-09-01 10:00 local-ish: synthetic rules are said then
DAY = 86_400.0
REAL_STORED_MAX = 3  # real cases: the newest stored rules since, as v8.2 would offer first
VARIANTS = ("a", "b", "c", "d")
SCORED = ("a", "b", "b+d", "c")

# --- the candidate questions --------------------------------------------------------------------

AGAINST = Truth(
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

RELATION_NOW = Choice(
    "The person stated `rule` in an earlier session of this project (`rule_said`). `request` is "
    "what they ask now, and `newer_rule` the closest thing they stated as a rule since (it may "
    "be empty). Taken together, how do they stand towards `rule`?",
    {
        "contradicts": "`request` or `newer_rule` names what `rule` is about and asks for or "
        "states the opposite, drops what it protects, or says it no longer holds: the person's "
        "latest word replaces `rule`",
        "refines": "They repeat, agree with, narrow or add to `rule`, which still stands",
        "unrelated": "They are about something else, or ask for work that only touches what "
        "`rule` is about without saying anything against it: `rule` still stands",
    },
)


# v8.2's question, frozen here as it was asked for variant a (memory_rules ships v8.3 since).
V82_STANDS = "stands"
V82_INSTRUCTIONS = (
    "The person stated `rule` in an earlier session of this project. Each option below is "
    "something they said after it, with when. Does one of them replace `rule`, so that work going "
    "against `rule` now follows what the person asked later?"
)
V82_STANDS_TEXT = (
    "None of them: `rule` still stands. They are about something else, add to it, "
    "refine it, repeat it or agree with it, or ask for work that only happens to touch what it "
    "protects; only an instruction that asks for the opposite, drops or renames what the rule "
    "protects, or says the rule no longer applies replaces it"
)


def v82_newer(rule: Mapping[str, Any], stored: Sequence[Mapping[str, Any]], request: str,
              ) -> list[tuple[str, str]]:  # fmt: skip
    """v8.2's options: the request's sentences, then up to 8 stored rules said since."""
    at = float(rule.get("at") or 0)
    seen = {_norm(str(rule.get("text") or ""))}
    out: list[tuple[str, str]] = []
    for sentence in points.sentences(request):
        if _norm(sentence) not in seen:
            seen.add(_norm(sentence))
            out.append((sentence, "in the request being checked"))
    later = sorted((r for r in stored if float(r.get("at") or 0) > at),
                   key=lambda r: -float(r.get("at") or 0))  # fmt: skip
    kept = 0
    for other in later:
        text = str(other.get("text") or "")
        if text.strip() and _norm(text) not in seen and kept < 8:
            seen.add(_norm(text))
            kept += 1
            out.append((text, f"said {mr._when(other.get('at'))}, a stored rule"))
    return out


def v82_question(rule: Mapping[str, Any], newer: Sequence[tuple[str, str]]) -> tuple[dict, dict]:
    options = {f"newer_{k}": f'"{truncate(text, points.SENTENCE_MAX)}" ({when})'
               for k, (text, when) in enumerate(newer, 1)}  # fmt: skip
    state = {"rule": truncate(str(rule.get("text") or ""), points.SENTENCE_MAX),
             "rule_said": mr._when(rule.get("at"))}  # fmt: skip
    return state, {"superseded": Choice(V82_INSTRUCTIONS, {**options, V82_STANDS: V82_STANDS_TEXT})}


def against_state(rule: Mapping[str, Any], said: str, when: str) -> dict[str, Any]:
    return {"rule": truncate(str(rule["text"]), points.SENTENCE_MAX),
            "rule_said": mr._when(rule.get("at")), "said": truncate(said, points.REQUEST_LIMIT),
            "said_when": when}  # fmt: skip


_WORD = re.compile(r"\w{4,}")


def _words(text: str) -> set[str]:
    return {w.casefold() for w in _WORD.findall(text)}


def closest(rule: Mapping[str, Any], stored: Sequence[Mapping[str, Any]]) -> str:
    """Of the stored rules said after `rule`, the one sharing the most words with it (Jaccard;
    ties to the newest), or ""."""
    at, mine = float(rule.get("at") or 0), _words(str(rule["text"]))
    later = sorted((s for s in stored if float(s.get("at") or 0) > at),
                   key=lambda s: -float(s.get("at") or 0))  # fmt: skip
    best, score = "", -1.0
    for s in later[: mr.NEWER_MAX]:
        theirs = _words(str(s["text"]))
        j = len(mine & theirs) / len(mine | theirs) if mine | theirs else 0.0
        if j > score:
            best, score = str(s["text"]), j
    return best


def stored_since(rule: Mapping[str, Any], stored: Sequence[Mapping[str, Any]]) -> list[dict]:
    at = float(rule.get("at") or 0)
    later = sorted((s for s in stored if float(s.get("at") or 0) > at),
                   key=lambda s: -float(s.get("at") or 0))  # fmt: skip
    return [dict(s) for s in later[: mr.NEWER_MAX]]


# --- building -----------------------------------------------------------------------------------


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def sha(text: str) -> str:
    return hashlib.sha256(_norm(text).encode()).hexdigest()[:12]


def _real_index() -> tuple[dict[str, tuple[float, str]], dict[str, dict], dict[str, list]]:
    """(sha -> (at, text)) of every sentence stored as a rule, (session8-index -> request), and
    per request key the project's rules (at, text) for its stored-since list."""
    data = json.loads(DETAIL.read_text(encoding="utf-8"))
    by_sha: dict[str, tuple[float, str]] = {}
    reqs: dict[str, dict] = {}
    hist_of: dict[str, list] = {}
    for project in data["projects"]:
        hist, seen = [], set()
        for req in sorted(project["requests"], key=lambda r: r["at"]):
            for s in req["sentences"]:
                if s["p"] >= 0.5 and _norm(s["sentence"]) not in seen:
                    seen.add(_norm(s["sentence"]))
                    hist.append((float(req["at"]), s["sentence"]))
                    by_sha.setdefault(sha(s["sentence"]), (float(req["at"]), s["sentence"]))
        for req in project["requests"]:
            key = f"{req['session'][:8]}-{int(req['index']):03d}"
            reqs[key] = req
            hist_of[key] = hist
    return by_sha, reqs, hist_of


def real_cases() -> list[dict[str, Any]]:
    by_sha, reqs, hist_of = _real_index()
    out = []
    for spec in REAL_SENDBACKS:
        req = reqs[spec["request"]]
        text = next(b for b in req["audit"]["broken"] if sha(b) == spec["rule"])
        at = by_sha.get(spec["rule"], (0.0, text))[0]
        mine = {_norm(s) for s in points.sentences(req["request"])}
        stored = [{"text": t, "at": a} for a, t in hist_of[spec["request"]]
                  if at < a < float(req["at"]) and _norm(t) not in mine]  # fmt: skip
        stored = sorted(stored, key=lambda s: -s["at"])[:REAL_STORED_MAX]
        out.append({**spec, "family": "real", "rule": {"text": text, "at": at},
                    "request": req["request"], "stored": stored,
                    "path": "request" if spec["label"] == 1 else "none"})  # fmt: skip
    for spec in REAL_PAIRS:
        at, text = by_sha[spec["rule"]]
        said = " ".join(by_sha[s][1] for s in spec["said"])
        out.append({**spec, "family": "real", "rule": {"text": text, "at": at},
                    "request": said, "stored": [],
                    "path": "request" if spec["label"] == 1 else "none"})  # fmt: skip
    return out


def carry_cases() -> list[dict[str, Any]]:
    scenes = {**SCENES, **CROSS, **HELD}
    own = {**RULES, **CROSS_RULES}
    names = sorted(scenes)
    out = []
    for i, name in enumerate(names):
        decoy = own[names[(i + 1) % len(names)]]
        out.append({"id": f"carry-{name}", "family": "carry", "label": 0, "path": "none",
                    "reason": f"own rule; the prompt {CARRY_NOTES[name]}",
                    "rule": {"text": own[name], "at": BASE_AT},
                    "request": scenes[name]["second"],
                    "stored": [{"text": decoy, "at": BASE_AT + DAY}]})  # fmt: skip
    return out


def _sentence_with(text: str, part: str) -> str:
    return next(s for s in points.sentences(text) if part[:40] in s)


def stale_cases() -> list[dict[str, Any]]:
    names = sorted(STALE)
    out = []
    for i, name in enumerate(names):
        scene, said = STALE[name], STALE_RULES[name]
        old = _sentence_with(scene["first"], said["stale"])
        new = _sentence_with(scene["between"], said["fact"])
        decoy = STALE_RULES[names[(i + 1) % len(names)]]["stale"]
        rule = {"text": old, "at": BASE_AT}
        out.append({"id": f"stale-{name}-new", "family": "stale", "label": 1, "path": "stored",
                    "reason": "A' stored since says 'we changed this' and gives another value",
                    "rule": rule, "request": scene["second"],
                    "stored": [{"text": decoy, "at": BASE_AT + DAY},
                               {"text": new, "at": BASE_AT + 2 * DAY}]})  # fmt: skip
        out.append({"id": f"stale-{name}-old", "family": "stale", "label": 0, "path": "none",
                    "reason": "the same rule and prompt without A': the prompt only touches the "
                    "rule's area", "rule": rule, "request": scene["second"],
                    "stored": [{"text": decoy, "at": BASE_AT + DAY}]})  # fmt: skip
    return out


def written_cases() -> list[dict[str, Any]]:
    out = []
    for spec in WRITTEN:
        stored = [{"text": t, "at": BASE_AT + (k + 1) * DAY}
                  for k, t in enumerate(spec.get("stored") or [])]  # fmt: skip
        out.append({**spec, "family": "written", "rule": {"text": spec["rule"], "at": BASE_AT},
                    "stored": stored})  # fmt: skip
    return out


def draw(cases: list[dict[str, Any]]) -> dict[str, str]:
    """A third held out per (family, label), by a seeded shuffle; ambiguous cases `report`."""
    rng = random.Random(SEED)
    split: dict[str, str] = {}
    strata: dict[tuple[str, Any], list[str]] = {}
    for case in cases:
        if case["label"] is None:
            split[case["id"]] = "report"
        else:
            strata.setdefault((case["family"], case["label"]), []).append(case["id"])
    for key in sorted(strata, key=str):
        ids = sorted(strata[key])
        rng.shuffle(ids)
        held = round(len(ids) / 3)
        for k, cid in enumerate(ids):
            split[cid] = "held" if k < held else "dev"
    return split


def build() -> int:
    cases = real_cases() + carry_cases() + stale_cases() + written_cases()
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "duplicate ids"
    split = draw(cases)
    cases = [{**c, "split": split[c["id"]]} for c in cases]
    CACHE.mkdir(parents=True, exist_ok=True)
    PRIVATE.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in cases
                                 if c["family"] == "real") + "\n", encoding="utf-8")  # fmt: skip
    public = []
    for c in cases:
        if c["family"] == "real":  # texts stay on this machine: ids, hashes, labels, reasons
            spec = next(s for s in [*REAL_SENDBACKS, *REAL_PAIRS] if s["id"] == c["id"])
            c = {**{k: c[k] for k in ("id", "family", "label", "reason", "path", "split")},
                 "rule_sha": spec["rule"], "said_sha": spec.get("said"),
                 "request_key": spec.get("request"), "private": True}  # fmt: skip
        public.append(c)
    BENCH.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in public) + "\n",
                     encoding="utf-8")  # fmt: skip
    for part in ("dev", "held", "report"):
        rows = [c for c in cases if c["split"] == part]
        pos = sum(c["label"] == 1 for c in rows)
        neg = sum(c["label"] == 0 for c in rows)
        fams = sorted({c["family"] for c in rows})
        print(f"{part}: {len(rows)} cases, {pos} positives, {neg} negatives, families {fams}")
    return 0


def load_cases() -> list[dict[str, Any]]:
    private = {}
    if PRIVATE.exists():
        for line in PRIVATE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                private[row["id"]] = row
    out = []
    for line in BENCH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("private"):
            full = private.get(row["id"])
            if full is None or sha(full["rule"]["text"]) != row["rule_sha"]:
                raise SystemExit(f"{row['id']}: private text missing or changed; run build")
            row = {**full, "split": row["split"], "label": row["label"]}
        out.append(row)
    return out


# --- asking -------------------------------------------------------------------------------------


def calls_for(case: Mapping[str, Any], variant: str) -> int:
    if variant == "d":
        return len(stored_since(case["rule"], case["stored"]))
    if variant == "a":
        return 1 if v82_newer(case["rule"], case["stored"], case["request"]) else 0
    return 1


def _ledger() -> dict[str, Any]:
    try:
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"calls": 0, "usd": 0.0, "runs": []}


def _results_path(variant: str) -> Path:
    return OUT / f"answers-{variant}.jsonl"


def _done(variant: str) -> set[str]:
    path = _results_path(variant)
    if not path.exists():
        return set()
    return {json.loads(x)["id"] for x in path.read_text(encoding="utf-8").splitlines() if x}


def plan(cases: Sequence[Mapping[str, Any]], variants: Sequence[str], split: str,
         ) -> list[tuple[str, Mapping[str, Any], int]]:  # fmt: skip
    out = []
    for v in variants:
        done = _done(v)
        for case in cases:
            if case["split"] == split and case["id"] not in done:
                out.append((v, case, calls_for(case, v)))
    return out


class Counted:
    """The squire, with every decision counted against the ledger as it is made."""

    def __init__(self, squire: Any, left: int) -> None:
        self.squire, self.left, self.calls, self.usd = squire, left, 0, 0.0

    async def decide(self, point: str, state: Any, questions: Any) -> Any:
        if self.calls >= self.left:
            raise RuntimeError("call cap reached")
        self.calls += 1
        decision = await self.squire.decide(point, state, questions)
        self.usd += float(getattr(decision, "cost_usd", 0.0) or 0.0)
        return decision


async def ask_case(sq: Counted, variant: str, case: Mapping[str, Any]) -> dict[str, Any]:
    rule, request, stored = case["rule"], case["request"], case["stored"]
    row: dict[str, Any] = {"id": case["id"], "variant": variant}
    if variant == "a":
        newer = v82_newer(rule, stored, request)
        d = await sq.decide("memory_rule_superseded", *v82_question(rule, newer))
        probs = {k: float(v) for k, v in (d.answer("superseded").probabilities or {}).items()}
        named = [k for k in probs if k != V82_STANDS]
        if d.failed or V82_STANDS not in probs or not named:
            return {**row, "score": None, "failed": "failed"}
        top = max(named, key=lambda k: probs[k])
        p, stands = round(probs[top], 3), round(probs[V82_STANDS], 3)
        return {**row, "score": p, "stands": stands, "failed": None,
                "v82_suppressed": p >= 0.5 and p > stands}  # fmt: skip
    if variant == "b":
        d = await sq.decide("bench_supersede_b", against_state(rule, request, "now, in the "
                            "request being checked"), {"against": AGAINST})  # fmt: skip
        ans = d.answer("against")
        fail = d.failed or ans.empty
        return {**row, "score": None if fail else ans.truth, "failed": "failed" if fail else None}
    if variant == "d":
        scores, failed = [], None
        for s in stored_since(rule, stored):
            d = await sq.decide("bench_supersede_d", against_state(
                rule, str(s["text"]), f"{mr._when(s['at'])}, as a rule for the project"),
                {"against": AGAINST})  # fmt: skip
            ans = d.answer("against")
            if d.failed or ans.empty:
                failed = "failed"
            else:
                scores.append(round(float(ans.truth), 4))
        return {**row, "scores": scores, "score": max(scores) if scores else None,
                "failed": failed}
    if variant == "c":
        state = {"rule": truncate(str(rule["text"]), points.SENTENCE_MAX),
                 "rule_said": mr._when(rule.get("at")),
                 "request": truncate(request, points.REQUEST_LIMIT),
                 "newer_rule": closest(rule, stored)}  # fmt: skip
        d = await sq.decide("bench_supersede_c", state, {"relation": RELATION_NOW})
        ans = d.answer("relation")
        fail = d.failed or ans.empty or "contradicts" not in (ans.probabilities or {})
        probs = {k: round(float(v), 4) for k, v in (ans.probabilities or {}).items()}
        return {**row, "score": None if fail else probs["contradicts"], "probs": probs,
                "failed": "failed" if fail else None}
    raise ValueError(variant)


async def run_paid(todo: list[tuple[str, Mapping[str, Any], int]], left: int) -> Counted:
    from sanchopanza.harness.claude_code import squire_from_env

    sq = Counted(squire_from_env(redact=True), left)
    gate = asyncio.Semaphore(6)
    OUT.mkdir(parents=True, exist_ok=True)

    async def one(variant: str, case: Mapping[str, Any]) -> None:
        async with gate:
            row = await ask_case(sq, variant, case)
        with _results_path(variant).open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

    await asyncio.gather(*(one(v, c) for v, c, n in todo if n > 0))
    return sq


def run(args: argparse.Namespace) -> int:
    cases = load_cases()
    variants = [v for v in args.variants.split(",") if v]
    assert all(v in VARIANTS for v in variants), variants
    if args.split == "held":
        sel = json.loads((OUT / "selection.json").read_text(encoding="utf-8"))
        # the winner and its cut are frozen in selection.json, from dev only; the other variants
        # are run held out for the report's table, never to choose again
        assert sel["winner"], "no winner on dev: nothing to run held out"
    todo = plan(cases, variants, args.split)
    need = sum(n for _, _, n in todo)
    ledger = _ledger()
    left = CAP - int(ledger["calls"])
    print(f"planned {need} calls for {len(todo)} case-variants; ledger {ledger['calls']} used, "
          f"{left} left of {CAP}")
    if not args.paid:
        return 0
    if need > left:
        print("refusing: the planned calls pass what is left of the cap")
        return 1
    if os.environ.get("SANCHOPANZA_PROVIDER") != "jev" or not os.environ.get("TYPESAFE_API_KEY"):
        print("refusing: needs SANCHOPANZA_PROVIDER=jev and TYPESAFE_API_KEY")
        return 1
    started = time.time()
    sq = asyncio.run(run_paid(todo, need))
    CACHE.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps({
        "calls": int(ledger["calls"]) + sq.calls, "usd": round(ledger["usd"] + sq.usd, 6),
        "runs": [*ledger["runs"], {"at": started, "split": args.split, "variants": variants,
                                   "calls": sq.calls, "usd": round(sq.usd, 6)}]}, indent=1),
        encoding="utf-8")  # fmt: skip
    print(f"made {sq.calls} calls, {sq.usd:.6f} USD")
    return 0


# --- scoring ------------------------------------------------------------------------------------


def answers() -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for v in VARIANTS:
        path = _results_path(v)
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    out.setdefault(v, {})[row["id"]] = row
    return out


def score_of(ans: Mapping[str, Mapping[str, dict]], variant: str, cid: str) -> float | None:
    if variant == "b+d":
        b = ans.get("b", {}).get(cid)
        d = ans.get("d", {}).get(cid)
        if b is None:
            return None
        if b.get("failed") or (d is not None and d.get("failed")):
            return None  # any failure: fail open
        vals = [x for x in (b.get("score"), (d or {}).get("score")) if x is not None]
        return max(vals) if vals else None
    row = ans.get(variant, {}).get(cid)
    if row is None or row.get("failed"):
        return None
    return row.get("score")


def asked(ans: Mapping[str, Mapping[str, dict]], variant: str, case: Mapping[str, Any]) -> bool:
    """Every question the variant needs for `case` was asked. `d` needs none where no rule was
    stored since (fixed 2026-10-05 after the dev run, before reading the selection: those cases
    were dropped from b+d instead of scoring as b alone)."""
    cid = case["id"]
    if variant == "b+d":
        no_d = calls_for(case, "d") == 0
        return cid in ans.get("b", {}) and (no_d or cid in ans.get("d", {}))
    return cid in ans.get(variant, {})


def auc(pos: Sequence[float], neg: Sequence[float]) -> float | None:
    if not pos or not neg:
        return None
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def cut_for(neg: Sequence[float]) -> float:
    top = max(neg) if neg else 0.0
    return max(0.5, round(0.05 * math.ceil(round((top + 0.01) / 0.05, 9)), 2))


def metrics(cases: Sequence[Mapping[str, Any]], ans: Mapping, variant: str, split: str,
            cut: float | None = None) -> dict[str, Any]:  # fmt: skip
    rows = [c for c in cases if c["split"] == split and c["label"] is not None
            and asked(ans, variant, c)]  # fmt: skip
    sc = {c["id"]: score_of(ans, variant, c["id"]) for c in rows}
    failed = [cid for cid, s in sc.items() if s is None]
    pos = [sc[c["id"]] or 0.0 for c in rows if c["label"] == 1]
    neg = [sc[c["id"]] or 0.0 for c in rows if c["label"] == 0]
    if cut is None:
        cut = cut_for(neg)
    own = [sc[c["id"]] or 0.0 for c in rows if c["label"] == 0 and c["family"] == "carry"]
    caught = [p for p in pos if p >= cut]
    return {"variant": variant, "split": split, "n": len(rows), "positives": len(pos),
            "negatives": len(neg), "cut": cut, "true_suppressed": len(caught),
            "false_suppressed": sum(n >= cut for n in neg),
            "own_false_suppressed": sum(n >= cut for n in own),
            "max_negative": round(max(neg), 3) if neg else None,
            "max_own": round(max(own), 3) if own else None,
            "min_caught": round(min(caught), 3) if caught else None,
            "auc": None if auc(pos, neg) is None else round(auc(pos, neg), 3),
            "failed": failed,
            "by_family": {f: {"pos": [round(sc[c["id"]] or 0, 3) for c in rows
                                      if c["family"] == f and c["label"] == 1],
                              "neg_max": max([round(sc[c["id"]] or 0, 3) for c in rows
                                              if c["family"] == f and c["label"] == 0] or [0])}
                          for f in ("real", "carry", "stale", "written")}}  # fmt: skip


def select(_: argparse.Namespace) -> int:
    cases, ans = load_cases(), answers()
    table = [metrics(cases, ans, v, "dev") for v in SCORED if v in ans or v == "b+d"]
    table = [m for m in table if m["n"]]
    per_case = {"a": 1, "b": 1, "c": 1, "b+d": 2}
    best = max(table, key=lambda m: (m["true_suppressed"], m["auc"] or 0,
                                     -per_case[m["variant"]]))  # fmt: skip
    winner = best["variant"] if best["true_suppressed"] > 0 else None
    asks = {"b+d": ["b", "d"]}.get(winner or "", [winner] if winner else [])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "selection.json").write_text(json.dumps(
        {"rule": "most dev positives at a cut over every dev negative (>= 0.5); ties AUC",
         "dev": table, "winner": winner, "cut": best["cut"] if winner else None,
         "winner_asks": asks}, indent=1), encoding="utf-8")  # fmt: skip
    for m in table:
        print({k: m[k] for k in ("variant", "n", "positives", "cut", "true_suppressed",
                                 "false_suppressed", "max_negative", "max_own", "min_caught",
                                 "auc", "failed")})  # fmt: skip
    print("winner:", winner, "cut", best["cut"] if winner else None)
    return 0


def report(_: argparse.Namespace) -> int:
    cases, ans = load_cases(), answers()
    sel = json.loads((OUT / "selection.json").read_text(encoding="utf-8"))
    rows = {"dev": sel["dev"], "held": []}
    cuts = {m["variant"]: m["cut"] for m in sel["dev"]}
    for v in SCORED:
        m = metrics(cases, ans, v, "held", cut=cuts.get(v))
        if m["n"]:
            rows["held"].append(m)
    amb = {}
    for c in cases:
        if c["split"] == "report":
            amb[c["id"]] = {v: score_of(ans, v, c["id"]) for v in SCORED
                            if asked(ans, v, c)}  # fmt: skip
    rows["ambiguous"] = amb
    rows["winner"], rows["cut"] = sel["winner"], sel["cut"]
    rows["ledger"] = _ledger()
    (OUT / "report.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    for m in rows["held"]:
        print("held", {k: m[k] for k in ("variant", "n", "positives", "cut", "true_suppressed",
                                         "false_suppressed", "own_false_suppressed",
                                         "max_negative", "auc", "failed")})  # fmt: skip
    print("ambiguous", amb)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", choices=("build", "plan", "run", "select", "report"))
    parser.add_argument("--variants", default="a,b,c,d")
    parser.add_argument("--split", default="dev", choices=("dev", "held", "report"))
    parser.add_argument("--paid", action="store_true")
    args = parser.parse_args()
    if args.cmd == "build":
        return build()
    if args.cmd in ("plan", "run"):
        return run(args)
    return {"select": select, "report": report}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
