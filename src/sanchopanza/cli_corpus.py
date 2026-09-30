"""`sanchopanza label` and `sanchopanza browse`: the corpus and page commands.

    sanchopanza label items.jsonl --rubric rubric.json --out labelled.csv --max-usd 0.50
    sanchopanza browse snapshot.yaml --goal "add the blue widget to the basket" --keep 15

Both use the provider from the environment (`SANCHOPANZA_PROVIDER`, or Jev when
`TYPESAFE_API_KEY` is set). With none, `label` refuses (a label nobody judged is not a label)
and `browse` ranks by BM25, free.
"""

from __future__ import annotations

# Imported by `cli.main` on every run, hooks included, which exist to start light: nothing heavy
# at module level (tests/test_hook_startup.py). asyncio, json and the modules come inside.
import argparse
import sys
from typing import Any


def register(sub: Any) -> None:
    label = sub.add_parser("label", help="label a corpus with a closed rubric (typed columns)")
    label.add_argument("items", help=".jsonl (key/id, text, context), .csv or .txt")
    label.add_argument("--rubric", required=True, help='JSON {"field", "options": {label: desc}}')
    label.add_argument("--out", required=True, help=".csv or .jsonl")
    label.add_argument("--max-usd", type=float, default=0.50, help="spend ceiling (default 0.50)")
    label.add_argument("--cache", default=".sanchopanza/label-cache.jsonl")
    label.add_argument("--max-age-days", type=float, default=30.0)
    label.add_argument("--concurrency", type=int, default=16)
    label.set_defaults(func=_label)

    browse = sub.add_parser("browse", help="rank a page's elements for the next action")
    browse.add_argument("page", help="a Playwright MCP snapshot (YAML) or an HTML file")
    browse.add_argument("--goal", required=True)
    browse.add_argument("--done", action="append", default=[], help="an action already taken")
    browse.add_argument("--keep", type=int, default=15)
    browse.set_defaults(func=_browse)


def _squire(max_usd: float | None = None) -> Any:
    """The environment's squire; `max_usd` becomes its ceiling (`SANCHOPANZA_T_MAX_USD`)."""
    import os

    from .harness.claude_code import squire_from_env

    env = dict(os.environ)
    if max_usd is not None:
        env["SANCHOPANZA_T_MAX_USD"] = str(max_usd)
    return squire_from_env(env)


def _label(args: argparse.Namespace) -> int:
    import asyncio
    import json

    from .label import LabelCache, Rubric, label, read_items, summary, write_rows

    squire = _squire(args.max_usd)
    if squire.provider == "null":
        sys.stderr.write("no provider: set TYPESAFE_API_KEY or SANCHOPANZA_PROVIDER\n")
        return 2
    rubric = Rubric.load(args.rubric)
    items = read_items(args.items)
    cache = LabelCache(args.cache, max_age_days=args.max_age_days) if args.cache else None
    rows = asyncio.run(
        label(items, rubric, squire=squire, cache=cache, concurrency=args.concurrency)
    )
    write_rows(args.out, rows)
    report = {**summary(rows), "spent_usd": round(squire.meter.cost_usd, 6), "out": args.out}
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


def page_elements(text: str) -> list[Any]:
    """Elements of a page given as a snapshot (YAML with refs) or as HTML."""
    from .browse import elements_from_html, elements_from_snapshot, snapshot_block

    span = snapshot_block(text)
    if span is not None:
        return elements_from_snapshot(text[span[0] : span[1]])
    if "[ref=" in text:
        return elements_from_snapshot(text)
    return elements_from_html(text)


def _browse(args: argparse.Namespace) -> int:
    import asyncio
    from pathlib import Path

    from .browse import rank, render

    text = Path(args.page).read_text(encoding="utf-8", errors="replace")
    elements = page_elements(text)
    squire = _squire()
    judge = None if squire.provider == "null" else squire
    ranked = asyncio.run(rank(args.goal, elements, squire=judge, done=args.done, keep=args.keep))
    print(render(ranked, total=len(elements)))
    return 0
