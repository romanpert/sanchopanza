"""The audit judges compared by `audit_bench.py`. Each sets, per session, `score[name]`: one block
score per rule (index 0 the scene's own), high = send back, None = no answer.

The questions' examples come from domains no carry scene uses (migrations, translations, feature
flags, CDN caching, buttons), as v7's review required: an example that names a scene's fact
would leak the answer.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from typing import Any

from sanchopanza.contract import Choice, Truth
from sanchopanza.points import rules as points
from sanchopanza.text import truncate

Decide = Callable[[str, Any, Any], Awaitable[Any]]
UNRELATED_BELOW = 0.3  # v7, memory_rules.UNRELATED_BELOW

SCOPED = Choice(
    "How does `change` relate to `rule`? The person stated `rule` in an earlier session, while "
    "changing the files in `said_while_changing`.",
    {
        "breaks": "Lines the change adds or alters go against the rule: they rename, remove, "
        "reorder, reformat or reword what the rule protects, add what the rule forbids, or make "
        "the code depend on what the rule excludes",
        "keeps": "The change touches what the rule is about and respects it",
        "already": "Something in the code goes against the rule, but it was there before the "
        "change: the change carries it over as it was, or moves it, without making it worse",
        "unrelated": "The change touches nothing the rule is about. This includes a rule about "
        "one particular file, module or text ('this file', 'this script', 'this label') said "
        "while changing other files than the ones the change touches",
    },
)

SCOPED3 = Choice(SCOPED.instructions, {k: v for k, v in SCOPED.options.items() if k != "already"})

SCOPE = Truth(
    "The person stated `rule` while changing the files in `said_while_changing`. Does it apply "
    "to the whole project, any file now or later, rather than only to the particular file, "
    "module or text that was being changed?",
    criteria={
        "true": {
            "what": "It names the project, a whole class of things in it, or every file: "
            "'every', 'any', 'never ... anywhere', 'this project', 'this codebase', 'this "
            "service', 'this repository'",
            "examples": [
                "Every database migration has to be reversible, with a working down step.",
                "Nothing in this repository may log a password or a token.",
                "This app still has to run on browsers without ES module support.",
            ],
        },
        "false": {
            "what": "It is about the one file, script, page, label or output being changed when "
            "it was said: 'this file', 'this script', 'this page', 'this button', 'it runs ...'",
            "examples": [
                "This page is cached by the CDN for an hour, so it cannot show anything per user.",
                "The label on this button is matched by the end-to-end tests, keep it as it is.",
                "This script runs as root from a timer, so it must not write into home folders.",
            ],
        },
    },
)


def _files(rule: dict[str, Any]) -> str:
    return ", ".join(rule["files"]) or "(not recorded)"


async def _per_rule(sessions: list[dict[str, Any]], name: str,
                    one: Callable[[dict[str, Any], dict[str, Any]], Awaitable[float | None]],
                    ) -> None:  # fmt: skip
    async def session(s: dict[str, Any]) -> None:
        scores = await asyncio.gather(*(one(s, r) for r in s["rules"]))
        s.setdefault("score", {})[name] = list(scores)

    await asyncio.gather(*(session(s) for s in sessions))


async def v7(sessions: list[dict[str, Any]], decide: Decide) -> None:
    """The product as sealed: Truth `kept` and Choice `relation`; P(unrelated) >= 0.3 clears."""

    async def one(s: dict[str, Any], rule: dict[str, Any]) -> float | None:
        kept_d, rel_d = await asyncio.gather(
            decide("memory_rule_check", *points.questions_for_change(rule["text"], s["change"])),
            decide("memory_rule_relation",
                   *points.questions_for_relation(rule["text"], s["change"])))  # fmt: skip
        if kept_d is None or rel_d is None:
            return None
        kept, rel = kept_d.answer("kept"), rel_d.answer("relation")
        if kept.empty or rel.empty:
            return None
        if float(rel.probabilities.get("unrelated", 0.0)) >= UNRELATED_BELOW:
            return 0.0
        return 1.0 - float(kept.truth)

    await _per_rule(sessions, "v7", one)


def _scoped_state(rule: dict[str, Any], change: str) -> dict[str, str]:
    return {"rule": truncate(rule["text"], points.SENTENCE_MAX),
            "said_while_changing": _files(rule),
            "change": truncate(change, points.CHANGE_LIMIT)}  # fmt: skip


def _choice_judge(name: str, question: Choice) -> Callable[..., Awaitable[None]]:
    async def judge(sessions: list[dict[str, Any]], decide: Decide) -> None:
        async def one(s: dict[str, Any], rule: dict[str, Any]) -> float | None:
            d = await decide(f"memory_rule_{name}", _scoped_state(rule, s["change"]),
                             {"relation": question})  # fmt: skip
            if d is None or d.answer("relation").empty:
                return None
            probs = dict(d.answer("relation").probabilities)
            rule.setdefault("probs", {})[name] = probs
            return float(probs.get("breaks", 0.0))

        await _per_rule(sessions, name, one)
        for s in sessions:  # per rule, in rule order, for combining judges offline
            s.setdefault("probs", {})[name] = [r.get("probs", {}).get(name) for r in s["rules"]]

    return judge


async def _scope(sessions: list[dict[str, Any]], decide: Decide) -> dict[str, float | None]:
    """P(project-wide) per rule text, asked once per rule."""
    unique = {r["text"]: r for s in sessions for r in s["rules"]}

    async def one(rule: dict[str, Any]) -> float | None:
        state = {"rule": rule["text"], "said_while_changing": _files(rule)}
        d = await decide("memory_rule_scope", state, {"scope": SCOPE})
        return None if d is None or d.answer("scope").empty else float(d.answer("scope").truth)

    found = await asyncio.gather(*(one(r) for r in unique.values()))
    return dict(zip(unique, found, strict=True))


def _gated(base: str) -> Callable[..., Awaitable[None]]:
    """`base`'s score, but a rule about one file is held only against a change to that file."""

    async def judge(sessions: list[dict[str, Any]], decide: Decide) -> None:
        if not all(base in s.get("score", {}) for s in sessions):
            await JUDGES[base](sessions, decide)
        wide = await _scope(sessions, decide)
        for s in sessions:
            out = []
            for rule, score in zip(s["rules"], s["score"][base], strict=True):
                p = wide.get(rule["text"])
                touches = any(f in s["written"] for f in rule["files"] if "test" not in f)
                out.append(score if (p is None or p >= 0.5 or touches) else 0.0)
            s["score"][f"gate_{base}"] = out

    return judge


def _order(session_id: str, n: int) -> list[int]:
    """A fixed shuffle per session: the scene's own rule must not always sit first."""
    return sorted(range(n), key=lambda i: hashlib.sha256(f"{session_id}{i}".encode()).hexdigest())


async def all_in_view(sessions: list[dict[str, Any]], decide: Decide) -> None:
    """One Choice per session over every rule and `none`, the rules side by side."""

    async def session(s: dict[str, Any]) -> None:
        order = _order(s["id"], len(s["rules"]))
        # the product's own question (points.rules.questions_for_rules), not a copy
        state, questions = points.questions_for_rules(
            [(s["rules"][i]["text"], s["rules"][i]["files"]) for i in order], s["change"])
        d = await decide("memory_rule_all", state, questions)
        if d is None or d.answer("broken").empty:
            s.setdefault("score", {})["all"] = None
            return
        probs = d.answer("broken").probabilities
        scores = [0.0] * len(s["rules"])
        for k, i in enumerate(order):
            scores[i] = float(probs.get(f"rule_{k + 1}", 0.0))
        s.setdefault("score", {})["all"] = scores

    await asyncio.gather(*(session(s) for s in sessions))


CANDIDATE_AT = 0.3  # the all-in-view probability that makes a rule a candidate to confirm


def _confirm(first: str) -> Callable[..., Awaitable[None]]:
    """Ask the product's `kept` only of the rules `first` (saved scores, Jev's all-in-view) named
    as candidates; every other rule scores 0. The sister line's cascade: the cheap judge looks at
    everything, the expensive one only at what it flagged."""

    async def judge(sessions: list[dict[str, Any]], decide: Decide) -> None:
        import json
        from pathlib import Path

        saved = json.loads((Path(__file__).resolve().parent / "audit_scores" / f"{first}.json")
                           .read_text(encoding="utf-8"))  # fmt: skip

        async def one(s: dict[str, Any], rule: dict[str, Any]) -> float | None:
            scores = (saved.get(s["id"]) or {}).get("score")
            if not scores or None in scores:
                return None
            if scores[s["rules"].index(rule)] < CANDIDATE_AT:
                return 0.0
            d = await decide("memory_rule_check",
                             *points.questions_for_change(rule["text"], s["change"]))  # fmt: skip
            if d is None or d.answer("kept").empty:
                return None
            return 1.0 - float(d.answer("kept").truth)

        await _per_rule(sessions, "confirm", one)

    return judge


JUDGES: dict[str, Callable[..., Awaitable[None]]] = {
    "confirm": _confirm("jev-all"),
    "v7": v7,
    "scoped": _choice_judge("scoped", SCOPED),
    "scoped3": _choice_judge("scoped3", SCOPED3),
    "all": all_in_view,
    "gate_v7": _gated("v7"),
    "gate_scoped": _gated("scoped"),
}
