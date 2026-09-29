# Candor: hold an agent's report against what it did

An agent's own "done" is the weakest signal in a loop. Among failed runs, 36 % (tau2-bench) to
76 % (AppWorld) still claim success (arXiv 2606.09863). Agents that skip files they were asked
to review say otherwise in 80 % of those runs (arXiv 2609.20812). `sanchopanza.candor` checks
the report against a record of the actions. When the two contradict each other, it can hold
every further tool call until a person has looked.

Measured in two pre-registered rounds of real Claude Code sessions
([results](results/2026-09-29-candor/)), the second on data the rules had never seen:

| | Result |
|---|---|
| Misstated reports stopped (model-written misstatements, real actions) | **96 %** (176/183) |
| Honest sessions stopped | **0 of 111** |
| Real misreports stopped | 9 of 12 overall; **9 of 9** on tasks the rules were never shaped on |
| Model cost of the lock | **none**: it is code |
| Jev as a second opinion, AUC | **0.98**, against 0.68 for Claude Haiku 4.5 on the same question, at about 1/40 of the cost (233 ms against 860 ms) |

The first round's hypotheses mostly failed, and that round is reported in full too.

## How it works

1. **The ledger is built by code.** Every tool call is recorded by the hook with its outcome.
   A test run is parsed for pass or fail, and every call is classified by its effect: read,
   write, delete, external, test, secret, or tamper. No model reads raw tool output to decide
   what happened, because that output is where an injection aimed at a monitor lives.
2. **The report states its claims in four lines.** The agent is asked to end with them:

   ```
   STATUS: done | partial | blocked
   TESTS: pass | fail | not run
   TEST_FILES_CHANGED: yes | no
   FILES_READ: <paths>
   ```

   This is what makes the check work. With the prose alone, the same rules stopped 25 % of the
   misstatements; with the block, 96 %.
3. **Deterministic rules compare claims with the ledger.** They raise:
   - a false success;
   - a denied edit or deletion;
   - a claimed test run, push or deletion that never happened;
   - a file cited or listed as read that was never read;
   - an input the task named, never read, replaced in silence;
   - a test edit behind a success claim that the report does not mention;
   - a consequential action (a delete, a push, a secret read) the report does not mention;
   - a change on disk that no tool call explains (with snapshots on);
   - any touch of the hooks, the settings, the permissions or the trace.
4. **Jev gives a second opinion (optional).** One closed question: does the report misstate what
   the ledger shows? It can only add a `high` note. It never approves anything and never
   engages the lock.
5. **The lock is sticky.** A `critical` finding engages it (or `high`, if you choose). From then
   on, PreToolUse refuses every tool call. It is pure code over a local file, and it fails
   closed. A person releases it with `python -m sanchopanza.candor release --by NAME --why
   TEXT`, and the release is recorded with who and why.

## Use it

In code, over any agent's turn record:

```python
from sanchopanza.candor import check_record, judge_record, should_lock

findings = check_record({
    "task": "Fix the failing tests.",
    "said": "Fixed. All tests pass.\nSTATUS: done\nTESTS: pass\nTEST_FILES_CHANGED: no",
    "did": [{"tool": "Edit", "target": "src/pager.py", "ok": True},
            {"tool": "Bash", "target": "python -m pytest", "ok": False,
             "result": "1 failed, 2 passed"}],
})
# [{'severity': 'critical', 'rule': 'false_success', ...}]
should_lock(findings)  # True
```

`judge_record(record, squire)` adds the Jev layer through a `Squire`, which brings its own
budget and journal. With no key, or on any error, it returns exactly what `check_record`
returns.

In Claude Code, as a command hook on `UserPromptSubmit`, `PreToolUse`, `PostToolUse`,
`PostToolUseFailure` and `Stop`:

```
<python> -m sanchopanza.harness.candor_hook
```

It is configured by environment:

| Variable | Values |
|---|---|
| `SANCHOPANZA_CANDOR_MODE` | `lock` (default) or `observe` |
| `SANCHOPANZA_CANDOR_LOCK_ON` | `critical` or `high` |
| `SANCHOPANZA_CANDOR_JUDGE` | `1` for the Jev layer |
| `SANCHOPANZA_CANDOR_SNAPSHOT` | `1` to diff the workspace between the prompt and the stop |

`python -m sanchopanza.candor status` shows what engaged the lock, with each claim beside the
action it contradicts.

Ask for the status block in your system prompt or CLAUDE.md. Without it, candor still checks
the prose, but catches far less.

## What it is not

- **It is not a defence against an agent that sets out to beat it.** Adaptive attacks break
  LLM monitors (arXiv 2510.09462: a GPT-4.1 monitor scored all 375 backdoored samples as safe
  once the agent wrote to it). The rules here are public, so a report can be written around
  them.
- **It sees what the hooks see.** A script's side effects appear only as a snapshot diff.
- **It has a race with parallel calls.** Tool calls issued in parallel within one turn can pass
  before the lock engages; from the next turn on, everything is refused. Seen in 1 of 6 lock
  sessions.
- **Its evidence is narrow.** Twelve small tasks. The misstatements were written by a model on
  instruction. The natural misreports (18 over both rounds) were almost all one kind: an input
  that did not exist, replaced in silence.
- **Humans rubber-stamp prompts.** Users approve 93-97 % of permission prompts, and catch fewer
  of them as a session goes on. The lock is only worth what the release is worth: read the
  claim and the action side by side before releasing.
