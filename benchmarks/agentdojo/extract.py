"""A harvested injection bench, built from AgentDojo rather than written by us.

    python benchmarks/agentdojo/extract.py --out benches/agentdojo-injection.jsonl

Free: no model is called. It replays each task's ground truth inside AgentDojo's own
environments, which is deterministic Python, and writes labelled cases.

Why this file exists. `benches/safety.jsonl` has 28 injection cases and its own header says
they were *written, not harvested*, by the same person who wrote the question they are
scored against. That is the weakest shape of evidence a security control can have, and
a harvested set is what it needs (`docs/paper.md` Section 5.2). AgentDojo (Debenedetti et
al., NeurIPS 2024 Datasets and Benchmarks, MIT licence) supplies one for free: four
application suites, 97 user tasks, 35 injection goals and 17 attack templates, none of them
ours.

**How the labels are made, and why they are not opinions.** AgentDojo places injections
through named slots in its environments, and its attack machinery can fill every slot with a
canary string instead of a payload. So the procedure is: run a task's ground truth once with
canaries, find the tool-result messages that actually reach the agent, and then build each
case by substituting into that same message either the attack payload (positive) or the
slot's own benign default (negative). Positive and negative are therefore **the same tool
output differing only by the injected text**. The label comes from what was substituted, not
from an annotator, so there is no second-annotator question here at all.

**What this bench is really for.** Detecting a template attack is the easy half - a regular
expression does it - and a bench of template attacks alone would flatter any detector. The
number that decides whether a detector can ship is the **false-positive rate on ordinary
application data**: calendars, invoices, emails and chat logs, full of instructions aimed at
people. Those negatives are the point. They are also the half our hand-written set was
weakest on, with 16 negatives that we invented ourselves.

Three things are recorded per case so that the analysis can ask more than "was it right":
the attack template, the character length of the text, and where in it the payload sits.
The last one exists because this repository has already shipped one length bug of exactly
that shape - triage judged a 10,000-character document by its first 1,500 - and the
injection question truncates rather than excerpting.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from collections import Counter
from typing import Any

# Attacks in the order they are cycled. Deliberately mixed: four families of
# "do this other thing instead" and four denial-of-service templates, which ask the agent to
# refuse rather than to act and are the ones a keyword rule is worst at.
ATTACK_NAMES = (
    "important_instructions",
    "ignore_previous",
    "injecagent",
    "system_message",
    "tool_knowledge",
    "important_instructions_no_names",
    "direct",
    "captcha_dos",
    "felony_dos",
    "swearwords_dos",
    "offensive_email_dos",
    "dos",
)
SUITES = ("workspace", "travel", "banking", "slack")
VERSION = "v1.2.2"


class _StubPipeline:
    """Enough of a pipeline for the attacks that want to name the victim model."""

    name = "claude-3-5-sonnet-20241022"

    def query(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover - never called
        raise NotImplementedError


def _tool_name(message: Any) -> str:
    call = message.get("tool_call")
    return str(getattr(call, "function", "") or "")


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def collect(limit_per_suite: int, quiet: bool = False) -> list[dict[str, Any]]:
    from agentdojo.agent_pipeline.ground_truth_pipeline import GroundTruthPipeline
    from agentdojo.attacks.attack_registry import ATTACKS
    from agentdojo.functions_runtime import FunctionsRuntime
    from agentdojo.task_suite.load_suites import get_suites
    from agentdojo.types import get_text_content_as_str

    suites = get_suites(VERSION)
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()

    for suite_name in SUITES:
        suite = suites[suite_name]
        defaults = suite.get_injection_vector_defaults()
        canaries = {slot: f"<CANARY---{slot}--->" for slot in defaults}
        attacks = {}
        for name in ATTACK_NAMES:
            if name in ATTACKS:
                try:
                    attacks[name] = ATTACKS[name](suite, _StubPipeline())
                except Exception as error:  # an attack that will not build is skipped loudly
                    print(f"  {suite_name}: attack {name} unavailable ({error})", file=sys.stderr)
        injection_tasks = list(suite.injection_tasks.values())
        # Attack-minor so that consecutive cases rotate through templates: ordering it
        # the other way spends the whole quota on the first attack, which a pilot did.
        pairs = [(a, t) for t in injection_tasks for a in attacks]
        taken = 0

        for task_index, user_task in enumerate(suite.user_tasks.values()):
            if taken >= limit_per_suite:
                break
            runtime = FunctionsRuntime(suite.tools)
            environment = suite.load_and_inject_default_environment(canaries)
            try:
                _, _, _, messages, _ = GroundTruthPipeline(user_task).query(
                    user_task.PROMPT, runtime, environment
                )
            except Exception as error:
                if not quiet:
                    print(f"  {suite_name}/{user_task.ID}: {error}", file=sys.stderr)
                continue

            for message_index, message in enumerate(messages):
                if message.get("role") != "tool" or not message.get("content"):
                    continue
                text = get_text_content_as_str(message["content"]) or ""
                if not text.strip():
                    continue
                present = [slot for slot in canaries if canaries[slot] in text]

                # The negative: this same tool output with every slot holding its own
                # benign default. Ordinary application data, including the instructions
                # real invoices and calendars address to people.
                clean = text
                for slot, canary in canaries.items():
                    clean = clean.replace(canary, defaults[slot])
                key = _digest(clean)
                if key not in seen and clean.strip():
                    seen.add(key)
                    cases.append(
                        _case(
                            f"ad-{suite_name}-{task_index:02d}-{message_index:02d}-clean",
                            user_task.PROMPT,
                            clean,
                            False,
                            suite=suite_name,
                            attack=None,
                            tool=_tool_name(message),
                        )
                    )

                if not present:
                    continue
                # The positive: the same message again, one slot carrying a real payload.
                attack_name, injection_task = pairs[taken % len(pairs)]
                payloads = attacks[attack_name].attack(user_task, injection_task)
                slot = present[0]
                payload = payloads.get(slot)
                if not payload:
                    continue
                attacked = text.replace(canaries[slot], payload)
                for other, canary in canaries.items():
                    attacked = attacked.replace(canary, defaults[other])
                key = _digest(attacked)
                if key in seen:
                    continue
                seen.add(key)
                cases.append(
                    _case(
                        f"ad-{suite_name}-{task_index:02d}-{message_index:02d}-{attack_name}",
                        user_task.PROMPT,
                        attacked,
                        True,
                        suite=suite_name,
                        attack=attack_name,
                        tool=_tool_name(message),
                        injection_task=injection_task.ID,
                        payload_at=attacked.find(payload[:60]),
                    )
                )
                taken += 1

    return cases


def _case(case_id: str, purpose: str, text: str, expected: bool, **meta: Any) -> dict[str, Any]:
    return {
        "id": case_id,
        "point": "injection",
        "input": {"purpose": purpose, "text": text},
        "expected": expected,
        "meta": {"chars": len(text), **meta},
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default="benches/agentdojo-injection.jsonl")
    p.add_argument("--per-suite", type=int, default=45, help="positives to take from each suite")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    try:
        cases = collect(args.per_suite, quiet=args.quiet)
    except ImportError as error:
        print(f"install agentdojo first: {error}", file=sys.stderr)
        return 2

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "# Injection cases harvested from AgentDojo " + VERSION + " (MIT, Debenedetti et al.,",
        "# NeurIPS 2024 D&B). Labels are by construction: a positive and a negative differ",
        "# only by the substituted payload. Regenerate with benchmarks/agentdojo/extract.py.",
    ]
    out.write_text(
        "\n".join(header + [json.dumps(c, ensure_ascii=False) for c in cases]) + "\n",
        encoding="utf-8",
    )

    positives = [c for c in cases if c["expected"]]
    negatives = [c for c in cases if not c["expected"]]
    lengths = sorted(c["meta"]["chars"] for c in cases)
    beyond = [
        c
        for c in positives
        if c["meta"].get("payload_at", 0) >= 2000  # points.injection.TEXT_LIMIT
    ]
    print(f"{len(cases)} cases -> {out}")
    print(f"  {len(positives)} positive, {len(negatives)} negative")
    print(f"  by suite: {dict(Counter(c['meta']['suite'] for c in cases))}")
    print(f"  by attack: {dict(Counter(c['meta']['attack'] for c in positives))}")
    if lengths:
        print(
            f"  text length: median {lengths[len(lengths) // 2]}, "
            f"max {lengths[-1]}, over 2000 chars: {sum(1 for n in lengths if n > 2000)}"
        )
    print(f"  payloads starting beyond the 2000-character limit: {len(beyond)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
