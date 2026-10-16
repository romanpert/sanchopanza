"""C6: the `select_passages` tournament with `page_view="window"` against the head, fresh questions.

    python -I benchmarks/b6_es/c6_window.py build [--data DIR]   # free, offline: rows, manifest
    python -I benchmarks/b6_es/c6_window.py ceiling              # free: views only, no model
    python -I benchmarks/b6_es/c6_window.py dry                  # free: calls and cost, a stub
    python -I benchmarks/b6_es/c6_window.py seal                 # once, before any answer
    python -I benchmarks/b6_es/c6_window.py paid --launcher c6-window-run.cmd   # spends: Jev
    python -I benchmarks/b6_es/c6_window.py report               # free once recorded: verdict

Pre-registered in docs/results/2026-10-16-c6-window/prereg.md (a draft until sealed).

Questions: MLQA v1.0 test (CC BY-SA 3.0) that B6 did not use, whose Spanish article is one of
B6's 614 docs articles, at B6's pinned revisions (CC BY-SA 4.0), read from B6's article cache
offline; the gold sentence is located by B6's own code (`b6_build.doc_row`). Arms, jev-1.13.0,
shipped thresholds and limits, no answering model: `Dh-es`/`Dw-es` and `Dh-en`/`Dw-en`,
`Squire.select_passages(page_view="head"|"window")` over the whole article.

Only questions whose article the window changes are asked (some paragraph shown differently
by `text.match_window`); on every other question both arms send the same requests, get the
same answers and keep the same sentences, a difference of exactly 0. Within a question the
window arm reuses the head arm's answer to any identical request (`b6_run.Asker`'s memo and
the recording), so the arms differ only where a request differs.

Every live call goes through `CappedDecider` on this lot's ledger, is recorded in FIXTURE
(hashed keys, no text), at most `b6_run.CONCURRENCY` in flight, never retried; `paid` refuses
before the key is read unless the seal, the instrument commit, the input's sha256, the cap and
the launch rule hold (`paid_once`). The key comes from TYPESAFE_API_KEY or the file
SANCHOPANZA_KEYS_ENV names, inside the process, never printed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "benchmarks"))
sys.path.insert(0, str(HERE))

import b6_build as bb  # noqa: E402
import b6_run as br  # noqa: E402
import b6_score as sc  # noqa: E402
import b6_wiki as wiki  # noqa: E402
import c6_stats as cs  # noqa: E402
import paid_once  # noqa: E402
import w17_round  # noqa: E402

from sanchopanza import _lockfile  # noqa: E402
from sanchopanza.text import match_window, truncate  # noqa: E402

OUT = REPO / "docs" / "results" / "2026-10-16-c6-window"
PREREG = OUT / "prereg.md"
MANIFEST = OUT / "bench-manifest.json"
NAME = "c6-window"
HOME = Path.home() / ".cache" / "sanchopanza"
INPUT = HOME / NAME / "c6-docs.jsonl"  # built by `build`, outside the repository
# The built file, as `build` writes it (raw bytes, LF): `paid`, `dry` and `report` refuse another.
INPUT_SHA256 = "c040e91417bc2daf78e4d2d428595dc06e0ae19479ec62bbbbaddb533b7841cb"
FIXTURE = REPO / "fixtures" / NAME / "recording.jsonl"  # below fixtures/: its own set
MODEL = br.MODEL  # jev-1.13.0, the production DEFAULT_MODEL
CAP_USD = w17_round.BATCH_CAPS[NAME]  # 4.50 on the round's shared ledger (6.00 over C4-C6)
# The squire's own dollar meter is no cap here: it charges a decision again each time the memo
# or the recording answers it, so a cap there cut the second run of a question to defaults
# (C5's sealed run: 1,437 of FREE's decisions, and 246 of PAGE's calls never asked on the first
# launch). The caps are the ledger's (`CappedDecider`, batch and round).
SQUIRE_CAP_USD = 1e9
VIEW = sc.VIEW  # 900, `chunks.PAGE_LIMIT`
LANGS = ("es", "en")
ARMS = {lang: (f"Dh-{lang}", f"Dw-{lang}") for lang in LANGS}
B6_USD_PER_CALL = 2.5277 / 11_202  # B6's docs bench, billed: what a real call cost there
INSTRUMENT = ("src", "benchmarks/b6_es", "benchmarks/paid_once.py",
              "benchmarks/jev114/l4_stats.py", "benchmarks/w17_round.py",
              "c6-window-run.cmd")  # fmt: skip


def lot() -> paid_once.Lot:
    return paid_once.Lot(
        name=NAME,
        prereg=PREREG,
        launcher=REPO / "c6-window-run.cmd",
        fixture=FIXTURE,
        model=MODEL,
        cap_usd=CAP_USD,
        instrument=INSTRUMENT,
        inputs=((INPUT, INPUT_SHA256),),
        home=HOME,
        shared_ledger=w17_round.LEDGER,
        shared_cap_usd=w17_round.CAP_USD,
    )


def lot_asker(fallback: Any | None) -> br.Asker:
    """B6's asker (recording first, one live call on a miss, never retried, stops on a cap or
    an outage) over this lot's recording, only the lines jev-1.13.0 answered."""
    return br.Asker(fallback, recorded=paid_once.recorded(lot()))


# ---- views ---------------------------------------------------------------------------------


def changed(row: Mapping[str, Any], lang: str) -> bool:
    """Some paragraph of the article is shown differently by the window."""
    side = row[lang]
    return any(
        match_window(t, side["question"], VIEW) != truncate(t, VIEW) for _, t in side["pages"]
    )


def gold_text(row: Mapping[str, Any], lang: str) -> tuple[str, str]:
    """(gold paragraph, its gold sentences as one span of text)."""
    side = row[lang]
    j = side["gold_paragraph"]
    text = side["pages"][j][1]
    ranges = bb.sentence_ranges(text)
    gold = [ranges[i] for i, g in enumerate(side["gold_s"][j]) if g]
    return text, text[gold[0][0] : gold[-1][1]]


def in_view(row: Mapping[str, Any], lang: str) -> tuple[bool, bool]:
    """Whether the gold sentence is in the tournament's view: (head, window)."""
    text, gold = gold_text(row, lang)
    question = row[lang]["question"]
    return gold in truncate(text, VIEW), gold in match_window(text, question, VIEW)


def ceiling(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Free: per language, the questions the window changes, and where the gold sentence
    enters or leaves the view."""
    out: dict[str, Any] = {"questions": len(rows)}
    for lang in LANGS:
        views = [in_view(r, lang) for r in rows]
        out[lang] = {
            "changed_questions": sum(changed(r, lang) for r in rows),
            "paragraphs_shown_differently": sum(
                match_window(t, r[lang]["question"], VIEW) != truncate(t, VIEW)
                for r in rows
                for _, t in r[lang]["pages"]
            ),
            "gold_in_head": sum(h for h, _ in views),
            "gold_enters_view": sum(w and not h for h, w in views),
            "gold_leaves_view": sum(h and not w for h, w in views),
        }
    return out


# ---- the bench -----------------------------------------------------------------------------


def b6_used() -> tuple[set[str], dict[str, Mapping[str, int]], list[str]]:
    """(every id B6 used, the docs bench's revisions by Spanish title, its ids)."""
    manifest = json.loads(bb.MANIFEST.read_text(encoding="utf-8"))
    used = {q for name in ("pages", "docs", "smoke-pages", "smoke-docs")
            for q in manifest[name]["ids"]}  # fmt: skip
    return used, manifest["docs"]["revids"], manifest["docs"]["ids"]


def build(data: Path) -> dict[str, Any]:
    """Every fresh test question in a B6 docs article, offline, in B6's draw order."""
    archive = bb.download(data)
    fetcher = wiki.Fetcher(data / "wiki", offline=True)
    items = bb.load_mlqa(archive, "test")
    used, revids, ids = b6_used()
    by_title = {items[q]["es"]["title"]: revids[q] for q in ids}
    rows: list[dict[str, Any]] = []
    excluded: dict[str, int] = {}
    for qid in bb.draw_order(items):
        pinned = by_title.get(items[qid]["es"]["title"])
        if qid in used or pinned is None:
            continue
        got = bb.doc_row(qid, items[qid], fetcher, pinned)
        if isinstance(got, str):
            excluded[got] = excluded.get(got, 0) + 1
            continue
        rows.append(got)
    sha = bb.write_jsonl(INPUT, rows)
    return {
        "source": bb.MLQA_URL,
        "mlqa_sha256": bb.MLQA_SHA256,
        "licence": bb.MLQA_LICENCE,
        "split": "test",
        "draw": "every MLQA test id B6 did not use whose Spanish article is a B6 docs article, "
        "at B6's pinned revisions, in B6's draw order (seed 20261016)",
        "ids": [r["id"] for r in rows],
        "articles": len({r["es"]["title"] for r in rows}),
        "excluded": dict(sorted(excluded.items())),
        "sha256": sha,
    }


def load_rows() -> list[dict[str, Any]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if (
        manifest["sha256"] != INPUT_SHA256
        or not INPUT.exists()
        or bb.sha256_of(INPUT) != INPUT_SHA256
    ):
        raise SystemExit(f"{INPUT} is not the file in the manifest: run `build` first")
    return [json.loads(x) for x in INPUT.read_text(encoding="utf-8").splitlines() if x]


# ---- asking --------------------------------------------------------------------------------


async def ask(rows: Sequence[Mapping[str, Any]], asker: br.Asker) -> list[dict[str, Any]]:
    """Both arms of each changed language, head first, then the window reusing what is equal."""
    squires = {arm: br.squire(asker, arm, SQUIRE_CAP_USD) for pair in ARMS.values() for arm in pair}

    async def one(position: int, row: Mapping[str, Any]) -> dict[str, Any]:
        br.ROW.set(str(row["id"]))
        out: dict[str, Any] = {"id": row["id"]}
        for lang in br.arm_order(position, LANGS):
            if not changed(row, lang):
                continue
            for arm, view in zip(ARMS[lang], ("head", "window"), strict=True):
                question, pages, _ = sc.doc_inputs(row, arm)
                got = await squires[arm].select_passages(
                    purpose=question, pages=pages, page_view=view
                )
                out[arm] = [None if e is None else [[k, p] for k, p in e] for e in got]
        return out

    return await br.shuffled(one, rows)


def scores(rows: Sequence[Mapping[str, Any]], out: Sequence[Mapping[str, Any]]) -> dict:
    by_lang: dict[str, list[dict[str, Any]]] = {lang: [] for lang in LANGS}
    for row, got in zip(rows, out, strict=True):
        for lang, (h, w) in ARMS.items():
            if h not in got:
                continue
            head_in, window_in = in_view(row, lang)
            by_lang[lang].append({
                "id": row["id"],
                "article": row["es"]["title"],
                "head": sc.doc_score(row, h, sc.doc_mask(row, h, got[h])),
                "window": sc.doc_score(row, w, sc.doc_mask(row, w, got[w])),
                "enters_view": window_in and not head_in,
            })  # fmt: skip
    return by_lang


def dry(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Free: the calls a stub's answers lead to (B6's stub, recordings first), priced three
    ways: `CappedDecider`'s pessimistic reservation (the cap check), the expected factor, and
    B6's billed cost a call."""
    asker = lot_asker(br.Stub())
    asyncio.run(ask(rows, asker))
    calls = sum(c["calls"] for c in asker.calls.values())
    pessimistic = sum(c["pessimistic_usd"] for c in asker.calls.values())
    return {
        "questions": len(rows),
        "by_arm": {
            a: {k: round(v, 4) for k, v in c.items()} for a, c in sorted(asker.calls.items())
        },
        "calls": calls,
        "pessimistic_usd": round(pessimistic, 4),
        "expected_usd": round(sum(c["expected_usd"] for c in asker.calls.values()), 4),
        "usd_at_b6_billed_per_call": round(calls * B6_USD_PER_CALL, 4),
        "cap_usd": CAP_USD,
        "fits_under_cap": pessimistic <= CAP_USD,
        "claude_usd": 0.0,
    }


def analysis(*, paid: bool) -> dict[str, Any]:
    """Free: replay the recording and apply the registered rule."""
    rows = load_rows()
    asker = lot_asker(None)
    out = asyncio.run(ask(rows, asker))
    if paid and paid_once.unanswered_blocks(lot(), asker.failures):
        raise SystemExit(f"{asker.failures} calls unanswered and a launch is still allowed")
    result = cs.report(scores(rows, out), {lang: len(rows) for lang in LANGS})
    return {"head": paid_once.head(), "unanswered_calls": asker.failures, **result}


# ---- paying --------------------------------------------------------------------------------


def make_live(the_lot: paid_once.Lot) -> tuple[Any, Any]:  # pragma: no cover - real client
    """(the Jev client, the capped and recording decider around it), inside the run's loop."""
    from sanchopanza.providers import CappedDecider, jev
    from sanchopanza.providers.jev import JevDecider
    from sanchopanza.providers.recorded import RecordingDecider

    jev.RETRYABLE = frozenset(jev.RETRYABLE - {429})  # a 429 stops the run, never retried
    inner = JevDecider(model=MODEL, long_context=False, images=False, timeout_s=br.TIMEOUT_S)
    capped = CappedDecider(inner, ledger=paid_once.ledger_of(the_lot), batch=NAME, max_usd=CAP_USD)
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    return inner, RecordingDecider(capped, FIXTURE)


def stopped_by(asker: br.Asker) -> str | None:
    if asker.halted:
        kind, why = asker.halted[0]
        return f"SpendCapReached: {why}" if kind == "cap" else why
    return f"{asker.failures} calls unanswered" if asker.failures else None


async def session(rows: Sequence[Mapping[str, Any]], the_lot: paid_once.Lot, check: Any,
                  build_live: Any, on_start: Any) -> dict[str, Any]:  # fmt: skip
    """The preflight, the live client, every call and its close, in ONE event loop."""
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
            "failed_ids": sorted(asker.failed_ids), "stopped": why,
            "stop_kind": paid_once.stop_kind(why)}  # fmt: skip


def paid(launcher: Path | None, *, load_key: Any = paid_once.load_key,
         check: Any = paid_once.preflight, build_live: Any = make_live) -> int:  # fmt: skip
    """Every check, then the key, then `session`. Tests pass traps for the last three."""
    the_lot = lot()
    if (
        launcher is None
        or not launcher.is_file()
        or (paid_once.launcher_digest(launcher) != paid_once.launcher_digest(the_lot.launcher))
    ):
        raise SystemExit("a paid run starts from c6-window-run.cmd (--launcher): nothing spent")
    rows = load_rows()
    plan = dry(rows)
    room = paid_once.room(the_lot)  # this batch's cap and the round's, whichever is less
    if plan["pessimistic_usd"] > room:
        raise SystemExit(f"{plan['pessimistic_usd']} USD does not fit in the {room:.4f} left")
    paid_once.require_sealed(the_lot)
    commit = paid_once.require_instrument(the_lot)
    paid_once.require_inputs(the_lot)
    the_lot.run_dir.mkdir(parents=True, exist_ok=True)
    lock = the_lot.run_dir / "paid"
    with _lockfile.locked(lock, wait_s=1.0, stale_s=paid_once.LOCK_STALE_S, strict=True):
        past = paid_once.history(the_lot)
        if not paid_once.may_launch(past):
            raise SystemExit("launch rule: no launch left (one relaunch at most, none after "
                             "a 402, a 429 or the cap)")  # fmt: skip
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("action", choices=("build", "ceiling", "dry", "seal", "paid", "report"))
    ap.add_argument("--data", type=Path, default=bb.DEFAULT_DATA, help="B6's MLQA and articles")
    ap.add_argument("--launcher", type=Path, help="the .cmd this run was started from")
    args = ap.parse_args()
    if args.action == "build":
        if PREREG.with_suffix(".sha256").exists():
            raise SystemExit("sealed: a new build would change the registered bench")
        manifest = build(args.data)
        OUT.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_bytes((json.dumps(manifest, indent=1) + "\n").encode())
        print(json.dumps({k: v for k, v in manifest.items() if k != "ids"}, indent=1))
        return 0
    if args.action == "seal":
        print(paid_once.seal(lot()))
        return 0
    if args.action == "paid":
        return paid(args.launcher)
    if args.action == "report":
        report = analysis(paid=True)
        (OUT / "analysis.json").write_bytes((json.dumps(report, indent=1) + "\n").encode())
        print(json.dumps(report, indent=1))
        return 0
    rows = load_rows()
    report = ceiling(rows) if args.action == "ceiling" else dry(rows)
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
