# Attaching sanchopanza to a harness

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
which run a shell (`Bash`, `shell`, `run_command`), and the map from sanchopanza's three tiers to
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

Status: **run end to end** in Claude Code 2.1, installed with `sanchopanza install --write`. The broader run, pre-registered, held all 15 of its criteria ([claude-code-broad](results/2026-09-28-claude-code-broad/)): over 144 headless sessions (Haiku 4.5, 9 scenarios, 8 repetitions per arm, hooked and plain), the hook stopped the two destructive commands 16 of 16 times, where plain Claude Code ran them 15 of 16 times (once it stopped to ask first), flagged planted instructions in a `Read` file or `curl` output 16 of 16 times, and raised 0 false alarms in 93 benign hooked events [0 %, 4.0 %]. The agent refused the planted text in every session either way, so the scan changed no reply. Through the hook process on labelled public sets, it flagged 0 of 250 unsafe ATBench-Codex trajectories, because their risk is in MCP calls the default hook does not judge (`--guard-mcp`, below). The first run, 24 sessions plus a registered confirmation of the content-scan fix, showed the wiring ([claude-code-harness](results/2026-09-28-claude-code-harness/)). Every model decision came from the `jev` provider; Claude was only the agent being guarded. Each hook call is a Python process: the e2e run measured 1.0-1.9 s of start-up on the maintainer's Windows laptop; after the imports were made lazy, an interleaved measurement on the same laptop gave a median 0.17 s for an event that needs no decision and 0.25 s up to the decision for one that does, against 0.31-0.34 s before ([hook-startup](results/2026-09-28-hook-startup/)).

`sanchopanza hook` is a process per event. Configuration is by environment variables (see
`examples/claude_code/README.md`). Same output shapes as the SDK. The hook exits 0 and prints
nothing on any internal error: it can never block a tool by failing.

Because each event is a new process, the squire is new each time: no cross-call query
memory, no per-job budget. If that matters, run sanchopanza as an MCP server instead and let the
agent call the tools, or use the SDK.

**What `install` wires by default:** the guard on shell commands, delegations and searches; the
compaction guard (next section); and memory, five hooks that record each finished request and
give a later request the records and standing rules that bear on it (`--no-memory` leaves them
out; [how memory works](memory.md)). Opt-in, among others (`sanchopanza install --help`):

- `--scan-content` flags instructions planted in what the agent reads, and `--check-done`
  checks "done" before the agent stops; the broader run above installed both.
- `--guard-mcp` judges MCP tool calls before they run: the `actions` point reads the session so
  far and the pending call, one paid decision per call. **Not confirmed**: replayed over
  ATBench-Codex with jev-1.13.0 it caught 185 of 250 unsafe trajectories (74.0 %), under its
  sealed 75.2 % recall floor, and flagged 82 of 250 safe ones (32.8 %)
  ([A3](results/2026-10-16-a3-mcp/README.md)).
- `--guard-mcp-post` asks the same question after an MCP call ran, with its result last. A flag
  blocks with a reason for Claude and a notice for the person; it cannot undo the call.
  `--guard-mcp-withhold` implies it and also replaces a flagged result before Claude reads it.
  Off by default, with no confirmed measurement.

### The compaction guard (on by default, `--no-guard` leaves it out)

Three more command hooks, all `sanchopanza guard-hook`: `PreCompact` (matcher `manual|auto`),
`SessionStart` (matcher `compact`) and `PostToolUse` (matcher `Bash`). Read from the 2.1.282
binary: a `PreCompact` hook's stdout is appended to the summary prompt; `SessionStart` hooks with
source `compact` run **before** `PostCompact`, and the new summary is written to the transcript
after both, so the guard can add context right after the summary but cannot read it (a
`PostCompact` hook can only show a message). `SANCHOPANZA_GUARD_CHOOSER` picks what is kept:
`pointers` (default, free: the requests verbatim first, the files changed, and pointers to the
tool output since the previous compaction; every output that cannot be had again is written
whole, masked, to `.sanchopanza/archive/<session>/` for the agent to Read; `context.pointers`),
`struct` (`install --guard-full`, free: whole tool results, the latest on each edited file
first, then by recency, pointers for re-readable ones left out; `context.structural`), `rule`
(free: value lines of one-shot output) or `keep` (the cascade, `context.keep`: built at the
`SessionStart`, about five decider calls per compaction, the rule after
`SANCHOPANZA_GUARD_DECIDER_SECONDS`).
The same binaries keep a hook's `additionalContext` inline only up to 10,000 characters (past
that the model sees a 2,000-character preview and a file path), per hook command: the contexts
of an event's hooks are joined with a newline, in the order the hooks finish, with no limit on
the whole (read in 2.1.287). The pointer block fits one hook, so by default `install` writes one
command per event. With `--guard-full` it writes `PreCompact` as `guard-hook --parts K` and K
`SessionStart` commands, `guard-hook --part i --parts K` (K = 6 at the defaults,
`--guard-parts`), and `struct` splits its block into parts under
`SANCHOPANZA_GUARD_INLINE_CHARS` (9,500), each naming itself "part i of N" (`context.parts`).
Without `--part` the hook keeps one block under the cap.
Measured end to end in
[the compaction-guard run](results/2026-09-29-context-guard/): 5 of 7 (`rule`) and 6 of 7
(`keep`) tasks finished, against 2 of 7 with the native summary alone; `struct` is measured
offline only ([guard-struct](results/2026-10-05-guard-struct/)), and `pointers` has no published
end-to-end result.

## MCP (any client)

Status: **built on FastMCP, exercised through its parsers in tests; not run against a live
client in CI.**

```python
from sanchopanza.harness.mcp import build_server
build_server(squire).run()
```

`build_server(squire)` serves the five decision tools: `verify_citation`, `evaluate_plan`,
`align_entities`, `classify_field`, `triage_text`. These are the decisions the orchestrator asks
for on purpose. Hooks cover the ones it does not ask for.

`python -m sanchopanza.harness.mcp --tools <sets>` serves one stdio server with the tool sets
you name (default `archive,find`):

| Set | Tools | Needs a provider |
|---|---|---|
| `decisions` | the five above | yes (`SANCHOPANZA_PROVIDER` or `TYPESAFE_API_KEY`) |
| `archive` | `search_archive`: BM25 over output archived out of context | no |
| `find` | `find_in_repo`: fragments of the repository for a request, a BM25 shortlist judged by the decider when one is set | no (BM25 alone without one) |
| `find_auto` | `find_auto`: the `--find-auto` hook's tool, hidden from the model | no |
| `label` | `label_file`: a closed rubric over every item of a file | yes |
| `browse` | `rank_elements`: a page's elements ranked for the next action | no (BM25 order without one) |
| `fetch` | `fetch_passages`: a web page's passages for a purpose | no model |
| `knowledge` | `search`, `read`, `pick`: search, read a page or local file, pick among many | no (BM25 without one) |
| `longdoc` | `ask_document`: a four-option question over one long local file, answered by Jev when sure (`points.longdoc`, opt-in) | Jev (without a key every question is handed back to the model) |

Clients: Claude Code (`claude mcp add`), Cursor (`.cursor/mcp.json`), Codex, Copilot, Hermes
Agent, or any MCP client.

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
