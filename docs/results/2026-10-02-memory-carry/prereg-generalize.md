# Memory carry: other models, written before their data (2026-10-02)

The Sonnet 5.5 confirmation (`prereg-confirm.md`) passed. This file asks whether the effect holds
on the other models people run Claude Code with. Code, scenes and checks are those of the
confirmation's commit (fddff84), unchanged.

## Runs

- **Haiku 4.5** (`claude-haiku-4-5-20251001`): all 16 scenes (`--scenes all`), repetition 0, so
  16 pairs, with `--total-cap 8`.
- **Opus 5.5** (`claude-opus-5-5`): all 16 scenes, repetition 0, so 16 pairs. The cap is fixed
  from Haiku's and Sonnet's measured costs before it runs, and the owner is told the figure.

## Analysis, per model

- **Primary.** The same one-sided exact McNemar on `fact_kept`. With 16 pairs, "holds" means
  p < 0.05 in favour of `M`.
- **Reported:**
  - the count per arm;
  - tests and task, each with the confirmation's non-inferiority margin of 2;
  - the paired median cost ratio;
  - whether Claude Code's own auto memory saved anything.
- **Wording.** A model where `N` already keeps nearly every fact has little room to differ. That
  is reported as "no room", not as a failure of the memory.
- **Exclusions.** As in the confirmation: usage limit, or a session that ended before its result,
  means NOT RUN. No retries.

## Amendment 1 (2026-10-02, during the Haiku run, before any verdict)

The runner crashed reading Haiku's `legacy` M session 1. The stream had a `permission_denied`
event, from Haiku trying the PowerShell tool, which neither arm allows, and its `message` was a
string. This was a runner bug, not a session's end. The reader is fixed, with a test. The run
continues with `--continue`, which keeps the three pairs recorded and runs the cut pair (legacy
M) again whole.
