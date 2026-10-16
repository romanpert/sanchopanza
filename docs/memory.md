# Memory: carry work across requests, sessions and worktrees

Claude Code starts every session blank, apart from its own `CLAUDE.md` and auto memory files.
`sanchopanza install` adds a memory that the agent does not have to write. It works in three
steps:

- Each finished request is recorded by code, verbatim.
- The person's standing rules are kept in their own words.
- A later request is given back what bears on it: at a new session's start, at its first
  prompt, or when the agent opens a file that earlier work changed.

It is on by default since 2026-10-14. `--no-memory` leaves it out.

## What it won

Two pre-registered head-to-head tests, both on **Claude Sonnet 5.5** against clean **Claude
Code 2.1.287**, with a project-scope install and Jev deciding. "S" is Claude Code with
sanchopanza; the other arms are clean Claude Code. The memory cell is the scoreboard's one
"gana". F2 met its own sealed verdict, **S better than the bare line and not worse than the
handoff ritual**; its prereg seals no cost condition, and S cost more than the bare line, so on
the scoreboard it reads as that verdict, not as "gana".

| test | the task | S | the others | cost of S |
|---|---|---|---|---|
| [Memory cell](results/2026-10-13-memory-cell/) (2026-10-13) | Keep a fact said in a parallel session or a sibling worktree | fact broken in **0 of 24** pairs | clean Claude Code: 11 of 24 (McNemar p 0.00049) | 1.12x clean (median per pair) |
| [F2](results/2026-10-16-memory-f2/) (2026-10-16) | Continue a two-step feature in a new session with one line, "Let's continue with the shipping labels." | next step done in **48 of 48** triples | the owner's handoff ritual: 44 of 48 (S not worse by the sealed margin; 4 to 0, p 0.0625). The same line in clean Claude Code: 4 of 48 (McNemar p 5.7e-14) | 0.92x the ritual [0.85, 0.95], 1.23x the bare line [1.14, 1.26] (median per triple, descriptive bootstrap) |

- **Memory cell.** The gain is in the 4 of 8 scenes where the fact is not visible in the code.
  By scene, S won 4 and lost none.
- **F2.** In the handoff ritual, the person asks the old session for a prompt and pastes it
  into the new one. S replaced it with no loss shown, at lower cost, and beat the bare line by
  44 to 0 at a higher one. Every session in F2 that built step 2, in any arm, kept the
  constraint and the decision. So what S carried was **the plan**, not a forgotten
  constraint:
  - The bare line in clean Claude Code mostly stopped with a question or an offer (35 of its
    44 misses).
  - The ritual missed when its own handoff listed open choices and the new session stopped to
    ask about them.

## How it works

Five Claude Code command hooks, all `sanchopanza memory-hook`, are in
`src/sanchopanza/harness/memory_hook.py`. Taking F2's two sessions as the example:

**Session 1 ends (`Stop`, and again at `SessionEnd`).** The hook reads the transcript and
writes one record per finished request (`context/episodes.py`). The record is built by code, and
no model writes or summarises it. It holds:

- the person's prompt, verbatim, up to 1,000 characters;
- the agent's final message, verbatim, up to 1,200 characters;
- the files the request changed and the files it read (up to 12 each), and its last test run;
- a few lines of one-shot command output (up to 800 characters);
- prints of the lines it wrote. These are never shown; they let a later Read say whose code
  it is looking at.

There is no separate "plan" field. In F2 the plan ("Step 2, in the next session:
ship_all(...)") reached session 2 because it was in session 1's prompt, and the record keeps
the prompt verbatim.

Then, with a decider, comes **rule extraction** (`memory_rules.py`). Each sentence of the
prompt (20 to 400 characters, up to 16) is asked one question: is it a standing rule or fact
about the project that later sessions must keep? The question is asked of Jev, one decision
per sentence. Sentences at 0.5 or above go into the project's `rules.json`, verbatim, with
when they were said and the files being changed. Only the prompt's text is read, never tool
output or files.

- In F2 this stored 1 to 3 sentences in every S arm: the constraint, and in most scenes also
  the decision about step 2.

**Session 2 starts (`SessionStart`).** The newest standing rules are given as context before
the first prompt:

- at most 8, within 1,800 characters, newest first;
- under a header saying that the newer of two conflicting rules stands.

That is what put the constraint, and usually the decision, in front of session 2.

**Session 2's first prompt (`UserPromptSubmit`).** This runs at a session's first live
request, and again after a compaction has taken every earlier request out. Only records that
are not already in the conversation are candidates.

1. BM25 proposes up to 5 of the project's records.
2. **A name gate, by code.** A record that changed files passes only if the prompt names one of
   them: its base name, or its stem of 4 characters or more as a whole word, in any case.
   "Let's continue with the shipping labels" names `app/labels.py`, which session 1 created.
   A record that changed nothing (a question, an investigation) skips this gate. When no
   candidate passes, the decider is not asked.
3. Jev is asked, in one call, one question per candidate: "Is the new `request` about the same
   code as earlier record R*i*, so that what was found or changed there helps with it?" It
   reads each record's 880-character page (files, request and outcome).
4. The records at **0.8** or above are injected whole, oldest first, within 6,000 characters.
   A closing line says they are not new instructions and that the files on disk are the
   current truth.

In F2 this path gave session 1's record in 36 of 48 Sonnet arms and 18 of 24 Opus arms: the
nine scenes whose line names a file step 1 wrote. In the other three scenes the line names no
such file ("currency work" for `app/fx.py`, "subscriber import" for `app/subscribers.py`,
"ticket triage" for `app/tickets.py`). There the gate let nothing through, and the record came
by the touch.

**When the agent opens or changes a file (`PostToolUse`, "the touch").** The touch runs on
Read, Edit, MultiEdit, Write and NotebookEdit, and on a shell command that writes a file. It
gives the record of the earlier request that changed that file (`memory_touch.py`):

- at a Read, the record whose written lines are in view;
- at an edit, the record whose lines it edits, else the newest.

It gives one record per touch, and each record once per session until the next compaction.
It asks no model; a touch takes about 0.17 s
([memory on real sessions](results/2026-10-01-memory-real/)). A shell read (`cat`, `sed -n`,
`grep`) gives nothing by design. In F2 the touch delivered the record in the arms the prompt
gate held back, at a Read of a step-1 file or at the first shell command that wrote one. So
every S arm had session 1's record in session 2.

**Where it is kept.** The store is `~/.sanchopanza/memory-store/<repository>/`, keyed by the
git repository the session started in. Sibling worktrees therefore share one store, which is
the memory cell's case. A session killed before its `Stop` is caught up at a later prompt (up
to 3 recent sessions of the project).

## What it costs

- **Model calls.** The touch and the recording call no model. With a decider, a session makes
  a few Jev decisions: one per sentence of each new prompt at `Stop`, and at most one call at
  the first prompt. In F2 that came to 377 decisions over 48 Sonnet triples, 0.012 USD in all,
  with 0 failures. In the memory cell it was 243 decisions over 24 pairs, 0.008 USD.
- **Tokens.** The injected text is capped at 1,800 characters of rules per session start and
  6,000 characters per recall or touch.
- **Per task, F2 on Sonnet 5.5.** The median cost per triple was 0.127 USD with memory, 0.142
  USD with the handoff ritual, and 0.105 USD with the bare line. The bare line is cheapest
  partly because it mostly did not do the work.
- **Memory cell.** 1.12x clean Claude Code per pair (median).
- **Time.** Session 2's median wall time in F2 was 26.8 s with memory, 26.75 s with the
  ritual and 20.4 s with the bare line. The prompt's decider call waits at most 15 s, then injects nothing.

## Without a decider

Without `TYPESAFE_API_KEY` or a provider, memory still records every request and the touch
still works, both by code. It drops three things:

- the standing rules;
- recall at the prompt, which is off because BM25 alone gives too many unrelated records at
  real session starts ([memory on real sessions](results/2026-10-01-memory-real/));
- the decider's judgment.

Neither test was measured this way. Both ran with Jev.

## When it does not help

- **Opus 5.5 with Claude Code's own auto memory.** In F2, Opus saved its own memory after
  every session 1, in every arm. Memory kept 22 of 24 and clean Claude Code with the bare line
  21, at 1.105x the cost. In the memory cell's gate, Opus left no room either. On Opus, memory
  adds cost and no measured gain; `--no-memory` saves it.
- **Facts already in the code.** In the memory cell, clean Claude Code kept every fact that
  the repository already showed (a logging habit, a naming style, a prefix). Memory tied
  there.
- **Web and code benchmarks.** The other scoreboard cells were measured without memory
  ([final scoreboard](results/2026-10-13-final/)). Nothing here says memory helps them.

## You can skip the handoff prompt, on Sonnet 5.5

F2 supports this for one setup only: Sonnet 5.5, clean Claude Code 2.1.287, a project-scope
install with a TypeSafe key. With that setup, starting the new session with one line that
names the work ("Let's continue with the shipping labels.") was not worse than pasting a
handoff from the old session by the sealed margin: 48 of 48 against 44 of 48 (4 to 0, p 0.0625,
so a gain over the ritual is not shown), at 0.92x its cost [0.85, 0.95]. It took no extra
request and no paste.

What F2 did not test:

- **A bare "continue."** By the code above, a line that names no file earlier work changed
  gives no record at the prompt, and the agent then gets one only when it opens or writes such
  a file. Naming the feature, or the module, is the safer habit.
- **A plan longer than the record keeps.** The record keeps the prompt up to 1,000 characters.
  Every F2 prompt was under 760.
- **Real use.** F2 ran headless, in a clean Claude Code configuration (no `CLAUDE.md` or
  settings of your own), with nobody answering the agent's questions.

On Opus 5.5 the ritual scored lowest (17 of 24, against 21 for the bare line; 1 to 5, p 0.11,
not shown): a fresh session stopped to ask the open questions the handoff listed.

## Turn it off or tune it

- `sanchopanza install --no-memory --write` takes the five hooks out.
- Environment variables, in the shell or in the settings' `env`:
  - `SANCHOPANZA_MEMORY_SELECT=off` records only, with no recall and no touch.
  - `SANCHOPANZA_MEMORY_RULES=off` drops standing rules.
  - `SANCHOPANZA_MEMORY_PROMPT=off` drops recall at the prompt.
  - `SANCHOPANZA_MEMORY_TOUCH=off` drops the touch.
- `SANCHOPANZA_MEMORY_RULES_AUDIT=on` turns on the Stop audit, which is off by default. It holds
  a request's diff against the stored rules and sends a confident break back once. Off because
  none of its send-backs on the maintainer's real sessions was right
  ([memory Stop](results/2026-10-14-memory-stop/)).
- The full list is in `memory_hook.py`'s docstring.

### Into Claude Code's own memory (`--memory-native`, opt-in, not measured live)

`sanchopanza install --memory --memory-native --write` also writes each session's last records
into Claude Code's own auto memory. It adds one note, `sanchopanza-next.md`, marked as ours in its
front matter, and one exact line in `MEMORY.md`. Claude Code loads that line itself at the next
start and reads the note when it chooses to.

- **What it is for.** The plan reaches the next session through Claude Code's own mechanism. It
  works with anything that reads that folder, it stays there if sanchopanza is off, and it
  composes with the memory Claude Code saves itself.
  - When Claude Code saved the plan itself during the session, no note is written.
  - That needs a memory of its own written in that session that restates the request and that
    the session wrote or that names a changed file.
- **What it costs.** It saves nothing. A replay of F2's recorded sessions on Sonnet 5.5 shows the
  bridge adds tokens to S:
  - about +38 per new session for the index line when the note is not read;
  - about +524 when it is, plus one tool turn.
  - The prompt still gets the record as before. After the session reads the note whole, a file
    touch does not repeat it.
- **What it never does.**
  - It never changes, moves or removes a line or file it did not write.
  - It stays off where Claude Code's memory is moved (`autoMemoryDirectory`, the cowork
    override) or off: `autoMemoryEnabled: false`, `CLAUDE_CODE_DISABLE_AUTO_MEMORY`, simple,
    safe and remote modes.
  - It leaves a full, read-only, linked or non-UTF-8 index alone.
- **Turning it off.** Run `install` without `--memory-native` (or with `--no-memory`). That
  removes only our marked notes and our exact lines, and says which.
- **A change that comes with it.** The memory gate (`memory_gate.memory_dir_for`) now finds the
  memory folder as Claude Code derives it: the canonical git root under the configuration folder,
  or the folder settings move it to. It used to take the transcript's folder. For a session
  started in a subfolder or a worktree, these are now the same folder Claude Code uses.

## What is stored, and what leaves the machine

- **On disk.** The store is `~/.sanchopanza/memory-store/<repository>/`, outside the project.
  Its files are readable by this user only (mode 600 where the file system has modes).
  - Records hold prompts, the agent's final messages and lines of command output, verbatim.
  - Secret-looking strings are masked before a record is written.
  - Records older than 30 days are removed when a newer record is saved.
  - The standing rules (the 60 newest) are in `rules.json` in the same folder. Today that
    cleanup also removes `rules.json` when the file has not been rewritten for 30 days.
  - Deleting the folder forgets the project.
- **Sent to the decider (TypeSafe's Jev), with secrets redacted:**
  - at `Stop`, each sentence of the prompt with up to 1,500 characters of the prompt around it;
  - at a first prompt, the prompt and up to 5 record pages (files, request and the agent's final
    message, 880 characters each).
  - Command output is not in a page.
  - `SANCHOPANZA_MEMORY_WINDOW=long` sends whole records instead, opt-in. Measured on 905
    SWE-chat first requests with jev-1.13.0, it gave a related record more often (+12.7 points
    [+6.3, +19.8]) and a record where nothing was related more often too (+3.7 [+1.5, +6.2]),
    past the sealed guard: "peor en ruido", so the hook stays on the short window
    ([memgate-hook](results/2026-10-16-memgate-hook/README.md)).
- **Never shown to the agent:** the line prints, the index and the per-session state.

## Limits of the evidence

- **Our scenes.** There were 8 scenes in the memory cell and 12 in F2, synthetic, with
  in-repository checks. Repetitions of one scene are correlated, so the evidence is 8 and 12
  scenes, not 24 and 48 independent trials. In F2, S beat the bare line in 12 of 12 scenes and
  the ritual in 3, losing none.
- **Headless, one prompt per session.** A session that asks a question counts as not done. In
  real use a person answers, and the ritual and the bare line would recover part of their
  misses.
- **One draw per triple**: four repetitions on Sonnet and two on Opus.
- **One setup.** Sonnet 5.5 for both tests, clean Claude Code 2.1.287, a project-scope install,
  Jev (`jev-1.13.0`) deciding, and 7 decoy rules in the store. The user-scope install (the
  README's `sanchopanza install --write`) and later Claude Code releases, whose auto memory may
  change, were not run.
