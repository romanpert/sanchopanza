"""The shipped hook (touch and first-request recall) replayed through `memory_hook.recall` and
`memory_hook.touch`. The prompt is the session's first prompt **whole**, read from the
transcript, as the hook receives it (items keep 1,000 characters; review of v5, M1). Decider
answers come from the cache; a missing one is asked only with --cap (USD, a hard stop in code),
else nothing enters for that request and it is counted.

    python benchmarks/memory_real/replay_v5.py --items CACHE/items-v4b.jsonl --tag dev [--v41]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from replay_v4b import touch_replay  # noqa: E402
from score import ANSWERS, CACHE, OUT, _answers, _key, metrics, squire_with_key  # noqa: E402
from variants_v4b import load  # noqa: E402

from sanchopanza.context import episodes as ep  # noqa: E402
from sanchopanza.context import guard  # noqa: E402
from sanchopanza.context.transcript import message_text  # noqa: E402
from sanchopanza.harness import memory_hook as mh  # noqa: E402

MISSES: list[str] = []
CALLS: list[str] = []  # the decider calls the hook would make
ASKED: list[float] = []  # USD spent by this process
_REAL_KEEP = mh.keep_by_decider


def first_prompt(session: str, request: str) -> str:
    """The session's first prompt as UserPromptSubmit carries it: the raw text, uncut (items
    and `guard.requests_of` cut it), when that is longer than the item's request; else the
    item's request (a slash command's markup holds its name, which the raw text drops)."""
    entries = ep.entries_of(CACHE / "transcripts" / f"{session}.jsonl")
    groups = ep.split_requests(entries).groups
    if not groups:
        return request
    raw = guard._MARKUP.sub("", message_text(groups[0][0])).strip()
    return raw if len(raw) > len(request) else request


def cached_keep(cached: dict[str, dict[str, float | None]], cap: float) -> Any:
    squire: list[Any] = []

    async def keep(_: Any, prompt: str, found: Sequence[ep.Episode]) -> Any:
        CALLS.append(prompt[:40])
        key = _key(prompt, [e.key for e in found])
        if key not in cached:
            if cap <= 0:  # never called: judged by nobody, so nothing enters (declared)
                MISSES.append(prompt[:40])
                return [], {e.key: None for e in found}
            squire[:] = squire or [squire_with_key(cap)]
            if squire[0].meter.cost_usd >= cap:
                raise SystemExit(f"cap {cap} USD reached")
            _, p = await _REAL_KEEP(squire[0], prompt, found)
            cached[key] = p
            with ANSWERS.open("a", encoding="utf-8", newline="\n") as log:
                log.write(json.dumps({"key": key, "probabilities": p}) + "\n")
            ASKED[:] = [squire[0].meter.cost_usd]
        p = cached[key]
        cut = mh._float("MEMORY_KEEP_AT", mh.KEEP_AT)
        kept = sorted((e for e in found if (p.get(e.key) or 0) >= cut),
                      key=lambda e: -(p.get(e.key) or 0))  # fmt: skip
        return kept, p

    return keep


def shown_in(text: str, pool: Sequence[ep.Episode]) -> list[str]:
    """The records a rendered text shows, by their whole title (review of v5, M2)."""
    return [e.key for e in pool if f"request {e.index} of session {e.session[:8]} (" in text]


def prompt_replay(
    items: list[dict[str, Any]], root: Path, cap: float = 0.0
) -> dict[int, list[str]]:
    os.environ["SANCHOPANZA_MEMORY_STORE"] = str(root / "store")
    os.environ["SANCHOPANZA_MEMORY_SELECT"] = "decider"
    os.environ["SANCHOPANZA_MEMORY_PROMPT"] = "first"
    mh.keep_by_decider = cached_keep(_answers(), cap)
    shown: dict[int, list[str]] = {}
    for n, item in enumerate(items):
        shown[n] = []
        if not item["first"]:
            continue
        project = root / "projects" / f"g{item['group']}-{item['session'][:8]}"
        store = mh.store_for({"transcript_path": str(project / "t.jsonl")})
        ep.save(store, item["pool"], keep_days=10_000)
        event = {"hook_event_name": "UserPromptSubmit", "session_id": item["session"],
                 "transcript_path": str(project / "absent.jsonl"), "cwd": "",
                 "prompt": first_prompt(item["session"], item["request"])}  # fmt: skip
        out = asyncio.run(mh.recall(event, squire=object()))  # type: ignore[arg-type]
        shown[n] = shown_in(out["hookSpecificOutput"]["additionalContext"] if out else "",
                            item["pool"])  # fmt: skip
    return shown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--items", default=str(CACHE / "items-v4b.jsonl"))
    parser.add_argument("--tag", default="dev")
    parser.add_argument("--v41", action="store_true", help="the gate off: v4.1 as shipped")
    parser.add_argument("--cap", type=float, default=0.0, help="USD to ask missing answers")
    args = parser.parse_args(argv)
    os.environ["SANCHOPANZA_MEMORY_PROMPT_NAMED"] = "off" if args.v41 else "on"
    items = load(Path(args.items))
    with tempfile.TemporaryDirectory() as tmp:
        touch, _ = touch_replay(items, Path(tmp) / "t")
        prompt = prompt_replay(items, Path(tmp) / "p", args.cap)
    both = {n: list(dict.fromkeys([*touch[n], *prompt[n]])) for n in touch}
    name = "v4.1" if args.v41 else "v5"
    m = {**metrics(items, both), "prompt_records": sum(len(v) for v in prompt.values()),
         "decider_calls": len(CALLS), "no_cached_answer": len(MISSES)}  # fmt: skip
    print(name, f"+{m['prompt_records']} calls {len(CALLS)} misses {len(MISSES)}"
          f" spent {ASKED[0] if ASKED else 0:.4f}", " | ".join(
        f"{k}: R {m[k]['recall']} P {m[k]['precision']} N {m[k]['noise']}"
        for k in ("all/any", "all/lineage", "first/any")))
    target = OUT / f"replay-v5-{args.tag}.json"
    old = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    target.write_text(json.dumps({**old, name: m}, indent=1), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
