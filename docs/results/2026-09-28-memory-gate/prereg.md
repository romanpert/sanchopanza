# Pre-registration: a recall gate for Claude Code's auto memory

Written 2026-09-28, before any decision of the gate was asked and before any baseline number
below was computed. `prereg.sha256` holds the sha256 of this file (LF line endings) and
`tests/test_memory_gate_bench.py` fails if it changes. `benchmarks/memory_gate/run.py --live`
refuses to spend while the hash does not match.

## Question

Claude Code keeps auto memory as one fact per file in `~/.claude/projects/<project>/memory/`
and loads only the head of the index `MEMORY.md` at session start; the model has to decide by
itself to `Read` a memory file. Does a `UserPromptSubmit` hook that judges every memory file
against the prompt (`src/sanchopanza/harness/memory_gate.py`) put the memories a prompt needs
in front of the model, with less text than injecting them all, and better than BM25?

## Data (free, local, never published)

- Every project under `~/.claude/projects/` with at least **8** memory files (index excluded)
  and at least one top-level transcript. Every first-level user prompt of those transcripts
  (sidechains, meta entries, slash-command wrappers, tool results and interruptions excluded)
  is a case, if at least one memory file was already born at the prompt (first evidence of a
  file: its creation time, or its first `Write`/`Edit` in any transcript of the project).
- Labels, defined in `benchmarks/memory_gate/labels.py` and not changed after this file is
  hashed: a memory is RELEVANT to a prompt if, in the next 12 assistant blocks before the next
  prompt, the assistant `Read` it (label *read*) or used in its own text or tool input a
  distinctive token of it (identifier-shaped, >= 6 characters) that is in no other memory, the
  index, the project's CLAUDE.md, the prompt, the session before the prompt, or any tool result
  earlier in the window (label *quoted*). A memory written or edited in the window is not
  labelled for that prompt.
- Everything built lives in `~/.cache/sanchopanza/memory_gate/`, with secrets redacted by
  `sanchopanza.redact.redact_secrets`. Committed files carry aggregates only, and project
  names only as a 10-character sha256 prefix.
- Memory contents are those on disk at build time, not at the prompt: a declared limitation.

## Arms

All share one renderer (`memory_gate.render`, a memory's body cut at 3,000 characters).

| arm | what is injected | cap |
|---|---|---|
| `nothing` | nothing (status quo: the index head only) | - |
| `all` | every available memory, in file-name order, while it fits | 25,000 characters |
| `bm25@k`, k = 1, 3, 5 | the k best BM25 scores (query = prompt, document = name, description, body), score > 0 | 10,000 |
| `triage` | `Squire.triage_pages` / `triage_many` with the prompt as purpose, kept memories most probable first | 10,000 |
| `gate` | `triage`, but nothing when `Squire.needs_recall` says the prompt is self-contained | 10,000 |

Shipped thresholds, unchanged: `act` 0.75 (recall skips at p <= 0.25), `pages_in_context`
0.40, `pages_first_round` 0.18. Provider `jev`, model pinned `jev-1.13.0`. For every sampled
case both the recall call and the triage calls are made, so `triage` and `gate` come from the
same answers. `check_conflicts` is off.

## Sample for the live run

All cases if there are at most 300. Otherwise, with `random.Random(20260928)`: up to 150 cases
with at least one relevant memory and fill to 300 with cases without, each drawn from the
case list sorted by (project hash, session hash, prompt index). The runner prints the
estimated cost first and refuses when it exceeds `--max-usd` (default 0.50 USD); the squire's
own budget is set to the same cap, and a run that hits it is reported as incomplete.

## Metrics

On the sample, per arm:

- **recall**: relevant memories injected (shown in full or cut, not only named) / relevant
  memories, over all cases (micro). Also by label kind (*read*, *quoted*).
- **complete**: share of cases with a relevant memory in which every relevant one is injected.
- **chars**: mean characters injected per prompt, over all cases.
- **precision**: relevant injected / injected, micro.
- **quiet**: share of cases with no relevant memory in which nothing is injected.

## Criterion (all four must hold to call it confirmed)

1. `gate` recall >= `bm25@3` recall + 0.05.
2. `gate` chars <= 50 % of `all` chars.
3. `gate` recall >= 0.60.
4. `gate` quiet >= 0.50.

Reported whatever the outcome. No threshold moves on this sample. `triage` against `gate`
(what the recall skip costs and saves) and every `bm25@k` are descriptive.

## What this does not measure

- Whether injecting a memory changes what the agent does. Labels come from the agent's own
  behaviour without the gate: a *read* label marks a memory the status quo already found, so
  the gate's value is where it injects what was needed and not read. That is bounded only by
  the *quoted* labels, a lexical proxy.
- One machine, one user, sessions of one month; memory contents at build time.
- `chunks.CONTRIBUTES` was written for factual questions; a memory that is an instruction
  ("never add AI co-authorship") is judged with it unchanged.

## Amendment 1 (2026-09-28, before any arm was scored)

The first version of this file was hashed as
`8afacd8b73997cfd84825d2f2c63d529abd1e1a7f125aa226b2215fb522c1253`. The build was then run
once with `--estimate`, which prints label counts and nothing about any arm. Those counts
showed the *quoted* proxy was mostly noise: 664 of 667 labels were *quoted*, and the most
frequent evidence tokens were `dev/null` (84), a git branch name that reaches the model
through the system prompt (73), `s.replace`, `node_modules`, `run_in_background`,
`WebFetch`, `python.exe`. None of them is evidence that a memory was recalled. Only 6 *read*
labels exist in 550 prompts: the model almost never opens a memory file, which is the
defect this gate is for, and it also means the *read* label cannot carry the measurement.

Two filters are added to the *quoted* label, in `labels.recallable_tokens`, and nothing else
changes:

1. **General vocabulary**: a token the assistant wrote (text or tool input) in two or more
   *other* project directories under `~/.claude/projects/` (directories that differ only by
   case are one project) is not distinctive.
2. **Older than the memory**: a token the assistant wrote in this project before the memory's
   first evidence of existence (creation time, or first `Read`/`Write`/`Edit` of it) came from
   somewhere else.

Birth evidence now also counts the first `Read` of a file, not only its first `Write`/`Edit`
(a file read at t existed at t). The sample rule, arms, metrics and criteria are unchanged.

## Amendment 2 (2026-09-28, before any arm was scored)

Amendment 1 was hashed as
`48ad0d3be7347f922db1c084dbc9a0156674b94fab34dba5ed1da7ea73b977a1`. One more `--estimate`
build, which again prints only label counts, was inspected together with the list of evidence
tokens (never with any arm). The labels fell from 667 to 342, but the git branch name still
carried 75 of them, and generic git/GitHub vocabulary (`rev-list`, `hash-object`) survived
the two-project rule. Two changes, and they are the last before scoring:

1. **Environment**: the session's working directories and git branches (the `cwd` and
   `gitBranch` fields of its entries, both slash styles) count as text seen before the prompt.
   They reach the model through the system prompt, which the transcript does not hold.
2. **General vocabulary** now means used by the assistant in **one** or more other projects,
   not two.

Result on the build of this date: 551 prompts, 137 with a relevant memory, 225 relevant
(prompt, memory) pairs out of 32,521 (base rate 0.69 %), 3 of them *read* labels. The
remaining evidence tokens are project identifiers (file paths, module names, service names).
The labels are now a conservative bound: a recall that uses only words and no identifiers is
not counted, and a memory about a second project loses the tokens that project also uses.
