# W17 prereg (DRAFT, not sealed): the memory bridge on Sonnet 5.5

Status: draft for review. Nothing here is sealed and nothing has run live. The seal, the
independent review (`revisor-prereg`) and the owner's yes on the cost come first.

## Question

F2 (`docs/results/2026-10-16-memory-f2`) measured continuing a two-step feature in a new session.
On Sonnet 5.5, sanchopanza's memory (S, project-scope install) kept the plan in 48 of 48 triples,
and clean Claude Code with a bare "let's continue" (N0) in 4. N0 kept it exactly when Claude Code
had saved its own auto memory in session 1 (4 of 4, against 0 of 44).

The memory bridge (`harness.memory_native`, `install --memory-native`) writes the session's
records into Claude Code's own auto memory: one note, `sanchopanza-next.md`, and one line in
`MEMORY.md`, which Claude Code loads itself at the next start. At that start, the records the note
carries count as already given, so the hooks do not inject them again.

The index and the hooks' SessionStart text both land in the first user message, which is
cache-written afresh every session. Moving text into native memory therefore saves no cache cost
by itself. The bridge's claim is:

- the plan reaches the next session through Claude Code's own mechanism, with fewer hook tokens;
- and continuing still works as well as with S.

## Arms (one triple = one scene, one repetition, three arms one after the other)

| arm | what runs |
|---|---|
| N0 | clean Claude Code 2.1.287 (pinned); session 2 is the scene's `continue` line |
| S | N0 plus `sanchopanza install --memory --write` at **user** scope, into the arm's clean configuration folder (`--path <config>/settings.json`). At user scope the install registers no MCP server: it prints the `claude mcp add-json` line, and the runner does not run it. |
| SN | S plus `--memory-native` |

- **Same as F2:** the scenes (`memory_carry/scenes_handoff.py`, all 12), the checks (`task`,
  `fact`, `decision`, `intact`, the repository's tests), the call shape, the per-session cap, the
  seeded decoy rules, neutral folders, and the arm order rotated per triple.
- **Different from F2:** user scope instead of project scope, so nothing is installed in the
  repository. There is no H arm.

## Primary measure and the sealed rule

**Kept all** per arm: task, C and D all held.

1. **SN not worse than S:** SN − S on kept all, one-sided 95 % Tango score lower bound
   > −12.5 points (F2's margin).
2. **SN better than N0:** exact one-sided McNemar, p < 0.05.
3. **Cost, SN against S:** the paired median cost ratio per triple (Claude Code's list price plus
   Jev). Its bootstrap 95 % upper bound (10,000 draws over triples, seed 20261017) must be
   ≤ 1.05.
4. **Cost, SN against N0, for the final scoreboard's "gana":** the same ratio's upper bound must be
   ≤ 1.10.
   - Stated in advance: F2's S/N0 was 1.226 [1.141, 1.261].
   - Most of that gap is N0 asking instead of working (N0 session 2 median 0.044 USD, against
     0.072 for N0's 4 kept-all sessions 2).
   - Of the rest, 42 % is S's fixed first-message overhead: the rules block with 7 decoys, the
     skill listing, the MCP instructions.
   - So criterion 4 is expected to fail unless that overhead shrinks. The verdict is reported as
     it comes out.
5. **No harm:**
   - SN's repository tests within floor(0.125 × triples) of S's;
   - SN never writes outside its own note and line in Claude Code's memory folder: every other
     file in that folder must be byte-identical before and after each SN session, checked by the
     runner.

**Verdicts:**
- 1 and 2 hold: "SN keeps S's result".
- 1, 2 and 3 hold: "SN substitutes for S".
- 1, 2, 3 and 4 hold: "gana" against clean Claude Code.

**Stratum (reported, not deciding):** the bare-continue scenes. These are the three whose
continue line names no file that step 1 wrote: `h_judge`, `h_loud` and `h_merge`. There, F2's
record came only through the file touch. Report kept all and the injected characters per arm.

**Reported whatever the result:**
- characters S and SN inject per session, from the hook logs: rules at start, record at the prompt,
  record at a touch;
- the note's size, and whether session 2 read it (a tool call naming the memory folder);
- tokens per arm;
- Claude Code's own memory saves, per arm.

## Power and n

**w17-sonnet:** 12 scenes × 4 repetitions = 48 triples (144 arms).

**Criterion 1.** With 48 pairs and no triple won by SN alone, the Tango lower bound holds at −12.5
only while S wins at most 2 triples SN loses. The bounds are −5.3, −8.8, −11.8 and −14.6 for 0 to
3 such triples (`handoff_analyze.tango_bound`).

| SN's true chance to lose a triple S keeps | chance that criterion 1 holds |
|---|---|
| 2 % | 0.93 |
| 5 % | 0.57 |

With 36 triples the margin would allow only 1 such loss (−11.5), so 48 it is.

**Criterion 2.** F2 had 44 to 0 against N0, so it is powered at any n here.

**Pilot (w17-pilot):** 4 scenes × 1 repetition (12 arms), F2's pilot scenes. It gates the night
on the same conditions as F2's pilot gate, plus:
- SN wrote its note in every SN session 1;
- the next session logged `carried` with session 1's keys.

## Cost and caps (in code: `benchmarks/w17_native/run.py`)

**Expected, at Claude Code's list price, from F2's Sonnet medians per triple:** N0 0.105 USD, S
0.127 USD, and SN taken as S.

| run | arms | expected | hard cap | every arm at its reserve |
|---|---|---|---|---|
| w17-pilot | 12 | 1.44 USD | 12.0 USD | 30.56 USD |
| w17-sonnet | 144 | 17.23 USD | 26.0 USD | 366.72 USD |

- Total expected: about 18.7 USD, paid by the subscription (`claude -p`). That is above the
  10 USD line, so **the owner's yes is required before any launch**.
- Jev: about 0.0003 USD per arm (F2: 377 decisions for 0.012 USD).
- **Per session:** `--max-budget-usd 0.80`, plus one worst turn past it (0.44 USD: 200,000 tokens
  read, 50,000 written and 20,000 out at Claude Code's rates, `handoff.WORST_TURN`).
- **Per arm reserve:** 2 × (0.80 + 0.44) + 0.10 of Jev for S and SN.
- A run stops before an arm whose reserve could pass the cap.
- STOP file, a 429 means stop, the midnight rule, and kills by PID only, all as in F2
  (`tanda-de-pago`).

## Free evidence before any money (done, 2026-10-16)

`python benchmarks/w17_native/replay_f2.py --run f2-sonnet|f2-opus` replays the bridge's
decisions on F2's recorded S arms, with no model call.

- **Folder rule.** `native_dir` named the folder Claude Code's own `init` reported in 72 of 72
  arms (48 Sonnet, 24 Opus).
- **Sonnet.** The bridge would have written its note after all 48 sessions 1. Claude Code saved
  none of its own in S.
  - Note median 1,921 characters; index line 150.
  - In all 48 sessions 2 the record S injected would not have been given again: median
    2,170 characters (prompt or touch).
  - Net change per session 2: −2,020 characters (about −505 tokens) if the note is not read,
    and −143 characters (about −36 tokens) if the model reads it. In F2, Sonnet N0 read the memory
    file in all 4 sessions that had one, so expect the second case plus one tool turn.
- **Opus.**
  - Claude Code's own memory restated the plan in 8 of 24 sessions 1, by the coverage rule (at
    least 50 % of the request's words). There the bridge writes no note and skips S's record:
    median 2,875 characters.
  - Elsewhere it writes the note: 16 of 24 arms.
  - 31 of the 40 rules that sessions 1 stored were restated in Claude Code's own memory, a
    second injection that a rules dedupe could skip.
  - 21 Opus folders changed again in session 2, so this side is approximate.
- **Dry run of this runner.** `python benchmarks/w17_native/run.py --run w17-pilot --dry`:
  - built the 12 pilot arms: repositories, clean configuration folders, the user-scope install
    with its hooks rewired, and the decoys;
  - S and SN differ only by `SANCHOPANZA_MEMORY_NATIVE=1`.
  - SN's installed and rewired Stop hook, fed a synthetic session 1, wrote `sanchopanza-next.md`
    and its index line into `<config>/projects/<slug>/memory/`.

## Before sealing (open items)

- **Wire the live path** (`run.py` refuses anything but `--dry`).
  - Sessions and checks go through F2's `handoff.sessions_of`, `handoff.checks` and
    `handoff.brief`.
  - The S-arm break checks must drop F2's "MCP server connected" condition, since user scope
    registers none.
  - Add the folder byte-identity check (criterion 5) and the `carried` check (pilot gate).
- **Midnight rule and resume:** as F2 (`handoff.run_plan`), with these arms and reserves.
- **Review:** `revisor-prereg` against this file and the code. Then seal (sha256 + commit) and
  run from a detached worktree.
