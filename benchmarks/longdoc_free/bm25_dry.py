"""The BM25 prefilter before Jev's page tournament, measured free on the dev (no call).

    python -I benchmarks/longdoc_free/bm25_dry.py            # every K in KS; writes OUT/*.json

Three replays of the 41 dev questions, all offline:
- real: the dev's recording (`fixtures/longdoc-free/jev-dev.jsonl.gz`) read back through
  `jev_phase.ask`, checked against the published rows (`jev-dev.jsonl`): each call's recorded
  cost, each page's recorded p round by round, and the pages Jev finally kept;
- stub: B6's dry-run Stub, without and with the prefilter (the sealed dry run's method);
- oracle: the tournament replayed over the prefilter's pages with each page's real p in each
  round (a page's p taken as its own, whatever group it is judged in), the sentence calls and
  the gate answered from the recording when the same call was recorded.

Recall: how many of the pages Jev kept survive the prefilter, whether a page holding a gold
answer does, and whether the kept text still holds it. Cost: tournament calls a question by the
stub times the question's real/stub ratio, and by the oracle; dollars from the estimate of each
call (`estimate_usd`) calibrated on the dev's recorded costs, per decision point.
"""

from __future__ import annotations

import asyncio
import gzip
import importlib.util
import json
import pathlib
import re
import statistics
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def _load(name: str, path: pathlib.Path) -> Any:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


jp = _load("lf_jev_phase", HERE / "jev_phase.py")
score = _load("lf_infbench_score", HERE / "infbench_score.py")
br = jp.br

from sanchopanza import truth  # noqa: E402
from sanchopanza.contract import Decision  # noqa: E402
from sanchopanza.limits import Limits  # noqa: E402
from sanchopanza.points import hierarchy  # noqa: E402
from sanchopanza.providers.capped import estimate_usd  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, key_of  # noqa: E402

FIXTURE = ROOT / "fixtures" / "longdoc-free" / "jev-dev.jsonl.gz"
PUBLISHED = jp.RESULTS / "jev-dev.jsonl"
OUT = ROOT / "docs" / "results" / "2026-10-17-lfree-bm25-dry"
KS = (30, 60, 90, 120, 150, 200, 300, 400)
PRICE = 0.042  # USD a million tokens: the asker's pessimistic estimate, calibrated below
POINTS = ("triage_pages", "select_sentences", jp.POINT)
PAGE_LINE = re.compile(r"^(P\d+)\| (\d+): ", re.M)
NO_P = 0.99  # a page real Jev left unanswered passes every cut, as None does in the tournament


def recording() -> list[dict[str, Any]]:
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as handle:
        lines = [json.loads(x) for x in handle if x.strip()]
    return [x for x in lines if x.get("model") == jp.MODEL]


class Counting:
    """A decider passed through: per question and point, calls, estimate and recorded cost;
    for the tournament, each page's p in the order it was asked (its rounds)."""

    def __init__(
        self, inner: Any, costs: dict[str, float] | None = None, *, answered_only: bool = False
    ) -> None:
        """`answered_only`: count only calls the inner decider answered (a replay's recorded
        calls), not every call attempted."""
        self.inner, self.costs, self.name = inner, costs or {}, "counting"
        self.answered_only = answered_only
        self.by_row: dict[str, dict[str, float]] = {}
        self.rounds: dict[tuple[str, str], list[float | None]] = {}

    async def decide(self, point: str, state: Any, qs: Any) -> Decision:
        decision = await self.inner.decide(point, state, qs)
        if self.answered_only and not decision.answers:
            return decision
        row = br.ROW.get()
        tally = self.by_row.setdefault(row, {})
        added = {
            f"calls_{point}": 1.0,
            f"est_{point}": estimate_usd(state, qs, price_per_mtok=PRICE),
            f"usd_{point}": self.costs.get(key_of(point, state, qs), 0.0),
        }
        for name, value in added.items():
            tally[name] = tally.get(name, 0.0) + value
        if point == "triage_pages" and decision.answers:
            for pid, title in PAGE_LINE.findall(str(state["pages"])):
                if pid in qs:
                    self.rounds.setdefault((row, title), []).append(decision.answer(pid).truth)
        return decision


class Oracle:
    """Each page's real p in its n-th round (its last one past those it reached); sentence
    calls and the gate from the recording when the same call was recorded, else 0.5."""

    name = "oracle"

    def __init__(self, rounds: dict[tuple[str, str], list[float | None]], rec: Any) -> None:
        self.rounds, self.rec = rounds, rec
        self.turn: dict[tuple[str, str], int] = {}
        self.misses: dict[str, int] = {}

    async def decide(self, point: str, state: Any, qs: Any) -> Decision:
        row = br.ROW.get()
        if point == "triage_pages":
            titles = dict(PAGE_LINE.findall(str(state["pages"])))
            answers = {}
            for pid in qs:
                page = (row, titles[pid])
                seen = self.rounds[page]
                turn = self.turn.get(page, 0)
                self.turn[page] = turn + 1
                p = seen[min(turn, len(seen) - 1)]
                answers[pid] = truth(NO_P if p is None else p)
            return Decision(point, answers, "oracle", jp.MODEL)
        found = await self.rec.decide(point, state, qs)
        if found.answers and found.model == jp.MODEL:
            return found
        self.misses[point] = self.misses.get(point, 0) + 1
        return Decision(point, {k: truth(0.5) for k in qs}, "oracle", jp.MODEL)


class Capture:
    """`jev_phase.pages` with `kept_text` noting each question's entries."""

    def __init__(self, module: Any) -> None:
        self._module, self.entries = module, {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._module, name)

    def kept_text(self, pages: Any, entries: Any) -> str:
        self.entries[br.ROW.get()] = list(entries)
        return self._module.kept_text(pages, entries)


def run(rows: list[dict[str, Any]], asker: Any, k: int | None) -> tuple[list[dict], dict]:
    capture, before = Capture(jp.pages), jp.pages
    jp.pages = capture
    try:
        got = asyncio.run(jp.ask(rows, asker, k))
    finally:
        jp.pages = before
    return got, capture.entries


def asker_over(fallback: Any, recorded: Any = None) -> Any:
    rec = RecordedDecider([]) if recorded is None else recorded
    return br.Asker(fallback, recorded=rec, memo_failures=True, model_halts=True)


def kept_pages(entry_list: list[Any]) -> set[int]:
    return {i for i, e in enumerate(entry_list) if e and any(keep for keep, _ in e)}


def gold_pages(pages: list[tuple[str, str]], answers: list[str]) -> set[int]:
    refs = [f" {r} " for r in (score.normalize_answer(a) for a in answers) if r.strip()]
    texts = [f" {score.normalize_answer(p)} " for _, p in pages]
    return {i for i, t in enumerate(texts) if any(r in t for r in refs)}


def usd(tally: dict[str, float], factor: dict[str, float], points: tuple[str, ...]) -> float:
    return sum(tally.get(f"est_{p}", 0.0) * factor[p] for p in points)


def mean(xs: list[float]) -> float:
    return round(statistics.fmean(xs), 4) if xs else float("nan")


def replay_real(rows: list[dict[str, Any]], lines: list[dict[str, Any]]) -> dict[str, Any]:
    """The dev's recording read back through `jev_phase.ask`, checked against its rows."""
    costs = {str(x["key"]): float(x.get("cost_usd") or 0.0) for x in lines}
    real = Counting(RecordedDecider(lines), costs)
    asker = asker_over(None, real)
    got, entries = run(rows, asker, None)
    if asker.failed_keys:
        raise SystemExit(f"{len(asker.failed_keys)} calls not recorded")
    published = {r["id"]: r for r in map(json.loads, PUBLISHED.read_text("utf-8").splitlines())}
    matches = all(
        published[g["id"]]["p"] == g["p"] and published[g["id"]]["kept_chars"] == len(g["kept"])
        for g in got
    )
    factor = {}
    for p in POINTS:
        spent = sum(t.get(f"usd_{p}", 0.0) for t in real.by_row.values())
        est = sum(t.get(f"est_{p}", 0.0) for t in real.by_row.values())
        factor[p] = spent / est if est else 0.0
    return {"counting": real, "got": got, "entries": entries, "matches": matches,
            "factor": factor}  # fmt: skip


def per_question(rows: list[dict[str, Any]], real: dict[str, Any], stub: Counting,
                 oracle: Counting) -> dict[str, dict[str, Any]]:  # fmt: skip
    out = {}
    for row, g in zip(rows, real["got"], strict=True):
        rid = str(row["id"])
        r_t, s_t = real["counting"].by_row[rid], stub.by_row[rid]
        out[rid] = {
            "id": row["id"],
            "novel": row["novel"],
            "pages": len(row["pages"]),
            "real_tournament_calls": int(r_t["calls_triage_pages"]),
            "stub_tournament_calls": int(s_t["calls_triage_pages"]),
            "oracle_tournament_calls": int(oracle.by_row[rid]["calls_triage_pages"]),
            "ratio": r_t["calls_triage_pages"] / s_t["calls_triage_pages"],
            "real_sentence_calls": int(r_t.get("calls_select_sentences", 0)),
            "real_usd": sum(r_t.get(f"usd_{p}", 0.0) for p in POINTS),
            "kept": kept_pages(real["entries"][rid]),
            "gold": gold_pages(row["pages"], row["answers"]),
            "gold_in_kept": jp.gold_in(g["kept"], row["answers"]),
        }
    return out


def real_summary(per_q: dict[str, dict[str, Any]], real: dict[str, Any], max_call: float) -> dict:
    qs = list(per_q.values())
    tournament_usd = sum(t.get("usd_triage_pages", 0.0) for t in real["counting"].by_row.values())
    sentence_usd = sum(t.get("usd_select_sentences", 0.0) for t in real["counting"].by_row.values())
    calls = sum(q["real_tournament_calls"] for q in qs)
    sentences = [q["real_sentence_calls"] for q in qs]
    return {
        "jev_usd_total": round(sum(q["real_usd"] for q in qs), 4),
        "jev_usd_a_question": mean([q["real_usd"] for q in qs]),
        "tournament_calls": calls,
        "tournament_usd_a_call": round(tournament_usd / calls, 6),
        "tournament_usd_max_call": round(max_call, 6),
        "sentence_calls_mean": mean(sentences),
        "sentence_calls_max": max(sentences),
        "sentence_usd_a_call": round(sentence_usd / sum(sentences), 6),
        "gold_in_kept": sum(q["gold_in_kept"] for q in qs),
        "gold_anywhere": sum(bool(q["gold"]) for q in qs),
    }


def measure() -> dict[str, Any]:
    rows = jp.load_rows("dev")
    lines = recording()
    rec = RecordedDecider(lines)
    real = replay_real(rows, lines)
    stub_full = Counting(br.Stub())
    run(rows, asker_over(stub_full), None)
    oracle_full = Counting(Oracle(real["counting"].rounds, rec))
    oracle_got, _ = run(rows, asker_over(oracle_full), None)
    per_q = per_question(rows, real, stub_full, oracle_full)
    qs = list(per_q.values())

    triage = [float(x.get("cost_usd") or 0.0) for x in lines if x["point"] == "triage_pages"]
    by_k = [
        one_k(rows, k, per_q, real["entries"], real["counting"].rounds, rec, real["factor"])
        | worst(k, max(triage))
        for k in KS
    ]
    ratios = [q["ratio"] for q in qs]
    pooled = sum(q["real_tournament_calls"] for q in qs) / sum(
        q["stub_tournament_calls"] for q in qs
    )
    return {
        "questions": len(rows),
        "replay_matches_published_rows": real["matches"],
        "oracle_full_matches_real_calls": all(
            q["oracle_tournament_calls"] == q["real_tournament_calls"] for q in qs
        ),
        "oracle_full_gold_in_kept": sum(
            jp.gold_in(o["kept"], r["answers"]) for o, r in zip(oracle_got, rows, strict=True)
        ),
        "real": real_summary(per_q, real, max(triage)),
        "calibration_real_over_estimate": {p: round(f, 4) for p, f in real["factor"].items()},
        "stub_full_tournament_calls": sum(q["stub_tournament_calls"] for q in qs),
        "ratio_real_over_stub": {
            "pooled": round(pooled, 3),
            "median": round(statistics.median(ratios), 3),
            "min": round(min(ratios), 3),
            "max": round(max(ratios), 3),
        },
        "by_k": by_k,
        "per_question": [
            {k: v for k, v in q.items() if k not in ("kept", "gold")}
            | {"kept_pages": len(q["kept"]), "gold_pages": len(q["gold"])}
            for q in qs
        ],
    }


def one_k(rows: list[dict[str, Any]], k: int, per_q: dict[str, dict[str, Any]],
          real_entries: dict[str, list[Any]], rounds: dict[tuple[str, str], list[float | None]],
          rec: Any, factor: dict[str, float]) -> dict[str, Any]:  # fmt: skip
    stub = Counting(br.Stub())
    run(rows, asker_over(stub), k)
    oracle = Oracle(rounds, rec)
    oracle_count = Counting(oracle)
    oracle_got, _ = run(rows, asker_over(oracle_count), k)
    recall, all_kept, gold_top, gold_masked, gold_oracle = [], 0, 0, 0, 0
    stub_ratio_usd, oracle_usd, stub_calls, oracle_calls = [], [], [], []
    for row, o in zip(rows, oracle_got, strict=True):
        rid, q = str(row["id"]), per_q[str(row["id"])]
        top = set(jp.pages.bm25_shortlist(row["pages"], row["question"], k))
        if q["kept"]:
            recall.append(len(q["kept"] & top) / len(q["kept"]))
            all_kept += q["kept"] <= top
        gold_top += bool(q["gold"] & top)
        masked = [e if i in top else None for i, e in enumerate(real_entries[rid])]
        gold_masked += jp.gold_in(jp.pages.kept_text(row["pages"], masked), row["answers"])
        gold_oracle += jp.gold_in(o["kept"], row["answers"])
        s_t, o_t = stub.by_row[rid], oracle_count.by_row[rid]
        rest = usd(o_t, factor, ("select_sentences", jp.POINT))
        tournament = s_t["est_triage_pages"] * factor["triage_pages"] * q["ratio"]
        stub_ratio_usd.append(tournament + rest)
        oracle_usd.append(usd(o_t, factor, POINTS))
        stub_calls.append(s_t["calls_triage_pages"] * q["ratio"])
        oracle_calls.append(o_t["calls_triage_pages"])
    n = len(rows)
    return {
        "k": k,
        "kept_page_recall_mean": mean(recall),
        "questions_all_kept_pages_survive": all_kept,
        "questions_with_kept_pages": len(recall),
        "gold_page_in_top_k": gold_top,
        "gold_in_kept_masked": gold_masked,
        "gold_in_kept_oracle": gold_oracle,
        "tournament_calls_stub_x_ratio_mean": mean(stub_calls),
        "tournament_calls_oracle_mean": mean(oracle_calls),
        "jev_usd_stub_x_ratio_mean": mean(stub_ratio_usd),
        "jev_usd_oracle_mean": mean(oracle_usd),
        "jev_usd_oracle_p90": round(sorted(oracle_usd)[int(0.9 * (n - 1))], 4),
        "jev_usd_stub_x_ratio_p90": round(sorted(stub_ratio_usd)[int(0.9 * (n - 1))], 4),
        "oracle_unrecorded_calls": dict(oracle.misses),
        "jev_usd_oracle_by_id": {
            str(r["id"]): round(x, 4) for r, x in zip(rows, oracle_usd, strict=True)
        },
    }


def worst(k: int, max_call: float) -> dict[str, Any]:
    """The tournament's ceiling over K pages, whatever Jev answers: at most MAX_ROUNDS pruning
    rounds and a final one, each of ceil(K / pages a call) calls, each at most the dev's dearest
    tournament call."""
    calls = (hierarchy.MAX_ROUNDS + 1) * -(-k // Limits().pages_per_call)
    return {"tournament_calls_worst": calls, "tournament_usd_worst": round(calls * max_call, 4)}


def main() -> int:
    out = measure()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "bm25-dry.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "per_question"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
