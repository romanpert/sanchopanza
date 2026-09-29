# The context archive inside OpenAI's Codex CLI

Status, 2026-09-29: **run, not verified.** Four `codex exec` checks (Codex CLI 0.158.0, model
`gpt-6-luna`, the owner's ChatGPT login; results in `results/check-*.json`) and **our trusted
hooks never ran in any of them**: the hook journals every call, even one it does not archive,
and not one line was written. What each attempt found, in order:

1. Setup, not Codex: with `CODEX_HOME` under `%TEMP%` the shared app-server's socket path is
   longer than `SUN_LEN` and Codex refuses to start; `--no-daemon` avoids the daemon (the
   runner now passes it). A window without `CODEX_HOME` set silently used the owner's own
   `~/.codex`, which is why `/hooks` first listed 0 hooks. Declaring the hooks in both
   `hooks.json` and `config.toml` loads them twice (Codex warns); one representation only.
2. Inside Codex's sandbox on Windows (`read-only`), `python` is not on `PATH`, a quoted
   interpreter path is mangled by the PowerShell wrapper, and a venv's `python.exe` cannot find
   its base interpreter (`No Python at '"C:\...\python.exe'`): the task never ran. A `.cmd`
   launcher fixed the first two, not the third.
3. With `sandbox_mode="danger-full-access"` (a diagnostic run; the task only prints a log) the
   tool ran and the agent answered the token correctly from its own history (the 10 KB log
   fits Codex's output limit), but the hooks still did not run.

Not established: whether `codex exec` skips user hooks, or whether the hook command (a venv
Python) failed to start before writing anything. The next check is one run with Codex's hook
debug logging on. Until then, the integration below is written and unit-tested, and nothing
about Codex in this folder is measured.

Sources are from reading `openai/codex` at `33a0f766a647208b471cfbcad889c67fd324ee04`. Paths
below are relative to `codex-rs/` in that tree.

## What was built

| File | What it does |
|---|---|
| `src/sanchopanza/harness/codex.py` | Hook bodies for Codex (`post-tool-use`, `session-start`) and generators for `.codex/hooks.json` and a `config.toml` fragment |
| `tests/test_codex_harness.py` | 26 offline tests: events shaped like the schema, archive written, `additionalContext` shape, fail-open, config parses |
| `make_task.py` | Writes the tiny task folder: `build_log.py` prints a 10,040-character log (10,272 with CRLF) holding one `RELEASE_TOKEN=RT-<8 hex>` line, with a new token on every run |
| `run_check.py` | The single check, gated behind `--i-am-authorised` |

The hooks:

- **PostToolUse.** Reads the event from stdin. The schema is
  `hooks/schema/generated/post-tool-use.command.input.schema.json`: `tool_name`,
  `tool_input`, `tool_response`, `tool_use_id`, `session_id`, `turn_id`, `cwd`,
  `transcript_path` and the rest. The hook writes the response text with
  `context.archive.write_entry` to `.sanchopanza/archive/<session>/codex-<tool_use_id>.txt`,
  plus a sidecar. When the text is at least 6,000 characters, it returns one line of
  `hookSpecificOutput.additionalContext` that gives the path, the `index_of` tokens (for the
  test log: `RELEASE_TOKEN=RT-…`) and says to read the file or call `search_archive`.
  - Results under 500 characters are not archived, because they would only dilute
    `search_archive`.
  - The hook's own `search_archive` results are never archived.
  - Every run appends a line to `.sanchopanza/codex-hooks.jsonl`. Both files are git-ignored
    by `keep_out_of_git`.
  - Any error prints `{}` and exits 0. Output is ASCII JSON and stdin is decoded as UTF-8, so
    the hook is safe on a cp1252 console.
- **SessionStart.** When the archive already holds entries, it returns a note of under 600
  characters: how many entries exist, where they are, and that `search_archive(query, k)`
  exists.
- **Config.** `python -m sanchopanza.harness.codex config` prints both files. The CLI module
  is not edited: that is the documented entry point, and no `sanchopanza codex-hook`
  subcommand was added. `project_files()` returns the text and writes nothing.
  - `hooks.json` has one `command` handler per event, no matcher, and `commandWindows` set to
    the same command.
  - `config.toml` holds `[mcp_servers.sanchopanza_archive]`, which runs `python -m
    sanchopanza archive-mcp --archive <root>`. It has a per-tool `approval_mode = "approve"`
    (read-only BM25; `codex exec` cannot prompt) and `output_token_limit = 2000`. It can also
    set `tool_output_token_limit`.

## What Codex allows today, with citations

| Question | Answer | Where |
|---|---|---|
| Where hooks live | `hooks.json` or `[hooks]` in `config.toml` of any config layer (`~/.codex`, `<repo>/.codex`, and so on). Having both in one layer gives a warning | `hooks/src/engine/discovery.rs:145-160`, `:340-345` |
| File shape | `{"hooks": {"PostToolUse": [{"matcher"?, "hooks": [{"type": "command", "command", "commandWindows"?, "timeout"?, "statusMessage"?, "additionalContextLimit"?}]}]}}` | `config/src/hook_config.rs:10-60`, `:161-185` |
| Trust | Non-managed hooks run only once trusted. Trust is a `trusted_hash` stored in `[hooks.state]`, set from the TUI `/hooks` view. Editing a hook makes it `Modified`, which counts as untrusted. `--dangerously-bypass-hook-trust` skips the check | `discovery.rs:713-719`, `:794-812`; `utils/cli/src/shared_options.rs:63`; `tui/src/bottom_pane/hooks_browser_view.rs:242-274` |
| Project `.codex/` | Loaded only for a trusted project (`[projects."<path>"] trust_level = "trusted"` in the user config), hooks included | `config/src/loader/mod.rs:1086-1103` |
| Windows | The hook command runs through `%COMSPEC% /C "<command>"` | `hooks/src/engine/command_runner.rs:387-411` |
| `additionalContext` | Recorded as a developer message right after the tool output. Past about 2,500 tokens it is spilled to a file (`additionalContextLimit`, `0` turns spilling off) | `core/src/hook_runtime.rs:849-873`; `core/src/tools/registry.rs:732-739`; `hook_config.rs:175-184` |
| Replace a tool's output | Not possible. `updatedMCPToolOutput` and `suppressOutput` are rejected. `decision: block` or `continue: false` replaces the output with a reason and stops normal processing | `hooks/src/engine/output_parser.rs:393-395`, `:431-435`; `core/tests/suite/hooks.rs:5484`, `:5544` |
| When PostToolUse runs | Only after a successful call. It also runs for tools called from code mode, but not for code-mode `wait` | `registry.rs:698-735`; `core/tests/suite/hooks.rs:4359`; `core/src/tools/code_mode/wait_handler.rs:224-233` |
| **What Bash's `tool_response` holds** | **A string that is already truncated to the model's output policy.** A process still running (`process_id` set) gets no hook until it completes | `core/src/tools/context.rs:438-445`, `:482-489` |
| MCP `tool_response` | The serialized `CallToolResult` (`content: [{type, text}]`) | `context.rs:179-181` |
| Output caps | `tool_output_token_limit` overrides the model's `truncation_policy`, which is 10,000 tokens for the listed models. Per MCP tool there is `[mcp_servers.X.tools.Y] output_token_limit` | `models-manager/src/model_info.rs:32-43`; `models-manager/models.json:15-18`; `config/src/mcp_types.rs:84-93`, `:447` |
| Compaction | Remote (server-side) compaction v2 for OpenAI models. No hook can edit earlier history | `core/src/compact_remote_v2.rs:81-134` |
| Models | Every listed model except `gpt-5.5` is `tool_mode: code_mode_only`. `gpt-6-luna` is described as "Fast and affordable model for easier tasks" | `models-manager/models.json` |
| `exec --json` | Emits `thread.started`, `item.*` (`command_execution`, `mcp_tool_call`, `agent_message`, …) and `turn.completed.usage` (`input_tokens`, `cached_input_tokens`, `output_tokens`, `reasoning_output_tokens`), taken from the thread's running totals. It emits **no hook events**. `exec resume <id>` continues a thread | `exec/src/exec_events.rs:11-73`, `:107-133`; `exec/src/event_processor_with_jsonl_output.rs:118-127`; `exec/src/cli.rs:151` |

### What this means for the archive

1. **Codex has no arrival cut.** A hook cannot swap a large result for a short one; it can only
   add a line after it. The context saving has to come from Codex's own truncation
   (`tool_output_token_limit`, and per-MCP-tool `output_token_limit`).
2. **The archive holds what the model saw, not more.** Codex truncates the Bash output before
   the hook sees it (`context.rs:438-445`). So with a low `tool_output_token_limit`, the
   elided middle is lost to both the model and the archive. The archive pays off at recall
   time: after a compaction (history the model no longer has), in a later session, or when the
   model would otherwise re-run a tool that is slow, costly or non-deterministic.
   - For MCP tools the hook gets the full `CallToolResult`, so a per-tool `output_token_limit`
     plus the archive is a real cut-and-keep. This part is unverified live.

### The least fragile integration

- Project `.codex/hooks.json` and `.codex/config.toml` from `project_files()`. The project must
  be trusted, and the two hooks trusted once under `/hooks`.
- Leave `tool_output_token_limit` at the model's default unless you accept that anything cut is
  gone.
- Use the `search_archive` MCP server for pull recall, and the SessionStart note for resumes
  and forks.
- Do not use `continue: false` or `block` to "replace" output: that halts the turn.
- Do not use `--dangerously-bypass-hook-trust` in normal use.

## The one check (`run_check.py`)

The check runs in an isolated `CODEX_HOME` (default `%TEMP%/sanchopanza-codex-check/codex-home`,
never `~/.codex`) and uses the same text `project_files()` produces. It refuses to go ahead
unless all of these hold:

- `--i-am-authorised` is passed;
- `codex login status` says **ChatGPT**; an API key login is refused, and `OPENAI_API_KEY` and
  `CODEX_API_KEY` are removed from the environment;
- both hooks are trusted in that home;
- the generated config has not drifted.

Owner steps (PowerShell):

```powershell
npm i -g @openai/codex        # or: npm install --prefix <dir> @openai/codex, then --codex <path>
.venv/Scripts/python.exe docs/results/2026-09-28-context-lean/codex/run_check.py    # free: writes home + task, prints the steps
$env:CODEX_HOME="$env:TEMP\sanchopanza-codex-check\codex-home"; codex login         # ChatGPT, browser
cd "$env:TEMP\sanchopanza-codex-check\task"; codex        # TUI: /hooks, trust both sanchopanza hooks, quit without a prompt
.venv/Scripts/python.exe docs/results/2026-09-28-context-lean/codex/run_check.py --i-am-authorised
```

It runs one thread in two turns, with `gpt-6-luna` at reasoning effort low and the `read-only`
sandbox:

1. `codex exec --json`: "run `python build_log.py` once; say whether the build succeeded; do
   not quote the log."
2. `codex exec resume <thread> --json`: "what was RELEASE_TOKEN? do not re-run."

Turn 2 is skipped if turn 1 used more than 400,000 input tokens. Each turn is killed after
300 s. The results go to `results/check-<time>.json`:

- `hooks_fired`, `session_start_note`;
- `archive_holds_true_token`, `log_archived_whole` (whether Codex cut the log before the hook);
- `additional_context_emitted`, `additional_context_in_rollout` (the marker found in the session
  rollout);
- `search_archive_called`, `tool_rerun` (a re-run prints a different token);
- `answer_correct`;
- turn usage, the last request's context size and the plan's rate-limit snapshot from the
  rollout.

The readers were exercised offline on a fabricated run: the real hook process wrote the
archive, and fake JSONL and rollout files stood in for Codex. No Codex process was started.

**Estimated usage (not measured).** About 80,000-130,000 input tokens across the 4-6 model
requests of the two turns, most of them cached after the first request, and 1,000-3,000 output
tokens. The biggest unknown is the size of Codex's system prompt plus its tools, which is
repeated on every request; the log itself is about 4,000 tokens. On a ChatGPT login this uses
the plan's usage window rather than a per-token bill, and the rollout's `rate_limits` shows how
much.

**What it can prove:**

- Codex on this Windows machine runs the trusted hooks through `cmd /C`.
- The archive receives the tool output, and whether that output was already truncated.
- The `additionalContext` line reaches the thread as a developer message.
- The MCP server starts and its tool is callable without a prompt.
- Whether the model chose `search_archive`, the context, or a re-run.
- The usage totals.

**What it cannot prove:**

- **Recall after compaction.** The 10 KB log fits the default 10,000-token output policy, so
  it stays in context and the answer can come straight from history. The rollout's
  `last_request_usage` from this run gives the context size needed to choose `--compact-at`
  (`model_auto_compact_token_limit`) for a second, separately authorised run that forces
  compaction before turn 2.
- Any saving. One run, one task, no comparison arm.
- Behaviour of other models, other tools, or MCP outputs cut by `output_token_limit`.
