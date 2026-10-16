"""C5: `select_passages(fit_chars=3400, fit_score=False)` against page order, fresh questions.

    python -I benchmarks/passage_fit/free_confirm.py export PARQUET  # free: QASPER validation
    python -I benchmarks/passage_fit/free_confirm.py rows            # free: the questions
    python -I benchmarks/passage_fit/free_confirm.py dry             # free: calls and cost, stub
    python -I benchmarks/passage_fit/free_confirm.py seal            # once, before any answer
    python -I benchmarks/passage_fit/free_confirm.py paid --launcher c5-free-run.cmd  # Jev
    python -I benchmarks/passage_fit/free_confirm.py report          # free once recorded

Pre-registered in docs/results/2026-10-16-c5-free/prereg.md (a draft until sealed).

B4 (docs/results/2026-10-16-b4-order/) found, exploring, that the free order (best sentence
probability, then tournament probability) kept +13.6 points [+7.1, +20.2] more answer sentences
than page order when what `select_passages` keeps from a QASPER test paper is longer than 3,400
characters. Here the budget, the order and the comparison are fixed before any answer, on the
QASPER validation split (CC BY 4.0), which no run of this package has read.

Per question, the shipped `Squire.select_passages` runs twice through one asker: without a
budget (what a caller gets today; PAGE cuts it in page order) and with `fit_chars=3400,
fit_score=False` (FREE, the option under test). The second run makes no call the first did not
(the asker's memo answers it): one question costs one `select_passages`. The asker is B6's
(`b6_run.Asker`: recording first, one live call on a miss, never retried, at most 4 in flight,
stopped by a cap refusal, an outage or three failures in a row) over this lot's recording.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import pathlib
import random
import sys
import time
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmarks"))
sys.path.insert(0, str(ROOT / "benchmarks" / "b6_es"))
sys.path.insert(0, str(ROOT / "benchmarks" / "jev114"))
sys.path.insert(0, str(HERE))

import b6_run as br  # noqa: E402
import l4_stats as ls  # noqa: E402
import orders as od  # noqa: E402
import paid_once  # noqa: E402
import w17_round  # noqa: E402

from sanchopanza import _lockfile  # noqa: E402
from sanchopanza.text import split_sentences  # noqa: E402


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sentences = _load("longdocs_sentences", ROOT / "benchmarks" / "longdocs" / "sentences.py")
ld = sentences.ld  # the 2026-09-27 builder: `eligible`, the paper's paragraphs

RESULTS = ROOT / "docs" / "results" / "2026-10-16-c5-free"
PREREG = RESULTS / "prereg.md"
NAME = "c5-free"
HOME = pathlib.Path.home() / ".cache" / "sanchopanza"
QASPER = pathlib.Path.home() / ".cache" / "sancho" / "qasper-validation.jsonl"
PARQUET_SHA256 = "089781b91c337d348dd9e8b57cc8adc100ed2d9cab84a6127402bcccf1559222"
QASPER_SHA256 = "1824533661cc2f8b4c442a9444ea62ac87b56c99b0aee1782f7c41464da1ab29"  # `export`, LF
FIXTURE = ROOT / "fixtures" / NAME / "recording.jsonl"
MODEL = br.MODEL  # jev-1.13.0
BUDGET = 3_400  # B4's budget: the median delivered size on its 261 derivation questions
CAP_USD = w17_round.BATCH_CAPS[NAME]  # 2.00, this batch's cap on the round's ledger
SEED = 20261018
# The squire's own dollar meter is no cap here: it charges a decision again each time the memo
# or the recording answers it, so a cap there cut the second run of a question to defaults
# (C5's sealed run: 1,437 of FREE's decisions, and 246 of PAGE's calls never asked on the first
# launch). The caps are the ledger's (`CappedDecider`, batch and round).
SQUIRE_CAP_USD = 1e9
SEALED_SQUIRE_CAP_USD = 2.00  # what the sealed instrument (319ee79) passed: replays analysis.json
POSTDATA_LABEL = ("post-data amendment, labelled: the sealed run's recorded answers, read with "
                  "the squire's own cap lifted; not the sealed verdict")  # fmt: skip
USD_PER_CALL = 0.537 / 5_132  # the QASPER whole-papers run, settled in its ledger (not the bill)
# The launcher is not here: the seal fixes it (`launcher_digest`, its local values as
# placeholders), and a copy filled in place must not fail the instrument check.
INSTRUMENT = ("src", "benchmarks/passage_fit", "benchmarks/b6_es", "benchmarks/paid_once.py",
              "benchmarks/jev114/l4_stats.py", "benchmarks/longdocs",
              "benchmarks/triage_sets/run.py", "benchmarks/w17_round.py")  # fmt: skip


def lot() -> paid_once.Lot:
    return paid_once.Lot(
        name=NAME,
        prereg=PREREG,
        launcher=ROOT / "c5-free-run.cmd",
        fixture=FIXTURE,
        model=MODEL,
        cap_usd=CAP_USD,
        instrument=INSTRUMENT,
        inputs=((QASPER, QASPER_SHA256),),
        home=HOME,
        shared_ledger=w17_round.LEDGER,
        shared_cap_usd=w17_round.CAP_USD,
    )


def lot_asker(fallback: Any | None) -> br.Asker:
    return br.Asker(
        fallback, recorded=paid_once.recorded(lot()), memo_failures=True, model_halts=True
    )


# ---- data ----------------------------------------------------------------------------------


def export(parquet: pathlib.Path) -> str:
    """QASPER's parquet, one paper a JSON line (`to_pylist`, the recipe that rebuilds the test
    export's content exactly), LF; returns the file's sha256."""
    import pyarrow.parquet as pq

    if paid_once.raw_digest(parquet) != PARQUET_SHA256:
        raise SystemExit(f"{parquet} is not the registered QASPER validation parquet")
    rows = pq.read_table(str(parquet)).to_pylist()
    text = "".join(json.dumps(r) + "\n" for r in rows)
    QASPER.write_bytes(text.encode("utf-8"))
    return paid_once.raw_digest(QASPER)


def papers_of(path: pathlib.Path) -> dict[str, dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return {p["id"]: p for p in (json.loads(x) for x in lines if x)}


def every_question(papers: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Every question whose first answer has evidence paragraphs in the paper (`ld.eligible`),
    pages as the 2026-09-27 runs built them; each distinct question of a paper once."""
    rows = []
    for pid in sorted(papers):
        ft = papers[pid]["full_text"]
        pages = [(str(s or ""), str(p).strip()) for s, ps in
                 zip(ft["section_name"], ft["paragraphs"], strict=True)
                 for p in ps if p and str(p).strip()]  # fmt: skip
        texts = {x for _, x in pages}
        seen: set[str] = set()
        qas = papers[pid]["qas"]
        for question, answers in zip(qas["question"], qas["answers"], strict=True):
            first = (answers.get("answer") or [None])[0]
            evidence = ld.eligible(first, texts) if first else None
            if not evidence or question.strip() in seen:
                continue
            seen.add(question.strip())
            gold = [x in set(evidence) for _, x in pages]
            rows.append({"id": f"{pid}#{len(seen)}", "paper": pid,
                         "question": question.strip(), "pages": pages, "gold": gold})  # fmt: skip
    return rows


def aligned(row: dict[str, Any]) -> bool:
    """The gold sentences (`sentences.enrich`) are in `select_passages`' own sentences."""
    return all(
        [para[a:b] for a, b in ranges] == split_sentences(text)
        for (_, text), para, ranges in zip(
            row["pages"], row["paras"], row["sentences"], strict=True
        )
    )


def build_rows(path: pathlib.Path = QASPER) -> tuple[list[dict[str, Any]], dict[str, int]]:
    papers = papers_of(path)
    asked = every_question(papers)
    # `enrich` finds a question by its text in the paper: the id carries the paper
    found, unlocated = sentences.enrich([{**r, "id": r["paper"]} for r in asked], papers)
    rows, misaligned = [], 0
    by_text = {(r["paper"], r["question"]): r["id"] for r in asked}
    for row in found:
        if not aligned(row):
            misaligned += 1
            continue
        rows.append({**row, "id": by_text[(row["paper"], row["question"])]})
    random.Random(SEED).shuffle(rows)
    counts = {"papers": len(papers), "eligible": len(asked), "unlocated": len(unlocated),
              "misaligned": misaligned, "rows": len(rows)}  # fmt: skip
    return rows, counts


def load_rows() -> list[dict[str, Any]]:
    if not QASPER_SHA256 or paid_once.raw_digest(QASPER) != QASPER_SHA256:
        raise SystemExit(f"{QASPER} is not the registered export: run `export` first")
    return build_rows()[0]


# ---- asking and scoring --------------------------------------------------------------------


async def ask(rows: list[dict[str, Any]], asker: br.Asker, *,
              squire_cap: float = SQUIRE_CAP_USD) -> list[dict[str, Any]]:  # fmt: skip
    """Per question: `select_passages` without a budget, then with FREE's. `squire_cap` at
    `SEALED_SQUIRE_CAP_USD` is the sealed run's setting, kept to replay its report."""
    squire = br.squire(asker, "select", squire_cap)

    async def one(row: dict[str, Any]) -> dict[str, Any]:
        br.ROW.set(row["id"])
        full = await squire.select_passages(purpose=row["question"], pages=row["pages"])
        free = await squire.select_passages(purpose=row["question"], pages=row["pages"],
                                            fit_chars=BUDGET, fit_score=False)  # fmt: skip
        return {"id": row["id"], "full": full, "free": free}

    return list(await asyncio.gather(*(one(row) for row in rows)))  # in the seeded row order


def mask_of(row: dict[str, Any], entries: list[Any]) -> list[list[bool]]:
    return [[bool(k) for k, _ in e] if e is not None else [False] * len(r)
            for e, r in zip(entries, row["sentences"], strict=True)]  # fmt: skip


def arms(row: dict[str, Any], got: dict[str, Any]) -> dict[str, Any]:
    """Recall (share of answer sentences kept) and all-gold per arm under BUDGET."""
    full = mask_of(row, got["full"])
    items = od.delivered(row, full)
    gold = [sum(row["gold_s"][it.index]) for it in items]
    cuts = {
        "PAGE": od.under_budget(full, items, list(range(len(items))), BUDGET),
        "BM25": od.under_budget(full, items, od.bm25_order(row["question"], items), BUDGET),
        "GOLD": od.under_budget(full, items, sorted(range(len(items)), key=lambda j: (-gold[j], j)),
                                BUDGET),
        "FREE": mask_of(row, got["free"]),
    }  # fmt: skip
    out: dict[str, Any] = {"overflow": od.total(items) > BUDGET}
    for arm, mask in cuts.items():
        hit, total = od.gold_kept(row, mask)
        out[arm] = {"recall": hit / total if total else 0.0, "all": hit == total,
                    "chars": sum(it.size for it in items if any(mask[it.index]))}  # fmt: skip
    return out


def bounds(values: list[float]) -> tuple[float, float]:
    """The 95 % percentile bounds, unrounded (`l4_stats.ci95`'s positions, without its rounding):
    the verdict compares these."""
    ordered = sorted(values)
    return ordered[int(0.025 * (len(ordered) - 1))], ordered[int(0.975 * (len(ordered) - 1))]


def compare(per: list[dict[str, Any]], papers: list[str], a: str, b: str) -> dict[str, Any]:
    if not per:
        return {"n": 0, "recall_diff": None, "recall_ci95_cluster": None,
                "recall_ci95_cluster_exact": None}  # fmt: skip
    diffs = [p[a]["recall"] - p[b]["recall"] for p in per]

    def mean(idx: list[int]) -> float:
        return sum(diffs[i] for i in idx) / len(idx)

    exact = bounds(ls.bootstrap(mean, ls.clusters_as_units(papers)))
    alls = ls.paired_binary([p[a]["all"] for p in per], [p[b]["all"] for p in per], papers)
    return {
        "n": len(per),
        "recall_diff": round(mean(list(range(len(per)))), 4),
        "recall_ci95_cluster": [round(exact[0], 4), round(exact[1], 4)],
        "recall_ci95_cluster_exact": list(exact),
        "recall_ci95_item": ls.ci95(ls.bootstrap(mean, ls.items_as_units(len(per)))),
        "all_gold": alls,
    }  # fmt: skip


def verdict(primary: dict[str, Any]) -> str:
    """The registered rule, on the unrounded cluster bounds."""
    ci = primary.get("recall_ci95_cluster_exact")
    if ci is None:
        return "no verdict: no question overflows the budget"
    if ci[0] > 0:
        return "FREE confirmed: it keeps more answer sentences than page order at 3,400 characters"
    if ci[1] < 0:
        return "FREE loses to page order"
    return "not confirmed: FREE and page order not told apart"


def report(
    rows: list[dict[str, Any]],
    out: list[dict[str, Any]],
    *,
    unanswered: int = 0,
    affected: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Every reading. With any call unanswered once no launch is left, no verdict: an
    unanswered call keeps its text (the package's rule), which pulls FREE toward PAGE; the
    readings without the affected questions are then a sensitivity, not a verdict."""
    got = readings(rows, out)
    if unanswered:
        clean = [g for g in out if g["id"] not in affected]
        kept = [r for r in rows if r["id"] not in affected]
        return {**got, "verdict": f"no verdict: incomplete, {unanswered} calls unanswered",
                "sensitivity_without_affected": {"questions_left_out": len(affected),
                                                 **readings(kept, clean)}}  # fmt: skip
    return got


def readings(rows: list[dict[str, Any]], out: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {r["id"]: r for r in rows}
    per_all = [(by_id[g["id"]], arms(by_id[g["id"]], g)) for g in out]
    over = [(r, a) for r, a in per_all if a["overflow"]]
    papers = [r["paper"] for r, _ in over]
    per = [a for _, a in over]
    pairs = {f"{a}-{b}": compare(per, papers, a, b)
             for a, b in (("FREE", "PAGE"), ("BM25", "PAGE"), ("GOLD", "PAGE"))}  # fmt: skip
    return {
        "budget_chars": BUDGET,
        "questions": len(rows),
        "papers": len({r["paper"] for r in rows}),
        "overflowing": {"n": len(over), "papers": len(set(papers))},
        "arms": {
            arm: {
                "recall": round(sum(p[arm]["recall"] for p in per) / max(1, len(per)), 4),
                "all_gold": round(sum(p[arm]["all"] for p in per) / max(1, len(per)), 4),
                "chars_mean": round(sum(p[arm]["chars"] for p in per) / max(1, len(per)), 1),
            }
            for arm in ("PAGE", "BM25", "FREE", "GOLD")
        },  # fmt: skip
        "paired": pairs,
        "verdict": verdict(pairs["FREE-PAGE"]),
    }


def dry(rows: list[dict[str, Any]]) -> dict[str, Any]:
    asker = lot_asker(br.Stub())
    asyncio.run(ask(rows, asker))
    c = asker.calls.get("select", {"calls": 0, "pessimistic_usd": 0.0, "expected_usd": 0.0})
    return {"questions": len(rows), **{k: round(v, 4) for k, v in c.items()},
            "usd_at_qasper_ledger_rate": round(c["calls"] * USD_PER_CALL, 4),
            "cap_usd": CAP_USD, "fits_under_cap": c["pessimistic_usd"] <= CAP_USD,
            "claude_usd": 0.0}  # fmt: skip


# ---- paying (as C6's: `c6_window.paid`) ----------------------------------------------------


def make_live(the_lot: paid_once.Lot) -> tuple[Any, Any]:  # pragma: no cover - real client
    """The Jev client without its retry of a 429 (a 429 stops the run; it still retries a 529
    up to 3 times inside one call, and does not retry a timeout), capped on the
    round's shared ledger under this batch's cap, and recorded."""
    from sanchopanza.providers import CappedDecider, jev
    from sanchopanza.providers.jev import JevDecider
    from sanchopanza.providers.recorded import RecordingDecider

    jev.RETRYABLE = frozenset(jev.RETRYABLE - {429})
    inner = JevDecider(model=MODEL, long_context=False, images=False, timeout_s=br.TIMEOUT_S)
    capped = CappedDecider(inner, ledger=paid_once.ledger_of(the_lot), batch=NAME,
                           max_usd=CAP_USD)  # fmt: skip
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    return inner, RecordingDecider(capped, FIXTURE)


def stopped_by(asker: br.Asker) -> str | None:
    if asker.halted:
        kind, why = asker.halted[0]
        if kind == "model":
            return f"model moved: {why}"
        return f"SpendCapReached: {why}" if kind == "cap" else why
    return f"{asker.failures} calls unanswered" if asker.failures else None


async def session(rows: list[dict[str, Any]], the_lot: paid_once.Lot, check: Any,
                  build_live: Any, on_start: Any) -> dict[str, Any]:  # fmt: skip
    await check(MODEL)
    on_start()
    inner, live = build_live(the_lot)
    asker = lot_asker(live)
    try:
        await ask(rows, asker)
    finally:
        close = getattr(inner, "aclose", None)
        if close is not None:
            await close()
    why = stopped_by(asker)
    return {"calls": {a: round(c["calls"]) for a, c in asker.calls.items()},
            "stopped": why, "stop_kind": paid_once.stop_kind(why)}  # fmt: skip


def paid(launcher: pathlib.Path | None, *, load_key: Any = paid_once.load_key,
         check: Any = paid_once.preflight, build_live: Any = make_live) -> int:  # fmt: skip
    the_lot = lot()
    if (
        launcher is None
        or not launcher.is_file()
        or (paid_once.launcher_digest(launcher) != paid_once.launcher_digest(the_lot.launcher))
    ):
        raise SystemExit("a paid run starts from c5-free-run.cmd (--launcher): nothing spent")
    rows = load_rows()
    plan = dry(rows)
    room = paid_once.room(the_lot)  # this batch's cap and the round's, whichever is less
    if plan["pessimistic_usd"] > room:
        raise SystemExit(f"{plan['pessimistic_usd']} USD does not fit in the {room:.4f} left")
    paid_once.require_sealed(the_lot)
    commit = paid_once.require_instrument(the_lot)
    paid_once.require_inputs(the_lot)
    the_lot.run_dir.mkdir(parents=True, exist_ok=True)
    with _lockfile.locked(the_lot.run_dir / "paid", wait_s=1.0,
                          stale_s=paid_once.LOCK_STALE_S, strict=True):  # fmt: skip
        past = paid_once.history(the_lot)
        if not paid_once.may_launch(past):
            raise SystemExit("launch rule: no launch left (one relaunch at most, none after "
                             "a 402, a 429, the cap or another model)")  # fmt: skip
        if not past and FIXTURE.exists() and FIXTURE.stat().st_size:
            raise SystemExit(f"first launch, but {FIXTURE.name} holds answers: nothing spent")
        load_key()
        start = {"event": "start", "head": paid_once.head(), "instrument": commit,
                 "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "plan": plan}  # fmt: skip
        result = asyncio.run(session(rows, the_lot, check, build_live,
                                     lambda: paid_once._note(the_lot, start)))  # fmt: skip
        paid_once._note(the_lot, {"event": "end", **result})
    print(json.dumps(result, indent=1))
    return 0 if result["stopped"] is None else 2


def analysis(squire_cap: float = SQUIRE_CAP_USD) -> dict[str, Any]:
    rows = load_rows()
    asker = lot_asker(None)
    out = asyncio.run(ask(rows, asker, squire_cap=squire_cap))
    missing = unanswered(asker)
    if paid_once.unanswered_blocks(lot(), missing):
        raise SystemExit(f"{missing} calls unanswered and a launch is still allowed")
    got = report(rows, out, unanswered=missing, affected=frozenset(asker.failed_ids))
    return {"head": paid_once.head(), "unanswered_calls": missing, **got}


def unanswered(asker: br.Asker) -> int:
    """Distinct calls without an answer: PAGE's and FREE's runs ask the same calls, and an
    unanswered one is met by both."""
    return len(asker.failed_keys)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("action", choices=("export", "rows", "dry", "seal", "paid", "report",
                                       "postdata"))  # fmt: skip
    ap.add_argument("parquet", nargs="?", type=pathlib.Path)
    ap.add_argument("--launcher", type=pathlib.Path)
    args = ap.parse_args()
    if args.action == "export":
        if args.parquet is None:
            raise SystemExit("export PARQUET: the downloaded QASPER validation parquet")
        print(export(args.parquet))
        return 0
    if args.action == "rows":
        print(json.dumps(build_rows()[1], indent=1))
        return 0
    if args.action == "seal":
        print(paid_once.seal(lot()))
        return 0
    if args.action == "paid":
        return paid(args.launcher)
    if args.action == "report":  # the sealed run's own report, replayed: analysis.json
        result = analysis(SEALED_SQUIRE_CAP_USD)
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / "analysis.json").write_bytes((json.dumps(result, indent=1) + "\n").encode())
        print(json.dumps(result, indent=1))
        return 0
    if args.action == "postdata":  # the same answers, the squire's cap lifted: labelled
        result = {"reading": POSTDATA_LABEL, **analysis(SQUIRE_CAP_USD)}
        out = RESULTS / "analysis-postdata.json"
        out.write_bytes((json.dumps(result, indent=1) + "\n").encode())
        print(json.dumps(result, indent=1))
        return 0
    print(json.dumps(dry(load_rows()), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
