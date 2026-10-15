"""Label a corpus with Jev 1.13 and 1.14, live and interleaved (docs/results/2026-10-15-jev114-l3).

python -I benchmarks/label/data114.py                       # the items, once (free, network)
python benchmarks/label/jev114.py --record-hash             # seal prereg.md
python benchmarks/label/jev114.py --dry                     # fake decider: the path, free
python benchmarks/label/jev114.py --live                    # spends, records, analyses
python benchmarks/label/jev114.py                           # free: replays the recordings

Two arms on the same items, both asked today: `13r` (`jev-1.13.0`) and `14` (`jev-1.14.0`),
one item at a time, the order of the two calls alternating by item. The question and policy
are `label.label_one` (the `classify` point), as on 2026-09-30. Every call goes through
`CappedDecider` on the shared ledger, so the batch cannot pass its cap; answers are recorded
(`fixtures/jev114/label-jev.jsonl` for 1.14, `fixtures/jev114/label-jev113r.jsonl` for
today's 1.13) and a re-run replays them for free. The key comes from `TYPESAFE_API_KEY`, else
from the `.env` file `SANCHOPANZA_KEYS_ENV` names; it is never printed.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import pathlib
import random
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sanchopanza.budget import SpendLedger  # noqa: E402
from sanchopanza.contract import (  # noqa: E402
    Answer,
    DeciderOutOfFunds,
    DeciderUnavailable,
    Decision,
)
from sanchopanza.eval.stats import mcnemar, wilson  # noqa: E402
from sanchopanza.label import Item, Row, Rubric, label_one  # noqa: E402
from sanchopanza.points import entities  # noqa: E402
from sanchopanza.policy import Thresholds  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.providers.capped import CappedDecider, SpendCapReached, estimate_usd  # noqa: E402
from sanchopanza.providers.recorded import (  # noqa: E402
    RecordedDecider,
    RecordingDecider,
    fixture_path,
)
from sanchopanza.squire import Squire  # noqa: E402

RESULTS = ROOT / "docs" / "results" / "2026-10-15-jev114-l3"
PREREG = RESULTS / "prereg.md"
ORIGINAL = ROOT / "docs" / "results" / "2026-09-30-label"
DATA = (
    pathlib.Path(
        os.environ.get("SANCHOPANZA_CACHE", pathlib.Path.home() / ".cache" / "sanchopanza")
    )
    / "label-jev114"
)
SETS = ("agnews", "dbpedia", "sib")
ARMS = {"13r": "jev-1.13.0", "14": "jev-1.14.0"}
FIXTURES = {
    "13r": ROOT / "fixtures" / "jev114" / "label-jev113r.jsonl",
    "14": fixture_path(ROOT / "fixtures" / "label-jev.jsonl", ARMS["14"]),
}
BATCH = "jev114-l3"
BATCH_CAP_USD = 0.20
LEDGER = pathlib.Path(os.environ.get("SANCHOPANZA_JEV114_LEDGER", r"C:\sp-runs\jev114\ledger.json"))
LEDGER_CAP_USD = 4.50
CONCURRENCY = 4  # items in flight; each item asks its two arms one after the other
PLAN_MARGIN = 1.25  # the plan must fit at its expected cost times this
EARLY_ITEMS, EARLY_UNANSWERED = 40, 10  # stop a set when an arm fails this often this early
NON_INFERIORITY = -0.02
MISSING_SHARE = 0.01  # more answers missing than this: incomplete
RECALIBRATE_COVERAGE = 0.02  # |coverage change at 0.60| above this, interval off 0: recalibrate
ALPHA = 0.05
REPS = 4000
SEED = 2026_10_15
ENGLISH = "eng_Latn"


# --- sealing and money ----------------------------------------------------------------------


def digest() -> str:
    return hashlib.sha256(PREREG.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def require_prereg() -> None:
    """The sealed prereg, unchanged, and the instrument as committed (no local edits)."""
    registered = RESULTS / "prereg.sha256"
    if not registered.exists() or registered.read_text().strip() != digest():
        raise SystemExit("prereg.md missing or changed since it was registered: nothing spent")
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", "benchmarks/label", "benchmarks/triage_sets",
         "src", "tests/test_label_jev114.py", str(PREREG.relative_to(ROOT))],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip
    if dirty:
        raise SystemExit("the instrument has uncommitted changes: nothing spent")


def api_key() -> str:
    key = os.environ.get("TYPESAFE_API_KEY", "")
    named = os.environ.get("SANCHOPANZA_KEYS_ENV", "")
    if not key and named:
        for line in pathlib.Path(named).read_text(encoding="utf-8").splitlines():
            if line.startswith("TYPESAFE_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("'\"")
    if not key:
        raise SystemExit("no TYPESAFE_API_KEY (nor SANCHOPANZA_KEYS_ENV): nothing spent")
    return key


def load(name: str) -> tuple[list[dict[str, Any]], Rubric]:
    rows = [
        json.loads(x) for x in (DATA / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    return rows, Rubric.load(DATA / f"{name}.rubric.json")


def estimate_ratio() -> float:
    """Recorded cost over the pessimistic estimate, on the 2026-09-30 answers (1.13)."""
    recorded = {}
    for line in (ROOT / "fixtures" / "label-jev.jsonl").read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        recorded[entry["key"]] = float(entry["cost_usd"])
    from sanchopanza.providers.recorded import key_of

    paid = estimated = 0.0
    for name in ("agnews", "dbpedia"):
        rows, rubric = load(name)
        for row in (r for r in rows if r.get("original")):
            state, qs = entities.classification_questions(
                field=rubric.field, text=row["text"], options=rubric.options,
                add_other=rubric.add_other,
            )  # fmt: skip
            key = key_of("classify", state, qs)
            if key in recorded:
                paid += recorded[key]
                estimated += estimate_usd(state, qs, price_per_mtok=0.042)
    return paid / estimated if estimated else 1.0


def plan(missing: dict[str, int], pessimistic: float, ledger: SpendLedger) -> dict[str, Any]:
    """Expected dollars of what is not recorded yet, against what is left under both caps."""
    ratio = estimate_ratio()
    expected = pessimistic * ratio
    left = min(BATCH_CAP_USD - ledger.spent(BATCH), LEDGER_CAP_USD - ledger.spent())
    return {"calls_to_make": missing, "pessimistic_usd": round(pessimistic, 5),
            "cost_over_estimate": round(ratio, 4), "expected_usd": round(expected, 5),
            "left_under_caps_usd": round(left, 5),
            "fits": expected * PLAN_MARGIN <= left}  # fmt: skip


# --- the run --------------------------------------------------------------------------------


class Halt:
    """Why the run stopped spending: the cap, the funds, or a model other than the arm's."""

    def __init__(self) -> None:
        self.reason: str | None = None

    def set(self, reason: str) -> None:
        self.reason = self.reason or reason


class ModelGuard:
    """Inside the recorder: a cap or funds refusal, or an answer from another model, halts the
    run (and that answer is neither recorded nor used)."""

    def __init__(self, inner: Any, model: str, halt: Halt) -> None:
        self._inner, self._model, self._halt = inner, model, halt
        self.name = inner.name

    async def decide(self, point: str, state: Any, questions: Any) -> Decision:
        try:
            decision = await self._inner.decide(point, state, questions)
        except (SpendCapReached, DeciderOutOfFunds) as error:
            self._halt.set(f"{error.__class__.__name__}: {error}")
            raise
        if decision.model != self._model:
            self._halt.set(f"asked {self._model}, answered by {decision.model!r}")
            raise DeciderUnavailable("answered by another model")
        return decision


class ReplayThenLive:
    """The recording first; live only for what is missing, at most `ATTEMPTS` times, never
    once the run is halted. Counts live calls and items left unanswered."""

    ATTEMPTS = 2

    def __init__(self, recorded: RecordedDecider, live: Any | None, halt: Halt) -> None:
        self._recorded, self._live, self._halt = recorded, live, halt
        self.name = "jev"
        self.asked = 0
        self.missing = 0

    async def decide(self, point: str, state: Any, questions: Any) -> Decision:
        decision = await self._recorded.decide(point, state, questions)
        if decision.answers:
            return decision
        for attempt in range(self.ATTEMPTS if self._live is not None else 0):
            if self._halt.reason:
                break
            try:
                self.asked += 1
                decision = await self._live.decide(point, state, questions)
                if decision.answers:
                    return decision
            except DeciderUnavailable:
                await asyncio.sleep(1 + attempt)
        self.missing += 1
        return Decision(point=point, answers={}, provider=self.name, model="-")


class FakeJev:
    """`--dry`: stands in for `JevDecider` inside the real chain (cap, ledger, recorder,
    replay). A gold-blind distribution; claims a price so the ledger moves."""

    name = "jev"

    def __init__(self, model: str) -> None:
        self._model = model

    async def decide(self, point: str, state: Any, questions: Any) -> Decision:
        options = list(questions["category"].options)
        blob = json.dumps(state, sort_keys=True) + self._model
        winner = options[int(hashlib.sha256(blob.encode()).hexdigest(), 16) % len(options)]
        probabilities = {o: (0.7 if o == winner else 0.3 / (len(options) - 1)) for o in options}
        answer = Answer(kind="choice", choice=winner, probabilities=probabilities, confidence=0.6)
        return Decision(point=point, answers={"category": answer}, provider="jev",
                        model=self._model, input_tokens=500, cost_usd=0.000021)  # fmt: skip


def arm_decider(
    arm: str, *, inner: Any | None, ledger: SpendLedger, fixtures: dict[str, pathlib.Path],
    halt: Halt,
) -> ReplayThenLive:  # fmt: skip
    """Replay, then (when `inner` is given) live: guard, recorder, cap, the model."""
    model = ARMS[arm]
    recorded = RecordedDecider.from_file(fixtures[arm], model=model)
    paid = None
    if inner is not None:
        capped = CappedDecider(inner, ledger=ledger, batch=BATCH, max_usd=BATCH_CAP_USD)
        paid = RecordingDecider(ModelGuard(capped, model, halt), fixtures[arm])
    return ReplayThenLive(recorded, paid, halt)


def squire_of(decider: Any) -> Squire:
    return Squire(decider, thresholds=Thresholds(max_usd=BATCH_CAP_USD, max_decisions=20_000))


def record_of(row: Row) -> dict[str, Any]:
    dist = dict(row.probabilities)
    top = max(dist, key=lambda k: dist[k]) if dist else None
    return {"label": top, "gated": row.label, "p": row.p, "margin": row.margin,
            "reason": row.reason,
            "p_is_top": bool(dist) and abs(row.p - dist[top]) < 1e-12}  # fmt: skip


async def run_set(
    rows: list[dict[str, Any]], rubric: Rubric, squires: dict[str, Squire],
    halt: Halt | None = None, flips: Callable[[int, dict[str, Any]], int] | None = None,
) -> list[dict[str, Any]]:  # fmt: skip
    """Both arms on every item, two calls in a row, the first arm alternating (`flips`). The
    rows come back without their text (third-party data stays out of the repository)."""
    flips = flips or (lambda i, _row: i)
    gate = asyncio.Semaphore(CONCURRENCY)
    out: list[dict[str, Any]] = [{k: v for k, v in r.items() if k != "text"} for r in rows]
    unanswered = {arm: 0 for arm in ARMS}
    stop = asyncio.Event()

    async def one(i: int, row: dict[str, Any]) -> None:
        order = list(ARMS) if flips(i, row) % 2 == 0 else list(reversed(ARMS))
        async with gate:
            if stop.is_set() or (halt is not None and halt.reason):
                return
            item = Item(row["key"], row["text"])
            for arm in order:
                answer = await label_one(squires[arm], rubric, item)
                out[i] = {**out[i], **{f"{k}_{arm}": v for k, v in record_of(answer).items()}}
                if not answer.probabilities:
                    unanswered[arm] += 1
            if i < EARLY_ITEMS and max(unanswered.values()) >= EARLY_UNANSWERED:
                stop.set()

    await asyncio.gather(*(one(i, r) for i, r in enumerate(rows)))
    return out


def sentence_flips(rows: list[dict[str, Any]]) -> Callable[[int, dict[str, Any]], int]:
    """SIB-200: which arm goes first alternates by sentence and by language at once, so every
    language has each arm first on half of its sentences."""
    langs = {lang: i for i, lang in enumerate(dict.fromkeys(r["lang"] for r in rows))}
    return lambda _i, row: row["sentence"] + langs[row["lang"]]


def interleave_sentences(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """SIB-200 by sentence, every language of a sentence together, so a cap that cuts the run
    short cuts every language alike."""
    langs = {lang: i for i, lang in enumerate(dict.fromkeys(r["lang"] for r in rows))}
    return sorted(rows, key=lambda r: (r["sentence"], langs[r["lang"]]))


# --- analysis -------------------------------------------------------------------------------


def right(rows: Sequence[dict], arm: str) -> list[bool]:
    return [r.get(f"label_{arm}") == r["gold"] for r in rows]


def fast_auc(scores: Sequence[float], truths: Sequence[bool]) -> float:
    """Mann-Whitney AUC from average ranks (ties count a half), O(n log n)."""
    pos = sum(truths)
    neg = len(truths) - pos
    if not pos or not neg:
        return float("nan")
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    rank_sum = sum(r for r, t in zip(ranks, truths, strict=True) if t)
    return (rank_sum - pos * (pos + 1) / 2) / (pos * neg)


def clusters_of(rows: Sequence[dict]) -> list[list[int]]:
    """Resampling units: one item, or (SIB-200) one sentence in all its languages."""
    groups: dict[Any, list[int]] = {}
    for i, r in enumerate(rows):
        groups.setdefault(r.get("sentence", r["key"]), []).append(i)
    return list(groups.values())


def bootstrap(
    rows: Sequence[dict], stat: Callable[[list[dict]], float], *, seed: int = SEED
) -> list[float]:
    """95 % percentile interval of `stat`, resampling clusters with replacement."""
    clusters = clusters_of(rows)
    rng = random.Random(seed)
    values = []
    for _ in range(REPS):
        sample = [rows[i] for _ in clusters for i in clusters[rng.randrange(len(clusters))]]
        value = stat(sample)
        if not math.isnan(value):
            values.append(value)
    values.sort()
    if not values:  # e.g. an AUROC where every item is right
        return [float("nan"), float("nan")]
    low, high = values[int(0.025 * len(values))], values[int(0.975 * len(values)) - 1]
    return [round(low, 4), round(high, 4)]


def accuracy(rows: Sequence[dict], arm: str) -> float:
    return sum(right(rows, arm)) / len(rows) if rows else float("nan")


def coverage(rows: Sequence[dict], arm: str) -> float:
    return sum(r.get(f"gated_{arm}") is not None for r in rows) / len(rows)


def gated_accuracy(rows: Sequence[dict], arm: str) -> float:
    kept = [r for r in rows if r.get(f"gated_{arm}") is not None]
    return sum(r[f"gated_{arm}"] == r["gold"] for r in kept) / len(kept) if kept else float("nan")


def auc_of(rows: Sequence[dict], arm: str) -> float:
    return fast_auc([float(r.get(f"p_{arm}") or 0.0) for r in rows], right(rows, arm))


def per_arm(rows: Sequence[dict], arm: str) -> dict[str, Any]:
    hits = sum(right(rows, arm))
    _, low, high = wilson(hits, len(rows))
    return {
        "accuracy": round(hits / len(rows), 4),
        "wilson95": [round(low, 4), round(high, 4)],
        "at_classify_0.60": {"coverage": round(coverage(rows, arm), 4),
                             "accuracy": round(gated_accuracy(rows, arm), 4)},
        "auroc_p1": round(auc_of(rows, arm), 4),
        "unanswered": sum(r.get(f"label_{arm}") is None for r in rows),
        "p1_not_the_top_option": sum(
            r.get(f"label_{arm}") is not None and not r.get(f"p_is_top_{arm}") for r in rows
        ),
    }  # fmt: skip


def paired(rows: Sequence[dict]) -> dict[str, Any]:
    """1.14 minus today's 1.13 on the same items."""
    a, b = right(rows, "14"), right(rows, "13r")
    only_14, only_13, p = mcnemar(a, b)

    def diff(f: Callable[[Sequence[dict], str], float]) -> Callable[[list[dict]], float]:
        return lambda s: f(s, "14") - f(s, "13r")

    return {
        "accuracy_diff": round(accuracy(rows, "14") - accuracy(rows, "13r"), 4),
        "accuracy_diff_ci95": bootstrap(rows, diff(accuracy)),
        "only_14_right": only_14,
        "only_13r_right": only_13,
        "mcnemar_p": round(p, 6),
        "coverage_diff_at_0.60": round(coverage(rows, "14") - coverage(rows, "13r"), 4),
        "coverage_diff_ci95": bootstrap(rows, diff(coverage)),
        "gated_accuracy_diff_at_0.60": round(
            gated_accuracy(rows, "14") - gated_accuracy(rows, "13r"), 4
        ),
        "gated_accuracy_diff_ci95": bootstrap(rows, diff(gated_accuracy)),
        "auroc_diff": round(auc_of(rows, "14") - auc_of(rows, "13r"), 4),
        "auroc_diff_ci95": bootstrap(rows, diff(auc_of)),
        "label_agreement": round(
            sum(r.get("label_14") == r.get("label_13r") for r in rows) / len(rows), 4
        ),
    }


def holm(pvalues: dict[str, float]) -> dict[str, float]:
    ranked = sorted(pvalues, key=lambda k: pvalues[k])
    out: dict[str, float] = {}
    running = 0.0
    for i, name in enumerate(ranked):
        running = max(running, min(1.0, (len(ranked) - i) * pvalues[name]))
        out[name] = round(running, 6)
    return out


def verdict(comparison: dict[str, Any], adjusted_p: float) -> str:
    low, high = comparison["accuracy_diff_ci95"]
    d = comparison["accuracy_diff"]
    if d > 0 and adjusted_p < ALPHA and low > 0:
        return "mejora"
    if d < 0 and adjusted_p < ALPHA and high < 0:
        return "peor"
    if low > NON_INFERIORITY:
        return "no peor"
    return "no concluyente"


def multilingual(rows: Sequence[dict]) -> dict[str, Any]:
    """Per language, and the change in the English-minus-language gap (difference in
    differences, resampling sentences)."""
    langs = sorted({r["lang"] for r in rows})
    per_lang = {
        lang: {arm: round(accuracy([r for r in rows if r["lang"] == lang], arm), 4) for arm in ARMS}
        for lang in langs
    }

    def did(sample: list[dict]) -> float:
        eng = [r for r in sample if r["lang"] == ENGLISH]
        other = [r for r in sample if r["lang"] != ENGLISH]
        return (accuracy(other, "14") - accuracy(other, "13r")) - (
            accuracy(eng, "14") - accuracy(eng, "13r")
        )

    return {"per_language": per_lang, "gain_outside_english_minus_gain_in_english": round(
        did(list(rows)), 4), "ci95": bootstrap(rows, did)}  # fmt: skip


def noise_check(name: str, rows: Sequence[dict]) -> dict[str, Any] | None:
    """Today's 1.13 against the 2026-09-30 recording of 1.13, on the 300 items both have."""
    path = ORIGINAL / f"{name}-rows.jsonl"
    if not path.exists():
        return None
    then = {
        (r := json.loads(line))["key"]: r["label"]
        for line in path.read_text(encoding="utf-8").splitlines()
    }
    both = [r for r in rows if r["key"] in then]
    if not both:
        return None
    old = [then[r["key"]] == r["gold"] for r in both]
    now = right(both, "13r")
    only_now, only_then, p = mcnemar(now, old)
    return {
        "items": len(both),
        "accuracy_2026_09_30": round(sum(old) / len(both), 4),
        "accuracy_13r_today": round(sum(now) / len(both), 4),
        "accuracy_14_today": round(accuracy(both, "14"), 4),
        "label_agreement_13_then_vs_13r": round(
            sum(then[r["key"]] == r.get("label_13r") for r in both) / len(both), 4
        ),
        "mcnemar_13r_vs_then": [only_now, only_then, round(p, 6)],
    }


def analyze(results: dict[str, list[dict]]) -> dict[str, Any]:
    families = {
        "agnews": results["agnews"],
        "dbpedia": results["dbpedia"],
        "sib_non_english": [r for r in results["sib"] if r["lang"] != ENGLISH],
    }
    report: dict[str, Any] = {}
    for name, rows in families.items():
        report[name] = {"items": len(rows), **{arm: per_arm(rows, arm) for arm in ARMS},
                        "paired_14_minus_13r": paired(rows)}  # fmt: skip
    adjusted = holm({k: report[k]["paired_14_minus_13r"]["mcnemar_p"] for k in families})
    for name, rows in families.items():
        report[name]["holm_p"] = adjusted[name]
        computed = verdict(report[name]["paired_14_minus_13r"], adjusted[name])
        report[name]["verdict_computed"] = computed
        short = any(report[name][arm]["unanswered"] > MISSING_SHARE * len(rows) for arm in ARMS)
        report[name]["verdict"] = "no concluyente (incompleto)" if short else computed
    english = [r for r in results["sib"] if r["lang"] == ENGLISH]
    report["sib_english"] = {"items": len(english), **{arm: per_arm(english, arm) for arm in ARMS},
                             "paired_14_minus_13r": paired(english)}  # fmt: skip
    report["sib_multilingual"] = multilingual(results["sib"])
    report["noise_vs_2026_09_30"] = {n: noise_check(n, results[n]) for n in ("agnews", "dbpedia")}
    report["recommendations"] = recommendations(report, list(families))
    return report


def recommendations(report: dict[str, Any], families: list[str]) -> dict[str, Any]:
    """The pre-registered consequences of the verdicts."""
    good = ("mejora", "no peor")

    def recalibrate(name: str) -> bool:
        pair = report[name]["paired_14_minus_13r"]
        low, high = pair["coverage_diff_ci95"]
        coverage_moved = abs(pair["coverage_diff_at_0.60"]) > RECALIBRATE_COVERAGE and (
            low > 0 or high < 0
        )
        gated_worse = pair["gated_accuracy_diff_ci95"][1] < 0 and report[name]["verdict"] in good
        return coverage_moved or gated_worse

    return {
        "move_label_to_1_14": all(report[n]["verdict"] in good for n in families),
        "recalibrate_classify_for_1_14": {n: recalibrate(n) for n in families},
        "gains_more_outside_english": report["sib_multilingual"]["ci95"][0] > 0,
    }


# --- main -----------------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record-hash", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--plan-only", action="store_true")
    args = ap.parse_args()
    if args.record_hash:
        (RESULTS / "prereg.sha256").write_text(digest() + "\n", encoding="utf-8")
        print(digest())
        return 0
    loaded = {name: load(name) for name in SETS}
    ledger = SpendLedger(LEDGER, cap_usd=LEDGER_CAP_USD)
    if args.live or args.plan_only:
        if args.live:
            require_prereg()
        missing: dict[str, int] = {}
        pessimistic = 0.0
        for arm, model in ARMS.items():
            recorded = RecordedDecider.from_file(FIXTURES[arm], model=model)
            for rows, rubric in loaded.values():
                for row in rows:
                    state, qs = entities.classification_questions(
                        field=rubric.field, text=row["text"], options=rubric.options,
                        add_other=rubric.add_other,
                    )  # fmt: skip
                    if not asyncio.run(recorded.decide("classify", state, qs)).answers:
                        missing[arm] = missing.get(arm, 0) + 1
                        pessimistic += estimate_usd(state, qs, price_per_mtok=0.042)
        budget = plan(missing, pessimistic, ledger)
        print(json.dumps(budget, indent=1))
        if args.plan_only:
            return 0
        if not budget["fits"]:
            raise SystemExit("the plan does not fit under the caps: nothing spent")
    halt = Halt()
    fixtures = FIXTURES
    if args.dry:  # the whole chain, with a fake model, a scratch ledger and scratch fixtures
        scratch = pathlib.Path(tempfile.mkdtemp(prefix="label-jev114-dry-"))
        ledger = SpendLedger(scratch / "ledger.json", cap_usd=LEDGER_CAP_USD)
        fixtures = {arm: scratch / path.name for arm, path in FIXTURES.items()}
    key = api_key() if args.live else None

    def inner(arm: str) -> Any:
        if args.dry:
            return FakeJev(ARMS[arm])
        if args.live:
            return create("jev", api_key=key, model=ARMS[arm], long_context=False, images=False)
        return None

    deciders = {
        arm: arm_decider(arm, inner=inner(arm), ledger=ledger, fixtures=fixtures, halt=halt)
        for arm in ARMS
    }
    squires = {arm: squire_of(deciders[arm]) for arm in ARMS}
    out_dir = RESULTS / "dry" if args.dry else RESULTS
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, list[dict]] = {}

    async def every_set() -> None:
        for name in SETS:
            rows, rubric = loaded[name]
            rows = interleave_sentences(rows) if name == "sib" else rows
            flips = sentence_flips(rows) if name == "sib" else None
            results[name] = await run_set(rows, rubric, squires, halt, flips)
            (out_dir / f"{name}-rows.jsonl").write_text(
                "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in results[name]),
                encoding="utf-8",
            )

    asyncio.run(every_set())
    report = analyze(results)
    report["run"] = {
        "live_calls": {arm: getattr(d, "asked", 0) for arm, d in deciders.items()},
        "missing": {arm: getattr(d, "missing", 0) for arm, d in deciders.items()},
        "squire_usd": {arm: round(squires[arm].meter.cost_usd, 6) for arm in ARMS},
        "ledger_batch_usd": round(ledger.spent(BATCH), 6),
        "ledger_total_usd": round(ledger.spent(), 6),
        "halted": halt.reason,
    }
    unanswered = sum(
        report[f][arm]["unanswered"]
        for f in ("agnews", "dbpedia", "sib_non_english", "sib_english")
        for arm in ARMS
    )
    total = sum(len(results[n]) for n in SETS) * len(ARMS)
    report["incomplete"] = unanswered > MISSING_SHARE * total
    (out_dir / "analysis.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    if halt.reason:
        return 2
    return 1 if report["incomplete"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
