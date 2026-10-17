"""The BM25 prefilter probe's reading, free: its recording replayed, its rule applied.

    python -I benchmarks/longdoc_free/probe_read.py     # after the probe's launch; no call

Sealed in docs/results/2026-10-17-lfree-bm25-dry/prereg-probe.md. Per question of
`jev_phase.PROBE_IDS`: the real Jev the probe billed (its recording's `cost_usd`, every call:
tournament, sentences, gate) and its real tournament calls, beside what the dry oracle predicted
for the same question at the same K (`bm25_dry.Oracle` over the dev's recorded rounds). The rule:
a new dev is worth preparing only if the questions' mean real Jev is at most RULE_MEAN_USD and
none exceeds RULE_MAX_USD. A probe whose launch did not end with every call answered (the cap,
a 402, a 429, an outage, another model, one failed call, a kill), or whose recording does not
answer every call of the replay, is "decided by spend" (a no) when its bills already say no
(`probe_verdict`), else "not run". Calls are counted from the recording: recorded calls only.
"""

from __future__ import annotations

import gzip
import importlib.util
import json
import pathlib
import statistics
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent


def _load(name: str, path: pathlib.Path) -> Any:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


dry = _load("lf_bm25_dry", HERE / "bm25_dry.py")
jp = dry.jp

from sanchopanza.providers.recorded import RecordedDecider  # noqa: E402

RULE_MEAN_USD = 0.015
RULE_MAX_USD = 0.031
RULE_TOTAL_USD = 3 * RULE_MEAN_USD  # the mean over the 3 questions, as a total: 0.045


def probe_verdict(
    questions: list[dict[str, Any]],
    *,
    ran: bool,
    settled_usd: float = 0.0,
    stop_kind: str | None = None,
) -> dict[str, Any]:
    """The sealed rule over each question's real Jev (`real_usd`, unrounded). A probe that did
    not run to the end is "decided by spend", a no, when what it already billed says no
    whatever the rest would cost (bills only add up): it stopped at the cap, its recorded bills
    (`settled_usd`) are past the 3 questions' 0.045, or one question's recorded bills are past
    0.031. Any other stop is "not run"."""
    if ran:
        spent = [q["real_usd"] for q in questions]
        mean, dearest = statistics.fmean(spent), max(spent)
        return {"status": "run", "mean_usd": round(mean, 4), "max_usd": round(dearest, 4),
                "prepare_new_dev": mean <= RULE_MEAN_USD and dearest <= RULE_MAX_USD}  # fmt: skip
    over = [q for q in questions if q["real_usd"] > RULE_MAX_USD]
    if stop_kind == "cap" or settled_usd > RULE_TOTAL_USD or over:
        why = ("stopped at the cap" if stop_kind == "cap"
               else f"{settled_usd:.4f} USD billed, past {RULE_TOTAL_USD:.3f}"
               if settled_usd > RULE_TOTAL_USD
               else f"a question billed past {RULE_MAX_USD}")  # fmt: skip
        return {"status": "decided by spend", "why": why, "prepare_new_dev": False}
    return {"status": "not run", "prepare_new_dev": None}


def lines_of(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return [json.loads(x) for x in handle if x.strip()]


def recorded_lines(the_lot: Any) -> list[dict[str, Any]]:
    """The lot's recorded lines from its model, from the plain file or its `.gz`."""
    lines = lines_of(jp.recording_path(the_lot))
    return [x for x in lines if the_lot.serves(str(x.get("model") or ""))]


def launched_cleanly(the_lot: Any) -> tuple[bool, str]:
    past = jp.paid_once.history(the_lot)
    if not past:
        return False, "no launch"
    last = past[-1]
    if last.get("stop_kind") is not None:
        return False, f"stopped: {last.get('stop_kind')} ({last.get('stopped')})"
    return True, "every call answered"


def stop_kind_of(the_lot: Any) -> str | None:
    past = jp.paid_once.history(the_lot)
    return past[-1].get("stop_kind") if past else "no launch"


def read() -> dict[str, Any]:
    the_lot = jp.lot(jp.PROBE)
    rows = jp.load_rows(jp.PROBE)
    lines = recorded_lines(the_lot)
    costs = {str(x["key"]): float(x.get("cost_usd") or 0.0) for x in lines}
    probe = dry.Counting(RecordedDecider(lines), costs, answered_only=True)  # recorded calls
    asker = dry.asker_over(None, probe)
    dry.run(rows, asker, jp.PROBE_K)
    clean, why = launched_cleanly(the_lot)
    complete = not asker.failed_keys
    settled = sum(costs.values())

    dev_lines = dry.recording()
    real_dev = dry.replay_real(rows, dev_lines)
    oracle = dry.Counting(dry.Oracle(real_dev["counting"].rounds, RecordedDecider(dev_lines)))
    dry.run(rows, dry.asker_over(oracle), jp.PROBE_K)

    questions = []
    for row in rows:
        rid = str(row["id"])
        got, predicted = probe.by_row.get(rid, {}), oracle.by_row[rid]
        questions.append({
            "id": row["id"],
            "complete": rid not in asker.failed_ids,
            "real_tournament_calls": int(got.get("calls_triage_pages", 0)),
            "oracle_tournament_calls": int(predicted["calls_triage_pages"]),
            "real_sentence_calls": int(got.get("calls_select_sentences", 0)),
            "real_usd": sum(got.get(f"usd_{p}", 0.0) for p in dry.POINTS),  # the rule's: unrounded
            "oracle_usd": round(dry.usd(predicted, real_dev["factor"], dry.POINTS), 6),
            "dev_full_novel_usd": round(
                sum(real_dev["counting"].by_row[rid].get(f"usd_{p}", 0.0) for p in dry.POINTS), 6
            ),
        })  # fmt: skip
    return {
        "k": jp.PROBE_K,
        "ids": list(jp.PROBE_IDS),
        "launch": why,
        "recording_complete": complete,
        "recorded_bills_usd": round(settled, 6),
        "ledger_spent_usd": round(jp.paid_once.spent(the_lot), 6),
        "cap_usd": the_lot.cap_usd,
        "questions": questions,
        "verdict": probe_verdict(
            questions, ran=clean and complete, settled_usd=settled, stop_kind=stop_kind_of(the_lot)
        ),  # fmt: skip
    }


def main() -> int:
    out = read()
    target = jp.PROBE_DIR / "probe-read.json"
    target.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
