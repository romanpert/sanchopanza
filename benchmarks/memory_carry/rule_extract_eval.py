"""Offline: does Jev pick, sentence by sentence, the standing rules out of what a person writes?

v7's standing rules come only from the person's own prompt text (never from tool output or
files: a poisoned memory persists, MemSecBench 2026). Each sentence of a request is asked one
Truth question with the whole request as context. Measured on:
- the carry scenes: the 16 rule sentences (`rules.py`) are positives; the other sentences of
  session 1's prompts and every sentence of session 2's prompts are negatives;
- real prompts from SWE-chat (the cached transcripts): every sentence flagged is printed for a
  person to judge, and the rate per prompt is the noise a project would carry.
Answers are recorded to `rule_extract_fixture.jsonl` and replayed.

    python benchmarks/memory_carry/rule_extract_eval.py [--live] [--real 200]
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import random
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "src"))

from rule_check_eval import api_key  # noqa: E402
from rules import RULES  # noqa: E402
from scenes import SCENES  # noqa: E402
from scenes_held import HELD  # noqa: E402

from sanchopanza.points.rules import questions_for_sentence, sentences  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider  # noqa: E402

FIXTURE = HERE / "rule_extract_fixture.jsonl"
POINT = "memory.standing_rule"
SWE_CHAT = Path.home() / ".cache" / "sanchopanza" / "candor-external" / "swe-chat" / "transcripts"


def scene_cases() -> list[dict[str, Any]]:
    out = []
    for name, scene in {**SCENES, **HELD}.items():
        rule = RULES[name]
        for text in sentences(scene["first"]):
            out.append({"source": f"scene:{name}:first", "sentence": text,
                        "request": scene["first"],
                        "rule": text in rule or rule in text})  # fmt: skip
        for text in sentences(scene["second"]):
            out.append({"source": f"scene:{name}:second", "sentence": text,
                        "request": scene["second"], "rule": False})  # fmt: skip
    return out


def real_prompts(count: int, seed: int = 20261002) -> list[str]:
    prompts = []
    for path in sorted(glob.glob(str(SWE_CHAT / "*.jsonl"))):
        for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            message = event.get("message") if isinstance(event, dict) else None
            content = message.get("content") if isinstance(message, dict) else None
            if event.get("type") == "user" and isinstance(content, str) \
                    and 30 < len(content) < 2000 and not content.startswith("<"):
                prompts.append(content)
    unique = sorted(set(prompts))
    random.Random(seed).shuffle(unique)
    return unique[:count]


def real_cases(count: int) -> list[dict[str, Any]]:
    return [{"source": f"real:{i}", "sentence": text, "request": prompt, "rule": None}
            for i, prompt in enumerate(real_prompts(count))
            for text in sentences(prompt)]  # fmt: skip


async def answer(items: list[dict[str, Any]], live: bool) -> float:
    recorded = RecordedDecider.from_file(FIXTURE) if FIXTURE.exists() else None
    writer = RecordingDecider(create("jev", api_key=api_key()), FIXTURE) if live else None
    gate, spent = asyncio.Semaphore(6), 0.0

    async def one(case: dict[str, Any]) -> None:
        nonlocal spent
        state, questions = questions_for_sentence(case["sentence"], case["request"])
        if recorded is not None:
            d = await recorded.decide(POINT, state, questions)
            if d.answers:
                case["p"] = d.answer("rule").truth
                return
        if writer is None:
            return
        async with gate:
            d = await writer.decide(POINT, state, questions)
            spent += d.cost_usd
            case["p"] = d.answer("rule").truth

    await asyncio.gather(*(one(c) for c in items))
    return spent


def report(items: list[dict[str, Any]], cut: float) -> None:
    scene = [c for c in items if c["rule"] is not None and c.get("p") is not None]
    pos = [c for c in scene if c["rule"]]
    neg = [c for c in scene if not c["rule"]]
    print(f"scenes: {len(pos)} rule sentences, {len(neg)} others")
    print(f"  recall at {cut}: {sum(c['p'] >= cut for c in pos)}/{len(pos)}; "
          f"false flags: {sum(c['p'] >= cut for c in neg)}/{len(neg)}")  # fmt: skip
    for c in sorted(pos, key=lambda c: c["p"])[:6]:
        print(f"  lowest rule {c['p']:.2f}: {c['sentence'][:110]}")
    for c in sorted(neg, key=lambda c: -c["p"])[:6]:
        print(f"  highest other {c['p']:.2f}: {c['sentence'][:110]}")
    real = [c for c in items if c["rule"] is None and c.get("p") is not None]
    prompts = {c["source"] for c in real}
    flagged = [c for c in real if c["p"] >= cut]
    print(f"real: {len(prompts)} prompts, {len(real)} sentences, {len(flagged)} flagged "
          f"({len({c['source'] for c in flagged})} prompts with one or more)")  # fmt: skip
    for c in sorted(flagged, key=lambda c: -c["p"]):
        print(f"  {c['p']:.2f} [{c['source']}] {c['sentence'][:160]!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--real", type=int, default=200)
    parser.add_argument("--cut", type=float, default=0.5)
    args = parser.parse_args(argv)
    items = scene_cases() + real_cases(args.real)
    spent = asyncio.run(answer(items, args.live))
    print(f"jev: {spent:.4f} USD, {len(items)} sentences")
    report(items, args.cut)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
