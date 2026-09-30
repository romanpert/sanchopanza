# Adoption study: development log

Development runs only (Haiku 4.5, subscription, list price). The held-out tasks have not been
run. Every number here is from development and does not count toward any confirmation.

## Pilot and round 1 (2026-09-30)

| chain | arm | resolved | list cost | compactions | notes |
|---|---|---|---|---|---|
| pygments-1 | N | 3/5 | 2.70 USD | 0 | request 2 spawned a subagent and hit the call cap |
| pygments-1 | S | 3/5 | 2.08 USD | 1 (161.7k, guard block attached) | one false shell denial (`rm -f` of its own scratch files) |
| starlette-1 | N | 4/5 | 1.86 USD | 0 | |
| starlette-1 | S | 4/5 | 1.90 USD | 1 (160.6k, guard block attached) | |

Same bugs resolved in every pair. Neither arm ever called `find_in_repo` or the skill: these
issues name the module or the function, and `Grep` finds it (what the skill itself says).

## What the pilot found in the harness and in sanchopanza, all fixed

- A resumed `claude -p` reports the session's cumulative cost: the first ledger counted 6.21 USD
  for 3.29 spent. Per-call cost is now the difference.
- A Docker pytest run that returned nothing was graded as every test failing; it now raises.
  Also, xargs turns pytest's exit 1 into 123.
- `runtests` had no extension: PowerShell treated it as a document and Windows asked the person
  at the desk which program should open it. A `runtests.cmd` goes first on PATH now.
- The agents saw sanchopanza's venv `python` on PATH and ran tests locally against it.
- **The shell guard judged a coding session as a research sandbox**: see
  `../2026-09-30-guard-coding/`. The default install now writes a coding profile.
- **The PowerShell tool was not guarded at all** (found by the adversarial review of the fix).

Declared: the S arms of round 1 ran the guard code as it was edited during the round (the
package is installed editable); the profile fix landed while they ran.

## Where the context goes, and why Haiku cannot show the budget lever

- Base context about 29k tokens; one hard request can add 90k (starlette request 2: 82 calls,
  40k to 128k), and every later request re-reads it.
- The 160k budget fires near the end of a five-bug chain on Haiku, whose own compaction would
  fire at about 167k anyway. The saving measured in the owner's real sessions (context re-read
  cost at 42 % with a 160k budget) lives in 1M-window sessions of 300k-400k tokens.

## Compaction at request boundaries: not buildable headless today (negative)

Replayed on the owner's 153 long sessions, compacting when a new request arrives with more than
100k in context, under a 200k budget, keeps the cost at 46 % of what it was (budget alone, 160k:
42 %) and cuts mid-request compactions from 938 to 333: the same saving, taken where a summary
loses least. Built as the function-hook module's trigger at `turn.complete` and at `turn.start`
(`benchmarks/adopt/probe_boundary.py`, four live probes, 0.19 USD): the hook fires and sees the
tokens, but `$.session.compact()` never resolves in `claude -p` 2.1.285 and nothing is compacted.
Reverted; not measurable in this benchmark. Untested in an interactive session.
