# Attaching Sancho to a harness

Every adapter translates one thing: a tool call into a `Verdict`, and a tool result into an
optional note. The translation lives in `sanchopanza.harness.generic.Guardian`; the files in
`sanchopanza.harness` are the per-harness wire formats.

```python
from sanchopanza.harness import Guardian, HarnessConfig, ToolCall

guardian = Guardian(squire, HarnessConfig(...))
verdict = await guardian.before_tool(ToolCall("Bash", {"command": "rm -rf /"}))
# Verdict(action="deny", reason="Command denied (recursive delete). ...")
note = await guardian.after_tool(ToolCall("Agent", {"prompt": "..."}), tool_result)
# "Thread review (decision model): answered 0.91, exhausted 0.12, unsourced 0.88. it states facts..."
```

`HarnessConfig` names what the harness calls things: which tools delegate (`Agent`, `Task`),
which key carries the subagent tier (`subagent_type`), which tools search (`WebSearch`),
which run a shell (`Bash`, `shell`, `run_command`), and the map from Sancho's three tiers to
the harness's subagent or model names.

## Claude Agent SDK

Status: **tested** (hook input/output shapes; the SDK is not imported by the tests).

```python
from claude_agent_sdk import ClaudeAgentOptions, HookMatcher
from sanchopanza.harness.claude_agent_sdk import pre_tool_use, post_tool_use, hook_matchers

options = ClaudeAgentOptions(hooks=hook_matchers(guardian))
# or by hand:
options = ClaudeAgentOptions(hooks={
    "PreToolUse": [HookMatcher(matcher="Agent|WebSearch|Bash", hooks=[pre_tool_use(guardian)])],
    "PostToolUse": [HookMatcher(matcher="Agent", hooks=[post_tool_use(guardian)])],
})
```

What the hooks return:

| Verdict | Hook output |
|---|---|
| allow | `{}` |
| deny | `{"hookSpecificOutput": {"permissionDecision": "deny", "permissionDecisionReason": ...}}` |
| rewrite | `{"hookSpecificOutput": {"permissionDecision": "allow", "updatedInput": {...}}}` |
| note | `{"hookSpecificOutput": {"additionalContext": "..."}}` |

The squire lives for the whole job, so the repeated-query memory and the budget hold across
calls. The MCP tools (`verify_citation`, `evaluate_plan`, ...) are added to the same squire
through `create_sdk_mcp_server` in your harness if you want them in-process.

## Claude Code (command hook)

Status: **run end to end** in Claude Code 2.1, installed with `sanchopanza install --write`: 24 headless sessions pre-registered, plus a registered confirmation of the content-scan fix (`docs/results/2026-09-28-claude-code-harness/`). Every model decision came from the `jev` provider; Claude was only the agent being guarded. Each hook call pays 1 to 2 s of Python start-up on Windows before any decision.

`sanchopanza hook` is a process per event. Configuration is by environment variables (see
`examples/claude_code/README.md`). Same output shapes as the SDK. The hook exits 0 and prints
nothing on any internal error: it can never block a tool by failing.

Because each event is a new process, the squire is new each time: no cross-call query
memory, no per-job budget. If that matters, run Sancho as an MCP server instead and let the
agent call the tools, or use the SDK.

## MCP (any client)

Status: **built on FastMCP, exercised through its parsers in tests; not run against a live
client in CI.**

```python
from sanchopanza.harness.mcp import build_server
build_server(squire).run()
```

Tools: `verify_citation`, `evaluate_plan`, `align_entities`, `classify_field`, `triage_text`.
These are the decisions the orchestrator asks for on purpose. Hooks cover the ones it does
not ask for. Clients: Claude Code (`claude mcp add`), Cursor (`.cursor/mcp.json`), Codex,
Copilot, Hermes Agent, or any MCP client.

## OpenAI Agents SDK, Codex-style guardrails

Status: **interface adapter; shape tested, not run against the SDK.**

```python
from sanchopanza.harness.openai_agents import tool_guardrail
check = tool_guardrail(guardian)
result = await check("shell", {"command": "..."})
# {"tripwire_triggered": bool, "output_info": {"action", "reason", "arguments"}}
```

Wrap it in the SDK's `@input_guardrail` and return `GuardrailFunctionOutput(result["output_info"],
result["tripwire_triggered"])`. Argument rewriting has no guardrail equivalent; call
`Guardian.before_tool` from a tool wrapper if the harness lets you replace arguments.

## LangChain, LangGraph and deepagents (middleware)

```python
from sanchopanza.harness.langchain import ToolSelectMiddleware

agent = create_agent(model, tools, middleware=[ToolSelectMiddleware(squire, always={"web_search"})])
```

`ToolSelectMiddleware` narrows `request.tools` to a per-conversation `ToolWindow` that only
grows. Tools are grouped by `group_of` (default: the tool's `metadata["server"]`, else the
prefix before the first `_`); on the conversation's first model call the squire asks one
question per group ("would work on the last human message need this group?") and the call
goes on with the groups that pass, plus `always`. Each new human turn can add groups, never
remove them, and the calls in between ask nothing. A group is left out only when its
probability is low (`Thresholds.tools`, 0.35): the costly error here is hiding a tool the
agent needed, not paying for one it did not use. The selection is never empty; with no human
message, a single group, unnamed tools or a silent decider the request passes untouched, and
a turn the decider could not answer adds every group nobody answered for.

The window never re-selects: choosing a different set on every call is the pattern
`benchmarks/cache/` measured at 4.15x the cost of deciding once. Because LangChain passes a
list rather than the platform's `tool_addition` channel, each widening here still rewrites
`tools` once; there are at most as many as there are groups, and `grow=False` keeps the
prefix byte-identical at the price of the misses. Pass `key_of` (the LangGraph `thread_id`)
to keep one window per conversation, each with its own meter, so one exhausted budget stays
in its own conversation. Without `key_of` nothing is kept between requests: each model call
opens a fresh window on its last human message, which is safe and costs one decision per
call. Never key by anything the user controls: two users who open with the same words must
not share a window.

Human-message text is treated as the user's and is not scanned for injection. An application
that puts documents or emails inside a human message should pass that text through
`ToolWindow.observe(..., trust="tool")` itself.

Tested in shape against a request-like object with `tools`, `messages` and `override(...)`,
which is what LangChain 1.x `ModelRequest` exposes; not yet against a live agent loop. The
window it wraps is measured (next section); the adapter is not. Requires
`pip install sanchopanza[langchain]` for the real `AgentMiddleware` base; without LangChain
the class still imports and runs for tests.

## Anthropic Messages API (a tool window)

Status: **every request shape checked with `messages.count_tokens`; measured end to end on
Sonnet 5; the proactive channel probed on Opus 5, not run end to end.**

```python
from sanchopanza import ToolWindow
from sanchopanza.harness.messages_api import WindowedTools, accepts_tool_addition

window = ToolWindow(squire, catalog, always={"clock"},
                    wait_on_deferred=accepts_tool_addition(model))
await window.open(user_request)
wt = WindowedTools(window, tools_by_group, model=model)
tools = wt.tools()                     # send unchanged on every request
messages += wt.opening()
...
change = await window.observe(result_text, trust="tool")   # scanned, then widened
messages += wt.after(change)           # a system message where tool_addition exists
```

`ToolWindow` (`src/sanchopanza/window.py`) opens narrow from the request and only grows: on a
new user turn, and after a tool result once that result has passed the injection scan. A
flagged or incompletely scanned result adds nothing and taints the window until the next
user turn. `WindowedTools` (`src/sanchopanza/harness/messages_api.py`) renders it in the
shapes the endpoint accepts (`docs/results/2026-09-25-window/README.md`, section 1):

| | Opus 5; Opus 4.8, Fable 5 and 5.1 (shape only, `count_tokens`) | Sonnet 5, Haiku 4.5 |
|---|---|---|
| The catalog | every tool declared with `defer_loading: true`, `tools` never changes | same |
| How a group is surfaced | a `system` message with one `tool_addition` per tool: proactive, no round trip | `tool_addition` is a 400; a `load_tools` tool, the only non-deferred one, answered with a `tool_result` holding only `tool_reference` blocks |
| `wait_on_deferred` | `True`: a request that defers its instructions opens narrow and widens once the deferred content is read | **`False`**: the whole catalog up front, as a one-shot selection would |

The `wait_on_deferred` rule is measured, not argued. On Sonnet 5 the model called
`load_tools` after the harness's "tools are now available" note in 2 of the 16-18 tasks
that got one, and `banking/user_task_12` failed in both runs under a window that waited and
succeeds with the rule (`docs/results/2026-09-25-e2e/README.md`, section 4). In that 40-task run the
rule opened the catalog for one request in 40.

**Do not write the `load_tools` call for the model.** The API accepts a harness-written load
answered with references, but after the model has read untrusted text Sonnet 5 reads the new
payment tools as the text escalating itself and refuses: 0 of 16 paid against 5 of 8 with
everything loaded, and 1 of 8 with the load moved before the read. Only a load in a turn of
its own before the model's first move worked (8 of 8), which is the same as opening the group
blind. On Opus 5 a
`tool_addition` after the read held 7 of 8 against 8 of 8. One toy task, variants added as
results came in, not pre-registered: a mechanism probe, not rates
(`docs/results/2026-09-25-push/README.md`).

**Never remove.** `tool_removal` reclaims no tokens: +26 measured, the removal block itself.
A removed tool's schema stays in the history where it was added, so the window is
append-only. A request whose every tool is deferred is a 400 even with a `tool_addition`, so
`load_tools` is always present and never deferred.

`load_tools` is a tool search answered by the selection question on the *user's* purpose,
with the model's `need` only as a clue, and it is refused after a blocked tool result: a
model that has read an injection writes its need in the attacker's words.

End to end (Sonnet 5, 40 AgentDojo tasks, 74 tools; `docs/results/2026-09-25-e2e/`), pooled
over runs the window completed 100/120 tasks against 70/80 loading every tool and 31/40 for
the platform's own tool search: no detectable difference at this n, and the all-tools arm
moved by two tasks between runs with nothing changed. With the scan and the observe question
running concurrently the window took 0.91x the time of loading everything. Cost, estimated
from recorded usage with the `tools` + `system` prefix shared between tasks as a production
harness shares it: the window 0.77-0.88x of loading everything, the platform's search 1.48x
(`docs/results/2026-09-25-cache/`).

On a real MCP catalog of 398 tools the order reverses: the platform's search cost an
estimated 0.34x of loading everything against the window's 0.54x, at the same success,
because the groups were whole servers and the window opened the 121-tool Google Workspace
server in 11 of 17 tasks (`docs/results/2026-09-25-wide/`). Use this adapter where the
platform offers no tool search or the catalog is small, and size groups as tasks use them,
not as servers ship them.

## Cursor, Copilot, Hermes Agent and others

Three routes, in order of effort:

1. **MCP server** (above): works wherever MCP works, no code in the harness.
2. **Command hook**: if the harness runs hooks as processes with JSON in and out, point it at
   `sanchopanza hook` and map field names. Claude Code's protocol is the default; a different one
   is a ten-line wrapper around `sanchopanza.harness.claude_code.handle`.
3. **Middleware**: call `Guardian.before_tool` / `after_tool` from the harness's own tool
   middleware (a custom loop; for LangChain see the section above). The `Verdict` is three fields.

Contributions of tested adapters are welcome; put them in `src/sanchopanza/harness/<name>.py` with a
docstring that says what is tested and what is not.
