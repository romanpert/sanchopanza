"""Amendment 3: v5 (the name gate at a session's first prompt) against v4.1 on selection-3.json.
Run once.

    python benchmarks/memory_real/confirm_v5.py --cap 0.5

Items by build_v4b.items_for. Both arms replayed through the hook's own code
(`memory_hook.touch` and `memory_hook.recall`, each first prompt whole from its transcript).
The v4.1 arm runs first and asks the decider for every first request with candidates, capped
in USD in code; the v5 arm reads the same answers from the cache only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build  # noqa: E402
import replay_v5  # noqa: E402
from build_v4b import items_for  # noqa: E402
from replay_v4b import touch_replay  # noqa: E402
from score import OUT, metrics  # noqa: E402
from select_v5 import SELECTION_3  # noqa: E402

from sanchopanza.context import episodes as ep  # noqa: E402

ITEMS = build.CACHE / "items-v4b-held3.jsonl"


def build_items() -> list[dict[str, Any]]:
    selection = json.loads(SELECTION_3.read_text(encoding="utf-8"))
    rows = []
    with ITEMS.open("w", encoding="utf-8", newline="\n") as handle:
        for g in selection["groups"]:
            for item in items_for(g["sessions"], g["group"], g["split"]):
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
                if item["pool"]:
                    rows.append({**item, "pool": [ep.Episode.from_dict(d) for d in item["pool"]]})
    return rows


def arm(items: list[dict[str, Any]], touch: dict[int, list[str]], gate: bool, root: Path,
        cap: float) -> tuple[dict[str, Any], dict[int, list[str]]]:  # fmt: skip
    os.environ["SANCHOPANZA_MEMORY_PROMPT_NAMED"] = "on" if gate else "off"
    replay_v5.MISSES.clear()
    replay_v5.CALLS.clear()
    prompt = replay_v5.prompt_replay(items, root, cap)
    both = {n: list(dict.fromkeys([*touch[n], *prompt[n]])) for n in touch}
    row = {**metrics(items, both), "decider_calls": len(replay_v5.CALLS),
           "no_cached_answer": len(replay_v5.MISSES),
           "prompt_records": sum(len(v) for v in prompt.values())}  # fmt: skip
    return row, both


def by_kind(items: list[dict[str, Any]], shown: dict[int, list[str]]) -> dict[str, Any]:
    kinds = {g["group"]: g["kind"]
             for g in json.loads(SELECTION_3.read_text(encoding="utf-8"))["groups"]}  # fmt: skip
    out = {}
    for kind in sorted(set(kinds.values())):
        keep = [n for n, i in enumerate(items) if kinds[i["group"]] == kind]
        sub = [items[n] for n in keep]
        out[kind] = metrics(sub, {j: shown[n] for j, n in enumerate(keep)})["all/any"]
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cap", type=float, default=0.5)
    args = parser.parse_args(argv)
    items = build_items()
    with tempfile.TemporaryDirectory() as tmp:
        touch, _ = touch_replay(items, Path(tmp) / "t")
        old, old_shown = arm(items, touch, False, Path(tmp) / "b", args.cap)  # asks, capped
        new, new_shown = arm(items, touch, True, Path(tmp) / "a", 0.0)  # the cache only
    rows = {"v5": {**new, "by_kind": by_kind(items, new_shown)},
            "v4.1": {**old, "by_kind": by_kind(items, old_shown)},
            "touch alone": metrics(items, touch)}  # fmt: skip
    a, b = rows["v5"], rows["v4.1"]
    fa, fb = a["first/any"], b["first/any"]
    first_better = ((fa["noise"] or 0) < (fb["noise"] or 0)
                    or (fa["precision"] or 0) > (fb["precision"] or 0))  # fmt: skip
    verdicts = {
        "1 first requests not worse, better in one": (fa["noise"] or 0) <= (fb["noise"] or 0)
        and (fa["precision"] or 0) >= (fb["precision"] or 0) and first_better,
        "2 recall within 0.005 of v4.1": a["all/any"]["recall"] >= b["all/any"]["recall"] - 0.005,
        "3 precision not below, noise not above v4.1":
            a["all/any"]["precision"] >= b["all/any"]["precision"]
            and a["all/any"]["noise"] <= b["all/any"]["noise"],
        "4 recall >= 0.80, precision >= 0.50, noise <= 0.10": a["all/any"]["recall"] >= 0.80
        and a["all/any"]["precision"] >= 0.50 and a["all/any"]["noise"] <= 0.10,
    }  # fmt: skip
    for name, m in rows.items():
        print(name.ljust(12), " | ".join(
            f"{k}: R {m[k]['recall']} P {m[k]['precision']} N {m[k]['noise']}"
            for k in ("all/any", "all/lineage", "first/any")),
            {k: m[k] for k in ("decider_calls", "no_cached_answer") if k in m})
    print(f"decider spent {replay_v5.ASKED[0] if replay_v5.ASKED else 0:.4f} USD")
    print(json.dumps(verdicts, indent=1))
    out = {"requests": len(items), "rows": rows, "verdicts": verdicts}
    (OUT / "confirm-v5.json").write_text(json.dumps(out, indent=1), encoding="utf-8",
                                         newline="\n")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
