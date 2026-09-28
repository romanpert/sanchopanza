"""The auto-memory recall gate on this machine's own sessions
(`docs/results/2026-09-28-memory-gate/prereg.md`).

python benchmarks/memory_gate/run.py --record-hash    # once, before anything is measured
python benchmarks/memory_gate/run.py --dry            # build labels, baselines, null gate: free
python benchmarks/memory_gate/run.py --estimate       # expected Jev calls, tokens, USD: free
python benchmarks/memory_gate/run.py --live --owner-consent --max-usd 0.70 --env-file PATH  # part B

Everything built (prompts, memories, recorded decisions) goes to
`~/.cache/sanchopanza/memory_gate/`, never into the repository: it is private text. What this
prints and what `--out` writes are aggregates, with project names hashed.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import math
import os
import pathlib
import random
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import labels  # noqa: E402

from sanchopanza import Squire, Thresholds  # noqa: E402
from sanchopanza.harness import memory_gate as mg  # noqa: E402
from sanchopanza.points import chunks, hierarchy, memory  # noqa: E402
from sanchopanza.providers.jev import DEFAULT_PRICE_PER_MTOK, to_wire  # noqa: E402
from sanchopanza.providers.null import NullDecider  # noqa: E402
from sanchopanza.redact import redact_secrets  # noqa: E402


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


triage_run = _load("triage_sets_run", ROOT / "benchmarks" / "triage_sets" / "run.py")

RESULTS = ROOT / "docs" / "results" / "2026-09-28-memory-gate"
PROJECTS = pathlib.Path.home() / ".claude" / "projects"
# Always this path, never the legacy ~/.cache/sancho: the brief of this benchmark names it.
CACHE = pathlib.Path.home() / ".cache" / "sanchopanza" / "memory_gate"
MIN_MEMORIES = 8
ELSEWHERE = 1  # amendment 2: used in any other project -> general vocabulary
ALL_CAP = 25_000
GATE_CAP = mg.CAP
BM25_K = (1, 3, 5)
SAMPLE = 300
POSITIVES = 150
SEED = 20260928
# Characters of the JSON body per billed input token, MEASURED on the 322 recorded
# `memory_write` calls of fixtures/memory-common.jsonl: median 3.01, minimum 2.64. Central and
# pessimistic. (A first guess of 4 / 3 underestimated the cost by a quarter.)
CHARS_PER_TOKEN = (3.0, 2.64)


def project_hash(name: str) -> str:
    return hashlib.sha256(name.encode("utf-8")).hexdigest()[:10]


def prereg_hash() -> str:
    raw = (RESULTS / "prereg.md").read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


def require_prereg() -> None:
    registered = RESULTS / "prereg.sha256"
    if not registered.exists() or registered.read_text().strip() != prereg_hash():
        raise SystemExit("prereg.md changed or was never hashed: nothing spent")


# --- build ------------------------------------------------------------------------------


def _birth(path: pathlib.Path) -> float:
    stat = path.stat()
    return float(getattr(stat, "st_birthtime", 0.0) or stat.st_ctime)


def _claude_md(sessions: Sequence[Sequence[Mapping[str, Any]]]) -> str:
    for rows in sessions:
        for row in rows:
            cwd = row.get("cwd")
            if cwd:
                path = pathlib.Path(str(cwd)) / "CLAUDE.md"
                try:
                    return path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    return ""
    return ""


def _assistant_rows(path: pathlib.Path) -> list[dict[str, Any]]:
    """Only the assistant entries of a transcript: the vocabulary pass reads 1.4 GB."""
    out: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if '"type":"assistant"' not in line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and not row.get("isSidechain"):
                out.append(row)
    return out


def vocabulary(root: pathlib.Path = PROJECTS) -> dict[str, int]:
    """Token -> number of projects whose assistant used it. Cached: it scans every transcript.

    Project directories that differ only by case (`C--x` and `c--x`) are one project."""
    cached = CACHE / "vocabulary.json"
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    per_project: dict[str, set[str]] = {}
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        tokens: set[str] = set()
        for path in sorted(directory.glob("*.jsonl")):
            tokens |= set(labels.assistant_tokens(_assistant_rows(path)))
        key = directory.name.lower()
        per_project[key] = per_project.get(key, set()) | tokens
    counts: dict[str, int] = {}
    for tokens in per_project.values():
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1
    CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(counts), encoding="utf-8")
    return counts


def build_project(
    directory: pathlib.Path, vocab: Mapping[str, int] | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """(cases, memories) of one project, redacted. Empty when it does not qualify."""
    memories = mg.load_memories(directory / "memory")
    transcripts = sorted(directory.glob("*.jsonl"))
    if len(memories) < MIN_MEMORIES or not transcripts:
        return [], {}
    name, key = directory.name, project_hash(directory.name)
    sessions = [labels.entries(p) for p in transcripts]
    touches = labels.first_touches(sessions, name)
    born = {}
    for m in memories:
        first = [t for t in (_birth(directory / "memory" / m.file), touches.get(m.file)) if t]
        born = {**born, m.file: min(first) if first else 0.0}
    index_path = directory / "memory" / mg.INDEX
    index = index_path.read_text(encoding="utf-8", errors="replace") if index_path.is_file() else ""
    shared = index + "\n" + _claude_md(sessions)
    tokens = labels.unique_tokens({m.file: f"{m.name}\n{m.text}" for m in memories}, shared)
    used_here: dict[str, float] = {}
    for rows in sessions:
        for token, t in labels.assistant_tokens(rows).items():
            if token not in used_here or (t and t < used_here[token]):
                used_here[token] = t
    vocab = vocab or {}
    elsewhere = {**vocab, **{t: vocab.get(t, 0) - 1 for t in used_here if t in vocab}}
    tokens = labels.recallable_tokens(tokens, born, used_here, elsewhere, elsewhere=ELSEWHERE)
    cases: list[dict[str, Any]] = []
    for path, rows in zip(transcripts, sessions, strict=True):
        session = project_hash(path.stem)
        for case in labels.cases_of_session(
            rows, project=name, session=session, born=born, tokens=tokens
        ):
            if not case.available:
                continue
            row = {**asdict(case), "project": key, "relevant": list(case.relevant)}
            cases = [*cases, redact_secrets(row)]
    stored = {
        m.file: {"name": m.name, "description": m.description, "body": m.body, "born": born[m.file]}
        for m in memories
    }
    return cases, {key: stored}


def build(root: pathlib.Path = PROJECTS) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    memories: dict[str, Any] = {}
    vocab = vocabulary(root)
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        got, mems = build_project(directory, vocab)
        cases, memories = [*cases, *got], {**memories, **mems}
    return cases, memories


def save(cases: list[dict[str, Any]], memories: dict[str, Any]) -> str:
    CACHE.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(c, ensure_ascii=False, sort_keys=True) + "\n" for c in cases)
    (CACHE / "cases.jsonl").write_text(text, encoding="utf-8")
    (CACHE / "memories.json").write_text(json.dumps(memories, ensure_ascii=False), encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- arms -------------------------------------------------------------------------------


def available(case: Mapping[str, Any], memories: Mapping[str, Any]) -> list[mg.Memory]:
    store = memories[case["project"]]
    return [
        mg.Memory(f, store[f]["name"], store[f]["description"], store[f]["body"])
        for f in case["available"]
        if f in store
    ]


def arm_all(case: Mapping[str, Any], ms: Sequence[mg.Memory]) -> tuple[str, tuple[str, ...]]:
    context, shown, _ = mg.render(ms, cap=ALL_CAP)
    return context, shown


def arm_bm25(
    case: Mapping[str, Any], ms: Sequence[mg.Memory], k: int
) -> tuple[str, tuple[str, ...]]:
    docs = [f"{m.name} {m.text}" for m in ms]
    scores = triage_run.bm25_scores(case["prompt"], docs) if docs else []
    ranked = sorted((s, i) for i, s in enumerate(scores) if s > 0)[::-1][:k]
    context, shown, _ = mg.render([ms[i] for _, i in ranked], cap=GATE_CAP)
    return context, shown


async def arm_gate(
    squire: Squire, case: Mapping[str, Any], ms: Sequence[mg.Memory]
) -> dict[str, tuple[str, tuple[str, ...]]]:
    """`triage` and `gate` from one set of answers: both calls are always made."""
    prompt = redact_secrets(case["prompt"])
    recall = await squire.needs_recall(prompt, topics=mg.topics_of(ms))
    verdicts = await mg.triage_memories(squire, prompt, ms)
    if not any(p is not None for _, p in verdicts):
        triage = ("", ())
    else:
        kept = [m for m, _ in mg.order_kept(ms, verdicts)]
        context, shown, _ = mg.render(kept, cap=GATE_CAP)
        triage = (context, shown)
    gate = triage if recall.look else ("", ())
    return {"triage": triage, "gate": gate}


def metrics(rows: Sequence[Mapping[str, Any]], arm: str) -> dict[str, Any]:
    rel = inj = hit = hit_read = rel_read = hit_quoted = rel_quoted = 0
    complete = with_rel = quiet = without = chars = 0
    for row in rows:
        relevant = set(row["relevant"])
        read = relevant & set(row["read"])
        quoted = relevant & set(row["quoted"])
        context, shown = row["arms"][arm]
        shown = set(shown)
        chars += len(context)
        inj += len(shown)
        hit += len(shown & relevant)
        rel += len(relevant)
        hit_read, rel_read = hit_read + len(shown & read), rel_read + len(read)
        hit_quoted, rel_quoted = hit_quoted + len(shown & quoted), rel_quoted + len(quoted)
        if relevant:
            with_rel += 1
            complete += relevant <= shown
        else:
            without += 1
            quiet += not shown
    n = len(rows)

    def ratio(a: int, b: int) -> float | None:
        return round(a / b, 4) if b else None

    return {
        "recall": ratio(hit, rel),
        "recall_read": ratio(hit_read, rel_read),
        "recall_quoted": ratio(hit_quoted, rel_quoted),
        "complete": ratio(complete, with_rel),
        "chars": round(chars / n, 1) if n else None,
        "precision": ratio(hit, inj),
        "quiet": ratio(quiet, without),
        "injected_per_prompt": round(inj / n, 2) if n else None,
    }


async def evaluate(
    cases: Sequence[Mapping[str, Any]], memories: Mapping[str, Any], squire: Squire | None
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        ms = available(case, memories)
        arms: dict[str, Any] = {"nothing": ("", ()), "all": arm_all(case, ms)}
        arms = {**arms, **{f"bm25@{k}": arm_bm25(case, ms, k) for k in BM25_K}}
        if squire is not None:
            arms = {**arms, **(await arm_gate(squire, case, ms))}
        rows = [*rows, {**case, "arms": arms}]
    return rows


def sample(cases: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    ordered = sorted(cases, key=lambda c: (c["project"], c["session"], c["index"]))
    if len(ordered) <= SAMPLE:
        return list(ordered)
    rng = random.Random(SEED)
    positives = [c for c in ordered if c["relevant"]]
    negatives = [c for c in ordered if not c["relevant"]]
    pos = rng.sample(positives, min(POSITIVES, len(positives)))
    neg = rng.sample(negatives, min(SAMPLE - len(pos), len(negatives)))
    return sorted([*pos, *neg], key=lambda c: (c["project"], c["session"], c["index"]))


def describe(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_project: dict[str, dict[str, int]] = {}
    for c in cases:
        p = by_project.get(c["project"], {"prompts": 0, "with_relevant": 0, "memories": 0})
        by_project = {
            **by_project,
            c["project"]: {
                "prompts": p["prompts"] + 1,
                "with_relevant": p["with_relevant"] + bool(c["relevant"]),
                "memories": max(p["memories"], len(c["available"])),
            },
        }
    pairs = sum(len(c["available"]) for c in cases)
    relevant = sum(len(c["relevant"]) for c in cases)
    return {
        "projects": len(by_project),
        "prompts": len(cases),
        "prompts_with_relevant": sum(bool(c["relevant"]) for c in cases),
        "pairs": pairs,
        "relevant_pairs": relevant,
        "base_rate_pairs": round(relevant / pairs, 4) if pairs else None,
        "read_labels": sum(len(set(c["read"]) & set(c["relevant"])) for c in cases),
        "quoted_labels": sum(len(set(c["quoted"]) & set(c["relevant"])) for c in cases),
        "by_project": by_project,
    }


# --- estimate ---------------------------------------------------------------------------


def _body_chars(state: Mapping[str, Any], questions: Mapping[str, Any]) -> int:
    wire = {
        "model": "jev-1.13.0",
        "state": state,
        "questions": {k: to_wire(q) for k, q in questions.items()},
    }
    return len(json.dumps(wire, ensure_ascii=False))


def estimate_case(case: Mapping[str, Any], ms: Sequence[mg.Memory]) -> tuple[int, int]:
    """(calls, JSON characters) for one case, with both calls made (the pre-registered run)."""
    prompt = case["prompt"]
    state, qs = memory.recall_questions(turn=prompt, topics=mg.topics_of(ms))
    calls, chars = 1, _body_chars(state, qs)
    pages = mg.pages_of(ms)
    if len(pages) <= chunks.PAGE_MAX:
        state, qs = chunks.context_questions(purpose=prompt, pages=pages)
        return calls + 1, chars + _body_chars(state, qs)
    for group in hierarchy.groups(len(pages), chunks.PAGE_MAX):
        state, qs = chunks.context_questions(purpose=prompt, pages=[pages[i] for i in group])
        calls, chars = calls + 1, chars + _body_chars(state, qs)
    # Final round: at most one call of PAGE_MAX survivors (upper bound on its size).
    state, qs = chunks.context_questions(purpose=prompt, pages=pages[: chunks.PAGE_MAX])
    return calls + 1, chars + _body_chars(state, qs)


def estimate(cases: Sequence[Mapping[str, Any]], memories: Mapping[str, Any]) -> dict[str, Any]:
    calls = chars = 0
    for case in cases:
        c, n = estimate_case(case, available(case, memories))
        calls, chars = calls + c, chars + n
    out: dict[str, Any] = {"cases": len(cases), "calls": calls, "json_chars": chars}
    for label, ratio in zip(("central", "pessimistic"), CHARS_PER_TOKEN, strict=True):
        tokens = math.ceil(chars / ratio)
        out = {
            **out,
            f"tokens_{label}": tokens,
            f"usd_{label}": round(tokens * DEFAULT_PRICE_PER_MTOK / 1_000_000, 4),
        }
    per = out["usd_pessimistic"] / len(cases) if cases else 0.0
    return {**out, "usd_per_prompt_pessimistic": round(per, 6)}


class Guarded:
    """Wraps a decider so that an exception is COUNTED, not only swallowed.

    `Squire.decide` turns any provider exception into an empty decision (fail-open), which is
    right in production and wrong in a benchmark: a failed call then reads as "the decider
    kept nothing". The cascade run of 2026-09-28 lost 336 of 555 sessions that way (an
    `asyncio.Lock` of `ReplayFirst` bound to a previous event loop) and still said complete.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.name = inner.name
        self.failed = 0

    async def decide(self, point: str, state: Any, questions: Any) -> Any:
        try:
            return await self._inner.decide(point, state, questions)
        except Exception:
            self.failed += 1
            raise


# --- main -------------------------------------------------------------------------------


def report(rows: Sequence[Mapping[str, Any]], arms: Sequence[str]) -> dict[str, Any]:
    return {arm: metrics(rows, arm) for arm in arms}


def write_hash(target: pathlib.Path, value: str) -> None:
    if target.exists() and target.read_text(encoding="utf-8").strip() not in ("", value):
        raise SystemExit(f"{target.name} already holds a different hash: nothing written")
    target.write_text(value + "\n", encoding="utf-8")


def _key(env_file: str | None) -> str:
    key = os.environ.get("TYPESAFE_API_KEY", "")
    if not key and env_file:
        text = pathlib.Path(env_file).read_text(encoding="utf-8")
        found = re.search(r"^TYPESAFE_API_KEY=(.*)$", text, re.M)
        key = found.group(1).strip().strip("'\"") if found else ""
    if not key:
        raise SystemExit("no TYPESAFE_API_KEY: nothing spent")
    return key


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--record-hash", action="store_true")
    mode.add_argument("--dry", action="store_true")
    mode.add_argument("--estimate", action="store_true")
    mode.add_argument("--live", action="store_true")
    ap.add_argument("--max-usd", type=float, default=0.50)
    ap.add_argument(
        "--owner-consent",
        action="store_true",
        help="the owner agreed to send his redacted memories and prompts to the decider",
    )
    ap.add_argument("--env-file", default=None)
    ap.add_argument("--out", default="", help="write the aggregate report here (JSON)")
    args = ap.parse_args()
    if args.record_hash:
        write_hash(RESULTS / "prereg.sha256", prereg_hash())
        print(prereg_hash())
        return 0
    if args.live and not args.owner_consent:
        raise SystemExit(
            "part B sends the owner's private memories and prompts (redacted) to a third "
            "party: it needs his explicit consent (--owner-consent). Nothing spent."
        )
    cases, memories = build()
    digest = save(cases, memories)
    chosen = sample(cases)
    out: dict[str, Any] = {
        "cases_sha256": digest,
        "all_cases": describe(cases),
        "sample": describe(chosen),
        "estimate_sample": estimate(chosen, memories),
        "estimate_per_prompt_all_cases": estimate(cases, memories),
    }
    if args.estimate:
        print(json.dumps({k: out[k] for k in ("all_cases", "estimate_sample")}, indent=1))
        return 0
    arms = ["nothing", "all", *(f"bm25@{k}" for k in BM25_K)]
    if args.dry:
        squire = Squire(NullDecider(), thresholds=replace(Thresholds(), max_decisions=10**7))
        rows_all = asyncio.run(evaluate(cases, memories, squire))
        keys = {_key_of(c) for c in chosen}
        rows_sample = [r for r in rows_all if _key_of(r) in keys]
        out = {
            **out,
            "baselines_all_cases": report(rows_all, [*arms, "triage", "gate"]),
            "baselines_sample": report(rows_sample, [*arms, "triage", "gate"]),
        }
    else:
        require_prereg()
        if out["estimate_sample"]["usd_pessimistic"] > args.max_usd:
            raise SystemExit(f"estimate above --max-usd {args.max_usd}: nothing spent")
        out = {**out, "live": asyncio.run(_live(chosen, memories, args))}
    text = json.dumps(out, indent=1)
    if args.out:
        pathlib.Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


def _key_of(case: Mapping[str, Any]) -> tuple[str, str, int]:
    return case["project"], case["session"], case["index"]


async def _live(
    chosen: Sequence[Mapping[str, Any]], memories: Mapping[str, Any], args: Any
) -> dict[str, Any]:
    from sanchopanza.providers import create
    from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider

    fixture = CACHE / "decisions.jsonl"
    recorded = RecordedDecider.from_file(fixture) if fixture.exists() else RecordedDecider([])
    live = RecordingDecider(create("jev", api_key=_key(args.env_file)), fixture)
    replay = triage_run.ReplayFirst(recorded, live)
    guard = Guarded(replay)
    squire = Squire(
        guard,
        thresholds=replace(Thresholds(), max_decisions=10**6, max_usd=args.max_usd),
    )
    rows = await evaluate(chosen, memories, squire)
    arms = ["nothing", "all", *(f"bm25@{k}" for k in BM25_K), "triage", "gate"]
    return {
        "complete": not squire.exhausted and not replay.missing and not guard.failed,
        "failed_calls": guard.failed,
        "live_calls": replay.asked,
        "spent_usd": round(squire.meter.cost_usd, 4),
        "arms": report(rows, arms),
    }


if __name__ == "__main__":
    sys.exit(main())
