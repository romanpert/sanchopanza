"""Everything the tool-window bench needs that costs nothing: trajectories, sizes, a probe.

    python benchmarks/agentdojo/window_data.py --build   # trajectories + group sizes, free
    python benchmarks/agentdojo/window_data.py --probe   # the channel probe, free

Run with the AgentDojo interpreter. `--build` and `--probe` call `messages.count_tokens`,
which is not billed, and need ANTHROPIC_API_KEY. Nothing here generates a token.

TRAJECTORIES, NOT REQUESTS. `tools_bench.py` measured a selection against the request alone.
A window is measured against what the agent does after it: each AgentDojo user task carries a
`ground_truth()` of tool calls, and running them through the suite's own `FunctionsRuntime`
on its default environment gives the calls **in order, with the text each one returned**.
So "the group was needed at step 3, after the agent had read the email at step 2" is a fact
of the data, not a judgment. No annotator.

SIZES ARE TOKENS, NOT CHARACTERS. Each group's schemas are counted with the API's own
tokenizer (claude-sonnet-5): the count with the group's tools minus the count without.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "src"))

from tools_bench import GROUPS, VERSION, group_of  # noqa: E402

OUT = HERE.parents[1] / "docs" / "results" / "2026-09-25-window"
COUNT_MODEL = "claude-sonnet-5"

# Pre-registered on 2026-09-25, from what the tools do, BEFORE any window decision was run.
# Each line is a claim that can fail: a declared prerequisite that the trajectories never use
# costs its schema in every session that loads the group, and the report counts that.
#
# - clock: one tool, a few hundred tokens, and "next", "tomorrow", "this week" all need it.
#   Too small and too universal to put to a vote; pinned by code (queue item 2).
# - messaging requires channels: posting "to the channel that starts with External" or "to
#   every channel Alice is in" needs the channels listed first. The request never says so.
ALWAYS: tuple[str, ...] = ("clock",)
REQUIRES: dict[str, tuple[str, ...]] = {"messaging": ("channels",)}


def catalog(prereq: bool) -> list[dict[str, Any]]:
    out = []
    for name, (about, _members) in GROUPS.items():
        entry: dict[str, Any] = {"name": name, "about": about}
        if prereq and name in REQUIRES:
            entry["requires"] = list(REQUIRES[name])
        out.append(entry)
    return out


def _client() -> Any:
    import anthropic

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit("ANTHROPIC_API_KEY is needed for count_tokens (free, not billed)")
    return anthropic.Anthropic(api_key=key)


def _anthropic_tool(tool: Any) -> dict[str, Any]:
    return {
        "name": str(tool.name),
        "description": str(tool.description or ""),
        "input_schema": tool.parameters.model_json_schema(),
    }


def group_tokens(suites: Any) -> dict[str, int]:
    client = _client()
    by_group: dict[str, list[dict[str, Any]]] = {}
    seen: set[str] = set()
    for suite in suites.values():
        for tool in suite.tools:
            name = str(tool.name)
            g = group_of(name)
            if not g or name in seen:
                continue
            seen.add(name)
            by_group.setdefault(g, []).append(_anthropic_tool(tool))
    messages = [{"role": "user", "content": "hello"}]
    base = client.messages.count_tokens(model=COUNT_MODEL, messages=messages).input_tokens
    sizes = {}
    for g, defs in sorted(by_group.items()):
        n = client.messages.count_tokens(model=COUNT_MODEL, messages=messages, tools=defs)
        sizes[g] = n.input_tokens - base
    return sizes


def trajectories() -> list[dict[str, Any]]:
    from agentdojo.agent_pipeline.ground_truth_pipeline import GroundTruthPipeline
    from agentdojo.functions_runtime import FunctionsRuntime
    from agentdojo.task_suite.load_suites import get_suites
    from agentdojo.types import get_text_content_as_str

    suites = get_suites(VERSION)
    out = []
    for suite_name, suite in suites.items():
        for task_index, (task_id, task) in enumerate(suite.user_tasks.items()):
            runtime = FunctionsRuntime(suite.tools)
            env = suite.load_and_inject_default_environment({})
            try:
                _, _, _, messages, _ = GroundTruthPipeline(task).query(task.PROMPT, runtime, env)
            except Exception as error:  # a task whose ground truth will not run is skipped loudly
                print(f"  {suite_name}/{task_id}: {error}", file=sys.stderr)
                continue
            steps = []
            for message in messages:
                if message.get("role") != "tool":
                    continue
                call = message.get("tool_call")
                tool = str(getattr(call, "function", "") or "")
                group = group_of(tool)
                if not group:
                    continue
                text = get_text_content_as_str(message.get("content") or []) or ""
                steps.append({"tool": tool, "group": group, "output": text})
            steps = _with_the_read_it_skips(task.PROMPT, steps, env)
            if steps:
                out.append(
                    {
                        "id": f"tw-{suite_name}-{task_id}",
                        "suite": suite_name,
                        "task_index": task_index,
                        "purpose": task.PROMPT,
                        "steps": steps,
                    }
                )
    return out


def _with_the_read_it_skips(
    prompt: str, steps: list[dict[str, Any]], env: Any
) -> list[dict[str, Any]]:
    """Prepend the fetch of a page the request names but the ground truth never reads.

    Two slack tasks ("do all the tasks on my TODO list at www.company-todo-list.com/bob")
    ship a `ground_truth()` that goes straight to the actions on the list, as if it already
    knew what the page says. No agent can: the page has to be read first. Replayed as
    shipped, those trajectories make any window that widens on what was read fail by
    construction, since the read it would widen on never happens. The fetch is added with
    the environment's own page text, flagged `synthetic`, and only when the named URL exists
    in the environment and no step already returned its content.
    """
    import re

    web = getattr(getattr(env, "web", None), "web_content", None) or {}
    outputs = {s["output"] for s in steps}
    for url in re.findall(r"www\.[\w./-]+[\w/]", prompt):
        content = web.get(url)
        if content and content not in outputs:
            fetch = {"tool": "get_webpage", "group": "web", "output": content, "synthetic": True}
            return [fetch, *steps]
    return steps


def probe(
    models: tuple[str, ...] = ("claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5"),
) -> dict[str, Any]:
    """The four channel facts `sanchopanza.window` states, re-measured. Free."""
    import anthropic

    client = _client()
    desc = "Look up detailed records. " + " ".join(
        f"field{i} explains attribute {i}." for i in range(60)
    )

    def tool(name: str, deferred: bool = False) -> dict[str, Any]:
        props = {f"arg{i}": {"type": "string", "description": f"argument {i}"} for i in range(8)}
        t: dict[str, Any] = {
            "name": name,
            "description": desc,
            "input_schema": {"type": "object", "properties": props, "required": ["arg0"]},
        }
        if deferred:
            t["defer_loading"] = True
        return t

    hot = {"name": "clock", "description": "today", "input_schema": {"type": "object"}}
    user = [{"role": "user", "content": "Summarise my records."}]
    names = [f"records_{i}" for i in range(10)]
    deferred_tools = [hot] + [tool(n, True) for n in names]
    call = {
        "role": "assistant",
        "content": [{"type": "tool_use", "id": "t1", "name": "clock", "input": {}}],
    }

    def count(model: str, tools: list, messages: list, betas: tuple = ()) -> Any:
        try:
            api = client.beta.messages if betas else client.messages
            kwargs = {"betas": list(betas)} if betas else {}
            return api.count_tokens(
                model=model, tools=tools, messages=messages, **kwargs
            ).input_tokens
        except anthropic.APIStatusError as error:
            return f"400: {str(error.message)[:120]}"

    def result(content: list) -> list:
        return user + [
            call,
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "t1", "content": content}],
            },
        ]

    refs = [
        {"type": "tool_reference", "tool_name": names[0]},
        {"type": "tool_reference", "tool_name": names[1]},
    ]
    add = {
        "role": "system",
        "content": [
            {"type": "tool_addition", "tool": {"type": "tool_reference", "name": n}}
            for n in names[:2]
        ],
    }
    remove = {
        "role": "system",
        "content": [{"type": "tool_removal", "tool": {"type": "tool_reference", "name": names[1]}}],
    }
    beta = ("mid-conversation-tool-changes-2026-07-01",)
    history = user + [
        add,
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "next"},
    ]
    rows = {}
    for model in models:
        rows[model] = {
            "10 tools loaded": count(model, [hot] + [tool(n) for n in names], user),
            "10 tools deferred": count(model, deferred_tools, user),
            "result: text": count(model, deferred_tools, result([{"type": "text", "text": "x"}])),
            "result: 2 tool_reference only": count(model, deferred_tools, result(refs)),
            "result: text + tool_reference": count(
                model, deferred_tools, result([{"type": "text", "text": "x"}, *refs])
            ),
            "system tool_addition x2": count(model, deferred_tools, user + [add], beta),
            "addition x2 then more turns": count(model, deferred_tools, history, beta),
            "same, plus tool_removal x1": count(model, deferred_tools, history + [remove], beta),
        }
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--build", action="store_true")
    p.add_argument("--probe", action="store_true")
    p.add_argument(
        "--probe-models",
        action="store_true",
        help="probe every model `harness.messages_api` sends tool_addition to (probe-models.json)",
    )
    args = p.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.probe:
        rows = probe()
        (OUT / "probe.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
        print(json.dumps(rows, indent=1))
    if args.probe_models:
        from sanchopanza.harness.messages_api import ADDITION_MODELS

        rows = probe(tuple(sorted(ADDITION_MODELS)) + ("claude-sonnet-5", "claude-haiku-4-5"))
        (OUT / "probe-models.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
        print(json.dumps(rows, indent=1))
    if args.build:
        from agentdojo.task_suite.load_suites import get_suites

        trajs = trajectories()
        sizes = group_tokens(get_suites(VERSION))
        (OUT / "trajectories.json").write_text(
            json.dumps(trajs, indent=1, ensure_ascii=False), encoding="utf-8"
        )
        (OUT / "sizes.json").write_text(json.dumps(sizes, indent=1), encoding="utf-8")
        steps = sum(len(t["steps"]) for t in trajs)
        print(f"{len(trajs)} trajectories, {steps} tool calls; group tokens: {sizes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
