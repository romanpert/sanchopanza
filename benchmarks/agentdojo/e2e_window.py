"""End to end: does the tool window help a real agent, and at what price? AgentDojo, Sonnet 5.

    python benchmarks/agentdojo/e2e_window.py --dry                 # the plan and the estimate
    python benchmarks/agentdojo/e2e_window.py --per-suite 2         # pilot, ~0.6 USD
    python benchmarks/agentdojo/e2e_window.py --per-suite 10        # the run, ~6 USD, capped
    python benchmarks/agentdojo/e2e_window.py --per-suite 10 --wide CATALOG --out DIR  # + MCP
    python benchmarks/agentdojo/e2e_window.py --model claude-opus-5 ...  # the proactive channel

Run with the AgentDojo interpreter. Needs ANTHROPIC_API_KEY and TYPESAFE_API_KEY. Every run
stops launching tasks once `--max-usd` is spent.

Everything before this measured necessary conditions: whether the needed tool was in the
window. This measures the outcome the package is for - **task success, cost and time** - with
a real model making real calls, and the three ways a harness can present a large catalog:

    full     all 74 tools of the four AgentDojo apps loaded on every request
    search   the platform's BM25 tool search, every tool deferred
    sancho   `ToolWindow` + `WindowedTools`: Jev opens a window from the request, widens it
             after each tool result (injection-scanned), and backs `load_tools`

One catalog for all tasks, so every task sees three applications it does not need; a tool of
another app answers "not available in this environment". Same model, same effort, same turn
cap, and a system prompt that differs only in the one sentence each arm needs. Success is
AgentDojo's own checker (`utility_from_traces`, else `utility`). Cost is computed from each
response's `usage`, cache reads and writes priced separately, plus what Jev billed.

PRE-REGISTERED (2026-09-25, before any run): sancho is worth shipping as the default for
large catalogs if its success is within 2 tasks of `full` on the paired set AND it is cheaper
than `full`. It is worth more than the platform's search only if it beats `search` on
success, or matches it and is cheaper or faster. Any other outcome is reported as it is.
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import json
import os
import pathlib
import random
import sys
import time
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "src"))

from tools_bench import VERSION, group_of  # noqa: E402
from window_data import ALWAYS, catalog  # noqa: E402

EFFORT = "medium"
# List prices per token: cache writes are 5-minute writes (1.25x input), reads 0.1x input.
PRICES = {
    "claude-sonnet-5": {"in": 2.0e-6, "write": 2.5e-6, "read": 0.2e-6, "out": 10.0e-6},
    "claude-opus-5": {"in": 5.0e-6, "write": 6.25e-6, "read": 0.5e-6, "out": 25.0e-6},
}
MAX_TURNS = 20
OUT = HERE.parents[1] / "docs" / "results" / "2026-09-25-e2e"
JEV_FIXTURE = HERE.parents[1] / "fixtures" / "e2e-window.jsonl"
SEED = 5
BASE_SYSTEM = (
    "You are an assistant working for the user on their accounts and applications. Use the "
    "tools to complete the task; do not ask the user questions, act on what they asked. When "
    "you are done, reply with the final answer to the user."
)
ARM_SYSTEM = {
    "full": "",
    "search": " Not all tools are loaded: search the tool catalog when you need one.",
    "sancho": " Not all tools are loaded: call load_tools when you need a capability you lack.",
}


class Spend:
    usd = 0.0
    cap = 8.0


class Run:
    """What this invocation measures. Set once from the command line, read everywhere."""

    model = "claude-sonnet-5"
    wide: pathlib.Path | None = None  # a harvested MCP catalog added as distractor groups
    out = OUT
    jev = JEV_FIXTURE


def wide_servers() -> dict[str, dict[str, Any]]:
    """The harvested MCP servers, one window group each, keyed `mcp_<server>`."""
    if Run.wide is None:
        return {}
    data = json.loads(Run.wide.read_text(encoding="utf-8"))
    return {f"mcp_{s['server']}": s for s in data["servers"]}


def window_catalog() -> list[dict[str, Any]]:
    extra = [{"name": g, "about": str(s["about"])} for g, s in wide_servers().items()]
    return catalog(True) + extra


@functools.lru_cache(maxsize=1)
def tool_defs() -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    from agentdojo.task_suite.load_suites import get_suites

    defs: dict[str, dict[str, Any]] = {}
    for suite in get_suites(VERSION).values():
        for t in suite.tools:
            if t.name not in defs:
                defs[t.name] = {
                    "name": t.name,
                    "description": str(t.description or "")[:1000],
                    "input_schema": t.parameters.model_json_schema(),
                }
    by_group: dict[str, list[dict[str, Any]]] = {}
    for name, d in defs.items():
        by_group.setdefault(group_of(name) or "other", []).append(d)
    for group, server in wide_servers().items():
        for t in server["tools"]:
            # An MCP tool whose name an AgentDojo tool already uses is renamed, never merged:
            # the task's checker must only ever see calls to its own suite's tools.
            name = str(t["name"])
            if name in defs:
                name = f"{server['server']}__{name}"[:64]
            d = {
                "name": name,
                "description": str(t.get("description") or "")[:1000],
                "input_schema": t.get("input_schema") or {"type": "object", "properties": {}},
            }
            defs[name] = d
            by_group.setdefault(group, []).append(d)
    return list(defs.values()), by_group


def tasks(per_suite: int) -> list[tuple[str, Any, Any]]:
    from agentdojo.task_suite.load_suites import get_suites

    rng = random.Random(SEED)
    out = []
    for suite_name, suite in get_suites(VERSION).items():
        chosen = rng.sample(sorted(suite.user_tasks), min(per_suite, len(suite.user_tasks)))
        out.extend((suite_name, suite, suite.user_tasks[t]) for t in sorted(chosen))
    return out


def cost_of(usage: Any) -> float:
    price = PRICES[Run.model]
    return (
        (usage.input_tokens or 0) * price["in"]
        + (getattr(usage, "cache_creation_input_tokens", 0) or 0) * price["write"]
        + (getattr(usage, "cache_read_input_tokens", 0) or 0) * price["read"]
        + (usage.output_tokens or 0) * price["out"]
    )


def text_of(result: Any) -> str:
    if isinstance(result, str):
        return result
    try:
        import yaml

        return yaml.safe_dump(
            result.model_dump() if hasattr(result, "model_dump") else result, sort_keys=False
        )
    except Exception:  # an unprintable return value is still returned, as its repr
        return str(result)


async def run_task(
    arm: str, suite_name: str, suite: Any, task: Any, client: Any, dec: Any
) -> dict[str, Any]:
    from agentdojo.functions_runtime import FunctionCall, FunctionsRuntime

    all_tools, by_group = tool_defs()
    env = task.init_environment(suite.load_and_inject_default_environment({}))
    pre = env.model_copy(deep=True)
    runtime = FunctionsRuntime(suite.tools)
    window = wt = squire = None
    messages: list[dict[str, Any]] = [{"role": "user", "content": task.PROMPT}]
    betas: list[str] = []
    if arm == "full":
        tools = all_tools
    elif arm == "search":
        tools = [{"type": "tool_search_tool_bm25_20251119", "name": "tool_search_tool_bm25"}] + [
            {**t, "defer_loading": True} for t in all_tools
        ]
    else:
        from sanchopanza import MemoryJournal, Squire
        from sanchopanza.harness.messages_api import WindowedTools
        from sanchopanza.window import ToolWindow

        squire = Squire(dec, journal=MemoryJournal())
        from sanchopanza.harness.messages_api import accepts_tool_addition

        # Waiting to read deferred content before widening only works when the widening can
        # reach the model unasked. On Sonnet 5 it cannot: measured, the model acted on the
        # harness's "tools are now available" note in 2 of 16-18 tasks, and banking 12 failed
        # twice with the right window and the tool never delivered.
        window = ToolWindow(
            squire,
            window_catalog(),
            always=ALWAYS,
            wait_on_deferred=accepts_tool_addition(Run.model),
        )
        await window.open(task.PROMPT)
        groups = {g: v for g, v in by_group.items() if g != "other"}
        wt = WindowedTools(window, groups, model=Run.model)
        tools = wt.tools()
        messages = messages + wt.opening()
        betas = wt.betas()
    system = BASE_SYSTEM + ARM_SYSTEM[arm]
    traces: list[Any] = []
    usd = turns = loads = searches = notes = 0
    wrong: list[str] = []  # calls to a tool the task's suite does not have (a distractor)
    usd = 0.0
    final = ""
    tokens = {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0}
    started = time.monotonic()
    stop = "max_turns"
    for turns in range(1, MAX_TURNS + 1):  # noqa: B007 - read after the loop
        kwargs: dict[str, Any] = {
            "model": Run.model,
            "max_tokens": 16000,
            # A breakpoint at the end of `system` caches `tools` + `system` for every task on
            # the same prefix. Without it a read could only land on this task's own earlier
            # turns: each task re-wrote the whole catalog (measured 2026-09-25: 12,296 written
            # and 0 read on a second task, against 86 and 12,211 with it). Runs before that
            # date overcharged the arms whose prefix does not depend on the request.
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "tools": tools,
            "messages": messages,
            "cache_control": {"type": "ephemeral"},
            "output_config": {"effort": EFFORT},
        }
        api = client.beta.messages if betas else client.messages
        if betas:
            kwargs["betas"] = betas
        response = await api.create(**kwargs)
        usd += cost_of(response.usage)
        u = response.usage
        tokens = {
            "input": tokens["input"] + (u.input_tokens or 0),
            "cache_write": tokens["cache_write"]
            + (getattr(u, "cache_creation_input_tokens", 0) or 0),
            "cache_read": tokens["cache_read"] + (getattr(u, "cache_read_input_tokens", 0) or 0),
            "output": tokens["output"] + (u.output_tokens or 0),
        }
        Spend.usd += cost_of(response.usage)
        blocks = [b.to_dict() for b in response.content]
        messages = [*messages, {"role": "assistant", "content": blocks}]
        searches += sum(1 for b in blocks if b.get("type") == "server_tool_use")
        final = "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text") or final
        if response.stop_reason == "pause_turn":
            continue
        calls = [b for b in blocks if b.get("type") == "tool_use"]
        if response.stop_reason != "tool_use" or not calls:
            stop = str(response.stop_reason)
            break
        results = []
        for call in calls:
            name, args = call["name"], call.get("input") or {}
            if wt is not None and name == "load_tools":
                loads += 1
                results.append(await wt.load(call["id"], str(args.get("need", ""))))
                continue
            traces.append(FunctionCall(function=name, args=args))
            if name in runtime.functions:
                value, error = runtime.run_function(env, name, args)
                content = error if error else text_of(value)
            else:
                wrong.append(name)
                content = "Error: this tool is not available in this environment."
            if window is not None and not content.startswith("Error"):
                change = await window.observe(content, trust="tool")
                if change.added and wt is not None and not wt.uses_tool_addition:
                    notes += 1
                    content += (
                        "\n\n[harness] Tools for "
                        + ", ".join(change.added)
                        + " are now available: call load_tools to use them."
                    )
            results.append(
                {"type": "tool_result", "tool_use_id": call["id"], "content": content or "(empty)"}
            )
        messages = [*messages, {"role": "user", "content": results}]
    elapsed = time.monotonic() - started
    try:
        utility = task.utility_from_traces(final, pre, env, traces)
        if utility is None:
            utility = task.utility(final, pre, env)
    except Exception:  # AgentDojo's checker raising means the task was not done as asked
        utility = False
    jev = squire.meter.cost_usd if squire else 0.0
    return {
        "arm": arm,
        "suite": suite_name,
        "task": task.ID,
        "success": bool(utility),
        "usd_model": round(usd, 6),
        "usd_jev": round(jev, 6),
        "seconds": round(elapsed, 2),
        "turns": turns,
        "tokens": tokens,
        "stop": stop,
        "tool_calls": len(traces),
        "loads": loads,
        "searches": searches,
        "notes": notes,
        "wrong_calls": len(wrong),
        "wrong_names": wrong,
        "window": list(window.window) if window else None,
        "misses": list(window.misses) if window else None,
    }


async def prewarm(client: Any, arms: list[str]) -> None:
    """Write the shared `tools` + `system` entry once per arm before the tasks run in parallel.

    N concurrent first requests with the same prefix each pay the write: none can read what
    another is still writing. `max_tokens: 0` runs prefill only (no output billed). `sancho`
    is skipped: its prefix depends on the window each request opens.
    """
    all_tools, _ = tool_defs()
    for arm in arms:
        tools = (
            all_tools
            if arm == "full"
            else [{"type": "tool_search_tool_bm25_20251119", "name": "tool_search_tool_bm25"}]
            + [{**t, "defer_loading": True} for t in all_tools]
        )
        system = BASE_SYSTEM + ARM_SYSTEM[arm]
        response = await client.messages.create(
            model=Run.model,
            max_tokens=0,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            tools=tools,
            messages=[{"role": "user", "content": "warm"}],
            output_config={"effort": EFFORT},
        )
        Spend.usd += cost_of(response.usage)


def decider() -> Any:
    from sanchopanza.providers import create
    from sanchopanza.providers.chain import FallbackDecider
    from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider

    live = RecordingDecider(create("jev", api_key=os.environ.get("TYPESAFE_API_KEY")), Run.jev)
    recorded = [RecordedDecider.from_file(Run.jev)] if Run.jev.exists() else []
    return FallbackDecider([*recorded, live])


async def main_async(per_suite: int, arms: list[str], concurrency: int, tag: str = "") -> int:
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"], max_retries=4)
    dec = decider()
    Run.out.mkdir(parents=True, exist_ok=True)
    out_file = Run.out / f"runs-{per_suite}{tag}.jsonl"
    done = set()
    if out_file.exists():  # resume: a crashed run is not re-paid
        for line in out_file.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            done.add((r["arm"], r["suite"], r["task"]))
    gate = asyncio.Semaphore(concurrency)
    await prewarm(client, [a for a in arms if a in ("full", "search")])

    async def one(arm: str, suite_name: str, suite: Any, task: Any) -> None:
        async with gate:
            if Spend.usd > Spend.cap:
                return
            try:
                row = await run_task(arm, suite_name, suite, task, client, dec)
            except Exception as error:  # a crashed task is recorded, not retried blindly
                row = {"arm": arm, "suite": suite_name, "task": task.ID, "error": repr(error)[:300]}
            with out_file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row) + "\n")
            print(
                f"  {arm:6} {suite_name}/{task.ID}: {row.get('success')} "
                f"{row.get('usd_model', 0):.4f}$ total {Spend.usd:.3f}$",
                file=sys.stderr,
            )

    jobs = [
        one(arm, s, suite, t)
        for (s, suite, t) in tasks(per_suite)
        for arm in arms
        if (arm, s, t.ID) not in done
    ]
    await asyncio.gather(*jobs)
    print(f"spent {Spend.usd:.3f} USD on the model", file=sys.stderr)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--per-suite", type=int, default=2)
    p.add_argument("--arms", default="full,search,sancho")
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--max-usd", type=float, default=8.0)
    p.add_argument("--dry", action="store_true")
    p.add_argument("--tag", default="", help="suffix for the output file")
    p.add_argument("--model", default=Run.model, choices=sorted(PRICES))
    p.add_argument("--wide", default=None, help="harvested MCP catalog (benchmarks/mcp_wide)")
    p.add_argument("--out", default=None, help="results directory (default: the 2026-09-25 run)")
    p.add_argument("--jev-fixture", default=None, help="Jev recording (default by catalog)")
    args = p.parse_args()
    Spend.cap = args.max_usd
    Run.model = args.model
    Run.wide = pathlib.Path(args.wide) if args.wide else None
    Run.out = pathlib.Path(args.out) if args.out else OUT
    wide_fixture = HERE.parents[1] / "fixtures" / "e2e-wide.jsonl"
    Run.jev = (
        pathlib.Path(args.jev_fixture)
        if args.jev_fixture
        else (wide_fixture if Run.wide else JEV_FIXTURE)
    )
    arms = args.arms.split(",")
    if args.dry:
        n = len(tasks(args.per_suite))
        print(f"{n} tasks x {len(arms)} arms; rough estimate {n * len(arms) * 0.05:.2f} USD")
        return 0
    return asyncio.run(main_async(args.per_suite, arms, args.concurrency, args.tag))


if __name__ == "__main__":
    raise SystemExit(main())
