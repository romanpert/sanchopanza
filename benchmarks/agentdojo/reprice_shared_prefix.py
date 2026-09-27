"""Re-price the end-to-end runs as if the harness had shared the tools+system prefix. Free.

    python benchmarks/agentdojo/reprice_shared_prefix.py            # needs ANTHROPIC_API_KEY
                                                                    # for count_tokens (not billed)

`e2e_window.py` used top-level automatic caching only, whose breakpoint sits on the last
message. A cache read can only land where an earlier request wrote a breakpoint, so no task
ever read the `tools` + `system` prefix another task had written: each task paid it as a
write. Measured on 2026-09-25 (74-tool catalog, two different first messages, and again with
normal requests): without a breakpoint on `system` the second task wrote 12,296 tokens and
read 0; with one it wrote 86 and read 12,211.

A production harness with a fixed catalog puts that breakpoint (Claude Code does), so the
arms whose prefix does not depend on the request - `full`, `search` - were overcharged. This
re-prices every task after the first one on the same prefix: its prefix tokens move from the
write price to the read price. `sancho` sends the groups its window opened, so its prefix
depends on the request; only tasks whose window matches an earlier task's are re-priced.
The concurrent cold start (N parallel first requests all write) is ignored: a pre-warm
removes it. This is an ESTIMATE from recorded usage, not a run.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "src"))

import e2e_window as e  # noqa: E402

ROOT = HERE.parents[1]
# The re-pricing moves at most what a task actually wrote (bounded by its recorded
# `cache_write`), so a task that already read part of its prefix cannot save it twice.
RUNS = {
    "2026-09-25-e2e/runs-10.jsonl": None,
    "2026-09-25-e2e/runs-10-parallel.jsonl": None,
    "2026-09-25-e2e/runs-10-v3.jsonl": None,
    "2026-09-25-wide/runs-5.jsonl": "docs/results/2026-09-25-wide/catalog.json",
}
OUT = ROOT / "docs" / "results" / "2026-09-25-cache" / "reprice.json"


def _client() -> Any:
    import anthropic

    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def _count(client: Any, tools: list[dict[str, Any]], arm: str) -> int:
    system = e.BASE_SYSTEM + e.ARM_SYSTEM[arm]
    return client.messages.count_tokens(
        model="claude-sonnet-5",
        system=system,
        tools=tools,
        messages=[{"role": "user", "content": "x"}],
    ).input_tokens


def _arm_tools(arm: str, window: tuple[str, ...]) -> list[dict[str, Any]]:
    all_tools, by_group = e.tool_defs()
    if arm == "full":
        return all_tools
    if arm == "search":
        return [{"type": "tool_search_tool_bm25_20251119", "name": "tool_search_tool_bm25"}] + [
            {**t, "defer_loading": True} for t in all_tools
        ]
    from sanchopanza.harness.messages_api import LOAD_TOOL_DEFINITION

    loaded = set(window)
    out = [LOAD_TOOL_DEFINITION]
    for group, tools in by_group.items():
        if group == "other":
            continue
        out += [dict(t) if group in loaded else {**t, "defer_loading": True} for t in tools]
    return out


def reprice(path: str, wide: str | None, client: Any) -> dict[str, Any]:
    e.tool_defs.cache_clear()
    e.Run.wide = ROOT / wide if wide else None
    text = (ROOT / "docs" / "results" / path).read_text("utf-8")
    rows = [json.loads(x) for x in text.splitlines()]
    rows = [r for r in rows if "error" not in r]
    price = e.PRICES["claude-sonnet-5"]
    saving = price["write"] - price["read"]
    sizes: dict[tuple[str, tuple[str, ...]], int] = {}
    seen: set[tuple[str, tuple[str, ...]]] = set()
    out: dict[str, dict[str, float]] = {}
    for r in rows:
        # Sonnet 5 loads the window it opened; the recorded window is the final one, which on
        # this model differs from the opened one only when load_tools was called.
        key = (r["arm"], tuple(r["window"] or ()) if r["arm"] == "sancho" else ())
        if key not in sizes:
            sizes[key] = _count(client, _arm_tools(r["arm"], key[1]), r["arm"])
        shared = key in seen
        seen.add(key)
        as_run = r["usd_model"] + r.get("usd_jev", 0.0)
        # Bounded by what the task actually wrote: a task that already read part of its prefix
        # (the twin process of the wide run wrote identical requests) cannot save it twice.
        movable = min(sizes[key], r["tokens"]["cache_write"])
        repriced = as_run - (movable * saving if shared else 0.0)
        a = out.setdefault(r["arm"], {"tasks": 0, "as_run": 0.0, "shared_prefix": 0.0, "shared": 0})
        a["tasks"] += 1
        a["as_run"] = round(a["as_run"] + as_run, 4)
        a["shared_prefix"] = round(a["shared_prefix"] + repriced, 4)
        a["shared"] += int(shared)
    prefix = {f"{k[0]}:{len(k[1])} groups" if k[1] else k[0]: v for k, v in sizes.items()}
    return {"arms": out, "prefix_tokens_sample": dict(list(prefix.items())[:6])}


def main() -> int:
    client = _client()
    result = {path: reprice(path, wide, client) for path, wide in RUNS.items()}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=1), encoding="utf-8")
    for path, r in result.items():
        full = r["arms"].get("full", {})
        print(path)
        for arm, a in r["arms"].items():
            ratio = ""
            if full and arm != "full":
                ratio = (
                    f"  x full: as run {a['as_run'] / full['as_run']:.2f}"
                    f" -> shared {a['shared_prefix'] / full['shared_prefix']:.2f}"
                )
            print(
                f"  {arm:6} n={a['tasks']:2} as run {a['as_run']:.3f} -> shared prefix "
                f"{a['shared_prefix']:.3f} ({a['shared']} re-priced){ratio}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
