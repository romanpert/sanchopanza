# guard-split: status (2026-10-06, built, not run end to end)

> **Historical.** A working note of 2026-10-06, kept as it was and moved here from the
> repository root on 2026-10-15; its state is superseded. Today's is the
> [final scoreboard](../results/2026-10-13-final/README.md) and the
> [roadmap](../ROADMAP.md).

Branch `guard-split` from main `7e75533`, worktree `../sanchopanza-guard-split`. Local only,
nothing pushed, not merged. No paid calls were made.

## Commits

- `a87508a` feat: split the guard's block over several SessionStart hooks, each under Claude
  Code's inline limit
- `d9572c0` test: split guard parts, hook files and install; offline-tested live probe (not run)
- docs: this file, README, CHANGELOG, docs/adapters.md, the guard-struct results README

## The premise, read in the installed binary (2.1.287, read only)

- `Pde(text, id, kind, {threshold = U3o})` with `U3o = 1e4`: `if (e.length <= s) return e`, else
  the text is written to disk and replaced by `I_e(...)`, the `<persisted-output>` notice with a
  2,000-character preview (`eAe = 2000`).
- The hook runner calls `Pde(ko.additionalContext, \`${s}-${po}\`, "additionalContext")` once
  per hook result and yields `{additionalContexts: [ur]}`: the cap is per hook command.
- `RY(session, "compact", ...)` (the SessionStart dispatch, called from the compaction code)
  pushes every `additionalContexts` into one list `Re` and builds one attachment
  `{type: "hook_additional_context", content: Re, hookEvent: "SessionStart"}`. No aggregate cap
  there (the per-dispatch cap `Nin`, 200,000, is for plugin `prompt.submit` only).
- Rendering: `hook_additional_context: (e) => ... \`${e.hookName} hook additional context:
  ${e.content.join("\n")}\``: one message, parts joined by a newline.
- Order: the hooks run concurrently through `wsn`, which yields with `Promise.race`, so the
  parts arrive in the order the commands finish. Hence "part i of N" on every part.

## Design

- `context/parts.py`: `split_calls` packs results in `structural.order` first-fit into K rooms
  (part 1's room is what the requests, trail and pointers leave; the others' is the cap minus
  their header), within GUARD_STRUCT_CHARS overall. A result never spans parts; one bigger than
  a part gets a pointer if re-readable, else is lost. K = 1 or no cap is today's block exactly.
  Raises if a part would exceed the cap.
- `structural.pack` replaces `choose`'s loop (`choose` is the one-room case); sizes count UTF-16
  code units (`structural.width`).
- `harness/guard_hook.py`: `--parts K` on PreCompact writes `<session>.part1..K.json` (empty past
  N); `--part i --parts K` on SessionStart reads and removes only its own file; missing or stale
  file: a single block kept by an older PreCompact goes to part 1 only, else the split is
  rebuilt from the transcript (pure, so all parts agree). Any error while splitting: the rule's
  block as part 1, nothing in the others. No `--part`: unchanged.
- `harness/install_guard.py`: PreCompact `guard-hook --parts K`, one SessionStart(compact) entry
  with K commands, PostToolUse unchanged. K = `default_parts` = 1 + ceil(struct / inline) = 6
  (part 1 spends about half its room on requests, trail and pointers); `--guard-parts K`, 1 for
  the single block. Any `sanchopanza guard-hook [--part...]` command is recognised as ours.
- `plan()` gained `guard_parts` as its last keyword (`tests/test_install_hooks.py` pin updated).

## Suite

`3165 passed, 42 skipped in 368.06s (0:06:08)`. Ruff clean on the changed files (the two
remaining findings, install.py:485 E501 and test_install_fetch.py:90 SIM300, are on main).

Offline wiring check (free): the probe's own settings run through Git Bash against a synthetic
transcript of 18 one-shot outputs: 6 parts of 5,748-8,161 characters, 17 of 18 results kept,
46,550 characters in all, the marker found in the last part, parts read in reverse order.

## The live probe (not run)

    PYTHONPATH=src .venv/Scripts/python.exe benchmarks/guard_split/probe.py              # free
    PYTHONPATH=src .venv/Scripts/python.exe benchmarks/guard_split/probe.py --run --cap 0.60

Haiku 4.5, three `claude -p` calls (18 Bash emits, `/compact`, one question), each under
`--max-budget-usd` of what is left of `--cap`; estimate 0.24 USD at list prices (0.15-0.40),
on the subscription (ANTHROPIC_* and CLAUDE_CODE_* dropped). Temp project, `--setting-sources
project`; HOME kept for the login. Passes when the attachment holds every part inline (no
`<persisted-output>`), as many as the guard's log says, and the model returns the hex after a
label taken from the last part.

## Open

1. Run the probe (an owner decision: it spends).
2. Unverified: whether `/compact` through `claude -p --resume` fires PreCompact and
   SessionStart(compact) there; the probe stops and says so if no boundary is in the transcript.
3. `benchmarks/adopt/analyze.py` counts `guard_blocks` per non-empty SessionStart output: with
   the split it would count parts. Sealed; not changed.
4. Six Python processes start at each compaction (about 0.2 s each here, concurrent).
