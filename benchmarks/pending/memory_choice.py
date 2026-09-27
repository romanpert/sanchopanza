"""`memory_write` as ONE Choice (long_term / session_only / drop) against the shipped three Truths.

    .venv/Scripts/python.exe benchmarks/pending/memory_choice.py --hash     # question hash
    .venv/Scripts/python.exe benchmarks/pending/memory_choice.py --offline   # replay, free
    .venv/Scripts/python.exe benchmarks/pending/memory_choice.py --live --env-file PATH

Pre-registered in `docs/results/2026-09-25-pending/memory-choice-prereg.md` BEFORE any call.
The live mode refuses to run unless that file exists and quotes this question's hash, so the
question cannot drift from what was registered without the script saying so.

Content is held constant on purpose: every option below is a translation of the criteria and
examples of the three SHIPPED questions (`points.memory.write_questions`: durable, specific,
derivable). Nothing is added from what the memory batches taught (no `common` clause). What is
under test is the FORMAT the vendor proposes, not a better-informed question.

Answers are recorded once to `docs/results/2026-09-25-pending/memory-choice.jsonl` and every
re-run replays them: a non-deterministic provider is never re-rolled.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import pathlib
import random
import sys
from dataclasses import asdict
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmarks"))

import memory_common  # noqa: E402

from sanchopanza.contract import Choice, DeciderUnavailable  # noqa: E402
from sanchopanza.eval import stats  # noqa: E402
from sanchopanza.points import memory  # noqa: E402
from sanchopanza.policy import Thresholds  # noqa: E402
from sanchopanza.providers.chain import FallbackDecider  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider  # noqa: E402

OUT = ROOT / "docs" / "results" / "2026-09-25-pending"
FIXTURE = OUT / "memory-choice.jsonl"
PREREG = OUT / "memory-choice-prereg.md"
POINT = "memory_write_choice"
MAX_RUN_USD = 0.05
BATCHES = (
    ("old", memory_common.OLD),
    ("new", memory_common.NEW),
    ("new2", memory_common.NEW2),
    ("new3", memory_common.NEW3),
)

QUESTION = Choice(
    "An agent keeps two stores: a long-term memory that is read again in every later task, "
    "and the working context of the task in progress. Where does `fact` belong?",
    {
        "long_term": {
            "what": "It will still be true and still matter after the current task is "
            "finished (a stable property of a person, organization, case or system; a decision "
            "taken and why; a constraint, preference or rule that will apply again), AND it is "
            "concrete: it names the entity and states the value, outcome or reason, AND it "
            "cannot be recovered cheaply and exactly by re-reading a source the agent already "
            "has: it is a conclusion, a reconciliation between sources, a negative result, or "
            "something the agent learned by doing and would have to redo",
            "examples": [
                "the registry only serves rulings from 2018 onward",
                "the client asked for the report in Spanish",
                "we ruled out the 2019 case: different defendant with the same name",
                "the two registries disagree on the depth; the official one is SGC",
                "the portal rejects requests without a referer header",
            ],
        },
        "session_only": {
            "what": "It matters only for the task in progress: the state of the current step, "
            "a transient value, a plan for the next few minutes, or a restatement of the task "
            "that was just given",
            "examples": [
                "we are on search number four",
                "the page is loading slowly today",
                "the user asked us to investigate this company",
            ],
        },
        "drop": {
            "what": "It is not worth keeping at all: a generality, a summary of the obvious, or "
            "a pointer with no content; or a verbatim copy of, or a direct lookup in, something "
            "durable and reachable (a file in the repository, a row in the database, a document "
            "already downloaded) that can be re-read exactly at any time",
            "examples": [
                "there is relevant information about the company",
                "defamation law has changed over the years",
                "the function is defined in agent/harness/motor.py",
                "the ruling's text says '500,000 pesos' in its third page",
            ],
        },
    },
)


def question_hash() -> str:
    body = json.dumps(asdict(QUESTION), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def _read_key(env_file: pathlib.Path) -> str:
    for line in env_file.read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "TYPESAFE_API_KEY":
            return value.strip().strip('"').strip("'")
    raise SystemExit("TYPESAFE_API_KEY not found in the env file")


def _choice_decider(live: bool, env_file: pathlib.Path | None) -> Any:
    recorded = RecordedDecider.from_file(FIXTURE)
    if not live:
        return recorded
    if not PREREG.exists() or question_hash() not in PREREG.read_text(encoding="utf-8"):
        raise SystemExit("pre-registration missing or does not quote this question's hash")
    from sanchopanza.providers.jev import JevDecider

    key = _read_key(env_file) if env_file else None
    return FallbackDecider([recorded, RecordingDecider(JevDecider(key), FIXTURE)])


async def collect(live: bool, env_file: pathlib.Path | None) -> list[dict[str, Any]]:
    shipped_dec = memory_common.decider(offline=True)
    choice_dec = _choice_decider(live, env_file)
    published = {
        r["id"]: r["shipped"]
        for r in json.loads(
            (ROOT / "docs/results/2026-09-25-window/memory-common.json").read_text(encoding="utf-8")
        )
    }
    t = Thresholds()
    rows, spent = [], 0.0
    for batch, names in BATCHES:
        for case in memory_common.load(names):
            fact = case["input"]["fact"]
            s3, q3 = memory.write_questions(fact=fact)
            three = await shipped_dec.decide("memory_write", s3, q3)
            shipped = memory.decide_write(three, t)
            verdict = "store" if shipped.store else "skip"
            if verdict != published[case["id"]]:
                raise SystemExit(f"{case['id']}: baseline replay differs from memory-common.json")
            if spent > MAX_RUN_USD:
                raise SystemExit(f"passed {MAX_RUN_USD} USD after {len(rows)} cases; stopped")
            try:
                d = await choice_dec.decide(POINT, {"fact": fact}, {"where": QUESTION})
                spent += d.cost_usd if d.provider == "jev" else 0.0
                a = d.answer("where")
            except DeciderUnavailable:
                a = None
            rows.append(
                {
                    "id": case["id"],
                    "batch": batch,
                    "family": memory_common._family(case["id"]),
                    "expected": case["expected"],
                    "shipped": verdict,
                    "composite": min(shipped.durable, shipped.specific, 1.0 - shipped.derivable),
                    "choice": None if a is None or a.empty else a.choice,
                    "confidence": None if a is None or a.empty else a.confidence,
                    "probabilities": {} if a is None else dict(a.probabilities),
                }
            )
    print(f"spent this run: {spent:.5f} USD (live calls only)")
    return rows


def _p_long(r: dict[str, Any]) -> float | None:
    if r["choice"] is None:
        return None
    probs = r["probabilities"]
    if "long_term" in probs:
        return float(probs["long_term"])
    return None


def _verdicts(r: dict[str, Any]) -> dict[str, str]:
    p = _p_long(r)
    return {
        "choice_argmax": "store" if r["choice"] == "long_term" else "skip",
        "choice_p070": "store" if (p is not None and p >= Thresholds().remember) else "skip",
    }


def _null_ece(ps: list[float], sims: int = 2000, seed: int = 7) -> tuple[float, float]:
    """Mean and 95th percentile ECE of a PERFECTLY calibrated model with these probabilities."""
    rng = random.Random(seed)
    values = sorted(stats.ece(ps, [rng.random() < p for p in ps]) for _ in range(sims))
    return sum(values) / sims, values[int(0.95 * sims)]


def analyse(rows: list[dict[str, Any]]) -> dict[str, Any]:
    for r in rows:
        r.update(_verdicts(r))
    out: dict[str, Any] = {"n": len(rows), "question_hash": question_hash()}
    out["answered"] = sum(r["choice"] is not None for r in rows)
    out["with_distribution"] = sum(_p_long(r) is not None for r in rows)
    out["choice_counts"] = {
        k: sum(r["choice"] == k for r in rows) for k in ("long_term", "session_only", "drop", None)
    }

    def cell(sub: list[dict[str, Any]], pol: str) -> dict[str, Any]:
        ok = sum(r[pol] == r["expected"] for r in sub)
        return {
            "agree": ok,
            "n": len(sub),
            "wilson": [round(x, 3) for x in stats.wilson(ok, len(sub))],
            "costly": sum(r[pol] == "store" and r["expected"] == "skip" for r in sub),
            "safe": sum(r[pol] == "skip" and r["expected"] == "store" for r in sub),
        }

    policies = ("shipped", "choice_argmax", "choice_p070")
    groups = {"all": rows, **{b: [r for r in rows if r["batch"] == b] for b, _ in BATCHES}}
    out["table"] = {g: {p: cell(sub, p) for p in policies} for g, sub in groups.items()}
    fams = sorted({r["family"] for r in rows if r["family"] != "-"})
    out["families"] = {
        f: {p: sum(r[p] == r["expected"] for r in rows if r["family"] == f) for p in policies}
        for f in fams
    }
    right = {p: [r[p] == r["expected"] for r in rows] for p in policies}
    skips = [r for r in rows if r["expected"] == "skip"]
    costly = {p: [r[p] == "store" for r in skips] for p in policies}
    out["tests"] = {}
    for p in ("choice_argmax", "choice_p070"):
        a_only, b_only, pv = stats.mcnemar(right[p], right["shipped"])
        diff = stats.bootstrap_difference(right[p], right["shipped"])
        c_only, s_only, pc = stats.mcnemar(costly[p], costly["shipped"])
        out["tests"][p] = {
            "mcnemar_agreement": {
                "only_choice_right": a_only,
                "only_shipped_right": b_only,
                "p": round(pv, 4),
            },
            "difference_ci": [round(x, 3) for x in diff],
            "mcnemar_costly": {
                "only_choice_costly": c_only,
                "only_shipped_costly": s_only,
                "p": round(pc, 4),
            },
        }
    truths = [r["expected"] == "store" for r in rows]
    have = [(r, _p_long(r)) for r in rows if _p_long(r) is not None]
    calib: dict[str, Any] = {}
    if have:
        ps = [p for _, p in have]
        ys = [r["expected"] == "store" for r, _ in have]
        calib["choice_p_long_term"] = {
            "n": len(ps),
            "ece": round(stats.ece(ps, ys), 3),
            "auc": round(stats.auc(ps, ys), 3),
            "brier": round(stats.brier(ps, ys), 3),
            "null_ece_mean_p95": [round(x, 3) for x in _null_ece(ps)],
        }
    conf = [
        (r["confidence"], r["choice_argmax"] == r["expected"])
        for r in rows
        if r["confidence"] is not None
    ]
    if conf:
        cs = [c for c, _ in conf]
        calib["choice_confidence_vs_correct"] = {
            "n": len(cs),
            "ece": round(stats.ece(cs, [y for _, y in conf]), 3),
            "mean_confidence": round(sum(cs) / len(cs), 3),
            "agreement": round(sum(y for _, y in conf) / len(conf), 3),
            "null_ece_mean_p95": [round(x, 3) for x in _null_ece(cs)],
        }
    comp = [r["composite"] for r in rows]
    calib["shipped_composite_min"] = {
        "n": len(comp),
        "ece": round(stats.ece(comp, truths), 3),
        "auc": round(stats.auc(comp, truths), 3),
        "brier": round(stats.brier(comp, truths), 3),
        "null_ece_mean_p95": [round(x, 3) for x in _null_ece(comp)],
    }
    out["calibration"] = calib
    out["decision"] = _decide(out)
    return out


def _decide(out: dict[str, Any]) -> str:
    """The pre-registered rule, applied to the primary policy (argmax) on all cases."""
    t = out["tests"]["choice_argmax"]
    ch, sh = out["table"]["all"]["choice_argmax"], out["table"]["all"]["shipped"]
    sig_better = t["mcnemar_agreement"]["p"] < 0.05 and ch["agree"] > sh["agree"]
    sig_worse = t["mcnemar_agreement"]["p"] < 0.05 and ch["agree"] < sh["agree"]
    costly_worse = (
        t["mcnemar_costly"]["p"] < 0.05
        and t["mcnemar_costly"]["only_choice_costly"] > t["mcnemar_costly"]["only_shipped_costly"]
    )
    if sig_worse or costly_worse:
        return "WORSE"
    if sig_better and ch["costly"] <= sh["costly"]:
        return "BETTER"
    if sig_better:
        return "TRADE"
    return "INDISTINGUISHABLE"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--hash", action="store_true")
    mode.add_argument("--offline", action="store_true")
    mode.add_argument("--live", action="store_true")
    ap.add_argument("--env-file", type=pathlib.Path)
    args = ap.parse_args()
    if args.hash:
        print(question_hash())
        return 0
    rows = asyncio.run(collect(args.live, args.env_file))
    result = analyse(rows)
    (OUT / "memory-choice.json").write_text(
        json.dumps({"summary": result, "rows": rows}, indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
