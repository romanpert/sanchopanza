"""The autopilot replayed offline on the context bench's units: arrival and recall.

    python benchmarks/context/simulate.py arrival --estimate      # blocks, Jev calls, USD; no call
    python benchmarks/context/simulate.py arrival --dry           # fake decider, zero cost
    python benchmarks/context/simulate.py recall --estimate
    python benchmarks/context/simulate.py recall --dry [--decider null]
    python benchmarks/context/simulate.py recall --dry --query runtime  # + last call's input

Same units and labels as `run.py` (`build.py`, public OpenHands trajectories, the lexical NEEDED
proxy of `labels.py`).

Registered by Amendment 2 of `prereg.md`: `--live` refuses unless prereg.md carries it and still
hashes to prereg.sha256, records every decision (model pinned) under ~/.cache, stops at
`--max-usd` (<= 0.60), runs in one event loop and counts failed or empty decider calls: a run
with any is marked incomplete and exits non-zero. Criteria and baselines: `criteria.py`,
`baselines.py`.

**Arrival.** Each history tool result is replayed in order through the same code the hook runs
(`sanchopanza.context.arrival.cut`), with the purpose built from the conversation before it
(`arrival.purpose_of`: first and latest prompt, the agent's last text, this call). Per result:
characters the agent would receive (header included) against the original, and for NEEDED
results whether the tokens the future used survive literally in what the agent received
(`all` tokens, and `any`). Everything cut is archived at runtime, so every NEEDED result that
lost a token is `recoverable` by construction; it is reported as such, not as kept.

**Recall.** The history is masked as the autopilot's compaction masks it (`compact` arm `mask`,
last 10 acting turns, last 6 messages kept); every masked result is an archive entry. Then
before each future assistant message a recall runs as the hook would: BM25 top `k` over the
archive entries not yet injected, one `triage_pages` over them, kept ones injected (their
passage that best matches the query, `memory_gate.BODY_LIMIT` characters). The query is built
ONLY from what exists before that message: the latest user prompt and the text of the previous
assistant message (`--query text`, the default); `--query runtime` adds the previous message's
tool inputs, which the PostToolUse hook also sees. A NEEDED result that masking removed is a
hit when it was injected at or before the message that first uses one of its tokens; `literal`
also requires one of those tokens in the injected passage. Leakage audit: for every hit, does
the query that injected it contain one of its needed tokens, and from which part (prompt or
assistant text); by construction the assistant part cannot, since a token in it would be an
earlier first use. Free baselines: BM25 alone injecting its top 1 and top 3 every step.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))


def sibling(name: str):
    """A file of this directory as `context_bench_<name>` (several benches ship a `run.py`)."""
    import importlib.util

    key = f"context_bench_{name}"
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, HERE / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        spec.loader.exec_module(module)
    return sys.modules[key]


run_mod = sibling("run")
CACHE, PINNED_MODEL, load = run_mod.CACHE, run_mod.PINNED_MODEL, run_mod.load
arms_mod = sibling("arms")
metrics = sibling("metrics")
baselines = sibling("baselines")

from sanchopanza import Squire, Thresholds  # noqa: E402
from sanchopanza.context import arrival, blocks, compact  # noqa: E402
from sanchopanza.context.transcript import calls as calls_of  # noqa: E402
from sanchopanza.context.transcript import is_prompt, message_text  # noqa: E402
from sanchopanza.harness import memory_gate as mg  # noqa: E402
from sanchopanza.points import chunks  # noqa: E402
from sanchopanza.points.hierarchy import groups  # noqa: E402
from sanchopanza.redact import redact_secrets  # noqa: E402
from sanchopanza.text import excerpt  # noqa: E402

REGISTERED_CAP_USD = 0.60  # prereg.md, Amendment 2: both simulations together
AMENDMENT = "## Amendment 2 (before any measurement)"


def registered() -> bool:
    """prereg.md carries Amendment 2 and still hashes to prereg.sha256."""
    path = run_mod.RESULTS / "prereg.md"
    if not path.exists() or AMENDMENT not in path.read_text(encoding="utf-8"):
        return False
    return (run_mod.RESULTS / "prereg.sha256").read_text().strip() == run_mod.prereg_hash()


RECORDINGS = CACHE / "recordings-autopilot"
K = mg.K
MASK_TURNS = compact.MASK_TURNS
KEEP_RECENT = 6
SENTENCE_SHARE = 0.2  # central guess: share of prose blocks that clear the 0.75 gate


# --- shared ------------------------------------------------------------------------------------


def squire_for(decider: Any, max_usd: float) -> Squire:
    thresholds = Thresholds().with_(max_usd=max_usd, max_decisions=1_000_000)
    return Squire(decider, thresholds=thresholds, redact=redact_secrets)


def decider_for(mode: str, name: str, piece: str) -> Any:
    from sanchopanza.providers import NullDecider, RecordedDecider, RecordingDecider

    if mode == "dry":
        return NullDecider() if name == "null" else arms_mod.FakeDecider()
    path = RECORDINGS / f"{piece}.jsonl"
    if mode == "replay":
        return RecordedDecider.from_file(path)
    from sanchopanza.providers.jev import JevDecider

    return RecordingDecider(JevDecider(model=PINNED_MODEL), path)


def blob(message: Mapping[str, Any], *, inputs: bool = True) -> str:
    """Text blocks, and tool inputs when asked, of one message (never tool results)."""
    out = []
    for block in message.get("content", []):
        if block.get("type") == "text":
            out.append(str(block.get("text", "")))
        elif inputs and block.get("type") == "tool_use":
            out.append("\n".join(sibling("labels").strings_of(block.get("input"))))
    return "\n".join(out)


def present(tokens: Sequence[str], text: str) -> list[str]:
    """Tokens found in `text` as substrings: literal survival in what the agent received."""
    return [t for t in tokens if t and t in text]


WORDLIKE = re.compile(r"[\w./@~:-]+")


def used(tokens: Sequence[str], text: str) -> list[str]:
    """Tokens `text` uses the way the labels count a use: the same distinctive-token
    extraction (`labels.tokens`), exact membership; an error string (anything with a space or
    a quote) by substring, as `labels.label` matches it."""
    found = sibling("labels").tokens(text)
    return [t for t in tokens if (t in found) if WORDLIKE.fullmatch(t)] + [
        t for t in tokens if not WORDLIKE.fullmatch(t) and t in text
    ]


# --- arrival -----------------------------------------------------------------------------------


async def arrival_unit(unit: Mapping[str, Any], squire: Squire, settings: Any) -> list[dict]:
    history, labels = unit["history"], unit["labels"]
    rows = []
    for call in sorted(calls_of(history), key=lambda c: c.result_msg):
        before = history[: call.result_msg]
        purpose = arrival.purpose_of(before, call.tool, call.input)
        result = await arrival.cut(
            squire,
            call.result,
            tool=call.tool,
            tool_input=call.input,
            purpose=purpose,
            settings=settings,
        )
        cut = result.text is not None
        shown = call.result
        if cut:
            shown = (
                arrival.header(call.tool, len(result.text), call.chars, 0, "ARCHIVE") + result.text
            )
        hits = labels[call.id]["hits"]
        kept = present(hits, shown)
        eligible = arrival.gate(call.result, settings) is None
        budget = len(result.text) if cut else call.chars
        base = baselines.all_of(call, purpose, budget, seed=f"{unit.get('unit', 'u')}:{call.id}")
        rows.append(
            {
                "unit": unit.get("unit", "u"),
                "split": unit.get("split", "test"),
                "eligible": eligible,
                "budget": budget,
                "arrival_tokens_kept": len(present(hits, result.text if cut else call.result)),
                **{f"{name}_tokens_kept": len(present(hits, text)) for name, text in base.items()},
                **{f"{name}_chars": len(text) for name, text in base.items()},
                "tool": call.tool,
                "chars": call.chars,
                "shown": len(shown),
                "cut": cut,
                "reason": result.reason,
                "needed": labels[call.id]["needed"],
                "tokens": len(hits),
                "tokens_kept": len(kept),
                "all_kept": len(kept) == len(hits),
                "any_kept": bool(kept) or not hits,
            }
        )
    return rows


def arrival_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total = sum(r["chars"] for r in rows)
    shown = sum(r["shown"] for r in rows)
    needed = [r for r in rows if r["needed"]]
    cut = [r for r in rows if r["cut"]]
    lost = [r for r in needed if not r["all_kept"]]
    return {
        "results": len(rows),
        "cut": len(cut),
        "chars": total,
        "freed": round(1 - shown / total, 4) if total else 0.0,
        "freed_in_cut": round(1 - sum(r["shown"] for r in cut) / sum(r["chars"] for r in cut), 4)
        if cut
        else 0.0,
        "needed": len(needed),
        "needed_cut": sum(r["cut"] for r in needed),
        "needed_all_tokens_kept": round(sum(r["all_kept"] for r in needed) / len(needed), 4)
        if needed
        else None,
        "needed_any_token_kept": round(sum(r["any_kept"] for r in needed) / len(needed), 4)
        if needed
        else None,
        "token_recall": round(
            sum(r["tokens_kept"] for r in needed) / max(1, sum(r["tokens"] for r in needed)), 4
        ),
        "needed_lost_recoverable": len(lost),  # archived: every cut is recoverable by Read
        "reasons_passed": _count(
            re.sub(r"\d+", "N", r["reason"].split(":")[0]) for r in rows if not r["cut"]
        ),
    }


def _count(items) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        out[item] = out.get(item, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1])[:8])


def _call_tokens(state: Any, qs: Mapping[str, Any]) -> int:
    return metrics._tokens(state, qs)


def arrival_estimate(units: Sequence[Mapping[str, Any]], settings: Any) -> dict[str, Any]:
    eligible = calls = calls_high = tokens = tokens_high = sentence_calls = 0
    for unit in units:
        for call in calls_of(unit["history"]):
            if arrival.gate(call.result, settings):
                continue
            kind = blocks.kind_of(call.tool, call.input, call.result)
            found = blocks.split(call.result, kind)
            if len(found) < 2:
                continue
            eligible += 1
            pages = [("t", b.of(call.result)) for b in found]
            per = [
                _call_tokens(
                    *chunks.context_questions(purpose="x" * 400, pages=[pages[i] for i in g])
                )
                for g in groups(len(pages), chunks.PAGE_MAX)
            ]
            mean = sum(per) / len(per)
            final = (
                0
                if len(pages) <= chunks.PAGE_MAX
                else math.ceil(0.5 * len(pages) / chunks.PAGE_MAX)
            )
            calls += len(per) + final
            tokens += round(sum(per) + final * mean)
            high = 1 if len(pages) <= chunks.PAGE_MAX else len(per) * 4
            calls_high += high
            tokens_high += round(high * mean)
            if kind == "prose" and settings.sentences:
                prose = len(found)
                sentence_calls += math.ceil(SENTENCE_SHARE * prose)
                calls_high += prose
                tokens_high += prose * 450  # one block of sentences, questions included
                tokens += math.ceil(SENTENCE_SHARE * prose) * 450
    return {
        "eligible_results": eligible,
        "calls": calls + sentence_calls,
        "calls_high": calls_high,
        "tokens": tokens,
        "tokens_high": tokens_high,
        "usd": round(metrics.usd(tokens), 4),
        "usd_high": round(metrics.usd(tokens_high), 4),
    }


# --- recall ------------------------------------------------------------------------------------


def masked(history: Sequence[Mapping[str, Any]]) -> list[Any]:
    """The history calls the autopilot's compaction masks (arm `mask`)."""
    found = calls_of(history)
    plan = compact._plan_mask(history, found, keep_recent=KEEP_RECENT, turns=MASK_TURNS)
    stubbed = {s.id for s in plan.steps if s.action == "stub"}
    return [c for c in found if c.id in stubbed]


def query_at(
    history: Sequence[Mapping[str, Any]],
    future: Sequence[Mapping[str, Any]],
    j: int,
    mode: str,
) -> tuple[str, str, str]:
    """(query, prompt part, assistant part) before future message `j`. Only earlier messages."""
    seen = [*history, *future[:j]]
    prompts = [message_text(m) for m in seen if is_prompt(m)]
    prompt = prompts[-1] if prompts else ""
    last = next((m for m in reversed(seen) if m.get("role") == "assistant"), None)
    said = blob(last, inputs=mode == "runtime") if last is not None else ""
    query = f"{prompt[-600:]}\n{said[-600:]}".strip()
    return query, prompt, said


def first_uses(future: Sequence[Mapping[str, Any]], hits: Sequence[str]) -> int | None:
    for j, message in enumerate(future):
        if message.get("role") == "assistant" and used(hits, blob(message)):
            return j
    return None


def entries_of(stubbed: Sequence[Any]) -> list[mg.Memory]:
    return [
        mg.Memory(
            file=c.id,
            name=f"{c.tool} {compact._about(c.input)}".strip(),
            description="archived tool output",
            body=c.result,
            kind="archive",
            search=f"{c.tool} {compact._about(c.input)} {c.result}",
        )
        for c in stubbed
    ]


def _shown(entry: mg.Memory, query: str) -> str:
    return excerpt(entry.body, query, mg.BODY_LIMIT)


async def recall_unit(
    unit: Mapping[str, Any], squire: Squire | None, mode: str, k: int = K
) -> dict[str, Any]:
    history, future, labels = unit["history"], unit["future"], unit["labels"]
    stubbed = masked(history)
    store = entries_of(stubbed)
    arms: dict[str, dict[str, Any]] = {
        name: {"injected": {}, "chars": 0, "texts": {}} for name in ("jev", "bm25@1", "bm25@3")
    }
    steps = asked = 0
    for j, message in enumerate(future):
        if message.get("role") != "assistant":
            continue
        steps += 1
        query, prompt, said = query_at(history, future, j, mode)
        for name, top in (("bm25@1", 1), ("bm25@3", 3)):
            arm = arms[name]
            pool = [m for m in store if m.file not in arm["injected"]]
            for i in mg.bm25_candidates(query, pool, top):
                _inject(arm, pool[i], j, query, prompt, said)
        if squire is None:
            continue
        arm = arms["jev"]
        pool = [m for m in store if m.file not in arm["injected"]]
        candidates = [pool[i] for i in mg.bm25_candidates(query, pool, k)]
        if not candidates:
            continue
        asked += 1
        verdicts = await squire.triage_pages(purpose=query, pages=mg.pages_of(candidates, query))
        if not any(p is not None for _, p in verdicts):
            continue
        for memory, (keep, _) in zip(candidates, verdicts, strict=True):
            if keep:
                _inject(arm, memory, j, query, prompt, said)
    return {
        "unit": unit.get("unit", "u"),
        "split": unit.get("split", "test"),
        "steps": steps,
        "asked": asked,
        "masked": len(stubbed),
        "arms": {name: _score(arm, stubbed, labels, future) for name, arm in arms.items()},
    }


def _inject(arm, memory, j, query, prompt, said) -> None:
    text = _shown(memory, query)
    arm["injected"][memory.file] = j
    arm["texts"][memory.file] = (text, prompt, said)
    arm["chars"] += len(text)


def _score(arm, stubbed, labels, future) -> dict[str, Any]:
    needed = hits = literal = leak_prompt = leak_said = 0
    for call in stubbed:
        label = labels[call.id]
        if not label["needed"]:
            continue
        first = first_uses(future, label["hits"])
        if first is None:
            continue  # used only in a future tool result's shape the proxy counts elsewhere
        needed += 1
        when = arm["injected"].get(call.id)
        if when is None or when > first:
            continue
        hits += 1
        text, prompt, said = arm["texts"][call.id]
        literal += bool(present(label["hits"], text))
        leak_prompt += bool(used(label["hits"], prompt))
        leak_said += bool(used(label["hits"], said))
    injected = len(arm["injected"])
    useful = sum(1 for c in stubbed if c.id in arm["injected"] and labels[c.id]["needed"])
    return {
        "needed_masked": needed,
        "hits": hits,
        "literal_hits": literal,
        "injected": injected,
        "injected_needed": useful,
        "injected_chars": arm["chars"],
        "leak_prompt": leak_prompt,
        "leak_assistant": leak_said,
    }


def recall_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "units": len(rows),
        "steps": sum(r["steps"] for r in rows),
        "jev_calls": sum(r["asked"] for r in rows),
        "masked": sum(r["masked"] for r in rows),
    }
    for name in rows[0]["arms"] if rows else ():
        parts = [r["arms"][name] for r in rows]
        total = {k: sum(p[k] for p in parts) for k in parts[0]}
        n = total["needed_masked"]
        out[name] = {
            **total,
            "hit_rate": round(total["hits"] / n, 4) if n else None,
            "literal_hit_rate": round(total["literal_hits"] / n, 4) if n else None,
            "precision": round(total["injected_needed"] / total["injected"], 4)
            if total["injected"]
            else None,
        }
    return out


def recall_estimate(units: Sequence[Mapping[str, Any]], mode: str, k: int = K) -> dict[str, Any]:
    """Upper bound: one call per future assistant message that has a BM25 candidate."""
    calls = tokens = 0
    for unit in units:
        store = entries_of(masked(unit["history"]))
        for j, message in enumerate(unit["future"]):
            if message.get("role") != "assistant":
                continue
            query, _, _ = query_at(unit["history"], unit["future"], j, mode)
            candidates = [store[i] for i in mg.bm25_candidates(query, store, k)]
            if not candidates:
                continue
            calls += 1
            tokens += _call_tokens(
                *chunks.context_questions(purpose=query, pages=mg.pages_of(candidates, query))
            )
    return {
        "calls_high": calls,
        "tokens_high": tokens,
        "usd_high": round(metrics.usd(tokens), 4),
        "note": "every step asks (none skipped for lack of fresh candidates): an upper bound",
    }


# --- command line ------------------------------------------------------------------------------


def parse(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("piece", choices=("arrival", "recall"))
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry", action="store_true")
    mode.add_argument("--estimate", action="store_true")
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--replay", action="store_true")
    p.add_argument("--decider", choices=("fake", "null"), default="fake")
    p.add_argument("--query", choices=("text", "runtime"), default="text")
    p.add_argument("--threshold", type=int, default=6_000)
    p.add_argument("--k", type=int, default=K)
    p.add_argument("--split", choices=("dev", "test", "all"), default="all")
    p.add_argument("--max-usd", type=float, default=REGISTERED_CAP_USD)
    p.add_argument("--dataset", type=Path, default=CACHE / "dataset")
    p.add_argument("--out", type=Path, default=None)
    return p.parse_args(argv)


async def _run(args: argparse.Namespace, units: Sequence[Mapping[str, Any]], mode: str) -> dict:
    """The whole simulation in ONE event loop; the decider is counted, never trusted blind."""
    counter = arms_mod.CountingDecider(decider_for(mode, args.decider, args.piece))
    squire = squire_for(counter, args.max_usd)
    if args.piece == "arrival":
        settings = arrival.Settings(threshold=args.threshold)
        rows = [r for u in units for r in await arrival_unit(u, squire, settings)]
        summary = arrival_summary(rows)
    else:
        rows = [await recall_unit(u, squire, args.query, args.k) for u in units]
        summary = recall_summary(rows)
    calls = counter.report()
    null = mode == "dry" and args.decider == "null"
    return {
        **summary,
        "jev_spent_usd": round(squire.meter.cost_usd, 6),
        "exhausted": squire.exhausted,
        "decider_calls": calls,
        "complete": (calls["complete"] or null) and not squire.exhausted,
        "rows": rows,
    }


def main(argv: Sequence[str] | None = None) -> dict[str, Any]:
    args = parse(argv)
    units = load(args.dataset, args.split)
    settings = arrival.Settings(threshold=args.threshold)
    if args.estimate:
        report = (
            arrival_estimate(units, settings)
            if args.piece == "arrival"
            else recall_estimate(units, args.query, args.k)
        )
        report = {"piece": args.piece, "units": len(units), "model": PINNED_MODEL, **report}
        print(json.dumps(report, indent=1))
        return report
    mode = "live" if args.live else "replay" if args.replay else "dry"
    if args.live:
        if not registered():
            raise SystemExit("not registered: prereg.md lacks Amendment 2 or its hash moved")
        if args.split != "all" or not units:
            raise SystemExit("the live run scores dev and test together (--split all), on units")
        if args.max_usd > REGISTERED_CAP_USD:
            raise SystemExit(f"--max-usd above {REGISTERED_CAP_USD}: refused")
        high = (
            arrival_estimate(units, settings)
            if args.piece == "arrival"
            else recall_estimate(units, args.query, args.k)
        )["usd_high"]
        if high > args.max_usd:
            raise SystemExit(f"high estimate {high} USD exceeds --max-usd: refused")
    report = {
        "piece": args.piece,
        "mode": mode,
        "query": args.query,
        "units": len(units),
        **asyncio.run(_run(args, units, mode)),
    }
    rows = report.pop("rows")
    out = args.out or CACHE / f"simulate-{args.piece}-{mode}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({**report, "rows": rows}, indent=1), encoding="utf-8")
    judged = sibling("criteria").judge(args.piece, rows)
    report = {**report, "criteria": judged}
    if mode != "dry":
        published = run_mod.RESULTS / f"simulate-{args.piece}.json"
        published.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    print(f"written {out}")
    if not report["complete"]:
        raise SystemExit("decider calls failed, came back empty or ran in several event loops")
    return report


if __name__ == "__main__":
    main()
